"""E-way bill agent: trigger, Part A prefill, Part B via transporter, pre-dispatch validation, validity watch."""
import json
from datetime import datetime
from . import db, calc, rules, gate, channels
from .util import today, now_iso, fmt, audit, norm_phone, add_days
from .i18n import t

PIN_DEST = {"570001": "Mysuru", "575001": "Mangaluru", "400001": "Mumbai", "411001": "Pune", "110001": "Delhi", "600001": "Chennai",
            "500001": "Hyderabad", "641001": "Coimbatore", "380001": "Ahmedabad", "560001": "Bengaluru", "682001": "Kochi", "583101": "Ballari"}


def threshold_for(biz, inv, on=None):
    on = on or inv["invoice_date"]
    inter = (inv["place_of_supply"] or biz["state_code"]) != biz["state_code"]
    if inter:
        return rules.get_rule("ewb.threshold.interstate", on), True
    th = rules.get_rule("ewb.threshold.intrastate", on)
    abbr = calc.STATES.get(biz["state_code"], ("",))[0]
    return th.get(abbr, th["default"]), False


def needs_ewb(biz, inv):
    if inv["direction"] != "sale" or not inv["goods_movement"] or inv["doc_type"] != "invoice":
        return False
    th, _ = threshold_for(biz, inv)
    return inv["total"] > th


def pending_dispatches(biz_id):
    biz = db.one("SELECT * FROM businesses WHERE id=?", (biz_id,))
    out = []
    for inv in db.q("SELECT i.*, p.name pname FROM invoices i LEFT JOIN parties p ON p.id=i.party_id WHERE i.business_id=? AND i.direction='sale' AND i.goods_movement=1", (biz_id,)):
        if needs_ewb(biz, inv):
            e = db.one("SELECT * FROM eway_bills WHERE invoice_id=? ORDER BY id DESC LIMIT 1", (inv["id"],))
            if not e or e["status"] in ("draft", "awaiting_part_b", "ready"):
                out.append({"invoice": inv, "ewb": e})
    return out


def build_part_a(biz, inv):
    lines = db.q("SELECT * FROM line_items WHERE invoice_id=?", (inv["id"],))
    meta = db.jl(inv["meta_json"], {}) or {}
    party = db.one("SELECT * FROM parties WHERE id=?", (inv["party_id"],)) or {}
    return {"supplier_gstin": biz["gstin"], "recipient_gstin": party.get("gstin") or "URP", "doc_type": "INV", "doc_no": inv["invoice_no"], "doc_date": inv["invoice_date"],
            "value": inv["total"], "taxable": inv["taxable_value"], "cgst": inv["cgst"], "sgst": inv["sgst"], "igst": inv["igst"],
            "hsn": lines[0]["hsn_sac"] if lines else "", "hsn_all": sorted({l["hsn_sac"] for l in lines}), "reason": "supply",
            "from_pin": meta.get("from_pin") or biz["address_pin"], "to_pin": meta.get("to_pin"), "recipient_name": party.get("name")}


def prepare_ewb(biz, invoice_id):
    inv = db.one("SELECT * FROM invoices WHERE id=? AND business_id=?", (invoice_id, biz["id"]))
    ex = db.one("SELECT * FROM eway_bills WHERE invoice_id=? AND status NOT IN ('expired')", (invoice_id,))
    if ex:
        return ex
    a = build_part_a(biz, inv)
    meta = db.jl(inv["meta_json"], {}) or {}
    km = calc.pin_distance_km(a["from_pin"], a["to_pin"]) if a["from_pin"] and a["to_pin"] else None
    tp = None
    if meta.get("transporter"):
        tp = _transporter(biz, meta["transporter"])
    eid = db.insert("eway_bills", business_id=biz["id"], invoice_id=invoice_id, part_a_json=json.dumps(a), transporter_party_id=tp["id"] if tp else None,
                    vehicle_no=calc.normalize_vehicle(meta.get("vehicle", ""))[0] if meta.get("vehicle") and calc.normalize_vehicle(meta["vehicle"])[1] else None,
                    distance_km=km, status="draft", created_at=now_iso())
    audit(biz["id"], "agent", "eway", "ewb_prepared", "eway_bill", eid)
    validate_ewb(biz, eid)
    request_part_b(biz, eid)
    return db.one("SELECT * FROM eway_bills WHERE id=?", (eid,))


