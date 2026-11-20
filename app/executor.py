"""Approval executor: the ONLY component allowed to call the portal's write endpoints or send third-party messages.
Runs only after a human approval (or an owner standing pre-approval). Not imported by any agent module."""
import json
from . import db, portal_write, portal_read, channels, rules, calc, itc
from .util import today, now_iso, audit, fmt, norm_phone


def execute(ap, user_id):
    fn = {"return": _return, "ims_action": _ims, "ewb_generate": _ewb_generate, "ewb_extend": _ewb_extend, "ewb_partb": _ewb_partb,
          "message": _message, "rule_change": _rule_change}.get(ap["item_type"])
    if not fn:
        return {"note": "no executor for " + ap["item_type"]}
    return fn(ap, json.loads(ap["payload_json"]), user_id)


def _return(ap, p, uid):
    db.update("returns", p["return_id"], status="approved", approved_by=uid)
    return {"status": "approved"}


# --- the human filing action (simulated). Called only from the API after approval + OTP ---
def request_filing_otp(return_id):
    r = db.one("SELECT * FROM returns WHERE id=?", (return_id,))
    biz = db.one("SELECT * FROM businesses WHERE id=?", (r["business_id"],))
    if r["status"] != "approved":
        raise PermissionError("Return must be approved before filing")
    return portal_write.post(f"/returns/{r['return_type']}/{biz['gstin']}/{r['period']}/otp")


def file_return(return_id, user_id, otp):
    r = db.one("SELECT * FROM returns WHERE id=?", (return_id,))
    if not r or r["status"] != "approved":
        raise PermissionError("Only approved returns can be filed")
    biz = db.one("SELECT * FROM businesses WHERE id=?", (r["business_id"],))
    c = json.loads(r["computed_json"])
    payload = {"totals": c.get("totals"), "outward": c.get("outward"), "itc": c.get("itc"), "net_cash": c.get("net_cash"), "tax_cash": c.get("tax_cash")}
    if r["return_type"] == "GSTR1":
        payload = {"totals": c["totals"], "tables": {k: (len(v) if isinstance(v, list) else v) for k, v in c["tables"].items()}}
    resp = portal_write.post(f"/returns/{r['return_type']}/{biz['gstin']}/{r['period']}/file", {"otp": otp, "payload": payload, "on_date": today().isoformat()})
    db.update("returns", return_id, status="filed_simulated", filed_at=now_iso(), ack_number=resp["ack_number"])
    ob = db.one("SELECT * FROM obligations WHERE business_id=? AND related_return_id=?", (biz["id"], return_id))
    if ob:
        db.update("obligations", ob["id"], status="done")
    audit(biz["id"], "user", user_id, "filed_simulated", "return", return_id, None, {"ack": resp["ack_number"], "otp_verified": True})
    return resp


def _ims(ap, p, uid):
    biz = db.one("SELECT * FROM businesses WHERE id=?", (ap["business_id"],))
    acts = []
    for a in p["actions"]:
        ri = db.one("SELECT * FROM reconciliation_items WHERE id=?", (a["item_id"],))
        if ri and ri["portal_2b_record_id"]:
            rec = db.one("SELECT portal_ref FROM portal_2b_records WHERE id=?", (ri["portal_2b_record_id"],))
            acts.append({"id": rec["portal_ref"], "action": a["action"]})
        if ri:
            db.update("reconciliation_items", ri["id"], decided_action=a["action"], decided_by=uid)
    if acts:
        portal_write.post(f"/ims/{biz['gstin']}/{p['period']}/actions", {"actions": acts})
    itc.reconcile_itc(biz, p["period"])
    return {"applied": len(acts)}


