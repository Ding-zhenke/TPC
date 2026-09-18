# TPC 总体架构 —— 每个包负责什么

> 这是全仓库的**总包说明**。想知道某个包具体怎么用，读 [`packages/`](./packages/) 下对应的单包文档。
> 最后更新：见 git log。

---

## 1. 一句话定位

TPC 是一个**拓扑光子晶体（Topological Photonic Crystal, TPC）太赫兹器件的自动化建模与仿真工具链**：
用 Python 驱动 CST Studio Suite，把「晶格路径 → 基板 → VPC 区域 → 光子晶体阵列 → 馈源 → 波导 → 端口 → 求解器」
这条建模流水线从手工点鼠标变成可参数化、可复现的代码。

---

## 2. 分层架构

Python 包保持独立使用；面向 AI 的 MCP 服务已按[双入口设计](./architecture/cst_mcp.md)实现首版适配层。真实 CST 建模与 stdio 通道已验证，求解闭环仍待验收；剩余工作只在[统一计划](./next_plan/README.md)维护。

`cst_solver.environment` 负责配置、安装发现和离线诊断；官方接口在实际操作时加载。
`mesh_grid.plotting` 提供共用中文字体配置，不依赖 CST；其他绘图模块复用它，不在导入时修改字体。
`tpc_service` 是后加的**运行服务层**（工程注册 + 任务服务）：Python 脚本与 MCP 适配层共用同一套执行与记录能力，
它**不依赖 MCP**，也不被 `cst_solver` 反向依赖。

```
┌──────────────────────────────────────────────────────────────┐
│  第 4 层  应用层     topo_templates/        直波导 / 单元天线 端到端一键建模   │
│                      tpc_service/    工程注册 + 任务服务（运行记录层）  │
├──────────────────────────────────────────────────────────────┤
│  第 3 层  引擎层     topo_modeler/     TopoModeler（智能推断 + 流水线） │
│                                      builders/（各部件构建器）        │
├───────────────────────────────┬──────────────────────────────┤
│  第 2 层  基础层               │  第 2 层  工具层（旁路）           │
│    cst_solver/  CST 会话封装    │    tpc_toolkit/  数据与优化         │
│    mesh_grid/   晶格/网格算法    │    （不依赖 CST）                  │
└───────────────────────────────┴──────────────────────────────┘
                              │
                     CST Studio Suite（外部，仅 Windows）
```

**依赖方向严格单向**：上层依赖下层，同层之间 `cst_solver` 与 `mesh_grid` **互不依赖**。

```
topo_templates ──▶ topo_modeler ──┬──▶ cst_solver ──▶ cst (CST 自带)
                             └──▶ mesh_grid.tri_grid
tpc_toolkit ──▶ mesh_grid（仅可视化/坐标，可选）        ← 独立，不需要 CST
tpc_service ──▶ cst_solver / topo_modeler / topo_templates   ← 运行记录层，不依赖 MCP
```

---

## 3. 六个包的分工

| 包 | 一句话职责 | 是否需要 CST | 主要入口 | 详细文档 |
|---|---|---|---|---|
| **`cst_solver/`** | 把 CST 的 VBA 宏 API 封装成 Pythonic 的 `setup` 对象 | ✅ 必须 | `setup`, `result` | [packages/cst_solver.md](./packages/cst_solver.md) |
| **`mesh_grid/`** | 纯数学：六边形/三角形晶格的生成、坐标换算、可视化、DXF 导出 | ❌ 不需要 | `HexLib`, `TopoPath` | [packages/mesh_grid.md](./packages/mesh_grid.md) |
| **`topo_modeler/`** | 建模引擎：把「路径 + 参数」变成完整 CST 模型 | ✅ 必须 | `TopoModeler`, `builders.*` | [packages/topo_modeler.md](./packages/topo_modeler.md) |
| **`topo_templates/`** | 端到端模板：一个类 = 一个器件，填参数就出模型 | ✅ 必须 | `StraightWaveguide`, `UnitAntenna` | [packages/topo_templates.md](./packages/topo_templates.md) |
| **`tpc_toolkit/`** | 独立工具：S 参数解析、遗传算法算子、等效介质公式 | ❌ 不需要 | 各子模块函数 | [packages/tpc_toolkit.md](./packages/tpc_toolkit.md) |
| **`tpc_service/`** | 会话、任务、执行记录：工程注册 + 任务服务；不依赖 MCP | ⚠️ 看后端（假后端可离线） | `RunService` | [packages/tpc_service.md](./packages/tpc_service.md) |