def _transporter(biz, spec):
    name, _, phone = [x.strip() for x in spec.partition("|")]
    p = db.one("SELECT * FROM parties WHERE business_id=? AND lower(name)=lower(?) AND type='transporter'", (biz["id"], name))
    if p:
        return p
    pid = db.insert("parties", business_id=biz["id"], name=name, type="transporter", phone=norm_phone(phone) if phone else None)
    return db.one("SELECT * FROM parties WHERE id=?", (pid,))


def request_part_b(biz, eid):
    e = db.one("SELECT * FROM eway_bills WHERE id=?", (eid,))
    if e["vehicle_no"]:
        return
    inv = db.one("SELECT * FROM invoices WHERE id=?", (e["invoice_id"],))
    a = json.loads(e["part_a_json"])
    tp = db.one("SELECT * FROM parties WHERE id=?", (e["transporter_party_id"],)) if e["transporter_party_id"] else None
    if tp and tp["phone"]:
        vars_ = {"biz": biz["trade_name"], "dest": PIN_DEST.get(a["to_pin"], a["to_pin"]), "inv": a["doc_no"], "value": fmt(a["value"], False)}
        gate.request_or_preapprove(biz["id"], "message", e["id"], {"party_id": tp["id"], "template": "m_transporter_partb", "vars": vars_, "related": ["eway_bill", e["id"]]},
                                   f"Ask {tp['name']} for vehicle number (invoice {a['doc_no']})", "m_transporter_partb")
    else:
        if not db.one("SELECT 1 x FROM questions WHERE kind='ewb_transporter' AND ref_id=? AND status='open'", (eid,)):
            db.insert("questions", business_id=biz["id"], kind="ewb_transporter", ref_type="eway_bill", ref_id=eid, field="vehicle",
                      question=f"Who is carrying invoice {a['doc_no']} ({fmt(a['value'], False)})? Send the vehicle number (e.g. KA05AB1234).", status="open", created_at=now_iso())
    db.update("eway_bills", eid, status="awaiting_part_b")


def validate_ewb(biz, eid):
    """Field-by-field comparison of the e-way bill draft vs the final invoice. Mismatches block generation."""
    e = db.one("SELECT * FROM eway_bills WHERE id=?", (eid,))
    inv = db.one("SELECT * FROM invoices WHERE id=?", (e["invoice_id"],))
    a = json.loads(e["part_a_json"])
    cur = build_part_a(biz, inv)
    issues = []
    for k, label in [("supplier_gstin", "Supplier GSTIN"), ("recipient_gstin", "Recipient GSTIN"), ("doc_no", "Invoice number"), ("doc_date", "Invoice date"),
                     ("hsn", "HSN"), ("taxable", "Taxable value"), ("value", "Invoice value"), ("igst", "IGST"), ("cgst", "CGST"), ("sgst", "SGST"),
                     ("from_pin", "Dispatch PIN"), ("to_pin", "Delivery PIN")]:
        if a.get(k) != cur.get(k):
            fm = (lambda v: fmt(v)) if k in ("taxable", "value", "igst", "cgst", "sgst") else (lambda v: v)
            issues.append({"field": label, "ewb": fm(a.get(k)), "invoice": fm(cur.get(k)), "fix": "Refresh Part A from the final invoice"})
    for fld in ("from_pin", "to_pin"):
        if not cur.get(fld) or not str(cur[fld]).isdigit() or len(str(cur[fld])) != 6:
            issues.append({"field": fld, "ewb": a.get(fld), "invoice": cur.get(fld), "fix": "PIN code must be 6 digits"})
    if e["vehicle_no"] and not calc.normalize_vehicle(e["vehicle_no"])[1]:
        issues.append({"field": "Vehicle number", "ewb": e["vehicle_no"], "invoice": None, "fix": "Invalid vehicle format"})
    if issues:
        audit(biz["id"], "agent", "eway", "ewb_validation_blocked", "eway_bill", eid, None, {"issues": issues})
    status = e["status"]
    if status in ("draft", "awaiting_part_b", "ready"):
        status = "draft" if issues else ("ready" if e["vehicle_no"] else "awaiting_part_b")
    db.update("eway_bills", eid, issues_json=json.dumps(issues), status=status)
    return issues


