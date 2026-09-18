# cst_solver —— CST 会话封装层

`cst_solver/` 是 TPC 的**最底层包**：CST Studio Suite 的自动化接口本质上是「拼一段 VBA 宏字符串 → 下发到工程的历史树」，本包把这套宏 API 收敛成 **24 个 Mixin 类**，再用多继承聚合成**一个** `setup` 类，于是 200 多个 CST 原语操作（画体、布尔、端口、边界、求解器、网格、导出）都能通过同一个 Python 对象调用；此外还独立提供一个 `result` 类，用于只读地读取**已算完**工程的导航树结果，以及一个**运行时守卫层**（`_guards.py`），把「读文档才知道」的约束变成「写错就提示」。它与 `mesh_grid` 互相不依赖，是 `topo_modeler` / `topo_templates` 的下层依赖。

| 项 | 内容 |
|---|---|
| **职责** | 把 CST 的 VBA 宏 API 封装成 Pythonic 的 `setup` 对象；另提供只读的 `result` 结果读取器与运行时守卫层 |
| **需要 CST** | 实际建模/求解/读取工程需要；导入、环境诊断和假后端测试不需要 |
| **入口** | `from cst_solver import setup, result`（`setup` = 聚合类，`result` = 结果读取类） |
| **依赖** | 第三方 `numpy`（`_result_core.py` 用到）；`cst` 由 CST 自带、无法从 PyPI 安装，故不列入 `pyproject.toml`；不依赖任何其它 TPC 包 |
| **被谁依赖** | `topo_modeler/`（如 `topo_modeler/modeler.py`、`topo_modeler/lens_build_standalone.py`）、`topo_templates/`；`tpc_toolkit/` **不**依赖它 |
| **源码位置** | `cst_solver/`：23 个 Mixin 模块 + `__init__.py`（内联 `FaceOpsMixin` 与 `setup`）+ `_result_core.py`（`Result`）+ `_guards.py`（守卫层）+ `config_template.py` / `_path_tools.py`，类型存根 `setup.pyi`、`simulation/setup.pyi`；P1 再加三个离线模块 `expressions.py` / `failures.py` / `run_contract.py`（见 §8） |

> AST 统计（不含已归档的死代码 `archive/legacy/_result_dead_duplicate.py`，原 `cst_solver/_result.py`）：`cst_solver/` 共 **24 个 Mixin 类**，
> Mixin 类上公开方法 **223** 个；另有 `Result` 13 个、`setup` 自身 1 个（`open`）、
> 守卫层模块级函数 6 个。
> 复核命令：`python scripts/_api_stats.py`（注意它把守卫层的 `GuardState` 也算进"类上公开方法"，
> 因此它给出的总数比上面这个口径大）。

---

## 1. 它解决什么问题

**问题**：CST 的 Python 接口（`cst.interface`）不提供「画长方体」这类高层函数，只提供 `add_to_history(日志名, VBA字符串)`。想建一个长方体，用户得自己拼这样一段宏：

```python
# 直接用 CST 原生接口 —— 每个模型都在重复这种字符串
app.cst_file.model3d.add_to_history("Square: substrate", f"""
With Brick
    .Reset
    .Name "substrate"
    .Component "component1"
    .Material "Quartz (Fused) (lossy)"
    .Xrange "{xmin}", "{xmax}"
    .Yrange "{ymin}", "{ymax}"
    .Zrange "{zmin}", "{zmax}"
    .Create
End With
""")
```

**封装层买到的东西**：

1. **不用记 VBA 语法**：`app.create_brick(xmin, xmax, ymin, ymax, zmin, zmax, "substrate", material="...")` 一行等价于上面 12 行。
2. **不用手拼字符串**：所有 `.Reset` / `.Name` / `.Create` / `End With` 由库生成，参数化表达式（CST 里长度/角度其实是**表达式字符串**，如 `"a/2"`、`"h/2"`）直接透传。
3. **统一环境入口**：由 `environment.py` 解析用户配置、环境变量与自动发现；只有执行入口才加载 CST。
4. **复合构件可以合成一条历史**：`log_flag=0` 时几何类方法**只返回 VBA 文本、不下发**，于是「画多边形 → 拉伸 → 旋转 → 平移」能拼成**一条**历史项（`triangle()` / `hexagon()` 就是这么实现的）。
   ⚠️ **`log_flag` 在不同方法里含义不同**（详见 §7.0）：几何类方法（`polyline` / `arc` / `extrude` / `rotation` / `translate` …）的 `log_flag=0` 表示「只返回文本不下发」，默认值是 **1**；而 `para()` / `paras()` 的 `log_flag=0` 表示「**写入参数表但不重建工程历史**」，默认值是 **0**。两者不能互相类推。
5. **同一对象上什么都能干**：建模、材料、端口、边界、求解器、网格、后处理全在 `setup` 上，不用在多个对象间传递 `cst_file`。

**它明确不保证的东西**：

- ❌ **不把 CST 报错转换成 Python 异常**。VBA 命令写错、实体不存在、布尔求交得到空集 —— CST 只在自己的消息区留一条消息，`add_to_history` 照样正常返回。唯一的例外是**打开工程**这一步：`setup(filename)` 在产品文件不存在时抛 `FileNotFoundError`、打开失败时抛 `RuntimeError`。因此**验收必须读 `app.cst_file.get_messages()`**（详见 §7.2）。
- ❌ 不校验参数量纲，不做几何合法性检查，不保证 VBA 命令与你的 CST 版本匹配。
- ❌ 不是 CST 的替代实现：没有 CST 可以导入、诊断与做离线测试，但不能实际建模、求解或读取 .cst 结果。

安装发现与用户配置见 [环境指南](../guides/cst_environment.md)：环境变量/JSON/旧 config.py → 自动发现；普通导入不加载 CST，`setup()` / `Result()` 才加载。公开环境入口为 `discover_cst_installations()`、`get_cst_paths()`、`diagnose_environment(probe=False)`、`describe_interface_abi()`、`interpreter_abi_tag()`。

---

## 2. 架构：Mixin 多继承

**设计**：每个模块只定义一个 `XxxMixin` 类，类里只放**与一个 VBA 主题相关**的方法，全部通过 `self.cst_file` 下发命令 —— 它们不重写 `__init__`、不保存状态。`cst_solver/__init__.py` 末尾用多继承把这 24 个 Mixin 聚合为唯一的 `setup` 类。

```python
# cst_solver/__init__.py 末尾（原样）
class setup(
    ProjectMixin,
    UnitsMixin,
    ParametersMixin,
    ModelingPrimitivesMixin,
    CurvesMixin,
    CurveOpsMixin,
    WCSMixin,
    SolidOpsMixin,
    TransformMixin,
    PickMixin,
    FaceOpsMixin,
    MaterialMixin,
    PortMixin,
    SourceMixin,
    MonitorMixin,
    BoundaryMixin,
    SolverMixin,
    MeshMixin,
    IOMixin,
    PostProcMixin,
    FarfieldMixin,
    PlotMixin,
    ExportMixin,
    ValidationMixin,
):
```

**为什么一个 `setup` 对象就暴露了全部能力**：Python 的 MRO 会把所有基类的命名空间合并进 `setup`，所以 `getattr(app, "create_brick")`、`app.substract(...)`、`app.define_monitor(...)` 都落在同一个实例上，而它们各自只依赖 `self.cst_file` 这一个实例属性 —— 因此**组合出来的类不需要任何额外胶水代码**，加一个新 Mixin 只需在基类列表里追加一项。

`setup` 自身只定义 5 个东西（`__init__`、`_open_and_activate`、`open`、`__enter__`、`__exit__`），其余全是继承来的；`__init__` 里 `self.project = cst.interface.DesignEnvironment()`，随后 `self.cst_file = self.project.open_project(...)` 并 `activate()`。

**两个结构性注意点**：

- `FaceOpsMixin`（面拉伸 / 面旋转 / 走线）**内联定义在 `__init__.py` 里**（第 120-221 行），不在 `modeling/picks.py`。`picks.py` 第 86-89 行专门留了注释提醒：不要在那里再定义一份 `rotation_face` / `extrude_face`，否则会**按 MRO 遮蔽**原版实现。
- 基类列表的顺序就是 MRO 顺序；`picks.py` 的注释说明过遮蔽风险，因此**重名方法只允许存在一份**。

`cst_solver/setup.pyi` 用同名 `_XxxMixin` 存根类复刻了完全相同的继承列表，供 Pylance 补全。

---

## 3. 模块地图

公开方法数为 AST 实测值（不含 `_` 开头的方法）。**23 个 Mixin 各占一个模块文件，第 24 个 `FaceOpsMixin` 内联在 `__init__.py`**；`_result_core.py`（`Result`）与 `_guards.py`（守卫层，非 Mixin）不参与 `setup`。

