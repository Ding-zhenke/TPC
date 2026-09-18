# P5 证据：PowerDivider 模板（α2 族，2026-09-17）

计划条目（`docs/next_plan/README.md` P5）：

> `MultiPortAntenna`、`PowerDivider`、`MZISwitch` 三类模板。

本文只记录 **PowerDivider**（α2 族）；三类模板的共同口径与决策见
[复杂器件模板：设计口径与决策记录](../guides/complex_device_templates_design.md)。

## 1. 器件与来源

| 项 | 值 |
|---|---|
| 器件 | 1 分 N 功分器（N ∈ {2,3,4,6}）：主干 + N 条输出路径 + 单馈源 + 单铜波导 + **1 个端口** |
| 参考 | α2 族 5 个 notebook：`Ant2_1div2_{AB,BA}_120D_epc`、`Ant3_1div3_BA_120D_epc`、`Ant4_1div4_BA_120D_epc`、`Ant4_1d2d4_2f2s_circle_DF`、`B5\Ant6_2H4L_epc` |
| 源码 | `topo_templates/power_divider.py`（`PowerDivider`） |
| 配置 | `model.type = 'power_divider'`（已从 `PLANNED_MODEL_TYPES` 挪进 `IMPLEMENTED_MODEL_TYPES`；**P5 三类模板至此全部落地，计划表为空**） |

### 1.1 分类口径（只有分路数有数据依据）

参考参数表里**没有** `divider_type` 字段（`y/t/cascade/mmi` 无出处，
[规格 §4.3](../guides/complex_device_specs.md)），实测能区分的只有**分几路**。
因此模板只接受 `split_ratio ∈ {2,3,4,6}`，其余取值**直接报错**。

**级联结构**（本库口径，与参考的"级联段数"对应）：

| `split_ratio` | 扇出 | 说明 |
|---|---|---|
| 2 | 2×1 | 单级二路 |
| 3 | 3×1 | 单级三路（−60°/0°/+60°） |
| 4 | **2×2** | 两级级联 = 参考的 `1d2d4` |
| 6 | **2×3** | 两级级联 |

臂方向取三角晶格的 60° 方向（`turn(±60)` / 三级中间臂 `turn(0)`），
每条**输出路径**都是"从输入端走到一个输出端"的完整中心线 ⇒ 多路径 VPC/晶体能覆盖整个器件。

### 1.2 透镜与相位（可选，参考里只在 1div4 / 2H4L 出现）
* `dphi1/dphi2` 的语义是**把同一枚透镜绕 z 转 `dphi` 后放到不同输出臂**
  ——**不是**几何长度差；
* 模板支持三条透镜路线（与 `GRINLensAntenna` **同名同义**，2026-09-17 补齐）：

  | `lens_method` | 行为 | 是否需要 DXF |
  |---|---|---|
  | `'generate'` | `GrinLensSpec` 现算孔阵列 → 落 DXF → 建 | 自己写一份 |
  | `'dxf'` | 用现成的孔阵列 DXF | 需要（`lens_dxf=`） |
  | `'insitu'` | **不落 DXF**，在 CST 内逐个 `hexagon` 建环 | **不要**（与 `lens_dxf` 互斥） |

  `lens_phase` 在没有透镜时**直接报错**（相位作用在透镜上，没透镜给相位是无效输入）；
  `lens_method='insitu'` 的孔集合由 `make_lens_ring()` 离线算（`grin_ring_holes`）。
* ⚠️ **修掉一个"真机上根本走不通"的缺陷**（2026-09-17）：模板原先**一个都没登记
  `Rbig` / `Ls`**，而 `build_grin_lens_from_dxf` 对它们有**前置拦截** ⇒
  `lens_dxf=...` 这条路线上真机会抛我们自己的 `ValueError`
  （好在是拦截而不是 CST 的模态框）。现在按路线登记：`Rbig` 两条路线都要
  （DXF 路线用于"移到 0° 顶点"，就地路线用于放置），`Ls` **只有 DXF 路线**要
  （就地路线没有楔形裁剪，登记它就是死写入）。真机 `H4 参数闭合性` 会查这一条。
