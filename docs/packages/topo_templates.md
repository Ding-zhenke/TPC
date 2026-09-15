# topo_templates —— 端到端模板层

`topo_templates/` 是 TPC 分层架构的**第 4 层（应用层）**，核心约定只有一条：**一个类 = 一个器件**。
类内部把「晶格路径 → CST 参数 → 基板 → VPC 区域 → 光子晶体阵列 → 馈源 → 波导 → 镜像 → 端口 → 布尔整合 → 求解器」
这条流水线一次性编排完毕；用户只需要在构造函数里填物理参数，然后调 3~4 个方法就能拿到一个可仿真的 `.cst` 工程。

模板层**自己不做几何推导**：所有坐标、边界框、阵列范围、多边形顶点都来自
`mesh_grid.tri_grid.TopoPath`；所有实体/布尔/端口/求解器操作都来自 `topo_modeler.builders.*`。
模板层只负责两件事：**顺序**（先建什么后建什么）和**器件特有的额外步骤**
（例如直波导要把馈源和波导镜像到另一端、单元天线要挂一个圆柱辐射体）。

| 项 | 内容 |
|---|---|
| **职责** | 把「某个具体器件的完整建模流程」固化成可复用、可参数化的类，实现一键端到端建模 |
| **需要 CST** | ✅ 必须。构造函数里就会 `TopoModeler(template_cst='tmp.cst')` 打开模板工程 |
| **入口** | `from topo_templates import StraightWaveguide, UnitAntenna` |
| **依赖** | `topo_modeler`（`TopoModeler` / `NameManager` / `builders.*`）、`mesh_grid.tri_grid.TopoPath`；间接依赖 `cst_solver` |
| **被谁依赖** | 库内**没有任何其它包依赖它**（全仓库 `from topo_templates` 只命中模板自身）；只有用户 notebook / 脚本使用 |
| **源码位置** | `topo_templates/__init__.py`、`topo_templates/straight_waveguide.py`、`topo_templates/unit_antenna.py` |
| **公开 API** | AST 统计：**2 个类、0 个模块级函数**；两个类各有 **4 个公开方法**：`preview` / `build_all` / `save` / `run` |
| **当前阶段** | 阶段 3（基础模板层）已完成；透镜模板属阶段 4，**尚未实现**（见 §6.3） |

---

## 1. 它解决什么问题

旧 notebook 里每建一个器件，都要手写一遍同样的东西：

1. 手算 `px1,py1 … px6,py6` 等路径点参数（10+ 行）；
2. 手推 `xmax / ymax_up / ymax_dn / xup / yup / ydn` 阵列范围；
3. 手写基板、VPC-A/B 区域的多边形顶点列表；
4. 手抄一整段光子晶体超元胞的「画孔 → 阵列复制 → 布尔」序列；
5. 手抄馈源、波导、端口、镜像、布尔整合、求解器配置的调用顺序。

同一类器件的每次新设计都要把这些复制一遍，任何一个环节抄错都会导致
「几何看起来对、布尔结果却是空集」这类不报错的故障。

模板层把这一整套压缩成：

```python
from topo_templates import StraightWaveguide

wg = StraightWaveguide(topology='AB', length=18, output_path=r'D:\out\wg.cst')
wg.preview()      # matplotlib 看一眼路径
wg.build_all()    # 一键建模
wg.save()         # 保存 .cst
# wg.run()        # 需要时再跑仿真
```

**约 200 行 notebook 代码 → 约 10 行**（对比见
[`../guides/topo_modeler_guide_stage0-3.md`](../guides/topo_modeler_guide_stage0-3.md) §4.4）。

模板层保留给用户的自由度只有**构造参数**；一旦参数超出模板的能力范围（换器件形态、
换馈源拓扑、需要局部加密的阵列范围），就应该下移到 Modeler 层或 Builder 层，见 §5。

---

## 2. 两个模板总览

| 维度 | `StraightWaveguide` | `UnitAntenna` |
|---|---|---|
| 器件 | 拓扑光子晶体**直波导** | **单元天线**（直段 + 拐弯 + 臂，可选辐射体） |
| 源文件 | `topo_templates/straight_waveguide.py` | `topo_templates/unit_antenna.py` |
| 内部路径 | `.start(0, -1).move(length+1, 'c')` → `[(0,-1), (0,length)]` | `.start(0, -1).move(straight_length+1, 'c')`；`bend_angle != 0` 时再加 `.turn(...).move(arm_length+1, 'along')` |
| 默认拓扑 | `'AB'` | `'BA'` |
| 默认馈源 | `'ab_elliptical'`（实体名 `feed1`） | `'ba_tapered'`（实体名 `feed2`） |
| 端口 | **2 个**（入口面 `'10'` + 出口面 `'22'`） | **1 个**（入口面 `'10'`） |
| 默认监视器 | `('E',)` | `('E', 'Farfield')` |
| 镜像步骤 | 有：feed + waveguide 镜像到右端（中心 `p2x/2`） | 无 |
| 辐射体 | 无 | 可选 `radiator='cylinder'`（圆柱，位于路径末端） |
| 额外校验 | `topology ∈ {'AB','BA'}` | 同上 + `bend_angle` 必须是 60 的整数倍 |
| 典型旧代码 | `AB_feed.ipynb` / `BA_feed.ipynb` | `Ant1_D_BA_120D` / `Ant3_epc` 等 |