### 3.1 `cst_solver/` —— CST 会话封装层

**它是什么**：CST Studio Suite 的 VBA 接口是「拼一段宏字符串再下发到历史树」。
本包把这套宏 API 收敛成 **24 个 Mixin 类**，再用多继承聚合成一个 `setup` 类，
于是 200+ 个 CST 操作都可以通过同一个 Python 对象调用。

**它解决什么**：不用记 VBA 语法、不用手拼宏字符串、不用维护 `sys.path` 里的 CST 库路径。

**关键设计**：
- 所有 Mixin 通过 `self.cst_file.model3d.add_to_history(日志名, vba字符串)` 下发命令（**唯一执行通道**）。
- `log_flag=0` 时只返回 VBA 文本、不下发 —— 复合构件（如 `triangle()`）靠这个把多条命令拼成**一条**历史。
- 新方法用 snake_case，旧 VBA 风格名保留为**别名**（如 `create_brick` ↔ `square`）。
- `Result` 类独立于 `setup`，只读已完成的工程结果。

**什么时候用它**：需要 CST 里**任何**原语级操作（画长方体、设端口、跑求解器、读结果）时。

### 3.2 `mesh_grid/` —— 晶格算法层

**它是什么**：与 CST 完全无关的纯算法包，两个子包：

| 子包 | 晶格 | 核心内容 |
|---|---|---|
| `mesh_grid.tri_grid` | 三角晶格 | 三角形网格生成、`(r,c) ↔ (x,y)` 坐标换算、空间选择（线上/线下/多边形内）、最短路径，以及 **`TopoPath` 声明式路径 DSL** |
| `mesh_grid.hex_grid` | 六边形晶格 | 立方体坐标 `(q,r,s)`、错位/六边形排布网格、像素坐标换算、matplotlib 可视化、DXF 导出 |

**它解决什么**：三角/六边形晶格的手工坐标推导极易出错（`x = c·a + r·a/2`、`y = r·a·√3/2`）。
`TopoPath` 把晶格坐标作为**唯一数据源**，直角坐标、CST 表达式、边界框、基板多边形、阵列范围全部自动推导。

**什么时候用它**：需要晶格坐标/路径/预览/DXF 时；`topo_modeler` 的几何全部建立在 `TopoPath` 之上。

### 3.3 `topo_modeler/` —— 建模引擎层

**它是什么**：把「一条晶格路径 + 一组物理参数」翻译成一个完整 CST 模型的编排层。

```
modeler.py       TopoModeler —— 智能推断（直波导 or 天线）+ 流水线编排
name_manager.py  NameManager —— CST 实体命名唯一化（feed_1 / crystal_A / wg_2 …）
builders/        每个部件一个构建器，全部是「无状态函数 + 显式参数」
    substrate.py   基板（沿路径的带状多边形 → 拉伸 → z 居中）
    vpc_region.py  VPC-A / VPC-B 区域 + 与基板求交
    crystal.py     光子晶体阵列（超元胞：triangle×8 → add×4 → subtract×2 → rotate×2 → translate×6）
    feed.py        馈源 3 型：ab_elliptical / ba_tapered / cylinder
    waveguide.py   空心矩形波导（外方体 − 内方体）
    port.py        波导端口（面编号 / 直波导 2 端口 / 天线 1 端口）
    solver.py      时域求解器 + 监视器 + 高级参数（稳态限制、并行、GPU）
lens_build.py    GRIN 透镜（阶段 4，进行中）
```

**它解决什么**：旧 notebook 里每个模型都要手写 200+ 行 `px1,py1,…` 计算与布尔序列。
分层后：`TopoModeler` 一行 `build_all()` 顶一整个 notebook。

