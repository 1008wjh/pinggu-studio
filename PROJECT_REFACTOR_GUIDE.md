# 项目重构说明与学习指南

本次重构把原来的“土地评估与财会工作室”迁移为“企业文档智能审查与知识问答平台”，主业务改为合同/招投标审查。目标是保留 RAG、Agent、文档解析、人工复核和审计追踪等技术骨架，同时让领域模型可以直接用于 LLM 应用工程师简历。

## 修改文件与原因

### `backend/agents/document_review/state.py`（新增）
定义审查 Agent 的共享状态和三个节点常量：文档抽取、风险审查、报告生成。`step_outputs`、`review_context` 和 `checkpoint_version` 让每一步都能展示、复核和恢复。

### `backend/agents/document_review/prompts.py`（新增）
集中管理企业文档审查的系统约束和三步提示词。提示词要求模型给出证据、风险原因、建议动作，并在资料不足时请求人工核验，避免把模型回答包装成最终法律意见。

### `backend/agents/document_review/graph.py`（新增）
使用 LangGraph 编排三步流程。每个业务节点后进入 `human_gate`，通过 `interrupt` 暂停；API 以 `Command(resume=...)` 注入人工决定。`MemorySaver` 保存线程状态，适合演示断点续跑和人机协同。

### `backend/api/v1/document_review.py`（新增）
新增合同/招投标审查 API，负责上传文件、创建工作流、查询审核上下文和恢复流程。数据库写入 `review_projects`、`review_actions`，因此每次人工动作都有审计记录。

### `backend/api/router.py`
注册 `/document-review` 路由，并把工作室接口标签改成企业文档智能审查。

### `backend/agents/studio/prompts.py`
把专业问答和材料初审提示词从土地评估/财会改为合同、招投标、企业制度和风险审查主题。

### `backend/api/v1/knowledge.py`
知识库 Agent 绑定名称改为企业文档问答、合同与招投标审查、文档风险审查，便于前端和数据库中的知识库用途保持一致。

### `frontend-discovery/src/views/DocumentReviewView.vue`（新增）
提供文档上传、三步进度、AI 输出展示、人工通过/打回和完成结果页面。

### `frontend-discovery/src/api/documentReview.ts`（新增）
封装审查工作流的创建、查询和恢复接口。

### `frontend-discovery/src/router/index.ts`
增加 `/document-review` 页面入口。

### `frontend-discovery/src/views/StudioHomeView.vue`、`StudioQAView.vue`、`StudioLandView.vue`、`WorkspaceView.vue`
把首页、问答、材料初审和文档工作台的业务文案迁移到合同/招投标场景。旧组件文件名保留是为了降低已有路由和接口的改动范围。

### `README.md`
重新编写项目定位、功能、接口、技术架构和学习入口，作为对外项目说明。

## 你需要掌握的主链路

1. 前端上传文件到 `POST /api/v1/document-review/workflows`。
2. API 保存文件和初始状态，然后调用 `build_document_review_graph().ainvoke(...)`。
3. `step1_extract` 调用文档解析器，再调用 LLM 生成审查上下文。
4. `human_gate` 调用 `interrupt`，流程暂停，接口返回 `pending_review`。
5. 前端点击通过后，API 用 `Command(resume={"action":"approve"})` 恢复 Graph。
6. Graph 进入风险识别，再次暂停，最后生成审查报告并等待最终确认。
7. 每次节点状态和人工动作写入 PostgreSQL，形成可追溯审计链。

## 当前实现边界

- 当前风险识别主要依靠提示词和知识库上下文，下一步应补充合同条款标注数据和离线评测集。
- 当前数据库使用已有的通用 `review_projects/review_actions` 表，后续可迁移为语义更明确的 `document_review_workflows/document_review_actions`。
- LangGraph 使用进程内 `MemorySaver`，生产环境建议替换为 PostgreSQL/Redis checkpoint saver。
- 旧的会计代码仍保留在仓库中作为迁移前历史实现，但主导航和新接口已经切换到文档审查；彻底清理前应先确认不再需要旧接口。

## 面试时的讲解顺序

先讲业务闭环，再讲技术实现：企业文档上传后，系统如何抽取信息、检索制度和法规、识别风险、生成报告，并让人工在每个高风险节点确认。然后解释混合 RAG 的召回/重排链路，最后说明多租户隔离、状态持久化和审计追踪。

## 新增评测测试模块

### `scripts/evaluation_schema.sql`

SQLite 建表语句，包含 `evaluation_tasks` 任务表和 `evaluation_samples` 样本结果表。样本表保存问题、标准答案、模型输出、Judge 分数、相似度、Token、缓存标记、各阶段耗时和硬件快照。

