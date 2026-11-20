"""ITC three-way reconciliation (books vs IMS/2B vs payments), recommended IMS actions, supplier score."""
import json
from datetime import date
from . import db, calc, rules, portal_read
from .util import today, now_iso, fmt, add_days, audit, normalize_invoice_no

ELIGIBLE_IMS = ("no_action", "accepted")


def pull_ims(biz, period):
    """Pull IMS/2B records for the period from the mock portal into portal_2b_records."""
    data = portal_read.get(f"/ims/{biz['gstin']}/{period}")["records"]
    seen = set()
    for r in data:
        ex = db.one("SELECT id FROM portal_2b_records WHERE business_id=? AND portal_ref=?", (biz["id"], r["id"]))
        vals = dict(period=period, supplier_gstin=r["supplier_gstin"], supplier_name=r["supplier_name"], invoice_no=r["invoice_no"],
                    invoice_date=r["invoice_date"], taxable_value=r["taxable"], cgst=r["cgst"], sgst=r["sgst"], igst=r["igst"],
                    ims_status=r["ims_status"], pulled_at=now_iso())
        if ex:
            db.update("portal_2b_records", ex["id"], **vals); seen.add(ex["id"])
        else:
            seen.add(db.insert("portal_2b_records", business_id=biz["id"], portal_ref=r["id"], **vals))
    return len(data)


def _book_dict(inv, gstin):
    return {"id": inv["id"], "gstin": gstin, "inv_no": inv["invoice_no"], "date": inv["invoice_date"], "taxable": inv["taxable_value"],
            "tax": inv["cgst"] + inv["sgst"] + inv["igst"], "inv": inv}


def _portal_dict(p):
    return {"id": p["id"], "gstin": p["supplier_gstin"], "inv_no": p["invoice_no"], "date": p["invoice_date"], "taxable": p["taxable_value"],
            "tax": p["cgst"] + p["sgst"] + p["igst"], "rec": p}


def _gstin_status(g):
    try:
        r = portal_read.get(f"/taxpayer/{g}")
        return r.get("status")
    except Exception:
        return None


def reconcile_itc(biz, period, refresh=True):
    """Matches purchases (registered suppliers, not RCM) against IMS/2B for a monthly period. Returns summary dict."""
    if biz["gst_scheme"] == "composition":
        return {"period": period, "items": [], "itc_at_risk": 0, "skipped": "composition scheme: no ITC"}
    if refresh:
        pull_ims(biz, period)
    ru = rules.RuleUse(today().isoformat())
    pay_days = ru.get("gst.itc.payment_days")
    purchases = db.q("""SELECT i.*, p.gstin pgstin, p.name pname, p.id pid FROM invoices i JOIN parties p ON p.id=i.party_id
                        WHERE i.business_id=? AND i.direction='purchase' AND i.period=? AND i.is_reverse_charge=0 AND i.status='posted' AND p.gstin IS NOT NULL""",
                     (biz["id"], period))
    books = [_book_dict(i, i["pgstin"]) for i in purchases]
    portal_recs = [_portal_dict(p) for p in db.q("SELECT * FROM portal_2b_records WHERE business_id=? AND period=?", (biz["id"], period))]
    res = calc.reconcile(books, portal_recs)
    keep_ids, out = [], []
    for r in res:
        b, p, st = r["book"], r["portal"], r["status"]
        inv = b["inv"] if b else None
        rec = p["rec"] if p else None
        at_risk, action, reason = 0, "accept", ""
        party_id = inv["pid"] if inv else None
        if not party_id and rec:
            pp = db.one("SELECT id FROM parties WHERE business_id=? AND gstin=?", (biz["id"], rec["supplier_gstin"]))
            party_id = pp["id"] if pp else None
        paid = 0
        if inv:
            paid = (db.one("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE invoice_id=?", (inv["id"],)) or {"s": 0})["s"]
        if st == "matched":
            if rec["ims_status"] == "accepted":
                action, reason = "none", "Already accepted in IMS."
            elif rec["ims_status"] in ("pending", "rejected"):
                action, reason = "accept", f"IMS status is {rec['ims_status']}: accept to claim credit."
                at_risk = b["tax"]
            else:
                action, reason = "accept", "Matches your books; accept in IMS."
            if inv and (date.fromisoformat(today().isoformat()) - date.fromisoformat(inv["invoice_date"])).days > pay_days and paid < inv["total"]:
                action, reason, at_risk = "reverse_itc", f"Supplier unpaid beyond {pay_days} days: ITC must be reversed. Pay the supplier.", b["tax"]
                st = "payment_overdue"
        elif st == "missing_in_2b":
            action, at_risk = "hold_itc", b["tax"]
            reason = "Not in GSTR-2B: supplier has not filed or used another GSTIN. Do not claim ITC this period; nudge the supplier."
        elif st == "missing_in_books":
            action = "pending"
            reason = "Appears against your GSTIN but is not in your books. Confirm with the supplier before accepting."
            if _gstin_status(rec["supplier_gstin"]) == "cancelled":
                action, reason = "reject", "Supplier registration is cancelled: reject this record."
        elif st == "value_mismatch":
            action, at_risk = "pending", abs(b["tax"] - p["tax"])
            reason = f"Value differs: books {fmt(b['taxable'])} vs supplier {fmt(p['taxable'])}. Claim the lower amount; ask supplier to amend."
        elif st == "gstin_mismatch":
            action, at_risk = "pending", b["tax"]
            reason = "Supplier filed against a different buyer GSTIN than yours."
        ex = None
        if inv:
            ex = db.one("SELECT * FROM reconciliation_items WHERE business_id=? AND period=? AND invoice_id=?", (biz["id"], period, inv["id"]))
        if not ex and rec:
            ex = db.one("SELECT * FROM reconciliation_items WHERE business_id=? AND period=? AND portal_2b_record_id=?", (biz["id"], period, rec["id"]))
        vals = dict(business_id=biz["id"], period=period, invoice_id=inv["id"] if inv else None,
                    portal_2b_record_id=rec["id"] if rec else None, party_id=party_id, match_status=st,
                    itc_at_risk=at_risk, recommended_action=action, reason=reason, updated_at=now_iso())
        if ex:
            if ex["match_status"] != "matched" and st == "matched" and ex["itc_at_risk"] > 0:
                audit(biz["id"], "agent", "itc", "itc_recovered", "reconciliation_item", ex["id"], None, {"amount": ex["itc_at_risk"]})
            db.update("reconciliation_items", ex["id"], **vals); rid = ex["id"]
        else:
            rid = db.insert("reconciliation_items", **vals)
        keep_ids.append(rid)
    for old in db.q("SELECT id FROM reconciliation_items WHERE business_id=? AND period=?", (biz["id"], period)):
        if old["id"] not in keep_ids:
            db.ex("DELETE FROM reconciliation_items WHERE id=?", (old["id"],))
    update_supplier_scores(biz)
    items = list_items(biz["id"], period)
    return {"period": period, "items": items, "itc_at_risk": sum(i["itc_at_risk"] for i in items),
            "counts": _counts(items), "rule_versions": ru.ids}


