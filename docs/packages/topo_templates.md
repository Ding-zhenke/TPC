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
| **当前阶段** | 六类模板已实现；透镜模板支持 `generate`、`dxf`、`insitu`。真机建模已验证，求解与物理结果仍待验收（见统一计划）。 |

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

## 2. 三个模板总览

| 维度 | `StraightWaveguide` | `UnitAntenna` | `GRINLensAntenna`（2026-09-17 新增） |
|---|---|---|---|
| 器件 | 拓扑光子晶体**直波导** | **单元天线**（直段 + 拐弯 + 臂，可选辐射体） | **单元天线 + 六边形顶点 6 个 GRIN 椭圆透镜** |
| 源文件 | `topo_templates/straight_waveguide.py` | `topo_templates/unit_antenna.py` | `topo_templates/grin_lens_antenna.py`（继承 `UnitAntenna`） |
| 内部路径 | `.start(0, -1).move(length+1, 'c')` → `[(0,-1), (0,length)]` | `.start(0, -1).move(straight_length+1, 'c')`；`bend_angle != 0` 时再加 `.turn(...).move(arm_length, 'along')`（**2026-09-17 起臂长不再 `+1`**） | 与 `UnitAntenna` **完全相同**（透镜与路径无关） |
| 默认拓扑 | `'AB'` | `'BA'` | `'BA'` |
| 默认馈源 | `'ab_elliptical'`（实体名 `feed1`） | `'ba_tapered'`（实体名 `feed2`） | `'ba_tapered'`（实体名 `feed2`） |
| 端口 | **2 个**（入口面 `'10'` + 出口面 `'22'`） | **1 个**（入口面 `'10'`） | **1 个**（入口面 `'10'`） |
| 默认监视器 | `('E',)` | `('E', 'Farfield')` | `('E', 'Farfield')` |
| 镜像步骤 | 有：feed + waveguide 镜像到右端（中心 `p2x/2`） | 无 | 无 |
| 辐射体 | 无 | 可选 `radiator='cylinder'`（圆柱，位于路径末端） | 可选（同 `UnitAntenna`） |
| 额外步骤 | — | — | **GRIN 透镜**：DXF 导入 → y 镜像 → 椭圆拉伸 → 减孔 → 楔形裁剪 → 移到顶点 → 旋转复制 ×6 |
| 额外校验 | `topology ∈ {'AB','BA'}` | 同上 + `bend_angle` 必须是 **120 的整数倍**（张角；单臂偏角 = 一半，必须是 60° 的整数倍） | 同上 + `lens_method ∈ {'generate','dxf','insitu'}`；`'dxf'` 时必须给存在文件的 `lens_dxf`；`'insitu'` 与 `lens_dxf` 互斥 |
| 典型旧代码 | `AB_feed.ipynb` / `BA_feed.ipynb` | `Ant1_D_BA_120D` / `Ant3_epc` 等 | `lens_build.py` / `Ant6_2H4L_epc.ipynb`（透镜几何）；**组合体的顺序是本库定的** |

三个模板的类接口完全一致，都是这 4 个公开方法：

| 方法 | 签名 | 说明 |
|---|---|---|
| `preview` | `preview(ax=None, show_grid=True)` | 委托 `TopoPath.preview()`，画路径 + 晶格背景，返回 `(fig, ax)` |
| `build_all` | `build_all()` | 端到端建模，返回 `self`（可链式） |
| `save` | `save(output_path=None)` | 保存 `.cst`；未建模则先自动 `build_all()`；返回实际保存路径 |
| `run` | `run()` | 运行仿真；未建模则先自动 `build_all()`；返回 `self` |

`GRINLensAntenna` 另有 4 个**离线可用**的方法（不碰 CST）：

| 方法 | 说明 |
|---|---|
| `make_lens_spec()` | 算 `GrinLensSpec`（`ec_a/ec_b/ec_c/r1/r2/r_big`） |
| `make_lens_dxf(path=None)` | 算孔阵列并导出 DXF（`lens_method='generate'` 用） |
| `make_lens_ring()` | 算**就地环透镜**的孔集合（`lens_method='insitu'` 用，纯几何） |
| `lens_summary()` | 几何摘要 dict（方法/孔数/DXF 路径/椭圆或环参数） |

它也支持 **`lens_rotation`**（参考的 `dphi`，度）：把**透镜绕自身近焦点自转**一个角度
（`build_grin_lens(..., self_rotation='dphi')`，用 CST 参数而不烘死角度；默认 0 ⇒ 不下发、
也不登记 `dphi`）。⚠️ 与 `PowerDivider` 的 `dphi1/dphi2`（第二个**相位副本**）不是一回事。

