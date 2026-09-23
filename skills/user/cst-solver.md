---
name: cst-solver
description: '**cst_solver 快速使用手册（使用者视角）** —— 常用 API 速查（开工程 / 参数 / 实体 / 布尔 / 变换 / 材料 / 端口 / 监视器 / 边界 / 求解 / 读结果），照抄即可，不必翻源码；不常用或不确定的 API 才按地图去查源码。含三条硬约定、CST 侧验收、**结构示意图的工程制图规范（Python+Matplotlib、中文显示入口、变量用 LaTeX）**、以及**疑似库 bug 的判定与报告流程（只报告，不修库）**。USE FOR: 直接用 cst_solver.setup / result 建模型、配仿真、读结果；想确认某个常用方法怎么调；**绘制结构示意图**；模型异常时区分「我用错了」还是「库有 bug」。DO NOT USE FOR: 拓扑光子晶体器件装配（超元胞/相/域壁）→ topo-quickstart.md；topo_modeler/topo_templates 的用法 → tpc-usage.md；修改 cst_solver 源码 / 新增封装 / 修 bug → developer/cst-solver-dev.md。'
---

# cst_solver 快速使用手册

> **本文件的定位**：`cst_solver` 是作者自己维护的库，封装层**确实可能有 bug**。
> 但最高频的 API 已经反复用过、是可靠的——这些**直接照抄本文件，不要每次再去翻底层**。
> 只有「不常用 / 本文件没覆盖 / 行为与预期不符」时，才按 §2 的地图去查源码。
>
> **铁律：发现疑似 bug，只报告，不修库**（流程见 §9）。修库由用户另外安排 AI 处理。

### 本 skill 在 TPC 中的位置（别选错文档）

**TPC 是整个库，`cst_solver` 只是其中领域最小的一个通用子包**，只负责把 CST VBA 封装成 Python
（开工程、画实体、配端口/求解、读结果），与研究方向无关。按任务落点选文档：

| 你要做的事 | 落在哪个包 | 读哪个 skill |
|---|---|---|
| 直接调 CST 通用建模 / 仿真 / 结果 API | `cst_solver` | **本文件** |
| 晶格坐标 / 路径 DSL | `mesh_grid` | `tri-grid.md` / `hex-grid.md` |
| 拓扑光子晶体器件（域壁/相/阵列/馈源）装配 | `topo_modeler` / `topo_templates` | `topo-quickstart.md`（不要在本文件找） |
| 端到端器件模板 / 服务 / MCP 全貌 | `topo_templates` / `tpc_service` | `tpc-usage.md` |

各 skill 只覆盖自己声明的子包：本文件**不讲** topo 器件的物理口径；topo skill 也不重复 VBA 封装细节。

---

## 0. 30 秒判断：这次要不要翻源码？

```
要做的事在本文件 §3「常用 API 速查」里吗？
├─ 在 → 直接照抄，不要翻源码
└─ 不在 / 有可选参数拿不准 / 行为与文档不符
        → ① 先查 cst_solver/setup.pyi（签名权威，纯存根、读起来便宜）
          ② 仍不确定 → 按 §2 地图读对应模块的函数体 + docstring
          ③ 源码显示封装本身有错（拼错 VBA / 调了不存在的方法 / 参数被丢弃）
               → 这是库 bug：按 §9 报告，不要自己改
```

**省 token 纪律**：禁止通读整包；签名一律先读 [`cst_solver/setup.pyi`](../../cst_solver/setup.pyi)；
定位实现用 grep，只读目标函数与其 docstring。

---

## 1. 导入与环境（已实测，放心用）

```python
from cst_solver import setup          # 建模 / 仿真主类（24 个 Mixin 聚合）
from cst_solver import result         # 离线读结果（= Result 类）
```

- 仓库已 `pip install -e .`，**禁止**再 `sys.path.append`。
- CST 安装路径走环境变量 `CST_INSTALL_PATH`；自定义配置走 `CST_CONFIG_FILE`。
- 只验证环境、不启动 CST：

  ```bash
  python -m cst_solver doctor --probe
  ```

- 一个 Python 进程只放一个 `setup` 实例；用完即 `close()`，关闭前先 `save()`。