def _counts(items):
    c = {}
    for i in items:
        c[i["match_status"]] = c.get(i["match_status"], 0) + 1
    return c


def list_items(biz_id, period=None):
    sql = """SELECT r.*, i.invoice_no book_inv_no, i.invoice_date book_date, i.taxable_value book_taxable, (i.cgst+i.sgst+i.igst) book_tax,
                    p.invoice_no p_inv_no, p.invoice_date p_date, p.taxable_value p_taxable, (p.cgst+p.sgst+p.igst) p_tax, p.ims_status, p.supplier_name,
                    pa.name party_name, pa.gstin party_gstin, pa.phone party_phone
             FROM reconciliation_items r LEFT JOIN invoices i ON i.id=r.invoice_id LEFT JOIN portal_2b_records p ON p.id=r.portal_2b_record_id
             LEFT JOIN parties pa ON pa.id=r.party_id WHERE r.business_id=?"""
    a = [biz_id]
    if period:
        sql += " AND r.period=?"; a.append(period)
    out = db.q(sql + " ORDER BY r.itc_at_risk DESC, r.id", a)
    for r in out:
        r["party_name"] = r["party_name"] or r["supplier_name"]
        r["inv_no"] = r["book_inv_no"] or r["p_inv_no"]
    return out


def update_supplier_scores(biz):
    """Rolling 6 periods: share of invoices that matched in 2B."""
    for p in db.q("SELECT id FROM parties WHERE business_id=? AND type='supplier'", (biz["id"],)):
        rows = db.q("""SELECT r.match_status, r.itc_at_risk, r.period FROM reconciliation_items r WHERE r.business_id=? AND r.party_id=? AND r.invoice_id IS NOT NULL
                       ORDER BY r.period DESC""", (biz["id"], p["id"]))
        periods = sorted({r["period"] for r in rows}, reverse=True)[:6]
        rows = [r for r in rows if r["period"] in periods]
        if rows:
            good = sum(1 for r in rows if r["match_status"] == "matched")
            db.update("parties", p["id"], reliability_score=round(100.0 * good / len(rows), 1))


