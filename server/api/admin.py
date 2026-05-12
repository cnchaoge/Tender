"""
ClawOS X - 管理后台 API（统一配置 + 用户管理）
"""
import os
import signal
import sys
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from passlib.context import CryptContext
from server.db.sqlite import get_db
from server.config import get_settings, update_env

# ============ 热重启信号处理 ============
def _hot_restart(signum, frame):
    """收到 SIGTERM 后用 os.execl 原地替换进程，实现零停机重启"""
    python = sys.executable
    os.execl(python, python, "-m", "uvicorn", "server.main:app",
             "--host", "0.0.0.0", "--port", "8000")

signal.signal(signal.SIGTERM, _hot_restart)
from server.models import Resp

router = APIRouter(prefix="/api/admin", tags=["管理后台"])
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()


# ============ 请求/响应模型 ============

class ModelConfigReq(BaseModel):
    provider: str = "dashscope"  # dashscope | deepseek
    api_key: str
    model: str = ""
    embed_provider: str = ""  # dashscope | bge | m3e | mock


class ModelConfigResp(BaseModel):
    valid: bool
    message: str


class SystemConfig(BaseModel):
    """System config (no sensitive info)"""
    llm_provider: str
    dashscope_model: str
    deepseek_model: str
    embed_provider: str
    dashscope_api_key_set: bool  # whether configured (no actual key)


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
        password_hash = pwd_ctx.hash(password)
        cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
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
        dashscope_model=s.DASHSCOPE_MODEL,
        deepseek_model=s.DEEPSEEK_MODEL,
        embed_provider=s.EMBED_PROVIDER,
        dashscope_api_key_set=bool(s.DASHSCOPE_API_KEY),
    )


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
    else:
        update_env("LLM_PROVIDER", "dashscope")
        update_env("DASHSCOPE_API_KEY", body.api_key)
        update_env("DASHSCOPE_MODEL", body.model or "qwen-turbo")
    return Resp(message="配置已保存，需重启服务生效")


# ============ Embedding 模型配置 ============

@router.post("/embed/config", response_model=Resp)
def save_embed_config(body: ModelConfigReq):
    """保存 Embedding 模型配置到 .env"""
    if body.embed_provider:
        update_env("EMBED_PROVIDER", body.embed_provider)
    return Resp(message="Embedding 配置已保存，需重启服务生效")


# ============ 服务重启 ============

@router.post("/restart", response_model=Resp)
def restart_server():
    """重启后端服务（热重启，不中断）"""
    pid = os.getpid()
    os.kill(pid, signal.SIGTERM)
    return Resp(message="服务重启中")
