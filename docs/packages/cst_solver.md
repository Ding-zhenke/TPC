# cst_solver —— CST 会话封装层

`cst_solver/` 是 TPC 的**最底层包**：CST Studio Suite 的自动化接口本质上是「拼一段 VBA 宏字符串 → 下发到工程的历史树」，本包把这套宏 API 收敛成 **23 个 Mixin 类**，再用多继承聚合成**一个** `setup` 类，于是 200 多个 CST 原语操作（画体、布尔、端口、边界、求解器、网格、导出）都能通过同一个 Python 对象调用；此外还独立提供一个 `result` 类，用于只读地读取**已算完**工程的导航树结果。它与 `mesh_grid` 互相不依赖，是 `topo_modeler` / `templates` 的下层依赖。

| 项 | 内容 |
|---|---|
| **职责** | 把 CST 的 VBA 宏 API 封装成 Pythonic 的 `setup` 对象；另提供只读的 `result` 结果读取器 |
| **需要 CST** | ✅ **必须**。`cst_solver/__init__.py` 在导入时直接 `import cst` / `import cst.interface` / `import cst.results`，未安装 CST Studio Suite 的机器上 `import cst_solver` 必然失败 |
| **入口** | `from cst_solver import setup, result`（`setup` = 聚合类，`result` = 结果读取类） |
| **依赖** | 第三方 `numpy`（`_result_core.py` 用到）；`cst` 由 CST 自带、无法从 PyPI 安装，故不列入 `pyproject.toml`；不依赖任何其它 TPC 包 |
| **被谁依赖** | `topo_modeler/`（如 `topo_modeler/modeler.py`、`topo_modeler/lens_build_standalone.py`）、`templates/`；`tpc_toolkit/` **不**依赖它 |
| **源码位置** | `cst_solver/`：22 个 Mixin 模块 + `__init__.py`（内联 `FaceOpsMixin` 与 `setup`）+ `_result_core.py`（`Result`）+ `config_template.py` / `_path_tools.py`，类型存根 `setup.pyi`、`simulation/setup.pyi` |

> AST 统计（不含归档中的死代码 `_result.py`）：类上公开方法共 **221** 个 = Mixin 方法 **211** 个 + `setup.open` 1 个 + `Result` 9 个。

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
3. **不用维护 CST 库路径**：导入时自动从配置推导 CST 的 `python_cst_libraries` 并加入 `sys.path`。
4. **复合构件可以合成一条历史**：`log_flag=0` 时方法**只返回 VBA 文本、不下发**，于是「画多边形 → 拉伸 → 旋转 → 平移」能拼成**一条**历史项（`triangle()` / `hexagon()` 就是这么实现的）。
5. **同一对象上什么都能干**：建模、材料、端口、边界、求解器、网格、后处理全在 `setup` 上，不用在多个对象间传递 `cst_file`。

**它明确不保证的东西**：

- ❌ **不把 CST 报错转换成 Python 异常**。VBA 命令写错、实体不存在、布尔求交得到空集 —— CST 只在自己的消息区留一条消息，`add_to_history` 照样正常返回。唯一的例外是**打开工程**这一步：`setup(filename)` 在产品文件不存在时抛 `FileNotFoundError`、打开失败时抛 `RuntimeError`。因此**验收必须读 `app.cst_file.get_messages()`**（详见 §7.2）。
- ❌ 不校验参数量纲，不做几何合法性检查，不保证 VBA 命令与你的 CST 版本匹配。
- ❌ 不是 CST 的替代实现：没有 CST 就完全跑不起来（连 `import` 都不行）。

---

## 2. 架构：Mixin 多继承

**设计**：每个模块只定义一个 `XxxMixin` 类，类里只放**与一个 VBA 主题相关**的方法，全部通过 `self.cst_file` 下发命令 —— 它们不重写 `__init__`、不保存状态。`cst_solver/__init__.py` 末尾用多继承把这 23 个 Mixin 聚合为唯一的 `setup` 类。

