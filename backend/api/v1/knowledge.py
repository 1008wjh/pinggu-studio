"""多知识库管理 API。

知识库、绑定关系和文档均按 tenant 隔离。上传文档时先写 PostgreSQL 原文分块，再写入对应
Milvus partition；专业问答只通过绑定关系获取允许检索的 knowledge_base_id。
"""
from __future__ import annotations
import json, shutil, tempfile
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.dependencies import get_current_user, get_db
from backend.services.document_workspace import extract_document
from backend.services.knowledge_rag import IsolatedKnowledgeRAG

router = APIRouter()
_ROOT = Path(tempfile.gettempdir()) / "pinggu_agent_knowledge"
_ROOT.mkdir(parents=True, exist_ok=True)
_ALLOWED = {".txt", ".md", ".pdf", ".docx", ".csv", ".tsv", ".xlsx", ".xlsm", ".json"}
AGENTS = {"domain_qa": "企业文档问答", "land_assessment": "合同与招投标审查", "document_review": "文档风险审查"}

class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field("", max_length=2000)
    agent_keys: list[str] = Field(default_factory=lambda: ["domain_qa"])

class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = Field(None, max_length=2000)
    agent_keys: list[str] | None = None

async def _base(db: AsyncSession, kb_id: str, tenant_id: str) -> dict[str, Any]:
    row=(await db.execute(text("""SELECT id, tenant_id, name, description, status, milvus_partition, created_at, updated_at
        FROM knowledge_bases WHERE id=:id AND tenant_id=:tenant_id"""), {"id":kb_id,"tenant_id":tenant_id})).mappings().first()
    if not row: raise HTTPException(404, detail="知识库不存在")
    agents=(await db.execute(text("SELECT agent_key FROM knowledge_base_agents WHERE knowledge_base_id=:id ORDER BY agent_key"), {"id":kb_id})).scalars().all()
    docs=(await db.execute(text("SELECT count(*) FROM knowledge_documents WHERE knowledge_base_id=:id"), {"id":kb_id})).scalar_one()
    return {**dict(row), "id":str(row["id"]), "agents":[{"key":key,"name":AGENTS.get(key,key)} for key in agents], "document_count":docs}

def _plain(value: object) -> str:
    if isinstance(value, str): return value
    if isinstance(value, list): return "\n".join(_plain(item) for item in value)
    if isinstance(value, dict): return "\n".join(f"{key}: {_plain(item)}" for key, item in value.items())
    return str(value)

def _chunks(content: str, size: int = 1600) -> list[str]:
    content=content.strip()
    return [content[i:i+size] for i in range(0,len(content),size)] or ["（文档没有可抽取的正文）"]

async def _save(upload: UploadFile, folder: Path) -> tuple[str, str]:
    filename=Path(upload.filename or "upload.bin").name; suffix=Path(filename).suffix.lower()
    if suffix not in _ALLOWED: raise HTTPException(400, detail=f"暂不支持 {suffix or '无扩展名'} 文件")
    folder.mkdir(parents=True, exist_ok=True); path=folder/filename
    with path.open("wb") as handle: shutil.copyfileobj(upload.file,handle)
    data=extract_document(str(path), max_rows=None)
    return str(path), _plain({key:value for key,value in data.items() if key != "file_name"})

async def _upsert_doc(db: AsyncSession, kb: dict[str, Any], path: str, content: str, title: str, tenant_id: str, document_id: UUID | None = None) -> dict[str, Any]:
    doc_id=document_id or uuid4(); filename=Path(path).name; suffix=Path(path).suffix.lower(); pieces=_chunks(content); vector_count=0; vector_error=""
    try:
        vector_count=await __import__('asyncio').to_thread(IsolatedKnowledgeRAG.upsert_vectors, str(kb["id"]), str(doc_id), filename, pieces, tenant_id)
    except Exception as exc:
        vector_error=f"Milvus 向量写入待重试：{str(exc)[:500]}"
    status = "ready" if not vector_error else "vector_pending"
    await db.execute(text("""INSERT INTO knowledge_documents
        (id, tenant_id, user_id, knowledge_base_id, title, source_name, domain, file_type, storage_path, status, chunk_count, vector_count, error_message)
        VALUES (:id,:tenant_id,:user_id,:kb,:title,:source,:domain,:type,:path,:status,:chunks,:vectors,:error)
        ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, source_name=EXCLUDED.source_name, storage_path=EXCLUDED.storage_path,
        status=EXCLUDED.status, chunk_count=EXCLUDED.chunk_count, vector_count=EXCLUDED.vector_count, error_message=EXCLUDED.error_message, updated_at=NOW()"""), {
        "id":doc_id,"tenant_id":tenant_id,"user_id":None,"kb":kb["id"],"title":title.strip() or Path(filename).stem,"source":filename,"domain":"studio","type":suffix.lstrip("."),"path":path,"status":status,"chunks":len(pieces),"vectors":vector_count,"error":vector_error})
    await db.execute(text("DELETE FROM knowledge_document_chunks WHERE document_id=:id"), {"id":doc_id})
    for index,piece in enumerate(pieces):
        await db.execute(text("""INSERT INTO knowledge_document_chunks (id, document_id, knowledge_base_id, chunk_index, content, metadata)
            VALUES (:id,:doc,:kb,:index,:content,CAST(:metadata AS JSONB))"""), {"id":uuid4(),"doc":doc_id,"kb":kb["id"],"index":index,"content":piece,"metadata":json.dumps({"source_name":filename,"knowledge_base_id":str(kb["id"])})})
    return {"id":str(doc_id),"knowledge_base_id":str(kb["id"]),"title":title.strip() or Path(filename).stem,"source_name":filename,"status":status,"chunk_count":len(pieces),"vector_count":vector_count,"vector_error":vector_error}

