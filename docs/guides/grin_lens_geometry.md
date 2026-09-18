# GRIN 透镜几何规格

从旧计划提取的参考公式；实现见 `topo_modeler/builders/lens.py`。剩余实现与真机验收见 [计划](../next_plan/README.md)。


06 对这两块**只给了「做什么」，没给「怎么做」和「怎么验证」**。现已补齐如下
（**全部来自可运行的代码，不是推测** —— 见 `topo_modeler/builders/lens.py` 的 docstring
与 `topo_modeler/tests/test_lens.py` 的等价性回归）。

### 4.1 `method='hexagon'` 的半径-距离公式 ✅

**坐标系**：局部系，原点 = **椭圆近焦点** = **大六边形 0° 顶点**。

| 量 | 公式 | 单位 | 参考配置取值 |
|---|---|---|---|
| 六边形半径 | `hex_size = a / √3 / ratio` | mm | 0.0175003125 |
| **孔网格格距** | `a2 = hex_size · √3` = **`a / ratio`** | mm | 0.0303125 |
| 长半轴 | `ec_a = nx · a2` | mm | 1.151875 |
| 短半轴 | `ec_b = ny · a2 · sind(60°)` | mm | 0.892547432 |
| 离心率 | `e = √(ec_a² − ec_b²) / ec_a` | — | 0.632126955 |

⚠️ **孔半径的换算约定（容易错一倍，2026-09-18 更正）**：本库 `GrinLensSpec` 用
``r = r1_0 / ratio``，而参考 `para_init` 写的是 ``r = 2·r_raw / ratio``
（`r_raw = 50.5/61.3 µm`）。⇒ **要给出与参考同样的等效半径，模板里的 `r1_0`
必须写 `2·r_raw`**（如 `ratio=2` 时参考的有效半径是 0.0505，本库就要传 `r1_0 = 0.101`）。
写 0.0505 会让孔半径**小一半**。`PowerDivider` 与 `MultiPortAntenna` 的默认值已按此更正
（回归 `test_divider_lens_defaults_match_the_reference_arithmetic` 等）；
`GRINLensAntenna` 的 `ratio=1.0 / r1_0=0.052`（等效 ≈0.052）是 V6 真机验收过的配置，未动。
| 焦距（椭圆中心） | `ec_c = e · ec_a` | mm | 0.728131237 |
| **渐变区起点** | `d0 = 6 · hex_size · 2 · √3` = **`12 · a2`** | mm | 0.36375 |
| 内圈孔半径 | `r1 = r1_0 / ratio` | mm | 0.012625 |
| 外圈孔半径 | `r2 = r2_0 / ratio` | mm | 0.015325 |

**孔心筛选**：椭圆包络判据 —— 到**两焦点**距离之和 `≤ 2·ec_a·tol`
（焦点在原点与 `(2·ec_c, 0)`）。`tol` 默认 **1.03**（参考实现用 1.1）：
`>1` 是为了把刚压在边界上的孔也收进来，否则椭圆最扁的两头会留下一圈没孔的实心边。

**孔半径**：沿椭圆**等高线**距离 `d_ell = √(x² + y²/(1−e²))`，
在 `[d0, d_out]` 上线性插值到 `[r1, r2]`：

```
t     = clip((d_ell − d0) / (d_out − d0), 0, 1)
r(x,y)= r1 + (r2 − r1) · t
```

**`d_out` 的确切含义**（原来完全没写清，两种语义差别很大）：

| 取值 | `d_out` | 后果 |
|---|---|---|
| `'ec_a'`（**默认，原脚本的取值**） | `ec_a` | `d_ell` 实际范围是 `0 → (ec_c + ec_a)`，分母只到 `ec_a` ⇒ **外侧约 63% 的孔全是 `r2`**，孔半径只在前 37% 单调渐变 |
| `'shift_plus_ec_a'` | `ec_c + ec_a` | 孔半径沿**整条**透镜单调渐变到底 |

> 原脚本注释里就写着这一点（并提示「想全长度渐变就改掉」），但**默认行为**是前者
> —— 本库把它固化成显式参数 `d_out_mode`，默认与原脚本一致（有等价性回归钉住）。

**层数定义**：孔网格是**点型六边形交排网格**（`HexGridVisualizer`，
`orientation='pointy'`、`coord_type='offset_q'`），行范围 `(-ny, ny)`；
**列范围不能取 `(-nx, nx)`** —— 见下。

🔴 **必须记住的坑：列范围按椭圆真实 x 范围取。** 局部系里近焦点在原点，
椭圆 `x ∈ [ec_c − ec_a, ec_c + ec_a]` **关于 0 不对称**，所以

