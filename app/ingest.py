"""Intake pipeline: raw inbox -> extract -> validate (code) -> classify -> dedup -> clarification loop -> ledger.
Extraction is a deterministic stub that reads the text template used by the demo bills (see demo/bills). A vision LLM
can replace `extract_text` behind the same dict schema; validation is always code."""
import csv, io, json, re
from datetime import date, datetime
from decimal import Decimal
from . import db, calc, rules
from .util import (now_iso, today, sha, audit, fy_of, period_of, fmt, rupees, normalize_invoice_no, norm_phone)
from .i18n import t

CONF_THRESHOLD = 0.85
TEMPLATE = """Seller: <name>
Seller GSTIN: <15-char GSTIN>
Buyer: <name>
Buyer GSTIN: <GSTIN or blank>
Invoice No: <no>
Date: <YYYY-MM-DD>
Place of Supply: <state code e.g. 29>
Item: <description> | <HSN> | <qty> | <unit price> | <GST %>
Goods Movement: yes/no
Paid: yes/no
"""


# ---------------- extraction (stub) ----------------
def parse_date(s):
    s = (s or "").strip()
    for fmt_ in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d %b %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt_).date().isoformat()
        except ValueError:
            pass
    return None


def _amount_or_candidates(tok: str):
    """'12,400' -> (paise, None) ; '12400 or 1240' -> (None, [paise, paise])"""
    parts = [p for p in re.split(r"\s+or\s+|/", tok) if p.strip()]
    vals = []
    for p in parts:
        d = calc.clean_amount_str(p)
        if d is not None:
            vals.append(rupees(d))
    if len(vals) == 1:
        return vals[0], None
    if len(vals) > 1:
        return None, vals
    return None, None


def classify_text(text: str, filename: str = "") -> str:
    low = text.lower()
    if re.search(r"^\s*date\s*,\s*narration", low, re.M) or ("narration" in low and "," in low.split("\n")[0]):
        return "bank_statement"
    if "show cause" in low or "gst notice" in low or "notice no" in low or "drc-0" in low or "asmt-10" in low:
        return "gst_notice"
    if re.search(r"licen[cs]e|fssai|udyam certificate|insurance policy", low) and "expiry" in low:
        return "licence"
    if "form 26as" in low or "tds certificate" in low:
        return "tds_certificate"
    if "payment received" in low and "invoice no" not in low:
        return "payment_receipt"
    return "invoice"


def extract_text(text: str) -> dict:
    ex = {"doc_type": "invoice", "fields": {}, "items": [], "total": None, "conf": {}, "candidates": {}}
    f, conf = ex["fields"], ex["conf"]
    for raw in text.splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, val = [x.strip() for x in line.split(":", 1)]
        k = key.lower()
        unsure = bool(re.search(r"\(\?\)|\[blurry\]|\[unclear\]", val, re.I))
        val = re.sub(r"\(\?\)|\[blurry\]|\[unclear\]", "", val, flags=re.I).strip()
        c = 0.6 if unsure else 0.97
        mapping = {"seller": "seller", "seller gstin": "seller_gstin", "buyer": "buyer", "buyer gstin": "buyer_gstin",
                   "invoice no": "invoice_no", "invoice number": "invoice_no", "bill no": "invoice_no",
                   "place of supply": "pos", "transporter": "transporter", "vehicle": "vehicle",
                   "dispatch pin": "from_pin", "delivery pin": "to_pin", "seller phone": "seller_phone",
                   "buyer phone": "buyer_phone", "buyer pin": "to_pin", "description": "description"}
        if k in mapping:
            f[mapping[k]] = val.upper() if "gstin" in k else val
            conf[mapping[k]] = c
        elif k == "date" or k == "invoice date":
            d = parse_date(val)
            f["date"] = d; conf["date"] = c if d else 0.0
        elif k in ("reverse charge", "goods movement", "paid"):
            f[k.replace(" ", "_")] = val.lower() in ("yes", "y", "true", "1")
        elif k in ("doc type", "document type"):
            f["doc_kind"] = {"credit note": "credit_note", "debit note": "debit_note"}.get(val.lower(), "invoice")
        elif k == "tds":
            v, _c = _amount_or_candidates(val)
            f["tds"] = v
        elif k == "pay mode":
            f["pay_mode"] = val.lower()
        elif k == "total":
            v, cands = _amount_or_candidates(val)
            ex["total"] = v
            conf["total"] = 0.5 if (unsure or cands) else 0.97
            if cands:
                ex["candidates"]["total"] = cands
        elif k == "item":
            parts = [p.strip() for p in val.split("|")]
            if len(parts) < 5:
                continue
            it = {"desc": parts[0], "hsn": re.sub(r"\D", "", parts[1]), "qty": float(parts[2] or 1)}
            v, cands = _amount_or_candidates(parts[3])
            idx = len(ex["items"])
            it["unit_price"] = v
            it["gst_rate"] = float(re.sub(r"[^\d.]", "", parts[4]) or 0)
            if cands:
                ex["candidates"][f"items.{idx}.unit_price"] = cands
                conf[f"items.{idx}.unit_price"] = 0.5
            elif unsure:
                conf[f"items.{idx}.unit_price"] = 0.6
            ex["items"].append(it)
    f.setdefault("doc_kind", "invoice")
    return ex


