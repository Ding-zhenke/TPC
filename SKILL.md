---
description: TPC 库总入口 —— 读 TPC 源码前先读本文件。拓扑光子晶体 CST 自动化建模与排错：cst_solver 封装、mesh_grid.tri_grid（TopoPath 路径 DSL / 晶格）、topo_modeler 构建器。含「按需查阅地图」「报错定位表」「z 平面 / 布尔语义 / 阵列范围 三条硬约定」「已知库缺陷」「验收清单」，用于快速定位错误来源并按需只读 1~2 个文件，避免通读整包。
applyTo: "**/*.py"
---

# TPC 库使用与排错手册

> **AI 助手：读 TPC 库源码前先读本文件。** 第 0~2 节是省 token 的索引与硬约定：先把问题定位到 1~2 个文件，再只读那几个文件的相关函数。

## 0. 省 token 铁律

1. **禁止通读整包**（`os.walk` + 全读）。先在第 2 节查到目标文件，只读那个文件的相关函数。
2. **要接口签名时优先读 `cst_solver/setup.pyi`** —— 类型存根含全部方法签名，一屏读完。
3. 用 `grep`/`Select-String` 定位函数名，只读函数定义行 + docstring，不要整文件读。
4. 需要低成本总览时用 AST 只取名字（不读实现）：打印每个 `.py` 的文档首行 + `FunctionDef/ClassDef` 名。
5. 子包自带 SKILL.md，细节读它们：`./mesh_grid/tri_grid/SKILL.md`、`./mesh_grid/hex_grid/SKILL.md`。

## 1. 包结构（4 层）

```
D:\成电博士生涯\自动建模算法尝试\TPC\    ← 需 sys.path.append 本目录
├── cst_solver/       CST VBA 封装（Mixin 聚合，入口 setup；库开发见 .github/skills/cst-solver-dev/）
├── mesh_grid/        纯算法：tri_grid（三角晶格/路径 DSL）、hex_grid（六边形/DXF）
├── topo_modeler/     建模引擎：TopoModeler + builders/ 各部件构建器
└── templates/        端到端模板（⚠ 当前有签名 bug，见 §6）
```

```python
import sys; sys.path.append(r'D:\成电博士生涯\自动建模算法尝试\TPC')
from cst_solver import setup                                  # CST 工程控制
from mesh_grid.tri_grid import TopoPath                       # 路径 DSL + 晶格
from topo_modeler.builders import (build_vpc_regions, build_feed,
                                   build_waveguide, add_port_for_antenna)
```

## 2. 按需查阅地图（**照此表读文件，别通读**）

| 你要做什么 | 读这个文件 |
|---|---|
| 任何 `app.xxx()` 的签名 | `cst_solver/setup.pyi`（最快） |
| 开/关/保存工程、`app.cst_file` | `cst_solver/project.py`、`cst_solver/__init__.py` |
| 参数 `para/freq_limit` | `cst_solver/parameters.py` |
| 基础体 `square/cylinder/triangle/hexagon` | `cst_solver/modeling/primitives.py` |
| 曲线 `polyline/ellipse` | `cst_solver/modeling/curves.py` |
| **拉伸 `extrude`（z 平面问题见 §3.1）** | `cst_solver/modeling/curves_ops.py` |
| **布尔 `add/substract/intersect/insert`（语义见 §3.2）** | `cst_solver/modeling/booleans.py` |
| 变换 `translate/rotation/mirror` | `cst_solver/modeling/transforms.py` |
| `pick_face/pick_edge` | `cst_solver/modeling/picks.py` |
| 材料/组件 | `cst_solver/material/materials.py` |
| 端口 `add_port` | `cst_solver/simulation/ports.py` |
| 监视器 `define_monitor/monitor2d` | `cst_solver/simulation/monitors.py` |
| 求解器 `T_solver/run` | `cst_solver/simulation/solver.py` |
| 边界/背景 | `cst_solver/simulation/boundary.py` |
| 导入导出 DXF/STEP | `cst_solver/import_export/io.py` |
| 结果读取（S 参数/远场） | `cst_solver/_result_core.py`、`cst_solver/postprocessing/`、`read.py` |
| 路径 DSL、CST 表达式生成、阵列范围 | `mesh_grid/tri_grid/topo_path.py` |
| 晶格/坐标/可视化函数 | `mesh_grid/tri_grid/core.py` |
| 六边形透镜 / DXF | `mesh_grid/hex_grid/core.py` |
| 整体编排、智能推断 | `topo_modeler/modeler.py` |
| 光晶阵列生成（核心 25 行） | `topo_modeler/builders/crystal.py` |
| 探针几何（AB/BA/圆柱） | `topo_modeler/builders/feed.py` |
| 空心铜波导 | `topo_modeler/builders/waveguide.py` |
| 端口添加 | `topo_modeler/builders/port.py` |
| 求解器/监视器配置 | `topo_modeler/builders/solver.py` |
| VPC 区域 / 基板 | `topo_modeler/builders/vpc_region.py`、`substrate.py`（⚠ §6） |

## 3. 三条硬约定（不遵守必出错）

### 3.1 z 平面：拉伸方向由多边形绕向决定 ✅实测

CST `ExtrudeCurve` 沿多边形**法向**拉伸，法向由顶点绕向决定：

