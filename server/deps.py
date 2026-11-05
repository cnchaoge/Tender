"""
Shared FastAPI auth dependencies.

Every protected route depends on ``get_current_user``. Admin routes depend on
``require_admin``, which implies a logged-in user whose role is ``admin``.
"""
from typing import Any, Optional

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from server.config import get_settings
from server.db.sqlite import get_db

# auto_error=False so a missing Authorization header is our 401, not the
# framework default 403 ("Not authenticated").
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _unauthorized(detail: str = "未登录或登录已过期") -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


PASSWORD_CHANGE_REQUIRED = "必须先修改密码"


def _load_user(token: Optional[str]) -> dict[str, Any]:
    """Resolve a Bearer token to a user row, or 401."""
    if not token:
        raise _unauthorized()

    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise _unauthorized("无效的 token")

    user_id = payload.get("sub")
    if user_id is None:
        raise _unauthorized("无效的 token")

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, role, must_change_password FROM users WHERE id = ?",
            (user_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        raise _unauthorized("用户不存在")

    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "must_change_password": bool(row["must_change_password"]),
    }


def get_authenticated_user(token: Optional[str] = Depends(oauth2_scheme)) -> dict[str, Any]:
    """Logged-in user, including one who still has to change their password."""
    return _load_user(token)


def get_current_user(
    user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Logged-in user who is allowed to use the API.

    A bootstrap or legacy password can sign in, then must be changed before
    any other protected route. Login, logout, the current-user profile, and
    the password change itself stay available.
    """
    if user.get("must_change_password"):
        raise HTTPException(status_code=403, detail=PASSWORD_CHANGE_REQUIRED)
    return user


def require_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Same as get_current_user, plus role == admin (403 otherwise)."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