两个模板的类接口完全一致，都是这 4 个公开方法：

| 方法 | 签名 | 说明 |
|---|---|---|
| `preview` | `preview(ax=None, show_grid=True)` | 委托 `TopoPath.preview()`，画路径 + 晶格背景，返回 `(fig, ax)` |
| `build_all` | `build_all()` | 端到端建模，返回 `self`（可链式） |
| `save` | `save(output_path=None)` | 保存 `.cst`；未建模则先自动 `build_all()`；返回实际保存路径 |
| `run` | `run()` | 运行仿真；未建模则先自动 `build_all()`；返回 `self` |

> `save()` / `run()` 里的 `build_all()` 是**幂等保护**（靠 `self._built` 标记），
> 所以下面的写法都合法：`wg.build_all(); wg.save()` 或直接 `wg.save()`。

---

## 3. StraightWaveguide

源码：`topo_templates/straight_waveguide.py`（224 行）。

### 3.1 构造参数

`StraightWaveguide.__init__`（`straight_waveguide.py:62`）：

```python
StraightWaveguide(topology='AB', length=18, width=14,
                  lattice_constant=0.2425, height=0.25,
                  large_hole_ratio=0.65, small_hole_ratio=0.35,
                  feed_type='ab_elliptical',
                  freq_range=(300, 380), monitors=('E',),
                  template_cst='tmp.cst', output_path=None)
```

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `topology` | `str` | `'AB'` | 拓扑相，只能是 `'AB'` 或 `'BA'`，否则 `ValueError` |
| `length` | `int` | `18` | 波导长度（晶格数，不含起点偏移） |
| `width` | `int` | `14` | 波导宽度（**预留**，当前仅存进 `self.width`，实际宽度由 VPC 区域与路径决定） |
| `lattice_constant` | `float` | `0.2425` | 晶格常数 `a`（mm），存为 `self.a` |
| `height` | `float` | `0.25` | 硅片厚度 `h`（mm） |
| `large_hole_ratio` | `float` | `0.65` | 大孔比例，`self.l1 = large_hole_ratio * a` |
| `small_hole_ratio` | `float` | `0.35` | 小孔比例，`self.l2 = small_hole_ratio * a` |
| `feed_type` | `str` | `'ab_elliptical'` | 馈源类型，透传给 `build_feed()`；可选 `'ab_elliptical'` / `'ba_tapered'` / `'cylinder'` |
| `freq_range` | `tuple` | `(300, 380)` | 频率范围 `(fmin, fmax)`，GHz |
| `monitors` | `tuple` | `('E',)` | 监视器类型，可选 `'E'` / `'H'` / `'Farfield'` / `'Powerflow'` |
| `template_cst` | `str` | `'tmp.cst'` | CST 模板工程路径；**相对路径按当前工作目录解析**，模板文件必须放在 notebook 同目录 |
| `output_path` | `str` | `None` | 输出 `.cst` 路径；也可以留 `None`，改在 `save(path)` 时再给 |

### 3.2 内部流程

`__init__` 只做「建路径 + 建 Modeler + 定义参数值」三件事，真正的建模全在 `build_all()`：

**构造期（`straight_waveguide.py:62-111`）**

1. 校验 `topology`；
2. 由 `lattice_constant` 派生 `l1/l2`，并算出三角晶格几何参数
   `self.e1 = a/2`、`self.e2 = a*sqrt(3)/2`；
3. 构建路径：`TopoPath.builder(self.a, name='p').start(0, -1).move(length+1, 'c').build()`
   → 晶格点 `[(0,-1), (0,length)]`；
4. `self.xup, self.yup, self.ydn = self.path.get_array_range()` 自动推导阵列范围；
5. 建 `TopoModeler(template_cst=...)`，`set_path(path)`（自动推断 `model_type`），再把
   `a/h/l1/l2/e1/e2` 通过 `set_parameters({...})` 写进 CST 参数表；
