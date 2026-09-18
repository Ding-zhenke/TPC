# P5 证据：GRINLensAntenna 模板与现成 DXF 入口（2026-09-17）

计划条目（`docs/next_plan/README.md` P5）：

> `GRINLensAntenna` 模板；复用已有 `GrinLensSpec/build_grin_lens`，**增加现有 DXF 入口**；
> 不要重做孔阵列算法。

## 1. 交付内容

| 位置 | 内容 |
|---|---|
| `topo_templates/grin_lens_antenna.py` | `GRINLensAntenna(UnitAntenna)`：天线全流程 + 六边形顶点 6 个 GRIN 透镜 |
| `topo_modeler/builders/lens.py` | `holes` 改成**可选**；新增 `build_grin_lens_from_dxf(app, dxf_path, spec=...)`（现成 DXF 入口）；返回值加 `holes_generated`（不回头算几何时**不猜孔数**，`n_holes_* = None`） |
| `topo_modeler/config.py` | `grin_lens_antenna` 从「计划中」挪进**已实现**；新增字段 `geometry.lens_method / lens_dxf / lens_ratio / lens_nx / lens_ny` |
| `topo_templates/__init__.py` | 导出 `GRINLensAntenna` |

**没有重做孔阵列算法**：几何仍全部走 `GrinLensSpec` / `build_grin_lens_holes` /
`export_dxf`，模板只做「接线 + 登记参数 + 调 CST 步骤」。

### 两条入口

| `lens_method` | 行为 | 孔数统计 |
|---|---|---|
| `'generate'`（默认） | `GrinLensSpec` → `build_grin_lens_holes` → `export_dxf` → 建透镜 | 真实值（`n_holes_total=713`、DXF 上部 373） |
| `'dxf'` | 直接用 `lens_dxf` 指向的**现成 DXF**（同事给的 / 旧脚本导出的） | **`None`** —— 不回头数几何、不猜数字 |

**第三条入口 `'insitu'`（2026-09-17 补）**：**不落 DXF**，在 CST 内逐个 `hexagon`
建环（参考 `Ant4_1d2d4_2f2s_circle_DF.ipynb` 的做法）—— 详见
[P5 就地环透镜证据](./p5_grin_lens_insitu_evidence.md)。

**`lens_rotation`（参考的 `dphi`，2026-09-17 补）**：把**透镜绕自身的近焦点自转**
一个角度。判据来自参考 `椭圆透镜单元天线/BA/.../*_rotation.ipynb`：

```text
app1.para('dphi','10')
app1.rotation('epc1', ['0', 0, 'dphi'], ['px2','py2',0])   # 绕顶点（= 近焦点）自转
```

⚠️ 语义容易搞错：`dphi` 是**透镜自己转**（相位图案旋转），**不是**"把透镜挪到别的臂"。
本库实现为 `build_grin_lens(..., self_rotation='dphi')` —— 在"移到 0° 顶点"**之前**
下发一次 `rotation`（那时局部原点正是近焦点，因为椭圆由 `ec_c` 定位 ⇒ 焦点在原点）。
默认 0 ⇒ **不下发、也不登记 `dphi`**（默认序列与旧脚本逐字节一致；登记了没人用就是死写入）。

`lens_method` 三条路线共用同一段 CST 步骤（DXF 导入 → y 镜像补齐 → 椭圆包络拉伸 → 减孔 →
楔形裁剪 → 移到顶点 → 旋转复制 ×6，`unite=False`）—— 就地路线另见其证据文档。

⚠️ **`Rbig` / `Ls` 必须登记**：`build_grin_lens()` 对它们有前置拦截 —— 缺了它们
CST 会弹「请输入变量值」**模态对话框**把脚本永久挂住（P4/V6 教训）。模板在
`_define_all_params()` 里按 `Rbig = a*(3*n_small/4 + lx1)`、`Ls = 2.2*Rbig` 登记，
真机实测落盘 `Rbig=2.91`、`Ls=6.402`。

