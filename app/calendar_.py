"""Compliance calendar, reminders, document vault, plus P2 extras (payroll, 43B(h), 44AD)."""
import json
from datetime import date, timedelta
from . import db, rules, calc, gate, channels
from .util import today, fmt, now_iso, add_days, fy_of, audit
from . import returns as R


def _add(biz_id, otype, label, period, due, rid=None):
    ex = db.one("SELECT * FROM obligations WHERE business_id=? AND obligation_type=? AND period=?", (biz_id, otype, period))
    if ex:
        db.update("obligations", ex["id"], due_date=due, label=label)
        return ex["id"]
    return db.insert("obligations", business_id=biz_id, obligation_type=otype, label=label, period=period, due_date=due, status="upcoming", related_return_id=rid)


def generate_obligations(biz):
    ru = rules.RuleUse(today().isoformat())
    t0 = today()
    periods = []
    y, m = t0.year, t0.month
    for k in range(-3, 2):
        mm = m + k
        yy = y + (mm - 1) // 12
        mm = (mm - 1) % 12 + 1
        periods.append(f"{yy}-{mm:02d}")
    scheme = biz["gst_scheme"]
    for p in periods:
        if scheme == "regular":
            _add(biz["id"], "GSTR1", f"GSTR-1 for {p}", p, R.due_date(biz, "GSTR1", p, ru))
            _add(biz["id"], "GSTR3B", f"GSTR-3B for {p}", p, R.due_date(biz, "GSTR3B", p, ru))
        elif int(p[5:]) % 3 == 0:
            if scheme == "qrmp":
                _add(biz["id"], "GSTR1", f"GSTR-1 (quarter ending {p})", p, R.due_date(biz, "GSTR1", p, ru))
                _add(biz["id"], "GSTR3B", f"GSTR-3B (quarter ending {p})", p, R.due_date(biz, "GSTR3B", p, ru))
            else:
                _add(biz["id"], "CMP08", f"CMP-08 (quarter ending {p})", p, R.due_date(biz, "CMP08", p, ru))
        from . import tds
        if tds.applicability(biz)["applicable"]:
            ny, nm = calc_next(p)
            _add(biz["id"], "TDS_DEPOSIT", f"TDS deposit for {p}", p, date(ny, nm, ru.get("tds.deposit_due_day")).isoformat())
        if biz["employee_count"]:
            ny, nm = calc_next(p)
            _add(biz["id"], "PF_ESI", f"PF/ESI/PT for {p}", p, date(ny, nm, 15).isoformat())
    for d in db.q("SELECT * FROM compliance_documents WHERE business_id=?", (biz["id"],)):
        _add(biz["id"], "DOC_EXPIRY", f"{d['doc_type']} renewal ({d['number'] or ''})", d["expiry_date"][:7] + "-" + str(d["id"]), d["expiry_date"])
    for n in db.q("SELECT * FROM notices WHERE business_id=? AND status='open' AND reply_due_date IS NOT NULL", (biz["id"],)):
        _add(biz["id"], "NOTICE_REPLY", f"Reply to notice {n['reference_no']}", f"notice-{n['id']}", n["reply_due_date"])
    _add(biz["id"], "GSTR9", "GST annual return", fy_of(today().isoformat()), f"{int(fy_of(today().isoformat())[:4]) + 1}-12-31")
    for mmdd, lab in (("06-15", "Advance tax 1st instalment"), ("09-15", "Advance tax 2nd instalment"), ("12-15", "Advance tax 3rd instalment"), ("03-15", "Advance tax 4th instalment")):
        fy0 = int(fy_of(today().isoformat())[:4])
        yr = fy0 if mmdd < "04" and False else (fy0 + 1 if mmdd.startswith("03") else fy0)
        _add(biz["id"], "ADV_TAX", lab, f"{yr}-{mmdd}", f"{yr}-{mmdd}")
    refresh_status(biz)


def calc_next(p):
    return R.next_month(p)


def refresh_status(biz):
    t0 = today().isoformat()
    for o in db.q("SELECT * FROM obligations WHERE business_id=?", (biz["id"],)):
        st = o["status"]
        if st == "done":
            continue
        r = db.one("SELECT * FROM returns WHERE business_id=? AND return_type=? AND period=?", (biz["id"], o["obligation_type"], o["period"]))
        if r:
            db.update("obligations", o["id"], related_return_id=r["id"])
            st = {"filed_simulated": "done", "approved": "awaiting approval", "awaiting_owner": "awaiting approval", "awaiting_accountant": "awaiting approval"}.get(r["status"], "preparing")
        elif o["obligation_type"] == "NOTICE_REPLY":
            n = db.one("SELECT status FROM notices WHERE id=?", (int(o["period"].split("-")[1]),))
            st = "done" if n and n["status"] != "open" else "upcoming"
        else:
            st = "upcoming"
        if st != "done" and o["due_date"] < t0:
            st = "overdue"
        db.update("obligations", o["id"], status=st)


def calendar(biz_id):
    biz = db.one("SELECT * FROM businesses WHERE id=?", (biz_id,))
    refresh_status(biz)
    out = db.q("SELECT * FROM obligations WHERE business_id=? ORDER BY due_date", (biz_id,))
    t0 = date.fromisoformat(today().isoformat())
    ru = rules.RuleUse(today().isoformat())
    for o in out:
        o["days_left"] = (date.fromisoformat(o["due_date"]) - t0).days
        if o["status"] == "overdue" and o["obligation_type"] in ("GSTR1", "GSTR3B"):
            d = -o["days_left"]
            fee = ru.get("gst.late_fee.per_day")
            o["late_fee_so_far"] = min(fee["regular_paise"] * d, fee["cap_paise"])
    return out


