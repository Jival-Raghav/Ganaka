import json, os, hashlib, re
from datetime import date, datetime, timezone, timedelta
from . import db


def today() -> date:
    return date.fromisoformat(os.environ.get("MUNSHI_TODAY", "2026-11-19"))


def now_iso() -> str:
    t = today()
    return datetime.now(timezone.utc).replace(year=t.year, month=t.month, day=t.day).strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt(p, paise=None) -> str:
    """Indian-grouped rupee string from paise."""
    p = int(p or 0)
    neg = p < 0
    p = abs(p)
    r, ps = divmod(p, 100)
    s = str(r)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    if ps and paise is not False:
        s += f".{ps:02d}"
    return ("-" if neg else "") + "₹" + s


def rupees(x) -> int:
    """float/str rupees -> paise"""
    from decimal import Decimal, ROUND_HALF_UP
    return int((Decimal(str(x)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def fy_of(d: str) -> str:
    y, m = int(d[:4]), int(d[5:7])
    return f"{y}-{str(y + 1)[2:]}" if m >= 4 else f"{y - 1}-{str(y)[2:]}"


def period_of(d: str) -> str:
    return d[:7]


def add_days(d: str, n: int) -> str:
    return (date.fromisoformat(d) + timedelta(days=n)).isoformat()


def next_month(period: str):
    y, m = int(period[:4]), int(period[5:7])
    return (y + (m == 12), 1 if m == 12 else m + 1)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def audit(business_id, actor_type, actor_id, action, item_type=None, item_id=None, before=None, after=None):
    db.insert("audit_log", business_id=business_id, actor_type=actor_type, actor_id=str(actor_id),
              action=action, item_type=item_type, item_id=item_id,
              before_json=json.dumps(before) if before is not None else None,
              after_json=json.dumps(after) if after is not None else None, at=now_iso())


def normalize_invoice_no(s: str) -> str:
    s = re.sub(r"[\s/\\\-_.]", "", (s or "").upper())
    return re.sub(r"^0+(?=\d)", "", s)


def norm_phone(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    return d[-10:] if len(d) >= 10 else d
