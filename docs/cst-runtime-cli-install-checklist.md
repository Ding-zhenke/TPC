# cst-runtime-cli 安装清单（调研版 · 未执行）

> 创建时间: 2026-09-15
> 状态: **仅供审阅，尚未执行任何安装步骤**
> 来源: https://github.com/bbl21/cst-runtime-cli （MIT，31 stars，Python 100%）

---

## 零、先说结论

| 项 | 结果 |
|---|---|
| 该装吗？ | **看你要什么**。它与本项目 `cst_solver` 功能高度重叠，但有独特价值（守卫层、113 工具的统一 JSON 契约、报告引擎） |
| 阻塞项 | 需要 **Python 3.13+**，本机只有 3.11.7 |
| 是否阻塞 | **不阻塞** —— `uv` 可自行下载 3.13，无需动 Anaconda |
| 风险 | 第三方代码 + `bootstrap.py` 会写入工作区；需先审代码 |

---

## 一、环境检测结果（已执行，只读）

```
uv              0.12.9  (2026-09-01)  ✅ 已安装
git             2.55.0.windows.5     ✅ 已安装
python (默认)    3.11.7 (Anaconda)   ⚠️ 低于要求的 3.13+
py launcher     未安装              —（不影响，uv 可代劳）
uv 已管理 Python cpython-3.11.7-windows-x86_64-none  ← 仅此一个
CST 安装         C:\SOFTWARE\CST Studio Suite 2026   ✅ 存在
CST 材料库       ...\Library\Materials               ✅ 存在
```

**缺口：Python 3.13+。** 解决方式（二选一，均不影响现有 Anaconda）：

```powershell
# 方式 1：让 uv 下载一个独立的 3.13（推荐，隔离干净）
uv python install 3.13

# 方式 2：完全不预装，交给 uv run 按 pyproject.toml 自动拉取
```

---

## 二、市场页 vs 真实项目（重要差异）

LobeHub 市场页给的 MCP 配置：

```json
{
  "mcpServers": {
    "bbl21-cst_mcp": { "command": "npx", "args": ["-y", "bbl21-cst_mcp"] }
  }
}
```

**这份配置是错的**，理由：

1. `bbl21/CST_MCP` 仓库实际重定向到 `bbl21/cst-runtime-cli`
2. 该项目是 **Python 项目**（`uv` + `bootstrap.py`），**不是 npm 包**
3. `npx -y bbl21-cst_mcp` 没有对应的 npm 包，跑起来会失败

> ⚠️ 也就是说：**不要**把市场页那段 JSON 直接贴进 `.vscode/mcp.json`。
> 该项目官方文档里**没有提供 MCP server 配置**，只有三种集成方式（见下）。

---

## 三、官方给出的三种集成方式

### 方式 A — AI 工具 skill

解压到 agent 的 skills 目录，结构需包含：

```
skills/cst-runtime-cli/
skills/cst-runtime-optimization/
```

### 方式 B — 直接 CLI（最小侵入）

```powershell
git clone https://github.com/bbl21/cst-runtime-cli.git
cd cst-runtime-cli
python skills/cst-runtime-cli/scripts/bootstrap.py --skill-path skills/cst-runtime-cli/scripts
uv run python -m cst_runtime list-tools
```

### 方式 C — 当 Python 包用

```python
from cst_runtime.core.session import open_project, close_project
from cst_runtime.core.results import get_1d_result
```

---

## 四、待执行清单（勾选式，**均未执行**）

### 阶段 0 — 前置准备

- [ ] **0.1** 先读源码，确认 `bootstrap.py` 会往哪里写文件
      ```powershell
      git clone --depth 1 https://github.com/bbl21/cst-runtime-cli.git <临时目录>
      ```
- [ ] **0.2** 审阅 `skills/cst-runtime-cli/scripts/bootstrap.py`（是否写注册表/环境变量/用户目录）
- [ ] **0.3** 确认落点：**不要** clone 进本仓库根目录，避免污染 `cst_solver` / `mesh_grid`
- [ ] **0.4** `uv python install 3.13`

### 阶段 1 — 安装（方式 B 为例）

- [ ] **1.1** `git clone` 到工作区**外部**目录（如 `D:\tools\cst-runtime-cli`）
- [ ] **1.2** `cd D:\tools\cst-runtime-cli`
- [ ] **1.3** `uv run python -m cst_runtime health-check --auto-fix`
- [ ] **1.4** `uv run python -m cst_runtime list-tools`（应列出 113 个工具）
- [ ] **1.5** 记录 `uv run` 实际用的 Python 版本

### 阶段 2 — 冒烟验证

- [ ] **2.1** 用官方参考工程验证：`skills/cst-runtime-cli/tests/refs/ref_0/ref_0.cst`（四脊喇叭天线，8–12 GHz）
- [ ] **2.2** `uv run python -m cst_runtime inspect-project --project-path <p.cst>`
- [ ] **2.3** 确认不会抢占/关闭你正在用的 CST 会话

### 阶段 3 — 与现有工作区整合（可选）

