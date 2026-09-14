# mesh_grid —— 晶格/网格算法层

`mesh_grid` 是 TPC 的**纯计算底座**：它只做晶格数学 —— 三角晶格与六边形晶格的网格生成、`(r, c) / (q, r, s) ↔ (x, y)` 坐标换算、几何与空间筛选、matplotlib 预览、DXF 导出，以及把「一条晶格路径」升格为唯一数据源的声明式路径 DSL（`TopoPath`，阶段 1 交付物）。它**从不 import CST**：既不需要 `cst` 模块，也不持有 `setup` 对象；`TopoPath` 只是在需要时把晶格坐标**编译成 CST 能接受的表达式字符串**（`'x1*a'`、`'y1*a/2*sqr(3)'`），这些字符串由上层（`topo_modeler` / `templates`）负责下发。因此它可以脱离 CST 单独安装、单独测试、单独画图。

**元信息**

| 项 | 内容 |
|---|---|
| 职责 | 三角晶格 / 六边形晶格的网格生成、坐标换算、空间分析与筛选、可视化、DXF 导出、路径 DSL（`TopoPath`） |
| 需要 CST | ❌ **完全不需要**。`import mesh_grid` 不会把 `cst` 拉进 `sys.modules`（实测为 `False`）；它只产出 CST 表达式**字符串**，不做任何下发 |
| 入口 | `from mesh_grid.tri_grid import TopoPath`（路径 DSL / 坐标统一层）<br>`from mesh_grid.hex_grid import HexLib, HexGridVisualizer`（六边形晶格）<br>子包 `__init__.py` 的 `__all__` 决定公开面 |
| 依赖 | 必需：`numpy`、`matplotlib`；进度条：`tqdm`。`mesh_grid/hex_grid/core.py` 在**模块顶层**就 `import ezdxf` 与 `from shapely...`，而 `mesh_grid/__init__.py` 会自动导入两个子包 —— 所以导入 `mesh_grid` 需要先 `pip install -e ".[geometry]"`（或 `.[all]`，即 `ezdxf>=1.0` + `shapely>=2.0`） |
| 被谁依赖 | `templates/`（`straight_waveguide.py`、`unit_antenna.py` 用 `TopoPath` 造路径）、`tpc_toolkit/`（`ga_optimizer.py`、`effective_medium.py` 用 hex_grid 工具）、`topo_modeler/builders/`（`substrate.py` / `vpc_region.py` / `crystal.py` 的 `path` 参数就是 `TopoPath` 实例）、`tests/test_grid_opt.py` |
| 源码位置 | `mesh_grid/__init__.py`、`mesh_grid/tri_grid/core.py`、`mesh_grid/tri_grid/topo_path.py`、`mesh_grid/hex_grid/core.py`、各自 README |
| 公开 API 规模 | **23 个模块级函数 + 4 个类 + 60 个公开方法**（`tri_grid` 19 个函数 + `hex_grid` 4 个函数；方法分布：`HexLib` 25、`TopoPath` 19、`HexGridVisualizer` 10、`TopoPathBuilder` 6）。口径 = `python scripts/_api_stats.py`（AST 扫描，跳过 `tests/` 与下划线开头符号） |
| 测试 | 全仓库唯一的单测套件：`mesh_grid/tri_grid/tests/test_topo_path.py`（16 项），运行 `python -m pytest mesh_grid -q` |

> 统计口径补注：`tri_grid` 的 19 个模块级函数中，17 个是 `README.md` / 技能文档里列出的经典函数，另 2 个是后来加入的向量化辅助函数（`equilateral_triangles_batch`、`color_triangles`）。
> `hex_grid/core.py` 除 4 个模块级函数外，还定义了 6 个模块级 namedtuple 数据结构：`Point`、`Hex`、`OffsetCoord`、`DoubledCoord`、`Orientation`、`Layout`。

---

## 1. 它解决什么问题

**问题一：三角晶格的坐标必须手推，且极易推错。**
三角晶格的晶格常数是边长 `a`，但直角坐标**不是**简单的 `x = c·a, y = r·a`：

```
x = c·a + r·(a/2)
y = r·(a/2·√3)
```

行方向每走一格，x 还要再挪半个 `a`，y 挪 `a√3/2`。一条「直段 + 120° 拐弯」的天线路径，需要逐个拐点手算 `(r, c)`、再逐个手算 `(x, y)`、再逐个换算成 CST 的 `px*/py*` 参数字符串；任何一个拐点算错，模型就错，而 CST 常常**不报错**（见 `docs/ARCHITECTURE.md` §6 硬约定 4）。

**问题二：旧 notebook 里 `path_points` 与 `(px, py)` 两套坐标重复维护。**
旧代码同时保存两份「同义」数据：

- `path_points = [(r, c), ...]` —— 用来画图、判断拐弯、算阵列范围；
- `px1, py1, ..., px6, py6` —— 用来在 CST 里画 polyline、拉伸基板。

两者没有自动推导关系，于是「改一处、忘另一处」是常态：路径多走几格，图变了、CST 里的 `px3` 没变；或者反过来，CST 里改了 `px3`，预览图还是旧的。参数化时更麻烦 —— 想「在 CST 里调 x1 就能改波导长度」，就必须手工把 `px2` 写成 `'x1*a'`、把 `px3` 写成 `'(x1-y1)*a+y1*a/2'`，符号推导全靠人脑。

**问题三：六边形晶格是「朝向 × 偏移奇偶 × 像素换算」的组合爆炸。**
6 个 cube 方向、2 种朝向（pointy / flat）、2 种偏移坐标（qoffset / roffset，各带 EVEN / ODD）、取整与插值细节，任何一处口径不一致都会导致网格错位。`docs/guides/hex_grid_guide.md` 记录的正是最初原型踩的坑：flat 朝向的网格整体倾斜、填不满指定矩形。

**本包的答案：**

- `TopoPath` —— 让**晶格坐标 `(r, c)` 成为唯一数据源**。直角坐标、CST 表达式、边界框、基板多边形、VPC 区域、阵列范围**全部自动推导**；用户只说「从哪出发、走多远、转多少度」（`.start().move().turn().build()`），不写任何 `(x, y)`。支持**符号步数**：`.move('x1', 'c')` 让路径长度本身变成 CST 参数。
- `HexLib` / `HexGridVisualizer` —— 把六边形晶格的全部坐标口径收敛到一个类里，并给出可复现的、填满矩形的交错网格生成规则。

---

## 2. 两个子包的分工

