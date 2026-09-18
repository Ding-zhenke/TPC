# P4 真机验收记录（进行中）

更新：2026-09-17。**性质：真实 CST 证据**（在装有 CST Studio Suite 2026 的本机实测）。
**未做长求解**：本文件覆盖的都是「秒到分钟级」的环境/会话与命令核验；
远场、谐振位置、真实 runner 闭环等**需要长求解**的条目仍待办（见 §4）。

环境：Windows / Anaconda Python 3.11.7 / CST Studio Suite 2026（`C:\SOFTWARE\CST Studio Suite 2026`）。

## 1. V8 环境与会话生命周期 —— ✅ 13/13 通过

脚本：`python scripts/verify_environment_lifecycle.py`（真机跑一次，退出码 0）

判定方式：以 `cst.interface.running_design_environments()` 的**进程号集合**为准，
每个探针跑完都要求回到基线（允许最多 30 s 延迟）。本次基线为空集（跑之前没有用户会话）。

| 探针 | 期望 | 实测 |
|---|---|---|
| D1 打开**不存在**的工程 | 创建 DE **之前**失败，不留空窗口 | 抛 `FileNotFoundError`；DE 集合仍为空 ✅ |
| D2 打开**存在但无效**的工程文件 | 建了 DE 之后失败 → 必须关掉 DE | 抛 `RuntimeError`（打开失败）；**DE 未残留** ✅ |
| D3 只创建 DE 再关闭 | 回到基线 | 创建后 1 个 → 关闭后 0 个 ✅ |
| D4 先关工程、再关 DE | 两步语义分别成立 | 打开后 1 个 → `project_close()` 后**仍为 1**（DE 还活着）→ 关 DE 后 0 个 ✅ |
| D5 `doctor --probe` | 只说明**接口可导入**；且不得创建 DE | `status=importable`；结束后 DE 集合为空 ✅ |

结论：`cst_solver.setup()` 的「路径错误在建 DE 之前暴露 + 打开失败清掉自有 DE」两条清理路径
**在真机上成立**；`doctor` 的 `importable` 确实只是「接口能加载」，不涉及许可与仿真（如实记录，不夸大）。

## 2. V5 存疑 VBA —— ✅ 关键问题有定论

脚本：`python scripts/verify_dubious_vba.py`（真机跑一次；每个探针**用全新工程**）

| 探针 | 结果 |
|---|---|
| C1 对照：`.Coordinates "BogusXYZ"` | **被拒**，CST 原文：`(&H8000ffff) Invalid coordinate type. Please specify either "Free", "Full" or "Picks".` ⇒ 判定通道有效 |
| C2 `.Coordinates "Picks"`（**库当前用法**，`ports.py:82`） | **被接受**（拾取 1 个面，无异常、无消息）⇒ **库是对的，不需要改名** |
| C3 `.Coordinates "Picked"`（另一种拼写） | **被拒**，同一条错误 ⇒ 第三方文档里的 `"Picked"` 是错的 |
| C4 `.Coordinates "Full"` | 被接受（CST 报错信息里列出的第三种合法值） |
| C5 对照：`.Coordinates "Free"` + `Xrange/Yrange/Zrange` | 被接受（复现既有结论） |
| C6 `Solid.Imprint "component1:b1", "component1:b2"`（两个相交方块） | **被接受** ⇒ `booleans.py:123` 的下发形式正确 |
| C7 对照：`Solid.Imprint` 坏实体名 | **被拒**：`Shape does not exist: component1:nope1` ⇒ 判定通道有效 |

**V5 定论**：`Port.Coordinates` 的合法取值是 **`"Free"` / `"Full"` / `"Picks"`**
（CST 自己的错误信息给出的枚举），库当前用的 `"Picks"` **正确**；
`Scripts/verify_port_face_api.py` 里「暂不核验」的那条现已核验完毕。`Solid.Imprint` 亦确认可用。

## 3. 真机发现的两条**既有约定需要修正**（重要）

### 3.1 「CST 不抛异常，只写消息」并不完全成立

实测：非法 VBA 会让 **`model3d.add_to_history()` 直接抛 Python `RuntimeError`**，
异常文本里带 CST 原文（`(&H8000ffff) …`）。例：

```
RuntimeError: An error occurred while trying to execute add_to_history:
(&H8000ffff) Invalid coordinate type. Please specify either "Free", "Full" or "Picks".
(.Coordinates "BogusXYZ")
```

⇒ 正确说法是：**失败有两条通道** —— ① `add_to_history` 可能直接抛异常；
② 有的只写消息。判定必须**两条都看**（本次脚本的 `verdict()` 就是这么做的）。

### 3.2 `get_messages()` 不是「读一次就干净」

实测：工程历史里只要留下**一条失败命令**，之后每次 `get_messages()` 都会**再次**
报出那条历史失败（Step 4 / Step 15 的错误在后续探针里反复出现）。

⇒ 后果很实在：**任何「消息为空 = 成功」的判定在脏工程里会一直判失败**。
本次第一版 V5 脚本就因此把 `pick_face_auto()` 带偏 —— 它一直返回 `None`，
而 `GetNumberOfPickedFaces()` 明确是 `1`（拾取其实成功了）。

**已据此修库**（`cst_solver/modeling/picks.py`）：`pick_face_auto()` 改为**优先用
已选面数**作为正向信号（`_pick_succeeded()`），拿不到计数时才退回消息判定；
新增 `cst_solver/tests/test_picks.py`（5 项）把两条路径都钉住，其中一项就是
「消息非空但已选面数为 1 ⇒ 必须判成功」的回归用例。

## 4. V1 天线阵列范围与路径方向语义 —— ✅ 参数映射真机核对、语义查清并实现（仅剩新路径真机复验）

脚本：`python scripts/verify_antenna_mapping.py --topology both`（真机；每次从干净模板复制新建）

### 4.1 旧 notebook 的权威取值（从参考工程读出）

| | AB（臂朝 +y） | BA（臂朝 −y） |
|---|---|---|
| 路径点（格点 r,c） | (0,0)→(0,18)→(14,18) | (0,0)→(0,18)→(−14,18) |
| `xup` | `x1+int(y1/2)` = **25** | `x1+int(y1/2)+1` = **26** |
| `yup` / `ydn` | `y1` = **14** / **14** | **14** / **14** |
| `xmax` | `a*x1+y1*e1+e1` = 6.18375 | `a*x1+e1` = 4.48625 |

