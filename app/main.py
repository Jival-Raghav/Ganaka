"""Ganaka API gateway (FastAPI). Website and WhatsApp call the same orchestrator."""
import json, os, secrets, re
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form, Depends, Header
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from . import db, rules, portal, seed, ingest, itc, returns, eway, tds, notices, calendar_, tracker, gate, executor, channels, orchestrator, gmail, jobs, proof, sarvam, calc
from .util import today, now_iso, fmt, audit, norm_phone, rupees
from .i18n import LANGS

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Ganaka", version="1.0")
app.mount("/portal", portal.app)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
OTP = "123456"


@app.on_event("startup")
def startup():
    seed.run()
    if os.environ.get("MUNSHI_SCHEDULER", "1") == "1":
        jobs.start()


# ---------------- auth ----------------
def current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not logged in")
    s = db.one("SELECT * FROM sessions WHERE token=?", (authorization[7:],))
    if not s:
        raise HTTPException(401, "Invalid session")
    return db.one("SELECT * FROM users WHERE id=?", (s["user_id"],))


class OtpReq(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None


class VerifyReq(OtpReq):
    otp: str


def _find_user(b):
    if b.email:
        u = db.one("SELECT * FROM users WHERE email=?", (b.email.lower(),))
        if not u or u["password"] != b.password:
            raise HTTPException(401, "Wrong email or password")
        return u
    u = db.one("SELECT * FROM users WHERE phone=?", (norm_phone(b.phone or ""),))
    if not u:
        raise HTTPException(404, "No account for this phone. Register via onboarding.")
    return u


@app.post("/api/auth/otp")
def auth_otp(b: OtpReq):
    _find_user(b)
    return {"sent": True, "demo_otp": OTP}


@app.post("/api/auth/verify")
def auth_verify(b: VerifyReq):
    u = _find_user(b)
    if b.otp != OTP:
        raise HTTPException(401, "Wrong OTP")
    tok = secrets.token_urlsafe(24)
    db.insert("sessions", token=tok, user_id=u["id"], created_at=now_iso())
    return {"token": tok, "user": _public(u)}


def _public(u):
    return {k: u[k] for k in ("id", "name", "phone", "email", "preferred_language")}


@app.get("/api/me")
def me(u=Depends(current_user)):
    ms = db.q("""SELECT m.role, m.business_id, b.trade_name, b.legal_name, b.gstin, b.business_type, b.gst_scheme, b.state_code, b.default_route FROM memberships m JOIN businesses b ON b.id=m.business_id
                 WHERE m.user_id=? AND m.revoked_at IS NULL ORDER BY b.id""", (u["id"],))
    return {"user": _public(u), "memberships": ms, "languages": LANGS, "today": today().isoformat()}


class LangReq(BaseModel):
    lang: str


@app.put("/api/me/lang")
def set_lang(b: LangReq, u=Depends(current_user)):
    if b.lang not in LANGS:
        raise HTTPException(400, "unsupported")
    db.update("users", u["id"], preferred_language=b.lang)
    return {"ok": True}


class Onboard(BaseModel):
    name: str
    phone: str
    legal_name: str
    trade_name: str
    gstin: str
    business_type: str
    gst_scheme: str = "regular"
    udyam_registered: bool = False
    employee_count: int = 0
    language: str = "en"
    constitution: str = "proprietor"
    address_pin: Optional[str] = None
    accountant_email: Optional[str] = None


@app.post("/api/onboard")
def onboard(b: Onboard):
    if not calc.gstin_valid(b.gstin):
        raise HTTPException(400, "GSTIN fails format/checksum validation")
    if db.one("SELECT 1 x FROM businesses WHERE gstin=?", (b.gstin,)):
        raise HTTPException(409, "GSTIN already registered")
    u = db.one("SELECT * FROM users WHERE phone=?", (norm_phone(b.phone),))
    uid = u["id"] if u else db.insert("users", name=b.name, phone=norm_phone(b.phone), preferred_language=b.language)
    bid = db.insert("businesses", legal_name=b.legal_name, trade_name=b.trade_name, gstin=b.gstin, pan=b.gstin[2:12], state_code=b.gstin[:2], business_type=b.business_type,
                    gst_scheme=b.gst_scheme, udyam_registered=int(b.udyam_registered), employee_count=b.employee_count, constitution=b.constitution, address_pin=b.address_pin, phone=norm_phone(b.phone), created_at=now_iso())
    seed.member(uid, bid, "owner")
    if b.accountant_email:
        acc = db.one("SELECT * FROM users WHERE email=?", (b.accountant_email.lower(),))
        if acc:
            fm = db.one("SELECT firm_id FROM memberships WHERE user_id=? AND role='accountant' LIMIT 1", (acc["id"],))
            seed.member(acc["id"], bid, "accountant", fm["firm_id"] if fm else None)
    biz = db.one("SELECT * FROM businesses WHERE id=?", (bid,))
    calendar_.generate_obligations(biz)
    return {"business_id": bid, "message": f"Business created. Modules on: {_modules(b.business_type)}. Log in with OTP {OTP} (demo)."}


def _modules(t):
    return {"trader": "GST, ITC reconciliation, e-way bills, TDS check, calendar", "manufacturer": "all trader modules + job-work + stock movement",
            "transporter": "GST (RCM), e-way Part B updates, calendar", "service": "GST, TDS (26AS), calendar"}.get(t, "GST, calendar")


def access(user, bid, roles=("owner", "staff", "accountant")):
    m = db.one("SELECT * FROM memberships WHERE user_id=? AND business_id=? AND revoked_at IS NULL", (user["id"], bid))
    if not m or m["role"] not in roles:
        raise HTTPException(403, "No access to this business")
    return m["role"], db.one("SELECT * FROM businesses WHERE id=?", (bid,))


# ---------------- owner: home / chat / voice ----------------
@app.get("/api/b/{bid}/home")
def home(bid: int, u=Depends(current_user)):
    role, biz = access(u, bid)
    period = orchestrator.default_period(biz)
    liab = returns.compute_gst_liability(biz, period)
    recon = itc.list_items(bid, period)
    return {"business": biz, "period": period, "liability": liab, "itc_at_risk": sum(r["itc_at_risk"] for r in recon),
            "deadlines": calendar_.next_deadlines(bid, 3), "approvals_waiting": db.one("SELECT COUNT(*) c FROM approvals WHERE business_id=? AND status='pending' AND requested_from='owner'", (bid,))["c"],
            "questions": db.q("SELECT * FROM questions WHERE business_id=? AND status='open' ORDER BY id", (bid,)),
            "notifications": db.q("SELECT * FROM notifications WHERE business_id=? ORDER BY id DESC LIMIT 8", (bid,)),
            "pending_dispatches": [{"invoice_no": p["invoice"]["invoice_no"], "value": p["invoice"]["total"], "ewb_status": p["ewb"]["status"] if p["ewb"] else None} for p in eway.pending_dispatches(bid)],
            "expiring_docs": [d for d in calendar_.vault(bid) if d["state"] != "ok"], "open_notices": db.one("SELECT COUNT(*) c FROM notices WHERE business_id=? AND status='open'", (bid,))["c"]}


class ChatReq(BaseModel):
    text: str
    channel: str = "web"


@app.post("/api/b/{bid}/chat")
def chat(bid: int, b: ChatReq, u=Depends(current_user)):
    role, biz = access(u, bid)
    return orchestrator.handle(biz, u, b.text, b.channel)


@app.get("/api/b/{bid}/chat")
def chat_history(bid: int, u=Depends(current_user)):
    access(u, bid)
    row = db.one("SELECT * FROM conversations WHERE business_id=? AND user_id=?", (bid, u["id"]))
    return db.jl(row["history_json"], []) if row else []


@app.post("/api/voice/transcribe")
async def stt(file: UploadFile = File(...), lang: str = Form("kn"), u=Depends(current_user)):
    try:
        text = sarvam.transcribe(await file.read(), file.filename or "a.webm", lang)
    except Exception as e:
        return {"text": None, "error": str(e)}
    return {"text": text, "engine": "sarvam" if sarvam.enabled() else "none"}


class TtsReq(BaseModel):
    text: str
    lang: str = "en"


@app.post("/api/voice/speak")
def tts(b: TtsReq, u=Depends(current_user)):
    try:
        a = sarvam.speak(b.text, b.lang)
    except Exception as e:
        return {"audio_base64": None, "error": str(e)}
    return {"audio_base64": a, "engine": "sarvam" if sarvam.enabled() else "browser"}


# ---------------- inbox / questions ----------------
@app.get("/api/b/{bid}/inbox")
def inbox(bid: int, u=Depends(current_user)):
    access(u, bid)
    docs = db.q("SELECT id, channel, sender, received_at, filename, status, doc_type, confidence, linked_invoice_id, note, typed_text FROM raw_documents WHERE business_id=? ORDER BY id DESC", (bid,))
    for d in docs:
        d["questions"] = db.q("SELECT * FROM questions WHERE ref_type='raw_document' AND ref_id=? AND status='open'", (d["id"],))
        for q in d["questions"]:
            q["options"] = db.jl(q["options_json"])
    return docs


@app.post("/api/b/{bid}/upload")
async def upload(bid: int, file: UploadFile = File(...), note: str = Form(""), u=Depends(current_user)):
    role, biz = access(u, bid)
    content = await file.read()
    r = ingest.process_document(biz, "upload", u["name"], file.filename, content, note)
    return r


@app.get("/api/b/{bid}/documents/{did}")
def document(bid: int, did: int, u=Depends(current_user)):
    access(u, bid)
    d = db.one("SELECT * FROM raw_documents WHERE id=? AND business_id=?", (did, bid))
    if not d:
        raise HTTPException(404)
    p = Path(db._path).parent / "raw" / str(bid) / f"{d['file_hash'][:16]}_{re.sub(r'[^A-Za-z0-9._-]', '_', d['filename'])}"
    d["content"] = p.read_text(encoding="utf8", errors="replace")[:4000] if p.exists() else None
    d["extraction"] = db.jl(d["extraction_json"])
    return d


class Answer(BaseModel):
    answer: str


@app.get("/api/b/{bid}/questions")
def questions(bid: int, u=Depends(current_user)):
    access(u, bid)
    qs = db.q("SELECT * FROM questions WHERE business_id=? AND status='open' ORDER BY id", (bid,))
    for q in qs:
        q["options"] = db.jl(q["options_json"])
    return qs


@app.post("/api/b/{bid}/questions/{qid}/answer")
def answer(bid: int, qid: int, b: Answer, u=Depends(current_user)):
    access(u, bid)
    q = db.one("SELECT * FROM questions WHERE id=? AND business_id=?", (qid, bid))
    if not q:
        raise HTTPException(404)
    try:
        if q["ref_type"] == "eway_bill":
            role, biz = access(u, bid)
            db.update("questions", qid, status="answered", answer=b.answer)
            return eway.set_vehicle(biz, q["ref_id"], b.answer)
        return ingest.answer_question(qid, b.answer, u["id"])
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/b/{bid}/bank-statement")
async def bank(bid: int, file: UploadFile = File(...), u=Depends(current_user)):
    role, biz = access(u, bid)
    return ingest.process_document(biz, "upload", u["name"], file.filename, await file.read())


@app.post("/api/b/{bid}/gmail/sync")
def gmail_sync(bid: int, u=Depends(current_user)):
    role, biz = access(u, bid)
    return gmail.sync(biz)


# ---------------- approvals ----------------
@app.get("/api/b/{bid}/approvals")
def approvals(bid: int, u=Depends(current_user)):
    role, biz = access(u, bid)
    rows = db.q("SELECT * FROM approvals WHERE business_id=? ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, id DESC LIMIT 100", (bid,))
    for a in rows:
        a["payload"] = db.jl(a["payload_json"]); a["result"] = db.jl(a["result_json"])
    return rows


class Decide(BaseModel):
    decision: str
    comment: str = ""


@app.post("/api/approvals/{aid}/decide")
def decide(aid: int, b: Decide, u=Depends(current_user)):
    ap = db.one("SELECT * FROM approvals WHERE id=?", (aid,))
    if not ap:
        raise HTTPException(404)
    if ap["business_id"] == 0:  # global rule-change proposals: accountants only
        if not db.one("SELECT 1 x FROM memberships WHERE user_id=? AND role='accountant' AND revoked_at IS NULL", (u["id"],)):
            raise HTTPException(403, "Only accountants can approve rule changes")
        role = "accountant"
    else:
        role, _ = access(u, ap["business_id"], ("owner", "accountant"))
    if role == "owner" and ap["requested_from"] == "accountant":
        raise HTTPException(403, "This item is with your accountant")
    if b.decision not in ("approved", "rejected", "changes_requested"):
        raise HTTPException(400, "bad decision")
    try:
        res = gate.decide(aid, u, role, b.decision, b.comment)
    except (ValueError, PermissionError) as e:
        raise HTTPException(400, str(e))
    _close_review(u, ap)
    return res


def _close_review(u, ap):
    rs = db.one("SELECT * FROM review_sessions WHERE user_id=? AND item_type=? AND item_id=? AND minutes IS NULL ORDER BY id DESC", (u["id"], ap["item_type"], ap["item_id"]))
    if rs:
        mins = max(0.1, (datetime.fromisoformat(now_iso().replace("Z", "")) - datetime.fromisoformat(rs["opened_at"].replace("Z", ""))).total_seconds() / 60)
        db.update("review_sessions", rs["id"], minutes=round(mins, 2))


@app.post("/api/approvals/{aid}/route-accountant")
def route(aid: int, u=Depends(current_user)):
    ap = db.one("SELECT * FROM approvals WHERE id=?", (aid,))
    access(u, ap["business_id"], ("owner",))
    gate.route_to_accountant(aid, u["id"])
    return {"ok": True}


class Open(BaseModel):
    item_type: str
    item_id: int


@app.post("/api/b/{bid}/review/open")
def review_open(bid: int, b: Open, u=Depends(current_user)):
    access(u, bid, ("accountant",))
    db.insert("review_sessions", business_id=bid, user_id=u["id"], item_type=b.item_type, item_id=b.item_id, period=today().isoformat()[:7], opened_at=now_iso())
    return {"ok": True}


# ---------------- returns ----------------
@app.get("/api/b/{bid}/returns")
def list_returns(bid: int, u=Depends(current_user)):
    access(u, bid)
    rows = db.q("SELECT * FROM returns WHERE business_id=? ORDER BY period DESC, return_type", (bid,))
    for r in rows:
        c = db.jl(r["computed_json"], {})
        r["net_cash"] = c.get("net_cash"); r["due_date"] = c.get("due_date"); r["explanation"] = db.jl(r["explanation_json"], {})
        for k in ("computed_json", "proof_json"):
            r.pop(k)
        ap = db.one("SELECT id, status, requested_from FROM approvals WHERE item_type='return' AND item_id=? ORDER BY id DESC", (r["id"],))
        r["approval"] = ap
    return rows


class Prep(BaseModel):
    return_type: str
    period: str


@app.post("/api/b/{bid}/returns/prepare")
def prepare(bid: int, b: Prep, u=Depends(current_user)):
    role, biz = access(u, bid, ("owner", "accountant"))
    try:
        if b.return_type == "GSTR1":
            r = returns.draft_gstr1(biz, b.period)
        elif b.return_type in ("GSTR3B", "CMP08"):
            returns.draft_gstr1(biz, b.period)
            r = returns.draft_gstr3b(biz, b.period)
        elif b.return_type == "TDS":
            return {"return_id": tds.prepare_tds_return(biz, b.period)}
        else:
            raise HTTPException(400, "unknown return type")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"return_id": r["return_id"]}


