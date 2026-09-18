# 旧 notebook 迁移登记：P1/P2/P3 批次

> 本表由 `python scripts/classify_notebook_migration.py --write` 生成（只解析 `.ipynb` 的 JSON，**不执行** notebook、不改源文件）。
> P0 的 5 个见 [P0 登记表](./notebook_migration_p0.md)；
> 清点表见 [notebook_migration_inventory.md](./notebook_migration_inventory.md)。

## 1. 汇总

| 状态 | 数量 |
|---|---|
| COVERED | 65 |
| PARTIAL | 7 |
| NO_TEMPLATE | 5 |
| NOT_MIGRATED | 5 |

| 器件类别 | 数量 | 对应模板 |
|---|---|---|
| GRIN 透镜单元天线 | 40 | GRINLensAntenna |
| MZI 开关 | 14 | MZISwitch |
| 多端口天线 | 9 | MultiPortAntenna |
| 功分器 | 9 | PowerDivider |
| 泄漏波天线 | 5 | （无模板） |
| 分析/测试/优化 | 5 | （无模板） |

## 2. 状态含义

| 状态 | 含义 |
|---|---|
| `COVERED` | 有模板对应，拓扑/参数口径能对上（可迁移） |
| `PARTIAL` | 有模板对应，但该 notebook 有模板**未覆盖**的特征（见列） |
| `NO_TEMPLATE` | 本库还没有对应器件模板（列出缺什么） |
| `NOT_MIGRATED` | P3 分析/测试/优化类，**保留不迁移** |

## 3. 缺口汇总（按特征聚合）

| 缺口特征 | 影响 notebook 数 | 含义 | 例子 |
|---|---|---|---|
| `mzi_parallel` | 4 | MZI 并联（10 点路径），本模板只实现 6 点的 basic（== cascade） | `MPMBA/Ant3_AB_epc_mf.ipynb` |
| `lens_subproject` | 1 | 透镜来自 CST 子工程（`.sab`），本库无对应入口 | `多端口/Ant6_undiretional/ANT6_C6_hexring.ipynb` |
| `twisted_waveguide` | 1 | 扭波导（`rotate_port`/`rotation_face`），本库无对应入口 | `多端口/Ant6_undiretional/ANT6_C6_hexring.ipynb` |
| `divider_2h4l` | 1 | 2H4L 双透镜组结构，1分6 用的不是本模板的 2×3 级联 | `功分器加天线/B5/Ant6_2H4L_epc.ipynb` |
| `mzi_anti` | 1 | MZI anti（两组 `ax/ay` + 不对称泵浦），本模板未实现 | `开关尝试/AB/MZI-anti.ipynb` |

> **缺口性质**：`lens_in_situ`（在 CST 内用 `app.hexagon()` 逐环建透镜）**本库已实现** —— `GRINLensAntenna(lens_method="insitu")`，见 [P5 就地环透镜证据](../validation/p5_grin_lens_insitu_evidence.md)。它在下面仍出现，是因为命中该特征的 notebook 对应的模板**不是** `GRINLensAntenna`（模板归属由目录分类决定），而不是「库里做不到」——真要把它们迁进来，仍需要给对应器件补透镜能力。

> 当前影响最大的三项缺口：`mzi_parallel`（4 个）、`lens_subproject`（1 个）、`twisted_waveguide`（1 个）。

## 4. 逐条登记