| 维度 | `mesh_grid.tri_grid` | `mesh_grid.hex_grid` |
|---|---|---|
| 晶格类型 | 等边三角晶格（正三角 + 倒三角交替铺满平面） | 六边形（蜂窝）晶格 |
| 坐标系 | 晶格坐标 `(r, c)`（整数行/列）；直角坐标由 `x = c·a + r·(a/2)`、`y = r·(a/2·√3)` 导出 | 立方体坐标 `(q, r, s)`，恒满足 `q + r + s = 0`；另有 `qoffset` / `roffset` 偏移坐标（EVEN / ODD）与像素坐标 |
| 主方向 | 6 个 60° 方向：`+c / +r / +r-c / -c / -r / -r+c` | 6 个 cube 方向：右 / 右上 / 左上 / 左 / 左下 / 右下 |
| 主要能力 | 网格生成（`build_triangle_lattice`）、`pos ↔ xy` 换算、**路径 DSL（`TopoPath` + `TopoPathBuilder`）**、空间筛选（上/下/多边形内）、曼哈顿最短路径 | 坐标运算（加/减/旋转 60°）、取整/插值/画线、邻居与距离、两种朝向的网格生成、像素坐标正反换算、六边形顶点与环 |
| 可视化 | `plot_triangle_grid`（PolyCollection 向量化）、`plot_tri_color`、`color_triangles`、`TopoPath.preview` | `HexGridVisualizer`（PolyCollection + 坐标标签 + 边界框 + 分层着色 + 颜色数组映射） |
| 导出 | 无文件导出；几何以**表达式字符串**形式交给 `topo_modeler` 建 CST 实体 | DXF：`save_to_dxf`（合并导出）、`save_multi_dxf`（多图层分组导出）、`read_and_display_dxf_matplotlib`（读回并显示） |
| 单位约定 | 长度单位 mm（晶格常数 `a`，工程默认 0.2425 mm） | 几何量级由 `hex_size`（像素/绘制单位）决定，供绘图与 DXF 参考 |
| 公开 API | 19 个模块级函数 + 2 个类（`TopoPath` 19 方法、`TopoPathBuilder` 6 方法） | 4 个模块级函数 + 2 个类（`HexLib` 25 方法、`HexGridVisualizer` 10 方法） |
| 测试 | 16 项单测（`tests/test_topo_path.py`） | 无专属单测；`tests/test_grid_opt.py` 是性能基准脚本（模块级代码直接执行，不是 pytest 用例） |

---

## 3. mesh_grid.tri_grid

### 3.1 坐标约定（唯一真源：`path_loc_to_xy`）

晶格坐标是 `(r, c)`：`r` 为行、`c` 为列。`mesh_grid/tri_grid/core.py::path_loc_to_xy(path, a)` 是**整个仓库的坐标唯一真源**，它的实现就是两条基向量：

```python
e1 = (a, 0)                        # 基向量 1（列方向，c 轴）
e2 = (a / 2, a / 2 * np.sqrt(3))   # 基向量 2（行方向，r 轴）
x = path[:, 1] * e1[0] + path[:, 0] * e2[0]     # x = c*a + r*(a/2)
y = path[:, 0] * e2[1]                          # y = r*(a/2*sqrt(3))
```

即：

```
x = c·a + r·(a/2)
y = r·(a/2·√3)
```

`TopoPath` 内部用 `TopoPath._lattice_to_xy` 复刻同一公式，并由单测（`test_consistency_with_path_loc_to_xy`）逐点比对，保证二者**永远一致**。任何新公式（新的晶格变换、新的方向定义）都必须与 `path_loc_to_xy` 对齐 —— 这是 `skills/developer/WORKFLOW.md` §3 步骤 2 的硬性要求。

> ⚠ 不要和 `pos_to_xy` 混淆。`pos_to_xy` 是**旧网格绘图接口**，内部带一个固定对齐偏移 `(_ox, _oy) = (a/2, h - a/√3)`（`h = a√3/2`），因此 `pos_to_xy(..., r=0, c=0, 'up')` 返回 `(0.5, 0.2887)` 而不是 `(0, 0)`；它的 `offset` 形参**仅为接口兼容保留，内部不使用**。路径 DSL 与所有几何推导一律走 `path_loc_to_xy` 口径（原点即 `(r,c)=(0,0)`）。

### 3.2 6 个晶格方向（逆时针从 0° 开始）

| 角度 | 方向向量 `(dr, dc)` | 名称 | 直角坐标增量 `(dx, dy)` | `segment_angles()` 实测返回值 |
|---|---|---|---|---|
| 0° | `(0, +1)` | `+c` | `(+a, 0)` | `0.0` |
| 60° | `(+1, 0)` | `+r` | `(+a/2, +a√3/2)` | `60.0` |
| 120° | `(+1, -1)` | `+r-c` | `(-a/2, +a√3/2)` | `120.0` |
| 180° | `(0, -1)` | `-c` | `(-a, 0)` | `180.0` |
| 240° | `(-1, 0)` | `-r` | `(-a/2, -a√3/2)` | `-120.0` |
| 300° | `(-1, +1)` | `-r+c` | `(+a/2, -a√3/2)` | `-60.0` |

角度由 `np.degrees(np.arctan2(y, x))` 得到，值域为 `(-180°, 180°]`，所以 240°/300° 会以负数形式返回（单测里做了 ±180° 等价处理）。

方向名的解析表（`topo_path.py::_NAME_TO_IDX`）额外接受一批别名：
`'c' / '+c' / 'c+'` → 0，`'r' / '+r' / 'r+'` → 1，`'rc' / 'r+c-' / '+r-c'` → 2，`'-c' / 'c-'` → 3，`'-r' / 'r-'` → 4，`'-rc' / 'r-c+' / '-r+c'` → 5；
`'along'` 或 `None` 表示「沿用当前方向」；也可以直接传 `(dr, dc)` 元组，但必须是上表 6 个方向之一，否则抛 `ValueError`。

### 3.3 模块级 API（19 个函数）

#### 几何计算

| 函数签名 | 说明 |
|---|---|
| `equilateral_triangle_vertices(center: Tuple[float, float], a: float, theta: float = 0) -> np.ndarray` | 单三角形三顶点，返回 `(3, 2)`。中心到顶点距离 `R = a/√3`，基础角度 `[90°, 210°, 330°]`（theta=0 时朝上），`theta` 为度 |
| `equilateral_triangles_batch(centers: np.ndarray, a: float, theta: float = 0) -> np.ndarray` | 向量化批量版本，`centers (N,2)` → `(N, 3, 2)` |
| `build_triangle_lattice(row_range: Tuple[int, int], col_range: Tuple[int, int], a: float, offset: Tuple[float, float] = (0.0, 0.0), theta: float = 0.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict, Dict]` | 生成整块网格，返回 `(triangles, centers_up, centers_dn, pos_to_center_up, pos_to_center_dn)`；`triangles` 为 `(N,3,2)` 朝上三角形顶点，`centers_dn` 由朝上中心下移 `2h/3` 得到，两个 dict 是 `(r,c) → (x,y)` 映射（含端点） |

#### 坐标转换

| 函数签名 | 说明 |
|---|---|
| `pos_to_xy(row_range, col_range, a, r, c, triangle_type='up', offset=(0.0, 0.0)) -> Tuple[float, float]` | `(r,c) → (x,y)`（含固定对齐偏移，见 3.1 警告）。越界或 `triangle_type` 非 `'up'/'down'` 抛 `ValueError` |
| `xy_to_pos(row_range, col_range, a, x, y, triangle_type='up', offset=(0.0, 0.0)) -> Tuple[int, int]` | `(x,y) → (r,c)`，结果**被夹取**在 `row_range` / `col_range` 内（不报错，直接 clamp） |
| `path_loc_to_xy(path: np.ndarray, a: float) -> np.ndarray` | 路径 `(N,2)` 晶格坐标 → `(N,2)` 直角坐标。**坐标唯一真源**，无任何偏移 |

#### 可视化

| 函数签名 | 说明 |
|---|---|
| `plot_tri_color(center, a, theta=0, color='black') -> matplotlib.patches.Polygon` | 生成单个带色三角形 Polygon（`linewidth=2`），不落图 |
| `plot_triangle_grid(row_range, col_range, a=1.0, offset=(0.0, 0.0), theta=0.0, show_labels=True, show_points=True, fill_colors_up=None, fill_colors_down=None, coord_auto_hide_threshold=500, edgecolor='black', linewidth=1.0) -> Tuple[Figure, Axes]` | 向量化画网格：正/倒三角各用**一个** `PolyCollection`（从 O(N) 个 Patch 降为 O(1)），返回 `(fig, ax)`；`fill_colors_up/down` 传颜色数组即填充，`None` 表示不填充；`coord_auto_hide_threshold` 控制标签自动隐藏。**注意：本函数不接受 `ax` 入参** |
| `color_triangles(ax, up_centers, dn_centers, a, theta=0, up_colors=None, dn_colors=None, cmap='viridis', vmin=None, vmax=None, edgecolor='black', linewidth=1.0) -> Tuple[PolyCollection, PolyCollection]` | 在**已有** Axes 上批量涂色并返回两个 PolyCollection（可后续更新面色）；一维数值数组自动经 `cmap` 映射 |