⚠️ **步骤顺序是本库定的**（参考工程里没有「单元天线 + GRIN 透镜」这个组合）：
材料 → 基板 → VPC → 晶体 → 馈源 → 波导 → **透镜** → 端口 → 整合 → 求解器。
透镜与天线实体没有布尔耦合，放波导之后是为了让片子上的硅先建完。

## 2. 顺带更正一个**写反的文档口径**（真缺陷，非本次引入）

库里三处（`modeler.build_lens()` docstring、`config.py` 字段说明、
`lens_build.py` 旧脚本注释）都写着「抬高 `ratio`（格距 ×k ⇒ 孔数 ÷k²）是唯一有效的
提速手段」。实测（a=0.2425、`r1_0=0.052/r2_0=0.066/n_small=8/lx1=6`）：

| 场景 | 组合 | 全孔数 |
|---|---|---|
| **固定 `nx/ny`，只改 ratio** | 0.5 / 1 / 2 / 4（nx=16, ny=13） | **713 / 713 / 713 / 713** |
| **固定物理尺寸**（nx 随 ratio 缩放，`ec_a`≈3.9） | 0.75→13/10、1→16/13、1.5→24/20、2→32/26 | **449 / 713 / 1630 / 2828** |
| 固定 ratio，缩小器件 | nx/ny = 16/13 → 13/11 | 713 → 487 |

⇒ 固定 `nx/ny` 时孔数与 `ratio` **无关**（抬高它只是把器件物理尺寸等比缩小，**不提速**）；
固定物理尺寸时孔数 **∝ ratio²**（抬高反而更慢）。要提速得**降 ratio 并把 nx/ny 同比缩小**，
且 `nx > 12` 是硬约束（`d_out > d0 = 12·a2`）。

**已更正**：`GrinLensSpec.ratio` docstring、`modeler.build_lens()` docstring、
`config.py` 字段说明、`lens_build.py` 注释、`grin_lens_geometry.md` 新增 §4.3
（含上表实测数据），并加三条回归钉住定律
（`test_lens_ratio_does_not_change_hole_count`、
`test_hole_count_scales_with_ratio_squared_at_fixed_size`、
`test_small_ellipse_is_rejected_by_geometry_constraint`）。

> 危害说明：提示写反会让人"为了更快去抬 ratio"，结果**激光器物理尺寸悄悄变了、
> 耗时一点没省** —— 属于"文档让人做错事"，比缺文档更糟。

## 3. 离线证据（不需要 CST）

`python -m pytest topo_templates/tests/test_grin_lens_antenna.py -q` → **14 项通过**：

| 守住什么 | 用例 |
|---|---|
| 几何与 V6 真机验过的规格**逐值相同**（`ec_a=3.88`、`r_big=2.91`、`ec_c=2.7569…`、`r_in=0.052`、`r_out=0.066`） | `test_default_lens_spec_matches_the_verified_configuration` |
| `ratio` 与孔数的定律（两条）+ `nx>12` 约束 | 上述三条 |
| 现成 DXF 入口的参数校验（缺参数 ValueError / 文件不存在 FileNotFoundError / 不猜孔数） | `test_dxf_method_*` |
| `Rbig`/`Ls` 被登记且是**表达式**不是写死小数 | `test_define_all_params_registers_rbig_and_ls` |
| 天线部分没被改坏（路径格点、臂端、阵列范围与 `UnitAntenna` 逐值相同） | `test_antenna_geometry_is_unchanged[AB/BA]` |
| 无 CST 时明确失败（不是静默跳过） | `test_build_without_cst_raises` |

## 4. 真机证据（CST 2026，**只建模不求解**）

命令：`python scripts/verify_grin_lens_antenna_real.py` → **OK 10 / FAIL 0**（退出码 0）。
天线用**小尺寸**（`straight_length=6 / arm_length=8` ⇒ 阵列 10/8/8）以便分钟级完成；
透镜用默认 `nx=16/ny=13`（上半 373 条多段线）。

