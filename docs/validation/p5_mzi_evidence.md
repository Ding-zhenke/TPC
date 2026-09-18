# P5 证据：MZISwitch 模板（2026-09-17）

计划条目（`docs/next_plan/README.md` P5）：

> `MultiPortAntenna`、`PowerDivider`、`MZISwitch` 三类模板。

本文只记录 **MZISwitch**；三类模板的共同口径与决策见
[复杂器件模板：设计口径与决策记录](../guides/complex_device_templates_design.md)。

## 1. 器件与来源

| 项 | 值 |
|---|---|
| 器件 | MZI 开关：单路径 6 点中心线（0° → +120° → 0° → −120° → 0°）+ 耦合区矩形 + 开关圆柱 + **2 端口** |
| 参考 | `开关尝试\AB\MZI.ipynb`（`basic`）与 `MZI-cascade.ipynb`（**CST 侧与 basic 完全相同**，逐 cell 取证） |
| 源码 | `topo_templates/mzi_switch.py`（`MZISwitch`） |
| 配置 | `model.type = 'mzi_switch'`（已从 `PLANNED_MODEL_TYPES` 挪进 `IMPLEMENTED_MODEL_TYPES`） |

### 1.1 `mzi_type` 的语义（**取证结论，不许按"级联段数"造几何**）

逐 cell 比对 `MZI.ipynb` 与 `MZI-cascade.ipynb`：只有 cell 1（matplotlib 预览函数
`plot_power_divider`，返回值**从未进入 CST**）与 cell 23（保存文件名）不同，
cell 2–22 的全部建模命令**逐字节相同** ⇒ **两者建出的 CST 模型是同一个**。

因此本模板把 `basic` / `cascade` 实现成**同一几何**（`mzi_type` 只作来源标签，
写进 `summary()`）；`parallel`（10 点路径 + 基板无 `ymax_dn` 分支 + 下半区改用整体
`mirror`）与 `anti`（两组 `ax/ay` + 不对称泵浦 + `copy=False` 的镜像）是**真实几何差别**，
**尚未实现** ⇒ 传入时**明确报错**（不静默当成 basic）。

## 2. 真机暴露的三个问题（都已修，且都有离线护栏）

### 2.1 `ydn=1` ⇒ `Invalid number of repetitions`（库缺口）

`TopoModeler.build_crystal()` **不能传** `xup/yup/ydn`，只能回退到
`path.get_array_range()`；MZI 这种**单边偏置**路径推出的是 `ydn=1`
⇒ 晶体复制次数 `int(ydn/2)=0` ⇒ CST 直接报错（P4/V1 同类坑第二次出现）。

**修法**：给 `TopoModeler.build_crystal()` 加 `**kwargs` 透传，模板传
`xup='xup', yup='yup', ydn='ydn'`（阵列次数走**参数引用**）。
模板本身按**参考公式**算阵列范围：`xup = x1*2+x2-int(y1)+1`、`yup = ydn = y1+y2`
（默认值 9/9/5 ⇒ **23/10/10**，与参考逐值一致）。

### 2.2 CST 的 `Intersect` 会**消耗第二个操作数**

写成 `intersect('pump2', vpc_A)` ⇒ `vpc_A` 被消耗，下一步
`insert(vpc_A, 'pump2')` 报 `Shape does not exist: component1:vpc_A`。

**修法**：按参考做法先 `translate(vpc_A, copy=True)` 得到副本 `vpc_A_1`，
拿副本求交，再 `insert` 回 `vpc_A`。

### 2.3 参考的面号 `'14'`/`'4'` 在我们的构序下**不存在**

`pick_face('feed1','14')` 实测选中 **0 个面**（面号与实体几何、生成顺序强相关 ——
仓库 `cst_solver/modeling/picks.py` 自己的说明），被 `add_waveguide_port` 的
"选不中就抛"校验挡下（**没有**把端口悄悄建错位置）。

**修法**：改用 `create_waveguide_port_free()`（`Coordinates "Free"`，给坐标范围，
不产生拾取动作）：端口面取器件两端**图形化硅的截面**
（y 跨整个阵列 = `±yup*e2`、z 跨片厚 = `±h/2`）。
⚠️ 参考是把端口建在**探针端面**上（口径不同，属设计记录 D1 的口径差异）。

## 3. 离线证据（不需要 CST）

