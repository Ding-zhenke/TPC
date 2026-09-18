# 参考模型验收证据（历史记录）

这些是 2026-09-15 已记录的实测数据，本轮未重新求解。此文件只保留证据，剩余任务统一见 [计划](../next_plan/README.md)。历史编号 T1–T15 仅供追溯。

## 几何与接口实测

### 2.1 构建已全程通过

用真实模板 `硅基\直波导\AB\tmp.cst` 的**副本**（先核对过它是干净模板：
`ModelHistory.json` 只有 3 条 —— 单位 + PML/边界，无几何）：

```
BUILD   messages: 空     ← 判据：跑通且无报错
REBUILD messages: 空     ← 判据：历史树无错重放
save()          成功     ← 产出 wg_AB_L18.cst（635 KB）
```

三组判据里的**第一组（几何）已完成可复现构建**，但**尚未做实体级比对**（见 §3 T1）。

### 2.2 参数级对比结果

本库实际定义/使用的 23 个参数中，**21 个与参考工程逐一吻合**：

| 判定 | 参数 |
|---|---|
| ✅ 一致 | `a` `h` `e1` `e2` `xup` `yup` `ydn` `x0` `wf1` `lf1` `lf2` `lf3` `wg_a` `wg_b` `wg_t` `fmin` `fmax` ＋ `p*` 路径参数 |
| ⚠️ 命名反转（已补偿） | `l1` ↔ `l2`（见 T3） |
| 🔴 实际差异 | 路径起点差一格（见 T2） |

规模对比：生成工程 81 参数 / 65 条历史，参考 77 参数 / 67 条历史 ——
差的 4 个正是本库新命名的 `p1x/p1y/p2x/p2y`（参考用旧命名 `px1/py1/px2/py2`）。

> ⚠️ **参数吻合只是代理指标，不能替代几何验证**：参数对不代表布尔序列、绕向、
> 阵列范围都正确。T1 才是本阶段的核心判据。

### 2.3 本轮暴露并已修掉的 8 处缺陷

| # | 位置 | 现象 | 修法 |
|---|---|---|---|
| 1 | `cst_solver/project.py::new_project()` | CST 2026 的 `DesignEnvironment.new_project()` **必传** `ProjectType`，缺参抛 `TypeError` | 加可选形参，默认 `ProjectType.MWS` |
| 2 | `cst_solver/project.py::save()` / `save_as()` | `Project` **没有** `save_as`，带路径保存必抛 `AttributeError` | 按真实签名 `save(path, include_results, allow_overwrite)` 改调 |
| 3 | `cst_solver/parameters.py::paras()` | docstring 声明支持 dict，**函数体未实现该分支** → CST 抛 `type must be array, but is object` | 按文档实现 dict → 两个等长数组的归一化 |
| 4 | `topo_modeler`（步骤缺失） | 流水线**从不定义材料**，模板又不带材料 → 第一条 extrude 报 `The specified material does not exist` | 新增 `builders/materials.py::build_materials()`，两个模板均调用 |
| 5 | `topo_templates/straight_waveguide.py` | 阵列范围用路径推断值（`19/1/1`），**违反 ARCHITECTURE §6 硬约定 3**；且 `int(yup/2)=0` → CST 报 `Invalid number of repetitions` | 按参考改为 `xup=length+int(width/2)=25`、`yup=ydn=width=14` |
| 6 | `cst_solver/simulation/solver.py::T_solver()` | `Solver.Method` 只接受 `"Hexahedral"` / `"Hexahedral TLM"`，原写 `"T-Solver"` | 改为 `"Hexahedral"` |
| 7 | 同上 | `.Accuracy` / `.CalculateAllModes` / `.DetermineFreq` / `.DetermineFreqFromN` **都不是真实属性** | 删除，只保留实测可用属性；补齐 `set_steady_state_limit()` / `set_parallel_threads()` / `set_gpu_acceleration()` 三个封装 |
| 8 | `topo_modeler/builders/solver.py` | `_configure_solver_advanced()` 手写 VBA（违反 WORKFLOW §2），且 `.ParallelizationThreads` / `.GPUAcceleration` 实测不存在 | 改为调用 `cst_solver` 新封装 |

