"""工作室 Agent 的通用重试工具。"""
from __future__ import annotations
import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
T = TypeVar('T')

async def run_with_retry(operation: Callable[[], Awaitable[T]], retries: int = 2, delay: float = 0.5) -> T:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await operation()
        except Exception as exc:
            last = exc
            if attempt < retries:
                await asyncio.sleep(delay * (attempt + 1))
    assert last is not None
    raise last

FALLBACK_MESSAGES = {
    'domain_qa': '专业问答暂时无法调用模型，请稍后重试。',
    'land_assessment': '土地评估已保存材料，模型恢复后可重新生成。',
    'document_workspace': '文档工作台暂时无法处理该文件。',
}
