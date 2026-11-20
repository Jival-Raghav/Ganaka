"""SQLite ledger (Postgres-ready schema). Money = integer paise, timestamps = UTC ISO strings.
Multi-tenancy: every business-owned table carries business_id; API layer enforces membership."""
import json, os, sqlite3, threading
from pathlib import Path

_path = os.environ.get("MUNSHI_DB", str(Path(__file__).resolve().parent.parent / "data" / "munshi.db"))
_local = threading.local()


def configure(path: str):
    global _path
    _path = path
    _local.conn = None


def conn():
    c = getattr(_local, "conn", None)
    if c is None or getattr(_local, "path", None) != _path:
        Path(_path).parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(_path, isolation_level=None, check_same_thread=False, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        _local.conn, _local.path = c, _path
    return c


def q(sql, args=()):
    return [dict(r) for r in conn().execute(sql, args).fetchall()]


def one(sql, args=()):
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None


def ex(sql, args=()):
    return conn().execute(sql, args).lastrowid


def insert(table, **kw):
    cols = ",".join(kw)
    ph = ",".join("?" * len(kw))
    vals = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in kw.values()]
    return ex(f"INSERT INTO {table}({cols}) VALUES({ph})", vals)


def update(table, id_, **kw):
    sets = ",".join(f"{k}=?" for k in kw)
    vals = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in kw.values()]
    ex(f"UPDATE {table} SET {sets} WHERE id=?", vals + [id_])


