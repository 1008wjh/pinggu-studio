from typing import Any, TypedDict
class StudioState(TypedDict, total=False):
    operation: str
    message: str
    file_paths: list[str]
    tenant_id: str
    content: str
    context: str
    result: dict[str, Any]