@app.get("/api/returns/{rid}")
def get_return(rid: int, u=Depends(current_user)):
    r = returns.get_return(rid)
    if not r:
        raise HTTPException(404)
    access(u, r["business_id"])
    r["approval"] = db.one("SELECT * FROM approvals WHERE item_type='return' AND item_id=? ORDER BY id DESC", (rid,))
    return r


@app.get("/api/returns/{rid}/proof", response_class=HTMLResponse)
def proof_pack(rid: int, token: str = ""):
    s = db.one("SELECT * FROM sessions WHERE token=?", (token,))
    if not s:
        raise HTTPException(401, "Open the proof pack from the app (token required)")
    u = db.one("SELECT * FROM users WHERE id=?", (s["user_id"],))
    r = db.one("SELECT * FROM returns WHERE id=?", (rid,))
    access(u, r["business_id"])
    return proof.render(r)


@app.post("/api/returns/{rid}/file/otp")
def file_otp(rid: int, u=Depends(current_user)):
    r = db.one("SELECT * FROM returns WHERE id=?", (rid,))
    access(u, r["business_id"], ("owner", "accountant"))
    try:
        return executor.request_filing_otp(rid)
    except (PermissionError, RuntimeError) as e:
        raise HTTPException(400, str(e))


class FileReq(BaseModel):
    otp: str


