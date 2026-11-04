"""
Tender - 认证 API
"""
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from passlib.context import CryptContext

from server.config import get_settings
from server.db.sqlite import get_db
from server.deps import get_current_user
from server.models import LoginReq, LoginResp, UserInfo

router = APIRouter(prefix="/api/auth", tags=["认证"])

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_token(data: dict) -> str:
    settings = get_settings()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    data.update({"exp": expire})
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


@router.post("/login", response_model=LoginResp)
def login(req: LoginReq):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash, role FROM users WHERE username = ?", (req.username,))
    row = cur.fetchone()
    conn.close()
    
    if not row or not pwd_ctx.verify(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    token = create_token({"sub": str(row["id"])})
    return LoginResp(
        access_token=token,
        user={"id": row["id"], "username": row["username"], "role": row["role"]}
    )


@router.post("/logout")
def logout(_user: dict[str, Any] = Depends(get_current_user)):
    return {"message": "ok"}


@router.get("/me", response_model=UserInfo)
def me(user: dict[str, Any] = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT created_at FROM users WHERE id = ?", (user["id"],))
    row = cur.fetchone()
    conn.close()
    return UserInfo(**user, created_at=row["created_at"] if row else "")
