"""GSTR-1 / GSTR-3B / CMP-08 preparation with proof packs. Drafts only: nothing here can file."""
import json
from collections import defaultdict
from datetime import date
from . import db, calc, rules, itc
from .util import today, now_iso, fmt, audit, add_days, next_month
from .i18n import t


def period_months(biz, period):
    if biz["gst_scheme"] in ("qrmp", "composition"):
        y, m = int(period[:4]), int(period[5:7])
        if m % 3:
            raise ValueError("QRMP / composition returns are quarterly: use the quarter-end month (03, 06, 09, 12)")
        out = []
        for k in (2, 1, 0):
            mm = m - k
            out.append(f"{y}-{mm:02d}")
        return out
    return [period]


def due_date(biz, rtype, period, ru=None):
    ru = ru or rules.RuleUse(today().isoformat())
    scheme = biz["gst_scheme"]
    y, m = next_month(period)
    if rtype == "GSTR1":
        d = ru.get("gst.return.gstr1.due_day")["qrmp" if scheme == "qrmp" else "regular"]
    elif rtype == "GSTR3B":
        d = ru.get("gst.return.gstr3b.due_day")["qrmp" if scheme == "qrmp" else "regular"]
    else:
        d = ru.get("gst.return.gstr3b.due_day")["composition_cmp08"]
    return date(y, m, d).isoformat()


def _sales(biz, months):
    return db.q("""SELECT i.*, p.name pname, p.gstin pgstin FROM invoices i LEFT JOIN parties p ON p.id=i.party_id
                   WHERE i.business_id=? AND i.direction='sale' AND i.period IN (%s) AND i.status='posted' ORDER BY i.invoice_date, i.id""" % ",".join("?" * len(months)),
                [biz["id"], *months])


def _row(inv):
    s = -1 if inv["doc_type"] == "credit_note" else 1
    return {"id": inv["id"], "no": inv["invoice_no"], "date": inv["invoice_date"], "party": inv["pname"], "gstin": inv["pgstin"], "pos": inv["place_of_supply"],
            "taxable": s * inv["taxable_value"], "cgst": s * inv["cgst"], "sgst": s * inv["sgst"], "igst": s * inv["igst"], "total": s * inv["total"], "doc_type": inv["doc_type"]}


