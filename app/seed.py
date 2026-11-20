"""Synthetic demo data: Ramesh Hardware (Bengaluru), Lakshmi Textiles (QRMP), Shree Tech Services (TDS), planted problems,
accountant firm, mock-portal data, and demo files. Only synthetic businesses and GSTINs. Run: python -m app.seed --reset"""
import hashlib, json, os, random, sys
from datetime import date
from pathlib import Path
from . import db, rules, portal, calc
from .util import rupees, now_iso, today, norm_phone

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"
R = random.Random(42)


def mk_pan(name, kind="P"):
    h = hashlib.md5(name.encode()).hexdigest()
    letters = "".join(chr(65 + int(c, 16) % 26) for c in h[:3])
    return f"{letters}{kind}{name[0].upper()}{int(h[3:7], 16) % 10000:04d}{chr(65 + int(h[7], 16) % 26)}"


def gst(state, name):
    return calc.make_gstin(state, mk_pan(name))


def user(name, phone=None, email=None, lang="en", pw=None):
    return db.insert("users", name=name, phone=norm_phone(phone) if phone else None, email=email, password=pw, preferred_language=lang)


def biz_row(legal, trade, state, btype, scheme, pin, phone, udyam=1, emp=0, constitution="proprietor", route="owner"):
    pan = mk_pan(legal)
    g = calc.make_gstin(state, pan)
    bid = db.insert("businesses", legal_name=legal, trade_name=trade, gstin=g, pan=pan, state_code=state, business_type=btype, gst_scheme=scheme,
                    udyam_registered=udyam, employee_count=emp, default_route=route, constitution=constitution, address_pin=pin, phone=norm_phone(phone), created_at=now_iso())
    return db.one("SELECT * FROM businesses WHERE id=?", (bid,))


def member(uid, bid, role, firm=None):
    db.insert("memberships", user_id=uid, business_id=bid, role=role, firm_id=firm, granted_at=now_iso())
    if role == "owner":
        for sc in ("gmail_read", "whatsapp", "bank_upload"):
            db.insert("consents", business_id=bid, user_id=uid, scope=sc, granted_at=now_iso())


def tp(gstin, name, state, status="active", pan=None):
    portal.c().execute("INSERT OR REPLACE INTO taxpayers VALUES(?,?,?,?,?)", (gstin, name, state, status, pan))


def inv(biz, direction, party, no, d, items, paid=True, rcm=False, goods=False, **extra):
    """party = dict(name, gstin, phone). items = [(desc, hsn, qty, unit_rupees, gst_rate)]"""
    from . import ingest
    f = {"invoice_no": no, "date": d, "paid": paid, "reverse_charge": rcm, "goods_movement": goods, "pay_mode": extra.pop("mode", R.choice(["bank", "UPI", "bank", "cash"]))}
    if direction == "sale":
        f.update(seller=biz["trade_name"], seller_gstin=biz["gstin"], buyer=party["name"], buyer_gstin=party.get("gstin") or "", buyer_phone=party.get("phone"), pos=extra.pop("pos", (party.get("gstin") or biz["gstin"])[:2]))
    else:
        f.update(seller=party["name"], seller_gstin=party.get("gstin") or "", seller_phone=party.get("phone"), buyer=biz["trade_name"], buyer_gstin=biz["gstin"], pos=biz["state_code"])
    f.update(extra)
    ex = {"doc_type": "invoice", "fields": f, "items": [{"desc": it[0], "hsn": it[1], "qty": it[2], "unit_price": rupees(it[3]), "gst_rate": it[4]} for it in items], "total": None, "conf": {}, "candidates": {}}
    return ingest.post_invoice(biz, ex, None, allow_near=True)


