# 源码恢复报告

## 原程序识别

- 桌面壳：Electron 32.2.0。
- 前端：Vue 3.5、Vite 5.4、Element Plus 2.8、Pinia 2.2、Vue Router 4.4。
- 后端：Python 3.11、FastAPI、SQLAlchemy、PyMuPDF、OpenAI SDK、OpenPyXL。
- 后端封装：PyInstaller onedir，入口为 `main.pyc`。

## 恢复精度

| 区域 | 恢复方式 | 结果 |
| --- | --- | --- |
| Electron main | `index.js.map` 的 `sourcesContent` | 原始 TypeScript 内容完整恢复 |
| Electron preload | `index.js.map` 的 `sourcesContent` | 原始 TypeScript 内容完整恢复 |
| Vue renderer | 生产 bundle、路由和组件边界重建 | 业务行为、接口、文案和样式恢复；原 SFC 排版及局部变量名不可恢复 |
| Python backend | PyInstaller 提取 + 两套反编译器 + 字节码校验 | 13 个模块、83/83 个递归代码对象逐指令等价 |

Python 校验使用 Python 3.11 重新编译恢复源码，并在移除行号、NOP、EXTENDED_ARG 等非语义差异后，与原 `.pyc` 比较控制流、异常表和每条指令。最终结果为 `83/83 code objects bytecode-equal`。

## 保留证据

- `production_bundle/`：原 Electron 资源目录中的前端生产 bundle 与源码映射。
- `src/renderer-recovered/`：格式化后的生产 bundle，便于逐行追溯。
- `recovery_evidence/backend_bytecode/`：从 PyInstaller 提取的业务 `.pyc`。
- `recovery_evidence/pylingual_raw/`：现代反编译器的原始输出，仅用于审计，不能代替最终修正源码。
- `recovery_evidence/SHA256SUMS.txt`：交付文件哈希清单。

## 已验证项目

- `npm run build`：Vue renderer、Electron main 和 preload 全部构建成功。
- Python 3.11 `compileall`：通过。
- FastAPI 离线烟雾测试：健康检查、非法上传校验、数据库增删查、详情响应和 Excel 三工作表生成通过。
- 外部 DeepSeek 与百度 OCR 网络调用未执行，以避免消耗额度或修改远端状态。