6. 保存 `self.app`（= `modeler.app`）与 `self.nm = NameManager()`，`self._built = False`。

**建模期 `build_all()`（`straight_waveguide.py:156-200`）**

1. `self._define_all_params()` —— 定义全部 CST 参数：
   基础 `a/h/l1/l2/e1/e2`；路径点 `self.path.auto_define_cst_params(app, prefix='p')`（生成 `p1x,p1y,…`）；
   阵列范围 `xup/yup/ydn`；feed 参数 `x0=1, wf1=0.5, lf1=0.5, lf2=0.3, lf3=5.0`；
   波导参数 `wg_a=0.5, wg_b=0.25, wg_t=0.02`；
2. `build_substrate(app, self.path, name='substrate')` —— 基板（其余参数用构建器默认值 `height='h'`、`material='Silicon (lossy)'`、`y_margin='e2'`）；
3. `build_vpc_regions(app, self.path, topology=self.topology)` —— VPC-A / VPC-B 区域
   ⚠️ **此调用当前必然 `TypeError`**，见 §6.1；
4. `build_topological_crystal(app, self.path, topology=self.topology, xup=..., yup=..., ydn=...)`
   —— 光子晶体三角孔阵列 ⚠️ **同样必然 `TypeError`**，见 §6.1；
5. `build_feed(app, feed_type=self.feed_type, name='feed1')` —— 馈源，返回实体名；
6. `build_waveguide(app, name='wg1')` —— 空心矩形铜波导，返回实体名；
7. `app.mirror(feed_name, ['p2x/2', '0', '0'], ['1', '0', '0'], copy=True, unite=True)`，
   对 `wg_name` 同样来一次 —— 把馈源和波导**镜像复制**到波导右端，镜像平面中心取 `p2x/2`、
   法向量沿 `x`（`copy=True/unite=True` 分别落成 VBA 的 `.MultipleObjects "True"` / `.GroupObjects "True"`）；
8. `add_ports_for_straight_waveguide(app, waveguide_name=wg_name)` —— 加 **2 个**波导端口（`'10'` + `'22'`）；
9. 布尔整合：`app.add('vpca', feed_name)`、`app.add('vpca', 'vpcb')`
   —— 结果留在 `vpca`，被加的实体被消耗（CST `Add` 语义）；
10. `configure_solver(app, freq_range=self.freq_range, monitors=self.monitors)`
    —— 时域求解器（`calculation_type='TD-S'`、`steady_state=-30`、`parallel_threads=1024`、`gpus=1`）+ 场监视器；
11. 置 `self._built = True` 并返回 `self`。

### 3.3 自动推断结果

| 项 | 值 / 来源 |
|---|---|
| `e1` | `a/2 = 0.12125` mm |
| `e2` | `a*sqrt(3)/2 ≈ 0.2100` mm |
| `l1` / `l2` | `0.65a = 0.157625` mm / `0.35a = 0.084875` mm |
| `path` 晶格点 | `[(0,-1), (0,length)]` |
| `xup / yup / ydn` | 由 `TopoPath.get_array_range()` 给出；本模板所有路径点都在 `r=0` 上，故 `xup = length+1`、`yup = 1`、`ydn = 1`（默认 `length=18` → `19 / 1 / 1`） |
| Modeler 侧推断 | `set_path()` 会把 `model_type` 判为 `'waveguide'`（`path.is_straight()` 成立），`modeler.topology` 随之取 `'AB'` |
| 端口数 / 监视器 | 模板**显式**给（2 端口、`monitors` 参数），没有走 `TopoModeler` 的推断方法 |

> **注意**：模板全程没有调用 `modeler.set_topology()`，也没有用 `TopoModeler.build_all()`；
> 它把 `topology` 存在 `self.topology` 里直接传给 builders。
> 因此当用户传 `topology='BA'` 时，`modeler.topology` 仍然是推断出的 `'AB'`——
> 这只影响 `modeler` 的展示与推断，不影响实际建模（实际拓扑以 `self.topology` 为准）。

### 3.4 完整示例

