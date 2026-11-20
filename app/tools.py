"""Typed tools the agents may call. There is deliberately NO filing/submission tool: filing is a human UI action
(executor.file_return, reachable only from the authenticated API after approval + OTP)."""
import json
from . import db, rules, itc, returns, eway, notices, tds, calendar_, gate, channels, tracker
from .util import today, now_iso, fmt

QUERYABLE = {"invoices", "line_items", "parties", "payments", "raw_documents", "returns", "obligations", "notices", "eway_bills", "reconciliation_items", "bank_transactions", "tds_entries"}


def query_ledger(biz, table, where="", args=()):
    if table not in QUERYABLE:
        raise ValueError("table not queryable")
    if table == "line_items":
        return db.q("SELECT l.* FROM line_items l JOIN invoices i ON i.id=l.invoice_id WHERE i.business_id=?", (biz["id"],))
    return db.q(f"SELECT * FROM {table} WHERE business_id=?" + (f" AND ({where})" if where else ""), (biz["id"], *args))


def get_document(biz, doc_id):
    return db.one("SELECT * FROM raw_documents WHERE id=? AND business_id=?", (doc_id, biz["id"]))


def get_rule(rule_key, date=None):
    return rules.get_rule(rule_key, date or today().isoformat())


def apply_ims_action(biz, period, item_actions):
    """item_actions: [{item_id, action}] -> approval, never applied directly."""
    return gate.request_approval(biz["id"], "ims_action", None, {"period": period, "actions": item_actions}, f"Apply {len(item_actions)} IMS action(s) for {period}", "owner")


def bulk_ims_actions(biz, period):
    m = {"accept": "accepted", "pending": "pending", "reject": "rejected"}
    acts = [{"item_id": r["id"], "action": m[r["recommended_action"]]} for r in itc.list_items(biz["id"], period)
            if r["portal_2b_record_id"] and r["recommended_action"] in m and not r["decided_action"]]
    return apply_ims_action(biz, period, acts) if acts else {"status": "nothing_to_apply"}


def generate_ewb(biz, ewb_id):
    return eway.request_generate(biz, ewb_id)


def nudge_supplier(biz, item_id, lang="en"):
    it = next((r for r in itc.list_items(biz["id"]) if r["id"] == item_id), None)
    if not it or not it["party_id"]:
        return {"status": "error", "message": "no supplier"}
    party = db.one("SELECT * FROM parties WHERE id=?", (it["party_id"],))
    if it["match_status"] == "missing_in_2b":
        tpl, v = "m_supplier_missing_2b", {"biz": biz["trade_name"], "inv": it["book_inv_no"], "date": it["book_date"], "amount": fmt(it["book_taxable"] + it["book_tax"], False)}
    elif it["match_status"] in ("value_mismatch", "gstin_mismatch"):
        tpl, v = "m_supplier_mismatch", {"biz": biz["trade_name"], "inv": it["inv_no"], "date": it["book_date"] or it["p_date"], "ours": fmt(it["book_taxable"] or 0, False), "theirs": fmt(it["p_taxable"] or 0, False)}
    else:
        return {"status": "error", "message": "no nudge needed"}
    return send_message(biz, party["id"], tpl, v, lang, ("reconciliation_item", item_id), f"Nudge {party['name']} about {it['inv_no']}")


def send_message(biz, party_id, template, vars_, lang="en", related=None, summary=None):
    return gate.request_or_preapprove(biz["id"], "message", related[1] if related else None, {"party_id": party_id, "template": template, "vars": vars_, "lang": lang, "related": list(related) if related else None},
                                      summary or f"Send {template}", template)


def request_approval(biz, item_type, item_id, payload, summary, frm="owner"):
    return gate.request_approval(biz["id"], item_type, item_id, payload, summary, frm)


def ask_owner(biz, question, options=None):
    return db.insert("questions", business_id=biz["id"], kind="ask_owner", ref_type="chat", ref_id=None, field=None, question=question,
                     options_json=json.dumps(options) if options else None, status="open", created_at=now_iso())


def create_reminder(biz, obligation_type, label, period, due):
    return calendar_._add(biz["id"], obligation_type, label, period, due)


def propose_rule_change(source_item):
    return tracker.understand(source_item)


TOOLS = {
    "query_ledger": (query_ledger, False), "get_document": (get_document, False), "get_rule": (get_rule, False),
    "compute_gst_liability": (returns.compute_gst_liability, False), "draft_gstr1": (returns.draft_gstr1, False), "draft_gstr3b": (returns.draft_gstr3b, False),
    "reconcile_itc": (itc.reconcile_itc, False), "recommend_ims_action": (itc.recommend_ims_action, False), "apply_ims_action": (apply_ims_action, True),
    "prepare_ewb": (eway.prepare_ewb, False), "validate_ewb": (eway.validate_ewb, False), "generate_ewb": (generate_ewb, True),
    "explain_notice": (notices.explain_notice, False), "ask_owner": (ask_owner, False), "send_message": (send_message, True),
    "request_approval": (request_approval, False), "create_reminder": (create_reminder, False), "propose_rule_change": (propose_rule_change, False),
}
