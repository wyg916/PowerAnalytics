# PowerAnalytics：AI 导读

> 本文件面向 AI 编程助手、自动化审查工具和首次接触项目的开发者。它描述 `v2.12.1-open-source` 公共快照的代码事实与边界，不代表生产就绪或提供 SLA，也不替代 [快速开始](docs/QUICKSTART.md)、测试证据或安全审查。

## 项目定位

PowerAnalytics（智能运营分析项目）是一个本地优先的智能电力运营分析与决策支持平台。Web 端覆盖经营总览、数据中心、预测、策略、报告、模型、任务、知识库、AI 助手和系统设置；后端通过受控 API 连接 PostgreSQL、Redis/Celery、预测与模型治理、RAG 和多模型 AI 运行时。

平台用于辅助分析和人工决策，不执行自动交易、资金动作或设备控制。页面可展示历史数据或按真实业务约束生成的受控数据；数据来源、批次和生成信息保留在后端审计链中，不能把它们描述成实时采集或真实成交结果。

## 业务主链

1. 数据进入 PostgreSQL，并经过字段、质量、权限和时间口径校验。
2. 预测任务读取受控输入与唯一 Active 模型，生成带 `run_id`、模型版本和特征版本的结果。
3. 首页、预测、策略和报告通过后端 API 读取同一批可追溯事实。
4. 策略与报告保留人工审核边界；Candidate 模型不得自动晋升为 Active。
5. AI 助手根据身份、会话和意图选择只读或受控工具，并由回答守卫处理证据、权限和失败状态。
6. 知识问答从已发布的知识版本检索证据；证据不足时应拒答，不能补造引用。

## AI 运行时

AI 助手的主要实现位于 `backend/app/ai_assistant/`，旧兼容与会话持久化能力位于 `backend/app/ai/`，图式 Agent 能力位于 `backend/langgraph_agent/`。

核心处理链包括：

- 输入规范化、身份上下文和会话状态恢复；
- 意图路由、上下文构建和能力注册；
- 预测、策略、报告、知识、模型、储能和数据时效等领域工具；
- 可配置的本地或 OpenAI-compatible 模型提供方；
- 工具结果、引用、回答计划和最终输出守卫；
- `trace_id`、`run_id`、工具调用和反馈的可追溯持久化。

模型提供方必须由本机环境变量或受控密钥系统显式启用。仓库不应包含 API Key；未配置或探测失败时，运行态必须如实显示 disabled、unavailable 或 error，不能伪装成外部模型成功。

## RAG 与 Citation

知识处理代码位于 `knowledge_pipeline/`，运行时接口位于后端知识与 AI 模块，Qdrant 预发布配置位于 `deploy/rag-r1/`。

RAG 链路按以下阶段治理：

1. 检查文档格式、来源和可处理性；
2. 受控解析、分块、去重并生成内容哈希；
3. 在 PostgreSQL 保存文档、Chunk、发布状态和审计元数据；
4. 生成 Embedding，并在 Qdrant 建立与发布版本一致的向量集合；
5. 执行检索、重排和访问控制；
6. 只根据检索证据生成回答，并返回可核对的 Citation；
7. 通过 validate、publish、alias 和回滚门禁管理版本。

原开发环境曾完成 RAG-R1 发布与检索验收；公共快照不包含该环境的验收证据、PostgreSQL 数据、Qdrant 集合、Alias、模型缓存或预热状态。任何新环境都必须重新完成导入、发布一致性检查和只读检索验收，不能仅凭代码或演示截图宣称 RAG 已可用。

原始语料、解析产物、Chunk 和 Embedding 不随本仓库分发；用户导入资产的权利需要独立确认，详见 [第三方声明](THIRD_PARTY_NOTICES.md)。

## Memory

会话内状态与跨会话记忆使用 PostgreSQL 持久化，并按 tenant、workspace、user、agent、session 等身份维度隔离。