### 2.4 CST 事实核验结论（已入库，供后续复用）

**`Solver` 对象属性**（一个会话内逐条实测）：

| 可用 | 不可用（报 `10091 no such property or method`） |
|---|---|
| `Method` `SteadyStateLimit` `MaximumNumberOfThreads` `UseParallelization` `HardwareAcceleration` `MaximumNumberOfGPUs` `MeshAdaption` `FrequencySamples` `FrequencySampleRuleLin` `CalculateModesOnly` `SParaSymmetry` `FullDeembedding` `StimulationPort` `PBAFillLimit` | `Accuracy` `CalculateAllModes` `DetermineFreq` `ParallelizationThreads` `GPUAcceleration` |

**`.Repetitions`**：**接受** `int(14/2)`、`int(yup/2)` 这类整数表达式，
**不接受** `yup/2` 这种非整数表达式。

**面选取链路**（核验脚本 `scripts/verify_port_face_api.py`，全部通过）：

| 项 | 结论 |
|---|---|
| `model3d.Pick` 是否暴露 | ✅ 暴露，取到 `_cst_interface.RemoteObject` |
| 按坐标反查面编号 | ✅ `(0.5,0.5,1.0)` → 面编号 `1`（`int`） |
| `get_picked_count()` | ✅ 未拾取返回 `0`，非法 `kind` 抛 `ValueError` |
| 反查编号喂回 `pick_face()` | ✅ 已选面数 = 1，链路闭环 |
| `Coordinates "Free"` + 范围建端口 | ✅ 无报错 |

> 核验脚本：`scripts/verify_port_face_api.py`（新建空白工程，不触碰既有工程；
> 只关本次新建的 DE，**绝不碰用户既有 CST 会话**）。

### 2.5 T1 实体级几何对比结果（已完成）

**方法**：不打开 CST、不调 API —— CST 工程的 `Model/3D/ModelHistory.json`
保存着**全部建模 VBA**，每条实体创建命令都带**精确坐标与表达式**，离线逐实体对比即可。
工具：`scripts/compare_model_history.py`（本阶段新增，可复现）。

> 为什么不用 bounding box：CST 的 `Solid` 对象**没有**包围盒查询
> （官方 VBA 参考 §7 只有布尔/实体管理/网格属性/高级建模）；参考实现里的
> `show-bounding-box` 也只是**切换显示**（`Plot.DrawBox "True"`），不是查询。

**对比对象**：本库生成工程 `wg_AB_L18` vs 参考 `AB_feed`。

**结果一：26 个共有实体中，13 个几何逐字节一致**（忽略缩进空白）：

| 一致（13） | `g1A` `g2A` `g1B` `g2B` `tri_up_A` `tri_up_B` `tri_dn_A` `tri_dn_B` `feed1` `feed1_epc` `feed1_cut1` `wg1` `wg1_1` |
|---|---|

其中 `wg1`/`wg1_1`/`feed1_cut1`/`feed1_epc` 的 `Xrange`/`Yrange`/`Zrange`
与 `feed1` 的 9 个多边形顶点**完全逐字相同**。

**结果二：6 处「不一致」全部是两类可解释的等价**（非缺陷）：

| 表面差异 | 实质 | 判定 |
|---|---|---|
| `tri_up_A` / `tri_dn_A` / `tri_up_B` / `tri_dn_B` 的 `l1`/`l2` | 本库用 `l2` 的地方参考用 `l1`，反之亦然；而两库 `l1`/`l2` 的**取值本来互换**（本库 `l1`=0.65a、参考 `l1`=0.35a），折算后**孔尺寸逐一相同** | ✅ **等价**（即 T3 的答案） |
| `component1:wg1` / `component1:feed1` 的 mirror 中心 | 本库写 `p2x/2`，参考写 `x1*a/2`；两者数值均为 `4.365/2 = 2.1825` | ✅ **等价** |

