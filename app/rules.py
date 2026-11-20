"""Versioned rule config. Rules are data: code calls get_rule(key, date); LLM never states a rate.
IMPORTANT: values below must be verified by an accountant before production use (see section 28 of the plan)."""
import json
from . import db
from .util import now_iso

V = "VERIFY"  # marker in note: assumption to verify with accountant
SEED = [
    ("gst.return.gstr1.due_day", {"regular": 11, "qrmp": 13}, "2017-07-01", "https://www.cbic.gov.in", "Due day of following month (regular) / month after quarter (QRMP)"),
    ("gst.return.gstr3b.due_day", {"regular": 20, "qrmp": 22, "composition_cmp08": 18}, "2017-07-01", "https://www.cbic.gov.in", V),
    ("gst.late_fee.per_day", {"regular_paise": 5000, "nil_paise": 2000, "cap_paise": 1000000}, "2017-07-01", "https://www.cbic.gov.in", "Rs50/day (Rs20 nil), cap Rs10,000 - " + V),
    ("gst.interest_rate", 18, "2017-07-01", "https://www.cbic.gov.in", "% p.a. on late-paid tax - " + V),
    ("gst.itc.payment_days", 180, "2017-07-01", "https://www.cbic.gov.in", "Supplier must be paid within 180 days or ITC reversed - " + V),
    ("gst.itc.blocked", {"keywords": ["food", "catering", "beverage", "motor car", "personal", "club membership", "beauty", "gift"], "hsn_prefixes": ["8703"]}, "2017-07-01", "https://www.cbic.gov.in", "Section 17(5) blocked credits - " + V),
    ("gst.ims.no_action_behaviour", {"treat_no_action_as": "accepted", "recommend_explicit_action": True}, "2025-10-01", "https://www.gst.gov.in", "Sources disagree; always recommend explicit action - " + V),
    ("gst.rate.allowed", [0, 0.25, 3, 5, 12, 18, 28], "2017-07-01", "https://www.cbic.gov.in", "Slabs"),
    ("gst.rate.hsn", {"7317": 18, "7318": 18, "8467": 18, "3917": 18, "8536": 18, "6109": 5, "5208": 5, "9965": 5, "9983": 18}, "2017-07-01", "https://www.cbic.gov.in", "Sample HSN->rate map for validation warnings - " + V),
    ("gst.composition.rate", {"trader": 1.0, "manufacturer": 1.0, "service": 6.0}, "2019-04-01", "https://www.cbic.gov.in", V),
    ("gst.b2cl.threshold", 25000000, "2024-08-01", "https://www.cbic.gov.in", "paise; inter-state B2C large invoice"),
    ("gst.reverse_charge.categories", {"keywords": ["freight", "goods transport", "gta"]}, "2017-07-01", "https://www.cbic.gov.in", "RCM categories"),
    ("ewb.threshold.interstate", 5000000, "2018-04-01", "https://ewaybillgst.gov.in (CGST Rule 138)", "paise"),
    ("ewb.threshold.intrastate", {"default": 5000000, "KA": 5000000, "MH": 10000000}, "2018-04-01", "https://ewaybillgst.gov.in", "paise per state - " + V),
    ("ewb.validity", {"km_per_day": 200}, "2018-04-01", "https://ewaybillgst.gov.in", "1 day up to 200km, +1 day per 200 km"),
    ("ewb.number.format", {"lengths": [12]}, "2018-04-01", "https://ewaybillgst.gov.in", "12 digit"),
    ("ewb.penalty_pct", 200, "2017-07-01", "https://www.cbic.gov.in", "Sec 129 penalty ~200% of tax - " + V),
    ("tds.applicability.proprietor_turnover", 100000000, "2020-04-01", "https://incometaxindia.gov.in", "paise (Rs 1 crore previous-year turnover) - " + V),
    ("tds.section.194C", {"rate": 1.0, "rate_other": 2.0, "single": 3000000, "annual": 10000000}, "2020-04-01", "https://incometaxindia.gov.in", "paise thresholds - " + V),
    ("tds.section.194J", {"rate": 10.0, "single": 3000000, "annual": 3000000}, "2020-04-01", "https://incometaxindia.gov.in", V),
    ("tds.section.194I", {"rate": 10.0, "annual": 24000000}, "2020-04-01", "https://incometaxindia.gov.in", V),
    ("tds.deposit_due_day", 7, "2017-07-01", "https://incometaxindia.gov.in", "7th of next month"),
    ("calendar.reminder_offsets", [7, 3, 1, 0], "2026-01-01", "internal", "days before due"),
    ("calendar.doc_reminder_days", [60, 30, 7], "2026-01-01", "internal", "licence expiry reminders"),
    ("risk.levels", {"gstr1_vs_3b": "high", "itc_vs_2b": "high", "ewb_vs_gstr1": "medium", "unfiled": "high", "cancelled_supplier": "medium"}, "2026-01-01", "internal", ""),
    ("msme.43bh.days", {"with_agreement": 45, "without": 15}, "2024-04-01", "https://incometaxindia.gov.in", "Section 43B(h) - " + V),
    ("pf.threshold_employees", 20, "2017-07-01", "https://epfindia.gov.in", V),
    ("esi.threshold_employees", 10, "2017-07-01", "https://esic.gov.in", V),
    ("pt.karnataka.slab", {"min_salary": 2500000, "monthly": 20000}, "2017-07-01", "https://pt.kar.nic.in", "paise - " + V),
    ("itr.44ad.rate", {"digital": 6.0, "cash": 8.0}, "2017-04-01", "https://incometaxindia.gov.in", V),
    ("retention.years", 6, "2017-07-01", "https://www.cbic.gov.in", "Record keeping period - " + V),
]


def seed():
    if db.one("SELECT 1 x FROM rule_versions LIMIT 1"):
        return
    for key, val, eff, src, note in SEED:
        db.insert("rule_versions", rule_key=key, value_json=json.dumps(val), effective_from=eff, source_url=src,
                  note=note, approved_by="seed", created_at=now_iso())


def get_rule_version(key: str, on: str):
    return db.one("SELECT * FROM rule_versions WHERE rule_key=? AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?) ORDER BY effective_from DESC, id DESC LIMIT 1", (key, on, on))


def get_rule(key: str, on: str):
    r = get_rule_version(key, on)
    if not r:
        raise KeyError(f"No rule {key} effective on {on}")
    return json.loads(r["value_json"])


class RuleUse:
    """Collects rule version ids used by a calculation (for proof packs)."""
    def __init__(self, on):
        self.on, self.ids, self.used = on, {}, {}

    def get(self, key, on=None):
        on = on or self.on
        r = get_rule_version(key, on)
        if not r:
            raise KeyError(key)
        self.ids[key] = r["id"]
        v = json.loads(r["value_json"])
        self.used[key] = {"version_id": r["id"], "value": v, "effective_from": r["effective_from"], "source": r["source_url"]}
        return v


def add_version(key, value, effective_from, source_url, approved_by, note=""):
    """Close the previous open version the day before and insert the new one."""
    prev = db.one("SELECT * FROM rule_versions WHERE rule_key=? AND effective_to IS NULL ORDER BY effective_from DESC LIMIT 1", (key,))
    if prev and prev["effective_from"] < effective_from:
        from .util import add_days
        db.ex("UPDATE rule_versions SET effective_to=? WHERE id=?", (add_days(effective_from, -1), prev["id"]))
    return db.insert("rule_versions", rule_key=key, value_json=json.dumps(value), effective_from=effective_from,
                     source_url=source_url, note=note, approved_by=str(approved_by), created_at=now_iso())
