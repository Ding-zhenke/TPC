# 复杂器件模板：设计口径与决策记录

> 对象：计划 P5 的三类模板 `MultiPortAntenna` / `PowerDivider` / `MZISwitch`。
> 证据来源：19 个参考 notebook 的逐 cell 取证（见 [复杂器件参考规格](./complex_device_specs.md) §4.2–§4.5）。
> 本文记录**已定的口径**、**默认决策**（可推翻）与**尚未拍板的问题** —— 让"为什么不那样做"可查。

## 1. 参考文献告诉我们什么（已取证）

| 组 | notebook | 端口 | 分路 | 路径形态 | 馈源 |
|---|---|---|---|---|---|
| α1 | `Ant3_1W2N`、`MPMBA\Ant3_*`（4 个） | **3** | 1分2 | **闭合轮廓** `path1` 回连 p1（6 点） | 双馈源：AB `feed1` + BA `feed2` |
| α2 | `椭圆透镜1div3\*`、`B5\Ant6_2H4L`（5 个） | 1 | 1分2/3/4、2H4L | 闭合轮廓 / 多区域拼接 | 单馈源 |
| β | `1分4\Ant4_1d2d4_2f2s` | 1 | 级联 1d2d4 | 闭合轮廓 | 单馈源（探针面 4） |
| γ | `Ant6_undiretional\ANT6_C6_hexring` | **6** | 1分6 C6 | 六边形环 + 6 径向臂 | 6×BA 探针 + 子工程透镜 |
| δ | `Ant6_undiretional\ANT6_undirectional` | 1 | 单臂 | `TopoPath` DSL（**唯一用库 API**） | 单 BA 探针 |
| MZI | `开关尝试\AB\MZI*`（4 个） | 2 | 单/并联 | 6 点（parallel 10 点）**折线** | 单 AB 探针 + 2×pump + 圆柱 |
| 直波导/天线 | P0 的 5 个 | 1–2 | — | `(r,c)` 中心线 | 单馈源 |

## 2. 🔴 结构性分歧：**闭合区域轮廓** vs **中心线派生**

这是写模板前必须先定的问题，取证的 19 个复杂器件 notebook **几乎全部**用前者：

| | 参考 notebook 的做法 | 本库既有模板的做法 |
|---|---|---|
| 区域怎么来 | 显式**闭合 polyline** 画出 VPC 区域（`vpc_a_area1` + `vpc_a_area2`…，`path1` 甚至直接回连 `p1` 闭合） | `TopoPath` 给**中心线**，`build_vpc_regions` 按 `±y_margin` **派生**上/下半区 |
| 分路怎么来 | 给区域轮廓 + `mirror` / 多块区域拼接 | 多条 `TopoPath`（P5-79 已支持多路径并集 + 逐分支晶体裁剪） |
| 与参考的关系 | —— | 直波导/天线两条模板**已与参考工程逐值核对**（`xup/yup/ydn`、臂端、包围盒） |

### 默认决策（可推翻）：**选本库口径（中心线派生）**

理由：

1. **与既有模板一致**：两个已真机验收的模板都走中心线；混两套口径会让 `TopoModeler` 的
   多路径/VPC/晶体机制出现两条并行代码路径；
2. **复用 P5-79 的成果**：多路径 VPC 并集 + 逐分支晶体裁剪已实现并真机验收（20 OK / 0 FAIL），
   复杂器件正好用得上；
3. **可离线验证**：中心线是纯几何数据，区域派生是纯函数，能离线逐值比对；
   而闭合轮廓方案要复刻每个 notebook 的轮廓顶点表达式（每个 notebook 都不一样）。

### 代价（必须写清，不许粉饰）

* 模板产物**不会**与参考 notebook **逐字节相同**：区域边界由 `±y_margin` 派生，
  而不是 notebook 里那条显式轮廓。因此**验收判据只能是**：
  ① 端口数/位置同类；② 全部关键尺寸参数名与取值一致；③ 只建模真机 0 错误消息；
  **不能**声称"与参考工程几何等价"（那是直波导/天线才有的待遇，因为它们有参考工程可逐值核对）；
* 若某个器件**必须**逐字节复刻（例如后续要做求解对比），那就得单独做"轮廓模式"入口 ——
  届时再评估，不在本轮承诺范围内。

## 3. 三个模板的目标范围（按取证收窄）

### 3.1 `MultiPortAntenna`（α1 族）

* 端口 **3 个**，编号**由调用方给**（参考 notebook 之间就存在对调，猜错会把激励端口搞反且 CST 不报错）；
  已落地 helper：`builders/port.py::add_multiport_port_set(app, [(solid, port, face), …])`（默认 `shield='electric'`）；
* 双馈源：AB `feed1`（`x0/wf1/lf1/lf2/lf3`）+ BA `feed2`（`x01/wf2/lf4/lf5`），
  两条铜波导分别用 AB 范围 `[-lf1-lf2-lf3, -lf1]` 与 BA 范围 `[-lf5-lf6-lf4, -lf4]`；
