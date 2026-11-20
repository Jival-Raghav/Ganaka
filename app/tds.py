"""TDS: applicability, deduction tracking (us -> others), 26AS matching (customers -> us)."""
import json
from . import db, rules, calc, gate, portal_read
from .util import today, fmt, audit, now_iso, fy_of

SECTION_KEYWORDS = [("194J", ["professional", "consultan", "legal fee", "audit fee", "technical"]),
                    ("194I", ["rent", "lease"]), ("194C", ["contract", "labour", "interior", "fabrication", "repair", "civil work", "printing job"])]


def prev_fy_turnover(biz):
    y = int(fy_of(today().isoformat())[:4])
    r = db.one("SELECT COALESCE(SUM(taxable_value),0) s FROM invoices WHERE business_id=? AND direction='sale' AND invoice_date>=? AND invoice_date<=?",
               (biz["id"], f"{y - 1}-04-01", f"{y}-03-31"))
    return r["s"]


def applicability(biz):
    ru = rules.RuleUse(today().isoformat())
    th = ru.get("tds.applicability.proprietor_turnover")
    to = prev_fy_turnover(biz)
    if biz["constitution"] in ("company", "partnership", "llp"):
        app, txt = True, "As a company/firm you must deduct TDS on contractor, professional fees and rent payments above the limits."
    elif to > th:
        app, txt = True, f"Last year's turnover {fmt(to, False)} crossed {fmt(th, False)}: you must deduct TDS on contractor and rent payments."
    else:
        app, txt = False, f"You don't need to deduct TDS this year (last year's turnover {fmt(to, False)} is below {fmt(th, False)}). Rule to be re-checked every April."
    return {"applicable": app, "text": txt, "turnover": to, "threshold": th, "rules": ru.used}


def check_purchase(business_id, inv_id):
    biz = db.one("SELECT * FROM businesses WHERE id=?", (business_id,))
    ap = applicability(biz)
    if not ap["applicable"]:
        return None
    inv = db.one("SELECT i.*, p.name pname FROM invoices i JOIN parties p ON p.id=i.party_id WHERE i.id=?", (inv_id,))
    desc = " ".join(l["description"].lower() for l in db.q("SELECT description FROM line_items WHERE invoice_id=?", (inv_id,)))
    for sec, kws in SECTION_KEYWORDS:
        if any(k in desc for k in kws):
            r = rules.get_rule(f"tds.section.{sec}", inv["invoice_date"])
            fy_total = db.one("""SELECT COALESCE(SUM(i.taxable_value),0) s FROM invoices i WHERE i.business_id=? AND i.party_id=? AND i.direction='purchase' AND i.fy=?""", (business_id, inv["party_id"], inv["fy"]))["s"]
            single, annual = r.get("single"), r.get("annual")
            if (single and inv["taxable_value"] >= single) or (annual and fy_total >= annual):
                amt = calc.tds_amount(inv["taxable_value"], r["rate"])
                if not db.one("SELECT 1 x FROM tds_entries WHERE invoice_id=? AND direction='deducted_by_us'", (inv_id,)):
                    db.insert("tds_entries", business_id=business_id, direction="deducted_by_us", party_id=inv["party_id"], invoice_id=inv_id, section=sec,
                              amount=inv["taxable_value"], tds_amount=amt, date=inv["invoice_date"], note=f"{sec} @ {r['rate']}%")
                    from . import channels
                    channels.notify_owner(business_id, "TDS to deduct", f"Deduct {fmt(amt, False)} TDS under {sec} from the {fmt(inv['taxable_value'], False)} you are paying {inv['pname']}.")
                return {"section": sec, "tds": amt}
    return None


def tds_by_us(biz_id):
    return db.q("SELECT t.*, p.name party FROM tds_entries t LEFT JOIN parties p ON p.id=t.party_id WHERE t.business_id=? AND t.direction='deducted_by_us' ORDER BY t.date", (biz_id,))


def record_deducted_from_us(biz, party_id, invoice_id, section, amount, tds, date_):
    return db.insert("tds_entries", business_id=biz["id"], direction="deducted_from_us", party_id=party_id, invoice_id=invoice_id, section=section,
                     amount=amount, tds_amount=tds, date=date_)


