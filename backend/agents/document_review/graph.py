from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from backend.agents.document_review.state import DocumentReviewState, STEP_EXTRACT, STEP_RISK, STEP_REPORT
from backend.agents.document_review.prompts import REVIEW_SYSTEM, EXTRACT_PROMPT, RISK_PROMPT, REPORT_PROMPT
from backend.core.llm_factory import get_llm
from backend.services.document_workspace import extract_document

_MEMORY = MemorySaver()

def _text(response: Any) -> str:
    return response.text if hasattr(response, "text") else str(getattr(response, "content", response))

def _read(paths: list[str]) -> str:
    blocks = []
    for raw in paths:
        try:
            data = extract_document(raw, max_rows=None)
            blocks.append(f"文件：{Path(raw).name}\n{json.dumps(data, ensure_ascii=False, default=str)}")
        except Exception as exc:
            blocks.append(f"文件：{Path(raw).name}\n解析失败：{exc}")
    return "\n\n".join(blocks)[:60000]

async def _ask(prompt: str) -> str:
    try:
        result = await get_llm("summarize", temperature=0.1).ainvoke([
            SystemMessage(content=REVIEW_SYSTEM), HumanMessage(content=prompt)
        ])
        return _text(result)
    except Exception:
        return "模型暂不可用，已完成材料解析；请人工核对主体、金额、期限、付款、责任和资格条件。"

def _review(state: DocumentReviewState, step: str, output: dict[str, Any], summary: str) -> DocumentReviewState:
    state["current_step"] = step
    state["status"] = "pending_review"
    state["review_context"] = {"step": step, "summary": summary, "ai_output": output, "original_data": output}
    state["step_outputs"] = {**(state.get("step_outputs") or {}), step: output}
    state["checkpoint_version"] = int(state.get("checkpoint_version", 0)) + 1
    return state

async def extract_step(state: DocumentReviewState) -> DocumentReviewState:
    content = _read(state.get("file_paths", []))
    answer = await _ask(EXTRACT_PROMPT.format(content=content))
    return _review(state, STEP_EXTRACT, {"document_type": state.get("document_type", "contract"), "analysis": answer, "source_files": [Path(p).name for p in state.get("file_paths", [])]}, "已完成文档解析和关键字段抽取")

async def risk_step(state: DocumentReviewState) -> DocumentReviewState:
    content = _read(state.get("file_paths", []))
    context = ""
    try:
        from backend.agents.studio.graph import _knowledge_context
        context, _ = await _knowledge_context(content[:3000], state.get("tenant_id", "tenant_default"), "document_review")
    except Exception:
        pass
    answer = await _ask(RISK_PROMPT.format(content=content, context=context))
    return _review(state, STEP_RISK, {"risk_analysis": answer, "knowledge_context": context[:8000]}, "已完成条款风险和合规项分析")

async def report_step(state: DocumentReviewState) -> DocumentReviewState:
    outputs = state.get("step_outputs") or {}
    answer = await _ask(REPORT_PROMPT.format(extracted=outputs.get(STEP_EXTRACT, {}), risks=outputs.get(STEP_RISK, {})))
    state["current_step"] = STEP_REPORT
    state["status"] = "pending_review"
    state["review_context"] = {"step": STEP_REPORT, "summary": "已生成审查报告，等待最终人工确认", "ai_output": {"report": answer}, "original_data": outputs}
    state["step_outputs"] = {**outputs, STEP_REPORT: {"report": answer}}
    state["checkpoint_version"] = int(state.get("checkpoint_version", 0)) + 1
    return state

def human_gate(state: DocumentReviewState) -> DocumentReviewState:
    decision = interrupt(state.get("review_context", {}))
    state["pending_action"] = decision if isinstance(decision, dict) else {"action": str(decision)}
    action = state["pending_action"].get("action", "approve")
    if action == "return":
        state["status"] = "pending_review"
        state["current_step"] = state["pending_action"].get("step", state.get("current_step", STEP_EXTRACT))
        return state
    if state.get("current_step") == STEP_REPORT:
        state["status"] = "completed"
    return state

def _next(state: DocumentReviewState) -> str:
    if state.get("status") == "completed": return "finish"
    if state.get("pending_action", {}).get("action") == "return": return state.get("current_step", STEP_EXTRACT)
    return {STEP_EXTRACT: STEP_RISK, STEP_RISK: STEP_REPORT, STEP_REPORT: "finish"}.get(state.get("current_step", STEP_EXTRACT), "finish")

def build_document_review_graph():
    builder = StateGraph(DocumentReviewState)
    builder.add_node(STEP_EXTRACT, extract_step); builder.add_node(STEP_RISK, risk_step); builder.add_node(STEP_REPORT, report_step); builder.add_node("human_gate", human_gate)
    builder.add_edge(START, STEP_EXTRACT); builder.add_edge(STEP_EXTRACT, "human_gate"); builder.add_edge(STEP_RISK, "human_gate"); builder.add_edge(STEP_REPORT, "human_gate")
    builder.add_conditional_edges("human_gate", _next, {STEP_EXTRACT: STEP_EXTRACT, STEP_RISK: STEP_RISK, STEP_REPORT: STEP_REPORT, "finish": END})
    return builder.compile(checkpointer=_MEMORY)
