"""PUT /api/admin/config persists settings and GET reflects them."""
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.api.auth import pwd_ctx
from server.config import get_settings
from server.db.sqlite import get_db
from server.main import app

USER_NAME = "zz_cfg_user"
ADMIN_NAME = "zz_cfg_admin"
PASSWORD = "test-pass-123"
SECRET = "sk-test#fragment"

# Every key the config update is allowed to write. Restored after each test
# so a saved value cannot leak into later tests.
_ENV_KEYS = (
    "LLM_PROVIDER",
    "EMBED_PROVIDER",
    "OLLAMA_MODEL",
    "OLLAMA_EMBED_MODEL",
    "DASHSCOPE_MODEL",
    "DASHSCOPE_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_API_KEY",
    "MINIMAX_MODEL",
    "MINIMAX_API_KEY",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_API_KEY",
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
                "UPDATE users SET password_hash = ?, role = ?, must_change_password = 0 WHERE id = ?",
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


def _login(client: TestClient, username: str) -> str:
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def accounts():
    with TestClient(app) as client:
        user_id = _upsert(USER_NAME, PASSWORD, "user")
        admin_id = _upsert(ADMIN_NAME, PASSWORD, "admin")
        try:
            yield {
                "client": client,
                "user_token": _login(client, USER_NAME),
                "admin_token": _login(client, ADMIN_NAME),
            }
        finally:
            _delete(user_id)
            _delete(admin_id)


@pytest.fixture
def config_home(tmp_path, monkeypatch):
    """Point .env writes at a temp dir and restore process env afterwards."""
    import server.config as config_mod

    monkeypatch.setattr(config_mod, "BASE_DIR", tmp_path)
    saved = {key: os.environ.get(key) for key in _ENV_KEYS}
    secret_before = os.environ.get("SECRET_KEY")
    get_settings.cache_clear()
    try:
        yield tmp_path
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if secret_before is None:
            # The handler must not create SECRET_KEY. Drop it if a test did.
            if os.environ.get("SECRET_KEY") != secret_before:
                os.environ.pop("SECRET_KEY", None)
        get_settings.cache_clear()


def _put(accounts, payload: dict):
    return accounts["client"].put(
        "/api/admin/config",
        headers=_auth(accounts["admin_token"]),
        json=payload,
    )


def _get(accounts) -> dict:
    resp = accounts["client"].get(
        "/api/admin/config",
        headers=_auth(accounts["admin_token"]),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_settings_page_saves_with_put():
    text = Path("web/src/pages/Settings.vue").read_text(encoding="utf-8")
    assert text.count('api.put("/api/admin/config"') == 2
    assert 'api.put("/api/admin/config"' in text
    # Model and embedding saves both use the unified endpoint.
    assert '"/api/admin/model/config"' not in text
    assert '"/api/admin/embed/config"' not in text


def test_put_requires_auth(accounts, config_home):
    resp = accounts["client"].put("/api/admin/config", json={"provider": "mock"})
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate", "").lower().startswith("bearer")
    assert not (config_home / ".env").exists()


def test_non_admin_cannot_update_config(accounts, config_home):
    resp = accounts["client"].put(
        "/api/admin/config",
        headers=_auth(accounts["user_token"]),
        json={"provider": "mock", "api_key": SECRET},
    )
    assert resp.status_code == 403
    assert SECRET not in resp.text
    assert not (config_home / ".env").exists()


def test_admin_put_round_trip_matches_settings_payloads(accounts, config_home):
    # Exact body saveModel() sends.
    model_save = _put(accounts, {
        "provider": "ollama",
        "api_key": "",
        "model": "qwen3:4b",
        "embed_provider": "mock",
    })
    assert model_save.status_code == 200, model_save.text
    got = _get(accounts)
    assert got["llm_provider"] == "ollama"
    assert got["ollama_model"] == "qwen3:4b"
    assert got["embed_provider"] == "mock"
    assert SECRET not in json.dumps(got)

    # Exact body saveEmbed() sends. Must not clobber the model provider.
    embed_save = _put(accounts, {
        "embed_provider": "ollama",
        "ollama_embed_model": "bge-m3",
    })
    assert embed_save.status_code == 200, embed_save.text
    got = _get(accounts)
    assert got["llm_provider"] == "ollama"
    assert got["ollama_model"] == "qwen3:4b"
    assert got["embed_provider"] == "ollama"
    assert got["ollama_embed_model"] == "bge-m3"

    env_text = (config_home / ".env").read_text(encoding="utf-8")
    assert "LLM_PROVIDER=ollama" in env_text
    assert "OLLAMA_MODEL=qwen3:4b" in env_text
    assert "OLLAMA_EMBED_MODEL=bge-m3" in env_text
    assert "EMBED_PROVIDER=ollama" in env_text


def test_get_field_names_and_preexisting_env_are_updated(accounts, config_home, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("EMBED_PROVIDER", "ollama")
    get_settings.cache_clear()

    saved = _put(accounts, {
        "llm_provider": "mock",
        "ollama_model": "qwen-test:1b",
        "embed_provider": "mock",
        "ollama_embed_model": "nomic-embed-text",
        "dashscope_api_key_set": True,
        "SECRET_KEY": "attacker-controlled-secret",
        "secret_key": "attacker-controlled-secret",
    })
    assert saved.status_code == 200, saved.text

    got = _get(accounts)
    assert got["llm_provider"] == "mock"
    assert got["ollama_model"] == "qwen-test:1b"
    assert got["embed_provider"] == "mock"
    assert got["ollama_embed_model"] == "nomic-embed-text"
    assert "attacker-controlled-secret" not in json.dumps(got)

    env_text = (config_home / ".env").read_text(encoding="utf-8")
    assert "attacker-controlled-secret" not in env_text
    assert "SECRET_KEY" not in env_text

    # Drop the process env so the follow-up read has to come from the file.
    os.environ.pop("LLM_PROVIDER", None)
    os.environ.pop("OLLAMA_MODEL", None)
    os.environ.pop("EMBED_PROVIDER", None)
    os.environ.pop("OLLAMA_EMBED_MODEL", None)
    get_settings.cache_clear()
    reloaded = get_settings()
    assert reloaded.LLM_PROVIDER == "mock"
    assert reloaded.OLLAMA_MODEL == "qwen-test:1b"
    assert reloaded.EMBED_PROVIDER == "mock"
    assert reloaded.OLLAMA_EMBED_MODEL == "nomic-embed-text"
    assert reloaded.SECRET_KEY != "attacker-controlled-secret"


def test_api_key_is_stored_but_not_returned(accounts, config_home):
    saved = _put(accounts, {
        "provider": "deepseek",
        "api_key": SECRET,
        "model": "deepseek-chat",
        "embed_provider": "mock",
    })
    assert saved.status_code == 200, saved.text
    assert SECRET not in saved.text

    got = _get(accounts)
    assert got["llm_provider"] == "deepseek"
    assert got["deepseek_model"] == "deepseek-chat"
    assert got["embed_provider"] == "mock"
    assert got["deepseek_api_key_set"] is True
    assert SECRET not in json.dumps(got)

    # A later save that leaves the key blank must not wipe it. The form
    # always sends api_key, and GET never gives the page the current key.
    blank = _put(accounts, {
        "provider": "deepseek",
        "api_key": "",
        "model": "deepseek-coder",
        "embed_provider": "mock",
    })
    assert blank.status_code == 200, blank.text
    got = _get(accounts)
    assert got["deepseek_model"] == "deepseek-coder"
    assert got["deepseek_api_key_set"] is True
    assert SECRET not in json.dumps(got)

    os.environ.pop("DEEPSEEK_API_KEY", None)
    os.environ.pop("DEEPSEEK_MODEL", None)
    get_settings.cache_clear()
    reloaded = get_settings()
    assert reloaded.DEEPSEEK_API_KEY == SECRET
    assert reloaded.DEEPSEEK_MODEL == "deepseek-coder"

    env_text = (config_home / ".env").read_text(encoding="utf-8")
    assert 'DEEPSEEK_API_KEY="sk-test#fragment"' in env_text
    assert "DEEPSEEK_MODEL=deepseek-coder" in env_text


def test_invalid_values_do_not_persist(accounts, config_home):
    first = _put(accounts, {"provider": "mock", "embed_provider": "mock"})
    assert first.status_code == 200, first.text

    unknown = _put(accounts, {"provider": "not-a-provider"})
    assert unknown.status_code == 400
    assert _get(accounts)["llm_provider"] == "mock"

    mismatch = _put(accounts, {"provider": "ollama", "llm_provider": "mock"})
    assert mismatch.status_code == 400
    assert _get(accounts)["llm_provider"] == "mock"

    conflict = _put(accounts, {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "deepseek_model": "deepseek-reasoner",
    })
    assert conflict.status_code == 400
    assert _get(accounts)["llm_provider"] == "mock"

    leaked = _put(accounts, {
        "provider": "deepseek",
        "api_key": "sk-leak-me\nLLM_PROVIDER=mock",
    })
    assert leaked.status_code == 400
    assert "sk-leak-me" not in leaked.text
    assert _get(accounts)["llm_provider"] == "mock"

    bad_type = _put(accounts, {"provider": ["nope"]})
    assert bad_type.status_code == 422
    assert _get(accounts)["llm_provider"] == "mock"

    empty = _put(accounts, {})
    assert empty.status_code == 200
    assert empty.json()["message"] == "没有需要更新的配置"


def test_existing_post_save_endpoints_still_persist(accounts, config_home):
    headers = _auth(accounts["admin_token"])
    model = accounts["client"].post(
        "/api/admin/model/config",
        headers=headers,
        json={"provider": "ollama", "api_key": "", "model": "qwen3:4b"},
    )
    assert model.status_code == 200, model.text
    got = _get(accounts)
    assert got["llm_provider"] == "ollama"
    assert got["ollama_model"] == "qwen3:4b"

    embed = accounts["client"].post(
        "/api/admin/embed/config",
        headers=headers,
        json={"embed_provider": "m3e", "ollama_embed_model": "bge-m3"},
    )
    assert embed.status_code == 200, embed.text
    got = _get(accounts)
    assert got["llm_provider"] == "ollama"
    assert got["ollama_model"] == "qwen3:4b"
    assert got["embed_provider"] == "m3e"
    assert got["ollama_embed_model"] == "bge-m3"


def test_explicit_provider_key_round_trip(accounts, config_home):
    saved = _put(accounts, {
        "llm_provider": "openai",
        "openai_model": "gpt-4o-mini",
        "openai_api_key": "sk-openai-test-value",
        "embed_provider": "bge",
    })
    assert saved.status_code == 200, saved.text
    assert "sk-openai-test-value" not in saved.text
    got = _get(accounts)
    assert got["llm_provider"] == "openai"
    assert got["openai_model"] == "gpt-4o-mini"
    assert got["openai_api_key_set"] is True
    assert got["embed_provider"] == "bge"
    assert "sk-openai-test-value" not in json.dumps(got)