@router.get("/bases")
async def list_bases(page: int=Query(1,ge=1), page_size: int=Query(20,ge=1,le=100), db: AsyncSession=Depends(get_db), user: dict=Depends(get_current_user)):
    total=(await db.execute(text("SELECT count(*) FROM knowledge_bases WHERE tenant_id=:tenant_id AND status='active'"), {"tenant_id":user["tenant_id"]})).scalar_one()
    rows=(await db.execute(text("SELECT id FROM knowledge_bases WHERE tenant_id=:tenant_id AND status='active' ORDER BY created_at DESC LIMIT :limit OFFSET :offset"), {"tenant_id":user["tenant_id"],"limit":page_size,"offset":(page-1)*page_size})).scalars().all()
    return {"items":[await _base(db,str(row),user["tenant_id"]) for row in rows],"page":page,"page_size":page_size,"total":total}

@router.post("/bases")
async def create_base(req: KnowledgeBaseCreate, db: AsyncSession=Depends(get_db), user: dict=Depends(get_current_user)):
    invalid=set(req.agent_keys)-set(AGENTS)
    if invalid: raise HTTPException(400,detail=f"不支持的智能体：{', '.join(invalid)}")
    kb_id=uuid4(); partition=IsolatedKnowledgeRAG._partition(str(kb_id))
    try:
        await db.execute(text("""INSERT INTO knowledge_bases (id,tenant_id,name,description,milvus_partition,created_by) VALUES (:id,:tenant,:name,:description,:partition,:user)"""), {"id":kb_id,"tenant":user["tenant_id"],"name":req.name.strip(),"description":req.description,"partition":partition,"user":user["user_id"]})
        for agent in req.agent_keys:
            await db.execute(text("INSERT INTO knowledge_base_agents (knowledge_base_id,agent_key,tenant_id) VALUES (:id,:agent,:tenant)"), {"id":kb_id,"agent":agent,"tenant":user["tenant_id"]})
        await __import__('asyncio').to_thread(IsolatedKnowledgeRAG.ensure_partition,partition)
    except Exception as exc: raise HTTPException(400,detail={"code":"KNOWLEDGE_BASE_CREATE_FAILED","message":str(exc)}) from exc
    return await _base(db,str(kb_id),user["tenant_id"])

@router.patch("/bases/{kb_id}")
async def update_base(kb_id: str, req: KnowledgeBaseUpdate, db: AsyncSession=Depends(get_db), user: dict=Depends(get_current_user)):
    await _base(db,kb_id,user["tenant_id"]); invalid=set(req.agent_keys or [])-set(AGENTS)
    if invalid: raise HTTPException(400,detail=f"不支持的智能体：{', '.join(invalid)}")
    if req.name is not None or req.description is not None:
        await db.execute(text("UPDATE knowledge_bases SET name=COALESCE(:name,name), description=COALESCE(:description,description), updated_at=NOW() WHERE id=:id AND tenant_id=:tenant"), {"name":req.name,"description":req.description,"id":kb_id,"tenant":user["tenant_id"]})
    if req.agent_keys is not None:
        await db.execute(text("DELETE FROM knowledge_base_agents WHERE knowledge_base_id=:id"), {"id":kb_id})
        for agent in req.agent_keys:
            await db.execute(text("INSERT INTO knowledge_base_agents (knowledge_base_id,agent_key,tenant_id) VALUES (:id,:agent,:tenant)"), {"id":kb_id,"agent":agent,"tenant":user["tenant_id"]})
    return await _base(db,kb_id,user["tenant_id"])

@router.delete("/bases/{kb_id}")
async def delete_base(kb_id: str, db: AsyncSession=Depends(get_db), user: dict=Depends(get_current_user)):
    base=await _base(db,kb_id,user["tenant_id"])
    if base["name"] == "默认工作室知识库": raise HTTPException(409,detail="默认兼容知识库不能删除")
    await db.execute(text("DELETE FROM knowledge_bases WHERE id=:id AND tenant_id=:tenant"), {"id":kb_id,"tenant":user["tenant_id"]})
    return {"deleted":True,"id":kb_id}

