# mesh_grid.tri_grid — 三角形网格算法库

## 概述

`mesh_grid.tri_grid` 是 TPC 项目的三角形网格核心算法库，提供等边三角形网格的生成、坐标转换、可视化和空间分析功能。支持朝上/朝下两种三角形类型的完整网格系统。

## 函数分类说明

### 几何计算

| 函数 | 功能 |
|------|------|
| `equilateral_triangle_vertices(center, a, theta)` | 计算等边三角形的三个顶点坐标 |
| `build_triangle_lattice(row_range, col_range, a, offset, theta)` | 生成完整的三角形网格结构数据 |

### 坐标转换

| 函数 | 功能 |
|------|------|
| `pos_to_xy(row_range, col_range, a, r, c, triangle_type, offset)` | 位置坐标 (r,c) → 实际 XY 坐标 |
| `xy_to_pos(row_range, col_range, a, x, y, triangle_type, offset)` | XY 坐标 → 位置坐标 (r,c) |
| `path_loc_to_xy(path, a)` | 路径位置坐标 → XY 坐标 |

### 可视化

| 函数 | 功能 |
|------|------|
| `plot_tri_color(center, a, theta, color)` | 生成带颜色的三角形 Polygon 对象 |
| `plot_triangle_grid(row_range, col_range, a, offset, theta, show_labels, show_points)` | 绘制三角形网格并标记中心 |

### 空间分析

| 函数 | 功能 |
|------|------|
| `find_different_points(P1, P2, eps)` | 筛选 P1 中与 P2 不同的点 |
| `find_corner_points(points)` | 找出点集的四个角点 |
| `is_above_segment(point, seg_start, seg_end)` | 判断点是否在线段上方 |
| `select_above(points, polyline)` | 筛选折线上方的点 |
| `select_below(points, polyline)` | 筛选折线下方的点 |
| `point_in_polygon(point, polygon)` | 判断点在多边形内（射线法） |
| `select_inside(points, polygon)` | 筛选多边形内部的点 |

### 路径规划

| 函数 | 功能 |
|------|------|
| `shortest_path(start, end, first_direction)` | 生成曼哈顿最短路径 |

### 工具

| 函数 | 功能 |
|------|------|
| `line_cal(point, slope, known_value, is_x)` | 直线方程计算 |
| `test_triangle_grid()` | 测试网格生成和坐标转换 |

## 快速开始

```python
from mesh_grid.tri_grid import build_triangle_lattice, plot_triangle_grid

# 1. 生成三角形网格
triangles, centers_up, centers_dn, pos_up, pos_dn = \
    build_triangle_lattice((0, 3), (0, 4), a=1.0)

# 2. 可视化
fig, ax = plot_triangle_grid((0, 3), (0, 4), a=1.0, show_labels=True)

# 3. 坐标转换
from mesh_grid.tri_grid import pos_to_xy, xy_to_pos
xy = pos_to_xy((0, 3), (0, 4), 1.0, r=2, c=3, triangle_type='up')
pos = xy_to_pos((0, 3), (0, 4), 1.0, xy[0], xy[1], triangle_type='up')
```

## 网格结构

三角形网格由两种三角形组成：

- **朝上三角形** (up)：中心标记为 `(r, c)`，红色
- **朝下三角形** (down)：中心标记为 `d(r, c)`，橙色

网格排布规则：
- 偶数行：朝上三角形和朝下三角形交替排列
- 奇数行：整体偏移半个列距

## 注意

- `pos_to_xy` 函数内部使用固定偏移 `[a/2, h - a/sqrt(3)]` 以对齐网格，参数 `offset` 仅保留接口兼容性
- `plot_triangle_grid` 已修复右侧朝下三角形重叠问题
