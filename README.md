# 合同分析系统逆向恢复源码

本目录由已打包程序 `D:\工具\合同分析系统\合同分析系统` 恢复。原安装目录未被修改。

## 恢复范围

- Electron 主进程及 preload：从内嵌源码映射逐字提取原 TypeScript。
- Vue 渲染层：根据生产 bundle 恢复为 Vue 3 + TypeScript 单文件组件，同时保留格式化后的原生产 bundle。
- Python 后端：从 PyInstaller 归档提取 Python 3.11 字节码并重建源码。13 个业务模块、83 个递归代码对象经标准化比较均达到逐指令等价。
- 提示词、构建脚本、依赖清单和打包配置均已整理。

原始注释、空行、Vue 源文件变量名等编译时被删除的信息无法逐字找回。详见 `RECOVERY_REPORT.md`。

## 开发运行

要求：Node.js 20+、Python 3.11。

```powershell
cd python_backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
cd ..
npm install
npm run dev
```

应用开发模式会由 Electron 自动启动 `python_backend\main.py`。

阶段 1 基础检查：

```powershell
npm run typecheck
npm run lint:python
npm run test:python
```

后端配置示例见 `python_backend/.env.example`，阶段 1 的迁移、密钥和验收说明见 `STAGE1_ENGINEERING_BASELINE.md`。

阶段 2 的合同领域模型、历史数据迁移规则和对账结果见 `STAGE2_DOMAIN_MIGRATION.md`。

阶段 3 的登录、组织权限、会话和审计说明见 `STAGE3_AUTH_AND_PERMISSIONS.md`。

阶段 4 的合同台账、文件版本、回收站和导入流程见 `STAGE4_CONTRACT_LEDGER.md`。

## 构建

```powershell
cd python_backend
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\pyinstaller.exe --clean main.spec
cd ..
npm run pack
```

Electron 安装包输出到 `release`。

## 安全提醒

API 密钥只从应用设置或环境变量读取，源码不再提供默认百度 OCR 凭据。PyInstaller 配置不会把本地 `.env` 文件复制进发布包；`.env` 仍被 `.gitignore` 排除。此前已经构建或分享过的包如果包含旧密钥，应在对应服务控制台轮换密钥后重新构建。
