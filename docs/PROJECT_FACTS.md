# PowerAnalytics 项目事实

生成时间：2026-08-30（Asia/Shanghai）

公开版本：`v2.12.1-open-source`

结构化版本：[PROJECT_FACTS.json](PROJECT_FACTS.json)

这些数字用于 README 的稳定展示口径。源码统计与已录制运行环境事实分开记录；历史验收结果不能替代新环境验证。

| 事实 | 公开口径 | 事实来源与边界 |
|---|---:|---|
| 主要 Web 业务模块 | 10 | `frontend/src/types/ui.ts` 的 `RouteKey`：Dashboard、Data、Forecast、Strategy、Assistant、Report、Model、Knowledge、Task、Settings |
| 声明的 HTTP 路由 | 206 | 对 `backend/app/` 与 `backend/model_gateway/` 的 FastAPI route decorators 做源码统计；README 使用较稳定的 `200+` |
| PostgreSQL 领域表 | 80+ | 23 个 Alembic revision 的 Schema 设计达到 80+ 领域表；新环境实际对象数必须由数据库只读盘点确认 |
| Alembic revisions | 23 | `migrations/versions/0001...0023`；唯一 revision head 为 `0023_model_center_facts`，对应文件 `0023_model_center_controlled_generation_metadata.py` |
| 预测特征契约 | 170 | `model_ops/safe_model_contract.py` 明确校验 170 个唯一、有序特征 |
| 单次成功预测结果 | 24 | Repository 和 Service 同时要求 success run 与结果表恰好 24 行且连续 |
| 企业知识文档 | 80+ | 最终演示环境画面记录 83 份；公开口径使用下界，数量不是新 clone 默认资产 |
| 知识 Chunk | 8k+ | 最终演示环境画面记录 8,339 个；公开口径使用下界，Chunk 与原始语料不随源码发布 |
| 云端模型能力族 | 3 | MiMo、DeepSeek、Kimi 按配置与能力路由；不是三个提供方默认同时启用 |
| AI 工程域 | 4+ | RAG、Memory、Trace、RBAC、Answer Guard、Citation/Grounding 等源码域 |

## 统计复现

PowerShell 示例：

```powershell
# 主要页面模块
Get-Content frontend/src/types/ui.ts

# FastAPI route decorator（源码声明数）
rg -n '@(router|app)\.(get|post|put|patch|delete|options|head)' `
  backend/app backend/model_gateway -g '*.py'

# Alembic revision 与唯一 head
Get-ChildItem migrations/versions -Filter '*.py'
python -m alembic heads

# 170 特征与 24 行结果的强制契约
rg -n '170|24' model_ops/safe_model_contract.py `
  backend/app/services/forecast_transaction_service.py `
  backend/app/repositories/forecast_repository.py
```

## 不应混淆的口径

- `206` 是源码声明的路由数量，不是独立业务产品数量，也不证明每个路由在任意环境都已配置可用。
- `80+ PostgreSQL 领域表` 是 Schema 规模口径；运行库还会包含 `alembic_version` 和 View 等对象。
- `83 / 8,339` 来自已录制的最终本地环境，不代表公开仓库自带这些文档或索引。
- 模型提供方只有在本机显式配置、权限和健康检查通过后才可用。
- 所有演示预测均按历史回放表达，不使用“实时在线预测”口径。
