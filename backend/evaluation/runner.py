from __future__ import annotations
import asyncio, json, re, time, os, sys, tempfile, subprocess
from pathlib import Path
from typing import Any
from . import store

_TASKS: dict[str, asyncio.Task] = {}

def _snapshot() -> dict[str, float]:
    result={"cpu_percent":0.0,"memory_percent":0.0,"gpu_memory_mb":0.0,"gpu_util_percent":0.0}
    try:
        import psutil; result["cpu_percent"]=psutil.cpu_percent(interval=None); result["memory_percent"]=psutil.virtual_memory().percent
    except Exception: pass
    try:
        import torch
        if torch.cuda.is_available(): result["gpu_memory_mb"]=torch.cuda.memory_allocated()/1024/1024
    except Exception: pass
    return result

def _similarity(predicted: str, reference: str) -> float:
    a=set(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+",predicted.lower())); b=set(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+",reference.lower()))
    return round(len(a & b)/max(len(a | b),1),4)

def _text(value: Any) -> str: return value.text if hasattr(value,"text") else str(getattr(value,"content",value))

async def _call_existing(sample: dict) -> str:
    category=sample.get("category") or "legal_qa"; question=sample["question"]; paths=[sample["attachment_path"]] if sample.get("attachment_path") else []
    if category in {"legal_qa", "document_summary"}:
        from backend.agents.studio.graph import build_studio_graph
        operation="qa" if category=="legal_qa" else "land"
        state=await build_studio_graph().ainvoke({"operation":operation,"message":question,"file_paths":paths,"tenant_id":"evaluation"})
        result=state.get("result",{}); return result.get("answer") or result.get("report") or ""
    from backend.agents.document_review.graph import build_document_review_graph
    from langgraph.types import Command
    graph=build_document_review_graph(); thread=f"evaluation-{sample['id']}"
    await graph.ainvoke({"workflow_id":thread,"thread_id":thread,"file_paths":paths,"document_type":"contract","instruction":question,"tenant_id":"evaluation"},config={"configurable":{"thread_id":thread}})
    for _ in range(4):
        state=await graph.aget_state({"configurable":{"thread_id":thread}})
        if not state.next: break
        await graph.ainvoke(Command(resume={"action":"approve"}),config={"configurable":{"thread_id":thread}})
    state=await graph.aget_state({"configurable":{"thread_id":thread}}); outputs=state.values.get("step_outputs",{})
    return str(outputs.get("step3_report",{}).get("report") or outputs.get("step2_risk_review",{}).get("risk_analysis") or "")

async def _judge(question: str, reference: str, predicted: str) -> tuple[float,str,dict,int]:
    from backend.core.llm_factory import get_llm
    prompt=f"请作为严格评测员，按1到5分评价模型回答与标准答案的一致性，只返回JSON。题目：{question}\n标准答案：{reference}\n模型回答：{predicted}\n格式：{{\"score\": 1到5, \"reason\": \"一句话\"}}"
    try:
        started=time.perf_counter(); response=await get_llm("qa",temperature=0).ainvoke(prompt); text=_text(response)
        match=re.search(r"(?:score|分数)\D*([1-5])",text,re.I); score=float(match.group(1)) if match else 1.0
        usage = _usage_from_response(response) or {"prompt_tokens":max(1,len(prompt)//4),"completion_tokens":max(1,len(text)//4),"total_tokens":max(1,len(prompt)//4)+max(1,len(text)//4),"usage_source":"estimated"}
        return score,text,usage,int((time.perf_counter()-started)*1000)
    except Exception: return 1.0,"Judge调用失败",{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0,"usage_source":"unavailable"},0

def _usage_from_response(response: Any) -> dict | None:
    usage = getattr(response, "usage_metadata", None) or {}
    raw = (getattr(response, "response_metadata", None) or {}).get("token_usage", {})
    prompt = usage.get("input_tokens", raw.get("prompt_tokens")); completion = usage.get("output_tokens", raw.get("completion_tokens")); total = usage.get("total_tokens", raw.get("total_tokens"))
    cached = (usage.get("input_token_details") or {}).get("cache_read", raw.get("prompt_cache_hit_tokens", (raw.get("prompt_tokens_details") or {}).get("cached_tokens")))
    if prompt is None and completion is None and total is None: return None
    return {"prompt_tokens":int(prompt or 0),"completion_tokens":int(completion or 0),"total_tokens":int(total if total is not None else (prompt or 0)+(completion or 0)),"cache_saved_tokens":int(cached or 0),"cache_hit":int(bool(cached)),"usage_source":"provider"}

def _run_isolated(sample: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="pinggu-eval-") as folder:
        request=os.path.join(folder,"sample.json"); output=os.path.join(folder,"result.json")
        with open(request,"w",encoding="utf-8") as handle: json.dump(sample,handle,ensure_ascii=False)
        completed=subprocess.run([sys.executable,"-m","backend.evaluation.worker",request,output],cwd=str(Path(__file__).resolve().parents[2]),capture_output=True,text=True,timeout=900)
        if completed.returncode != 0: raise RuntimeError(completed.stderr[-2000:] or "evaluation worker failed")
        with open(output,encoding="utf-8") as handle: return json.load(handle)

async def run_task(task_id: str) -> None:
    store.update_task(task_id,status="running",started_at=store.now())
    rows=store.samples(task_id)
    try:
        for index,sample in enumerate(rows):
            result=await asyncio.to_thread(_run_isolated,sample); usage=result.get("usage") or {}; telemetry=result.get("telemetry") or {}
            store.update_sample(sample["id"],predicted_answer=result.get("predicted_answer",""),judge_score=result.get("judge_score"),judge_reason=result.get("judge_reason",""),similarity=result.get("similarity",0),prompt_tokens=usage.get("prompt_tokens",0),completion_tokens=usage.get("completion_tokens",0),total_tokens=usage.get("total_tokens",0),usage_source=usage.get("usage_source","unavailable"),cache_hit=usage.get("cache_hit",0),cache_saved_tokens=usage.get("cache_saved_tokens",0),parse_ms=telemetry.get("parse_ms",0),retrieval_ms=telemetry.get("retrieval_ms",0),llm_ms=telemetry.get("llm_ms",0),judge_ms=result.get("judge_ms",0),total_ms=result.get("total_ms",0),telemetry_json=result.get("telemetry_json"),error=result.get("error"),cpu_percent=result.get("cpu_percent"),memory_percent=result.get("memory_percent"),gpu_memory_mb=result.get("gpu_memory_mb"),gpu_util_percent=result.get("gpu_util_percent"))
            store.update_task(task_id,completed_samples=index+1)
        store.update_task(task_id,status="completed",finished_at=store.now())
    except asyncio.CancelledError:
        store.update_task(task_id,status="stopped",finished_at=store.now()); raise
    except Exception as exc:
        store.update_task(task_id,status="failed",finished_at=store.now(),error=str(exc))

def start(task_id: str) -> None:
    old=_TASKS.get(task_id)
    if old and not old.done(): return
    _TASKS[task_id]=asyncio.create_task(run_task(task_id))

def stop(task_id: str) -> None:
    task=_TASKS.get(task_id)
    if task and not task.done(): task.cancel()
