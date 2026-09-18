# P5 证据：多路径 VPC 区域并集与晶体裁剪（2026-09-17）

计划条目（`docs/next_plan/README.md` P5）：

> 多路径 VPC 区域并集与晶体裁剪；基板并集已存在，需增加 VPC 的对应组合并真机验收。

## 1. 缺口是什么

`build_substrate_multi`（阶段 8 模块 6.1）早就支持「各分支各做一条带再布尔并」，
但 VPC 区域与晶体阵列还是**单路径**的：

| 部件 | 修前 | 后果 |
|---|---|---|
| VPC 区域 | `build_vpc_regions(app, path, …)` 只吃一条路径 | 功分器 / MZI 的分支露在 VPC 区域外，分支上的光子晶体被裁掉 |
| 晶体阵列 | `build_topological_crystal` 的实体名固定（`g1A` / `tri_up_A`） | 两条分支建两套晶体时**实体重名**（`tri_up_A` 撞车），CST 里会重名/复用 |
| 裁剪 | `intersect_crystal_with_vpc` 只处理一对晶体 | 多分支时没有「把每条分支的晶体都裁进并集区域」的入口 |

## 2. 新增能力

| 函数 | 作用 |
|---|---|
| `builders/vpc_region.py::build_vpc_regions_multi(app, paths, …)` | 每条路径各做上/下半区带，**按侧布尔并**成 `vpc_A` / `vpc_B` |
| `builders/crystal.py::build_crystals_multi(app, paths, …)` | 每条路径各建一套 A/B 晶体阵列，返回 `{路径名: (a, b)}` |
| `builders/crystal.py::clip_crystals_with_vpc(app, vpca, vpcb, crystals)` | 逐分支 `vpca intersect g{k}A`，返回被消耗的晶体名（可核对"每条分支都裁到了"） |
| `TopoModeler.build_vpc_regions()` | **多路径时自动走并集**（与 `build_substrate` 对称） |
| `TopoModeler.build_crystals_multi()` / `.clip_crystals_with_vpc()` | 模型层的两个入口，`_built_parts` 里留痕 |

### 命名口径（自定，参考规格里没有这条；已写进 docstring）

* **VPC**：第一条路径的第一段沿用规范名 `vpc_A` / `vpc_B`，其余是
  `vpc_A_p{i}_seg{j}` 并进规范名里 —— 单条路径时与 `build_vpc_regions`
  **连 CST 参数名都相同**（`p1x/p2x…`），多条路径才编号（`p01x/p11x…`，避免互相覆盖）；
* **晶体**：第 1 条分支用规范名（`g1A`/`g1B`/`tri_up_A`，与单路径逐名相同），
  第 `k≥2` 条在名字里插入分支号（`g{k}1A`/`tri_up_A{k}`）—— 这是为了让
  **两条分支的实体名不撞车**（`tri_up_A` 这种名字跨分支会重名）。

> ⚠️ 命名规则不是从参考工程抄来的（参考工程里没有多分支器件），
> 是本库为了让实体名唯一而定的；改动它需要同步改 `test_vpc_crystal_multi.py`。

## 3. 离线证据（不需要 CST）

`python -m pytest topo_modeler/tests/test_vpc_crystal_multi.py -q` → **22 项通过**：

| 守住的性质 | 用例 |
|---|---|
| 单路径等价（可以安全按路径数自动分流） | `test_single_path_multi_matches_single_path_builder`（调用序列逐条相同）、`test_single_path_keeps_canonical_entity_names` |
| 并集目标永远是规范名（`Add` 结果留第一个操作数） | `test_union_targets_are_the_canonical_names`、`test_every_segment_of_every_path_is_united_once` |
| 各路径用各自的参数前缀 | `test_each_path_gets_its_own_parameter_prefix`（`p0*` 与 `p1*` 不相交） |
| 每条分支的晶体都被吸收 | `test_clip_absorbs_every_branch`（`(vpc, crystal)` 顺序 + 4 条 Intersect） |
| 实体名不撞车（含内部小三角形） | `test_crystals_multi_has_no_entity_name_collisions` |
| 阵列次数可走参数引用（P4 §8.7 口径） | `test_crystals_multi_can_reference_cst_parameters` |
| 模型层接线与缺件报错 | 5 条 `TopoModeler` 用例 |

写这几条用例时踩到两个**假 app 的坑**（已写进测试文件注释）：
`extrude(name=…)` / `translate(repetitions=…)` 是**关键字**传的；
`_Recorder.__getattr__` 会把写错的助手名静默变成"啥都不做的假 CST 方法"（返回 `None` 而不是报错）。

## 4. 真机证据（CST 2026，**只建模不求解**）

命令：`python scripts/verify_vpc_multi_real.py` → **OK 16 / INFO 1 / WARN 3 / FAIL 0**（退出码 0）。

构造：Y 形两分支（主干直走 18 步；分支第 6 步后拐 120° 再走 10 步），
材料 → 多路径基板 → VPC 并集 → 每条分支一套晶体 → 逐分支裁剪 → 保存。
**阵列次数缩小成 4/4/4**（真机验收只关心"CST 接不接受这套 VBA"与命名，
阵列规模不影响这一点；完整阵列是 26/15/15，孔数上千、耗时不可控）。

| 观测 | 实测 |
|---|---|
| M1 多路径基板并集 | ✅ 建模成功、**0 条 CST 消息** |
| M2 多路径 VPC 并集 | ✅ 建模成功、**0 条 CST 消息**，实体 `vpc_A` / `vpc_B` |
| M3 多路径晶体阵列（阵列次数走 `int(xup)` 参数引用） | ✅ 建模成功、**0 条 CST 消息** |
| M4 逐分支裁剪 | ✅ 4 条 `Solid.Intersect`、0 消息 |
| H1 历史里有布尔并 | ✅ 含 `Solid.Add` |
| H2 每条分支都裁到了 | ✅ `Solid.Intersect` = **4** = 2 × 分支数 |
| H3 命名 | ✅ `vpc_A` / `vpc_B` / `g1A` / `g1B` / `g21A` / `g21B` 齐全 |
| H4 分支段实体真的并进了规范名 | ✅ 25 行涉及 `vpc_*_p*_seg*` |
| H5 参数闭合性（复用 P4 §8.7 的工具） | ✅ **库下发参数死写入 0 项**（已引用 39 / 共 87） |
| 收尾 | ✅ 无残留 DE（回到基线 `[]`）、无弹窗 |

> 顺带说明：报警项只有 3 条 `WARN` 与 1 条 `INFO`，全部来自模板自带的旧工程参数
> （`N=(y0+4)*2` 求值为空、`xmax`/`cell_h*` 等未被引用），与本次新增能力无关。

## 5. 复现命令

```text
python -m pytest topo_modeler/tests/test_vpc_crystal_multi.py -q   # 离线 22 项
python scripts/verify_vpc_multi_real.py                            # 真机（只建模，分钟级）
```

## 6. 仍未覆盖

* **真实功分器 / MZI 拓扑**（`PowerDivider` / `MZISwitch`）还没建模板 ——
  本条目只保证「多路径 VPC 与晶体裁剪」这条路通了，见计划 P5 的模板条目；
* 多路径 + **端口/馈源**的多端口整合（`integrate` 目前仍是占位实现）；
* 多路径晶体的**阵列范围**仍按各路径 `get_array_range()` 推断 —— 真实器件要的是
  「覆盖整个基板」的并集范围，需在模板层显式传参（`TopoModeler.array_range()` 已能给并集值）。