def amounts_of(ex, biz, direction):
    """Compute taxable/tax per line (code, not LLM). Returns (lines, totals) or None if amounts missing."""
    f = ex["fields"]
    seller_state = (f.get("seller_gstin") or "")[:2] or biz["state_code"]
    pos = f.get("pos") or (f.get("buyer_gstin") or "")[:2] or seller_state
    pos = re.sub(r"\D", "", pos)[:2] or seller_state
    intra = seller_state == pos
    lines, tot = [], {"taxable": 0, "cgst": 0, "sgst": 0, "igst": 0}
    for it in ex["items"]:
        if it.get("unit_price") is None:
            return None
        taxable = calc.r_half_up(Decimal(str(it["qty"])) * Decimal(it["unit_price"]))
        tx = calc.line_tax(taxable, it["gst_rate"], intra)
        lines.append({**it, "taxable": taxable, **tx})
        tot["taxable"] += taxable
        for k in ("cgst", "sgst", "igst"):
            tot[k] += tx[k]
    tot["total"] = tot["taxable"] + tot["cgst"] + tot["sgst"] + tot["igst"]
    tot["pos"] = pos
    return lines, tot


def direction_of(ex, biz):
    f = ex["fields"]
    if f.get("seller_gstin") == biz["gstin"]:
        return "sale"
    if f.get("buyer_gstin") == biz["gstin"]:
        return "purchase"
    if f.get("direction"):
        return f["direction"]
    return None


