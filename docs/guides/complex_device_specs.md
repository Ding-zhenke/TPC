# 复杂器件参考规格

保留原 notebook 的参数与拓扑证据，不代表对应模板已实现。剩余工作见 [计划](../next_plan/README.md)。


原计划只有一行：「`num_ports`(2/3/4/6)、`divider_type`、`mzi_type` —— **无**；
补每个取值的**几何含义**、`port_config` 结构；**4 / 6 端口目前无数据依据**」，
并标了红灯：「先确认这两种结构在旧代码里是否真的存在」。

### 4.1 红灯已解除：4 / 6 端口**确实存在**（按文件名，无启发式）

| 端口数 | 数量 | 证据 |
|---|---|---|
| 2 | 2 | `椭圆透镜1div3\Ant2_1div2_{AB,BA}_120D_epc.ipynb` |
| 3 | 7 | `MPMBA\Ant3_{epc,epc2,epc_mf,AB_epc_mf}.ipynb`、`椭圆透镜1div3\Ant3_1div3_BA_120D_epc.ipynb`、`多端口\Ant3_1W2N\Ant3_{240D3,BA_240D}_epc.ipynb` |
| **4** | **5** | `1分4\Ant4_1d2d4_2f2s_{circle_DF,circle_DF_BA,circle_DF_grid120,2G2F_circle_DF,2G2F_circle_DF_grid120}.ipynb`、`椭圆透镜1div3\Ant4_1div4_BA_120D_epc.ipynb` |
| **6** | **4** | `功分器加天线\B5\Ant6_2H4L_epc.ipynb`、`多端口\Ant6_undiretional\ANT6_{C6_hexring,undirectional,undirectional_test}.ipynb` |

### 4.2 `mzi_type` 的取值有数据依据 —— 映射到**参数表的可测差异**

计划列的 `mzi_type('basic'/'cascade'/'parallel'/'anti')` 与旧 notebook 的文件名**完全对应**，
而且它们的参数表**确实不同**（实测抽取）：

| `mzi_type` | 旧 notebook | 坐标点数 | 臂参数 | 判别特征 |
|---|---|---|---|---|
| `basic` | `开关尝试\AB\MZI.ipynb` | `px1..py6`（**6 点**） | `ax, ay` | 单组臂参数 |
| `cascade` | `开关尝试\AB\MZI-cascade.ipynb` | `px1..py6`（6 点） | `ax, ay` | 与 basic 参数表**完全同构** |
| `parallel` | `开关尝试\AB\MZI-parallel.ipynb` | `px1..py10`（**10 点**） | `ax, ay` | **点数最多** ⇒ 并联双臂 |
| `anti` | `开关尝试\AB\MZI-anti.ipynb` | `px1..py6`（6 点） | **`ax1, ay1, ax2, ay2`** | **两组臂参数** ⇒ 上下臂不对称 |

> 🔴 **可测的判别式**（不用猜）：
> `len(坐标点) == 10` ⇒ `parallel`；出现 `ax1/ay1` ⇒ `anti`；其余是 6 点 + 单组 `ax/ay`。

#### 4.2.1 ⚠️ 更正：`basic` 与 `cascade` 在 **CST 侧没有差别**（2026-09-17 逐 cell 取证）

此前这里写着「差异在**拓扑/级联段数**（需读几何代码才能区分）」。逐 cell 比对
`MZI.ipynb` 与 `MZI-cascade.ipynb` 后发现**这一说法没有依据**：

| 比对 | 结果 |
|---|---|
| cell 2–22（全部 `para` / `polyline` / `extrude` / `triangle` / `port` / `cylinder` / solver） | **逐字节相同** |
| 只有 cell 1 与 cell 23 不同 | cell 1 是 **matplotlib 预览**用的 `plot_power_divider`；cell 23 只是保存文件名（`MZI-circle.cst` vs `MZI-circle-cascade.cst`） |
| cell 1 的差别 | 预览网格列范围 `23 → 45`；多算一块 `area3`（`path3[:,1] += x[0]+y[0]-1`，把弯折区平移 13 格）、并多并进 `vpca_up/vpca_dn` |
| `plot_power_divider` 的返回值用在哪 | 全 notebook 里**只出现在 cell 1/2**，**从未进入 CST** ⇒ cell 1 是**死代码/预览实验残留** |

