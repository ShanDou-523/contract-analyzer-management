# 阶段 1 工程基础验收报告

## 状态

通过。阶段 1 建立配置、迁移、日志、异常、provider 和测试边界，不改变现有合同业务模型。

## 已完成

- 使用 Pydantic Settings 统一读取环境变量，支持 `local`、`staging`、`production`。
- 增加 `CONTRACT_ANALYZER_DATA_DIR`、`CONTRACT_ANALYZER_DATABASE_URL` 和 `CONTRACT_ANALYZER_UPLOAD_DIR`，测试环境可隔离数据库和文件目录。
- 使用 Alembic 管理数据库版本；`0001_baseline` 以现有 SQLAlchemy 模型建立基线，不删除旧数据。
- 增加 request_id、user_id、organization_id、task_id 和请求耗时日志字段。
- 增加统一错误响应：`code`、`message`、`details`、`request_id`。
- 增加 `/api/health/ready`，分项检查 database、redis、storage、ocr、ai，检查结果不返回密钥。
- 增加 OCR、AI、文件存储和数据库会话 provider 协议，现有百度 OCR/DeepSeek 仍为默认实现。
- 使用 Fernet 对 settings 表中的 provider 密钥加密；启动时会把旧版明文密钥迁移为密文。
- 增加 pytest、ruff、ruff format 和前端 `vue-tsc` 命令。

## 配置

开发环境可以复制 `python_backend/.env.example` 为 `.env`。生产环境应通过安全的环境变量或密钥注入系统提供 `CONTRACT_ANALYZER_SECRET_KEY`，不要把 `.env` 或 `.contract_analyzer_secret.key` 提交到 Git。

未配置自定义数据目录时，源码运行使用 `python_backend` 目录；打包运行使用系统应用数据目录。设置 `CONTRACT_ANALYZER_DATA_DIR` 后，数据库、上传目录和自动生成的 Fernet 密钥均可迁移到指定目录。

## 数据库迁移

应用启动会执行：

```powershell
cd D:\工具\合同分析系统_逆向源码\python_backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

应用入口的 `init_db()` 会先升级迁移，再执行历史模板回填、内置模板种子和旧密钥加密迁移。首次在旧库上启动前仍应备份数据库和 `uploads`。当前 `0001_baseline` 是不可破坏的基线 revision，`downgrade` 不主动删除表；需要回滚时恢复阶段 0 备份或恢复数据库副本，再启动应用。

## 验证命令

```powershell
cd D:\工具\合同分析系统_逆向源码
npm run typecheck
npm run build
npm run lint:python
npm run test:python
```

同时使用了空 SQLite、临时上传目录和 fake provider 验证，未调用真实 OCR/DeepSeek，也未修改历史生产数据库。

## 已知限制

- Redis、对象存储和真实 provider 的网络连通性只提供 readiness 诊断，不在测试中发起外部请求。
- 当前业务接口仍是旧 `/api/...` 路径，`/api/v1`、登录和组织权限属于后续阶段。
- user_id、organization_id、task_id 目前从请求头作为日志关联占位字段读取，不能替代后续鉴权；业务权限必须在阶段 3 实现。
- `0001_baseline` 只建立当前模型的可审查基线，阶段 2 才新增合同领域表和历史数据迁移。