**关键设计**：`builders/` 里的函数**不依赖 `TopoModeler` 实例**，可以被单独调用（完全控制模式）。

### 3.4 `topo_templates/` —— 端到端应用层

**它是什么**：每个类对应一个具体器件，内部组装 `TopoModeler` + 参数定义 + 端口 + 求解器。

| 类 | 器件 | 说明 |
|---|---|---|
| `StraightWaveguide` | 拓扑光子晶体直波导 | 2 端口，默认 AB 型、单馈源镜像到两端 |
| `UnitAntenna` | 单元天线 | 1 端口，支持任意 60° 倍数拐弯 + 圆柱辐射体 |

**它解决什么**：同一类器件反复建模时的最高层复用。

> ✅ **命名风险已解决**（2026-09-15，T10）：旧包名 `templates` 过于通用，安装到 site-packages
> 后有与第三方包重名的风险（`import templates` 命中谁取决于 `sys.path` 顺序）。
> 现已更名为 **`topo_templates`**；旧名 `templates` 保留为**一个版本周期的转发 shim**
> （发 `DeprecationWarning`），下一版本周期移除 —— 见
> [`packages/topo_templates.md`](./packages/topo_templates.md) §6.3 与
> [统一计划 P5](next_plan/README.md)。

### 3.5 `tpc_toolkit/` —— 独立工具层（不依赖 CST）

**它是什么**：与仿真软件无关的通用工具，可在任意 Python 环境导入。

| 模块 | 内容 |
|---|---|
| `s2p.py` | CST 导出的 s2p 分组文本解析（`read_s2p_groups`）、按频率/阈值筛选参数组 |
| `ga_optimizer.py` | 遗传算法算子（种群初始化/选择/交叉/变异）、种群落盘、拓扑结构可视化、S 参数适应度 |
| `effective_medium.py` | 六边形面积、等效介电常数（体积加权 / 含空气孔）、介电常数 → 折射率 |

**它解决什么**：仿真前后的数据处理与优化循环，不该被 CST 依赖绑架。

### 3.6 `tpc_service/` —— 共用运行服务层（会话、任务、执行记录）

**它是什么**：把「一次 CST 操作」（`cst_solver`）与「一个器件怎么建」（`topo_modeler`）之间
**缺的那一层**补齐 —— **工程注册 + 任务服务**。它管的是：一个工程怎么被注册进工作目录、
一次任务怎么被提交与排队、执行到哪了、产物落在哪、进程重启后账目是否还对得上。

它**不依赖 MCP**，也**不重写**任何几何 / VBA / 数值逻辑：那些仍然分别属于 `topo_modeler` 与 `cst_solver`。
P3 的 MCP 适配层与 Python 脚本**共用**这一套执行与记录能力，因此不会出现两套行为漂移。

| 模块 | 内容 |
|---|---|
| `service.py` | `RunService`：提交 / 等待 / 查询 / 日志 / 产物 / 结果 / 会话 / 恢复 / 取消 / 关闭 |
| `registry.py` | `ProjectRegistry` / `ProjectRecord` / `copy_project()`：工程注册与工作副本（默认**复制**，`overwrite=True` 才重建） |
| `worker.py` | `SingleWorker`：**一个后台线程 + 一个队列** ⇒ **全局串行**（比「同工程串行」更强） |
| `state.py` | 状态机与记录：`JOB_KINDS = ('build','solve','study')`、`JOB_STATUSES`、`TERMINAL_STATUSES`、`params_digest()`、`JobRecord` |
| `store.py` | `JobStore`：`<workdir>/jobs/<job_id>.json` 原子写 + `<workdir>/events.jsonl`；`ensure_within()` 是**唯一**的产物路径约束入口 |
| `errors.py` | `ServiceError`（`code` / `retryable` / `details`），结构**复用** `cst_solver.failures.structured_error()` |
| `backends/` | `base.py`（契约）、`fake.py`（`FakeBackend`，离线）、`cst_backend.py`（真实 CST，**惰性导入**） |

