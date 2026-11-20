"""Posting events fan out to downstream agents."""
def fire(event, business_id, ref_id):
    from . import db
    if event == "invoice_posted":
        inv = db.one("SELECT * FROM invoices WHERE id=?", (ref_id,))
        if inv["direction"] == "sale" and inv["goods_movement"]:
            from . import eway
            eway.on_invoice_posted(business_id, ref_id)
        if inv["direction"] == "purchase":
            from . import tds
            tds.check_purchase(business_id, ref_id)
    elif event == "licence_posted":
        from . import calendar_
        calendar_.generate_obligations(db.one("SELECT * FROM businesses WHERE id=?", (business_id,)))