### 2.1 `MultiPortAntenna`（P5，2026-09-17 新增）

| 维度 | 值 |
|---|---|
| 器件 | **多端口天线**：1 分 2（主干 + 两条分支）+ **双馈源** + 两条铜波导 ⇒ **3 个端口** |
| 来源 | α1 族取证（`多端口\Ant3_1W2N` + `MPMBA\Ant3_*`，4 个 notebook 命令序列同构），见 [设计记录](../guides/complex_device_templates_design.md) |
| 拓扑构造 | **本库口径**（多条 `TopoPath` 中心线 + `±y_margin` 派生区域 + 多路径布尔并），**不是** notebook 的闭合轮廓复刻 ⇒ 验收判据是「端口/参数同类 + 只建模 0 消息」，**不是**几何等价 |
| 参数 | `straight_length` / `arm_length` / `topology` / `port_numbers`（**编号必须由调用方给**：参考 notebook 之间有对调）/ `feed_params`（两族键都接受）/ `lens_method`（`generate`/`dxf`/`insitu`）/ `lens_dxf` / `lens_layers` / `lens_d0_layers` / `lens_name` / `lens_component` |
| 专属方法 | `summary()`（离线摘要：三条路径格点、并集阵列范围、端口、馈源覆盖、透镜）；`make_lens_spec()` / `make_lens_dxf()` / `make_lens_ring()` / `lens_summary()`（离线透镜几何） |
| 透镜 | 三条路线（与 `GRINLensAntenna`/`PowerDivider` 同名同义）；口径 = **单枚、近焦点在原点**（`place=False`，无 `Rbig` 平移、无 6 份复制 ⇒ 不登记 `Rbig`）—— 与参考 `MPMBA/Ant3_*` 一致 |
| 真机（只建模） | 见 [P5 多端口记录](../validation/p5_multiport_evidence.md) |

> `save()` / `run()` 里的 `build_all()` 是**幂等保护**（靠 `self._built` 标记），
> 所以下面的写法都合法：`wg.build_all(); wg.save()` 或直接 `wg.save()`。

### 2.2 `MZISwitch`（P5，2026-09-17 新增）

| 维度 | 值 |
|---|---|
| 器件 | **MZI 开关**：6 点中心线 + 耦合区矩形（镜像）+ 开关圆柱（材料 `m1`）+ **2 端口** |
| 来源 | `开关尝试\AB\MZI.ipynb`（`basic`）与 `MZI-cascade.ipynb`（**CST 侧与 basic 完全相同**） |
| 参数 | `arm_x1` / `mid_x2` / `arm_gap_y1`（参考 9/9/5 ⇒ 阵列范围 **23/10/10**）/ `mzi_type`（`basic`/`cascade` 同一几何；`parallel`/`anti` **未实现，传入即报错**）/ `pump_ax` / `pump_ay` / `cylinder_radius` / `sigma1` / `feed_params` / `lens_method`（`generate`/`dxf`/`insitu`）/ `lens_dxf` / `lens_layers` / `lens_d0_layers` / `lens_name` / `lens_component` |
| 阵列范围 | **参考公式**：`xup = x1*2+x2-int(y1)+1`、`yup = ydn = y1+y2` —— ⚠️ 不能用 `path.get_array_range()`（单边偏置路径给 `ydn=1` ⇒ 0 次复制 ⇒ CST 报错） |
| 端口 | **Free 模式**（`create_waveguide_port_free`，给坐标范围），不用面号 —— 参考的面号在我们构序下不存在 |
| 透镜 | 三条路线（与另外三个模板同名同义）；口径 = **单枚、近焦点在原点**（`place=False`，**不登记 `Rbig`**）—— 覆盖参考 `MZI-GRIB.ipynb` 的活代码环透镜 |
| 专属方法 | `port_specs()`（离线核对端口规格）、`summary()`（离线摘要）；`make_lens_spec()` / `make_lens_dxf()` / `make_lens_ring()` / `lens_summary()`（离线透镜几何） |
| 真机（只建模） | 见 [P5 MZI 记录](../validation/p5_mzi_evidence.md)（OK 25 / FAIL 0，含两条透镜路线） |

### 2.3 `PowerDivider`（P5，2026-09-17 新增）

