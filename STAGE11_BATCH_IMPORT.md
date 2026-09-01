# 阶段 11 批量上传、OCR/AI 处理和进度管理

## 状态

已完成。阶段 11 在不改写认证、不删除旧 `documents`、`uploads`、`analysis_results` 或历史业务数据的前提下，增加了面向 PDF 合同的批量导入批次。每个文件独立排队 OCR 和 AI 分析，失败项可单独或批量重试，批次进度持久化并可在前端实时查看。

## 已实现

- 新增 `batch_imports` 和 `batch_import_items` 表，保存批次状态、总数、完成数、失败数、百分比、文件哈希、文档关联、当前阶段、任务 ID、错误信息和重试次数。
- 新增 `POST /api/v1/batch-imports`，支持一次选择多个 PDF，单批最多 100 个文件；每个文件独立落盘和建档，非法格式、空文件、超大文件和批内重复文件作为失败项保留，不阻断同批其他文件。
- 每个有效文件拆为两个持久化任务：`batch_document_ocr` 成功后排队 `batch_document_analysis`。OCR 成功后不会重复 OCR，AI 失败重试只从分析阶段继续。
- 复用现有 OCR、DeepSeek 分析、合同台账、分析运行和审计逻辑；任务失败使用阶段 10 的指数退避和最终失败机制，风险、历史结果和已有文档状态不会因单项失败而被删除。
- 新增批次列表、详情、单文件重试和批量重试失败项 API，所有查询和操作强制按当前用户 `organization_id` 隔离，并记录审计。
- 首页增加多选 PDF、批次进度条、文件级阶段/百分比/错误和重试操作；前端每 3 秒轮询批次详情，完成后刷新文档列表。
- 保留原有单文件上传、手动 OCR 和手动 AI 分析接口，不改变旧业务流程。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/batch-imports` | 上传多个 PDF 并排队处理 |
| GET | `/api/v1/batch-imports` | 分页查询当前组织批次 |
| GET | `/api/v1/batch-imports/{id}` | 查询批次及每个文件的进度 |
| POST | `/api/v1/batch-imports/{id}/items/{item_id}/retry` | 重试单个失败文件 |
| POST | `/api/v1/batch-imports/{id}/retry-failed` | 重试该批次可恢复的失败文件 |

## 处理状态

批次：`queued`、`running`、`completed`、`partial`、`failed`、`cancelled`。

文件：`queued`、`ocr_processing`、`ocr_done`、`analyzing`、`done`、`error`。进度按 OCR 50% 和 AI 100% 两个阶段持久化；批次进度为所有文件进度的平均值。

## 数据库迁移

```powershell
cd D:\工具\合同分析系统_逆向源码\python_backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

新增 revision `0011_batch_imports`，只创建批次和批次项表，不改写现有业务表和历史记录；降级保留批次历史，避免删除运维证据。

## 验收结果

- 阶段 11 专项测试覆盖迁移、多个文件入队、非法文件隔离、OCR 后自动排队 AI、批次进度、失败项重试和组织范围，共 1 项通过。
- 阶段 10 与阶段 11 专项测试共 3 项通过；完整 Python 测试共 24 项通过。
- `npm run build`、`npm run typecheck`、`npm run lint:python` 和 `npm run test:python` 均通过。
- 生产数据库升级至 `0011_batch_imports` 后，旧数据计数保持；批次表仅新增批量导入产生的记录。

## 已知限制

- 当前仍使用 SQLite 和单 worker 轮询。批量文件数量很大时建议使用独立 worker 进程和支持更强并发控制的数据库。
- OCR/AI 受百度 OCR、DeepSeek 接口配额、网络和单页图片大小限制；单项失败会明确保留错误并支持重试，不会自动压缩或修改原 PDF。
- 当前批次只支持 PDF，沿用单文件 50MB 限制；真实通知 Provider 仍保持阶段 10 的 fake 默认。

## 后续生产验收提示词

```text
你正在验收 D:\工具\合同分析系统_逆向源码。阶段 0 至阶段 11 的开发已经完成。本次只执行最终发布回归，不新增业务功能。

检查批量导入迁移、组织隔离、权限、审计、每文件 OCR/AI 任务、失败重试、进度轮询、旧单文件接口兼容和历史数据对账。不得重写认证，不得删除 documents、uploads、analysis_results、原始 AI 响应、结构化版本、风险、通知、后台任务或已有合同数据。

使用临时数据库、脱敏 PDF、mock OCR/DeepSeek 和 fake Provider 验证成功、失败、重试、重复文件和中断恢复；不得调用真实 OCR、DeepSeek、邮件、短信或桌面通知。运行 npm run build、npm run typecheck、npm run lint:python、npm run test:python，记录迁移 revision、旧数据计数和剩余风险。
```
