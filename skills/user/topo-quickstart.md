---
name: topo-quickstart
description: '用 topo_templates / TopoModeler / builders 建 AB/BA 域壁器件及已实现的直波导、单元天线、GRIN 透镜天线、多端口天线、MZI 开关、功分器；核对参考 notebook 的几何口径、装配顺序与离线拓扑正确性。修改库源码应读开发者工作流；泄漏波、C6 环和未实现变体须先查看统一计划。'
applyTo: "**/*.py"
---

# 拓扑光子晶体建模（TOPO 模块）

> **这份技能的定位**：**专为"把拓扑光子晶体模型建对、建好"服务**。
> 它不讲泛泛的 CST 用法，而是回答三个 TOPO 专有问题：
> **(1) 一个域壁器件由哪些拓扑结构组成、每一块由哪几行代码生成；**
> **(2) 参数怎么选才能得到你要的那条域壁（相序 / 覆盖 / 端口）；**
> **(3) 怎么在不开 CST、不跑仿真的情况下证明"域壁真的建出来了、相没错"。**
>
> 本文件已把**参考工程（`D:\成电博士生涯\拓扑光子晶体模型\硅基`）的建模逻辑**与
> **TPC 现有 API 的口径**做过逐值比对（含源码级实测），结论直接写在这里；
> 只有需要更细的 API 时才去读源码。
>
> **对象**：`topo_templates` + `topo_modeler` + `mesh_grid.tri_grid.TopoPath`。
> **核心族**：域壁直波导 + 单元天线（含馈源与波端口口径）；其它族见 §13。

---

## 0. 30 秒上手（可直接复制）

```python
# 前提：仓库根目录已 `pip install -e .`；环境变量 CST_INSTALL_PATH 已配；
#      模板工程 tmp.cst 在**当前工作目录**（相对路径按 CWD 解析）。
from topo_templates import StraightWaveguide, UnitAntenna

# ① 直波导 AB（= 参考工程 直波导\AB\AB_feed.ipynb 的口径）
wg = StraightWaveguide(topology='AB', length=18, width=14,
                       lattice_constant=0.2425, height=0.25,
                       large_hole_ratio=0.65, small_hole_ratio=0.35,
                       feed_type='ab_elliptical',
                       freq_range=(300, 380), monitors=('E',),
                       template_cst='tmp.cst', output_path=r'D:\out\wg_AB.cst')
wg.preview()        # matplotlib 预览（不需要 CST）
wg.build_all()      # 12 步：参数→材料→相区→晶体→晶体∩相区→馈源→波导→镜像→2 端口→整合→求解器
wg.save()           # 保存 .cst

# ② 直波导 BA（参考工程 直波导\BA\优化后的\BA_feed_epc.ipynb）
#    ⚠ 默认 feed_type='ab_elliptical' 不会随 topology 变，BA 必须显式换 BA 族馈源
wb = StraightWaveguide(topology='BA', feed_type='ba_tapered',
                       feed_params={'x01': 0, 'wf2': 0.2, 'lf4': 0.2, 'lf5': 3.0, 'lf6': 0.2},
                       output_path=r'D:\out\wg_BA.cst')
wb.build_all(); wb.save()

# ③ 单元天线 120°（参考工程 普通单元天线\Ant1_D_BA_120_Feed_antenna-DF）
ant = UnitAntenna(bend_angle=120,            # 张角：单臂偏角 = bend_angle/2
                  straight_length=18,        # 直段（= 参考的 x1）
                  arm_length=14,             # 臂长（= 参考的 y1）
                  topology='BA',             # 天线默认 BA
                  radiator=None,             # 或 'cylinder'
                  freq_range=(300, 380), monitors=('E', 'Farfield'),
                  output_path=r'D:\out\ant_BA_120.cst')
ant.build_all(); ant.save()
```

**建完立刻做两件事**：§8 的**离线拓扑自检**（秒级、不用 CST），再按 §10 验收。

---

## 1. 面向 AI 的省 token 铁律

1. **本文件是 TOPO 模块的唯一入口。** 先读这里；只有需要「某个函数的完整签名/默认值」时才去读源码。
2. **禁止通读 TPC 包**，也**禁止通读参考 notebook**（单个 1–17 MB，且里面 90% 是 matplotlib 预览与结果分析）。
3. 参考 notebook 的正确读法是**只抽 code cell**：

   ```python
   import json, io, sys
   nb = json.load(io.open(r'<某.ipynb>', encoding='utf-8'))
   for i, c in enumerate(nb['cells']):
       if c['cell_type'] == 'code':
           print(f'### CELL {i} ###'); print(''.join(c['source']))
   ```
   参考 notebook **没有 markdown cell**，作者的说明全在 `#` 注释里，别去找。
4. 参考工程的**权威参数表**不是 notebook 里的 Python 变量（常常与 CST 注册值不一致），而是
   `<工程名>\Model\Parameters.json`；权威构序是 `<工程名>\Model\3D\ModelHistory.json`；
   端口位置/法向是 `<工程名>\Model\3D\anchorpoints.json`。
5. 需要 CST 封装层签名时读 `cst_solver/setup.pyi`（一屏读完）。
6. `topo_templates` / `topo_modeler` 的公开签名已在本文件 §6–§7 汇总，**不要重复去读源码**。
7. **判断"这模型建对了吗"不要去读源码**——跑 §8 的自检脚本。

---

## 2. 四条硬约定（违反必出问题）

1. **z 平面 / 绕向**：所有多边形必须 **CCW**（有向面积 > 0），配合内部 `translate -h/2`。
   `ExtrudeCurve` 沿多边形**法向**拉伸：**CCW → +z，CW → −z**。
   绕向错了 → 实体之间在 z 上差一个 `h` → 布尔求交得**空集且 CST 不报错**（晶体静默消失）。
   > ⚠️ 仅 CCW 还不够：恒定宽度的整条带在**折返路径**上会自覆盖，CST 报
   > `The specified curve is not closed and planar.`。库已改为「逐段四边形 + 拐角补块 + 布尔并」
   > （`TopoPath.build_segment_band_polygons`）—— 你要做的是**不要自己手写整条带多边形**。
2. **布尔语义**（最容易记反的一条，域壁的成败就压在这里）：

   | 调用 | 几何 | 结果存在哪 | 另一个操作数 |
   |---|---|---|---|
   | `app.add(A, B)` | A ∪ B | **A** | B 被删除 |
   | `app.subtract(A, B)` | A − B | **A** | B 被删除 |
   | `app.intersect(A, B)` | A ∩ B | **A** | **B 被消耗**（不能再引用） |
   | `app.insert(A, B)` | **A − B（差集，不是并集！）** | **A** | **B 保留、可继续引用** |

   > `Insert` 是差集这一点被第三方 VBA 速查表写错过（记成并集），并曾导致对照参考工程时误判
   > `VPC-B` 的形状。TPC 源码 `topo_modeler/builders/vpc_region.py` 里引了 CST 官方原文确认。
   > **为什么这条对 TOPO 特别致命**：相区就是靠 `insert` 求补、`intersect` 求交得到的
   > （§3.4）。记反 ⇒ **两种相塌到同一侧、域壁消失**，而 CST 一声不响。
3. **阵列范围**：`xup / yup / ydn` 必须覆盖**整个基板**，不能只按路径推断；并且阵列次数必须写成
   **CST 参数引用**（`int(xup)` / `int(yup/2)` / `int(ydn/2)`），**不许烘成数字**。
   烘了数字 ⇒ 参数表里的 `xup/yup/ydn` 形同备注，**改参数不动几何**。
   `ydn = 1`（或 `yup = 1`）⇒ `int(ydn/2) = 0` ⇒ CST 直接报 `Invalid number of repetitions`。
4. **元规则：CST 不抛异常。** 非法 VBA 可能只写进消息列表；未定义的参数会弹
   **「请输入变量值」模态对话框把脚本挂住**（不是异常）。
   所以：*跑通 ≠ 建模正确* —— 拓扑对不对必须自己证明（§8）。
   > 附带推论：**参数名拼错、少登记一个参数**，症状是「卡住」，不是报错。

---

## 3. TOPO 核心：拓扑光子晶体是怎么建出来的

> 这一节是本文档的**主干**。读懂了它，后面几节只是查表。

### 3.1 一个成品器件的解剖

```
        ┌────────────────────── 器件本体 = 图形化硅（没有额外整块基板）──────────────────────┐
        │                                                                                  │
 端口1 ─┤ 铜波导 ─ 探针 ─┤   B 相光子晶体（路径**上**半区 = vpc_B ∩ g1B）                    │
        │                 ├───────────────────────────────────────────────                  │
        │                 │   ★ 域壁：就是 TopoPath 那条路径 —— 器件功能沿它发生 ★             │
        │                 ├───────────────────────────────────────────────                  │
        │                 │   A 相光子晶体（路径**下**半区 = vpc_A ∩ g1A）                    │
        └──────────────────────────────────────────────────────────────────────────────────┘
```

四条要点（每一条都有对应代码，见后续小节）：