@app.post("/api/returns/{rid}/file")
def file_return(rid: int, b: FileReq, u=Depends(current_user)):
    """The human filing action (simulated). Requires an approved return and the portal OTP."""
    r = db.one("SELECT * FROM returns WHERE id=?", (rid,))
    role, _ = access(u, r["business_id"], ("owner", "accountant"))
    try:
        return executor.file_return(rid, u["id"], b.otp)
    except (PermissionError, RuntimeError) as e:
        raise HTTPException(400, str(e))


# ---------------- ITC / suppliers ----------------
@app.get("/api/b/{bid}/recon")
def recon(bid: int, period: Optional[str] = None, refresh: bool = False, u=Depends(current_user)):
    role, biz = access(u, bid)
    period = period or orchestrator.default_period(biz)
    if refresh:
        return itc.reconcile_itc(biz, period)
    itc_ = itc.list_items(bid, period)
    if not itc_:
        return itc.reconcile_itc(biz, period)
    return {"period": period, "items": itc_, "itc_at_risk": sum(i["itc_at_risk"] for i in itc_), "counts": itc._counts(itc_)}


class ReconApply(BaseModel):
    period: str
    item_ids: Optional[list] = None


@app.post("/api/b/{bid}/recon/apply")
def recon_apply(bid: int, b: ReconApply, u=Depends(current_user)):
    """Human clicks 'approve recommended': creates the approval and decides it as the human."""
    from . import tools
    role, biz = access(u, bid, ("owner", "accountant"))
    m = {"accept": "accepted", "pending": "pending", "reject": "rejected"}
    acts = [{"item_id": r["id"], "action": m[r["recommended_action"]]} for r in itc.list_items(bid, b.period)
            if r["portal_2b_record_id"] and r["recommended_action"] in m and not r["decided_action"] and (not b.item_ids or r["id"] in b.item_ids)]
    if not acts:
        return {"applied": 0}
    res = tools.apply_ims_action(biz, b.period, acts)
    out = gate.decide(res["approval_id"], u, role, "approved", "approve recommended")
    return {"applied": len(acts), "result": out}