| 顶点绕向 | 拉伸方向 | 居中到 z=0 |
|---|---|---|
| 逆时针 CCW（有向面积 > 0） | +z（0 → h） | `translate -h/2` |
| 顺时针 CW（有向面积 < 0） | −z（0 → −h） | `translate +h/2` |

绕向不一致 ⇒ 两实体在 z 上差一个 `h` ⇒ **布尔相交得空集、实体"莫名消失"，且库不报错**。

```python
def signed_area(p):                    # >0 = CCW
    import numpy as np; p = np.asarray(p, float)
    return 0.5 * np.sum(p[:-1, 0] * p[1:, 1] - p[1:, 0] * p[:-1, 1])
assert signed_area(my_poly) > 0        # 手写多边形拉伸前先自检
```

- 库的 `triangle()`、AB/BA 探针都是 **CCW + 内部 -h/2**（放心用）
- 想彻底避开绕向问题：**用 `app.square()`（Brick）直接给 zmin/zmax** ← 裁剪框首选
- `translate` 的 z 参数写成字符串表达式，如 `'-h/2'`

### 3.2 布尔语义 ✅实测

| 调用 | 结果 |
|---|---|
| `Solid.Intersect "A","B"` | 交集**保留在 A**，B 被消耗 |
| `Solid.Add / Subtract "A","B"` | 结果在 A，**B 被删除** |
| `Solid.Insert "A","B"` | 把 B 嵌入 A，**B 仍可被其它布尔继续引用**（旧代码用它复制"裁剪工具"） |

即 `app.intersect('g1A', 'clip_A')` 之后 `g1A` 就是结果，`clip_A` 已不存在。

### 3.3 阵列范围：`get_array_range()` 只够细长直波导 ✅实测

`TopoPath.get_array_range()` 返回 `(xup, yup, ydn)`；**直线路径的 `yup/ydn` 只有 1~2**，
做菱形/宽板时阵列覆盖不到全宽 ⇒ 必须显式给范围。
注意 `build_topological_crystal()` **不接受** `xup/yup/ydn` 参数（内部自己调 `get_array_range()`）。

## 4. 报错定位表（症状 → 病因 → 动作）

| 症状 | 病因 | 动作 |
|---|---|---|
| `RuntimeError: Shape does not exist: component1:xxx` | 该实体此刻不存在：① 上一步布尔把它消耗了（§3.2）② 上一步相交得**空集**（§3.1 z 不共面）③ 命令在 CST 重建中被排队 | 查 §3.1；重操作**分单元**；下一条命令前 `model3d.Rebuild()` 同步 |
| 实体凭空消失、后续 `add` 报缺实体 | 同上②，最常见是 **CW 多边形 + `-h/2`** | 统一 CCW，或改用 Brick |
| `NameError: name 'x' is not defined` | ① 定义它的单元没跑 ② **旧 kernel 残留变量掩盖了 bug** | 重启 kernel → 全量顺序重跑；别信"上次跑通了" |
| `TypeError: build_vpc_regions() got an unexpected keyword argument 'topology'` | `templates/*.py` 传了函数不接受的参数（§6） | 不用 templates，直接调 builders |
| 改参数不生效 | `para()` 只 `StoreParameter`，需刷新 | `app.para(name, val, log_flag=1)` 或 `full_history_rebuild()` |
| 端口选到错误的面 | `pick_face` 面编号依赖具体几何 | 试 `'10'` / `'22'`，或先在 CST 里看面号 |
| 求解器 VBA 报错 | `builders/solver.py` 的 `configure_solver` 含存疑 VBA（`.ParallelizationThreads`、`.GPUAcceleration`） | 优先用旧 notebook 实测过的 `With Solver … End With` 整块 |
| `FileNotFoundError: CST project file not found` | 相对路径按**工作目录**解析 | 模板 `tmp.cst` 放 notebook 同目录 |
| `ImportError: cst` | CST python 库路径没配 | 改 `cst_solver/config.py` 的 `CST_INSTALL_PATH` |
| `AttributeError: … no attribute 'GetBoundingBox'` | `cst_file.modeler` 已废弃 | 改用 `cst_file.model3d` |
| 保存后模型里有垃圾实体 | 实验性命令写进了历史 | 关工程 → 从干净模板重开 → 重跑 → 重新保存（§5） |

### 4.1 唯一可靠的反馈通道：CST 自己的消息日志 ✅实测

TPC 库**不保证**把 CST 的错误抛成 Python 异常，所以每个重操作后**读 CST 日志**（只读、不污染历史）：

```python
def cst_log(tag=''):
    msgs = app.cst_file.get_messages()      # 读取后即清空
    print(f'[{tag}]', '无消息' if not msgs else msgs)

app.intersect(g1A, clip_A); cst_log('g1A ∩ clip_A')
app.cst_file.model3d.Rebuild()              # 阻塞式强制重放历史（大模型约数秒）← 最佳同步点
cst_log('完整重建后')
```

其它探测手段：
- `app.cst_file.model3d` 有 387 个方法，可 `dir()` 找（`Rebuild`、`StoreParameter`、`add_to_history` 等）
- 判断实体是否存在（`add_to_history` 会真校验）：`app.add(name, 'ZZZ_GHOST')`；
  报错里出现 `ZZZ_GHOST` ⇒ `name` 存在，出现 `name` ⇒ 它不存在
