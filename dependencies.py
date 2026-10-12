"""数据库会话和统一用户 JWT 依赖。"""
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from jose import JWTError, jwt
from backend.config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, pool_size=10, max_overflow=20, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

bearer_scheme = HTTPBearer()
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证凭证", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if not user_id:
            raise invalid
    except JWTError:
        raise invalid
    return {"user_id": str(user_id), "tenant_id": payload.get("tenant_id", settings.default_tenant_id),
            "username": payload.get("username", "")}
