# 阶段 4 合同台账、文件版本和导入

## 状态

已完成。阶段 4 在不删除旧 `documents`、`uploads` 和 `analysis_results` 的前提下，增加组织隔离的合同台账、文件版本管理、回收站和可审计的 Excel/CSV 导入流程。

## 已实现

- `contracts` 支持分页、搜索、状态筛选、排序和组织范围过滤。
- 合同支持软删除、回收站查询和恢复；不会物理删除合同、分析结果或历史文件。
- `contract_files` 与 `file_versions` 支持同一合同多文件用途和递增版本号。
- 新文件使用生成式存储键写入 `<数据目录>/uploads/contract-files`，原始文件名只作为展示元数据保存。
- 上传前后均校验扩展名和大小；支持 PDF、DOCX、XLSX、CSV，单文件默认不超过 50MB。
- 每个文件计算 SHA-256；同一组织内已有文件内容会返回 409，临时文件会被清理。
- 下载和预览必须同时通过合同、文件和版本的组织归属检查，不能直接拼接路径访问。
- `.xlsx` 和 `.csv` 导入使用独立 `contract_import_jobs` 表，严格经过：上传预览 → 校验 → 确认三步。
- 导入支持中英文表头、金额/日期/枚举校验、文件内编号重复检测和已有合同编号检测。
- 确认导入只新增合同，任何校验错误或重复编号都会拒绝整批写入，不覆盖已有合同。
- 前端新增“合同台账”入口，包含台账筛选、回收站、文件版本操作和导入向导；旧首页分析流程继续保留。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/contracts` | 在册合同分页、搜索、状态筛选、排序 |
| GET | `/api/v1/contracts/recycle-bin` | 回收站分页查询 |
| POST | `/api/v1/contracts` | 创建合同 |
| DELETE | `/api/v1/contracts/{id}` | 移入回收站 |
| POST | `/api/v1/contracts/{id}/restore` | 恢复合同 |
| GET | `/api/v1/contracts/{id}/files` | 文件用途和全部有效版本 |
| POST | `/api/v1/contracts/{id}/files` | 上传新文件版本 |
| GET | `/api/v1/contracts/{id}/files/{file_id}/versions` | 查询版本 |
| GET | `/api/v1/contracts/{id}/files/{file_id}/versions/{version_id}/download` | 鉴权下载 |
| GET | `/api/v1/contracts/{id}/files/{file_id}/versions/{version_id}/preview` | 鉴权预览 |
| POST | `/api/v1/contracts/imports` | 创建导入作业并返回预览 |
| GET | `/api/v1/contracts/imports/{job_id}` | 读取导入预览 |
| POST | `/api/v1/contracts/imports/{job_id}/validate` | 执行导入校验 |
| POST | `/api/v1/contracts/imports/{job_id}/confirm` | 确认新增合同 |

旧 `/api/documents`、`/api/ocr`、`/api/analysis`、`/api/export` 接口保持兼容，阶段4没有切断原有分析流程。

## 数据库迁移

```powershell
cd D:\工具\合同分析系统_逆向源码\python_backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

当前 revision 为 `0004_contract_import_jobs`。迁移只创建导入作业表和索引，不删除任何阶段0至阶段3数据。导入作业保存规范化原始行和校验结果，默认 24 小时后过期。

## 导入模板

必填列为 `name` 或“合同名称”。可选列包括：`contract_no`、`category`、`party_a_name`、`party_b_name`、`project_name`、`department_name`、`sign_date`、`effective_date`、`start_date`、`end_date`、`amount`、`currency`、`tax_included`、`risk_level`、`status`。日期使用 `YYYY-MM-DD`，金额允许千分位和人民币符号，币种使用三位字母。

## 验收结果

- 阶段4专项测试覆盖创建台账、组织权限上下文、文件版本、SHA-256 重复检测、下载/预览、软删除/恢复、CSV 预览/校验/确认和禁止重复确认。
- 所有测试使用临时 SQLite、临时上传目录和脱敏 CSV/PDF 字节，不调用真实 OCR 或 DeepSeek。
- 阶段1至阶段4共 12 项后端测试通过。
- `npm run typecheck`、`npm run build`、`npm run lint:python` 和 `python -m compileall` 通过。

## 已知限制

- 当前版本只实现 XLSX/CSV 导入，不解析旧式 `.xls`；导入最多 5000 行。
- 文件版本删除和永久清理留到后续存储运维阶段，合同软删除只隐藏业务记录。
- 文件预览通过浏览器 inline 响应，DOCX/XLSX 是否直接预览取决于客户端能力，始终提供鉴权下载。
- 旧兼容接口仍返回旧文档结构；阶段5再补合同详情、关联主体和履约任务工作流。

## 下一阶段 AI 执行提示词

```text
你正在开发 D:\工具\合同分析系统_逆向源码，请严格按照《合同分析管理系统分阶段开发手册》和 STAGE4_CONTRACT_LEDGER.md 执行。

本次只执行：阶段 5 / 合同详情、主体关联和履约任务。
先阅读阶段 2、阶段 3、阶段 4 的模型、迁移、组织隔离、文件版本和导入测试，不要重写认证，不要删除旧 documents、uploads、analysis_results 或已导入合同。

要求：
1. 新 API 使用 /api/v1，所有查询强制按当前用户 organization_id 过滤；旧 /api 接口继续兼容。
2. 增加合同详情聚合、甲乙方/联系人关联、履约节点、提醒状态和操作历史；合同软删除规则保持不变。
3. 履约任务必须有状态机、负责人组织范围校验、截止日期校验和审计日志，禁止越权查看或修改。
4. 复用现有 FastAPI、SQLAlchemy、Vue 3、Pinia 和 Element Plus 结构，先补 Alembic 迁移，再补 API、前端和测试。
5. 测试只使用临时 SQLite、脱敏数据和 fake provider，不调用真实 OCR/DeepSeek，不修改生产数据库。
6. 完成后运行 npm run build、npm run typecheck、npm run lint:python、npm run test:python，并更新阶段报告和下一阶段提示词。
```
