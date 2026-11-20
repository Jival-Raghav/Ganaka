"""The human approval gate. Tools that touch the outside world never execute directly: they create an `approvals`
row and return pending_approval. Only a human decision (or an owner-configured standing pre-approval for a low-risk
template) leads to execution, and execution lives in executor.py (not importable from agent modules)."""
import json
from . import db
from .util import now_iso, audit, fmt


def request_approval(business_id, item_type, item_id, payload: dict, summary: str, requested_from="owner", requested_by="agent"):
    pj = json.dumps(payload, sort_keys=True)
    dup = db.one("SELECT * FROM approvals WHERE business_id=? AND item_type=? AND item_id IS ? AND payload_json=? AND status='pending'", (business_id, item_type, item_id, pj))
    if dup:
        return {"status": "pending_approval", "approval_id": dup["id"]}
    aid = db.insert("approvals", business_id=business_id, item_type=item_type, item_id=item_id, payload_json=pj, summary=summary,
                    requested_by=requested_by, requested_from=requested_from, status="pending", created_at=now_iso())
    audit(business_id, "agent", requested_by, "approval_requested", item_type, item_id, None, {"approval_id": aid, "summary": summary})
    return {"status": "pending_approval", "approval_id": aid}


def preapproved(business_id, template_id, value=0):
    p = db.one("SELECT * FROM preapprovals WHERE business_id=? AND template_id=? AND active=1", (business_id, template_id))
    return bool(p and (p["max_value"] is None or value <= p["max_value"]))


def request_or_preapprove(business_id, item_type, item_id, payload, summary, template_id, value=0, requested_from="owner"):
    """Standing pre-approvals (set by the owner, revocable) release low-risk items automatically."""
    r = request_approval(business_id, item_type, item_id, payload, summary, requested_from)
    if template_id and preapproved(business_id, template_id, value):
        ap = db.one("SELECT * FROM approvals WHERE id=?", (r["approval_id"],))
        if ap["status"] == "pending":
            result = _approve(ap, None, "standing pre-approval")
            return {"status": "executed_preapproved", "approval_id": ap["id"], "result": result}
    return r


def ensure_return_approval(biz, rid, rtype, period, status):
    frm = "accountant" if status == "awaiting_accountant" else "owner"
    ex = db.one("SELECT * FROM approvals WHERE item_type='return' AND item_id=? AND status='pending'", (rid,))
    if ex:
        if ex["requested_from"] != frm:
            db.update("approvals", ex["id"], requested_from=frm)
        return ex["id"]
    return request_approval(biz["id"], "return", rid, {"return_id": rid}, f"{rtype} {period} draft", frm, "return_prep")["approval_id"]


def route_to_accountant(approval_id, user_id):
    ap = db.one("SELECT * FROM approvals WHERE id=?", (approval_id,))
    db.update("approvals", approval_id, requested_from="accountant")
    if ap["item_type"] == "return":
        db.update("returns", ap["item_id"], status="awaiting_accountant")
    audit(ap["business_id"], "user", user_id, "sent_to_accountant", ap["item_type"], ap["item_id"])


def _approve(ap, user_id, comment):
    from . import executor  # the only place that can act on the outside world
    db.update("approvals", ap["id"], status="approved", decided_by=user_id, decided_at=now_iso(), comment=comment)
    audit(ap["business_id"], "user" if user_id else "system", user_id or "preapproval", "approved", ap["item_type"], ap["item_id"], None, {"approval_id": ap["id"], "comment": comment})
    try:
        res = executor.execute(db.one("SELECT * FROM approvals WHERE id=?", (ap["id"],)), user_id)
    except Exception as e:  # surface errors to the approver without losing the approval record
        res = {"error": str(e)}
        audit(ap["business_id"], "system", "executor", "execution_failed", ap["item_type"], ap["item_id"], None, res)
    db.update("approvals", ap["id"], result_json=json.dumps(res))
    return res


def decide(approval_id, user, role, decision, comment=""):
    ap = db.one("SELECT * FROM approvals WHERE id=?", (approval_id,))
    if not ap or ap["status"] != "pending":
        raise ValueError("Approval is not pending")
    if role == "accountant" and ap["requested_from"] != "accountant":
        raise PermissionError("This item was not sent to the accountant")
    if role not in ("owner", "accountant"):
        raise PermissionError("Only the owner or accountant can decide")
    if decision == "approved":
        return _approve(ap, user["id"], comment)
    status = "rejected" if decision == "rejected" else "changes_requested"
    db.update("approvals", approval_id, status=status, decided_by=user["id"], decided_at=now_iso(), comment=comment)
    audit(ap["business_id"], "user", user["id"], status, ap["item_type"], ap["item_id"], None, {"comment": comment})
    if ap["item_type"] == "return":
        db.update("returns", ap["item_id"], status="draft")
    if comment and role == "accountant":
        from . import channels
        channels.notify_owner(ap["business_id"], "Accountant comment", f"{ap['summary']}: {comment}")
    return {"status": status}