* ⚠️ **per-arm 定位尚未实现**：参考是每个输出臂各放一枚透镜（各自 `rotation(dphiN)` +
  `translate` 到臂端），本模板只做「建 + 相位旋转」，臂端定位属 D1 的待补项。
  就地路线的 `place=True` 只是「平移到 0° 顶点 + 绕原点旋转复制 ×5」
  （与 `GRINLensAntenna` 同口径），**不等于**参考的 per-arm 定位。
* 🔴 **更正：孔半径的默认值原先小一倍**（2026-09-18 发现，证据见
  [多端口证据](./p5_multiport_evidence.md) §3.1）：参考的 `para_init` 写
  ``r = [50.5,61.3]/1e3/ratio*2``（`ratio=2` ⇒ **等效半径 0.0505/0.0613**），
  而本库 `GrinLensSpec` 的约定是 ``r = r1_0/ratio`` ⇒ `r1_0` 必须写 **0.101/0.1226**。
  原先是 0.0505/0.0613（小了整整一倍），现已更正；`nx/ny` 也从"抄自天线模板"的
  16/13 改成参考的 `yl=10, ratio=2` 口径 **24/21**。回归
  `test_divider_lens_defaults_match_the_reference_arithmetic`。

### 1.3 开关/泵浦区（可选，覆盖 `pump_switching` 特征，2026-09-18 补）

参考（`椭圆透镜1div3/Ant2_1div2_*`、`B5/Ant6_2H4L_epc`）：

```text
app1.para('sigma1','0')
app1.create_material_custom(name='switch1', epsilon=11.9, mu=1, kappa='sigma1', …)
app1.para('rc1','0.4')
for i in range(4):                          # 2H4L 是 4 个开关（+2 个 `iso` 圆柱）
    app1.translate('vpca',['0','0','0'],copy=True,unite=False,log_flag=1)
    app1.intersect(f'sw{i+1}','vpca_1')     # 副本名恒为 `vpca_1`
    app1.insert('vpca', f'sw{i+1}')
```

本库实现（`switch_mode`）：

| 取值 | 行为 |
|---|---|
| `None`（默认） | 不建开关，也**不登记** `rc1`/`sigma1`（避免死写入） |
| `'arm_mid'` | 每条**第一级输出臂最后一段的中点**各一个圆柱；坐标写成**已登记的路径参数**表达式 `(p<i>{n-1}x+p<i>{n}x)/2` |
| `'explicit'` | 由 `switch_xy=[(x, y), …]` 直接给坐标（数值或 CST 表达式） |

⚠️ **位置口径**：参考取的是它**闭合区域轮廓**的角点中点（`(px4+px5)/2` 等），
本库是**中心线派生**（D1）⇒ 默认位置是"臂中点"，**不保证与参考同一坐标**；
验收判据是"自定义材料 + 圆柱 + 区域副本求交 + insert 这套**做法**齐备，
且 `rc1/sigma1` 都是参数、只建模 0 消息"。

## 2. 离线证据（不需要 CST）

`python -m pytest topo_templates/tests/test_power_divider.py -q` → **40 项通过**：
（原 20 项 + 透镜 11 项 + 开关 9 项）

