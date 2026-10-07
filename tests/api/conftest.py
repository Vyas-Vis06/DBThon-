"""API test fixtures: a migrated database, the real FastAPI app on top of it (as the runtime role ze_app),
and a user for every role with the same password, logged in on demand."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tests.factories import Factory
from zeroentry.config import Settings
from zeroentry.main import create_app
from zeroentry.security import hash_password

PASSWORD = "Api-Test-Pass-1"
API = "/api/v1"
STAFF = {"admin", "engineer", "supervisor", "auditor"}


def make_settings(db, **overrides) -> Settings:
    base = dict(app_env="test", database_url=db.app_url, bcrypt_rounds=4, login_max_failures=3, login_ip_limit=10_000,
                safety_sweep_interval_seconds=0)
    return Settings(**{**base, **overrides})


@pytest.fixture
def make_app(db):
    return lambda **overrides: create_app(make_settings(db, **overrides))


@pytest.fixture
def app(make_app):
    return make_app()


def build_world(conn) -> dict:
    f = Factory(conn)
    hashed = hash_password(PASSWORD, rounds=4)
    w: dict = {"f": f}
    w["ulb"] = f.ulb(name="Test Zone")
    w["manhole"] = f.manhole(w["ulb"])
    w["machine"] = f.machine(w["ulb"])
    w["detector"] = f.detector()
    w["ca"], w["cb"] = f.contractor(), f.contractor()
    w["workers_a"] = [f.worker(w["ca"]) for _ in range(5)]
    w["workers_b"] = [f.worker(w["cb"]) for _ in range(5)]
    users: dict[str, dict] = {}

    def add(key: str, role: str, **kw) -> None:
        email = f"{key}@zeroentry.example"
        users[key] = {"id": f.user(role, email=email, password_hash=hashed, **kw), "email": email, "role": role}

    add("admin", "ADMIN")
    add("engineer", "ENGINEER", ulb_id=w["ulb"])
    add("supervisor", "SUPERVISOR")
    add("supervisor2", "SUPERVISOR")
    add("auditor", "AUDITOR")
    add("contractor_a", "CONTRACTOR", contractor_id=w["ca"])
    add("contractor_b", "CONTRACTOR", contractor_id=w["cb"])
    add("worker_a", "WORKER", worker_id=w["workers_a"][0])
    w["users"] = users
    return w


@pytest.fixture
def world(conn):
    return build_world(conn)


def login(app, email: str, password: str = PASSWORD) -> TestClient:
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


@pytest.fixture(scope="module")
def shared(module_db):
    """world + app + api() on a module-wide database, for read-only probe modules (see tests/api/test_rbac.py)."""
    with module_db.connect() as c:
        world = build_world(c)
    app = create_app(make_settings(module_db))
    cache: dict[str, TestClient] = {}

    def get(who: str) -> TestClient:
        if who not in cache:
            cache[who] = login(app, world["users"][who]["email"])
        return cache[who]

    return SimpleNamespace(world=world, app=app, api=get)


@pytest.fixture
def api(app, world):
    """api('engineer') -> a TestClient signed in as that user (cookie jar + CSRF header), created once per test."""
    cache: dict[str, TestClient] = {}

    def get(who: str) -> TestClient:
        if who not in cache:
            cache[who] = login(app, world["users"][who]["email"])
        return cache[who]

    return get


def ok(response, status: int = 200):
    assert response.status_code == status, f"{response.request.method} {response.request.url.path} -> {response.status_code}: {response.text}"
    return response.json()


def refused(response, status: int, code: str | None = None, message: str | None = None):
    assert response.status_code == status, f"{response.request.method} {response.request.url.path} -> {response.status_code}: {response.text}"
    error = response.json()["error"]
    if code:
        assert error["code"] == code, error
    if message:
        assert message.lower() in error["message"].lower(), error
    return error