- 已保存的工程可直接读磁盘（§5 第 4 条）

## 5. 验收清单（每次交付建模 notebook 必做）

1. 每个重操作后 `cst_log()` 无消息；`model3d.Rebuild()` 后无消息
2. **重启 kernel → 从第一个代码单元顺序全量重跑**（唯一可信的验证）
3. notebook 无 error 输出（用 json 扫 `output_type == 'error'`）
4. 保存后核验磁盘产物（**不用连 CST**）：
   - `<工程名>/Model/3D/ModelHistory.json` → 只应出现本项目实体名，grep 模板残留（`vpca`/`feed1`/`epc1`…）
   - `<工程名>/Model/Parameters.json` → 参数是否按预期写入，**连表达式一起看**：CST 几何用到的
     每个尺寸都应在这里查到 `name`/`expr`/`descr`，而不是散落在 notebook 里的浮点数
5. 编辑 notebook 后**回读文件核对**：工具报"编辑成功" ≠ 文件已更新（编辑器缓冲区可能覆盖）；
   改 notebook **优先整格重写**（`edit_notebook_file`），多段替换容易把单元改乱
6. **CST 建模调用里不得出现硬编码数值**：`app.ellipse(2.0612, 1.5751, [1.3296,'0'])` ✗
   → `app.ellipse('ec_a', 'ec_b', ['ec_c','0'])` ✓（详见文末「挖孔板 / 椭圆透镜」一节）

## 6. 已知库缺陷（可直接改库）

| 位置 | 缺陷 | 影响 | 建议 |
|---|---|---|---|
| `builders/vpc_region.py` `build_vpc_regions(side='lower')` | 生成**顺时针**多边形，却用内部 `translate -h/2` | 下半区与晶体差一个 h → 相交空集 | 多边形统一 CCW，或按绕向取 `±h/2`，或改 Brick |
| `builders/substrate.py` `build_substrate` | 同上（带状多边形为 CW） | 基板错一个 h 的平面 | 同上 |
| `templates/straight_waveguide.py` | 调 `build_vpc_regions(..., topology=...)`、`build_topological_crystal(..., xup/yup/ydn=...)`，两函数都不接受 | 模板直接 TypeError | 去掉多余参数，或给构建器加形参 |
| `templates/unit_antenna.py` | 同 `topology=` 问题 | 同 | 同 |
| `builders/crystal.py` | 阵列范围只能从 `path.get_array_range()` 推断 | 宽板覆盖不全 | 加 `xup/yup/ydn` 形参 |

## 7. 最小可用配方（实测写法）

```python
import sys, numpy as np
sys.path.append(r'D:\成电博士生涯\自动建模算法尝试\TPC')
from cst_solver import setup
from mesh_grid.tri_grid import TopoPath
from topo_modeler.builders import build_feed, build_waveguide, add_port_for_antenna

a, h, lx1 = 0.2425, 0.25, 9                  # 晶格常数 / 板厚 / 路径周期数
e1, e2 = a / 2, a * np.sqrt(3) / 2           # x = c*a + r*a/2, y = r*a*√3/2, +c 即 +X
d_xmax, d_ymax = lx1 * a, lx1 * e2           # 菱形板：长对角线 / 半宽

path = TopoPath.builder(a, name='p').start(0, 0).move(lx1, 'c').build()
path.preview()                                # 预览不需要 CST

try: app.close()                              # 重复运行先关旧环境
except Exception: pass
app = setup('tmp.cst')                        # 相对工作目录，模板必须存在

app.para('a', a); app.para('h', h)
app.para('e1', 'a/2'); app.para('e2', 'a/2*sqr(3)')
app.para('l1', '0.65*a'); app.para('l2', '0.35*a')      # BA：l1 大孔 / l2 小孔
app.para('lx1', lx1)
path.auto_define_cst_params(app, prefix='p')            # 生成 p1x,p1y,p2x,p2y
app.new_material('Copper (annealed)'); app.new_material('Silicon (lossy)')
app.para('fmin', '300'); app.para('fmax', '380'); app.freq_limit('fmin', 'fmax')

# 裁剪框用 Brick（显式 z，最稳）；菱形板用 CCW 顶点 + extrude 'h' + translate '-h/2'
app.square('0', 'd_xmax', '0', 'd_ymax', '-h/2', 'h/2',
           'clip_A', 'component1', 'Silicon (lossy)')

# 光晶阵列：triangle() 造超元胞 → rotation 120°×2 → translate 阵列（见 crystal.py），
# 手动版必须显式给 xup/yup/ydn
feed = build_feed(app, feed_type='ba_tapered', name='feed2')
wg = build_waveguide(app, name='wg1', x_min='-lf5-lf6-lf4', x_max='-lf4', y_center='0')
add_port_for_antenna(app, waveguide_name=wg, port_face='10')

app.add('g1A', feed)
app.define_monitor('E', np.arange(300, 322, 2))
app.cst_file.model3d.Rebuild()                          # 同步 + 自检
app.cst_file.save(r'<绝对路径>\out.cst', include_results=False, allow_overwrite=True)
```

