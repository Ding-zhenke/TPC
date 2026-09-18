# 旧 notebook 迁移清点表

> **本文件由 `scripts/survey_legacy_notebooks.py` 生成**（只读扫描，不执行 notebook）。
> 用途：让「87 个 notebook 的迁移状态逐个可查」这句话变成一张**真的表**。

- 源目录：`D:\成电博士生涯\拓扑光子晶体模型\硅基`
- `.ipynb` 总数：**87**
- 扫描方式：只解析 `.ipynb` 的 JSON 结构、抽 code cell 源码做**正则特征匹配**；
  **不执行**任何单元格，也不改动任何源文件。

## 1. 按优先级汇总

| 优先级 | 含义 | notebook 数 |
|---|---|---|
| P0 | 验证基础流水线（直波导 / 普通单元天线 / 透镜核心） | 5 |
| P1 | GRIN 透镜（最大类）+ 多端口天线 | 49 |
| P2 | 功分器 / 耦合器 + MZI 开关 | 28 |
| P3 | 分析/测试/优化 + 未分类（**保留，不迁移**） | 5 |
| **合计** | | **87** |

## 2. 按分类汇总

| 分类（目录） | 优先级 | 数量 | 说明 | 新库里对应能力 |
|---|---|---|---|---|
| `直波导` | P0 | 3 | 基础流水线（已有 StraightWaveguide 覆盖） | ✅ `StraightWaveguide` |
| `普通单元天线` | P0 | 2 | 基础流水线（已有 UnitAntenna 覆盖） | ✅ `UnitAntenna` |
| `单元天线GRIB` | P1 | 20 | GRIN 透镜天线（最大类） | 🔄 `builders/lens.py`（几何已就绪，模板待建） |
| `椭圆透镜单元天线` | P1 | 20 | GRIN 透镜天线（最大类） | 🔄 `builders/lens.py`（几何已就绪，模板待建） |
| `多端口` | P1 | 5 | 多端口天线（验证多路径） | ❌ 无（阶段 8 多路径） |
| `MPMBA` | P1 | 4 | 多端口天线（验证多路径） | ❌ 无（阶段 8 多路径） |
| `开关尝试` | P2 | 14 | MZI 开关（验证复杂干涉结构） | ❌ 无（阶段 8 MZI） |
| `功分器加天线` | P2 | 9 | 功分器 / 耦合器（验证分支结构） | ❌ 无（阶段 8 功分器） |
| `Leaky` | P2 | 5 | 泄漏波天线（原表未单列，归 P2） | ❌ 无 |
| `针对隔离和开关的分析研究` | P3 | 5 | 分析类（原表 P3「分析/测试/优化」） | ➖ 不迁移（分析类） |

## 3. 逐个清单（迁移前先看这一列）

**证据说明**：`CST 参数` = 从 `.para(...)` / `StoreParameter` / CST 参数三元组里抽到的参数**个数**；`透镜 / MZI / 功分 / 端口` 由**参数名**是否命中对应签名判定（比自由文本正则可靠得多）；`六边 / DXF / 旋转 / GA` 是收紧后的正则特征。