**几条硬契约**（都有离线测试守着）：

1. **先保存再读**：`solve` / `study` 的 `saved` 不是 `True` 时服务层**直接判 `failed`** ——
   不保存就交给读取器，读到的是**上一轮**的结果；
2. **请求去重**：同 `request_id` + 同参数摘要 ⇒ 返回既有任务（`duplicate=True`），**不重复执行**；
   同 ID 不同参数 ⇒ `request_id_conflict`（参数摘要是稳定 JSON 的 sha256，**键顺序不同不算冲突**）；
3. **重启恢复不自动重跑**：`recover=True`（默认）把磁盘上 `queued` / `running` 的任务标成 `interrupted`；
4. **取消不撒谎**：`queued` 真的取消；`running` 返回 `cancel_not_supported`
   —— 2026-09-17 真机探针已确认 CST 侧**存在** `abort_solver` / `start_solver` /
   `get_solver_run_info`（见 [P4 证据](./validation/p4_real_machine_evidence.md) §4.5），
   但「调用后求解**真的**停下」这件事**必须在一次运行中的求解里验证**（禁止无求解就宣称支持），
   所以接口放开前保持拒绝；
5. **工作目录约束**：所有产物必须落在服务工作目录内，逃逸报 `workdir_escape`；
6. **坏记录不静默丢弃**：读不出来的记录如实变成一条 `failed` 记录（`backend_failed`）。

**它解决什么**：把「复制工程、记账、串行、判断结果是不是本次的、崩了之后对账」这套与器件无关的编排逻辑
从每个脚本里收走一次。

> ⚠️ **证据等级**：服务层行为目前只有**离线**证据（`tpc_service/tests/`，47 项，用假后端）。
> **真实 CST 后端的真机行为尚未验证**，属计划 P4/V7。详见 [`packages/tpc_service.md`](./packages/tpc_service.md)。

---

## 4. 仓库目录结构

```
TPC/
├── README.md                  ← 项目入口
├── pyproject.toml             ← 打包配置：pip install -e .
│
├── cst_solver/                ← 包 1：CST 会话封装
├── mesh_grid/                 ← 包 2：晶格算法
├── topo_modeler/              ← 包 3：建模引擎
├── topo_templates/                 ← 包 4：端到端模板
├── tpc_toolkit/               ← 包 5：独立工具
├── tpc_service/               ← 包 6：共用运行服务（工程注册 + 任务服务）
│
├── docs/                      ← 文档（本目录）
│   ├── README.md              文档索引
│   ├── ARCHITECTURE.md        总体架构（本文件）
│   ├── packages/              每个包一份说明
│   ├── guides/                使用指南 + 自动生成的 API HTML
│   └── next_plan/             唯一未完成计划
│
├── skills/                    ← 技能文档（给 AI 助手读的规则）
│   ├── user/                  使用者视角：怎么用库把模型建出来
│   └── developer/             开发者视角：怎么维护/扩展库（含工作流规则）
│
├── scripts/                   ← 仓库级工具（文档生成等）
├── tests/                     ← 跨包测试
├── examples/                  ← 示例 notebook
├── assets/sat/                ← 参考几何文件（.sat）
└── archive/                   ← 归档：兼容 shim、一次性脚本、MATLAB 旧代码
```

---

## 5. 环境与安装

```bash
# 在仓库根目录执行一次即可
pip install -e .

# 需要 DXF 导出 / 透镜几何运算时
pip install -e ".[all]"
```

安装后**不再需要 `sys.path.append(...)`**，直接用：

```python
from cst_solver import setup, result
from mesh_grid.tri_grid import TopoPath
from topo_modeler.builders import build_feed
from topo_templates import StraightWaveguide
from tpc_service import RunService          # 工程注册 + 任务服务（不传 backend 则用真实 CST 后端）
```