# ---------------- validation (code) ----------------
def validate(ex, biz):
    """Returns list of issues: {field, kind: 'low_conf'|'invalid'|'missing'|'candidates'|'direction'|'total_mismatch'|'warning', msg, options?}"""
    f, conf, issues = ex["fields"], ex["conf"], []
    for fld, cand in ex["candidates"].items():
        if fld == "total" or fld.startswith("items."):
            if ex.get("resolved", {}).get(fld) is None:
                issues.append({"field": fld, "kind": "candidates", "options": cand,
                               "msg": t("q_amount", "en", field="amount", options=" or ".join(fmt(x) for x in cand))})
    for fld in ("invoice_no", "date"):
        if not f.get(fld):
            issues.append({"field": fld, "kind": "missing", "msg": f"I could not find the {fld.replace('_', ' ')} on this bill."})
    if not ex["items"]:
        issues.append({"field": "items", "kind": "missing", "msg": "I could not find any line items on this bill."})
    for fld, c in conf.items():
        if c < CONF_THRESHOLD and fld not in ex["candidates"] and fld.split(".")[0] != "total" and fld not in ex.get("resolved", {}) \
                and fld not in ex.get("confirmed", []):
            issues.append({"field": fld, "kind": "low_conf", "msg": f"I'm not sure about '{fld}' ({(f.get(fld) or '?')}). Is that correct?"})
    for g in ("seller_gstin", "buyer_gstin"):
        if f.get(g) and not calc.gstin_valid(f[g]):
            issues.append({"field": g, "kind": "invalid", "msg": f"GSTIN {f[g]} fails the format/checksum check. Please send the correct GSTIN."})
    d = direction_of(ex, biz)
    if d is None and not any(i["kind"] == "invalid" for i in issues):
        issues.append({"field": "direction", "kind": "direction", "options": ["sale", "purchase"],
                       "msg": "Neither GSTIN matches your business. Is this a sale or a purchase?"})
    if f.get("date") and f["date"] > today().isoformat():
        issues.append({"field": "date", "kind": "invalid", "msg": f"Bill date {f['date']} is in the future. Please send the correct date."})
    for i, it in enumerate(ex["items"]):
        if it["hsn"] and len(it["hsn"]) not in (4, 6, 8):
            issues.append({"field": f"items.{i}.hsn", "kind": "invalid", "msg": f"HSN '{it['hsn']}' should be 4, 6 or 8 digits."})
    if not any(i["kind"] in ("candidates", "missing") and i["field"].startswith("items") for i in issues) and ex["items"] and not issues_blocking_amounts(issues):
        res = amounts_of(ex, biz, d)
        if res:
            lines, tot = res
            allowed = rules.get_rule("gst.rate.allowed", today().isoformat())
            hsn_map = rules.get_rule("gst.rate.hsn", today().isoformat())
            for i, ln in enumerate(lines):
                if ln["gst_rate"] not in allowed:
                    issues.append({"field": f"items.{i}.gst_rate", "kind": "invalid", "msg": f"GST rate {ln['gst_rate']}% is not a valid slab."})
                elif ln["hsn"] in hsn_map and hsn_map[ln["hsn"]] != ln["gst_rate"]:
                    ex.setdefault("warnings", []).append(f"HSN {ln['hsn']} usually attracts {hsn_map[ln['hsn']]}% but bill shows {ln['gst_rate']}%.")
            bill_total = ex.get("total_resolved", ex["total"])
            if bill_total is not None and abs(bill_total - tot["total"]) > 100 and not ex.get("ignore_bill_total"):
                issues.append({"field": "total", "kind": "total_mismatch", "options": ["use_calculated", "manual"],
                               "msg": f"The bill total {fmt(bill_total)} does not match the items ({fmt(tot['total'])}). Use the calculated total?"})
    return issues


def issues_blocking_amounts(issues):
    return any(i["kind"] == "candidates" for i in issues)


# ---------------- ledger writes ----------------
def upsert_party(biz_id, name, gstin, ptype, phone=None):
    p = None
    if gstin:
        p = db.one("SELECT * FROM parties WHERE business_id=? AND gstin=?", (biz_id, gstin))
    if not p and name:
        p = db.one("SELECT * FROM parties WHERE business_id=? AND lower(name)=lower(?) AND type=?", (biz_id, name, ptype))
    if p:
        if phone and not p["phone"]:
            db.update("parties", p["id"], phone=norm_phone(phone))
        return p["id"]
    return db.insert("parties", business_id=biz_id, name=name or "Unknown", gstin=gstin or None,
                     state_code=(gstin or "")[:2] or None, phone=norm_phone(phone) if phone else None, type=ptype, reliability_score=None)


class Duplicate(Exception):
    def __init__(self, inv_id):
        self.inv_id = inv_id


