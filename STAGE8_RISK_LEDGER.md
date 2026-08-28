# 阶段 8 合同风险台账、整改闭环和复核协作

## 状态

已完成。阶段 8 在保留旧 `documents`、`uploads`、`analysis_results`、原始 AI 响应、结构化历史版本和已有合同数据的前提下，基于 `analysis_risks` 增加组织级风险台账、整改负责人、整改期限、整改说明、状态流转和复核关闭能力。

## 已实现

- `analysis_risks` 增加 `assignee_id`、`remediation_due_at`、`remediation_notes`、`closed_by`、`closed_at` 和 `closure_comment`；阶段 7 的风险标题、说明、严重程度、结构化结果和证据关联保持不变。
- 风险状态支持 `open`、`in_progress`、`accepted`、`mitigated`、`dismissed`、`closed`，状态转换由服务层统一校验；关闭、接受、缓释和排除必须填写复核意见，关闭仅允许复核角色执行。
- 风险负责人只能选择当前组织内的有效用户；查询、负责人校验、合同和结构化结果关联均强制使用当前 `organization_id`，并排除已软删除合同和已替代结构化版本。
- 整改期限按 UTC 计算逾期，组织级汇总和合同级汇总提供总数、状态、严重程度及逾期统计。
- 新增风险台账、合同风险汇总和整改更新 API；所有整改更新写入审计日志，阶段 7 原结构化复核接口继续可用并复用统一状态校验。
- 前端新增“风险台账”导航和筛选、状态/等级/负责人/逾期查询、整改编辑、负责人分配、期限及说明界面；合同详情结构化分析页增加合同风险摘要、负责人、期限和整改入口。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/risks` | 组织级风险分页、搜索、状态/等级/负责人/逾期筛选 |
| GET | `/api/v1/risks/summary` | 当前组织风险总数、状态、等级和逾期汇总 |
| GET | `/api/v1/contracts/{contract_id}/risks` | 当前合同风险明细和合同级汇总 |
| PATCH | `/api/v1/risks/{risk_id}` | 更新整改状态、负责人、期限、说明和复核意见 |

阶段 7 的 `/api/v1/analysis-runs/.../risks/...` 风险复核接口保留，且继续要求复核角色和待复核结构化结果。

## 数据库迁移

```powershell
cd D:\工具\合同分析系统_逆向源码\python_backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

当前 revision 为 `0008_risk_remediation`。迁移使用 Alembic SQLite batch 模式，仅向 `analysis_risks` 增加整改字段、外键和索引，不删除或重写旧表及历史数据；降级不会删除风险整改历史。

## 验收结果

- 阶段 8 专项测试覆盖空库迁移、组织级汇总、逾期筛选、负责人校验、整改字段、状态机、关闭、组织隔离和审计，共 2 项通过。
- 全部 Python 测试共 19 项通过；测试只使用临时 SQLite、脱敏数据和测试令牌，不调用真实 OCR、DeepSeek、邮件或桌面通知。
- `npm run build`、`npm run typecheck`、`npm run lint:python` 和 `npm run test:python` 均通过。
- 生产数据库已升级到 `0008_risk_remediation`；数据计数保持：`documents=28`、`analysis_results=56`、`contracts=28`、`uploads=28`。

## 已知限制

- 阶段 8 提供逾期统计和组织内协作更新，暂未新增外部邮件或桌面通知；后续如接入风险提醒，应复用阶段 6 的幂等扫描/通知机制，并放入后台任务而非 API 请求线程。
- 当前风险台账以结构化结果的最新版本为来源，已替代版本不计入统计；尚未提供跨组织汇总或风险负责人绩效报表。
- 风险定义本身仍由结构化结果版本 API 管理，批准后的字段、证据和风险定义保持不可变；整改元数据可独立更新。

## 下一阶段 AI 执行提示词

```text
你正在开发 D:\工具\合同分析系统_逆向源码，请严格按照《合同分析管理系统分阶段开发手册》和 STAGE8_RISK_LEDGER.md 执行。

本次只执行：阶段 9 / 风险提醒编排、整改协作通知和跨合同风险报表。
先阅读阶段 2 至阶段 8 的模型、迁移、认证、组织隔离、结构化分析、履约通知和风险台账测试，不要重写认证，不要删除旧 documents、uploads、analysis_results、原始 AI 响应、结构化历史版本、风险历史或已有合同业务数据。

要求：
1. 新 API 使用 /api/v1，所有查询强制按当前用户 organization_id 过滤；继续兼容旧 /api 和阶段 7 结构化结果接口。
2. 基于阶段 6 的通知表和幂等扫描模式，增加风险整改到期/逾期提醒；外部通知和定时处理必须在后台任务中执行，不得阻塞 API 请求。
3. 保留阶段 8 风险状态机和批准结构化结果不可变性，通知失败不得回滚风险状态更新。
4. 增加组织级风险趋势、合同风险排名、负责人负荷和逾期整改报表，支持导出和分页。
5. 复用现有 FastAPI、SQLAlchemy、Vue 3、Pinia 和 Element Plus 结构，先补 Alembic 迁移，再补服务、API、前端和测试。
6. 测试只使用临时 SQLite、脱敏数据和 fake provider/clock，不调用真实 OCR、DeepSeek、邮件或桌面通知，不修改生产数据库。
7. 完成后运行 npm run build、npm run typecheck、npm run lint:python、npm run test:python，并更新阶段报告和下一阶段提示词。
```
