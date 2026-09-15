# topo_modeler 使用技能（使用者视角）

> **场景**：用 TPC 把拓扑光子晶体器件建出来。**只调用现成 API，不改库源码。**
> 要改库 → 去 [`../developer/WORKFLOW.md`](../developer/WORKFLOW.md)。
> 包的设计细节 → [`../../docs/packages/topo_modeler.md`](../../docs/packages/topo_modeler.md)。
> 最后更新：见 git log。

---

## 0. 三十秒上手

```python
from templates import StraightWaveguide        # 模板层：一个类 = 一个器件

wg = StraightWaveguide(topology='AB', length=18, output_path=r'D:\out\wg.cst')
wg.preview()      # matplotlib 预览路径
wg.build_all()    # 参数 → 基板 → VPC → 晶体 → 馈源 → 波导 → 端口 → 求解器
wg.save()         # 保存 .cst
```

**前提**：仓库已 `pip install -e .`，且 `cst_solver/config.py` 里配好了 `CST_INSTALL_PATH`。
模板文件 `tmp.cst` 必须位于**当前工作目录**（`setup` 用相对路径打开它）。

---

## 1. 三层用法，按需选择

| 层次 | 入口 | 什么时候用 | 代价 |
|---|---|---|---|
| **① 模板层** | `templates.StraightWaveguide` / `UnitAntenna` | 建的就是这两种标准器件，只想填参数 | 器件形状被模板限定 |
| **② Modeler 层** | `topo_modeler.TopoModeler` + `TopoPath` | 器件形状自定义，但仍想用标准流水线 | 要自己写路径与参数 |
| **③ Builder 层** | `topo_modeler.builders.*` | 只要一两个部件，或要插进自己的流程 | 全都要自己编排 |

三层是**叠加**而非互斥：模板内部就是 Modeler，Modeler 内部就是 builders。

---

## 2. ① 模板层

### `StraightWaveguide`（拓扑光子晶体直波导）

```python
from templates import StraightWaveguide

wg = StraightWaveguide(
    topology='AB',           # 'AB' 或 'BA'
    length=18,               # 波导长度（晶格数）
    lattice_constant=0.2425, # 晶格常数 a (mm)
    height=0.25,             # 硅片厚度 h (mm)
    large_hole_ratio=0.65,   # 大孔比例（l1 = 比例 × a）
    small_hole_ratio=0.35,   # 小孔比例（l2 = 比例 × a）
    feed_type='ab_elliptical',
    freq_range=(300, 380),   # GHz
    monitors=('E',),
    feed_width=...,          # 见源码签名；feed / waveguide 尺寸默认值取自参考模型
    output_path=r'D:\out\wg.cst',
)
wg.preview(); wg.build_all(); wg.save()
```

内部做的事（8 步）：构建路径 → 定义 CST 参数 → 基板 → VPC 区域 → 光子晶体阵列
→ 馈源 → 空心波导 → **镜像到右端** → 2 个端口 → 整合 → 求解器。

### `UnitAntenna`（单元天线）

```python
from templates import UnitAntenna

ant = UnitAntenna(
    bend_angle=120,          # 拐弯角度（60 的倍数；0 = 直波导型）
    straight_length=18,      # 直段长度（晶格数）
    arm_length=14,           # 臂长（拐弯后长度，晶格数）
    topology='BA',           # 天线默认 BA
    radiator=None,           # None 或 'cylinder'
    radiator_radius=0.3,     # 圆柱辐射体半径 (mm)
    monitors=('E', 'Farfield'),
    output_path=r'D:\out\ant.cst',
)
ant.preview(); ant.build_all(); ant.save()
```

> ⚠️ **模板类目前有已知限制**：端到端 `build_all()` 的验收（与参考工程对比几何）
> 尚在进行中；`run()` 需要 CST 环境。详见
> [`../../docs/next_plan/stages/04_阶段4_验收与缺陷清账.md`](../../docs/next_plan/stages/04_阶段4_验收与缺陷清账.md)。

---

## 3. ② Modeler 层（自定义形状 + 标准流水线）

