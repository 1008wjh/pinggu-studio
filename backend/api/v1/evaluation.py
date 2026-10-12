"""独立 LLM 评测 API。只调用现有 Agent，不改 RAG/LLM 业务实现。"""
from __future__ import annotations
import csv, io, json, shutil, tempfile
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from backend.dependencies import get_current_user
from backend.evaluation import runner, store

router=APIRouter()
ALLOWED={"legal_qa","contract_review","document_summary"}
ROOT=Path(tempfile.gettempdir())/"pinggu_evaluation_attachments"; ROOT.mkdir(parents=True,exist_ok=True)

def _parse_dataset(raw: bytes, filename: str) -> list[dict]:
    if filename.lower().endswith(".json"):
        data=json.loads(raw.decode("utf-8-sig")); return data if isinstance(data,list) else data.get("samples",[])
    text=raw.decode("utf-8-sig"); return list(csv.DictReader(io.StringIO(text)))

class SampleRequest(BaseModel):
    question: str = Field(..., min_length=1)
    reference_answer: str = Field(..., min_length=1)
    category: str = "legal_qa"
    attachment_path: str | None = None

@router.post("/tasks")
async def create_task(name: str=Form(...), category: str=Form("legal_qa"), dataset: UploadFile|None=File(None), user: dict=Depends(get_current_user)):
    if category not in ALLOWED: raise HTTPException(400,"不支持的评测分类")
    samples=[]
    if dataset:
        try: samples=_parse_dataset(await dataset.read(),dataset.filename or "dataset.csv")
        except Exception as exc: raise HTTPException(400,f"测试集解析失败：{exc}")
    valid=[item for item in samples if item.get("question") and item.get("reference_answer")]
    if len(valid)!=len(samples): raise HTTPException(400,"每条样本必须包含 question 和 reference_answer")
    return {"task_id":store.create_task(name,category,valid,user["tenant_id"]),"sample_count":len(valid)}

@router.post("/tasks/{task_id}/samples")
async def add_sample(task_id: str, req: SampleRequest, user: dict=Depends(get_current_user)):
    if not store.task(task_id): raise HTTPException(404,"评测任务不存在")
    if req.category not in ALLOWED: raise HTTPException(400,"不支持的评测分类")
    return {"sample_id":store.add_sample(task_id,req.model_dump())}

@router.post("/tasks/{task_id}/samples/upload")
async def add_sample_with_attachment(task_id: str, question: str=Form(...), reference_answer: str=Form(...), category: str=Form("contract_review"), attachment: UploadFile|None=File(None), user: dict=Depends(get_current_user)):
    if not store.task(task_id): raise HTTPException(404,"评测任务不存在")
    if category not in ALLOWED: raise HTTPException(400,"不支持的评测分类")
    attachment_path=None
    if attachment and attachment.filename:
        folder=ROOT/task_id; folder.mkdir(parents=True,exist_ok=True); target=folder/Path(attachment.filename).name
        with target.open("wb") as handle: shutil.copyfileobj(attachment.file,handle)
        attachment_path=str(target)
    return {"sample_id":store.add_sample(task_id,{"question":question,"reference_answer":reference_answer,"category":category,"attachment_path":attachment_path})}

@router.delete("/tasks/{task_id}/samples/{sample_id}")
async def delete_sample(task_id: str, sample_id: str, user: dict=Depends(get_current_user)):
    if not store.task(task_id): raise HTTPException(404,"评测任务不存在")
    conn=store.connect()
    try:
        result=conn.execute("DELETE FROM evaluation_samples WHERE id=? AND task_id=?",(sample_id,task_id))
        conn.execute("UPDATE evaluation_tasks SET total_samples=(SELECT count(*) FROM evaluation_samples WHERE task_id=?) WHERE id=?",(task_id,task_id)); conn.commit()
        if result.rowcount == 0: raise HTTPException(404,"评测样本不存在")
    finally: conn.close()
    return {"deleted":True,"sample_id":sample_id}

@router.post("/tasks/{task_id}/start")
async def start_task(task_id: str, user: dict=Depends(get_current_user)):
    task=store.task(task_id)
    if not task: raise HTTPException(404,"评测任务不存在")
    runner.start(task_id); return {"task_id":task_id,"status":"running"}

@router.post("/tasks/{task_id}/stop")
async def stop_task(task_id: str, user: dict=Depends(get_current_user)):
    if not store.task(task_id): raise HTTPException(404,"评测任务不存在")
    runner.stop(task_id); return {"task_id":task_id,"status":"stopping"}

@router.get("/tasks")
async def list_tasks(user: dict=Depends(get_current_user)): return {"items":store.list_tasks()}

@router.get("/tasks/{task_id}")
async def get_report(task_id: str, user: dict=Depends(get_current_user)):
    if not store.task(task_id): raise HTTPException(404,"评测任务不存在")
    return store.report(task_id)

@router.get("/tasks/{task_id}/samples/{sample_id}")
async def get_sample(task_id: str, sample_id: str, user: dict=Depends(get_current_user)):
    row=next((item for item in store.samples(task_id) if item["id"]==sample_id),None)
    if not row: raise HTTPException(404,"评测样本不存在")
    return row

@router.get("/tasks/{task_id}/export.csv")
async def export_csv(task_id: str, user: dict=Depends(get_current_user)):
    from fastapi.responses import StreamingResponse
    rows=store.samples(task_id); output=io.StringIO(); writer=csv.DictWriter(output,fieldnames=list(rows[0].keys()) if rows else ["id"]); writer.writeheader(); writer.writerows(rows)
    return StreamingResponse(iter([output.getvalue()]),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename=evaluation-{task_id}.csv"})