def post_invoice(biz, ex, doc_id=None, allow_near=False):
    f = ex["fields"]
    d = direction_of(ex, biz)
    if d == "sale":
        party = upsert_party(biz["id"], f.get("buyer"), f.get("buyer_gstin"), "customer", f.get("buyer_phone"))
    else:
        party = upsert_party(biz["id"], f.get("seller"), f.get("seller_gstin"), "supplier", f.get("seller_phone"))
    lines, tot = amounts_of(ex, biz, d)
    fy = fy_of(f["date"])
    kind = f.get("doc_kind", "invoice")
    n_no = normalize_invoice_no(f["invoice_no"])
    for r in db.q("SELECT id, invoice_no FROM invoices WHERE business_id=? AND direction=? AND party_id=? AND fy=? AND doc_type=?", (biz["id"], d, party, fy, kind)):
        if normalize_invoice_no(r["invoice_no"]) == n_no:
            raise Duplicate(r["id"])
    if not allow_near:
        for r in db.q("SELECT id, invoice_no, invoice_date, total FROM invoices WHERE business_id=? AND direction=? AND party_id=? AND doc_type=?", (biz["id"], d, party, kind)):
            if r["total"] == tot["total"] and abs((date.fromisoformat(r["invoice_date"]) - date.fromisoformat(f["date"])).days) <= 3:
                raise Duplicate(("near", r["id"]))
    rcm = 1 if f.get("reverse_charge") else 0
    rcm_kw = rules.get_rule("gst.reverse_charge.categories", f["date"])["keywords"]
    if d == "purchase" and not f.get("seller_gstin") and any(k in " ".join(i["desc"].lower() for i in ex["items"]) for k in rcm_kw):
        rcm = 1
    goods = 1 if f.get("goods_movement") else 0
    inv_id = db.insert("invoices", business_id=biz["id"], direction=d, party_id=party, invoice_no=f["invoice_no"],
                       invoice_date=f["date"], period=period_of(f["date"]), fy=fy, place_of_supply=tot["pos"],
                       is_reverse_charge=rcm, goods_movement=goods, taxable_value=tot["taxable"], cgst=tot["cgst"],
                       sgst=tot["sgst"], igst=tot["igst"], total=tot["total"], doc_type=kind, source_document_id=doc_id,
                       status="posted", meta_json=json.dumps({"transporter": f.get("transporter"), "vehicle": f.get("vehicle"),
                                                              "from_pin": f.get("from_pin"), "to_pin": f.get("to_pin")}))
    for ln in lines:
        db.insert("line_items", invoice_id=inv_id, description=ln["desc"], hsn_sac=ln["hsn"], qty=ln["qty"], unit="nos",
                  rate=ln["unit_price"], taxable_value=ln["taxable"], gst_rate=ln["gst_rate"], cgst=ln["cgst"], sgst=ln["sgst"], igst=ln["igst"])
    if f.get("paid"):
        db.insert("payments", business_id=biz["id"], invoice_id=inv_id, amount=tot["total"], date=f["date"], mode=f.get("pay_mode", "bank"))
    if f.get("tds") and d == "sale":
        db.insert("tds_entries", business_id=biz["id"], direction="deducted_from_us", party_id=party, invoice_id=inv_id, section=f.get("tds_section", "194J"),
                  amount=tot["taxable"], tds_amount=f["tds"], date=f["date"])
    audit(biz["id"], "system", "ingest", "invoice_posted", "invoice", inv_id, None, {"no": f["invoice_no"], "total": tot["total"], "direction": d})
    from . import triggers
    triggers.fire("invoice_posted", biz["id"], inv_id)
    return inv_id


# ---------------- pipeline ----------------
def ask(biz_id, kind, ref_id, field, question, options=None):
    return db.insert("questions", business_id=biz_id, kind=kind, ref_type="raw_document", ref_id=ref_id, field=field,
                     question=question, options_json=json.dumps(options) if options is not None else None,
                     status="open", created_at=now_iso())