1. **域壁 = 路径**。`TopoPath` 的每一段就是 A/B 两相的分界线；器件要"从哪走到哪"，路径就得画到哪。
2. **A / B 相 = 同一套三角孔阵列的两种排布**，差别**只在**「朝上孔 / 朝下孔」谁用大孔谁用小孔。
3. **相区**：`vpc_A` = 路径**下**半区，`vpc_B` = 路径**上**半区（方向不能反，见 §5.2）。
4. **成品 = `vpc_A` ∪ 探针 ∪ `vpc_B`**，其中 `vpc_A`/`vpc_B` 已各自被 `∩` 上对应相的晶体阵列裁成图形化硅。
   **刻意没有**一块独立的整块 substrate —— 多一块未图形化的同材料硅，会**把光子晶体的孔洞全部填平**。

### 3.2 超元胞：6 个三角孔是怎么来的（11 步，代码级）

三角晶格的"单元"是**边长 a 的等边三角形**。把「朝上大三角 + 朝下大三角」拼成一个菱形，在其中各挖一个
**三角孔**，再绕 z 轴 **120° 复制 2 次** ⇒ 3 个菱形 = **一个六孔超元胞**（六方单元）。

`build_topological_crystal()` 对每一相（`tick` = `'A'` / `'B'`）执行同一串 11 步（已逐条实测确认）：

| # | CST 调用 | 关键参数 |
|---|---|---|
| 1 | `triangle('a','h', center=center_up, theta=[0,0,0], name='g1X')` | 朝上大三角，边长 **a** |
| 2 | `triangle('a','h', center=center_dn, theta=[0,0,180], name='g2X')` | 朝下大三角，边长 **a** |
| 3 | `triangle(up_hole,'h', center=center_up, theta=[0,0,0], name='tri_up_X')` | 朝上**孔** |
| 4 | `triangle(dn_hole,'h', center=center_dn, theta=[0,0,180], name='tri_dn_X')` | 朝下**孔** |
| 5 | `add('g1X','g2X')` | 结果留 `g1X`，`g2X` 被删（硬约定 2） |
| 6 | `add('tri_up_X','tri_dn_X')` | 两孔并成一个挖孔工具 |
| 7 | `subtract('g1X','tri_up_X')` | **挖孔**；结果留 `g1X`，孔工具被删 |
| 8 | `rotation('g1X', angle=[0,0,120], repetition=2, copy=True, unite=True)` | ⇒ **6 孔超元胞** |
| 9 | `translate('g1X', ['a','0','0'], repetitions='int(xup)')` | +x 阵列 |
| 10 | `translate('g1X', ['0', f'{y_margin}*2', '0'], repetitions='int(yup/2)')` | +y 阵列（**步长 = 2·行距**） |
| 11 | `translate('g1X', ['0', f'-{y_margin}*2', '0'], repetitions='int(ydn/2)')` | −y 阵列 |

两个中心（与参考工程逐位一致，`a` 为晶格常数参数名）：

```python
center_up = ['-a/2', 'sqr(3)/2*a-a/sqr(3)', '-h/2']   # 朝上三角形中心
center_dn = ['0',    'a/sqr(3)',            '-h/2']   # 朝下三角形中心
```

> **为什么 y 的复制次数要除以 2**：阵列步长是 `e2*2`（`e2 = a·√3/2` 是行距），
> 一次复制跨**两行**三角孔；所以 `yup` 记的是"行数"，实际复制 `int(yup/2)` 次。
> **为什么孔是三角孔不是圆孔**：`l1`/`l2` 是**等边三角孔的边长**（外接圆半径 `l/√3`），
> 核心族里根本没有孔半径参数（`r1/r2` 只出现在 GRIB 透镜族的六边形上）。

### 3.3 两种相（A / B）与域壁判据

同一个超元胞，**把两个孔的尺寸对调**就得到另一种相：

| | 相 A（`tick='A'`） | 相 B（`tick='B'`） |
|---|---|---|
| 朝上孔（`tri_up_*`） | `l[i]` | `l[1-i]` |
| 朝下孔（`tri_dn_*`） | `l[1-i]` | `l[i]` |

`i` 是相序号的循环下标（A→0、B→1）。**相区配对是固定的**：`vpc_A ↔ g1A`、`vpc_B ↔ g1B`。
因为沿路径两侧的孔排布互为镜像，路径上就出现一条区别于体态的界面通道 —— 这就是域壁波导的工作原理；
库自己的说法是：相序一错，**「A/B 相整体反相（域壁消失）」**。

**判据（唯一权威陈述）** —— 设 P1 =「朝上三角孔是大孔」：

> **AB ⇔ P1 在域壁的 +y 侧、P2（朝上孔是小孔）在 −y 侧。**
> **BA ⇔ P1 在 −y 侧、P2 在 +y 侧。**

等价表述（可交叉校验，见 §5.3）。

> ⚠️ **"AB/BA 互为镜像"这句话在直波导族里是错的**：两者构序逐字节相同，
> 只有**孔大小赋值**（直波导）或**区域/路径侧**（单元天线）不同。按"镜像"理解会把器件在 y 方向整体镜像。

### 3.4 相区（VPC-A / VPC-B）：怎么切、怎么裁

**区域本身**（`build_vpc_regions`）：

* `vpc_A` = 路径**下**半区，`vpc_B` = 路径**上**半区。`y_margin` 是半宽（不是"扩展量总数"）。
* 生成方式是**逐段一个四边形 + 拐角补块 + 布尔并**，不是"一条整带多边形"——

  ```python
  rings = path.build_segment_band_polygons(y_margin=..., prefix='p', side='lower')
  # 每段：polyline(ring) → extrude(..., thickness=height) → translate(z = -height/2)
  # 最后：add(solid_0, solid_1); add(solid_0, solid_2); ...
  ```
  原因见 §2 硬约定 1 的 ⚠️：恒定宽度的整条带在折返路径上会自覆盖，CST 直接拒绝。
  **直线路径只有一段 ⇒ 退化成单个多边形。**

**裁剪成图形化硅**（`intersect_crystal_with_vpc`）：操作数顺序与参考工程一致 ——
`vpca ∩ g1A`、`vpcb ∩ g1B`。因为 `Intersect` 结果留第一个操作数，
**保留下来的是 VPC 区域名，晶体阵列名被消耗** —— 之后要引用硅本体，用的是 `vpc_A` / `vpc_B`。

**整合**：`add(vpc_A, feed)` / `add(vpc_A, vpc_B)` ⇒ 一块名为 `vpc_A` 的图形化硅。

### 3.5 阵列范围：为什么必须覆盖整块板

* `xup` 只影响 +x 复制次数；`yup` / `ydn` 分别管 +y / −y，且都要 **≥ 2**（否则 `int(·/2)` 取整成 0）。
* 参考工程与模板的取值公式（逐值对齐）：

  | 器件 | `xup` | `yup` = `ydn` |
  |---|---|---|
  | 直波导 | `x1 + int(y1/2)`（= `length + int(width/2)`）= 25 | `y1` = `width` = 14 |
  | 单元天线 AB | `straight_length + int(arm_length/2)` = 25 | `arm_length` = 14 |
  | 单元天线 BA | 上面 **+1** = 26 | `arm_length` = 14 |

* **不要用 `path.get_array_range()` 推**（实测值见 §5.4）。
* 覆盖不全的症状：晶体没铺满板 / 分支上的晶体被裁掉 / `Invalid number of repetitions`。

### 3.6 多域壁器件（MZI / 功分器）的相区构造 —— 与单域壁**不是一回事**

单域壁器件（直波导 / 单元天线）的"下"半区就是整个 A 相。**Z 型折叠 / 分束器件有多条域壁，
A 相区是两个多边形的并集**，不能用"路径下侧"一句话描述。参考工程 `MZI-BA.ipynb` 的写法：

```python
# ① A 相工具零件 1：主路径以上（一直到板顶）
area1 = [['p1x','p1y'], ['p2x','p2y'], ['p3x','p3y'], ['p4x','p4y'],
         ['p5x','p5y'], ['p6x','p6y'], ['p6x','ymax_up'], ['0','ymax_up'], ['p1x','p1y']]
# ② A 相工具零件 2：下臂与轴线之间那一段
area2 = [['p2x','p2y'], ['p3x','-p3y'], ['p4x','-p4y'], ['p5x','p5y'], ['p2x','p2y']]
# ③ 并成一个 A 相工具，再求补 / 求交
app.add(...area1...); app.add(...area2...)
app.add('area1', 'area2')            # 结果是「A 相工具」
app.insert('vpcb', 'area1')          # Insert 是差集 ⇒ vpcb = 板 − A 相 = **B 相**
app.intersect('vpca', 'area1')       # ⇒ vpca = **A 相**（工具还留着，能接着用）
```
（对照 `硅基\参杂控制\_work\build_cst_nb.py` 的 C3 单元。）

**库提供两个机制，都不是上面这个**：