（来源：`普通单元天线\Ant1_D_{AB,BA}_120_Feed_antenna-DF` 的 `Model/Parameters.json` 与对应 ipynb；x1=18 直段周期数、y1=14 臂长。）

### 4.2 修复前的实测（缺陷确认）

| 探针 | 实测 |
|---|---|
| 模板路径 | `[(0,-1), (0,18), (15,3)]` —— 臂走了 **arm_length+1** 步 |
| 阵列范围（模板用的 `path.get_array_range()`） | **`(26, 16, 1)`** vs 参考 (25, 14, 14)：`yup=16`/`ydn=1` 既不对称也覆盖不到臂；`ydn=1` 会让 `crystal.py` 下发 `int(ydn/2)`=**0 次复制** |
| 建模 | 失败：`(&H8000ffff) The specified curve is not closed and planar. (.Create)` |

### 4.3 已修（库改动）

`topo_templates/unit_antenna.py`：
- 臂长改为 `move(arm_length, 'along')`（此前多一步，与库自己的映射表不符）；
- 阵列范围**不再用 `path.get_array_range()`**，改为参考工程公式：
  `xup = straight_length + int(arm_length/2) (+1 for BA)`、`yup = ydn = arm_length`。

修复后实测（真机）：**AB `(25, 14, 14)` ✅ / BA `(26, 14, 14)` ✅**，与参考工程逐值相同；
路径 `[(0,-1), (0,18), (14,4)]`。离线回归 `topo_templates/tests/test_antenna_mapping.py`（7 项）钉住这些数字。

### 4.4 ✅ 已解决：弯折路径的偏移多边形自交（本轮修复）

**原现象**：修复参数后仍无法建模，报
`(&H8000ffff) The specified curve is not closed and planar.`（`ExtrudeCurve .Create`）。
跳过基板直接调用 `build_vpc_regions(app, path)` 也抛同一个异常。

**根因（两层）**：

1. `topo_path.build_substrate_polygon()` / `build_vpc_area_polygon()` 只在 **y 方向**偏移
   （`py ± y_margin`）—— 直线路径没问题，拐弯路径上两条链互相穿插；
2. 更本质的是：**恒定宽度的整条带在折回路径上会自覆盖**，单个简单多边形**根本无法表达**
   （120° 折回的天线路径就是这种情形）。所以只把偏移算「准」还不够。

**修复（2026-09-17）**：

| 位置 | 改动 |
|---|---|
| `mesh_grid/tri_grid/topo_path.py` | 新增 `_step_vectors()` / `_normal_coeff()` / `_vertex_offset_coeffs()` / `_offset_chains()`：按**段法向 + miter 连接**偏移，全部用有理数运算并把系数写成 CST 表达式（`sqr(3)`、`y_margin`），**不引入硬编码数值**；新增 `build_segment_band_polygons()`：**每段一个平行四边形 + 拐角补块**（`_turn_cross()` 判定左/右转，只在**外侧**补） |
| `topo_modeler/builders/substrate.py` | 改为按 `build_segment_band_polygons()` 逐段建模 + 布尔并（与既有 `build_substrate_multi` 同一套路） |
| `topo_modeler/builders/vpc_region.py` | 同上，A/B 两个半区各按 `side='lower'/'upper'` 逐段建模 + 布尔并 |

**向后兼容**：直线路径只有一段 ⇒ 产物与旧实现**逐字节相同**（单测钉住）；`build_substrate_polygon()` /
`build_vpc_area_polygon()` 仍然提供（弯折路径下仍是单多边形，仅供兼容与查看，构建器已不再用它）。

**真机复验**（`python scripts/verify_antenna_mapping.py --topology AB|BA`，两次各 8/8 通过）：

| 拓扑 | 路径 | 阵列范围 | 建模 | 落盘 `xup/yup/ydn` |
|---|---|---|---|---|
| AB | `[(0,-1),(0,18),(14,4)]` | (25, 14, 14) | **成功，0 条 CST 消息** | 25 / 14 / 14 |
| BA | `[(0,-1),(0,18),(14,4)]` | (26, 14, 14) | **成功，0 条 CST 消息** | 26 / 14 / 14 |

新增离线回归：`mesh_grid/tri_grid/tests/test_band_polygon.py`（平行四边形不自交、CCW、直线路径逐字节兼容、
**带内采样点覆盖性**、miter 表达式无硬编码数值、180° 折返给出明确错误）。

### 4.5 ✅ 语义已查清：参考 notebook 的「120D」= 库里的 `turn(60)`，不是 `turn(120)`

**取证方式（全部离线、只读，不启动 CST）**：解析参考 notebook 的 JSON 源码取参数定义 +
解码**已建好的参考工程**的 `Model/Parameters.json`（`px3/py3`、`xmax`、`x1/y1`），
再用库的 `TopoPath` 复现同一条路径比对格点与物理坐标。

**参考工程的权威事实**（`普通单元天线\Ant1_D_{AB,BA}_120_Feed_antenna-DF.cst`）：

| 工程 | `px1,py1` | `px2,py2` | `px3,py3` | 臂的物理方向 |
|---|---|---|---|---|
| AB 120 | (0, 0) | (`x1*a`, 0) = (4.365, 0) | (`px2+y1*e1`, `py2+y1*e2`) = (6.0625, **+2.9402**) | **+60°** |
| BA 120 | (0, 0) | (`x1*a`, 0) = (4.365, 0) | (`px2+y1*e1`, `py1−y1*e2`) = (6.0625, **−2.9402**) | **−60°** |

即：直段沿 **+x**（`x1 = 18` 步 × `a`），然后臂相对直段**只转 60°**（AB 逆时针、BA 顺时针，两者严格镜像）。
`x1 = 18`、`y1 = 14`、`xup = x1+int(y1/2)[+1 for BA] = 25/26` 与模板当前默认值一致。

**库侧复现（`TopoPath.builder(a).start(0,-1).move(19,'c').turn(θ).move(14,'along')`）**：

| θ | 路径格点 `(r,c)` | 臂端物理坐标 | 与参考对照 |
|---|---|---|---|
| `0` | `[(0,-1),(0,18)]` | (4.3650, 0.0000) | 直波导型 ✅ |
| **`60`** | `[(0,-1),(0,18),(14,18)]` | **(6.0625, +2.9402)** | **= 参考 AB 120，逐位相同 ✅** |
| **`−60`** | `[(0,-1),(0,18),(-14,32)]` | **(6.0625, −2.9402)** | **= 参考 BA 120，逐位相同 ✅** |
| `120` | `[(0,-1),(0,18),(14,4)]` | (2.6675, +2.9402) | **不匹配任何参考单元天线** ❌ |

