"""Authentication: opaque server-side sessions, lockout, throttling, CSRF. SECURITY.md."""

import hashlib

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import API, PASSWORD, login, ok, refused


def sign_in(app, email, password=PASSWORD):
    return TestClient(app, raise_server_exceptions=False).post(f"{API}/auth/login", json={"email": email, "password": password})


def test_login_sets_an_httponly_strict_cookie_and_returns_the_csrf_token(app, world, conn):
    response = sign_in(app, world["users"]["admin"]["email"])
    body = ok(response)
    assert body["user"]["role"] == "ADMIN" and body["csrf_token"] and body["session_token"]
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith("ze_session=") and "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    assert "password" not in response.text.lower().replace("current_password", "")
    row = conn.execute("SELECT token_hash, csrf_token FROM user_session").fetchone()
    assert bytes(row["token_hash"]) == hashlib.sha256(body["session_token"].encode()).digest()   # only the hash is stored
    assert body["session_token"].encode() not in bytes(row["token_hash"])


def test_wrong_password_and_unknown_email_are_refused_identically(app, world):
    wrong = refused(sign_in(app, world["users"]["admin"]["email"], "Wrong-Password-9"), 401, "unauthorized")
    unknown = refused(sign_in(app, "nobody@zeroentry.example"), 401, "unauthorized")
    assert wrong == unknown                                                  # no account enumeration


def test_repeated_failures_lock_the_account_even_against_the_right_password(app, world, conn, api):
    email = world["users"]["auditor"]["email"]
    for _ in range(3):
        refused(sign_in(app, email, "Wrong-Password-9"), 401)
    refused(sign_in(app, email), 401)                                        # correct password, but locked
    assert conn.execute("SELECT locked_until > now() AS locked FROM app_user WHERE email = %s", (email,)).fetchone()["locked"]
    ok(api("admin").patch(f"{API}/admin/users/{world['users']['auditor']['id']}", json={"unlock": True}))
    ok(sign_in(app, email))


def test_a_success_resets_the_failure_counter(app, world, conn):
    email = world["users"]["auditor"]["email"]
    refused(sign_in(app, email, "Wrong-Password-9"), 401)
    refused(sign_in(app, email, "Wrong-Password-9"), 401)
    ok(sign_in(app, email))
    assert conn.execute("SELECT failed_logins FROM app_user WHERE email = %s", (email,)).fetchone()["failed_logins"] == 0


def test_a_deactivated_user_cannot_sign_in_and_loses_live_sessions(app, world, api):
    uid = world["users"]["auditor"]["id"]
    auditor = api("auditor")
    ok(auditor.get(f"{API}/auth/me"))
    ok(api("admin").patch(f"{API}/admin/users/{uid}", json={"is_active": False}))
    refused(auditor.get(f"{API}/auth/me"), 401)
    refused(sign_in(app, world["users"]["auditor"]["email"]), 401)


def test_unauthenticated_and_forged_credentials_are_401(app):
    c = TestClient(app, raise_server_exceptions=False)
    refused(c.get(f"{API}/auth/me"), 401)
    c.cookies.set("ze_session", "not-a-real-token")
    refused(c.get(f"{API}/auth/me"), 401)
    refused(TestClient(app, raise_server_exceptions=False).get(f"{API}/auth/me", headers={"Authorization": "Bearer forged"}), 401)


