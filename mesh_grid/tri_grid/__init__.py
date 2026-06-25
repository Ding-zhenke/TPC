# -*- coding: utf-8 -*-
"""
mesh_grid.tri_grid — 三角形网格算法库
======================================
三角形网格的生成、坐标转换、可视化与空间分析功能。

导出函数:
    几何计算: equilateral_triangle_vertices, build_triangle_lattice
    坐标转换: pos_to_xy, xy_to_pos, path_loc_to_xy
    可视化: plot_tri_color, plot_triangle_grid
    空间分析: find_different_points, find_corner_points,
              is_above_segment, select_above, select_below,
              point_in_polygon, select_inside
    路径规划: shortest_path
    工具: line_cal, test_triangle_grid

快速开始:
    >>> from mesh_grid.tri_grid import build_triangle_lattice, plot_triangle_grid
    >>> triangles, centers_up, centers_dn, _, _ = build_triangle_lattice((0, 3), (0, 4), 1.0)
    >>> fig, ax = plot_triangle_grid((0, 3), (0, 4), 1.0)

@author: PC
"""

from mesh_grid.tri_grid.core import (
    find_different_points,
    equilateral_triangle_vertices,
    equilateral_triangles_batch,
    plot_tri_color,
    build_triangle_lattice,
    pos_to_xy,
    xy_to_pos,
    plot_triangle_grid,
    color_triangles,
    find_corner_points,
    shortest_path,
    path_loc_to_xy,
    is_above_segment,
    select_above,
    select_below,
    point_in_polygon,
    select_inside,
    line_cal,
    test_triangle_grid,
)

__all__ = [
    "find_different_points",
    "equilateral_triangle_vertices",
    "equilateral_triangles_batch",
    "plot_tri_color",
    "build_triangle_lattice",
    "pos_to_xy",
    "xy_to_pos",
    "plot_triangle_grid",
    "color_triangles",
    "find_corner_points",
    "shortest_path",
    "path_loc_to_xy",
    "is_above_segment",
    "select_above",
    "select_below",
    "point_in_polygon",
    "select_inside",
    "line_cal",
    "test_triangle_grid",
]