**结论与实现**：`bend_angle` = **两侧臂张角**（= 2 × 单臂偏角，与 notebook 文件名一致）。

> **用户确认（2026-09-17）采用「张角口径」并已实现**（本轮）：
> `UnitAntenna` 下发 `turn(±bend_angle/2)`，符号按拓扑取（AB `+`、BA `−`）；
> 合法值收紧为 **120 的整数倍**（`60/180/300` 会让单臂落在 30°/90°/150°，不是晶格方向，
> 构造时 `ValueError`，配置层 `choices=(0,120,240,360)`）；`topo_modeler/config.py`
> 的 `modeler_from_config()` 同步（含符号）。
> 于是默认 `bend_angle=120` + 默认 `18/14/xup` **正好复现参考 120D**，`240` 对应 240D。
> 离线回归：`topo_templates/tests/test_antenna_mapping.py`（臂端与参考工程逐位比对、
> AB/BA 镜像、张角≠转角、合法值边界）+ `topo_modeler/tests/test_config.py`。

> ⚠️ **遗留的真机复验**：§4.4 那批真机核验（AB/BA 各 8/8、0 条 CST 消息）跑的是**改语义之前**
> 的弯折路径 `[(0,-1),(0,18),(14,4)]`；臂方向改为 `turn(±60)` 后路径变成
> `[(0,-1),(0,18),(14,18)]` / `[(0,-1),(0,18),(-14,32)]`，**需用新路径补跑一次真机建模核验**
> （建模级、分钟量级、不求解）。在此之前不要把「弯折路径已真机通过」当作新路径的结论。
>
> **离线层面已把新形状补进回归（2026-09-17）**：`mesh_grid/tri_grid/tests/test_band_polygon.py`
> 现在把三种弯折形状（新 AB `turn(+60)`、新 BA `turn(-60)`、旧 `turn(120)`）都参数化跑一遍 ——
> 「每段四边形不自交」「CCW」「带内采样点被四边形并集覆盖」「miter 表达式含 `sqr(3)` 且无硬编码
> 小数」四项全部通过，并新增「AB/BA 路径互为镜像且臂端 x=6.0625」的断言。
> 也就是说：**改语义后没有引入新的自交风险**（那正是当初真机报
> `The specified curve is not closed and planar.` 的成因），但「CST 是否接受」仍只能由真机回答。
>
> **补跑只需一条命令**：`python scripts/verify_antenna_mapping.py`（AB + BA 各一次建模，
> 核对 0 条 CST 消息、落盘参数、臂端与参考工程逐位一致），并且它默认在**同一次 CST 会话**里
> 顺带跑「求解控制 API 探针」（P2 待办的 `--live` 那一步）—— **两个待办一条命令一起收**。
> 脚本内部一致性（参考臂端常量、`--no-solver-api-probe`、替身 `probe_live_app`）由
> `tests/test_real_machine_scripts.py` 离线钉住。

**改语义同时消掉的两个口径问题**（同一轮实现）：

1. **默认值现在自洽**：模板的 `straight_length=18`、`arm_length=14`、`xup/yup/ydn`
   取自 120D 参考工程（§4.3），而 `bend_angle=120` 现在**也**就是 120D 几何 ✅
2. **两种拓扑现在互为镜像**：`sign = +1 (AB) / −1 (BA)`，
   与参考的 AB `+60°` / BA `−60°`（`structureBB` y 界 ±2.9402 对称）一致 ✅

> 参考 240D 族的 notebook（`Ant1_grid_240D_circle.ipynb`）臂方向是 `(−e1,+e2)` = 120°，
> 等于 `turn(120)` = 张角 240 的一半 —— 这也是「数字 = 两侧臂张角」这条口径的另一半证据。

## 5. V4 守卫与导出流程 —— ✅ 真机 10/10 通过（含修掉一处误报）

脚本：`python scripts/verify_guard_export_flow.py`（真机；G3 只操作**已求解工程的副本**）

| 探针 | 结果 |
|---|---|
| G1 `StraightWaveguide`（warn 模式） | 建模成功；CST 消息 0；守卫 finding 0；噪声警告 0 ✅ |
| G2 `UnitAntenna`（warn 模式） | **修复前**：6 条 `[LOG_FLAG_NO_REBUILD]`（T7'/T13）误报；**修复后**：0 条 ✅ |
| G3 T3 场景（已求解工程副本） | `export_result_1d` 真的产出文件；随后 `save(include_results=True)` **如期**给出 `SAVE_AFTER_RESULT_EXPORT`（plan_id=T3，severity=warning）；改用 `include_results=False` **不再告警** ✅ |
| G4 端口增强真实调用 | `add_port(1, number_of_modes=2, adjust_polarization='True', polarization_angle='30', reference_plane_distance='0.5')` → CST 消息 0 条 ⇒ 被接受 ✅ |

### 5.1 G2 的误报：根因与修复

**现象**：天线模板 warn 模式下刷 6 条 `[LOG_FLAG_NO_REBUILD]`，点名 `p1x/p1y/p2x/p2y/p3x/p3y`。

**根因**：`build_substrate`、`build_vpc_regions` 与模板的 `_define_all_params` **都会**调用
`TopoPath.auto_define_cst_params()`。第二次及以后登记时参数**已存在**（`preexisting=True`）
且几何**已建了一部分**（`geometry_exists()` 为真），守卫便按「改了已存在参数」判脏并告警 ——
但登记的是**同一个表达式**，路径晶格根本没变，属于误报。

**修复**：`auto_define_cst_params()` 改为**幂等** —— 同一个 `TopoPath` 在同一个 `app`
（且同一前缀）上只登记一次；换 app 或换前缀仍然正常登记，参数化能力不受影响。

**离线回归**：`mesh_grid/tri_grid/tests/test_param_definition.py`（4 项：幂等、换 app 仍登记、
换前缀仍登记、登记值仍是表达式而非数值）。

## 6. V6 GRIN 透镜与多路径基板 —— ✅ 真机核验（17 OK / 0 FAIL / 1 UNKNOWN，UNKNOWN 已离线消解）

脚本：`python scripts/verify_grin_multipath.py`（真机，**只建模不求解**；产物落
`%TEMP%\tpc_verify_v6_*`，退出码 0）

### 6.1 L1 GRIN 透镜构建序列

