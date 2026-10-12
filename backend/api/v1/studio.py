"""企业文档智能审查 Agent API：专业问答和文档初审。"""
from __future__ import annotations
import shutil, tempfile
import re
from pathlib import Path
from typing import Annotated
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.agents.studio.graph import build_studio_graph
from backend.dependencies import get_db, get_current_user

router = APIRouter()
_ROOT = Path(tempfile.gettempdir()) / "pinggu_agent_studio"
_ROOT.mkdir(parents=True, exist_ok=True)

async def _save(upload: UploadFile, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / Path(upload.filename or "material.bin").name
    with path.open("wb") as handle: shutil.copyfileobj(upload.file, handle)
    return path

async def _run(operation: str, message: str = "", paths: list[Path] | None = None, tenant_id: str = "tenant_default") -> dict:
    try:
        result = await build_studio_graph().ainvoke({"operation": operation, "message": message,
            "file_paths": [str(path) for path in (paths or [])], "tenant_id": tenant_id})
        return result.get("result", {})
    except Exception as exc:
        raise HTTPException(400, detail={"code": "STUDIO_AGENT_ERROR", "message": str(exc)}) from exc

async def _create_project(operation: str, result: dict, user: dict, db: AsyncSession) -> str:
    project_id = uuid4()
    await db.execute(text("""INSERT INTO review_projects
        (id, tenant_id, user_id, operation, status, source_files, report)
        VALUES (:id, :tenant_id, :user_id, :operation, :status, CAST(:source_files AS JSONB), :report)"""), {
        "id": project_id, "tenant_id": user["tenant_id"], "user_id": user["user_id"], "operation": operation,
        "status": result.get("status", "pending_review"), "source_files": __import__("json").dumps(result.get("source_files", [])),
        "report": result.get("report", "")})
    return str(project_id)

class QARequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)

@router.post("/qa")
async def domain_qa(req: QARequest, user: dict = Depends(get_current_user)):
    command = re.fullmatch(r"\s*运行测试任务\s*(.+?)\s*", req.message)
    if command:
        from backend.evaluation import runner, store
        task = next((item for item in store.list_tasks() if item["name"] == command.group(1)), None)
        if not task:
            return {"answer": f"未找到评测任务：{command.group(1)}", "sources": [], "status": "not_found"}
        if task["status"] in {"draft", "stopped", "failed"}: runner.start(task["id"])
        summary = store.report(task["id"])["summary"]
        return {"answer": f"评测任务「{task['name']}」已启动。当前完成 {summary['completed']}/{summary['total']} 条，平均 Judge 得分 {summary['avg_judge_score']} 分。可在“评测测试”页面查看实时报告。", "sources": [], "status": "evaluation_started"}
    return await _run("qa", req.message, tenant_id=user["tenant_id"])

async def _review_upload(operation: str, files: list[UploadFile], instruction: str, db: AsyncSession, user: dict):
    if not files: raise HTTPException(400, detail="至少需要一个材料文件")
    folder = _ROOT / str(uuid4())
    paths = [await _save(file, folder) for file in files]
    result = await _run(operation, instruction, paths, user["tenant_id"])
    result["project_id"] = await _create_project(operation, result, user, db)
    return result

@router.post("/land-assessment")
async def land_assessment(files: Annotated[list[UploadFile], File(...)], instruction: str = Form(""), db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)):
    return await _review_upload("land", files, instruction, db, user)

class ReviewRequest(BaseModel):
    project_id: str
    decision: str = Field(..., pattern="^(approved|revision_required|rejected)$")
    comment: str = Field("", max_length=4000)

@router.post("/review")
async def review_report(req: ReviewRequest, db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)):
    result = await db.execute(text("""UPDATE review_projects SET status = :status, review_decision = :decision,
        review_comment = :comment, updated_at = NOW() WHERE id = :id AND tenant_id = :tenant_id"""), {
        "status": req.decision, "decision": req.decision, "comment": req.comment,
        "id": req.project_id, "tenant_id": user["tenant_id"]})
    if result.rowcount == 0: raise HTTPException(404, detail="审查项目不存在")
    await db.execute(text("""INSERT INTO review_actions (id, project_id, user_id, decision, comment)
        VALUES (:id, :project_id, :user_id, :decision, :comment)"""), {
        "id": uuid4(), "project_id": req.project_id, "user_id": user["user_id"],
        "decision": req.decision, "comment": req.comment})
    return {"status": req.decision, "project_id": req.project_id, "message": "人工复核结果已保存"}

@router.get("/projects")
async def list_projects(db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)):
    rows = (await db.execute(text("""SELECT id, operation, status, source_files, report, review_decision, review_comment, created_at
        FROM review_projects WHERE tenant_id = :tenant_id ORDER BY created_at DESC"""), {"tenant_id": user["tenant_id"]})).mappings().all()
    return {"items": [dict(row) for row in rows]}

@router.get("/health")
async def studio_health():
    return {"status": "ok", "agents": ["qa", "land", "accounting"], "human_review": True}