def draft_gstr1(biz, period, save=True):
    ru = rules.RuleUse(today().isoformat())
    months = period_months(biz, period)
    sales = _sales(biz, months)
    b2cl_th = ru.get("gst.b2cl.threshold")
    t_b2b, t_b2cl, t_b2cs, t_cdn = [], [], defaultdict(lambda: {"taxable": 0, "tax": 0}), []
    hsn = defaultdict(lambda: {"qty": 0.0, "taxable": 0, "cgst": 0, "sgst": 0, "igst": 0})
    checks, warnings, nil = [], [], {"taxable": 0, "count": 0}
    seen_no = {}
    for inv in sales:
        r = _row(inv)
        key = (inv["invoice_no"], inv["doc_type"])
        if key in seen_no:
            checks.append({"check": "duplicate_invoice_no", "ok": False, "detail": f"Invoice number {inv['invoice_no']} appears twice."})
        seen_no[key] = 1
        lines = db.q("SELECT * FROM line_items WHERE invoice_id=?", (inv["id"],))
        s = -1 if inv["doc_type"] == "credit_note" else 1
        if abs(sum(l["cgst"] + l["sgst"] + l["igst"] for l in lines) - (inv["cgst"] + inv["sgst"] + inv["igst"])) > 100:
            checks.append({"check": "tax_maths", "ok": False, "detail": f"{inv['invoice_no']}: line tax != invoice tax"})
        for l in lines:
            if not l["hsn_sac"]:
                checks.append({"check": "hsn_present", "ok": False, "detail": f"{inv['invoice_no']}: missing HSN"})
            h = hsn[(l["hsn_sac"], l["gst_rate"])]
            h["qty"] += s * (l["qty"] or 0); h["taxable"] += s * l["taxable_value"]
            for k in ("cgst", "sgst", "igst"):
                h[k] += s * l[k]
            if l["gst_rate"] == 0:
                nil["taxable"] += s * l["taxable_value"]; nil["count"] += 1
        registered = bool(inv["pgstin"])
        if registered and not calc.gstin_valid(inv["pgstin"]):
            checks.append({"check": "buyer_gstin_valid", "ok": False, "detail": f"{inv['invoice_no']}: buyer GSTIN {inv['pgstin']} invalid"})
        if inv["doc_type"] in ("credit_note", "debit_note"):
            t_cdn.append(r)
        elif registered:
            t_b2b.append(r)
        elif inv["igst"] > 0 and inv["total"] > b2cl_th:
            t_b2cl.append(r)
        else:
            k = (inv["place_of_supply"],)
            t_b2cs[k]["taxable"] += r["taxable"]; t_b2cs[k]["tax"] += r["cgst"] + r["sgst"] + r["igst"]
    for tbl in ("buyer_gstin_valid", "duplicate_invoice_no", "hsn_present", "tax_maths"):
        if not any(c["check"] == tbl for c in checks):
            checks.append({"check": tbl, "ok": True, "detail": "passed"})
    allrows = t_b2b + t_b2cl + t_cdn
    tot = {"taxable": sum(r["taxable"] for r in allrows), "cgst": sum(r["cgst"] for r in allrows), "sgst": sum(r["sgst"] for r in allrows), "igst": sum(r["igst"] for r in allrows)}
    for v in t_b2cs.values():
        tot["taxable"] += v["taxable"]
    # b2cs tax heads from invoices directly
    b2cs_rows = [_row(i) for i in sales if not i["pgstin"] and i["doc_type"] == "invoice" and not (i["igst"] > 0 and i["total"] > b2cl_th)]
    for r in b2cs_rows:
        for k in ("cgst", "sgst", "igst"):
            tot[k] += r[k]
    tot["tax"] = tot["cgst"] + tot["sgst"] + tot["igst"]
    tot["invoices"] = len(sales)
    b2b_grouped = defaultdict(list)
    for r in t_b2b:
        b2b_grouped[r["gstin"]].append(r)
    computed = {"period": period, "months": months, "totals": tot,
                "tables": {"b2b": [{"gstin": g, "party": v[0]["party"], "invoices": v} for g, v in b2b_grouped.items()],
                           "b2cl": t_b2cl, "b2cs": [{"pos": k[0], **v} for k, v in t_b2cs.items()], "cdnr": t_cdn,
                           "hsn": [{"hsn": k[0], "rate": k[1], **v} for k, v in hsn.items()], "nil_exempt": nil},
                "due_date": due_date(biz, "GSTR1", period, ru)}
    proof = {"summary": {"invoices": tot["invoices"], "taxable": tot["taxable"], "tax": tot["tax"], "cgst": tot["cgst"], "sgst": tot["sgst"], "igst": tot["igst"]},
             "sources": [{"invoice_id": r["id"], "label": f"{r['party']} {r['no']}", "date": r["date"], "total": r["total"]} for r in map(_row, sales)],
             "trace": [{"step": "Sum output tax over sales invoices (credit notes negative)", "value": tot["tax"], "rule": None}],
             "exclusions": [], "checks": checks, "rules": ru.used,
             "documents_for_accountant": ["Sales register", "Original sales invoices (linked)", "Debit/credit notes"]}
    return _save_return(biz, "GSTR1", period, computed, proof, ru, save)


def _prev_cash(biz, period):
    y, m = int(period[:4]), int(period[5:7])
    pm = f"{y - (m == 1)}-{(12 if m == 1 else m - 1):02d}"
    r = db.one("SELECT computed_json FROM returns WHERE business_id=? AND return_type='GSTR3B' AND period=?", (biz["id"], pm))
    return json.loads(r["computed_json"])["net_cash"] if r else None


