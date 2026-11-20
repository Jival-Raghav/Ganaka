"""Gmail intake. Production: OAuth gmail.readonly + query 'has:attachment (invoice OR bill OR GST)', poll 15 min (or watch+Pub/Sub).
Prototype: reads demo/mailbox/*.txt as the connected mailbox. Requires the owner's gmail_read consent."""
import os
from pathlib import Path
from . import db, ingest
from .seed import DEMO_DIR


def has_consent(biz_id):
    return bool(db.one("SELECT 1 x FROM consents WHERE business_id=? AND scope='gmail_read' AND revoked_at IS NULL", (biz_id,)))


def sync(biz):
    if not has_consent(biz["id"]):
        return {"error": "Gmail consent not granted", "processed": []}
    if os.environ.get("GMAIL_REFRESH_TOKEN"):
        raise NotImplementedError("Real Gmail polling: use google-api-python-client with gmail.readonly; query has:attachment (invoice OR bill OR GST)")
    out = []
    for p in sorted((DEMO_DIR / "mailbox").glob("*.txt")):
        raw = p.read_bytes()
        text = raw.decode("utf8")
        body = text.split("\n\n", 1)[1] if "\n\n" in text else text
        # only mail addressed to this business (buyer GSTIN match) is fetched; others are never stored
        if biz["gstin"] not in body and biz["trade_name"].lower() not in body.lower():
            continue
        sender = next((l.split(":", 1)[1].strip() for l in text.splitlines() if l.lower().startswith("from:")), "gmail")
        r = ingest.process_document(biz, "gmail", sender, p.name, body.encode("utf8"))
        out.append({"file": p.name, **r})
    return {"processed": out}
