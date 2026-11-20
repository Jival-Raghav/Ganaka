"""Mock GST / IMS / e-way bill portal. SIMULATION. Own database. Filing endpoints require the worker key
that only the approval executor holds (the agent modules never import this client)."""
import json, os, random, sqlite3, threading
from pathlib import Path
from datetime import date, timedelta
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

WORKER_KEY = os.environ.get("PORTAL_WORKER_KEY", "munshi-worker-key")
_path = os.environ.get("MUNSHI_PORTAL_DB", str(Path(__file__).resolve().parent.parent / "data" / "portal.db"))
_local = threading.local()
BANNER = "SIMULATION - not connected to the real GST / e-way bill portal"


def configure(path):
    global _path
    _path = path
    _local.c = None


def c():
    cn = getattr(_local, "c", None)
    if cn is None or getattr(_local, "p", None) != _path:
        Path(_path).parent.mkdir(parents=True, exist_ok=True)
        cn = sqlite3.connect(_path, isolation_level=None, check_same_thread=False, timeout=30)
        cn.row_factory = sqlite3.Row
        _local.c, _local.p = cn, _path
        cn.executescript("""
        CREATE TABLE IF NOT EXISTS taxpayers(gstin TEXT PRIMARY KEY,name TEXT,state TEXT,status TEXT,pan TEXT);
        CREATE TABLE IF NOT EXISTS ims(id INTEGER PRIMARY KEY,buyer_gstin TEXT,period TEXT,supplier_gstin TEXT,supplier_name TEXT,invoice_no TEXT,invoice_date TEXT,taxable INT,cgst INT,sgst INT,igst INT,ims_status TEXT DEFAULT 'no_action',visible INT DEFAULT 1);
        CREATE TABLE IF NOT EXISTS filed(id INTEGER PRIMARY KEY,gstin TEXT,type TEXT,period TEXT,json TEXT,ack TEXT,filed_at TEXT);
        CREATE TABLE IF NOT EXISTS otps(k TEXT PRIMARY KEY,otp TEXT);
        CREATE TABLE IF NOT EXISTS ewbs(number TEXT PRIMARY KEY,gstin TEXT,json TEXT,vehicle TEXT,valid_from TEXT,valid_until TEXT,extensions INT DEFAULT 0);
        CREATE TABLE IF NOT EXISTS tds26as(id INTEGER PRIMARY KEY,pan TEXT,fy TEXT,deductor TEXT,deductor_tan TEXT,amount INT,tds INT,date TEXT);
        CREATE TABLE IF NOT EXISTS advisories(id INTEGER PRIMARY KEY,source TEXT,title TEXT,url TEXT,date TEXT,body TEXT,published INT DEFAULT 1);
        """)
    return cn


def rows(sql, a=()):
    return [dict(r) for r in c().execute(sql, a).fetchall()]


def row(sql, a=()):
    r = c().execute(sql, a).fetchone()
    return dict(r) if r else None


def reset():
    cn = c()
    for t in ("taxpayers", "ims", "filed", "otps", "ewbs", "tds26as", "advisories"):
        cn.execute(f"DELETE FROM {t}")


app = FastAPI(title="Mock GST Portal (SIMULATION)")


def need_worker(k):
    if k != WORKER_KEY:
        raise HTTPException(403, "Filing endpoints are reachable only from the approval executor")


@app.get("/")
def root():
    return {"banner": BANNER}


@app.get("/taxpayer/{gstin}")
def taxpayer(gstin: str):
    r = row("SELECT * FROM taxpayers WHERE gstin=?", (gstin,))
    if not r:
        raise HTTPException(404, "GSTIN not found")
    return {**r, "banner": BANNER}


@app.get("/ims/{gstin}/{period}")
def ims(gstin: str, period: str):
    return {"banner": BANNER, "records": rows("SELECT * FROM ims WHERE buyer_gstin=? AND period=? AND visible=1", (gstin, period))}


class ImsAction(BaseModel):
    actions: list  # [{id, action}]


@app.post("/ims/{gstin}/{period}/actions")
def ims_actions(gstin: str, period: str, body: ImsAction, x_worker_key: str = Header(None)):
    need_worker(x_worker_key)
    n = 0
    for a in body.actions:
        if a["action"] not in ("accepted", "rejected", "pending", "no_action"):
            raise HTTPException(400, "bad action")
        c().execute("UPDATE ims SET ims_status=? WHERE id=? AND buyer_gstin=?", (a["action"], a["id"], gstin)); n += 1
    return {"updated": n, "banner": BANNER}


@app.get("/gstr2b/{gstin}/{period}")
def gstr2b(gstin: str, period: str):
    recs = rows("SELECT * FROM ims WHERE buyer_gstin=? AND period=? AND visible=1 AND ims_status IN ('no_action','accepted')", (gstin, period))
    return {"banner": BANNER, "period": period, "records": recs,
            "totals": {k: sum(r[k] for r in recs) for k in ("taxable", "cgst", "sgst", "igst")}}


@app.post("/returns/{rtype}/{gstin}/{period}/otp")
def otp(rtype: str, gstin: str, period: str, x_worker_key: str = Header(None)):
    need_worker(x_worker_key)
    code = "123456"  # demo OTP, shown on screen
    c().execute("INSERT OR REPLACE INTO otps VALUES(?,?)", (f"{rtype}|{gstin}|{period}", code))
    return {"otp_sent": True, "demo_otp": code, "banner": BANNER}


class FileBody(BaseModel):
    otp: str
    payload: dict
    on_date: str


