"""写入可重复执行的工作室演示用户和知识资料。"""
from __future__ import annotations
import asyncio, json
from uuid import uuid4
from passlib.context import CryptContext
from sqlalchemy import text
from backend.dependencies import AsyncSessionLocal
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
DOCS = [
    ("土地估价方法速查", "land", "市场比较法适用于有足够可比交易实例的土地；收益法适用于收益稳定且可以合理预测未来收益的经营性不动产；成本法关注重置成本和折旧；假设开发法适用于具有明确开发计划和市场条件的待开发土地。"),
]
def chunks(value: str, size: int = 1600):
    return [value[i:i + size] for i in range(0, len(value), size)]
async def main():
    async with AsyncSessionLocal() as db:
        exists = await db.execute(text("SELECT id FROM users WHERE username='analyst' LIMIT 1"))
        if not exists.scalar():
            await db.execute(text("""INSERT INTO users (id, tenant_id, username, email, password_hash)
                VALUES (:id, 'tenant_default', 'analyst', 'analyst@pinggu.local', :password)"""), {"id": uuid4(), "password": pwd.hash("Analyst@123456")})
        for title, domain, content in DOCS:
            old = await db.execute(text("SELECT id FROM knowledge_documents WHERE title=:title LIMIT 1"), {"title": title})
            if old.scalar():
                continue
            doc_id = uuid4(); parts = chunks(content)
            await db.execute(text("""INSERT INTO knowledge_documents
                (id, tenant_id, title, source_name, domain, file_type, status, chunk_count)
                VALUES (:id, 'tenant_default', :title, :source_name, :domain, 'txt', 'ready', :count)"""), {"id": doc_id, "title": title, "source_name": f"seed_{domain}.txt", "domain": domain, "count": len(parts)})
            for index, part in enumerate(parts):
                await db.execute(text("""INSERT INTO knowledge_document_chunks
                    (id, document_id, chunk_index, content, metadata) VALUES (:id, :document_id, :index, :content, CAST(:metadata AS JSONB))"""), {"id": uuid4(), "document_id": doc_id, "index": index, "content": part, "metadata": json.dumps({"source_name": f"seed_{domain}.txt", "domain": domain})})
        await db.commit()
    print("STUDIO_SEED_OK user=analyst password=Analyst@123456 documents=3")
if __name__ == '__main__':
    asyncio.run(main())
