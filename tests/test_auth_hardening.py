"""JWT secret defaults and one-time admin bootstrap."""
import sqlite3
import stat
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import JWTError, jwt

from server import config as config_mod
from server.api.admin import router as admin_router
from server.api.auth import pwd_ctx, router as auth_router
from server.config import (
    PUBLIC_INSECURE_SECRET_KEYS,
    SecretKeyError,
    Settings,
    get_settings,
    resolve_secret_key,
)
from server.db import sqlite as sqlite_mod
from server.deps import PASSWORD_CHANGE_REQUIRED, get_current_user

PUBLIC_SECRET = "tender-secret-key-change-in-production"
CONFIGURED_SECRET = "configured-signing-secret-0123456789abcdef"
ROOT = Path(__file__).resolve().parents[1]


def _password_from_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    return ""


def _admin():
    conn = sqlite_mod.get_db()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, role, must_change_password "
            "FROM users WHERE username = ?",
            (sqlite_mod.BOOTSTRAP_ADMIN_USERNAME,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _config_value(key: str):
    conn = sqlite_mod.get_db()
    try:
        row = conn.execute(
            "SELECT value FROM configs WHERE key = ?",
            (key,),
        ).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def _use_db(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sqlite_mod, "DB_PATH", tmp_path / "tender.db")
    monkeypatch.setattr(sqlite_mod, "DATA_DIR", tmp_path)


@pytest.fixture
def clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_public_placeholder_is_rejected_constant():
    assert PUBLIC_SECRET in PUBLIC_INSECURE_SECRET_KEYS


def test_configured_secret_is_used_for_signing(monkeypatch, clear_settings):
    monkeypatch.setenv("SECRET_KEY", CONFIGURED_SECRET)
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("APP_ENV", "production")

    from server.api.auth import create_token

    settings = get_settings()
    assert settings.SECRET_KEY == CONFIGURED_SECRET
    assert settings.SECRET_KEY not in PUBLIC_INSECURE_SECRET_KEYS

    token = create_token({"sub": "7"})
    decoded = jwt.decode(token, CONFIGURED_SECRET, algorithms=[settings.ALGORITHM])
    assert decoded["sub"] == "7"
    with pytest.raises(JWTError):
        jwt.decode(token, PUBLIC_SECRET, algorithms=["HS256"])


def test_public_placeholder_is_not_the_dev_signing_key(tmp_path):
    settings = Settings(
        SECRET_KEY=PUBLIC_SECRET,
        DEBUG=True,
        APP_ENV="development",
    )
    resolved = resolve_secret_key(settings, data_dir=tmp_path)
    assert resolved != PUBLIC_SECRET
    assert resolved not in PUBLIC_INSECURE_SECRET_KEYS
    token = jwt.encode(
        {"sub": "1", "exp": datetime.utcnow() + timedelta(minutes=5)},
        resolved,
        algorithm="HS256",
    )
    with pytest.raises(JWTError):
        jwt.decode(token, PUBLIC_SECRET, algorithms=["HS256"])
    stored = (tmp_path / config_mod.DEV_SECRET_FILENAME).read_text(encoding="utf-8")
    assert stored.strip() == resolved
    mode = (tmp_path / config_mod.DEV_SECRET_FILENAME).stat().st_mode & 0o777
    assert mode == stat.S_IRUSR | stat.S_IWUSR


def test_dev_secret_stays_stable_across_restarts(tmp_path):
    settings = Settings(SECRET_KEY="", DEBUG=True, APP_ENV="development")
    first = resolve_secret_key(settings, data_dir=tmp_path)
    second = resolve_secret_key(settings, data_dir=tmp_path)
    assert first == second
    assert first != PUBLIC_SECRET


def test_explicit_secret_beats_dev_file(tmp_path):
    dev_file = tmp_path / config_mod.DEV_SECRET_FILENAME
    dev_file.write_text("d" * 48, encoding="utf-8")
    settings = Settings(
        SECRET_KEY=CONFIGURED_SECRET,
        DEBUG=True,
        APP_ENV="development",
    )
    assert resolve_secret_key(settings, data_dir=tmp_path) == CONFIGURED_SECRET


def test_production_without_secret_refuses_to_start(monkeypatch, tmp_path, clear_settings):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path)

    with pytest.raises(SecretKeyError) as exc:
        get_settings()
    assert "SECRET_KEY" in str(exc.value)
    assert not (tmp_path / config_mod.DEV_SECRET_FILENAME).exists()