---

## 2. 不常用 API 的查源码地图（任务 → 文件）

| 任务 | 文件（`cst_solver/` 下） |
|---|---|
| 任何 `app.xxx()` 的签名 / 参数类型 | **先读 `setup.pyi`** |
| 打开 / 关闭 / 保存工程 | `project.py` |
| 参数定义 / 读取 | `parameters.py` |
| 方块 / 圆柱 / 三角棱柱 / 球等基础体 | `modeling/primitives.py` |
| 折线 / 圆弧 / 椭圆 / 样条等曲线 | `modeling/curves.py` |
| 拉伸 / 放样 / 扫掠 / 封面 | `modeling/curves_ops.py` |
| 布尔（add/subtract/intersect/insert） | `modeling/booleans.py` |
| 平移 / 旋转 / 镜像 / 缩放 | `modeling/transforms.py` |
| 拾取点 / 边 / 面 | `modeling/picks.py`（面操作另有 `FaceOpsMixin`，在 `__init__.py`） |
| 材料定义 / 改色 / 材料库 | `material/materials.py` |
| 波导端口 / 离散端口 / 集总元件 / Floquet | `simulation/ports.py` |
| 激励源（平面波 / 电流端口等） | `simulation/sources.py` |
| 场监视器 / 探针 | `simulation/monitors.py` |
| 时域 / 频域 / 本征模 / 参数扫描 / 优化器 | `simulation/solver.py` |
| 边界 / 背景 / 层叠 | `simulation/boundary.py` |
| 网格属性 / 局部网格 | `mesh/mesh.py`（局部网格也可直接发 VBA，见 §7） |
| DXF / STEP / IGES / STL / 子工程导入 | `import_export/io.py` |
| 离线结果读取 | `_result_core.py` |

---

## 3. ⭐ 常用 API 速查（已反复验证，照抄即可）

> 只列**最常用的形态**；完整可选参数查 `setup.pyi`。所有几何尺寸与工作单位一致
> （默认 length=mm、frequency=GHz）。

### 3.1 工程生命周期

```python
app = setup('tmp.cst')                 # 打开/新建工程（相对路径按当前工作目录解析！）
# app = setup.attach()                 # 复用已开 CST（许可证紧张时用），可选 pid=/filename=
...
app.save(r'D:\out\device.cst', include_results=False)   # 始终显式给绝对路径最稳
app.close()                            # 旧名 project_close / close_project 也可用
```

`save()` 返回实际写出的绝对路径；无参 `save()` 已修（取当前工程路径），但仍建议显式传路径。

### 3.2 单位与参数

```python
app.set_units(frequency='GHz', length='mm')          # 一般默认即可
app.para('a', 0.2425)                    # 数值参数
app.para('l1', '0.65*a')                 # 表达式参数（字符串）
v = app.get_parameter('a')               # → float（表达式也返回求值后的数）；不存在 → KeyError
app.freq_limit(300, 380)                 # 频域监视器/求解器频率范围
```

⚠️ **`para()` 默认 `log_flag=0`**：写进参数表但不触发历史重建。
改完参数后几何/结果不刷新，多半是这个原因——重建靠后续几何操作或 `model3d.Rebuild()`。

### 3.3 基础实体

```python
app.square(xmin, xmax, ymin, ymax, zmin, zmax, 'box',
           component='component1', material='PEC')     # = Brick

app.cylinder(center=[0,0,0], r=[0.5], h=[0.2], name='rod',
             axis='z', material='PEC')

# 等边三角棱柱：a=边长，h=Z 向拉伸高度；center=最终平移中心[x,y,z]，theta=[绕x,y,z角度]
app.triangle(a, h, center=[x, y, z], theta=[0,0,0], name='tri1',
             curve='curve1', material='Silicon (lossy)')

app.hexagon(a, h, center=[x,y,z], theta=[0,0,0], name='hex1')   # a=外接圆半径，h=拉伸高
app.create_sphere(center=[0,0,0], radius=0.5, name='sph1')
```