## 8. 坐标与方向速查

- 三角晶格：`x = c*a + r*(a/2)`，`y = r*(a/2)*√3`；`e1 = a/2`，`e2 = a*√3/2`
- 6 个主方向（逆时针）：0°`(0,+1)`、60°`(+1,0)`、120°`(+1,-1)`、180°`(0,-1)`、240°`(-1,0)`、300°`(-1,+1)`
- `+c` = +X；`TopoPath.move(n, 'c')` 即沿 +X 走 n 个周期
- `triangle(a, h, center, theta, name, curve)`：`theta=[0,0,0]` 朝上、`[0,0,180]` 朝下
- 晶格菱形（斜边严格 ±60°，长对角线 = `lx1*a`）顶点（**此顺序即 CCW**）：
  `(0,0) → (lx1*a/2, -lx1*e2) → (lx1*a, 0) → (lx1*a/2, lx1*e2) → 闭合`

---

## 9. 读结果 / 后处理（API 索引）

`result` 类独立于 `setup`，用于读取已算完的工程：

| 方法 | 用途 |
|---|---|
| `result(工程路径)` | 打开结果 |
| `get_available_results()` | 列出可用结果树（**先看它**，再按 `tree_path` 读具体项） |
| `get_tree_items()` | 结果树条目 |
| `read_s_parameter(s_param, run_id)` | 读 S 参数，如 `'S1,1'` |
| `read_1D / read_2d / read_3d(tree_path, run_id)` | 读 1D/2D/3D 结果 |
| `get_run_ids(treepath, skip_nonparametric)`、`get_all_run_ids(max_mesh_passes_only)` | 取 run id |

```python
from cst_solver import result
res = result(r'<工程绝对路径>')
print(res.get_available_results()[:5])       # 先看树，再读具体项
s11 = res.read_s_parameter('S1,1')
```

配套模块：`read.py`（`read_s2p_groups` 批量读 s2p）、`postprocessing/proc.py`、`farfield.py`、`plot.py`、`result_export.py`。

> 以上为**签名索引**（取自 `cst_solver/_result_core.py`），返回结构待首次实测后补成完整配方。

---

## 库开发 / 维护视角 → 已拆成独立 skill

给 `cst_solver` **新增封装、修库内部缺陷、改 API 存根与文档**：
**`./.github/skills/cst-solver-dev/SKILL.md`**
（把 TPC 作为 VS Code 工作区打开时会自动加载，也可用 `/cst-solver-dev` 调用。）

本文件只负责「用库建模型 + 排错」。

---

## 面拾取：不要再硬编码面号（2026-09 新增）

CST 的面编号（`'10'` / `'22'` / `'9'` …）随几何与生成顺序变化，**布尔/扭转/阵列之后不可复用**。
库已提供按**坐标点**拾取的接口（`cst_solver/modeling/picks.py`）：

| 方法 | 说明 |
|---|---|
| `pick_face_at(name, x, y, z)` | 按坐标点拾取面（下发 `Pick.PickFaceFromPoint`），点需落在目标面上 |
| `pick_face_auto(name, points=[…], candidates=[…])` | 先按点逐个试、失败再按编号试；以 `get_messages()` 是否报错判定，返回 `('point',(x,y,z))` / `('id',fid)` / `None`，失败的点会自动 `pick_clear()` |

用法（扭波导 / 加端口这类面号会变的场景）：

```python
app.pick_clear()
app.pick_face_auto('wg1', points=[(1.13, 0.2878, 0)], candidates=('10',))   # 径向内端面（环壁中点）
app.set_edge('x_fold', '0', '1', 'x_fold', '0', '-1')                      # 定扭转轴
app.rotation_face('wg1_bend', 30, material='Copper (annealed)')            # 扭转该面
app.pick_clear()
app.pick_face_auto('wg1_bend', points=[(0.9861, 0.2493, 0)], candidates=('9',))   # 扭转后的面
app.extrude_face('wg1_sec', 'Ls', material='Copper (annealed)')            # 延长一段
```

> ⚠ `rotation_face` / `extrude_face` 的默认材料是 `Vacuum` / `PEC`，**必须显式传**目标材料（如铜）。
> ⚠ 每次拾取前先 `pick_clear()`，避免上一次的选取被后续操作带上。

---

## 挖孔板 / 椭圆透镜（GRIN 孔阵列）：2026-09 新增

用 `mesh_grid.hex_grid`（`HexGridVisualizer` + `create_staggered_grid` + `create_hex_polygon` + `save_to_dxf`）
做"六边形孔阵列 + 椭圆包络 − 孔阵列"这类渐变折射率（GRIN）透镜时，按下面六条做。

### 1. 孔网格的列范围必须**覆盖整个图形**（最容易翻车）
`create_staggered_grid(col_range, row_range)` 的 `(col, row)` 是**索引不是坐标**：
pointy 时 `x = a2*(col + (row%2)/2)`、`y = 1.5*hex_size*row`（`a2 = hex_size*sqr(3)`）。

图形关于原点不对称时（典型：椭圆**近焦点放在原点** ⇒ 椭圆跨 `x ∈ [ec_c-ec_a, ec_c+ec_a]`），
列范围**必须按图形的真实 x 范围算**，不能用对称的 `(-Nx, +Nx)`：