def process_document(biz, channel, sender, filename, content: bytes, typed_text: str = "", lang="en"):
    h = sha(content)
    existing = db.one("SELECT * FROM raw_documents WHERE business_id=? AND file_hash=?", (biz["id"], h))
    if existing:
        audit(biz["id"], "system", "ingest", "duplicate_file_linked", "raw_document", existing["id"])
        return {"status": "duplicate", "document_id": existing["id"], "message": "Exact duplicate file; linked to the existing record, not double-counted."}
    doc_id = db.insert("raw_documents", business_id=biz["id"], channel=channel, sender=sender, received_at=now_iso(),
                       filename=filename, storage_url=f"raw/{biz['id']}/{h[:16]}_{filename}", file_hash=h,
                       typed_text=typed_text, status="received")
    _store(biz["id"], h, filename, content)
    audit(biz["id"], "system", "ingest", "raw_received", "raw_document", doc_id, None, {"channel": channel, "file": filename})
    text = None
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        pass
    if text is None or not text.strip():
        # binary image/PDF: the stub cannot read it. Ask the owner to key it in / confirm (vision LLM would go here).
        db.update("raw_documents", doc_id, status="needs_review", doc_type="unknown", confidence=0.0)
        if typed_text.strip():
            return process_text(biz, doc_id, typed_text)
        ask(biz["id"], "manual_entry", doc_id, "all",
            "I can't read this image yet (demo extractor). Please type the bill details in this format, or answer when the vision model is connected.", [TEMPLATE])
        return {"status": "needs_review", "document_id": doc_id, "message": "Needs your help: could not read the file."}
    return process_text(biz, doc_id, text if not typed_text else typed_text + "\n" + text)


def _store(biz_id, h, filename, content):
    from pathlib import Path
    p = Path(db._path).parent / "raw" / str(biz_id)
    p.mkdir(parents=True, exist_ok=True)
    (p / f"{h[:16]}_{re.sub(r'[^A-Za-z0-9._-]', '_', filename)}").write_bytes(content)


def process_text(biz, doc_id, text):
    kind = classify_text(text)
    db.update("raw_documents", doc_id, doc_type=kind)
    if kind == "bank_statement":
        return _bank(biz, doc_id, text)
    if kind == "gst_notice":
        from . import notices
        nid = notices.register_notice(biz, doc_id, text)
        db.update("raw_documents", doc_id, status="posted")
        return {"status": "posted", "document_id": doc_id, "message": "GST notice recognised; explanation prepared.", "notice_id": nid}
    if kind == "licence":
        return _licence(biz, doc_id, text)
    if kind in ("tds_certificate", "payment_receipt"):
        db.update("raw_documents", doc_id, status="posted")
        return {"status": "posted", "document_id": doc_id, "message": f"Stored as {kind}."}
    ex = extract_text(text)
    return finish_invoice(biz, doc_id, ex)


def finish_invoice(biz, doc_id, ex):
    issues = validate(ex, biz)
    confs = [c for c in ex["conf"].values()]
    db.update("raw_documents", doc_id, extraction_json=json.dumps(ex), confidence=min(confs) if confs else 0.0)
    if issues:
        db.update("raw_documents", doc_id, status="needs_review")
        for i in issues:
            if i["kind"] == "warning":
                continue
            ask(biz["id"], i["kind"], doc_id, i["field"], i["msg"], i.get("options"))
        audit(biz["id"], "agent", "intake", "clarification_requested", "raw_document", doc_id, None, {"issues": [i["msg"] for i in issues]})
        return {"status": "needs_review", "document_id": doc_id, "message": issues[0]["msg"], "issues": issues}
    try:
        inv_id = post_invoice(biz, ex, doc_id)
    except Duplicate as dup:
        if isinstance(dup.inv_id, tuple):
            db.update("raw_documents", doc_id, status="needs_review")
            ask(biz["id"], "near_duplicate", doc_id, "dup", "This looks like a bill I already have (same party, amount and a date within 3 days, different number). Is it the same bill?", ["yes_same", "no_different"])
            return {"status": "needs_review", "document_id": doc_id, "message": "Possible duplicate: please confirm."}
        db.update("raw_documents", doc_id, status="posted", linked_invoice_id=dup.inv_id, note="duplicate linked")
        audit(biz["id"], "system", "ingest", "duplicate_linked", "invoice", dup.inv_id)
        return {"status": "duplicate", "document_id": doc_id, "invoice_id": dup.inv_id, "message": "Same bill already recorded (from another channel). Linked, not double-counted."}
    db.update("raw_documents", doc_id, status="posted", linked_invoice_id=inv_id)
    return {"status": "posted", "document_id": doc_id, "invoice_id": inv_id, "message": "Posted to your books."}


