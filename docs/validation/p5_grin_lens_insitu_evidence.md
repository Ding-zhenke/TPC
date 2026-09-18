# P5 证据：就地 hexagon 环透镜（`lens_method='insitu'`，2026-09-17）

计划条目（`docs/next_plan/README.md` P5）：迁移 87 个 notebook 时最大的缺口是
`lens_in_situ` —— 参考里**大部分 GRIN 天线**是在 CST 内用 `app.hexagon()` 逐环
建透镜的，而本库 `GRINLensAntenna` 原先只有「现算孔阵列 → 落 DXF」与
「用现成 DXF」两条路（都要落 DXF）。

## 1. 交付内容

| 位置 | 内容 |
|---|---|
| `topo_modeler/builders/lens.py` | `grin_ring_holes(a, *, n_layers, r1_0, r2_0, d0_layers, hex_size, quadrant_only)`（**纯几何**，不需要 CST）+ `build_grin_lens_insitu(app, holes, *, name, height, material, component, clip_name, theta, r_big, place, rotation_repetition, rotation_axis, log)`（**不落 DXF**，在 CST 内逐个 `hexagon` 建孔） |
| `topo_modeler/builders/__init__.py` | 导出上面两个 + `DEFAULT_RING_LAYERS` / `DEFAULT_D0_LAYERS` |
| `topo_templates/grin_lens_antenna.py` | `lens_method='insitu'`（第三条入口）+ `make_lens_ring()` 离线几何入口 + `lens_layers` / `lens_d0_layers` 参数；`lens_summary()` 增加环透镜字段；`Ls` 改为**按路线登记** |
| `topo_modeler/config.py` | YAML 侧同步：`lens_method` 取值加 `insitu`，新增 `geometry.lens_layers` / `geometry.lens_d0_layers`（默认 30 / 8）。否则新入口在配置文件路线上等于不存在 |
| `scripts/classify_notebook_migration.py` | `GRINLensAntenna` 能力集加 `lens_in_situ`（⇒ 该特征不再是 GRIN 天线批次的缺口）；缺口说明改成"`GRINLensAntenna` 能覆盖，但该 notebook 对应的模板不是它" |

几何常数与参考 notebook（`功分器加天线\1分4\Ant4_1d2d4_2f2s_circle_DF.ipynb`）
**逐值相同**（不是"大致一样"）：

| 量 | 参考写法 | 本库 | a=0.2425 / N=30 下的值 |
|---|---|---|---|
| `HEX_SIZE` | `a/np.sqrt(3)/2` | `a/sqr(3)/2` | 0.07000372013924212 |
| `a2` | `HEX_SIZE*np.sqrt(3)` | `HEX_SIZE*sqr(3)` | 0.12125（= a/2） |
| `N` | `(y[1]+2)*2`（y[1]=13） | `n_layers`（默认 30） | 30 |
| `d0` | `8*HEX_SIZE*2*np.sqrt(3)` | `d0_layers*HEX_SIZE*2*sqr(3)`（默认 8） | 1.94（= 8a） |
| `r1 / r2` | `np.array([50.5,61.3])/1e3` | `r1_0=0.0505 / r2_0=0.0613` | 0.0505 / 0.0613 |

下发序列与参考**逐条对应**（顺序、操作数、命名、`theta=[0,0,90]`、`center=[x,y,'-h/2']`、
`mirror([1,0,0], copy=True, unite=True)`、`Cylinder + Square → subtract` 取半圆、
再 `subtract(裁剪体, 孔阵)` 取**孔阵负形**、`translate([0,'r1',0])`）：

```
hexagon(第 0 个孔)                                    # 第一象限
hexagon(第 i 个孔) + add('{name}-0', '{name}-{i}')    # i = 1..n-1
mirror('{name}-0', [0,0,0], [1,0,0], copy=True, unite=True)
create_cylinder(center=[0,0], r=['HEX_SIZE*N*cosd(30)*sqr(3)','0'], h=['-h/2','h/2'], name='{name}')
square(-half, half, -half, '-r1', '-h/2', 'h/2', name='{name}-cut')   # half = HEX_SIZE*(N+1)*cosd(30)*sqr(3)
subtract('{name}', '{name}-cut')
subtract('{name}', '{name}-0')                        # ⇒ 孔阵负形（介质柱），实体名仍是 `name`
translate('{name}', ['0','r1','0'])
translate('{name}', ['Rbig','0','0']) ; rotation('{name}', [0,0,60], repetition=5, copy=True, unite=False)
```

