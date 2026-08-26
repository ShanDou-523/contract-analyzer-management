# 阶段 0 API 与数据库快照

记录时间：2026-08-26（Asia/Shanghai）

## API 路由快照

### 系统

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` | 后端健康检查 |

### 文档

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/documents/upload` | 上传 PDF 并创建文档 |
| GET | `/api/documents` | 按方案/文件名查询文档列表 |
| GET | `/api/documents/{doc_id}` | 查询文档详情及最新分析结果 |
| PUT | `/api/documents/{doc_id}/template` | 手动归类到分析方案 |
| DELETE | `/api/documents/{doc_id}` | 删除文档和本地文件 |

### OCR、AI 和导出

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/ocr/{doc_id}/process` | 执行百度 OCR |
| POST | `/api/analysis/{doc_id}/analyze` | 执行 DeepSeek 分析 |
| GET | `/api/export/{doc_id}` | 导出合同分析 Excel |

### 分析方案

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/analysis-templates` | 查询方案 |
| POST | `/api/analysis-templates` | 创建方案 |
| PUT | `/api/analysis-templates/{template_id}` | 修改方案并递增版本 |
| DELETE | `/api/analysis-templates/{template_id}` | 删除非默认方案 |
| POST | `/api/analysis-templates/{template_id}/duplicate` | 复制方案 |
| POST | `/api/analysis-templates/{template_id}/set-default` | 设置默认方案 |

### 设置

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/settings` | 查询掩码后的 API 设置 |
| PUT | `/api/settings` | 更新 API 设置 |

## SQLite 快照

数据库：`python_backend/contract_analyzer.db`

| 项目 | 快照值 |
|---|---:|
| 文件大小 | 2,236,416 bytes |
| `documents` | 28 |
| `analysis_results` | 56 |
| `analysis_templates` | 2 |
| `settings` | 3 |
| `documents.status = done` | 28 |
| `PRAGMA quick_check` | `ok` |
| `PRAGMA foreign_key_check` | 空 |

### 表结构摘要

#### `documents`

`id`、`original_filename`、`stored_filename`、`file_size`、`status`、`ocr_text`、`page_count`、`ocr_pages_detail`、`error_message`、`analysis_template_id`、`analysis_template_name`、`analysis_template_version`、`created_at`、`updated_at`。

#### `analysis_results`

`id`、`document_id`、`prompt_type`、`prompt_text`、`response_text`、`tokens_used`、`template_id`、`template_name`、`template_version`、`fields_snapshot_json`、`created_at`。

#### `analysis_templates`

`id`、`name`、`description`、`analysis_focus`、`fields_json`、`review_enabled`、`review_instructions`、`version`、`is_default`、`created_at`、`updated_at`。

#### `settings`

`key`、`value`。当前值包含 DeepSeek 和百度 OCR 配置；具体密钥不写入快照。

## 文件快照

- `python_backend/uploads`：28 个 PDF。
- 总大小：97,778,962 bytes。
- 文件名采用 UUID，数据库 `stored_filename` 与磁盘文件一一对应。
- 文件、数据库和 `.env` 已被根目录及 `python_backend/.gitignore` 排除，不进入 Git。
