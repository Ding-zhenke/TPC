# P5 证据：MultiPortAntenna 模板（α1 族，2026-09-17）

计划条目（`docs/next_plan/README.md` P5）：

> `MultiPortAntenna`、`PowerDivider`、`MZISwitch` 三类模板。

本文只记录 **MultiPortAntenna**（α1 族）；三类模板的共同口径与决策见
[复杂器件模板：设计口径与决策记录](../guides/complex_device_templates_design.md)。

## 1. 器件与来源

| 项 | 值 |
|---|---|
| 器件 | 多端口天线：**1 分 2**（主干 + 两条分支）+ **双馈源** + 两条铜波导 ⇒ **3 个端口** |
| 参考 | α1 族 4 个 notebook：`多端口\Ant3_1W2N\Ant3_{240D3, BA_240D}_epc`、`MPMBA\Ant3_{epc, epc2}`（命令序列逐条同构） |
| 源码 | `topo_templates/multiport_antenna.py`（`MultiPortAntenna`） |
| 配置 | `model.type = 'multiport_antenna'`（已从 `PLANNED_MODEL_TYPES` 挪进 `IMPLEMENTED_MODEL_TYPES`） |

⚠️ **不与参考 notebook 逐字节相同**（设计记录 §2 的口径决策 D1）：参考用**闭合区域轮廓**
画 VPC，本模板用本库口径 —— 三条 `TopoPath` 中心线 + `±y_margin` 派生区域 +
多路径布尔并（P5-79 的能力）。因此验收判据是「端口/参数同类 + 只建模 0 条 CST 消息」，
**不是**几何等价。

## 2. 实现要点（每条都对应一处取证结论）

| 要点 | 依据 |
|---|---|
| 三条中心线：主干 + `turn(±60)` 两条分支，**物理严格镜像**（`1.94, ±0.84`） | 分支角度与 `UnitAntenna` 已真机验证的口径一致（`turn(±60)`） |
| **分支角度不乘拓扑符号** | `arm_up`/`arm_dn` 按**物理**上下命名，与 AB/BA 无关（写错过一次：BA 下命名与物理方向相反） |
| 双馈源：AB `feed1` + BA `feed2`，**两族参数都要登记**（含 `lf6`） | 参考 α1 就是双馈源；缺登记会让 CST 弹模态框挂住（P4/V6 教训） |
| 三条路径**各用自己的参数前缀** `p0/p1/p2` | 共用 `p1x…` 会互相覆盖 |
| 阵列范围取**三条路径的并集** | ARCHITECTURE §6 硬约定 3 |
| 逐分支晶体 + 逐分支裁剪进并集 VPC | P5-79 的能力（`build_crystals_multi` / `clip_crystals_with_vpc`） |
| 阵列次数走**参数引用** `int(xup)` | P4 §8.7（烘数字=假参数化） |
| `wg1`（AB 侧）必须 `translate` + **关于 y 镜像成双端实体** | ⚠️ **真机实测**：不镜像时 `pick_face('wg1','22')` 选中 **0 个面**，被 `add_waveguide_port` 的校验挡下（面号与几何强相关） |
| 端口编号**由调用方给**（`port_numbers`） | 参考 notebook 之间编号就对调（A 与 B/K 不同），猜错会把激励端口搞反且 CST 不报错 |
| `shield='electric'`、面号 `'10'`（轴向口径端面） | 12/12 参考一致 |

## 3. 离线证据（不需要 CST）

| 检查 | 结果 |
|---|---|
| `pytest topo_templates/tests/test_multiport_antenna.py` | **23 项通过**（拓扑/镜像/并集阵列范围/端口校验/两族登记/路径前缀/覆盖入口/无 CST 报错/离线摘要 + 本轮新增 8 项透镜） |
| `pytest tests/test_template_param_registration.py` | **14 项通过**（其中 `multiport` 分支：双馈源 + 双波导的表达式里出现的标识符**必须都已登记**） |
| 配置文件字段 | `accepted_fields('multiport_antenna')` 给出 **22** 个可配字段（本轮新增 `lens_method/lens_dxf/lens_dxf_out/lens_layers/lens_d0_layers/lens_name/lens_component`）；`list_templates` 里 `buildable=True`、`class='MultiPortAntenna'` |

### 3.1 透镜（2026-09-18 补）：口径与**一个换算错一倍的更正**

参考里 6 个多端口/MPMBA notebook 都带透镜（`MPMBA/Ant3_epc.ipynb`、
`多端口/Ant3_1W2N/Ant3_240D3_epc.ipynb` …），做法是：

```text
def para_init(yl=10, l=[50.5, 61.3], a=0.2425, ratio=2):
    r = np.array(l)/1e3/ratio*2          # ⇒ 等效孔半径 0.0505 / 0.0613
    hexsize = a/np.sqrt(3)/ratio         # ⇒ 本库 a2 = a/ratio
    Nx = int(yl*1.15)*ratio+1            # yl=10, ratio=2 ⇒ 24
    Ny = yl*ratio+1                      #             ⇒ 21
    d0 = 6*hexsize*2*np.sqrt(3)          # ⇒ 本库 d0 = 12*a2（与 GrinLensSpec 一致）
app1.dxf_import(<lens>.dxf, component='gridlens', height='h')
app1.mirror('import_1',[0,0,0],[0,1,0],component='gridlens',copy=True,unite=True)
app1.mirror('import_1',[0,0,0],[1,0,0],component='gridlens',copy=True,unite=True)
app1.ellipse('ec_a','ec_b',[0,0],'epc1') → translate(['ec_c','0','0']) → 剪孔
```