```python
from topo_templates import StraightWaveguide

wg = StraightWaveguide(
    topology='AB',            # 'AB' 或 'BA'
    length=18,                # 波导长度（晶格数）
    lattice_constant=0.2425,  # 晶格常数 a (mm)
    height=0.25,              # 硅片厚度 h (mm)
    large_hole_ratio=0.65,    # l1 = 0.65 * a
    small_hole_ratio=0.35,    # l2 = 0.35 * a
    feed_type='ab_elliptical',
    freq_range=(300, 380),    # GHz
    monitors=('E',),
    template_cst='tmp.cst',   # 必须放在当前工作目录
    output_path=r'D:\out\wg.cst',
)

print(wg)                     # StraightWaveguide(topology='AB', length=18, a=..., h=..., built=False)
fig, ax = wg.preview()        # matplotlib 预览路径 + 晶格背景
wg.build_all()                # 参数 → 基板 → VPC → 晶体 → feed → 波导 → 镜像 → 端口 → 整合 → 求解器
print(wg.app.cst_file.get_messages())   # 验收：应为空（库不保证把 CST 报错抛成异常）
wg.app.cst_file.model3d.Rebuild()       # 验收：历史树能否无错重放
print(wg.app.cst_file.get_messages())   # 应仍为空

wg.save()                     # 保存到 output_path
# wg.save(r'D:\out\wg_2.cst') # 也可以覆盖输出路径
# wg.run()                    # 最后再跑仿真
```

---

## 4. UnitAntenna

源码：`topo_templates/unit_antenna.py`（238 行）。

### 4.1 构造参数

`UnitAntenna.__init__`（`unit_antenna.py:67`）：

```python
UnitAntenna(bend_angle=120, straight_length=18, arm_length=14,
            topology='BA', lattice_constant=0.2425, height=0.25,
            large_hole_ratio=0.65, small_hole_ratio=0.35,
            feed_type='ba_tapered',
            radiator=None, radiator_radius=0.3,
            freq_range=(300, 380), monitors=('E', 'Farfield'),
            template_cst='tmp.cst', output_path=None)
```

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `bend_angle` | `int` | `120` | 拐弯角度（**必须是 60 的整数倍**，否则 `ValueError`）；`0` 表示不拐弯（直波导型天线） |
| `straight_length` | `int` | `18` | 直段长度（晶格数） |
| `arm_length` | `int` | `14` | 拐弯后的臂长（晶格数，仅在 `bend_angle != 0` 时生效） |
| `topology` | `str` | `'BA'` | 拓扑相，`'AB'` / `'BA'`，否则 `ValueError` |
| `lattice_constant` | `float` | `0.2425` | 晶格常数 `a`（mm） |
| `height` | `float` | `0.25` | 硅片厚度 `h`（mm） |
| `large_hole_ratio` | `float` | `0.65` | 大孔比例，`l1 = ratio * a` |
| `small_hole_ratio` | `float` | `0.35` | 小孔比例，`l2 = ratio * a` |
| `feed_type` | `str` | `'ba_tapered'` | BA 型对称渐变馈源（天线常用） |
| `radiator` | `str` | `None` | 辐射体类型；`None` = 不加，`'cylinder'` = 在路径末端加圆柱辐射体 |
| `radiator_radius` | `float` | `0.3` | 圆柱辐射体半径（mm） |
| `freq_range` | `tuple` | `(300, 380)` | 频率范围（GHz） |
| `monitors` | `tuple` | `('E', 'Farfield')` | 默认含远场监视器 |
| `template_cst` | `str` | `'tmp.cst'` | CST 模板工程（相对路径按当前工作目录解析） |
| `output_path` | `str` | `None` | 输出 `.cst` 路径 |

### 4.2 内部流程

**构造期（`unit_antenna.py:67-122`）**

1. 校验 `topology` 与 `bend_angle`（60 的倍数）；
2. 派生 `l1/l2`、`e1 = a/2`、`e2 = a*sqrt(3)/2`；
3. 构建路径（**条件拐弯**）：

   ```python
   b = (TopoPath.builder(self.a, name='p')
        .start(0, -1)
        .move(straight_length + 1, 'c'))
   if bend_angle != 0:
       b.turn(bend_angle).move(arm_length + 1, 'along')
   self.path = b.build()
   ```

   `bend_angle=0` → `[(0,-1), (0,18)]`（2 点，直线）；
   `bend_angle=120`（默认）→ 直段后方向由 `+c` 逆时针转 120° 变成 `+r-c`，
   再走 `arm_length+1 = 15` 步 → `[(0,-1), (0,18), (15,3)]`。

4. `self.xup, self.yup, self.ydn = self.path.get_array_range()`；
5. 建 `TopoModeler`、`set_path`、`set_parameters({'a','h','l1','l2','e1','e2'})`，存下 `self.app` 与 `self.nm`。

**建模期 `build_all()`（`unit_antenna.py:167-214`）**

1. `self._define_all_params()`：基础 6 个参数 + 路径点参数 + `xup/yup/ydn`
   + **BA 型 feed 参数** `x01=1, wf2=0.5, lf4=0.5, lf5=0.3`（与旧代码 `Ant3_epc` 一致）
   + 波导参数 `wg_a=0.5, wg_b=0.25, wg_t=0.02`；