⚠️ 命名与参考**有意不同**：参考的最终实体叫 `GRIB-sub-180`，本库**就叫 `name`**
（= 模板的 `lens_name`），理由见 §2 ③。

## 2. 真机暴露并修掉的三个问题（这一轮真正的收获）

### ① `component` 漏传 ⇒ 整枚透镜建不出来（**blocker 级**）

`translate` / `rotation` 的封装默认组件是 `'component1'`，而实体在调用方给的
`component` 里（模板默认 `gridlens`）。首跑直接报：

```
(&H8000ffff) Shape does not exist: component1:grib-sub
(.Transform "Shape", "Translate")
```

**DXF 路线为什么没暴露**：那条路线里包络与透镜实体**本来就落在 `component1` 里**
（见 §4），所以漏传正好"凑对"。这说明——**同一个封装在两条路线上"恰好能用"不等于正确**。
修复：就地路线全程显式传 `component`；回归
`topo_modeler/tests/test_grin_lens_insitu.py::test_insitu_never_relies_on_default_component`
（同时反向钉住默认组件下调用的名字不变），真机侧
`_check_component()` 直接数历史里 `"<组件>:<名字>"` 的出现次数（`component1:` = 0）。

### ② `Ls` 在就地路线上是**死写入**

`Ls` 只被 **DXF 路线的楔形裁剪**用到。模板原先无条件登记 `Rbig` + `Ls`，
于是就地路线的真机跑被 `verify_model_parameter_usage.py` 抓到
`库下发参数死写入：['Ls']`。修复：`Ls` 改为**按路线登记**
（`Rbig` 两条路线都要 —— 就地路线用它把透镜平移到顶点）；回归
`topo_templates/tests/test_grin_lens_antenna.py::test_insitu_does_not_register_unused_ls`
与 `::test_generate_still_registers_ls`。

### ③ 最终透镜实体名必须就叫 `lens_name`（否则相位旋转打空）

第一版 `build_grin_lens_insitu()` 把最终实体命名为 `{name}-sub`（照参考的
`GRIB-sub-180`）。模板对外承诺"透镜叫 `lens_name`"，于是**功分器**那条
「相位副本」的 `rotation('lens_epc', ...)` 打到了不存在的实体上，CST 报：

```
(&H8000ffff) Shape does not exist: gridlens:lens_epc
(.Transform "Shape", "Rotate")
```

修复：**最终透镜实体就用 `name`**（`{name}-0` 是中间孔阵、`{name}-cut` 是方框裁剪体，
两者都会被布尔运算消耗掉）。这是与参考命名的**有意差异**（本库口径：模板参数怎么说
就怎么叫）。回归补在真机侧（`1分4+透镜(x) 相位旋转指向真实实体`）与就地测试里。

**同一个坑的另一半（接功分器时发现）**：DXF/generate 路线的实体**实际在 `component1`**
（旧脚本等价性，见 §5），而调用方按 `lens_component`（`gridlens`）寻址 ⇒ 同样报
`Shape does not exist: gridlens:lens_epc`。修法不是改路线的组件（那会破坏逐字节等价性），
而是让两个 builder **如实报告 `entity_component`**，模板按它寻址；回归
`test_builders_report_the_real_entity_component`。

### ④ `self_rotation` 的参数名没登记 ⇒ CST **挂死 30 分钟**（2026-09-18）

`lens_rotation`（参考的 `dphi`）实现成引用一个 CST **参数名**。真机脚本 C 段忘了
`app.para('dphi', 10)`，于是：

* CST 不报错，弹「请输入变量值」模态框把脚本挂住（实测 **30+ 分钟**）；
* `EnumWindows` **看不到那个框** —— `cst_dialog_guard.describe_dialogs()` 返回
  "没有可见的 CST 对话框"，守卫没救回来，只能强杀进程。

修法（两层）：脚本里登记参数；**库里**给 `build_grin_lens()` / `build_grin_lens_insitu()`
加「参数是否存在」前置拦截（探针 `guard.param_existed`），把 `self_rotation` 的参数名
与放置用的 `Rbig` 一起查，缺了就抛 `ValueError`。回归三条见 §3 表。