def test_production_rejects_public_placeholder(tmp_path):
    settings = Settings(SECRET_KEY=PUBLIC_SECRET, DEBUG=False, APP_ENV="development")
    with pytest.raises(SecretKeyError):
        resolve_secret_key(settings, data_dir=tmp_path)
    assert not (tmp_path / config_mod.DEV_SECRET_FILENAME).exists()


def test_app_env_production_requires_secret_even_if_debug(tmp_path):
    settings = Settings(SECRET_KEY="", DEBUG=True, APP_ENV="production")
    with pytest.raises(SecretKeyError):
        resolve_secret_key(settings, data_dir=tmp_path)


def test_get_settings_dev_does_not_sign_with_public_default(
    monkeypatch, tmp_path, clear_settings
):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path)

    from server.api.auth import create_token

    settings = get_settings()
    assert settings.SECRET_KEY not in PUBLIC_INSECURE_SECRET_KEYS
    token = create_token({"sub": "3"})
    jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    with pytest.raises(JWTError):
        jwt.decode(token, PUBLIC_SECRET, algorithms=["HS256"])


def test_fresh_bootstrap_is_once_and_not_recreated(monkeypatch, tmp_path, capsys):
    _use_db(monkeypatch, tmp_path)
    sqlite_mod.init_db()
    first_log = capsys.readouterr().out

    password_file = tmp_path / sqlite_mod.INITIAL_PASSWORD_FILENAME
    password = _password_from_file(password_file)
    assert password
    assert password != PUBLIC_SECRET
    assert password != sqlite_mod.LEGACY_ADMIN_PASSWORD
    assert password in first_log
    assert first_log.count(password) == 1
    mode = password_file.stat().st_mode & 0o777
    assert mode == stat.S_IRUSR | stat.S_IWUSR

    admin = _admin()
    assert admin["username"] == "admin"
    assert admin["role"] == "admin"
    assert admin["must_change_password"] == 1
    assert pwd_ctx.verify(password, admin["password_hash"])
    assert not pwd_ctx.verify(sqlite_mod.LEGACY_ADMIN_PASSWORD, admin["password_hash"])
    assert _config_value(sqlite_mod.BOOTSTRAP_DONE_KEY) == "1"
    original_hash = admin["password_hash"]

    sqlite_mod.init_db()
    second_log = capsys.readouterr().out
    assert password not in second_log
    again = _admin()
    assert again["password_hash"] == original_hash
    assert _password_from_file(password_file) == password

    conn = sqlite_mod.get_db()
    try:
        conn.execute("DELETE FROM users WHERE username = ?", ("admin",))
        conn.commit()
    finally:
        conn.close()

    sqlite_mod.init_db()
    assert _admin() is None
    assert _config_value(sqlite_mod.BOOTSTRAP_DONE_KEY) == "1"
    assert _password_from_file(password_file) == password


def _seed_user(path: Path, username: str, password: str, role: str = "admin") -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username, pwd_ctx.hash(password), role),
    )
    conn.commit()
    conn.close()


def test_existing_legacy_admin_must_change_without_reset(monkeypatch, tmp_path, capsys):
    _use_db(monkeypatch, tmp_path)
    db_path = tmp_path / "tender.db"
    _seed_user(db_path, "admin", sqlite_mod.LEGACY_ADMIN_PASSWORD)
    sqlite_mod.init_db()
    log = capsys.readouterr().out

    admin = _admin()
    assert admin["must_change_password"] == 1
    assert pwd_ctx.verify(sqlite_mod.LEGACY_ADMIN_PASSWORD, admin["password_hash"])
    assert not (tmp_path / sqlite_mod.INITIAL_PASSWORD_FILENAME).exists()
    assert sqlite_mod.LEGACY_ADMIN_PASSWORD not in log
    assert _config_value(sqlite_mod.BOOTSTRAP_DONE_KEY) == "1"

    conn = sqlite_mod.get_db()
    try:
        conn.execute("DELETE FROM users")
        conn.commit()
    finally:
        conn.close()
    sqlite_mod.init_db()
    assert _admin() is None


def test_existing_custom_admin_is_left_alone(monkeypatch, tmp_path, capsys):
    _use_db(monkeypatch, tmp_path)
    _seed_user(tmp_path / "tender.db", "admin", "custom-pass-999")
    sqlite_mod.init_db()
    capsys.readouterr()

    admin = _admin()
    assert admin["must_change_password"] == 0
    assert pwd_ctx.verify("custom-pass-999", admin["password_hash"])
    assert not (tmp_path / sqlite_mod.INITIAL_PASSWORD_FILENAME).exists()


