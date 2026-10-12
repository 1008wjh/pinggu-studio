"""一个样本一个隔离子进程：复用原业务函数，模拟审核不写业务数据库。"""
import asyncio
import json
import sys
import time
from pathlib import Path
from .telemetry import Telemetry, hardware


async def evaluate(sample):
    telemetry = Telemetry()
    telemetry.install()
    # graph import 的 get_llm/extract_document 会指向本进程的透明观测代理。
    from .runner import _call_existing, _judge, _similarity
    hardware_start = hardware()
    started = time.perf_counter()
    predicted = await _call_existing(sample)
    elapsed = (time.perf_counter()-started)*1000
    business_usage = telemetry.result()
    result = dict(predicted_answer=predicted, similarity=_similarity(predicted, sample['reference_answer']), total_ms=elapsed, telemetry=business_usage, **hardware_start)
    result['telemetry_json'] = json.dumps({'scope':'业务调用，不含Judge', 'calls':telemetry.calls, 'hardware_end':hardware(), 'retrieval_scope':'Milvus向量查询，含连接；不含embedding及BM25', 'errors':telemetry.errors}, ensure_ascii=False)
    result['judge_score'] = None
    if telemetry.errors:
        result['error'] = '; '.join(telemetry.errors)
    else:
        try:
            # judge 使用工厂类原始方法，不计入业务观测代理。
            score, reason, judge_usage, judge_ms = await _judge(sample['question'], sample['reference_answer'], predicted)
            combined = {key: (business_usage.get(key) or 0) + (judge_usage.get(key) or 0) for key in ('prompt_tokens','completion_tokens','total_tokens','cache_saved_tokens')}
            combined['cache_hit'] = int(bool(business_usage.get('cache_hit') or judge_usage.get('cache_hit')))
            combined['usage_source'] = 'provider' if any(c.get('prompt_tokens') is not None for c in telemetry.calls) else judge_usage.get('usage_source','estimated')
            result.update(judge_score=score, judge_reason=reason, usage=combined, judge_usage=json.dumps(judge_usage), judge_ms=judge_ms, error=None)
        except Exception as exc:
            result['error'] = 'Judge失败: ' + type(exc).__name__
    return result


if __name__ == '__main__':
    request_path, output_path = map(Path, sys.argv[1:3])
    try:
        sample = json.loads(request_path.read_text(encoding='utf-8'))
        result = asyncio.run(evaluate(sample))
    except Exception as exc:
        result = {'error': '评测执行失败: ' + type(exc).__name__, 'judge_score': None, 'usage': {"usage_source":"unavailable"}}
    output_path.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
