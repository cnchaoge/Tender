"""
Tender - 认证 API
"""
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from passlib.context import CryptContext

from server.config import get_settings
from server.db import sqlite as sqlite_db
from server.db.sqlite import (
    BOOTSTRAP_ADMIN_USERNAME,
    LEGACY_ADMIN_PASSWORD,
    get_db,
)
from server.deps import get_authenticated_user
from server.models import ChangePasswordReq, LoginReq, LoginResp, UserInfo

router = APIRouter(prefix="/api/auth", tags=["认证"])

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
_MIN_PASSWORD_LENGTH = 8


def create_token(data: dict) -> str:
    settings = get_settings()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    data.update({"exp": expire})
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


@router.post("/login", response_model=LoginResp)
def login(req: LoginReq):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username, password_hash, role, must_change_password "
        "FROM users WHERE username = ?",
        (req.username,),
    )
    row = cur.fetchone()
    conn.close()

    if not row or not pwd_ctx.verify(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    must_change = bool(row["must_change_password"])
    token = create_token({"sub": str(row["id"])})
    user = {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "must_change_password": must_change,
    }
    return LoginResp(
        access_token=token,
        must_change_password=must_change,
        user=user,
    )


@router.post("/logout")
def logout(_user: dict[str, Any] = Depends(get_authenticated_user)):
    return {"message": "ok"}


@router.get("/me", response_model=UserInfo)
def me(user: dict[str, Any] = Depends(get_authenticated_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT created_at FROM users WHERE id = ?", (user["id"],))
    row = cur.fetchone()
    conn.close()
    return UserInfo(**user, created_at=row["created_at"] if row else "")


@router.post("/change-password")
def change_password(
    req: ChangePasswordReq,
    user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Replace the caller's password and clear a pending forced change."""
    new_password = req.new_password or ""
    old_password = req.old_password or ""
    if len(new_password) < _MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail="新密码至少 8 位")
    if new_password == old_password:
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")
    if new_password in {LEGACY_ADMIN_PASSWORD, user["username"]}:
        raise HTTPException(status_code=400, detail="不能使用已公开或过于简单的密码")

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],))
        row = cur.fetchone()
        if not row or not pwd_ctx.verify(old_password, row["password_hash"]):
            raise HTTPException(status_code=400, detail="当前密码不正确")
        cur.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
            (pwd_ctx.hash(new_password), user["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    if user["username"] == BOOTSTRAP_ADMIN_USERNAME:
        # Read DATA_DIR at call time so a relocated data directory is honored.
        path = sqlite_db.DATA_DIR / sqlite_db.INITIAL_PASSWORD_FILENAME
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return {"message": "密码已更新", "must_change_password": False}
