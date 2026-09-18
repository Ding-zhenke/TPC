# 旧 notebook 迁移登记：P0 批次（5 个）

> 本表由 `python scripts/verify_notebook_p0_migration.py --write` 生成（只解析 `.ipynb` 的 JSON，**不执行** notebook、不改任何源文件）。
> 判据与口径见脚本 docstring；清点表见 [notebook_migration_inventory.md](./notebook_migration_inventory.md)。

## 1. 结论表

| # | notebook | 拓扑 | 新库模板 | 路径格点（新库实测） | 阵列范围 | 状态 | 差异/说明 |
|---|---|---|---|---|---|---|---|
| 1 | `普通单元天线/Ant1_D_AB_120D_cylinder_DF.ipynb` | AB | `unit_antenna` | [(0, -1), (0, 18), (14, 18)] | [25, 14, 14] | ✅ 几何一致（可迁移） | 模板未暴露、旧 notebook 里也**只定义不使用**（不算缺口）：lf4, lf5, lf6, wf2 |
| 2 | `普通单元天线/Ant1_D_BA_120D_circle_DF.ipynb` | BA | `unit_antenna` | [(0, -1), (0, 18), (-14, 32)] | [26, 14, 14] | ✅ 几何一致（可迁移） | 旧 notebook 的预览只画了直段（`path1 = vstack((p1,p2))`），臂段是由 `mirror`/`area2` 生成的；新库按**参考工程**建完整三点路径（臂端 `(6.0625,∓2.9402)` 已与参考工程逐位核对，见 P4 §4.5）；模板未暴露、旧 notebook 里也**只定义不使用**（不算缺口）：lf1, lf2, lf3, lf6, wf1, x0 |
| 3 | `直波导/AB/AB_feed.ipynb` | AB | `straight_waveguide` | [(0, 0), (0, 18)] | [25, 14, 14] | ✅ 几何一致（可迁移） | 旧 `start(0,-1)`（19 格）vs 新 `start(0,0)`（18 格）——新库按参考工程 `AB_feed.cst` 的 `xup=25` 修正过，见 docs/packages/topo_templates.md §3.2；模板未暴露、旧 notebook 里也**只定义不使用**（不算缺口）：lf4, lf5, lf6, wf2 |
| 4 | `直波导/BA/优化后的/BA_feed_epc.ipynb` | BA | `straight_waveguide` | [(0, 0), (0, 18)] | [25, 14, 14] | ✅ 几何一致（可迁移） | 旧 `start(0,-1)`（19 格）vs 新 `start(0,0)`（18 格）——新库按参考工程 `AB_feed.cst` 的 `xup=25` 修正过，见 docs/packages/topo_templates.md §3.2；模板未暴露、旧 notebook 里也**只定义不使用**（不算缺口）：lf1, lf2, lf3, wf1, x0 |
| 5 | `直波导/短探针/short.ipynb` | AB | `straight_waveguide` | [(0, 0), (0, 29)] | [34, 10, 10] | ⚠️ 需补能力 | 旧 `start(0,-1)`（19 格）vs 新 `start(0,0)`（18 格）——新库按参考工程 `AB_feed.cst` 的 `xup=25` 修正过，见 docs/packages/topo_templates.md §3.2；模板未暴露、但旧 notebook 的几何**确实引用**（需补能力）：lf1, lf2, lf3, lf4, wf1, wf2；模板未暴露、旧 notebook 里也**只定义不使用**（不算缺口）：x0 |

## 2. 验收口径

* **几何验收（本表）**：路径格点、阵列范围、基础参数、馈源参数逐值比对 —— 全部离线，不需要 CST；
* **仿真验收**：本批次**未做**（需要真实求解；单次时域求解约 5300 s CPU），属计划 P4/V2、V7、V9，等用户确认算例与开销；
* 迁移方式：P0 批次的功能已被 `StraightWaveguide` / `UnitAntenna` 覆盖，因此不重写 notebook，而是**登记「旧 notebook → 新库模板」的映射与差异**。