**CCW 安全件**：`triangle()`/`hexagon()` 的底层多边形是 CCW（拉伸朝 +z），
center 给多少就平移到多少——**需要板底落在 z=0 时，自己把 center 的 z 给成 `h/2`**
（这两个函数内部不做 `-h/2`）。自己用 `polyline + extrude` 拼多边形时遵守 §4①。

### 3.4 曲线与拉伸

```python
app.polyline([[x1,y1,z1],[x2,y2,z2],...], name='p1', curve='curve1')  # → 返回名
app.arc(center=[0,0,0], p=[1,0,0], angle=90, name='a1')
app.ellipse(a=1.0, b=0.5, center=[0,0,0], name='e1')
app.create_circle(center=[0,0,0], r=0.3, name='c1')

app.extrude('curve1:p1', name='solid1', thickness=0.2,
            component='component1', material='Silicon (lossy)')
app.cover_curve('curve1:p1', name='cover1', component='component1', material='...')
```

### 3.5 布尔（语义见 §4②，调用本身放心用）

```python
app.add('A', 'B')            # A ∪ B，结果在 A，B 被删除
app.subtract('A', 'B')       # A − B，结果在 A，B 被删除（旧拼写 substract 保留）
app.insert('A', 'B')         # A − B，B 保留（用于多材料分层，不是并集！）
app.intersect('A', 'B')      # A ∩ B，结果留 A，B 被消耗
```

### 3.6 变换

```python
app.translate('A', [dx, dy, dz], copy=False, unite=False)
app.rotation('A', angle=[0, 0, 90], center=[0,0,0], copy=False, unite=False)
app.mirror('A', center=[0,0,0], plane=[1,0,0], copy=False, unite=False)   # 法向指定镜像面
```

需要复制阵列/对称件时：`copy=True`；复制后自动并回用 `unite=True`。

### 3.7 材料

```python
app.new_material('Silicon (lossy)')
app.create_material_custom('Si_custom', epsilon=11.9, mu=1.0, kappa=0.0,
                           tand=None, material_type='Normal', color=[0.3,0.3,0.8])
app.change_material('component1:solid1', 'Silicon (lossy)')
app.list_library_materials()
```

⚠️ 改材料颜色用 `create_material_custom(color=...)` 或 `change_material_color`；
离线核验时在 `Model.mif` 里搜 `.Color`（不是 `.Colour`）。
材料定义失败（库文件缺失等）历史上是**静默**的，以 §6 的正向验收为准。

### 3.8 端口（2026-09-20 起有朝向守卫）

```python
# 必须先拾取端口面（add_port 的 VBA 用 .Coordinates "Picks"），再建端口。
app.pick_face_at('box', -5, 0, 0)
# orientation 只接受位置枚举，不能再写 positive/negative
app.add_port(id_val, orientation='xmin',                 # xmin/xmax/ymin/ymax/zmin/zmax
             number_of_modes=2, reference_plane_distance='0')

app.create_waveguide_port_free(id_val, xrange=[...], yrange=[...], zrange=[...],
                               orientation='xmax')
app.create_discrete_port(id_val, p1=[...], p2=[...], impedance=50)
app.create_floquet_port(id_val, number_of_modes=2)
```

⚠️ `orientation` 非法（含旧写法 `'positive'`）现在**当场 ValueError**；
传 `None` 则不下发朝向行（用于完全可控的手动场景）。**不要依赖默认朝向**，显式传枚举。

### 3.9 监视器 / 边界 / 求解

```python
app.define_monitor('E', [314.0])                 # 也可传频点列表
app.boundary(xmax='expanded open', xmin='expanded open',
             ymax='expanded open', ymin='expanded open',
             zmax='expanded open', zmin='expanded open')

app.T_solver()                  # 选时域求解器
# app.configure_time_solver()
app.set_steady_state_limit(db='-50')
report = app.run_checked(note='device run 1')     # → dict：status/errors/evidence
app.save(..., include_results=True)
```

`run_checked()` 的 `status` 只有 `succeeded / failed / unverified`：
**`unverified` 不能当成功**。succeeded 需要「无错误消息 + 正常终止 + 结果可读 + 指纹一致」同时成立。

### 3.10 离线读结果（不需要 DE / 许可证）