def refresh_part_a(biz, eid):
    e = db.one("SELECT * FROM eway_bills WHERE id=?", (eid,))
    inv = db.one("SELECT * FROM invoices WHERE id=?", (e["invoice_id"],))
    a = build_part_a(biz, inv)
    km = calc.pin_distance_km(a["from_pin"], a["to_pin"]) if a["from_pin"] and a["to_pin"] else e["distance_km"]
    db.update("eway_bills", eid, part_a_json=json.dumps(a), distance_km=km)
    audit(biz["id"], "agent", "eway", "ewb_part_a_refreshed", "eway_bill", eid)
    return validate_ewb(biz, eid)


def set_vehicle(biz, eid, text):
    n, ok = calc.normalize_vehicle(text)
    if not ok:
        return {"ok": False, "message": f"'{text}' is not a valid vehicle number (expected like KA05AB1234)."}
    db.update("eway_bills", eid, vehicle_no=n)
    issues = validate_ewb(biz, eid)
    return {"ok": True, "vehicle": n, "issues": issues, "status": db.one("SELECT status FROM eway_bills WHERE id=?", (eid,))["status"]}


def request_generate(biz, eid):
    """Approval-gated. Below the owner's pre-approved value, valid drafts are released automatically."""
    e = db.one("SELECT * FROM eway_bills WHERE id=?", (eid,))
    issues = validate_ewb(biz, eid)
    e = db.one("SELECT * FROM eway_bills WHERE id=?", (eid,))
    if issues:
        return {"status": "blocked", "issues": issues}
    if not e["vehicle_no"]:
        return {"status": "blocked", "issues": [{"field": "Part B", "fix": "Vehicle number missing"}]}
    a = json.loads(e["part_a_json"])
    return gate.request_or_preapprove(biz["id"], "ewb_generate", eid, {"ewb_id": eid}, f"Generate e-way bill for {a['doc_no']} ({fmt(a['value'], False)}) vehicle {e['vehicle_no']}",
                                      "ewb_generate", a["value"])


def compute_validity(biz, e, on=None):
    on = on or today().isoformat()
    kmpd = rules.get_rule("ewb.validity", on)["km_per_day"]
    return calc.ewb_valid_until(on, e["distance_km"] or 1, kmpd)


def validity_watch(biz, now=None):
    """Alert transporter/owner before expiry; mark expired."""
    now = now or datetime.fromisoformat(now_iso().replace("Z", ""))
    out = []
    for e in db.q("SELECT * FROM eway_bills WHERE business_id=? AND status IN ('generated_simulated','extended')", (biz["id"],)):
        until = datetime.fromisoformat(e["valid_until"])
        hrs = (until - now).total_seconds() / 3600
        if hrs < 0:
            db.update("eway_bills", e["id"], status="expired"); out.append({"ewb": e["ewb_number"], "state": "expired"}); continue
        if hrs <= 12:
            tp = db.one("SELECT * FROM parties WHERE id=?", (e["transporter_party_id"],)) if e["transporter_party_id"] else None
            if tp and not db.one("SELECT 1 x FROM messages WHERE template_id='m_ewb_expiry' AND related_id=? AND business_id=?", (e["id"], biz["id"])):
                gate.request_or_preapprove(biz["id"], "message", e["id"], {"party_id": tp["id"], "template": "m_ewb_expiry",
                                           "vars": {"biz": biz["trade_name"], "ewb": e["ewb_number"], "until": e["valid_until"][:16].replace("T", " "), "veh": e["vehicle_no"]},
                                           "related": ["eway_bill", e["id"]]}, f"Warn transporter: e-way bill {e['ewb_number']} expiring", "m_ewb_expiry")
            channels.notify_owner(biz["id"], "E-way bill expiring", f"E-way bill {e['ewb_number']} expires in {int(hrs)} hours. Extend?")
            out.append({"ewb": e["ewb_number"], "state": "expiring", "hours": round(hrs, 1)})
    return out