def test_existing_non_admin_does_not_grow_a_bootstrap_admin(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    _seed_user(tmp_path / "tender.db", "bob", "bob-pass-999", role="user")
    sqlite_mod.init_db()
    assert _admin() is None
    assert _config_value(sqlite_mod.BOOTSTRAP_DONE_KEY) == "1"


def _mini_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(admin_router)

    @app.get("/protected")
    def protected(_user: dict = Depends(get_current_user)):
        return {"ok": True}

    return app


def test_forged_legacy_token_fails_and_bootstrap_forces_change(
    monkeypatch, tmp_path, clear_settings
):
    secret = "real-install-secret-0123456789abcdefEXTRA"
    monkeypatch.setenv("SECRET_KEY", secret)
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("APP_ENV", "production")
    _use_db(monkeypatch, tmp_path)
    sqlite_mod.init_db()

    password_file = tmp_path / sqlite_mod.INITIAL_PASSWORD_FILENAME
    password = _password_from_file(password_file)
    admin = _admin()
    forged = jwt.encode(
        {"sub": str(admin["id"]), "exp": datetime.utcnow() + timedelta(hours=1)},
        PUBLIC_SECRET,
        algorithm="HS256",
    )

    with TestClient(_mini_app()) as client:
        rejected = client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert rejected.status_code == 401

        bad_login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": sqlite_mod.LEGACY_ADMIN_PASSWORD},
        )
        assert bad_login.status_code == 401

        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": password},
        )
        assert login.status_code == 200, login.text
        body = login.json()
        assert body["must_change_password"] is True
        assert body["user"]["must_change_password"] is True
        token = body["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        decoded = jwt.decode(token, secret, algorithms=["HS256"])
        assert decoded["sub"] == str(admin["id"])
        with pytest.raises(JWTError):
            jwt.decode(token, PUBLIC_SECRET, algorithms=["HS256"])

        me = client.get("/api/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["must_change_password"] is True

        blocked = client.get("/protected", headers=headers)
        assert blocked.status_code == 403
        assert blocked.json()["detail"] == PASSWORD_CHANGE_REQUIRED

        admin_blocked = client.get("/api/admin/users", headers=headers)
        assert admin_blocked.status_code == 403

        logout = client.post("/api/auth/logout", headers=headers)
        assert logout.status_code == 200

        same = client.post(
            "/api/auth/change-password",
            headers=headers,
            json={"old_password": password, "new_password": password},
        )
        assert same.status_code == 400

        legacy = client.post(
            "/api/auth/change-password",
            headers=headers,
            json={
                "old_password": password,
                "new_password": sqlite_mod.LEGACY_ADMIN_PASSWORD,
            },
        )
        assert legacy.status_code == 400

        wrong = client.post(
            "/api/auth/change-password",
            headers=headers,
            json={"old_password": "not-the-password", "new_password": "replacement-pass-1"},
        )
        assert wrong.status_code == 400

        changed = client.post(
            "/api/auth/change-password",
            headers=headers,
            json={"old_password": password, "new_password": "replacement-pass-1"},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["must_change_password"] is False
        assert not password_file.exists()

        assert client.get("/protected", headers=headers).status_code == 200
        users = client.get("/api/admin/users", headers=headers)
        assert users.status_code == 200
        assert any(row["username"] == "admin" for row in users.json())

        public_password = client.post(
            "/api/admin/users",
            headers=headers,
            json={"username": "other", "password": sqlite_mod.LEGACY_ADMIN_PASSWORD, "role": "user"},
        )
        assert public_password.status_code == 400

        old_login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": password},
        )
        assert old_login.status_code == 401

        new_login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "replacement-pass-1"},
        )
        assert new_login.status_code == 200
        assert new_login.json()["must_change_password"] is False

        forged_again = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {forged}"},
        )
        assert forged_again.status_code == 401


def test_login_ui_has_no_hardcoded_credentials():
    text = (ROOT / "web/src/pages/Login.vue").read_text(encoding="utf-8")
    assert "admin123" not in text
    assert "默认账号" not in text


def test_secret_files_are_gitignored():
    for rel in ("data/.secret_key", "data/initial_admin_password.txt"):
        result = subprocess.run(
            ["git", "check-ignore", "-q", rel],
            cwd=ROOT,
            check=False,
        )
        assert result.returncode == 0, rel


def test_env_example_does_not_publish_a_secret():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        assert PUBLIC_SECRET not in stripped
        assert "admin123" not in stripped
        assert not stripped.startswith("SECRET_KEY=") or stripped == "SECRET_KEY="