@app.post("/returns/{rtype}/{gstin}/{period}/file")
def file_return(rtype: str, gstin: str, period: str, body: FileBody, x_worker_key: str = Header(None)):
    need_worker(x_worker_key)
    o = row("SELECT otp FROM otps WHERE k=?", (f"{rtype}|{gstin}|{period}",))
    if not o or o["otp"] != body.otp:
        raise HTTPException(401, "Invalid OTP")
    if not row("SELECT 1 x FROM taxpayers WHERE gstin=? AND status='active'", (gstin,)):
        raise HTTPException(400, "Taxpayer not active")
    if row("SELECT 1 x FROM filed WHERE gstin=? AND type=? AND period=?", (gstin, rtype, period)):
        raise HTTPException(409, "Already filed")
    p = body.payload
    if rtype == "GSTR3B":
        g1 = row("SELECT json FROM filed WHERE gstin=? AND type='GSTR1' AND period=?", (gstin, period))
        if not g1:
            raise HTTPException(400, "GSTR-3B outward liability is auto-populated from GSTR-1: file GSTR-1 first")
        g1t = json.loads(g1["json"]).get("totals", {})
        if g1t and (g1t.get("tax") != p.get("outward", {}).get("tax")):
            raise HTTPException(400, "GSTR-3B outward liability must equal GSTR-1 (locked); use GSTR-1A to amend")
    if "totals" not in p and rtype in ("GSTR1",):
        raise HTTPException(400, "Schema error: missing totals")
    ack = f"AA{gstin[:2]}{period.replace('-', '')}{random.randint(10**7, 10**8 - 1)}"
    c().execute("INSERT INTO filed(gstin,type,period,json,ack,filed_at) VALUES(?,?,?,?,?,?)",
                (gstin, rtype, period, json.dumps(p), ack, body.on_date))
    return {"ack_number": ack, "filed_at": body.on_date, "banner": BANNER}


@app.get("/returns/{gstin}")
def filed_returns(gstin: str):
    return rows("SELECT type,period,ack,filed_at FROM filed WHERE gstin=?", (gstin,))


@app.get("/returns/{rtype}/{gstin}/{period}")
def filed_one(rtype: str, gstin: str, period: str):
    r = row("SELECT * FROM filed WHERE gstin=? AND type=? AND period=?", (gstin, rtype, period))
    return r or {}


class EwbGen(BaseModel):
    part_a: dict
    part_b: dict
    valid_until: str
    on_date: str


@app.post("/ewb/generate")
def ewb_generate(body: EwbGen, x_worker_key: str = Header(None)):
    need_worker(x_worker_key)
    a, b = body.part_a, body.part_b
    for k in ("supplier_gstin", "doc_no", "doc_date", "value", "hsn", "from_pin", "to_pin"):
        if not a.get(k):
            raise HTTPException(400, f"Part A missing {k}")
    if not b.get("vehicle_no"):
        raise HTTPException(400, "Part B missing vehicle_no")
    digits = 14 if body.on_date >= "2027-01-01" else 12
    number = "".join(str(random.randint(0, 9)) for _ in range(digits))
    c().execute("INSERT INTO ewbs VALUES(?,?,?,?,?,?,0)", (number, a["supplier_gstin"], json.dumps({"a": a, "b": b}), b["vehicle_no"], body.on_date, body.valid_until))
    return {"ewb_number": number, "valid_until": body.valid_until, "banner": BANNER}


class PartB(BaseModel):
    vehicle_no: str


@app.post("/ewb/{number}/partb")
def ewb_partb(number: str, body: PartB, x_worker_key: str = Header(None)):
    need_worker(x_worker_key)
    if not row("SELECT 1 x FROM ewbs WHERE number=?", (number,)):
        raise HTTPException(404, "unknown ewb")
    c().execute("UPDATE ewbs SET vehicle=? WHERE number=?", (body.vehicle_no, number))
    return {"ok": True, "banner": BANNER}


class Extend(BaseModel):
    new_valid_until: str


@app.post("/ewb/{number}/extend")
def ewb_extend(number: str, body: Extend, x_worker_key: str = Header(None)):
    need_worker(x_worker_key)
    c().execute("UPDATE ewbs SET valid_until=?, extensions=extensions+1 WHERE number=?", (body.new_valid_until, number))
    return {"ok": True, "valid_until": body.new_valid_until, "banner": BANNER}


@app.get("/26as/{pan}/{fy}")
def as26(pan: str, fy: str):
    return {"banner": BANNER, "entries": rows("SELECT * FROM tds26as WHERE pan=? AND fy=?", (pan, fy))}


@app.get("/advisories")
def advisories():
    return {"banner": BANNER, "items": rows("SELECT * FROM advisories WHERE published=1 ORDER BY date DESC")}


class SupplierFile(BaseModel):
    supplier_gstin: str
    period: str | None = None


@app.post("/admin/supplier-files")
def admin_supplier_files(body: SupplierFile):
    """Demo control: make a supplier file their GSTR-1 now -> their invoices appear in buyers' IMS / 2B."""
    q = "UPDATE ims SET visible=1 WHERE supplier_gstin=? AND visible=0"
    a = [body.supplier_gstin]
    if body.period:
        q += " AND period=?"; a.append(body.period)
    cur = c().execute(q, a)
    return {"made_visible": cur.rowcount, "banner": BANNER}


@app.post("/admin/publish-advisory/{aid}")
def admin_publish(aid: int):
    c().execute("UPDATE advisories SET published=1 WHERE id=?", (aid,))
    return {"ok": True}