@router.get("/bases/{kb_id}/documents")
async def list_base_documents(kb_id: str, db: AsyncSession=Depends(get_db), user: dict=Depends(get_current_user)):
    await _base(db,kb_id,user["tenant_id"])
    rows=(await db.execute(text("""SELECT id,title,source_name,file_type,status,chunk_count,vector_count,error_message,created_at,updated_at
        FROM knowledge_documents WHERE tenant_id=:tenant AND knowledge_base_id=:kb ORDER BY created_at DESC"""), {"tenant":user["tenant_id"],"kb":kb_id})).mappings().all()
    return {"items":[{**dict(row),"id":str(row["id"])} for row in rows]}

@router.post("/bases/{kb_id}/documents")
async def upload_base_document(kb_id: str, file: Annotated[UploadFile,File(...)], title: str=Form(""), db: AsyncSession=Depends(get_db), user: dict=Depends(get_current_user)):
    base=await _base(db,kb_id,user["tenant_id"]); path,content=await _save(file,_ROOT/str(uuid4()))
    try: return await _upsert_doc(db,base,path,content,title,user["tenant_id"])
    except Exception as exc: raise HTTPException(400,detail={"code":"KNOWLEDGE_INGEST_FAILED","message":str(exc)}) from exc

@router.get("/documents/{document_id}")
async def get_document(document_id: str, db: AsyncSession=Depends(get_db), user: dict=Depends(get_current_user)):
    row=(await db.execute(text("""SELECT id,knowledge_base_id,title,source_name,file_type,status,chunk_count,vector_count,error_message,created_at,updated_at
        FROM knowledge_documents WHERE id=:id AND tenant_id=:tenant"""), {"id":document_id,"tenant":user["tenant_id"]})).mappings().first()
    if not row: raise HTTPException(404,detail="文档不存在")
    chunks=(await db.execute(text("SELECT id,chunk_index,content,metadata FROM knowledge_document_chunks WHERE document_id=:id ORDER BY chunk_index"), {"id":document_id})).mappings().all()
    return {**dict(row),"id":str(row["id"]),"knowledge_base_id":str(row["knowledge_base_id"]),"chunks":[dict(chunk) for chunk in chunks]}

@router.put("/documents/{document_id}")
async def update_document(document_id: str, file: Annotated[UploadFile,File(...)], title: str=Form(""), db: AsyncSession=Depends(get_db), user: dict=Depends(get_current_user)):
    row=(await db.execute(text("SELECT knowledge_base_id FROM knowledge_documents WHERE id=:id AND tenant_id=:tenant"), {"id":document_id,"tenant":user["tenant_id"]})).mappings().first()
    if not row: raise HTTPException(404,detail="文档不存在")
    base=await _base(db,str(row["knowledge_base_id"]),user["tenant_id"]); await __import__('asyncio').to_thread(IsolatedKnowledgeRAG.delete_document_vectors,str(row["knowledge_base_id"]),document_id)
    path,content=await _save(file,_ROOT/document_id)
    await db.execute(text("DELETE FROM knowledge_documents WHERE id=:id"), {"id":document_id})
    return await _upsert_doc(db,base,path,content,title,user["tenant_id"],UUID(document_id))

@router.delete("/documents/{document_id}")
async def delete_document(document_id: str, db: AsyncSession=Depends(get_db), user: dict=Depends(get_current_user)):
    row=(await db.execute(text("SELECT knowledge_base_id FROM knowledge_documents WHERE id=:id AND tenant_id=:tenant"), {"id":document_id,"tenant":user["tenant_id"]})).mappings().first()
    if not row: raise HTTPException(404,detail="文档不存在")
    await __import__('asyncio').to_thread(IsolatedKnowledgeRAG.delete_document_vectors,str(row["knowledge_base_id"]),document_id)
    await db.execute(text("DELETE FROM knowledge_documents WHERE id=:id"), {"id":document_id})
    return {"deleted":True,"id":document_id}

# 兼容旧页面：默认写入当前用户的默认工作室知识库。
@router.post("/documents")
async def upload_legacy_document(file: Annotated[UploadFile,File(...)], title: str=Form(""), domain: str=Form("studio"), db: AsyncSession=Depends(get_db), user: dict=Depends(get_current_user)):
    row=(await db.execute(text("SELECT id FROM knowledge_bases WHERE tenant_id=:tenant ORDER BY name LIMIT 1"), {"tenant":user["tenant_id"]})).first()
    if not row: raise HTTPException(409,detail="请先创建知识库")
    return await upload_base_document(str(row[0]),file,title,db,user)

@router.get("/health")
async def knowledge_health(): return {"status":"ok","agent":"isolated_knowledge_base","retrieval":"0.5*bm25+0.5*vector","partition_isolation":True}
