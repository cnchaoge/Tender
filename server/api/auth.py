"""
ClawOS X - 认证 API
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext

from server.config import get_settings
from server.db.sqlite import get_db
from server.models import LoginReq, LoginResp, UserInfo, Resp

settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["认证"])

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def create_token(data: dict) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    data.update({"exp": expire})
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="无效的 token")
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的 token")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="用户不存在")
    return dict(row)


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
def logout(token: str = Depends(oauth2_scheme)):
    return {"message": "ok"}


@router.get("/me", response_model=UserInfo)
def me(token: str = Depends(oauth2_scheme)):
    user = get_current_user(token)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT created_at FROM users WHERE id = ?", (user["id"],))
    row = cur.fetchone()
    conn.close()
    return UserInfo(**user, created_at=row["created_at"] if row else "")