def portal_from_books(biz, skip=(), overrides=None):
    overrides = overrides or {}
    for i in db.q("SELECT i.*, p.gstin pg, p.name pn FROM invoices i JOIN parties p ON p.id=i.party_id WHERE i.business_id=? AND i.direction='purchase' AND i.is_reverse_charge=0 AND p.gstin IS NOT NULL", (biz["id"],)):
        o = overrides.get(i["invoice_no"], {})
        vis = 0 if i["invoice_no"] in skip else 1
        t_ = o.get("taxable", i["taxable_value"])
        cg, sg, ig = o.get("cgst", i["cgst"]), o.get("sgst", i["sgst"]), o.get("igst", i["igst"])
        portal.c().execute("INSERT INTO ims(buyer_gstin,period,supplier_gstin,supplier_name,invoice_no,invoice_date,taxable,cgst,sgst,igst,ims_status,visible) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                           (biz["gstin"], i["period"], i["pg"], i["pn"], i["invoice_no"], i["invoice_date"], t_, cg, sg, ig, "no_action", vis))


def reset():
    p = Path(db._path)
    for ext in ("", "-wal", "-shm"):
        try:
            Path(str(p) + ext).unlink()
        except FileNotFoundError:
            pass
    pp = Path(portal._path)
    for ext in ("", "-wal", "-shm"):
        try:
            Path(str(pp) + ext).unlink()
        except FileNotFoundError:
            pass
    db._local.conn = None
    portal._local.c = None
    import shutil
    shutil.rmtree(p.parent / "raw", ignore_errors=True)


def run(force=False):
    db.init()
    portal.c()
    if db.one("SELECT 1 x FROM businesses LIMIT 1") and not force:
        return
    rules.seed()
    old = os.environ.get("MUNSHI_TODAY")
    # ---------- people ----------
    firm = db.insert("firms", name="Priya & Associates")
    priya = user("Priya Nair, CA", "9845000001", "priya@demo.in", "en", "demo123")
    ramesh = user("Ramesh Gowda", "9845012345", None, "kn")
    manju_staff = user("Manju (staff)", "9845012346", None, "kn")
    lakshmi = user("Lakshmi Devi", "9845098765", None, "hi")
    shree = user("Suresh Shree", "9845077777", None, "en")
    # ---------- businesses ----------
    rh = biz_row("Ramesh Gowda", "Ramesh Hardware", "29", "trader", "regular", "560001", "9845012345", 1, 3)
    lt = biz_row("Lakshmi Devi", "Lakshmi Textiles", "29", "trader", "qrmp", "560001", "9845098765", 1, 0)
    st = biz_row("Suresh Shree", "Shree Tech Services", "29", "service", "regular", "560100", "9845077777", 0, 0)
    for b, owner in ((rh, ramesh), (lt, lakshmi), (st, shree)):
        member(owner, b["id"], "owner")
        member(priya, b["id"], "accountant", firm)
        tp(b["gstin"], b["legal_name"], b["state_code"], "active", b["pan"])
    member(manju_staff, rh["id"], "staff")
    db.update("businesses", st["id"], default_route="accountant")
    st = db.one("SELECT * FROM businesses WHERE id=?", (st["id"],))
    for t_ in ("m_transporter_partb", "m_doc_pack", "m_buyer_copy", "m_ewb_expiry"):
        db.insert("preapprovals", business_id=rh["id"], template_id=t_, max_value=None, active=1)
    # ---------- parties (synthetic) ----------
    S = {}
    for key, name, state, ph in [("ravi", "Ravi Traders", "29", "9845011001"), ("sharma", "Sharma Electricals", "29", "9845011002"), ("gupta", "Gupta Fasteners", "29", "9845011003"),
                                 ("mehta", "Mehta Agencies", "29", "9845011004"), ("nair", "Nair Plastics", "29", "9845011005"), ("patel", "Patel Tools", "24", "9845011006"),
                                 ("annapurna", "Annapurna Catering", "29", "9845011007"), ("unknown", "Unknown Enterprises", "29", "9845011008")]:
        S[key] = {"name": name, "gstin": gst(state, name), "phone": ph}
        tp(S[key]["gstin"], name, state, "cancelled" if key == "mehta" else "active")
    S["manju"] = {"name": "Manju Transport", "gstin": "", "phone": "9845011111"}
    C = {}
    for key, name, state, ph in [("shree_c", "Shree Constructions", "29", "9845022001"), ("mysore", "Mysore Builders", "29", "9845022002"), ("deccan", "Deccan Infra", "29", "9845022003"),
                                 ("rao", "Rao Interiors", "29", "9845022004"), ("metro", "Metro Hardware Mart", "27", "9845022005"), ("chennai", "Chennai Fixtures", "33", "9845022006"),
                                 ("vijay", "Vijay Engineering", "29", "9845022007"), ("ganesh", "Ganesh Electricals", "29", "9845022008")]:
        C[key] = {"name": name, "gstin": gst(state, name), "phone": ph}
        tp(C[key]["gstin"], name, state)
    WALK = {"name": "Walk-in customer", "gstin": "", "phone": None}
    PROD = [("Iron nails 2 inch", "7317", 18), ("Hex bolts M10", "7318", 18), ("Power drill 650W", "8467", 18), ("PVC pipe 1 inch", "3917", 18), ("Modular switch", "8536", 18)]
    suppliers_reg = [S["ravi"], S["sharma"], S["gupta"], S["mehta"], S["nair"]]
    # ---------- Ramesh Hardware: Sep, Oct, Nov ----------
    mon = {"2026-09": 28, "2026-10": 28, "2026-11": 18}
    sn = 100
    for per, last in mon.items():
        n_sales = 18 if per != "2026-11" else 10
        for k in range(n_sales):
            c = R.choice(list(C.values()) + [WALK, WALK])
            if c is C["metro"]:
                c = C["shree_c"]
            d = f"{per}-{R.randint(1, last):02d}"
            p = R.choice(PROD)
            sn += 1
            inv(rh, "sale", c, f"RH/26-27/{sn:04d}", d, [(p[0], p[1], R.choice([20, 50, 100, 150]), R.choice([85, 120, 150, 340, 520]), p[2])], paid=R.random() < 0.75)
        for k in range(14 if per != "2026-11" else 8):
            s_ = R.choice([S["ravi"], S["gupta"], S["nair"], S["sharma"], S["patel"]])
            d = f"{per}-{R.randint(1, last):02d}"
            p = R.choice(PROD)
            inv(rh, "purchase", s_, f"{s_['name'].split()[0][:3].upper()}-{R.randint(100, 999)}-{per[5:]}", d, [(p[0], p[1], R.choice([10, 20, 30]), R.choice([60, 90, 110, 240, 410]), p[2])], paid=(per != "2026-11" or R.random() < 0.7))
        # planted problems
    inv(rh, "purchase", S["ravi"], "INV-1043", "2026-10-28", [("Hex bolts M10 bulk", "7318", 1000, 100, 18)], paid=False)           # Rs18,000 ITC, supplier files late
    inv(rh, "purchase", S["sharma"], "SE-221", "2026-10-12", [("Modular switch", "8536", 250, 100, 18)], paid=True)                   # books Rs25,000; supplier reports Rs22,000
    inv(rh, "purchase", S["manju"], "FRT-88", "2026-10-15", [("Freight charges (goods transport agency)", "9965", 1, 20000, 5)], paid=True)   # RCM
    inv(rh, "purchase", S["annapurna"], "AC-17", "2026-10-20", [("Staff lunch catering", "9963", 1, 10000, 5)], paid=True)           # blocked credit (food)
    inv(rh, "purchase", S["mehta"], "MA-552", "2026-10-09", [("PVC pipe 1 inch", "3917", 100, 300, 18)], paid=True)                  # cancelled supplier
    # inter-state sale needing an e-way bill (Rs72,000) and an intra-state sale near the threshold
    inv(rh, "sale", C["metro"], "RH/26-27/0900", "2026-11-19", [("Iron nails 2 inch bulk", "7317", 1, 61016.95, 18)], paid=False, goods=True,
        transporter="Manju Transport | 9845011111", to_pin="400001", from_pin="560001", pos="27")
    inv(rh, "sale", C["mysore"], "RH/26-27/0901", "2026-11-18", [("Hex bolts M10", "7318", 100, 415, 18)], paid=True, goods=True, to_pin="570001", from_pin="560001")
    # portal side
    portal_from_books(rh, skip=("INV-1043",), overrides={"SE-221": {"taxable": rupees(22000), "cgst": rupees(1980), "sgst": rupees(1980)}})
    portal.c().execute("INSERT INTO ims(buyer_gstin,period,supplier_gstin,supplier_name,invoice_no,invoice_date,taxable,cgst,sgst,igst,ims_status,visible) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)",
                       (rh["gstin"], "2026-10", S["unknown"]["gstin"], "Unknown Enterprises", "UE-9001", "2026-10-22", rupees(50000), rupees(4500), rupees(4500), 0, "no_action"))
    # ewb draft: snapshot HSN differs from the final invoice (planted validator catch)
    from . import eway
    metro_inv = db.one("SELECT id FROM invoices WHERE invoice_no='RH/26-27/0900'")
    e = db.one("SELECT * FROM eway_bills WHERE invoice_id=?", (metro_inv["id"],))
    if e:
        a = json.loads(e["part_a_json"]); a["hsn"] = "7318"
        db.update("eway_bills", e["id"], part_a_json=json.dumps(a))
        eway.validate_ewb(rh, e["id"])
    # employees, licence
    for nm, sal in (("Raju", 18000), ("Kumar", 22000), ("Shanta", 26000)):
        db.insert("employees", business_id=rh["id"], name=nm, monthly_salary=rupees(sal), join_date="2024-04-01", pf_applicable=1, esi_applicable=1)
    db.insert("compliance_documents", business_id=rh["id"], doc_type="Shop & Establishment licence", number="SE/BLR/4471", issue_date="2025-12-14", expiry_date="2026-12-14", storage_url="vault/shop-licence")
    db.insert("compliance_documents", business_id=rh["id"], doc_type="Udyam registration", number="UDYAM-KR-03-0012345", issue_date="2022-07-01", expiry_date="2031-07-01", storage_url="vault/udyam")
    # bank (payments already modelled; add statement rows for matched ones)
    for pay in db.q("SELECT p.*, i.invoice_no, i.direction, pa.name pn FROM payments p JOIN invoices i ON i.id=p.invoice_id JOIN parties pa ON pa.id=i.party_id WHERE p.business_id=? AND p.mode='bank' LIMIT 30", (rh["id"],)):
        bid = db.insert("bank_transactions", business_id=rh["id"], date=pay["date"], amount=pay["amount"], direction="out" if pay["direction"] == "purchase" else "in",
                        narration=f"NEFT {pay['pn']} {pay['invoice_no']}", matched_invoice_id=pay["invoice_id"])
        db.update("payments", pay["id"], bank_transaction_id=bid)
    # ---------- Lakshmi Textiles (QRMP) ----------
    TEX = [("Cotton shirting fabric", "5208", 5), ("Knitted t-shirts", "6109", 5)]
    lbuyers = [C["vijay"], C["ganesh"], WALK]
    ln = 0
    for per in ("2026-07", "2026-08", "2026-09", "2026-10"):
        for k in range(4):
            ln += 1
            p = R.choice(TEX)
            inv(lt, "sale", R.choice(lbuyers), f"LT/{ln:04d}", f"{per}-{R.randint(1, 27):02d}", [(p[0], p[1], R.choice([50, 100]), R.choice([180, 240, 320]), p[2])], paid=True)
        for k in range(3):
            p = R.choice(TEX)
            inv(lt, "purchase", R.choice([S["gupta"], S["nair"]]), f"TX-{R.randint(100, 999)}-{per[5:]}", f"{per}-{R.randint(1, 27):02d}", [(p[0], p[1], 100, R.choice([120, 150]), 12)], paid=True)
    portal_from_books(lt)
    # ---------- Shree Tech Services (service, TDS) ----------
    cust = [{"name": "Infosys Peers Pvt Ltd", "gstin": gst("29", "Infosys Peers"), "phone": "9845033001"}, {"name": "Zenith Retail Ltd", "gstin": gst("29", "Zenith Retail"), "phone": "9845033002"},
            {"name": "BlueLeaf Foods", "gstin": gst("29", "BlueLeaf Foods"), "phone": "9845033003"}]
    for c in cust:
        tp(c["gstin"], c["name"], "29")
    k = 0
    for per in ("2026-09", "2026-10"):
        for c in cust:
            k += 1
            amt = R.choice([40000, 60000, 85000])
            from . import ingest
            f = {"invoice_no": f"ST/{k:03d}", "date": f"{per}-{R.randint(2, 25):02d}", "paid": True, "pay_mode": "bank", "seller": st["trade_name"], "seller_gstin": st["gstin"], "buyer": c["name"], "buyer_gstin": c["gstin"], "buyer_phone": c["phone"], "pos": "29",
                 "tds": rupees(amt * 0.10)}
            ex = {"doc_type": "invoice", "fields": f, "items": [{"desc": "Software consultancy", "hsn": "9983", "qty": 1, "unit_price": rupees(amt), "gst_rate": 18}], "total": None, "conf": {}, "candidates": {}}
            ingest.post_invoice(st, ex, None, allow_near=True)
    ents = db.q("SELECT t.*, p.name party FROM tds_entries t JOIN parties p ON p.id=t.party_id WHERE t.business_id=? AND t.direction='deducted_from_us' ORDER BY t.id", (st["id"],))
    for i_, t_ in enumerate(ents):
        if i_ == 2:
            continue  # one TDS credit missing in 26AS
        tds_amt = t_["tds_amount"] - (rupees(1500) if i_ == 4 else 0)  # one amount mismatch
        portal.c().execute("INSERT INTO tds26as(pan,fy,deductor,deductor_tan,amount,tds,date) VALUES(?,?,?,?,?,?,?)", (st["pan"], "2026-27", t_["party"], "BLRX12345A", t_["amount"], tds_amt, t_["date"]))
    # ---------- advisory for the rule tracker (unpublished until demo) ----------
    portal.c().execute("INSERT INTO advisories(source,title,url,date,body,published) VALUES(?,?,?,?,?,?)",
                       ("GSTN", "Advisory: E-way bill numbers to be 14 digits from 1 January 2027", "https://ewaybillgst.gov.in/advisory/14-digit-ewb", "2026-11-17",
                        "The E-way Bill system will generate 14-digit e-way bill numbers instead of 12-digit numbers. This change comes into effect from 1st January 2027. Taxpayers and transporters should update their systems.", 0))
    portal.c().execute("INSERT INTO advisories(source,title,url,date,body,published) VALUES(?,?,?,?,?,?)",
                       ("GSTN", "Advisory on biometric Aadhaar authentication in Gujarat", "https://www.gst.gov.in/newsandupdates/read/900", "2026-11-05", "Taxpayers in Gujarat are advised to complete Aadhaar authentication.", 1))
    # ---------- calendar, return history ----------
    from . import calendar_, returns, itc, gate, executor, notices
    for b in (rh, lt, st):
        calendar_.generate_obligations(b)
    # History: Sept GSTR-1 + 3B filed (simulated) on 15 Oct; Oct GSTR-1 filed on 10 Nov (so Oct GSTR-3B is the live item, due 20 Nov)
    for as_of, rts, per in (("2026-10-15", ("GSTR1", "GSTR3B"), "2026-09"), ("2026-11-10", ("GSTR1",), "2026-10")):
        os.environ["MUNSHI_TODAY"] = as_of
        for rt in rts:
            r = (returns.draft_gstr1 if rt == "GSTR1" else returns.draft_gstr3b)(rh, per)
            db.update("returns", r["return_id"], status="approved")
            executor.request_filing_otp(r["return_id"])
            executor.file_return(r["return_id"], priya, "123456")
    os.environ["MUNSHI_TODAY"] = old or "2026-11-19"
    if not old:
        os.environ.pop("MUNSHI_TODAY", None)
    db.ex("UPDATE approvals SET status='approved', decided_by=?, decided_at=? WHERE item_type='return' AND status='pending'", (priya, now_iso()))
    # October drafts for Ramesh (due tomorrow) + reconciliation + risk scan
    returns.draft_gstr3b(rh, "2026-10")
    itc.reconcile_itc(rh, "2026-10")
    notices.risk_scan(rh, "2026-10")
    tds_mod = __import__("app.tds", fromlist=["x"])
    tds_mod.match_26as(st)
    # accountant review timing (synthetic) for the capacity dashboard
    for b in (rh, lt, st):
        for per in ("2026-08", "2026-09"):
            db.insert("review_sessions", business_id=b["id"], user_id=priya, item_type="return", item_id=0, period=per, minutes=R.choice([95, 110, 130]), auto_prepared=1, synthetic=1, opened_at=now_iso())
    calendar_.refresh_status(rh)
    write_demo_files(rh)


def write_demo_files(rh):
    (DEMO_DIR / "bills").mkdir(parents=True, exist_ok=True)
    (DEMO_DIR / "mailbox").mkdir(parents=True, exist_ok=True)
    gupta_g = db.one("SELECT gstin FROM parties WHERE business_id=? AND name='Gupta Fasteners'", (rh["id"],))["gstin"]
    nair_g = db.one("SELECT gstin FROM parties WHERE business_id=? AND name='Nair Plastics'", (rh["id"],))["gstin"]
    base = f"Seller: {{s}}\nSeller GSTIN: {{sg}}\nBuyer: Ramesh Hardware\nBuyer GSTIN: {rh['gstin']}\nInvoice No: {{no}}\nDate: {{d}}\nPlace of Supply: 29\n"
    clear = base.format(s="Gupta Fasteners", sg=gupta_g, no="GF-2026-771", d="2026-11-17") + "Item: Hex bolts M12 | 7318 | 200 | 95 | 18\nPaid: yes\nPay Mode: UPI\nTotal: 22420\n"
    (DEMO_DIR / "bills" / "1_purchase_gupta_clear.txt").write_text(clear, encoding="utf8")
    (DEMO_DIR / "mailbox" / "email_gupta_invoice.txt").write_text("From: accounts@guptafasteners.example\nSubject: Invoice GF-2026-771\n\n" + clear.replace("GF-2026-771", "GF/2026/771"), encoding="utf8")
    blurry = base.format(s="Nair Plastics", sg=nair_g, no="NP-3320", d="2026-11-18") + "Item: PVC pipe 2 inch [blurry] | 3917 | 40 | 310 or 31 | 18\nPaid: no\n"
    (DEMO_DIR / "bills" / "2_purchase_nair_blurry.txt").write_text(blurry, encoding="utf8")
    (DEMO_DIR / "bills" / "3_kachha_bill_unregistered.txt").write_text(
        f"Seller: Local Scrap Dealer\nBuyer: Ramesh Hardware\nBuyer GSTIN: {rh['gstin']}\nInvoice No: K-12\nDate: 2026-11-16\nItem: Packing material | 4819 | 30 | 45 | 0\nPaid: yes\nPay Mode: cash\n", encoding="utf8")
    sale = (f"Seller: Ramesh Hardware\nSeller GSTIN: {rh['gstin']}\nBuyer: Rao Interiors\nBuyer GSTIN: {db.one('SELECT gstin FROM parties WHERE business_id=? AND name=?', (rh['id'], 'Rao Interiors'))['gstin'] if db.one('SELECT gstin FROM parties WHERE business_id=? AND name=?', (rh['id'], 'Rao Interiors')) else gst('29', 'Rao Interiors')}\n"
            "Invoice No: RH/26-27/0950\nDate: 2026-11-19\nPlace of Supply: 29\nItem: Power drill 650W | 8467 | 12 | 2450 | 18\nGoods Movement: yes\nPaid: no\n")
    (DEMO_DIR / "bills" / "4_sale_rao.txt").write_text(sale, encoding="utf8")
    (DEMO_DIR / "notice.txt").write_text(
        "GST NOTICE - Show Cause Notice under Section 73\nNotice Type: Show Cause Notice (ITC mismatch)\nRef No: ZD2910261234567\nDate: 2026-11-15\nPeriod: 2026-10\nAmount Demanded: 6000\nReply By: 2026-12-12\n"
        "Subject: ITC claimed in GSTR-3B exceeds ITC available in GSTR-2B for the period. Please explain the difference.\n", encoding="utf8")
    (DEMO_DIR / "bank_statement.csv").write_text("date,narration,debit,credit\n2026-11-03,UPI Sharma Electricals,8500,\n2026-11-05,NEFT Shree Constructions,,45000\n2026-11-09,IMPS Gupta Fasteners GF-2026-771,22420,\n", encoding="utf8")
    (DEMO_DIR / "licence.txt").write_text("Trade Licence\nType: Trade licence\nNumber: TL/BLR/88123\nIssued: 2025-11-01\nExpiry: 2026-12-31\n", encoding="utf8")


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset()
    run(force=True)
    print("Seeded.")