| 维度 | 值 |
|---|---|
| 器件 | **1 分 N 功分器**（N ∈ {2,3,4,6}）：主干 + N 条完整输出路径 + 单馈源 + 单铜波导 + **1 端口** |
| 来源 | α2 族 5 个 notebook（`Ant2_1div2_*`、`Ant3_1div3_BA_120D_epc`、`Ant4_1div4_BA_120D_epc`、`Ant4_1d2d4_2f2s_circle_DF`、`B6\Ant6_2H4L_epc`） |
| 参数 | `split_ratio`（**只接受 2/3/4/6** —— 参考里有数据依据的全部取值）/ `trunk_length` / `arm_length` / `sub_length` / `topology` / `port_number` / `feed_params` / `lens_method`（`generate`/`dxf`/`insitu`）/ `lens_dxf` / `lens_layers` / `lens_d0_layers` / `lens_phase` / `lens_kwargs` / `switch_mode`（`None`/`arm_mid`/`explicit`）/ `switch_xy` / `switch_radius` / `switch_sigma` / `switch_material` |
| 级联 | `4` = **2×2**（= 参考 `1d2d4`）、`6` = **2×3**；`2`/`3` 单级扇出（臂方向取晶格 60° 方向） |
| 分类口径 | **只按分路数**：`divider_type('y'/'t'/'cascade'/'mmi')` 在参考参数表里**没有出处** ⇒ 不提供（传入即报错） |
| 透镜/相位 | 三条路线（与 `GRINLensAntenna` 同名同义）：`generate` 现算 + 落 DXF / `dxf` 用现成 DXF / `insitu` **不落 DXF**（CST 内逐 `hexagon` 建环）+ `lens_phase`（`dphi1/dphi2`，语义=把透镜绕 z 转 dphi 放到不同输出臂）；**per-arm 定位未实现** |
| 开关/泵浦区 | `switch_mode`：`None` 不建 / `'arm_mid'` 每条第一级输出臂最后一段中点（本库口径）/ `'explicit'` 用 `switch_xy=[(x,y),…]`；做法 = 自定义材料（ε=11.9、κ=`sigma1`）+ 圆柱（r=`rc1`）+ **区域副本求交** + `insert` 回区域；`rc1/sigma1` **只在建开关时登记** |
| 专属方法 | `output_paths()`、`make_lens_spec()`、`switch_positions()`、`summary()` |
| 真机（只建模） | 见 [P5 功分器记录](../validation/p5_power_divider_evidence.md)（四种分路数各建一次：OK 22 / FAIL 0） |

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

> ✅ **模板已可建模（2026-09-17，P4/V1 真机复验 ✅ 已在新臂方向上复跑：AB 单拓扑 14 OK / 0 FAIL）。**
> 阵列范围与路径映射已按参考工程修好并逐值核对通过，弯折路径的偏移多边形自交缺陷也已修复
> （`mesh_grid/tri_grid/topo_path.py`；详见 §4.6 与 §6.5）。
> **单条带多边形在折回路径上无法表达，故改为「每段四边形 + 布尔并」**；
> 真机上 `build_all()` 的 `build_substrate` 与 `build_vpc_regions` 两步均**成功且 0 条 CST 消息**，
> 落盘 `xup/yup/ydn` 与参考工程逐值相同（AB `25/14/14`、BA `26/14/14`）。
> 完整实测证据：[`../validation/p4_real_machine_evidence.md`](../validation/p4_real_machine_evidence.md) §4.3/§4.4。
> ⚠️ **语义已查清并实现**：`bend_angle` 是**张角**（两侧臂夹角），参考「120D」正是 `120`
> （臂端与参考工程 `px3/py3` 逐位相同，见 §4.7）。
> **新臂方向的真机复验已完成（2026-09-17）**：路径 `[(0,-1),(0,18),(14,18)]` / `(-14,32)`、
> AB 臂端 `(6.0625,+2.9402)` 与 BA `(6.0625,−2.9402)` 均与参考工程**逐位一致**，0 条 CST 消息、
> 0 弹窗、收尾无残留 DE。同一轮还修掉一处「假参数化」（阵列次数被烘成 `int(25)` ⇒ 参数表里的
> `xup/yup/ydn` 无人引用），见 §4.8 与 [P4 证据](../validation/p4_real_machine_evidence.md) §8.7。

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
| `bend_angle` | `int` | `120` | 拐弯**张角**（两侧臂夹角 = 单臂偏角 ×2，**必须是 120 的整数倍**，否则 `ValueError`）；`0` 表示不拐弯（直波导型天线）。参考 notebook 文件名的数字就是它：`120D` ⇔ `120`、`240D` ⇔ `240` |
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