| 机制 | 相区定义 | 适用 |
|---|---|---|
| `build_vpc_regions(path)` | **一条**路径的逐段上/下半带 | 单域壁（直波导、单元天线、单条折叠路径） |
| `build_vpc_regions_multi(paths)` | 每条路径各做上/下半带，然后**按侧全局并**（"所有路径的下侧"并在一起 = A） | 多分支器件；这是**全局上下划分**，≠ 参考的"两多边形之并" |

> ⇒ 多域壁器件**优先用 `MZISwitch` / `PowerDivider` 模板**（它们把相区逻辑写进去了）。
> 要自己搭多域壁器件的相区，就照上面参考写法手搓，**并且在建模前跑 §8 的自检**——
> 相区定义选错是"能跑、看起来对、物理上错"的典型来源。

### 3.7 因果链（这张图就是 §11 报错表的组织方式）

```
参数  →  路径（= 域壁）  →  相区（vpc_A/B）  →  晶体阵列（两种相）  →  裁剪（晶体∩相区）
      →  馈源  →  铜波导  →  镜像  →  端口  →  整合  →  求解器
```

**任何一步的输入错了，症状都在后面才出现**：参数少登记 ⇒ 后面卡住；
相序错 ⇒ 求解器正常但器件不导通；阵列范围小 ⇒ 晶体缺一块。
所以排错要**沿链回查**，而不是只看报错那一步。

---

## 4. 三层入口：先选层，再动手

| 层 | 入口 | 什么时候用 | 代价 |
|---|---|---|---|
| **① 模板层**（推荐起点） | `topo_templates.{StraightWaveguide, UnitAntenna, GRINLensAntenna, MultiPortAntenna, MZISwitch, PowerDivider}` | 器件形状就是这几种标准件 | 形状被模板限定 |
| **② Modeler 层** | `topo_modeler.TopoModeler` + `mesh_grid.tri_grid.TopoPath` | 走标准流水线但形状自定义 | 要自己写路径与参数 |
| **③ Builder 层** | `topo_modeler.builders.*` | 只要一两个部件，或要插进自己的流程 | 全都要自己编排 |

三层是**叠加**的（模板内部是 Modeler，Modeler 内部是 builders）。

> ### ⚠️ 不要用 `TopoModeler.build_all()` 直接出成品
> `TopoModeler.build_all()` 的顺序是
> `substrate → vpc_regions → crystal → feed → waveguide → ports → solver`，
> 它**不做晶体∩相区裁剪**、**不做右端镜像**、**不做 `vpc_A+feed+vpc_B` 整合**，
> 并且**会额外建一块整幅未图形化的 substrate** —— 那块硅与图形化区域在物理上重叠，
> **会把光子晶体的孔洞全部填平**（库自己在 `straight_waveguide.py` 里写明了这个教训）。
>
> **成品请用模板层**；要自定义形状就照 §7.2 的 Modeler 手动顺序逐步调用（显式补上裁剪与镜像）。

---

## 5. 参数口径表（参考工程 → TPC）

单位一律 **mm / GHz / ns**。参考工程的全部 notebook 共用同一套晶格口径。

### 5.1 晶格与孔（全库一致）

| 意义 | 参考工程 CST 参数 | 数值 / 表达式 | TPC 里的对应 |
|---|---|---|---|
| 晶格常数 | `a` | `0.2425` | `lattice_constant=0.2425` → `app.para('a', …)` |
| 硅片厚度 | `h` | `0.25`（z 向，实体居中于 `[-h/2, +h/2]`） | `height=0.25` |
| 半格偏移 | `e1` | `a/2 = 0.12125` | 自动 `para('e1', a/2)` |
| 行距 = 三角高 | `e2` | `a/2*sqr(3) = 0.210011160…` | 自动 `para('e2', a/2*sqr(3))` |
| **大孔边长** | 见 §5.2 | `0.65*a = 0.157625` | `large_hole_ratio=0.65` → `l1` |
| **小孔边长** | 见 §5.2 | `0.35*a = 0.084875` | `small_hole_ratio=0.35` → `l2` |

> **孔是三角形，不是圆孔。** `l1`/`l2` 是**等边三角孔的边长**（外接圆半径 `l/√3`），
> 不是半径也不是直径；核心族里根本没有孔半径参数。
> **没有 `l = a` 的孔**：超元胞的大三角用边长 `a`，孔严格更小（`0.65a` / `0.35a`）。

### 5.2 孔尺寸命名：这里是**唯一的同名不同义**重灾区 🔴

| | 参考工程（`硅基` notebook） | TPC 库 |
|---|---|---|
| `l1` 的含义 | **A 相「朝上」那个孔**（按位置命名），大小**随拓扑交换** | **恒为大孔**（`large_hole='l1'`），与拓扑无关 |
| `l2` 的含义 | **A 相「朝下」那个孔** | **恒为小孔**（`small_hole='l2'`） |
| 直波导 AB | `l1 = 0.35a`（小）、`l2 = 0.65a`（大） | `l1 = 0.65a`、`l2 = 0.35a` |
| 直波导 BA | `l1 = 0.65a`、`l2 = 0.35a` | 同上（靠 `topology` 分支换分配） |

参考工程的绑定（`ModelHistory.json` 逐条核实过）：
`tri_up_A → l1`、`tri_dn_A → l2`、`tri_up_B → l2`、`tri_dn_B → l1`。

**因此：当你复用参考工程的参数名/数值时，必须显式交换**，否则 **A/B 相整体反相、域壁消失**：

```python
ca, cb = build_topological_crystal(
    app, path, topology='AB',
    large_hole='l2', small_hole='l1',      # ← 复用参考工程口径时必须写这一行
    xup='xup', yup='yup', ydn='ydn')
```

参考工程里已经有人在 TPC 上踩过并写下了结论（`硅基\参杂控制\_work\build_cst_nb.py`）：
> 「参考工程是「A 相：上孔 l1 小 / 下孔 l2 大」，而 TPC 的默认假设是 `large_hole='l1'`
> ⇒ 这里必须显式交换，否则 A/B 相会整体反相（域壁消失）。」

**不要「顺手改正」TPC 里看起来反了的 AB/BA 分支**（`builders/crystal.py` 的 `hole_sizes`）——
它看着反，实际是对的，源码注释也禁止改。

> **关键区分**：`large_hole` / `small_hole` **只跟"你用的参数名口径"有关，不跟拓扑有关**。
> 用 TPC 口径（`l1`=大孔）就**不要**传这两个参数；用参考工程口径（`l1`=A 相朝上孔）才传
> `large_hole='l2', small_hole='l1'`。**两者同时用会把相再翻回去**（等价于整体反相）。
>
> 附带的两个陷阱：
> * `l1`/`l2` **永远不能按字面读成「大/小」**。参考工程 `短探针\short.ipynb` 里 Python 变量与 CST
>   参数名就是**互相反的**；连 `MZI-BA.ipynb` 自己都注册了 AB 形状的 `l1/l2`。
> * 参考 notebook 里的 matplotlib 预览函数 `plot_power_divider()` **本地硬编码** `l1 = 0.65*a`，
>   于是**每一个预览图都画的是 BA 图案** ⇒ **预览不能用来确认拓扑**（§8 才是可靠办法）。

### 5.3 AB / BA 不变式与等价表述

见 §3.3 的判据。等价表述（可交叉校验）：

| 说法 | AB | BA |
|---|---|---|
| 参考直波导里 CST `l1`（绑在 `tri_up_A`） | `0.35a`（小） | `0.65a`（大） |
| 参考单元天线里 `l1` | `0.65a` | `0.65a`（**值相同**，靠区域/路径侧区分） |
| 第二段路径的方向（`py3` 符号） | `+e2*y1`（`turn(+60)`） | `−e2*y1`（`turn(−60)`） |
| 馈源 / 铜波导**中线 y** | `e2/2 = +0.105` | `0` |
| 参考直波导里 `vpca` 是 | −y 半区 | −y 半区（区域划分不变，**只换孔大小**） |

### 5.4 路径与阵列范围

| 意义 | 参考工程表达式 | 计算值（a=0.2425, x1=18, y1=14） | TPC 模板的等价写法 |
|---|---|---|---|
| 路径起点 | `px1 = 0`, `py1 = 0` | `(0, 0)` | `TopoPath.builder(a).start(0, 0)` |
| 直段终点 | `px2 = px1 + x1*a`, `py2 = py1` | `(4.365, 0)` | `.move(length, 'c')` → `p2x/p2y` |
| 拐弯终点 | `px3 = px2 + y1*e1`, `py3 = py1 ∓ y1*e2` | `(6.0625, ∓2.940156)` | `.turn(±60).move(arm_length, 'along')` |
| y 边界 | `ymax_up = +e2*y1`, `ymax_dn = −e2*y1` | `±2.940156` | 相区半宽 `y_margin = f'{width}*e2'` |
| **x 方向阵列** | `xup = x1 + int(y1/2)`（BA 天线 `+1`） | `25`（BA 天线 `26`） | 见 §3.5 表 |
| **y 方向阵列** | `yup = ydn = y1` | `14` | `width` / `arm_length` |

