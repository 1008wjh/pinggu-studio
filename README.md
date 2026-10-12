# 企业文档智能审查与知识问答平台

面向企业合同、招投标文件和内部制度的 LLM 应用平台。系统把文档解析、知识库检索、风险分析、审查报告和人工复核串成可追溯的工作流。

## 核心能力

- 企业合同、招标文件和投标响应文件的 PDF/Word/Excel/图片材料解析。
- 基于 BGE-M3 dense/sparse 向量、BM25、Milvus 和 BGE Reranker 的混合 RAG。
- 合同/招投标专业知识问答，返回知识库来源。
- LangGraph 三步审查：字段抽取 → 条款风险识别 → 审查报告生成。
- 每一步通过 `interrupt` 暂停，支持人工通过、打回和继续执行。
- PostgreSQL 保存租户、知识库、工作流、审核动作和审计记录。
- FastAPI + Vue 3 + Docker Compose 部署。

## 审查流程

```text
上传文档 → 解析与字段抽取 → 人工复核
       → 条款风险识别 → 人工复核
       → 审查报告生成 → 最终人工确认
```

## 主要接口

- `POST /api/v1/studio/qa`：企业文档知识问答
- `POST /api/v1/document-review/workflows`：创建合同/招投标审查工作流
- `GET /api/v1/document-review/workflows/{id}`：查看当前节点和审核上下文
- `POST /api/v1/document-review/workflows/{id}/resume`：人工通过、打回并恢复流程
- `GET|POST|PATCH|DELETE /api/v1/knowledge/bases`：知识库管理

## 技术架构

- **应用层**：FastAPI、Vue 3、Element Plus、JWT
- **Agent 层**：LangGraph、结构化 State、Human-in-the-loop
- **检索层**：PostgreSQL 原文/BM25 + Milvus 向量检索 + BGE Reranker
- **模型层**：DeepSeek/兼容 OpenAI 接口、BGE-M3、BGE-Reranker
- **文档层**：PDF、DOCX、XLSX/XLS、CSV、图片 OCR
- **部署层**：Docker Compose、PostgreSQL、Milvus、MinIO、etcd、Nginx

## 学习入口

先阅读 `PROJECT_REFACTOR_GUIDE.md`，再按顺序查看 `backend/agents/document_review/state.py`、`graph.py`、`backend/api/v1/document_review.py` 和 `frontend-discovery/src/views/DocumentReviewView.vue`。

## 评测测试模块

`backend/evaluation/` 是独立的观测与回归评测模块，不改法律问答、合同审查和文书摘要的原有实现。它从 SQLite 测试集读取样本，在后台任务中调用已有 Agent，使用 LLM-as-judge（优先读取 OpenAI/LangChain usage_metadata）（1~5 分）和词项相似度生成结果，并记录 Token、耗时、缓存标记和 CPU/内存/GPU 快照。

建表语句位于 `scripts/evaluation_schema.sql`。前端页面为 `/evaluation`，接口前缀为 `/api/v1/evaluation`。在问答框输入 `运行测试任务任务名称` 可以启动任务并返回简要状态。