* 拓扑：主干 + 双分支（`mirror` 得到第二条），走 P5-79 的多路径 VPC 并集 + 逐分支晶体裁剪；
* 分路数维度：**只做 1分2**（α1 的 4 个 notebook 全是 1分2）。

### 3.2 `PowerDivider`（α2 族）

* 分路数 `split_ratio ∈ {2, 3, 4, 6}`（**有数据依据**：1分2/1分3/1分4/1分6 各有 notebook）；
  **不提供** `divider_type('y'/'t'/'cascade'/'mmi')` —— 参考参数表里没有这些字段
  （`tests/test_complex_device_scope.py` 已用机器护栏挡住）；
* 可选：是否带透镜、是否有相位差（`dphi1/dphi2`，仅 F 与 H 有；语义 = **把透镜绕 z 转 dphi 再放到各输出臂**）；
* 单馈源 + 单铜波导 ⇒ **1 端口**（参考 notebook 就是这么建的）。

### 3.3 `MZISwitch`

* 路径：6 点折线（0°/+120°/0°/−120°/0°），单 AB 探针，**2 端口**；
* 附加结构：`pump1` 矩形耦合区（`ax`=半宽[单位 a]、`ay`=上抬[单位 e2]）+ 镜像；圆柱（`rc1=0.4`，材料 m1）；
* `mzi_type`：**`basic` 与 `cascade` 在 CST 侧完全相同**（逐 cell 取证）⇒ 模板里二者只能是
  **同一几何的别名**（或按来源文件名记录），**不许**按"级联段数"造不同几何；
  `parallel`（10 点）与 `anti`（两组 `ax/ay` + 不对称泵浦）是**真的有几何差别**，可各做一个分支；
* 材料 `m1`（`Epsilon 11.9` / `Sigma=sigma1`）用 `cst_solver.create_material_custom()` 建。

## 4. 默认决策清单（可被用户推翻）

