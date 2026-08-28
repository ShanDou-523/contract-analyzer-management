# 阶段 9 风险提醒编排、整改协作通知和跨合同报表

## 状态

已完成。阶段 9 在保留旧 `documents`、`uploads`、`analysis_results`、原始 AI 响应、结构化历史版本、风险历史和已有合同数据的前提下，扩展阶段 6 站内通知机制，提供风险整改到期/逾期提醒、后台扫描入口以及组织级风险趋势和整改负荷报表。

## 已实现

- `notifications.task_id` 改为可空并新增 `risk_id`，旧履约任务通知的字段、查询和幂等键保持兼容；风险通知可通过同一通知中心按 `risk_reminder`、`risk_overdue` 筛选。
- 新增风险提醒扫描服务：只处理当前组织、未删除合同、最新结构化结果中的 `open`/`in_progress` 风险；整改负责人优先接收，负责人缺失或停用时回退风险创建人，均无有效用户时跳过。
- 风险提醒按风险、接收人、通知类型和整改期限生成 SHA-256 幂等键；整改期限 24 小时内生成到期提醒，已超过期限生成逾期提醒，重复扫描不会重复写入。
- 新增后台任务入口 `POST /api/v1/risks/reminders/scan`。API 仅排队并返回 `202 queued`，扫描使用独立数据库会话；扫描异常记录日志，不影响风险整改状态更新。
- 新增组织级风险报表：近 N 天风险趋势、合同风险排名、负责人风险负荷和逾期统计；合同排行提供分页、排序，并提供 UTF-8 CSV 导出。
- 风险报表和通知列表均强制按当前用户 `organization_id` 过滤，排除软删除合同和已替代结构化结果；阶段 6 履约通知、阶段 7 结构化结果和阶段 8 风险状态机继续保留。
- 前端风险台账增加提醒扫描、报表刷新、合同排行、负责人负荷和 CSV 导出；履约看板通知页增加风险提醒类型和风险标识。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/risks/reminders/scan` | 后台排队风险到期/逾期提醒扫描（管理角色） |
| GET | `/api/v1/notifications` | 兼容履约通知并支持风险通知类型筛选 |
| GET | `/api/v1/risk-reports/overview` | 组织风险趋势、合同排行和负责人负荷总览 |
| GET | `/api/v1/risk-reports/contracts` | 合同风险排行，支持分页和排序 |
| GET | `/api/v1/risk-reports/export` | 导出合同排行和负责人负荷 CSV |

## 数据库迁移

```powershell
cd D:\工具\合同分析系统_逆向源码\python_backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

新增 revision `0009_risk_notifications_reports`，使用 Alembic SQLite batch 模式，仅调整通知关联和索引，不删除或重写任何历史数据；降级不会删除通知或整改历史。

## 验收结果

- 阶段 9 专项测试覆盖空库迁移、风险到期/逾期提醒、重复扫描幂等、通知查询、报表组织隔离、合同排行分页、CSV 导出和后台排队，共 2 项通过。
- 全部 Python 测试共 21 项通过；测试只使用临时 SQLite、脱敏数据和测试令牌，不调用真实 OCR、DeepSeek、邮件或桌面通知。
- `npm run build`、`npm run typecheck`、`npm run lint:python` 和 `npm run test:python` 均通过。
- 生产数据库已升级到 `0009_risk_notifications_reports`；数据计数保持：`documents=28`、`analysis_results=56`、`contracts=28`、`contract_files=28`、`file_versions=28`、`analysis_runs=28`、`uploads=28`。

## 已知限制

- 当前“后台”实现为 FastAPI `BackgroundTasks`，由管理端显式触发扫描；尚未绑定独立定时器、邮件、短信或桌面推送通道。后续接入外部通道时应沿用通知幂等键，并将发送重试放入独立 worker。
- 报表趋势按风险创建日期分桶，当前状态指标按生成时刻计算；未引入每日历史快照，因此不能还原过去某天的完整状态。
- 风险整改更新与通知扫描解耦，扫描失败不会回滚整改状态；生产部署应补充后台任务监控和失败告警。

## 下一阶段 AI 执行提示词

```text
你正在开发 D:\工具\合同分析系统_逆向源码，请严格按照《合同分析管理系统分阶段开发手册》和 STAGE9_RISK_REPORTS.md 执行。

本次只执行：阶段 10 / 后台任务持久化、外部通知适配和风险报表快照。
先阅读阶段 2 至阶段 9 的模型、迁移、认证、组织隔离、结构化分析、履约通知、风险台账和报表测试，不要重写认证，不要删除旧 documents、uploads、analysis_results、原始 AI 响应、结构化历史版本、风险历史、通知历史或已有合同业务数据。

要求：
1. 新 API 使用 /api/v1，所有查询强制按当前用户 organization_id 过滤；继续兼容旧 /api、阶段 6 通知和阶段 7 结构化结果接口。
2. 将阶段 9 的风险提醒扫描从请求附带任务升级为可持久化后台任务，支持重试、失败状态和幂等恢复；外部通知适配必须可插拔，默认 fake provider，不发送真实消息。
3. 通知发送失败不得回滚风险整改状态或历史记录；保留通知去重键和旧履约通知语义。
4. 增加按日风险报表快照，支持趋势历史、合同排行、负责人负荷和逾期率查询与导出；快照任务必须组织隔离。
5. 复用现有 FastAPI、SQLAlchemy、Vue 3、Pinia 和 Element Plus 结构，先补 Alembic 迁移，再补服务、API、前端和测试。
6. 测试只使用临时 SQLite、脱敏数据、fake provider 和可控时钟，不调用真实 OCR、DeepSeek、邮件、短信或桌面通知，不修改生产数据库。
7. 完成后运行 npm run build、npm run typecheck、npm run lint:python、npm run test:python，并更新阶段报告和下一阶段提示词。
```