- 短期状态恢复最近意图、主题、关注对象、指标、值、run 和回答摘要；消息与工具调用由独立持久化记录承载。
- 长期记忆以 semantic、episodic 为当前召回范围；procedural 内容可进入 Candidate，但不能在未准入时表述为已可召回。
- 记忆有版本、状态迁移、使用记录、TTL、归档、删除请求、法律保留和 outbox 处理链。
- `SESSION_ONLY`、`LONG_TERM_CANDIDATE` 与 `LONG_TERM_ACCEPTED` 是不同准入结果；不能把候选或会话内容描述成已稳定长期保存。
- 显式长期记忆写入或召回失败时应 fail closed；普通会话状态读写失败会进入可见降级并记录 `degraded_components`，不得跨身份回退或补造偏好。

## 目录速览

| 路径 | 职责 |
|---|---|
| `frontend/` | React、TypeScript、Vite、Ant Design 和 ECharts Web 前端 |
| `backend/app/` | FastAPI API、领域服务、认证/RBAC、AI、知识、任务、报告和模型接口 |
| `backend/langgraph_agent/` | 图式 Agent 状态、节点、工具和服务编排 |
| `prediction_engine/` | 预测训练、推理和输入输出契约 |
| `model_ops/` | 模型注册、评估、准入、监控与回滚辅助能力 |
| `knowledge_pipeline/` | 多格式检查、解析、Chunk、Embedding 和发布候选治理 |
| `migrations/` | PostgreSQL Alembic 迁移；当前唯一 revision head 为 `0023_model_center_facts`，对应文件 `0023_model_center_controlled_generation_metadata.py` |
| `scripts/` | 启动前检、健康检查、导入、RAG/模型治理和验收脚本 |
| `tests/` | 后端、契约、RAG、AI、权限、预测和端到端测试 |
| `deploy/`、`docker/` | 本地/预发布部署配置和容器辅助文件 |
| `docs/` | 架构、状态、任务与验收资料；历史证据不等于当前环境状态 |

## 启动与验证

推荐基线：Python 3.11、Node.js `>=18 <25`、npm `>=9 <12`、Docker Compose、PostgreSQL 和 Redis。完整依赖、密钥、迁移、容器与手动开发流程见 [docs/QUICKSTART.md](docs/QUICKSTART.md)。公开快照不携带内部机器专用启动器。

推荐先用 Docker Compose 验证配置并启动核心服务：

```powershell
Copy-Item .env.docker.example .env.docker
# 替换占位密钥，并按 QUICKSTART.md 3.3 节完成显式数据库角色与管理员初始化
docker compose --env-file .env.docker config --quiet
# 初始化成功后再启动常规服务
docker compose --env-file .env.docker up -d --build
```

默认入口为：

- Web：`http://127.0.0.1:8080`
- 后端健康：`http://127.0.0.1:8000/api/health`
- OpenAPI：`http://127.0.0.1:8000/docs`（仅非 production 模式启用）

不得提交 `.env`、数据库密码、令牌、API Key、模型二进制、本地数据库或运行日志。不要在未获授权的数据库上执行迁移、Seed、全表更新或清理。

## 真实性与安全边界

- 本地可复现运行不等于生产 SLA、生产容量、灾备或生产就绪保证。
- GET/查询接口不得隐式 Seed、同步、激活模型或发布 RAG。
- 前端不得直连数据库，也不得用硬编码或成功态 fallback 伪造缺失业务数据。
- 模型输入的列、类型、顺序、时区或 schema hash 不一致时必须拒绝执行。
- 未经哈希、来源、运行时和隔离检查，不得反序列化模型二进制。
- RAG Citation 只代表检索到的证据位置，不代表内容天然正确或获得再分发授权。
- 外部大模型调用可能把请求发送到第三方；启用前应完成数据分类、脱敏、供应商条款和网络边界审查。
- 安全问题应按 [SECURITY.md](SECURITY.md) 私密报告，不要写入公开 Issue。

## 版本状态

- 当前公共版本为 `v2.12.1-open-source`，采用从已审计源码 allowlist 生成的全新公开 Git 历史。
- 首个公开提交不包含内部提交历史、任务证据、本机路径清单或运行资产。
- 前端包版本与公共版本统一为 `2.12.1`；公开版本不代表生产 SLA、外部生产联调或自动交易能力。
- 变更摘要见 [CHANGELOG.md](CHANGELOG.md)，贡献流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。