> `cst` 模块由 CST Studio Suite 自带，**不能**从 PyPI 安装；
> `cst_solver` 按需加载官方接口，配置优先使用环境变量或用户 JSON，旧 config.py 仍兼容。详见 [环境指南](./guides/cst_environment.md)。
>
> **DE 生命周期已真机核实**（P4/V8，2026-09-17）：路径错误在**建 DE 之前**暴露、打开失败的工程会清掉自有 DE、
> **先关工程后 DE 仍存活**（须再关 DE 才回到基线）；`doctor --probe` 的 `status=importable`
> 只表示**接口可加载**，**不代表**许可/仿真可用。见 [P4 真机验收记录](./validation/p4_real_machine_evidence.md) §1。

---

## 6. 核心硬约定（跨包通用，踩过的坑）

1. **z 平面**：所有多边形给 **CCW 绕向**（有向面积 > 0）+ 内部 `translate -h/2`。
   `ExtrudeCurve` 沿**多边形法向**拉伸，法向由顶点绕向决定：
   **CCW → +z，CW → −z**。绕向错了，实体之间会在 z 上差一个 `h`，
   布尔求交得到**空集且不报错**。
2. **布尔语义**（CST 官方帮助原文核对过，2026-09-15）：
   - `Intersect "A","B"` → 交集，**结果留 A**，B 被消耗；
   - `Add "A","B"` → 并集，结果在 A，**B 被删除**；
   - `Subtract "A","B"` → **差集 `A − B`**，结果在 A，**B 被删除**；
   - `Insert "A","B"` → **差集 `A − B`，但不删除 B**
     （官方原文：*"Performs an subtraction between the solids solid1 and solid2
     (solid1 - solid2) but does not delete solid2"*）。
     ⚠️ 常见误记为「并集」—— 某第三方整理的 VBA 参考就是这么写错的，
     曾导致对照参考工程时误判 VPC-B 的形状。
3. **阵列范围**：光子晶体阵列的 `xup / yup / ydn` 必须覆盖**整个基板**，不能只按路径推断。
   并且 —— 阵列次数必须写成**CST 参数引用**（`int(xup)` / `int(yup/2)` / `int(ydn/2)`，
   与参考工程逐字一致），**不许**把 Python 值烘成数字（`int(25)`）：烘了数字参数表里的
   `xup/yup/ydn` 就没人引用，改参数不动几何（2026-09-17 真机取证，见
   [P4 真机证据](./validation/p4_real_machine_evidence.md) §8.7；
   回归 `topo_modeler/tests/test_crystal_array_expression.py`）。
4. **失败有两条通道**（2026-09-17 真机修正，见 [P4 真机证据](./validation/p4_real_machine_evidence.md) §3）：
   ① `model3d.add_to_history()` **可能直接抛 Python `RuntimeError`**，异常文本里带 CST 原文；
   ② 有的失败**只写消息**，不抛异常。所以验收既要接异常，也要读
   `app.cst_file.get_messages()`，并跑 `Rebuild()` 重放历史。
   ⚠️ `get_messages()` **不是「读一次就干净」**，历史失败会反复出现 ——
   **「消息为空」不得当作唯一的成功判据**（见第 10 条）。
   阶段 5 起有 API 支撑，不用再自己抄这三步：
   **`app.validate_model()` → `{status, messages, rebuild_ok, before, guard}`**（不抛异常，按 `status` 分流）。
5. **参数改了必须重建历史，否则仿真是旧几何**（阶段 5 起有守卫层兜底）。
   ⚠️ **`log_flag` 在两类方法里含义不同，不要互相类推**：
   几何类方法（`polyline`/`extrude`/`translate`…，默认 `1`）的 `log_flag=0`＝**只返回 VBA 文本不下发**；
   `para()`/`paras()`（默认 `0`）的 `log_flag=0`＝**写入参数表但不调用 `full_history_rebuild()`** ——
   参数确实存进去了，只有几何悄悄停在旧值上，从返回值看不出任何异常。
   改完参数要么传 `log_flag=1`，要么调用 `app.update()`。
   守卫层（`cst_solver/_guards.py`）会在 `run()` 前拦截这一条（陷阱 T2），
   默认 `mode='warn'` 只警告、`'strict'` 抛 `CstGuardError`；`'off'` 与引入前逐字节一致。