def jl(s, default=None):
    if s is None or s == "":
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, phone TEXT UNIQUE, email TEXT UNIQUE, password TEXT, preferred_language TEXT DEFAULT 'en');
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INT, created_at TEXT);
CREATE TABLE IF NOT EXISTS firms(id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE IF NOT EXISTS businesses(id INTEGER PRIMARY KEY, legal_name TEXT, trade_name TEXT, gstin TEXT UNIQUE, pan TEXT, state_code TEXT, business_type TEXT, gst_scheme TEXT DEFAULT 'regular', udyam_registered INT DEFAULT 0, employee_count INT DEFAULT 0, default_route TEXT DEFAULT 'owner', constitution TEXT DEFAULT 'proprietor', address_pin TEXT, phone TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS memberships(id INTEGER PRIMARY KEY, user_id INT, business_id INT, role TEXT, firm_id INT, granted_at TEXT, revoked_at TEXT);
CREATE TABLE IF NOT EXISTS consents(id INTEGER PRIMARY KEY, business_id INT, user_id INT, scope TEXT, granted_at TEXT, revoked_at TEXT);
CREATE TABLE IF NOT EXISTS raw_documents(id INTEGER PRIMARY KEY, business_id INT, channel TEXT, sender TEXT, received_at TEXT, filename TEXT, storage_url TEXT, file_hash TEXT, typed_text TEXT, status TEXT, doc_type TEXT, extraction_json TEXT, confidence REAL, linked_invoice_id INT, note TEXT);
CREATE TABLE IF NOT EXISTS parties(id INTEGER PRIMARY KEY, business_id INT, name TEXT, gstin TEXT, state_code TEXT, phone TEXT, email TEXT, type TEXT, reliability_score REAL);
CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY, business_id INT, direction TEXT, party_id INT, invoice_no TEXT, invoice_date TEXT, period TEXT, fy TEXT, place_of_supply TEXT, is_reverse_charge INT DEFAULT 0, goods_movement INT DEFAULT 0, taxable_value INT, cgst INT, sgst INT, igst INT, cess INT DEFAULT 0, total INT, doc_type TEXT DEFAULT 'invoice', source_document_id INT, status TEXT DEFAULT 'posted', meta_json TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS ux_inv ON invoices(business_id, direction, party_id, invoice_no, fy, doc_type);
CREATE TABLE IF NOT EXISTS line_items(id INTEGER PRIMARY KEY, invoice_id INT, description TEXT, hsn_sac TEXT, qty REAL, unit TEXT, rate INT, taxable_value INT, gst_rate REAL, cgst INT, sgst INT, igst INT);
CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY, business_id INT, invoice_id INT, amount INT, date TEXT, mode TEXT, bank_transaction_id INT);
CREATE TABLE IF NOT EXISTS bank_transactions(id INTEGER PRIMARY KEY, business_id INT, date TEXT, amount INT, direction TEXT, narration TEXT, matched_invoice_id INT, asked INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS portal_2b_records(id INTEGER PRIMARY KEY, business_id INT, period TEXT, supplier_gstin TEXT, supplier_name TEXT, invoice_no TEXT, invoice_date TEXT, taxable_value INT, cgst INT, sgst INT, igst INT, ims_status TEXT, portal_ref INT, pulled_at TEXT);
CREATE TABLE IF NOT EXISTS reconciliation_items(id INTEGER PRIMARY KEY, business_id INT, period TEXT, invoice_id INT, portal_2b_record_id INT, party_id INT, match_status TEXT, itc_at_risk INT, recommended_action TEXT, reason TEXT, decided_action TEXT, decided_by INT, supplier_reply TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS returns(id INTEGER PRIMARY KEY, business_id INT, return_type TEXT, period TEXT, status TEXT, computed_json TEXT, proof_json TEXT, rule_version_ids TEXT, prepared_at TEXT, approved_by INT, filed_at TEXT, ack_number TEXT, explanation_json TEXT);
CREATE TABLE IF NOT EXISTS eway_bills(id INTEGER PRIMARY KEY, business_id INT, invoice_id INT, part_a_json TEXT, transporter_party_id INT, vehicle_no TEXT, distance_km INT, valid_from TEXT, valid_until TEXT, status TEXT, ewb_number TEXT, issues_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS tds_entries(id INTEGER PRIMARY KEY, business_id INT, direction TEXT, party_id INT, invoice_id INT, section TEXT, amount INT, tds_amount INT, date TEXT, deposited INT DEFAULT 0, matched_26as INT DEFAULT 0, note TEXT);
CREATE TABLE IF NOT EXISTS notices(id INTEGER PRIMARY KEY, business_id INT, raw_document_id INT, notice_type TEXT, reference_no TEXT, period TEXT, amount INT, issue_date TEXT, reply_due_date TEXT, summary TEXT, explanation_json TEXT, linked_invoice_ids TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS risk_findings(id INTEGER PRIMARY KEY, business_id INT, period TEXT, check_key TEXT, level TEXT, rupee_impact INT, detail TEXT, fix TEXT, detected_at TEXT, status TEXT DEFAULT 'open');
CREATE TABLE IF NOT EXISTS employees(id INTEGER PRIMARY KEY, business_id INT, name TEXT, monthly_salary INT, join_date TEXT, pf_applicable INT, esi_applicable INT);
CREATE TABLE IF NOT EXISTS compliance_documents(id INTEGER PRIMARY KEY, business_id INT, doc_type TEXT, number TEXT, issue_date TEXT, expiry_date TEXT, storage_url TEXT);
CREATE TABLE IF NOT EXISTS obligations(id INTEGER PRIMARY KEY, business_id INT, obligation_type TEXT, label TEXT, period TEXT, due_date TEXT, status TEXT, related_return_id INT, last_reminded TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS ux_obl ON obligations(business_id, obligation_type, period);
CREATE TABLE IF NOT EXISTS approvals(id INTEGER PRIMARY KEY, business_id INT, item_type TEXT, item_id INT, payload_json TEXT, summary TEXT, requested_by TEXT, requested_from TEXT, status TEXT, comment TEXT, decided_by INT, decided_at TEXT, created_at TEXT, result_json TEXT);
CREATE TABLE IF NOT EXISTS preapprovals(id INTEGER PRIMARY KEY, business_id INT, template_id TEXT, max_value INT, active INT DEFAULT 1);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, business_id INT, channel TEXT, direction TEXT, counterparty TEXT, counterparty_name TEXT, template_id TEXT, body TEXT, status TEXT, related_type TEXT, related_id INT, created_at TEXT);
CREATE TABLE IF NOT EXISTS conversations(id INTEGER PRIMARY KEY, business_id INT, user_id INT, channel TEXT, history_json TEXT);
CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, business_id INT, kind TEXT, ref_type TEXT, ref_id INT, field TEXT, question TEXT, options_json TEXT, status TEXT DEFAULT 'open', answer TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS rule_versions(id INTEGER PRIMARY KEY, rule_key TEXT, value_json TEXT, effective_from TEXT, effective_to TEXT, source_url TEXT, note TEXT, approved_by TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS rule_change_proposals(id INTEGER PRIMARY KEY, source_url TEXT, source_title TEXT, detected_at TEXT, summary TEXT, affected_rule_keys TEXT, proposed_values TEXT, effective_from TEXT, evidence TEXT, status TEXT, reviewed_by INT, impact_json TEXT);
CREATE TABLE IF NOT EXISTS seen_sources(url TEXT PRIMARY KEY, seen_at TEXT);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, business_id INT, user_id INT, title TEXT, body TEXT, lang TEXT, created_at TEXT, read INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS review_sessions(id INTEGER PRIMARY KEY, business_id INT, user_id INT, item_type TEXT, item_id INT, period TEXT, minutes REAL, auto_prepared INT DEFAULT 1, synthetic INT DEFAULT 0, opened_at TEXT);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, business_id INT, actor_type TEXT, actor_id TEXT, action TEXT, item_type TEXT, item_id INT, before_json TEXT, after_json TEXT, at TEXT);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT,'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT,'audit_log is append-only'); END;
"""


def init():
    conn().executescript(SCHEMA)
