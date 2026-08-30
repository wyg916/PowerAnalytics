# 为 PowerAnalytics 贡献

感谢你改进智能运营分析项目。项目包含数据、预测、模型、AI/RAG、权限和数据库迁移等高风险边界，因此每个变更都应小范围、可验证、可回滚，并如实报告未通过项。

开始前请阅读 [AI 导读](README.ai.md)、[快速开始](docs/QUICKSTART.md)、[安全策略](SECURITY.md) 和 [第三方核验边界](THIRD_PARTY_NOTICES.md)。

## 工作流：Issue → `codex/` 分支 → 测试 → PR

### 1. 先创建或认领 Issue

Issue 应至少说明：

- 当前行为、期望行为和业务影响；
- 可复现步骤或最小示例；
- 预计涉及的模块、数据、API、迁移、模型或界面；
- 验收标准与明确不在范围内的内容；
- 是否包含安全、隐私、第三方素材或许可证问题。

安全漏洞不得公开披露，请改用 [SECURITY.md](SECURITY.md) 中的私密报告路径。

### 2. 从最新目标基线创建隔离分支

保持主工作树不受影响，分支统一使用：

```text
codex/<issue-number>-<short-topic>
```

一个分支只解决一个主题。大变更应拆分；不要顺手格式化或重构无关文件。开始修改前记录 HEAD、`git status --short --branch`、未跟踪文件和目标文件差异，且不要接管他人的未提交内容。

### 3. 实现最小变更

- 前端只能通过 Backend API 读取业务数据。
- 查询接口不得产生 Seed、同步、模型激活或 RAG 发布副作用。
- 不得把测试、历史、受控生成或 fallback 数据描述成实时采集、真实成交或生产结果。
- 数据、预测、策略、报告和 AI 应保留 `run_id` 与来源元数据。
- Candidate 模型不能自动晋升 Active。
- Schema、特征、时区或类型不匹配时应 fail closed。
- 不要提交秘密、凭据、个人信息、模型二进制、数据库、运行日志或无明确权利的语料。
- 新增第三方代码、模型、字体、图标、图片或语料时，必须说明来源、版本、许可证和再分发依据。

### 4. 运行与风险相称的测试

先运行最小相关测试，再根据影响扩大范围。以下命令是常见入口，不要求每个 PR 无差别全部执行。

后端或 Python：

```powershell
python -m pytest <相关测试路径> -q
```

迁移结构检查：

```powershell
python -m alembic heads
```

前端：

```powershell
cd frontend
npm ci
npm run typecheck
npm run unit
npm run build
```

启动配置与健康：

```powershell
docker compose --env-file .env.docker config --quiet
Invoke-WebRequest http://localhost:8000/api/health
```

| 变更类型 | 最低验证 |
|---|---|
| 文档 | 相对链接、命令、版本和事实边界检查 |
| 后端/API | 相关 pytest、鉴权/RBAC、失败路径和幂等性 |
| 前端 | typecheck、相关单测、build；视觉变更附目标视口截图 |
| 数据库迁移 | 单一 head、隔离 upgrade/downgrade、数据保护和恢复步骤 |
| 预测/模型 | 输入契约、可追溯版本、负向用例、Candidate/Active 门禁 |
| AI/RAG/Memory | 身份隔离、证据/引用、拒答、敏感信息、并发与持久化失败 |
| 部署/容器 | 配置渲染、健康检查、秘密注入和回滚 |

依赖数据库、模型、GPU、外部服务或凭据而未执行的测试必须在 PR 中标为 `NOT EXECUTED` 或 `BLOCKED`，不能写成 PASS。测试不得连接未授权数据库或调用未授权外部服务。

### 5. 使用 Conventional Commits

提交标题格式：

```text
<type>(<scope>): <imperative summary>
```

常用 `type`：

- `feat`：新增用户可见能力；
- `fix`：修复缺陷；
- `docs`：仅文档；
- `test`：测试或测试基础设施；
- `refactor`：不改变外部行为的重构；
- `perf`：性能改进；
- `build`：依赖或构建；
- `ci`：持续集成；
- `chore`：不属于以上类别的维护。

标题应具体、可审计。行为修改、迁移、生成产物和大段文档尽量拆成独立提交；不要用“update”“fix stuff”等模糊描述。

### 6. 提交 Pull Request

PR 描述应包含：

- 关联 Issue；
- 变更目的与文件范围；
- API、数据库、模型、RAG、Memory、权限和兼容性影响；
- 实际执行的命令与结果；
- 未执行项、已知风险和剩余问题；
- 回滚步骤；
- UI 变更的前后截图与视口；
- 第三方内容的来源和许可证核验记录。

合并前检查：

- [ ] 变更与 Issue 验收标准一致；
- [ ] 没有无关文件、秘密或本地产物；
- [ ] 成功、失败、空态、无权限和过期状态均如实处理；
- [ ] 测试结果可复现，跳过项有原因；
- [ ] 数据库与运行态有明确回滚；
- [ ] 文档、配置和实现未发生事实漂移；
- [ ] 第三方来源与再分发权不存在未披露问题。

## 评审与合并

维护者可以要求缩小范围、补充负向测试、拆分迁移或等待许可证/语料审查。提交 PR 不保证合并；涉及未决第三方权利、安全披露或不可逆数据操作的变更将保持阻塞，直到相应审查完成。

除明确标注第三方许可的内容外，贡献默认按仓库根目录 `LICENSE` 中的 AGPL-3.0-or-later 条款提交。贡献者必须确认自己拥有入站贡献所需权利；第三方代码、数据和素材必须保留其原始许可证、署名与来源说明。