> ⚠️ **`xup = x1*2 + x2 - int(y1) + 1` 这个公式在核心族里根本没有出现**（`x2` 在参考工程里是死参数）。
> 别按它推导。
> ⚠️ 阵列步长是 `a`（x）、`e2*2`（y）；`yup/ydn ≥ 2` 是硬前提。
> ⚠️ **不要用 `path.get_array_range()` 推阵列范围**。实测（本机离线跑 `TopoPath`）：
> `StraightWaveguide` 形状的直线路径给 `(19, 1, 1)`，`UnitAntenna` 形状的折弯路径给 `(33, 1, 15)`
> —— 两者的 `yup` 都是 `1` ⇒ `int(yup/2) = 0` ⇒ **都会直接触发 `Invalid number of repetitions`**，
> 而且 x/y 范围都覆盖不到基板。（`topo_templates/unit_antenna.py` 的注释里记的是 `(26, 16, 1)`，
> 那是**旧路径形状**（`bend_angle` 语义改动前）的取值，别再引用。）

### 5.5 馈源 / 铜波导参数（两种族别混用）

| 参数 | 值 | 属于 | 含义 |
|---|---|---|---|
| `x0` | 4 | AB 族（`ab_elliptical`，实体名 `feed1`） | 探针起点（晶格数） |
| `wf1` | 0.2 | AB 族 | 探针宽度 |
| `lf1` / `lf2` / `lf3` | 0.2 / 3.0 / 0.2 | AB 族 + 波导范围 | 探针长度段 / 椭圆过渡半轴 / 长度段 |
| `x01` | 0 | BA 族（`ba_tapered`，实体名 `feed2`） | 三角底部半格修剪 |
| `wf2` | 0.2 | BA 族 | 颈部宽度 |
| `lf4` / `lf5` / `lf6` | 0.2 / 3.0 / 0.2 | BA 族 + 波导范围 | 颈长 / 椭圆过渡段长 / 铜管端口段长 |
| `wg_a` | **0.7312** | 两族 | 铜波导内腔 **z 向高度**（宽的那一维） |
| `wg_b` | **0.3756** | 两族 | 铜波导内腔 **y 向宽度** |
| `wg_t` | 0.2 | 两族 | 铜壁厚（四边） |

铜波导（空心 = 外方体 − 内方体）的 x 范围：

| 族 | x 范围 | 中线 y |
|---|---|---|
| AB | `[-lf1-lf2-lf3, -lf1]` | `e2/2 = 0.105` |
| BA | `[-lf5-lf6-lf4, -lf4]` | `0` |

> `x_cyl*` / `w_cyl*` / `r_cyl` 只属于参考工程的**圆柱辐射体**天线变体（TPC 用
> `radiator='cylinder', radiator_radius=0.3`）。
> `tx1/ty1` 是参考 BA 探针的「入口优化块」，TPC 的 `ba_tapered` 默认 `add_optimizer=True` 会自动补。

### 5.6 频段 / 监视器 / 求解器 / 材料

| 项 | 值 |
|---|---|
| 频段 | `300–380 GHz`（`fmin`/`fmax`）；单元天线个别族用 `280` 起 |
| 场监视器 | `E` 场，参考写 `310:2:320`（BA 探针族 `302:2:322`）；2-D 截面用 `monitor2d`（z=0） |
| 远场 | 天线族加 `Farfield`（TPC：`monitors=('E','Farfield')`） |
| 求解器 | `TD-S` / `Method "Hexahedral"` / `MeshAdaption "False"` / `SteadyStateLimit "-30"` |
| 硅 | `Silicon (lossy)`：εr = 11.9，κ = 2.5e−4 S/m |
| 铜 | `Copper (annealed)`：κ = 5.8e7 S/m |
| 单位/边界 | mm / GHz / ns；边界 `expanded open`；**Zsymmetry "magnetic"** |

> **单位与边界不在 notebook 里设**，全靠打开模板工程 `tmp.cst`（参考工程里是
> `use template: Antenna - Waveguide.cfg` + `define boundaries`）。
> ⇒ 换模板工程就等于换单位与边界，务必确认。
> ⚠️ **不要相信 `.cst` 目录里 `Model.mod` 头部声明的单位**：参考工程里出现过声明 mm 却把端口写成 µm 数值、
> 同一参数族的两个工程端口盒**恰好差 1000 倍**的情况。
> **可靠的交叉校验**：端口口径必须等于 `wg_b × wg_a`。

---

## 6. 模板层：签名与逐步骤行为

### 6.1 `StraightWaveguide`

```python
StraightWaveguide(topology='AB', length=18, width=14,
                  lattice_constant=0.2425, height=0.25,
                  large_hole_ratio=0.65, small_hole_ratio=0.35,
                  feed_type='ab_elliptical',
                  x0=4, wf1=0.2, lf1=0.2, lf2=3.0, lf3=0.2,
                  wg_a=0.7312, wg_b=0.3756, wg_t=0.2,
                  freq_range=(300, 380), monitors=('E',),
                  template_cst='tmp.cst', output_path=None,
                  feed_params=None)
```

* `length` = 参考的 `x1`（直段格数），`width` = 参考的 `y1`（也＝y 向阵列次数）。
* 路径是 `start(0,0).move(length, 'c')`（**不是** `start(0,-1).move(length+1)`，那样会多一格）。
* `feed_params` 只在 `feed_type='ba_tapered'` 时可用，允许键 = `x01 / wf2 / lf4 / lf5 / lf6`；
  AB 族的 `x0/wf1/lf1/lf2/lf3` 直接是构造参数。**写错键名会 `ValueError`（不静默忽略）。**
* 方法：`preview()`、`build_all()`、`save(output_path=None)`、`run()`、`validate()`、`close()`，支持 `with`。

`build_all()` 的 12 步（对应 §3.7 的因果链）：

| # | 动作 | 不变量 |
|---|---|---|
| 1 | 登记全部 CST 参数（`a h l1 l2 e1 e2`、`p1x…p2y`、`xup yup ydn`、馈源族、`wg_*`） | 后续所有表达式引用的参数**必须先存在** |
| 2 | `build_materials` | `Silicon (lossy)` / `Copper (annealed)` 存在，否则第一条 `extrude` 报材料不存在 |
| 3 | `y_margin = f'{width}*e2'` | 相区半宽覆盖整个 14 行阵列（库默认 `'e2'` 只有一行） |
| 4 | `build_vpc_regions` | **`vpc_A` = 路径下方半区、`vpc_B` = 上方半区**；**本模板刻意不建 substrate** |
| 5 | `build_topological_crystal(topology, xup='xup', yup='yup', ydn='ydn')` | 阵列次数是**参数名** |
| 6 | `intersect_crystal_with_vpc` | `vpca ∩ g1A`、`vpcb ∩ g1B`；**VPC 名保留，晶体名被消耗** |
| 7 | `build_feed`（AB→`feed1`，BA→`feed2`，名字与参考工程一致） | 探针 z 居中 |
| 8 | `build_waveguide`（AB 用默认范围；BA 用 `[-lf5-lf6-lf4, -lf4]`、`y_center='0'`） | 空心铜管 |
| 9 | `mirror(feed, ['p2x/2','0','0'], ['1','0','0'], copy=True, unite=True)`；`wg1` 同 | 右端镜像 |
| 10 | `add_ports_for_straight_waveguide` | 端口 1 = 面 `'10'`，端口 2 = 面 `'22'` |
| 11 | `add(vpca, feed)`；`add(vpca, vpcb)` | 合成一整块图形化硅，名为 `vpc_A` |
| 12 | `configure_solver(freq_range, monitors)` | 频段 + 监视器 + 求解器类型 |

### 6.2 `UnitAntenna`

```python
UnitAntenna(bend_angle=120, straight_length=18, arm_length=14,
            topology='BA', lattice_constant=0.2425, height=0.25,
            large_hole_ratio=0.65, small_hole_ratio=0.35,
            feed_type='ba_tapered',
            radiator=None, radiator_radius=0.3,
            wg_a=0.7312, wg_b=0.3756, wg_t=0.2,
            freq_range=(300, 380), monitors=('E', 'Farfield'),
            template_cst='tmp.cst', output_path=None, feed_params=None)
```

* **`bend_angle` 是张角**（两侧臂夹角）：`120D` ⇔ `bend_angle=120` ⇒ 单臂 `turn(±60)`；
  合法值 = `0` 或 **120 的整数倍**（`60/180/300` 会让单臂落在 30°/90°/150°，不是晶格方向）。
  符号按拓扑取：AB 臂朝 +y，BA 臂朝 −y。
  > 2026-09-17 **之前**它是「单臂偏角」语义；按旧语义传 `60` 会得到「120° 折返天线」而不是 V 形。
* `radiator='cylinder'` 才会在路径末端加圆柱辐射体（`radiator_radius`）。
* 方法：`preview()`、`build_all()`、`save()`、`run()`、`validate()`、`close()`。
* 与 `StraightWaveguide` 的**结构差异（不要当成 bug 去"修"）**：
  `UnitAntenna.build_all` **会建 substrate**、**不做晶体∩相区裁剪**、馈源名恒为 `feed2`、只有 **1 个端口**。