真机全序列 **8 步全部 0 条 CST 消息**：DXF 导入 → y 镜像 → 椭圆挤出 → 椭圆减孔洞
→ 楔形裁剪体 → 减六边形重叠 → 平移到 0° 顶点 → 绕轴旋转并 `unite=False` 重复 6 次。

| 项 | 实测 | 判据 |
|---|---|---|
| 参数化 | 85 个 CST 参数，其中 39 个含符号表达式；`e2 = a/2*sqr(3)`、`HEX_SIZE = a/sqr(3)/2` | 表达式形式，无硬编码数值 ✅ |
| 历史命令 | `Import / Mirror / Polygon / Ellipse / ExtrudeCurve / Solid.Subtract / Transform / Material` | 与库的 VBA 序列一致 ✅ |
| 包围盒 | `x∈[-9.5469,9.5469] y∈[-8.5346,8.5346] z∈[-0.1250,0.1250]` | 关于原点对称 ✅ |
| 厚度 | z 向 `0.25000` | = `h`（0.25），且**只在收尾居中一次** ✅ |

### 6.2 L2 落盘取证

从保存后的 `lens_small.cst` 里解 `Model.abi` 的 `structureBB`（base64 → 6×double）、
读 `ModelHistory.json` 的命令关键字、读 `Parameters.json` 的 `expr` 字段 ——
**全部离线复核**，不依赖再跑一次 CST。

### 6.3 M 多路径基板

`build_substrate_multi` 在**弯折多分支**路径上建模成功、0 条 CST 消息；
包围盒 `x∈[0.0000,4.3650] y∈[-0.2100,1.7851] z∈[-0.1250,0.1250]`：
包含路径自身范围、不超出保守的 ±e2 上界、厚度 `0.25000` = `h` ✅

**UNKNOWN 的消解（本轮离线补证）**：V6 运行时那条 UNKNOWN 是「历史里找不到布尔并集
关键字」—— 当时的检查词表只有 `ExtrudeCurve/Material/Polygon/Transform`，**没有列
`Solid.Add`**。本轮直接离线重读产物：

| 工程 | 出现的布尔命令 |
|---|---|
| `lens_small.cst` | `Solid.Subtract`（椭圆减孔洞、减六边形重叠） |
| `multi.cst` | **`Solid.Add`**（逐段四边形并集 —— 正是弯折路径防自交用的那条路径） |

⇒ M 组「逐段四边形 + 布尔并集」在真机产物里**有确凿命令级证据**，该 UNKNOWN 关闭。
（检查词表已补：`scripts/verify_grin_multipath.py::_history_commands` 应含 `Solid.Add`。）

## 7. CST 弹窗检测（2026-09-17 用户实际遇到「是否保存」弹窗后加固）

### 7.1 现象与代价

用户手工点掉了 CST 的**「是否保存更改？」模态弹窗**。这类弹窗（和未定义参数时的
「请输入变量值」）会**永久阻塞** Python 侧的下一次 CST 调用，而纯文本运行的调用方
看不到任何异常 —— 表现为脚本无声挂死。

### 7.2 加固后的 `scripts/cst_dialog_guard.py`

| 能力 | 说明 |
|---|---|
| 全量窗口枚举 | `EnumWindows`（`Get-Process.MainWindowTitle` **只给主窗口，看不到对话框**） |
| 进程名解析 | `QueryFullProcessImageNameW` + **进程名缓存**；对高完整性进程（实测 CST 的 `cstd.exe`）OpenProcess 被拒时用**一次** `tasklist` 全量兜底。旧实现每个窗口起一次 `tasklist`，947 个顶层窗口下直接超时 ❌ |
| 对话框识别 | 按窗口类名 `#32770` 判定，并枚举按钮文字与控件 ID |
| 保存弹窗识别 | `save_prompts()`：标题/按钮命中 保存·save·更改·changes |
| 主动断言 | `check_dialogs(label)`：有可见对话框就抛 `CstDialogTimeout`（附快照），**不继续调用 CST** |
| 显式关闭 | `dismiss_dialogs(prefer=('否','no','取消','cancel'))`：默认「不保存」（与用户手工选择一致）；**按钮不匹配时绝不盲点**，返回 `no_match` |
| 看门狗 | `guard(label, timeout)`：超时抓窗口 + 对话框快照再报错 |

离线回归：`tests/test_cst_dialog_guard.py`（8 项，不碰真机窗口）。
真机接入：`verify_grin_multipath.py` 在建/关 DE 前后打印窗口与对话框快照，
关 DE 后调用 `_check_close_dialogs()` 记录「有无残留保存弹窗」。

### 7.3 会话收尾实测（本轮）

窗口枚举是**可靠证据**：`EnumWindows` 下**没有任何 CST 顶层窗口**（`cstd` 主界面已退出、
没有对话框），只剩一个**无窗口的常驻进程** `cstd.exe`。

⚠️ **一处更正（2026-09-17 复查）**：当时还引用了
`topo_modeler.batch.running_design_environments() is []` 作为「没有 DE 活着」的证据 ——
**这条不成立**：该函数在 `cst.interface` 无法导入时**吞掉异常返回空列表**
（本机 Anaconda 解释器默认没把 CST 的 `python_cst_libraries` 放进 `sys.path`，
所以它**必然**返回 `[]`，与是否真有 DE 无关）。
结论：**判「有没有 DE 活着」必须用能区分「没有」和「问不到」的判据**
（例如先确认接口可导入、或直接看进程/窗口），不能把「空列表」当否定证据。
这也正是 P1 新增 `describe_interface_abi()` 的用途 —— 先离线确认
解释器能不能加载接口（本机 CST 2026 提供 cp311，当前解释器 3.11.7 = cp311，ABI 匹配）。

## 8. V7 的「读」半边 —— ✅ 已在**真实 CST 输出**上验证（不需要 CST、不需要求解）

计划 P4/V7 要「真实 runner 完成一次小范围串行闭环」，其中**跑求解**那半必须真机；
但**读结果**那半只需一份**真的算过的工程** —— CST 官方明确写着
`cst.results` *"No running instance of CST Studio Suite is required for data access"*。

**此前被登记为「未验证风险」**：`topo_modeler/tests/test_result_reader.py` 开头写着
「本机没有任何『已存结果可读』的工程 ……`source` 是真 .cst 路径时读取路径未验证」。
本轮复查发现该前提**已不成立**：参考工程 `普通单元天线\Ant1_D_BA_120_Feed_antenna-DF.cst`
里有**真实求解结果**。于是这条风险**离线**关掉了。

