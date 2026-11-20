"""Notices: explain after they arrive, warn before they are likely (nightly risk scan)."""
import json, re
from . import db, rules, itc, portal_read, channels
from .util import today, fmt, now_iso, audit, rupees
from .ingest import parse_date
from . import calc


def _f(text):
    f = {}
    for line in text.splitlines():
        if ":" in line:
            k, v = [x.strip() for x in line.split(":", 1)]
            f[k.lower()] = v
    return f


def register_notice(biz, doc_id, text):
    f = _f(text)
    ntype = f.get("notice type") or f.get("subject") or ("Show Cause Notice (ITC mismatch)" if "itc" in text.lower() else "GST notice")
    ref = f.get("ref no") or f.get("reference no") or f.get("notice no") or "N/A"
    period = (f.get("period") or "")[:7]
    amt = calc.clean_amount_str(f.get("amount") or f.get("amount demanded") or "")
    due = parse_date(f.get("reply by") or f.get("reply due") or f.get("due date"))
    linked = []
    if period and "itc" in text.lower():
        linked = [r["invoice_id"] for r in itc.list_items(biz["id"], period) if r["invoice_id"] and r["itc_at_risk"] > 0]
    nid = db.insert("notices", business_id=biz["id"], raw_document_id=doc_id, notice_type=ntype, reference_no=ref, period=period, amount=rupees(amt) if amt else None,
                    issue_date=parse_date(f.get("date") or f.get("issue date")) or today().isoformat(), reply_due_date=due, summary=text[:500],
                    linked_invoice_ids=json.dumps(linked), status="open")
    expl = explain_notice(biz, nid)
    db.update("notices", nid, explanation_json=json.dumps(expl))
    from . import calendar_
    calendar_.generate_obligations(biz)
    channels.notify_owner(biz["id"], "Notice received", expl["en"]["what"] + " " + expl["en"]["deadline"])
    audit(biz["id"], "agent", "notice", "notice_explained", "notice", nid)
    return nid


def explain_notice(biz, nid):
    n = db.one("SELECT * FROM notices WHERE id=?", (nid,))
    linked = db.jl(n["linked_invoice_ids"], [])
    invs = [db.one("SELECT i.invoice_no, p.name, (i.cgst+i.sgst+i.igst) tax FROM invoices i JOIN parties p ON p.id=i.party_id WHERE i.id=?", (i,)) for i in linked]
    amt = f" of {fmt(n['amount'], False)}" if n["amount"] else ""
    why = ("The difference is probably the invoice(s): " + ", ".join(f"{x['name']} {x['invoice_no']} ({fmt(x['tax'], False)} tax)" for x in invs if x) + ".") if invs else "I could not link it to a specific invoice yet."
    acct = db.one("SELECT u.name FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.business_id=? AND m.role='accountant' AND m.revoked_at IS NULL LIMIT 1", (biz["id"],))
    who = acct["name"] if acct else "your accountant"
    en = {"what": f"This is a {n['notice_type']}{amt} (ref {n['reference_no']}) about period {n['period'] or 'n/a'}.", "why": why,
          "deadline": f"{who} needs to reply by {n['reply_due_date'] or 'the date on the notice'}.",
          "documents": ["Purchase invoices for the period", "GSTR-2B reconciliation", "Proof of payment to suppliers", "Supplier filing confirmation"],
          "reply_outline": ["Acknowledge the notice and reference number", "State that the credit claimed is supported by valid tax invoices", "Attach the reconciliation and supplier correspondence", "Request time/hearing if documents are pending"]}
    hi = {"what": f"यह एक {n['notice_type']}{amt} है (संदर्भ {n['reference_no']})।", "why": why, "deadline": f"{who} को {n['reply_due_date']} तक जवाब देना है।"}
    kn = {"what": f"ಇದು {n['notice_type']}{amt} (ಉಲ್ಲೇಖ {n['reference_no']}).", "why": why, "deadline": f"{who} {n['reply_due_date']} ರೊಳಗೆ ಉತ್ತರಿಸಬೇಕು."}
    return {"en": en, "hi": hi, "kn": kn}