> 本节数字由脚本复核：`python scripts/_api_stats.py`。若与源码不符，以 AST 实测为准并顺手更新本表
> （`cst-solver-dev.md` 的规程要求「改公开 API 必须同步本文件」）。

### 根目录

| 文件 | Mixin 类 | VBA 主题 | 公开方法数 |
|---|---|---|---|
| `project.py` | `ProjectMixin` | 工程 打开/关闭/另存/激活（`open_project`、`new_project`…）+ T10/T15 守卫接线 | 9 |
| `units.py` | `UnitsMixin` | `Units` 单位；单位查询（`GetLengthUnit` 等） | 2 |
| `parameters.py` | `ParametersMixin` | 参数 / 表达式参数 / `Solver.FrequencyRange` 频率范围 + T2/T7'/T13 守卫接线 | 11 |
| `validation.py` | `ValidationMixin` | **结构化验收**：`get_messages()` + `validate_model()`（读消息 + `Rebuild()`） | 2 |
| `__init__.py` | `FaceOpsMixin`（内联） | 面旋转、面拉伸、`TraceFromCurve` 走线 | 4 |
| `_result_core.py` | `Result`（**非 Mixin**，不参与 `setup`） | `cst.results.ProjectFile` 结果读取 + 批量读取 / CSV 导出 | 13 |

**根目录小计：Mixin 方法 28 个。**

### `modeling/`

| 文件 | Mixin 类 | VBA 主题 | 公开方法数 |
|---|---|---|---|
| `primitives.py` | `ModelingPrimitivesMixin` | `Brick` / `Cylinder` / `Sphere` / `Cone` / `Torus` / `ECylinder` / `Wire` + 三角形、六边形棱柱 | 13 |
| `curves.py` | `CurvesMixin` | `Polygon` / `Arc` / `Circle` / `Ellipse` / `Line` / `Spline` / `Rectangle` / `Polygon3D` | 11 |
| `curves_ops.py` | `CurveOpsMixin` | `ExtrudeCurve` / `Loft` / `SweepCurve` / `BlendCurve` / `ChamferCurve` / `CoverCurve` / `TrimCurves` | 8 |
| `booleans.py` | `SolidOpsMixin` | `Solid.Add` / `Subtract` / `Insert` / `Intersect` / `Imprint` / `BlendEdge` | 11 |
| `transforms.py` | `TransformMixin` | `Transform` 的 `Rotate` / `Translate` / `Mirror` / `Scale` | 6 |
| `picks.py` | `PickMixin` | 按编号/按坐标拾取面、棱、点（`PickFaceFromId` / `PickFaceFromPoint` / `GetFaceIdFromPoint` / `GetNumberOfPicked*`）+ `pick_face_auto` 稳健拾取（成功判定走私有 `_pick_succeeded()`，见 §7.9） | 13 |
| `wcs.py` | `WCSMixin` | `WCS.Reset` / `RotateWCS` / `MoveWCS` / `AlignWCSWithSelected` / `SetOrigin` / `Store` / `Restore` / `Scale` | 17 |

**`modeling/` 小计：79 个。**

### `material/`

| 文件 | Mixin 类 | VBA 主题 | 公开方法数 |
|---|---|---|---|
| `materials.py` | `MaterialMixin` | `Material` 预设/自定义材料、`.mtd` 材料库加载、`Component.New`、`Solid.Rename` / `ChangeComponent` / `ChangeMaterial`、`Material.ChangeColor` | 15 |

**`material/` 小计：15 个。**

### `simulation/`

| 文件 | Mixin 类 | VBA 主题 | 公开方法数 |
|---|---|---|---|
| `ports.py` | `PortMixin` | `Port` / `DiscreteFacePort` / `DiscretePort` / `LumpedFaceElement` / `FloquetPort` / `CablePort` | 10 |
| `sources.py` | `SourceMixin` | `PlaneWave` / `CurrentPort` / `Coil` / `VoltageWire` / `Charge` / `CurrentPath` / `Magnet` / `FieldSource` / `PredefinedField` / `FarfieldSource` / `TimeSignal` | 11 |
| `monitors.py` | `MonitorMixin` | `Monitor`（场/远场/2D 切面监视器）、`Probe` 探针 | 4 |
| `boundary.py` | `BoundaryMixin` | `Boundary` / `Background` / `LayerStacking` | 4 |
| `solver.py` | `SolverMixin` | `Solver`(T) / `FDSolver` / `EigenmodeSolver` / `IESolver` / `AsymptoticSolver` / `ParameterSweep` / `Optimizer` / `SolverParameter`、`run_solver()` / `full_history_rebuild()` + T2 守卫接线 | 27 |

**`simulation/` 小计：56 个。**

### `mesh/`

| 文件 | Mixin 类 | VBA 主题 | 公开方法数 |
|---|---|---|---|
| `mesh.py` | `MeshMixin` | `Mesh`（属性/自动网格）、`MeshAdaption3D` 自适应、`MeshSettings`、`MeshShapes` 加密区域 | 6 |

**`mesh/` 小计：6 个。**

### `import_export/`

| 文件 | Mixin 类 | VBA 主题 | 公开方法数 |
|---|---|---|---|
| `io.py` | `IOMixin` | `SAT` / `DXF` / `STEP` / `IGES` / `STL` 导入、`StartSubProject` 子工程导入、`ASCIIExport` 场数据与方向图导出 | 14 |

**`import_export/` 小计：14 个。**

### `postprocessing/`

| 文件 | Mixin 类 | VBA 主题 | 公开方法数 |
|---|---|---|---|
| `proc.py` | `PostProcMixin` | `QFactor` / `CombineResults` / `SAR` / `PostProcess1D` | 7 |
| `farfield.py` | `FarfieldMixin` | `FarfieldPlot`、`FarfieldArray` 阵列远场 | 3 |
| `plot.py` | `PlotMixin` | `Plot` / `Plot1D` / `Plot2D3D` / `ScalarPlot2D,3D` / `VectorPlot2D,3D` / `FarfieldPlot` 绘图控制 | 13 |
| `result_export.py` | `ExportMixin` | `ASCIIExport` 的 1D / 2D-3D 结果导出 | 2 |

**`postprocessing/` 小计：25 个。**

### 不是 Mixin 的文件

| 文件 | 内容 |
|---|---|
| `config_template.py` | 配置模板（`CST_INSTALL_PATH` 及两条推导路径，另可设 `CST_GUARD_MODE` 覆盖守卫模式） |
| `_path_tools.py` | `get_paths(cst_install_path)` —— 只做路径推导的纯函数 |
| `_result_core.py` | `Result` 类 + 旧名别名类 `result(Result)`，包顶层 `result` 由它导出 |
| `_guards.py` | **运行时守卫层**（纯标准库，不 import CST）：`GuardState` / `GuardFinding` / `CstGuardError` + 全局模式开关。见 §7.0 |
| `expressions.py` | **P1 新增**：CST 表达式 / 名称 / 路径 / VBA 文本的**离线**校验（纯标准库，不 import CST、不建 DE）。见 §8.1 |
| `failures.py` | **P1 新增**：结构化失败通道；`{code, message, details, retryable}` 四件套的唯一实现是 `structured_error()`。见 §8.2 |
| `run_contract.py` | **P1 新增**：求解运行契约（`RunContract` / `JsonlSink` / `result_conventions` / 结果指纹）。见 §8.3 |
| `setup.pyi` / `simulation/setup.pyi` | 类型存根（IDE 补全唯一依赖），改公开 API 必须同步；P1 修掉两处漂移，见 §8.7 |
| `tests/test_guards.py` | 守卫层与结构化验收的单测（**假 CST 对象**，43 条），`pytest cst_solver/tests/test_guards.py -v` |
| `tests/test_expressions.py` / `test_failures.py` / `test_run_contract.py` | **P1 新增**：三块离线能力的单测（99 + 19 + 20 条，全部用假 CST 对象与临时目录），`pytest cst_solver/tests/ -q` |
| ~~`_result.py`~~ | ✅ **已归档**（2026-09-17 核实）：它是 `_result_core.py` 的陈旧重复副本（307 行 vs 107 行、全仓零引用），现已移到 [`archive/legacy/_result_dead_duplicate.py`](../../archive/legacy/_result_dead_duplicate.py)，**不在本包里**（本行只作历史说明）。归档清单见 [`archive/legacy/README.md`](../../archive/legacy/README.md) |

---

## 4. 安装配置与环境诊断

配置优先级、环境变量、JSON 示例及旧 config.py 兼容方式见 [环境指南](../guides/cst_environment.md)。不再执行 config_template.py，也不静默吞掉配置错误。