1. 校验 `topology` 与 `bend_angle`（**张角，120 的整数倍**）；
2. 派生 `l1/l2`、`e1 = a/2`、`e2 = a*sqrt(3)/2`；
3. 构建路径（**条件拐弯**）：

   ```python
   sign = 1 if topology == 'AB' else -1          # 两种拓扑互为镜像
   b = (TopoPath.builder(self.a, name='p')
        .start(0, -1)
        .move(straight_length + 1, 'c'))
   if bend_angle != 0:
       b.turn(sign * (bend_angle // 2)).move(arm_length, 'along')   # 张角的一半
   self.path = b.build()
   ```

   `bend_angle=0` → `[(0,-1), (0,18)]`（2 点，直线）；
   `bend_angle=120`（默认，AB）→ 直段后由 `+c` 逆时针转 **60°**（= 张角的一半）变成 `+r`，
   走 `arm_length = 14` 步 → `[(0,-1), (0,18), (14,18)]`，臂端 `(6.0625, +2.9402)`
   **= 参考工程 AB 120 的 `px3/py3`**；BA 取 `sign=-1` → `[(0,-1), (0,18), (-14,32)]`，
   臂端 `(6.0625, -2.9402)` = 参考 BA 120（两者严格镜像）。
   （2026-09-17 起臂长就是 `arm_length`，**不再多走一步** —— 此前写成 `arm_length + 1`，
   真机实测路径为 `[(0,-1), (0,18), (15,3)]`，与库自己的映射表不符，见 §4.5。）

4. 计算阵列范围 `self.xup / self.yup / self.ydn` —— **不用 `path.get_array_range()`**，
   而是按参考工程公式直接算（见 §4.5）；
5. 建 `TopoModeler`、`set_path`、`set_parameters({'a','h','l1','l2','e1','e2'})`，存下 `self.app` 与 `self.nm`。

**建模期 `build_all()`（`unit_antenna.py:167-214`）**

1. `self._define_all_params()`：基础 6 个参数 + 路径点参数 + `xup/yup/ydn`
   + **BA 型 feed 参数** `x01=1, wf2=0.5, lf4=0.5, lf5=0.3`（与旧代码 `Ant3_epc` 一致）
   + 波导参数 `wg_a=0.5, wg_b=0.25, wg_t=0.02`；
2. `build_substrate(app, self.path, name='substrate')` —— ✅ **已可建模**。弯折路径下基板不再是
   单条带多边形，而是内部按 `path.build_segment_band_polygons()` **逐段建模 + 布尔并**
   （每段一个平行四边形 + 拐角补块）；直线路径产物与旧实现逐字节相同，见 §4.6；
3. `build_vpc_regions(app, self.path)` —— 拓扑相不影响 VPC 区域，**不接受 `topology=`**（§6.1 的那条 `TypeError` 已修）；
4. `build_topological_crystal(app, self.path, topology=..., xup=..., yup=..., ydn=...)`
   —— 构建器已支持 `xup/yup/ydn` 显式覆盖（§6.1 的那条 `TypeError` 已修），
   模板传入的就是 §4.5 的参考公式值；
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
| 路径（`bend_angle != 0`） | 直段 + 拐弯 + 臂，如默认参数下 `[(0,-1), (0,18), (14,4)]`（臂长 = `arm_length` 步） |
| 路径（`bend_angle == 0`） | 只有直段 `[(0,-1), (0,straight_length)]`，**不加臂** |
| `xup / yup / ydn` | 参考工程公式，**不再来自 `TopoPath.get_array_range()`**：`xup = straight_length + int(arm_length/2) (+1 当 topology=='BA')`、`yup = ydn = arm_length`；默认参数 AB `(25, 14, 14)` / BA `(26, 14, 14)`，详见 §4.5 |
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
    bend_angle=120,            # 张角（120 的整数倍；0 = 直波导型）
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

### 4.5 参数映射口径（P4/V1 真机核验，2026-09-17）

**只用参考工程的口径，不再用 `path.get_array_range()`。** 参考工程
`普通单元天线\Ant1_D_{AB,BA}_120_Feed_antenna-DF` 的 `Parameters.json`（及对应 ipynb）给出：

| | AB（臂朝 +y） | BA（臂朝 −y） |
|---|---|---|
| `xup` | `x1 + int(y1/2)` = **25** | `x1 + int(y1/2) + 1` = **26** |
| `yup` / `ydn` | **14** / **14** | **14** / **14** |

（`x1 = 18` 直段周期数、`y1 = 14` 臂长，对应库里的 `straight_length` / `arm_length`。）
现行实现即：

```python
self.xup = straight_length + int(arm_length / 2) + (1 if topology == 'BA' else 0)
self.yup = self.arm_length
self.ydn = self.arm_length
```

**为什么必须改掉 `get_array_range()`。** 旧实现直接取 `path.get_array_range()`，真机实测得到
**`(26, 16, 1)`**：