> 这是 P4/V6 `Rbig`/`Ls` 教训的加强版：**CST 缺参数的失败方式是"挂着"，而且这次连
> 对话框都看不见** ⇒ 只能**事先查参数表**，不能事后看窗口。

## 3. 离线证据（不需要 CST）

| 命令 | 结果 |
|---|---|
| `python -m pytest topo_modeler/tests/test_grin_lens_insitu.py -q` | **31 项通过**（含 3 条前置拦截回归） |
| `python -m pytest topo_templates/tests/test_grin_lens_antenna.py -q` | **32 项通过**（含 `lens_rotation`/`dphi` 四条） |
| `python -m pytest topo_modeler/tests/test_config.py -q` | **49 项通过**（含 `test_insitu_lens_is_configurable` 与配置一致性护栏） |
| `python -m pytest`（整仓） | **977 项通过**（本轮开始时 938；两轮共 +82） |

守住什么（摘）：

* 四个常数与参考**逐值相同**；孔集合 = N 层六边形网格的**第一象限**（N=30 ⇒ 721 个象限格点、1426 孔，`x==0` 上的 16 个镜像后会落回自身）；
* 半径两段式（`< d0` ⇒ 常量 `r1`；否则 `r1+(r2-r1)*(dist-d0)/(N*a2-d0)`）、按距离排序、渐变单调；
* 渐变区间为空（`N*a2 <= d0`）**明确报错**，不默默退化成"全是 r1"；
* 下发序列逐条对账（hexagon/add/mirror/cylinder/square/subtract/translate/rotation 的**条数、顺序、参数**）；
* 表达式里引用的 6 个参数（`HEX_SIZE / a2 / N / d0 / r1 / r2`）**在任何 `hexagon` 之前登记**（缺一个 CST 就弹「请输入变量值」模态框把脚本挂住）；
* 变换/布尔全部带正确 `component`（① 的回归）；
* 端到端模板：`lens_method='insitu'` 不要求 DXF、`lens_summary()` 离线可算且 `dxf=None`、`Ls` 不再登记（② 的回归）、天线几何与 `UnitAntenna` 逐值相同。

## 4. 真机证据（CST 2026，**只建模不求解**）

命令：`python scripts/verify_grin_lens_insitu_real.py`（默认 `N=10 / d0=3` ⇒ 91 象限孔 /
176 孔，分钟级完成；`--full` 跑参考规模 `N=30 / d0=8`）、
`python scripts/verify_grin_lens_insitu_real.py --layers 20 --d0-layers 8` 可自定规模。

**最终结果：`OK 36 / INFO 2 / WARN 2 / FAIL 0`（退出码 0）**。剩下的 2 条 WARN 是
「模板遗留参数值未变但被引用」（`D:\TPC_out\tmp.cst` 这个模板本身不干净，是既有现象，
不是本次引入），没有 FAIL。

| 观测 | 实测 |
|---|---|
| A 裸工程（干净模板 + 材料 + `a/h/Rbig`）直接调 `build_grin_lens_insitu()` | ✅ 未抛异常、**0 条 CST 消息** |
| A 下发条数 = 离线几何 | ✅ `Hexagon=91 / add=90 / mirror=1 / Cylinder=1 / Square=1 / subtract=2 / translate=2 / rotation=1`（**逐条对账**，caption 里带透镜自己的名字） |
| A 参数表 | ✅ `HEX_SIZE=0.0700037201… / a2=0.12125 / N=10 / d0=0.7275 / r1=0.0505 / r2=0.0613`，且 `N=d0` 与离线几何**逐值相同** |
| A 不落 DXF | ✅ 历史里没有任何 DXF 导入（这条路线与 DXF 两条入口的本质区别） |
| A 组件口径 | ✅ 指向 `grib:grib` 的指令 **370 条** / 误指 `component1` 的 **0 条** |
| A 参数闭合性（复用 `verify_model_parameter_usage.py`） | ✅ **库下发参数死写入 0** |
| B 端到端模板 `GRINLensAntenna(lens_method='insitu')`（小尺寸天线 + 就地环透镜） | ✅ 未抛异常、**0 条 CST 消息** |
| B 天线部分未受影响 | ✅ 历史里 `Waveguide` / `Port` 都在 |
| B 组件口径 | ✅ 指向 `gridlens:lens_epc` 的指令 **370 条** / 误指 `component1` 的 **0 条** |
| B 参数表 | ✅ 六个环透镜参数 + `Rbig=2.91`；**`Ls` 不在表里**（就地路线用不到 ⇒ 不登记，避免死写入） |
| B 参数闭合性 | ✅ **库下发参数死写入 0** |
| 收尾 | ✅ 无残留 DE（回到基线 `[]`） |