| 检查 | 结果 |
|---|---|
| `pytest topo_templates/tests/test_mzi_switch.py` | **22 项通过**：6 点路径与方向序列、三个长度参数可缩放、阵列范围公式（`23/10/10`）、**`yup/ydn ≥ 2` 回归**、`get_array_range()` 的 `ydn<2` 反例、`basic==cascade` 同一几何、`parallel/anti` **明确报错**、参数登记（`ax/ay/rc1/sigma1` + AB 族 + 路径参数）、端口规格走 Free 模式、无 CST 报错 + 本轮新增 **6 项透镜**（三条路线校验 / `Ls` 登记但**不登记 `Rbig`** / 环几何与单枚 / `generate` 落 DXF / 摘要） |
| 端口规格 | `port_specs()` 给出两条 Free 端口（`x = -(lf1+lf2+lf3)` 与 `2*(8a/2)+(lf1+lf2+lf3)`），**离线可核对** |

### 3.1 透镜（2026-09-18 补）：覆盖参考的 `MZI-GRIB`

参考 `开关尝试/AB/MZI-GRIB.ipynb` 里**整段 GRIB 环透镜建环是活代码**
（`HEX_SIZE=a/sqr(3)/2`、`N=(y[1]+2)*2`、`r=[50.5,61.3]/1e3`、只建第一象限再镜像），
且透镜放在**原点**（随后用 `arc` + 楔形裁剪，而不是整圆切半）。本模板因此提供
**三条透镜路线**（与另外三个模板同名同义）：`generate` / `dxf` / `insitu`，
并统一用 `place=False` 建**单枚、近焦点在原点**的透镜
⇒ **不登记 `Rbig`**（那个参数只服务于"移到顶点 + 6 份旋转复制"，登记了就是死写入）。

## 4. 真机证据（CST 2026，**只建模不求解**）

命令：`python scripts/verify_mzi_switch_real.py` → **OK 25 / INFO 1 / WARN 3 / FAIL 0，退出码 0**。
（用小尺寸 `arm_x1=4 / mid_x2=4 / arm_gap_y1=2` 以便分钟级完成；透镜另跑两条路线。）

| 观测 | 实测 |
|---|---|
| 建模（探针镜像 + 耦合区 + 圆柱 + 2 端口） | ✅ 未抛异常、**0 条 CST 消息** |
| 部件清单 | ✅ 端口 2 个、`feed1`/`pump1`/`pump2`/材料 `m1` 齐全 |
| H1 布尔并 `Solid.Add` | ✅ |
| H2 圆柱 `Cylinder` | ✅ |
| H3 求交 `Solid.Intersect` | ✅ |
| H4 `Solid.Insert` 回并 | ✅ |
| H5 镜像（探针/耦合区） | ✅ |
| H6 阵列次数是参数引用 | ✅ `int(xup)` / `int(yup/2)` / `int(ydn/2)` |
| **透镜 `generate`** 建模（现算 + 落 DXF） | ✅ **0 条 CST 消息**；`ec_a=2.91`、`nx=24/ny=21/ratio=2`（等效孔半径 0.0505） |
| 透镜 `generate` 路线语义 | ✅ DXF 在 + 历史有 `Import` |
| **透镜 `insitu`** 建模（**不落 DXF**） | ✅ **0 条 CST 消息**；历史 `Hexagon` **91** 条 = 离线象限孔数 |
| 透镜 `insitu` 路线语义 | ✅ DXF 不在 + 历史无 `Import` |
| 单枚口径 + 无多余参数（两条路线） | ✅ 无该透镜的 `rotation` 条目；`Rbig=None`（`Ls` 只在椭圆路线登记） |
| 组件口径（`insitu`） | ✅ 误指 `component1` 的指令 **0** 条 |
| H7 参数闭合性（复用 P4 §8.7 工具） | ✅ **库下发参数死写入 0 项**（已引用 50 / 共 93） |
| 收尾 | ✅ 无残留 DE（回到基线 `[]`） |

报警项只有 3 条 `WARN` / 1 条 `INFO`，全部来自模板自带的旧工程参数（与新增能力无关）。

## 5. 复现命令

```text
python -m pytest topo_templates/tests/test_mzi_switch.py -q   # 离线 22 项
python scripts/verify_mzi_switch_real.py                      # 真机（只建模，分钟级）
```

## 6. 仍未覆盖

* **求解级**：该器件没做过任何求解（开关隔离度/相位全未验证）—— 属 P4/V2、V7、V9；
* `mzi_type='parallel'` 与 `'anti'` **未实现**（真实几何差别），传入即报错；
* 端口口径：本模板用**两端截面**建端口，参考用**探针端面**（D1 的代价，已在 §2.3 记录）；
* 透镜口径：参考的环透镜用 `arc + 楔形` 裁剪，本库用**圆柱切半 + 楔形**（D12/D1 的口径差异）；
* `PowerDivider` 仍在 `PLANNED_MODEL_TYPES`（护栏测试会挡住"悄悄宣称支持"）。