def draft_gstr3b(biz, period, save=True, as_of=None):
    ru = rules.RuleUse(today().isoformat())
    months = period_months(biz, period)
    g1 = draft_gstr1(biz, period, save=False)
    g1t = g1["computed"]["totals"]
    out = {"igst": g1t["igst"], "cgst": g1t["cgst"], "sgst": g1t["sgst"]}
    due = due_date(biz, "GSTR3B", period, ru)
    as_of = as_of or today().isoformat()
    fee_rule, rate = ru.get("gst.late_fee.per_day"), ru.get("gst.interest_rate")
    if biz["gst_scheme"] == "composition":
        rate_c = ru.get("gst.composition.rate").get(biz["business_type"] if biz["business_type"] in ("trader", "manufacturer", "service") else "trader")
        turnover = g1t["taxable"]
        tax = calc.tds_amount(turnover, rate_c)
        due = due_date(biz, "CMP08", period, ru)
        late = calc.late_fee_and_interest(due, as_of, tax, tax == 0, fee_rule, rate)
        computed = {"period": period, "months": months, "scheme": "composition", "turnover": turnover, "composition_rate": rate_c, "outward": {"tax": tax, "taxable": turnover},
                    "net_cash": tax + late["late_fee"] + late["interest"], "tax_cash": tax, "late": late, "due_date": due,
                    "itc": {"claimed": {}, "total": 0}, "rcm_cash": 0, "setoff": None}
        proof = {"summary": {"turnover": turnover, "tax": tax, "net_cash": computed["net_cash"]}, "sources": g1["proof"]["sources"],
                 "trace": [{"step": f"Turnover x composition rate {rate_c}%", "value": tax, "rule": "gst.composition.rate"}],
                 "exclusions": [{"label": "ITC module", "reason": "Composition scheme: no input tax credit"}], "checks": g1["proof"]["checks"], "rules": ru.used,
                 "documents_for_accountant": ["Sales register"]}
        r = _save_return(biz, "CMP08", period, computed, proof, ru, save)
        return r
    # RCM
    rcm = {"igst": 0, "cgst": 0, "sgst": 0}
    rcm_rows = []
    for m in months:
        for inv in db.q("SELECT i.*, p.name pname FROM invoices i LEFT JOIN parties p ON p.id=i.party_id WHERE i.business_id=? AND i.direction='purchase' AND i.period=? AND i.is_reverse_charge=1 AND i.status='posted'", (biz["id"], m)):
            for k in rcm:
                rcm[k] += inv[k]
            rcm_rows.append({"invoice_id": inv["id"], "label": f"{inv['pname']} {inv['invoice_no']}", "amount": inv["cgst"] + inv["sgst"] + inv["igst"]})
    claim, claimed, excl = itc.itc_decisions(biz, months, ru)
    so = calc.setoff(out, claim)
    rcm_cash = sum(rcm.values())
    tax_cash = sum(so["cash"].values())
    late = calc.late_fee_and_interest(due, as_of, tax_cash + rcm_cash, (tax_cash + rcm_cash) == 0 and g1t["tax"] == 0, fee_rule, rate)
    net_cash = tax_cash + rcm_cash + late["late_fee"] + late["interest"]
    prev = _prev_cash(biz, period)
    itc_total = sum(claim.values())
    stuck = sum(e["amount"] for e in excl if "2B" in e["reason"] or "IMS" in e["reason"] or "unpaid" in e["reason"])
    computed = {"period": period, "months": months, "scheme": biz["gst_scheme"],
                "outward": {"taxable": g1t["taxable"], "cgst": out["cgst"], "sgst": out["sgst"], "igst": out["igst"], "tax": g1t["tax"]},
                "rcm": {**rcm, "total": rcm_cash}, "itc": {"claimed": claim, "total": itc_total, "stuck": stuck},
                "setoff": so, "tax_cash": tax_cash, "rcm_cash": rcm_cash, "late": late, "net_cash": net_cash, "due_date": due,
                "prev_net_cash": prev, "gstr1_return_id": None}
    trace = [{"step": "Output tax per GSTR-1 (locked, auto-populated)", "value": g1t["tax"], "rule": None},
             {"step": "Reverse-charge tax payable in cash", "value": rcm_cash, "rule": "gst.reverse_charge.categories"},
             {"step": "Eligible ITC (in 2B/IMS, not blocked, supplier paid) incl. RCM ITC", "value": itc_total, "rule": "gst.itc.blocked"}]
    for s in so["trace"]:
        trace.append({"step": f"Set-off {s['credit']} credit against {s['against']} liability", "value": s["amount"], "rule": "CGST Act s.49 / r.88A"})
    trace.append({"step": "Cash payable (after set-off) + RCM", "value": tax_cash + rcm_cash, "rule": None})
    if late["days_late"]:
        trace.append({"step": f"Late fee ({late['days_late']} days)", "value": late["late_fee"], "rule": "gst.late_fee.per_day"})
        trace.append({"step": "Interest on late-paid tax", "value": late["interest"], "rule": "gst.interest_rate"})
    proof = {"summary": {"output_tax": g1t["tax"], "rcm_cash": rcm_cash, "itc_claimed": itc_total, "itc_stuck": stuck, "tax_cash": tax_cash, "net_cash": net_cash,
                         "cash_by_head": so["cash"], "prev_net_cash": prev},
             "sources": g1["proof"]["sources"] + [{"invoice_id": c["invoice_id"], "label": "ITC: " + c["label"], "total": c["amount"]} for c in claimed],
             "trace": trace, "exclusions": excl, "claimed_itc": claimed, "rcm": rcm_rows, "checks": g1["proof"]["checks"], "rules": ru.used,
             "documents_for_accountant": ["Sales register", "Purchase register", "GSTR-2B reconciliation", "Bank summary", "RCM invoices"]}
    return _save_return(biz, "GSTR3B", period, computed, proof, ru, save)