| 入口 | 作用 |
|---|---|
| `discover_cst_installations(search_roots=None)` | 发现含 Python 库的 Windows 安装，按年份降序 |
| `get_cst_paths(install_path=None, ...)` | 解析安装/Python/材料路径，不加载 CST、不修改 sys.path |
| `diagnose_environment(probe=False)` | JSON 可序列化诊断；probe=True 仅尝试接口导入。**另含 `interface_abi` 段**（离线比对解释器 ABI 与 CST 提供的 `_cst_interface.cpNN*.pyd`） |
| `describe_interface_abi(install_path=None)` | **离线**报告接口 ABI 匹配情况：`interfaces`（安装里有 cp38…cp313 哪些）/`interpreter_abi`/`abi_match`/`note`。有同 ABI 的 .pyd **只说明「有可能导入」**，不等于「已验证组合」（实际导入还依赖 DLL 与许可） |
| `interpreter_abi_tag()` | 当前解释器的 ABI 标签（如 `cp311`；CST 扩展名用的就是这种写法） |
| `python -m cst_solver doctor --probe` | 输出 JSON；不可用/配置错误时退出码 1；不启动 DE |

`_path_tools.get_paths()` 仍保留为显式路径推导的兼容工具。实际配置解析统一使用 `get_cst_paths()`，材料加载也使用同一解析结果。

> **环境与会话生命周期已真机核实**（P4/V8，2026-09-17，13/13 通过，脚本 `scripts/verify_environment_lifecycle.py`）：
> 打开**不存在**的工程在**创建 DE 之前**就失败（不留空窗口）；打开**存在但无效**的文件抛 `RuntimeError`
> 且**自有 DE 被清掉、无残留**；只建 DE 再关能回到基线；**先关工程后 DE 仍存活**，再关 DE 才回到基线
> （两步语义分别成立）；`doctor --probe` 返回 `status=importable` 且**不创建 DE** ——
> `importable` 只说明**接口能加载**，**不代表**许可/仿真可用。逐条证据见
> [`../validation/p4_real_machine_evidence.md`](../validation/p4_real_machine_evidence.md) §1。

---

## 5. 结果读取（Result 类）

### 正确的导入路径

```python
from cst_solver import setup, result      # ✅ 推荐：result 是类
from cst_solver import Result             # ✅ 也可以（同名类，包顶层已绑定）
from cst_solver._result_core import Result  # ✅ 需要显式拿到类对象时
```

```python
from cst_solver.result import result      # ❌ 不存在的模块
```

**为什么**：`Result` 定义在 `cst_solver/_result_core.py`，包顶层用 `result = _result_class` 把**类**导出（`__init__.py:110-113`）。仓库里**没有** `cst_solver/result.py` 这个模块；如果新增一个，Python 的导入机制会让 `cst_solver.result` 指向那个**子模块**，从而遮蔽包属性 `cst_solver.result`，`from cst_solver import result` 拿到的就不再是类了。

> `cst_solver/__init__.py` 第 104-109 行的注释仍然建议 `from cst_solver.result import result`，那是历史遗留描述，**已失效**（`archive/compat/cst_solver_shim.py`、`archive/scripts/fix_cst_solver_20250914.py` 里的旧写法就属于这一类）。

### 构造

```python
Result(cst_file)   # :param cst_file: str, CST 工程文件路径（.cst）
```

内部做两件事：`self.app_result = cst.results.ProjectFile(cst_file, allow_interactive=True)`、`self.result_module = self.app_result.get_3d()`。之后的读取都委托给 `self.result_module`。类 `result(Result)` 只是 `pass`，是向后兼容的旧名。

> **结果树路径两种写法都接受**（2026-09-17 修掉的陷阱）：`read_1D()` 原先**无条件**加
> `1D Results\` 前缀，而 `get_tree_items()` 返回的是**完整**路径 —— 于是「查出路径 → 读回来」
> 会拼成 `1D Results\1D Results\…` 并报 `tree path not found`。现在完整路径原样用、
> 相对路径补前缀；两种都失败时，错误信息里会**列出试过的候选路径**并说明前缀规则。
>
> 同一个类里**三个方法共用同一套约定**（`read_1D` / `get_run_ids` / `get_result_item`）：
> `get_run_ids('S-Parameters\\S1,1')` 以前会报 `tree path not found`（只有 `read_1D` 支持相对写法），
> 现在也走 `_candidate_paths()`（先补 `1D Results\`，再依次试其它一级分类）。
>
> **`list_s_parameters()` 只列真 S 参数**（2026-09-17 修）：判定条件是「`S-Parameters`
> 目录的**直接子项**」+「名字符合 ``S<端口1>,<端口2>``」。旧实现只看路径里有没有
> `'S-Parameter'`，于是把收敛监控曲线
> `1D Results\Convergence\S-Parameters\Reflection S-Parameters [1]` 也列了出来、
> 还排在**第一个** —— `names[0]` 之类的调用会直接失败。
> **不变式**：本函数返回的每个名字都必须能被 `read_s_parameter()` 读出来。
>
> ⚠️ **已知读不出来的条目**（实测 CST 2026，`Leaky\ANT_LEAKY_EPC_GRID.cst`）：
> 63 个结果项里 18 个 `1D Results\farfield (f=…)` 在 `get_result_item()` 阶段即抛
> `UnicodeDecodeError`，同工程其它（含带括号的）条目正常；能用的远场派生数据是
> `Tables\1D Results\Realized Gain…` 一类汇总表。裸 `UnicodeDecodeError` 会被翻译成
> 可执行的话（`describe_result_item_failure()`）。逐项扫描：
> `python scripts/verify_result_item_coverage.py`；证据
> [P4 记录 §8.3](../validation/p4_real_machine_evidence.md)。

> **打开失败会给出可执行的原因**：`Result(path)` 打不开时抛 `RuntimeError`，消息由
> `describe_result_open_failure()` 生成并保留原始异常链 —— 例如
> 「工程文件不存在：<路径>（原始错误：UnicodeDecodeError: …）」。
> 之所以要翻译：CST 的读取器在「路径不存在 **且** 含非 ASCII 字符」时抛的是
> `UnicodeDecodeError`（看着像编码问题，其实是文件不存在）；工程正被 CST 打开时抛的是
> `UserWarning: Project is opened in CST Studio Suite`。**非 ASCII 路径本身可以正常读取**
> （实测中文路径下的已求解工程读出 31 个结果树条目，见
> [P4 记录 §8](../validation/p4_real_machine_evidence.md)）。回归：`cst_solver/tests/test_result_open.py`。

### 13 个公开方法

| 方法（签名） | 返回结构 |
|---|---|
| `get_tree_items(tree_filter=None)` | 直接返回 `self.result_module.get_tree_items(...)` —— 导航树中所有结果项（先看它，再决定读哪一项）。`tree_filter` 可传 `"0D/1D"` / `"colormap"` / `"farfields"` 等做过滤 |
| `get_available_results()` | 中文别名，等价于 `get_tree_items()` |
| `get_all_run_ids(max_mesh_passes_only: bool = True)` | `list[int]`；`True` 只列最终结果，`False` 连中间结果一起列 |
| `get_run_ids(treepath: str, skip_nonparametric: bool = False)` | `list[int]`；`skip_nonparametric=True` 时**排除 `run_id=0`** |
| `get_result_item(treepath: str, run_id=0, load_impedances: bool = True)` | `cst.results.ResultItem`；`load_impedances=False` 跳过自动加载参考阻抗 |
| `read_1D(tree_path, run_id: int = 0)` | `ndarray (n, 2)` = `[xdata, ydata]`（内部 `np.asarray([...]).T`）；`tree_path` **自动加前缀** `"1D Results\\"` |
| `read_2d(tree_path, run_id: int = 0)` | `dict`：`{'x','y','z','values'}`（`z` 在对象没有 `get_zdata` 时为 `None`）；前缀 `"2D Results\\"` |
| `read_s_parameter(s_param: str, run_id: int = 0)` | 便捷方法 = `read_1D(f"S-Parameters\\{s_param}", run_id)`，即 `ndarray (n, 2)` = `[频率, S 参数]` |
| `read_3d(tree_path, run_id: int = 0)` | `dict`：`{'x','y','z','values'}`；前缀 `"2D/3D Results\\"`；全部尝试失败时抛 `ValueError(f"无法读取 3D 结果: {tree_path}")` |
| `list_s_parameters(tree_filter='0D/1D')` | `list[str]`：工程里所有可读的 S 参数名，如 `['S1,1', 'S2,1']`（阶段 5.5 新增） |
| `read_all_s_parameters(run_id=0, names=None)` | `dict{名称: ndarray(n,2)}`：第 0 列是**float** 频率（已剥掉 CST 的复数外壳），第 1 列是复数 S 值。个别条目失败不抛异常，记入 `self.last_errors`（阶段 5.5 新增） |
| `export_s_parameters_csv(save_path, run_id=0, names=None, in_db=True, delimiter=',')` | `str`：写出的 CSV 绝对路径。每个 S 参数一列、第一列频率；`in_db=True` 写 dB，否则写 `_re`/`_im` 两列。**离线**，不需要设计环境（阶段 5.5 新增） |
| `export_farfield_csv(save_path, tree_path='Farfields', run_id=0)` | `str`：把远场 2D 云图拉平成 `x, y, value` 长表 CSV。⚠️ **未验证**（本机没有含远场结果的工程可试），见统一计划 P4/V2（阶段 5.5 新增） |

### `run_id` 是什么

CST 工程里同一份结果会存**多次运行的副本**：`run_id=0` 是默认的**最终结果**，其它 id 对应参数扫描的各个样本、网格自适应的中间 pass 等。

- **默认值**：`run_id=0`（最终结果），所有读取方法都带这个默认值。
- **枚举**：`get_all_run_ids(max_mesh_passes_only=True)` 拿工程级 run id 列表；`get_run_ids(treepath, skip_nonparametric=True)` 拿某一项专属的 run id（并排除 `0`，用于只看参数扫描样本）。
- **交叉读**：把某个 run id 传给 `read_1D` / `read_s_parameter` 就能读那次运行的结果，例如 `res.read_s_parameter("S1,1", run_id=run_ids[-1])`。

---

## 6. 核心用法

> 前置：仓库根目录已 `pip install -e .`，且 `cst_solver/config.py` 的 `CST_INSTALL_PATH` 指向本机 CST。示例中**不需要** `sys.path.append`。

### (a) 打开工程 → 建模 → 求解 → 读结果（全流程）

```python
from cst_solver import setup, result

