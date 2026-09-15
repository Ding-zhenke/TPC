---
name: cst-solver-dev
description: '**维护 / 扩展 cst_solver 库** —— 为 CST Studio Suite 的 VBA API 增加 Python 封装、修封装层缺陷、统一 Mixin/命名/docstring 规范、重新生成 API 文档。USE FOR: 新增 app.xxx() 方法；修 cst_solver/ 内部 bug；核对 VBA 命令与 CST 帮助；更新 setup.pyi 存根与 docs。DO NOT USE FOR: 用 TPC 库建电磁模型 —— 那属于使用视角，读 ../../SKILL.md。'
argument-hint: 描述要新增/修复的 CST VBA 功能（如「增加 EigenmodeSolver 的 … 封装」）
---

# cst_solver 库开发与维护

## 何时使用

- 给 `cst_solver` **新增** CST VBA 的 Python 封装
- **修** `cst_solver/` 内部缺陷（含下表「待修清单」）
- 统一命名 / docstring / 存根 / 文档

> 用 TPC 库**做设计（建模、跑仿真、读结果）** → 读使用视角手册：`../../SKILL.md`。
> 栅格算法细节 → `../../mesh_grid/tri_grid/SKILL.md`、`../../mesh_grid/hex_grid/SKILL.md`。

## 架构速览

`cst_solver/` 用 **Mixin 多继承**把 21 个模块聚合为 `setup` 主类（150+ 方法），
VBA 命令通过 `self.cst_file.model3d.add_to_history("<日志名>", f1)` 下发。

| 模块 | 类 | VBA 主题 |
|---|---|---|
| `project.py` | `ProjectMixin` | 开/关/另存/激活工程 |
| `units.py` | `UnitsMixin` | 单位 |
| `parameters.py` | `ParametersMixin` | 参数、表达式、频率范围 |
| `modeling/primitives.py` | `ModelingPrimitivesMixin` | Brick/Cylinder/Sphere/Cone/Torus/ECylinder/triangle/hexagon/Wire |
| `modeling/curves.py` | `CurvesMixin` | Polygon/Arc/Circle/Ellipse/Line/Spline/Rectangle/Polygon3D |
| `modeling/curves_ops.py` | `CurveOpsMixin` | ExtrudeCurve/Loft/Sweep/Blend/Chamfer/Cover/Trim |
| `modeling/booleans.py` | `SolidOpsMixin` | Add/Subtract/Insert/Intersect/Imprint/Blend |
| `modeling/transforms.py` | `TransformMixin` | Translate/Rotate/Mirror/Scale |
| `modeling/picks.py` | `PickMixin` | Pick edge/face/vertex/endpoint、按坐标拾取、按坐标反查编号 |
| `modeling/wcs.py` | `WCSMixin` | 工作坐标系 |
| `material/materials.py` | `MaterialMixin` | 材料、组件、重命名 |
| `simulation/ports.py` | `PortMixin` | Port（含 Free 坐标范围）/DiscretePort/Floquet/Cable |
| `simulation/sources.py` | `SourceMixin` | PlaneWave/Coil/Current/Field/Farfield 源、时域信号 |
| `simulation/monitors.py` | `MonitorMixin` | Monitor/Probe/2D 监视器 |
| `simulation/boundary.py` | `BoundaryMixin` | Boundary/Background/LayerStacking |
| `simulation/solver.py` | `SolverMixin` | T/FD/Eigenmode/IE/Asymptotic、参数扫描、优化器 |
| `mesh/mesh.py` | `MeshMixin` | 网格属性/自适应/区域 |
| `import_export/io.py` | `IOMixin` | SAT/DXF/STEP/IGES/STL |
| `postprocessing/proc.py` | `PostProcMixin` | Q 因子/SAR/结果组合 |
| `postprocessing/farfield.py` | `FarfieldMixin` | 远场 |
| `postprocessing/plot.py` | `PlotMixin` | 1D/2D/3D 绘图控制 |
| `postprocessing/result_export.py` | `ExportMixin` | ASCII 导出 |
| `_result_core.py` | `Result` | 仿真结果读取（独立于 `setup`） |
| `config.py` | — | `CST_INSTALL_PATH`（gitignored，逐机配置） |
| `setup.pyi` | — | 类型存根，**改 API 必须同步**（Pylance 补全靠它） |

## 新增一个 VBA 封装的步骤