```python
from mesh_grid.tri_grid import TopoPath
from topo_modeler import TopoModeler

# 1) 用 DSL 描述路径（唯一数据源是三角晶格坐标 (r, c)）
path = (TopoPath.builder(a=0.2425, name='p')
        .start(0, -1)
        .move(19, 'c')
        .turn(120)
        .move(15, 'along')
        .build())

# 2) 交给 Modeler，它会自动推断
modeler = TopoModeler(template_cst='tmp.cst')   # 相对路径 → 按当前工作目录解析
modeler.set_path(path)
modeler.set_topology('BA')          # 可选，覆盖自动推断
modeler.set_parameters({'a': 0.2425, 'h': 0.25, 'l1': 0.157625, 'l2': 0.084875})

# 3) 分步构建（或直接 build_all()）
modeler.build_substrate()
modeler.build_vpc_regions()
modeler.build_crystal()
modeler.build_feed(feed_type='ba_tapered')
modeler.build_waveguide()
modeler.add_ports()
modeler.configure_solver(freq_range=(300, 380))
modeler.save(r'D:\out\custom.cst')
```

### 自动推断规则（路径说了算）

| 路径特征 | `model_type` | `topology` | `monitors` | 端口数 | `feed_type` |
|---|---|---|---|---|---|
| 直线（≤2 个晶格点） | `waveguide` | `AB` | `('E',)` | 2 | `ab_elliptical` |
| 有拐弯（>2 个点） | `antenna` | `BA` | `('E','Farfield')` | 1 | `ba_tapered` |

推断结果都能用 `set_topology()` / `set_parameters()` 显式覆盖。

### `TopoPath` 路径 DSL 要点

```python
path.xy                       # 直角坐标 (N,2) numpy 数组
path.lattice                  # 数值晶格坐标
path.lattice_symbolic         # 原始（可能含符号）坐标
path.has_symbols              # 是否含符号步数
path.get_array_range()        # (xup, yup, ydn) 阵列范围
path.get_bounding_box()       # (xmin, xmax, ymin, ymax)
path.auto_define_cst_params(app, prefix='p')   # 在 CST 中定义 p1x,p1y,...
path.preview(ax=None, show_grid=True)          # matplotlib 预览
```

**符号坐标**（让路径长度成为 CST 里可调参数）：

```python
path = (TopoPath.builder(a=0.2425)
        .start(0, 0).move('x1', 'c').turn(120).move('y1', 'along')
        .build(param_values={'x1': 18, 'y1': 14}))
path.auto_define_cst_params(app)     # 生成 px2='x1*a' 之类
```

> ⚠️ 符号路径的 `xy` / `lattice` / `get_bounding_box()` / `get_array_range()`
> **必须先给 `param_values`**，否则抛 `RuntimeError`。

---

## 4. ③ Builder 层（完全控制）

```python
from topo_modeler.builders import (
    build_substrate, build_vpc_regions, build_topological_crystal,
    build_feed, build_waveguide,
    add_waveguide_port, add_ports_for_straight_waveguide, add_port_for_antenna,
    configure_solver,
)

build_substrate(app, path, name='my_sub')
vpca, vpcb = build_vpc_regions(app, path)          # 返回 'vpc_A' / 'vpc_B'
ca, cb = build_topological_crystal(app, path, topology='AB',
                                   xup=26, yup=15, ydn=1)   # 显式覆盖阵列范围
build_feed(app, feed_type='ab_elliptical', name='my_feed')
build_waveguide(app, name='my_wg')
add_ports_for_straight_waveguide(app, waveguide_name='my_wg')
configure_solver(app, freq_range=(300, 380), monitors=('E',))
```

**builders 全是无状态函数**，可以脱离 `TopoModeler` 单独调用 —— 这是刻意的设计。

### 关键参数说明

| 函数 | 容易踩的点 |
|---|---|
| `build_substrate` | 沿路径上下各扩展 `y_margin`（默认 `'e2'`） |
| `build_vpc_regions` | **不接受 `topology`**；AB/BA 的大孔小孔分配在 `build_topological_crystal` 里 |
| `build_topological_crystal` | `xup/yup/ydn` 为 `None` 时才用 `path.get_array_range()` 自动推断；宽基板要显式给 |
| `build_feed` | `feed_type`：`'ab_elliptical'`（直波导）/ `'ba_tapered'`（天线）/ `'cylinder'`（辐射体） |
| `configure_solver` | `calculation_type` 可选 `'TD-S'`/`'FD-S'`/`'EIGENMODE'`/`'IE-S'`/`'ASYMPTOTIC'`，其它值抛 `ValueError` |
| `add_ports_for_straight_waveguide` | 面编号 `'10'`/`'22'` 是**硬编码**的 CST 内部编号，改波导尺寸后可能指错面 |