def answer_question(qid, answer: str, user_id=None):
    qn = db.one("SELECT * FROM questions WHERE id=?", (qid,))
    if not qn or qn["status"] != "open":
        raise ValueError("Question not open")
    biz = db.one("SELECT * FROM businesses WHERE id=?", (qn["business_id"],))
    db.update("questions", qid, status="answered", answer=answer)
    audit(biz["id"], "user", user_id, "clarification_answered", "question", qid, None, {"answer": answer[:200]})
    if qn["ref_type"] != "raw_document":
        return _answer_other(qn, biz, answer)
    doc = db.one("SELECT * FROM raw_documents WHERE id=?", (qn["ref_id"],))
    # other open questions on same doc are re-evaluated after this answer
    if qn["kind"] == "manual_entry":
        for o in db.q("SELECT id FROM questions WHERE ref_type='raw_document' AND ref_id=? AND status='open'", (doc["id"],)):
            db.update("questions", o["id"], status="superseded")
        ex = extract_text(answer)
        return finish_invoice(biz, doc["id"], ex)
    ex = json.loads(doc["extraction_json"])
    ex.setdefault("resolved", {}); ex.setdefault("confirmed", [])
    k, fld = qn["kind"], qn["field"]
    if k == "candidates":
        val = int(answer)
        ex["resolved"][fld] = val
        if fld == "total":
            ex["total"] = val
        else:
            ex["items"][int(fld.split(".")[1])]["unit_price"] = val
            ex["conf"][fld] = 1.0
        ex["candidates"].pop(fld, None)
    elif k == "low_conf":
        if answer.lower() in ("yes", "y", "correct"):
            ex["confirmed"].append(fld)
        else:
            _set_path(ex, fld, answer); ex["confirmed"].append(fld)
    elif k in ("invalid", "missing"):
        _set_path(ex, fld, answer)
        ex["conf"][fld] = 1.0
    elif k == "direction":
        ex["fields"]["direction"] = answer
    elif k == "total_mismatch":
        if answer == "use_calculated":
            ex["ignore_bill_total"] = True
        else:
            ex["ignore_bill_total"] = False
    elif k == "near_duplicate":
        if answer == "yes_same":
            db.update("raw_documents", doc["id"], status="posted", note="duplicate confirmed by owner")
            return {"status": "duplicate", "document_id": doc["id"], "message": "Marked as the same bill."}
        ex["allow_near"] = True
    # clear this doc's other open questions that will be re-derived
    for o in db.q("SELECT id FROM questions WHERE ref_type='raw_document' AND ref_id=? AND status='open'", (doc["id"],)):
        db.update("questions", o["id"], status="superseded")
    if ex.get("allow_near"):
        try:
            inv_id = post_invoice(biz, ex, doc["id"], allow_near=True)
            db.update("raw_documents", doc["id"], status="posted", linked_invoice_id=inv_id, extraction_json=json.dumps(ex))
            return {"status": "posted", "document_id": doc["id"], "invoice_id": inv_id, "message": "Posted."}
        except Duplicate as dup:
            db.update("raw_documents", doc["id"], status="posted", linked_invoice_id=dup.inv_id if not isinstance(dup.inv_id, tuple) else dup.inv_id[1])
            return {"status": "duplicate", "document_id": doc["id"], "message": "Linked to existing."}
    return finish_invoice(biz, doc["id"], ex)


def _set_path(ex, fld, val):
    if fld.startswith("items."):
        _, i, attr = fld.split(".")
        it = ex["items"][int(i)]
        if attr == "gst_rate":
            it[attr] = float(val)
        elif attr == "unit_price":
            it[attr] = rupees(calc.clean_amount_str(val))
        elif attr == "hsn":
            it[attr] = re.sub(r"\D", "", val)
        else:
            it[attr] = val
        return
    if fld == "date":
        ex["fields"]["date"] = parse_date(val) or val
    elif fld == "items":
        pass
    elif fld == "total":
        ex["total"] = rupees(calc.clean_amount_str(val))
    else:
        ex["fields"][fld] = val.upper() if "gstin" in fld else val


def _answer_other(qn, biz, answer):
    if qn["kind"] == "bank_bill":
        return {"status": "ok", "message": "Noted."}
    return {"status": "ok"}


