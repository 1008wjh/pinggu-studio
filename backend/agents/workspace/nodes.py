from __future__ import annotations
from langchain_core.messages import HumanMessage, SystemMessage
from backend.services.document_workspace import extract_document, inspect_spreadsheet, merge_spreadsheets
from backend.agents.workspace.prompts import SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_PROMPT
from backend.core.llm_factory import get_llm
from backend.agents.workspace.state import WorkspaceState

def classify_operation(state: WorkspaceState) -> WorkspaceState:
    operation = (state.get("operation") or "extract").strip().lower()
    aliases = {"document_extract": "extract", "doc_extract": "extract", "spreadsheet_inspect": "inspect", "sheet_inspect": "inspect", "spreadsheet_merge": "merge", "sheet_merge": "merge", "document_summary": "summarize", "summary": "summarize"}
    state["operation"] = aliases.get(operation, operation)
    return state

def execute_operation(state: WorkspaceState) -> WorkspaceState:
    operation = state.get("operation", "extract"); paths = state.get("file_paths", []); options = state.get("options", {})
    if not paths: raise ValueError("至少需要一个输入文件")
    if operation == "extract": state["result"] = extract_document(paths[0], max_rows=options.get("max_rows", None))
    elif operation == "summarize":
        extracted = extract_document(paths[0], max_rows=options.get("max_rows", None))
        content = str(extracted)
        if len(content) > 50000: content = content[:50000] + "\n[内容过长，已截取前 50000 个字符]"
        llm = get_llm("summarize", temperature=0.2)
        response = llm.invoke([SystemMessage(content=SUMMARY_SYSTEM_PROMPT), HumanMessage(content=SUMMARY_USER_PROMPT.format(file_name=paths[0], content=content))])
        state["result"] = {"file_name": paths[0].split("\\")[-1], "summary": response.text if hasattr(response, "text") else str(response.content), "source_type": extracted.get("type")}
    elif operation == "inspect": state["result"] = inspect_spreadsheet(paths[0], max_rows=int(options.get("max_rows", 20)))
    elif operation == "merge":
        output_path = state.get("output_path")
        if not output_path: raise ValueError("合并表格缺少输出路径")
        state["result"] = merge_spreadsheets(paths, output_path, sheet_name=options.get("sheet_name", "merged"))
    else: raise ValueError(f"不支持的工作台操作: {operation}")
    return state
