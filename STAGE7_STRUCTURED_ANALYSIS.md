# 阶段 7 结构化分析结果、证据和风险复核

## 状态

已完成。阶段 7 在保留旧 `documents`、`uploads`、`analysis_results`、旧 `/api` 分析响应和已有业务数据的前提下，增加组织隔离的结构化结果、证据定位、风险项、版本化修订和人工复核流程。

## 已实现

- `structured_analysis_results` 保存同一分析运行、提示类型下的不可变版本，状态为 `draft`、`in_review`、`approved`、`rejected` 或 `superseded`。
- 结构化结果强制关联组织、合同、分析运行、文件版本和模板版本；从旧原始结果导入时同时保留 `source_result_id`。
- `structured_analysis_fields` 保存字段键、展示名称、JSON 值、文本值、置信度和稳定顺序。
- `analysis_evidence` 保存原文摘录、页码、字符区间和扩展定位信息；每条证据强制关联本次分析使用的文件版本。
- `analysis_risks` 保存风险编码、标题、说明、严重程度、处置状态、关联证据和人工复核意见。
- 旧 `/api/analysis/{document_id}/analyze` 不再删除历史 `analysis_results`，每次分析只追加原始响应，并在合同域内记录成功或失败的 `AnalysisRun` 和审计日志。
- 对上传后立即分析、尚未经过启动迁移的旧版文档，分析入口会在当前组织内幂等补齐合同、原始文件版本和模板版本，不移动或删除上传文件。
- 原始 JSON 可以幂等转换为结构化草稿。字段提取结果映射为结构化字段；合理性检查中的问题映射为风险项，合同标注映射为证据。
- 草稿或已驳回版本可提交复核；只有当前最新的草稿或已驳回版本可创建修订，修订后旧版本标记为 `superseded`。
- `system_admin`、`org_admin`、`reviewer` 可处置单条风险并批准或驳回结果；驳回和风险处置必须填写意见，存在开放风险时不能批准。
- 结构化创建、导入、修订、提交、风险处置、批准和驳回均写入审计日志。所有 `/api/v1` 查询按当前 `organization_id` 过滤，并排除已软删除合同。
- 合同详情新增“结构化分析”页签，可切换分析运行，查看字段、证据和风险，并按角色执行导入、提交、风险处置、批准和驳回。
- 统一参数校验错误会把异常上下文安全转换为 JSON，继续返回稳定的 `VALIDATION_ERROR` 响应。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/contracts/{contract_id}/analysis-runs` | 查询当前组织合同的分析运行和最新结构化结果 |
| GET | `/api/v1/analysis-runs/{run_id}` | 查询单次分析运行和最新结构化结果 |
| GET | `/api/v1/analysis-runs/{run_id}/structured-results` | 查询运行下全部结构化历史版本 |
| POST | `/api/v1/analysis-runs/{run_id}/structured-results/import-legacy` | 幂等转换旧原始结果 |
| POST | `/api/v1/analysis-runs/{run_id}/structured-results` | 创建结构化结果 |
| POST | `/api/v1/analysis-runs/{run_id}/structured-results/{result_id}/revisions` | 从当前可编辑版本创建修订 |
| POST | `/api/v1/analysis-runs/{run_id}/structured-results/{result_id}/submit` | 提交人工复核 |
| POST | `/api/v1/analysis-runs/{run_id}/structured-results/{result_id}/review` | 批准或驳回结构化结果 |
| PATCH | `/api/v1/analysis-runs/{run_id}/structured-results/{result_id}/risks/{risk_id}` | 处置单条风险项 |

查询接口对全部已登录角色开放。创建、导入、修订和提交需要 `system_admin`、`org_admin`、`contract_manager` 或 `reviewer`；风险处置和结果审批需要 `system_admin`、`org_admin` 或 `reviewer`。

## 数据库迁移

```powershell
cd D:\工具\合同分析系统_逆向源码\python_backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

当前 revision 为 `0007_structured_analysis_review`。迁移只新增 `structured_analysis_results`、`structured_analysis_fields`、`analysis_evidence`、`analysis_risks` 四张表及约束、索引，不删除或重写旧表和已有业务数据。降级不会删除分析与复核历史；回滚应停止服务并恢复升级前备份。

## 验收结果

- 阶段 7 专项测试使用临时 SQLite、脱敏数据和 fake DeepSeek，覆盖空库升级、上传文档域桥接、原始结果历史保留、分析运行、幂等导入、字段/证据/风险映射、版本化修订、状态机、风险处置、审批、角色权限、组织隔离和审计。
- 全部 17 项 Python 测试通过；测试不调用真实 OCR、DeepSeek、邮件或桌面通知，不修改生产数据库。
- `npm run build`、`npm run typecheck`、`npm run lint:python` 和 `npm run test:python` 均通过。
- 构建仍有 Vite 大 chunk 提示；它是既有打包优化提示，不影响阶段 7 构建通过。
- 测试仍报告旧 Pydantic class-based `Config` 的弃用警告；阶段 7 新 schema 未继续使用该旧写法。

## 已知限制

- 旧 AI 响应只有原文摘录时无法可靠推断页码和字符区间，导入结果会保留摘录并将缺失定位留空，等待后续 OCR 坐标增强或人工补录。
- 当前结构化导入是用户显式触发的确定性转换，不在旧分析请求线程内自动审批或修改 AI 原始响应。
- 当前复核以单个结构化结果为单位，尚无合同级风险台账、风险负责人、整改截止时间和跨合同汇总。
- 结构化字段和证据修订已提供后端版本 API，当前前端主要覆盖查看、导入、提交与复核，复杂字段编辑器可在后续阶段补充。
- 并发创建同一提示类型版本最终由数据库唯一约束兜底；高并发部署可进一步增加事务重试。

## 下一阶段 AI 执行提示词

```text
你正在开发 D:\工具\合同分析系统_逆向源码，请严格按照《合同分析管理系统分阶段开发手册》和 STAGE7_STRUCTURED_ANALYSIS.md 执行。

本次只执行：阶段 8 / 合同风险台账、整改闭环和复核协作。
先阅读阶段 2 至阶段 7 的模型、迁移、认证、组织隔离、合同详情、履约任务、通知和结构化分析测试，不要重写认证，不要删除旧 documents、uploads、analysis_results、原始 AI 响应、结构化历史版本或已有合同业务数据。

要求：
1. 新 API 使用 /api/v1，所有查询强制按当前用户 organization_id 过滤；继续兼容旧 /api 和阶段 7 结构化结果接口。
2. 基于 analysis_risks 建立合同级风险台账，增加负责人、整改期限、整改说明、状态流转、复核关闭和逾期统计；风险与结构化结果、证据、合同保持可追溯关联。
3. 风险状态变更必须鉴权、校验状态并写审计；外部通知或定时处理不得放入 API 请求线程，复用阶段 6 的通知与幂等扫描模式。
4. 增加组织级风险筛选、合同风险汇总和合同详情协作界面，保留已批准结构化结果的不可变性。
5. 复用现有 FastAPI、SQLAlchemy、Vue 3、Pinia 和 Element Plus 结构，先补 Alembic 迁移，再补服务、API、前端和测试。
6. 测试只使用临时 SQLite、脱敏数据和 fake provider/clock，不调用真实 OCR、DeepSeek、邮件或桌面通知，不修改生产数据库。
7. 完成后运行 npm run build、npm run typecheck、npm run lint:python、npm run test:python，并更新阶段报告和下一阶段提示词。
```