@app.post("/api/b/{bid}/recon/{item_id}/nudge")
def nudge(bid: int, item_id: int, send: bool = False, u=Depends(current_user)):
    from . import tools
    role, biz = access(u, bid, ("owner", "accountant"))
    owner = db.one("SELECT preferred_language l FROM users WHERE id=?", (u["id"],))
    res = tools.nudge_supplier(biz, item_id, owner["l"])
    if send and res.get("approval_id") and res["status"] == "pending_approval":
        res = {"status": "sent", "result": gate.decide(res["approval_id"], u, role, "approved", "owner approved nudge")}
    return res


@app.get("/api/b/{bid}/suppliers")
def suppliers(bid: int, u=Depends(current_user)):
    access(u, bid)
    return itc.supplier_report(bid)


# ---------------- e-way bills ----------------
@app.get("/api/b/{bid}/ewb")
def ewb_list(bid: int, u=Depends(current_user)):
    role, biz = access(u, bid)
    rows = db.q("SELECT e.*, i.invoice_no, i.total, p.name buyer FROM eway_bills e JOIN invoices i ON i.id=e.invoice_id LEFT JOIN parties p ON p.id=i.party_id WHERE e.business_id=? ORDER BY e.id DESC", (bid,))
    now = datetime.fromisoformat(now_iso().replace("Z", ""))
    for e in rows:
        e["part_a"] = db.jl(e["part_a_json"]); e["issues"] = db.jl(e["issues_json"], [])
        tp = db.one("SELECT name, phone FROM parties WHERE id=?", (e["transporter_party_id"],)) if e["transporter_party_id"] else None
        e["transporter"] = tp
        e["hours_left"] = round((datetime.fromisoformat(e["valid_until"]) - now).total_seconds() / 3600, 1) if e["valid_until"] else None
        e["approval"] = db.one("SELECT id, status FROM approvals WHERE item_type='ewb_generate' AND item_id=? ORDER BY id DESC", (e["id"],))
    pend = [p["invoice"]["invoice_no"] for p in eway.pending_dispatches(bid) if not p["ewb"]]
    return {"bills": rows, "unprepared_invoices": db.q("SELECT id, invoice_no, total FROM invoices WHERE business_id=? AND direction='sale' AND goods_movement=1 AND invoice_no IN (%s)" % ",".join("?" * len(pend)), [bid, *pend]) if pend else []}


class Ref(BaseModel):
    invoice_id: Optional[int] = None
    text: Optional[str] = None
    extra_km: Optional[int] = None