- `yup = 16` / `ydn = 1` **既不对称、也覆盖不到臂**（阵列应上下各铺 `arm_length`）；
- 更致命的是 `ydn = 1` —— `topo_modeler/builders/crystal.py` 下发的是
  `repetitions=f'int({ydn}/2)'`，即 **0 次复制**，CST 直接报 `Invalid number of repetitions`。

**修复后真机实测**：AB `(25, 14, 14)` ✅ / BA `(26, 14, 14)` ✅，与参考工程**逐值相同**；
模板路径为 `[(0,-1), (0,18), (14,4)]`。离线回归
`topo_templates/tests/test_antenna_mapping.py`（7 项：两个拓扑的范围、`int(yup/2) >= 1` 的回归、
随臂长缩放、路径步数 = 臂长、不拐弯、参数校验）钉住这些数字：

```bash
python -m pytest topo_templates/tests/test_antenna_mapping.py -q
```

详见 [`../validation/p4_real_machine_evidence.md`](../validation/p4_real_machine_evidence.md) §4.1–§4.3。

### 4.6 已修：弯折路径的偏移多边形自交（修复方式与真机结果）

> ✅ **状态：已修并真机复验（2026-09-17）。** 本节保留原始现象与根因，便于日后对照；
> 末段的「修复方向」已在本次落地，不再是待办。

**原现象**：参数修好之后**仍然无法建模** —— `build_all()` 在 `build_substrate` 一步就失败：

```
(&H8000ffff) The specified curve is not closed and planar.   (ExtrudeCurve .Create)
```

**根因（两层）**：

1. `mesh_grid/tri_grid/topo_path.py` 的 `build_substrate_polygon()` 与
   `build_vpc_area_polygon()` 生成的偏移链**只在 y 方向偏移**（`py ± y_margin`）。
   直线路径没问题（直波导就是这么用的），但**拐弯路径**上两条链会互相穿插，
   得到一个**自交多边形**，CST 拒绝拉伸。
2. **更本质**：**恒定宽度的整条带在折回路径上会自覆盖**，单个简单多边形**根本无法表达**它
   （120° 折回的天线路径就是这种情形）。所以只把偏移算「准」还不够。

**原证据**：跳过基板、直接调用 `build_vpc_regions(app, path)` 也抛同一个异常
⇒ 缺陷在**共享的多边形构造**里，不只是 `substrate.py`。

**修复方式（2026-09-17 已落地）**：

| 位置 | 改动 |
|---|---|
| `mesh_grid/tri_grid/topo_path.py` | 新增 `_step_vectors()` / `_normal_coeff()` / `_vertex_offset_coeffs()` / `_offset_chains()` / `_offset_term()` / `_turn_cross()`：偏移改为**按段法向 + 拐点 miter 连接**，用 `Fraction` 有理数运算，偏移量写成 CST 表达式（`sqr(3)`、`y_margin`），**不出现硬编码数值**；新增 **`build_segment_band_polygons(y_margin='e2', prefix=None, side=None)`**：**每段一个平行四边形 + 拐角补块**（只补**外侧**），每个四边形都是 CCW 简单多边形；180° 折返抛明确 `ValueError` |
| `topo_modeler/builders/substrate.py` | `build_substrate()` 改为按 `build_segment_band_polygons()` **逐段建模 + 布尔并**（与既有 `build_substrate_multi` 同一套路） |
| `topo_modeler/builders/vpc_region.py` | `build_vpc_regions()` 同样改为逐段建模 + 布尔并（A 用 `side='lower'`、B 用 `side='upper'`） |

`build_substrate_polygon()` / `build_vpc_area_polygon()` **保留**（弯折路径下仍是单多边形，
仅供兼容与查看），但**构建器已不再使用它们**。
**向后兼容**：直线路径只有一段 ⇒ 产物与旧实现**逐字节相同**（单测钉住）。
⚠️ **适用条件**：拐角补块基于「带宽远小于段长」的常规用量；**超宽带宽**（如 `y_margin` 远大于段长）
自交仍可能出现，这属于输入不当，**不在保证范围内**。

**真机复验结果**（`python scripts/verify_antenna_mapping.py --topology AB|BA`，两次各 8/8 通过）：

| 拓扑 | 路径 | 阵列范围 | 建模 | 落盘 `xup/yup/ydn` |
|---|---|---|---|---|
| AB | `[(0,-1),(0,18),(14,4)]` | (25, 14, 14) | **成功，0 条 CST 消息** | 25 / 14 / 14 |
| BA | `[(0,-1),(0,18),(14,4)]` | (26, 14, 14) | **成功，0 条 CST 消息** | 26 / 14 / 14 |

