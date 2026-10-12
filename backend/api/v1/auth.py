"""统一用户认证接口。工作室不区分教师、学生或管理员角色。"""
import asyncio
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt
from passlib.context import CryptContext
from backend.config import get_settings
from backend.dependencies import get_db, get_current_user

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    tenant_id: str
    username: str

def _token(user_id: str, tenant_id: str, username: str) -> str:
    settings = get_settings()
    payload = {"sub": user_id, "tenant_id": tenant_id, "username": username,
               "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""SELECT id, username, password_hash, tenant_id, is_active
        FROM users WHERE username = :value OR email = :value LIMIT 1"""), {"value": req.username})
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not row.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    ok = await asyncio.to_thread(pwd_context.verify, req.password, row.password_hash)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    settings = get_settings()
    return TokenResponse(access_token=_token(str(row.id), row.tenant_id, row.username),
        expires_in=settings.jwt_access_token_expire_minutes * 60, user_id=str(row.id),
        tenant_id=row.tenant_id, username=row.username)

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user
