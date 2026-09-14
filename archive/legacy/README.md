# archive/legacy

本目录存放**已确认无人引用**的历史文件，仅作留档，不参与运行与打包。

| 文件 | 原位置 | 说明 |
|---|---|---|
| `_result_dead_duplicate.py` | `cst_solver/_result.py` | `cst_solver/_result_core.py` 的**陈旧重复副本**（307 行 vs 107 行），全仓库零引用。其中的 `class result(Result)` 还把 `Result` 已有的方法**逐条重抄了一遍**，属于死代码。真正在用的是 `_result_core.py`，由 `cst_solver/__init__.py` 以 `result` 之名导出。 |

**不要**从这里 import 任何东西。如需恢复，先确认当前代码确实缺少该能力。