# ---------------- bank statements ----------------
def _bank(biz, doc_id, text):
    rd = csv.DictReader(io.StringIO(text))
    n = 0
    for r in rd:
        r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
        d = parse_date(r.get("date"))
        if not d:
            continue
        debit = calc.clean_amount_str(r.get("debit") or r.get("withdrawal") or "") or 0
        credit = calc.clean_amount_str(r.get("credit") or r.get("deposit") or "") or 0
        if not debit and not credit:
            continue
        if db.one("SELECT 1 x FROM bank_transactions WHERE business_id=? AND date=? AND amount=? AND narration=?",
                  (biz["id"], d, rupees(debit or credit), r.get("narration", ""))):
            continue
        db.insert("bank_transactions", business_id=biz["id"], date=d, amount=rupees(debit or credit),
                  direction="out" if debit else "in", narration=r.get("narration", ""))
        n += 1
    matched, asked = match_bank(biz)
    db.update("raw_documents", doc_id, status="posted")
    return {"status": "posted", "document_id": doc_id, "message": f"Bank statement parsed: {n} transactions, {matched} matched to bills, {asked} need your input."}


def match_bank(biz):
    matched = asked = 0
    for bt in db.q("SELECT * FROM bank_transactions WHERE business_id=? AND matched_invoice_id IS NULL AND asked=0", (biz["id"],)):
        want = "purchase" if bt["direction"] == "out" else "sale"
        best = None
        for inv in db.q("SELECT i.*, p.name pname FROM invoices i JOIN parties p ON p.id=i.party_id WHERE i.business_id=? AND i.direction=? AND i.total=?", (biz["id"], want, bt["amount"])):
            dd = abs((date.fromisoformat(inv["invoice_date"]) - date.fromisoformat(bt["date"])).days)
            tok = inv["pname"].lower().split()[0]
            if dd <= 45 and tok in bt["narration"].lower():
                best = inv; break
        if best:
            db.update("bank_transactions", bt["id"], matched_invoice_id=best["id"])
            if not db.one("SELECT 1 x FROM payments WHERE invoice_id=?", (best["id"],)):
                db.insert("payments", business_id=biz["id"], invoice_id=best["id"], amount=bt["amount"], date=bt["date"], mode="bank", bank_transaction_id=bt["id"])
            matched += 1
        elif bt["direction"] == "out":
            db.update("bank_transactions", bt["id"], asked=1)
            q = f"{fmt(bt['amount'])} paid on {bt['date']} ({bt['narration'][:40]}). Is there a bill for this?"
            db.insert("questions", business_id=biz["id"], kind="bank_bill", ref_type="bank_transaction", ref_id=bt["id"], field="bill",
                      question=q, options_json=json.dumps(["I will send the bill", "Not a business expense", "No bill (cash/unregistered)"]), status="open", created_at=now_iso())
            asked += 1
    return matched, asked


# ---------------- licences ----------------
def _licence(biz, doc_id, text):
    f = {}
    for line in text.splitlines():
        if ":" in line:
            k, v = [x.strip() for x in line.split(":", 1)]
            f[k.lower()] = v
    exp = parse_date(f.get("expiry") or f.get("expiry date") or f.get("valid till"))
    if not exp:
        db.update("raw_documents", doc_id, status="needs_review")
        ask(biz["id"], "missing", doc_id, "expiry", "I could not read the expiry date on this licence. Please type it (YYYY-MM-DD).")
        return {"status": "needs_review", "document_id": doc_id, "message": "Need the expiry date."}
    db.insert("compliance_documents", business_id=biz["id"], doc_type=f.get("type") or f.get("licence type") or "licence",
              number=f.get("number") or f.get("licence no"), issue_date=parse_date(f.get("issued") or f.get("issue date")), expiry_date=exp, storage_url=f"raw/{doc_id}")
    db.update("raw_documents", doc_id, status="posted")
    from . import triggers
    triggers.fire("licence_posted", biz["id"], doc_id)
    return {"status": "posted", "document_id": doc_id, "message": f"Licence stored; reminders set before {exp}."}