脚本：`python scripts/verify_result_reading.py`（只读；不启动 CST、不求解、不复制大文件）
→ **OK 12 / FAIL 0 / UNKNOWN 0**

| 探针 | 实测 |
|---|---|
| `cst_solver.Result(真工程)` 打开 + 结果树 | 31 个结果树条目；run ids `[0, 1]` |
| `ResultReader.read_s_parameters('S1,1')` | **1001 点，300.0–380.0 GHz** |
| `ResultReader.peak_position('S1,1', kind='min')` | **−32.075 dB @ 341.920 GHz** |
| `run_contract.cst_result_probe()` | `run_ids=[0, 1] available_results=31` |
| `run_contract.result_fingerprint()` | 真实输出上的磁盘指纹（`ModelCache/*` 条目） |
| 缺项 `S9,9` | 抛 `ResultReaderError` —— **报错而不是返回空数据** |
| 只读性 | 工程目录 **3049 个文件，前后快照 0 变化**（含 mtime） |
| 「工程不存在」 | 报「工程文件不存在」+ 保留原始异常（见下） |

### 8.1 顺手抓到并修掉的一个**误导性错误**

`cst.results.ProjectFile()` 在**路径不存在**且**含非 ASCII 字符**时抛的是
``UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb2 ...`` ——
看着像编码问题，其实是「文件不存在」（错误消息里带着本地代码页编码的路径，读取器又按
UTF-8 解它）；纯 ASCII 的不存在路径则正常报 `FileNotFoundError`。
现已在 `cst_solver/_result_core.describe_result_open_failure()` 里**先判存在性**，
把它翻译成「工程文件不存在：<路径>（原始错误：…）」，并说明这个坑。

> ⚠️ **一处自我更正**：本轮的第一次判断曾是「非 ASCII 路径会破坏结果读取」——
> **错的**。当时传给 `ProjectFile` 的路径把工程目录名与文件名拼重了（文件并不存在）。
> 复核后确认：**中文路径下的已求解工程读取完全正常**（31 个条目，与复制到纯 ASCII 路径的
> 结果一致），真正的问题是「不存在」被报成了编码错误。结论已按复核结果重写。

回归：`tests/test_result_reading_real_project.py`（7 项，真工程；缺 CST 库或参考工程时整文件 skip）
与 `cst_solver/tests/test_result_open.py`（6 项，纯离线，覆盖诊断与异常链）。

### 8.2 V3 判据（「谐振峰偏差 < 1 GHz」）在真实曲线上跑通（2026-09-17）

计划 P4/V3 原文：*「旧四个频点 dB 比较不等于『谐振峰偏差 < 1 GHz』；需使用可比曲线、
明确峰/谷提取规则并实际计算频率差」*。这条判据此前只是文档里的一句话（既没有 API，
也没在真数据上算过）。本轮把它做成可执行版本，并用**真实曲线**验证：

脚本：`python scripts/verify_resonance_criterion.py`（离线，只读已求解工程）
→ **OK 24 / FAIL 0 / UNKNOWN 0**；参考工程目录前后快照 **0 变化**。

**首先消掉一处真实的重复实现**：这些规则原本有**两份** ——
`cst_mcp/analysis.py`（prominence 多极值）与 `topo_modeler/result_reader.py::peak_position`
（全带单一极值），属于 `conventions.md` 明令禁止的「同一数值规则两处实现」。
现在只有一份：`tpc_toolkit/curves.py`（`contiguous_bands` / `find_resonances` /
`match_resonances` / `resonance_criterion`），MCP 层与库层都调它
（MCP 只把 `ValueError` 翻成 `invalid_arguments` 错误码）。

**真实数据结果**（5 个参考工程的 `S1,1`，prominence 0.5 dB）：

| 工程 | 提取到的谐振（GHz） |
|---|---|
| AB_120_Feed | 297.20, 345.40, 347.40, 350.00, 353.90 |
| BA_120_Feed | 311.68, 323.20, 324.80, 341.92 |
| AB_180_Feed | 284.20, 331.00, 343.90, 346.30, 348.20, 350.60, 356.20, 370.20, 374.70, 377.40 |
| AB_120_cylinder | 288.80, 302.50, 334.90, 342.20, 344.70, 349.40, 353.50, 375.40, 377.50 |
| BA_120_cylinder | 307.20, 316.00, 324.00, 325.44, 343.68, 348.56, 370.08 |

两两配对（就近 + 容差 3 GHz）后，判据的**三个出口都在真实数据上出现过**：

| 出口 | 真实例子 |
|---|---|
| `within_limit`（通过） | BA_120_Feed vs AB_120_cylinder：配 1 对，最大 Δf **0.280 GHz < 1 GHz** |
| `exceeds_limit`（未通过） | AB_180_Feed vs AB_120_cylinder：配 6 对，最大 Δf **2.900 GHz** |
| `no_matched_resonance`（**不算通过**） | AB_120_Feed vs BA_120_Feed：容差内一对都配不上 ⇒ `ok=False` 并如实报告原因 |

**跨层一致性**（防规则漂移的机器检查）：5 个工程各比对一次 ——
同一条曲线经 `cst_mcp.analysis.find_resonances` 与库层规则得到的结果**逐条完全相同**。

> ⚠️ **这里验证的是判据与方法学那一半**。「本库自己跑一次求解再与参考对比」（V3 的另一半）
> 仍属真机，需要 ≥2 次求解 —— 那时这条判据已经可以直接用
> `ResultReader.resonance_shift(...)` 调出来。

回归：`tests/test_curve_rules.py`（13 项：区间/谐振/配对/判据三出口、跨层一致、
MCP 层不得再实现规则本体、`ResultReader` 委托）。

### 8.3 结果项覆盖扫描 + 一个卡住 **V2** 的真实限制（2026-09-17）

V2 要验证「`create_field_monitor('Farfield', …)` + `export_farfield_csv()` 的路径、模式与单位」。
在动手之前先用离线手段**探清能不能读远场结果** —— 结果是：**读不了一类关键条目**。

脚本：`python scripts/verify_result_item_coverage.py`（离线、只读；逐项尝试打开并读数据）
→ 对 `Leaky\ANT_LEAKY_EPC_GRID.cst`：**OK 6 / FAIL 0**，其中

