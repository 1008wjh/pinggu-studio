"""仅在评测子进程安装的透明观测代理；不影响在线业务进程。"""
import time
import subprocess
from functools import wraps


def hardware():
    values = dict(cpu_percent=None, memory_percent=None, gpu_memory_mb=None, gpu_util_percent=None)
    try:
        import psutil
        values.update(cpu_percent=psutil.cpu_percent(interval=0.1), memory_percent=psutil.virtual_memory().percent)
    except ImportError:
        pass
    try:
        output = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,utilization.gpu', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=2, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        rows = [[float(x.strip()) for x in line.split(',')] for line in output.stdout.strip().splitlines()]
        if rows:
            values.update(gpu_memory_mb=sum(r[0] for r in rows), gpu_util_percent=sum(r[1] for r in rows)/len(rows))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return values


class Telemetry:
    def __init__(self):
        self.calls = []
        self.parse_ms = 0.0
        self.retrieval_ms = 0.0
        self.llm_ms = 0.0
        self.errors = []

    def observe_response(self, response):
        usage = getattr(response, 'usage_metadata', None) or {}
        raw = (getattr(response, 'response_metadata', None) or {}).get('token_usage', {})
        prompt = usage.get('input_tokens', raw.get('prompt_tokens'))
        completion = usage.get('output_tokens', raw.get('completion_tokens'))
        cached = (usage.get('input_token_details') or {}).get('cache_read', raw.get('prompt_cache_hit_tokens', (raw.get('prompt_tokens_details') or {}).get('cached_tokens')))
        self.calls.append(dict(prompt_tokens=prompt, completion_tokens=completion, total_tokens=usage.get('total_tokens', raw.get('total_tokens')), cache_saved_tokens=cached))

    def result(self):
        def total(key):
            values = [c[key] for c in self.calls]
            return sum(values) if values and all(v is not None for v in values) else None
        cached = total('cache_saved_tokens')
        return dict(prompt_tokens=total('prompt_tokens'), completion_tokens=total('completion_tokens'), total_tokens=total('total_tokens'), cache_saved_tokens=cached, cache_hit=None if cached is None else int(cached > 0), parse_ms=self.parse_ms, retrieval_ms=self.retrieval_ms, llm_ms=self.llm_ms)

    def install(self):
        # 必须在导入业务 graph 之前安装；仅限 subprocess worker。
        from backend.services import document_workspace
        from backend.services.knowledge_rag import IsolatedKnowledgeRAG
        from backend.core import llm_factory
        original_parse = document_workspace.extract_document
        original_search = IsolatedKnowledgeRAG.vector_search
        original_llm = llm_factory.get_llm
        telemetry = self

        @wraps(original_parse)
        def parse(*args, **kwargs):
            start = time.perf_counter()
            try: return original_parse(*args, **kwargs)
            except Exception as exc:
                telemetry.errors.append('文档解析失败: ' + type(exc).__name__)
                raise
            finally: telemetry.parse_ms += (time.perf_counter()-start)*1000

        def search(cls, *args, **kwargs):
            start = time.perf_counter()
            try: return original_search(*args, **kwargs)
            finally: telemetry.retrieval_ms += (time.perf_counter()-start)*1000

        class ObservedModel:
            def __init__(self, model): self.model = model
            async def ainvoke(self, *args, **kwargs):
                start = time.perf_counter()
                try:
                    response = await self.model.ainvoke(*args, **kwargs)
                    telemetry.observe_response(response)
                    return response
                except Exception as exc:
                    telemetry.errors.append('业务模型调用失败: ' + type(exc).__name__)
                    raise
                finally: telemetry.llm_ms += (time.perf_counter()-start)*1000
            def __getattr__(self, name): return getattr(self.model, name)

        document_workspace.extract_document = parse
        IsolatedKnowledgeRAG.vector_search = classmethod(search)
        llm_factory.get_llm = lambda *args, **kwargs: ObservedModel(original_llm(*args, **kwargs))