```
col_min = floor((ec_c − ec_a) / a2) − 1
col_max = ceil ((ec_c + ec_a) / a2) + 1
```

原脚本注释记着：旧版写 `(-nx, +nx)`，网格只到 `x = nx·a2`，而椭圆要伸到
`ec_c + ec_a` ⇒ **椭圆外侧整片没孔 = 实心硅**。本库的
`test_coverage_check_catches_missing_columns` 就是这条的反例测试。

**验收判据**（三道，全部与 CST 无关）：`GrinLensHoles.run_self_checks()`

| 自查 | 判据 | 参考配置实测 |
|---|---|---|
| 裁剪不重叠 | 楔形裁剪后透镜与大六边形的重叠面积 `< 1e-3 mm²` | 0.00000000 mm² |
| 孔阵覆盖 | 透镜内采样点到最近孔心的最远距离 `d_max ≤ 1.05 · a2/√3` | 1.00×（理论值 0.0175） |
| 镜像等价 | 「上半 ∪ y镜像」与完整阵列的对称差面积 `< 1e-6 mm²` | 6.8e-15 mm² |

### 4.2 `method='dxf'` 的参数 —— ⚠️ 原计划的说法**已过时**

计划写「`cst_solver.import_dxf()` 只收 `filename, add, HealSelfIntersections, ...`，
**没有** `component` / `material` / `height` / `translate`」。

**实测（2026-09-15，`cst_solver/import_export/io.py:91-113`）：前三个都有**，
而且 `component` / `material` / `height` 还支持**列表**（逐图层给不同材质/厚度），
CST 侧走 `.AddLayer`。原脚本 `lens_build.py:270` 本身就是
`app.dxf_import(lens_dxf, add='True', component='gridlens', height='h')`。

所以这条「硬缺口」实际只剩 **`translate`** —— 而平移在原脚本里本来就是**单独一句**
`app.translate(...)`（`lens_build.py:327-328`），不是导入参数。
`build_grin_lens()` 已按原脚本的顺序把这两句平移放在导入之后，不需要新参数。

**剩下的**：`method='dxf'` 只差一个入口函数（复用 `build_grin_lens()` 的后半段）。
✅ **2026-09-17 已补**：`builders/lens.py::build_grin_lens_from_dxf(app, dxf_path, spec=...)`
（`build_grin_lens` 的 `holes` 改成可选，现成 DXF 不再回头算几何）。

### 4.3 `ratio` 与孔数的关系 —— ⚠️ 库里原先**写反了**（2026-09-17 实测更正）

`modeler.build_lens()` / `config.py` / 旧脚本注释里曾写着
「抬高 `ratio`（格距 ×k ⇒ 孔数 ÷k²）是唯一有效的提速手段」。**这句话方向反了。**
用 `grin_lens_spec_from_cst_params` + `build_grin_lens_holes` 实测（a = 0.2425、
`r1_0=0.052 / r2_0=0.066 / n_small=8 / lx1=6`）：

| 场景 | 组合 | 全孔数 |
|---|---|---|
| **固定 `nx/ny`，只改 ratio** | ratio 0.5 / 1 / 2 / 4（nx=16, ny=13） | **713 / 713 / 713 / 713** |
| **固定物理尺寸**（nx 随 ratio 同步缩放，`ec_a` 都 ≈3.9） | 0.75→13/10、1→16/13、1.5→24/20、2→32/26 | **449 / 713 / 1630 / 2828** |
| 固定 ratio，缩小器件 | nx/ny = 16/13 → 13/11 | 713 → 487 |

**结论（两条）**：

1. 固定 `nx/ny` 时孔数与 `ratio` **无关** —— 因为 `ec_a = nx·a2` 与格距 `a2 = a/ratio`
   同比缩放：抬高 ratio 只是把**器件物理尺寸**等比缩小，孔数不变（**不提速**）；
2. 固定物理尺寸时孔数 **∝ ratio²** ⇒ **要减少孔数（提速）得降 ratio 并把 nx/ny
   同比缩小**；而且 `nx > 12` 是硬约束（`d_out > d0 = 12·a2`，否则
   `LensGeometryError: 渐变区间为空`），所以固定尺寸下提速幅度有限
   （本组参数 ratio 下限约 0.75，最多约 ÷1.8）。要大幅减孔只能整体缩小器件。

回归：`topo_templates/tests/test_grin_lens_antenna.py` 的
`test_lens_ratio_does_not_change_hole_count`（钉住"与 ratio 无关"）、
`test_hole_count_scales_with_ratio_squared_at_fixed_size`（钉住 ∝ ratio²）、
`test_small_ellipse_is_rejected_by_geometry_constraint`（钉住 nx>12 约束）。