@app.post("/api/b/{bid}/ewb/prepare")
def ewb_prepare(bid: int, b: Ref, u=Depends(current_user)):
    role, biz = access(u, bid, ("owner", "accountant", "staff"))
    return eway.prepare_ewb(biz, b.invoice_id)


@app.post("/api/b/{bid}/ewb/{eid}/refresh")
def ewb_refresh(bid: int, eid: int, u=Depends(current_user)):
    role, biz = access(u, bid, ("owner", "accountant"))
    return {"issues": eway.refresh_part_a(biz, eid)}


@app.post("/api/b/{bid}/ewb/{eid}/vehicle")
def ewb_vehicle(bid: int, eid: int, b: Ref, u=Depends(current_user)):
    role, biz = access(u, bid, ("owner", "accountant", "staff"))
    return eway.set_vehicle(biz, eid, b.text or "")


@app.post("/api/b/{bid}/ewb/{eid}/generate")
def ewb_generate(bid: int, eid: int, approve: bool = False, u=Depends(current_user)):
    role, biz = access(u, bid, ("owner", "accountant"))
    res = eway.request_generate(biz, eid)
    if approve and res.get("status") == "pending_approval":
        return {"status": "generated", "result": gate.decide(res["approval_id"], u, role, "approved", "owner approved")}
    return res


@app.post("/api/b/{bid}/ewb/{eid}/extend")
def ewb_extend(bid: int, eid: int, b: Ref, approve: bool = False, u=Depends(current_user)):
    role, biz = access(u, bid, ("owner", "accountant"))
    res = eway.request_extension(biz, eid, b.extra_km)
    if approve:
        return gate.decide(res["approval_id"], u, role, "approved", "owner approved extension")
    return res


@app.get("/api/b/{bid}/ewb/{eid}/held")
def ewb_held(bid: int, eid: int, u=Depends(current_user)):
    role, biz = access(u, bid)
    audit(bid, "user", u["id"], "truck_held_pack", "eway_bill", eid)
    return eway.held_truck_pack(biz, eid)


# ---------------- calendar / vault / notices / tds / extras ----------------
@app.get("/api/b/{bid}/calendar")
def cal(bid: int, u=Depends(current_user)):
    access(u, bid)
    return calendar_.calendar(bid)


@app.get("/api/b/{bid}/vault")
def vault(bid: int, u=Depends(current_user)):
    access(u, bid)
    return calendar_.vault(bid)


@app.get("/api/b/{bid}/notices")
def notices_list(bid: int, u=Depends(current_user)):
    access(u, bid)
    rows = db.q("SELECT * FROM notices WHERE business_id=? ORDER BY id DESC", (bid,))
    for n in rows:
        n["explanation"] = db.jl(n["explanation_json"])
    return {"notices": rows, "risk": db.q("SELECT * FROM risk_findings WHERE business_id=? AND status='open' ORDER BY CASE level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END", (bid,))}


@app.post("/api/b/{bid}/risk/scan")
def risk_scan(bid: int, u=Depends(current_user)):
    role, biz = access(u, bid)
    return notices.risk_scan(biz, orchestrator.default_period(biz))


@app.get("/api/b/{bid}/tds")
def tds_view(bid: int, u=Depends(current_user)):
    role, biz = access(u, bid)
    return {"applicability": tds.applicability(biz), "deducted_by_us": tds.tds_by_us(bid),
            "deducted_from_us": db.q("SELECT t.*, p.name party FROM tds_entries t LEFT JOIN parties p ON p.id=t.party_id WHERE t.business_id=? AND t.direction='deducted_from_us'", (bid,))}


@app.post("/api/b/{bid}/tds/match-26as")
def tds_match(bid: int, u=Depends(current_user)):
    role, biz = access(u, bid)
    return tds.match_26as(biz)


@app.get("/api/b/{bid}/extras")
def extras(bid: int, u=Depends(current_user)):
    role, biz = access(u, bid)
    return {"payroll": calendar_.payroll(biz), "receivables": calendar_.overdue_receivables(biz), "presumptive": calendar_.presumptive_income(biz),
            "unmatched_bank": db.q("SELECT * FROM bank_transactions WHERE business_id=? AND matched_invoice_id IS NULL AND direction='out'", (bid,))}


@app.post("/api/b/{bid}/receivables/{inv_id}/chase")
def chase(bid: int, inv_id: int, u=Depends(current_user)):
    role, biz = access(u, bid, ("owner", "accountant"))
    return calendar_.chase_receivable(biz, inv_id)


@app.get("/api/b/{bid}/ledger")
def ledger(bid: int, u=Depends(current_user)):
    access(u, bid)
    return db.q("SELECT i.id, i.direction, i.invoice_no, i.invoice_date, i.taxable_value, i.cgst, i.sgst, i.igst, i.total, i.is_reverse_charge, i.goods_movement, p.name party FROM invoices i LEFT JOIN parties p ON p.id=i.party_id WHERE i.business_id=? ORDER BY i.invoice_date DESC, i.id DESC", (bid,))


@app.get("/api/b/{bid}/audit")
def audit_view(bid: int, u=Depends(current_user)):
    access(u, bid, ("owner", "accountant"))
    return db.q("SELECT * FROM audit_log WHERE business_id=? ORDER BY id DESC LIMIT 200", (bid,))


# ---------------- settings ----------------
@app.get("/api/b/{bid}/settings")
def settings(bid: int, u=Depends(current_user)):
    access(u, bid)
    return {"preapprovals": db.q("SELECT * FROM preapprovals WHERE business_id=?", (bid,)), "consents": db.q("SELECT * FROM consents WHERE business_id=?", (bid,)),
            "members": db.q("SELECT m.id, m.role, m.revoked_at, u.name, u.email FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.business_id=?", (bid,))}