即 **`UnitAntenna` 模板现在可以建模了**（此前在建 `build_substrate` 一步就失败）。
新增离线回归 `mesh_grid/tri_grid/tests/test_band_polygon.py`（平行四边形不自交、CCW、
直线路径逐字节兼容、**带内采样点覆盖性**、miter 表达式含 `sqr(3)` 且无硬编码小数、180° 折返报错）。

⚠️ **语义已查清并实现**（张角口径，见 §4.7）；**新臂方向的真机复验已完成**（2026-09-17，AB 单拓扑 14 OK / 0 FAIL，见 §4.8）。

完整证据（含探针与报错原文）见
[`../validation/p4_real_machine_evidence.md`](../validation/p4_real_machine_evidence.md) §4.3/§4.4；
本缺陷已同时登记在 §6.5，以及 [`../../skills/user/topo-modeler.md`](../../skills/user/topo-modeler.md) §2。

### 4.7 `bend_angle` = 张角（两侧臂夹角）—— 已查清并实现

2026-09-17 离线取证（只读参考 notebook JSON + 解码参考工程的 `Parameters.json`，
再用 `TopoPath` 复现同一条路径比对）给出**逐位比对**的结论：

| 参考工程（`bend_angle=120`） | 臂端物理坐标 | 等价库调用 | 库实测臂端 |
|---|---|---|---|
| AB 120 | (6.0625, **+2.9402**) | `turn(+60)` | (6.0625, +2.9402) ✅ |
| BA 120 | (6.0625, **−2.9402**) | `turn(−60)` | (6.0625, −2.9402) ✅ |
| （无） | — | `turn(120)` | (2.6675, +2.9402) ❌ 不匹配任何参考单元天线 |

⇒ 文件名/notebook 里的数字是**两侧臂张角**（= 2 × 单臂偏角）：参考 240D 族
（`Ant1_grid_240D_circle.ipynb`）的臂方向正是 120°，等于 `turn(120)`，与「张角 240」自洽。
`bend_angle` 本身**不是** `TopoPath.turn()` 的转角 —— 模板下发的是它的一半，
且符号按拓扑取（AB `+`、BA `−`，两种拓扑严格镜像）。

**已按「张角口径」实现**（2026-09-17，用户确认）：`bend_angle` = 两侧臂张角
= 2 × 单臂偏角，实现为 `turn(±bend_angle/2)`（AB 取 `+`、BA 取 `−`）。
于是默认 `bend_angle=120` + 默认 `straight_length=18/arm_length=14/xup` **正好复现参考 120D**，
`240` 对应 240D notebook；合法值因此收紧为 **120 的整数倍**（60/180/300 会让单臂落在
30°/90°/150°，不是晶格方向，构造时与配置层都会 `ValueError`）。
回归用例：`topo_templates/tests/test_antenna_mapping.py`（臂端与参考工程逐位比对 + 镜像 + 合法值）。
证据：[P4 真机验收记录](../../docs/validation/p4_real_machine_evidence.md) §4.5。

### 4.8 已修：阵列次数必须是**参数引用**，不许烘成数字（2026-09-17 真机取证）

新臂方向的真机复验（`python scripts/verify_antenna_mapping.py --topology AB` → **14 OK / 0 FAIL**）
顺手挖出一个**真缺陷**：两个模板都把阵列次数当**数值**传下去，于是历史里写的是

```text
.Repetitions "int(25)"        ← 我们（修前），参数 xup 一次都没被引用
.Repetitions "int(xup)"       ← 参考工程 Ant1_D_{AB,BA}_120_Feed_antenna-DF
```

后果：参数表里的 `xup/yup/ydn` **形同备注** —— 在 CST 里改它阵列不会重排（参考工程会）。
真机实测修前整份 `ModelHistory.json` 里 `xup|yup|ydn` 出现 **0 次**。

**修复**：`builders/crystal.py` 新增 `repeat_expression(value, divisor=1)` —— `str` 当参数名引用、
数字仍烘数值（逐字节兼容旧行为）；`UnitAntenna` / `StraightWaveguide` 改为传
`xup='xup', yup='yup', ydn='ydn'`。修后真机：历史里三条参考写法齐全，`xup/yup/ydn`
从「未引用」变成「已引用」，**死写入 0 项**，臂端/阵列范围回归无变化。

回归：`topo_modeler/tests/test_crystal_array_expression.py`（12 项）、
`tests/test_model_parameter_usage.py`（13 项）、检查工具 `scripts/verify_model_parameter_usage.py`。
完整取证：[P4 真机验收记录](../../docs/validation/p4_real_machine_evidence.md) §8.7。

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

