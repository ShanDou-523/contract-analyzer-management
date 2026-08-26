# 阶段 0 基线报告

## 记录时间

2026-08-26（Asia/Shanghai）

## 源码与运行环境

- 源码目录：`D:\工具\合同分析系统_逆向源码`
- Git：源码目录初始不是 Git 仓库；本阶段初始化本地仓库并创建基线提交。
- Node.js：24.14.0
- npm：11.9.0
- Python 虚拟环境：3.11.15
- FastAPI：0.141.1
- SQLAlchemy：2.0.52
- Pydantic：2.13.4
- 当前虚拟环境没有 pytest/httpx，因此 smoke test 使用 Python 标准库 `unittest`。

## 数据快照

- SQLite 数据库：`python_backend/contract_analyzer.db`
- 数据库文件大小：2,236,416 bytes（以执行快照时为准）
- 合同记录：28 条
- 分析结果：56 条
- 分析方案：2 条
- 上传 PDF：28 个，约 97,778,962 bytes
- 当前历史合同状态：全部为 `done`

数据库和上传文件没有纳入 Git。它们已复制到带时间戳的外部备份目录：

```text
D:\工具\合同分析系统_逆向源码_stage0_baseline_20260826_105505
```

该目录包含 `BACKUP_METADATA.txt` 和 `BASELINE_SHA256SUMS.txt`。备份复制使用 `robocopy /E`，退出码为 1，表示文件已成功复制但存在新文件，不表示失败；复制统计为 90 个文件、约 98.76 MB。

## 已执行验证

### 前端/Electron 构建

```powershell
cd D:\工具\合同分析系统_逆向源码
npm run build
```

结果：通过。Vite renderer、Electron main、preload 均构建成功。Vite 对主 bundle 体积较大给出 warning，但不影响构建。

### Python 编译

```powershell
cd D:\工具\合同分析系统_逆向源码
$env:PYTHONDONTWRITEBYTECODE='1'
.\python_backend\.venv\Scripts\python.exe -m compileall .\python_backend
```

结果：通过。

### 离线后端 smoke test

```powershell
cd D:\工具\合同分析系统_逆向源码\python_backend
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

结果：3 tests OK。测试使用临时 SQLite、临时 uploads 和 fake OCR/DeepSeek，不进入 FastAPI lifespan，不调用真实网络服务，不修改生产数据库和合同文件。

覆盖范围：

1. `/api/health` 返回值与路由注册。
2. 上传 PDF → OCR → AI 分析 → `AnalysisResult` 落库的核心闭环。
3. 非 PDF 文件返回 400 且不会写入文件或数据库。

## 当前基线测试文件

- `python_backend/tests/__init__.py`
- `python_backend/tests/test_smoke.py`

## 已知问题（本阶段只记录，不修复）

- 源码目录此前没有 Git，无法使用原有提交回滚；本阶段已建立本地 Git 基线。
- `.venv` 没有 pytest/httpx，后续阶段再决定是否引入并锁定测试依赖。
- `config.py` 在 import 时固定真实数据库和 uploads 路径，后续需要增加可注入的数据目录/数据库 URL。
- 当前 FastAPI 使用 `allow_origins=["*"]` 和凭据，部署为 Web 服务前必须收紧。
- 当前 OCR/AI 在同步 HTTP 请求中执行。
- 当前重新分析会删除旧分析结果。
- 当前删除接口会直接删除文件和数据库记录。
- 当前密钥存储在 SQLite 的 `settings` 表中，后续必须加密或迁移到 Secret 管理。
- 当前数据库迁移依赖 `create_all` 和手写 `ALTER TABLE`，阶段 1 应引入 Alembic。

## 阶段 0 验收结论

通过。现有代码、历史数据和上传文件已完成外部备份；构建、Python 编译和离线 smoke test 均通过；没有调用真实 OCR/DeepSeek，也没有修改业务模型。

阶段 1 的前置条件是：保留本地 Git 基线提交，后续所有数据库变更使用可审查的迁移脚本，并继续使用 fake provider 做自动化测试。
