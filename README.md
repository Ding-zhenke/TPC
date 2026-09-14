# TPC —— 拓扑光子晶体 CST 自动化建模库

用 Python 驱动 **CST Studio Suite**，把拓扑光子晶体太赫兹器件的建模流程
（晶格路径 → 基板 → VPC 区域 → 光子晶体阵列 → 馈源 → 波导 → 端口 → 求解器）
从手工点鼠标变成**可参数化、可复现**的代码。

```
┌──────────────────────────────────────────────────────────────┐
│  templates/       直波导 / 单元天线 端到端一键建模                     │
├──────────────────────────────────────────────────────────────┤
│  topo_modeler/    TopoModeler（智能推断+流水线） + builders/ 部件构建器 │
├───────────────────────────────┬──────────────────────────────┤
│  cst_solver/     CST 会话封装    │  tpc_toolkit/  数据与优化（不依赖 CST） │
│  mesh_grid/      晶格/网格算法    │                              │
└───────────────────────────────┴──────────────────────────────┘
```

---

## 安装

```bash
# 在仓库根目录执行一次，之后在任何 Python 环境下都能直接 import
pip install -e .

# 需要 DXF 导出 / GRIN 透镜几何运算时
pip install -e ".[all]"
```

> **不再需要 `sys.path.append(r'D:\...\TPC')`。**
>
> 唯一例外：`cst` 模块由 CST Studio Suite 自带，无法从 PyPI 安装。
> `cst_solver` 导入时会自行读取配置并把 CST 的 `python_cst_libraries` 加入 `sys.path`，
> 所以你只需要复制一次配置文件：

```bash
copy cst_solver\config_template.py cst_solver\config.py
# 然后编辑 config.py 里的 CST_INSTALL_PATH
```

---

## 快速开始

```python
from cst_solver import setup, result          # CST 工程控制 + 结果读取
from mesh_grid.tri_grid import TopoPath       # 三角晶格路径 DSL
from topo_modeler import TopoModeler          # 建模引擎
from templates import StraightWaveguide       # 端到端模板

# ── 最简：用模板建一个直波导 ──
wg = StraightWaveguide(topology='AB', length=18,
                       lattice_constant=0.2425, height=0.25,
                       freq_range=(300, 380),
                       output_path=r'D:\out\wg.cst')
wg.preview()      # matplotlib 预览路径
wg.build_all()    # 参数 → 基板 → VPC → 晶体 → 馈源 → 波导 → 端口 → 求解器
wg.save()         # 保存 .cst

# ── 进阶：自定义路径 + 分步构建 ──
path = (TopoPath.builder(a=0.2425)
        .start(0, -1).move(19, 'c').turn(120).move(15, 'along').build())
modeler = TopoModeler(template_cst='tmp.cst')   # tmp.cst 需在当前工作目录
modeler.set_path(path)                          # 自动推断为 antenna + BA
modeler.build_all(freq_range=(300, 380))
modeler.save('antenna.cst')
```

---

## 包一览

| 包 | 职责 | 需要 CST | 详细说明 |
|---|---|---|---|
| [`cst_solver/`](./cst_solver) | CST VBA → Python 封装；23 个 Mixin 聚合成 `setup` 类 | ✅ | [docs/packages/cst_solver.md](./docs/packages/cst_solver.md) |
| [`mesh_grid/`](./mesh_grid) | 三角晶格 / 六边形晶格算法、可视化、DXF 导出、`TopoPath` 路径 DSL | ❌ | [docs/packages/mesh_grid.md](./docs/packages/mesh_grid.md) |
| [`topo_modeler/`](./topo_modeler) | 建模引擎：`TopoModeler` + `builders/` 各部件构建器 | ✅ | [docs/packages/topo_modeler.md](./docs/packages/topo_modeler.md) |
| [`templates/`](./templates) | 端到端器件模板 | ✅ | [docs/packages/templates.md](./docs/packages/templates.md) |
| [`tpc_toolkit/`](./tpc_toolkit) | S 参数解析、遗传算法算子、等效介质公式 | ❌ | [docs/packages/tpc_toolkit.md](./docs/packages/tpc_toolkit.md) |

整体架构与依赖关系 → [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)

---

## 先读哪个？

### 我是使用者（写 notebook 建模型）

| 目的 | 读哪份 |
|---|---|
| **主手册**：按需查阅地图、报错定位表、三条硬约定、已知库缺陷、验收清单 | [`skills/user/tpc-usage.md`](./skills/user/tpc-usage.md) |
| 三角晶格 / 路径 DSL | [`skills/user/tri-grid.md`](./skills/user/tri-grid.md) |
| 六边形晶格 / DXF | [`skills/user/hex-grid.md`](./skills/user/hex-grid.md) |
| 建模引擎三种用法（模板 / Modeler / Builder） | [`skills/user/topo-modeler.md`](./skills/user/topo-modeler.md) |
| 建模引擎阶段 0–3 详细指南 | [`docs/guides/topo_modeler_guide_stage0-3.md`](./docs/guides/topo_modeler_guide_stage0-3.md) |

### 我是开发者（改库本身）

| 目的 | 读哪份 |
|---|---|
| ⭐ **开发宪法**：改动归属、工作流、验收清单、文档同步矩阵、提交规范 | [`skills/developer/WORKFLOW.md`](./skills/developer/WORKFLOW.md) |
| 维护 / 扩展 `cst_solver`（含待修清单） | [`skills/developer/cst-solver-dev.md`](./skills/developer/cst-solver-dev.md) |
| 项目约定与 cst_solver 结构 | [`skills/developer/conventions.md`](./skills/developer/conventions.md) |
| 重新生成 API 文档 | [`skills/developer/doc-generation.md`](./skills/developer/doc-generation.md) |
| 后面要做什么、做到哪了 | [`docs/next_plan/README.md`](./docs/next_plan/README.md) |

> **AI 助手注意**：不要通读整包源码。先按上表读对应的技能文档，再按需定位到具体文件。

---

## 目录结构

```
TPC/
├── README.md                  项目入口
├── pyproject.toml             打包配置（pip install -e .）
│
├── cst_solver/                包 1：CST 会话封装
├── mesh_grid/                 包 2：晶格算法
├── topo_modeler/              包 3：建模引擎
├── templates/                 包 4：端到端模板
├── tpc_toolkit/               包 5：独立工具
│
├── docs/                      文档：架构 / 单包说明 / 指南 / 计划
├── skills/                    技能：使用者视角 + 开发者视角
├── scripts/                   仓库工具（文档生成、API 统计）
├── tests/                     跨包测试
├── examples/                  示例 notebook
├── assets/sat/                参考几何文件（.sat）
└── archive/                   归档：兼容 shim、一次性脚本、MATLAB 旧代码
```

---

## 环境要求

- **Python** ≥ 3.9（开发环境为 Anaconda Python 3.11）
- **CST Studio Suite**（仅使用 `cst_solver` / `topo_modeler` / `templates` 时需要，仅 Windows）
- `numpy` / `matplotlib` / `tqdm` 为必需依赖；`shapely` / `ezdxf` / `scipy` 为可选依赖

---

## 许可

见 [LICENSE](./LICENSE)。