| 项 | 实测 |
|---|---|
| 结果树条目 | **63** 条 |
| 可读（`get_result_item` + `get_xdata` 均成功） | **45 / 63** |
| 不可读 | **18 / 63**，**全部**是 `1D Results\farfield (f=290…324)` |
| 失败类型 | 全部 `UnicodeDecodeError`，且发生在 **`get_result_item()` 阶段**（还没碰数据） |
| 是否路径写法问题 | ❌ 同工程 `Materials\Silicon (lossy)\…`、`Copper (annealed)\Z' (Fit)`、`Port Information\…` 等**带括号**的条目全部正常；相对路径也失败 |
| 是否有远场数据可替代 | ✅ `Tables\1D Results\Realized Gain,3D,Max. Value (Solid Angle)`（18 点）可读 |
| 工程目录 | 5043 个文件，前后快照 **0 变化** |

**结论（对 V2 的影响）**：在**这个**工程上，「远场 1D 条目」无法用 `cst.results` 离线读出，
因此 `export_farfield_csv()` 的离线验证**不能**用这些条目做依据；能读的远场派生数据是
`Tables` 下的汇总表。真机上 V2 仍需要真跑一次求解（我们自己的工程，结果由我们自己写），
届时这条限制是否同样出现要**重新实测**（目前只在 1 个旧工程上观察到，样本 = 1，不推广）。

