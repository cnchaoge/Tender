"""
ClawOS X - 管理后台 API（统一配置 + 用户管理）
"""
import os
import signal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from passlib.context import CryptContext
from server.db.sqlite import get_db
from server.config import get_settings, update_env
from server.models import Resp

router = APIRouter(prefix="/api/admin", tags=["管理后台"])
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()


# ============ 请求/响应模型 ============

class ModelConfigReq(BaseModel):
    api_key: str
    model: str = "qwen-turbo"


class ModelConfigResp(BaseModel):
    valid: bool
    message: str


class FeishuConfigReq(BaseModel):
    app_id: str
    app_secret: str


class FeishuConfigResp(BaseModel):
    valid: bool
    message: str


class SystemConfig(BaseModel):
    """系统配置（不含敏感信息）"""
    llm_provider: str
    dashscope_model: str
    dashscope_api_key_set: bool  # 是否已配置（不返回实际 key）
    feishu_app_id: str
    feishu_app_secret_set: bool  # 是否已配置
    feishu_status: str  # not_configured | connected | error


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

    cur.execute("SELECT COUNT(*) as cnt FROM documents")
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
    """获取当前系统配置（含是否已配置的标识）"""
    s = get_settings()
    return SystemConfig(
        llm_provider=s.LLM_PROVIDER,
        dashscope_model=s.DASHSCOPE_MODEL,
        dashscope_api_key_set=bool(s.DASHSCOPE_API_KEY),
        feishu_app_id=s.FEISHU_APP_ID,
        feishu_app_secret_set=bool(s.FEISHU_APP_SECRET),
        feishu_status="connected" if s.FEISHU_APP_ID and s.FEISHU_APP_SECRET else "not_configured",
    )


# ============ AI 模型配置 ============

@router.post("/model/verify", response_model=ModelConfigResp)
def verify_model_config(body: ModelConfigReq):
    """验证通义千问 API Key 是否有效"""
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
    """保存通义千问配置到 .env"""
    update_env("DASHSCOPE_API_KEY", body.api_key)
    update_env("DASHSCOPE_MODEL", body.model or "qwen-turbo")
    update_env("LLM_PROVIDER", "dashscope")
    return Resp(message="配置已保存，需重启服务生效")


# ============ 飞书配置 ============

@router.post("/feishu/verify", response_model=FeishuConfigResp)
def verify_feishu_config(body: FeishuConfigReq):
    """验证飞书配置是否有效"""
    if not body.app_id or not body.app_secret:
        return FeishuConfigResp(valid=False, message="App ID 和 App Secret 不能为空")

    import httpx
    try:
        resp = httpx.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": body.app_id, "app_secret": body.app_secret},
            timeout=10
        )
        data = resp.json()
        if data.get("code") == 0:
            return FeishuConfigResp(valid=True, message="连接成功")
        else:
            return FeishuConfigResp(valid=False, message=f"验证失败: {data.get('msg', data)}")
    except Exception as e:
        return FeishuConfigResp(valid=False, message=f"连接异常: {str(e)}")


@router.post("/feishu/config", response_model=Resp)
def save_feishu_config(body: FeishuConfigReq):
    """保存飞书配置到 .env"""
    update_env("FEISHU_APP_ID", body.app_id)
    update_env("FEISHU_APP_SECRET", body.app_secret)
    return Resp(message="飞书配置已保存，需重启服务生效")


# ============ 服务重启 ============

@router.post("/restart", response_model=Resp)
def restart_server():
    """重启后端服务（开发模式）"""
    pid = os.getpid()
    os.kill(pid, signal.SIGTERM)
    return Resp(message="服务重启中")
