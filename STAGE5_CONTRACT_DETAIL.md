# 阶段 5 合同详情、主体关联和履约任务

## 状态

已完成。阶段 5 在保留旧 `documents`、`uploads`、`analysis_results` 和阶段 4 已导入合同的前提下，增加合同详情聚合、组织内主体/联系人关联和可审计履约任务工作流。

## 已实现

- 合同详情聚合返回合同基础信息、文件及版本、关联主体和联系人、履约任务、操作历史。
- `parties` 保存组织内可复用的甲方、乙方或其他主体；同一组织同一主体类型不允许重名。
- `contract_parties` 支持合同与主体按 `party_a`、`party_b`、`other` 角色关联，同一合同的甲方和乙方各最多一个。
- `contacts` 归属于组织主体，支持主要联系人标记；切换主要联系人会自动取消同主体其他主要标记。
- `fulfillment_tasks` 支持待处理、执行中、已完成、已取消状态，以及优先级、负责人、截止时间和提醒时间。
- 任务状态只能按状态机转换：`pending -> in_progress/cancelled`、`in_progress -> pending/completed/cancelled`、`cancelled -> pending`；已完成任务不可重新打开。
- 创建和更新任务时校验截止时间、提醒时间和负责人；负责人必须是当前组织的有效用户。更新已逾期任务的状态不要求重新设置未来日期，但显式修改截止时间仍必须为未来时间。
- 合同软删除规则保持不变；已删除合同不能读取详情、主体或任务，也不会删除关联历史记录。
- 主体、联系人、主体关联和任务变更均写入 `audit_logs`；详情页按当前组织返回相关合同操作历史。
- 新增组织范围的 `/api/v1/fulfillment-assignees` 只读接口，供任务负责人选择使用；旧 `/api` 路由未修改。
- Vue 3 + Element Plus 合同详情页提供概览、主体联系人、履约任务、文件版本和操作历史视图，可创建关联主体、联系人和任务，并推动任务状态。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/contracts/{id}/detail` | 合同详情聚合 |
| GET | `/api/v1/contracts/{id}/operations` | 合同操作历史 |
| GET | `/api/v1/parties` | 当前组织主体列表，可按类型和名称筛选 |
| POST | `/api/v1/parties` | 创建主体（管理员/合同管理角色） |
| PUT | `/api/v1/parties/{id}` | 更新主体 |
| GET | `/api/v1/parties/{id}/contacts` | 查询主体联系人 |
| POST | `/api/v1/parties/{id}/contacts` | 创建联系人 |
| PUT | `/api/v1/parties/{id}/contacts/{contact_id}` | 更新联系人 |
| GET | `/api/v1/fulfillment-assignees` | 当前组织有效负责人列表 |
| GET | `/api/v1/contracts/{id}/parties` | 查询合同主体关联 |
| POST | `/api/v1/contracts/{id}/parties` | 关联主体 |
| DELETE | `/api/v1/contracts/{id}/parties/{link_id}` | 解除主体关联 |
| GET | `/api/v1/contracts/{id}/tasks` | 查询履约任务，可按状态/逾期筛选 |
| POST | `/api/v1/contracts/{id}/tasks` | 创建履约任务 |
| PATCH | `/api/v1/contracts/{id}/tasks/{task_id}` | 更新任务字段或状态 |

所有新查询均使用当前用户 `organization_id`，详情、任务和主体关联还会校验合同未被软删除。写操作需要 `system_admin`、`org_admin` 或 `contract_manager`；只读详情和负责人列表遵循现有认证依赖。

## 数据库迁移

```powershell
cd D:\工具\合同分析系统_逆向源码\python_backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

当前 revision 为 `0005_parties_and_fulfillment`。迁移新增 `parties`、`contract_parties`、`contacts`、`fulfillment_tasks` 及组织、合同、状态、截止时间相关索引；降级不会删除业务数据。

## 验收结果

- 阶段 5 专项测试使用临时 SQLite、脱敏主体/联系人、跨组织用户和合同数据，覆盖详情聚合、审计历史、任务状态机、截止时间、负责人组织校验、只读/写权限、软删除和跨组织访问拒绝。
- 不调用真实 OCR、DeepSeek 或生产数据库。
- 全部 Python 测试和前端构建、类型检查、Python lint 均通过（详见提交前终端验收记录）。

## 已知限制

- 提醒状态当前按 `remind_at` 和任务截止时间计算并展示，尚未接入后台定时通知渠道；后续通知中心阶段再接入邮件、站内信或桌面通知。
- 主体与联系人目前提供创建、更新和禁用，没有单独的回收站；禁用记录不会出现在默认选择列表中。
- 任务完成后不可编辑状态，但仍可由授权用户更新描述等非状态字段。

## 下一阶段 AI 执行提示词

```text
你正在开发 D:\工具\合同分析系统_逆向源码，请严格按照《合同分析管理系统分阶段开发手册》和 STAGE5_CONTRACT_DETAIL.md 执行。

本次只执行：阶段 6 / 提醒通知、履约看板和任务查询。
先阅读阶段 2、阶段 3、阶段 4、阶段 5 的模型、迁移、组织隔离、文件版本、主体关联、任务状态机和测试，不要重写认证，不要删除旧 documents、uploads、analysis_results 或已有合同、主体、联系人、任务。

要求：
1. 新 API 使用 /api/v1，所有查询强制按当前用户 organization_id 过滤；旧 /api 接口继续兼容。
2. 基于 fulfillment_tasks 的 remind_at、due_at 和状态增加可重复执行的提醒扫描、通知记录、已读/忽略状态和履约看板聚合；不得在请求线程中调用真实外部通知服务。
3. 通知生成必须幂等，任务状态和合同软删除规则保持不变，越权用户不能查看其他组织的任务、通知或统计。
4. 复用现有 FastAPI、SQLAlchemy、Vue 3、Pinia 和 Element Plus 结构，先补 Alembic 迁移，再补服务、API、前端和测试。
5. 测试只使用临时 SQLite、脱敏数据和 fake clock/provider，不调用真实 OCR、DeepSeek、邮件或桌面通知，不修改生产数据库。
6. 完成后运行 npm run build、npm run typecheck、npm run lint:python、npm run test:python，并更新阶段报告和下一阶段提示词。
```
