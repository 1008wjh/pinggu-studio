from __future__ import annotations
from typing import Any, TypedDict
class WorkspaceState(TypedDict, total=False):
    operation: str
    file_paths: list[str]
    output_path: str
    options: dict[str, Any]
    result: dict[str, Any]
    error: str