app = setup(r"D:\TPC\examples\tmp.cst")      # 打开并激活工程；文件不存在 → FileNotFoundError

app.set_units(frequency="GHz", length="mm")
app.para("a", 0.2425)                        # StoreParameter
app.para("h", 0.25)
app.para("l1", "0.65*a", log_flag=1)         # log_flag=1 → 立刻 full_history_rebuild() 让参数生效
app.new_material("Silicon (lossy)")
app.create_component("crystal")
app.create_brick("-2*a", "2*a", "-2*a", "2*a", "-h/2", "h/2",
                 "substrate", component="component1", material="Silicon (lossy)")
app.set_frequency_range(300, 380)            # Solver.FrequencyRange
app.create_waveguide_port(1)                 # 波导端口（需已拾取端口面）
app.define_monitor("E", [310, 320])          # 场监视器
app.add("substrate", "crystal_part")         # Solid.Add

print(app.cst_file.get_messages())           # ✅ 应为空 —— CST 失败有两条通道，消息只是其中之一（§7.2）
app.cst_file.model3d.Rebuild()               # ✅ 阻塞式重放整条历史，最能暴露问题
print(app.cst_file.get_messages())           # ✅ 重建后仍应为空（须在干净工程里）

app.run()                                    # 提交求解任务
app.save()
app.close()                                  # 关工程 + 关设计环境

res = result(r"D:\TPC\examples\tmp.cst")     # 结果读取器独立于 setup
print(res.get_available_results()[:5])       # 先看树里有什么
s11 = res.read_s_parameter("S1,1")           # ndarray (n, 2)
freq, mag = s11[:, 0], s11[:, 1]
```

### (b) `log_flag=0` 拼接复合命令 → 只留**一条**历史

`log_flag=0` 的方法**只返回 VBA 文本、不下发**。手工复刻 `triangle()` 的做法：

```python
data = [["0", "a/sqr(3)"],
        ["-a/2", "-a/2/sqr(3)"],
        ["a/2", "-a/2/sqr(3)"],
        ["0", "a/sqr(3)"]]                       # 首尾重合 = 闭合；注意必须 CCW（见 §7.3）

f1 = app.polyline(data, "tri1", "curve1", log_flag=0)                       # 只返回文本
f2 = app.extrude("curve1:tri1", "tri1", "h",
                 material="Silicon (lossy)", log_flag=0)
f3 = app.translate("tri1", ["0", "0", "-h/2"], log_flag=0)

app.cst_file.model3d.add_to_history("Triangle: tri1", f1 + f2 + f3)          # 一次下发 = 一条历史
```

不带 `log_flag` 的方法（如 `create_brick`、`add`、`define_monitor`）**总是立即下发**，各自占一条历史 —— 需要合并时用带 `log_flag` 的**几何类**方法（`polyline` / `arc` / `extrude` / `rotation` / `translate`）自己拼。库内的 `triangle()`、`hexagon()` 就是这么写的。
⚠️ **不要照搬这个手法去用 `para` / `paras`** —— 它们的 `log_flag` 是另一个意思（「是否重建历史」），不返回 VBA 文本，见 §7.1 的对照表。

### (c) 用旧名别名（VBA 风格名仍然可用）

新方法一律 `snake_case`，旧 VBA 风格名保留为别名，两套写法等价：

```python
app.square(0, 10, 0, 10, 0, 2, "substrate")        # 旧名 ≡ create_brick(...)
app.cylinder([0, 0], [2, 0], [0, 3], "rod")        # 旧名 ≡ create_cylinder(...)
app.subtract("substrate", "hole")                  # 正确拼写（旧名 substract 仍是等价别名）
app.rotation("rod", [0, 0, 90])                    # 旧名 ≡ rotate(...)
app.new_component("crystal")                       # 正确拼写（旧名 new_componet 仍是等价别名）
app.project_open(r"D:\other.cst")                  # 旧名 ≡ open_project(...)
```

### (d) 用 `with` 上下文管理

```python
from cst_solver import setup

with setup(r"D:\TPC\examples\tmp.cst") as app:      # __enter__ 返回 self
    app.square(0, 1, 0, 1, 0, 1, "smoke", "component1", "Silicon (lossy)")
    print(app.cst_file.get_messages())              # 应为空
    app.cst_file.model3d.Rebuild()
    print(app.cst_file.get_messages())              # 应为空
# 退出 with 自动调用 app.close()：先 cst_file.close() 再 project.close()，释放设计环境
```

`__exit__` 无条件调用 `self.close()`（**不**吞异常、**不**返回 `True`），所以异常仍会正常抛出，只是资源一定会被回收。

### (e) 结果读取：先看树，再按 `run_id` 读

```python
from cst_solver import result

res = result(r"D:\TPC\examples\tmp.cst")

print(res.get_tree_items()[:5])                 # 1) 先看导航树里有什么
run_ids = res.get_all_run_ids()                 # 2) 默认只看最终结果（max_mesh_passes_only=True）
print(run_ids)

s11 = res.read_1D("S-Parameters\\S1,1")         # 自动加前缀 "1D Results\\"
s21 = res.read_s_parameter("S2,1", run_id=run_ids[-1])   # 指定某次运行的结果
field = res.read_3d("E-Field\\e-field (f=310)")          # 前缀 "2D/3D Results\\"
print(field['values'].shape, field['x'].shape, field['z'])   # z 可能为 None
```

---

## 7. 硬约定与已知缺陷

以下 6 条是**跨包通用**的铁律（`docs/ARCHITECTURE.md` §6 同款），违反任何一条都会得到「能跑通但结果是错的」——CST 未必会报错来提醒你。

### 7.0 运行时守卫层（`cst_solver/_guards.py`，阶段 5 新增）

上面这些铁律原本全是**文档约定**，靠人记住；阶段 4 暴露的 8 处缺陷里 6 处属于这一类。
守卫层把它们变成**可执行检查**，每条给出错误三件套 `code` / `message` / `next_action`。

```python
from cst_solver import get_guard_state, set_guard_mode, CstGuardError

set_guard_mode('strict')          # 'off' | 'warn'(默认) | 'strict'
try:
    app.run()
except CstGuardError as e:
    print(e.finding.code, '->', e.finding.next_action)
