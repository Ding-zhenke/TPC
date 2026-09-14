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

```
┌──────────────────────────────────────────────────────────────┐
│  第 4 层  应用层     templates/        直波导 / 单元天线 端到端一键建模   │
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
templates ──▶ topo_modeler ──┬──▶ cst_solver ──▶ cst (CST 自带)
                             └──▶ mesh_grid.tri_grid
tpc_toolkit ──▶ mesh_grid（仅可视化/坐标，可选）        ← 独立，不需要 CST
```

---

## 3. 五个包的分工

| 包 | 一句话职责 | 是否需要 CST | 主要入口 | 详细文档 |
|---|---|---|---|---|
| **`cst_solver/`** | 把 CST 的 VBA 宏 API 封装成 Pythonic 的 `setup` 对象 | ✅ 必须 | `setup`, `result` | [packages/cst_solver.md](./packages/cst_solver.md) |
| **`mesh_grid/`** | 纯数学：六边形/三角形晶格的生成、坐标换算、可视化、DXF 导出 | ❌ 不需要 | `HexLib`, `TopoPath` | [packages/mesh_grid.md](./packages/mesh_grid.md) |
| **`topo_modeler/`** | 建模引擎：把「路径 + 参数」变成完整 CST 模型 | ✅ 必须 | `TopoModeler`, `builders.*` | [packages/topo_modeler.md](./packages/topo_modeler.md) |
| **`templates/`** | 端到端模板：一个类 = 一个器件，填参数就出模型 | ✅ 必须 | `StraightWaveguide`, `UnitAntenna` | [packages/templates.md](./packages/templates.md) |
| **`tpc_toolkit/`** | 独立工具：S 参数解析、遗传算法算子、等效介质公式 | ❌ 不需要 | 各子模块函数 | [packages/tpc_toolkit.md](./packages/tpc_toolkit.md) |

### 3.1 `cst_solver/` —— CST 会话封装层

**它是什么**：CST Studio Suite 的 VBA 接口是「拼一段宏字符串再下发到历史树」。
本包把这套宏 API 收敛成 **23 个 Mixin 类**，再用多继承聚合成一个 `setup` 类，
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

### 3.4 `templates/` —— 端到端应用层

**它是什么**：每个类对应一个具体器件，内部组装 `TopoModeler` + 参数定义 + 端口 + 求解器。

| 类 | 器件 | 说明 |
|---|---|---|
| `StraightWaveguide` | 拓扑光子晶体直波导 | 2 端口，默认 AB 型、单馈源镜像到两端 |
| `UnitAntenna` | 单元天线 | 1 端口，支持任意 60° 倍数拐弯 + 圆柱辐射体 |

**它解决什么**：同一类器件反复建模时的最高层复用。

> ⚠ **命名风险**：顶层包名 `templates` 过于通用，安装到 site-packages 后有与第三方包重名的风险。
> 计划在后续版本改名为 `topo_templates`（详见 [`next_plan/`](./next_plan/)）。

### 3.5 `tpc_toolkit/` —— 独立工具层（不依赖 CST）

**它是什么**：与仿真软件无关的通用工具，可在任意 Python 环境导入。

| 模块 | 内容 |
|---|---|
| `s2p.py` | CST 导出的 s2p 分组文本解析（`read_s2p_groups`）、按频率/阈值筛选参数组 |
| `ga_optimizer.py` | 遗传算法算子（种群初始化/选择/交叉/变异）、种群落盘、拓扑结构可视化、S 参数适应度 |
| `effective_medium.py` | 六边形面积、等效介电常数（体积加权 / 含空气孔）、介电常数 → 折射率 |

**它解决什么**：仿真前后的数据处理与优化循环，不该被 CST 依赖绑架。

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
├── templates/                 ← 包 4：端到端模板
├── tpc_toolkit/               ← 包 5：独立工具
│
├── docs/                      ← 文档（本目录）
│   ├── README.md              文档索引
│   ├── ARCHITECTURE.md        总体架构（本文件）
│   ├── packages/              每个包一份说明
│   ├── guides/                使用指南 + 自动生成的 API HTML
│   └── next_plan/             改善计划（含阶段实施计划与 TODO）
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
from templates import StraightWaveguide
```

> `cst` 模块由 CST Studio Suite 自带，**不能**从 PyPI 安装；
> `cst_solver` 在导入时会自行读取 `cst_solver/config.py` 并把 CST 的
> `python_cst_libraries` 加入 `sys.path`。详见 [`packages/cst_solver.md`](./packages/cst_solver.md)。

---

## 6. 核心硬约定（跨包通用，踩过的坑）

1. **z 平面**：所有多边形给 **CCW 绕向**（有向面积 > 0）+ 内部 `translate -h/2`。
   `ExtrudeCurve` 沿**多边形法向**拉伸，法向由顶点绕向决定：
   **CCW → +z，CW → −z**。绕向错了，实体之间会在 z 上差一个 `h`，
   布尔求交得到**空集且不报错**。
2. **布尔语义**：`Intersect "A","B"` → 结果留 **A**，B 被消耗；
   `Add/Subtract "A","B"` → 结果在 A，**B 被删除**；`Insert` 保留 B 供继续引用。
3. **阵列范围**：光子晶体阵列的 `xup / yup / ydn` 必须覆盖**整个基板**，不能只按路径推断。
4. **错误不可见**：库**不保证**把 CST 报错抛成 Python 异常，
   验收必须读 `app.cst_file.get_messages()`（读后即清空）。
5. **相对路径**按**当前工作目录**解析，模板 `tmp.cst` 必须放在 notebook 同目录。
6. `cst_file.modeler` 已废弃 → 用 `cst_file.model3d`。

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
| 加一个器件模板 | `templates/<器件>.py` |
| 加 S 参数处理 / 优化算法 | `tpc_toolkit/` |
| 改文档 / 重新生成 API HTML | `docs/`、`scripts/gen_cst_solver_docs.py`、`scripts/gen_mesh_docs.py` |

---

## 8. 相关文档

- **使用**（写 notebook、排错、验收）→ [`../skills/user/tpc-usage.md`](../skills/user/tpc-usage.md)
- **开发**（改库本身）→ [`../skills/developer/WORKFLOW.md`](../skills/developer/WORKFLOW.md)
- **计划**（后续阶段要做什么）→ [`next_plan/README.md`](./next_plan/README.md)
- **API 速查**（自动生成）→ [`guides/api/`](./guides/api/)