6. **相对路径**按**当前工作目录**解析，模板 `tmp.cst` 必须放在 notebook 同目录。
7. `cst_file.modeler` 已废弃 → 用 `cst_file.model3d`。
8. **面/棱边编号不可移植**：`pick_face` / `pick_edge` 的编号（`'10'`、`'22'` …）是 CST 内部编号，
   与实体几何、生成顺序强相关，扭转/布尔/阵列之后会变，跨模型不可复用
   （典型受害者：`topo_modeler/builders/port.py` 里硬编码的端口面号）。
   优先按**坐标**绕开编号 —— `pick_face_at()` / `pick_edge_at()`；
   需要编号时用 `get_face_id_from_point()` 由坐标**反查**；
   校验拾取是否真的生效用 `get_picked_count()`，不要只看有无报错
   （2026-09 真机确认：这是**脏工程里唯一可靠**的判据，理由见第 10 条）；
   轴对齐的矩形端口面可直接用 `create_waveguide_port_free()` 给范围，完全不产生拾取动作。
   > 注意：CST **没有**面法向/面中心/面面积的查询 API（`Solid.GetArea` 返回的是**实体**表面积），
   > 所以"按法向自动找面"必须由参数化几何**正算出一个点**再反查，不能靠遍历已有面匹配法向量。
9. **静默失败必须结构化登记，`unverified` 不等于成功**（P1「核心契约收口」，2026-09）。
   `{code, message, details, retryable}` 的唯一实现是 `cst_solver/failures.py` 的
   `structured_error()`；`cst_solver/expressions.py`、`cst_solver/run_contract.py`、
   `topo_modeler/preflight.py` 都复用它，**不再有第二套**错误结构。
   静默失败（返回 `None`/`[]`/`False` 却只写一条 `logging.warning`）必须走
   `record_failure()` 登记，`collect_failures()` 能把一段代码里的静默失败一次收齐 ——
   **「返回 `None`/`[]`/`False` 不等于成功」**。同理，求解结果由
   `cst_solver/run_contract.py` 判定：只有「提交未抛异常 + `get_messages()` 为空 +
   结果存在 + 结果指纹提交前后变化」同时成立才是 `succeeded`，否则如实给
   `failed` / `unverified`，**`unverified` 不得被当成成功**
   （`results_changed` 是必要条件不是充分条件，真机判据见[统一计划 P4/V7](./next_plan/README.md)）。
10. **CST 失败有两条通道，且历史失败会反复出现；成功判定不许只看消息**（P4 真机，2026-09-17，CST 2026）：
   工程历史里只要留下过**一条失败命令**，之后**每次** `get_messages()` 都会**再次**报出那条
   历史失败，并不是「读一次就清空」。后果：「消息为空 = 成功」在**脏工程**里会**一直判失败** ——
   实测 `pick_face_auto()` 因此一直返回 `None`，而 `GetNumberOfPickedFaces()` 明确是 `1`
   （拾取其实成功了）。判定顺序统一为：**先用正向信号**（已选面数、实体存在性、几何量、
   结果指纹），**取不到时才**退回消息判定 —— 实现见 `cst_solver/modeling/picks.py` 的
   `_pick_succeeded()`（回归用例 `cst_solver/tests/test_picks.py`）。
   真机证据：[P4 真机验收记录](./validation/p4_real_machine_evidence.md) §3。
