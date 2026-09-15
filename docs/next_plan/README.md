# TPC 改善计划索引（next_plan）

> 本目录收纳项目历史上多份 AI 撰写的改善计划。**本文件是唯一的计划入口与阶段状态权威**。
> 动代码之前先读这里，确认需求属于哪个阶段。
> 最后更新：见 git log。

---

## 0. 三十秒结论

| 问题 | 答案 |
|---|---|
| **哪份计划算数？** | [`06_整合实施计划_分阶段分模块.md`](./06_整合实施计划_分阶段分模块.md)。它自述整合了 04 与 05，且仓库实际实现与它一致。 |
| **现在做到哪了？** | **阶段 0–3 的代码已全部落地**（= 06 编号）。阶段 4–6 未开始。 |
| **「第三阶段」指哪个？** | **06 的阶段 3**（基础模板层：feed / waveguide / port builders + 直波导模板 + 单元天线模板）。 |
| **还有别的阶段编号吗？** | 有，而且互相冲突 —— 见 §3「四套编号对照」。**除 06 外一律不再作为实施依据。** |
| **下一步做什么？** | 先做完阶段 3 的**几何验收**（见 §5 阻塞项），再进阶段 4。 |

---

## 1. 目录内容与角色

| 文件 | 撰写时的用途 | 现在的角色 |
|---|---|---|
| [`01_Python建模拓扑光子晶体指南.md`](./01_Python建模拓扑光子晶体指南.md) | 面向 AI 的现状教程（`sys.path.append` + 手写 16 步建模） | **历史资料**。描述的是重构前的 notebook 工作流，不含 `topo_modeler/`、`TopoPath`、`templates/`；且含若干会报错的 API 签名。仅可当「旧 notebook 参数事实」的参考。其中「旧 notebook 参数」已被阶段 3 的验收基准吸收。 |
| [`02_函数优化清单.md`](./02_函数优化清单.md) | 函数级/架构级优化清单（53 条可执行议题）+ `TopoPath` 完整实现方案 | **已被实施 19 条**。`TopoPath`（B33–B36）与 `TopoModeler`（B32）两大 P0 架构项均已落地。剩余价值集中在命名/魔法数字（B18–B27）、YAML（B38）、批量建模（B39）、结果自动绘图（B49）、参数扫描/GA 内置（B50/B51）、增量建模（B53）。 |
| [`03_AI技能知识库.md`](./03_AI技能知识库.md) | AI 干活前的强制知识库 | **已被 [`../skills/user/tpc-usage.md`](../../skills/user/tpc-usage.md) 取代**。其骨架（快速导航/API 速查/10 步流程/参数表/调试表/自检清单）与新技能文档逐节同构但内容更旧。仍有三块独有价值待迁移：notebook 文件名编码约定、物理概念与频段、症状→病因→动作调试表。 |
| [`04_详细实施计划清单.md`](./04_详细实施计划清单.md) | 112 条详细任务 + 模板参数表 + **第三套阶段编号**（阶段一~四） | **被 06 取代**。§3 的 28 条「库层任务」在 04 自己的阶段表里没有任何归属。 |
| [`05_阶段实施计划.md`](./05_阶段实施计划.md) | 按步骤拆分的执行计划 + **第二套阶段编号**（阶段 0–8） | **被 06 取代**。与 06 有 10 组「同一交付物被指派到不同阶段」的冲突（含 `05:342` 要求 `build_feed/build_waveguide/build_lens` 先 `raise NotImplementedError`，与 06 及仓库实际实现**直接互斥**）。 |
| [`06_整合实施计划_分阶段分模块.md`](./06_整合实施计划_分阶段分模块.md) | 整合 04+05，以**模块**为最小实现单元 | ⭐ **权威计划**。本轮的缺陷修正都落在它身上。 |
| [`cst_solver_TODO_LIST.md`](./cst_solver_TODO_LIST.md) | `cst_solver` 待实现功能清单（208 方法 / 23 Mixin 口径） | **有效**。记录 4 处拼写缺陷（本轮已全部修正）与「尚未覆盖的 CST VBA 对象」清单。 |

---

## 2. 各阶段状态（以 06 编号为准）