| # | 问题 | 默认取值 | 依据/代价 |
|---|---|---|---|
| D1 | 区域构造口径 | **中心线派生**（本库口径） | §2；代价=不与 notebook 逐字节相同 |
| D2 | `lf5` 过渡段实现 | **解析半椭圆**（`build_ba_tapered_feed` 现有实现，`create_elliptical_cylinder` + `square` + `subtract`） | 参考里三种实现（三角近似/解析/离散 80 点）分别属不同 notebook 族；本库已有的是解析版且**已真机验收**。选它意味着与 K/L（解析）同构，与 ①③ 族有形状差异（记录在案） |
| D3 | `PowerDivider` 分类维度 | **分路数 + 透镜 + 相位**，无 `divider_type` | §4.3 取证；已有护栏测试 |
| D4 | MZI `basic`/`cascade` | **同一几何**（别名或来源标签） | 逐 cell 取证：CST 侧无差别 |
| D5 | 端口面号 | 轴向口径面 `'10'`；其余面号由调用方给，且沿用"选不中就抛"校验 | 12/12 取证 + 仓库 `picks.py` 的警告 |
| D6 | 模板落位 | `topo_templates/{multiport_antenna,power_divider,mzi_switch}.py`，并把三个类型从 `PLANNED_MODEL_TYPES` 挪进 `IMPLEMENTED_MODEL_TYPES` | 与 GRINLensAntenna 同一流程（`tests/test_complex_device_scope.py` 会强制同步） |
| D7 | 就地环透镜的**组件口径** | `insitu` 路线**全程**用调用方给的 `component`；DXF 路线**保持** `component1`（孔阵列在 `lens_component` 里） | DXF 路线与被收编的 `lens_build.py` **逐字节一致**且真机验过（`test_lens.py::test_cst_call_sequence_matches_original` 钉着），改它要同时改基线与真机复验 ⇒ 属"要不要放弃旧脚本等价性"的决策，未擅自改。代价：同一模板的两条路线透镜落在不同组件（由测试分别钉住，见 [P5 就地环透镜证据](../validation/p5_grin_lens_insitu_evidence.md) §5） |
| D8 | 就地环透镜的**参数化边界** | 孔径渐变的"距离"照参考做法**烘成数字**（`(1.2345-d0)`），不追求 P4 §8.7 的"全 CST 表达式" | 参考 notebook 就是 f-string 写死距离；改成全参数化需要另发明一套表达方式，且没有任何参考可比对。代价：改 `lens_layers`/`lens_d0_layers` 必须整枚重建（本库离线重算孔集合，不缓存） |
| D9 | 就地路线的 `Ls` | **不登记**（`Ls` 只被 DXF 路线的楔形裁剪用到） | 真机跑 `verify_model_parameter_usage.py` 抓到 `Ls` 死写入后改；回归 `test_insitu_does_not_register_unused_ls` + `test_generate_still_registers_ls` |
| D10 | `PowerDivider` 的透镜路线 | 与 `GRINLensAntenna` **同名同义**的三条：`generate`（现算 + 落 DXF）/ `dxf`（现成 DXF）/ `insitu`（**不落 DXF**）；`Rbig` 三条都登记、`Ls` 只有**椭圆透镜**路线（generate/dxf）登记 | 原模板**一个都没登记 `Rbig`/`Ls`** ⇒ 透镜路线在真机上直接抛 preflight ValueError；第二轮又发现 `Ls` 只在 `== 'dxf'` 时登记 ⇒ `generate` 漏登记（本轮修）。三条同名让配置侧的 `lens_method` 取值集合对两个模板都成立（否则 YAML 会写出模板不接受的值） |
| D10b | 透镜实体的**组件实际值** | 两个 builder 都返回 **`entity_component`**（实体**实际**所在组件），调用方按它寻址 | DXF 路线实体在 `component1`（D7），就地路线在 `component` —— 调用方按参数猜组件会报 `Shape does not exist`（真机踩两次）；回归 `test_builders_report_the_real_entity_component` |
| D11 | 配置（YAML）与模板构造参数的**一致性** | 机器护栏：每个构造参数要么能配，要么在 `NON_CONFIGURABLE` 里写明"为什么不该配"；`FieldSpec.choices` 对**非 enum 类型也强制校验** | 2026-09-17 发现 `power_divider` 连 `split_ratio` 都配不了 ⇒ YAML 表达不出"1分4"；且 `split_ratio` 声明的 `choices=(2,3,4,6)` 从来没生效（只对 `kind='enum'` 查）—— 属"文档写了、机器不守"的静默失效。回归 `topo_modeler/tests/test_config.py` 的四条新用例 |
| D12 | 多端口/MZI 模板的透镜**放置口径** | `place=False`：**单枚、近焦点在原点**（无 `Rbig` 平移、无 6 份旋转复制） | 参考 `MPMBA/Ant3_epc.ipynb`（`ellipse(...,[0,0])` → `translate(['ec_c','0','0'])` → 剪孔）与 `MZI-GRIB.ipynb`（环透镜 + `arc` 楔形）都是**单枚放原点**，**没有** Rbig。⇒ 这两个模板**不登记 `Rbig`**（登记就是死写入）；`build_grin_lens/_insitu` 因此新增 `place` 开关（默认 True 保持旧脚本逐字节一致） |
| D13 | 透镜**孔半径**的换算约定 | `GrinLensSpec` 用 ``r = r1_0/ratio``；参考是 ``r = 2*r_raw/ratio`` ⇒ 模板默认值必须写 `2×` 的那个数（`r1_0=0.101`，不是 0.0505） | 参考 `para_init` 逐行取证（`功分器加天线/椭圆透镜1div3/Ant2_1div2_*`、`MPMBA/Ant3_epc`）；`PowerDivider` 原先写 0.0505 ⇒ **孔半径小一倍**，本轮更正并加回归 `test_divider_lens_defaults_match_the_reference_arithmetic`。`GRINLensAntenna` 的 `ratio=1.0/r1_0=0.052` 等效 ≈0.052（与参考 0.0505 差 ~3%）是 V6 真机验收过的配置，**不动** |
| D14 | 功分器的**开关/泵浦区位置** | `switch_mode=None`（默认不建）/ `'arm_mid'`（每条第一级输出臂最后一段中点，用已登记的路径参数表达）/ `'explicit'`（调用方给坐标） | 参考取的是它**闭合区域轮廓**的角点中点（`(px4+px5)/2` 等），本库是**中心线派生**（D1）⇒ 坐标不可能相同；验收判据因此是"做法齐备（自定义材料 + 圆柱 + 区域副本求交 + insert）+ `rc1/sigma1` 是参数 + 只建模 0 消息"。⚠️ 实现时必须**每个开关各拷一次区域**（`Intersect` 消耗第二个操作数，副本名恒为 `<区域>_1`）—— 与 MZI 的 `pump2` 同一坑 |

## 5. 验收口径（每类模板都要满足）

| 层级 | 判据 | 是否需 CST |
|---|---|---|
| 离线几何 | 路径格点/阵列范围/关键参数逐值比对；端口条目与面号来自调用方而非硬编码 | 不需要 |
| 离线契约 | 表达式引用的标识符**必须都已登记**（`tests/test_template_param_registration.py` 的护栏） | 不需要 |
| 真机（只建模） | 每一步 **0 条 CST 消息**、历史里能看到预期命令、收尾无残留 DE | 需要（已授权，**不求解**） |
| 求解 | **不在本轮范围**（V2/V7/V9，需用户先确认算例与开销） | 需要 |

## 6. 相关文档

* 参考规格与取证：[`complex_device_specs.md`](./complex_device_specs.md) §4.2–§4.5
* 多路径 VPC/晶体的实现与真机验收：[`../validation/p5_vpc_multi_evidence.md`](../validation/p5_vpc_multi_evidence.md)
* 迁移登记（P0）：[`notebook_migration_p0.md`](./notebook_migration_p0.md)
* 计划：[`../next_plan/README.md`](../next_plan/README.md) P5