#### 空间分析

| 函数签名 | 说明 |
|---|---|
| `find_different_points(P1, P2, eps=1e-9) -> np.ndarray` | 返回 `P1` 中与 `P2` 所有点距离均 `≥ eps` 的点（平方距离比较） |
| `find_corner_points(points) -> np.ndarray` | 返回 `[左下, 右下, 左上, 右上]`（`4,2`）；点数 < 4 抛 `ValueError` |
| `is_above_segment(point, seg_start, seg_end) -> bool` | 点是否在线段上方（垂直线段特判为 `x > x1`；按线段方向决定比较符号） |
| `select_above(points, polyline) -> np.ndarray` | 折线**所有**线段上方的点；折线点数 < 2 抛 `ValueError` |
| `select_below(points, polyline) -> np.ndarray` | 折线**所有**线段下方的点；折线点数 < 2 抛 `ValueError` |
| `point_in_polygon(point, polygon) -> bool` | 射线法（内部 `+1e-7` 防除零） |
| `select_inside(points, polygon) -> np.ndarray` | 多边形内部的点；顶点数 < 3 抛 `ValueError` |

#### 路径规划

| 函数签名 | 说明 |
|---|---|
| `shortest_path(start: Tuple[int, int], end: Tuple[int, int], first_direction: str = 'x') -> np.ndarray` | 生成 `(r,c)` 曼哈顿路径点列 `(N,2)`。`first_direction` 支持 `'x'`（先列后行）、`'y'`（先行后列）、`'xy'`（斜向优先）、`'xxy'`（先列对齐再斜向）；当 `dx·dy < 0` 时自动切换到斜向优先；其他取值抛 `ValueError` |

#### 工具

| 函数签名 | 说明 |
|---|---|
| `line_cal(point, slope, known_value, is_x=True)` | 直线方程求未知坐标：`is_x=True` 时 `y = k(x-x0)+y0`，否则 `x = (y-y0)/k + x0`。异常被**捕获并 print**，失败返回 `None` |
| `test_triangle_grid()` | 自检脚本：打印 `(r,c) ↔ (x,y)` 往返结果并 `plt.show()` 画网格（人工目视） |

### 3.4 网格结构

- **朝上三角形**中心标记 `(r, c)`（红点），**朝下三角形**中心标记 `d(r,c)`（橙点）。
- 行列排布：偶数列偏移半格 —— 朝上中心 `cx = c·a + (r%2)·(a/2)`、`cy = r·h`；朝下中心为朝上中心下移 `2h/3`。
- 内部私有函数 `_build_down_triangle_verts` 负责补出真正可见的倒三角，它只遍历 `r ∈ [start_row, end_row)` 且**偶数行的最后一列不生成**朝下三角形（否则会与右侧重叠）—— 这正是 `tri_grid/README.md` 里「已修复右侧朝下三角形重叠问题」所指。
- 大网格性能：`build_triangle_lattice` 用 `np.meshgrid` 广播替代双重 for；绘图用单个 `PolyCollection`；坐标标签在总数超过阈值（默认 500）时自动隐藏。

```python
from mesh_grid.tri_grid import build_triangle_lattice, plot_triangle_grid, pos_to_xy

triangles, centers_up, centers_dn, pos_up, pos_dn = \
    build_triangle_lattice((0, 3), (0, 4), a=1.0)      # triangles: (20, 3, 2)
fig, ax = plot_triangle_grid((0, 3), (0, 4), a=1.0, show_labels=True)
xy_up = pos_to_xy((0, 3), (0, 4), 1.0, r=2, c=3, triangle_type='up')      # (3.5, 2.0207)
xy_dn = pos_to_xy((0, 3), (0, 4), 1.0, r=2, c=3, triangle_type='down')    # (3.5, 1.4434)
```

---

## 4. TopoPath —— 路径 DSL（阶段 1 交付物）

### 4.1 设计原则

1. **唯一数据源**：只保存**晶格坐标** `path_lattice = [(r, c), ...]`（`r/c` 可为 `int` 或 `str`）。直角坐标、CST 表达式、边界框、基板多边形、VPC 区域、阵列范围**全部现场推导**，不存在第二份需要同步维护的坐标。
2. **声明式**：用户说「走多远、转多少度」，不写坐标。构建器 `TopoPathBuilder` 用链式调用累积路径点，`build()` 一次性产出 `TopoPath`。
3. **符号化**：步数可以传字符串（CST 参数名），于是**路径长度本身成为 CST 参数**。数值模式下 CST 表达式是硬编码（`'18*a'`），符号模式下是参数化表达式（`'x1*a'`、`'(x1-y1)*a+y1*a/2'`），在 CST 里改 `x1/y1` 就能改路径长度。
4. **一个公式**：所有直角坐标换算都走 `_lattice_to_xy`，与 `path_loc_to_xy` 完全同式，并由单测锁定。
5. **不下发**：`mesh_grid` 只生成表达式字符串；`auto_define_cst_params(app)` 通过鸭子类型调用 `app.para(name, expr)`，因此**不 import CST**（传任何有 `para` 方法的对象都能工作，便于测试）。

### 4.2 链式构建器 `TopoPathBuilder`（6 个公开方法）

构造入口：`TopoPath.builder(a, name='path')`（等价于 `TopoPathBuilder(a, name)`）。

| 方法 | 说明 |
|---|---|
| `.start(r, c, direction=(0, 1))` | 设置起点（`r/c` 可为 `int` 或符号 `str`），并设定初始行进方向，默认 `+c`（0°，从左到右）。返回 `self` |
| `.move(steps, direction='along')` | 沿方向走 `steps` 格并**追加**一个路径点。`steps` 为 `int` 时硬编码；为 `str` 时按符号运算合并（`new_r = r + steps·dr`）。`direction` 可给方向名 / `(dr,dc)` / `'along'`（沿用当前方向）。**数值 `steps <= 0` 直接返回 `self`（静默忽略，不报错）** |
| `.turn(angle)` | 只旋转方向、不移动。`angle` 必须是 60 的整数倍（否则 `ValueError`），正为逆时针、负为顺时针，按 `(idx + angle//60) % 6` 取模 |
| `.line_to(r, c)` | 直接走到指定晶格坐标并**自动推断**行进方向（数值位移取 `gcd` 归一后匹配 6 主方向；不在主方向则 `warnings.warn` 并把方向置为 `None`）。起点相同则原地返回 `self` |
| `.close()` | 闭合路径：末点 != 起点时追加起点。点数 < 2 直接返回 `self` |
| `.build(param_values=None)` | 产出 `TopoPath`。未 `start()` 抛 `RuntimeError`；若最后一次 `turn()` 之后没有 `move()`，`warnings.warn` 提示「旋转未产生新的路径点」 |

未 `start()` 就调用 `.move()` / `.line_to()` 一律抛 `RuntimeError("请先调用 .start(r, c) 设置起点")`。

