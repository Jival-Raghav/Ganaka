"""Rule-tracker agent: watch official sources -> detect new items -> understand -> propose rule change -> accountant approves -> notify."""
import json, re
from . import db, rules, portal_read, gate, channels
from .util import today, now_iso, audit
from .i18n import t


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def understand(item):
    """Stub for the LLM reading step: maps an advisory to rule keys with quoted evidence (structured output)."""
    body = item["title"] + ". " + item["body"]
    low = body.lower()
    changes = []
    if re.search(r"14[- ]digit", low) and "e-way" in low:
        m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})", low)
        months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
        eff = f"{m.group(3)}-{months.index(m.group(2)) + 1:02d}-{int(m.group(1)):02d}" if m else None
        ev = next((s for s in _sentences(body) if "14" in s), body[:200])
        if eff:
            changes.append({"key": "ewb.number.format", "value": {"lengths": [12, 14]}, "effective_from": eff, "evidence": ev})
    m = re.search(r"intra-?state e-?way bill.*?threshold.*?(?:for|in)\s+([A-Za-z ]+?)\s+(?:raised|revised|changed|increased)?\s*(?:to)?\s*(?:rs\.?|₹)\s*([\d,]+)", low)
    if m:
        abbr = {"karnataka": "KA", "maharashtra": "MH", "tamil nadu": "TN", "kerala": "KL", "gujarat": "GJ", "delhi": "DL"}.get(m.group(1).strip())
        eff = re.search(r"(?:from|effective)\s+(\d{4}-\d{2}-\d{2})", low)
        if abbr and eff:
            cur = rules.get_rule("ewb.threshold.intrastate", today().isoformat())
            changes.append({"key": "ewb.threshold.intrastate", "value": {**cur, abbr: int(m.group(2).replace(",", "")) * 100}, "effective_from": eff.group(1),
                            "evidence": next((s for s in _sentences(body) if "threshold" in s.lower()), body[:200])})
    return changes


def scan():
    items = portal_read.get("/advisories")["items"]
    created = []
    for it in items:
        if db.one("SELECT 1 x FROM seen_sources WHERE url=?", (it["url"],)):
            continue
        db.insert("seen_sources", url=it["url"], seen_at=now_iso())
        ch = understand(it)
        if not ch:
            continue
        cur_vals = {c["key"]: rules.get_rule(c["key"], today().isoformat()) for c in ch}
        pid = db.insert("rule_change_proposals", source_url=it["url"], source_title=it["title"], detected_at=now_iso(), summary=it["title"],
                        affected_rule_keys=json.dumps([c["key"] for c in ch]),
                        proposed_values=json.dumps({"old": cur_vals, "new": {c["key"]: c["value"] for c in ch}}), effective_from=ch[0]["effective_from"],
                        evidence=json.dumps([c["evidence"] for c in ch]), status="pending")
        db.update("rule_change_proposals", pid, impact_json=json.dumps(impact(pid)))
        payload = {"proposal_id": pid, "proposed_values": {c["key"]: c["value"] for c in ch}, "effective_from": ch[0]["effective_from"], "source_url": it["url"]}
        gate.request_approval(0, "rule_change", pid, payload, f"Rule change: {it['title']}", "accountant", "rule_tracker")
        created.append(pid)
    return created


def impact(pid):
    p = db.one("SELECT * FROM rule_change_proposals WHERE id=?", (pid,))
    keys = json.loads(p["affected_rule_keys"])
    out = []
    for b in db.q("SELECT * FROM businesses"):
        if any(k.startswith("ewb.") for k in keys):
            n = db.one("SELECT COUNT(*) c FROM invoices WHERE business_id=? AND direction='sale' AND goods_movement=1", (b["id"],))["c"]
            if n:
                out.append({"business_id": b["id"], "name": b["trade_name"], "reason": f"{n} dispatches with goods movement"})
        else:
            out.append({"business_id": b["id"], "name": b["trade_name"], "reason": "all GST taxpayers"})
    return out


def notify_affected(pid):
    p = db.one("SELECT * FROM rule_change_proposals WHERE id=?", (pid,))
    n = 0
    for b in json.loads(p["impact_json"] or "[]"):
        owner = db.one("SELECT u.preferred_language l FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.business_id=? AND m.role='owner' LIMIT 1", (b["business_id"],))
        lang = owner["l"] if owner else "en"
        what = "e-way bill numbers will have 14 digits" if "ewb.number.format" in p["affected_rule_keys"] else "a GST rule changes"
        action = "Nothing to do: Ganaka already accepts the new format." if "ewb.number.format" in p["affected_rule_keys"] else "Your accountant has reviewed the change."
        channels.notify_owner(b["business_id"], t("rule_change", lang, title=p["source_title"], date=p["effective_from"], what=what, action=action).split(".")[0], t("rule_change", lang, title=p["source_title"], date=p["effective_from"], what=what, action=action), lang)
        n += 1
    return n
