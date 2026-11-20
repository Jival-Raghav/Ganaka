"""Conversational orchestrator (deterministic intent router standing in for the LLM). Numbers come only from tool outputs;
a post-check rejects answers containing amounts that are not in tool output."""
import json, re
from . import db, returns, itc, eway, calendar_, notices, tds, tools
from .i18n import t, detect_lang, BCP
from .util import today, fmt, now_iso, audit

INTENTS = [
    ("ewb", ["e-way", "eway", "e way", "dispatch", "truck", "sending goods", "lorry", "ಇ-ವೇ", "ई-वे", "transport"]),
    ("itc", ["itc", "credit", "stuck", "input", "ಕ್ರೆಡಿಟ್", "क्रेडिट", "supplier", "mismatch"]),
    ("notice", ["notice", "risk", "ನೋಟಿಸ್", "नोटिस"]),
    ("tds", ["tds"]),
    ("deadline", ["due", "deadline", "calendar", "when", "ಗಡುವು", "डेडलाइन", "date"]),
    ("bills", ["bill", "inbox", "received", "invoice", "document", "ಬಿಲ್", "बिल"]),
    ("approvals", ["approve", "approval", "pending", "waiting"]),
    ("suppliers", ["supplier", "reliab"]),
    ("gst", ["gst", "tax", "pay", "eshtu", "kitna", "ತೆರಿಗೆ", "कर", "return", "liability"]),
    ("hello", ["hello", "hi", "hey", "namaste", "namaskara", "ನಮಸ್ಕಾರ", "नमस्ते"]),
]


def default_period(biz):
    y, m = today().year, today().month
    m -= 1
    if m == 0:
        y, m = y - 1, 12
    if biz["gst_scheme"] in ("qrmp", "composition"):
        while m % 3:
            m -= 1
            if m == 0:
                y, m = y - 1, 12
    return f"{y}-{m:02d}"


def intent_of(text):
    low = text.lower()
    scored = [(sum(k in low for k in kws), name) for name, kws in INTENTS]
    best = max(scored, key=lambda x: x[0])
    return best[1] if best[0] else "fallback"


def _numbers_in(text):
    return {int(x.replace(",", "")) for x in re.findall(r"₹\s?([\d,]+)", text)}


