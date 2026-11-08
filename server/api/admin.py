"""
Tender - 管理后台 API（统一配置 + 用户管理）
"""
import os
import sys
import subprocess
import threading
import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from passlib.context import CryptContext
from server.db.sqlite import LEGACY_ADMIN_PASSWORD, get_db
from server.config import get_settings, update_env, update_env_many
from server.deps import require_admin

# ============ 热重启 ============
def _do_restart():
    """用辅助脚本启动新进程，辅助脚本会延迟等旧进程释放端口后再启动"""
    python = sys.executable
    settings = get_settings()
    helper = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "restart_helper.py")
    try:
        subprocess.Popen(
            [python, helper, "3", settings.HOST, str(settings.PORT)],
        )
    except Exception as e:
        print(f"[Restart] 启动辅助脚本失败: {e}")
    os._exit(0)

def restart_server_async():
    """在后台线程执行重启"""
    t = threading.Thread(target=_do_restart, daemon=True)
    t.start()
from server.models import Resp

router = APIRouter(prefix="/api/admin", tags=["管理后台"], dependencies=[Depends(require_admin)])
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()


# ============ 请求/响应模型 ============

class ModelConfigReq(BaseModel):
    provider: str = "dashscope"  # dashscope | deepseek | ollama
    api_key: str = ""
    model: str = ""
    embed_provider: str = ""  # dashscope | bge | m3e | ollama | mock
    ollama_embed_model: str = ""  # bge-m3 | nomic-embed-text


class ModelConfigResp(BaseModel):
    valid: bool
    message: str


class SystemConfig(BaseModel):
    """System config (no sensitive info)"""
    llm_provider: str
    ollama_model: str
    ollama_embed_model: str
    dashscope_model: str
    deepseek_model: str
    openai_model: str
    minimax_model: str
    embed_provider: str
    dashscope_api_key_set: bool  # whether configured (no actual key)
    deepseek_api_key_set: bool
    openai_api_key_set: bool
    minimax_api_key_set: bool


# Settings form field names, plus the GET field names, so either shape can be saved.
_LLM_PROVIDERS = frozenset({
    "ollama", "dashscope", "openai", "minimax", "deepseek", "mock",
})
_EMBED_PROVIDERS = frozenset({"ollama", "dashscope", "bge", "m3e", "mock"})
_MODEL_ENV_BY_PROVIDER = {
    "ollama": "OLLAMA_MODEL",
    "dashscope": "DASHSCOPE_MODEL",
    "openai": "OPENAI_MODEL",
    "minimax": "MINIMAX_MODEL",
    "deepseek": "DEEPSEEK_MODEL",
}
_KEY_ENV_BY_PROVIDER = {
    "dashscope": "DASHSCOPE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}
_EXPLICIT_MODEL_FIELDS = {
    "ollama_model": "OLLAMA_MODEL",
    "dashscope_model": "DASHSCOPE_MODEL",
    "openai_model": "OPENAI_MODEL",
    "minimax_model": "MINIMAX_MODEL",
    "deepseek_model": "DEEPSEEK_MODEL",
}
_EXPLICIT_KEY_FIELDS = {
    "dashscope_api_key": "DASHSCOPE_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "minimax_api_key": "MINIMAX_API_KEY",
    "deepseek_api_key": "DEEPSEEK_API_KEY",
}


class SystemConfigUpdate(BaseModel):
    """Partial config update.

    Accepts the settings form payload (`provider`, `api_key`, `model`,
    `embed_provider`, `ollama_embed_model`) and the GET /config field names.
    Blank API keys are left unchanged: GET never returns the key, so an empty
    form field means "not editing the secret", not "clear it".
    """

    model_config = ConfigDict(extra="ignore")

    provider: str | None = None
    llm_provider: str | None = None
    api_key: str | None = None
    model: str | None = None
    embed_provider: str | None = None
    ollama_embed_model: str | None = None
    ollama_model: str | None = None
    dashscope_model: str | None = None
    deepseek_model: str | None = None
    openai_model: str | None = None
    minimax_model: str | None = None
    dashscope_api_key: str | None = None
    deepseek_api_key: str | None = None
    openai_api_key: str | None = None
    minimax_api_key: str | None = None
    # Read-only flags echoed by GET. Ignored on write.
    dashscope_api_key_set: bool | None = None
    deepseek_api_key_set: bool | None = None
    openai_api_key_set: bool | None = None
    minimax_api_key_set: bool | None = None


# ============ 用户管理 ============

@router.get("/users", response_model=list)
def list_users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, created_at FROM users ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/users", response_model=Resp)
def create_user(body: dict):
    username = body.get("username", "").strip()
    password = body.get("password", "")
    role = body.get("role", "user")

    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")
    if password == LEGACY_ADMIN_PASSWORD:
        raise HTTPException(status_code=400, detail="不能使用已公开的默认密码")

    if role not in ["admin", "user"]:
        raise HTTPException(status_code=400, detail="角色无效")

    password_hash = pwd_ctx.hash(password)
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, password_hash, role)
        )
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"创建失败: {str(e)}")
    conn.close()
    return Resp(message="创建成功")