⇒ **单枚透镜、近焦点在原点**：没有 `Rbig` 平移、没有 6 份旋转复制。本模板用
`build_grin_lens(..., place=False)` / `build_grin_lens_insitu(..., place=False)`
复刻这个口径，因此**不登记 `Rbig`**（登记它就是死写入 —— 真机脚本会查这一条）。

🔴 **更正一个换算错一倍的地方**（本轮发现）：本库 `GrinLensSpec` 的约定是
``r = r1_0 / ratio``，而参考是 ``r = 2*r_raw / ratio``。要在参考的 `ratio=2` 下得到
同样的 0.0505，`r1_0` 必须写 **0.101**（写 0.0505 会让**孔半径小一半**）。
`PowerDivider` 原先写的就是 0.0505，本轮一并更正为 0.101 / 0.1226（并加回归
`test_divider_lens_defaults_match_the_reference_arithmetic`）；`MultiPortAntenna`
的默认值同样取 0.101 / 0.1226 + `nx=24 / ny=21`（= 参考 `yl=10, ratio=2`）。
⚠️ 注意 `GRINLensAntenna` 的默认（`ratio=1.0, r1_0=0.052`）**等效半径 ≈0.052**，
与参考的 0.0505 只差 ~3%（那是 V6 真机验收过的配置），本轮**不动**它。

## 4. 真机证据（CST 2026，**只建模不求解**）

命令：`python scripts/verify_multiport_antenna_real.py` → **OK 23 / INFO 1 / WARN 3 / FAIL 0，退出码 0**。
（天线用**小尺寸** `straight_length=4 / arm_length=3` 以便分钟级完成；透镜另跑两条路线。）

| 观测 | 实测 |
|---|---|
| 建模（多路径 + 双馈源 + 3 端口） | ✅ 未抛异常、**0 条 CST 消息** |
| 部件清单 | ✅ 晶体 **3 套**、端口 **3 个**、`feed1`/`feed2`/`wg1`/`wg2` 齐全；裁剪吸收 3 对晶体 |
| H1 多路径并集 | ✅ 历史里含 `Solid.Add` |
| H2 每条分支都裁到 | ✅ `Solid.Intersect` ≥ 6（= 3 分支 × 2 晶体） |
| H3 关键实体名 | ✅ `vpc_A`/`vpc_B` + `feed1`/`feed2` + `wg1`/`wg2` |
| H4 阵列次数是参数引用 | ✅ 历史里出现 `int(xup)` / `int(yup/2)` / `int(ydn/2)` |
| H5 参数闭合性（复用 P4 §8.7 工具） | ✅ **库下发参数死写入 0 项**（已引用 60 / 共 95） |
| **透镜 `generate`** 建模（现算 + 落 DXF） | ✅ **0 条 CST 消息**；`ec_a=2.91`、`nx=24/ny=21/ratio=2` |
| 透镜 `generate` 路线语义 | ✅ DXF 文件在 + 历史里 `Import` 在（真的走了 DXF 路线） |
| 透镜 `generate` 没有多余的 `Rbig` | ✅ 参数表 `Rbig=None`、`Ls=9.0695` |
| **透镜 `insitu`** 建模（**不落 DXF**） | ✅ **0 条 CST 消息**；历史里 `Hexagon` **91** 条 = 离线象限孔数 |
| 透镜 `insitu` 路线语义 | ✅ DXF 文件不在 + 历史里无 `Import`；`Rbig`/`Ls` **都不登记** |
| 单枚口径（两条路线） | ✅ 历史 caption 里**没有**该透镜的 `rotation` 条目（没有 6 份复制） |
| 组件口径（`insitu`） | ✅ 误指 `component1` 的指令 **0** 条 |
| 收尾 | ✅ 无残留 DE（回到基线 `[]`）、无弹窗 |

报警项只有 3 条 `WARN` 与 1 条 `INFO`，全部来自模板自带的旧工程参数
（`N=(y0+4)*2` 求值为空、`cell_h*`/`xmax` 等未被引用），与本次新增能力无关。

## 5. 复现命令

```text
python -m pytest topo_templates/tests/test_multiport_antenna.py -q   # 离线 23 项
python -m pytest tests/test_template_param_registration.py -q        # 离线 14 项
python scripts/verify_multiport_antenna_real.py                      # 真机（只建模，分钟级）
```

## 6. 仍未覆盖

* **求解级**：该器件**没做过任何求解**（端口激励/隔离度/传输全未验证）—— 属 P4/V2、V7、V9；
* **端口几何位置**沿用参考约定（AB 侧双端实体 + BA 侧轴线），**没有**把波导建到分支末端的物理位置
  —— 参考的 `path1` 是闭合轮廓，本库是 Y 形中心线，二者对"分支末端"的定义不同；
  若要严格对齐参考，需要另做"轮廓模式"入口（设计记录 §2 已记代价）；
* `PowerDivider` 与 `MZISwitch` 两个类型仍在 `PLANNED_MODEL_TYPES`（护栏测试会挡住"悄悄宣称支持"）。