| 阶段 | 名称 | 状态 | 证据 / 备注 |
|---|---|---|---|
| **0** | 准备与规范 | ✅ 代码就绪 | `topo_modeler/`、`templates/` 包结构、`__init__.py`、风格规范均已在位 |
| **1** | 坐标统一层 | ✅ 代码就绪 | `mesh_grid/tri_grid/topo_path.py`（625 行）；`python -m pytest mesh_grid -q` → **16 passed**（本轮新增第 16 项绕向测试） |
| **2** | 基础建模引擎 | ✅ 代码就绪（本轮修了 4 个缺陷） | `name_manager.py`、`builders/{substrate,vpc_region,crystal,solver}.py`、`modeler.py` 全部在位 |
| **3** | 基础模板层 | ✅ 代码就绪（本轮修了 4 个缺陷） | `builders/{feed,waveguide,port}.py`、`templates/{straight_waveguide,unit_antenna}.py` 全部在位 |
| **4** | 复杂模板层 | ❌ 未开始 | `builders/lens.py` 不存在；`lens_build.py` / `lens_build_standalone.py` 只是脚本；`GRINLensAntenna` 模板不存在；`TopoModeler.build_lens()` 抛 `NotImplementedError` |
| **5** | 工具层 | ❌ 未开始 | `result_reader` / `config`(YAML) / `scanner` / `batch` / `optimizer` 五个模块**源码零命中**；`modeler.read_results()` / `plot_results()` 抛 `NotImplementedError`；全仓无 `import yaml` |
| **6** | 复杂结构 + 旧代码迁移 | ❌ 未开始 | 多路径支持未做；`MultiPortAntenna` / `PowerDivider` / `MZISwitch` 模板不存在；87 个旧 notebook 无一迁移 |

> ⚠️ **「代码就绪」≠「验收通过」。** 06 给阶段 2/3 定的判据是**与参考工程对比几何**（关键尺寸偏差 < 0.1%）、**S 参数谐振峰偏差 < 1 GHz**、**远场主瓣偏差 < 5°**。这三条**从未执行过** —— 见 §5。

---

## 3. 四套阶段编号对照（这是本目录最大的历史坑）

同一件事在四份文档里有四种阶段编号，**互相不可映射**：

| 06（权威） | 05 | 04 | 仓库实际采用 |
|---|---|---|---|
| 阶段 0 准备与规范 | 阶段 0 | （无阶段 0） | 06 |
| 阶段 1 坐标统一层 | 阶段 1 | 阶段一（部分） | 06 |
| 阶段 2 基础建模引擎 | **阶段 3** | 阶段二 | 06 |
| 阶段 3 基础模板层 | **阶段 4** | 阶段三（部分） | 06 |
| 阶段 4 复杂模板层 | **阶段 5** | 阶段三（部分） | 06 |
| 阶段 5 工具层 | **阶段 6–7** | 阶段三（部分） | 06 |
| 阶段 6 复杂结构 + 迁移 | **阶段 8** | 阶段四 | 06 |

**典型事故**：按 04 的编号，`阶段三 = 多端口/功分器/MZI/YAML` —— 这些**一项都不存在**；按 05 的编号，所谓「阶段 3」指的是 `modeler.py`（06 的阶段 2）。因此**「做到第几阶段」这句话，不指明文档就没有意义**。

**处理方式**：06 是唯一实施依据。05 与 04 已在文首加了「已被 06 取代」的告示；它们的阶段编号仅作历史参考，不再用于排期。

---

## 4. 本轮对计划本身做的修正（只改文档，不改实现）

针对 06 的硬伤逐条修正：

