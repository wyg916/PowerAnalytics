# PowerAnalytics 快速开始

本指南以 `v2.12.1-open-source` 公共快照为准。推荐先以 **AI/RAG 关闭的最小本地环境** 启动核心 Web 平台，再按需接入模型和知识资产。不要把示例占位值用于生产。

## 1. 环境要求

| 组件 | 已声明/验证范围 |
|---|---|
| 操作系统 | Windows、macOS 或 Linux；命令按 Shell 调整 |
| Python | 3.11.x；本地验收使用 3.11.9 |
| Node.js | `>=18 <25` |
| npm | `>=9 <12` |
| Docker | Engine 24+ 或 Docker Desktop |
| Docker Compose | v2 |
| PostgreSQL | Compose 使用 16 Alpine |
| Redis | Compose 固定 8.10.1 Alpine，并选择 AGPLv3 许可路径 |
| Qdrant | RAG 预发布配置锁定 1.18.2；核心 Web 启动可先禁用 RAG |

首次启动需要下载依赖和容器镜像。请先确认网络、磁盘与端口 `5433`、`6380`、`8000`、`8080` 可用。

## 2. 获取源码

```bash
git clone git@github.com:wyg916/PowerAnalytics.git
cd PowerAnalytics
```

也可以使用 HTTPS：

```bash
git clone https://github.com/wyg916/PowerAnalytics.git
cd PowerAnalytics
```

## 3. Docker Compose 最短路径

### 3.1 创建本机配置

PowerShell：

```powershell
Copy-Item .env.docker.example .env.docker
```

Bash：

```bash
cp .env.docker.example .env.docker
```

只在未跟踪的 `.env.docker` 中替换以下占位值：

- `JWT_SECRET_KEY`：至少 32 字符的随机值；
- `POSTGRES_PASSWORD`：PostgreSQL 管理身份随机密码；
- `APP_DB_PASSWORD`：应用运行身份随机密码；
- `SECURITY_DB_PASSWORD`：安全仓储身份随机密码；
- `CORS_ALLOWED_ORIGINS`：实际前端 Origin。

生成随机值的示例命令：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

不要把命令输出提交到 Git、Issue、日志或截图。

### 3.2 先验证配置

```bash
docker compose --env-file .env.docker config --quiet
docker compose -f docker-compose.enterprise.yml --env-file .env.docker config --quiet
```

### 3.3 初始化数据库角色与管理员

管理员初始化是显式操作，不由 GET 请求或前端页面触发。先在 `.env.docker` 中保持 `ADMIN_INITIALIZED=0`，并仅启动 PostgreSQL 与 Redis：

```bash
docker compose --env-file .env.docker up -d postgres redis
docker compose --env-file .env.docker --profile bootstrap run --rm -e APP_ENV=development -e AUTH_REQUIRED=0 database_bootstrap
```

从本机秘密存储把 `ADMIN_USERNAME`、`ADMIN_PASSWORD` 和 `ADMIN_EMAIL` 临时注入当前 Shell 环境，然后使用后端镜像执行管理员初始化。Compose 的 `backend.environment` 不会自动转发 `.env.docker` 中这三个键，因此命令必须显式传递变量名：

```bash
docker compose --env-file .env.docker run --rm --no-deps -e APP_ENV=development -e AUTH_REQUIRED=0 -e ADMIN_USERNAME -e ADMIN_PASSWORD -e ADMIN_EMAIL backend python scripts/create_admin_user.py
```

不要把真实值直接写进命令历史。确认脚本成功后，清除 Shell 中的临时 `ADMIN_PASSWORD`，并把 `.env.docker` 中 `ADMIN_INITIALIZED` 改为 `1`。不要在管理员未创建时虚假开启该标记。

### 3.4 启动核心服务

```bash
docker compose --env-file .env.docker up -d --build
docker compose --env-file .env.docker ps
```

默认入口：

- Web：`http://127.0.0.1:8080`
- 后端健康：`http://127.0.0.1:8000/api/health`
- 数据库健康：`http://127.0.0.1:8000/api/db/health`（production 需要登录后的 Bearer Token）
- OpenAPI：生产模式默认关闭；开发模式可使用 `http://127.0.0.1:8000/docs`