```python
col_min = int(np.floor((ec_c - ec_a) / a2)) - 1     # ← 不是 -Nx
col_max = int(np.ceil((ec_c + ec_a) / a2)) + 1      # ← 不是 +Nx
```

> 实测：`ec_a = 2.061、ec_c = 1.330` 时用 `±Nx = ±17` ⇒ 网格只到 `x = 2.06`，而椭圆要伸到 `3.39`
> ⇒ **外侧 1.33 mm（26% 面积）整片无孔 = 实心硅**（用户一眼就看出"有一块没挖空"）。

### 2. 边界那一圈孔要用"容差"收进来
只用标准椭圆判据 `((x-ec_c)/ec_a)^2 + (y/ec_b)^2 <= 1` 时，图形最扁的两头会留一圈没孔的实心边
（椭圆短半轴恰好落在某行孔心上时，那一行孔心全在界外 ⇒ 整行被丢掉）。
改用**到两焦点距离之和 ≤ 2a·tol**，`tol` 取 1.03~1.1：

```python
d1 = np.sqrt(x**2 + y**2); d2 = np.sqrt((x - 2*ec_c)**2 + y**2)
keep = (d1 + d2) <= 2*ec_a*tol          # 参考案例 Ant1_grid_BA_240D_epc_epc 用 1.1
```

界外的孔在 CST 里只会把图形边缘啃掉很小的缺口；**不这样做就一定留实心边**。

### 3. 验收：孔阵覆盖率（一条硬指标）
图形内任一点到**最近孔心**的最远距离 `d_max`；完好三角格子里最坏点（三角形重心）距离 = `格距/√3`。
`d_max ≈ 1.00×` 才算铺满。

```python
dmax = max( 图形内采样点到最近孔心的距离 )        # 与 格距/sqr(3) 比
# 实测：修复前 1.269 mm（18.1×，椭圆末端整片无孔）；修复后 0.0699 mm（1.00×）
```

> 采样图形内点时，楔形/被剪区域的角度判据要写 `np.mod(np.arctan2(y, x), 2*np.pi)`；
> 直接用 `atan2` 的原始负角区间会把"下半楔形"误判成图形内部（会让剪枝后的指标虚高）。

### 4. 尺寸参数一律用晶格常数 a 表出（含椭圆）
参数表里把"个数"单列出来，改 `a` 就能整体缩放，也便于核对：

```python
app.para('nrin',  '3*nsm/4',  expression='挖孔内切半径 = nrin 个晶格常数')
app.para('nRbig', 'nrin+lx1', expression='大六边形边长 = nRbig 个晶格常数（=17）')
app.para('rin',   'nrin*a');  app.para('Rbig', 'nRbig*a');  app.para('Ls', '2.2*nRbig*a')
```

实测（`a = 0.2425、nsm = 12、lx1 = 8`）：`nrin = 9`、`nRbig = 17`、`rin = 9a = 2.1825`、
**大六边形边长 = 17a = 4.1225**。改成表达式后 CST 求值结果与写死数值完全一致。

### 5. ★ 椭圆的建模：长短轴与中心**必须用 CST 变量**
`app.ellipse()` 的半径与中心都接受**参数名/表达式字符串**。照参考案例
`Ant1_grid_BA_240D_epc_epc.ipynb`（其 cell 8 / cell 10）的写法：

```python
app.para('ec_a', 'Nx*a2',              expression='椭圆长半轴')
app.para('ec_b', 'Ny*a2*sind(60)',     expression='椭圆短半轴')
app.para('ec_c', 'sqr(ec_a^2-ec_b^2)', expression='焦距：椭圆中心在 (ec_c,0)，近焦点在原点')
app.ellipse('ec_a', 'ec_b', ['ec_c', '0'], 'epc1')      # ← 不要写 2.0612 / 1.5751 / 1.3296
# 等价写法（参考案例用的）：app.ellipse('ec_a','ec_b',[0,0],'epc1') → translate('epc1',['ec_c','0','0'])
```

> ⚠ 把 Python 里算好的浮点数传给 `ellipse()`/`translate()` ⇒ 模型里就固化成数值了，
> 参数表里既看不到来源、也没法靠改 `a` 缩放。

### 6. GRIN 透镜建模配方（DXF → CST）
```python
app.dxf_import(dxf, add='True', component='gridlens', height='h')      # 孔阵列（实体名固定 import_1）
app.ellipse('ec_a', 'ec_b', ['ec_c', '0'], 'lens_epc')                 # 椭圆包络（变量！）
app.extrude('curve1:lens_epc', 'lens_epc', 'h', material='Silicon (lossy)', log_flag=1)
app.substract('lens_epc', 'import_1', component2='gridlens')           # 椭圆 − 孔阵列 = GRIN 透镜
```

---

## 10. 大几何「建一次 + 子工程引用」架构（2026-09 实测，ANT6_C6_hexring）

**问题**：GRIN 透镜的孔阵列（DXF 里 2215 条多段线）每次 run 都要重建 ⇒ 单次 ≈ 300 s。

**实测数据（每次都在 CST 里真跑出来的）**

