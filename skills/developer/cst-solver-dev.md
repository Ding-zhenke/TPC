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

`cst_solver/` 用 **Mixin 多继承**把 23 个模块聚合为 `setup` 主类（24 个 Mixin / 223 个公开方法），
VBA 命令通过 `self.cst_file.model3d.add_to_history("<日志名>", f1)` 下发。

| 模块 | 类 | VBA 主题 |
|---|---|---|
| `project.py` | `ProjectMixin` | 开/关/另存/激活工程（含 T10/T15 守卫接线） |
| `units.py` | `UnitsMixin` | 单位 |
| `parameters.py` | `ParametersMixin` | 参数、表达式、频率范围（含 T2/T7'/T13 守卫接线） |
| `validation.py` | `ValidationMixin` | 结构化验收：`get_messages()` + `validate_model()` |
| `_guards.py` | （非 Mixin） | 运行时守卫层：`GuardState`/`GuardFinding`/`CstGuardError` |
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
| `simulation/solver.py` | `SolverMixin` | T/FD/Eigenmode/IE/Asymptotic、参数扫描、优化器（含 T2 守卫接线） |
| `mesh/mesh.py` | `MeshMixin` | 网格属性/自适应/区域 |
| `import_export/io.py` | `IOMixin` | SAT/DXF/STEP/IGES/STL |
| `postprocessing/proc.py` | `PostProcMixin` | Q 因子/SAR/结果组合 |
| `postprocessing/farfield.py` | `FarfieldMixin` | 远场（含 T8 守卫接线） |
| `postprocessing/plot.py` | `PlotMixin` | 1D/2D/3D 绘图控制（含 T8 守卫接线） |
| `postprocessing/result_export.py` | `ExportMixin` | ASCII 导出（含 T3 守卫接线） |
| `_result_core.py` | `Result` | 仿真结果读取（独立于 `setup`），含批量读取与 CSV 导出 |
| `config.py` | — | `CST_INSTALL_PATH`（gitignored，逐机配置）；可加 `CST_GUARD_MODE` |
| `setup.pyi` | — | 类型存根，**改 API 必须同步**（Pylance 补全靠它） |
| `tests/test_guards.py` | — | 守卫层与结构化验收单测（假 CST 对象，43 条） |

> ⚠️ **两类 `log_flag` 含义不同，不要互相类推**：几何类方法（`polyline`/`extrude`/`translate`…）
> 默认 `log_flag=1`，`0` = 只返回 VBA 文本不下发；`para()`/`paras()` 默认 `log_flag=0`，
> `0` = **写入参数表但不重建历史**（参数存了、几何没变 → 陷阱 T2）。详见
> [`../../docs/packages/cst_solver.md`](../../docs/packages/cst_solver.md) §7.0–7.1。

## 权威参考资料（本地，离线可查）

本仓库 `docs/references/` 下**已就地 vendored** 4 份第三方官方 API 整理
（MIT，来源与许可原文见 [`../../docs/references/THIRD_PARTY_NOTICES.md`](../../docs/references/THIRD_PARTY_NOTICES.md)）：

| 文件 | 用来干什么 |
|---|---|
| `vba-official-reference.md` | **查 VBA 对象/属性/方法的确切拼写** —— 加封装前先在这里搜一遍对象名 |
| `cst-official-api-reference.md` | 查 `cst.interface` / `cst.results` 的 Python 侧 API（`DesignEnvironment`、`ProjectFile`、`ResultItem`…） |
| `tool-development-guide.md` | 新增 VBA 对象封装的方法论（如何组织一个"工具"） |
| `Test_kit_README.md` | 测试体系设计（分层、合约测试、缓存机制） |