```python
res = result(r'D:\out\device.cst')           # 打不开 → RuntimeError，消息带处置建议
print(res.get_available_results())           # 先看结果树真实路径
s21 = res.read_s_parameter('S2,1')           # → ndarray (n,2)：[频率, 复S]
s11 = res.read_1D(r'S-Parameters\S1,1')      # 完整/相对路径都接受
all_s = res.read_all_s_parameters()          # → {'S1,1': ndarray, ...}；缺项见 res.last_errors
path = res.export_s_parameters_csv('s.csv')  # dB 口径，返回绝对路径
run_ids = res.get_run_ids(r'S-Parameters\S1,1')
```

口径：频率 GHz；`read_s_parameter` 返回的是**复数 S 值**，要 dB 自己 `20*np.log10(np.abs(s))`；
零幅度对应 −300 dB。`run_id=0` = 最新/最终结果别名。

远场 CSV：**离线 `Result.export_farfield_csv` 已废弃（抛 NotImplementedError）**，
正确路径是 `setup.attach().export_farfield_csv(tree_item, save_path)`（经 DE 导出 θ/φ 长表）。

---

## 4. 三条硬约定（违反必出几何/物理错误）

1. **z 平面与绕向**：自己写闭合多边形时一律给 **CCW**（有向面积 > 0），
   实体内部 `translate(name, [0,0,-h/2])`。`ExtrudeCurve` 沿法向拉伸：
   **CCW → +z，CW → −z**。绕向错 → 实体间在 z 上差一个 h，
   布尔求交得**空集且 CST 不报错**。
   （topo builders 已内置 `-h/2`；但 `triangle()`/`hexagon()` 只平移到你给的 center，不做 `-h/2`。）
2. **布尔语义**：

   | 操作 | 结果落点 | B 的命运 |
   |---|---|---|
   | add / subtract | A | **删除** |
   | intersect | A | **消耗** |
   | **insert** | A（= A−B） | **保留 B**（不是并集！） |

3. **阵列/覆盖范围**：宽板上铺孔/端口时，覆盖范围必须按真实基板尺寸显式给，
   不能只按路径（`get_array_range()` 只够细长直波导）；范围必须写成 **CST 参数表达式**。

---

## 5. 高频症状速查（先排除「用错」，再怀疑库）

| 症状 | 最可能原因 | 处理 |
|---|---|---|
| `Shape does not exist` | 实体已被布尔消耗 / 求交为空 / 还在排队 | 检查布尔顺序与绕向（§4） |
| 改参数后模型不变 | `para(log_flag=0)` 未重建 | `model3d.Rebuild()` 或确认后续有几何操作 |
| 端口报错或 S 参数方向怪 | orientation 写错/没写 | 显式传 `xmin/xmax/...`（§3.8） |
| 布尔后某个实体消失 | 忘了 B 会被消耗/删除 | 用 `insert` 保 B，或先 `copy=True` |
| 脚本报找不到工程 | 相对路径按 cwd 解析 | 用绝对路径；不存在 → FileNotFoundError、给了目录 → IsADirectoryError |
| `cst_unavailable` / unverified | 没连上 CST 或无法确认成功 | **不能当成功**；连真机重跑 |
| `Invalid number of repetitions` | 阵列参数整数化后为 0（如 `int(ydn/2)`） | 保证范围参数 ≥ 1 |

注意：`add_to_history` 通道里，一部分错误会直接抛 RuntimeError（带 CST 原文）；
另一部分只是**写进消息**。所以**每一步之后都要读消息**（§6）。

---

## 6. CST 侧验收（每次交付必做）

```python
print(app.get_messages())            # 读后即清空；必须为 []
app.cst_file.model3d.Rebuild()       # 阻塞式重放全部历史，最能暴露问题
print(app.get_messages())            # 必须为 []
print(app.get_picked_count('face'))  # 拾取类操作的正向判据（== 期望数）
```

- **CST 不抛异常**：库不保证把 CST 错误转成 Python 异常，「跑通」≠「建对」。
- 脏工程里旧的失败消息会反复出现；以**正向信号**为准（实体存在、拾取计数、结果可读）。
- 磁盘核验：`Model/3D/ModelHistory.json`、`Model/Parameters.json`。
- 最终交付：重启 kernel 从头跑一遍；禁止硬编码数值（走 CST 参数）；清理临时工程与脚本。