| 步骤 | 耗时 | 说明 |
|---|---|---|
| `dxf_import` 2215 条多段线 | **165–185 s** | ≈75 ms/条；与模型里已有多少实体无关 |
| y 镜像复制（2215 → 4351 孔） | 3 s | |
| 椭圆 − 孔阵列（布尔减） | **73–95 s** | |
| 楔形裁剪 / 平移 / 旋转 ×6 | 7.7 / 1.8 / 15.0 s | `rotation(..., unite=False)`：**不要**做布尔并（6×4351 壳做 union 会卡 >19 min） |
| 铜基板全流程（板+晶体+6 探针+6 铜管+6 端口） | **≈33 s** | 与透镜并行跑 |

⇒ 透镜 ≈ 300 s、基板 ≈ 33 s ⇒ **并行后可重叠**；透镜不变时整个 run ≈ 60 s。

**落地做法（子工程引用，CST 原生机制）**

```
ANT6_C6_tmpl.cst        干净模板（参考模型清空全部变量后的副本，只清一次，之后每轮 2 s 复制）
ANT6_C6_base.cst        基板工作工程（每轮复制；透镜稍后用子工程引进来）
ANT6_C6_lens.cst        透镜工程（只含透镜）
ANT6_C6_lens_export.sab 子工程几何（SAT.WriteAll 导出）
lens_build_standalone.py + lens_build.py   透镜构建（可独立 / 并行运行）
lens_params.json        notebook → 子进程的“本次意图参数 + CST 参数表”
```

单元顺序（关键）：`准备(判缓存+复制模板)` → `打开基板工程` → **`并行 subprocess.Popen(透镜脚本)`**
→ 基板建模（板/晶体/探针/铜管/端口） → **`import_subproject(.sab, .cst, scale_factor=…)`** → 监视器/求解器 → 保存。

**库接口**：`app.import_subproject(filename, subproject_name, scale_factor=...)`
= CST VBA 的 `StartSubProject … EndSubProject`（**链接式**子工程，会连带子工程的参数/材料）。
导出侧用 `SAT.Reset/FileName/SaveVersion/WriteAll`（`Write` 需要参数：`.Write("comp:shape")`）。

### ⚠ 四条踩过的坑（都是实测报错）

1. **两个工程的参数表必须完全一致**。透镜脚本里会出现 `translate(..., 'Rbig')` 这类
   基板工程才有的变量；子工程只登自己的 17 个参数时，CST 直接报
   `RuntimeError: Unable to evaluate expression: "Rbig"`。
   ⇒ **一张表、一个来源**：notebook 第 2.5 节定义 `CST_PARAMS`（40 项，= 原来单工程版的集合），
   notebook 第 4 节登记它，`lens_params.json` 里带 `ctsparams` 交给 `lens_build_standalone.py` 也登记它。
2. **`exec(open(...).read(), globals())` 共享命名空间**：被 exec 的透镜代码里有 `_t`（numpy 数组）、
   `_t0`、`_dt_*` ⇒ 驱动脚本里同名的计时变量会被覆盖，日志 `f'{t:.1f}'` 报
   `TypeError: unsupported format string passed to numpy.ndarray.__format__`，
   **后续的导出与保存全部被跳过**（白跑 300 s）。⇒ 驱动脚本变量加前缀，并且**几何建完先 `save()` 一次**。
3. **未裁剪的原始孔阵列不能早于端口拾取存在**（CST 报 `The picked port area is empty`）；
   成品透镜在六边形板之外，安全 ⇒ 缓存/引用进来的必须是成品透镜。
4. **子进程崩溃后 CST 会话不退出**，会一直占着 `.cst`，导致下一轮复制/删除工程失败
   ⇒ 重跑前 `Get-Process 'CST DESIGN ENVIRONMENT*' | Stop-Process`（只杀本次的）。

### 缓存有效性判定（毫秒级，不启动 CST）

读 `<透镜工程>/Model/Parameters.json`（字段 `name`/`expr`/`value`/`descr`），比对
`a, h, nsm, lx1, ratio, Nx, Ny, r1, r2`（含 `nsm/lx1`：透镜裁剪板 `Ls = 2.2*(nrin+lx1)*a` 由它们决定）
+ 检查 `.sab` 是否存在；一致就**跳过重建**，只 `import_subproject`。
app.substract('lens_epc', 'lens_hex_cut')                              # 只剪掉与其它实体重叠的部分
# ↑ 该裁剪体 = 目标实体的**内角楔形**（六边形顶点内角 120° ⇒ 张开 120°~240° 的楔形）
app.translate('lens_epc', ['0', '0', '-h/2'])                          # z 居中（与板共面）
app.translate('lens_epc', ['Rbig', '0', '0'])                          # 局部原点（近焦点）→ 目标位置
app.rotation('lens_epc', [0, 0, 60], repetition=5, copy=True, unite=True)   # 6 重对称复制
```

> - 要求"**只剪重叠、不重叠的全留**"时，必须用目标实体的内角楔形去 `substract`，
>   不能用"切掉内半边"的做法。
> - 孔阵列 DXF 用 `save_to_dxf()` 生成（内部 `unary_union`，孔不重叠时输出 MultiPolygon）。
> - 本模型实测：`ec_a = 2.0613、ec_b = 1.5751、ec_c = 1.3296`，871 个孔，覆盖率 1.00×。

### 7. DXF 只写一半，另一半在 CST 里镜像复制（导入提速）
**CST 的 DXF 导入耗时基本正比于多边形数量** —— 直接用阵列的对称性砍一半最省事。
本模型的孔阵列在 **y → −y** 下严格不变（椭圆中心在 `(ec_c,0)` 故对称轴是 y=0；
网格行 `y = k·行距` 正负成对、同一对行的 x 位置相同；孔半径只依赖 `y²`）：

```python
# 9b-①：只把上半平面写进 DXF
_upper = _yp >= 0
save_to_dxf([create_hex_polygon(center=(float(x), float(y)), cell_width=float(r))
             for x, y, r in zip(_xp[_upper], _yp[_upper], _ri[_upper])],
            lens_dxf, layer_name='gridlens')