class Pre(BaseModel):
    template_id: str
    active: bool
    max_value: Optional[int] = None


@app.put("/api/b/{bid}/preapprovals")
def set_pre(bid: int, b: Pre, u=Depends(current_user)):
    access(u, bid, ("owner",))
    ex = db.one("SELECT * FROM preapprovals WHERE business_id=? AND template_id=?", (bid, b.template_id))
    if ex:
        db.update("preapprovals", ex["id"], active=int(b.active), max_value=b.max_value)
    else:
        db.insert("preapprovals", business_id=bid, template_id=b.template_id, active=int(b.active), max_value=b.max_value)
    audit(bid, "user", u["id"], "preapproval_changed", "preapproval", None, None, b.dict())
    return {"ok": True}


class Consent(BaseModel):
    scope: str
    granted: bool


@app.put("/api/b/{bid}/consents")
def set_consent(bid: int, b: Consent, u=Depends(current_user)):
    access(u, bid, ("owner",))
    if b.granted:
        if not db.one("SELECT 1 x FROM consents WHERE business_id=? AND scope=? AND revoked_at IS NULL", (bid, b.scope)):
            db.insert("consents", business_id=bid, user_id=u["id"], scope=b.scope, granted_at=now_iso())
    else:
        db.ex("UPDATE consents SET revoked_at=? WHERE business_id=? AND scope=? AND revoked_at IS NULL", (now_iso(), bid, b.scope))
    audit(bid, "user", u["id"], "consent_changed", "consent", None, None, b.dict())
    return {"ok": True}


@app.post("/api/b/{bid}/members/{mid}/revoke")
def revoke(bid: int, mid: int, u=Depends(current_user)):
    access(u, bid, ("owner",))
    db.update("memberships", mid, revoked_at=now_iso())
    audit(bid, "user", u["id"], "membership_revoked", "membership", mid)
    return {"ok": True}


@app.get("/api/b/{bid}/impact")
def impact(bid: int, u=Depends(current_user)):
    access(u, bid)
    docs = db.one("SELECT COUNT(*) c FROM raw_documents WHERE business_id=? AND status='posted'", (bid,))["c"]
    rets = db.one("SELECT COUNT(*) c FROM returns WHERE business_id=?", (bid,))["c"]
    recon = db.one("SELECT COUNT(*) c, COALESCE(SUM(itc_at_risk),0) s FROM reconciliation_items WHERE business_id=?", (bid,))
    rec = sum(json.loads(a["after_json"])["amount"] for a in db.q("SELECT after_json FROM audit_log WHERE business_id=? AND action='itc_recovered'", (bid,)))
    ewb_blocked = db.one("SELECT COUNT(DISTINCT item_id) c FROM audit_log WHERE business_id=? AND action='ewb_validation_blocked'", (bid,))["c"]
    ewb_prep = db.one("SELECT COUNT(*) c FROM eway_bills WHERE business_id=?", (bid,))["c"]
    mins = docs * 4 + rets * 90 + recon["c"] * 6 + ewb_prep * 20
    done = db.one("SELECT COUNT(*) c FROM obligations WHERE business_id=? AND status='done'", (bid,))["c"]
    fee = rules.get_rule("gst.late_fee.per_day", today().isoformat())["regular_paise"]
    filing_fee = 200000
    return {"hours_saved_estimate": round(mins / 60, 1), "assumptions": "4 min/bill, 90 min/return, 6 min/recon line, 20 min/e-way bill (replace with field-interview numbers)",
            "itc_at_risk_found": recon["s"], "itc_recovered": rec, "ewb_errors_caught": ewb_blocked, "deadlines_met": done, "late_fee_avoided_estimate": done * fee,
            "documents_auto_posted": docs, "returns_prepared": rets, "filing_fee_baseline": filing_fee,
            "owner_baseline_hours_per_month": "15-20 (problem statement; replace with interview data)"}


# ---------------- accountant console ----------------
def acc_user(u=Depends(current_user)):
    if not db.one("SELECT 1 x FROM memberships WHERE user_id=? AND role='accountant' AND revoked_at IS NULL", (u["id"],)):
        raise HTTPException(403, "Accountant access only")
    return u


@app.get("/api/acc/clients")
def acc_clients(u=Depends(acc_user)):
    out = []
    for m in db.q("SELECT business_id FROM memberships WHERE user_id=? AND role='accountant' AND revoked_at IS NULL", (u["id"],)):
        biz = db.one("SELECT * FROM businesses WHERE id=?", (m["business_id"],))
        cal = calendar_.calendar(biz["id"])
        nxt = [o for o in cal if o["status"] != "done"][:1]
        overdue = [o for o in cal if o["status"] == "overdue"]
        period = orchestrator.default_period(biz)
        risk = db.q("SELECT level FROM risk_findings WHERE business_id=? AND status='open'", (biz["id"],))
        last = db.one("SELECT MAX(at) a FROM audit_log WHERE business_id=?", (biz["id"],))["a"]
        out.append({"business": biz, "next_due": nxt[0] if nxt else None, "traffic": "red" if overdue or any(r["level"] == "high" for r in risk) else ("amber" if nxt and nxt[0]["days_left"] <= 7 else "green"),
                    "itc_at_risk": sum(r["itc_at_risk"] for r in itc.list_items(biz["id"], period)), "notice_risk": {"high": sum(r["level"] == "high" for r in risk), "medium": sum(r["level"] == "medium" for r in risk)},
                    "pending_approvals": db.one("SELECT COUNT(*) c FROM approvals WHERE business_id=? AND status='pending' AND requested_from='accountant'", (biz["id"],))["c"], "last_activity": last, "period": period})
    out.sort(key=lambda c: c["next_due"]["due_date"] if c["next_due"] else "9999")
    return out