2. `build_substrate(app, self.path, name='substrate')`；
3. `build_vpc_regions(app, self.path, topology=self.topology)` ⚠️ **必然 `TypeError`**（§6.1）；
4. `build_topological_crystal(app, self.path, topology=..., xup=..., yup=..., ydn=...)` ⚠️ **同样 `TypeError`**（§6.1）；
5. `build_feed(app, feed_type=self.feed_type, name='feed2')` —— BA 型对称渐变馈源；
6. `build_waveguide(app, name='wg1')`；
7. **可选辐射体**：仅当 `self.radiator == 'cylinder'` 时执行
   —— 取路径末点 `self.path.xy[-1]`，调
   `build_cylinder_feed(app, name='radiator', radius=self.radiator_radius, position=[x, y, '-h/2'])`，
   再把结果 `app.add('vpca', cyl_name)` 并入 VPC-A；
8. `add_port_for_antenna(app, waveguide_name=wg_name)` —— 只加 **1 个**端口（入口面 `'10'`）；
9. 布尔整合：`app.add('vpca', feed_name)`、`app.add('vpca', 'vpcb')`；
10. `configure_solver(app, freq_range=..., monitors=...)`（默认含 `'Farfield'`，会走远场监视器分支）；
11. `self._built = True`，返回 `self`。

### 4.3 自动推断结果

| 项 | 值 / 来源 |
|---|---|
| 路径（`bend_angle != 0`） | 直段 + 拐弯 + 臂，如默认参数下 `[(0,-1), (0,18), (15,3)]` |
| 路径（`bend_angle == 0`） | 只有直段 `[(0,-1), (0,straight_length)]`，**不加臂** |
| `xup / yup / ydn` | `TopoPath.get_array_range()`；随臂长增长（默认参数下按该公式算得约 `26 / 16 / 1`） |
| 默认拓扑 | `'BA'`（天线常用），并通过 `set_path()` 让 `modeler` 推断出 `model_type='antenna'`、`topology='BA'` |
| 默认监视器 | `('E', 'Farfield')`，与 `_infer_monitors()` 的结论一致 |
| 端口数 | 1（入口），与 `_infer_ports()` 的结论一致 |
| 端点用法 | `self.path.xy[-1]` 作为圆柱辐射体的落点 |

> **注意**：`bend_angle=0` 时路径只剩 2 个点，`TopoPath.is_straight()` 会成立，
> `TopoModeler` 因此把 `model_type` 判成 `'waveguide'`、`modeler.topology` 取 `'AB'`；
> 而模板自身的 `self.topology` 仍是默认的 `'BA'`（实际建模以 `self.topology` 为准）。
> 若要建「直波导型天线」，建议显式传 `topology=`，避免推断与实际不一致造成困惑。

### 4.4 完整示例

```python
from topo_templates import UnitAntenna

# ① 默认：BA 型 120° 单元天线
ant = UnitAntenna(
    bend_angle=120,            # 60 的整数倍；0 = 直波导型
    straight_length=18,        # 直段（晶格数）
    arm_length=14,             # 臂长（晶格数）
    topology='BA',
    feed_type='ba_tapered',
    freq_range=(300, 380),
    monitors=('E', 'Farfield'),
    template_cst='tmp.cst',
    output_path=r'D:\out\ant.cst',
)
fig, ax = ant.preview()
ant.build_all()
ant.save()

# ② 带圆柱辐射体
ant2 = UnitAntenna(bend_angle=60, straight_length=18, arm_length=10,
                   radiator='cylinder', radiator_radius=0.3,
                   output_path=r'D:\out\ant_cyl.cst')

# ③ 直波导型天线（不拐弯，只有直段）
ant3 = UnitAntenna(bend_angle=0, straight_length=20,
                   topology='BA',          # 建议显式声明，别依赖推断
                   output_path=r'D:\out\ant_straight.cst')
```

---

## 5. 三种用法对比

TPC 建模有**三层入口**，能力越往下越通用、代码越长。模板层只是「最常用器件的最短路径」。

| 层 | 入口 | 何时用 | 自由度 | 代码量 |
|---|---|---|---|---|
| **模板层** | `topo_templates.StraightWaveguide` / `UnitAntenna` | 器件正好是「直波导」或「单元天线」，只想改尺寸/拓扑/频段 | 只能改构造参数 | ~10 行 |
| **Modeler 层** | `TopoModeler` | 器件形态相同但需要自定义路径、分步构建、调整流水线开关 | 路径任意（`TopoPath` DSL）+ 每步可跳过 + 可传 kwargs 给 builders | ~15 行 |
| **Builder 层** | `topo_modeler.builders.*` | 需要**完全控制**：换阵列范围、改布尔顺序、插自定义部件、混用 `cst_solver` 原语 | 完全自由 | 30 行以上 |

