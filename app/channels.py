"""Outbound/inbound message layer (WhatsApp/email). Simulated store by default; real Twilio if env keys are set.
Templates are fixed text: the LLM never free-writes to third parties."""
import os
from . import db
from .i18n import T, t, BCP
from .util import now_iso, norm_phone, audit


def render(template_id: str, lang: str, **vars) -> str:
    en = T[template_id]["en"].format(**vars)
    if lang and lang != "en" and T[template_id].get(lang):
        return en + "\n\n" + T[template_id][lang].format(**vars)
    return en


def _twilio(to, body):
    sid, tok, frm = os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN"), os.environ.get("TWILIO_WHATSAPP_FROM")
    if not (sid and tok and frm):
        return "sent_simulated"
    import httpx
    r = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", auth=(sid, tok),
                   data={"From": f"whatsapp:{frm}", "To": f"whatsapp:+91{norm_phone(to)}", "Body": body}, timeout=15)
    return "sent" if r.status_code < 300 else f"failed_{r.status_code}"


def send_template(business_id, phone, name, template_id, vars: dict, lang="en", related_type=None, related_id=None, channel="whatsapp"):
    body = render(template_id, lang, **vars)
    status = _twilio(phone, body) if phone else "no_phone"
    mid = db.insert("messages", business_id=business_id, channel=channel, direction="out", counterparty=norm_phone(phone or ""),
                    counterparty_name=name, template_id=template_id, body=body, status=status, related_type=related_type,
                    related_id=related_id, created_at=now_iso())
    audit(business_id, "system", "executor", "message_sent", "message", mid, None, {"to": name, "template": template_id})
    return mid


def log_inbound(business_id, phone, name, body, related_type=None, related_id=None, channel="whatsapp"):
    return db.insert("messages", business_id=business_id, channel=channel, direction="in", counterparty=norm_phone(phone or ""),
                     counterparty_name=name, template_id=None, body=body, status="received", related_type=related_type,
                     related_id=related_id, created_at=now_iso())


def notify_owner(business_id, title, body, lang=None, urgent=False):
    """In-app notification + WhatsApp copy to the owner (messages to the owner's own channel need no approval)."""
    owner = db.one("""SELECT u.* FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.business_id=? AND m.role='owner' AND m.revoked_at IS NULL LIMIT 1""", (business_id,))
    lang = lang or (owner["preferred_language"] if owner else "en")
    db.insert("notifications", business_id=business_id, user_id=owner["id"] if owner else None, title=title, body=body, lang=lang, created_at=now_iso())
    if owner and owner["phone"]:
        db.insert("messages", business_id=business_id, channel="whatsapp", direction="out", counterparty=norm_phone(owner["phone"]),
                  counterparty_name=owner["name"], template_id="owner_notice", body=f"{title}: {body}", status="sent_simulated", created_at=now_iso())
