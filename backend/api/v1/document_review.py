"""合同与招投标文档审查 API：三步 Agent 流程，每步必须人工确认。"""
from __future__ import annotations
import json, shutil, tempfile
from pathlib import Path
from typing import Annotated
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph.types import Command
from backend.agents.document_review.graph import build_document_review_graph
from backend.agents.document_review.state import STEP_EXTRACT, STEP_RISK, STEP_REPORT
from backend.dependencies import get_current_user, get_db

router = APIRouter()
ROOT = Path(tempfile.gettempdir()) / "pinggu_document_review"
ROOT.mkdir(parents=True, exist_ok=True)
GRAPH = build_document_review_graph()

class ResumeRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|return|edit)$")
    comment: str = Field("", max_length=4000)
    edited_output: dict = Field(default_factory=dict)

async def _snapshot(workflow_id: str) -> dict:
    state = await GRAPH.aget_state({"configurable": {"thread_id": workflow_id}})
    return dict(state.values or {})

async def _persist(db: AsyncSession, workflow_id: str, state: dict, user: dict, event: str, comment: str = "") -> None:
    payload = json.dumps(state, ensure_ascii=False, default=str)
    await db.execute(text("""UPDATE review_projects SET status=:status, report=:report, extracted_data=CAST(:state AS JSONB), updated_at=NOW() WHERE id=:id AND tenant_id=:tenant"""), {"status": state.get("status", "pending_review"), "report": state.get("review_context", {}).get("summary", ""), "state": payload, "id": workflow_id, "tenant": user["tenant_id"]})
    await db.execute(text("""INSERT INTO review_actions (id, project_id, user_id, decision, comment) VALUES (:id,:project,:user,:decision,:comment)"""), {"id": uuid4(), "project": workflow_id, "user": user["user_id"], "decision": event, "comment": comment})

def _response(workflow_id: str, state: dict) -> dict:
    return {"workflow_id": workflow_id, "status": state.get("status", "pending_review"), "current_step": state.get("current_step", STEP_EXTRACT), "checkpoint_version": state.get("checkpoint_version", 0), "review": state.get("review_context", {}), "step_outputs": state.get("step_outputs", {})}

@router.post("/workflows")
async def create_workflow(files: Annotated[list[UploadFile], File(...)], document_type: str = Form("contract"), instruction: str = Form(""), db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)):
    if not files: raise HTTPException(400, "至少上传一个合同或招投标文件")
    workflow_id = str(uuid4()); folder = ROOT / workflow_id; folder.mkdir(parents=True)
    paths=[]
    for upload in files:
        path = folder / Path(upload.filename or "document.bin").name
        with path.open("wb") as handle: shutil.copyfileobj(upload.file, handle)
        paths.append(str(path))
    initial = {"workflow_id": workflow_id, "thread_id": workflow_id, "tenant_id": user["tenant_id"], "user_id": user["user_id"], "file_paths": paths, "document_type": document_type, "instruction": instruction, "status": "running", "checkpoint_version": 0}
    await db.execute(text("""INSERT INTO review_projects (id,tenant_id,user_id,operation,status,source_files,report) VALUES (:id,:tenant,:user,'document_review','running',CAST(:files AS JSONB),'')"""), {"id":workflow_id,"tenant":user["tenant_id"],"user":user["user_id"],"files":json.dumps([Path(p).name for p in paths],ensure_ascii=False)})
    await GRAPH.ainvoke(initial, config={"configurable": {"thread_id": workflow_id}})
    state = await _snapshot(workflow_id); await _persist(db, workflow_id, state, user, "workflow_started")
    return _response(workflow_id, state)

@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)):
    row=(await db.execute(text("SELECT id FROM review_projects WHERE id=:id AND tenant_id=:tenant"), {"id":workflow_id,"tenant":user["tenant_id"]})).first()
    if not row: raise HTTPException(404,"审查工作流不存在")
    return _response(workflow_id, await _snapshot(workflow_id))

@router.post("/workflows/{workflow_id}/resume")
async def resume_workflow(workflow_id: str, req: ResumeRequest, db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)):
    state = await _snapshot(workflow_id)
    if not state: raise HTTPException(404,"审查工作流不存在")
    decision = {"action": req.action, "comment": req.comment, "edited_output": req.edited_output}
    await GRAPH.ainvoke(Command(resume=decision), config={"configurable": {"thread_id": workflow_id}})
    state = await _snapshot(workflow_id); await _persist(db, workflow_id, state, user, req.action, req.comment)
    return _response(workflow_id, state)

@router.get("/health")
async def document_review_health(): return {"status":"ok","domain":"contract_and_tender_review","human_review":True}