---

## 7. 库内没有封装、但可直接发 VBA 的常用操作

`add_to_history` 是唯一执行通道。以下两条常用能力库内**没有方法**，直接发 VBA 不算「改库」：

```python
# ① 实体局部网格步长（0 = 该方向不限制）；实体名必须是 component1:name 全名
app.cst_file.model3d.add_to_history(
    "SetMeshStepWidth",
    'Solid.SetMeshStepWidth "component1:my_solid","0","0","0.004"')

# ② 参数扫描：任意离散点（一 sequence 挂多参数 = 全组合）
app.cst_file.model3d.add_to_history(
    "ParameterSweep",
    'With ParameterSweep\n'
    ' .AddParameter_ArbitraryPoints "sweep1", "angle", "0;15;30;50"\n'
    'End With\n'
    'ParameterSweep.Start')
```

注：`simulation/solver.py` 也有 `configure_parameter_sweep / add_sweep_parameter_samples /
start_parameter_sweep` 封装（线性等步），需要时查 `setup.pyi` 后使用。

---

## 8. 绘制结构示意图（被要求画示意图时必须遵守）

当用户要求**绘制结构示意图**（器件 / 几何结构的说明图，不是仿真结果曲线）时：

### 8.1 工具与标准

- **必须用 Python + Matplotlib 程序化绘制**（可结合 numpy 计算几何顶点），
  不要手画、不要用截图、不要用 PPT/画图。
- 按**工程制图标准**出图，至少做到：

  1. **线型有语义**：可见轮廓 = 实线；被遮挡轮廓 = 虚线（`linestyle='--'`）；
     对称/回转中心 = 点划线（`'-. '`）；尺寸/引出线 = 细实线。
  2. **尺寸标注完整**：尺寸线 + 两端箭头（`arrowprops` / `annotate`）+ 尺寸界线（extension line），
     数字写在尺寸线上方/中断处，不重复、不遗漏关键尺寸。
  3. **视图选择**：平面结构用正视（俯视）图按真实比例；需要表达厚度/层次时加截面图或轴测图，
     并注明视角；`ax.set_aspect('equal')` 保证不变形。
  4. **标注不压图**：文字/箭头不与轮廓线重叠；引线从标注对象指向文字；
     必要时局部放大（inset）。
  5. 介质 / 材料区域用**剖面线或淡色填充**区分（`hatch` / 低饱和 `facecolor`），
     PEC/金属用实填充或斜线，并配图例。
  6. 出图给 **PNG（`dpi≥180`）+ 矢量 PDF/SVG**，`bbox_inches='tight'`。

### 8.2 中文显示（本仓库有专门入口，必须走它）

- **必须**用 `mesh_grid.plotting.chinese_plot_style()`（上下文，推荐）或
  `configure_chinese_font(strict=True)`（notebook 全局），
  详见 [`../../docs/guides/chinese_plotting.md`](../../docs/guides/chinese_plotting.md)。
- **禁止**写死 `SimHei` / `Microsoft YaHei`（换机不一定有）；**禁止**屏蔽
  Glyph missing 警告；正式导出 `strict=True`，缺字直接失败而不是出豆腐块。
- 负刻度交给该入口处理（U+2212 缺字问题）；批处理先 `matplotlib.use('Agg')` 再 import pyplot。

```python
import matplotlib
matplotlib.use('Agg')                       # 仅无界面批处理需要，且必须在 pyplot 前
import matplotlib.pyplot as plt
from mesh_grid.plotting import chinese_plot_style

with chinese_plot_style(text='波导 端口 基板 长度', strict=True):
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.set_aspect('equal')
    # …绘制轮廓 / 虚线隐藏线 / 尺寸标注…
    ax.set_xlabel('x (mm)'); ax.set_ylabel('y (mm)')
    fig.tight_layout()
    fig.savefig('structure.png', dpi=200, bbox_inches='tight')
    fig.savefig('structure.pdf', bbox_inches='tight')
    plt.close(fig)
```

### 8.3 变量标注一律用 LaTeX（mathtext）