* 它构建的是「BA 探针 + 空心铜波导 + 1 端口」这一支（对应参考工程 `*_Feed_antenna-DF` 变体）；
  参考的 `*_cylinder-DF` 变体（波端口直接建在探针端面、无铜波导）需要 `radiator='cylinder'` 近似，
  或按 §7.3 用 builder 自己接。

### 6.3 其它模板（一句话）

| 模板 | 用途 | 备注 |
|---|---|---|
| `GRINLensAntenna(UnitAntenna)` | 单元天线 + GRIN 透镜 | `lens_method ∈ {'generate','dxf','insitu'}`；`build_all()` = 天线 11 步 + `build_lens()` |
| `MultiPortAntenna` | 3 端口（2 个轴向 + 1 个侧向） | `port_numbers` 必须 3 个；**无 `preview()`** |
| `MZISwitch` | Z 型折叠 MZI（双域壁） | `mzi_type ∈ {'basic','cascade'}`（**两者几何相同**）；`'parallel'/'anti'` 抛 `ValueError`；相区见 §3.6 |
| `PowerDivider` | 1 分 2/3/4/6 | `split_ratio ∈ {2,3,4,6}`；**无 `preview()` / 无 `__repr__`**；相区见 §3.6 |

> 透镜族的孔口径（`LENS_DEFAULTS`、`n_small`/`lx1`/`R_big` 公式）与参考工程**逐值一致**，
> 但**per-arm 透镜定位未实现**（模板只在原点/0° 顶点放一片透镜）。详见 §13。

---

## 7. Modeler / Builder 层

### 7.1 `TopoPath` 路径 DSL 速查

```python
from mesh_grid.tri_grid import TopoPath

path = (TopoPath.builder(a=0.2425, name='p')
        .start(0, 0)                 # 起点（晶格坐标 (r, c)），默认方向 (0, +1)
        .move(18, 'c')               # 沿方向走 18 格；'along' 表示沿用当前方向
        .turn(-120)                  # 转角必须是 60 的整数倍
        .move(14, 'along')
        .build(param_values=None))   # 符号路径必须在这里给 param_values
```

| 方向 token | `(dr, dc)` | 物理角 |
|---|---|---|
| `'c'` `'+c'` `'c+'` | `(0, 1)` | 0° |
| `'r'` `'r+'` | `(1, 0)` | 60° |
| `'rc'` `'r+c-'` | `(1, -1)` | 120° |
| `'-c'` `'c-'` | `(0, -1)` | 180° |
| `'-r'` `'r-'` | `(-1, 0)` | 240° |
| `'-rc'` `'-r+c'` | `(-1, 1)` | 300° |
| `'along'` / `None` | 当前方向 | — |

坐标真源：`x = c·a + r·a/2`，`y = r·a/2·√3`。**路径点就是域壁的折点**——想改域壁形状就改这里。

常用成员：

| 成员 | 说明 |
|---|---|
| `xy` / `lattice` / `lattice_symbolic` / `has_symbols` | 数值/晶格/原始坐标 |
| `get_array_range()` | 仅供推断，**别直接拿去建阵列**（§5.4） |
| `get_bounding_box(margin_c=1, margin_r=1)` | 包围盒 |
| `auto_define_cst_params(app, prefix='p')` | 生成 `p1x/p1y/…`（幂等，多路径要用不同 prefix） |
| `preview(ax=None, show_grid=True)` | matplotlib 预览，**不需要 CST**（⚠ 不能用来确认拓扑，§5.2） |
| `build_segment_band_polygons(y_margin, prefix, side)` | 相区带的逐段四边形（**builders 实际用的就是它**） |
| `is_straight()` / `has_bend()` | 直线 = 点数 ≤ 2；**这决定 `TopoModeler` 的 model_type 推断** |
| `segment_angles()` / `segment_directions()` | 每段角度/方向 —— 与参考工程比对域壁形状时用 |

> ⚠️ 符号路径（`.move('x1', 'c')`）在没给 `param_values` 时，
> `xy` / `lattice` / `get_bounding_box()` / `get_array_range()` / `preview()` **一律抛 `RuntimeError`**
> （不返回占位值）。错误信息都是「符号路径无法…，请提供 param_values」。
> ⚠️ `build_substrate_polygon()` / `build_vpc_area_polygon()` / `get_cst_polygon()` 是**死代码**
> （没有任何 builder 调用）—— 别照着它们写。

### 7.2 `TopoModeler` 手动顺序（要自定义域壁形状时照这个抄）

```python
from mesh_grid.tri_grid import TopoPath
from topo_modeler import TopoModeler
from topo_modeler.builders import build_materials, register_multiport_params

# ① 域壁路径 = 你要的器件形状
path = (TopoPath.builder(0.2425, name='p').start(0, 0).move(18, 'c').build())

m = TopoModeler(template_cst='tmp.cst')      # 无 CST 时只 warnings.warn + app=None（不抛）
m.set_path(path)                             # 自动推断：直线 → waveguide / AB / 2 端口
m.set_topology('BA')                         # 显式覆盖推断（模板不做这一步，见 §9 陷阱 8）

# ② 参数：TPC 口径 = l1 恒为大孔。用参考工程口径则改成 l1=0.35a / l2=0.65a 并见下方 ★
m.set_parameters({'a': 0.2425, 'h': 0.25, 'l1': 0.65*0.2425, 'l2': 0.35*0.2425,
                  'e1': 'a/2', 'e2': 'a/2*sqr(3)',
                  'xup': 25, 'yup': 14, 'ydn': 14})     # ← 阵列次数必须显式登记

# ③ 馈源族参数：**换 feed_type 就必须换登记的那一族**，否则 CST 弹框挂住（§11）
register_multiport_params(m.app, wf2=0.2, lf4=0.2, lf5=3.0, lf6=0.2)   # BA 族
m.app.para('x01', 0)

# ④ 材料必须先建，否则第一条 extrude 报「材料不存在」
build_materials(m.app)

# —— 照 StraightWaveguide 的顺序逐步走（顺序不能换）——
m.build_vpc_regions(y_margin='14*e2')        # vpc_A = 路径下方半区
m.build_crystal(topology='BA',                # TPC 口径：不写 large_hole/small_hole 即为默认
                xup='xup', yup='yup', ydn='ydn')   # ★ 复用参考工程口径时改为
                                                   #   large_hole='l2', small_hole='l1'（§5.2）
m.clip_crystals_with_vpc()                   # ★ build_all() 缺的就是这一步
fp = m.build_feed(feed_type='ba_tapered', name='feed2')
wg = m.build_waveguide(name='wg1', x_min='-lf5-lf6-lf4', x_max='-lf4', y_center='0')
m.app.mirror(fp, ['p2x/2', '0', '0'], ['1', '0', '0'], copy=True, unite=True)
m.app.mirror(wg, ['p2x/2', '0', '0'], ['1', '0', '0'], copy=True, unite=True)
m.add_ports()                                # 直线 → 面 '10' / '22'（天线 → 1 端口）
m.app.add('vpc_A', fp); m.app.add('vpc_A', 'vpc_B')
m.configure_solver(freq_range=(300, 380), monitors=('E',))
m.save(r'D:\out\custom.cst')
```

**`TopoModeler` 关键签名**

| 方法 | 签名要点 |
|---|---|
| `__init__` | `TopoModeler(template_cst='tmp.cst')`；构造函数**从不抛异常** |
| `set_path` / `set_paths` / `add_path` / `remove_path` | 路径状态；`set_paths` 支持多路径（多分支器件） |
| `set_topology` | `'AB'` / `'BA'`，其它抛 `ValueError` |
| `set_parameters` / `set_parameter` | dict 形式走 `app.paras`；单个走 `app.para` |
| `build_substrate(name, height, material, y_margin, paths, **kwargs)` | ⚠ **单路径分支会吞掉 `**kwargs`** |
| `build_vpc_regions(...)` | ⚠ 同上；返回 `(vpc_A, vpc_B)`；多路径相区语义见 §3.6 |
| `build_crystal(topology, lattice, height, large_hole, small_hole, y_margin, **kwargs)` | `**kwargs` 透传 `xup/yup/ydn` |
| `clip_crystals_with_vpc(paths=None)` | 晶体∩相区 |
| `build_crystals_multi(...)` | 多路径版（每条域壁一套 A/B 阵列） |
| `build_feed(feed_type, name, **params)` | 默认：waveguide→`ab_elliptical`，antenna→`ba_tapered` |
| `build_waveguide(name='wg1', material='Copper (annealed)', **params)` | |
| `add_ports(auto=True, waveguide_name=None, **params)` | ⚠ **`auto` 与 `**params` 全被忽略**；直线→2 端口，天线→1 端口 |
| `configure_solver(freq_range=(300, 380), monitors=None, **kwargs)` | |
| `build_all(freq_range, include_feed, include_waveguide, include_ports, **kwargs)` | 只认 `substrate_kw / vpc_kw / crystal_kw / feed_kw / waveguide_kw / port_kw / solver_kw` 七个键；**`output_path=` 会被静默忽略** |
| `save(path)` / `run()` / `validate()` / `close()` | `app is None` 时 `save/run` 抛 `CstOperationError`；`validate()` 返回 dict |
| `preview()` / `read_results(path=None, …)` / `plot_results(…)` / `get_built_parts()` | 离线可用 |

