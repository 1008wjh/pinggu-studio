from __future__ import annotations
import json, sqlite3
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2] / "data"
DB_PATH = ROOT / "evaluations.sqlite3"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "scripts" / "evaluation_schema.sql"

def now() -> str: return datetime.now(timezone.utc).isoformat()

def connect() -> sqlite3.Connection:
    ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        conn.execute("ALTER TABLE evaluation_tasks ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'tenant_default'")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    for column, definition in (("judge_reason", "TEXT"), ("usage_source", "TEXT DEFAULT 'unavailable'"), ("telemetry_json", "TEXT"), ("judge_ms", "REAL DEFAULT 0")):
        try:
            conn.execute(f"ALTER TABLE evaluation_samples ADD COLUMN {column} {definition}"); conn.commit()
        except sqlite3.OperationalError:
            pass
    return conn

def create_task(name: str, category: str, samples: list[dict], tenant_id: str = "tenant_default") -> str:
    task_id = str(uuid4()); conn = connect()
    try:
        conn.execute("INSERT INTO evaluation_tasks(id,tenant_id,name,category,total_samples,created_at) VALUES(?,?,?,?,?,?)", (task_id,tenant_id,name,category,len(samples),now()))
        for sample in samples:
            conn.execute("""INSERT INTO evaluation_samples(id,task_id,question,reference_answer,category,attachment_path,created_at)
                VALUES(?,?,?,?,?,?,?)""", (str(uuid4()),task_id,str(sample.get("question", "")),str(sample.get("reference_answer", "")),sample.get("category") or category,sample.get("attachment_path"),now()))
        conn.commit(); return task_id
    finally: conn.close()

def add_sample(task_id: str, sample: dict) -> str:
    sample_id=str(uuid4()); conn=connect()
    try:
        conn.execute("INSERT INTO evaluation_samples(id,task_id,question,reference_answer,category,attachment_path,created_at) VALUES(?,?,?,?,?,?,?)", (sample_id,task_id,sample["question"],sample["reference_answer"],sample.get("category"),sample.get("attachment_path"),now()))
        conn.execute("UPDATE evaluation_tasks SET total_samples=total_samples+1 WHERE id=?", (task_id,)); conn.commit(); return sample_id
    finally: conn.close()

def task(task_id: str) -> dict | None:
    conn=connect()
    try:
        row=conn.execute("SELECT * FROM evaluation_tasks WHERE id=?",(task_id,)).fetchone(); return dict(row) if row else None
    finally: conn.close()

def samples(task_id: str) -> list[dict]:
    conn=connect()
    try: return [dict(row) for row in conn.execute("SELECT * FROM evaluation_samples WHERE task_id=? ORDER BY created_at",(task_id,)).fetchall()]
    finally: conn.close()

def list_tasks() -> list[dict]:
    conn=connect()
    try: return [dict(row) for row in conn.execute("SELECT * FROM evaluation_tasks ORDER BY created_at DESC").fetchall()]
    finally: conn.close()

def update_task(task_id: str, **fields) -> None:
    if not fields: return
    conn=connect(); assignments=", ".join(f"{key}=?" for key in fields)
    try: conn.execute(f"UPDATE evaluation_tasks SET {assignments} WHERE id=?", (*fields.values(),task_id)); conn.commit()
    finally: conn.close()

def update_sample(sample_id: str, **fields) -> None:
    if not fields: return
    conn=connect(); assignments=", ".join(f"{key}=?" for key in fields)
    try: conn.execute(f"UPDATE evaluation_samples SET {assignments} WHERE id=?", (*fields.values(),sample_id)); conn.commit()
    finally: conn.close()

def report(task_id: str) -> dict:
    rows=samples(task_id); t=task(task_id)
    scored=[r for r in rows if r.get("judge_score") is not None]
    # A sample can finish with a recorded business/Judge error and therefore
    # have no score.  It still counts as completed work, and must be visible
    # in the failed total instead of silently disappearing from the report.
    completed_rows=[r for r in rows if r.get("predicted_answer") is not None or r.get("error")]
    errored=sum(1 for r in rows if r.get("error"))
    avg=lambda key: round(sum(float(r.get(key) or 0) for r in rows)/max(len(rows),1),2)
    return {"task":t,"samples":rows,"summary":{"total":len(rows),"completed":len(completed_rows),"passed":sum(1 for r in scored if float(r["judge_score"])>=3),"failed":errored+sum(1 for r in scored if float(r["judge_score"])<3),"avg_judge_score":round(sum(float(r["judge_score"]) for r in scored)/max(len(scored),1),2),"avg_similarity":avg("similarity"),"avg_prompt_tokens":avg("prompt_tokens"),"avg_completion_tokens":avg("completion_tokens"),"avg_total_tokens":avg("total_tokens"),"cache_hit_rate":round(sum(int(r.get("cache_hit") or 0) for r in rows)/max(len(rows),1),2),"avg_retrieval_ms":avg("retrieval_ms"),"avg_llm_ms":avg("llm_ms"),"avg_total_ms":avg("total_ms"),"avg_cpu_percent":avg("cpu_percent"),"avg_memory_percent":avg("memory_percent"),"avg_gpu_memory_mb":avg("gpu_memory_mb"),"avg_gpu_util_percent":avg("gpu_util_percent")}}