⇒ **`basic` 与 `cascade` 建出来的 CST 模型是同一个**。因此：

* `MZISwitch` 模板**不能用几何量区分**这两者；若保留 `cascade` 取值，只能做成
  **显式开关且不改变 CST 几何**（或按来源文件名记录来源）；
* **不要**依据"级联段数"生成不同几何 —— 那是凭空发明，与参考工程不符。

#### 4.2.2 四型的**真实几何差别**（同样逐 cell 取证）

| 维度 | basic / cascade / anti | parallel |
|---|---|---|
| px/py 点数 | 6 | **10**（多一段直线 + 两段对称 S 弯） |
| 基板轮廓（cell 9） | 7 点、含 `ymax_dn` | **5 点**、无 `ymax_dn` |
| 下半区怎么来 | `translate(['0','-e2*2','0'], repetitions='int(ydn/2)')` | 该块被注释 ⇒ 改用 `mirror('vpca',[0,0,0],[0,1,0])` |
| 长边镜像写法 | `-py3/-py4` | `2*py4-py5` / `2*py4-py6` |
| feed 镜像中心 | `(x1*2+x2-y1)*a/2` | `(x1*2+x2*2+x3-y1-y2)*a/2` |
| 臂参数 | 一组 `ax, ay`（`anti` 为 `ax1/ay1` + `ax2/ay2` 两组） | 一组 `ax, ay` |
| 泵浦区（`pump1`/`pump2`） | basic：一块 `pump1` + 圆柱，均 `mirror(copy=True)`；anti：`pump1`（`ax1=0` ⇒ 退化成三角形、**不镜像**）+ `pump2`（`copy=False`） | 一块 `pump1`（镜像）+ 圆柱**也镜像** |

四型**共用**：方向集恒为 `{0°, +120°, −120°}`、步长恒为 `a`、`e1='a/2'` / `e2='a/2*sqr(3)'`、
2 个端口（`pick_face('feed1','4')→port2`、`pick_face('feed1','14')→port1`，`shield='electric'`）、
`m1` 材料（Epsilon 11.9 / Sigma=sigma1）、圆柱 `rc1=0.4`、`freq_limit(300,380)`、
`define_monitor('E', np.arange(310,322,2))`。

#### 4.2.3 旧 notebook 里查出来的几处**不一致**（实测，非猜测；实施时要处理）

1. **硬编码端口面号 `4`/`14`**：仓库自己的 `cst_solver/modeling/picks.py` 就写明
   「面编号与几何/生成顺序强相关，扭转/布尔/阵列之后会变，跨模型不可复用」，并推荐
   `pick_face_at`。模板**不应**沿用硬编码面号。
2. **`parallel` 用了 `y3` 但从未定义**：cell 5 里 `ymax_up='e2*(y1+y2+y3)'`、
   `xup='x1*2+x2*2+x3-int(y1+y2)+1'`，而 cell 4 的导出循环是 `range(len(y)-1)`
   ⇒ `y3` 从未 `para()`。（basic/anti 不用 `y3`，无害。）
3. **`parallel` 的 cell 14 与 15 内容重复**：`intersect` + `add` + `mirror` 被执行两次。
4. **`l1/l2` 在 basic 里与 Python 变量互换**：`l1=0.65a, l2=0.35a`，但
   `para('l2','0.65*a')` / `para('l1','0.35*a')`；parallel/anti 里不互换。
5. **`lf3/lf4/lf5/lf6/wf2/wg_a/wg_b/wg_t/x01` 四型都"只定义、不使用"**：
   在四个 notebook 里各只出现两次（Python 字面量 + `.para()`），此后无任何几何引用；
   真正被几何引用的只有 `lf1/lf2/wf1/x0`。⚠️ 这与 §4.4「多端口用 `lf4-lf6/wf2` 馈源族」
   的说法**需要在实施多端口模板时重新取证**（MZI 这一族并不用它们）。

---

