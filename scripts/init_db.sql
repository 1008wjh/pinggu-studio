-- 土地评估与财会工作室数据库初始化脚本
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(128) NOT NULL DEFAULT 'tenant_default',
    username VARCHAR(128) NOT NULL,
    email VARCHAR(256),
    password_hash VARCHAR(256) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, username)
);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);

CREATE TABLE IF NOT EXISTS knowledge_documents (
    id UUID PRIMARY KEY, tenant_id VARCHAR(128) NOT NULL, user_id UUID,
    title VARCHAR(256) NOT NULL, source_name VARCHAR(512) NOT NULL,
    domain VARCHAR(64) NOT NULL DEFAULT 'studio', file_type VARCHAR(32), storage_path TEXT,
    status VARCHAR(24) NOT NULL DEFAULT 'processing', chunk_count INT NOT NULL DEFAULT 0,
    error_message TEXT, vector_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS knowledge_document_chunks (
    id UUID PRIMARY KEY, document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL, content TEXT NOT NULL, metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(document_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_documents_tenant ON knowledge_documents(tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS review_projects (
    id UUID PRIMARY KEY, tenant_id VARCHAR(128) NOT NULL, user_id UUID,
    operation VARCHAR(32) NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'pending_review',
    source_files JSONB NOT NULL DEFAULT '[]'::jsonb, extracted_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    report TEXT, review_decision VARCHAR(32), review_comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS review_actions (
    id UUID PRIMARY KEY, project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    user_id UUID, decision VARCHAR(32) NOT NULL, comment TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_review_projects_tenant ON review_projects(tenant_id, created_at DESC);

CREATE OR REPLACE FUNCTION update_updated_at_column() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;
-- 会计核算流水线表（工作室初始化脚本）
CREATE TABLE IF NOT EXISTS accounting_workflows (
    id UUID PRIMARY KEY, tenant_id VARCHAR(128) NOT NULL, user_id UUID,
    thread_id VARCHAR(160) NOT NULL UNIQUE, status VARCHAR(32) NOT NULL DEFAULT 'pending_review',
    current_step VARCHAR(32) NOT NULL DEFAULT 'step1_classification', state JSONB NOT NULL DEFAULT '{}'::jsonb,
    checkpoint_version INT NOT NULL DEFAULT 0, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS accounting_step_reviews (
    id UUID PRIMARY KEY, workflow_id UUID NOT NULL REFERENCES accounting_workflows(id) ON DELETE CASCADE,
    step_name VARCHAR(64) NOT NULL, attempt INT NOT NULL DEFAULT 1, ai_output JSONB NOT NULL DEFAULT '{}'::jsonb,
    original_data JSONB NOT NULL DEFAULT '{}'::jsonb, confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    risk DOUBLE PRECISION NOT NULL DEFAULT 1, decision VARCHAR(32) NOT NULL DEFAULT 'pending_review',
    edited_output JSONB, comment TEXT NOT NULL DEFAULT '', actor_user_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), acted_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS accounting_checkpoints (
    id UUID PRIMARY KEY, workflow_id UUID NOT NULL REFERENCES accounting_workflows(id) ON DELETE CASCADE,
    thread_id VARCHAR(160) NOT NULL, step_name VARCHAR(64) NOT NULL, state JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS accounting_audit_logs (
    id UUID PRIMARY KEY, workflow_id UUID NOT NULL REFERENCES accounting_workflows(id) ON DELETE CASCADE,
    step_name VARCHAR(64), event_type VARCHAR(64) NOT NULL, payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor_user_id UUID, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_bases (
    id UUID PRIMARY KEY, tenant_id VARCHAR(128) NOT NULL, name VARCHAR(128) NOT NULL,
    description TEXT NOT NULL DEFAULT '', status VARCHAR(24) NOT NULL DEFAULT 'active',
    milvus_partition VARCHAR(128) NOT NULL, created_by UUID, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(tenant_id, name), UNIQUE(milvus_partition)
);
CREATE TABLE IF NOT EXISTS knowledge_base_agents (
    knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    agent_key VARCHAR(64) NOT NULL, tenant_id VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(knowledge_base_id, agent_key)
);
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS knowledge_base_id UUID REFERENCES knowledge_bases(id) ON DELETE CASCADE;
ALTER TABLE knowledge_document_chunks ADD COLUMN IF NOT EXISTS knowledge_base_id UUID REFERENCES knowledge_bases(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_knowledge_bases_tenant ON knowledge_bases(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_documents_kb ON knowledge_documents(knowledge_base_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_kb ON knowledge_document_chunks(knowledge_base_id);
INSERT INTO knowledge_bases (id, tenant_id, name, description, milvus_partition)
SELECT uuid_generate_v4(), 'tenant_default', '默认工作室知识库', '迁移前资料的兼容知识库', 'kb_default'
WHERE NOT EXISTS (SELECT 1 FROM knowledge_bases WHERE tenant_id='tenant_default' AND name='默认工作室知识库');
UPDATE knowledge_documents d SET knowledge_base_id=b.id FROM knowledge_bases b
WHERE d.knowledge_base_id IS NULL AND b.tenant_id=d.tenant_id AND b.name='默认工作室知识库';
UPDATE knowledge_document_chunks c SET knowledge_base_id=d.knowledge_base_id FROM knowledge_documents d
WHERE c.document_id=d.id AND c.knowledge_base_id IS NULL AND d.knowledge_base_id IS NOT NULL;
INSERT INTO knowledge_base_agents (knowledge_base_id, agent_key, tenant_id)
SELECT id, 'domain_qa', tenant_id FROM knowledge_bases b WHERE b.name='默认工作室知识库'
AND NOT EXISTS (SELECT 1 FROM knowledge_base_agents a WHERE a.knowledge_base_id=b.id AND a.agent_key='domain_qa');
DELETE FROM knowledge_base_agents WHERE agent_key IN ('contract_review', 'finance_review');
