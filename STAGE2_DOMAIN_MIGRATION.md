# 阶段 2 合同领域模型与历史迁移

## 状态

通过。阶段 2 在保留旧 `documents`、`analysis_results`、`analysis_templates` 和 `settings` 表的前提下，增加合同管理领域模型，并提供可重复执行的历史数据迁移。

## 新增领域表

- `organizations`、`users`：组织上下文和最小用户占位记录，暂不实现登录与角色权限。
- `contracts`：合同主记录，包含编号、名称、状态、双方、项目、负责人、日期、金额、币种、风险等级、来源和软删除字段。
- `contract_files`、`file_versions`：文件业务身份与实际版本分离，保存 storage key、大小、SHA-256、页数和当前版本。
- `analysis_template_versions`：为现有分析方案建立不可变版本快照。
- `analysis_runs`：保存历史分析任务、文件版本、模板版本、provider、模型、状态、耗时和 token 统计。

旧 `analysis_results` 增加可空 `analysis_run_id` 兼容字段，旧接口和原始响应不删除。结构化字段、证据和风险表留到阶段 6。

## 历史迁移规则

迁移入口为 `services/domain_migration.py:migrate_legacy_data`，由 `database.init_db()` 在 Alembic 升级、模板种子和旧密钥迁移后调用。

- 每个旧 `documents` 通过稳定 UUID 映射到一个 `contracts`，原文档 ID 写入 `legacy_document_id`。
- 每个旧文档生成一个原始 `contract_files` 和一个 `file_versions(version_no=1)`。
- 文件使用数据库中的 UUID 文件名作为 `storage_key`，迁移时计算 SHA-256；文件缺失会进入报告，不会删除数据库记录。
- 每个旧 `analysis_templates` 生成对应的 `analysis_template_versions`，保留字段 JSON、分析重点和审查规则。
- 每个包含旧分析结果的文档生成一个 `analysis_runs(task_type=legacy_analysis)`，所有旧结果通过 `analysis_run_id` 关联。
- 无法可靠推断的合同编号、主体、金额和日期不写入主字段，原始上下文保留在 `metadata_json` 和旧表中。
- 使用稳定 UUID、`legacy_document_id` 和唯一约束保证重复执行不会创建重复业务数据。

报告默认写入：

```text
<数据目录>/migration_reports/stage2_legacy_migration.json
```

报告包含源表数量、目标表数量、旧 ID 到新 ID 映射、缺失文件、重复 SHA-256 和分析运行映射。

## 迁移与回滚

```powershell
cd D:\工具\合同分析系统_逆向源码\python_backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

当前 revision 为 `0002_contract_domain`。阶段 1 的 `0001_baseline` 已限定只创建旧表，避免新领域表被基线提前创建。阶段 2 不提供自动删表 downgrade，因为这会破坏已经迁移的业务数据；回滚应先停止服务，再恢复阶段 0 数据库和 `uploads` 备份。

## 验收结果

使用阶段 0 数据库复制品和原始上传目录验证：

| 项目 | 数量 |
|---|---:|
| 旧 `documents` | 28 |
| 新 `contracts` | 28 |
| 新 `contract_files` | 28 |
| 新 `file_versions` | 28 |
| 新 `analysis_template_versions` | 2 |
| 新 `analysis_runs` | 28 |
| 已关联旧 `analysis_results` | 56 |
| 缺失文件 | 0 |
| 重复文件 SHA-256 | 0 |

专项测试覆盖空库升级、旧库缺列补齐、历史迁移、重复执行、SHA-256、ID 映射和报告生成。全部 9 项后端测试通过。

## 后续边界

- 当前旧 `/api/documents` 接口仍使用旧文档模型，阶段 2 先完成数据双轨和只读对账，不切换前端。
- 阶段 3 实现登录、组织隔离、角色权限和审计，并将 `legacy-migration` 用户替换为真实操作者。
- 阶段 4 再切换合同台账、文件版本上传、下载和软删除 API。