计划列的 `divider_type('y'/'t'/'cascade'/'mmi')` **在参数表里找不到对应字段**：
所有分路 notebook 的参数表用的都是通用的 `lx1` / `nsm` / `Rbig` 一类。
实测能区分的只有**分几路**：

| 结构 | 旧 notebook | 参数表特征 |
|---|---|---|
| 一分二 | `椭圆透镜1div3\Ant2_1div2_{AB,BA}_120D_epc.ipynb` | 4 个坐标点，**含透镜参数**（`ec_a/ec_b/ec_c/Nx/Ny`） |
| 一分三 | `椭圆透镜1div3\Ant3_1div3_BA_120D_epc.ipynb` | 含透镜参数 |
| 一分四 | `1分4\Ant4_1d2d4_2f2s_circle_DF.ipynb` | 5 个坐标点，**不含透镜参数** |
| 一分六（2H4L） | `功分器加天线\B5\Ant6_2H4L_epc.ipynb` | **8 个 p 点 + 4 个 q 点**（两套坐标族）、**两组透镜参数**（`Nx1/Ny1/ec_a1…` 与 `Nx2/Ny2/ec_a2…`）、`dphi1/dphi2`（相位） |

> ⚠️ **结论**：`divider_type` 的 `'y'/'t'/'cascade'/'mmi'` **目前没有数据依据**，
> 不要凭"应该支持"就写进模板。真实可用的输入维度是
> **`split_ratio`（分几路）+ 是否带透镜 + 是否带相位差**。
> 与「4/6 端口」那次不同：那次是**存在但计划没说清**，这次是**计划里的取值本身没有出处**。

### 4.4 多端口器件的**馈源族** —— ✅ 几何含义已提取（2026-09-17）

实测参数表：多端口 / Leaky / 多端口天线这几类用的是 **`lf4/lf5/lf6` + `wf2`**，
而直波导与普通单元天线用 **`lf1/lf2/lf3` + `wf1`**。
⇒ 写复杂模板时**不能直接复用 `StraightWaveguide` 的 feed 默认值**。

**几何含义（权威出处：`多端口\Ant6_undiretional\ANT6_undirectional.ipynb` 的注释）**：

```python
wf2 = 0.2   # 探针颈部宽度
lf4 = 0.2   # 探针颈部长度
lf5 = 3.0   # 椭圆过渡段长度
lf6 = 0.2   # 铜波导端口段长度
```

**派生量（出处：`ANT6_C6_hexring.ipynb` 的 `CST_PARAMS` 表）**：

```python
('wg_out', 'rin-lf4',        '铜波导径向外端 = 探针颈部起点'),
('wg_in',  'wg_out-lf5-lf6', '铜波导径向内端 = 波端口所在半径'),
```

⇒ 多端口族的铜波导 x 范围是 **`[-lf5-lf6-lf4, -lf4]`**（长在椭圆过渡段之外），
不是直波导族的 `[-lf1-lf2-lf3, -lf1]`。

**已落地为库 API（离线性已测）**：
`topo_modeler.builders.register_multiport_params()`（登记 `wf2/lf4/lf5/lf6` +
**表达式形式**的 `wg_out/wg_in`）、`build_multiport_waveguide()`（默认 x 范围 +
可选波端口）。回归 `topo_modeler/tests/test_multiport_feed.py`（9 项）。

> ⚠️ **登记 `lf6` 不只是"补全"**：多端口族波导的 `x_min` 引用 `lf6`，而本库的
> `UnitAntenna`/`StraightWaveguide` 都**没登记它** —— 参数未定义时 CST 会弹
> 「请输入变量值」**模态对话框把脚本挂住**（不是抛异常，见 P4/V6 的 Rbig/Ls 教训）。
> 新的登记函数对缺 `rin` 的场景也做了**前置拦截**。

**参考取值统计**（12 个 notebook）：`lf4=0.2` 12/12、`wf2=0.2` 12/12、
`lf6=0.2` 11/11、`wg_a=0.7312`/`wg_b=0.3756`/`wg_t=0.2` 12/12、`x01=0` 12/12；
`lf5` = **3.0×9** / 0.2×2 / 0.45×1；`lf2` = 3×6 / 0.2×4（两类器件族不同，别互相套用）。