| 守住什么 | 用例 |
|---|---|
| 只有 2/3/4/6 有依据，其余**报错** | `test_supported_split_ratios_are_the_evidenced_ones`、`test_unsupported_split_ratio_fails_loudly`（1/5/8/0） |
| N 分路 ⇒ **N 条输出路径**、每条都从输入端出发 | `test_output_path_count_equals_the_split_ratio` |
| 臂方向是晶格方向（两臂分居上下；三路中间臂沿原方向） | `test_fan_angles_are_lattice_directions` |
| 级联同源臂共享第一阶段、第二阶段真分叉 | `test_cascade_paths_share_their_first_stage_arm`、`test_cascade_second_stage_fans_out_from_the_first_stage` |
| 单端口 / 单馈源 / 单波导 | `test_single_port_and_single_waveguide` |
| 相位无透镜时**报错**；DXF 不存在报错；透镜规格离线可算 | `test_phase_without_lens_is_rejected` 等 4 项 |
| 参数登记（阵列范围/路径前缀/AB 族/WG） | `test_registers_paths_array_range_and_feed_params` |
| **默认不建透镜**（不登记透镜相关参数） | `test_divider_default_has_no_lens` |
| 三条路线各自的入参校验（缺 DXF / 互斥 / 非法 `lens_method` / 层数） | `test_divider_dxf_method_requires_dxf`、`test_divider_insitu_rejects_dxf_and_bad_layers`、`test_divider_generate_conflicts_with_dxf` |
| 历史行为兼容（只给 `lens_dxf` 等价于 `'dxf'`） | `test_divider_legacy_lens_dxf_implies_dxf_method` |
| **`Rbig` 两条路线都登记、`Ls` 只有 DXF 路线登记**（本轮真缺陷） | `test_divider_registers_rbig_for_both_lens_routes` |
| 就地环透镜的孔集合与参数（`HEX_SIZE=a/sqr(3)/2`、象限 91 孔）+ 摘要不混椭圆量 | `test_divider_insitu_ring_geometry` |
| 就地路线的下发序列与组件口径（`component` 必须一路带到变换上） | `test_divider_insitu_build_sequence` |
| `generate` 路线**离线**真的落出 DXF | `test_divider_generate_method_writes_dxf` |
| 摘要报告透镜信息（`summary()['lens']`） | `test_divider_summary_reports_lens` |
| **默认不建开关**（不登记 `rc1/sigma1`） | `test_divider_default_has_no_switch` |
| 开关入参校验（模式/坐标冲突/半径/坐标对） | `test_divider_switch_validation` |
| `arm_mid` 位置用的是**已登记的路径参数**表达式 | `test_divider_switch_positions_use_registered_params` |
| `explicit` 坐标原样透传 | `test_divider_explicit_switch_positions_are_passed_through` |
| `rc1/sigma1` 只在建开关时登记 | `test_divider_registers_rc1_and_sigma1_only_with_switches` |
| 下发序列：材料 → 每开关「圆柱 + **区域副本**求交 + insert」 | `test_divider_switch_build_sequence`（还钉住求交第二操作数 = `vpc_A_1`、圆柱半径用 `rc1`） |
| 没建 VPC 区域就调 `build_switches()` ⇒ 明确报错 | `test_divider_switch_requires_vpc_region` |
| 摘要把开关信息算出来（离线） | `test_divider_summary_reports_switches` |

## 3. 真机证据（CST 2026，**只建模不求解**）

命令：`python scripts/verify_power_divider_real.py`
→ **OK 38 / INFO 1 / WARN 3 / FAIL 0，退出码 0**（孔半径默认值更正后**复跑过**；
加入开关/泵浦区后又复跑一次，仍 FAIL 0）。
四种分路数**各建一次**（小尺寸 `trunk_length=4 / arm_length=3 / sub_length=2`），
外加**两条透镜路线**（1分4 + 相位 `(30, 10)`）与**一条开关路线**（1分3 + `switch_mode='arm_mid'`）。

| 观测 | 1分2 | 1分3 | 1分4（2×2） | 1分6（2×3） |
|---|---|---|---|---|
| 建模（多路径 + 单馈源 + 1 端口） | ✅ 0 消息 | ✅ 0 消息 | ✅ 0 消息 | ✅ 0 消息 |
| H1 多路径并集 + 逐分支裁剪 | ✅ | ✅ | ✅ | ✅ |
| H2 阵列次数是参数引用 | ✅ | ✅ | ✅ | ✅ |
| H3 单端口 + 单馈源（`feed1`/`wg1`） | ✅ | ✅ | ✅ | ✅ |

