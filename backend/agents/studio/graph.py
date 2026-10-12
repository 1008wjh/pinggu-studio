"""工作室 LangGraph：统一入口、知识检索、材料解析和待人工复核状态。"""
from __future__ import annotations
import asyncio
from pathlib import Path
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from backend.agents.studio.state import StudioState
from backend.agents.studio.prompts import DOMAIN_QA_SYSTEM, LAND_ASSESSMENT_PROMPT
from backend.core.llm_factory import get_llm
from backend.services.document_workspace import extract_document

async def _knowledge_context(query: str, tenant_id: str = "tenant_default", agent_key: str = "domain_qa") -> tuple[str, list[str]]:
    """只检索当前智能体绑定的知识库，并使用 BM25 + 向量 0.5/0.5 融合。"""
    from sqlalchemy import text
    from backend.dependencies import AsyncSessionLocal
    from backend.services.knowledge_rag import IsolatedKnowledgeRAG
    try:
        async with AsyncSessionLocal() as db:
            rows=(await db.execute(text("""SELECT b.id FROM knowledge_bases b
                JOIN knowledge_base_agents a ON a.knowledge_base_id=b.id
                WHERE b.tenant_id=:tenant AND b.status='active' AND a.agent_key=:agent
                ORDER BY b.created_at"""), {"tenant":tenant_id,"agent":agent_key})).scalars().all()
            merged=[]
            for kb_id in rows:
                merged.extend(await IsolatedKnowledgeRAG.search(db,str(kb_id),query,top_k=8))
        merged=sorted(merged,key=lambda item:item.get("score",0),reverse=True)[:8]
        sources=[]
        for item in merged:
            source=item.get("metadata",{}).get("source_name","")
            if source and source not in sources: sources.append(source)
        return "\n\n".join(item.get("content","") for item in merged), sources
    except Exception:
        return "（当前智能体未绑定可用知识库或知识库暂不可用）", []

def _content_from_files(paths: list[str]) -> str:
    blocks = []
    for raw_path in paths:
        data = extract_document(raw_path, max_rows=None)
        blocks.append(f"文件：{Path(raw_path).name}\n{data}")
    return "\n\n".join(blocks)[:60000]

def _text(response) -> str:
    return response.text if hasattr(response, "text") else str(response.content)

def _offline_report(operation: str, content: str) -> str:
    labels = {"land": "文书要点摘要"}
    return (f"【{labels.get(operation, operation)}】\n\n"
            "系统已完成文档解析，当前为离线演示结果。\n"
            f"材料摘要：{content[:800]}\n\n"
            "待人工复核：请核对主体、日期、金额、权属、附件完整性及适用依据。")

async def execute_studio(state: StudioState) -> StudioState:
    operation = state.get("operation", "qa")
    paths = state.get("file_paths", [])
    message = state.get("message", "")
    if operation == "qa":
        context, sources = await _knowledge_context(message, state.get("tenant_id", "tenant_default"))
        prompt = f"问题：{message}\n\n知识库片段：{context}"
        try:
            response = await get_llm("qa", temperature=0.2).ainvoke([SystemMessage(content=DOMAIN_QA_SYSTEM), HumanMessage(content=prompt)])
            answer = _text(response)
        except Exception:
            answer = "当前模型不可用。建议先检查 DeepSeek 配置；已保留问题，稍后可重试。\n\n" + context[:800]
        state["result"] = {"answer": answer, "sources": sources, "status": "completed"}
        return state
    if not paths:
        raise ValueError("至少需要一个材料文件")
    content = _content_from_files(paths)
    if operation == "land":
        context, _ = await _knowledge_context(content[:3000], state.get("tenant_id", "tenant_default"), agent_key="land_assessment")
    else:
        context = ""
    templates = {"land": LAND_ASSESSMENT_PROMPT}
    if operation not in templates:
        raise ValueError(f"不支持的工作室 Agent: {operation}")
    prompt = templates[operation].format(content=content, context=context)
    try:
        response = await get_llm("summarize", temperature=0.1).ainvoke([HumanMessage(content=prompt)])
        report = _text(response)
    except Exception:
        report = _offline_report(operation, content)
    state["result"] = {"report": report, "status": "pending_review", "operation": operation,
                       "source_files": [Path(path).name for path in paths]}
    return state

def build_studio_graph():
    builder = StateGraph(StudioState)
    builder.add_node("execute", execute_studio)
    builder.set_entry_point("execute")
    builder.add_edge("execute", END)
    return builder.compile()



