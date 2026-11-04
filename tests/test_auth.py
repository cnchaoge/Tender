"""Logged-in user required on API routes; admin role required on /api/admin."""
import re
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from server.api.auth import pwd_ctx
from server.config import get_settings
from server.db.sqlite import get_db
from server.main import app

USER_NAME = "zz_auth_user"
ADMIN_NAME = "zz_auth_admin"
GHOST_NAME = "zz_auth_ghost"
PASSWORD = "test-pass-123"

# Endpoints a normal signed-in user must still be able to call.
USER_OK_PATHS = (
    "/api/kb/documents",
    "/api/bid/templates",
    "/api/bid/disqualify_rules",
    "/api/checklist/categories",
    "/api/price/formula-templates",
)


def _upsert(username: str, password: str, role: str) -> int:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        password_hash = pwd_ctx.hash(password)
        if row:
            cur.execute(
                "UPDATE users SET password_hash = ?, role = ? WHERE id = ?",
                (password_hash, role, row["id"]),
            )
            user_id = int(row["id"])
        else:
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, role),
            )
            user_id = int(cur.lastrowid)
        conn.commit()
        return user_id
    finally:
        conn.close()


def _delete(user_id: int) -> None:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


def _api_operations():
    seen = set()
    for route in app.routes:
        path = getattr(route, "path", "") or ""
        methods = getattr(route, "methods", None) or set()
        if not path.startswith("/api/"):
            continue
        for method in sorted(methods):
            if method in {"HEAD", "OPTIONS"}:
                continue
            key = (method, path)
            if key in seen:
                continue
            seen.add(key)
            yield method, path


def _login(client: TestClient, username: str) -> str:
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["username"] == username
    return body["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def auth_env():
    with TestClient(app) as client:
        user_id = _upsert(USER_NAME, PASSWORD, "user")
        admin_id = _upsert(ADMIN_NAME, PASSWORD, "admin")
        try:
            yield {
                "client": client,
                "user_id": user_id,
                "admin_id": admin_id,
                "user_token": _login(client, USER_NAME),
                "admin_token": _login(client, ADMIN_NAME),
            }
        finally:
            _delete(user_id)
            _delete(admin_id)


def test_health_and_login_stay_public(auth_env):
    client = auth_env["client"]
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    # Login is public. A bad password is 401 from the credential check itself.
    bad = client.post(
        "/api/auth/login",
        json={"username": "nobody-zz", "password": "nope"},
    )
    assert bad.status_code == 401

    missing = client.post("/api/auth/login", json={})
    assert missing.status_code == 422


def test_unauthenticated_api_routes_return_401(auth_env):
    client = auth_env["client"]
    checked = 0
    for method, path in _api_operations():
        if method == "POST" and path == "/api/auth/login":
            continue
        resp = client.request(method, _concrete(path))
        assert resp.status_code == 401, f"{method} {path} -> {resp.status_code} {resp.text}"
        assert resp.headers.get("www-authenticate", "").lower().startswith("bearer")
        checked += 1
    # Guards against the walker silently matching nothing.
    assert checked >= 20


def test_invalid_and_expired_token_return_401(auth_env):
    client = auth_env["client"]
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert resp.status_code == 401

    settings = get_settings()
    expired = jwt.encode(
        {
            "sub": str(auth_env["user_id"]),
            "exp": datetime.utcnow() - timedelta(minutes=5),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    resp = client.get("/api/kb/documents", headers=_auth(expired))
    assert resp.status_code == 401

    no_sub = jwt.encode(
        {"exp": datetime.utcnow() + timedelta(minutes=5)},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    resp = client.get("/api/bid/templates", headers=_auth(no_sub))
    assert resp.status_code == 401


def test_deleted_user_token_returns_401(auth_env):
    client = auth_env["client"]
    ghost_id = _upsert(GHOST_NAME, PASSWORD, "user")
    try:
        token = _login(client, GHOST_NAME)
    finally:
        _delete(ghost_id)
    resp = client.get("/api/auth/me", headers=_auth(token))
    assert resp.status_code == 401


def test_logged_in_user_can_call_non_admin_routes(auth_env):
    client = auth_env["client"]
    headers = _auth(auth_env["user_token"])

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"] == USER_NAME
    assert me.json()["role"] == "user"

    logout = client.post("/api/auth/logout", headers=headers)
    assert logout.status_code == 200

    for path in USER_OK_PATHS:
        resp = client.get(path, headers=headers)
        assert resp.status_code == 200, f"{path} -> {resp.status_code} {resp.text}"

    # Auth is enforced before body validation.
    assert client.post("/api/rag/query").status_code == 401
    authed = client.post("/api/rag/query", headers=headers)
    assert authed.status_code not in (401, 403)


def test_non_admin_gets_403_on_every_admin_route(auth_env):
    client = auth_env["client"]
    headers = _auth(auth_env["user_token"])
    checked = 0
    for method, path in _api_operations():
        if not path.startswith("/api/admin"):
            continue
        resp = client.request(method, _concrete(path), headers=headers)
        assert resp.status_code == 403, f"{method} {path} -> {resp.status_code} {resp.text}"
        checked += 1
    assert checked >= 5


def test_admin_can_read_management_routes(auth_env):
    client = auth_env["client"]
    headers = _auth(auth_env["admin_token"])

    users = client.get("/api/admin/users", headers=headers)
    assert users.status_code == 200
    names = {row["username"] for row in users.json()}
    assert ADMIN_NAME in names
    assert USER_NAME in names

    config = client.get("/api/admin/config", headers=headers)
    assert config.status_code == 200
    assert "llm_provider" in config.json()

    stats = client.get("/api/admin/stats", headers=headers)
    assert stats.status_code == 200
    assert "document_count" in stats.json()

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["role"] == "admin"
