# 阶段 6 提醒通知、履约看板和任务查询

## 状态

已完成。阶段 6 在保留旧 `documents`、`uploads`、`analysis_results` 以及已有合同、主体、联系人和履约任务的前提下，增加组织隔离的提醒扫描、站内通知、全局任务查询和履约看板。

## 已实现

- `notifications` 保存由履约任务生成的站内提醒，包含组织、接收人、合同、任务、类型、状态、触发时间和生成时间。
- 提醒扫描基于未完成任务的 `remind_at` 和 `due_at` 生成 `reminder`、`overdue` 两类通知；合同已软删除或任务已完成/取消时不会生成新通知。
- 接收人优先使用任务负责人；负责人为空或已停用时回退到任务创建人。两者均不可用时跳过并记录扫描统计。
- 通知去重键由任务、接收人、通知类型和对应触发时间共同生成；数据库唯一约束和扫描前查询共同保证重复扫描不重复写入。
- 通知只记录站内消息，不在请求线程调用邮件、桌面通知或其他外部服务。
- 当前用户只能查询、标记已读或忽略自己的通知；批量已读和单条状态变更均写入审计日志。
- 组织级任务查询支持分页、任务/合同搜索、状态、优先级、负责人、未分配、逾期和截止日期筛选，并返回合同与负责人展示信息。
- 履约看板聚合未完成、待处理、进行中、逾期、今日到期、未来 7 天、未分配、近 30 天完成和个人未读通知数量。
- 看板同时返回近期截止任务、优先级分布和负责人负荷；所有统计排除已软删除合同并强制按当前组织过滤。
- Vue 3 + Element Plus 新增“履约看板”入口，包含看板概览、任务查询和个人通知三个视图；授权角色可推动既有任务状态机并手动执行站内提醒扫描。
- 浏览器开发模式支持通过 `VITE_API_BASE_URL` 连接隔离后端，Electron 生产路径仍优先使用 preload 提供的后端地址。
- 全局顶部导航增加窄屏布局，390px 视口下无页面横向溢出。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/fulfillment/reminders/scan` | 扫描当前组织到期提醒并幂等生成站内通知 |
| GET | `/api/v1/fulfillment/dashboard` | 当前组织履约看板聚合 |
| GET | `/api/v1/fulfillment/tasks` | 当前组织全局履约任务分页与筛选 |
| GET | `/api/v1/notifications` | 当前用户通知分页与筛选 |
| GET | `/api/v1/notifications/unread-count` | 当前用户未读通知数量 |
| PATCH | `/api/v1/notifications/{id}` | 将当前用户通知标记为已读或忽略 |
| POST | `/api/v1/notifications/read-all` | 将当前用户全部未读通知标记为已读 |

提醒扫描需要 `system_admin`、`org_admin` 或 `contract_manager`；看板和任务查询遵循现有登录权限，通知接口还会校验接收人必须是当前用户。旧 `/api` 路由和阶段 5 合同任务接口未修改。

## 数据库迁移

```powershell
cd D:\工具\合同分析系统_逆向源码\python_backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

当前 revision 为 `0006_fulfillment_notifications`。迁移只新增 `notifications` 表、唯一约束和组织/接收人/任务相关索引，不删除或重写任何既有业务表。降级不会删除通知历史；回滚应停止服务并恢复升级前备份。

## 验收结果

- 阶段 6 专项测试使用临时 SQLite、脱敏合同和 fake clock，覆盖空库升级、提醒与逾期通知、重复扫描、回退接收人、通知已读/忽略、批量已读、任务筛选、看板统计、只读角色、合同软删除和跨组织访问拒绝。
- 全部 15 项 Python 测试通过；测试不调用真实 OCR、DeepSeek、邮件或桌面通知，不修改生产数据库。
- `npm run build`、`npm run typecheck`、`npm run lint:python` 和 `npm run test:python` 均通过。
- 本地隔离后端完成真实浏览器验收：桌面端看板、任务和通知数据正常渲染，通知状态交互正常；390px 移动视口文档宽度等于视口宽度，无横向溢出。

## 已知限制

- 当前提醒扫描由受权用户或后续调度器显式触发，尚未接入独立后台调度进程。
- 通知仅为站内记录，没有邮件、企业微信或系统桌面推送；外部渠道应由后续异步 worker 消费通知记录，不能放入 API 请求线程。
- 看板按当前组织展示全部未软删除合同任务，尚未增加部门或负责人数据权限层级。
- 通知保留历史状态；任务完成、取消或合同软删除不会物理删除已经生成的通知，但查询会隐藏软删除合同的通知。

## 下一阶段 AI 执行提示词

```text
你正在开发 D:\工具\合同分析系统_逆向源码，请严格按照《合同分析管理系统分阶段开发手册》和 STAGE6_FULFILLMENT_DASHBOARD.md 执行。

本次只执行：阶段 7 / 结构化分析结果、证据和风险复核。
先阅读阶段 2 至阶段 6 的模型、迁移、认证、组织隔离、文件版本、履约任务和通知测试，不要重写认证，不要删除旧 documents、uploads、analysis_results 或已有合同业务数据。

要求：
1. 新 API 使用 /api/v1，所有查询强制按当前用户 organization_id 过滤；旧 /api 分析接口和原始响应继续兼容。
2. 基于 analysis_runs 和 analysis_results 增加结构化字段、证据定位、风险项、人工复核状态和版本化结果，不覆盖历史原始 AI 响应。
3. 结构化结果必须关联合同、文件版本、模板版本和分析运行；复核操作必须鉴权、校验状态并写入审计日志。
4. 复用现有 FastAPI、SQLAlchemy、Vue 3、Pinia 和 Element Plus 结构，先补 Alembic 迁移，再补服务、API、前端和测试。
5. 测试只使用临时 SQLite、脱敏数据和 fake provider，不调用真实 OCR、DeepSeek、邮件或桌面通知，不修改生产数据库。
6. 完成后运行 npm run build、npm run typecheck、npm run lint:python、npm run test:python，并更新阶段报告和下一阶段提示词。
```