| 观测 | 实测 |
|---|---|
| A `lens_method='generate'` 建模（天线 + 透镜） | ✅ 未抛异常、**0 条 CST 消息** |
| A1 孔阵列落 DXF | ✅ `A(generate).dxf` 222 KB，`n_holes_total=713`、DXF 上部 373 条 |
| A2 透镜实体与几何参数 | ✅ `lens_epc`、`holes_generated=True`、`ec_a=3.88`、`ec_c=2.756938…` |
| A3 历史里有透镜步骤 | ✅ DXF 导入 / 椭圆 / 减孔 / 旋转复制 都在 |
| A4 参数表里有 `Rbig` / `Ls` | ✅ `Rbig=2.91`、`Ls=6.402` |
| B `lens_method='dxf'`（拿 A 的 DXF 再建一次） | ✅ 未抛异常、**0 条 CST 消息** |
| B1 用现成 DXF 且不猜孔数 | ✅ `holes_generated=False`、`n_holes_total=None` |
| B2 两条入口都真的导入了 DXF | ✅ 两个工程的历史都含 `Import` |
| 收尾 | ✅ 无残留 DE（回到基线 `[]`） |

**`lens_rotation`（`dphi`）真机验收（2026-09-18，同一脚本的 C 段 + 就地路线的
`verify_grin_lens_insitu_real.py` C 段）**：

| 观测 | 实测 |
|---|---|
| C 建模（`self_rotation='dphi'`，就地路线 N=10 ⇒ 91 象限孔） | ✅ 未抛异常、**0 条 CST 消息** |
| C1 `dphi` 是 **CST 参数**而不是烘死的角度 | ✅ 参数表 `dphi=10` |
| C2 自转步骤真的下发 | ✅ 历史 caption 里 `rotation` **2 条**（自转 1 + 旋转复制 1） |
| C3 实体名与组件 | ✅ `grib_rot`（实体名 = 给的名字） |

### 4.1 ⚠️ 一个 30 分钟的真机挂死 —— 并因此补上前置拦截

第一版 C 段**忘了登记 `dphi`**（`self_rotation` 引用的参数名），结果是：

* CST **不报错**，而是弹「请输入变量值」的模态对话框**把脚本挂住** —— 实测挂了
  **30 分钟以上**，而且 `EnumWindows` 枚举**看不到那个框**
  （`scripts/cst_dialog_guard.py` 的 `describe_dialogs()` 返回"没有可见的 CST 对话框"），
  连"对话框守卫"都没救回来；只有强杀进程才结束。

⇒ 除了在脚本里登记参数，**库本身也得拦**：`build_grin_lens()` 与
`build_grin_lens_insitu()` 现在都用「参数是否存在」探针（`guard.param_existed`）
把 `self_rotation` 给的**参数名**、以及就近路线放置用的 `Rbig` 一起做前置检查，
缺了就抛 `ValueError`（而不是让 CST 去挂）。回归：
`topo_modeler/tests/test_grin_lens_insitu.py` 的
`test_insitu_preflight_rejects_unregistered_rotation_param`、
`test_insitu_preflight_rejects_missing_rbig_when_placing`、
`test_dxf_route_preflight_rejects_unregistered_rotation_param`。

> 这条与 P4/V6 的 `Rbig`/`Ls` 教训是**同一类**：CST 缺参数时的失败方式不是异常，
> 而是"挂着等你输入"。区别是这次**连对话框都看不见** —— 所以拦截只能靠**事先查参数表**，
> 不能靠事后看窗口。

## 5. 复现命令

```text
python -m pytest topo_templates/tests/test_grin_lens_antenna.py -q   # 离线 14 项
python scripts/verify_grin_lens_antenna_real.py                      # 真机（只建模，分钟级）
```

## 6. 仍未覆盖

* **求解级**：这个组合（天线 + 透镜）**没有做过任何求解**，辐射/透镜相位效果
  完全未验证 —— 属 P4/V2、V9（需用户先确认算例与开销）；
* 参考工程里**没有**「单元天线 + GRIN 透镜」这个组合，所以本模板的
  **实体命名与步骤顺序**是本库定的，不是从参考工程抄的（已在 docstring 说明）；
* `lens_method='dxf'` 只校验"文件存在"，**不校验 DXF 内容**（是否只含 y≥0 的一半、
  图层名是否与 `component` 一致）—— 拿别人的 DXF 时需人工确认，见
  `build_grin_lens_from_dxf` docstring 的提醒。