> **区域多边形绕向是硬约定（CCW）。** `build_substrate_polygon()` 与 `build_vpc_area_polygon()` 都保证**逆时针**（有向面积 > 0）。原因见 `docs/ARCHITECTURE.md` §6 硬约定 1：CST 的 `ExtrudeCurve` 沿多边形**法向**拉伸，而法向由顶点绕向决定 —— CCW 拉到 `+z`、CW 拉到 `−z`；绕向反了，实体在 z 上会与其它部件差一个 `h`，布尔求交得到**空集却不报错**。这也是为什么两条边界链都包含**每一个**路径点：只取两端偏移点的稀疏写法，其绕向会随拐弯方向翻转，无法保证 CCW。该不变量由单测 16（`test_polygon_winding_is_ccw`）钉住。

### 4.3 `TopoPath` 公开成员（19 个方法 / 属性）

构造入口还有 `TopoPath.from_lattice(points, a, name='path', param_values=None)`（从 `(r,c)` 列表直接创建，兼容旧代码）；另有 `len(path)`、`path[i]`、`repr(path)`、公开属性 `path_lattice`（原始、可能含符号）、构造函数参数 `a` / `name` / `param_values`。

| 成员 | 类型 | 说明 |
|---|---|---|
| `xy` | property → `np.ndarray (N,2)` | 直角坐标。符号路径且未提供 `param_values` 时抛 `RuntimeError` |
| `lattice` | property → `np.ndarray (N,2) int` | 数值化晶格坐标；同上会抛 `RuntimeError` |
| `lattice_symbolic` | property → `list[tuple]` | 原始晶格坐标（可能含 `str`），用于生成 CST 表达式 |
| `has_symbols` | property → `bool` | 是否含符号坐标 |
| `lattice_to_cst_expr(r, c)` | staticmethod → `(px, py)` | **纯静态换算**，不需要实例：把 `(r,c)`（可含符号）编成 CST 表达式字符串；含 `+`/`-` 的符号表达式自动加括号 |
| `auto_define_cst_params(app, prefix=None)` | 方法 | 逐点调用 `app.para(f'{pfx}{i+1}x', px)` / `app.para(f'{pfx}{i+1}y', py)`；`pfx` 默认取 `self.name` |
| `get_cst_point(idx, prefix=None)` | 方法 | 返回第 `idx` 个点的参数名元组，如 `('path3x', 'path3y')` |
| `get_cst_polygon(indices, prefix=None)` | 方法 | 返回指定索引点组成的 CST 表达式顶点列表 `[[px, py], ...]` |
| `get_bounding_box(margin_c=1, margin_r=1)` | 方法 | 用 `(r_min-1, c_min-1) … (r_max+1, c_max+1)` 四个角换算后取包络，返回 `(xmin, xmax, ymin, ymax)`。需数值坐标 |
| `get_array_range()` | 方法 | 自动推导光子晶体阵列复制范围 `(xup, yup, ydn)` = `(c_max + abs(r_max)//2 + 1, abs(r_max) + 1, abs(r_min) + 1)`（源码写法 `int(c_max) + int(abs(r_max)/2) + 1`、`int(abs(r_max)) + 1`、`int(abs(r_min)) + 1`）。需数值坐标 |
| `build_substrate_polygon(y_margin='e2', prefix=None)` | 方法 | 基板带状多边形顶点（CST 表达式形式）。顶点顺序：**下侧偏移链正向**（各点 `py - y_margin`，`i=0…N-1`）→ **上侧偏移链反向**（各点 `py + y_margin`，`i=N-1…0`）→ 回到首点 ⇒ 顶点数 `2N + 1`。**绕向固定为逆时针（CCW，有向面积 > 0）** |
| `build_vpc_area_polygon(side='upper', y_margin='e2', prefix=None)` | 方法 | VPC-A / VPC-B 裁剪区域顶点，同样保证 **CCW**、两条边界链都含全部路径点 ⇒ 顶点数 `2N + 1`。`side='upper'`（路径是下边界）：路径链正向 → 上侧偏移链反向（`py + y_margin`）→ 首点；`side='lower'`（路径是上边界）：下侧偏移链正向（`py - y_margin`）→ 路径链反向 → 首点。`side` 不是 `'upper'` / `'lower'` 时抛 `ValueError` |
| `segment_directions()` | 方法 | 每段的方向单位向量 `(dr, dc)` 列表（按 `gcd` 归一）。需数值坐标 |
| `segment_angles()` | 方法 | 每段的物理角度（度，`arctan2` 值域 `(-180, 180]`）。需数值坐标 |
| `is_straight()` | 方法 | `len(path_lattice) <= 2` |
| `has_bend()` | 方法 | `len(path_lattice) > 2` |
| `preview(ax=None, show_grid=True, color='green', marker='o', linewidth=2, markersize=6, label=None, lattice_rows=None, lattice_cols=None)` | 方法 | matplotlib 预览：画路径 + 每个点的 `(r,c)` 标注 + 可选晶格背景，返回 `(fig, ax)`。需数值坐标（见 4.5 限制） |
| `builder(a, name='path')` | staticmethod | 创建 `TopoPathBuilder` |
| `from_lattice(points, a, name='path', param_values=None)` | staticmethod | 从 `(r,c)` 列表直接创建 |

### 4.4 三个典型用法（输出均为实测值）

**(a) 直波导**（`a = 0.2425 mm`）

```python
from mesh_grid.tri_grid import TopoPath

path = TopoPath.builder(a=0.2425).start(0, -1).move(19, 'c').build()
```

| 结果 | 值 |
|---|---|
| `list(path)` | `[(0, -1), (0, 18)]` |
| `path.is_straight()` / `has_bend()` | `True` / `False` |
| `path.xy` | `[[-0.2425, 0.0], [4.365, 0.0]]` |
| `segment_directions()` / `segment_angles()` | `[(0, 1)]` / `[0.0]` |
| `get_bounding_box()` | `(-0.60625, 4.72875, -0.21001, 0.21001)` |
| `get_array_range()` | `(19, 1, 1)`，即 `xup=19, yup=1, ydn=1` |

**(b) 120° 天线**

```python
path = (TopoPath.builder(a=0.2425)
        .start(0, -1)
        .move(19, 'c')       # 直段：0°
        .turn(120)           # 逆时针 120°
        .move(14, 'along')   # 沿 120° 方向走 14 格
        .build())
```

| 结果 | 值 |
|---|---|
| `list(path)` | `[(0, -1), (0, 18), (14, 4)]` |
| `path.segment_angles()` | `[0.0, 120.0]` |
| 各点 CST 表达式 | `('-1*a+0*a/2', '0*a/2*sqr(3)')`、`('18*a+0*a/2', '0*a/2*sqr(3)')`、`('4*a+14*a/2', '14*a/2*sqr(3)')` |
| `has_bend()` | `True` |
| `build_substrate_polygon()` | 顶点数 `7`（= `2×3+1`）：`[['path1x','path1y-e2'], ['path2x','path2y-e2'], ['path3x','path3y-e2'], ['path3x','path3y+e2'], ['path2x','path2y+e2'], ['path1x','path1y+e2'], ['path1x','path1y-e2']]`（CCW） |
| `build_vpc_area_polygon('upper')` 顶点数 | `7`（= `2×3+1`）：路径链正向 → 上侧偏移链反向 → 首点 |
| `build_vpc_area_polygon('lower')` 顶点数 | `7`（= `2×3+1`）：下侧偏移链正向 → 路径链反向 → 首点；`side='middle'` 抛 `ValueError` |
| `get_array_range()` | `(26, 15, 1)` |