### 4.5 12 个多端口/功分 notebook 的端口与拓扑普查（2026-09-17 逐 cell 取证）

| 组 | notebook | 端口数 | 分路 | 透镜 | 相位 |
|---|---|---|---|---|---|
| α1 | `Ant3_1W2N\Ant3_{240D3, BA_240D}_epc`、`MPMBA\Ant3_{epc, epc2}` | **3** | 1分2 | DXF | — |
| α2 | `椭圆透镜1div3\Ant2_1div2_{AB,BA}_*`、`Ant3_1div3_BA`、`Ant4_1div4_BA`、`B5\Ant6_2H4L_epc` | 1 | 1分2/3/4、2H4L | DXF | 1div4/2H4L 有 `dphi1/dphi2` |
| β | `1分4\Ant4_1d2d4_2f2s_circle_DF` | 1 | 级联 1d2d4 | 就地 `hexagon`（无 DXF） | — |
| γ | `Ant6_undiretional\ANT6_C6_hexring` | **6** | 1分6 C6 环 | CST **子工程** `.sab` | — |
| δ | `Ant6_undiretional\ANT6_undirectional` | 1 | 单臂 | 无 | — |

* **α 组（9 个）命令序列逐条同构** ⇒ 可以共用一份 builder；α1 与 α2 的差别只在
  「双馈源（AB `feed1` + BA `feed2`）+ 两个铜波导（⇒ 3 端口）」还是「单馈源」；
* **γ 组不可与 α 共用**（`rotate_port` / `rotation_face` / 子工程 / 扭波导）；
* **δ 组（J）是模板的最佳起点**：它是唯一用**本库 builder API** 写的多端口 notebook，
  且带上述参数语义注释；
* **端口机制**：12/12 都是 `pick_face(solid, 面号)` + `add_port(n)`，**没有**
  `Port.Coordinates` / `StoreParameter` / `SetPort` 的用法。观测到的面号：
  **`10`（轴向口径端面，最稳）**、`22`、`43`、`109`、`4`。
  ⚠️ 面号与几何/构建顺序强相关（仓库 `cst_solver/modeling/picks.py` 自己的说明），
  **跨模型不可复用** ⇒ 新模板要沿用 `add_waveguide_port()` 的"选不中就抛"校验。
* **`lf5` 椭圆过渡段有三种实现**（建模板时得选一种，别混用）：
  ① 三角近似（α2 多数）；② 真半椭圆-解析（`create_elliptical_cylinder` + `square` + `subtract`，MPMBA）；
  ③ 真半椭圆-离散（`np.linspace(π/2, 3π/2, 80)`，γ/δ）。本库 `build_ba_tapered_feed` 走的是 ②。
* **相位参数 `dphi1/dphi2` 的语义已查清**（只在 F、H 出现）：把**同一块透镜**分别绕 z 旋转
  `dphi1` / `dphi2` 后平移到不同输出臂的顶点（F：`rotation(epc1,['0',0,'dphi1'],copy)` +
  `translate→(px6,py6)`；H：两套透镜各带自己的相位）。⇒ 相位差是**透镜朝向**实现的，
  不是几何长度差。其余 10 个 notebook 无相位参数。
* ⚠️ **γ 组（C6 环）的关键坑：`rotation` 不带走端口**。`ANT6_C6_hexring` 的注释明确记着
  「铜管旋转不会带走端口，必须单独 `rotate_port`」：`rotation('wg3',[0,0,180])` 之后要再
  `rotate_port(4,[0,0,180])`。另外它的 6 个端口里两条斜臂要先靠
  `pick_face → set_edge → rotation_face(30°)` 把管口扭到轴向（波端口面法向必须沿坐标轴）。
* **α1 / α2 的分工**：α1（`Ant3_1W2N`、`MPMBA`）是**双馈源**（AB `feed1` + BA `feed2`）
  + 两个铜波导 ⇒ **3 端口**（`wg2:10→P1`、`wg1:10→P3`、`wg1:22→P2`，编号在各 notebook 间有对调）；
  α2（`椭圆透镜1div3`、`B5`）是**单馈源 + 单铜波导** ⇒ 1 端口。

---
