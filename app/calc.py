"""Deterministic calculators (pure Python). The LLM never does arithmetic."""
import math, re
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timedelta
from .util import normalize_invoice_no

CH = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
STATES = {"01": ("JK", "Jammu & Kashmir"), "06": ("HR", "Haryana"), "07": ("DL", "Delhi"), "08": ("RJ", "Rajasthan"),
          "09": ("UP", "Uttar Pradesh"), "19": ("WB", "West Bengal"), "24": ("GJ", "Gujarat"), "27": ("MH", "Maharashtra"),
          "29": ("KA", "Karnataka"), "32": ("KL", "Kerala"), "33": ("TN", "Tamil Nadu"), "36": ("TS", "Telangana"),
          "37": ("AP", "Andhra Pradesh"), "03": ("PB", "Punjab"), "23": ("MP", "Madhya Pradesh"), "21": ("OD", "Odisha")}


def gstin_checksum(first14: str) -> str:
    total = 0
    for i, c in enumerate(first14):
        p = CH.index(c) * (1 if i % 2 == 0 else 2)
        total += p // 36 + p % 36
    return CH[(36 - total % 36) % 36]


def make_gstin(state: str, pan: str, entity: str = "1") -> str:
    base = f"{state}{pan}{entity}Z"
    return base + gstin_checksum(base)


def gstin_valid(g) -> bool:
    if not g or not re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]", g):
        return False
    return g[:2] in STATES and gstin_checksum(g[:14]) == g[14]


def state_of(gstin_or_code) -> str:
    return (gstin_or_code or "")[:2]