**(c) 符号坐标参数化路径**（路径长度变成 CST 参数）

```python
path = (TopoPath.builder(a=0.2425, name='path')
        .start(0, 0)
        .move('x1', 'c')       # 符号步数：x1 是 CST 参数
        .turn(120)
        .move('y1', 'along')   # 符号步数：y1 是 CST 参数
        .build(param_values={'x1': 18, 'y1': 14}))   # 预览/计算用的数值

path.has_symbols            # True
path.lattice_symbolic       # [(0, 0), (0, 'x1'), ('y1', 'x1-y1')]
path.lattice                # [[0, 0], [0, 18], [14, 4]]   ← 用 param_values 数值化
path.xy                     # [[0.0, 0.0], [4.365, 0.0], [2.6675, 2.9402]]

app = ...                   # 任何提供 .para(name, expr) 的对象（如 cst_solver 的 setup）
path.auto_define_cst_params(app)
```

`auto_define_cst_params(app)` 实际下发（`prefix` 默认取 `name`，故为 `path1x…`）：

```
app.para('path1x', '0*a')
app.para('path1y', '0')
app.para('path2x', 'x1*a')
app.para('path2y', '0')
app.para('path3x', '(x1-y1)*a+y1*a/2')      # 展开即 x1*a - y1*a/2
app.para('path3y', 'y1*a/2*sqr(3)')         # 展开即 y1*a*√3/2
```

在 CST 中把 `x1` 从 18 改成别的值，整条路径的直段与拐点**同时**跟着变 —— 这正是「统一坐标层」要买的东西。

### 4.5 已知限制与注意事项

1. **符号路径必须给 `param_values` 才能做数值计算。** 没有 `param_values`（或其中的符号解析不出来）时，`path_lattice` 里仍留着字符串，`_path_numeric` 为 `None`，于是 `xy` / `lattice` / `get_bounding_box()` / `get_array_range()` / `segment_directions()` / `segment_angles()` / `preview()` 全部抛 `RuntimeError("符号路径…请提供 param_values")`。**此时唯一可用的仍是 `lattice_symbolic` 与静态的 `lattice_to_cst_expr()`** —— 也就是说「生成 CST 表达式」不需要数值，「画图 / 算边界 / 算阵列」才需要。**特别地：`get_array_range()` 对符号路径同样需要 `param_values`**（单测 15 只显式校验了 `xy` / `lattice` / `get_bounding_box`，但源码对 `get_array_range()` 有同一道 `_path_numeric is None` 检查）。
2. **`preview()` 的默认参数当前会抛异常。** `preview(show_grid=True)` 内部调用 `plot_triangle_grid(..., ax=ax)`，而 `plot_triangle_grid` 的签名**没有 `ax` 参数**，实测抛 `TypeError: plot_triangle_grid() got an unexpected keyword argument 'ax'`；`try/except` 只捕获 `ImportError`，所以异常会冒出来。**规避方式：`path.preview(show_grid=False)`**（实测正常），或先自己建好 Axes 再手工画。修这个缺陷属于 `mesh_grid` 的开发者任务（见 §8）。
3. **`lattice_to_cst_expr(0, 0)` 返回 `('0*a', '0')`**，而不是 `('0', '0')`：「`r == 0` 且 `c == 0`」时走的是 `r` 为零的分支 `px = f'{c}*a'`。单测 `test_symbolic_straight_waveguide` 已按 `px1 == '0*a' or px1 == '0'` 兼容两种写法；CST 两种都能算，但如果做字符串比对要注意。
4. **`segment_angles()` 值域是 `(-180°, 180°]`**：240° 方向返回 `-120.0`、300° 方向返回 `-60.0`。比较角度时必须做 ±180° 归一（单测 1 就是这么做的）。
5. **符号解析用 `eval`，且 `int()` 截断。** `_resolve_symbol` 先查 `param_values`，再把 `'x1-y1'` 这类表达式用 `eval(value, {'__builtins__': {}}, param_values)` 求值，最后 `int(...)`。所以：`param_values` 传浮点会被**截断**（建议只传整数），表达式只能引用 `param_values` 里的名字，解析失败时会把原字符串当结果返回（进而在访问 `xy` 时报 `RuntimeError`）。
6. **`.move(0, ...)` / 负步数是静默无操作**（`steps <= 0` 直接 `return self`）；`.turn()` 之后若不 `move()` 就 `build()`，只会得到一条 warning，旋转不会产生新点。
7. **`get_array_range()` 是按路径推断的，不是按基板。** `docs/ARCHITECTURE.md` §6 硬约定 3 明确要求「光子晶体阵列的 `xup/yup/ydn` 必须覆盖整个基板，不能只按路径推断」—— 所以把 `TopoPath.get_array_range()` 当作**下界参考**，落地时由 `topo_modeler` 依据基板尺寸取更大值。
8. **`line_to()` 推断不出 6 主方向时**会 `warnings.warn` 并把当前方向置为 `None`；此后若再用 `direction='along'`，`_resolve_move_direction` 会抛 `RuntimeError("当前方向未定义…")`。

---

## 5. mesh_grid.hex_grid

### 5.1 立方体坐标与朝向

采用 Red Blob Games 的六边形网格理论，核心是**立方体坐标** `Hex(q, r, s)`，恒满足 `q + r + s = 0`（`create_hex` 用 `assert np.round(q+r+s) == 0` 校验，`s` 省略时自动取 `-q-r`）。`q` 映射 X 方向、`r` 映射 Y 方向，`s` 是冗余量。

模块级数据结构（6 个 namedtuple）：

| 名称 | 字段 |
|---|---|
| `Point` | `x, y` |
| `Hex` | `q, r, s` |
| `OffsetCoord` | `col, row` |
| `DoubledCoord` | `col, row` |
| `Orientation` | `f0 f1 f2 f3 b0 b1 b2 b3 start_angle` |
| `Layout` | `orientation, size, origin` |

两种朝向由类常量 `HexLib.LAYOUT_POINTY` / `HexLib.LAYOUT_FLAT` 提供（正向 `f*` 与逆向 `b*` 矩阵）：

| 朝向 | 构造参数 | `start_angle` | `x_step` | `y_step` | 交错规则（`create_staggered_grid`） |
|---|---|---|---|---|---|
| Pointy-top（尖朝上） | `orientation="pointy"` | `0.5` | `hex_size·√3` | `hex_size·1.5` | 先遍历行，按 `row // 2` 修正列：`q = col - row//2, r = row` |
| Flat-top（平朝上） | `orientation="flat"` | `0.0` | `hex_size·1.5` | `hex_size·√3` | 先遍历列，按 `col // 2` 修正行：`q = col, r = row - col//2` |

偏移坐标的奇偶常量：`HexLib.EVEN = 1`、`HexLib.ODD = -1`（四个 `*offset_*` 方法都会校验该取值，否则 `ValueError`）。

### 5.2 `HexLib`（25 个公开方法，不含 `__init__`）

构造：`HexLib(hex_size=20, orientation="pointy", origin=(0, 0))`，`orientation` 非 `pointy/flat` 抛 `ValueError`。

