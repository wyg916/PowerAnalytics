# PowerAnalytics 第三方声明

本文件记录首个公共源码快照中的主要第三方组件、许可证边界与下游核验义务。它不是法律意见，也不能替代每个依赖随附的许可证原文。最终分发者应以实际解析版本、构建产物和容器镜像为准生成 SBOM，并保留相应许可证与 Notices。

## 项目许可证与第一方素材

PowerAnalytics 自有源码、仓库内自有文档、品牌图和产品截图由版权所有者以 **GNU Affero General Public License v3.0 or later（AGPL-3.0-or-later）** 发布，完整条款见 [LICENSE](LICENSE)。

Copyright (C) 2026 wyg916.

作者已于 2026-08-30 确认仓库内第一方项目内容及截图可以公开发布。原始录屏母带不随仓库或 Release 分发。商标和服务标识权利不因源码许可证而自动授予。

## 当前源码快照的直接依赖

以下是根据 `requirements.web.txt`、`frontend/package.json`、Compose 与部署配置整理的主要直接依赖。版本范围可能解析到新版本，因此许可证标识仅作为当前核验起点。

| 组件 | 上游许可证/路径 | 说明 |
|---|---|---|
| [PyMuPDF / MuPDF](https://pymupdf.readthedocs.io/en/latest/about.html#license) | AGPL-3.0-only 或 Artifex 商业许可 | 本项目选择 AGPL 路径；PyMuPDF 自身仍按上游条款授权 |
| FastAPI、Pydantic、SQLAlchemy、Alembic | MIT | 保留上游版权与许可文本 |
| Uvicorn、Celery、pandas、NumPy、scikit-learn、joblib、python-dotenv | BSD 系列 | 以实际安装包附带文本为准 |
| requests、XGBoost、sentence-transformers | Apache-2.0 | 模型库许可证不等于模型权重许可证 |
| PyYAML、PyMySQL、LightGBM、redis-py | MIT | 以实际解析版本为准 |
| psycopg / psycopg-binary | LGPL-3.0 系列 | 二进制 wheel 可能带有额外原生组件 |
| Matplotlib、Pillow | 各自 PSF/HPND 风格许可证 | 保留包内许可证和版权声明 |
| python-docx、openpyxl、lxml、chardet | MIT/BSD/LGPL 等各自许可证 | 文档解析库与被解析文档的权利相互独立 |
| httpx2 | BSD-3-Clause | 这是 PyPI 包名 `httpx2`，不是 `httpx` 的别名 |
| React、React DOM、Ant Design、Ant Design Icons | MIT | 以 `frontend/package-lock.json` 的解析版本为准 |
| Apache ECharts | Apache-2.0 | `echarts-for-react` 另按其 MIT 许可证 |
| TypeScript、Vite、@vitejs/plugin-react | Apache-2.0 / MIT | 主要用于构建与开发 |
| PostgreSQL | PostgreSQL License | 数据库内容不随源码快照分发 |
| [Redis 8.10.1](https://redis.io/legal/licenses/) | AGPL-3.0、RSALv2 或 SSPLv1 三选一 | Compose 固定 `redis:8.10.1-alpine`，本项目选择与根许可证兼容的 AGPLv3 路径；生产分发还应固定 digest |
| Qdrant | Apache-2.0 | 运行镜像要求固定版本与 digest |
| Ollama | MIT | 通过 Ollama 获取的模型仍按各自模型许可证授权 |

本表不穷举传递依赖、操作系统包、容器基础层或可选 extras。对应许可证文本通常位于已安装 Python/npm 包或上游源码中；打包二进制或容器时应把适用文本一并交付。

## 强 Copyleft 与网络部署

本项目采用 AGPL-3.0-or-later；该路径与 PyMuPDF/MuPDF 的 AGPLv3 开源路径以及 Redis 8 的 AGPLv3 选项相容。修改后通过网络向用户提供服务时，应为这些用户提供对应源码，具体以 AGPL 第 13 节为准。

PyMuPDF 也提供商业授权路径。如分发者改用商业许可，应自行取得授权并重新评估整个组合的许可方案；本仓库不代表 Artifex 授予商业许可。

## 明确排除的组件和资产

首个公共快照不包含：

- PySide6、PySide6-Fluent-Widgets 及桌面 GUI 打包产物；
- BGE、Reranker、Ollama 或预测模型权重、tokenizer 和模型缓存；
- 原始 PDF/Word/表格语料、解析文本、Chunk、Embedding、向量集合或 Snapshot；
- PostgreSQL/Redis 数据、Dump、日志、Secrets、API Key、私钥或管理员凭据；
- 字体包、客户资料、内部审计证据、原始录屏母带和内部 Git 历史。

将这些内容加入派生发行版前，必须分别核验准确来源、版本、许可证、服务条款、隐私和再分发权限。公开可访问、能够下载或能够被模型处理，都不等于允许再分发。

## 模型、外部服务与用户数据

代码许可证与模型权重许可证是两件事。用户自行获取的 BGE、Reranker、Ollama 模型、本地预测 Artifact 及其 tokenizer/config，应按模型卡和上游许可证使用。

DeepSeek、Kimi、MiMo、OpenAI-compatible 或其他远程服务受各自服务条款、数据处理和隐私政策约束。启用前应完成数据分类、脱敏、跨境和供应商审查；API 兼容不代表许可证或服务条款相同。

用户导入的文档、数据库记录和业务数据不因进入 PowerAnalytics 而自动获得 AGPL 许可或再分发权。操作者负责确保其有权处理、检索、生成派生索引并按预期范围展示这些内容。

## 下游分发清单

构建、打包或部署派生版本时至少应：

1. 固定 Python、npm、容器和模型的准确版本或 digest；
2. 生成 SPDX 或 CycloneDX SBOM；
3. 收集直接与传递依赖的许可证及 Notices；
4. 扫描前端 bundle、Python wheels、容器层和 Release 附件；
5. 为网络用户提供修改版的对应源码；
6. 对新增字体、图标、图片、模型和语料逐项保存来源与授权证据；
7. 不把第三方组件、模型或内容声明为 PowerAnalytics 作者自研或自有。

如某一新增资产的权利或许可证无法确认，应将其从分发物中隔离，而不是省略来源或作推断。