@app.get("/api/acc/queue")
def acc_queue(u=Depends(acc_user)):
    bids = [m["business_id"] for m in db.q("SELECT business_id FROM memberships WHERE user_id=? AND role='accountant' AND revoked_at IS NULL", (u["id"],))]
    rows = db.q("SELECT a.*, b.trade_name FROM approvals a LEFT JOIN businesses b ON b.id=a.business_id WHERE a.status='pending' AND a.requested_from='accountant' AND (a.business_id IN (%s) OR a.business_id=0)" % ",".join("?" * len(bids)), bids)
    for a in rows:
        a["payload"] = db.jl(a["payload_json"])
        if a["item_type"] == "return":
            r = db.one("SELECT return_type, period, computed_json FROM returns WHERE id=?", (a["item_id"],))
            c = db.jl(r["computed_json"], {})
            a["due_date"] = c.get("due_date"); a["return_type"] = r["return_type"]; a["period"] = r["period"]; a["net_cash"] = c.get("net_cash")
        a["trade_name"] = a["trade_name"] or "All clients"
    rows.sort(key=lambda a: a.get("due_date") or "9999")
    return rows


@app.get("/api/acc/calendar")
def acc_cal(u=Depends(acc_user)):
    out = []
    for m in db.q("SELECT business_id FROM memberships WHERE user_id=? AND role='accountant' AND revoked_at IS NULL", (u["id"],)):
        biz = db.one("SELECT trade_name FROM businesses WHERE id=?", (m["business_id"],))
        for o in calendar_.calendar(m["business_id"]):
            if o["status"] != "done" and o["days_left"] > -60:
                out.append({**o, "client": biz["trade_name"]})
    return sorted(out, key=lambda o: o["due_date"])


@app.get("/api/acc/rules")
def acc_rules(u=Depends(acc_user)):
    rows = db.q("SELECT * FROM rule_change_proposals ORDER BY id DESC")
    for r in rows:
        r["proposed"] = db.jl(r["proposed_values"]); r["evidence_list"] = db.jl(r["evidence"], []); r["impact"] = db.jl(r["impact_json"], [])
        r["approval"] = db.one("SELECT id, status FROM approvals WHERE item_type='rule_change' AND item_id=? ORDER BY id DESC", (r["id"],))
    return {"proposals": rows, "active_rules": db.q("SELECT id, rule_key, value_json, effective_from, effective_to, source_url, note FROM rule_versions ORDER BY rule_key, effective_from")}


@app.post("/api/acc/rules/scan")
def acc_scan(u=Depends(acc_user)):
    return {"created": tracker.scan()}


@app.get("/api/acc/capacity")
def acc_capacity(u=Depends(acc_user)):
    bids = [m["business_id"] for m in db.q("SELECT business_id FROM memberships WHERE user_id=? AND role='accountant' AND revoked_at IS NULL", (u["id"],))]
    rows = db.q("SELECT business_id, period, SUM(minutes) m, MIN(synthetic) syn FROM review_sessions WHERE minutes IS NOT NULL AND business_id IN (%s) GROUP BY business_id, period" % ",".join("?" * len(bids)), bids)
    avg_h = (sum(r["m"] for r in rows) / len(rows) / 60) if rows else None
    avail, base = 160, 6.0
    cap = int(avail / avg_h) if avg_h else None
    base_cap = int(avail / base)
    return {"avg_hours_per_client_month": round(avg_h, 2) if avg_h else None, "baseline_hours_per_client_month": base, "available_hours": avail,
            "capacity_clients_now": cap, "capacity_clients_before": base_cap, "additional_clients": (cap - base_cap) if cap else None, "current_clients": len(bids),
            "sample_months": len(rows), "synthetic_samples": sum(1 for r in rows if r["syn"]),
            "note": "Baseline 6h is an assumption: replace with accountant-interview data (section 23). Review time is logged from opening an item to approving it."}