```
```python
# 9b-②：导入后立刻镜像补齐
app.dxf_import(lens_dxf, add='True', component='gridlens', height='h')
app.mirror('import_1', [0, 0, 0], [0, 1, 0], component='gridlens', copy=True, unite=True)
```

实测：**871 → 453 个多边形，DXF 581 KB → 300 KB，导入时间约减半**，几何完全等价。

> - 参考案例 `Ant1_grid_BA_240D_epc_epc` 用的是**四分之一**（只写 `x≥0 & y≥0`，再先后绕 y、x
>   镜像两次）。那条路只在"网格关于 x=0 也对称"时才严格成立 —— 本例椭圆中心在 `(ec_c,0)`、
>   网格关于 y=0 对称但**不**关于 x=0 对称（列范围不对称），所以只能砍一半。
> - 用镜像前**必须先证明**对称性，并做一次 Python 自查（应 ≈ 0）：
>   ```python
>   d = unary_union([half_u, scale(half_u, yfact=-1, origin=(0, 0))]).symmetric_difference(full_u).area
>   ```
>   （`shapely.affinity.scale(geom, yfact=-1)` 即关于 y=0 镜像）
> - 镜像平面上的孔（`y=0` 那一行）会**自己镜像自己** ⇒ 必须 `copy=True, unite=True`，
>   否则会留下重复实体。
> - 镜像出来的孔若落到图形之外（例如绕 x=0 镜像后跑到椭圆外面）没有危害 —— 没材料可切。

### 8. 导入提速 / 画布 / 坐标范围（2026-09 补，都实测过）
**CST 的 DXF 导入耗时 ∝ 多段线数量**，不是文件大小。库的 `dxf_import`（`cst_solver/import_export/io.py`）
下发的是：

```
.AsCurves "False"  .HealSelfIntersections "False"  .PreserveHoles "True"  .CloseShapes "True"
.SetSimplifyActive "False"   .ModelTolerance "0.0001"
```

`.AsCurves "False"` ⇒ **CST 为每条多段线单独建一个实体**，所以：

| 手段 | 效果 | 备注 |
|---|---|---|
| 对称性减半（上面第 7 条） | **×0.5**（多段线数） | 孔少时很赚；耗时是**超线性**的（见 §9） |
| 加粗孔网格 `ratio`（格距 = a/ratio） | **×4**（ratio 2→1） | 会改变 GRIN 的采样密度/等效折射率，属设计取舍 |
| 坐标位数 `precision` | 文件 −21%（6→2 位） | 实测 2215 条：6/5/4/3/2 位 → 1397/1328/1252/1175/1098 KB，对导入帮助有限 |
| `.SetSimplifyActive "True"` | 只对**圆弧**有效 | 六边形只有 6 个顶点，简化无意义 |

> 结论：**优先砍条数**（对称性 → 网格粗细），`precision` 顺手设 3 位（1 µm）即可，不必纠结。

**画布**：`HexGridVisualizer.__init__` 里有一句 `self.fig, self.ax = plt.subplots(figsize=(14, 12))`
—— 它自己建了一张空画布。只用它的 `hex_lib` 时，**用完立刻 `plt.close(_vis.fig)`**，
否则 notebook 单元末尾会先冒出一张空白图，然后才是自己的示意图。

**预览坐标范围**：不要写死比例系数。椭圆右端是 `ec_c+ec_a`（近焦点在原点、中心在 ec_c），
写死 `2·ec_c + 0.3·ec_a` 在离心率 `e < 0.7` 时会被切掉（Nx/Ny 一大就中招）。
按实际几何取：`xlim = [min(ec_c−ec_a, 孔心 xmin)−余量, max(ec_c+ec_a, 孔心 xmax)+余量]`。

**GRIN 透镜只能做 y 镜像（不能做 1/4 对称）**：孔半径沿轴向单调变化（近焦点 r1 → 远焦点 r2），
绕椭圆中心 x 镜像会把远端的半径搬到近端 ⇒ 几何错了。

### 9. CST 侧「布尔/复制」的两个耗时坑（2026-09 实测：Nx/Ny = 38/34，单透镜孔 4351 个）

同一台机、CST 2026，一次完整建模的分步实测：

| 步骤 | 耗时 | 结论 |
|---|---|---|
| `dxf_import` 2215 条多段线 | **183.9 s** | 随多段线数量**超线性**增长（不是线性、更不是文件大小） |
| `mirror` 孔阵列（`unite=True`） | 3.6 s | 便宜 |
| `substract(椭圆, 孔阵列)`，4351 个工具体 | 100.1 s | ≈ 23 ms / 工具体 |
| `rotation(repetition=5, copy=True, **unite=True**)` | **> 19 min 卡死** | ✗ 千万别这样写 |
| `rotation(..., unite=False)` | 秒级 | ✓ 6 个独立实体，网格/求解等价 |

**坑 A：`rotation(..., unite=True)` 会卡死。**
把「已挖几千个孔」的实体旋转复制 5 份再 `unite`，CST 要并 6×4351 个壳 ⇒ 实测 19 min 未结束。
6 个互不接触的独立实体对 CST 网格/求解**完全等价** ⇒ **一律 `unite=False`**。
推广：任何「复制 N 份再合并」的写法，N 大时必须先问自己**是否真的需要 unite**。

**坑 B：布尔减的耗时 ∝ 工具体个数，与被减实体的大小关系不大。**
⇒ **壳少的操作放前面、壳多的放最后**：光板只有 1 个壳时先做楔形 / 半空间裁剪（几乎免费），
再把孔阵列用对称性砍半后一次减掉（2215 而不是 4351），镜像合并作为最后一步。
（若要把「半边孔」镜像成整体，注意**不能**镜像已减孔的透镜再 unite ——
`(E−H₁)∪(E−H₂) = E−(H₁∩H₂)`，会把孔**填回来**；必须先把实体沿 y=0 切开成互补两半。）

**排除法结论**：`precision` 6→2 只让文件小 21%，对导入耗时几乎无影响 ⇒ 慢的不是精度，是**实体条数**。
想根治只能减少孔数：抬高 `ratio`（格距 ×k ⇒ 孔数 ÷k²，要接受 GRIN 采样变粗）。

---

### 11. 端口三件事：面号拾取 / 端口旋转 / 用「复制旋转」补齐对称端口（2026-09 实测）

**① 拾取端口面用「面号」，且面号要在「轴向状态」下确认。**
`build_waveguide`（外方体 − 内方体）的**径向内端面 = 面号 `'10'`**（用 anchorpoints 里端口位置
正好落在 `wg_in` 反证过）。转 / 扭 / 镜像之后新生成的面，面号要**在 CST 里现查**。
库里有现成封装：`topo_modeler.builders.add_waveguide_port(app, solid, 端口号, 面号)`
= `pick_face` + `add_port`。

**② `rotation()` 原本转不了端口 —— 已补 `object='Shape'|'Port'`（与 `mirror()` 对称）。**
`Transform "Shape","Rotate"` 只作用于实体，端口不会跟着走（曾出现 6 个端口全堆在 0°）。
现在可直接：

```python
app.rotation('Port 2', [0, 0, 180], object='Port', auto_destination='False')
app.rotate_port(2, [0, 0, 180])                 # 端口 2 转 180°
app.rotate_port(2, [0, 0, 180], copy=True)      # 复制并旋转 ⇒ 新增一个端口
```

要点：端口名**不带组件前缀**（写 `Name "Port 2"`，不是 `"component1:Port 2"`）；
`.AutoDestination` 要给 `'False'`；默认参数保持旧行为（实体旋转的 VBA 一字未变，向后兼容）。

**③ 用「复制旋转 180°」一次补齐对称臂的端口 + 控制编号顺序。**
4 条臂由镜像得到、关于原点成对（60↔240、120↔300 相差 180°）⇒
**只需在其中 2 条臂的端面上各加一个端口，再 `rotate_port(..., copy=True)` 转 180°**，
副本自动落到对径两臂上，且法向也正好翻到正确方向（300°→120°、240°→60°）。

**编号顺序**：副本拿的是「下一个空号」⇒ 想让端口号按顺时针
`1=0°, 2=300°, 3=240°, 4=180°, 5=120°, 6=60°`，建端口的顺序就必须是
`0° → 斜臂 300° → 斜臂 240° → 180° → 最后才复制旋转`。

**④ 扭波导（把端口面法向扭到坐标轴）的稳定做法 —— 避开未知面号：**
`pick_face(端口面号)` → `set_edge(外侧壁竖边)` → `rotation_face(β)` 扫出缺角楔形 →
**另建一段长 L 的直管、绕同一条铰边转同一个 β**（它的端面正好是楔形的斜端面，面面贴合）→ `add` 拼合。
比「拉伸楔形的斜端面」省一步：**不需要知道楔形实体的面号**。
铰边坐标必须用**本模型**的参数表达式（沿用别的脚本的变量名会报
`Invalid coordinate setting, please specify a number`）。
只需扭 1 条 + `mirror` 两次即得 4 条对称斜臂；铰边要在「扭转朝向那一侧」的外侧壁上，
否则扭出的段会埋进管腔（反了就把铰边符号与 β 一起取反）。

**⑤ 顺带：`import_subproject(filename, subproject_name)` 两个路径都必须传绝对路径。**
CST 用**它自己的**工作目录解析相对路径 ⇒ 传相对名会报 `Unable to read SAB file`
（文件本身没问题：`.sab` 头 `ACIS BinaryFile … ACIS 35.0`、尾 `End-of-ACIS-data`）。