| # | notebook | 优先级 | 类别 | 模板 | 状态 | CST 参数行 | 未覆盖特征 |
|---|---|---|---|---|---|---|---|
| 1 | `MPMBA/Ant3_AB_epc_mf.ipynb` | P1 | 多端口天线 | `MultiPortAntenna` | PARTIAL | 58 | mzi_parallel |
| 2 | `MPMBA/Ant3_epc.ipynb` | P1 | 多端口天线 | `MultiPortAntenna` | COVERED | 52 | — |
| 3 | `MPMBA/Ant3_epc2.ipynb` | P1 | 多端口天线 | `MultiPortAntenna` | COVERED | 50 | — |
| 4 | `MPMBA/Ant3_epc_mf.ipynb` | P1 | 多端口天线 | `MultiPortAntenna` | PARTIAL | 60 | mzi_parallel |
| 5 | `单元天线GRIB/AB型/120°透镜/Ant1_grid_120D_circle_st.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 41 | — |
| 6 | `单元天线GRIB/AB型/120°透镜/Ant1_grid_120D_circle_turn.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 40 | — |
| 7 | `单元天线GRIB/AB型/120°透镜/Ant1_grid_120D_circle_turn_DF.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 40 | — |
| 8 | `单元天线GRIB/AB型/120°透镜/Ant1_grid_240D_circle.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 38 | — |
| 9 | `单元天线GRIB/AB型/180°透镜/Ant1_grid_circle.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 40 | — |
| 10 | `单元天线GRIB/AB型/180°透镜/Ant1_grid_circle_DF.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 40 | — |
| 11 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_120D.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 38 | — |
| 12 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_120D_DF.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 38 | — |
| 13 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_120D_circle.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 40 | — |
| 14 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_120D_circle_DF-140.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 40 | — |
| 15 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_120D_circle_DF-EX.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 42 | — |
| 16 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_120D_circle_DF.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 40 | — |
| 17 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_120D_circle_square.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 45 | — |
| 18 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_120D_circle_turn.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 40 | — |
| 19 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_240D_circle-hex.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 40 | — |
| 20 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_240D_circle.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 40 | — |
| 21 | `单元天线GRIB/BA型/180°透镜/Ant1_grid_BA.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 40 | — |
| 22 | `单元天线GRIB/BA型/180°透镜/Ant1_grid_BA_DF.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 40 | — |
| 23 | `单元天线GRIB/BA型/180°透镜/Ant1_grid_BA_circle.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 42 | — |
| 24 | `单元天线GRIB/BA型/180°透镜/Ant1_grid_BA_circle_DF.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 42 | — |
| 25 | `多端口/Ant3_1W2N/Ant3_240D3_epc.ipynb` | P1 | 多端口天线 | `MultiPortAntenna` | COVERED | 48 | — |
| 26 | `多端口/Ant3_1W2N/Ant3_BA_240D_epc.ipynb` | P1 | 多端口天线 | `MultiPortAntenna` | COVERED | 50 | — |
| 27 | `多端口/Ant6_undiretional/ANT6_C6_hexring.ipynb` | P1 | 多端口天线 | `MultiPortAntenna` | PARTIAL | 1 | lens_subproject, twisted_waveguide |
| 28 | `多端口/Ant6_undiretional/ANT6_undirectional.ipynb` | P1 | 多端口天线 | `MultiPortAntenna` | COVERED | 22 | — |
| 29 | `多端口/Ant6_undiretional/ANT6_undirectional_test.ipynb` | P1 | 多端口天线 | `MultiPortAntenna` | COVERED | 22 | — |
| 30 | `椭圆透镜单元天线/AB/Ant1_grid_120D_epc-0d.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 44 | — |
| 31 | `椭圆透镜单元天线/AB/Ant1_grid_120D_epc-0d_DR.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 44 | — |
| 32 | `椭圆透镜单元天线/AB/Ant1_grid_120D_epc0.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 44 | — |
| 33 | `椭圆透镜单元天线/AB/Ant1_grid_120D_epc_turn.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 44 | — |
| 34 | `椭圆透镜单元天线/AB/Ant1_grid_240D_epc.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 44 | — |
| 35 | `椭圆透镜单元天线/AB/Ant1_grid_240D_epc_epc.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 44 | — |
| 36 | `椭圆透镜单元天线/AB/Ant1_grid_240D_epc_epc_fpr.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 44 | — |
| 37 | `椭圆透镜单元天线/BA/D120/Ant1_grid_BA_120D_circle_epc.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 44 | — |
| 38 | `椭圆透镜单元天线/BA/D120/Ant1_grid_BA_120D_epc_epc.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 44 | — |
| 39 | `椭圆透镜单元天线/BA/D120/Ant1_grid_BA_120D_epc_rotation.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 45 | — |
| 40 | `椭圆透镜单元天线/BA/D120/Ant1_grid_BA_240D_circle_epc.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 44 | — |
| 41 | `椭圆透镜单元天线/BA/D120/Ant1_grid_BA_240D_epc_1c.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 44 | — |
| 42 | `椭圆透镜单元天线/BA/D120/Ant1_grid_BA_240D_epc_epc.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 44 | — |
| 43 | `椭圆透镜单元天线/BA/D120/ep_cal.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 0 | — |
| 44 | `椭圆透镜单元天线/BA/leaky/Ant1_grid_BA_120D_circle_epc.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 50 | — |
| 45 | `椭圆透镜单元天线/BA/leaky/crossover_1.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 49 | — |
| 46 | `椭圆透镜单元天线/BA/rotation/Ant1_grid_BA_120D_epc_ex.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 47 | — |
| 47 | `椭圆透镜单元天线/BA/rotation/Ant1_grid_BA_120D_epc_rotation.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 45 | — |
| 48 | `椭圆透镜单元天线/透镜优化/Ant1_grid_BA_120D_circle_epc.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 44 | — |
| 49 | `椭圆透镜单元天线/透镜优化/sweep.ipynb` | P1 | GRIN 透镜单元天线 | `GRINLensAntenna` | COVERED | 10 | — |
| 50 | `Leaky/ANT_LEAKY_EPC_GRID.ipynb` | P2 | 泄漏波天线 | `—` | NO_TEMPLATE | 50 | — |
| 51 | `Leaky/ANT_LEAKY_MK_GRID.ipynb` | P2 | 泄漏波天线 | `—` | NO_TEMPLATE | 47 | — |
| 52 | `Leaky/ANT_LEAKY_MK_GRID_opt.ipynb` | P2 | 泄漏波天线 | `—` | NO_TEMPLATE | 47 | — |
| 53 | `Leaky/ANT_LEAKY_MK_GRID_z.ipynb` | P2 | 泄漏波天线 | `—` | NO_TEMPLATE | 47 | — |
| 54 | `Leaky/analysis_GRIN_approximation.ipynb` | P2 | 泄漏波天线 | `—` | NO_TEMPLATE | 0 | — |
| 55 | `功分器加天线/1分4/Ant4_1d2d4_2f2s_2G2F_circle_DF.ipynb` | P2 | 功分器 | `PowerDivider` | COVERED | 44 | — |
| 56 | `功分器加天线/1分4/Ant4_1d2d4_2f2s_2G2F_circle_DF_grid120.ipynb` | P2 | 功分器 | `PowerDivider` | COVERED | 44 | — |
| 57 | `功分器加天线/1分4/Ant4_1d2d4_2f2s_circle_DF.ipynb` | P2 | 功分器 | `PowerDivider` | COVERED | 44 | — |
| 58 | `功分器加天线/1分4/Ant4_1d2d4_2f2s_circle_DF_BA.ipynb` | P2 | 功分器 | `PowerDivider` | COVERED | 44 | — |
| 59 | `功分器加天线/B5/Ant6_2H4L_epc.ipynb` | P2 | 功分器 | `PowerDivider` | PARTIAL | 75 | divider_2h4l |
| 60 | `功分器加天线/椭圆透镜1div3/Ant2_1div2_AB_120D_epc.ipynb` | P2 | 功分器 | `PowerDivider` | COVERED | 48 | — |
| 61 | `功分器加天线/椭圆透镜1div3/Ant2_1div2_BA_120D_epc.ipynb` | P2 | 功分器 | `PowerDivider` | COVERED | 48 | — |
| 62 | `功分器加天线/椭圆透镜1div3/Ant3_1div3_BA_120D_epc.ipynb` | P2 | 功分器 | `PowerDivider` | COVERED | 48 | — |
| 63 | `功分器加天线/椭圆透镜1div3/Ant4_1div4_BA_120D_epc.ipynb` | P2 | 功分器 | `PowerDivider` | COVERED | 59 | — |
| 64 | `开关尝试/AB/MZI-BA.ipynb` | P2 | MZI 开关 | `MZISwitch` | COVERED | 43 | — |
| 65 | `开关尝试/AB/MZI-GRIB.ipynb` | P2 | MZI 开关 | `MZISwitch` | COVERED | 50 | — |
| 66 | `开关尝试/AB/MZI-anti.ipynb` | P2 | MZI 开关 | `MZISwitch` | PARTIAL | 47 | mzi_anti |
| 67 | `开关尝试/AB/MZI-cascade.ipynb` | P2 | MZI 开关 | `MZISwitch` | COVERED | 45 | — |
| 68 | `开关尝试/AB/MZI-hex.ipynb` | P2 | MZI 开关 | `MZISwitch` | PARTIAL | 53 | mzi_parallel |
| 69 | `开关尝试/AB/MZI-parallel.ipynb` | P2 | MZI 开关 | `MZISwitch` | PARTIAL | 53 | mzi_parallel |
| 70 | `开关尝试/AB/MZI.ipynb` | P2 | MZI 开关 | `MZISwitch` | COVERED | 45 | — |
| 71 | `开关尝试/AB/cal_mzi.ipynb` | P2 | MZI 开关 | `MZISwitch` | COVERED | 0 | — |
| 72 | `开关尝试/AB/mzi_opt_cal.ipynb` | P2 | MZI 开关 | `MZISwitch` | COVERED | 0 | — |
| 73 | `开关尝试/AB/mzi_opt_cal_feed.ipynb` | P2 | MZI 开关 | `MZISwitch` | COVERED | 0 | — |
| 74 | `开关尝试/AB/mzi_opt_cal_feed_all.ipynb` | P2 | MZI 开关 | `MZISwitch` | COVERED | 0 | — |
| 75 | `开关尝试/AB/test.ipynb` | P2 | MZI 开关 | `MZISwitch` | COVERED | 0 | — |
| 76 | `开关尝试/BA/MZI-BA-wo.ipynb` | P2 | MZI 开关 | `MZISwitch` | COVERED | 43 | — |
| 77 | `开关尝试/BA/MZI-BA.ipynb` | P2 | MZI 开关 | `MZISwitch` | COVERED | 45 | — |
| 78 | `针对隔离和开关的分析研究/AB-MXene.ipynb` | P3 | 分析/测试/优化 | `—` | NOT_MIGRATED | 41 | — |
| 79 | `针对隔离和开关的分析研究/AB-light-wo.ipynb` | P3 | 分析/测试/优化 | `—` | NOT_MIGRATED | 39 | — |
| 80 | `针对隔离和开关的分析研究/AB-light.ipynb` | P3 | 分析/测试/优化 | `—` | NOT_MIGRATED | 41 | — |
| 81 | `针对隔离和开关的分析研究/BA-MXene.ipynb` | P3 | 分析/测试/优化 | `—` | NOT_MIGRATED | 41 | — |
| 82 | `针对隔离和开关的分析研究/BA-light.ipynb` | P3 | 分析/测试/优化 | `—` | NOT_MIGRATED | 41 | — |

## 4. 验收口径

* **几何验收**：P0 已逐值比对；P1/P2 的复杂器件模板走**本库口径**（设计记录 D1），因此本表只登记「分类 / 对应模板 / 未覆盖特征」，**不声称几何等价**；每个器件要单独取证才有几何结论。
* **仿真验收**：**全部未做**（需要真实求解）—— 属计划 P4/V2、V7、V9，等用户确认算例与开销。
* **迁移方式**：不重写 notebook，而是登记「旧 notebook → 新库模板」的映射；有缺口的部分要么补模板能力，要么在计划里明确不做。