@router.put("/users/{user_id}", response_model=Resp)
def update_user(user_id: int, body: dict):
    conn = get_db()
    cur = conn.cursor()

    username = body.get("username", "").strip()
    password = body.get("password", "")
    role = body.get("role", "")

    if username:
        cur.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
    if password:
        if password == LEGACY_ADMIN_PASSWORD:
            conn.close()
            raise HTTPException(status_code=400, detail="不能使用已公开的默认密码")
        password_hash = pwd_ctx.hash(password)
        cur.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
            (password_hash, user_id),
        )
    if role in ["admin", "user"]:
        cur.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))

    conn.commit()
    conn.close()
    return Resp(message="更新成功")


@router.delete("/users/{user_id}", response_model=Resp)
def delete_user(user_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return Resp(message="删除成功")


@router.get("/stats", response_model=dict)
def get_stats():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) as cnt FROM (SELECT 1 FROM documents GROUP BY filename)")
    doc_count = cur.fetchone()["cnt"]

    cur.execute("SELECT COUNT(*) as cnt FROM chunks")
    chunk_count = cur.fetchone()["cnt"]

    cur.execute("SELECT COUNT(*) as cnt FROM users")
    user_count = cur.fetchone()["cnt"]

    conn.close()

    return {
        "document_count": doc_count,
        "chunk_count": chunk_count,
        "user_count": user_count
    }


# ============ 系统配置（统一入口）============

@router.get("/config", response_model=SystemConfig)
def get_config():
    """Get current system config (with configuration flags)"""
    s = get_settings()
    return SystemConfig(
        llm_provider=s.LLM_PROVIDER,
        ollama_model=s.OLLAMA_MODEL,
        ollama_embed_model=s.OLLAMA_EMBED_MODEL or s.OLLAMA_MODEL,
        dashscope_model=s.DASHSCOPE_MODEL,
        deepseek_model=s.DEEPSEEK_MODEL,
        openai_model=s.OPENAI_MODEL,
        minimax_model=s.MINIMAX_MODEL,
        embed_provider=s.EMBED_PROVIDER,
        dashscope_api_key_set=bool(s.DASHSCOPE_API_KEY),
        deepseek_api_key_set=bool(s.DEEPSEEK_API_KEY),
        openai_api_key_set=bool(s.OPENAI_API_KEY),
        minimax_api_key_set=bool(s.MINIMAX_API_KEY),
    )


def _plain(value: object, label: str) -> str:
    """Strip a config value and reject line breaks so .env stays one key per line."""
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{label}无效")
    if any(ch in value for ch in ("\n", "\r", "\x00")):
        raise HTTPException(status_code=400, detail=f"{label}包含非法字符")
    return value.strip()