def test_bearer_tokens_need_no_csrf_but_cookie_writes_do(app, world):
    admin = world["users"]["engineer"]["email"]
    login_body = ok(sign_in(app, admin))
    payload = {"manhole_id": world["manhole"], "description": "Overflow outside the school gate"}

    bearer = TestClient(app, raise_server_exceptions=False)                    # no cookie jar, no CSRF header
    ok(bearer.post(f"{API}/complaints", json=payload, headers={"Authorization": f"Bearer {login_body['session_token']}"}), 201)

    cookie_client = TestClient(app, raise_server_exceptions=False)
    cookie_client.post(f"{API}/auth/login", json={"email": admin, "password": PASSWORD})
    refused(cookie_client.post(f"{API}/complaints", json=payload), 403, "csrf")                              # missing header
    refused(cookie_client.post(f"{API}/complaints", json=payload, headers={"X-CSRF-Token": "wrong"}), 403, "csrf")
    csrf = cookie_client.get(f"{API}/auth/me").json()["csrf_token"]
    refused(cookie_client.post(f"{API}/complaints", json=payload, headers={"X-CSRF-Token": csrf, "Origin": "http://evil.example"}),
            403, "csrf")                                                                                     # cross-origin
    ok(cookie_client.post(f"{API}/complaints", json=payload, headers={"X-CSRF-Token": csrf}), 201)
    ok(cookie_client.get(f"{API}/complaints"))                                                               # reads need no token


def test_logout_revokes_the_session_on_the_server(app, world, conn):
    email = world["users"]["engineer"]["email"]
    response = sign_in(app, email)
    token = response.json()["session_token"]
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set("ze_session", token)
    csrf = response.json()["csrf_token"]
    ok(client.post(f"{API}/auth/logout", headers={"X-CSRF-Token": csrf}))
    assert conn.execute("SELECT revoked_at IS NOT NULL AS revoked FROM user_session").fetchone()["revoked"]
    refused(client.get(f"{API}/auth/me"), 401)                                                              # cookie replay
    refused(TestClient(app, raise_server_exceptions=False).get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}), 401)


def test_an_expired_session_is_refused(world, conn, api):
    admin = api("admin")
    ok(admin.get(f"{API}/auth/me"))
    conn.execute("UPDATE user_session SET created_at = now() - interval '2 hours', expires_at = now() - interval '1 minute'")
    refused(admin.get(f"{API}/auth/me"), 401)


def test_me_reports_the_server_side_identity(api, world):
    me = ok(api("contractor_a").get(f"{API}/auth/me"))
    assert me["user"]["role"] == "CONTRACTOR" and me["user"]["contractor_id"] == world["ca"] and me["csrf_token"]


def test_change_password_validates_revokes_other_sessions_and_takes_effect(app, world, api):
    email = world["users"]["supervisor"]["email"]
    first, second = api("supervisor"), login(app, email)
    refused(first.post(f"{API}/auth/change-password", json={"current_password": "Wrong-Password-9", "new_password": "New-Password-123"}), 422)
    refused(first.post(f"{API}/auth/change-password", json={"current_password": PASSWORD, "new_password": "short"}), 422, message="12 characters")
    ok(first.post(f"{API}/auth/change-password", json={"current_password": PASSWORD, "new_password": "New-Password-123"}))
    ok(first.get(f"{API}/auth/me"))                                          # the session that changed it survives
    refused(second.get(f"{API}/auth/me"), 401)                               # every other one is gone
    refused(sign_in(app, email, PASSWORD), 401)
    ok(sign_in(app, email, "New-Password-123"))


def test_login_is_throttled_per_address(make_app, world):
    app = make_app(login_ip_limit=3, login_max_failures=20)
    attempts = [sign_in(app, "nobody@zeroentry.example").status_code for _ in range(5)]
    assert attempts == [401, 401, 401, 429, 429]
    refused(sign_in(app, "nobody@zeroentry.example"), 429, "rate_limited")


def test_security_headers_are_set_and_docs_are_hidden_in_production(make_app):
    headers = TestClient(make_app()).get("/health").headers
    assert headers["x-content-type-options"] == "nosniff" and headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in headers["content-security-policy"] and headers["cache-control"] == "no-store"
    production = TestClient(make_app(app_env="production", cookie_secure=True))
    assert production.get("/docs").status_code == 404 and production.get("/openapi.json").status_code == 404


def test_the_session_cookie_is_marked_secure_when_configured(make_app, world):
    app = make_app(cookie_secure=True)
    response = TestClient(app, base_url="https://testserver").post(
        f"{API}/auth/login", json={"email": world["users"]["admin"]["email"], "password": PASSWORD})
    assert "secure" in response.headers["set-cookie"].lower()