def supplier_report(biz_id):
    out = []
    for p in db.q("SELECT * FROM parties WHERE business_id=? AND type='supplier' ORDER BY reliability_score", (biz_id,)):
        rows = db.q("SELECT match_status, itc_at_risk, period FROM reconciliation_items WHERE business_id=? AND party_id=? AND invoice_id IS NOT NULL", (biz_id, p["id"]))
        late_periods = sorted({r["period"] for r in rows if r["match_status"] != "matched"})
        all_periods = sorted({r["period"] for r in rows})[-6:]
        p["late_periods"] = len(late_periods)
        p["total_periods"] = len(all_periods)
        p["itc_delayed"] = sum(r["itc_at_risk"] for r in rows)
        p["summary"] = (f"{p['name']} had problems in {len(late_periods)} of the last {len(all_periods)} periods; {fmt(p['itc_delayed'])} of credit delayed."
                        if rows else "No reconciliation history yet.")
        out.append(p)
    return out


def recommend_ims_action(item):
    return {"record_id": item["portal_2b_record_id"], "recommended": item["recommended_action"], "reason": item["reason"]}


def itc_decisions(biz, months, ru):
    """Invoice-by-invoice ITC eligibility for GSTR-3B. Returns (claim{heads}, claimed_rows, exclusions)."""
    claim = {"igst": 0, "cgst": 0, "sgst": 0}
    claimed, excl = [], []
    blocked_rule = ru.get("gst.itc.blocked")
    pay_days = ru.get("gst.itc.payment_days")
    for m in months:
        if biz["gst_scheme"] == "composition":
            break
        reconcile_itc(biz, m, refresh=True)
        items = {r["invoice_id"]: r for r in list_items(biz["id"], m) if r["invoice_id"]}
        purchases = db.q("""SELECT i.*, p.gstin pgstin, p.name pname FROM invoices i JOIN parties p ON p.id=i.party_id
                            WHERE i.business_id=? AND i.direction='purchase' AND i.period=? AND i.status='posted'""", (biz["id"], m))
        for inv in purchases:
            sign = -1 if inv["doc_type"] == "credit_note" else 1
            heads = {k: inv[k] for k in ("igst", "cgst", "sgst")}
            tot_tax = sum(heads.values())
            if tot_tax == 0:
                continue
            label = f"{inv['pname']} {inv['invoice_no']}"
            ref = {"invoice_id": inv["id"], "label": label}
            reason = None
            it = items.get(inv["id"])
            if inv["is_reverse_charge"]:
                pass  # RCM: ITC claimable after cash payment of RCM
            elif not inv["pgstin"]:
                reason = "Supplier unregistered: no ITC."
            elif not it:
                reason = "Not reconciled."
            else:
                st = it["match_status"]
                if st in ("missing_in_2b", "gstin_mismatch"):
                    reason = "Not in GSTR-2B (supplier has not filed / wrong GSTIN)."
                elif st == "payment_overdue":
                    reason = f"Supplier unpaid beyond {pay_days} days."
                elif it.get("ims_status") in ("rejected", "pending"):
                    reason = f"IMS status {it['ims_status']}: not available in GSTR-2B."
                elif st == "value_mismatch":
                    prec = db.one("SELECT * FROM portal_2b_records WHERE id=?", (it["portal_2b_record_id"],))
                    if prec:
                        heads = {k: min(inv[k], prec[k]) for k in heads}
                        ref["note"] = f"Claimed lower of books/supplier value ({fmt(sum(heads.values()))} of {fmt(tot_tax)})"
                    else:
                        reason = "Value mismatch."
            if reason:
                excl.append({**ref, "reason": reason, "amount": tot_tax}); continue
            # blocked credit (per line, Sec 17(5))
            bl = {"igst": 0, "cgst": 0, "sgst": 0}
            for ln in db.q("SELECT * FROM line_items WHERE invoice_id=?", (inv["id"],)):
                d = (ln["description"] or "").lower()
                if any(k in d for k in blocked_rule["keywords"]) or any((ln["hsn_sac"] or "").startswith(h) for h in blocked_rule["hsn_prefixes"]):
                    for k in bl:
                        bl[k] += ln[k]
            if sum(bl.values()):
                excl.append({**ref, "reason": "Blocked credit (Section 17(5)): " + ", ".join(sorted(blocked_rule["keywords"][:3])) + " etc.", "amount": sum(bl.values())})
                heads = {k: max(0, heads[k] - bl[k]) for k in heads}
            if sum(heads.values()) == 0:
                continue
            for k in claim:
                claim[k] += sign * heads[k]
            claimed.append({**ref, "heads": heads, "amount": sign * sum(heads.values()), "rcm": bool(inv["is_reverse_charge"])})
    return claim, claimed, excl
