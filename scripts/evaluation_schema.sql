-- LLM 应用评测模块 SQLite 建表语句
CREATE TABLE IF NOT EXISTS evaluation_tasks (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL DEFAULT 'tenant_default', name TEXT NOT NULL, category TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft', total_samples INTEGER NOT NULL DEFAULT 0,
  completed_samples INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
  started_at TEXT, finished_at TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS evaluation_samples (
  id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES evaluation_tasks(id) ON DELETE CASCADE,
  question TEXT NOT NULL, reference_answer TEXT NOT NULL, category TEXT NOT NULL,
  attachment_path TEXT, predicted_answer TEXT, judge_score REAL, judge_reason TEXT, similarity REAL,
  prompt_tokens INTEGER DEFAULT 0, completion_tokens INTEGER DEFAULT 0, total_tokens INTEGER DEFAULT 0, usage_source TEXT DEFAULT 'unavailable',
  cache_hit INTEGER DEFAULT 0, cache_saved_tokens INTEGER DEFAULT 0,
  parse_ms REAL DEFAULT 0, retrieval_ms REAL DEFAULT 0, llm_ms REAL DEFAULT 0, total_ms REAL DEFAULT 0,
  cpu_percent REAL, memory_percent REAL, gpu_memory_mb REAL, gpu_util_percent REAL,
  telemetry_json TEXT, judge_ms REAL DEFAULT 0, error TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evaluation_samples_task ON evaluation_samples(task_id);
