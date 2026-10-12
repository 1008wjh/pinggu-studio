"""Create a user interactively without storing a default password in the repository."""
from __future__ import annotations

import asyncio
from getpass import getpass
from uuid import uuid4

from passlib.context import CryptContext
from sqlalchemy import text

from backend.config import get_settings
from backend.dependencies import AsyncSessionLocal

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def main() -> None:
    username = input("Username: ").strip()
    if not username:
        raise SystemExit("Username is required")

    password = getpass("Password (14+ characters): ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    if len(password) < 14 or len(password.encode("utf-8")) > 72:
        raise SystemExit("Password must be at least 14 characters and at most 72 UTF-8 bytes")

    tenant_id = get_settings().default_tenant_id
    async with AsyncSessionLocal() as db:
        exists = await db.execute(
            text("SELECT 1 FROM users WHERE tenant_id=:tenant AND username=:username"),
            {"tenant": tenant_id, "username": username},
        )
        if exists.scalar():
            raise SystemExit("That username already exists in the default tenant")
        await db.execute(
            text("""INSERT INTO users (id, tenant_id, username, password_hash)
                VALUES (:id, :tenant, :username, :password_hash)"""),
            {
                "id": uuid4(),
                "tenant": tenant_id,
                "username": username,
                "password_hash": password_context.hash(password),
            },
        )
        await db.commit()
    print(f"User created: {username}")


if __name__ == "__main__":
    asyncio.run(main())