- [ ] **3.1** 决定是否装 skill 到 agent skills 目录（方式 A）
- [ ] **3.2** 若整合，明确它和 `cst_solver` 的职责边界，避免两套 API 混用
- [ ] **3.3** 更新 `.github/copilot-instructions.md` 说明何时用哪套

### 明确不做

- [x] ~~跑 `npx -y @lobehub/market-cli mcp rate/comment`~~ —— 会对外**公开发布**评分与评论，未经授权
- [x] ~~把市场页的 `npx` 配置写入 `.vscode/mcp.json`~~ —— 配置本身是错的

---

## 五、能力对照（它有什么 / 你已有什么）

### 它的 113 个工具

| 类别 | 数量 | 代表命令 |
|---|---|---|
| 几何建模 | 42 | `define-brick`, `define-cylinder`, `boolean-subtract`, `change-material`, `transform-shape` |
| 工程操作 | 25 | `change-parameter`, `define-port`, `define-mesh`, `inspect-project`, `capture-3d-view` |
| 结果读取 | 11 | `get-1d-result`, `get-2d-result`, `export-run-results`, `list-run-ids`, `generate-report` |
| 优化 | 11 | `create-study`, `ask-study`, `tell-study`, `run-probe-phase`, `run-optimization-step` |
| 会话管理 | 7 | `cst-session-open/close/quit`, `create-blank-project`, `save-project` |
| 远场 | 4 | `export-farfield-grid`, `export-farfield-cut`, `inspect-farfield-monitors` |
| 工作区 | 4 | `init-workspace`, `init-task`, `health-check`, `install-cst-libraries` |
| 项目身份 | 4 | `verify-project-identity`, `infer-run-dir`, `wait-project-unlocked` |
| 审计 | 3 | `record-stage`, `update-status`, `stage-evidence` |
| DOE | 2 | `design-probes`, `analyze-probes` |
| 运行 | 2 | `prepare-run`, `get-run-context` |

### 与本项目 `cst_solver` 的关系

| 维度 | `cst_solver`（本项目） | `cst-runtime-cli` |
|---|---|---|
| 定位 | Python 库，import 即用 | CLI + agent 基础设施 |
| 形态 | 22 个 Mixin，207 方法 | 113 个原子命令，统一 JSON 契约 |
| 调用方式 | `app.create_brick(...)` | `uv run python -m cst_runtime define-brick ...` |
| 参数化 | 拼 VBA 字符串 → `add_to_history` | 同样 VBA 驱动 |
| 审计 | 无 | `stages/` + `logs/production_chain.md` 自动落盘 |
| 报告 | 无 | 内联 HTML/SVG/WebGL，零外部依赖 |
| 优化 | 无 | 11 个 DOE/优化命令 |
| **守卫层** | 无 | **10+ 运行时陷阱拦截（见下）** |

### 它的守卫层（最有价值的部分）

拦截已知 CST 陷阱，并附带 `next_action` 指导：

| 编号 | 陷阱 | 处理 |
|---|---|---|
| T2 | 改参后未重建模型直接仿真 | 拦截 + 提示 |
| T3 | 远场导出后 save 损坏工程 | 强制 `save=False` |
| T4 | S11 复数当 dB 用 | 自动 `20*log10(hypot(real,imag))` |
| T5 | modeler/results session 混用 | 拒绝跨 session |
| T8 | `Abs(E)` 当增益证据 | 拒绝非增益量 |
| T13 | `StoreDoubleParameter` 只改参数表不重建模型 | 警告 |

> 💡 **T13 正是你在 `parameters.py` 里已经处理过的坑** ——
> `para()` 的 `log_flag=1` 会调 `full_history_rebuild()`。
> **T4 也和你的 `read.py`（S2P 解析）直接相关**，值得对照检查。

### 双 Session 模型

- **Modeler session**（COM 读写，`cst.interface`）：建模 / 仿真 / 参数变更
- **Results session**（只读，`cst.results`）：结果读取 / S11 / 远场导出

> 与你 `cst_solver/__init__.py`（`setup`）和 `_result_core.py`（`Result`）的分离思路一致。

---

## 六、风险清单

| 风险 | 等级 | 缓解 |
|---|---|---|
| `bootstrap.py` 写入范围不明 | 🟡 中 | 阶段 0.2 先读代码 |
| clone 到工作区会污染现有包 | 🟡 中 | 装到工作区**外部**目录 |
| Python 3.13 环境与现有 3.11 冲突 | 🟢 低 | `uv` 隔离，不动 Anaconda |
| CST 会话被抢占 | 🟡 中 | 冒烟测试用参考工程，避开你正在用的会话 |
| 两套 API 混用导致混乱 | 🟡 中 | 明确职责边界（阶段 3.2） |
| 许可证兼容 | 🟢 低 | MIT，无冲突 |

---

## 七、下一步

告诉我选哪条路，我再动手：

1. **只读调研** —— 我 clone 到临时目录，把 `bootstrap.py` 和安全相关的代码读一遍，报告它到底会改什么（**推荐先做这步**）
2. **直接装（方式 B）** —— 装到工作区外部，跑 `health-check` + `list-tools`
3. **只做能力对比** —— 不装，把 113 工具逐条对照 `cst_solver` 的 207 方法，输出差距报告
4. **暂不处理** —— 保留这份清单
