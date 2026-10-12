from __future__ import annotations
import json, shutil, tempfile
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from backend.agents.workspace.graph import build_workspace_graph

router = APIRouter()
_UPLOAD_ROOT = Path(tempfile.gettempdir()) / "pinggu_agent_workspace"
_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

async def _save_upload(upload: UploadFile, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / Path(upload.filename or "upload.bin").name
    with destination.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle)
    return destination

async def _run(operation: str, paths: list[Path], options: dict | None = None, output_path: Path | None = None) -> dict:
    graph = build_workspace_graph()
    state = {"operation": operation, "file_paths": [str(path) for path in paths], "options": options or {}, "output_path": str(output_path) if output_path else ""}
    try:
        result = await graph.ainvoke(state)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "WORKSPACE_ERROR", "message": str(exc)}) from exc
    if result.get("error"):
        raise HTTPException(status_code=400, detail={"code": "WORKSPACE_ERROR", "message": result["error"]})
    return result.get("result", {})

@router.post("/extract")
async def extract_document(file: Annotated[UploadFile, File(...)], max_rows: int | None = 200):
    folder = _UPLOAD_ROOT / next(tempfile._get_candidate_names())
    path = await _save_upload(file, folder)
    return await _run("extract", [path], {"max_rows": max_rows})

@router.post("/summarize")
async def summarize_document(file: Annotated[UploadFile, File(...)], max_rows: int | None = None):
    """调用 DeepSeek 对抽取后的文档内容进行工作室业务摘要。"""
    folder = _UPLOAD_ROOT / next(tempfile._get_candidate_names())
    path = await _save_upload(file, folder)
    return await _run("summarize", [path], {"max_rows": max_rows})

@router.post("/spreadsheet/inspect")
async def inspect_spreadsheet(file: Annotated[UploadFile, File(...)], max_rows: int = 20):
    folder = _UPLOAD_ROOT / next(tempfile._get_candidate_names())
    path = await _save_upload(file, folder)
    return await _run("inspect", [path], {"max_rows": max_rows})

@router.post("/spreadsheet/merge")
async def merge_spreadsheets(files: Annotated[list[UploadFile], File(...)], sheet_name: str = "merged"):
    if not files:
        raise HTTPException(status_code=400, detail="至少上传一个表格文件")
    folder = _UPLOAD_ROOT / next(tempfile._get_candidate_names())
    paths = [await _save_upload(upload, folder) for upload in files]
    output_path = folder / "merged_result.xlsx"
    result = await _run("merge", paths, {"sheet_name": sheet_name}, output_path)
    return FileResponse(output_path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename="merged_result.xlsx", headers={"X-Merge-Metadata": json.dumps(result, ensure_ascii=True)})

@router.get("/health")
async def workspace_health():
    return {"status": "ok", "agent": "document_workspace", "operations": ["extract", "summarize", "inspect", "merge"]}