---

## 5. 三条硬约定（违反必出问题）

1. **z 平面**：所有多边形必须 **CCW**（有向面积 > 0），配合内部 `translate -h/2`。
   `ExtrudeCurve` 沿多边形**法向**拉伸：**CCW → +z，CW → −z**。
   绕向错了 → 实体在 z 上差一个 `h` → 布尔求交得**空集且 CST 不报错**。
   （`TopoPath` 的两个多边形方法已保证 CCW，并有单测钉住。）
2. **布尔语义**：`Intersect "A","B"` → 结果留 **A**、B 被消耗；
   `Add/Subtract "A","B"` → 结果在 A、**B 被删除**；`Insert` 保留 B 供继续引用。
3. **阵列范围**：`xup/yup/ydn` 必须覆盖**整个基板**，不能只按路径长度推断。

### 命名约定（AB/BA 的孔分配）

本库把 `l1` 固定为**大孔**、`l2` 固定为**小孔**；参考 notebook 里的 `l1` 则是 VPC-A 的**朝上孔**
（AB 时 `l1 = 0.35a` 是小孔）。两者是**命名错位**，分配方向由 `build_topological_crystal`
的 AB/BA 分支负责对齐，并已按参考工程的 `ModelHistory.json` 核实。

> **不要**在没对照参考工程的情况下「顺手改正」这两处分支 —— 看着反，实际是对的。

---

## 6. 验收（必做）

```python
print(app.cst_file.get_messages())     # 必须为空
app.cst_file.model3d.Rebuild()         # 阻塞式重放历史，最能暴露问题
print(app.cst_file.get_messages())     # 必须为空
```

**CST 不抛异常**，跑通 ≠ 建模正确。完整验收清单见
[`tpc-usage.md`](./tpc-usage.md) 与 [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) §6。

---

## 7. 报错定位

| 现象 | 原因 | 处理 |
|---|---|---|
| `FileNotFoundError: tmp.cst` | 模板不在当前工作目录 | 把 `tmp.cst` 放到 notebook 同目录，或传绝对路径 |
| `ModuleNotFoundError: No module named 'cst'` | 未配 CST 路径 | 复制 `cst_solver/config_template.py` 为 `config.py`，改 `CST_INSTALL_PATH` |
| `RuntimeError: 符号路径无法…` | 符号路径没给 `param_values` | `.build(param_values={'x1': 18, ...})` |
| `ValueError: topology 必须是…` | 传了 `'ab'` / `'BA '` 之类 | 严格用 `'AB'` 或 `'BA'` |
| `ValueError: side 必须是…` | `build_vpc_area_polygon(side=...)` 传错 | 只能 `'upper'` / `'lower'` |
| `ValueError: 不支持的 calculation_type` | 求解器类型写错 | 用 §4 列出的 5 个取值 |
| 布尔运算「成功」但结果是空集 | z 平面/绕向不对，或阵列范围没覆盖 | 查 §5 三条硬约定 |
| `AttributeError: 'TopoModeler' object has no attribute ...` | 调了阶段 4/5 才实现的方法 | `build_lens` / `read_results` / `plot_results` 目前会抛 `NotImplementedError` |

---

## 8. 相关文档

- 主使用手册（报错定位表、已知库缺陷、验收清单）→ [`tpc-usage.md`](./tpc-usage.md)
- 三角晶格 / 路径 DSL 细节 → [`tri-grid.md`](./tri-grid.md)
- 六边形晶格 / DXF → [`hex-grid.md`](./hex-grid.md)
- 包设计与完整 API → [`../../docs/packages/topo_modeler.md`](../../docs/packages/topo_modeler.md)
- 阶段 0-3 详细指南 → [`../../docs/guides/topo_modeler_guide_stage0-3.md`](../../docs/guides/topo_modeler_guide_stage0-3.md)
- 后续计划与阻塞项 → [`../../docs/next_plan/README.md`](../../docs/next_plan/README.md)
