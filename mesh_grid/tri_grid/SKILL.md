---
description: 三角形网格核心算法库 — 网格生成、坐标转换、可视化、空间分析
applyTo: "**/*.py"
---

# mesh_grid.tri_grid — 三角形网格算法库

## 概述
提供等边三角形网格的生成、坐标转换、可视化和空间分析功能。支持朝上/朝下两种三角形类型。

## 核心函数

### 网格生成
- `build_triangle_lattice(row_range, col_range, a, offset, theta)` — 生成完整网格数据
- `equilateral_triangle_vertices(center, a, theta)` — 计算三角形顶点

### 坐标转换
- `pos_to_xy(row_range, col_range, a, r, c, triangle_type, offset)` — (r,c) → XY
- `xy_to_pos(row_range, col_range, a, x, y, triangle_type, offset)` — XY → (r,c)
- `path_loc_to_xy(path, a)` — 路径坐标转换

### 可视化
- `plot_triangle_grid(row_range, col_range, a, ...)` — 绘制完整网格
- `plot_tri_color(center, a, theta, color)` — 带颜色的 Polygon

### 空间分析
- `find_corner_points(points)` — 找出四个角点
- `point_in_polygon(point, polygon)` — 射线法判断点在多边形内
- `select_above/below/inside` — 空间筛选

### 路径规划
- `shortest_path(start, end, first_direction)` — 曼哈顿路径（支持 'x', 'y', 'xy', 'xxy'）

## 示例
```python
from mesh_grid.tri_grid import build_triangle_lattice
triangles, centers_up, centers_dn, _, _ = build_triangle_lattice((0, 3), (0, 4), 1.0)
```