```python
# cst_solver/__init__.py:229-253（原样）
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

公开方法数为 AST 实测值（不含 `_` 开头的方法）。**22 个 Mixin 各占一个模块文件，第 23 个 `FaceOpsMixin` 内联在 `__init__.py`**；`_result_core.py` 不是 Mixin。

### 根目录

| 文件 | Mixin 类 | VBA 主题 | 公开方法数 |
|---|---|---|---|
| `project.py` | `ProjectMixin` | 工程 打开/关闭/另存/激活（`open_project`、`new_project`…） | 9 |
| `units.py` | `UnitsMixin` | `Units` 单位；单位查询（`GetLengthUnit` 等） | 2 |
| `parameters.py` | `ParametersMixin` | 参数 / 表达式参数 / `Solver.FrequencyRange` 频率范围 | 11 |
| `__init__.py` | `FaceOpsMixin`（内联） | 面旋转、面拉伸、`TraceFromCurve` 走线 | 4 |
| `_result_core.py` | `Result`（**非 Mixin**，不参与 `setup`） | `cst.results.ProjectFile` 结果读取 | 9 |

**根目录小计：Mixin 方法 26 个。**

### `modeling/`

| 文件 | Mixin 类 | VBA 主题 | 公开方法数 |
|---|---|---|---|
| `primitives.py` | `ModelingPrimitivesMixin` | `Brick` / `Cylinder` / `Sphere` / `Cone` / `Torus` / `ECylinder` / `Wire` + 三角形、六边形棱柱 | 13 |
| `curves.py` | `CurvesMixin` | `Polygon` / `Arc` / `Circle` / `Ellipse` / `Line` / `Spline` / `Rectangle` / `Polygon3D` | 11 |
| `curves_ops.py` | `CurveOpsMixin` | `ExtrudeCurve` / `Loft` / `SweepCurve` / `BlendCurve` / `ChamferCurve` / `CoverCurve` / `TrimCurves` | 8 |
| `booleans.py` | `SolidOpsMixin` | `Solid.Add` / `Subtract` / `Insert` / `Intersect` / `Imprint` / `BlendEdge` | 11 |
| `transforms.py` | `TransformMixin` | `Transform` 的 `Rotate` / `Translate` / `Mirror` / `Scale` | 6 |
| `picks.py` | `PickMixin` | `Pick.PickEdgeFromId` / `PickEndpointFromId` / `PickFaceFromId` / `PickVertexFromId` / `PickFaceFromPoint` / `AddEdge` / `ClearAllPicks` | 8 |
| `wcs.py` | `WCSMixin` | `WCS.Reset` / `RotateWCS` / `MoveWCS` / `AlignWCSWithSelected` / `SetOrigin` / `Store` / `Restore` / `Scale` | 17 |

**`modeling/` 小计：74 个。**

### `material/`

| 文件 | Mixin 类 | VBA 主题 | 公开方法数 |
|---|---|---|---|
| `materials.py` | `MaterialMixin` | `Material` 预设/自定义材料、`.mtd` 材料库加载、`Component.New`、`Solid.Rename` / `ChangeComponent` / `ChangeMaterial`、`Material.ChangeColor` | 15 |

**`material/` 小计：15 个。**

### `simulation/`

| 文件 | Mixin 类 | VBA 主题 | 公开方法数 |
|---|---|---|---|
| `ports.py` | `PortMixin` | `Port` / `DiscreteFacePort` / `DiscretePort` / `LumpedFaceElement` / `FloquetPort` / `CablePort` | 9 |
| `sources.py` | `SourceMixin` | `PlaneWave` / `CurrentPort` / `Coil` / `VoltageWire` / `Charge` / `CurrentPath` / `Magnet` / `FieldSource` / `PredefinedField` / `FarfieldSource` / `TimeSignal` | 11 |
| `monitors.py` | `MonitorMixin` | `Monitor`（场/远场/2D 切面监视器）、`Probe` 探针 | 4 |
| `boundary.py` | `BoundaryMixin` | `Boundary` / `Background` / `LayerStacking` | 4 |
| `solver.py` | `SolverMixin` | `Solver`(T) / `FDSolver` / `EigenmodeSolver` / `IESolver` / `AsymptoticSolver` / `ParameterSweep` / `Optimizer` / `SolverParameter`、`run_solver()` / `full_history_rebuild()` | 23 |

**`simulation/` 小计：51 个。**

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
| `config_template.py` | 配置模板（`CST_INSTALL_PATH` 及两条推导路径） |
| `_path_tools.py` | `get_paths(cst_install_path)` —— 只做路径推导的纯函数 |
| `_result_core.py` | `Result` 类 + 旧名别名类 `result(Result)`，包顶层 `result` 由它导出 |
| `setup.pyi` / `simulation/setup.pyi` | 类型存根（IDE 补全唯一依赖），改公开 API 必须同步 |
| `_result.py` | ⚠ **陈旧、从未被任何模块导入的 `_result_core.py` 副本**（307 行 vs 107 行），正在按死代码归档 |

---

## 4. 配置系统

`cst_solver/__init__.py` 第 26-69 行在做任何导入之前先解决「CST 装在哪」。

### 三级解析顺序

| 优先级 | 来源 | 说明 |
|---|---|---|
| 1 | `cst_solver/config.py` | **逐机本地配置**，已被 `.gitignore` 忽略（第 155 行 `cst_solver/config.py`），不进仓库 |
| 2 | `cst_solver/config_template.py` | 随仓库分发的模板；命中时打印「⚠ 未找到 config.py，使用 config_template.py 中的默认配置」 |
| 3 | 内置默认值 | 前两个文件**都不存在**时，硬编码回退到 `C:\SOFTWARE\CST Studio Suite 2026`，并提示创建 `config.py` |

实现上是一个 `for _name in ["config.py", "config_template.py"]` 循环，**命中第一个存在的文件就 `break`**；读取方式是用 `compile` + `exec` 直接执行文件源码（注释里写明这是为了**避免循环导入**：此时若 `import cst_solver.config`，包本身还没初始化完）。

### 需要读/改的只有一项

```python
# cst_solver/config_template.py —— 复制成 config.py 后只改这一行
CST_INSTALL_PATH = r"C:\SOFTWARE\CST Studio Suite 2026"
```

其余两个变量**自动推导**，不要手改：

| 变量 | 推导规则 | 用途 |
|---|---|---|
| `CST_PYTHON_LIB` | `{CST_INSTALL_PATH}\AMD64\python_cst_libraries` | 第 68-69 行 `sys.path.append(...)`，随后 `import cst` 才能成功 |
| `CST_MATERIAL_LIB` | `{CST_INSTALL_PATH}\Library\Materials` | 材料库 `.mtd` 文件目录（`MaterialMixin.list_library_materials()` / `get_material_filepath()`） |

**新机器上的三步**：

1. `cp cst_solver/config_template.py cst_solver/config.py`（Windows 下直接复制粘贴改名）；
2. 把 `CST_INSTALL_PATH` 改成本机 CST 安装目录；
3. 在仓库根目录 `pip install -e .`（**不要**再在示例里写 `sys.path.append`）。

### `_path_tools.get_paths()`

配置之外，任何需要从安装路径推导从属路径的地方，统一走这个纯函数（`config_template.py` 的注释里就这么推荐）：

```python
from cst_solver._path_tools import get_paths