| 观测 | 透镜 `generate` | 透镜 `insitu` |
|---|---|---|
| 建模（含透镜 + 相位副本） | ✅ 0 消息 | ✅ 0 消息 |
| 路线语义一致（落 DXF ?= 路线声明） | ✅ DXF 在 + 历史有 `Import` | ✅ **DXF 不在** + 历史无 `Import` |
| 前置参数口径 | ✅ `Rbig=4.1225` + `Ls=9.0695` | ✅ `Rbig=4.1225` + **`Ls` 不登记** |
| 相位副本（`rotation` + `dphi1`） | ✅ | ✅ |
| 相位旋转指向真实实体 | ✅ | ✅ |
| 逐 `hexagon` 建环 | —（走 DXF 导入） | ✅ 历史 91 条 = 离线象限孔 91 |
| 变换/布尔组件口径 | 实体在 `component1`（见下） | ✅ 误指 `component1` 的指令 0 条 |

| 观测 | 开关/泵浦区（1分3 + `arm_mid`） |
|---|---|
| 建模（含开关） | ✅ **0 条 CST 消息** |
| 半径/电导率是 CST 参数 | ✅ `rc1=0.4`、`sigma1=100.0`（不是烘死的数） |
| 每个开关都走「圆柱 + 区域副本求交 + insert」 | ✅ 开关 3 个 ⇒ `Cylinder` 3 条 / `Intersect` 11 条（含晶体裁剪）/ `Insert` **3** 条 |
| 自定义材料已建 | ✅ 历史里出现 `switch1`（`epsilon=11.9` + `kappa=sigma1`） |

`Solid.Intersect` 条数 ≥ **2N**（N 分支 × 2 晶体）—— 说明**每条输出分支都被裁进了并集 VPC**。
另：`H4 参数闭合性`（复用 P4 §8.7 工具）→ **库下发参数死写入 0 项**；收尾无残留 DE。

### 3.1 真机暴露并修掉的三个问题（离线测试一个都测不到）

1. **模板压根没登记 `Rbig`/`Ls`** ⇒ 首跑 `ValueError: build_grin_lens 需要这两个 CST
   参数先存在：['Ls']`。锁在"前置拦截"上是运气（否则就是 CST 的模态框把脚本挂死）。
   现在按路线登记。
2. **`Ls` 只在 `lens_method == 'dxf'` 时登记** ⇒ 第二轮真机跑时 **`generate` 路线漏了它**
   （`generate` 走的 `build_grin_lens` 同样要裁楔形）。判据改成"**就地路线不要、其余两条都要**"。
3. **相位旋转寻址的组件错**（两次踩、两种原因）：
   * 就地路线：最终实体曾叫 `{name}-sub` ⇒ 旋转打到 `lens_epc` 报
     `Shape does not exist: gridlens:lens_epc`（已改成"最终实体就叫 `name`"）；
   * `generate`/`dxf` 路线：实体实际在 **`component1`**（旧脚本等价性，见 §1.2），
     而旋转按 `lens_component`（`gridlens`）寻址 ⇒ 同样的报错。
   ⇒ 两个 builder 现在都返回 **`entity_component`**（实体**实际**所在组件），
   模板按它寻址；离线回归 `test_builders_report_the_real_entity_component`，
   真机回归 `1分4+透镜(x) 相位旋转指向真实实体`。

> 教训（写进设计记录 D10）：**"能下发" ≠ "CST 接受" ≠ "名字/组件真的如调用方所想"**。
> 三个层次只有真机能同时验证。

## 4. 复现命令

```text
python -m pytest topo_templates/tests/test_power_divider.py -q   # 离线 40 项
python scripts/verify_power_divider_real.py                      # 真机（只建模，四种分路数 + 两条透镜路线）
```

## 5. 仍未覆盖

* **求解级**：四种分路器都没做过任何求解（分路比/隔离度/传输全未验证）—— 属 P4/V2、V7、V9；
* **透镜 per-arm 定位**未实现（见 §1.2）；相位目前只是"建 + 旋转一次"；
* **开关位置**与参考不同坐标（见 §1.3：本库取臂中点，参考取它区域轮廓的角点中点）；
* **1分6 的 `2H4L` 结构**（双透镜组 `ec_a1/ec_a2`、两组半径 + `iso` 圆柱组）未复刻 ——
  本模板的 6 路是 2×3 级联（`divider_2h4l` 特征仍算缺口）；
* 端口口径同 `MultiPortAntenna`：本库按截面建端口，参考建在铜波导轴向面上（D1 的代价）。