> 这条更正是为了守住仓库的一条纪律：**文档里的数与方向必须有实测依据**。
> 提速提示写反会让使用者"为了更快去抬 ratio"，结果激光器尺寸悄悄变了、耗时一点没省。

### 4.4 `method='insitu'`（就地 hexagon 环透镜）—— 另一套几何，**别与 4.1 混用**

4.1–4.3 讲的是「**椭圆包络 + DXF 孔阵列**」那条路（`GrinLensSpec`）。
参考工程里还有另一套做法：**不落 DXF**，在 CST 内直接逐个 `hexagon` 建**环形**
孔阵（`功分器加天线\1分4\…circle_DF.ipynb`）。它**没有椭圆**，环也是**正六边形网格**
的同心圈，参数完全不同：

| 量 | 公式（参考写法） | 本库 | a=0.2425 / N=30 下的值 |
|---|---|---|---|
| 网格半格距 | `HEX_SIZE = a/√3/2` | `a/sqr(3)/2` | 0.07000372013924212 |
| 列间步距 | `a2 = HEX_SIZE·√3` | `HEX_SIZE*sqr(3)` | 0.12125（= a/2） |
| 层数 | `N = (y[1]+2)*2` | `n_layers`（默认 30） | 30 |
| 内圈半径门槛 | `d0 = 8·HEX_SIZE·2·√3` | `d0_layers*HEX_SIZE*2*sqr(3)` | 1.94（= 8a） |
| 孔半径 | `distance < d0` ⇒ `r1`；否则 `r1 + (r2-r1)·(distance-d0)/(N·a2-d0)` | 同左（`r1_0=0.0505`、`r2_0=0.0613`） | — |
| 孔集合 | **六边形网格的第一象限**格点（另一半靠镜像） | `quadrant_only=True` | 721 个象限格点 ⇒ 共 1426 孔 |

含义上的两个坑：

1. **孔半径的渐变公式里"距离"是烘死的数字**（参考用 f-string 写进去的），所以这条路线
   **不是全参量化**：改 `n_layers` / `d0_layers` 必须整枚重建（本库由
   `grin_ring_holes()` 离线重算，不缓存）。这与 P4 §8.7 的"只用 CST 表达式"标准有差距，
   是**跟着参考口径**的有意选择；
2. **这条路线不需要 `Ls`**（`Ls` 只服务于 4.1 的楔形裁剪）—— 登记它就是死写入，
   所以模板按路线登记参数（真机被 `verify_model_parameter_usage.py` 抓到后改的）。

⚠️ 两条路线的**组件口径不同**（DXF 路线为了与旧脚本逐字节一致，最终透镜落在
`component1`；就地路线全程用 `component`），差异与理由见
[P5 就地环透镜证据](../validation/p5_grin_lens_insitu_evidence.md) §5。

回归：`topo_modeler/tests/test_grin_lens_insitu.py`（27 项，常数/孔集/两段半径/下发序列/
参数登记/组件）。

### 4.5 `dphi`（透镜绕自身近焦点自转）—— 与"挪到别的臂"不是一回事

参考 `椭圆透镜单元天线/BA/.../*_rotation.ipynb`：

```text
app1.para('dphi','10')
app1.rotation('epc1', ['0', 0, 'dphi'], ['px2','py2',0])   # 绕顶点自转
```

`['px2','py2',0]` 是该工程的 **0° 顶点**，而在本库 `build_grin_lens()` 里顶点就等价于
**椭圆的近焦点**（椭圆中心由 `ec_c` 定位 ⇒ 焦点恰在局部原点）。所以本库把它实现成
**在"移到 0° 顶点"之前**下发一次 `rotation(name, [0, 0, dphi])`：

* 用 CST **参数** `dphi`（不把角度烘进 VBA，符合 §8.7 的表达式口径）；
* 默认 0 ⇒ 不下发、**也不登记** `dphi`（登记了没人引用就是死写入）；
* 回归：`topo_templates/tests/test_grin_lens_antenna.py` 的
  `test_self_rotation_step_is_inserted_before_placement`（还钉住"自转必须在平移之前"）、
  `test_lens_rotation_default_is_zero_and_sends_nothing`。

⚠️ 与 `PowerDivider` 的 `dphi1/dphi2` **不同**：后者是"把同一枚透镜绕 z 转 dphi 后当
**第二个相位副本**放到另一条输出臂"（参考 `1div4`/`2H4L`）。两者都叫"相位"，但一个是
自转、一个是复制，别混用。

---