def risk_scan(biz, period):
    ru = rules.RuleUse(today().isoformat())
    lv = ru.get("risk.levels")
    db.ex("DELETE FROM risk_findings WHERE business_id=? AND period=? AND status='open'", (biz["id"], period))
    out = []

    def add(key, impact, detail, fix):
        out.append(db.insert("risk_findings", business_id=biz["id"], period=period, check_key=key, level=lv[key], rupee_impact=impact, detail=detail, fix=fix, detected_at=now_iso()))
    g1 = db.one("SELECT * FROM returns WHERE business_id=? AND return_type='GSTR1' AND period=?", (biz["id"], period))
    g3 = db.one("SELECT * FROM returns WHERE business_id=? AND return_type='GSTR3B' AND period=?", (biz["id"], period))
    if g1 and g3:
        a, b = json.loads(g1["computed_json"])["totals"], json.loads(g3["computed_json"])
        if a["taxable"] != b["outward"]["taxable"]:
            add("gstr1_vs_3b", abs(a["tax"] - b["outward"]["tax"]), f"GSTR-1 shows {fmt(a['taxable'])} but GSTR-3B shows {fmt(b['outward']['taxable'])}", "Amend via GSTR-1A before filing GSTR-3B")
        claimed_ncrm = b["itc"]["total"] - sum(c["amount"] for c in json.loads(g3["proof_json"]).get("claimed_itc", []) if c.get("rcm"))
        avail = db.q("SELECT COALESCE(SUM(cgst+sgst+igst),0) s FROM portal_2b_records WHERE business_id=? AND period=? AND ims_status IN ('no_action','accepted')", (biz["id"], period))[0]["s"]
        if claimed_ncrm > avail:
            add("itc_vs_2b", claimed_ncrm - avail, f"ITC claimed {fmt(claimed_ncrm)} but GSTR-2B shows {fmt(avail)}", f"Reverse {fmt(claimed_ncrm - avail)} ITC in the next return")
        for c in json.loads(g3["proof_json"]).get("claimed_itc", []):
            inv = db.one("SELECT p.gstin, p.name FROM invoices i JOIN parties p ON p.id=i.party_id WHERE i.id=?", (c["invoice_id"],))
            if inv and inv["gstin"]:
                try:
                    if portal_read.get(f"/taxpayer/{inv['gstin']}")["status"] == "cancelled":
                        add("cancelled_supplier", c["amount"], f"Credit {fmt(c['amount'])} claimed from {inv['name']} whose registration is cancelled", "Reverse this credit")
                except Exception:
                    pass
    sales_inv = {s["invoice_id"] for s in json.loads(g1["proof_json"])["sources"]} if g1 else set()
    if g1:
        for e in db.q("SELECT e.*, i.period ip, i.total FROM eway_bills e JOIN invoices i ON i.id=e.invoice_id WHERE e.business_id=? AND e.ewb_number IS NOT NULL AND i.period=?", (biz["id"], period)):
            if e["invoice_id"] not in sales_inv:
                add("ewb_vs_gstr1", e["total"], f"E-way bill {e['ewb_number']} ({fmt(e['total'])}) is not in GSTR-1", "Include the invoice in GSTR-1 / GSTR-1A")
    from .returns import due_date
    for rt in ("GSTR1", "GSTR3B"):
        r = db.one("SELECT status FROM returns WHERE business_id=? AND return_type=? AND period=?", (biz["id"], rt, period))
        if (not r or r["status"] != "filed_simulated") and due_date(biz, rt, period) < today().isoformat():
            add("unfiled", 0, f"{rt} for {period} was due {due_date(biz, rt, period)} and is not filed", "File now; late fee accrues daily")
    high = [x for x in db.q("SELECT * FROM risk_findings WHERE business_id=? AND period=? AND level='high' AND status='open'", (biz["id"], period))]
    if high:
        channels.notify_owner(biz["id"], "Notice risk (high)", "; ".join(h["detail"] for h in high[:2]))
    return db.q("SELECT * FROM risk_findings WHERE business_id=? AND period=? AND status='open' ORDER BY level, id", (biz["id"], period))