paths = get_paths(r"C:\SOFTWARE\CST Studio Suite 2026")
# {'CST_PYTHON_LIB': '...\\AMD64\\python_cst_libraries',
#  'CST_MATERIAL_LIB': '...\\Library\\Materials'}
```

### 为什么 `config.py` 必须 gitignored

CST 安装路径是**逐机事实**：它因机器、版本（2024/2025/2026…）、盘符而异，提交上去只会造成「别人的路径覆盖我的路径」的冲突。因此仓库里**只有模板**，`config.py` 由使用者本地生成；`MaterialMixin._get_material_library_path()` 也按同一顺序回退（`config` → `config_template` → 默认路径），保证在没建 `config.py` 时至少能跑通。

> WORKFLOW 明确列为禁止事项：**为了让自己的代码跑通而去改 `cst_solver/config.py` 的逻辑**（它是逐机本地配置）。

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

### 9 个公开方法

| 方法（签名） | 返回结构 |
|---|---|
| `get_tree_items()` | 直接返回 `self.result_module.get_tree_items()` —— 导航树中所有结果项（先看它，再决定读哪一项） |
| `get_available_results()` | 中文别名，等价于 `get_tree_items()` |
| `get_all_run_ids(max_mesh_passes_only: bool = True)` | `list[int]`；`True` 只列最终结果，`False` 连中间结果一起列 |
| `get_run_ids(treepath: str, skip_nonparametric: bool = False)` | `list[int]`；`skip_nonparametric=True` 时**排除 `run_id=0`** |
| `get_result_item(treepath: str, run_id=0, load_impedances: bool = True)` | `cst.results.ResultItem`；`load_impedances=False` 跳过自动加载参考阻抗 |
| `read_1D(tree_path, run_id: int = 0)` | `ndarray (n, 2)` = `[xdata, ydata]`（内部 `np.asarray([...]).T`）；`tree_path` **自动加前缀** `"1D Results\\"` |
| `read_2d(tree_path, run_id: int = 0)` | `dict`：`{'x','y','z','values'}`（`z` 在对象没有 `get_zdata` 时为 `None`）；前缀 `"2D Results\\"` |
| `read_s_parameter(s_param: str, run_id: int = 0)` | 便捷方法 = `read_1D(f"S-Parameters\\{s_param}", run_id)`，即 `ndarray (n, 2)` = `[频率, S 参数]` |
| `read_3d(tree_path, run_id: int = 0)` | `dict`：`{'x','y','z','values'}`；前缀 `"2D/3D Results\\"`；全部尝试失败时抛 `ValueError(f"无法读取 3D 结果: {tree_path}")` |

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

print(app.cst_file.get_messages())           # ✅ 必须为空 —— CST 不抛异常，这是唯一验收通道
app.cst_file.model3d.Rebuild()               # ✅ 阻塞式重放整条历史，最能暴露问题
print(app.cst_file.get_messages())           # ✅ 重建后仍必须为空

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

不带 `log_flag` 的方法（如 `create_brick`、`add`、`define_monitor`）**总是立即下发**，各自占一条历史 —— 需要合并时用带 `log_flag` 的那几个（`polyline` / `arc` / `extrude` / `rotation` / `translate` / `para` / `paras`）自己拼。库内的 `triangle()`、`hexagon()` 就是这么写的。

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

以下 6 条是**跨包通用**的铁律（`docs/ARCHITECTURE.md` §6 同款），违反任何一条都会得到「能跑通但结果是错的」——CST 不会报错来提醒你。

### 7.1 `add_to_history` 是唯一执行通道

所有 Mixin 的 VBA 都经 `self.cst_file.model3d.add_to_history("<历史标签>", vba_string)` 下发，没有第二条路径（少数查询类操作会直接调 CST 接口，如 `Units.GetLengthUnit()`、`model3d.GetParameter()`、`model3d.run_solver()`、`model3d.full_history_rebuild()`）。`log_flag=0` 时**只拼字符串不下发** —— 这是 `triangle()` 等复合构件把「画线 + 拉伸 + 旋转 + 平移」合成**一条**历史的手法。历史标签也是可读的排错线索（`"Square: substrate"`、`"Define Port: 1"`…）。

### 7.2 库不保证把 CST 报错抛成 Python 异常

- 验收必须读 **`app.cst_file.get_messages()`**：**读后即清空**，所以要即读即存（`msgs = app.cst_file.get_messages()`），别指望事后回看。
- 更要跑 **`app.cst_file.model3d.Rebuild()`**：阻塞式重放整条历史树，大模型约几秒。历史能不能无错重放，决定了模型是否真的可复现。
- 典型症状：实体名被上一步布尔消耗掉（`Shape does not exist`）、几何只在重建后才暴露问题。改动后必须「`get_messages()` 为空 + `Rebuild()` 后仍为空」双验收。

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

---

## 8. 如何扩展这个包

**先读**：`skills/developer/cst-solver-dev.md`（cst_solver 专用规程 + 待修清单 + 硬约定）与 `skills/developer/WORKFLOW.md`（仓库开发宪法：归属判定、命名规则、文档同步矩阵、提交规范）。**本节的步骤只是索引，一切以这两份为准。**

1. **判定归属**（WORKFLOW §2）：只有「CST 原语级操作」才进 `cst_solver/`。如果需求能用现有 API 组合出来，属于使用者任务，**不要改库**；`topo_modeler/` 里手写 VBA 字符串是反例 —— 应先给 `cst_solver` 补封装。
2. **查权威来源**：CST 安装目录的 VBA 帮助 `{CST_INSTALL_PATH}\Online Help\mergedProjects\VBA_3D\`，逐个核对命令与参数名。
3. **选 Mixin 文件**：按 §3 模块地图的主题归类（画体 → `modeling/primitives.py`，求解器 → `simulation/solver.py`…）；不要新建平行体系。
4. **写方法**：新名 `snake_case` + **保留旧 VBA 名作为别名**；docstring 含参数/返回值/说明，长度与角度标注 `float | str`（CST 表达式是字符串）；需要合并历史的方法加 `log_flag=1` 默认值并在 `log_flag=0` 时**只返回文本不下发**。
5. **同步类型存根（必做）**：改了 `setup` 的公开方法，就必须更新 **`cst_solver/setup.pyi`**（`simulation/` 相关还要看 `cst_solver/simulation/setup.pyi`）。Pylance 的补全完全依赖存根，漏改等于 API 对 IDE 不可见。
6. **重新生成文档（必做）**：跑 `python scripts/gen_cst_solver_docs.py`（产物 `docs/guides/api/cst_solver_api.html`；顺带维护 `mesh_grid` 时跑 `scripts/gen_mesh_docs.py`）。**不要手改生成的 HTML。**
7. **冒烟测试**：用**临时**模板工程（不要污染正式工程）建一个体 → `print(app.cst_file.get_messages())` 应为空 → `app.cst_file.model3d.Rebuild()` → 再读一次仍应为空 → `app.close()`。
8. **同步文档**：改动涉及公开 API / 硬约定 / 缺陷清单时，按 WORKFLOW §6 的同步矩阵更新 `docs/ARCHITECTURE.md`、本文件、对应 skill，并在修掉已知缺陷后删掉 `cst-solver-dev.md` 待修清单里的对应行。
9. **一个包一条 commit**（`feat(cst_solver): …` / `fix(cst_solver): …`），正文写清现象、改动、验证命令与兼容性影响，然后 push。

---

## 9. 相关文档

- 总体架构与包分工 → [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
- 自动生成的 API 速查（HTML）→ [`../guides/api/cst_solver_api.html`](../guides/api/cst_solver_api.html)
- 本包的开发规程（硬约定 + 待修清单）→ [`../../skills/developer/cst-solver-dev.md`](../../skills/developer/cst-solver-dev.md)
- 仓库开发宪法（流程 / 命名 / 文档同步 / 提交）→ [`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md)
- 后续阶段要做什么（计划索引）→ [`../next_plan/README.md`](../next_plan/README.md)
- 使用者视角（建模型、排错、验收）→ [`../../skills/user/tpc-usage.md`](../../skills/user/tpc-usage.md)