def next_deadlines(biz_id, n=3):
    return [o for o in calendar(biz_id) if o["status"] != "done" and o["days_left"] >= -30][:n]


def send_reminders(biz):
    ru = rules.RuleUse(today().isoformat())
    offs = ru.get("calendar.reminder_offsets")
    doc_offs = ru.get("calendar.doc_reminder_days")
    sent = []
    for o in calendar(biz["id"]):
        if o["status"] == "done" or o["obligation_type"] in ("ADV_TAX", "GSTR9"):
            continue
        offs_use = doc_offs if o["obligation_type"] == "DOC_EXPIRY" else offs
        hit = [x for x in offs_use if o["days_left"] <= x and o["days_left"] >= 0]
        if not hit:
            continue
        tag = f"{today().isoformat()}:{min(hit)}"
        if (o["last_reminded"] or "").split(":")[-1] == str(min(hit)):
            continue
        db.update("obligations", o["id"], last_reminded=tag)
        channels.notify_owner(biz["id"], "Deadline reminder", f"{o['label']} is due in {o['days_left']} day(s) ({o['due_date']}).")
        sent.append(o["label"])
    return sent


def vault(biz_id):
    out = db.q("SELECT * FROM compliance_documents WHERE business_id=? ORDER BY expiry_date", (biz_id,))
    for d in out:
        d["days_left"] = (date.fromisoformat(d["expiry_date"]) - date.fromisoformat(today().isoformat())).days
        d["state"] = "expired" if d["days_left"] < 0 else ("expiring" if d["days_left"] <= 60 else "ok")
    return out


# ---- P2 extras ----
def payroll(biz):
    ru = rules.RuleUse(today().isoformat())
    rows, tot = [], {"pf": 0, "esi": 0, "pt": 0}
    pt = ru.get("pt.karnataka.slab")
    pf_applicable = biz["employee_count"] >= ru.get("pf.threshold_employees")
    esi_applicable = biz["employee_count"] >= ru.get("esi.threshold_employees")
    for e in db.q("SELECT * FROM employees WHERE business_id=?", (biz["id"],)):
        pf = calc.tds_amount(min(e["monthly_salary"], 1500000), 12) if (e["pf_applicable"] and pf_applicable) else 0
        esi = calc.tds_amount(e["monthly_salary"], 4) if (esi_applicable and e["esi_applicable"] and e["monthly_salary"] <= 2100000) else 0
        ptx = pt["monthly"] if e["monthly_salary"] >= pt["min_salary"] else 0
        rows.append({**e, "pf": pf, "esi": esi, "pt": ptx})
        tot["pf"] += pf; tot["esi"] += esi; tot["pt"] += ptx
    return {"employees": rows, "totals": tot, "pf_applicable": pf_applicable, "esi_applicable": esi_applicable, "rules": ru.used}


def overdue_receivables(biz):
    """43B(h): Udyam-registered seller chases buyers late beyond 45 days."""
    if not biz["udyam_registered"]:
        return []
    ru = rules.RuleUse(today().isoformat())
    days = ru.get("msme.43bh.days")["with_agreement"]
    out = []
    for inv in db.q("SELECT i.*, p.name pname, p.phone pphone FROM invoices i JOIN parties p ON p.id=i.party_id WHERE i.business_id=? AND i.direction='sale' AND i.doc_type='invoice'", (biz["id"],)):
        paid = db.one("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE invoice_id=?", (inv["id"],))["s"]
        age = (date.fromisoformat(today().isoformat()) - date.fromisoformat(inv["invoice_date"])).days
        if paid < inv["total"] and age > days:
            out.append({"invoice_id": inv["id"], "invoice_no": inv["invoice_no"], "party": inv["pname"], "party_id": inv["party_id"], "outstanding": inv["total"] - paid, "age_days": age})
    return out


def chase_receivable(biz, invoice_id):
    inv = db.one("SELECT i.*, p.name pname FROM invoices i JOIN parties p ON p.id=i.party_id WHERE i.id=?", (invoice_id,))
    return gate.request_approval(biz["id"], "message", invoice_id, {"party_id": inv["party_id"], "template": "m_buyer_overdue",
                                 "vars": {"biz": biz["trade_name"], "inv": inv["invoice_no"], "amount": fmt(inv["total"], False), "date": inv["invoice_date"]}, "related": ["invoice", invoice_id]},
                                 f"Remind {inv['pname']} about overdue {inv['invoice_no']}", "owner")


def presumptive_income(biz):
    """Section 44AD estimate: 6% on digital receipts, 8% on cash."""
    ru = rules.RuleUse(today().isoformat())
    r = ru.get("itr.44ad.rate")
    y = int(fy_of(today().isoformat())[:4])
    rows = db.q("SELECT i.total, i.id FROM invoices i WHERE i.business_id=? AND i.direction='sale' AND i.invoice_date>=? AND i.invoice_date<=?", (biz["id"], f"{y}-04-01", f"{y + 1}-03-31"))
    turnover = sum(x["total"] for x in rows)
    dig = sum(p["amount"] for p in db.q("SELECT amount FROM payments WHERE business_id=? AND mode IN ('bank','UPI') AND invoice_id IN (SELECT id FROM invoices WHERE direction='sale')", (biz["id"],)))
    dig = min(dig, turnover)
    est = calc.tds_amount(dig, r["digital"]) + calc.tds_amount(turnover - dig, r["cash"])
    return {"turnover_to_date": turnover, "digital": dig, "estimated_presumptive_income": est, "rate_digital": r["digital"], "rate_cash": r["cash"],
            "tip": "More digital receipts lower the presumptive rate from 8% to 6%.", "rules": ru.used}