11. **真机脚本必须检测 CST 弹窗（模态弹窗 = 无声死锁）**（P4 真机，2026-09-17，CST 2026）：CST 在**交互模式**下遇到未定义参数会弹「请输入变量值」，关闭项目/退出时会弹
    「是否保存更改？」—— 这些**模态对话框不会抛异常、也不写 `get_messages()`**，
    而是让 Python 侧的下一次 CST 调用**永久阻塞**。纯文本运行的调用方只能看到「脚本不动了」。
    因此真机脚本：① 建/关 DesignEnvironment 前后都要打窗口与对话框快照；
    ② 重步骤套 `guard(label, timeout)` 看门狗，超时就报「疑似模态弹窗」+ 快照；
    ③ 能离线预检的**先离线预检**（例如透镜的 `Rbig`/`Ls` 在建模前就断言，别等 CST 弹窗）。
    实现：`scripts/cst_dialog_guard.py`（`EnumWindows` 全量枚举、类名 `#32770` 判定对话框、
    `save_prompts()` 识别保存弹窗、`check_dialogs()` 主动断言、`dismiss_dialogs()` 显式关闭且
    **按钮不匹配时绝不盲点**；离线回归 `tests/test_cst_dialog_guard.py`）。
    真机证据：[P4 真机验收记录](./validation/p4_real_machine_evidence.md) §7。
12. **「空结果」不等于「问到了，就是空」**（P1 静默失败审计，2026-09-17）：
    `except` 块里 `pass` / 返回 `None·False·[]·''` / 只写一条日志，都会把
    **「失败」伪装成「正常但没有数据」** —— 调用方据此下的判断是错的。
    规矩：① 已知的静默失败必须走 `cst_solver/failures.py` 的 `record_failure()`
    （返回值可以照旧，但失败进结构化通道）；② **能区分「没有」与「问不到」的接口优先**，
    例如 `topo_modeler.batch.design_environment_query()` 返回 `{ok, pids, reason}`，
    而旧的 `running_design_environments()` 把两种情况都返回 `[]`
    （实测踩过：本机解释器默认导入不到 `cst.interface`，该函数**必然**返回 `[]`，
    差点被当成「没有 DE 活着」的证据）。
    审计：`python scripts/audit_silent_failures.py` 扫 6 个库包里所有「吞异常」的
    `except` 块，**每个站点必须在登记表里写明理由**；落在写/判定路径上的还要求
    `record_failure(...)` 或显式 `risk_ok` 理由。报告：
    [静默失败审计](./guides/silent_failure_audit.md)；回归 `tests/test_silent_failure_audit.py`。

---

## 7. 我要做 X，该动哪个包？

| 需求 | 包 / 文件 |
|---|---|
| 加一个新 CST 原语（VBA 封装） | `cst_solver/modeling/` 或 `simulation/` 对应 Mixin + 同步 `setup.pyi` |
| 修 CST 封装层缺陷 | `cst_solver/`（读 [`skills/developer/cst-solver-dev.md`](../skills/developer/cst-solver-dev.md)） |
| 加一种晶格/坐标变换 | `mesh_grid/tri_grid/core.py` 或 `hex_grid/core.py` |
| 改路径 DSL（`.move/.turn/.line_to`） | `mesh_grid/tri_grid/topo_path.py`（**有单测**：`mesh_grid/tri_grid/tests/`） |
| 加一个新部件构建器 | `topo_modeler/builders/<部件>.py` + 在 `builders/__init__.py` 导出 |
| 改建模流水线顺序 | `topo_modeler/modeler.py` |
| 加一个器件模板 | `topo_templates/<器件>.py` |
| 加 S 参数处理 / 优化算法 | `tpc_toolkit/` |
| 让脚本 / AI 按任务提交建模与求解、查状态与产物（排错、恢复、取消、产物路径） | `tpc_service/`（读 [`packages/tpc_service.md`](./packages/tpc_service.md)） |
| 改文档 / 重新生成 API HTML | `docs/`、`scripts/gen_cst_solver_docs.py`、`scripts/gen_mesh_docs.py` |

---

## 8. 相关文档

- **使用**（写 notebook、排错、验收）→ [`../skills/user/tpc-usage.md`](../skills/user/tpc-usage.md)
- **开发**（改库本身）→ [`../skills/developer/WORKFLOW.md`](../skills/developer/WORKFLOW.md)
- **计划**（后续阶段要做什么）→ [`next_plan/README.md`](./next_plan/README.md)
- **支持矩阵**（已验证的 CST/Python 组合与能力边界）→ [`SUPPORT_MATRIX.md`](./SUPPORT_MATRIX.md)
- **API 速查**（自动生成）→ [`guides/api/`](./guides/api/)