> **2026-09-17 更新（P4/V1 真机核验）**：表中 **`unit_antenna.py` 的两行已修** ——
> 现行 `unit_antenna.py:215` 是 `build_vpc_regions(app, self.path)`（不传 `topology`），
> 且 `build_topological_crystal` 已支持 `xup=None, yup=None, ydn=None` 显式覆盖
> （`topo_modeler/builders/crystal.py:41-44`），模板传入的是 §4.5 的参考公式值。
> 本表其余行（`straight_waveguide.py`）不在本轮核验范围内，**不要据本表推断
> `UnitAntenna` 的可用性** —— 它的弯折路径偏移多边形缺陷已在同轮修好（§4.6 / §6.5），
> `bend_angle` 语义已查清并实现（张角口径，参考「120D」= `120`），
> **新臂方向的真机复验也已完成**（§4.7 / §4.8：AB 14 OK / 0 FAIL）。

### 6.2 其它已核实问题（本次核查新增）

| 位置 | 问题 | 影响 | 建议修法 |
|---|---|---|---|
| `topo_templates/*.py` 构造期 `self.modeler.set_parameters({...})` | `TopoModeler.set_parameters(params)` 内部调用 `self.app.set_parameters(params)`；而 `cst_solver` 的 `set_parameters(name, value, log_flag=0)` 需要**两个**位置参数（批量接口叫 `paras(name, value)`） | CST 可用时，`StraightWaveguide(...)` / `UnitAntenna(...)` **在构造阶段就 `TypeError`**（缺 `value`），比 §6.1 更早触发 | 在 `topo_modeler/modeler.py` 里改为 `self.app.paras(params, None)`（`paras` 的 docstring 明确支持 dict），或逐项 `self.app.para(k, v)`。**✅ 已按此修（2026-09-17 核对 `modeler.py:319`）** —— P4/V1 真机上 `UnitAntenna(...)` 构造成功，未再出现该 `TypeError` |
| `topo_templates/*.py` 的 `run()` | 调用 `self.app.start_solver()`，但 `cst_solver` 里**没有** `start_solver` 方法，求解器入口是 `SolverMixin.run()` | `wg.run()` → `AttributeError: 'setup' object has no attribute 'start_solver'` | 改为 `self.app.run()`（`TopoModeler.run()` 用的就是它） |
| `topo_templates/*.py` 的 `build_all()` 缺少收尾校验 | 建完直接返回，不检查 CST 消息；而库**不保证**把 CST 报错抛成异常（`add_to_history` 只是下发 VBA） | 「跑通」不等于「建对」，可能静默产生空集布尔结果 | 在 `build_all()` 末尾（或提供 `verify()`）读 `app.cst_file.get_messages()`；文档/示例里明确这一步为验收动作 |
| `topo_templates/*.py` 的 `save()` | 直接调 `self.app.cst_file.save(...)`，绕过 `setup` 封装的 `save()`；`self.width` 接受后从未使用；`a/h/l1/l2/e1/e2` 在 `__init__`（`set_parameters`）与 `_define_all_params()`（`app.para`）被定义两次 | 风格/可维护性问题，不影响几何正确性 | 按 `docs/next_plan/` 的 P2 条目逐步收敛到 `app.save(path)`；`width` 要么实现要么标注 deprecated |

### 6.3 包命名风险 —— ✅ **已解决**（T10，2026-09-15）

| 项 | 说明 |
|---|---|
| 原风险 | 旧包名 `templates` 是极其通用的名字。一旦本库安装进 site-packages，极可能与第三方包**重名**，届时 `import templates` 命中的是谁取决于 `sys.path` 顺序，属于难以排查的隐性故障 |
| 处置 | **已完成改名**：`templates/` → **`topo_templates/`**（`git mv`，历史保留）；旧名 `templates/` 保留为**转发 shim**（`templates/__init__.py`，导入即发 `DeprecationWarning`），约定**一个版本周期后移除** |
| 连带改动 | `pyproject.toml` 的 `packages.find`（新增 `topo_templates*`，**并保留** `templates*` 以便 shim 一起分发）；全仓 35 个文件里的 167 处引用统一改名；`docs/packages/templates.md` → `docs/packages/topo_templates.md`；`scripts/_api_stats.py` 的扫描目标改名 |
| 移除计划 | 下一个版本周期删除 shim。到期前的复评登记在 [`../next_plan/stages/08`](../next_plan/README.md) |
| 怎么验 | `python -c "import warnings; warnings.simplefilter('error', DeprecationWarning); import templates"` 应当**报** DeprecationWarning；`import topo_templates` 不应有任何告警 |

### 6.4 透镜模板 —— ✅ **已完成（P5，2026-09-17）**

- `topo_templates/__init__.py` 的 docstring 说的「透镜天线」现在真的有了：
  **`GRINLensAntenna`**（继承 `UnitAntenna`，加 6 个顶点透镜）。