- 图中出现的**变量 / 物理量一律写成 LaTeX 数学格式**：用 Matplotlib 的 mathtext `$...$`，
  **不需要系统装 LaTeX**。例如：`r'$a$'`、`r'$l_1$'`、`r'$h$'`、`r'$\theta$'`、
  `r'$d_{\rm sub}$'`、`r'$f_0$'`、`r'$\lambda$'`。
- 下标/希腊字母/单位符号都走 mathtext；**中文说明文字留在 `$...$` 外面**
  （如 `r'晶格常数 $a$ (mm)'`），不要把中文塞进数学环境。
- 单位与数字用正体：变量斜体、下标里的文字标签用 `\mathrm{}` / `\rm`（如 `r'$E_{\rm z}$'`）。

---

## 9. ⭐ 疑似库 bug 的判定与报告流程（只报告，不修库）

### 9.1 什么才算「库 bug」（先排除用法问题）

按以下顺序自查，**全部排除**后再报告：

1. 本文件 §3 的用法是否照对了？（尤其三条硬约定、orientation、log_flag）
2. `setup.pyi` 里该方法的真实签名/参数名是否一致？——参数名拼错、传了不存在的 kwarg 是用法问题。
3. CST 消息与行为是否可复现？换一个干净工程、最小复现是否仍错？
4. 读对应模块源码：VBA 模板/参数映射是否真的有问题？

**库 bug 的典型形态**（读到源码即可坐实）：

- 调用了 `model3d` 上**不存在的方法**（`Model3D` 动态代理，写错名不抛 AttributeError，真机才炸）；
- VBA 模板拼错/缺行，或某个 Python 参数**收下了却从不下发**（如历史上的 `pattern_export(step=)`）；
- 下发了 CST 对象**没有的成员**，被静默忽略（如历史上的 `Background.Material`）；
- 默认值非法且被 CST 静默回退（如历史上 orientation 默认 `'positive'`）。

### 9.2 报告，不修

🔴 **禁止修改 `cst_solver/` 下任何源码、`setup.pyi`、VBA 模板来「顺手修一下」**。
用户会找专门的 AI 按开发流程修复。可以做的是：**用现有 API 绕开**（§7 的直发 VBA、
换相邻 API、在自己的脚本里规避），并把问题报告清楚。

### 9.3 报告格式（交给用户 / 录入待修清单）

向用户输出一份结构化报告，包含：

1. **标题**：一句话说明哪个方法出什么问题；
2. **环境**：CST 版本、Python 版本、库的 commit（`git rev-parse HEAD`）；
3. **最小复现**：可直接运行的最短脚本 + 输入；
4. **预期 vs 实际**：实际报错原文（**逐字保留**）/ 静默错误的观察证据；
5. **源码定位**：文件与行号、问题行（如 VBA 模板里具体哪一行）；
6. **当前绕过方案**：你在本次任务里用了什么替代写法；
7. **建议修法**（可选，供修复 AI 参考，不要自己动手）。

随后把这条 bug **追加到开发者技能的「待修清单」**
（[`../developer/cst-solver-dev.md`](../developer/cst-solver-dev.md) §待修清单；
该清单 2026-09-20 曾清空为 0 项，新报告即重新登记），
并提醒用户：修完后按 `developer/WORKFLOW.md` 规则删掉对应行。
**除该待修清单登记外，不动任何库文件。**

---

## 相关文档

- 拓扑光子晶体器件（域壁/相/阵列）装配 → [`topo-quickstart.md`](./topo-quickstart.md)
- 建模引擎 / 模板层 / MCP / 服务的完整使用手册 → [`tpc-usage.md`](./tpc-usage.md)
- 三角晶格 / 六边形晶格速查 → [`tri-grid.md`](./tri-grid.md)、[`hex-grid.md`](./hex-grid.md)
- 要改库源码 / 新增封装 → [`../developer/cst-solver-dev.md`](../developer/cst-solver-dev.md)
  + [`../developer/WORKFLOW.md`](../developer/WORKFLOW.md)
- API 参考（HTML）→ [`../../docs/guides/api/cst_solver_api.html`](../../docs/guides/api/cst_solver_api.html)
