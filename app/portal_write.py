"""WRITE access to the mock portal (OTP, filing, IMS actions, e-way bill generation).
ONLY approval/executor.py may import this module; tests assert agent modules never do."""
import os
from fastapi.testclient import TestClient
from . import portal

_c = None
KEY = {"x-worker-key": portal.WORKER_KEY}


def _client():
    global _c
    if _c is None:
        if os.environ.get("PORTAL_URL"):
            import httpx
            _c = httpx.Client(base_url=os.environ["PORTAL_URL"], timeout=20)
        else:
            _c = TestClient(portal.app)
    return _c


def post(path: str, json: dict | None = None):
    r = _client().post(path, json=json or {}, headers=KEY)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise RuntimeError(str(detail))
    return r.json()