> ⚠️ 模板的 `save()` 走 `app.cst_file.save(...)`，**不会回写 `modeler._cst_path`**；
> 所以模板保存成功后 `modeler.read_results()`（不给 `path=`）仍会抛 `RuntimeError`。

### 7.3 Builder 层速查（全部无状态，可脱离 Modeler 单独调用）

| 部件 | 函数 | 要点 |
|---|---|---|
| 材料 | `build_materials(app, names=DEFAULT_MATERIALS)` | 预设只有 3 个：`Copper (annealed)` / `Silicon (lossy)` / `Quartz (Fused) (lossy)`；自定义走 `app.create_material_custom(name, eps, mu, kappa)` |
| 基板 | `build_substrate(app, path, name='substrate', height='h', material='Silicon (lossy)', y_margin='e2')` | 逐段四边形 + 布尔并。**直波导模板刻意不调它**（§3.1） |
| 基板（多域壁） | `build_substrate_multi(app, paths, …, prefix='p', unite=True)` | 每条路径用**各自的参数前缀** |
| 相区 | `build_vpc_regions(app, path, name_prefix='vpc', …, y_margin='e2')` | 返回 `('vpc_A','vpc_B')`；**A=下半区、B=上半区** |
| 相区（多域壁） | `build_vpc_regions_multi(app, paths, …, prefix='p', unite=True)` | **按侧全局并**；≠ 参考的"两多边形之并"（§3.6） |
| 晶体阵列 | `build_topological_crystal(app, path, topology='AB', lattice='a', height='h', large_hole='l1', small_hole='l2', y_margin='e2', name_prefix='g', xup=None, yup=None, ydn=None, index=None)` | 返回 `('g1A','g1B')`；`xup/yup/ydn` 传**参数名字符串**；11 步见 §3.2 |
| 裁剪 | `intersect_crystal_with_vpc(app, ca, cb, vpca, vpcb)` / `clip_crystals_with_vpc(app, vpca, vpcb, crystals)` | **操作数顺序 = 参考工程**：`vpca ∩ g1A`，相区名保留 |
| 馈源 | `build_feed(app, feed_type='ab_elliptical', name=None, **kwargs)` | 三个类型：`ab_elliptical`→`feed1`、`ba_tapered`→`feed2`、`cylinder`→`cylinder_feed` |
| 波导 | `build_waveguide(app, name='wg1', material='Copper (annealed)', x_min='-lf1-lf2-lf3', x_max='-lf1', y_center='e2/2', wg_b='wg_b', wg_a='wg_a', wg_t='wg_t')` | 全部参数都是 **CST 表达式字符串** |
| 端口 | `add_ports_for_straight_waveguide(app, waveguide_name='wg1', port1_face='10', port2_face='22')` / `add_port_for_antenna(app, waveguide_name='wg1', port_face='10')` / `add_multiport_port_set(app, entries)` | 面号是 **CST 内部编号，硬编码且脆弱**（见 §9 陷阱 6） |
| 求解器 | `configure_solver(app, freq_range=(300,380), monitors=('E',), calculation_type='TD-S', steady_state=-30, parallel_threads=1024, gpus=1, component='component1', monitor_frequencies=None)` | `calculation_type ∈ {TD-S, FD-S, EIGENMODE, IE-S, ASYMPTOTIC}`；`component` 是**死参数**（不生效） |
| 透镜 | `builders/lens.py` 一族 | 本 skill 范围外；`lens_build.py` / `lens_build_standalone.py` 是**不可导入的旧脚本**，别用 |

> `configure_solver` **不覆盖**参考工程那一大段 MPI/分布式 VBA，也不暴露 `Mesh.SetCreator`。
> 需要时只能 `app.cst_file.model3d.add_to_history('Define solver', VBA)`（参考工程的做法）。

---

## 8. 拓扑正确性自检（离线优先）⭐

> **这是"建好"的关键**：CST 消息为空只证明"没有非法 VBA"，**不证明域壁存在、相序正确**。
> 下面 4 项**不需要 CST、秒级完成**，任何一次 TPC 建模都该跑。

### 8.1 相绑定断言（离线 / 秒级 / 无需 CST）

用一个"录制假 app"把 `build_topological_crystal` 的实际调用录下来，**直接断言孔到相的绑定**。
这是唯一能在建模前就证明"相没搞反"的低成本手段：

```python
from mesh_grid.tri_grid import TopoPath
from topo_modeler.builders.crystal import build_topological_crystal

class _Recorder:
    def __init__(self): self.calls = []
    def __getattr__(self, label):
        def f(*a, **k): self.calls.append((label, a, k))
        return f

app = _Recorder()
path = TopoPath.builder(0.2425, name='p').start(0, 0).move(18, 'c').build()
build_topological_crystal(app, path, topology='AB',
                          large_hole='l2', small_hole='l1',   # ← 参考工程口径
                          xup='xup', yup='yup', ydn='ydn')

binding = {k['name']: a[0] for label, a, k in app.calls
           if label == 'triangle' and str(k.get('name', '')).startswith('tri_')}
assert binding == {'tri_up_A': 'l1', 'tri_dn_A': 'l2',
                   'tri_up_B': 'l2', 'tri_dn_B': 'l1'}, binding   # 参考工程的权威绑定

reps = [k.get('repetitions') for label, a, k in app.calls if label == 'translate']
assert reps == ['int(xup)', 'int(yup/2)', 'int(ydn/2)'] * 2, reps  # 阵列必须引用参数
print('相绑定与阵列引用 OK')
```

只用 TPC 口径（`l1`=大孔）时，把上面的期望值换成 `topology='AB' → l1 给朝下孔`：

| 口径 | AB 期望绑定 |
|---|---|
| 参考工程口径（`large_hole='l2', small_hole='l1'`） | `tri_up_A→l1`、`tri_dn_A→l2`、`tri_up_B→l2`、`tri_dn_B→l1` |
| TPC 口径（默认 `large_hole='l1', small_hole='l2'`） | `tri_up_A→l2`、`tri_dn_A→l1`、`tri_up_B→l1`、`tri_dn_B→l2` |

两个都错不奇怪——**先确定你要哪一种口径，再钉住它**。BA 就是把 `A`/`B` 两组对调。

### 8.2 几何不变式清单（离线，逐条问自己）

| # | 不变式 | 不满足的后果 |
|---|---|---|
| 1 | **路径就是域壁**：起点/终点分别落在两个端口上；段数与折点数 = 你要的域壁形状 | 域壁没连到端口 ⇒ 不导通 |
| 2 | **相区覆盖整块板**：`vpc_A ∪ vpc_B` = 整块基板，且两者不重叠 | 板上有洞/有双相重叠 |
| 3 | **阵列覆盖相区**：`xup/yup/ydn`（尤其 `yup/ydn ≥ 2`）覆盖整个板 | 晶体缺一块 / `Invalid number of repetitions` |
| 4 | **相区半宽够**：`y_margin ≥ width * e2`（模板用 `width*e2`，库默认 `'e2'` 只有一行） | 14 行阵列落在板外 |
| 5 | **裁剪后是图形化硅**：引用的是 `vpc_A` / `vpc_B`（晶体名已被消耗） | 引用已消失的实体 ⇒ `Shape does not exist` |
| 6 | **没有多余的整块 substrate** | 孔洞被填平、周期性消失 |
| 7 | **端口口径 = `wg_b × wg_a`**（用于反查单位是否正确） | 单位错 ×1000 |

### 8.3 相区/覆盖的离线自算（可选，想更稳就用）

`TopoPath` 的相区带是纯几何，可以离线算出环顶点再自己求面积/并集，从而验证"覆盖整板、A/B 不重叠"：

```python
lower = path.build_segment_band_polygons(y_margin='14*e2', prefix='p', side='lower')
upper = path.build_segment_band_polygons(y_margin='14*e2', prefix='p', side='upper')
# 用 shapely（可选依赖）取并集/交集面积，确认 union == 板面积、intersection == 0
```
> 折返路径上会得到**多个环**（每段一个 + 拐角补块），这正是"整条带多边形会自覆盖"的体现（§2 硬约定 1）。

### 8.4 连 CST 之后（§10 的自动化版）

```python
app = wg.app
print(app.cst_file.get_messages())        # 必须为空
app.cst_file.model3d.Rebuild()            # 阻塞式重放历史
print(app.cst_file.get_messages())        # 必须为空
print(wg.validate())                      # {'status','messages','rebuild_ok','before','guard'}
print([s for s in app.cst_file.model3d.GetAllSolidNames()])   # 实体清单：该有的都在、无模板残留
```