@router.put("/config", response_model=Resp)
def update_config(body: SystemConfigUpdate):
    """Save system config to .env. Admin only, same as the other admin routes.

    The settings page PUTs the model form (`provider`, `api_key`, `model`,
    `embed_provider`) and the embedding form (`embed_provider`,
    `ollama_embed_model`). GET field names are accepted too.
    """
    fields = body.model_dump(exclude_unset=True)
    updates: dict[str, str] = {}

    def queue(env_key: str, value: str) -> None:
        previous = updates.get(env_key)
        if previous is not None and previous != value:
            raise HTTPException(status_code=400, detail="配置项冲突")
        updates[env_key] = value

    provider: str | None = None
    if "provider" in fields or "llm_provider" in fields:
        chosen: list[str] = []
        for raw in (fields.get("provider"), fields.get("llm_provider")):
            if raw is None:
                continue
            text = _plain(raw, "模型提供商").lower()
            if not text:
                raise HTTPException(status_code=400, detail="模型提供商不能为空")
            chosen.append(text)
        if len(set(chosen)) > 1:
            raise HTTPException(status_code=400, detail="provider 与 llm_provider 不一致")
        if chosen:
            provider = chosen[0]
            if provider not in _LLM_PROVIDERS:
                raise HTTPException(status_code=400, detail="不支持的模型提供商")
            queue("LLM_PROVIDER", provider)

    if provider is None:
        provider = (get_settings().LLM_PROVIDER or "").strip().lower()

    if "model" in fields and fields.get("model") is not None:
        model_name = _plain(fields["model"], "模型")
        env_key = _MODEL_ENV_BY_PROVIDER.get(provider)
        if model_name and env_key:
            queue(env_key, model_name)

    for field, env_key in _EXPLICIT_MODEL_FIELDS.items():
        if field in fields and fields.get(field) is not None:
            model_name = _plain(fields[field], "模型")
            if model_name:
                queue(env_key, model_name)

    if "embed_provider" in fields and fields.get("embed_provider") is not None:
        embed = _plain(fields["embed_provider"], "Embedding 提供商").lower()
        if not embed:
            raise HTTPException(status_code=400, detail="Embedding 提供商不能为空")
        if embed not in _EMBED_PROVIDERS:
            raise HTTPException(status_code=400, detail="不支持的 Embedding 提供商")
        queue("EMBED_PROVIDER", embed)

    if "ollama_embed_model" in fields and fields.get("ollama_embed_model") is not None:
        # Empty string is the settings form's "reuse the LLM model" choice.
        queue("OLLAMA_EMBED_MODEL", _plain(fields["ollama_embed_model"], "Embedding 模型"))

    if fields.get("api_key"):
        secret = _plain(fields["api_key"], "API Key")
        key_env = _KEY_ENV_BY_PROVIDER.get(provider)
        if secret and key_env:
            queue(key_env, secret)

    for field, env_key in _EXPLICIT_KEY_FIELDS.items():
        if fields.get(field):
            secret = _plain(fields[field], "API Key")
            if secret:
                queue(env_key, secret)

    if not updates:
        return Resp(message="没有需要更新的配置")

    try:
        update_env_many(updates)
    except ValueError:
        raise HTTPException(status_code=400, detail="配置值无效") from None
    return Resp(message="配置已保存，需重启服务生效")


# ============ AI 模型配置 ============

