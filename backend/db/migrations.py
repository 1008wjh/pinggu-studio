"""工作室数据库幂等迁移。旧教育表保留，新增业务只使用工作室表。"""
from sqlalchemy import text
from backend.dependencies import AsyncSessionLocal
from backend.core.logger import get_logger
logger = get_logger(__name__)
_MIGRATIONS = [
    # Older databases may not have the role column at all.  Keep this as one
    # PostgreSQL statement because asyncpg prepares each migration statement
    # and rejects multiple commands in a single prepared query.
    ("users_role_compat", "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(32)"),
    ("knowledge_documents", """CREATE TABLE IF NOT EXISTS knowledge_documents (
        id UUID PRIMARY KEY, tenant_id VARCHAR(128) NOT NULL, user_id UUID,
        title VARCHAR(256) NOT NULL, source_name VARCHAR(512) NOT NULL,
        domain VARCHAR(64) NOT NULL DEFAULT 'studio', file_type VARCHAR(32), storage_path TEXT,
        status VARCHAR(24) NOT NULL DEFAULT 'processing', chunk_count INT NOT NULL DEFAULT 0,
        error_message TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )"""),
    ("knowledge_document_chunks", """CREATE TABLE IF NOT EXISTS knowledge_document_chunks (
        id UUID PRIMARY KEY, document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
        chunk_index INT NOT NULL, content TEXT NOT NULL, metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(document_id, chunk_index)
    )"""),
    ("knowledge_bases", """CREATE TABLE IF NOT EXISTS knowledge_bases (
        id UUID PRIMARY KEY, tenant_id VARCHAR(128) NOT NULL, name VARCHAR(128) NOT NULL,
        description TEXT NOT NULL DEFAULT '', status VARCHAR(24) NOT NULL DEFAULT 'active',
        milvus_partition VARCHAR(128) NOT NULL, created_by UUID, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(tenant_id, name), UNIQUE(milvus_partition)
    )"""),
    ("knowledge_base_agents", """CREATE TABLE IF NOT EXISTS knowledge_base_agents (
        knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
        agent_key VARCHAR(64) NOT NULL, tenant_id VARCHAR(128) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(knowledge_base_id, agent_key)
    )"""),
    ("knowledge_documents_vector_status", "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS vector_count INT NOT NULL DEFAULT 0"),
    ("knowledge_documents_kb_id", "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS knowledge_base_id UUID REFERENCES knowledge_bases(id) ON DELETE CASCADE"),
    ("knowledge_chunks_kb_id", "ALTER TABLE knowledge_document_chunks ADD COLUMN IF NOT EXISTS knowledge_base_id UUID REFERENCES knowledge_bases(id) ON DELETE CASCADE"),
    ("knowledge_default_seed", """INSERT INTO knowledge_bases (id, tenant_id, name, description, milvus_partition)
        SELECT uuid_generate_v4(), 'tenant_default', '默认工作室知识库', '迁移前资料的兼容知识库', 'kb_default'
        WHERE NOT EXISTS (SELECT 1 FROM knowledge_bases WHERE tenant_id='tenant_default' AND name='默认工作室知识库')"""),
    ("knowledge_default_assign", """UPDATE knowledge_documents d SET knowledge_base_id=b.id
        FROM knowledge_bases b WHERE d.knowledge_base_id IS NULL AND b.tenant_id=d.tenant_id AND b.name='默认工作室知识库'"""),
    ("knowledge_default_qa_binding", """INSERT INTO knowledge_base_agents (knowledge_base_id, agent_key, tenant_id)
        SELECT id, 'domain_qa', tenant_id FROM knowledge_bases b WHERE b.name='默认工作室知识库'
        AND NOT EXISTS (SELECT 1 FROM knowledge_base_agents a WHERE a.knowledge_base_id=b.id AND a.agent_key='domain_qa')"""),
    ("knowledge_removed_agent_bindings", "DELETE FROM knowledge_base_agents WHERE agent_key IN ('contract_review', 'finance_review')"),
    ("knowledge_chunk_default_assign", """UPDATE knowledge_document_chunks c SET knowledge_base_id=d.knowledge_base_id
        FROM knowledge_documents d WHERE c.document_id=d.id AND c.knowledge_base_id IS NULL AND d.knowledge_base_id IS NOT NULL"""),
    ("knowledge_base_indexes", "CREATE INDEX IF NOT EXISTS idx_knowledge_bases_tenant ON knowledge_bases(tenant_id, created_at DESC)"),
    ("knowledge_doc_kb_indexes", "CREATE INDEX IF NOT EXISTS idx_knowledge_documents_kb ON knowledge_documents(knowledge_base_id, created_at DESC)"),
    ("knowledge_chunk_kb_indexes", "CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_kb ON knowledge_document_chunks(knowledge_base_id)"),
    ("review_projects", """CREATE TABLE IF NOT EXISTS review_projects (
        id UUID PRIMARY KEY, tenant_id VARCHAR(128) NOT NULL, user_id UUID,
        operation VARCHAR(32) NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'pending_review',
        source_files JSONB NOT NULL DEFAULT '[]'::jsonb, extracted_data JSONB NOT NULL DEFAULT '{}'::jsonb,
        report TEXT, review_decision VARCHAR(32), review_comment TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )"""),
    ("review_actions", """CREATE TABLE IF NOT EXISTS review_actions (
        id UUID PRIMARY KEY, project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
        user_id UUID, decision VARCHAR(32) NOT NULL, comment TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )"""),
    ("accounting_workflows", """CREATE TABLE IF NOT EXISTS accounting_workflows (
        id UUID PRIMARY KEY, tenant_id VARCHAR(128) NOT NULL, user_id UUID,
        thread_id VARCHAR(160) NOT NULL UNIQUE, status VARCHAR(32) NOT NULL DEFAULT 'pending_review',
        current_step VARCHAR(32) NOT NULL DEFAULT 'step1_classification', state JSONB NOT NULL DEFAULT '{}'::jsonb,
        checkpoint_version INT NOT NULL DEFAULT 0, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )"""),
    ("accounting_step_reviews", """CREATE TABLE IF NOT EXISTS accounting_step_reviews (
        id UUID PRIMARY KEY, workflow_id UUID NOT NULL REFERENCES accounting_workflows(id) ON DELETE CASCADE,
        step_name VARCHAR(64) NOT NULL, attempt INT NOT NULL DEFAULT 1, ai_output JSONB NOT NULL DEFAULT '{}'::jsonb,
        original_data JSONB NOT NULL DEFAULT '{}'::jsonb, confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
        risk DOUBLE PRECISION NOT NULL DEFAULT 1, decision VARCHAR(32) NOT NULL DEFAULT 'pending_review',
        edited_output JSONB, comment TEXT NOT NULL DEFAULT '', actor_user_id UUID,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), acted_at TIMESTAMPTZ
    )"""),
    ("accounting_checkpoints", """CREATE TABLE IF NOT EXISTS accounting_checkpoints (
        id UUID PRIMARY KEY, workflow_id UUID NOT NULL REFERENCES accounting_workflows(id) ON DELETE CASCADE,
        thread_id VARCHAR(160) NOT NULL, step_name VARCHAR(64) NOT NULL, state JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )"""),
    ("accounting_audit_logs", """CREATE TABLE IF NOT EXISTS accounting_audit_logs (
        id UUID PRIMARY KEY, workflow_id UUID NOT NULL REFERENCES accounting_workflows(id) ON DELETE CASCADE,
        step_name VARCHAR(64), event_type VARCHAR(64) NOT NULL, payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        actor_user_id UUID, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )"""),
    ("review_indexes", "CREATE INDEX IF NOT EXISTS idx_review_projects_tenant ON review_projects(tenant_id, created_at DESC)"),
    ("accounting_workflow_indexes", "CREATE INDEX IF NOT EXISTS idx_accounting_workflows_tenant ON accounting_workflows(tenant_id, updated_at DESC)"),
    ("accounting_audit_indexes", "CREATE INDEX IF NOT EXISTS idx_accounting_audit_logs_workflow ON accounting_audit_logs(workflow_id, created_at DESC)"),
]
async def run_migrations() -> None:
    async with AsyncSessionLocal() as session:
        for name, sql in _MIGRATIONS:
            try:
                await session.execute(text(sql))
                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.warning("db.migration_failed", migration=name, error=str(exc))
    logger.info("db.migrations_done", count=len(_MIGRATIONS))