**① 模板层**（推荐起点）：

```python
from topo_templates import StraightWaveguide

wg = StraightWaveguide(topology='AB', length=18, output_path=r'D:\out\wg.cst')
wg.preview(); wg.build_all(); wg.save()
```

**② Modeler 层**（自定义路径 + 一键流水线）：

```python
from mesh_grid.tri_grid import TopoPath
from topo_modeler import TopoModeler

path = (TopoPath.builder(a=0.2425)
        .start(0, -1).move(19, 'c')
        .turn(120).move(15, 'along')
        .build())

modeler = TopoModeler(template_cst='tmp.cst')   # tmp.cst 需在当前工作目录
modeler.set_path(path)                          # 自动推断：antenna + BA
modeler.set_parameters({'a': 0.2425, 'h': 0.25,
                        'l1': 0.65 * 0.2425, 'l2': 0.35 * 0.2425,
                        'e1': 0.2425 / 2, 'e2': 0.2425 * 3 ** 0.5 / 2})
modeler.build_all(freq_range=(300, 380))        # 基板→VPC→晶体→馈源→波导→端口→求解器
modeler.save(r'D:\out\antenna.cst')
```

> `TopoModeler.build_all()` 是「基础流水线」，**不含**模板里的镜像、圆柱辐射体、
> 器件特有的布尔整合顺序；`TopoModeler.integrate()` 目前是空实现（`pass`），
> 真正的整合由各 builder 内部与调用方完成。需要这些步骤就必须用模板层或 Builder 层。
> 另外 `build_lens()` / `read_results()` / `plot_results()` 目前直接
> `raise NotImplementedError`（阶段 4 / 阶段 5 才实现）。

**③ Builder 层**（完全控制）：

```python
from cst_solver import setup
from mesh_grid.tri_grid import TopoPath
from topo_modeler.builders import (
    build_substrate, build_vpc_regions, build_topological_crystal,
    build_waveguide, add_ports_for_straight_waveguide, configure_solver,
)

app = setup('tmp.cst')                          # 用临时模板工程
path = TopoPath.builder(a=0.2425, name='p').start(0, -1).move(19, 'c').build()

build_substrate(app, path, name='substrate')     # 内部会自动定义 p1x,p1y,...
build_vpc_regions(app, path)                     # 注意：不接受 topology=
build_topological_crystal(app, path, topology='AB')   # 注意：不接受 xup/yup/ydn=
wg = build_waveguide(app, name='wg1')
add_ports_for_straight_waveguide(app, waveguide_name=wg)
configure_solver(app, freq_range=(300, 380), monitors=('E',))

print(app.cst_file.get_messages())               # 验收
```

`builders/` 里的函数都是「无状态纯函数 + 显式参数」，可以脱离 `TopoModeler` 单独调用，
这也是排查模板类缺陷时最快的绕行方案。

---

## 6. 已知缺陷

### 6.1 参数不匹配导致运行时 `TypeError`（**已确认，必修**）

| 位置 | 问题 | 影响 | 建议修法 |
|---|---|---|---|
| `topo_templates/straight_waveguide.py:172` | `build_vpc_regions(app, self.path, topology=self.topology)` —— `build_vpc_regions` 的真实签名是 `(app, path, name_prefix='vpc', height='h', material='Silicon (lossy)', y_margin='e2', component='component1')`，**没有 `topology`** | `build_all()` 一执行到第 3 步就 `TypeError: build_vpc_regions() got an unexpected keyword argument 'topology'`，整个模板不可用 | 去掉 `topology=` 实参；拓扑只影响晶体阵列，与 VPC 区域无关 |
| `topo_templates/straight_waveguide.py:175-176` | `build_topological_crystal(app, self.path, topology=..., xup=..., yup=..., ydn=...)` —— 真实签名是 `(app, path, topology='AB', lattice='a', height='h', large_hole='l1', small_hole='l2', y_margin='e2', component='component1', name_prefix='g')`，**不接受 `xup/yup/ydn`**，阵列范围目前只能由内部 `path.get_array_range()` 推断 | 同上，`TypeError`；且即使删掉实参，「宽板覆盖不全」的问题仍在（阵列范围只按路径推，覆盖不到整个基板） | 给 `build_topological_crystal` **新增可选形参** `xup=None, yup=None, ydn=None`（`None` 时回退到原行为），模板再只传被接受的参数 |
| `topo_templates/unit_antenna.py:181` | 同样的 `build_vpc_regions(app, self.path, topology=self.topology)` | 同第 1 行 | 同第 1 行 |
| `topo_templates/unit_antenna.py:184-185` | 同样的 `xup/yup/ydn=` | 同第 2 行 | 同第 2 行 |