@router.post("/model/verify", response_model=ModelConfigResp)
def verify_model_config(body: ModelConfigReq):
    """验证 AI 模型 API Key 是否有效"""
    if not body.api_key:
        return ModelConfigResp(valid=False, message="API Key 不能为空")

    if body.provider == "deepseek":
        try:
            from openai import OpenAI
            client = OpenAI(api_key=body.api_key, base_url="https://api.deepseek.com")
            model = body.model or "deepseek-chat"
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5
            )
            return ModelConfigResp(valid=True, message="API Key 有效")
        except Exception as e:
            return ModelConfigResp(valid=False, message=f"验证异常: {str(e)}")

    elif body.provider == "ollama":
        try:
            import httpx
            base_url = get_settings().OLLAMA_BASE_URL.rstrip("/")
            resp = httpx.get(f"{base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m["name"] for m in models]
                return ModelConfigResp(valid=True, message=f"Ollama 连接成功，可用模型: {', '.join(model_names)}")
            else:
                return ModelConfigResp(valid=False, message=f"Ollama 连接失败: {resp.status_code}")
        except Exception as e:
            return ModelConfigResp(valid=False, message=f"Ollama 连接失败: {str(e)}")

    else:  # dashscope
        import dashscope
        dashscope.api_key = body.api_key
        from dashscope import Generation
        try:
            resp = Generation.call(
                model=body.model or "qwen-turbo",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5
            )
            if resp["status_code"] == 200:
                return ModelConfigResp(valid=True, message="API Key 有效")
            else:
                return ModelConfigResp(valid=False, message=f"验证失败: {resp.get('message', resp)}")
        except Exception as e:
            return ModelConfigResp(valid=False, message=f"验证异常: {str(e)}")


@router.post("/model/config", response_model=Resp)
def save_model_config(body: ModelConfigReq):
    """保存 AI 模型配置到 .env"""
    if body.provider == "deepseek":
        update_env("LLM_PROVIDER", "deepseek")
        update_env("DEEPSEEK_API_KEY", body.api_key)
        update_env("DEEPSEEK_MODEL", body.model or "deepseek-chat")
    elif body.provider == "ollama":
        update_env("LLM_PROVIDER", "ollama")
        if body.model:
            update_env("OLLAMA_MODEL", body.model)
    else:
        update_env("LLM_PROVIDER", "dashscope")
        update_env("DASHSCOPE_API_KEY", body.api_key)
        update_env("DASHSCOPE_MODEL", body.model or "qwen-turbo")
    return Resp(message="配置已保存，需重启服务生效")


# ============ Ollama 模型列表 ============

@router.get("/ollama/models", response_model=list)
def list_ollama_models():
    """从 Ollama 获取可用的模型列表"""
    import httpx
    try:
        base_url = get_settings().OLLAMA_BASE_URL.rstrip("/")
        resp = httpx.get(f"{base_url}/api/tags", timeout=5)
        if resp.status_code != 200:
            return []
        models = resp.json().get("models", [])
        # 返回模型名列表
        return sorted([m["name"] for m in models])
    except Exception:
        return []


# ============ Embedding 模型配置 ============

@router.get("/index")
def get_index_status():
    """当前 Embedding 与 active 索引是否同一套。不一致时 message 供页面提示重建。"""
    from server.domain.documents.index_build import index_status

    return index_status()


@router.post("/index/rebuild")
def rebuild_index():
    """用现有线程池按 SQLite 切片重嵌，完成后切换 active。不删除旧集合。"""
    from server.domain.documents.index_build import (
        MockIndexError,
        RebuildInProgress,
        begin_rebuild,
    )

    try:
        return begin_rebuild()
    except MockIndexError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RebuildInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/embed/config", response_model=Resp)
def save_embed_config(body: ModelConfigReq):
    """保存 Embedding 模型配置到 .env"""
    if body.embed_provider:
        update_env("EMBED_PROVIDER", body.embed_provider)
    if body.ollama_embed_model:
        update_env("OLLAMA_EMBED_MODEL", body.ollama_embed_model)
    return Resp(message="Embedding 配置已保存，需重启服务生效")


# ============ 服务重启 ============

@router.post("/restart")
def restart_server():
    """重启后端服务"""
    restart_server_async()
    return {"message": "服务重启中，请等待页面刷新"}