def request_extension(biz, eid, extra_km=None):
    e = db.one("SELECT * FROM eway_bills WHERE id=?", (eid,))
    kmpd = rules.get_rule("ewb.validity", today().isoformat())["km_per_day"]
    base = datetime.fromisoformat(e["valid_until"][:10]).date().isoformat()
    new = calc.ewb_valid_until(base if base >= today().isoformat() else today().isoformat(), extra_km or kmpd, kmpd)
    new = add_days(e["valid_until"][:10], 1) + "T23:59:00" if not extra_km else new
    return gate.request_approval(biz["id"], "ewb_extend", eid, {"ewb_id": eid, "new_valid_until": new}, f"Extend e-way bill {e['ewb_number']} to {new[:10]}", "owner")


def handle_transporter_reply(biz, party, text):
    """Parse vehicle numbers and 'vehicle changed' / EXTEND replies from transporters."""
    low = text.lower()
    e = db.one("SELECT * FROM eway_bills WHERE business_id=? AND transporter_party_id=? AND status IN ('awaiting_part_b','draft','ready','generated_simulated','extended') ORDER BY id DESC LIMIT 1", (biz["id"], party["id"]))
    if not e:
        return "No active dispatch for you right now. Thank you."
    if "extend" in low:
        request_extension(biz, e["id"])
        return "Noted: extension requested from the owner."
    n, ok = calc.normalize_vehicle(text)
    if not ok:
        return "Sorry, that doesn't look like a vehicle number. Please send like KA05AB1234."
    if e["status"] in ("generated_simulated", "extended") and e["ewb_number"]:
        db.update("eway_bills", e["id"], vehicle_no=n)
        gate.request_approval(biz["id"], "ewb_partb", e["id"], {"ewb_id": e["id"], "vehicle_no": n}, f"Update Part B of e-way bill {e['ewb_number']} to vehicle {n}", "owner")
        return f"Thanks, vehicle changed to {n}. Part B update sent for approval."
    r = set_vehicle(biz, e["id"], text)
    audit(biz["id"], "agent", "eway", "part_b_received", "eway_bill", e["id"], None, {"vehicle": n})
    if r["ok"] and not r["issues"]:
        a = json.loads(e["part_a_json"])
        channels.notify_owner(biz["id"], "E-way bill ready", f"Vehicle {n} received for invoice {a['doc_no']}. Approve generation.")
    return f"Thank you, vehicle {n} recorded."


def held_truck_pack(biz, eid):
    e = db.one("SELECT * FROM eway_bills WHERE id=?", (eid,))
    inv = db.one("SELECT i.*, p.name buyer FROM invoices i LEFT JOIN parties p ON p.id=i.party_id WHERE i.id=?", (e["invoice_id"],))
    pay = db.q("SELECT * FROM payments WHERE invoice_id=?", (inv["id"],))
    return {"title": "Truck stopped: proof pack", "invoice": {"no": inv["invoice_no"], "date": inv["invoice_date"], "value": fmt(inv["total"]), "buyer": inv["buyer"]},
            "eway_bill": {"number": e["ewb_number"], "valid_until": e["valid_until"], "vehicle": e["vehicle_no"], "status": e["status"]},
            "route": json.loads(e["part_a_json"]) and {"from": json.loads(e["part_a_json"])["from_pin"], "to": json.loads(e["part_a_json"])["to_pin"], "km": e["distance_km"]},
            "payment_proof": [{"amount": fmt(p["amount"]), "date": p["date"], "mode": p["mode"]} for p in pay] or "No payment recorded yet",
            "lorry_receipt": "Attach LR copy from driver (not stored in demo)", "send_to": ["driver", "accountant"]}


def on_invoice_posted(biz_id, inv_id):
    biz = db.one("SELECT * FROM businesses WHERE id=?", (biz_id,))
    inv = db.one("SELECT * FROM invoices WHERE id=?", (inv_id,))
    if needs_ewb(biz, inv):
        e = prepare_ewb(biz, inv_id)
        channels.notify_owner(biz_id, "E-way bill needed", f"Invoice {inv['invoice_no']} ({fmt(inv['total'], False)}) needs an e-way bill before the truck leaves.")
        return e