def _facts(obj, acc=None):
    acc = acc if acc is not None else set()
    if isinstance(obj, bool):
        return acc
    if isinstance(obj, int):
        acc.add(obj // 100)
    elif isinstance(obj, dict):
        for v in obj.values():
            _facts(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _facts(v, acc)
    return acc


def postcheck(text, tool_outputs):
    facts = _facts(tool_outputs)
    return all(n in facts for n in _numbers_in(text))


def handle(biz, user, text, channel="web"):
    lang = detect_lang(text, user["preferred_language"] if user else "en")
    intent = intent_of(text)
    calls, cards, outputs = [], [], []
    ans = ""
    period = default_period(biz)
    if intent == "hello":
        ans = t("hello", lang, name=user["name"].split()[0] if user else "")
    elif intent == "gst":
        r = tools.TOOLS["compute_gst_liability"][0](biz, period); calls.append("compute_gst_liability"); outputs.append(r)
        ans = t("gst_summary", lang, period=period, sales=fmt(r["sales"], False), output=fmt(r["output_tax"], False), itc=fmt(r["itc"], False), cash=fmt(r["cash"], False), due=r["due"])
        if r["itc_stuck"]:
            ans += " " + t("itc_stuck", lang, amount=fmt(r["itc_stuck"], False), suppliers=returns._stuck_suppliers(biz, period))
        ret = db.one("SELECT id FROM returns WHERE business_id=? AND return_type='GSTR3B' AND period=?", (biz["id"], period))
        if not ret:
            returns.draft_gstr1(biz, period); ret = {"id": returns.draft_gstr3b(biz, period)["return_id"]}
            calls += ["draft_gstr1", "draft_gstr3b"]
        cards.append({"type": "gst", "title": f"GSTR-3B {period}", "rows": [["Sales (taxable)", fmt(r["sales"], False)], ["GST on sales", fmt(r["output_tax"], False)], ["Input credit used", fmt(r["itc"], False)],
                                                                          ["Credit stuck", fmt(r["itc_stuck"], False)], ["Cash to pay", fmt(r["cash"], False)], ["Due", r["due"]]],
                      "actions": [{"label": "View proof", "href": f"/api/returns/{ret['id']}/proof"}, {"label": "Open return", "nav": f"returns/{ret['id']}"}]})
    elif intent == "itc":
        s = itc.reconcile_itc(biz, period); calls.append("reconcile_itc"); outputs.append(s)
        risky = [i for i in s["items"] if i["itc_at_risk"] > 0]
        if risky:
            ans = t("itc_stuck", lang, amount=fmt(s["itc_at_risk"], False), suppliers=", ".join(sorted({i["party_name"] for i in risky if i["party_name"]})[:3]))
            cards.append({"type": "itc", "title": f"ITC at risk {period}", "rows": [[f"{i['party_name']} {i['inv_no']}", fmt(i["itc_at_risk"], False)] for i in risky[:5]],
                          "actions": [{"label": "Review & approve actions", "nav": "suppliers"}]})
        else:
            ans = t("itc_none", lang)
    elif intent == "ewb":
        pend = eway.pending_dispatches(biz["id"]); calls.append("pending_dispatches")
        if pend:
            p = pend[0]; outputs.append([p["invoice"]["total"]])
            ans = t("ewb_need", lang, n=len(pend), inv=p["invoice"]["invoice_no"], value=fmt(p["invoice"]["total"], False))
            cards.append({"type": "ewb", "title": "E-way bills needed", "rows": [[f"{x['invoice']['invoice_no']} → {x['invoice']['pname']}", fmt(x["invoice"]["total"], False)] for x in pend], "actions": [{"label": "Open e-way bills", "nav": "ewb"}]})
        else:
            ans = t("ewb_none", lang)
    elif intent == "bills":
        docs = db.q("SELECT status FROM raw_documents WHERE business_id=?", (biz["id"],))
        ans = t("bills", lang, n=len(docs), posted=sum(d["status"] == "posted" for d in docs), review=sum(d["status"] == "needs_review" for d in docs))
        cards.append({"type": "inbox", "title": "Inbox", "rows": [], "actions": [{"label": "Open inbox", "nav": "inbox"}]})
    elif intent == "deadline":
        nd = calendar_.next_deadlines(biz["id"], 3)
        ans = t("deadlines", lang, list="; ".join(f"{o['label']} on {o['due_date']}" for o in nd) or "none")
        cards.append({"type": "calendar", "title": "Deadlines", "rows": [[o["label"], o["due_date"]] for o in nd], "actions": [{"label": "Open calendar", "nav": "calendar"}]})
    elif intent == "notice":
        n = db.q("SELECT * FROM notices WHERE business_id=? AND status='open' ORDER BY reply_due_date", (biz["id"],))
        risks = db.q("SELECT * FROM risk_findings WHERE business_id=? AND status='open'", (biz["id"],))
        ans = t("notices", lang, n=len(n), due=n[0]["reply_due_date"]) if n else t("no_notices", lang, risks=len(risks))
    elif intent == "tds":
        a = tds.applicability(biz); calls.append("tds.applicability"); outputs.append(a)
        ans = a["text"]
    elif intent == "approvals":
        n = db.one("SELECT COUNT(*) c FROM approvals WHERE business_id=? AND status='pending' AND requested_from='owner'", (biz["id"],))["c"]
        ans = t("approvals", lang, n=n)
        cards.append({"type": "approvals", "title": "Approvals", "rows": [], "actions": [{"label": "Open approvals", "nav": "approvals"}]})
    elif intent == "suppliers":
        sp = [s for s in itc.supplier_report(biz["id"]) if s["reliability_score"] is not None]
        if sp:
            ans = t("suppliers", lang, name=sp[0]["name"], pct=int(sp[0]["reliability_score"]))
        else:
            ans = t("itc_none", lang)
    else:
        ans = t("fallback", lang)
    if not postcheck(ans, outputs) and outputs:
        ans = t("safe_fail", lang)
    audit(biz["id"], "agent", "orchestrator", "chat_answer", "chat", None, {"q": text[:200]}, {"intent": intent, "tools": calls})
    res = {"text": ans, "cards": cards, "lang": lang, "bcp47": BCP[lang], "intent": intent, "tools": calls}
    _remember(biz, user, channel, text, res)
    return res


def _remember(biz, user, channel, text, res):
    row = db.one("SELECT * FROM conversations WHERE business_id=? AND user_id=?", (biz["id"], user["id"] if user else None))
    hist = db.jl(row["history_json"], []) if row else []
    hist += [{"role": "user", "text": text, "channel": channel, "at": now_iso()}, {"role": "agent", "text": res["text"], "cards": res["cards"], "channel": channel, "at": now_iso()}]
    hist = hist[-60:]
    if row:
        db.update("conversations", row["id"], history_json=json.dumps(hist), channel=channel)
    else:
        db.insert("conversations", business_id=biz["id"], user_id=user["id"] if user else None, channel=channel, history_json=hist)
