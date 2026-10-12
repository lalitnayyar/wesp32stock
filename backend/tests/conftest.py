import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="lstest_"))
os.environ.update({
    "APP_ENV": "test",
    "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", f"sqlite:///{(_tmp / 'test.db').as_posix()}"),
    "MARKET_PROVIDER": "fixture",
    "SCHEDULER_ENABLED": "false",
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": "correct-horse-battery",
    "APP_SECRET_KEY": "test-secret-key-0123456789abcdef0123456789",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.ratelimit import limiter  # noqa: E402
from app.main import app  # noqa: E402
from app.services.market import service as market  # noqa: E402

ADMIN_PW = "correct-horse-battery"


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    limiter.reset()
    market.set_provider(None)
    market.LAST_POLL.__init__()
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


class Admin:
    """TestClient wrapper that logs in and sends the CSRF header on mutating requests."""

    def __init__(self, client: TestClient):
        self.c = client
        r = client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PW})
        assert r.status_code == 200, r.text
        self.csrf = r.json()["csrf_token"]

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def _m(self, method, url, **kw):
        headers = {"X-CSRF-Token": self.csrf, **kw.pop("headers", {})}
        return self.c.request(method, url, headers=headers, **kw)

    def post(self, url, **kw):
        return self._m("POST", url, **kw)

    def put(self, url, **kw):
        return self._m("PUT", url, **kw)

    def delete(self, url, **kw):
        return self._m("DELETE", url, **kw)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin(client):
    return Admin(client)