def match_26as(biz, fy=None):
    fy = fy or fy_of(today().isoformat())
    if not biz["pan"]:
        return {"error": "PAN missing"}
    entries = portal_read.get(f"/26as/{biz['pan']}/{fy}")["entries"]
    used, flags, credit = set(), [], 0
    for t in db.q("SELECT t.*, p.name party, i.invoice_no FROM tds_entries t LEFT JOIN parties p ON p.id=t.party_id LEFT JOIN invoices i ON i.id=t.invoice_id WHERE t.business_id=? AND t.direction='deducted_from_us'", (biz["id"],)):
        tok = (t["party"] or "").lower().split()[0] if t["party"] else ""
        m = next((e for e in entries if e["id"] not in used and tok and tok in e["deductor"].lower() and abs(e["tds"] - t["tds_amount"]) <= 100), None)
        near = next((e for e in entries if e["id"] not in used and tok and tok in e["deductor"].lower()), None)
        if m:
            used.add(m["id"]); db.update("tds_entries", t["id"], matched_26as=1); credit += m["tds"]
        elif near:
            used.add(near["id"]); flags.append({"kind": "amount_mismatch", "party": t["party"], "invoice": t["invoice_no"], "ours": t["tds_amount"], "26as": near["tds"]}); credit += min(near["tds"], t["tds_amount"])
        else:
            flags.append({"kind": "missing_in_26as", "party": t["party"], "invoice": t["invoice_no"], "ours": t["tds_amount"], "entry_id": t["id"]})
            p = db.one("SELECT * FROM parties WHERE id=?", (t["party_id"],))
            if p and p["phone"]:
                gate.request_approval(biz["id"], "message", t["id"], {"party_id": p["id"], "template": "m_tds_missing", "vars": {"biz": biz["trade_name"], "amount": fmt(t["tds_amount"], False), "inv": t["invoice_no"] or "-"}, "related": ["tds_entry", t["id"]]},
                                      f"Tell {p['name']} their {fmt(t['tds_amount'], False)} TDS is missing in 26AS", "owner")
    for e in entries:
        if e["id"] not in used:
            flags.append({"kind": "in_26as_not_in_books", "party": e["deductor"], "26as": e["tds"]})
    return {"fy": fy, "tds_credit_available": credit, "flags": flags, "entries_26as": len(entries)}


def prepare_tds_return(biz, quarter_label):
    rows = tds_by_us(biz["id"])
    by_party = {}
    for r in rows:
        d = by_party.setdefault(r["party"], {"party": r["party"], "section": r["section"], "amount": 0, "tds": 0})
        d["amount"] += r["amount"]; d["tds"] += r["tds_amount"]
    computed = {"period": quarter_label, "deductees": list(by_party.values()), "total_tds": sum(d["tds"] for d in by_party.values()), "net_cash": sum(d["tds"] for d in by_party.values())}
    proof = {"summary": {"total_tds": computed["total_tds"]}, "sources": [{"label": f"{r['party']} {r['section']}", "total": r["tds_amount"]} for r in rows], "trace": [{"step": "Sum TDS deducted per deductee", "value": computed["total_tds"]}], "exclusions": [], "checks": [], "rules": {}}
    ex = db.one("SELECT id FROM returns WHERE business_id=? AND return_type='TDS' AND period=?", (biz["id"], quarter_label))
    vals = dict(computed_json=json.dumps(computed), proof_json=json.dumps(proof), prepared_at=now_iso(), explanation_json=json.dumps({"en": f"TDS return {quarter_label}: {fmt(computed['total_tds'], False)} deducted from {len(by_party)} parties."}))
    if ex:
        db.update("returns", ex["id"], status="awaiting_owner", **vals); rid = ex["id"]
    else:
        rid = db.insert("returns", business_id=biz["id"], return_type="TDS", period=quarter_label, status="awaiting_owner", **vals)
    gate.ensure_return_approval(biz, rid, "TDS", quarter_label, "awaiting_owner")
    return rid