```

| 编号 | 陷阱 | 在哪触发 | 处置 |
|---|---|---|---|
| **T2** | 改了**已被几何引用**的参数，却直接 `run()` → 算的是**旧几何** | `run()` 之前 | strict 抛 `CstGuardError`；warn 只警告 |
| **T7'/T13** | `para(..., log_flag=0)` 写进参数表但**不重建历史** | `para()` / `paras()` 调用点 | 警告，并给出 `log_flag=1` / `update()` 两条修法 |
| **T3** | 导出远场/2D-3D 结果后再 `save(include_results=True)` | `save()` 之前 | 建议改 `include_results=False` |
| **T8** | 把 `Abs(E)`（`'efield'`）当**增益证据** | 远场绘图 | 未知模式拦截；`require_gain=True` 时非增益模式拦截 |
| **T10** | `project_path` 后缀不是 `.cst` / `.prj` | `open_project()` | strict 抛错 |
| **T15** | `close()` 之后再 `save()`（什么都不会写出） | `save()` / `close()` | 先 `save()` 再 `close()`；未保存就关会给警告 |

**三个必须知道的实现细节**：

1. **`mode='off'` 与引入守卫层之前逐字节一致** —— 不报警、不拦截、**不额外调用任何 CST 接口**。
   只有 `mode!='off'` 时守卫才会问 CST 两句：`Solid.GetNumberOfShapes()`
   （判断工程里有没有几何）与 `GetParameter(name)`（判断参数是否是新定义的）。
   `config.py` 里写 `CST_GUARD_MODE = 'strict'` 可改默认模式。
2. **只把「改一个已存在的参数」判成脏**，首次写入的参数名不算 —— 因为库的约定是
   「先定义参数、再用它建几何」，所以一个全新参数不可能被**已有**几何引用。
   这条判据是阶段 5 实测模板时补的：`topo_modeler/builders/feed.py` 的优化块会在
   几何已存在之后才 `para('tx1', 0.2)`，按最初的「几何已存在就判脏」会**误报**。
   （代价：打开已有工程后，本次会话第一次改一个**已存在**的参数，靠 `GetParameter()`
   兜住；若该接口读不出来，会退化为「按新参数处理」而**漏报**一次。）
3. 守卫**不替代验收**：它只在 `run()` 前防呆，`validate_model()`（见 §7.2）才是拿到结论的地方。

**判据与影响面（`mark_params_changed()`，P4/V4 真机补充，2026-09-17）**：
T7'/T13 只在「**参数已存在**（`preexisting=True`）**且几何已建**（`geometry_exists()` 为真）」时判脏并告警。
因此**重复登记同名同值参数会被误报** —— 登记的是同一个表达式、几何根本没变，却仍被判成脏。
这不是守卫判据的错，而是**调用方的冗余下发**：上层已通过让 `TopoPath.auto_define_cst_params()`
**幂等**（同一 `TopoPath` + 同一 `app` + 同一前缀只登记一次）来规避，详见
[`../validation/p4_real_machine_evidence.md`](../validation/p4_real_machine_evidence.md) §5.1 与
[`mesh_grid.md`](./mesh_grid.md) §4.3 / §4.5 第 10 条。真机现象：`UnitAntenna` 在 warn 模式下
曾刷出 6 条 `[LOG_FLAG_NO_REBUILD]`（点名 `p1x/p1y/p2x/p2y/p3x/p3y`），修复后为 0 条。

**T3 的真机结论（同日，CST 2026）**：在**已求解工程的副本**上，`export_result_1d('S-Parameters\\S1,1', path)`
确实产出了文件；随后 `save(include_results=True)` **如期**给出 `SAVE_AFTER_RESULT_EXPORT`
（plan_id=T3，severity=warning）；改用 `include_results=False` **不再告警**（与守卫给出的建议一致）。
详见 [`../validation/p4_real_machine_evidence.md`](../validation/p4_real_machine_evidence.md) §5。

### 7.1 `add_to_history` 是唯一执行通道

所有 Mixin 的 VBA 都经 `self.cst_file.model3d.add_to_history("<历史标签>", vba_string)` 下发，没有第二条路径（少数查询类操作会直接调 CST 接口，如 `Units.GetLengthUnit()`、`model3d.GetParameter()`、`model3d.run_solver()`、`model3d.full_history_rebuild()`）。

⚠️ 它同时是**异常出口**：CST 拒绝这条 VBA 时会把原文抛回 Python（`RuntimeError: An error occurred while trying to execute add_to_history: (&H8000ffff) …`），所以「不看消息就没事」不成立，两条通道都要看（§7.2）。

⚠️ **`log_flag` 有两种含义，不要互相类推**：

| 方法族 | 默认值 | `log_flag=0` 的含义 | `log_flag=1` 的含义 |
|---|---|---|---|
| **几何类**：`polyline` / `arc` / `extrude` / `rotation` / `translate` / `mirror` … | **1** | **只返回 VBA 文本，不下发**（`triangle()` / `hexagon()` 用它把多步合成一条历史） | 写入历史并立即生效 |
| **参数类**：`para()` / `paras()` | **0** | **写入参数表，但不调用 `full_history_rebuild()`** —— 参数存进去了，几何却不会跟着变 | 写入参数表**并**立即重建历史 |

参数类的 `log_flag=0` 正是 T2/T7'/T13 的来源：它**不是**「不下发」，所以从返回值上看不出任何异常，
只有几何悄悄停留在旧值上。守卫层会在这种改法之后、`run()` 之前提醒你（§7.0）。
历史标签也是可读的排错线索（`"Square: substrate"`、`"Define Port: 1"`…）。

### 7.2 CST 报错有**两条**通道，且消息不会自动清空

**通道 ①：`add_to_history()` 可能直接抛 Python 异常。** 真机实测（2026-09-17，CST 2026）
非法 VBA 会让 `model3d.add_to_history()` 抛出 `RuntimeError`，异常文本里带 CST 原文：

```
RuntimeError: An error occurred while trying to execute add_to_history:
(&H8000ffff) Invalid coordinate type. Please specify either "Free", "Full" or "Picks".
(.Coordinates "BogusXYZ")
```

**通道 ②：有的失败只写消息**，`add_to_history()` 正常返回。所以判定必须**两条都看**：
调用点接异常 + 读 `app.cst_file.get_messages()`。

- 读消息要**即读即存**（`msgs = app.cst_file.get_messages()`），本次读到的消息读走就没了，
  别指望事后回看。
- ⚠️ 但**读取并不让工程变干净**：工程历史里只要留下过**一条失败命令**，之后**每次**读都会
  **再次**报出那条历史失败（不是「读一次就清空」）。后果是「消息为空 = 成功」在**脏工程**里会
  **一直判失败** —— 实测 `pick_face_auto()` 因此一直返回 `None`，而 `GetNumberOfPickedFaces()`
  明确是 `1`（拾取其实成功了）。**判定必须优先用正向信号**（§7.9）。
- 更要跑 **`app.cst_file.model3d.Rebuild()`**：阻塞式重放整条历史树，大模型约几秒。历史能不能无错重放，决定了模型是否真的可复现。
- 典型症状：实体名被上一步布尔消耗掉（`Shape does not exist`）、几何只在重建后才暴露问题。改动后必须「`get_messages()` 为空 + `Rebuild()` 后仍为空」双验收 ——
  但**只在干净工程里成立**，历史里留过失败命令时以正向判据为准。

**阶段 5 起有 API 支撑，不用再自己抄这三步**：

```python
out = app.validate_model()          # 读消息 → Rebuild() → 再读消息
out['status']       # 'success' | 'error'
out['messages']     # 本次验收到的问题消息（含 Rebuild 阶段）
out['rebuild_ok']   # Rebuild 本身是否干净
out['before']       # 调用前积压的历史消息（已清空）
out['guard']        # 守卫层发现摘要
```

`validate_model()` **不抛异常**，调用方按 `status` 分流 —— 既能用在断言脚本里，
也能用在「先跑一遍看看能不能继续」的探测场景。`Rebuild()` 成功时它会顺带清掉
守卫层的「参数脏」标记（历史已重放 ⇒ 参数与几何重新一致）。

> P1 起求解侧还有更进一步的 `app.run_checked()`：它把「提交未抛异常 / 消息为空 /
> 结果存在 / 结果指纹发生变化」四条**一起**判，理由与判定表见 §8.3。

### 7.3 `ExtrudeCurve` 沿多边形法向拉伸，绕向决定方向

法向由顶点**绕向**决定：**CCW（有向面积 > 0）→ +z，CW → −z**。库内统一「**多边形给 CCW + `translate -h/2`**」。绕向写错时，实体之间会在 z 上**差一个 `h`**，随后的布尔求交得到**空集、且不报错**。想彻底绕开这个问题，用 `app.square(...)`（`Brick`）直接给 `zmin/zmax`。

### 7.4 布尔语义（谁留下、谁消失）

| 命令 | 结果留在 | 被消耗/删除 |
|---|---|---|
| `Intersect "A","B"` | **A** | B 被消耗 |
| `Add "A","B"` | **A** | **B 被删除** |
| `Subtract "A","B"` | **A** | **B 被删除** |
| `Insert "A","B"` | A | **B 保留**，可继续引用 |

即 `app.intersect('g1A', 'clip_A')` 之后 `g1A` 就是结果，而 `clip_A` 已不存在；`Insert` 是唯一保留 B 的。

### 7.5 相对路径按当前工作目录解析

`setup("tmp.cst")`、`save(r"out.cst")`、`dxf_import("a.dxf")` 里的相对路径都相对**当前工作目录**（`setup.__init__` 只在打开工程时做 `os.path.abspath`）。模板 `tmp.cst` 必须放在 notebook/脚本的同目录，或直接用绝对路径。

### 7.6 `cst_file.modeler` 已废弃 → 用 `cst_file.model3d`

新代码一律 `self.cst_file.model3d.*`。全包只剩一处残留：`simulation/monitors.py:61` 的 `_get_model_bbox()` 仍调 `self.cst_file.modeler.GetBoundingBox()`（且只捕获 `AttributeError`，失败返回 `None`）。

### 7.7 已知拼写问题（现状：**已全部修正**，改法见 `skills/developer/WORKFLOW.md` §5）

| 原拼写 | 位置 | 修正方式 | 状态 |
|---|---|---|---|
| `substract` | `modeling/booleans.py` | 真实现改名为 `subtract()`，`boolean_subtract()` 转发，`substract` 保留为**弃用别名**；历史标签一并改为 `"... subtract ..."` | ✅ 已修 |
| `roation` | `modeling/transforms.py:66`（**历史标签**，非方法名；方法名一直正确） | 历史标签改为 `" rotation "` | ✅ 已修 |
| `new_componet` | `material/materials.py` | 真实现改名为 `new_component()`，`create_component()` 转发，`new_componet` 保留为**弃用别名**；同时修掉误用的历史标签 `"Freq_range "` → `"New Component: <name>"` | ✅ 已修 |
| `patten_export` | `import_export/io.py` | 真实现改名为 `pattern_export()`，`export_pattern()` 转发，`patten_export` 保留为**弃用别名** | ✅ 已修 |
| `invertdrection` | `simulation/ports.py` | 形参改名为 `invert_direction`；旧关键字仍可通过 `**legacy_kwargs` 传入（同时传两者会抛 `TypeError`） | ✅ 已修 |
| `AccurarcyHex` / `AccurarcyTet` | `simulation/solver.py`（docstring 中的 `set_solver_parameter` 键名示例） | 改为 `AccuracyHex` / `AccuracyTet` | ✅ 已修 |

修法统一遵循 WORKFLOW §5：**加正确名 → 旧名指向正确名（别名）→ 文档标注「旧名，已弃用」**；不允许静默破坏兼容。所有旧名目前仍然可用。

### 7.8 其他读代码核对到的次要不一致（未实测，供修复时定位）

| 位置 | 现象 |
|---|---|
| `simulation/monitors.py:61` | 使用已废弃的 `cst_file.modeler`，违反 §7.6 |
| `postprocessing/plot.py:80` | `.ScalarFieldComponent "{component}" if component else "Abs"` 整段是 f-string **文本**，下发的 VBA 形如 `... "X" if X else "Abs"`，并非合法 VBA；`component=''` 时也不会回退成 `"Abs"` |
| `material/materials.py` | ~~`new_componet()` 下发历史时用的标签是 `"Freq_range "`~~ —— **已修**：标签改为 `"New Component: <name>"` |

### 7.9 面拾取的成功判定：`_pick_succeeded()`（P4/V5 真机修正，2026-09-17）

`PickMixin.pick_face_auto()` 原本以「`get_messages()` 没报错」判定每次拾取是否成功。
真机实测推翻了这条判据：**脏工程里历史失败会反复报出**（§7.2），于是即便本次拾取成功、
消息仍非空 ⇒ `pick_face_auto()` **一直返回 `None`**（同一场景实测 `GetNumberOfPickedFaces() == 1`）。

现在 `pick_face_auto()` 的两处判定都改用新增的 `_pick_succeeded()`：

1. **优先看正向信号**：`get_picked_count('face') == 1`（即 `Pick.GetNumberOfPickedFaces()`）
   ⇒ 直接判成功，**完全不看消息**；
2. **取不到计数时**才退回原来的「`get_messages()` 为空」判定。

⚠️ `get_picked_count()` 在 `model3d.Pick` 未暴露时**按文档抛 `RuntimeError`**（不是返回 `None`）；
`_pick_succeeded()` 内部吞掉该异常后走第 2 条路径 —— **两条路径都有测试覆盖**：
`cst_solver/tests/test_picks.py`（5 项，含回归用例「消息非空但已选面数为 `1` ⇒ 必须判成功」）。
真机证据：[`../validation/p4_real_machine_evidence.md`](../validation/p4_real_machine_evidence.md) §3。

### 7.10 真机已核验的 VBA（P4/V5）：`Port.Coordinates` 与 `Solid.Imprint`

| 位置 | 写法 | 真机结论（CST 2026，2026-09-17） |
|---|---|---|
| `simulation/ports.py:82` | `.Coordinates "Picks"` | **被接受**（拾取 1 个面，无异常、无消息）⇒ **库当前用法正确，不要改名** |
| `simulation/ports.py` | `.Coordinates "Picked"` | **被拒绝** ⇒ 第三方文档里的这个拼写是错的 |
| `simulation/ports.py` | `.Coordinates "Free"` / `"Full"` | 被接受（合法取值就这三种，枚举由 CST 自己的报错信息给出） |
| `modeling/booleans.py:123` | `Solid.Imprint "component1:b1", "component1:b2"` | **被接受**（两个相交方块）；坏实体名被拒（`Shape does not exist: component1:noxx`） |

`scripts/verify_port_face_api.py` docstring 里那句「V1 `Port.Coordinates` 究竟认 `"Picks"` 还是
`"Picked"` —— 按要求暂不核验」**已核验完毕**：认 `"Picks"`。逐条证据见
[`../validation/p4_real_machine_evidence.md`](../validation/p4_real_machine_evidence.md) §2
（该轮 P4 只做掉 V8/V5 两项，其余条目仍待办）。

---

## 8. P1 加固层：表达式校验、结构化失败通道与运行契约

P1（契约收口）在 `cst_solver` 里加了三块**离线**能力，落点都在 Mixin 之外 ——
目的就是在「拼字符串下发」（§7.1）这条唯一执行通道的**前后各加一道可校验的关口**：
**下发前**能查输入（表达式 / 名称 / 路径 / 文本），**下发后**能分清「返回了」与「真的做成了」。

| 模块 | 主要符号 | 一句话职责 |
|---|---|---|
| `expressions.py` | `check_expression` / `check_name` / `check_path` / `check_vba_text` + 各自的 `validate_*` | 表达式 / 名称 / 路径 / VBA 文本的**离线**校验（不 import CST、不建 DE） |
| `failures.py` | `structured_error` / `record_failure` / `collect_failures` / `CstOperationError` | **结构化失败通道**：把「记一条 warning 后返回」的静默失败变成可检查、可判定的记录 |
| `run_contract.py` | `RunContract` / `JsonlSink` / `result_conventions` / `result_fingerprint` + `app.run_checked()` | **运行契约**：把「提交了」「算完了」「结果存在」「结果是本次的」逐条分开 |

> ⚠️ **证据等级（本节全部内容）**：目前只有**离线测试**证据 ——
> 假 CST 对象 + 临时目录，`python -m pytest cst_solver/tests/ -q`；
> 汇总记录见 [`../validation/p1_contract_evidence.md`](../validation/p1_contract_evidence.md)。
> 运行契约的真机判据（真实 runner 串行闭环、`cst_result_probe()` 读真工程结果区）
> 属计划 **P4/V7**，本文件不声称已通过真机验证。

### 8.1 表达式与名称校验（`cst_solver/expressions.py`）

CST 里长度/角度其实都是**表达式字符串**（§1 第 2 条），字符串写错要等到 CST 消息区才知道。
`expressions.py` **不 `import cst`、不创建 `DesignEnvironment`**，把「明显拼错的输入」
在没有 CST 的机器上先筛掉：所有 `check_*` **不抛异常**，返回带 `ok` / `errors` 的结构，
`validate_*` 是同一个检查的**抛异常**版本。

| 公开入口 | 返回 | 作用 |
|---|---|---|
| `check_expression(expression, parameters=None, allow_unknown_functions=True)` | `ExpressionCheck` | 表达式语法；给了 `parameters` 就**逐个核对参数引用** |
| `validate_expression(...)` | `True` / 抛 `CstExpressionError` | 同上，抛异常版 |
| `check_name(name, kind='geometry', known=None)` | `NameCheck` | 实体 / 组件 / 材料名；`kind='parameter'` 时按标识符查 |
| `check_path(path, kind='path', known=None)` | `NameCheck` | **路径**（禁止字符集与名称不同，见下） |
| `check_vba_text(text, kind='text')` | `NameCheck` | 参数说明等「VBA 字符串字面量内部的自由文本」 |
| `check_material_name` / `validate_name` / `validate_parameter_name` / `validate_path` / `validate_material_name` / `validate_vba_text` | `NameCheck` / `True` | 上面几种检查的便捷入口与抛异常版 |
| `tokenize` / `parse_expression` / `expression_identifiers` | 词法 / 语法 / 标识符表 | 校验的实现件，也单独公开 |
| `KNOWN_FUNCTIONS` / `KNOWN_CONSTANTS` / `MAX_NAME_LENGTH` | 数据 | 白名单函数（`sqr`、`int`、`min`…）、常量（`pi` / `e`）、名称长度上限 **128** |

**语法口径**：覆盖四则、`^`、括号、一元符号、数值字面量（含 `1e-3` / `.5`）、常量 `pi` / `e`
与白名单函数。下列**真实表达式必须放行**（有测试逐条钉住）：
`a/2`、`a/2*sqr(3)`、`0.65*a`、`-lf5-lf6-lf4`、`int(yup/2)`、`sqr(ec_a^2-ec_b^2)`。

**宁可漏拒、不可误拒**：白名单外的函数名默认**只放行、并记进 `unknown_functions`，不判错** ——
CST 的函数集比 `KNOWN_FUNCTIONS` 大，误杀一个合法函数的代价远高于放过一个存疑函数。
要收紧就显式传 `allow_unknown_functions=False`。

**三套禁止字符集是不同的**（P1 踩过并修掉的坑：路径最初被名称规则校验，
于是**所有 Windows 路径被判死**，因为反斜杠在名称里非法）：

| 检查 | 允许 | 拦下 | 典型通过样例 |
|---|---|---|---|
| `check_name`（几何 / 组件 / 材料） | 括号、空格、点、连字符、中文 | 引号、换行、回车、制表、**反斜杠**、控制字符；空名、超长（`> MAX_NAME_LENGTH`） | `Copper (annealed)`、`Port 2`、`直波导BA-18a` |
| `check_name(kind='parameter')` | 同上，但**还要求是合法标识符** | 额外拦 `1a`、`a-1` 这类非标识符 | `vpc_A`、`feed2_opt1` |
| `check_path` | **反斜杠与冒号合法** | 只拦会破坏 VBA 的：引号、换行、制表、控制字符 | `D:\out\wg.cst`、`C:/tmp/tmp.cst` |
| `check_vba_text` | 单引号、反斜杠、制表、中文、空格 | 只拦会**逃出引号**的：双引号、换行、回车、控制字符 | `直波导 BA 型，长度 18a` |

> `check_vba_text` 之所以另有一套更宽松的规则，与路径同理：参数说明本来就带空格、
> 中文与标点，用名称规则去套会大面积误报。

错误码：名称侧 `name_empty` / `name_not_string` / `name_too_long` /
`name_forbidden_character` / `name_not_identifier` / `name_unknown_value`；
表达式侧 `expression_empty` / `expression_not_string` / `expression_syntax_error` /
`expression_forbidden_character` / `expression_unknown_parameter` / `expression_unknown_function`。

### 8.2 结构化失败通道（`cst_solver/failures.py`）

**它解决的问题**：旧兼容路径「记一条 `logging.warning` 后返回」时，
`None` / `[]` / `False` 既可能是「失败了」，也可能是「本来就没有数据」——
`new_material('Gold')` 在既有 notebook 里就是「提示一下、继续跑」，
调用方拿不到任何判据（`docs/architecture/cst_mcp.md` §5 明令禁止把失败伪装成成功）。

| 公开入口 | 签名 | 作用 |
|---|---|---|
| `structured_error` | `structured_error(code, message, *, retryable=False, **details)` | `{code, message, details, retryable}` 的**唯一实现** |
| `record_failure` | `record_failure(operation, code, message, *, retryable=False, log=True, **details)` | 记一条**静默失败**：写 logging，同时进当前收集器；严格模式下抛 `CstOperationError` |
| `collect_failures` | `with collect_failures() as failures:` | 上下文管理器：退出时 `failures` 就是本次块内发生的静默失败列表 |
| `recent_failures` | `recent_failures(*, clear=False)` | 读全局最近的记录（可顺带清空） |
| `set_failure_strict` / `failure_strict_enabled` | `set_failure_strict(enabled)` | 可选**严格模式**（默认关闭）：开启后静默失败直接抛异常 |
| `reset_failure_state` | `reset_failure_state()` | 清空收集状态（测试用） |
| `CstOperationError` | `CstOperationError(code, message, *, retryable=False, operation='', **details)` | 结构化异常，带同样的四件套 |

**默认不抛异常是刻意的兼容决策**：`new_material('Gold')` 在既有 notebook 里只是「提示一下」，
直接改成抛异常会破坏一批脚本（P1 的验收判据之一正是「旧 notebook 导入兼容」）。
因此默认行为只是**多一条可检查的记录**，要硬拦截由调用方显式开严格模式。

`structured_error()` 是**唯一实现**：`cst_solver.expressions`、`cst_solver.run_contract`
与 `topo_modeler.preflight` 三处的结构化错误都复用它（预检层把 `topo_modeler.config.ConfigError`
转成同一个四件套回给调用方），因此**错误结构在整个仓库里只有一种**。

### 8.3 运行契约（`cst_solver/run_contract.py` + `run_checked()`）

**问题**：`app.run()` 把 VBA 交下去就返回 ——「返回了」既不代表「算完了」，
也不代表「结果存在」，更不代表「这份结果是本次算的」。契约层把这四件事分开判定。

| 入口 | 签名 | 返回 |
|---|---|---|
| `app.run_checked`（**P1 新增**，`simulation/solver.py`） | `run_checked(project_path=None, *, sink=None, note='', probe=None, read_messages=True) -> dict` | 结构化运行结论（`RunContract` 的记录） |
| `app.run` | `run()` | **仍返回 `None`，行为一字未改** |

⚠️ 两者是**并存**而不是替代关系：`run()` 保持原样是为了不破坏既有 notebook 与模板
（`topo_templates` 的 `run()` 未改）；契约入口是 **opt-in** 的。
`run_checked` 默认把记录写到 `run_log_path(工程)` —— 因为 CST 的 `get_messages()`
**读到的消息读走就没了**（§7.2；注意历史失败会反复报出），不落盘就事后无据可查；`project_path` 取不到时结论落到 `unverified`，
**不会假装成功**。

**判定表**（`RunContract`；`succeeded` 需**同时**满足「提交未抛异常 + `get_messages()` 为空 +
结果存在 + 结果指纹在提交前后发生变化」）：

| 场景 | `status` | 错误码 |
|---|---|---|
| 提交成功、消息为空、指纹变化 | `succeeded` | — |
| 提交抛异常 | `failed` | `run_exception` |
| 提交后消息非空（有的失败不抛异常，消息是主要线索；脏工程里消息会反复报历史失败，判据见 §7.2/§7.9） | `failed` | `run_messages` |
| 读消息失败 | 降级 `unverified` | `messages_unreadable` |
| 工程里看不到任何结果 | `unverified` | `results_missing` |
| 指纹与提交前完全一致（很可能还是上一轮的结果） | `unverified` | `results_unchanged` |
| 指纹不可用（探测失败 / 取不到工程路径） | `unverified` | `results_not_verified` |
| 运行记录落盘失败 | 结论不变 + 附一条错误 | `audit_write_failed` |

`RUN_STATUSES = ('succeeded', 'failed', 'unverified', 'interrupted')`；
`RUN_ERROR_CODES` = 上表右列的全部取值。

> ⚠️ **必须连同结论一起引用的局限**：`results_changed` 是**必要条件，不是充分条件** ——
> 它只能证明「结果区在提交之后变了」，**不证明**这份结果就是本次提交算出来的
> （例如另一个会话/进程也在写同一个工程）。真正的判据是 P4/V7 的**真机**串行闭环
> （真实 runner 跑一次 + `cst_result_probe()` 直接读结果区）。
> **在 P4 完成之前，任何「运行契约已通过真机验证」的说法都不成立。**

**单位与口径做成了数据**（`result_conventions()` 返回 JSON 可序列化字典）：

| 键 | 值 |
|---|---|
| `frequency_unit` | `GHz` |
| `s_magnitude` | 复数（实部 / 虚部） |
| `s_db` | `20*log10(abs(S))` |
| `zero_magnitude_db` | `-300.0`（零值口径，不是 `-inf`） |
| `run_id_default` / `run_id_semantics` | `0`；`run_id=0` 是「**当前最新结果**」的**别名**，**不是**历史 run 编号 —— 要固定某次运行必须显式传入该 run_id（对照 §5） |
| `port_mode_naming` | `S<i>,<j>` 对应 `cst_solver` 的端口编号，模式 1 为主模 |
| `length_unit` | `mm`（CST 工程单位；另有 `cst_solver.units.get_units`） |
| `source` | `cst_solver/_result_core.py::_to_db` 与 `topo_modeler/result_reader.py::_to_db` |

**落盘**：`JsonlSink(path)` 每行一条 JSON、**追加写**，接口是 `write(record) -> path`；
`run_log_path(project)` = 工程目录下的 `run_contract.jsonl`。

其余公开件：`result_fingerprint(project_path, probe=None)`（取一次结果指纹）、
`disk_result_probe` / `cst_result_probe`（两种默认探测器：磁盘态与 CST 结果区）、
`project_path_of(app)`（从 `setup` 实例推断工程路径）。

### 8.4 参数入口的自查（`cst_solver/parameters.py`）

`para()` 现在在下发之前先过一遍 `_check_parameter_inputs(name, value, expression)`，
三样输入各查一次：

| 输入 | 用什么查 | 口径 |
|---|---|---|
| 参数名 | `check_name(kind='parameter')` | 必须是合法标识符 |
| 字符串值（`value` 是 str 时） | `check_expression` | 按 **CST 表达式**查 |
| 说明文本（`expression`） | `check_vba_text` | 按 **VBA 字面量内的文本**查 |

⚠️ 这一层**只记录结构化失败，不改变下发内容、不抛异常** —— 参数照旧写进 CST，
返回值照旧（默认行为与 P1 之前完全一致）。要硬拦截需显式开 `set_failure_strict(True)`。

表达式检查**不做参数表引用核对**：此刻参数表可能还没建全
（`para('l1', '0.65*a')` 里的 `a` 可能稍后才定义），核对会大面积误报。

### 8.5 材料旧接口的结构化失败表（`material/materials.py`）

4 处「记 warning 后返回」的旧兼容路径改为 `record_failure(...)`（共 5 个错误码）：
**返回值与日志文案一字未变**，只是多登记一条结构化失败。

| 方法 | 触发条件 | 错误码 | 返回值（**不变**） |
|---|---|---|---|
| `new_material` | 材料不在预设表内 | `material_not_preset` | 无（继续走原流程，不中断） |
| `list_library_materials` | 材料库路径不存在 | `material_library_missing` | `[]` |
| `load_material_from_file` | 材料文件不存在 | `material_file_not_found` | `False` |
| `load_material_from_file` | `.mtd` 里没有有效定义 | `material_definition_empty` | `False` |
| `get_material_filepath` | 材料库里找不到该材料 | `material_file_missing` | `None` |

### 8.6 `__all__`：公开面显式声明（`cst_solver/__init__.py`）

包顶层新增 `__all__`，把**公开面**与 24 个内部 Mixin 分开：**Mixin 类仍可直接 import**，
只是不再算公开面。唯一例外是 `FaceOpsMixin` —— 它内联定义在 `__init__.py`（§2 注意点 1），
因此在 `__all__` 里。

| 分组 | 名字 |
|---|---|
| 主入口 | `setup`、`result`、`Result` |
| 环境 | `CSTPaths`、`CSTConfigurationError`、`CSTUnavailableError`、`discover_cst_installations`、`get_cst_paths`、`diagnose_environment`、`describe_interface_abi`、`interpreter_abi_tag`、`CST_INSTALL_PATH`、`CST_PYTHON_LIB`、`CST_MATERIAL_LIB` |
| 守卫层 | `CstGuardError`、`GuardFinding`、`GuardState`、`GUARD_MODES`、`DEFAULT_GUARD_MODE`、`FARFIELD_GAIN_MODES`、`FARFIELD_KNOWN_MODES`、`PROJECT_SUFFIXES`、`assert_gain_mode`、`get_guard_mode`、`get_guard_state`、`reset_guard_state`、`set_guard_mode` |
| 内联 Mixin | `FaceOpsMixin` |

> 注：`expressions` / `failures` / `run_contract` 三个 P1 模块**不在** `__all__` 里，
> 按子模块路径导入（`from cst_solver.failures import collect_failures`）。

### 8.7 存根修正记录（P1）

一致性检查（`scripts/check_api_consistency.py` 第 1 项「存根漂移」）把「存根与实现不一致」
变成了可执行检查，第一轮就暴露两处真问题：

| 文件 | 现象 | 处理 | 状态 |
|---|---|---|---|
| `cst_solver/setup.pyi:208-213` | `rotation` 少声明两个**早已实现**的形参：`object='Shape'`、`auto_destination='True'` | 补齐存根 | ✅ 已修 |
| `cst_solver/simulation/setup.pyi:23-25` | `monitor2d` 声明了实现里**不存在**的 `field_type` / `subvolume` | 按实现改正为 `(name, frequencies, plane_normal='z', plane_position=0)` | ✅ 已修 |

> 存根漂移的后果是 API 对 IDE 不可见或被误导（Pylance 补全完全依赖存根，§9 第 5 条）。
> 检查命令为 `python scripts/check_api_consistency.py`，共 8 项：存根漂移 / `__all__` 公开入口 /
> pyproject 打包白名单与 package-data / 安装态与发行版本（**区分 editable**）/
> `python -m cst_solver doctor` 输出 JSON / **MCP 写入口纪律**（`cst_mcp` 必须经共用运行服务
> 与共用校验层，且不得出现 CST 原语或第二套校验规则）/ **错误码一致性**（代码里用到的每个
> 错误码都必须出现在某个 `*_ERROR_CODES` 表里）/ **文档命令一致性**（文档里写的
> `python scripts/*.py`、`pytest <路径>`、`pip install -e <路径>` 必须指向真实存在的文件，
> 且识别 `cd X && …` 的基准目录）；同一套检查另有 pytest 入口
> `pytest tests/test_api_consistency.py`（含反向用例：故意写坏时必须报出来）。

---

## 9. 如何扩展这个包

**先读**：`skills/developer/cst-solver-dev.md`（cst_solver 专用规程 + 待修清单 + 硬约定）与 `skills/developer/WORKFLOW.md`（仓库开发宪法：归属判定、命名规则、文档同步矩阵、提交规范）。**本节的步骤只是索引，一切以这两份为准。**

1. **判定归属**（WORKFLOW §2）：只有「CST 原语级操作」才进 `cst_solver/`。如果需求能用现有 API 组合出来，属于使用者任务，**不要改库**；`topo_modeler/` 里手写 VBA 字符串是反例 —— 应先给 `cst_solver` 补封装。
2. **查权威来源**：CST 安装目录的 VBA 帮助 `{CST_INSTALL_PATH}\Online Help\mergedProjects\VBA_3D\`，逐个核对命令与参数名。
3. **选 Mixin 文件**：按 §3 模块地图的主题归类（画体 → `modeling/primitives.py`，求解器 → `simulation/solver.py`…）；不要新建平行体系。
4. **写方法**：新名 `snake_case` + **保留旧 VBA 名作为别名**；docstring 含参数/返回值/说明，长度与角度标注 `float | str`（CST 表达式是字符串）；需要合并历史的方法加 `log_flag=1` 默认值并在 `log_flag=0` 时**只返回文本不下发**。
5. **同步类型存根（必做）**：改了 `setup` 的公开方法，就必须更新 **`cst_solver/setup.pyi`**（`simulation/` 相关还要看 `cst_solver/simulation/setup.pyi`）。Pylance 的补全完全依赖存根，漏改等于 API 对 IDE 不可见。改完跑一次 `python scripts/check_api_consistency.py`，它会直接报出存根与实现的参数名漂移（P1 起，见 §8.7）。
6. **重新生成文档（必做）**：跑 `python scripts/gen_cst_solver_docs.py`（产物 `docs/guides/api/cst_solver_api.html`；顺带维护 `mesh_grid` 时跑 `scripts/gen_mesh_docs.py`）。**不要手改生成的 HTML。**
7. **冒烟测试**：用**临时**模板工程（不要污染正式工程）建一个体 → `print(app.cst_file.get_messages())` 应为空 → `app.cst_file.model3d.Rebuild()` → 再读一次仍应为空 → `app.close()`。
8. **同步文档**：改动涉及公开 API / 硬约定 / 缺陷清单时，按 WORKFLOW §6 的同步矩阵更新 `docs/ARCHITECTURE.md`、本文件、对应 skill，并在修掉已知缺陷后删掉 `cst-solver-dev.md` 待修清单里的对应行。
9. **一个包一条 commit**（`feat(cst_solver): …` / `fix(cst_solver): …`），正文写清现象、改动、验证命令与兼容性影响，然后 push。

---

## 10. 相关文档

- 总体架构与包分工 → [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
- 自动生成的 API 速查（HTML）→ [`../guides/api/cst_solver_api.html`](../guides/api/cst_solver_api.html)
- 本包的开发规程（硬约定 + 待修清单）→ [`../../skills/developer/cst-solver-dev.md`](../../skills/developer/cst-solver-dev.md)
- 仓库开发宪法（流程 / 命名 / 文档同步 / 提交）→ [`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md)
- 后续阶段要做什么（计划索引）→ [`../next_plan/README.md`](../next_plan/README.md)
- 使用者视角（建模型、排错、验收）→ [`../../skills/user/tpc-usage.md`](../../skills/user/tpc-usage.md)
- P1 契约收口的**离线**实测记录（校验口径边界、判定矩阵、一致性检查发现的问题）→ [`../validation/p1_contract_evidence.md`](../validation/p1_contract_evidence.md)
- P4 真机实测记录（**两条失败通道 + 历史失败反复报出**、`Port.Coordinates` / `Solid.Imprint` 定论、环境与会话生命周期）→ [`../validation/p4_real_machine_evidence.md`](../validation/p4_real_machine_evidence.md)