健康检查：

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8080/health
```

数据库健康接口在 production 模式不属于匿名白名单，应从已登录页面检查，或使用本机安全取得的短期 Token 请求；不要把 Token 写进文档或命令历史。

查看日志：

```bash
docker compose --env-file .env.docker logs --tail=100 backend
docker compose --env-file .env.docker logs --tail=100 celery_worker
docker compose --env-file .env.docker logs --tail=100 frontend
```

停止服务但保留数据卷：

```bash
docker compose --env-file .env.docker stop
```

不要为了重试删除 PostgreSQL、Redis、Qdrant 或模型数据卷。

## 4. 本地开发方式

该方式面向已准备 PostgreSQL、Redis、最小权限身份、Python 虚拟环境和本机配置的开发者。新 clone 不会携带秘密、数据、模型或其他运行资产。

### 4.1 安装依赖

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.web.txt
Set-Location frontend
npm ci
Set-Location ..
```

复制 `.env.example` 为 `.env`，仅在本机填写 PostgreSQL、Redis、JWT 和可选模型配置。缺少必需数据库身份或秘密时，服务应 fail closed。

### 4.2 启动后端与前端

在仓库根目录启动后端：

```powershell
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

在另一个终端启动前端：

```powershell
Set-Location frontend
npm run dev
```

开发入口：

- 前端：`http://127.0.0.1:5173`
- 后端健康：`http://127.0.0.1:8000/api/health`
- OpenAPI：`http://127.0.0.1:8000/docs`

使用当前终端的 `Ctrl+C` 停止对应开发进程；不要终止归属不明的端口进程。

## 5. 前端与后端开发检查

前端：

```bash
cd frontend
npm ci
npm run typecheck
npm run unit
npm run build
```

Python 语法、迁移头和定向测试：

```bash
python -m compileall backend prediction_engine model_ops knowledge_pipeline migrations scripts
python -m alembic heads
python -m pytest <相关测试路径> -q
```

Alembic 应只有一个 revision head：`0023_model_center_facts`，对应迁移文件 `0023_model_center_controlled_generation_metadata.py`。实际 `upgrade` 会修改数据库，必须先建立数据库检查点并使用获授权迁移身份；不要把它当作只读诊断命令。

## 6. 可选 AI 与 RAG

核心 Web 可在 `AI_ASSISTANT_LLM_ENABLED=0`、`RAG_ENABLED=0` 下启动并如实显示不可用状态。启用前需要自行准备：

- 合法取得的 LLM API Key，或本地兼容模型服务；
- 合法取得的 BGE Embedding 与 Reranker 权重；
- PostgreSQL 知识元数据与 Qdrant 1.18.2 运行环境；
- 明确拥有处理和再分发权的文档；
- 与当前发布版本、Embedding 维度和 Collection/Alias 一致的索引。

仓库不分发 API Key、模型权重、原始语料、Chunk、Embedding 或 Qdrant Snapshot。详见 [数据和模型资产](DATA_AND_MODEL_ASSETS.md)。

## 7. 常见失败

- **占位密钥被拒绝**：用本机随机值替换 `replace_with_*`，不要修改示例文件。
- **管理员未初始化**：重新执行第 3.3 节，成功后再设 `ADMIN_INITIALIZED=1`。
- **端口冲突**：调整 `.env.docker` 的外部端口，或停止你明确拥有的进程。
- **RAG unavailable**：先确认合法模型、文档、PostgreSQL Release 与 Qdrant Alias；不要启用 hash/fallback 假装成功。
- **预测缺少输入或模型**：公开源码不携带本机数据和模型二进制；缺失时系统应拒绝运行。
- **外部 LLM 不可用**：检查提供方配置与网络，并保持密钥只在本机秘密存储中。

> 当前开源版本面向本地部署、技术交流与项目展示；预测演示使用历史回放数据；系统默认不执行自动交易、资金操作或生产控制动作。