1. **查 VBA 命令与参数**：CST 帮助 `C:\SOFTWARE\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D\`
2. **选 Mixin 文件**（按上表主题归类）
3. **写方法**：
   - `snake_case` 命名 + **保留旧 VBA 名作为别名**（旧名可能带驼峰，如 `create_brick` ↔ `square`）
   - 完整 docstring：`参数 / 返回值 / 说明`，参数类型写 `float/str`（CST 表达式是字符串）
   - 需要写历史时用 `log_flag=1` 开关（`log_flag=0` 只返回 VBA 文本，方便把多条命令拼成**一次**历史）
4. **同步 `setup.pyi` 存根**（加签名）
5. **重新生成文档**：`python scripts/gen_cst_solver_docs.py`
6. **冒烟测试**（见下）

## 硬约定（都是踩过的坑）

- **`add_to_history` 是唯一执行通道**；`log_flag=0` 时**只拼字符串不下发** —— 这是 `triangle()` 等复合命令把「画线+拉伸+旋转+平移」合成一条历史的手法
- 库**不保证**把 CST 报错抛成 Python 异常 → 验收必须读 `app.cst_file.get_messages()`（读后即清空）
- `ExtrudeCurve` 沿多边形**法向**拉伸，法向由顶点**绕向**决定：**CCW(有向面积>0) → +z，CW → −z**。
  库内统一「多边形给 CCW + `translate -h/2`」；否则实体间在 z 上差一个 `h`，布尔相交得空集（且不报错）
- 布尔语义：`Intersect "A","B"` → 结果留 **A**、B 被消耗；`Add/Subtract "A","B"` → 结果在 A、**B 被删除**；`Insert` 则保留 B 供继续引用
- 相对路径按**当前工作目录**解析（模板 `tmp.cst` 必须放 notebook 同目录）
- `cst_file.modeler` 已废弃 → 用 `cst_file.model3d`
- `param` 类改动后需 `log_flag=1`（内部 `full_history_rebuild()`）才生效
- **面/棱边编号不可移植**：`pick_face` / `pick_edge` 的编号（`'10'`、`'22'` …）是 CST 内部编号，与实体几何、生成顺序强相关，扭转/布尔/阵列之后会变
  - 绕开编号：按**坐标**拾取 → `pick_face_at()` / `pick_edge_at()` / `pick_point_at()`
  - 需要编号：由坐标**反查** → `get_face_id_from_point()` / `get_edge_id_from_point()`
  - 校验拾取是否真生效：`get_picked_count('face')`，别只看有没有报错
  - **不依赖拾取**：轴对齐矩形端口面用 `create_waveguide_port_free()` 给 `Xrange/Yrange/Zrange`（`Coordinates "Free"`）
  - CST **没有**面法向/面中心/面面积的查询 API（`Solid.GetArea` 返回的是**实体**表面积），
    所以"按法向自动找面"只能由参数化几何**正算出一个点**再反查，不能遍历已有面匹配法向量

## 待修清单

**当前为空。** 此前 5 行已全部修掉（对照 [`../../docs/next_plan/00_旧版README_整理与历史记录.md`](../../docs/next_plan/00_旧版README_整理与历史记录.md) §5 第 1–5 号），按 [`../../skills/developer/WORKFLOW.md`](./WORKFLOW.md) §6 的「修掉一个已知缺陷 → 删掉对应行」规则清空：

| 原问题 | 现状 |
|---|---|
| `builders/vpc_region.py` 顶点顺时针 → 与晶体差一个 h | ✅ 已修（两条边界链改为「每个路径点都参与」的确定绕向，全部保证 CCW，并有第 16 项单测用有向面积钉住） |
| `builders/substrate.py` 带状多边形为 CW | ✅ 已修（同上，未改 `topo_path.build_substrate_polygon`） |
| `builders/crystal.py` 阵列范围只能按路径推断 | ✅ 已修（加可选形参 `xup=None, yup=None, ydn=None`） |
| `templates/straight_waveguide.py` 传了不被接受的实参 → TypeError | ✅ 已修 |
| `templates/unit_antenna.py` 同 `topology=` 问题 | ✅ 已修 |

> **注意**：`unit_antenna.py` 仍有一处**已知但未验证**的隐患 ——
> 它用 `path.get_array_range()` 推导阵列范围，与 `StraightWaveguide` 同源
> （后者已修为「覆盖整个基板」）。详见
> [`../../docs/next_plan/stages/04_阶段4_验收与缺陷清账.md`](../../docs/next_plan/stages/04_阶段4_验收与缺陷清账.md) 的 T5。
> 单元天线是含拐弯的路径，需先确定参考基准再改，**不要照搬直波导的取法**。

## 冒烟测试（最小验证，不污染正式工程）

```python
import sys; sys.path.insert(0, r'D:\成电博士生涯\自动建模算法尝试\TPC')
from cst_solver import setup

app = setup(r'<某个 tmp.cst 的绝对路径>')      # 用临时模板，别用正式工程
app.square(0, 1, 0, 1, 0, 1, 'smoke', 'component1', 'Silicon (lossy)')
print(app.cst_file.get_messages())              # 应为空
app.cst_file.model3d.Rebuild()                  # 阻塞式重放历史，最能暴露问题
print(app.cst_file.get_messages())
app.close()
```

## 进阶

- 想自动加载本 skill：它已在 `TPC/.github/skills/cst-solver-dev/`，把 TPC 作为工作区打开即生效（也可 `/cst-solver-dev` 调用）
- 需要栅格/DXF/六边形透镜能力 → 见 `mesh_grid/` 两套子包及各自 SKILL.md