**先查这里，再翻 CST 安装目录的 Online Help**（帮助仍在
`{CST_INSTALL_PATH}\Online Help\mergedProjects\VBA_3D\`，两者互为补充：
本地这几份是第三方整理、覆盖面窄但可全文检索；CST 帮助是唯一权威）。

⚠️ 已知与上游文档不符：采纳计划提到的 `devkit/tools/vba_defs/`（10 个 TOML 参考实现）
在该仓库 HEAD 上**不存在**（`git ls-files` 零命中）—— 是上游文档领先于代码，不是 clone 不全。

## 并发与资源生命周期（阶段 5.7.2）

阶段 7 的 `BatchModeler`（批量建模/扫描）要在**同一台机器**上串起多次 CST 会话，
因此必须先把「CST 到底允许多少并发」这件事写清楚。下面按**证据强度**分三档，
不要把它们混为一谈。

**① 本项目实测过的事实**（可以依赖）

| 事实 | 证据 |
|---|---|
| `cst.interface.DesignEnvironment()` 会**新起一个 CST 进程**（即新建一个 DE），而不是复用已有的 | 阶段 4 全程用 `running_design_environments()` 记录基线，每次 `setup(...)` 都新增一项 |
| **同一个工程不能同时被两个 DE 打开** —— 第二个会报 `Project is already open in another instance of CST Studio Suite` | 阶段 4 遇到并记录了这条错误 |
| `cst.results.ProjectFile(path)` **离线**读结果，**不需要** DE、不占求解器许可 | 阶段 4 T6 的 `scripts/compare_s_parameters.py` 就是这么读 S 参数的 |
| 时域求解**一次算完整个频段**，监视器频点数不影响耗时 | 阶段 4 §4.4 第 9 条 |
| 一次时域求解的成本量级：**约 5300 s CPU、峰值约 2.4 GB 内存**（关网格自适应 + 稳态 −20 dB 的省时配置） | 阶段 4 §4.5 成本记录 |
| 关网格自适应能显著省时间；`set_steady_state_limit(-20)` 比默认 `-30` 快 | 同上 |

**② 观察到一次、但未重复验证**（用之前要自己再测）

- **`app.run()`（`model3d.run_solver()`）看起来是阻塞的** —— 阶段 4 T6 里它在求解完成后
  才返回，脚本没有写任何等待循环就直接 `save()` + 关工程，随后离线读到了 S 参数。
  但这只观察过一次，CST 官方并未承诺同步语义；**写批量脚本时不要假设它一定阻塞**，
  至少要有「结果读不出来就重试/报错」的兜底。

**③ 未验证（阶段 7 前必须实测）**

- ❌ 同时开 **N 个 DE** 的许可上限（CST 许可可能是单机单实例、也可能是浮动 token 池）；
- ❌ 同时提交 **N 个求解任务**是否排队、报错、还是共用线程数；
- ❌ `Solver` 的 `MaximumNumberOfThreads` 与多 DE 叠加后的实际 CPU 占满情况；
- ❌ 关掉 DE 之后 CST 的 `remotesolverdispatcherservice` 之类后台进程是否残留
  （阶段 4 观察到**会残留一个**，非 GUI、不影响后续操作，但没有系统验证过）。

**④ 因此本库的并发纪律（现在就这么办）**

1. **一个进程同时只持有一个 `setup` 实例**（即一个 DE）。要批量跑就在循环里
   `setup(...) → 干活 → save() → close()`，一次一个 —— 这也是 `templates/*` 和
   `TopoModeler` 都补了 `close()` 与 `with` 支持的原因（阶段 5.7.1）。
2. **`close()` 之前一定 `save()`**：反之什么都不会写出（守卫层陷阱 T15 会直接拦）。
3. **用完就关**，别把 DE 留着等下一次 —— 阶段 4 反复强调过「不要开几十个工程窗口留着」。
4. **读结果一律走 `Result`（离线）**，不要为了读 S 参数再开一个 DE。
5. 批量脚本必须有**兜底清理**：进循环前记下 `running_design_environments()` 基线，
   结束时只关「不在基线里」的那些（`scripts/compare_s_parameters.py` 的 `close_extra()`
   是现成写法，照抄即可 —— 绝不能去关用户自己开着的会话）。

## 新增一个 VBA 封装的步骤

1. **查 VBA 命令与参数**：
   - 先搜本仓库 vendored 的 [`../../docs/references/vba-official-reference.md`](../../docs/references/vba-official-reference.md)（快、可全文检索）；
   - 再核对 CST 帮助 `C:\SOFTWARE\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D\`（唯一权威）。
2. **选 Mixin 文件**（按上表主题归类）
3. **写方法**：
   - `snake_case` 命名 + **保留旧 VBA 名作为别名**（旧名可能带驼峰，如 `create_brick` ↔ `square`）
   - 完整 docstring：`参数 / 返回值 / 说明`，参数类型写 `float/str`（CST 表达式是字符串）
   - 几何类方法需要写历史时用 `log_flag=1` 开关（`log_flag=0` 只返回 VBA 文本，方便把多条命令拼成**一次**历史）
   - 若新方法属于守卫层覆盖的陷阱（改参不重建 / save-close 顺序 / 远场模式 / 路径后缀），
     在方法里调用 `get_guard_state(self).check_*()`，并补一条 `cst_solver/tests/test_guards.py` 用例
4. **同步 `setup.pyi` 存根**（加签名）
5. **重新生成文档**：`python scripts/gen_cst_solver_docs.py`
   （新增 Mixin 时还要把类加进生成器的 `CATEGORIES` 与 `modules` 列表，否则它不出现在 API 页里）
6. **跑单测**：`python -m pytest cst_solver/tests/test_guards.py -q`
7. **冒烟测试**（见下）

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