| 分组 | 方法签名 | 说明 |
|---|---|---|
| 基础坐标运算 | `create_hex(q, r, s=None)` | 创建立方体坐标（自动补 `s`，校验 `q+r+s=0`） |
| | `hex_add(a, b)` / `hex_subtract(a, b)` | 立方体坐标加 / 减 |
| | `hex_rotate_left(a)` / `hex_rotate_right(a)` | 左 / 右旋 60°（`(-s,-q,-r)` / `(-r,-s,-q)`） |
| 邻居与距离 | `get_hex_direction(direction)` | 6 个方向单位向量，索引 `0..5` = 右 / 右上 / 左上 / 左 / 左下 / 右下，超出自动 `% 6` |
| | `get_hex_neighbor(hex_coord, direction)` | 邻居坐标 |
| | `get_hex_length(hex_coord)` | 到原点的六边形步数 `(abs(q)+abs(r)+abs(s))//2` |
| | `get_hex_distance(a, b)` | 两六边形步数距离 |
| 取整 / 插值 / 画线 | `hex_round(hex_coord)` | 浮点立方体坐标取整（分量差最大者由另两者反推） |
| | `hex_lerp(a, b, t)` | 线性插值 `t∈[0,1]` |
| | `hex_linedraw(a, b)` | 两点间经过的所有六边形（端点加 `1e-6` 微扰避免边界歧义） |
| 偏移坐标 | `qoffset_from_cube(offset_type, hex_coord)` / `qoffset_to_cube(offset_type, offset_coord)` | Q 轴（列）偏移 ↔ 立方体 |
| | `roffset_from_cube(offset_type, hex_coord)` / `roffset_to_cube(offset_type, offset_coord)` | R 轴（行）偏移 ↔ 立方体 |
| 笛卡尔换算 | `hex_to_pixel(hex_coord)` → `Point` | 立方体坐标 → 像素坐标（`x=(f0·q+f1·r)·size.x + origin.x`，`y` 同理） |
| | `hexes_to_pixels(hex_coords)` → `(x_array, y_array)` | 向量化批量换算 |
| | `pixel_to_hex_fractional(pixel_coord)` | 像素 → 浮点立方体坐标（接受 `Point` 或 `(x, y)` 元组） |
| | `pixel_to_hex(pixel_coord)` | 像素 → 取整后的立方体坐标（与 `hex_to_pixel` 互为逆，实测往返一致） |
| 顶点 | `get_hex_corners(hex_coord)` → `list[Point]` | 6 个顶点（角度 `2π(start_angle - i)/6`） |
| | `get_hex_corners_batch(hex_coords)` → `(N, 6, 2)` | 向量化批量顶点，空输入返回 `(0,6,2)` |
| 网格生成 | `create_staggered_grid(col_range, row_range)` → `list[Hex]` | 交错类矩形网格，**会 print** 朝向/范围/总数；数量 = `(max_col-min_col+1)×(max_row-min_row+1)` |
| | `create_hex_grid_hexagonal(N)` → `list[Hex]` | 半径 `N` 的正六边形排布，数量 `3N²+3N+1`（N=0/1/2/3 → 1/7/19/37） |
| | `get_hex_ring(radius)` → `list[Hex]` | 单层环，`radius=0` 返回原点；`radius>0` 返回 `6·radius` 个（1/2/3 → 6/12/18） |

### 5.3 `HexGridVisualizer`（10 个公开方法，不含 `__init__`）

构造：`HexGridVisualizer(hex_size=30, orientation="pointy", origin=(0, 0), coord_auto_hide_threshold=500)`，内部自建一个 `HexLib` 并创建 `fig, ax`（`figsize=(14, 12)`，等比例、带网格线与原点十字线）。

| 方法签名 | 说明 |
|---|---|
| `set_grid(grid_hexes)` | 设置待绘制网格 |
| `set_hex_color(hex_coord, color)` | 设置单个六边形颜色（存入 `hex_colors` 字典） |
| `batch_set_color(color_map)` | 批量合并颜色字典 |
| `toggle_coord_display(show)` | 开关坐标标签 |
| `set_coord_type(coord_type)` | 标签格式，取值 `cube` / `offset_r` / `offset_q` / `pixel`（其他值抛 `ValueError`）；实测分别渲染为 `(2,-1,-1)` / `R(1,-1)` / `Q(2,0)` / `P(52,-30)`（偏移坐标用 ODD 口径） |
| `draw(title="Hex Grid", show_on=True)` | 向量化绘制：所有六边形合成**一个** `PolyCollection`（从 O(N) 个 Patch 降为 O(1)），额外画中心坐标文字、红色虚线边界框与图例；网格数 > `coord_auto_hide_threshold` 时自动隐藏坐标标签；`show_on=True` 会调 `plt.show()` |
| `add_color_array(colors, cmap='viridis', vmin=None, vmax=None)` | 直接更新已有 `PolyCollection` 的面色（无需重绘）：一维数值数组经 `cmap` 映射，颜色值数组直接使用，`None` 重置为白色。**必须先 `draw()`**，否则抛 `ValueError` |
| `add_color_map(color_map, cmap='viridis', vmin=None, vmax=None)` | `{Hex: 颜色或数值}` 字典 → 按 `grid_hexes` 顺序转数组后调用 `add_color_array` |
| `draw_hexagonal_grid(N, highlight_boundary=True, color_layers=True)` | 一键画正六边形网格：按层着色（0→red, 1→yellow, 2→green, 3→blue, 4→purple），最外层（`get_hex_length == N`）高亮为 orange，再 `draw()` |
| `draw_staggered_grid(col_range, row_range, highlight_origin=True)` | 一键画交错网格；原点 `Hex(0,0)` 在范围内时标红 |

### 5.4 模块级导出与 DXF 工具

`hex_grid/__init__.py` 的 `__all__` 导出 6 个符号：2 个类 + 4 个函数。

| 函数签名 | 说明 |
|---|---|
| `create_hex_polygon(center, cell_width, theta=np.pi/6)` | 生成 Shapely 六边形 `Polygon`：`angles = linspace(0, 2π, 7)[:-1] + theta`，默认旋转 30° 成平顶。`cell_width` 是外接圆半径（中心到顶点），故边长也是 `cell_width` |
| `save_to_dxf(hex_all, filename="hex_grid.dxf", layer_name="hexgrid", precision=6)` | 把一组六边形**先合并再导出**：`unary_union` → `buffer(1e-6).buffer(-1e-6)`（消除自交/微缝）→ 逐 polygon 以 `add_lwpolyline(..., close=True)` 写入指定图层，DXF 版本 `R2010`，坐标按 `precision` 四舍五入（docstring 建议 3~4 以减小文件、加速 CST 导入）；`MultiPolygon` 会逐段导出 |
| `save_multi_dxf(hex_groups, filename="hex_grid.dxf", layer_name="hexgrid", precision=6)` | 多组六边形分别合并后写入**独立图层** `layer_name + str(i)`，外层用 `tqdm` 显示进度 |
| `read_and_display_dxf_matplotlib(filename="hex_grid.dxf", show_on=True)` | 读回 DXF，只遍历 `LWPOLYLINE` 并用 matplotlib 画线（自动闭合首尾点）。**异常被 try/except 吞掉并 print**「读取 DXF 文件时出错」，不向上抛 —— 排查 DXF 问题时要看 stdout |

### 5.5 快速开始（实测值）

```python
from mesh_grid.hex_grid import HexLib, HexGridVisualizer, create_hex_polygon, save_to_dxf

lib = HexLib(hex_size=20, orientation="pointy")
grid = lib.create_staggered_grid((0, 5), (0, 4))     # 30 个 Hex（会 print 网格信息）
hexagon_grid = lib.create_hex_grid_hexagonal(2)      # 19 个 Hex = 3·2² + 3·2 + 1

hx = lib.create_hex(2, -1)                           # Hex(q=2, r=-1, s=-1)
pixel = lib.hex_to_pixel(hx)                         # Point(x=51.96, y=-30.0)
assert lib.pixel_to_hex(pixel) == hx                 # 往返一致
cx, cy = lib.hexes_to_pixels(grid[:3])               # 向量化批量换算
corners = lib.get_hex_corners_batch(grid[:4])        # (4, 6, 2)

viz = HexGridVisualizer(hex_size=20, orientation="pointy")
viz.set_grid(grid)
viz.draw(title="pointy 交错网格", show_on=False)       # PolyCollection 一次性绘制
viz.add_color_array([h.q for h in grid], cmap="viridis")   # 必须先 draw()

hex_polys = [create_hex_polygon(lib.hex_to_pixel(h), 20) for h in grid]
save_to_dxf(hex_polys, "output.dxf", precision=4)    # 需要 ezdxf + shapely
```