这两条已在两处技能文档登记，修完请同步删除对应条目：

- [`../../skills/developer/cst-solver-dev.md`](../../skills/developer/cst-solver-dev.md) §「待修清单」
  （`topo_templates/straight_waveguide.py` / `topo_templates/unit_antenna.py` 两行，以及配套的
  `builders/crystal.py` 新增 `xup=None, yup=None, ydn=None` 一行）；
- [`../../skills/user/tpc-usage.md`](../../skills/user/tpc-usage.md) §6「已知库缺陷」
  （同一缺陷的使用者视角表述）。

### 6.2 其它已核实问题（本次核查新增）

| 位置 | 问题 | 影响 | 建议修法 |
|---|---|---|---|
| `topo_templates/*.py` 构造期 `self.modeler.set_parameters({...})` | `TopoModeler.set_parameters(params)` 内部调用 `self.app.set_parameters(params)`；而 `cst_solver` 的 `set_parameters(name, value, log_flag=0)` 需要**两个**位置参数（批量接口叫 `paras(name, value)`） | CST 可用时，`StraightWaveguide(...)` / `UnitAntenna(...)` **在构造阶段就 `TypeError`**（缺 `value`），比 §6.1 更早触发 | 在 `topo_modeler/modeler.py` 里改为 `self.app.paras(params, None)`（`paras` 的 docstring 明确支持 dict），或逐项 `self.app.para(k, v)` |
| `topo_templates/*.py` 的 `run()` | 调用 `self.app.start_solver()`，但 `cst_solver` 里**没有** `start_solver` 方法，求解器入口是 `SolverMixin.run()` | `wg.run()` → `AttributeError: 'setup' object has no attribute 'start_solver'` | 改为 `self.app.run()`（`TopoModeler.run()` 用的就是它） |
| `topo_templates/*.py` 的 `build_all()` 缺少收尾校验 | 建完直接返回，不检查 CST 消息；而库**不保证**把 CST 报错抛成异常（`add_to_history` 只是下发 VBA） | 「跑通」不等于「建对」，可能静默产生空集布尔结果 | 在 `build_all()` 末尾（或提供 `verify()`）读 `app.cst_file.get_messages()`；文档/示例里明确这一步为验收动作 |
| `topo_templates/*.py` 的 `save()` | 直接调 `self.app.cst_file.save(...)`，绕过 `setup` 封装的 `save()`；`self.width` 接受后从未使用；`a/h/l1/l2/e1/e2` 在 `__init__`（`set_parameters`）与 `_define_all_params()`（`app.para`）被定义两次 | 风格/可维护性问题，不影响几何正确性 | 按 `docs/next_plan/` 的 P2 条目逐步收敛到 `app.save(path)`；`width` 要么实现要么标注 deprecated |

### 6.3 包命名风险 —— ✅ **已解决**（T10，2026-09-15）

| 项 | 说明 |
|---|---|
| 原风险 | 旧包名 `templates` 是极其通用的名字。一旦本库安装进 site-packages，极可能与第三方包**重名**，届时 `import templates` 命中的是谁取决于 `sys.path` 顺序，属于难以排查的隐性故障 |
| 处置 | **已完成改名**：`templates/` → **`topo_templates/`**（`git mv`，历史保留）；旧名 `templates/` 保留为**转发 shim**（`templates/__init__.py`，导入即发 `DeprecationWarning`），约定**一个版本周期后移除** |
| 连带改动 | `pyproject.toml` 的 `packages.find`（新增 `topo_templates*`，**并保留** `templates*` 以便 shim 一起分发）；全仓 35 个文件里的 167 处引用统一改名；`docs/packages/templates.md` → `docs/packages/topo_templates.md`；`scripts/_api_stats.py` 的扫描目标改名 |
| 移除计划 | 下一个版本周期删除 shim。到期前的复评登记在 [`../next_plan/stages/08`](../next_plan/stages/08_阶段8_复杂结构与旧代码迁移.md) |
| 怎么验 | `python -c "import warnings; warnings.simplefilter('error', DeprecationWarning); import templates"` 应当**报** DeprecationWarning；`import topo_templates` 不应有任何告警 |

### 6.4 透镜模板尚未实现 —— 🔄 **几何层已就绪，模板仍缺**

- `topo_templates/__init__.py` 的 docstring 写的是「直波导、单元天线、**透镜天线**等」，但目录里目前**只有 2 个模板**。
- ✅ `TopoModeler.build_lens()` **已不再抛 `NotImplementedError`**（2026-09-15，阶段 6 几何层）：
  透镜几何下沉到了 `topo_modeler/builders/lens.py`（`GrinLensSpec` / `GrinLensHoles` /
  `build_grin_lens_holes()` / `build_grin_lens()`），并已与原脚本
  `topo_modeler/lens_build.py` 做**逐点/逐条等价**回归（`topo_modeler/tests/test_lens.py`）。
