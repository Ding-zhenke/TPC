# mesh_grid.hex_grid — 六边形网格算法库

## 概述

`mesh_grid.hex_grid` 是 TPC 项目的六边形网格核心算法库，基于 **Red Blob Games** 的六边形网格理论（立方体坐标系），提供完整的六边形网格生成、坐标转换、可视化和 DXF 导出功能。

## 核心类

### `HexLib` — 六边形网格核心算法类

六边形网格的数学核心，所有坐标操作和网格生成的核心。

| 方法 | 功能 |
|------|------|
| `__init__(hex_size, orientation, origin)` | 初始化网格参数（边长、朝向、原点） |
| `create_hex(q, r, s)` | 创建立方体坐标 |
| `hex_add(a, b)` / `hex_subtract(a, b)` | 坐标加减法 |
| `hex_rotate_left(a)` / `hex_rotate_right(a)` | 坐标旋转 60° |
| `get_hex_direction(direction)` | 获取 6 方向偏移量 |
| `get_hex_neighbor(hex, direction)` | 获取相邻六边形 |
| `get_hex_length(hex)` / `get_hex_distance(a, b)` | 距离计算 |
| `hex_round(hex)` | 浮点坐标取整 |
| `hex_lerp(a, b, t)` | 线性插值 |
| `hex_linedraw(a, b)` | 路径绘制 |
| `qoffset_from_cube(...)` / `roffset_from_cube(...)` | 偏移坐标转换 |
| `hex_to_pixel(hex)` / `pixel_to_hex(pixel)` | 六边形 ↔ 像素坐标 |
| `get_hex_corners(hex)` | 获取 6 个顶点 |
| `create_staggered_grid(col_range, row_range)` | 交错类矩形网格 |
| `create_hex_grid_hexagonal(N)` | 正六边形排布网格 |
| `get_hex_ring(radius)` | 单层六边形环 |

### `HexGridVisualizer` — 六边形网格可视化类

基于 matplotlib 的网格可视化。

| 方法 | 功能 |
|------|------|
| `__init__(hex_size, orientation, origin)` | 初始化可视化器 |
| `set_grid(grid_hexes)` | 设置要绘制的网格 |
| `set_hex_color(hex, color)` | 设置单个颜色 |
| `batch_set_color(color_map)` | 批量设置颜色 |
| `toggle_coord_display(show)` | 开关坐标标签 |
| `set_coord_type(type)` | 设置坐标类型 |
| `draw(title)` | 绘制网格 |
| `draw_hexagonal_grid(N, ...)` | 绘制正六边形网格 |
| `draw_staggered_grid(col_range, row_range, ...)` | 绘制交错网格 |

## 工具函数

| 函数 | 功能 |
|------|------|
| `create_hex_polygon(center, cell_width, theta)` | 创建 Shapely 六边形多边形 |
| `save_to_dxf(hex_all, filename, layer_name)` | 合并导出 DXF |
| `save_multi_dxf(hex_groups, filename, layer_name)` | 分组导出 DXF（多图层） |
| `read_and_display_dxf_matplotlib(filename)` | 读取并显示 DXF |

## 快速开始

```python
from mesh_grid.hex_grid import HexLib, HexGridVisualizer

# 1. 创建六边形网格
lib = HexLib(hex_size=20, orientation="pointy")
grid = lib.create_staggered_grid((0, 5), (0, 4))

# 2. 可视化
viz = HexGridVisualizer(hex_size=20, orientation="pointy")
viz.set_grid(grid)
viz.draw()

# 3. 导出 DXF
from mesh_grid.hex_grid import create_hex_polygon, save_to_dxf
hex_polys = [create_hex_polygon(lib.hex_to_pixel(h), 20) for h in grid]
save_to_dxf(hex_polys, "output.dxf")
```

## 坐标系统

使用**立方体坐标系** `(q, r, s)`，满足 `q + r + s = 0`。

- `q` — 列方向（X 轴映射）
- `r` — 行方向（Y 轴映射）
- `s` — 冗余坐标（`s = -q - r`）

### 朝向说明

- **Pointy-top**（尖向）：六边形尖头朝上，行影响列偏移
- **Flat-top**（扁向）：六边形平头朝上，列影响行偏移