> 背景阅读提示：`docs/guides/hex_grid_guide.md` 记录的是这一模块**最初的原型实现**（`HexLib(layout_type=...)`、`hex_size` 为 `(w, h)` 元组、`create_hex` 返回 dict 并直接算像素坐标）。当前实现已改为 `orientation=` 参数 + `Hex` namedtuple + `Orientation` 矩阵 + `Layout`，`create_hex` 只做坐标不做像素换算。指南里的**交错偏移规则**与结论（flat 偶数列偏移行、pointy 奇数行偏移列 → 网格填满矩形）与现在一致，但示例代码不能直接复制运行。

---

## 6. 测试与验收

`mesh_grid/tri_grid/tests/test_topo_path.py` 是**全仓库唯一的单测套件**（16 项，`pyproject.toml` 的 `testpaths` 显式包含该目录，打包时 `mesh_grid.tri_grid.tests*` 被排除）。它是路径 DSL 与坐标公式的**回归护栏**：

> 仓库里另一个 `test_*.py` 命中 `python_files` 的文件是 `tests/test_grid_opt.py`，但它**不是单测**：它是网格绘制性能基准脚本（模块级代码直接跑，没有 `test_*` 函数），且内部调用了 `plot_triangle_grid(..., show_on=False)` —— 当前 `plot_triangle_grid` 签名没有 `show_on` 参数，所以 `python -m pytest -q` 会在**收集阶段**就报错 `TypeError: plot_triangle_grid() got an unexpected keyword argument 'show_on'`（与 §4.5 第 2 条的 `preview()` 是同一类「绘制辅助函数签名漂移」缺陷）。因此本包的正确验收命令是 **`python -m pytest mesh_grid -q`**（实测 16 passed）；修好该脚本或改用它之后再跑仓库级 `python -m pytest -q`。

| # | 测试函数 | 守住什么 |
|---|---|---|
| 1 | `test_directions_mapping` | 6 个方向 `(dr,dc)` → 物理角度映射（0/60/120/180/240/300°），用 `segment_angles()` 校验并处理 ±180° 等价 |
| 2 | `test_turn_rotation` | `turn(±60/120/180/240/300)` 后 `move(1,'along')` 的位移方向正确，含负角度取模 |
| 3 | `test_straight_waveguide_path` | 直波导 `.start(0,-1).move(19,'c')` → `[(0,-1), (0,18)]`，且 `is_straight()` / `not has_bend()` |
| 4 | `test_120degree_antenna_path` | 120° 天线 → `[(0,-1), (0,18), (14,4)]`，且段角度为 `[0°, 120°]` |
| 5 | `test_cst_expr_0_18` | `lattice_to_cst_expr(0, 18) == ('18*a', '0')`（`r=0` 时 `py` 必须为 `'0'`） |
| 6 | `test_cst_expr_14_4` | `lattice_to_cst_expr(14, 4) == ('4*a+14*a/2', '14*a/2*sqr(3)')`（项序与 `sqr(3)` 写法） |
| 7 | `test_consistency_with_path_loc_to_xy` | **核心护栏**：`TopoPath.xy` 与 `path_loc_to_xy(path.lattice, a)` 在直波导 / 120° / 240° 三种路径上逐点相等 |
| 8 | `test_bounding_box_and_array_range` | 边界框包含所有路径点；`get_array_range()` 对 120° 天线返回 `(xup=26, yup=15, ydn=1)`（`r∈[0,14]`、`c∈[-1,18]`） |
| 9 | `test_substrate_polygon_vertices` | 基板顶点数 = `2N+1`；VPC 区域顶点数同样 = `2N+1`（upper / lower 一样，因为两条边界链都含全部路径点）；`side='middle'` 必须抛含 `'upper'` 的 `ValueError` |
| 10 | `test_invalid_inputs` | 5 类非法输入必须抛明确异常：`turn(90)`→`ValueError`（含「60」）、空路径 `build()`→`RuntimeError`、未 `start()` 就 `move()`→`RuntimeError`、未知方向名→`ValueError`（含「未知方向」）、`path_lattice` 形状错误→`ValueError`（含「(N,2)」） |
| 11 | `test_symbolic_operations` | 符号运算化简规则：`_symbolic_add(-1,'x1')=='x1-1'`、`_symbolic_add('x1','y1')=='x1+y1'`、零元、数值加法；`_symbolic_mul` 的 0/1/-1/数值分支 |
| 12 | `test_symbolic_straight_waveguide` | 符号直波导：`has_symbols`、末点为 `(0,'x1')`、表达式 `p2x=='x1*a'`、`py2=='0'`，且 `param_values={'x1':18}` 数值化为 `[[0,0],[0,18]]`、`xy[1]==[18a, 0]` |
| 13 | `test_symbolic_120_antenna` | 符号 120° 天线：第三点 `('y1','x1-y1')`、`p3x=='(x1-y1)*a+y1*a/2'`、`p3y=='y1*a/2*sqr(3)'`，数值化 `[[0,0],[0,18],[14,4]]` 且直角坐标与手算一致 |
| 14 | `test_symbolic_vs_old_code` | 与旧 notebook 的参数化方式对齐：`px2/px3` 完全一致；旧代码的拐弯方向等价于 `turn(240)`（`turn(120)` 的 `py3` 符号相反） |
| 15 | `test_symbolic_without_param_values` | 无 `param_values` 时：CST 表达式仍正常生成，而 `xy` / `lattice` / `get_bounding_box()` 必须抛含 `'param_values'` 的 `RuntimeError` |
| 16 | `test_polygon_winding_is_ccw` | **跨包硬约定护栏**：用 CST 表达式反推数值后算有向面积，钉住「基板 + VPC upper + VPC lower 三种多边形一律 CCW（面积 > 0）」。背景是真实缺陷：CW 会让 `ExtrudeCurve` 沿 `−z` 拉伸，实体与其它部件在 z 上差一个 `h`，布尔求交得空集且 CST 不报错（`docs/ARCHITECTURE.md` §6 硬约定 1） |

**运行方式**

```bash
# 只跑本包（推荐，也是当前唯一全绿的验收命令）
python -m pytest mesh_grid -q            # 实测：16 passed

# 跑全仓库：当前会在收集阶段因 tests/test_grid_opt.py 报 TypeError（见上）
python -m pytest -q

# 脚本自带 main，也可直接运行（会 print 每项结果）
python mesh_grid/tri_grid/tests/test_topo_path.py
```

**验收规则**：任何改动只要触碰**坐标公式**（`path_loc_to_xy` / `_lattice_to_xy` / 方向表 `DIRECTIONS` / 方向名别名表）、**路径 DSL**（`TopoPathBuilder` / `TopoPath`）或**区域多边形绕向**，就必须保证这 16 项全绿；新增行为应**追加**测试而不是放宽既有断言。`skills/developer/WORKFLOW.md` §4 的 `mesh_grid/` 验收清单与此一致：新公式与 `path_loc_to_xy` 一致、`__init__.py` 的 `__all__` 已更新、`python -m pytest mesh_grid -q` 通过、重新生成 API HTML。