def _ewb_generate(ap, p, uid):
    from . import eway
    biz = db.one("SELECT * FROM businesses WHERE id=?", (ap["business_id"],))
    issues = eway.validate_ewb(biz, p["ewb_id"])
    if issues:
        raise ValueError("Validation failed: " + "; ".join(i["field"] for i in issues))
    e = db.one("SELECT * FROM eway_bills WHERE id=?", (p["ewb_id"],))
    until = eway.compute_validity(biz, e)
    resp = portal_write.post("/ewb/generate", {"part_a": json.loads(e["part_a_json"]), "part_b": {"vehicle_no": e["vehicle_no"]}, "valid_until": until, "on_date": today().isoformat()})
    number = resp["ewb_number"]
    rule = rules.get_rule("ewb.number.format", today().isoformat())
    if not calc.ewb_number_valid(number, rule["lengths"]):
        raise ValueError(f"E-way bill number {number} not accepted by current format rule {rule['lengths']}")
    db.update("eway_bills", e["id"], status="generated_simulated", ewb_number=number, valid_from=today().isoformat() + "T00:00:00", valid_until=resp["valid_until"])
    audit(biz["id"], "user" if uid else "system", uid or "preapproval", "ewb_generated_simulated", "eway_bill", e["id"], None, {"number": number})
    a = json.loads(e["part_a_json"])
    dest = _dest(a["to_pin"])
    tp = db.one("SELECT * FROM parties WHERE id=?", (e["transporter_party_id"],)) if e["transporter_party_id"] else None
    until_s = resp["valid_until"][:16].replace("T", " ")
    if tp:
        channels.send_template(biz["id"], tp["phone"], tp["name"], "m_doc_pack", {"biz": biz["trade_name"], "dest": dest, "inv": a["doc_no"], "ewb": number, "until": until_s, "veh": e["vehicle_no"]}, "en", "eway_bill", e["id"])
    inv = db.one("SELECT * FROM invoices WHERE id=?", (e["invoice_id"],))
    buyer = db.one("SELECT * FROM parties WHERE id=?", (inv["party_id"],))
    if buyer and buyer["phone"]:
        channels.send_template(biz["id"], buyer["phone"], buyer["name"], "m_buyer_copy", {"biz": biz["trade_name"], "inv": a["doc_no"], "ewb": number, "until": until_s}, "en", "eway_bill", e["id"])
    return {"ewb_number": number, "valid_until": resp["valid_until"]}


def _dest(pin):
    from .eway import PIN_DEST
    return PIN_DEST.get(pin, pin)


def _ewb_extend(ap, p, uid):
    e = db.one("SELECT * FROM eway_bills WHERE id=?", (p["ewb_id"],))
    portal_write.post(f"/ewb/{e['ewb_number']}/extend", {"new_valid_until": p["new_valid_until"]})
    db.update("eway_bills", e["id"], valid_until=p["new_valid_until"], status="extended")
    audit(ap["business_id"], "user", uid, "ewb_extended_simulated", "eway_bill", e["id"])
    return {"valid_until": p["new_valid_until"]}


def _ewb_partb(ap, p, uid):
    e = db.one("SELECT * FROM eway_bills WHERE id=?", (p["ewb_id"],))
    portal_write.post(f"/ewb/{e['ewb_number']}/partb", {"vehicle_no": p["vehicle_no"]})
    db.update("eway_bills", e["id"], vehicle_no=p["vehicle_no"])
    return {"vehicle": p["vehicle_no"]}


def _message(ap, p, uid):
    biz = db.one("SELECT * FROM businesses WHERE id=?", (ap["business_id"],))
    party = db.one("SELECT * FROM parties WHERE id=?", (p["party_id"],))
    owner = db.one("SELECT u.preferred_language l FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.business_id=? AND m.role='owner' LIMIT 1", (biz["id"],))
    lang = p.get("lang") or "en"
    rel = p.get("related") or [None, None]
    mid = channels.send_template(biz["id"], party["phone"], party["name"], p["template"], {"gstin": biz["gstin"], **p["vars"]}, lang, rel[0], rel[1])
    if rel[0] == "reconciliation_item":
        db.update("reconciliation_items", rel[1], supplier_reply=None)
    return {"message_id": mid}


def _rule_change(ap, p, uid):
    for key, val in p["proposed_values"].items():
        rules.add_version(key, val, p["effective_from"], p["source_url"], uid, "approved from rule-change proposal")
    db.update("rule_change_proposals", p["proposal_id"], status="approved", reviewed_by=uid)
    from . import tracker
    return {"notified": tracker.notify_affected(p["proposal_id"])}