def _explain(biz, rtype, c, period):
    out = {}
    for lang in ("en", "hi", "kn"):
        if rtype == "GSTR3B":
            out[lang] = t("gst_summary", lang, period=period, sales=fmt(c["outward"]["taxable"], False), output=fmt(c["outward"]["tax"], False),
                          itc=fmt(c["itc"]["total"], False), cash=fmt(c["net_cash"], False), due=c["due_date"])
            if c["itc"].get("stuck"):
                out[lang] += " " + t("itc_stuck", lang, amount=fmt(c["itc"]["stuck"], False), suppliers=_stuck_suppliers(biz, period))
        elif rtype == "GSTR1":
            tot = c["totals"]
            out[lang] = {"en": f"GSTR-1 for {period}: {tot['invoices']} sales invoices, taxable {fmt(tot['taxable'], False)}, GST collected {fmt(tot['tax'], False)}. Due {c['due_date']}.",
                         "hi": f"GSTR-1 {period}: {tot['invoices']} बिक्री बिल, कर योग्य {fmt(tot['taxable'], False)}, GST {fmt(tot['tax'], False)}। अंतिम तिथि {c['due_date']}।",
                         "kn": f"GSTR-1 {period}: {tot['invoices']} ಮಾರಾಟ ಬಿಲ್, ತೆರಿಗೆ ಮೌಲ್ಯ {fmt(tot['taxable'], False)}, GST {fmt(tot['tax'], False)}. ಗಡುವು {c['due_date']}."}[lang]
        else:
            out[lang] = f"Composition tax for {period}: {fmt(c['tax_cash'], False)} on turnover {fmt(c['turnover'], False)}. Due {c['due_date']}."
    return out


def _stuck_suppliers(biz, period):
    names = [r["party_name"] for r in itc.list_items(biz["id"], period) if r["itc_at_risk"] > 0 and r["party_name"]]
    return ", ".join(sorted(set(names))[:3]) or "suppliers"


def _save_return(biz, rtype, period, computed, proof, ru, save):
    result = {"computed": computed, "proof": proof, "return_type": rtype, "period": period}
    if not save:
        return result
    ex = db.one("SELECT * FROM returns WHERE business_id=? AND return_type=? AND period=?", (biz["id"], rtype, period))
    if ex and ex["status"] == "filed_simulated":
        raise ValueError(f"{rtype} {period} is already filed (simulated)")
    expl = _explain(biz, rtype, computed, period)
    status = "awaiting_accountant" if biz["default_route"] == "accountant" else "awaiting_owner"
    vals = dict(computed_json=json.dumps(computed), proof_json=json.dumps(proof), rule_version_ids=json.dumps(ru.ids),
                prepared_at=now_iso(), explanation_json=json.dumps(expl))
    if ex:
        rid = ex["id"]
        db.update("returns", rid, status=status if ex["status"] in ("draft", "awaiting_owner", "awaiting_accountant") else ex["status"], **vals)
        if ex["status"] in ("approved",):
            db.update("returns", rid, status=status)  # recomputed: needs fresh approval
    else:
        rid = db.insert("returns", business_id=biz["id"], return_type=rtype, period=period, status=status, **vals)
    audit(biz["id"], "agent", "return_prep", "return_prepared", "return", rid, None, {"type": rtype, "period": period, "net_cash": computed.get("net_cash")})
    from . import gate
    gate.ensure_return_approval(biz, rid, rtype, period, status)
    result["return_id"] = rid
    return result


def compute_gst_liability(biz, period):
    r = draft_gstr3b(biz, period, save=False)
    c = r["computed"]
    return {"period": period, "sales": c["outward"]["taxable"], "output_tax": c["outward"]["tax"], "itc": c["itc"]["total"], "itc_stuck": c["itc"].get("stuck", 0),
            "cash": c["net_cash"], "due": c["due_date"], "rcm": c.get("rcm_cash", 0)}


def get_return(rid):
    r = db.one("SELECT * FROM returns WHERE id=?", (rid,))
    if r:
        for k in ("computed_json", "proof_json", "rule_version_ids", "explanation_json"):
            r[k.replace("_json", "")] = db.jl(r[k])
    return r