### 8.5 物理侧（最终确认）

**AB 与 BA 两个工程在带内都完全不导通**（S21 极低）⇒ 第一嫌疑是 §9 的 1/2/3（相序反了 /
拓扑按文件名选错 / 相区换边）。另外**求解尚未真机验证**（见 §12），首次跑通求解后请把结果记下来。

---

## 9. 语义错位与陷阱（按危险程度排序）

1. 🔴 **`l1`/`l2` 同名不同义** → §5.2。复用参考工程口径**必须** `large_hole='l2', small_hole='l1'`；
   用 TPC 口径则**不要**传这两个参数。两者混用 ⇒ 相再翻一次。
2. 🔴 **按文件名猜 `topology`**：参考工程的 AB/BA **不是**代码里的标志位，而是「目录名 + `l1/l2` 数值」。
   `MZI-BA.ipynb` 注册进 CST 的 `l1/l2` 其实是 **AB 形状**（`l1 = 0.35a`，而它自己的 Python 变量写的是 `0.65a`）。
   ⇒ 按文件名选拓扑会得到「能跑、看起来对、物理上拓扑错了」的器件。
   **判定拓扑的权威来源是 CST 参数表 + 区域/路径侧**，不是文件名、更不是预览图。
3. 🔴 **`VPC-A` = 路径下方半区**（不是上方）。TPC 到 2026-09-15 才与参考工程对齐；
   如果把 A/B 换边，整个器件在 y 方向镜像（哪种相在上半区反了）。
   且 **`Insert` 是差集不是并集** —— 当成并集会让 A/B 两区塌到同一半区、互相重叠。
4. 🔴 **多域壁器件的相区不是"路径下侧"**（§3.6）：Z 型折叠 / 分束器件的 A 相是**两个多边形之并**。
   把单域壁的直觉套上去 ⇒ 相区错、域壁数量和位置都错。
5. 🟠 **`bend_angle` 是张角**（= 2 × 单臂偏角），必须是 120 的整数倍。按旧语义传 60 会得到折返天线。
6. 🟠 **`extrude` 的形参名是 `thickness`，且 `material` 默认 `PEC`。**
   写法 `app.extrude(curve, name, thickness='h')` 不写 `material=` 会**静默建出 PEC 实体**（无报错无消息）。
   参考工程的复数写法 `extrude(..., materials='Silicon (lossy)')` 在新签名下是 `TypeError`。
7. 🟠 **端口面号 `'10'`/`'22'`/`'4'`/`'5'` 是 CST 内部编号**，随实体几何与生成顺序变化。
   参考工程用 `pick_face(solid, '10')`，换构序后会**静默指错面**。
   更稳的做法：`app.create_waveguide_port_free(n, xrange=…, yrange=…, zrange=…, orientation=…, shield='electric')`
   —— 但它**只支持轴对齐矩形面**。库的 `add_waveguide_port` 有「拾取数必须为 1」的运行时护栏。
8. 🟠 **`intersect` 会消耗第二个操作数**（`insert` 不消耗，但它是差集）。
   想在**保留下一个操作数**的前提下求交（例如把掺杂块嵌进介质），必须先在**副本**上求交再 `insert` 回去；
   直接 `intersect('pump2', 'vpc_A')` 会让随后的 `insert('vpc_A', 'pump2')` 报 `Shape does not exist: vpc_A`
   （库在 `mzi_switch.py` 里记录过这次真机失败）：

   ```python
   app.translate('vpc_A', ['0','0','0'], copy=True, unite=False, log_flag=1)   # → vpc_A_1
   app.intersect(block, 'vpc_A_1')        # 结果留 block
   app.insert('vpc_A', block)             # 嵌回，block 保留
   ```
9. 🟡 **模板不调用 `modeler.set_topology()`** ⇒ `wg.modeler.topology` 仍是**推断值**
   （直线恒 `'AB'`、天线恒 `'BA'`），与模板自己的 `topology` 参数可能是两回事。
   要在同一 Modeler 上继续调 builder，请显式 `set_topology()`。
10. 🟡 **参数名与参考工程不一一对应**：模板用 `length/width`，参数表里生成的是 `a h l1 l2 e1 e2 p1x…p2y xup yup ydn`，
    **没有** `x1/y1/x2/px3/py3/ymax_up/ymax_dn`。
    ⇒ 想复用参考工程的参数名做扫描/比对，必须**显式 `app.para` 补登记**。
11. 🟡 **改参数不动几何**：`para` / `paras` 默认 `log_flag=0`（不触发 `full_history_rebuild`）。
    几何类方法默认 `log_flag=1`。改已有参数后要 `app.update()` 或 `log_flag=1`。
12. 🟡 **参数描述不能含非 GBK 字符**：CST 用 GBK 写历史，一个 `⇒`（U+21D2）就能让整个构建以
    `UnicodeDecodeError` 崩掉。库的校验只挡会破坏 VBA 字面量的字符（引号/换行/控制符），**不查 GBK**。
    ⇒ `expression=` 里写中文没问题，但别写特殊数学符号。

---

## 10. 验收清单（每次交付建模脚本必做）

顺序固定：**§8 离线自检 → 连 CST 验收 → 磁盘侧核对**。

```python
app = wg.app                     # 模板 / Modeler 都把 setup 实例挂在 .app 上

# 1) CST 消息（读后即清空）
print('before:', app.cst_file.get_messages())
# 2) 阻塞式重放历史 —— 最能暴露问题的一步
app.cst_file.model3d.Rebuild()
print('after :', app.cst_file.get_messages())

# 3) 结构化校验（模板 / Modeler 都有）
print(wg.validate())             # 或 m.validate()：{'status','messages','rebuild_ok','before','guard'}

# 4) 实体清单：该有的都在、没有模板残留
print([s for s in app.cst_file.model3d.GetAllSolidNames()])
```

> **`get_messages()` 为空只在干净工程里可信**：历史里留过一条失败命令后，
> 它会**反复报同一条**。所以「跑通」不等于「建模正确」—— 拓扑对不对看 §8。
>
> 磁盘侧交叉核对（不连 CST）：工程保存后查
> `<工程名>\Model\Parameters.json`（参数求值）、`Model\3D\ModelHistory.json`（构序、孔到相的绑定）、
> `Model\3D\anchorpoints.json`（端口位置/法向是否与 `wg_b × wg_a` 口径一致）。

---

## 11. 报错定位表

排错要**沿 §3.7 的因果链回查**：症状出现在哪一步、输入错在哪一步。

| 现象 | 病因 | 动作 |
|---|---|---|
| **脚本卡住不报错**，CST 弹「请输入变量值」 | 引用了**未登记**的参数（最常见：换 `feed_type` 后 `wf2/lf4/lf5/lf6` 或 `x0/wf1` 没登记；透镜的 `Ls`/`Rbig`/`dphi`） | 对照 §5.5/§6.1 检查 `_define_all_params` 是否把该族参数都登记了；模板已按 `feed_type` 分支登记 |
| `Invalid number of repetitions` | `yup`/`ydn` 太小，`int(yup/2)` 或 `int(ydn/2)` 取整成 0 | 显式给 `xup/yup/ydn`（别用 `get_array_range()`） |
| `The specified curve is not closed and planar.` | 折返路径上手写整条恒定宽度带 ⇒ 自覆盖 | 用库的 `build_segment_band_polygons`（逐段四边形+补块），别自己拼多边形 |
| 布尔运算「成功」但结果是**空集**（晶体静默消失） | 绕向/z 平面不对（实体差一个 `h`）；或阵列范围没覆盖 | 查 §2 硬约定 1、3；确认多边形 CCW |
| `Shape does not exist: vpc_A` | `intersect` 吃掉了第一操作数 | 先在**副本**上求交再 `insert` 回去（§9 陷阱 8） |
| 器件能建、但**完全不导通** | 相序反了 / 相区换边 / 多壁相区按单壁做了 | 跑 §8.1 的绑定断言 + §8.2 清单；查 §9 的 1/2/3/4 |
| `The specified material does not exist` | 忘了 `build_materials(app)` | 材料必须先建 |
| 实体建出来了但是 **PEC 而不是硅** | `extrude`/`square`/`cylinder` 忘了 `material=`（默认 PEC） | 补 `material='Silicon (lossy)'` |
| `TypeError: extrude() got an unexpected keyword argument 'materials'` | 参考工程用复数 `materials=` | 改单数 `material=`；形参名是 `thickness` 不是 `height` |
| `ModuleNotFoundError: No module named 'cst'` | CST 路径未配 | 设 `CST_INSTALL_PATH`；`python -m cst_solver doctor --probe` |
| `FileNotFoundError: tmp.cst` | 模板不在**当前工作目录** | 传绝对路径，或把 `tmp.cst` 放到 notebook 同目录 |
| `RuntimeError: 符号路径无法…请提供 param_values` | 符号路径没给 `param_values` | `.build(param_values={'x1': 18, …})` |
| `ValueError: topology 必须是 'AB' 或 'BA'` | 传了 `'ab'` / 带空格 | 严格 `'AB'` / `'BA'` |
| `ValueError` on `bend_angle` | 不是 120 的整数倍 | 用 `0/120/240/…` |
| `ValueError` on `calculation_type` / `side` / `feed_type` | 枚举写错 | 见 §7.3 的合法取值 |
| 改了参数但几何没动 | `para` 默认 `log_flag=0`，不触发 rebuild | `app.update()` 或 `log_flag=1` |
| `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb2` | 参数描述含非 GBK 字符（如 `⇒`） | 去掉特殊符号 |
| `CstOperationError: cst_unavailable` | `app is None`（构造模板时 CST 没起来） | 看构造时的 `warnings`，检查 `CST_INSTALL_PATH` |
| 参数扫描「跑了但什么都没变」 | 扫描的**参数名**不在该工程的参数表里（如扫 `sigma1` 而工程用的是 `sig1`） | 以 `Parameters.json` 为准 |