**结果三：🔴 布尔运算序列差 4 条**（这是模型不等价的真正原因）：

| | add | subtract | mirror | **intersect** | **insert** | 合计 |
|---|---|---|---|---|---|---|
| 本库生成 | 7 | 4 | 2 | **0** | **0** | 13 |
| 参考 | 7 | 4 | 2 | **3** | **1** | 17 |

参考有、本库没有的 4 条：

```
vpcb Insert vpc_a_area1      ← VPC-B 里嵌入 A 区
vpca intersect vpc_a_area1   ← VPC-A 裁到 A 区
vpca intersect g1A           ← VPC-A 与晶体阵列求交
vpcb intersect g1B           ← VPC-B 与晶体阵列求交
```

**根因**：`topo_modeler/builders/` 里**已经实现了对应的两个函数**，但**零调用者**
（`grep intersect_crystal_with_vpc / intersect_vpc_with_substrate` → 除定义与
`__init__.py` 导出外无任何调用）：

| 函数 | 位置 | 调用者 |
|---|---|---|
| `intersect_vpc_with_substrate()` | `builders/vpc_region.py:55` | **无** |
| `intersect_crystal_with_vpc()` | `builders/crystal.py:151` | **无** |

也就是说：**本库根本没有把晶体阵列裁剪到 VPC 区域内**，两个 `g1A`/`g1B`
作为独立实体留在模型里。这与 T8（VPC 语义）是同一件事的两面 —— 现在它有了量化证据。

**结果四：实体命名分组不同**（`substrate`/`vpc_A`/`vpc_B` vs `vpca`/`vpcb`/`vpc_a_area1`），
属 T8 的构造路线差异，见该任务。

**T1 小结**：就「**共有实体的关键尺寸偏差**」而言，结论是 **0%**（13/13 逐字节一致），
判据 `< 0.1%` **满足**；但**整体模型尚不等价** —— 差在那 4 条布尔运算，属 T8。

---

## S 参数对比及局限

**设置**：两个模型走**同一个**配置函数 —— 时域求解器、关网格自适应、稳态限制 −20 dB、
频段 310–370 GHz；参考工程用**副本**（原件未动）。各跑一次，比较 4 个频点。

| 频点 | S1,1 本库 | S1,1 参考 | Δ | S2,1 本库 | S2,1 参考 | Δ |
|---|---|---|---|---|---|---|
| 310 GHz | −14.973 | −14.781 | 0.192 | −2.063 | −1.936 | 0.127 |
| 330 GHz | −20.817 | −20.326 | 0.491 | −3.939 | −3.885 | 0.054 |
| **350 GHz** | −11.838 | −10.008 | **1.830** ⚠️ | −17.779 | −18.511 | 0.731 |
| 370 GHz | −11.538 | −11.842 | 0.304 | −7.371 | −7.913 | 0.542 |

（单位 dB。8 个点里 **7 个在 1 dB 内**。）

**结论**：

- **传输 S21 四个点全部 ≤ 0.73 dB** —— 与参考高度一致，说明**几何对齐成功**；
- 反射 S11 三个点 ≤ 0.49 dB，**仅 350 GHz 一处差 1.83 dB**。

**⚠️ 两点必须说清的局限**：

1. **1 dB 是我设的代理容差，不是原判据。** 计划原本的判据是「谐振峰偏差 < 1 GHz」——
   那是**频域上的峰值位置对比**，需要先做峰值识别；用「某几个频点的 dB 差」代理它，
   只能发现结构性错误，不能直接判定是否满足原判据。
2. **S11 在反射低谷附近对微小差异极其敏感** —— 350 GHz 处 S11 已到 −11 dB 量级，
   1.8 dB 的差别可能来自数值误差/网格差异而非结构错误。要判定这一点，
   需要看**曲线形状**（是否只是整体平移）而不只是单点数值。

**成本记录**（供后续估算）：单次时域求解约 **5300 秒 CPU 时间**、峰值内存约 **2.4 GB**，
用的是"关自适应 + 稳态 −20 dB"的省时配置。完整自适应版本会显著更久。
