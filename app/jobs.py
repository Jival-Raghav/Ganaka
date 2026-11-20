"""Scheduler jobs: gmail poll, validity watch, risk scan, reminders, rule tracker."""
import threading, time, os
from . import db, gmail, eway, notices, calendar_, tracker
from .orchestrator import default_period


def run_all():
    out = {"gmail": 0, "reminders": 0, "validity": 0, "risk": 0}
    for biz in db.q("SELECT * FROM businesses"):
        try:
            out["gmail"] += len(gmail.sync(biz).get("processed", []))
        except Exception:
            pass
        out["validity"] += len(eway.validity_watch(biz))
        out["reminders"] += len(calendar_.send_reminders(biz))
        out["risk"] += len(notices.risk_scan(biz, default_period(biz)))
    out["rule_proposals"] = len(tracker.scan())
    return out


def start(interval=900):
    def loop():
        while True:
            time.sleep(interval)
            try:
                run_all()
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True).start()