⚠️ 真机跑了**五轮**才对（每一轮都暴露一个离线测不到的问题）：

1. 第 1 次 **FAIL**：`Shape does not exist: component1:grib-sub` ⇒ §2 ①（`component` 漏传）；
2. 第 2 次 **建模 OK**，但 `verify_model_parameter_usage.py` 抓到 `Ls` 死写入 ⇒ §2 ②；
3. 第 3 次全部 OK，只剩**脚本自己**的计数 bug（`add` 把天线的 13 条也数了进去）；
   修好后用**同一份落盘历史**离线复核到逐条相符，第 4 次真机跑即 **OK / FAIL 0**；
4. 第 5 轮（接功分器时暴露）**FAIL**：`Shape does not exist: gridlens:lens_epc` ⇒
   §2 ③（最终实体名 `{name}-sub` 与模板承诺的 `lens_name` 不一致）；改成"最终实体就叫
   `name`"后重跑 **OK 36 / FAIL 0**。

> 这五轮的价值说明一件事：**"能下发"和"CST 接受"是两回事，而"CST 接受"和
> "名字/组件真的是调用方以为的那个"又是第三回事** —— 只有真机跑才能同时验证三件事。

## 5. **已知差异**：两条路线的透镜组件口径不同（有意保留）| 路线 | 孔阵列所在组件 | 最终透镜实体所在组件 | 原因 |
|---|---|---|---|
| `generate` / `dxf` | `lens_component`（= DXF 层名） | **`component1`** | 与被收编的旧脚本 `topo_modeler/lens_build.py` **逐字节一致**，且真机验过 —— `topo_modeler/tests/test_lens.py::test_cst_call_sequence_matches_original` 钉着这条 |
| `insitu` | `lens_component` | **`lens_component`** | 新代码，没有旧脚本要兼容；`component` 参数确实管住整枚透镜 |

⇒ `lens_component` 在 DXF 路线上只表示「DXF 层名 / 孔阵列组件」。这个差异由两侧测试
分别钉住（不是疏漏）；要统一必须**同时**改 `test_lens.py` 的逐字节基线与真机复验，
属于"要不要放弃旧脚本等价性"的决策，未擅自改。

## 6. 仍未覆盖

* **求解级**：完全没做（属 P4/V2、V7、V9，需先确认算例与开销）；
* **就地路线的孔数是"参考量级"**：`N=30 / d0=8 层` ⇒ 象限 721 孔 / 共 1426 孔
  ≈ 1455 条建模指令（比 DXF 路线 `nx=16,ratio=1` 的 181 孔重得多）。真机默认只跑
  `N=10 / d0=3`（91 象限孔 / 176 孔）以保证分钟级完成，要跑参考规模用 `--full`；
* **不是全参量化**：孔径渐变的公式里带**烘死的距离数字**（`(1.2345-d0)`），与参考
  notebook 一致 ⇒ 改 `lens_layers` / `lens_d0_layers` 必须整枚重建（孔集合由
  `grin_ring_holes()` 离线重算，不缓存）。这一点与 P4 §8.7 的"参数化"标准有差距，
  属于**跟着参考口径**的有意选择；
* **4 个 `功分器加天线\1分4` notebook 仍未覆盖**：它们的对应模板是 `PowerDivider`
  （本身不含透镜），要覆盖得把就地建环接到功分器上。

## 7. 复现命令

```text
python -m pytest topo_modeler/tests/test_grin_lens_insitu.py -q      # 离线 27 项
python -m pytest topo_templates/tests/test_grin_lens_antenna.py -q   # 离线 28 项
python scripts/verify_grin_lens_insitu_real.py                       # 真机（只建模，分钟级）
python scripts/verify_grin_lens_insitu_real.py --full                # 参考规模 N=30/d0=8（慢）
```

登记表复评：`python scripts/classify_notebook_migration.py --write`
⇒ `lens_in_situ` 不再是 GRIN 天线批次的缺口，`COVERED` 25 → 45。
