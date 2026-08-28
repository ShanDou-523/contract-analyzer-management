# 阶段 10 持久化后台任务、通知适配和风险日报快照

## 状态

已完成。阶段 10 在保留认证体系、组织权限、审计记录以及旧 `documents`、`uploads`、`analysis_results`、原始 AI 响应、结构化分析版本、风险、通知和合同业务数据的前提下，将阶段 9 的请求附带扫描升级为可恢复的持久化任务，并补齐外部通知适配边界和每日风险报表快照。

## 已实现

- 新增 `background_jobs` 持久化队列，支持任务优先级、可执行时间、租约、尝试次数、指数退避、最终失败、人工重试、结果和错误记录。
- 任务领取使用条件更新和租约；worker 启动及轮询时可恢复超时的 `running` 任务。唯一幂等键与数据库保存点共同避免并发重复入队。
- 阶段 9 风险提醒扫描改为持久化任务，原 `POST /api/v1/risks/reminders/scan` 仍兼容返回 `202 queued`。
- 新增通知投递记录和 Provider 协议。默认 `fake` Provider 只生成确定性的模拟消息 ID，不访问邮件、短信或桌面服务；同一通知与 Provider 只建立一条投递记录。
- 通知扫描、投递调度、单条投递和风险快照均由同一 worker 执行。投递失败只更新任务及投递状态，不回滚风险整改、站内通知或历史记录。
- 新增按组织、按日期唯一的风险日报快照，保存风险总数、待处置、逾期、严重、已关闭、逾期率、合同排行和负责人负荷；同日重复生成会更新当天快照。
- 风险快照支持分页、日期筛选和 UTF-8 CSV 导出；后台任务、投递记录和快照查询均强制使用当前用户的 `organization_id`。
- 风险台账增加“自动化与历史”区域，可查看日报快照、后台任务和通知投递，管理角色可生成快照、调度投递和重试失败任务。
- API 默认启动嵌入式 worker；多进程部署可关闭嵌入式 worker 并运行独立 `python_backend/worker.py`。

## 任务类型

| 类型 | 说明 |
|---|---|
| `risk_reminder_scan` | 扫描风险整改到期/逾期提醒 |
| `notification_dispatch` | 为尚未投递的站内通知建立投递任务 |
| `notification_delivery` | 通过配置的 Provider 投递单条通知 |
| `risk_report_snapshot` | 生成或更新组织当日风险快照 |

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/background-jobs` | 查询当前组织后台任务，支持类型和状态筛选 |
| GET | `/api/v1/background-jobs/{id}` | 查询当前组织单个任务 |
| POST | `/api/v1/background-jobs/{id}/retry` | 重新排队最终失败任务（管理角色） |
| POST | `/api/v1/notification-deliveries/dispatch` | 排队通知投递调度（管理角色） |
| GET | `/api/v1/notification-deliveries` | 查询当前组织通知投递记录 |
| POST | `/api/v1/risk-reports/snapshots` | 排队生成今日风险快照（管理角色） |
| GET | `/api/v1/risk-reports/snapshots` | 分页查询当前组织风险快照 |
| GET | `/api/v1/risk-reports/snapshots/export` | 导出当前组织风险快照 CSV |

## 配置与运行

默认配置适合单 API 进程开发环境：

```dotenv
CONTRACT_ANALYZER_BACKGROUND_WORKER_ENABLED=true
CONTRACT_ANALYZER_BACKGROUND_WORKER_POLL_SECONDS=2
CONTRACT_ANALYZER_BACKGROUND_JOB_LOCK_TIMEOUT_SECONDS=300
CONTRACT_ANALYZER_NOTIFICATION_PROVIDER=fake
```

生产多进程部署应只运行一个 worker，或使用支持并发任务领取的数据库。关闭 API 内置 worker 后可独立运行：

```powershell
cd D:\工具\合同分析系统_逆向源码\python_backend
$env:CONTRACT_ANALYZER_BACKGROUND_WORKER_ENABLED='false'
.\.venv\Scripts\python.exe worker.py
```

当前版本只内置 `fake` Provider；配置其他名称会明确失败并进入任务重试，不会静默发送真实消息。

## 数据库迁移

```powershell
cd D:\工具\合同分析系统_逆向源码\python_backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

新增 revision `0010_background_jobs_snapshots`，创建 `background_jobs`、`notification_deliveries` 和 `risk_report_snapshots`。迁移不删除、不覆盖旧表或业务记录；降级操作保留任务、投递和快照历史，避免误删运维证据。

## 验收结果

- 阶段 10 专项测试覆盖空库迁移、幂等入队、租约超时恢复、风险扫描、fake 投递、失败重试、最终失败、快照统计、API 权限、组织隔离和 CSV 导出，共 2 项通过。
- 全部 Python 测试共 23 项通过；测试使用临时 SQLite、脱敏数据、fake Provider 和可控执行，不调用真实 OCR、DeepSeek、邮件、短信或桌面通知。
- `npm run build`、`npm run typecheck`、`npm run lint:python` 和 `npm run test:python` 均通过。
- 生产数据库已升级到 `0010_background_jobs_snapshots`；迁移前后旧数据计数保持：`documents=28`、`analysis_results=56`、`contracts=28`、`contract_files=28`、`file_versions=28`、`analysis_runs=28`、`uploads=28`、`users=2`。
- 运行态定时任务已成功完成风险提醒扫描、通知投递调度和当日风险快照；风险及通知业务状态未被测试投递修改。

## 已知限制

- 当前生产数据仍使用 SQLite。单 worker 运行可靠，多 worker 高并发部署建议迁移到支持更强行级锁和并发控制的数据库。
- 任务调度由 worker 轮询实现，没有引入 Redis、Celery 或独立消息中间件；进程不可用期间任务会保留，恢复后继续执行，但没有进程外存活探针和告警。
- 快照保存的是生成时刻的汇总及排行，不保存每条风险的完整历史副本；同日重跑更新当天快照。
- 真实邮件、短信或桌面通知尚未启用。接入时应新增独立 Provider、密钥配置、限流和供应商回执测试，不能替换或绕过现有站内通知和幂等键。

## 后续生产发布验收 AI 提示词

```text
你正在验收 D:\工具\合同分析系统_逆向源码。阶段 0 至阶段 10 的业务开发已经完成，本次只执行生产发布准备和最终验收，不新增业务阶段。

先阅读 README.md、STAGE1_ENGINEERING_BASELINE.md 至 STAGE10_BACKGROUND_AUTOMATION.md，检查 git status、当前提交和数据库备份条件。不要重写认证，不要删除或改写 documents、uploads、analysis_results、原始 AI 响应、结构化历史版本、风险、通知、后台任务、快照或已有合同业务数据。

要求：
1. 对阶段 0 至阶段 10 做迁移链、组织隔离、权限、审计、幂等、任务恢复、fake 通知和关键前端流程的最终回归。
2. 在不接入真实外部服务的前提下检查生产配置模板、密钥管理、备份恢复、日志轮转、worker 单实例策略和健康检查。
3. 构建可发布产物并在全新临时目录做安装/启动冒烟测试；不得覆盖现有安装目录和生产数据库。
4. 测试只使用临时数据库、脱敏数据和 fake Provider，不调用真实 OCR、DeepSeek、邮件、短信或桌面通知。
5. 运行 npm run build、npm run typecheck、npm run lint:python、npm run test:python，记录版本、测试数量、迁移 revision、旧数据对账和残余风险。
6. 仅在全部通过后更新最终验收报告、提交并推送；发现阻断问题先修复并回归，不得通过删除历史数据规避问题。
```
