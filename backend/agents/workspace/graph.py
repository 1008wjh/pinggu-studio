from __future__ import annotations
from langgraph.graph import END, StateGraph
from backend.agents.workspace.nodes import classify_operation, execute_operation
from backend.agents.workspace.state import WorkspaceState

def build_workspace_graph():
    graph = StateGraph(WorkspaceState)
    graph.add_node("classify", classify_operation)
    graph.add_node("execute", execute_operation)
    graph.set_entry_point("classify")
    graph.add_edge("classify", "execute")
    graph.add_edge("execute", END)
    return graph.compile()
