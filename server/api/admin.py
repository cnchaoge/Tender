"""
ClawOS X - 管理后台 API
"""
from fastapi import APIRouter, HTTPException
from passlib.context import CryptContext
from server.db.sqlite import get_db
from server.models import Resp

router = APIRouter(prefix="/api/admin", tags=["管理后台"])
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