# ---------------- WhatsApp (Twilio webhook + dev simulator) ----------------
def inbound_whatsapp(phone: str, body: str, media: Optional[bytes] = None, media_name: str = "whatsapp_media"):
    phone = norm_phone(phone)
    u = db.one("SELECT * FROM users WHERE phone=?", (phone,))
    if u:
        m = db.one("SELECT business_id FROM memberships WHERE user_id=? AND role IN ('owner','staff') AND revoked_at IS NULL ORDER BY id LIMIT 1", (u["id"],))
        biz = db.one("SELECT * FROM businesses WHERE id=?", (m["business_id"],))
        channels.log_inbound(biz["id"], phone, u["name"], body or "[media]")
        if media or ingest.classify_text(body or "") != "invoice" or re.search(r"invoice no|bill no", (body or "").lower()):
            r = ingest.process_document(biz, "whatsapp", u["name"], media_name if media else "whatsapp_text.txt", media or (body or "").encode("utf8"), body if media else "")
            reply = r["message"]
        else:
            res = orchestrator.handle(biz, u, body, "whatsapp")
            reply = res["text"] + "".join(f"\n[{c['title']}: " + "; ".join(f"{k} {v}" for k, v in c["rows"][:4]) + "]" for c in res["cards"] if c["rows"])
            if any(a.get("nav") for c in res["cards"] for a in c["actions"]):
                reply += "\nOpen the app for details/approvals."
        db.insert("messages", business_id=biz["id"], channel="whatsapp", direction="out", counterparty=phone, counterparty_name=u["name"], template_id="reply", body=reply, status="sent_simulated", created_at=now_iso())
        return reply
    party = db.one("SELECT * FROM parties WHERE phone=? ORDER BY id DESC", (phone,))
    if not party:
        return "Sorry, this number is not registered with Ganaka."
    biz = db.one("SELECT * FROM businesses WHERE id=?", (party["business_id"],))
    channels.log_inbound(biz["id"], phone, party["name"], body)
    if party["type"] == "transporter":
        reply = eway.handle_transporter_reply(biz, party, body)
    elif party["type"] == "supplier":
        n = 0
        for it in itc.list_items(biz["id"]):
            if it["party_id"] == party["id"] and it["match_status"] != "matched":
                db.update("reconciliation_items", it["id"], supplier_reply=body); n += 1
        reply = "Thank you. We will re-check after the next GSTR-2B refresh." if n else "Thank you."
        audit(biz["id"], "system", "inbound", "supplier_reply", "party", party["id"], None, {"text": body[:100]})
    else:
        reply = "Thank you. We have noted your reply."
        audit(biz["id"], "system", "inbound", "party_reply", "party", party["id"], None, {"text": body[:100]})
    db.insert("messages", business_id=biz["id"], channel="whatsapp", direction="out", counterparty=phone, counterparty_name=party["name"], template_id="reply", body=reply, status="sent_simulated", created_at=now_iso())
    return reply


@app.post("/api/whatsapp/webhook")
async def wa_webhook(request: Request):
    form = await request.form()
    media = None
    if int(form.get("NumMedia", 0) or 0) > 0 and form.get("MediaUrl0"):
        import httpx
        sid, tok = os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN")
        try:
            media = httpx.get(form["MediaUrl0"], auth=(sid, tok) if sid else None, timeout=20, follow_redirects=True).content
        except Exception:
            media = None
    reply = inbound_whatsapp(str(form.get("From", "")).replace("whatsapp:", ""), str(form.get("Body", "")), media)
    return Response(f"<?xml version='1.0'?><Response><Message>{reply}</Message></Response>", media_type="application/xml")


class DevReply(BaseModel):
    phone: str
    text: str


@app.post("/api/dev/whatsapp")
def dev_whatsapp(b: DevReply):
    return {"reply": inbound_whatsapp(b.phone, b.text)}


@app.post("/api/dev/whatsapp-file")
async def dev_whatsapp_file(phone: str = Form(...), body: str = Form(""), file: UploadFile = File(...)):
    return {"reply": inbound_whatsapp(phone, body, await file.read(), file.filename)}


@app.get("/api/dev/messages")
def dev_messages(limit: int = 80):
    return db.q("SELECT m.*, b.trade_name biz FROM messages m LEFT JOIN businesses b ON b.id=m.business_id ORDER BY m.id DESC LIMIT ?", (limit,))


@app.get("/api/dev/contacts")
def dev_contacts():
    ps = db.q("SELECT p.name, p.phone, p.type, b.trade_name biz FROM parties p JOIN businesses b ON b.id=p.business_id WHERE p.phone IS NOT NULL AND p.type IN ('supplier','transporter') ORDER BY p.type, p.name")
    us = db.q("SELECT u.name, u.phone, 'owner/staff' type, '' biz FROM users u WHERE u.phone IS NOT NULL")
    return ps + us


class SupplierFile(BaseModel):
    supplier_gstin: str


@app.post("/api/dev/supplier-files")
def dev_supplier_files(b: SupplierFile):
    r = portal.admin_supplier_files(portal.SupplierFile(supplier_gstin=b.supplier_gstin))
    return r


@app.get("/api/dev/suppliers")
def dev_suppliers():
    return db.q("SELECT DISTINCT p.name, p.gstin FROM parties p WHERE p.type='supplier' AND p.gstin IS NOT NULL")


@app.post("/api/dev/publish-advisory")
def dev_publish():
    portal.c().execute("UPDATE advisories SET published=1")
    return {"ok": True}


@app.post("/api/dev/reseed")
def dev_reseed():
    seed.reset()
    seed.run(force=True)
    return {"ok": True}


@app.post("/api/jobs/run")
def run_jobs(u=Depends(current_user)):
    return jobs.run_all()


@app.post("/api/dev/run-jobs")
def dev_run_jobs():
    return jobs.run_all()


@app.get("/api/dev/demo-files")
def demo_files():
    out = {}
    for sub in ("bills", "mailbox", "."):
        for p in sorted((seed.DEMO_DIR / sub).glob("*")):
            if p.is_file():
                out[f"{sub}/{p.name}" if sub != "." else p.name] = p.read_text(encoding="utf8")
    return out


# ---------------- pages ----------------
@app.get("/", response_class=HTMLResponse)
def owner_page():
    return (STATIC / "owner.html").read_text(encoding="utf8")


@app.get("/accountant", response_class=HTMLResponse)
def acc_page():
    return (STATIC / "accountant.html").read_text(encoding="utf8")


@app.get("/sim", response_class=HTMLResponse)
def sim_page():
    return (STATIC / "sim.html").read_text(encoding="utf8")