### `backend/evaluation/store.py`

只使用 Python 标准库 `sqlite3`，负责建库、任务/样本增删改查和汇总报告。数据库默认写入 `data/evaluations.sqlite3`，不会连接或改变 PostgreSQL/Milvus。

### `backend/evaluation/runner.py`

后台执行器。按样本类别调用已有 `build_studio_graph` 或 `build_document_review_graph`，合同审查自动通过三个已有人工门；评测只注入批准信号，不改原业务节点。完成后调用 LLM-as-judge，优先从 LangChain response 的 usage_metadata/response_metadata.token_usage 读取真实 Token；无法返回 usage 时才标记 unavailable 或 estimated，并记录耗时和硬件快照。通过 `asyncio.create_task` 运行，不阻塞普通请求。

### `backend/api/v1/evaluation.py`

提供任务创建、JSON/CSV 导入、单条样本添加、带附件样本添加、启动、停止、历史列表、报告、样本详情和 CSV 导出接口。接口前缀是 `/api/v1/evaluation`。

### `frontend-discovery/src/api/evaluation.ts`

前端评测接口封装。

### `frontend-discovery/src/views/EvaluationView.vue`

独立评测页面，包含测试集管理、历史任务选择、启动/停止、进度轮询、汇总指标、样本明细展开和 CSV 导出。

### `frontend-discovery/src/router/index.ts`、`Sidebar.vue`、`AppLayout.vue`

增加 `/evaluation` 路由、导航项和页面标题。

### `backend/api/v1/studio.py`

在原有问答入口增加命令识别：输入 `运行测试任务xxx` 时只查询并启动评测任务，返回文本状态；普通问题仍走原有 QA Agent。

## 测试集格式

JSON 可以是数组，也可以是 `{ "samples": [...] }`：

```json
[
  {"question":"合同约定的付款节点有哪些风险？","reference_answer":"应核对付款条件、验收前置条件和逾期责任","category":"contract_review"},
  {"question":"什么是不可抗力？","reference_answer":"依据法律和合同约定判断，不当然免除全部责任","category":"legal_qa"},
  {"question":"请总结这份会议纪要的待办事项","reference_answer":"列出负责人、截止时间和交付物","category":"document_summary","attachment_path":"meeting.docx"}
]
```

CSV 至少需要 `question,reference_answer` 两列，可以增加 `category,attachment_path`。

## 评测接入链路

```text
上传测试集 → SQLite 保存样本 → 后台 runner
  → 按 category 调用原有 Agent
  → 记录 predicted_answer 和资源指标
  → LLM-as-judge 打分
  → SQLite 汇总 → 前端报告/CSV
```

评测 worker 在独立子进程中安装透明观测代理：业务 Agent 的每次模型响应都会检查 `response.usage_metadata` 和 `response.response_metadata.token_usage`。OpenAI 兼容客户端返回 usage 时，样本写入 `usage_source=provider`；只在服务端确实没有 usage 时才写入 estimated/unavailable。GPU 指标通过 nvidia-smi 读取，CPU/内存使用可选 psutil。

本轮增量修改：

- `backend/agents/studio/prompts.py`：法律问答提示词改为法律法规/司法解释/制度依据；原“文档审查”改为文书要点摘要提示词。
- `backend/agents/studio/graph.py`：摘要降级文案改为文书摘要。
- `frontend-discovery/src/views/StudioLandView.vue`、`StudioQAView.vue`、`StudioHomeView.vue`、`StudioAgentPage.vue`：将重复的“文档智能审查”入口改成“文书要点摘要”。合同风险审查仍由独立审查工作流负责。
- `backend/evaluation/`、`backend/api/v1/evaluation.py`、`scripts/evaluation_schema.sql`：新增独立 SQLite 评测、后台执行、Judge 打分、资源记录、历史报告和导出。
- `frontend-discovery/src/views/EvaluationView.vue`、`src/api/evaluation.ts`：新增评测测试页面和 API 封装。
- `Sidebar.vue`、`AppLayout.vue`、`router/index.ts`：增加“评测测试”入口。
- `backend/api/v1/studio.py`：问答框支持 `运行测试任务任务名` 快捷命令，普通问答路径不变。

评测模块不会修改已有三个业务 Agent 的输出逻辑。评测 worker 在隔离子进程中读取模型响应的 `usage_metadata` 或 `response_metadata.token_usage`，写入 `usage_source=provider`；只有 provider 未返回 usage 时才写 estimated/unavailable。解析和向量召回耗时由透明代理采集，GPU 指标在没有 NVIDIA 环境时为空。