---

## 7. 硬约定

1. **`path_loc_to_xy` 是坐标的唯一真源。**
   `mesh_grid/tri_grid/core.py::path_loc_to_xy`（`x = c·a + r·(a/2)`，`y = r·(a/2·√3)`）定义了整套三角晶格坐标口径。`TopoPath._lattice_to_xy`、`lattice_to_cst_expr`、`build_*_polygon`、`get_array_range` 以及上层 `topo_modeler` 的全部几何都必须与它一致；新增任何晶格变换/方向定义，先对齐它，再用单测锁定（`test_consistency_with_path_loc_to_xy`）。
2. **`mesh_grid` 永不 import CST。**
   它是纯计算包（`numpy` + `matplotlib`，`tqdm` 进度条，`ezdxf` / `shapely` 用于 DXF 与几何运算）。它只产出 CST **表达式字符串**；实际的 CST 下发永远发生在 `cst_solver` / `topo_modeler` / `templates`。这条是 `skills/developer/WORKFLOW.md` §10 的禁止事项之一（「❌ 在 `mesh_grid` 里引入 CST 依赖（它必须保持纯计算）」），也是 `docs/ARCHITECTURE.md` §2 单向依赖图的一部分。相应地，`auto_define_cst_params(app)` 只做鸭子类型调用（要求 `app.para(name, expr)`），不 import 任何 CST 模块。
3. **新增公开 API 必须导出到子包 `__init__.py` 的 `__all__`。**
   `mesh_grid/__init__.py` 自动导入两个子包，`mesh_grid/tri_grid/__init__.py` 与 `mesh_grid/hex_grid/__init__.py` 各自维护 `__all__`。只在 `core.py` 里写函数而不导出，等于对外不可见，且 `docs/guides/api/*.html` 与技能文档都会与代码脱节。删除/改名公开符号时按 `WORKFLOW.md` §5 保留别名并登记弃用。
4. **改动公开 API 后重新生成 `docs/guides/api/{hex,tri}_grid_api.html`。**
   ```bash
   python scripts/gen_mesh_docs.py        # → docs/guides/api/{hex,tri}_grid_api.html
   ```
   生成器从 `mesh_grid.hex_grid.core` / `mesh_grid.tri_grid.core` 的 docstring 提取内容，**不要手改 HTML**。配套的规模统计用 `python scripts/_api_stats.py`（本文「元信息」里的 23 / 4 / 60 即出自它）。
   > 注意：`gen_mesh_docs.py` 采用 `inspect.getmembers` 口径，会把 `core.py` 里被 import 进来的第三方函数/类一并列出（HTML 中的「公开符号」计数因此大于 AST 口径的函数数）；两个数字用途不同，不要互相「纠正」。
   > 另外：`topo_path.py` 不在生成器扫的模块列表里，`TopoPath` / `TopoPathBuilder` 目前没有自动生成的 HTML 页面 —— 本文件 §4 是它们的权威说明。

---

## 8. 如何扩展这个包

**先读流程，再动手**：完整开发流程、验收清单、提交规范、文档同步矩阵一律以 [`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md) 为准（文档生成细节见 `skills/developer/doc-generation.md`）。以下是落到 `mesh_grid` 的最短路径：

1. **判定归属**：确认需求属于「与 CST 无关的晶格数学 / 坐标 / 可视化 / DXF」→ `mesh_grid`；若它只在某个器件里成立，或需要 CST 对象 → 归 `topo_modeler` / `templates`（`WORKFLOW.md` §2）。`mesh_grid` 必须保持通用，禁止塞入只服务单个模板的逻辑。
2. **读技能文档**：`skills/user/tri-grid.md`、`skills/user/hex-grid.md`；改路径 DSL 还要读 `docs/guides/topo_modeler_guide_stage0-3.md` 的「阶段 1」章节。
3. **确认公式基准**：三角晶格一律与 `path_loc_to_xy` 对齐（§7 约定 1）；六边形晶格一律与 Red Blob Games 的 cube 口径和 `Orientation` 矩阵对齐。
4. **设计签名**：明确参数名/默认值/返回类型与异常语义；数值与符号双模式的 API 要写清「哪些操作需要 `param_values`」；遵循 `WORKFLOW.md` §4 的 mesh_grid 清单（中文 Google/Numpy 风格 docstring、`# -*- coding: utf-8 -*-` 文件头、4 空格缩进）。
5. **改代码并导出**：`mesh_grid/tri_grid/core.py` 或 `hex_grid/core.py`（新增晶格/坐标变换），路径 DSL 改 `tri_grid/topo_path.py`；同步子包 `__init__.py` 的 `import` 与 `__all__`（§7 约定 3）。
6. **补测试**：触碰 `topo_path.py`、坐标公式或区域多边形绕向，必须扩充 `mesh_grid/tri_grid/tests/test_topo_path.py`（保持既有 16 项全绿）；hex_grid 的新能力建议在 `tests/` 下加最小冒烟（注意 `tests/test_grid_opt.py` 目前不是 pytest 用例且会挡住仓库级收集，见 §6）。
7. **同步文档**：本文件（`docs/packages/mesh_grid.md`）、必要时 `docs/ARCHITECTURE.md` §3.2/§7；然后 `python scripts/gen_mesh_docs.py` 重新生成 API HTML（§7 约定 4），并检查全仓库是否还有旧路径/旧符号引用（`WORKFLOW.md` §9）。
8. **验证并提交**：先确保 `python -m pytest mesh_grid -q` 全绿（仓库级 `python -m pytest -q` 目前会被 `tests/test_grid_opt.py` 的收集错误挡住，见 §6）；然后按「一个包一条 commit」提交，示例见 `WORKFLOW.md` §8。

---

## 9. 相关文档

| 文档 | 内容 |
|---|---|
| [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | 总体架构：`mesh_grid` 在五包分层中的位置、单向依赖图、跨包硬约定（z 平面绕向、布尔语义、阵列范围、错误不可见） |
| [`../guides/api/tri_grid_api.html`](../guides/api/tri_grid_api.html) | `mesh_grid.tri_grid.core` 自动生成 API（签名 + docstring） |
| [`../guides/api/hex_grid_api.html`](../guides/api/hex_grid_api.html) | `mesh_grid.hex_grid.core` 自动生成 API（签名 + docstring） |
| [`../guides/hex_grid_guide.md`](../guides/hex_grid_guide.md) | HexGrid 六边形网格工具包说明（物理/几何背景与交错网格「填满矩形」的修复对照；代码为早期原型实现） |
| [`../guides/topo_modeler_guide_stage0-3.md`](../guides/topo_modeler_guide_stage0-3.md) | 阶段 0–3 建模引擎指南，其中「阶段 1：坐标统一层 — TopoPath」给出坐标公式、6 方向表与核心 API 表 |
| [`../../skills/user/tri-grid.md`](../../skills/user/tri-grid.md) | 使用者视角：三角晶格与路径 DSL 速查 |
| [`../../skills/user/hex-grid.md`](../../skills/user/hex-grid.md) | 使用者视角：六边形晶格与 DXF 导出速查 |
| [`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md) | 开发宪法：改动归属、标准工作流、各包验收清单、命名/文档同步/提交规范 |

**包内文档**：`mesh_grid/tri_grid/README.md`（三角晶格函数分类表与网格结构）、`mesh_grid/hex_grid/README.md`（六边形核心类与坐标系统）。