def r_half_up(x) -> int:
    return int(Decimal(x).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def line_tax(taxable: int, rate: float, intra: bool):
    tax = r_half_up(Decimal(taxable) * Decimal(str(rate)) / Decimal(100))
    if intra:
        c = tax // 2
        return {"cgst": c, "sgst": tax - c, "igst": 0}
    return {"cgst": 0, "sgst": 0, "igst": tax}


# ---------- set-off (CGST Act s.49 / rule 88A) ----------
def setoff(output: dict, itc: dict):
    L = {k: int(output.get(k, 0)) for k in ("igst", "cgst", "sgst")}
    C = {k: int(itc.get(k, 0)) for k in ("igst", "cgst", "sgst")}
    trace = []

    def use(cf, lt):
        x = min(C[cf], L[lt])
        if x > 0:
            C[cf] -= x; L[lt] -= x
            trace.append({"credit": cf.upper(), "against": lt.upper(), "amount": x})
    for cf, lt in [("igst", "igst"), ("igst", "cgst"), ("igst", "sgst"), ("cgst", "cgst"), ("cgst", "igst"),
                   ("sgst", "sgst"), ("sgst", "igst")]:
        use(cf, lt)
    return {"cash": L, "credit_left": C, "trace": trace}


def late_fee_and_interest(due: str, filed_on: str, cash_tax: int, nil: bool, fee_rule: dict, rate_pct: float):
    d = (date.fromisoformat(filed_on) - date.fromisoformat(due)).days
    if d <= 0:
        return {"days_late": 0, "late_fee": 0, "interest": 0}
    per = fee_rule["nil_paise"] if nil else fee_rule["regular_paise"]
    fee = min(per * d, fee_rule["cap_paise"])
    interest = r_half_up(Decimal(cash_tax) * Decimal(str(rate_pct)) / Decimal(100) * d / Decimal(365))
    return {"days_late": d, "late_fee": fee, "interest": interest}


# ---------- reconciliation ----------
def match_key(gstin, inv_no, inv_date):
    return (gstin or "", normalize_invoice_no(inv_no), inv_date)


def reconcile(books: list, portal: list, tol_exact=100, tol_fuzzy=1000, fuzzy_days=5):
    """books/portal: dicts with gstin, inv_no, date, taxable, tax, id.
    Returns list of {status, book, portal}. Statuses: matched, missing_in_2b, missing_in_books, value_mismatch, gstin_mismatch"""
    out, used_p = [], set()
    pidx = {}
    for p in portal:
        pidx.setdefault(match_key(p["gstin"], p["inv_no"], p["date"]), []).append(p)
    unmatched_books = []
    for b in books:
        k = match_key(b["gstin"], b["inv_no"], b["date"])
        cand = [p for p in pidx.get(k, []) if p["id"] not in used_p]
        if cand:
            p = cand[0]; used_p.add(p["id"])
            st = "matched" if abs(p["taxable"] - b["taxable"]) <= tol_exact else "value_mismatch"
            out.append({"status": st, "book": b, "portal": p})
        else:
            unmatched_books.append(b)
    for b in unmatched_books:
        found = None
        for p in portal:
            if p["id"] in used_p:
                continue
            same_no = normalize_invoice_no(p["inv_no"]) == normalize_invoice_no(b["inv_no"])
            dd = abs((date.fromisoformat(p["date"]) - date.fromisoformat(b["date"])).days)
            if p["gstin"] == b["gstin"] and abs(p["taxable"] - b["taxable"]) <= tol_fuzzy and dd <= fuzzy_days:
                found = (p, "matched" if abs(p["taxable"] - b["taxable"]) <= tol_exact else "value_mismatch"); break
            if same_no and p["gstin"] != b["gstin"] and abs(p["taxable"] - b["taxable"]) <= tol_exact and dd <= fuzzy_days:
                found = (p, "gstin_mismatch"); break
            if same_no and p["gstin"] == b["gstin"] and dd <= 31:  # same invoice, different value/date
                found = (p, "value_mismatch"); break
        if found:
            used_p.add(found[0]["id"]); out.append({"status": found[1], "book": b, "portal": found[0]})
        else:
            out.append({"status": "missing_in_2b", "book": b, "portal": None})
    for p in portal:
        if p["id"] not in used_p:
            out.append({"status": "missing_in_books", "book": None, "portal": p})
    return out


# ---------- e-way bill ----------
PIN_GEO = {"560001": (12.97, 77.59), "570001": (12.30, 76.64), "575001": (12.91, 74.86), "641001": (11.00, 76.96),
           "400001": (18.93, 72.83), "411001": (18.52, 73.86), "110001": (28.63, 77.22), "600001": (13.08, 80.27),
           "500001": (17.38, 78.48), "380001": (23.03, 72.58), "700001": (22.57, 88.36), "682001": (9.97, 76.28),
           "560100": (12.84, 77.68), "583101": (15.14, 76.92)}


def pin_distance_km(a: str, b: str):
    if a == b:
        return 10
    if a not in PIN_GEO or b not in PIN_GEO:
        return None
    (la1, lo1), (la2, lo2) = PIN_GEO[a], PIN_GEO[b]
    p1, p2 = math.radians(la1), math.radians(la2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return max(10, int(round(2 * 6371 * math.asin(math.sqrt(h)) * 1.3)))  # 1.3 road factor


def ewb_validity_days(km: int, km_per_day: int = 200) -> int:
    return max(1, math.ceil(km / km_per_day))


def ewb_valid_until(valid_from: str, km: int, km_per_day=200) -> str:
    d = date.fromisoformat(valid_from[:10]) + timedelta(days=ewb_validity_days(km, km_per_day) - 1)
    return d.isoformat() + "T23:59:00"


VEH_RE = re.compile(r"^[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{4}$")


def normalize_vehicle(s: str):
    """'ka 05 ab 1234' -> 'KA05AB1234'. Returns (normalized, valid)."""
    n = re.sub(r"[^A-Za-z0-9]", "", s or "").upper()
    m = re.search(r"[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{4}", n)
    if m:
        n = m.group(0)
    return n, bool(VEH_RE.match(n))


def ewb_number_valid(number: str, lengths: list) -> bool:
    return bool(number) and number.isdigit() and len(number) in lengths


# ---------- TDS ----------
def tds_amount(amount: int, rate_pct: float) -> int:
    return r_half_up(Decimal(amount) * Decimal(str(rate_pct)) / Decimal(100))


def clean_amount_str(s: str):
    s = re.sub(r"[₹,\s]|Rs\.?|INR", "", s or "", flags=re.I)
    try:
        return Decimal(s)
    except Exception:
        return None