| # | 相对路径 | 优先级 | 大小(KB) | 代码行 | CST 参数 | 透镜 | MZI | 功分 | 端口 | 六边 | DXF | 旋转 | GA |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `普通单元天线/Ant1_D_AB_120D_cylinder_DF.ipynb` | P0 | 740.8 | 303 | 38 |  |  |  |  |  |  | ✓ |  |
| 2 | `普通单元天线/Ant1_D_BA_120D_circle_DF.ipynb` | P0 | 555.6 | 303 | 38 |  |  |  |  |  |  | ✓ |  |
| 3 | `直波导/AB/AB_feed.ipynb` | P0 | 512.7 | 307 | 35 |  |  |  |  |  |  | ✓ |  |
| 4 | `直波导/BA/优化后的/BA_feed_epc.ipynb` | P0 | 19.6 | 389 | 37 |  |  |  |  | ✓ | ✓ | ✓ |  |
| 5 | `直波导/短探针/short.ipynb` | P0 | 8.0 | 151 | 20 | ✓ |  |  |  |  |  |  |  |
| 6 | `MPMBA/Ant3_AB_epc_mf.ipynb` | P1 | 2228.5 | 499 | 55 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 7 | `MPMBA/Ant3_epc.ipynb` | P1 | 3302.3 | 625 | 46 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 8 | `MPMBA/Ant3_epc2.ipynb` | P1 | 2830.2 | 504 | 47 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 9 | `MPMBA/Ant3_epc_mf.ipynb` | P1 | 3570.0 | 585 | 54 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 10 | `单元天线GRIB/AB型/120°透镜/Ant1_grid_120D_circle_st.ipynb` | P1 | 2878.7 | 364 | 38 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 11 | `单元天线GRIB/AB型/120°透镜/Ant1_grid_120D_circle_turn.ipynb` | P1 | 2867.2 | 355 | 37 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 12 | `单元天线GRIB/AB型/120°透镜/Ant1_grid_120D_circle_turn_DF.ipynb` | P1 | 2882.8 | 342 | 37 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 13 | `单元天线GRIB/AB型/120°透镜/Ant1_grid_240D_circle.ipynb` | P1 | 2916.7 | 352 | 35 |  |  |  |  | ✓ |  | ✓ |  |
| 14 | `单元天线GRIB/AB型/180°透镜/Ant1_grid_circle.ipynb` | P1 | 3056.6 | 244 | 33 |  |  |  |  |  | ✓ |  |  |
| 15 | `单元天线GRIB/AB型/180°透镜/Ant1_grid_circle_DF.ipynb` | P1 | 3056.3 | 250 | 33 |  |  |  |  |  | ✓ |  |  |
| 16 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_120D.ipynb` | P1 | 2868.2 | 351 | 35 |  |  |  |  | ✓ |  | ✓ |  |
| 17 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_120D_DF.ipynb` | P1 | 2871.0 | 339 | 35 |  |  |  |  | ✓ |  | ✓ |  |
| 18 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_120D_circle.ipynb` | P1 | 1687.3 | 356 | 37 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 19 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_120D_circle_DF-140.ipynb` | P1 | 2534.0 | 343 | 37 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 20 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_120D_circle_DF-EX.ipynb` | P1 | 2869.0 | 352 | 39 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 21 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_120D_circle_DF.ipynb` | P1 | 2864.5 | 340 | 37 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 22 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_120D_circle_square.ipynb` | P1 | 2866.9 | 404 | 42 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 23 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_120D_circle_turn.ipynb` | P1 | 2872.2 | 356 | 37 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 24 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_240D_circle-hex.ipynb` | P1 | 3056.8 | 252 | 33 |  |  |  |  |  | ✓ |  |  |
| 25 | `单元天线GRIB/BA型/120°透镜/Ant1_grid_BA_240D_circle.ipynb` | P1 | 3056.2 | 244 | 33 |  |  |  |  |  | ✓ |  |  |
| 26 | `单元天线GRIB/BA型/180°透镜/Ant1_grid_BA.ipynb` | P1 | 2940.6 | 322 | 37 |  |  |  |  | ✓ | ✓ |  |  |
| 27 | `单元天线GRIB/BA型/180°透镜/Ant1_grid_BA_DF.ipynb` | P1 | 2940.8 | 322 | 37 |  |  |  |  | ✓ | ✓ |  |  |
| 28 | `单元天线GRIB/BA型/180°透镜/Ant1_grid_BA_circle.ipynb` | P1 | 2939.2 | 382 | 39 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 29 | `单元天线GRIB/BA型/180°透镜/Ant1_grid_BA_circle_DF.ipynb` | P1 | 2937.3 | 426 | 39 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 30 | `多端口/Ant3_1W2N/Ant3_240D3_epc.ipynb` | P1 | 2108.2 | 522 | 45 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 31 | `多端口/Ant3_1W2N/Ant3_BA_240D_epc.ipynb` | P1 | 1931.3 | 519 | 47 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 32 | `多端口/Ant6_undiretional/ANT6_C6_hexring.ipynb` | P1 | 433.3 | 1003 | 0 |  |  |  |  |  | ✓ | ✓ |  |
| 33 | `多端口/Ant6_undiretional/ANT6_undirectional.ipynb` | P1 | 364.3 | 418 | 22 |  |  | ✓ |  |  | ✓ | ✓ |  |
| 34 | `多端口/Ant6_undiretional/ANT6_undirectional_test.ipynb` | P1 | 363.8 | 418 | 22 |  |  | ✓ |  |  | ✓ | ✓ |  |
| 35 | `椭圆透镜单元天线/AB/Ant1_grid_120D_epc-0d.ipynb` | P1 | 1335.6 | 453 | 41 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 36 | `椭圆透镜单元天线/AB/Ant1_grid_120D_epc-0d_DR.ipynb` | P1 | 1922.9 | 454 | 41 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 37 | `椭圆透镜单元天线/AB/Ant1_grid_120D_epc0.ipynb` | P1 | 2530.0 | 456 | 41 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 38 | `椭圆透镜单元天线/AB/Ant1_grid_120D_epc_turn.ipynb` | P1 | 2734.8 | 385 | 41 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 39 | `椭圆透镜单元天线/AB/Ant1_grid_240D_epc.ipynb` | P1 | 2923.5 | 385 | 41 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 40 | `椭圆透镜单元天线/AB/Ant1_grid_240D_epc_epc.ipynb` | P1 | 3053.9 | 351 | 38 | ✓ |  |  |  | ✓ | ✓ |  |  |
| 41 | `椭圆透镜单元天线/AB/Ant1_grid_240D_epc_epc_fpr.ipynb` | P1 | 2717.1 | 460 | 41 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 42 | `椭圆透镜单元天线/BA/D120/Ant1_grid_BA_120D_circle_epc.ipynb` | P1 | 2743.9 | 384 | 41 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 43 | `椭圆透镜单元天线/BA/D120/Ant1_grid_BA_120D_epc_epc.ipynb` | P1 | 1737.1 | 466 | 41 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 44 | `椭圆透镜单元天线/BA/D120/Ant1_grid_BA_120D_epc_rotation.ipynb` | P1 | 2732.3 | 386 | 42 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 45 | `椭圆透镜单元天线/BA/D120/Ant1_grid_BA_240D_circle_epc.ipynb` | P1 | 2923.0 | 388 | 41 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 46 | `椭圆透镜单元天线/BA/D120/Ant1_grid_BA_240D_epc_1c.ipynb` | P1 | 2663.9 | 462 | 41 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 47 | `椭圆透镜单元天线/BA/D120/Ant1_grid_BA_240D_epc_epc.ipynb` | P1 | 3054.2 | 352 | 38 | ✓ |  |  |  | ✓ | ✓ |  |  |
| 48 | `椭圆透镜单元天线/BA/D120/ep_cal.ipynb` | P1 | 388.6 | 526 | 0 |  |  |  |  |  |  |  |  |
| 49 | `椭圆透镜单元天线/BA/leaky/Ant1_grid_BA_120D_circle_epc.ipynb` | P1 | 2729.5 | 402 | 42 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 50 | `椭圆透镜单元天线/BA/leaky/crossover_1.ipynb` | P1 | 2217.8 | 434 | 41 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 51 | `椭圆透镜单元天线/BA/rotation/Ant1_grid_BA_120D_epc_ex.ipynb` | P1 | 17368.5 | 726 | 42 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 52 | `椭圆透镜单元天线/BA/rotation/Ant1_grid_BA_120D_epc_rotation.ipynb` | P1 | 2728.6 | 372 | 42 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 53 | `椭圆透镜单元天线/透镜优化/Ant1_grid_BA_120D_circle_epc.ipynb` | P1 | 2733.2 | 384 | 41 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 54 | `椭圆透镜单元天线/透镜优化/sweep.ipynb` | P1 | 12018.6 | 236 | 5 | ✓ |  |  |  | ✓ | ✓ |  |  |
| 55 | `Leaky/ANT_LEAKY_EPC_GRID.ipynb` | P2 | 1270.9 | 463 | 47 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 56 | `Leaky/ANT_LEAKY_MK_GRID.ipynb` | P2 | 648.3 | 471 | 44 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 57 | `Leaky/ANT_LEAKY_MK_GRID_opt.ipynb` | P2 | 662.6 | 733 | 44 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 58 | `Leaky/ANT_LEAKY_MK_GRID_z.ipynb` | P2 | 649.0 | 479 | 44 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 59 | `Leaky/analysis_GRIN_approximation.ipynb` | P2 | 289.7 | 169 | 0 |  |  |  |  |  |  |  |  |
| 60 | `功分器加天线/1分4/Ant4_1d2d4_2f2s_2G2F_circle_DF.ipynb` | P2 | 3031.9 | 261 | 37 |  |  |  |  |  | ✓ |  |  |
| 61 | `功分器加天线/1分4/Ant4_1d2d4_2f2s_2G2F_circle_DF_grid120.ipynb` | P2 | 3025.2 | 261 | 37 |  |  |  |  |  | ✓ |  |  |
| 62 | `功分器加天线/1分4/Ant4_1d2d4_2f2s_circle_DF.ipynb` | P2 | 3031.5 | 260 | 37 |  |  |  |  |  | ✓ |  |  |
| 63 | `功分器加天线/1分4/Ant4_1d2d4_2f2s_circle_DF_BA.ipynb` | P2 | 2982.0 | 260 | 37 |  |  |  |  |  | ✓ |  |  |
| 64 | `功分器加天线/B5/Ant6_2H4L_epc.ipynb` | P2 | 2479.2 | 624 | 68 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 65 | `功分器加天线/椭圆透镜1div3/Ant2_1div2_AB_120D_epc.ipynb` | P2 | 1537.5 | 496 | 45 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 66 | `功分器加天线/椭圆透镜1div3/Ant2_1div2_BA_120D_epc.ipynb` | P2 | 1932.5 | 485 | 45 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 67 | `功分器加天线/椭圆透镜1div3/Ant3_1div3_BA_120D_epc.ipynb` | P2 | 1792.2 | 430 | 45 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 68 | `功分器加天线/椭圆透镜1div3/Ant4_1div4_BA_120D_epc.ipynb` | P2 | 1841.8 | 627 | 55 | ✓ |  |  |  | ✓ | ✓ | ✓ |  |
| 69 | `开关尝试/AB/MZI-BA.ipynb` | P2 | 695.5 | 467 | 45 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 70 | `开关尝试/AB/MZI-GRIB.ipynb` | P2 | 3045.9 | 267 | 39 |  |  |  |  |  | ✓ |  |  |
| 71 | `开关尝试/AB/MZI-anti.ipynb` | P2 | 742.6 | 497 | 49 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 72 | `开关尝试/AB/MZI-cascade.ipynb` | P2 | 587.5 | 497 | 47 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 73 | `开关尝试/AB/MZI-hex.ipynb` | P2 | 589.6 | 502 | 55 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 74 | `开关尝试/AB/MZI-parallel.ipynb` | P2 | 660.9 | 508 | 55 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 75 | `开关尝试/AB/MZI.ipynb` | P2 | 694.2 | 482 | 47 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 76 | `开关尝试/AB/cal_mzi.ipynb` | P2 | 22.1 | 251 | 0 |  |  |  |  |  |  |  |  |
| 77 | `开关尝试/AB/mzi_opt_cal.ipynb` | P2 | 611.1 | 128 | 0 |  |  |  |  |  |  |  |  |
| 78 | `开关尝试/AB/mzi_opt_cal_feed.ipynb` | P2 | 1552.1 | 597 | 0 |  |  |  |  |  |  |  |  |
| 79 | `开关尝试/AB/mzi_opt_cal_feed_all.ipynb` | P2 | 1213.0 | 204 | 0 |  |  |  |  |  |  |  |  |
| 80 | `开关尝试/AB/test.ipynb` | P2 | 149.4 | 91 | 0 |  |  |  |  |  |  |  |  |
| 81 | `开关尝试/BA/MZI-BA-wo.ipynb` | P2 | 695.5 | 467 | 45 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 82 | `开关尝试/BA/MZI-BA.ipynb` | P2 | 697.1 | 484 | 47 | ✓ |  |  |  | ✓ |  | ✓ |  |
| 83 | `针对隔离和开关的分析研究/AB-MXene.ipynb` | P3 | 511.2 | 384 | 39 |  |  |  |  |  |  | ✓ |  |
| 84 | `针对隔离和开关的分析研究/AB-light-wo.ipynb` | P3 | 511.1 | 380 | 37 |  |  |  |  |  |  | ✓ |  |
| 85 | `针对隔离和开关的分析研究/AB-light.ipynb` | P3 | 511.6 | 395 | 39 |  |  |  |  |  |  | ✓ |  |
| 86 | `针对隔离和开关的分析研究/BA-MXene.ipynb` | P3 | 520.2 | 385 | 39 |  |  |  |  |  |  | ✓ |  |
| 87 | `针对隔离和开关的分析研究/BA-light.ipynb` | P3 | 520.2 | 383 | 39 |  |  |  |  |  |  | ✓ |  |

## 4. 特征交叉（用于判断「4/6 端口到底有没有数据依据」）

| 问题 | 命中的 notebook |
|---|---|
| 参数表像**GRIN 透镜**（含 ec_a/ec_b/ec_c/Nx/Ny/d0/r1/r2/ratio/a2 之一） | **54** 个：`Leaky/ANT_LEAKY_EPC_GRID.ipynb`, `Leaky/ANT_LEAKY_MK_GRID.ipynb`, `Leaky/ANT_LEAKY_MK_GRID_opt.ipynb`, `Leaky/ANT_LEAKY_MK_GRID_z.ipynb`, `MPMBA/Ant3_AB_epc_mf.ipynb`, `MPMBA/Ant3_epc.ipynb`… |
| 参数表像**MZI / 干涉臂**（含 MZI/arm/L1/L2/phase/nsm/Rbig 之一） | **0** 个 |
| 参数表像**功分器**（含 1div*/div2-4/lx1/lx2 之一） | **2** 个：`多端口/Ant6_undiretional/ANT6_undirectional.ipynb`, `多端口/Ant6_undiretional/ANT6_undirectional_test.ipynb` |
| 代码里出现 `MZI` 字样（辅助证据，可能只是注释） | **30** 个：`MPMBA/Ant3_epc.ipynb`, `MPMBA/Ant3_epc_mf.ipynb`, `功分器加天线/1分4/Ant4_1d2d4_2f2s_2G2F_circle_DF.ipynb`, `功分器加天线/1分4/Ant4_1d2d4_2f2s_2G2F_circle_DF_grid120.ipynb`, `功分器加天线/1分4/Ant4_1d2d4_2f2s_circle_DF.ipynb`, `功分器加天线/1分4/Ant4_1d2d4_2f2s_circle_DF_BA.ipynb`… |
| 代码里出现「功分 / 分路」字样（辅助证据） | **75** 个：`Leaky/ANT_LEAKY_EPC_GRID.ipynb`, `Leaky/ANT_LEAKY_MK_GRID.ipynb`, `Leaky/ANT_LEAKY_MK_GRID_opt.ipynb`, `Leaky/ANT_LEAKY_MK_GRID_z.ipynb`, `MPMBA/Ant3_AB_epc_mf.ipynb`, `MPMBA/Ant3_epc.ipynb`… |
| 含 DXF 导入（透镜的 DXF 路线） | **51** 个：`Leaky/ANT_LEAKY_EPC_GRID.ipynb`, `Leaky/ANT_LEAKY_MK_GRID.ipynb`, `Leaky/ANT_LEAKY_MK_GRID_opt.ipynb`, `Leaky/ANT_LEAKY_MK_GRID_z.ipynb`, `MPMBA/Ant3_AB_epc_mf.ipynb`, `MPMBA/Ant3_epc.ipynb`… |
| 含遗传算法特征 | **0** 个 |

### 4.1 多端口的结构到底存不存在（红绿灯项）

计划把「4 / 6 端口目前无数据依据」标成红灯，要求先确认这两种结构在旧代码里是否存在。下面是**按文件名**能直接看到的证据（不依赖任何启发式）：

| 端口数 | 证据（文件名） |
|---|---|
| **2 端口** | 2 个：`功分器加天线/椭圆透镜1div3/Ant2_1div2_AB_120D_epc.ipynb`, `功分器加天线/椭圆透镜1div3/Ant2_1div2_BA_120D_epc.ipynb` |
| **3 端口** | 7 个：`MPMBA/Ant3_AB_epc_mf.ipynb`, `MPMBA/Ant3_epc.ipynb`, `MPMBA/Ant3_epc2.ipynb`, `MPMBA/Ant3_epc_mf.ipynb`, `功分器加天线/椭圆透镜1div3/Ant3_1div3_BA_120D_epc.ipynb`, `多端口/Ant3_1W2N/Ant3_240D3_epc.ipynb`, `多端口/Ant3_1W2N/Ant3_BA_240D_epc.ipynb` |
| **4 端口** | 5 个：`功分器加天线/1分4/Ant4_1d2d4_2f2s_2G2F_circle_DF.ipynb`, `功分器加天线/1分4/Ant4_1d2d4_2f2s_2G2F_circle_DF_grid120.ipynb`, `功分器加天线/1分4/Ant4_1d2d4_2f2s_circle_DF.ipynb`, `功分器加天线/1分4/Ant4_1d2d4_2f2s_circle_DF_BA.ipynb`, `功分器加天线/椭圆透镜1div3/Ant4_1div4_BA_120D_epc.ipynb` |
| **6 端口** | 4 个：`功分器加天线/B5/Ant6_2H4L_epc.ipynb`, `多端口/Ant6_undiretional/ANT6_C6_hexring.ipynb`, `多端口/Ant6_undiretional/ANT6_undirectional.ipynb`, `多端口/Ant6_undiretional/ANT6_undirectional_test.ipynb` |

### 4.2 各分类里出现最多的参数名（用于补规格缺口）

| 分类 | 出现最多的 CST 参数名（前 20） |
|---|---|
| `Leaky` | `h`, `a`, `e1`, `e2`, `l2`, `l1`, `lf1`, `lf2`, `lf3`, `lf4`, `lf5`, `lf6`, `wf1`, `wf2`, `wg_a`, `wg_b`, `wg_t`, `x0`, `x01`, `px1` |
| `MPMBA` | `h`, `a`, `e1`, `e2`, `l1`, `l2`, `lf1`, `lf2`, `lf3`, `lf4`, `lf5`, `lf6`, `wf1`, `wf2`, `wg_a`, `wg_b`, `wg_t`, `x0`, `x01`, `px1` |
| `功分器加天线` | `h`, `a`, `e1`, `e2`, `l1`, `l2`, `lf1`, `lf2`, `lf3`, `lf4`, `lf5`, `lf6`, `wf1`, `wf2`, `wg_a`, `wg_b`, `wg_t`, `x0`, `x01`, `px1` |
| `单元天线GRIB` | `h`, `a`, `e1`, `e2`, `l2`, `l1`, `lf1`, `lf2`, `lf3`, `lf4`, `lf5`, `lf6`, `wf1`, `wf2`, `wg_a`, `wg_b`, `wg_t`, `x0`, `x01`, `px1` |
| `多端口` | `h`, `a`, `e1`, `e2`, `l1`, `l2`, `lf4`, `lf5`, `lf6`, `wf2`, `wg_a`, `wg_b`, `wg_t`, `x01`, `xup`, `yup`, `ydn`, `fmin`, `fmax`, `lf1` |
| `开关尝试` | `h`, `a`, `e1`, `e2`, `l2`, `l1`, `lf1`, `lf2`, `lf3`, `lf4`, `lf5`, `lf6`, `wf1`, `wf2`, `wg_a`, `wg_b`, `wg_t`, `x0`, `x01`, `px1` |
| `普通单元天线` | `h`, `a`, `e1`, `e2`, `l1`, `l2`, `lf1`, `lf2`, `lf3`, `lf4`, `lf5`, `lf6`, `wf1`, `wf2`, `wg_a`, `wg_b`, `wg_t`, `x0`, `x01`, `px1` |
| `椭圆透镜单元天线` | `HEX_SIZE`, `a2`, `d0`, `Nx`, `Ny`, `h`, `a`, `e1`, `e2`, `l2`, `l1`, `lf1`, `lf2`, `lf3`, `lf4`, `lf5`, `lf6`, `wf1`, `wf2`, `wg_a` |
| `直波导` | `h`, `a`, `e1`, `e2`, `l1`, `l2`, `lf1`, `lf2`, `lf3`, `lf4`, `wf1`, `wf2`, `wg_a`, `wg_b`, `wg_t`, `x0`, `x01`, `fmin`, `fmax`, `lf5` |
| `针对隔离和开关的分析研究` | `h`, `a`, `e1`, `e2`, `l1`, `l2`, `lf1`, `lf2`, `lf3`, `lf4`, `lf5`, `lf6`, `wf1`, `wf2`, `wg_a`, `wg_b`, `wg_t`, `x0`, `x01`, `px1` |