| # | 原问题 | 修正 |
|---|---|---|
| 1 | `06:94` 称总工时 17.5 天，但其阶段表各项之和为 **13.5 天**（17.5 是从 05 抄来未重算） | 改为 13.5 天 |
| 2 | `06:94` 称 25 个模块，实为 **27 个** | 改为 27 |
| 3 | `06:38` 称建模引擎层 12 个模块，实为 **16 个** | 改为 16 |
| 4 | `06:88` 称阶段 2 有 7 模块 / 5 builders，实为 **6 模块 / 4 builders** | 已改 |
| 5 | `06:89` 称阶段 3 有 4 模块，实为 **5 模块** | 已改 |
| 6 | `06:92` 称阶段 6 有 4 模块，实为 **6 模块** | 已改 |
| 7 | `06:111` 阶段 0 验证标准写 `from topo_modeler import TopoModeler` 不报错 —— 但该类属于阶段 2，必然 `ImportError`，判据自相矛盾 | 改为只验证包级 `import` |
| 8 | `06:118` 目录树把 `topo_path.py` 放在 `topo_modeler/`，实际在 `mesh_grid/tri_grid/` | 已改 |
| 9 | `06:135` 把透镜 builder 写成 `builders/lens.py`，实际是 `topo_modeler/lens_build.py` + `lens_build_standalone.py` | 已改 |
| 10 | `06:152` 自引用「本文档第〇节」—— 06 里没有第〇节 | 改为指向模块 0.2 的风格规范 |
| 11 | `06:178` 引 `E:\代码仓库\topo_path.py`（16.6 KB），与落地的 `mesh_grid/tri_grid/topo_path.py`（24,479 B / 625 行）**哈希不同** | 已改为指向仓库内真实文件 |
| 12 | `06:197` 称测试 10 项，实际 `test_topo_path.py` 有 **16 项**且位于 `mesh_grid/tri_grid/tests/` | 已改 |
| 13 | `06:278` 超元胞逻辑写成 `triangle×4 → add×2 → substract → rotation(120°,×2) → translate×3 → intersect×2`，与实际实现（`triangle×8 → add×4 → subtract×2 → rotation×2 → translate×6`）及阶段指南都不一致 | 已按实现改正 |
| 14 | `06:290` 求解器输入含 `calculation_type='TD-S'`，而 `configure_time_solver()` **不接受任何参数** | 已改为「分派到对应求解器方法」 |
| 15 | `06:361` PortBuilder 输入写 `side='end'` / `shield=None`，实际 API 是 `face_id` | 已按真实签名改正 |
| 16 | `06:510` 依赖写「所有模板（3.4, 3.5, 4.2, 6.1-6.3）」，6.1 是多路径支持、不是模板 | 改为 6.2-6.4 |
| 17 | `06:579` 说 GA 优化器「可推迟到阶段 6 之后」，而阶段 6 是最后一个阶段 | 改为「推迟到阶段 6 完成后单独排期」 |
| 18 | `06:646/676` 称 84 个旧 notebook，但迁移优先级表合计只有 **71**（差 13） | 补齐合计行 |
| 19 | `06:434/459` 称透镜覆盖约 40 个 notebook，而 `06:448/451` 又写 hexagon 33 + dxf 35 = 68 | 统一为 68 |
| 20 | `06:706` 称「236 个方法不动」，AST 实测 = **221 个公开方法**（23 Mixin 共 211 + `Result` 9 + `setup.open` 1） | 已改 |
| 21 | `06:709` 说旧入口 `tri_lib.py / hexlib.py / cst_solver.py`「保留」，它们已归档到 `archive/compat/*_shim.py` | 已改 |
| 22 | `06:753` 提到 `get_face_id_by_normal()`，但 06 的阶段表里**没有安排任何阶段实现它**（只在 04 出现过） | 已登记到阶段 4 的前置项 |
| 23 | `06:766` 明文要求「新代码也用 `substract`，不要纠正为 `subtract`」——与本仓库「拼写必须修正但保留别名」的规则冲突 | 已改：正确名 `subtract()`，旧名保留为弃用别名 |
| 24 | `06:799-806` 相关文档索引全部指向不存在的 `E:\代码仓库\` 与 `TPC\SKILL.md` | 全部改指仓库内真实路径 |
| 25 | `06:789/777` 审查清单里的「17.5 天」「25 个模块」 | 已改 |

同时给 05、04 加了「已被 06 取代」的告示与编号对照，避免继续误用。

---

## 5. 本轮对代码做的修正（阶段 ≤ 3 的问题）

原则上按用户要求：**属于已完成阶段（0–3）的问题直接改代码；属于未开始阶段（4+）的只改计划。**

| # | 位置 | 问题 | 处理 |
|---|---|---|---|
| 1 | `topo_modeler/builders/crystal.py` | **AB / BA 的大孔小孔分配装反了**。参考工程 `AB_feed/Model/3D/ModelHistory.json` 的历史树明确记录 `tri_up_A → l1`、`tri_dn_A → l2`、`tri_up_B → l2`、`tri_dn_B → l1`，而旧 notebook 里 AB 的 `l1 = 0.35a`（小孔）；本库把 `l1` 固定为「大孔」，却沿用了旧的列表顺序，导致 AB 与 BA **两张相图都反了** | ✅ 已修：交换 AB / BA 两个分支的 `hole_sizes`，并在模块 docstring 里写下对照表与核对方法 |
| 2 | `mesh_grid/tri_grid/topo_path.py` | `build_substrate_polygon()` 与 `build_vpc_area_polygon(side='lower')` 生成的多边形是**顺时针**；而调用方统一用「+ 内部 `translate -h/2`」，于是基板 / VPC-B 与晶体在 z 上**差一个 `h`**，布尔求交得空集且 CST 不报错 | ✅ 已修：两条边界链改为「每个路径点都参与」的确定绕向写法，`upper`/`lower`/基板**全部保证 CCW**；新增第 16 项单测用有向面积钉住 |
| 3 | `topo_modeler/builders/crystal.py` | 阵列范围只能由 `path.get_array_range()` 推断，宽基板覆盖不全 | ✅ 已修：新增可选形参 `xup=None, yup=None, ydn=None` |
| 4 | `templates/*.py` | `build_all()` 给 `build_vpc_regions` 传 `topology=`、给 `build_topological_crystal` 传 `xup/yup/ydn=` —— 都不被接受 → `TypeError` | ✅ 已修 |
| 5 | `templates/*.py` | `run()` 调 `self.app.start_solver()`，该方法**全库不存在** → `AttributeError` | ✅ 已修：改用 `self.app.run()` |
| 6 | `topo_modeler/modeler.py` | `set_parameters()` 调 `app.set_parameters(params)`，而真实签名是 `set_parameters(name, value, log_flag=0)` → **模板构造时就 `TypeError`**（比第 4 条更早触发） | ✅ 已修：改用字典式批量接口 `app.paras(params, None)` |
| 7 | `templates/*.py` | 布尔加引用 `'vpca'` / `'vpcb'`，而 `build_vpc_regions` 生成的是 `vpc_A` / `vpc_B` | ✅ 已修：改用 `build_vpc_regions()` 的返回值 |
| 8 | `templates/*.py` | feed / waveguide 参数是硬编码字面量（`x0=1, wf1=0.5, wg_a=0.5 …`），与参考模型（`x0=4, wf1=0.2, wg_a=0.7312, wg_b=0.3756, wg_t=0.2`）不符 → 默认参数下几何必然对不上参考工程 | ✅ 已修：提升为构造参数并把默认值改为参考模型取值 |
| 9 | `topo_modeler/builders/port.py` | `full_deembedding` / `consider_material_inside` 形参存在但函数体从不使用（调用方以为生效） | ✅ 已修：删除这两个空转形参，改为 `orientation` / `shield` 并真正转发给 `add_port()` |
| 10 | `topo_modeler/builders/solver.py` | `calculation_type` 形参被完全忽略，恒定调 `configure_time_solver()` | ✅ 已修：按 `TD-S`/`FD-S`/`EIGENMODE`/`IE-S`/`ASYMPTOTIC` 分派，非法值抛 `ValueError` |
| 11 | `topo_modeler/lens_build.py` | `from hexlib import ...` —— `hexlib.py` 归档后**导入即失败** | ✅ 已修：改从 `mesh_grid.hex_grid` 导入 |
| 12 | 全库拼写 | `substract`、`roation`、`new_componet`、`patten_export`、`invertdrection`、`AccurarcyHex/Tet` | ✅ 已修：正确名 + 旧名保留为弃用**别名**，不破坏兼容 |
| 13 | `mesh_grid/tri_grid/core.py` | `plot_triangle_grid()` 没有 `ax` 形参，导致 `TopoPath.preview()`（默认 `show_grid=True`）必抛 `TypeError` | ✅ 已修：新增可选 `ax=None` |
| 14 | `tpc_toolkit/effective_medium.py` | 顶层 `from scipy import signal` / `from tqdm import tqdm` / 一批 `hex_grid` 符号，**一个都没用到**，却把 scipy、tqdm、ezdxf、shapely 变成硬依赖（`import tpc_toolkit` 直接 `ImportError`） | ✅ 已修：删除死导入，可选依赖恢复为可选 |
| 15 | `tpc_toolkit/ga_optimizer.py` | `plot_single_pop()` 读全局 `GA`（已被注释掉）→ `NameError`；`calculate_fitness_single()` 每次评估都 `plt.show()` 弹图（GA 循环里会拖垮性能）；`selection()` docstring 与签名不符；`save_population()` 在循环内重算与索引无关的文件名 | ✅ 已修：`ga` 改为显式形参、绘图改为 `plot=False` 可选、docstring 对齐、文件名提到循环外 |
| 16 | 仓库级测试 | `tests/test_grid_opt.py` 是性能基准而非测试，且用了不存在的 `show_on=` 形参 → `pytest` 整体收集失败 | ✅ 已修：移至 `scripts/bench_grid_draw.py` 并修正形参；`python -m pytest -q` 现在 **16 passed** |

---

## 6. 仍然阻塞的事项（进阶段 4 之前必须先解决）

### 6.1 几何验收从未执行（最高优先级）

06 为阶段 2/3 定的判据是「与旧 `AB_feed.cst` / `BA_feed.cst` 逐项对比，关键尺寸偏差 < 0.1%」。
**这条从未跑过**，阶段 3 的自测脚本也从不调用 `build_all()`，所以上面第 4/5/6 号缺陷才能潜伏到本轮。

需要补的验收动作（在装有 CST 的机器上）：

```python
from cst_solver import setup
from templates import StraightWaveguide

wg = StraightWaveguide(topology='AB', length=18, output_path=r'D:\out\wg.cst')
wg.build_all()
print(wg.app.cst_file.get_messages())        # 必须为空
wg.app.cst_file.model3d.Rebuild()            # 阻塞式重放历史，最能暴露问题
print(wg.app.cst_file.get_messages())        # 必须为空
wg.save()
```

然后把生成的工程与参考工程逐参数、逐实体比对（重点：`l1`/`l2` 的 AB·BA 分配、`vpc_A/vpc_B` 的半平面、基板与晶体在 z 上是否对齐）。

### 6.2 VPC 区域语义与参考 notebook 并不一致

参考 `AB_feed.ipynb` 的 VPC-A 是「三角形区域 + `insert` / `intersect`」造出来的，
而新库 `build_vpc_regions()` 实现的是「路径上/下半区带状区域」。
**两者不是同一个几何**，而且参考 notebook 里 VPC-A 实际落在 **y < 0 半平面**（`vpca_up/dn` 的 up/dn 指的是**三角形朝向**，不是上下半区）。

本轮修 CCW 绕向时顺带把拐弯路径的带状区域改成了「真正沿路径的带」（顶点数 `N+3 → 2N+1`），
**这使差异更明确**。必须在阶段 4 之前做一次显式决策：以参考工程为准复刻旧造法，还是以新带状语义为准并重新定基线。

### 6.3 端口面编号硬编码（方案已确定，实现待阶段 4）

`builders/port.py` 的 `'10'` / `'22'` 是从旧 notebook 抄来的 CST 内部面编号。
波导尺寸/朝向/构建顺序一变就会指错面。

#### 6.3.1 先修正一个做不到的假设

06 / 04 登记的 `get_face_id_by_normal()` 隐含「遍历模型里已有的面、按法向量挑出目标面」。
**这条路走不通**：CST 的 VBA 接口**没有**任何面法向/面中心/面面积的查询 API
（`Solid.GetArea(solidname)` 返回的是**实体**表面积，不是面的）。

正确表述是**反过来**做：

> 由**参数化几何正算出**目标面上的一个点（法向与位置本来就已知）
> → 反查该点所在面的编号 → 拾取。

对 TPC 反而更合适：几何全部源自 `TopoPath` 与波导参数，点是解析已知的，不需要"猜"。

#### 6.3.2 已就位的原语（`cst_solver`，已提交）

| 接口 | 支撑的 VBA | 作用 |
|---|---|---|
| `pick_face_at(name, x, y, z)` | `Pick.PickFaceFromPoint` | 按坐标直接拾取面，**绕开编号** |
| `pick_edge_at(name, x, y, z)` | `Pick.PickEdgeFromPoint` | 同上，用于棱边 |
| `pick_point_at(x, y, z)` | `Pick.PickPointFromCoordinates` | 按坐标选点 |
| `get_face_id_from_point(name, x, y, z)` | `Pick.GetFaceIdFromPoint` | **按坐标反查面编号** |
| `get_edge_id_from_point(name, x, y, z)` | `Pick.GetEdgeIdFromPoint` | 同上，用于棱边 |
| `get_picked_count(kind='face')` | `GetNumberOfPickedFaces/Edges/Points` | **校验拾取是否真的生效** |

#### 6.3.3 方案决策：双通道，按端口面朝向分流

| 端口面类型 | 方案 | 理由 |
|---|---|---|
| **轴对齐矩形面**（直波导两端、单元天线入口） | `create_waveguide_port_free(...)`（`Coordinates "Free"` + `Xrange/Yrange/Zrange`） | 零拾取、零编号，不产生拾取状态，可复现性最好 |
| **非轴对齐面**（拐弯 / 扭转后的端面） | 正算出面上一点 → `get_face_id_from_point()` → `pick_face()` + `add_port()` | `Port.Orientation` 只有轴方向，Free 模式覆盖不了斜置面 |

`create_waveguide_port_free()` 已在 `cst_solver/simulation/ports.py` 落地（纯新增，
未改动旧的 `add_port` / `create_waveguide_port`）。

#### 6.3.4 仍未核验的事实（进阶段 4 之前必须验）

| 编号 | 待验 | 影响 |
|---|---|---|
| V2 | `Coordinates "Free"` + `Xrange/Yrange/Zrange` 能否真正建出端口 | 决定 §6.3.3 第一行是否成立 |
| V3 | `model3d.Pick` 是否暴露、查询能否把值返回 Python | 决定 `get_face_id_from_point` / `get_picked_count` 是否可用 |
| V4 | 反查出的编号喂回 `pick_face()` 能否真的选中面 | 决定 §6.3.3 第二行是否闭环 |

核验脚本：`scripts/verify_port_face_api.py`（新建空白工程，不触碰任何既有工程；
逐项打印 V2/V3/V4 并汇总）。结论出来后回填本节，并把 `builders/port.py` 的
硬编码编号替换排进阶段 4。

> **依据**：[bbl21/cst-runtime-cli](https://github.com/bbl21/cst-runtime-cli)（MIT）
> 随包的 `devkit/references/vba-official-reference.md` §9 Pick / §16 Port。
> 该仓库本机已 clone 到**本仓库之外**的 `D:\成电博士生涯\自动建模算法尝试\cst-runtime-cli\`，
> 尚未纳入本仓库，故此处不给仓库内相对链接。

> **不在本议题范围**：`Port.Coordinates` 的取值究竟认 `"Picks"` 还是 `"Picked"`，暂不核验。
> 注意它**不影响**本节方案 —— Free 通道用的是 `"Free"`（官方参考与第三方实现两处一致），
> 拾取通道沿用现有代码原样取值，两者都不依赖该判定。

### 6.4 `templates` 包名风险

顶层包名 `templates` 过于通用，安装进 site-packages 后有与第三方包重名的风险。
计划改名为 `topo_templates`，并在一个版本周期内保留旧名 shim。

---

## 7. 后续阶段的排期（以修正后的 06 为准）

| 阶段 | 名称 | 前置条件 | 预估 |
|---|---|---|---|
| 4 | 复杂模板层（GRIN 透镜 builder + 透镜天线模板） | **§6.1 几何验收通过**、§6.2 语义决策完成、§6.3 方案已定 **且 V2/V3/V4 已核验** | 3 天 |
| 5 | 工具层（ResultReader / YAML 配置 / 参数扫描 / 批量建模 / GA 优化可选） | 阶段 4 的模板可用（ResultReader 需要有结果产出） | 2 天 |
| 6 | 复杂结构 + 旧代码迁移（多路径、多端口、功分器、MZI、87 个 notebook 迁移） | 阶段 5 完成 | 3 天 |

合计约 **13.5 天**（阶段 0–3 已完成部分不计入）。

---

## 8. 相关文档

- 总架构与包职责 → [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
- 每个包一份说明 → [`../packages/`](../packages/)
- 开发工作流（改代码前必读）→ [`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md)
- `cst_solver` 维护技能（含待修清单）→ [`../../skills/developer/cst-solver-dev.md`](../../skills/developer/cst-solver-dev.md)
- 使用手册 → [`../../skills/user/tpc-usage.md`](../../skills/user/tpc-usage.md)
- 阶段 0–3 使用指南 → [`../guides/topo_modeler_guide_stage0-3.md`](../guides/topo_modeler_guide_stage0-3.md)
