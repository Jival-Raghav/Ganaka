"""READ-ONLY access to the mock portal. Agent modules may import this; it carries no worker key."""
import os
from fastapi.testclient import TestClient
from . import portal

_c = None


def _client():
    global _c
    if _c is None:
        if os.environ.get("PORTAL_URL"):
            import httpx
            _c = httpx.Client(base_url=os.environ["PORTAL_URL"], timeout=20)
        else:
            _c = TestClient(portal.app)
    return _c


def get(path: str):
    r = _client().get(path)
    if r.status_code >= 400:
        raise RuntimeError(f"portal {r.status_code}: {r.text}")
    return r.json()
