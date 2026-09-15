# TPC 工作区约定（Copilot 自动加载入口）

> 本文件是**薄壳**，只做转指。**唯一事实来源是 [`../skills/`](../skills/)**。
> 修改规则请改 `skills/` 下的文件，不要改这里。

---

## 先读哪个

| 你的任务 | 读 |
|---|---|
| 用 TPC 建模型、跑仿真、读结果（**使用者视角**，不改库） | [`skills/user/tpc-usage.md`](../skills/user/tpc-usage.md) |
| 改 `cst_solver` / `mesh_grid` / `topo_modeler` / `topo_templates` / `tpc_toolkit` 的源码（**开发者视角**） | [`skills/developer/WORKFLOW.md`](../skills/developer/WORKFLOW.md) ← 先读这个 |
| 给 `cst_solver` 加 VBA 封装 / 修封装层缺陷 | [`skills/developer/cst-solver-dev.md`](../skills/developer/cst-solver-dev.md) |
| 了解包结构 | [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) |

---

## 硬约定（踩过的坑，违反必出问题）

1. **z 平面**：所有多边形给 **CCW 绕向**（有向面积 > 0）+ 内部 `translate -h/2`。
   `ExtrudeCurve` 沿多边形**法向**拉伸，绕向决定方向：**CCW → +z，CW → −z**。
   绕向错了，实体之间在 z 上差一个 `h`，布尔求交得**空集且不报错**。
2. **布尔语义**：`Intersect "A","B"` → 结果留 **A**、B 被消耗；
   `Add/Subtract "A","B"` → 结果在 A、**B 被删除**；`Insert` 保留 B。
3. **CST 不抛异常**：库不保证把 CST 报错转成 Python 异常。
   验收必须读 `app.cst_file.get_messages()`（读后即清空），并跑 `Rebuild()`。
4. **`add_to_history` 是唯一执行通道**；`log_flag=0` 时只拼字符串不下发 ——
   这是把「画线+拉伸+旋转+平移」合成**一条**历史的手法。
5. **相对路径**按当前工作目录解析，模板 `tmp.cst` 必须放 notebook 同目录。
6. `cst_file.modeler` 已废弃 → 用 `cst_file.model3d`。

---

## 开发铁律

1. **一次只改一个包**，并为这个包单独写一条 commit（详细 commit message，禁止 `"update"`）。
2. **改代码必须同步文档**：公开 API → `setup.pyi` + 重跑文档生成器；包结构 → `docs/ARCHITECTURE.md` + `docs/packages/*.md`。
3. **拼写错误必须修，但不许静默破坏兼容**：加正确名 + 旧名作别名，再登记弃用。
4. **阶段判定**：先看 [`docs/next_plan/`](../docs/next_plan/)。
   属于已完成阶段（0–3）的问题 → 直接改代码；属于未开始阶段（4+）→ **只完善计划，不写实现**。
5. **不要用 `sys.path.append`**：本仓库通过 `pip install -e .` 安装。

---

## 仓库包一览

| 包 | 职责 | 需要 CST |
|---|---|---|
| `cst_solver/` | CST VBA → Python 封装（24 个 Mixin 聚合成 `setup`） | ✅ |
| `mesh_grid/` | 三角晶格 / 六边形晶格算法（含 `TopoPath` 路径 DSL） | ❌ |
| `topo_modeler/` | 建模引擎：`TopoModeler` + `builders/` 各部件构建器 | ✅ |
| `topo_templates/` | 端到端器件模板 | ✅ |
| `tpc_toolkit/` | S 参数解析、遗传算法、等效介质公式 | ❌ |

细节见 [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)。