- ❌ 仍缺：**`GRINLensAntenna` 模板本身**（阶段 6 剩余项）、`method='dxf'` 入口。
  端到端跑通必须真 CST，在算力受限期间不做 —— 详见
  [`../next_plan/stages/06`](../next_plan/stages/06_阶段6_复杂模板层.md) §7。
- 沙盒脚本 `topo_modeler/lens_build.py` / `lens_build_standalone.py` **保留**（notebook 仍在 `exec` 它），
  但库侧不再依赖它们。按 [`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md) §10.7，
  实验性代码仍应先留在沙盒、不直接进 `topo_templates/` 公开路径。

---

## 7. 如何新增一个模板

模板层的改动流程固定，**完整流程以
[`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md) 为准**（尤其 §2 改动归属、
§3 标准工作流、§4 `topo_templates/` 验收清单、§6 文档同步矩阵、§8 提交规范）。这里只列模板专属要点：

1. **判定阶段与归属**：读 `docs/next_plan/` 确认需求属于哪个阶段；确认它确实是「某个具体器件的完整流程」
   （若只是新增几何部件，应落在 `topo_modeler/builders/`，不是模板）。
2. **确认几何推导不在模板里**：路径用 `TopoPath`，实体/布尔/端口/求解器用 `topo_modeler.builders.*`。
   模板里出现手算坐标、手写 VBA 字符串、多边形顶点列表，都属于违规（WORKFLOW §2 反例）。
   —— 而且**不要传构建器签名里没有的参数**（§6.1 就是这么来的）。
3. **新建 `topo_templates/<器件>.py`**：一个类 = 一个器件；`__init__` 只做「校验 + 派生参数 + 建 `TopoPath` + 建 `TopoModeler` + 定义参数」，
   建模全部放在 `build_all()`；提供 `preview()` / `build_all()` / `save()` / `run()` 这套统一接口，并实现 `__repr__`。
4. **同步导出**：修改 `topo_templates/__init__.py`，把新类加进 `import` 与 `__all__`。
5. **同步文档**：本文件（§2 总览表 + 新增一节）、`docs/ARCHITECTURE.md` §3.4 的模板表、
   `docs/guides/topo_modeler_guide_stage0-3.md` §4 的模板小节，以及 `README.md`
   （若有面向使用者的用法变化）。
6. **验收**（WORKFLOW §4）：
   - 参数有合理默认值，构造后 `preview()` 能画出路径；
   - `build_all()` 端到端跑通，且 `app.cst_file.get_messages()` 为空，`model3d.Rebuild()` 之后仍为空；
   - 与 `TopoModeler` 的自动推断结果一致，或显式覆盖并说明理由。
7. **提交**：一个包一条 commit（`feat(topo_templates): …`），建议连带跑一次
   `python -m pytest -q` 确认没有破坏 `mesh_grid` 的单测。

---

## 8. 相关文档

- 总体架构与依赖方向 → [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
- 建模引擎（`TopoModeler` + `builders/`）→ [`../packages/topo_modeler.md`](../packages/topo_modeler.md)
- 阶段 0–3 详细指南（含 §4.4 / §4.5 模板小节）→ [`../guides/topo_modeler_guide_stage0-3.md`](../guides/topo_modeler_guide_stage0-3.md)
- 使用者主手册（按需查阅地图、报错定位表、已知库缺陷、验收清单）→ [`../../skills/user/tpc-usage.md`](../../skills/user/tpc-usage.md)
- 建模引擎三种用法（模板 / Modeler / Builder）→ [`../../skills/user/topo-modeler.md`](../../skills/user/topo-modeler.md)
- 开发者工作流（改动归属、验收清单、文档同步、提交规范）→ [`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md)

> 说明：`docs/packages/` 下每个包一份文档，本文是其中一份；同级页面
> [`../packages/cst_solver.md`](../packages/cst_solver.md)、
> [`../packages/mesh_grid.md`](../packages/mesh_grid.md)、
> [`../packages/topo_modeler.md`](../packages/topo_modeler.md) 与本文互为补充。
> 另外，上面 `../../skills/user/topo-modeler.md` 一条已被 `README.md` 与
> [`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md) §3 引用，
> 但该页面目前尚未落地（`skills/user/` 下只有 `tpc-usage.md`、`tri-grid.md`、`hex-grid.md`），
> 暂时打不开属正常现象。