**顺带修掉一个真实陷阱**：`read_1D()` 一直**无条件**给路径加 `1D Results\` 前缀，
而 `get_tree_items()` 返回的是**完整**路径 —— 于是最自然的「查出路径 → 读回来」会拼成
`1D Results\1D Results\…` 并报 `tree path not found`。现在两种写法都接受
（完整路径原样用、相对路径补前缀），失败时错误信息里**列出试过的候选路径**并说明前缀规则。
脚本里也对真实工程核对了「完整路径 vs 相对路径结果一致」✅。
另外：裸 `UnicodeDecodeError` 现在会被翻译成可执行的话（指出该项元数据解不开、
可改用 `Tables` 汇总或从 CST 导出 CSV），见
`cst_solver._result_core.describe_result_item_failure()`。

回归：`cst_solver/tests/test_result_items.py`（7 项，纯离线替身）。

### 8.4 `list_s_parameters()` 误报收敛曲线（2026-09-17 修，真机数据发现）

用**本库自己的 API**（而不是裸 `cst.results`）逐个读真实工程时发现：
`Leaky\ANT_LEAKY_EPC_GRID.cst` 上 `list_s_parameters()` 返回的是

```python
['Reflection S-Parameters [1]', 'S1,1', 'S2,1']
```

第一个根本不是 S 参数，而是**收敛监控曲线**
（`1D Results\Convergence\S-Parameters\Reflection S-Parameters [1]`，262 点）。
旧实现只判「路径里是否含 `'S-Parameter'`」，于是它被排在**第一个** ——
任何 `names[0]` / 逐个遍历的调用（`ResultReader` 的自动发现路径就是这样）
会立刻抛 `ResultReaderError`。

**修复**：`list_s_parameters()` 改为双条件 —— 必须是 `S-Parameters` 目录的**直接子项**，
且叶子名符合 CST 的 S 参数命名 ``S<端口1>,<端口2>``。并写下**不变式**：
> 本函数返回的每个名字都必须能被 `read_s_parameter()` 读出来。

真机核对（3 个工程）：

| 工程 | 修前 | 修后 |
|---|---|---|
| `Leaky\ANT_LEAKY_EPC_GRID.cst` | `['Reflection S-Parameters [1]', 'S1,1', 'S2,1']` | `['S1,1', 'S2,1']` ✅ 全部可读 |
| `Leaky\ANT_LEAKY_EPC_GRID_r1=0.04.cst` | `['S1,1','S2,1']`（恰好没踩到） | `['S1,1','S2,1']` ✅ |
| `普通单元天线\Ant1_D_BA_120_Feed_antenna-DF.cst` | `['S1,1']` | `['S1,1']` ✅ |

修后 `ResultReader.peak_position(names[0])` 在 3 个工程上都正常返回
（例：`ANT_LEAKY_EPC_GRID` → −40.343 dB @ 376.400 GHz）。

回归：`cst_solver/tests/test_result_items.py`（10 项，含把那条收敛曲线作为**陷阱样例**的
离线用例）、`tests/test_result_reading_real_project.py`（多端口工程的不变式 + 往返读取）。
扫描脚本也加了这条不变式：`python scripts/verify_result_item_coverage.py` → **8 OK / 0 FAIL**。

### 8.5 广域核验：30 个真实工程 × 结果读取全动作集（2026-09-17）

单个工程只能证明「那条路径能走通」，而结果树形态差异很大（1 端口 / 3 端口 /
只有材料色散曲线 / 带收敛监控 / 带远场 1D 项…）。新增
`scripts/verify_result_reading_wide.py`：按家族抽样，对每个工程跑**同一套动作**：

> 打开 → `list_s_parameters()`（不变式：列出的每个名字都必须可读）→
> `read_all_s_parameters()`（条目数一致、点数非零）→
> `export_s_parameters_csv()`（行数 = 点数 + 1、表头含全部名字）→
> `ResultReader` 用自动发现的名字取峰 → `cst_result_probe` / `result_fingerprint`

结果：**OK 42 / FAIL 0 / UNKNOWN 0，问题 0 条**（30 个工程，5 个家族）

| 家族 | 抽查 | 形态 |
|---|---|---|
| 普通单元天线 | 5 | 1 端口，1001 点 |
| Leaky | 7 | 2 端口（含收敛监控曲线的那个工程） |
| MPMBA | 7 | 1 端口 + **3 端口**（6 条 S 参数）+ 无 S 参数 |
| 多端口 | 5 | **3 端口 6 条 S 参数** / 无 S 参数 |
| 开关尝试 | 6 | MZI：2 端口 / 无 S 参数 |

要点：

* **3 端口工程**（`Ant3_epc.cst`、`Ant3_240D3_epc29_MP3.cst`）写出 **6 条 S 参数**
  （`S1,1…S3,2`），逐条 1001 点、CSV 表头含全部 6 个名字 ✅ —— 这是此前没覆盖到的形态；
* **8 个工程本来就没有 S 参数结果**（只有材料色散/收敛曲线，如 `Ant1_epc_mf_AB.cst`）：
  `list_s_parameters()` 返回 `[]` 被**如实**记为「该工程没有 S 参数结果」，不是失败 ——
  这正是「空结果 ≠ 问到就是空」的应用：区分「没有」与「读不到」；
* 五个家族目录前后快照 **0 变化**（合计约 2.1 万个文件）；
* 选择策略上也修了一处：家族工程可能在**子目录**里（`多端口`/`开关尝试` 顶层是 0 个），
  且固定切片会把多端口工程全挡在门外 —— 改成**递归查找 + 家族间轮流取**。

回归：`tests/test_result_reading_real_project.py`（11 项，新增 3 端口工程的
「6 条 S 参数 + CSV 表头 + 取峰 + 谐振判据自比」用例）。

### 8.6 路径写法在整类里统一（2026-09-17 修，真机数据发现）

接着 §8.3 的双层前缀问题继续排查「还没在真实数据上跑过的那几个 API」时发现：
**同一个类里三种路径约定**。

| 方法 | 修前接受 | 实测 |
|---|---|---|
| `read_1D()` | 完整 **或** 相对（§8.3 已修） | ✅ |
| `get_run_ids()` | **只有完整** | `get_run_ids('S-Parameters\\S1,1')` → `tree path not found` ❌ |
| `get_result_item()` | **只有完整** | 相对写法同样失败 ❌ |

修复：抽出一份共用的候选路径展开（`Result._candidate_paths()`）——
完整路径原样用；相对路径先补 `1D Results\\`，再依次补其它一级分类
（`2D/3D Results\\` / `Tables\\` / `Farfields\\`），全部失败时抛出**列出候选**的错误。
三个方法现在都走它。真机核对（`Leaky\ANT_LEAKY_EPC_GRID.cst`）：

| 调用 | 结果 |
|---|---|
| `get_run_ids('1D Results\\S-Parameters\\S1,1')` | `[0, 1, 2]` |
| `get_run_ids('S-Parameters\\S1,1')` | `[0, 1, 2]`（与完整路径**一致**） |
| `get_run_ids('S-Parameters\\S1,1', skip_nonparametric=True)` | `[1, 2]` |
| `get_result_item(完整)` vs `(相对)` | 数据逐点一致 ✅ |
| 底层接口没有 `get_run_ids`（老版本） | 明确说「该版本不支持」，而不是 `AttributeError` |

**顺带确认了两件事（本轮探针的另一半）**：

* `ResultReader.plot_s_parameters()` / `plot_all()` / `export_csv()` 在真实工程上可用
  （自包含 HTML 28 KB / 75 KB、CSV 38 KB / 90 KB）；
* `export_farfield_csv()` 在本机两个工程上**仍无法验证** —— 它们没有 `Farfields`
  二维/三维远场结果项（`2D/3D` 分组为空），调用会抛 `ValueError` 并**列出结果树里的
  候选路径**（错误信息本身是可用的）。远场条目的限制见 §8.3。

回归：`cst_solver/tests/test_result_items.py`（15 项，含候选路径顺序/去重、
两种写法等价、缺项报错、老版本接口缺失的提示）、
`tests/test_result_reading_real_project.py`（12 项，含真机 `get_run_ids` 两种写法一致）。

### 8.7 阵列次数被「烘成数字」= 假参数化（2026-09-17 真机取证并修复）

**起因**：V1 真机复验里 `ant_AB_120` 落盘的 `xmax = 8.85125` 与参考工程的
`a*x1+y1*e1+e1 = 6.18375` 对不上，而且 AB/BA 两个拓扑的 `xmax` **完全相同**
（参考工程里两者不同）。顺着这条线查参数表，查出两件事。

#### 发现 1：模板 `tmp.cst` **并不干净**

`CLEAN_TEMPLATE`（`D:\TPC_out\tmp.cst`）实际带着 **77 项参数**，是某个旧工程留下的：

| 类别 | 实测 |
|---|---|
| 与本次无关的常量 | `x1=8`、`y1=8`、`xmax=8.85125`、`ymax_up/ymax_dn`、`HEX_SIZE`、`cell_Width`、`cell_h0…h14`、`Gen_Length/Gen_Width`、`tmpx1/tmpy1/…` |
| 阵列范围 | `xup=37`、`yup=24`、`ydn=24`（本次库会覆盖成 AB `25/14/14`、BA `26/14/14`） |
| **求值为空的死参数** | `N = (y0+4)*2` —— `y0` 从未定义，CST 把它的 `value` 存成**空串** |

* `xmax` 就是这类遗留常量：三个工程（模板 / AB / BA）值**逐字相同**、AB 与 BA 无差别，
  不可能是库算出来的；
* 脚本里那句注释「干净模板（**只含单位/边界/网格设置**）」**是错的** —— 已改写；
* 这些遗留项**没有被任何表达式引用**（历史里的 `.Xmax` 只是边界设置，大小写敏感匹配下
  不是参数 `xmax`），所以**不影响几何**，属无害噪声；真正的规矩是「不许引用模板垃圾」，
  由下面的检查工具把住。

#### 发现 2（真缺陷）：阵列次数是数字，不是参数引用

| 复制方向 | 参考工程 `Ant1_D_AB_120_Feed_antenna-DF` | 本库（修前） |
|---|---|---|
| X 阵列 | `.Repetitions "int(xup)"` | `.Repetitions "int(25)"` |
| Y+ 阵列 | `.Repetitions "int(yup/2)"` | `.Repetitions "int(14/2)"` |
| Y− 阵列 | `.Repetitions "int(ydn/2)"` | `.Repetitions "int(14/2)"` |

修前整份 `ModelHistory.json`（1523 条字符串）里 `xup|yup|ydn` 出现 **0 次** ——
参数表里的阵列范围**形同备注**：在 CST 里改 `xup` 阵列不会重排，而参考工程会。
全库这类「烘数字」只有 3 处（`builders/crystal.py` 的三个 `translate`）；其余路径点
（`p1x…`）、晶格常数（`a/e1/e2`）、孔尺寸（`l1/l2`）本来就是**参数名引用**，没有问题。

#### 修复

`topo_modeler/builders/crystal.py` 新增 `repeat_expression(value, divisor=1)`：
**str ⇒ 当 CST 参数名引用**（`int(xup)`、`int(yup/2)`），**数字 ⇒ 烘成数值**
（`int(25)`、`int(14/2)`，与修前**逐字节一致**，不影响别的调用方）；
`UnitAntenna` / `StraightWaveguide` 改为传 `xup='xup', yup='yup', ydn='ydn'`。

#### 真机前后对照（CST 2026，只建模、不求解）

| 观测项 | 修前 `ant_AB_120`（20:18） | 修后 `ant_AB_120` |
|---|---|---|
| 历史里 `xup|yup|ydn` | **0 次** | `int(xup)` / `int(yup/2)` / `int(ydn/2)` 各 2 次（A/B 两个晶体） |
| 引用统计 | 已引用 44 / 未引用 41 | 已引用 **47** / 未引用 38 |
| **库写过却没人引用（死写入）** | **`xup, ydn, yup`** | **无** |
| CST 消息 | 0 | 0 |
| 臂端 / 阵列范围 | 与参考一致 | **与参考一致**（回归未被破坏：AB `(6.0625,+2.9402)`、BA `(6.0625,−2.9402)`；AB `25/14/14`、BA `26/14/14`） |

#### 新增的检查工具（离线，不连 CST）

* `scripts/verify_model_parameter_usage.py`：查「参数表 ↔ 表达式 ↔ 建模历史」闭合性

  | 判据 | 内容 | 严重度 |
  |---|---|---|
  | A | **在用**公式引用了未定义名字 | FAIL |
  | A | 死参数里的坏公式（模板自带的 `N`） | WARN |
  | A2 | 参数在 CST 里求值为空（引用了未定义名字的指纹） | WARN |
  | B | 每个参数名是否被历史/公式引用 | OK |
  | C | 未引用项分类：模板遗留（无害）/ **本次写过却没人引用（死写入）** / 公式参数 | FAIL / INFO |
  | D | 模板遗留项被引用时，值是否被本次改写过 | WARN |

  判据关键点：CST 的 `Parameters.json` 里 `expr` 是**表达式原文**（常量参数就是自己的
  数字文本），所以「是不是公式」要拿 `expr != value` 判断；C 的死写入证据是**值被改写**
  （`37→25`），不是「名字在不在模板里」—— 模板自己也有同名 `xup`，光看名字判不出来。

* `scripts/verify_antenna_mapping.py` 默认调用它（`--no-param-usage` 可关），
  并直接断言历史里出现参考工程那三条 `int(...)` 原文。

#### 顺手修掉新检查自己的一个假 FAIL

新检查最初用 `output`（`…ant_AB_120.cst`）拼 `Model\3D\ModelHistory.json`，
而 CST 存的是**文件夹形式**工程（`…ant_AB_120\Model\3D\…`）⇒ 历史读成**空**、
三条表达式全报「缺」⇒ 假 FAIL（**又是「空结果 ≠ 问到就是空」的同族坑**：
没区分「没有这个文件」和「没有这些表达式」）。改成先 `resolve_project()` 解析，
并让 detail 带上历史字符串条数；在同一份真机产物上复检 **FAIL = 0**。

#### 回归

* `topo_modeler/tests/test_crystal_array_expression.py`（12 项）：`repeat_expression`
  四条分支、两个晶体 6 次 `translate` 的表达式序列、数字入参逐字节兼容、
  `None` 回退 `get_array_range()`、模板源码里必须传参数名（防止回退）；
* `tests/test_model_parameter_usage.py`（13 项）：判据 A/A2/B/C 的每条分支、
  `3` vs `3.0` 数值等价、`.Xmax` 大小写不误判、无模板模式不猜死写入。

## 9. 仍未完成（需要长求解或更大工作量）

| 编号 | 项目 | 为什么还没做 |
|---|---|---|
| V1 | ~~`UnitAntenna` 阵列范围及路径参数映射~~ | ✅ **已完成**（§8.7：新臂方向真机复验 AB 14 OK / 0 FAIL；顺手修掉「阵列次数烘成数字」的假参数化） |
| V2 | 远场监视器与主瓣 | **需要求解**（含远场监视器） |
| V3 | 谐振位置判据 | **需要可比曲线**（通常≥2 次求解） |
| V4 | 守卫/导出流程 | ✅ **已完成**（§5：真机 10/10） |
| V6 | GRIN 与多路径 | ✅ **已完成**（§6：真机 17 OK / 0 FAIL，UNKNOWN 已离线消解） |
| V7 | 读取/扫描/报告/审计/优化真实 runner 闭环 | **需要多次求解**（「读」半边已离线关掉；真后端 `build` 已由 P2 §5.1 真机验收） |
| V9 | MCP 最终交付（真机闭环） | **需要至少 1 次求解**（「预检 → 建模 → 任务记录」真机段已完成：P3 §5.4，真 CST + 真 stdio，20 OK / 0 FAIL） |

**开销提醒**（引自历史记录）：单次时域求解（关自适应 + 稳态 −20 dB）约 **5300 s CPU**、
峰值内存约 **2.4 GB**。按计划要求，启动任何新求解前先说明算例范围与预计开销并取得确认。

## 10. 复现命令

```text
python scripts/verify_environment_lifecycle.py   # V8，13 项全绿，退出码 0
python scripts/verify_antenna_mapping.py         # V1，真机建模核验 + 参数引用/闭合性审计；AB 单拓扑 14 OK / 0 FAIL
python scripts/verify_dubious_vba.py             # V5，7 OK / 0 FAIL / 2 UNKNOWN（有意留 UNKNOWN）
python scripts/verify_grin_multipath.py          # V6，真机建模级；17 OK / 0 FAIL（不求解）
python scripts/verify_result_reading.py          # V7「读」半边：真实 CST 输出上离线读取；12 OK / 0 FAIL
python scripts/verify_resonance_criterion.py     # V3 判据在真实曲线上的方法学验证；24 OK / 0 FAIL
python scripts/verify_result_item_coverage.py    # 结果项覆盖扫描 + S 参数不变式；8 OK / 0 FAIL
python scripts/verify_result_reading_wide.py     # 广域核验：30 个真实工程 × 读取全动作集；42 OK / 0 FAIL
python scripts/verify_model_parameter_usage.py <工程目录>   # 参数表↔表达式↔历史 闭合性（离线，不连 CST）
python scripts/verify_service_mcp_real.py        # 真 CST + 真 stdio MCP（只建模不求解）：20 OK / 0 FAIL
python scripts/verify_service_mcp_real.py --no-cst          # 同一脚本离线骨架：OK 10 / FAIL 0
python scripts/cst_dialog_guard.py               # 弹窗快照（--dialogs 只看对话框，--all 看所有窗口）
python -m pytest cst_solver/tests/test_picks.py -q       # 5 项：拾取判定的回归
python -m pytest tests/test_cst_dialog_guard.py -q        # 8 项：弹窗识别/不盲点（离线）
```
