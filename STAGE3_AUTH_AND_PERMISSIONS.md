# 阶段 3 用户、组织和权限

## 状态

通过。阶段 3 将系统从单机无身份访问扩展为最小可用的用户、组织、角色、登录会话和审计体系，同时保留旧 `/api/...` 接口作为兼容层。

## 已实现

- `roles`、`user_roles`、`auth_sessions`、`audit_logs` 表。
- `users` 增加失败次数、锁定时间和最近登录时间。
- `documents`、`analysis_templates` 增加 `organization_id`，历史数据由迁移服务回填到历史数据组织。
- `scrypt-v1` 密码哈希，密码最少 10 个字符，不保存明文。
- JWT access token，默认 30 分钟有效；随机 refresh token 只保存 SHA-256 摘要，并支持轮换和撤销。
- 角色：`system_admin`、`org_admin`、`contract_manager`、`reviewer`、`viewer`。
- `/api/v1/auth/login`、`/refresh`、`/logout`、`/me`、`/password`。
- `/api/v1/auth/bootstrap` 首次初始化接口；无用户的新环境可创建首个系统管理员，旧历史库中只有无密码迁移用户时允许本地恢复。
- `/api/v1/users`、`/api/v1/roles` 用户和角色管理接口。
- `/api/v1/contracts` 合同列表、分页、搜索、创建和详情接口，强制按组织过滤。
- 旧文档、OCR、AI、导出、分析方案和设置接口均要求登录；写操作按角色限制。
- 上传、删除、合同创建、用户变更、登录、退出和 provider 密钥变更写入审计日志。
- Electron 前端增加登录/首次初始化页、路由守卫、token 自动注入、401 自动清理会话。

## 首次运行

方式一：复制 `python_backend/.env.example` 为 `.env`，设置：

```text
CONTRACT_ANALYZER_ADMIN_USERNAME=admin
CONTRACT_ANALYZER_ADMIN_PASSWORD=请使用至少10位的随机密码
```

应用启动时会在已有组织中创建管理员，或在新库创建默认组织。方式二：在登录页切换到“首次初始化”，调用 `/api/v1/auth/bootstrap` 创建组织和管理员。生产环境禁止公开 bootstrap，必须通过安全环境变量或受控部署流程初始化。

历史数据库迁移后会存在一个没有密码的 `legacy-migration` 用户，它只用于数据归属和映射，不可直接登录。没有配置管理员环境变量时，local/staging 可通过首次初始化创建实际管理员；production 必须配置 `CONTRACT_ANALYZER_ADMIN_USERNAME/PASSWORD` 后再启动。

## 数据库迁移

```powershell
cd D:\工具\合同分析系统_逆向源码\\python_backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

当前 revision 为 `0003_auth_and_audit`。迁移增加字段和表，不删除合同、文件或分析结果。阶段 3 不提供自动删表 downgrade；回滚应停止服务并恢复阶段 0 备份。

## 权限规则

| 角色 | 主要能力 |
|---|---|
| `system_admin` | 用户、角色、组织和 provider 配置；全部合同操作 |
| `org_admin` | 本组织用户、模板和合同管理 |
| `contract_manager` | 合同、文件、OCR 和 AI 分析 |
| `reviewer` | AI 分析和后续复核操作 |
| `viewer` | 本组织合同和分析结果只读 |

后端始终重新校验权限，前端隐藏按钮只改善体验，不构成安全边界。access token 中包含组织 ID，但每次请求仍从数据库读取当前用户和角色，用户停用后立即失效。

## 验收结果

- 空库升级成功，包含旧表、阶段 2 领域表和阶段 3 认证审计表。
- 旧库复制品升级后：28 条文档、28 条合同、28 个文件版本、28 个分析运行和 56 条分析结果保持不变。
- 11 项后端测试通过，覆盖登录、初始化、refresh/logout 所需模型、角色禁止写入、组织范围查询和审计。
- 前端 `npm run typecheck`、`npm run build` 通过。
- Python `npm run lint:python`、`npm run test:python` 通过。

## 已知限制与下一阶段

- 当前 provider 配置仍是组织无关的应用设置，阶段 10 再接入外部 Secret 管理。
- 旧兼容接口仍返回旧文档结构，新合同台账 UI 和文件版本 API 属于阶段 4。
- refresh token 尚未限制单用户最大会话数；生产运维阶段可增加会话管理和设备撤销。
- 登录失败锁定按用户名计数，尚未增加 IP 级速率限制；外网部署前必须在反向代理和应用层补充限流。

## 下一阶段 AI 执行提示词

```text
你正在开发 D:\工具\合同分析系统_逆向源码，请严格按照《合同分析管理系统分阶段开发手册》和 STAGE3_AUTH_AND_PERMISSIONS.md 执行。

本次只执行：阶段 4 / 合同台账、文件版本和导入。
先阅读阶段 2、阶段 3 的模型、迁移、权限依赖和测试，不要重写认证，不要删除旧 documents、uploads 或 analysis_results。

要求：
1. 新 API 使用 /api/v1，旧 /api 接口保留兼容；所有新查询按当前用户 organization_id 过滤。
2. 实现合同台账分页、排序、筛选、软删除、回收站恢复、文件版本、SHA-256 重复检测、鉴权下载/预览。
3. 上传失败必须清理孤立文件和数据库记录；只支持的文件格式要在 API 和 UI 明确声明。
4. Excel/CSV 导入必须经过预览、校验、确认三步，不能直接覆盖已有合同。
5. 复用现有 FastAPI、SQLAlchemy、Vue 3、Pinia 结构，先补迁移，再补 API、前端和测试。
6. 不调用真实 OCR/DeepSeek；使用临时目录、fake provider 和脱敏测试数据。
7. 完成后运行 npm run build、npm run typecheck、npm run lint:python、npm run test:python，并按阶段完成报告模板汇报。
```
