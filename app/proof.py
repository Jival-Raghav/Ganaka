"""Proof pack as printable HTML (HTML -> PDF via browser print / WeasyPrint)."""
import json, html
from .util import fmt
from . import db


def _money(v):
    return fmt(v) if isinstance(v, int) else html.escape(str(v))


def render(r):
    c, p = json.loads(r["computed_json"]), json.loads(r["proof_json"])
    expl = json.loads(r["explanation_json"] or "{}")
    biz = db.one("SELECT * FROM businesses WHERE id=?", (r["business_id"],))
    h = [f"<html><head><meta charset='utf-8'><title>Proof pack {r['return_type']} {r['period']}</title><style>body{{font:14px system-ui;max-width:900px;margin:24px auto;padding:0 16px;color:#1a1a1a}}table{{border-collapse:collapse;width:100%;margin:8px 0}}td,th{{border:1px solid #ddd;padding:6px 8px;text-align:left}}th{{background:#f3f3f3}}h2{{margin-top:28px;border-bottom:2px solid #0a7;padding-bottom:4px}}.sim{{background:#fff3cd;padding:6px 10px;border-radius:6px}}</style></head><body>"]
    h.append(f"<h1>{r['return_type']} {r['period']} - {html.escape(biz['trade_name'])}</h1><p class='sim'>SIMULATION: prepared by Ganaka for human approval. Not filed on the real portal. Status: <b>{r['status']}</b> {('(ack ' + r['ack_number'] + ')') if r['ack_number'] else ''}</p>")
    h.append("<h2>1. Plain-language summary</h2>" + "".join(f"<p><b>{k.upper()}</b>: {html.escape(v)}</p>" for k, v in expl.items()))
    h.append("<h2>2. Summary</h2><table>" + "".join(f"<tr><th>{html.escape(k)}</th><td>{_money(v) if not isinstance(v, dict) else html.escape(json.dumps({a: fmt(b) for a, b in v.items()}))}</td></tr>" for k, v in p["summary"].items() if v is not None) + "</table>")
    h.append("<h2>3. Calculation trace</h2><table><tr><th>Step</th><th>Amount</th><th>Rule</th></tr>" + "".join(f"<tr><td>{html.escape(t['step'])}</td><td>{_money(t['value'])}</td><td>{html.escape(str(t.get('rule') or ''))}</td></tr>" for t in p["trace"]) + "</table>")
    h.append("<h2>4. Source records</h2><table><tr><th>Record</th><th>Date</th><th>Total</th></tr>" + "".join(f"<tr><td>{html.escape(s['label'])}</td><td>{s.get('date', '')}</td><td>{_money(s.get('total', ''))}</td></tr>" for s in p["sources"]) + "</table>")
    h.append("<h2>5. Exclusions (not claimed)</h2>" + ("<table><tr><th>Record</th><th>Reason</th><th>Amount</th></tr>" + "".join(f"<tr><td>{html.escape(e.get('label', ''))}</td><td>{html.escape(e['reason'])}</td><td>{_money(e.get('amount', ''))}</td></tr>" for e in p["exclusions"]) + "</table>" if p["exclusions"] else "<p>None.</p>"))
    h.append("<h2>6. Checks run</h2><table>" + "".join(f"<tr><td>{'PASS' if k['ok'] else 'WARN'}</td><td>{html.escape(k['check'])}</td><td>{html.escape(k['detail'])}</td></tr>" for k in p["checks"]) + "</table>")
    h.append("<h2>7. Rule versions used</h2><table><tr><th>Rule</th><th>Version id</th><th>Effective from</th><th>Source</th></tr>" + "".join(f"<tr><td>{html.escape(k)}</td><td>{v['version_id']}</td><td>{v['effective_from']}</td><td>{html.escape(v['source'])}</td></tr>" for k, v in p["rules"].items()) + "</table>")
    h.append("<h2>8. Documents for the accountant</h2><ul>" + "".join(f"<li>{html.escape(d)}</li>" for d in p["documents_for_accountant"]) + "</ul></body></html>")
    return "".join(h)