---

## 12. 影响使用者的已知库缺陷（不要当"用法问题"去修）

| 缺陷 | 影响 | 规避 |
|---|---|---|
| `TopoModeler.build_all()` 不裁剪晶体、不镜像、且多建一块整幅 substrate | 直接出**错误几何**（孔被填平） | 用模板层，或照 §7.2 手动补 `clip_crystals_with_vpc` + `mirror` |
| `build_vpc_regions_multi` 是**按侧全局并**，不是参考的"两多边形之并" | 多域壁器件相区可能与参考不一致 | 用 `MZISwitch`/`PowerDivider` 模板，或手搓相区 + §8 自检 |
| `TopoModeler.build_substrate` / `build_vpc_regions` **单路径分支丢弃 `**kwargs`** | 传进去的 `name`/`material`/`y_margin` 静默失效 | 单路径请直接调 `builders.build_vpc_regions(...)` |
| `TopoModeler.add_ports(auto, **params)` **忽略全部参数** | 端口配置改不动 | 直接调 `builders/port.py` 的函数 |
| `build_all(**kwargs)` 只认 7 个 `*_kw` 键 | `output_path=` 之类被静默忽略 | 用模板的 `save(output_path=…)` |
| 模板 `save()` 不回写 `_cst_path` | 保存后 `modeler.read_results()` 仍抛错 | 显式 `read_results(path=…)` |
| `UnitAntenna` / `GRINLensAntenna` 不裁剪晶体、`y_margin` 用默认 `'e2'` | 与 `StraightWaveguide` 结构不同，别以为能互换 | 需要一致结构就用 builder 手搓 |
| 端口面号硬编码 `'10'`/`'22'` | 改波导尺寸后可能指错面 | 改用 `create_waveguide_port_free` 或 `pick_face` + 拾取数护栏 |
| `NameManager` 从不被调用，实际实体名是 builder 里的字面量（`vpc_A`/`g1A`/`wg1`/`feed1`） | 按文档找 `feed_1`/`crystal_A` 会找不到 | 以 §6.1/§3.2 的实体名为准 |
| `lens_build.py` / `lens_build_standalone.py` 是**不可导入**的旧脚本 | 直接 import 会失败 | 用 `topo_modeler/builders/lens.py` |
| 求解能力**尚未真机验证** | 不要把它当已验证能力用 | 建模式已真机验证（CST 2026 + Python 3.11.7） |

---

## 13. 超出本 skill 范围的器件族（当前 TPC 能建到什么程度）

按「能不能用现有 API 建出来」分类。**动手前先看这一节，别白读参考 notebook。**

| 器件族 | 参考工程位置 | 现状 | 建议 |
|---|---|---|---|
| **参杂控制 MZI**（矩形掺杂块 σ₁/σ₂） | `硅基\参杂控制\` | ✅ **可以** —— 参考工程里唯一 100% 用 TPC API 写成的族 | 照 `_work\build_cst_nb.py` 抄（含三条坑的标准规避写法） |
| MZI basic / cascade | `硅基\开关尝试\` | ✅ 有 `MZISwitch` 模板 | 直接用；`basic` 与 `cascade` 几何相同 |
| MZI parallel / anti / hex | 同上 | ❌ `mzi_type` 抛 `ValueError` | 需新模板能力 |
| 功分器 1分2/1分4 | `硅基\功分器\` | ✅ 有 `PowerDivider` | `split_ratio ∈ {2,3,4,6}` |
| 1分6（2H4L 双透镜组） | `硅基\功分器加天线\B5\` | ❌ 未实现 | 需新模板 |
| 三环 / 六边形功分结点 / 集总电阻版 | `硅基\功分器\` | ❌ 无对应原语（库里没有环形基元） | 研究向 |
| 多端口 Ant3（3 端口：2 轴向 + 1 侧向）/ 单向直波导 | `硅基\多端口\` | ✅ 有 `MultiPortAntenna` | |
| C6 六边环腔（6 条 BA 域壁 + 扭端口 + `.sab` 子工程） | `硅基\多端口\Ant6_undiretional\` | ❌ 环腔、扭端口、子工程交付全缺 | 需新 builder |
| 单元天线 + 椭圆/GRIN 透镜 | `硅基\单元天线GRIB\`、`椭圆透镜单元天线\` | ✅ 有 `GRINLensAntenna`（`dxf`/`insitu` 两条路线） | 但**per-arm 透镜定位未实现** |
| 泄漏波天线（EPC 椭圆栅 / MK sech 剖面 / Maxwell-Garnett） | `硅基\Leaky\` | ❌ 无模板（列为 `NO_TEMPLATE`） | 需新模板 |
| 耦合器（3 dB 同相电桥 / 间隔一行三角） | `硅基\耦合器\` | ❌ 无耦合区概念 | 研究向 |
| 波导扩大段 / 缺陷波导 / 圆极化铜管 / 无晶体开槽探针 | `硅基\直波导\` 附加件 | ⚠️ 部分可用原语拼 | 逐件评估 |
| MXene 薄膜 / 光泵柱调谐 | `硅基\针对隔离和开关的分析研究\` | ⚠️ 只有「圆柱 + 自定义材料」一种表达 | 逐件评估 |

**已确认的能力缺口**（想扩展时要新增库能力，不是用法问题）：

1. `.sab` / SAT 几何导出（CST 侧 `WriteAll`）—— 库只有 `import_subproject`，无导出 ⇒ 透镜重建无法缓存。
2. 弧形/扭转馈源（`rotation_face` 原语存在，但**没有 builder**）。
3. **非轴对齐端口**（`create_waveguide_port_free` 只支持轴对齐；面号路线脆弱）。
4. per-arm 透镜定位。
5. 六边环腔。
6. **多域壁相区的显式构造**（参考的"两多边形之并"没有 builder，只有"按侧全局并"）。
7. MPI/分布式求解 VBA 块 + `Mesh.SetCreator`。
8. 参数描述的 GBK 可编码性预检。

---

## 14. 相关文档

| 需要什么 | 读哪份 |
|---|---|
| **库总入口 / 报错定位 / 大几何子工程** | [`tpc-usage.md`](./tpc-usage.md) |
| 三角晶格 / `TopoPath` 细节 | [`tri-grid.md`](./tri-grid.md) |
| 六边形晶格 / DXF | [`hex-grid.md`](./hex-grid.md) |
| 建模引擎三种用法（与本文重叠，API 细节更全） | [`topo-modeler.md`](./topo-modeler.md) |
| 包设计 / 完整 API | [`../../docs/packages/topo_modeler.md`](../../docs/packages/topo_modeler.md)、[`../../docs/packages/topo_templates.md`](../../docs/packages/topo_templates.md) |
| 阶段 0–3 详细指南 | [`../../docs/guides/topo_modeler_guide_stage0-3.md`](../../docs/guides/topo_modeler_guide_stage0-3.md) |
| 硬约定的出处 | [`../../docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) §6 |
| 已验证的 CST/Python 组合与能力边界 | [`../../docs/SUPPORT_MATRIX.md`](../../docs/SUPPORT_MATRIX.md) |
| 要改库源码 | [`../developer/WORKFLOW.md`](../developer/WORKFLOW.md) |

**参考工程（只读，不在本仓库内）**：`D:\成电博士生涯\拓扑光子晶体模型\硅基`
—— 权威参数表看 `<工程>\Model\Parameters.json`，权威构序与**孔到相的绑定**看
`<工程>\Model\3D\ModelHistory.json`，端口看 `<工程>\Model\3D\anchorpoints.json`。
其中 `参杂控制\_work\build_cst_nb.py` 是该库**唯一** 100% 用 TPC API 写成的端到端范例
（含 §3.6 的多域壁相区构造），值得先读。

## 中文绘图约定

预览已接入自动字体检测。自定义 Matplotlib 图在创建 Figure 前使用
`mesh_grid.plotting.chinese_plot_style(text=实际中文标签, strict=True)`，在上下文内保存。
无字体时设 `TPC_CJK_FONT` 或用英文标签，**不要屏蔽缺字警告**。
见 [中文绘图指南](../../docs/guides/chinese_plotting.md)。
