# Ganaka — Simplifying Compliance. Empowering Businesses.

Agentic compliance assistant (working prototype).

Prepares GST returns, ITC reconciliation, e-way bills, TDS, notices, and a compliance calendar from one ledger.
**It never files**: the agent has no filing tool; filing is a human action against a mock portal (OTP + audit log).

## Research and references
- [Madras School of Economics, Working Paper 229](https://mse.ac.in/wp-content/uploads/2022/10/Working-Paper-229.pdf): estimates of GST compliance costs for small businesses.
- [CGST Act, Section 129 (CBIC)](https://taxinformation.cbic.gov.in/content/html/tax_repository/gst/acts/2017_CGST_act/active/chapter19/section129_v1.00.html): detention, seizure and release of goods and conveyances (the e-way bill penalty basis).
- [IIM Indore working paper WP-01-2021-22-ECO](https://iimidr.ac.in/wp-content/uploads/2022/06/WP-01-2021-22-ECO.pdf): impact of GST on small businesses.
- [Taxscan: Economic Survey on rising GST compliance cost for MSMEs](https://www.taxscan.in/top-stories/gst-stability-comes-at-rising-compliance-cost-for-msmes-survey-data-suggests-says-economic-survey-1442460)
- [Deloitte India GST@9 survey of MSMEs](https://www.deloitte.com/in/en/about/press-room/msmes-back-gst-reforms-call-for-faster-refunds-and-better-working-capital-support-deloitte-India-gst-9-survey.html)

## Run
```
pip install -r requirements.txt
python -m app.seed --reset        # synthetic data (also auto-seeds on first start)
python -m uvicorn app.main:app --port 8000
python -m pytest -q tests         # 25 tests
```
- Owner app (mobile-first, chat + voice): http://localhost:8000/
- Accountant console: http://localhost:8000/accountant  (priya@demo.in / demo123, OTP 123456)
- WhatsApp + mock-portal simulator (second phones, demo controls): http://localhost:8000/sim
- Mock GST/IMS/e-way bill portal: http://localhost:8000/portal/docs
- Demo owners: Ramesh 9845012345 (Kannada), Lakshmi 9845098765 (QRMP, Hindi), Suresh 9845077777 (services). OTP is always 123456.
- Demo clock is fixed to 2026-11-19 (`MUNSHI_TODAY` to override).

## Demo script (plan section 24)
1. `/sim` → "Send as Ramesh" the demo bills (clear, blurry → answer in Inbox, kachha, notice, bank CSV, licence). The Gmail copy of the Gupta bill is linked as a duplicate (Inbox → Sync Gmail).
2. Owner app → Chat: "ee month GST eshtu?" → GSTR-3B draft, proof pack, "₹18,000 stuck with Ravi Traders".
3. Suppliers: approve recommended IMS actions; nudge Ravi (message appears in the sim). In `/sim` make Ravi file → Refresh → credit recovered.
4. E-way bills: ₹72,000 inter-state sale is blocked (HSN mismatch) → refresh Part A; in `/sim` reply as Manju Transport "ka 05 ab 1234" → approve & generate; document pack goes to driver and buyer.
5. Returns → Send to accountant → console queue → approve → File (simulated) with OTP → ack number. Capacity tab.
6. `/sim` → publish the 14-digit advisory → console → Rule updates → scan → approve → owners notified.

## Where things are
`app/` — `ingest.py` (intake/dedup/clarify), `calc.py` (deterministic maths), `rules.py` (versioned rules), `returns.py`/`itc.py`/`eway.py`/`tds.py`/`notices.py`/`calendar_.py`/`tracker.py` (specialist agents), `tools.py` + `orchestrator.py` (agent tools, chat), `gate.py` (approval gate), `executor.py` + `portal_write.py` (only code that can act externally), `portal.py` (mock portal), `channels.py`/`gmail.py`/`sarvam.py` (adapters).

## Prototype choices / not production
- LLM is a deterministic stub (bill text template extraction, keyword intents); swap `ingest.extract_text` / `orchestrator.handle` for a vision LLM behind the same schemas. Photos currently ask the owner to key in details.
- SQLite instead of Postgres+RLS (tenant checks in the API layer); no Redis/Celery/LangGraph; vanilla-JS UI instead of Next.js.
- WhatsApp: Twilio sends if `TWILIO_*` env vars are set (webhook `/api/whatsapp/webhook`); otherwise simulated. Gmail reads `demo/mailbox`. Sarvam STT/TTS used if `SARVAM_API_KEY` is set; otherwise browser Web Speech.
- All tax rules in `rules.py` are assumptions marked VERIFY: have an accountant check them (plan §28). Baselines (6 h/client, hours-saved factors) are placeholders until field interviews.