- ✅ `TopoModeler.build_lens()` 已可用（2026-09-15，阶段 6 几何层）：透镜几何在
  `topo_modeler/builders/lens.py`（`GrinLensSpec` / `GrinLensHoles` /
  `build_grin_lens_holes()` / `build_grin_lens()`），与原脚本
  `topo_modeler/lens_build.py` 有**逐点/逐条等价**回归（`topo_modeler/tests/test_lens.py`）。
- ✅ 曾经的缺口「`GRINLensAntenna` 模板本身」和「`method='dxf'` 入口」**都已补上**：
  模板见 `topo_templates/grin_lens_antenna.py`，DXF 入口见
  `builders/lens.py::build_grin_lens_from_dxf()`（`holes` 改成可选，现成 DXF 不回头算几何）。
  真机（只建模、不求解）**10 OK / 0 FAIL**，见
  [`../validation/p5_grin_lens_evidence.md`](../validation/p5_grin_lens_evidence.md)。
- 沙盒脚本 `topo_modeler/lens_build.py` / `lens_build_standalone.py` **保留**（notebook 仍在 `exec` 它），
  但库侧不再依赖它们。按 [`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md) §10.7，
  实验性代码仍应先留在沙盒、不直接进 `topo_templates/` 公开路径。

### 6.5 `UnitAntenna` 弯折路径下基板/VPC 偏移多边形自交 —— ✅ **已修复（P4/V1，2026-09-17）**

| 项 | 内容 |
|---|---|
| 原现象 | 阵列范围已按参考工程修好，但 `UnitAntenna` **当时仍无法建模**：`build_all()` 在 `build_substrate` 一步报 `(&H8000ffff) The specified curve is not closed and planar.`（`ExtrudeCurve .Create`） |
| 位置 | `mesh_grid/tri_grid/topo_path.py` 的 `build_substrate_polygon()` 与 `build_vpc_area_polygon()` —— 两条偏移链**只在 y 方向偏移**（`py ± y_margin`） |
| 根因 | ① 直线路径下没问题（直波导模板就是这么用的），**拐弯路径**上两条链互相穿插 → **自交多边形** → CST 拒绝拉伸；② 更本质：**恒定宽度的整条带在折回路径上会自覆盖**，单个简单多边形根本无法表达 |
| 证据（原） | 跳过基板、直接调用 `build_vpc_regions(app, path)` 也抛同一个异常 ⇒ 缺陷在**共享的多边形构造**里，不只是 `substrate.py` |
| 处置 | ✅ **已修**：偏移改为**按段法向 + miter 连接**；新增 `build_segment_band_polygons()`（**每段一个平行四边形 + 拐角补块**，只补外侧）；`builders/substrate.py` 与 `builders/vpc_region.py` 改为**逐段建模 + 布尔并** |
| 向后兼容 | 直线路径只有一段 ⇒ 产物与旧实现**逐字节相同**（单测钉住）；180° 折返抛明确 `ValueError` |
| 适用条件 | 拐角补块基于「带宽远小于段长」的常规用量；**超宽带宽**自交仍可能出现，属输入不当，**不在保证范围内** |
| 真机验收 | ✅ **已通过**（2026-09-17，CST 2026）：`python scripts/verify_antenna_mapping.py --topology AB`（BA 同理）两次各 **8/8**（旧臂方向），`build_substrate` 与 `build_vpc_regions` 均**成功且 0 条 CST 消息**；落盘 `xup/yup/ydn` AB `25/14/14`、BA `26/14/14`。**改臂方向后又复跑一次**：AB 单拓扑 **14 OK / 0 FAIL**（新增臂端/参数引用/闭合性审计项），新路径 `[(0,-1),(0,18),(14,18)]` 上臂端与参考工程逐位一致。完整证据见 [`../validation/p4_real_machine_evidence.md`](../validation/p4_real_machine_evidence.md) §4.3/§4.4/§8.7 |

配套事实：**参数映射**（§4.5）与**路径方向语义**（§4.7）是两件独立的事 ——
语义现已离线查清并按「张角口径」实现（`bend_angle` = 两侧臂夹角，参考「120D」= `120`，
臂端与参考工程 `px3/py3` 逐位相同，AB/BA 互为镜像），
**新臂方向的真机复验也已完成**（§4.8：AB 14 OK / 0 FAIL）。
另：P4 其余条目（V2 远场、V3 谐振位置、V7 真实 runner、V9 MCP 真机闭环）
中，**V4/V6 已完成**，V1 见 §4.5/§4.8，其余仍未做（需真实求解）。

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
