# -*- coding: utf-8 -*-
"""
三角形网格核心算法库
===================
提供三角形网格的坐标计算、网格生成、可视化、空间分析等功能。

函数分类:
    几何计算: equilateral_triangle_vertices, build_triangle_lattice
    坐标转换: pos_to_xy, xy_to_pos, path_loc_to_xy
    可视化: plot_tri_color, plot_triangle_grid
    空间分析: find_different_points, find_corner_points,
              is_above_segment, select_above, select_below,
              point_in_polygon, select_inside
    路径规划: shortest_path
    工具函数: line_cal, test_triangle_grid

@author: PC
"""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from matplotlib.collections import PolyCollection
from typing import Tuple, List, Dict, Union, Optional
from tqdm import tqdm
import matplotlib

matplotlib.rc("font", family='Microsoft YaHei')


def find_different_points(P1, P2, eps=1e-9):
    """
    筛选出 P1 中与 P2 所有点在误差范围内不相等的点

    参数:
        P1: numpy 数组，形状为 (N, D)
        P2: numpy 数组，形状为 (M, D)
        eps: 允许的绝对误差阈值（默认 1e-9）

    返回:
        P3: numpy 数组，形状为 (K, D)，P1 中与 P2 所有点都不同的点
    """
    P1 = np.atleast_2d(P1)
    P2 = np.atleast_2d(P2)

    errors = np.sum((P1[:, np.newaxis, :] - P2) ** 2, axis=2)
    is_equal = np.any(errors < eps ** 2, axis=1)
    P3 = P1[~is_equal]
    return P3


def equilateral_triangle_vertices(center: Tuple[float, float],
                                 a: float,
                                 theta: float = 0) -> np.ndarray:
    """
    计算等边三角形的三个顶点坐标

    参数:
        center: 三角形中心坐标 (x, y)
        a: 三角形边长
        theta: 旋转角度（度），默认 0 度（朝上）

    返回:
        3x2 的 numpy 数组，包含三个顶点的 (x, y) 坐标
    """
    R = a / np.sqrt(3)  # 中心到顶点的距离
    base_angles = np.deg2rad([90, 210, 330])  # 基础角度（朝上三角形）
    rot = np.radians(theta)  # 旋转角度（弧度）
    x = R * np.cos(base_angles + rot) + center[0]
    y = R * np.sin(base_angles + rot) + center[1]
    return np.column_stack((x, y))


def plot_tri_color(center: Tuple[float, float],
                  a: float,
                  theta: float = 0,
                  color: str = 'black') -> Polygon:
    """
    生成带颜色的三角形多边形对象

    参数:
        center: 三角形中心坐标 (x, y)
        a: 三角形边长
        theta: 旋转角度（度）
        color: 填充和边框颜色

    返回:
        matplotlib 的 Polygon 对象
    """
    vertices = equilateral_triangle_vertices(center, a, theta)
    return Polygon(
        vertices,
        facecolor=color,
        edgecolor=color,
        linewidth=2
    )


def equilateral_triangles_batch(centers: np.ndarray, a: float, theta: float = 0) -> np.ndarray:
    """向量化：批量计算等边三角形的顶点坐标

    利用 numpy 广播一次性生成所有三角形的顶点坐标。

    参数:
        centers: numpy 数组，形状 (N, 2)，每行 (cx, cy) 为中心坐标
        a: 三角形边长
        theta: 旋转角度（度），默认 0 度（朝上）

    返回:
        numpy 数组，形状 (N, 3, 2) — N 个三角形，每个 3 个顶点 (x, y)
    """
    R = a / np.sqrt(3)
    base_angles = np.deg2rad([90, 210, 330])
    rot = np.radians(theta)
    angles = base_angles + rot  # (3,)

    # centers: (N, 2), 广播到 (N, 3, 2)
    cx = centers[:, 0:1]  # (N, 1)
    cy = centers[:, 1:2]  # (N, 1)

    x = cx + R * np.cos(angles[np.newaxis, :])  # (N, 3)
    y = cy + R * np.sin(angles[np.newaxis, :])  # (N, 3)

    return np.stack([x, y], axis=-1)  # (N, 3, 2)


def build_triangle_lattice(row_range: Tuple[int, int],
                          col_range: Tuple[int, int],
                          a: float,
                          offset: Tuple[float, float] = (0.0, 0.0),
                          theta: float = 0.0) -> Tuple[
                              np.ndarray,
                              np.ndarray,
                              np.ndarray,
                              Dict[Tuple[int, int], Tuple[float, float]],
                              Dict[Tuple[int, int], Tuple[float, float]]]:
    """
    生成三角形网格结构数据（向量化版本）

    使用 numpy 网格广播替代逐格双重 for 循环，大幅提升大网格生成性能。

    参数:
        row_range: 行号范围 (start_row, end_row)，包含端点
        col_range: 列号范围 (start_col, end_col)，包含端点
        a: 三角形边长
        offset: 网格整体偏移量 (dx, dy)
        theta: 旋转角度（度）

    返回:
        triangles: numpy 数组，形状 (N, 3, 2)，所有朝上三角形顶点
        centers_up: numpy 数组，形状 (N, 2)，朝上三角形中心坐标
        centers_dn: numpy 数组，形状 (N, 2)，朝下三角形中心坐标
        pos_to_center_up: 朝上三角形位置坐标到中心坐标的映射
        pos_to_center_dn: 朝下三角形位置坐标到中心坐标的映射
    """
    h = a * np.sqrt(3) / 2  # 三角形高
    start_row, end_row = row_range
    start_col, end_col = col_range

    # 用 numpy 网格广播生成所有 (r, c) 组合
    rows = np.arange(start_row, end_row + 1, dtype=float)
    cols = np.arange(start_col, end_col + 1, dtype=float)
    RR, CC = np.meshgrid(rows, cols, indexing='ij')  # (NR, NC)

    # 朝上三角形中心
    cx_up = offset[0] + CC * a + (RR % 2) * (a / 2)   # (NR, NC)
    cy_up = offset[1] + RR * h                          # (NR, NC)
    centers = np.stack([cx_up, cy_up], axis=-1).reshape(-1, 2)  # (N, 2)

    # 向量化批量顶点计算
    triangles = equilateral_triangles_batch(centers, a, theta)  # (N, 3, 2)

    # 朝下三角形中心
    centers_dn = centers.copy()
    centers_dn[:, 1] -= h * 2 / 3

    # 构建位置映射字典
    pos_to_center_up: Dict[Tuple[int, int], Tuple[float, float]] = {}
    pos_to_center_dn: Dict[Tuple[int, int], Tuple[float, float]] = {}
    idx = 0
    for r in range(start_row, end_row + 1):
        for c in range(start_col, end_col + 1):
            pos_to_center_up[(r, c)] = (float(cx_up[r - start_row, c - start_col]),
                                        float(cy_up[r - start_row, c - start_col]))
            pos_to_center_dn[(r, c)] = (float(centers_dn[idx, 0]),
                                        float(centers_dn[idx, 1]))
            idx += 1

    return triangles, centers, centers_dn, pos_to_center_up, pos_to_center_dn


def pos_to_xy(row_range: Tuple[int, int],
             col_range: Tuple[int, int],
             a: float,
             r: int,
             c: int,
             triangle_type: str = 'up',
             offset: Tuple[float, float] = (0.0, 0.0)) -> Tuple[float, float]:
    """
    将位置坐标 (r, c) 转换为实际 XY 坐标

    注意: 函数内部使用固定偏移 [a/2, h - a/sqrt(3)]
          以对齐三角形网格中心，参数 offset 仅保留接口兼容性。

    参数:
        row_range: 行号范围 (start_row, end_row)
        col_range: 列号范围 (start_col, end_col)
        a: 三角形边长
        r: 行号
        c: 列号
        triangle_type: 三角形类型，'up'（朝上）或 'down'（朝下）
        offset: 网格偏移量（保留参数，内部使用固定对齐偏移）

    返回:
        三角形中心的 (x, y) 坐标

    异常:
        ValueError: 行号或列号超出范围，或三角形类型无效
    """
    start_row, end_row = row_range
    start_col, end_col = col_range

    # 范围校验
    if not (start_row <= r <= end_row):
        raise ValueError(f"行号 r={r} 超出范围 [{start_row}, {end_row}]")
    if not (start_col <= c <= end_col):
        raise ValueError(f"列号 c={c} 超出范围 [{start_col}, {end_col}]")

    h = a * np.sqrt(3) / 2  # 三角形高
    # 固定对齐偏移（使网格原点与实际位置对齐）
    _ox, _oy = a / 2, h - a / np.sqrt(3)

    if triangle_type == 'up':
        x = _ox + c * a + (r % 2) * (a / 2)
        y = _oy + r * h
    elif triangle_type == 'down':
        x = _ox + c * a + (r % 2) * (a / 2)
        y = _oy + r * h - h * 2 / 3
    else:
        raise ValueError("triangle_type 必须是 'up' 或 'down'")

    return (x, y)


def xy_to_pos(row_range: Tuple[int, int],
             col_range: Tuple[int, int],
             a: float,
             x: float,
             y: float,
             triangle_type: str = 'up',
             offset: Tuple[float, float] = (0.0, 0.0)) -> Tuple[int, int]:
    """
    将 XY 坐标转换为位置坐标 (r, c)

    参数:
        row_range: 行号范围 (start_row, end_row)
        col_range: 列号范围 (start_col, end_col)
        a: 三角形边长
        x: X 坐标
        y: Y 坐标
        triangle_type: 三角形类型，'up'（朝上）或 'down'（朝下）
        offset: 网格偏移量

    返回:
        位置坐标 (r, c)
    """
    start_row, end_row = row_range
    start_col, end_col = col_range
    h = a * np.sqrt(3) / 2  # 三角形高

    # 去除偏移量影响
    x -= offset[0]
    y -= offset[1]

    if triangle_type == 'up':
        r = int(round(y / h))
        c = int(round(x / a)) if r % 2 == 0 else int(round((x - a / 2) / a))
    elif triangle_type == 'down':
        adjusted_y = y + (2 * h / 3)  # 转换为对应朝上三角形的 y 坐标
        r = int(round(adjusted_y / h))
        c = int(round(x / a)) if r % 2 == 0 else int(round((x - a / 2) / a))
    else:
        raise ValueError("triangle_type 必须是 'up' 或 'down'")

    # 限制在有效范围内
    r = max(start_row, min(r, end_row))
    c = max(start_col, min(c, end_col))

    return (r, c)


def _build_down_triangle_verts(row_range, col_range, a, offset, theta):
    """构建朝下三角形的顶点数组（向量化版本，修复右侧重叠）

    返回:
        np.ndarray: (M, 3, 2) — 有效朝下三角形的顶点
    """
    from itertools import product
    start_row, end_row = row_range
    start_col, end_col = col_range
    h = a * np.sqrt(3) / 2

    dn_centers = []
    for r in range(start_row, end_row):
        for c in range(start_col, end_col + 1):
            if r % 2 == 0 and c >= end_col:
                continue  # 偶数行最后一列无朝下三角形
            if r % 2 == 0:
                cx = offset[0] + c * a + a / 2
            else:
                cx = offset[0] + c * a
            cy = offset[1] + r * h + h / 3
            dn_centers.append((cx, cy))

    if not dn_centers:
        return np.empty((0, 3, 2))
    return equilateral_triangles_batch(np.array(dn_centers), a, theta + 180)


def plot_triangle_grid(row_range: Tuple[int, int],
                      col_range: Tuple[int, int],
                      a: float = 1.0,
                      offset: Tuple[float, float] = (0.0, 0.0),
                      theta: float = 0.0,
                      show_labels: bool = True,
                      show_points: bool = True,
                      fill_colors_up: Optional[list] = None,
                      fill_colors_down: Optional[list] = None,
                      coord_auto_hide_threshold: int = 500,
                      edgecolor: str = 'black',
                      linewidth: float = 1.0) -> Tuple[plt.Figure, plt.Axes]:
    """
    向量化绘制三角形网格 — 使用 PolyCollection 替代逐格 Polygon

    性能提升：从 O(N) 个独立 Polygon 对象降为 O(1) 个 PolyCollection。

    参数:
        row_range: 行号范围 (start_row, end_row)
        col_range: 列号范围 (start_col, end_col)
        a: 三角形边长
        offset: 网格偏移量
        theta: 旋转角度（度）
        show_labels: 是否显示位置坐标标签
        show_points: 是否显示中心标记点
        fill_colors_up: 朝上三角形颜色数组（长度 = 朝上三角形数），None 表示不填充
        fill_colors_down: 朝下三角形颜色数组，None 表示不填充
        coord_auto_hide_threshold: 网格数超过此阈值时自动隐藏坐标标签
        edgecolor: 边框颜色
        linewidth: 边框线宽

    返回:
        fig: 图形对象
        ax: 坐标轴对象
    """
    # 生成网格数据
    triangles, centers_up, centers_dn, pos_to_center_up, pos_to_center_dn = \
        build_triangle_lattice(row_range, col_range, a, offset, theta)

    start_row, end_row = row_range
    start_col, end_col = col_range
    h = a * np.sqrt(3) / 2

    # 创建图形
    fig, ax = plt.subplots(figsize=(10, 8))

    # 朝下三角形顶点
    dn_verts = _build_down_triangle_verts(row_range, col_range, a, offset, theta)
    n_up = len(triangles)
    n_dn = len(dn_verts)

    # === 朝上三角形 PolyCollection ===
    fc_up = fill_colors_up if fill_colors_up is not None else 'none'
    ec_up = edgecolor if fill_colors_up is None else edgecolor
    up_poly = PolyCollection(triangles, facecolors=fc_up, edgecolors=ec_up,
                             linewidths=linewidth, closed=True)
    ax.add_collection(up_poly)

    # === 朝下三角形 PolyCollection ===
    if n_dn > 0:
        fc_dn = fill_colors_down if fill_colors_down is not None else 'none'
        ec_dn = edgecolor if fill_colors_down is None else edgecolor
        dn_poly = PolyCollection(dn_verts, facecolors=fc_dn, edgecolors=ec_dn,
                                 linewidths=linewidth, closed=True)
        ax.add_collection(dn_poly)

    # 标记中心和标签
    n_total = n_up + n_dn
    show_coord = show_points
    if show_coord and n_total > coord_auto_hide_threshold:
        show_coord = False

    if show_points:
        for (r, c), (x, y) in pos_to_center_up.items():
            ax.scatter(x, y, color='red', s=20, zorder=5)
            if show_labels and show_coord:
                ax.annotate(f'({r},{c})', (x, y), xytext=(3, 3),
                           textcoords='offset points', fontsize=6)

        for (r, c), (x, y) in pos_to_center_dn.items():
            valid = (r <= end_row) and (
                (r % 2 == 1) or (r % 2 == 0 and c < end_col)
            )
            if valid:
                ax.scatter(x, y, color='orange', s=20, zorder=5)
                if show_labels and show_coord:
                    ax.annotate(f'd({r},{c})', (x, y), xytext=(3, 3),
                               textcoords='offset points', fontsize=6, color='orange')

    # 设置坐标轴
    if n_up > 0:
        min_x = triangles[..., 0].min()
        max_x = triangles[..., 0].max()
        min_y = triangles[..., 1].min()
        max_y = triangles[..., 1].max()
    else:
        min_x, max_x, min_y, max_y = 0, 1, 0, 1

    ax.set_aspect('equal')
    ax.set_xlim(min_x - a, max_x + a)
    ax.set_ylim(min_y - h, max_y + h)
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_title(f'三角形网格 [{start_row},{end_row}]×[{start_col},{end_col}]')
    ax.grid(True, linestyle='--', alpha=0.7)

    return fig, ax


def color_triangles(ax: plt.Axes, up_centers: np.ndarray, dn_centers: np.ndarray,
                    a: float, theta: float = 0,
                    up_colors: Optional[list] = None,
                    dn_colors: Optional[list] = None,
                    cmap: str = 'viridis',
                    vmin: Optional[float] = None,
                    vmax: Optional[float] = None,
                    edgecolor: str = 'black',
                    linewidth: float = 1.0) -> Tuple[PolyCollection, PolyCollection]:
    """向量化涂色：在已有坐标轴上绘制带颜色的三角形网格

    所有三角形通过 PolyCollection 一次性绘制，支持数值数组自动 cmap 映射。

    参数:
        ax: matplotlib Axes 对象
        up_centers: 朝上三角形中心坐标数组 (N_up, 2)
        dn_centers: 朝下三角形中心坐标数组 (N_dn, 2)
        a: 三角形边长
        theta: 旋转角度（度）
        up_colors: 朝上三角形颜色数组（None 表示不填充）
        dn_colors: 朝下三角形颜色数组（None 表示不填充）
        cmap: 数值映射的 colormap 名称（默认 'viridis'）
        vmin, vmax: 数值映射范围
        edgecolor: 边框颜色
        linewidth: 边框线宽

    返回:
        (up_poly, dn_poly): 两个 PolyCollection 对象，可用于后续更新颜色
    """
    up_verts = equilateral_triangles_batch(up_centers, a, theta) if len(up_centers) > 0 else np.empty((0, 3, 2))
    dn_verts = equilateral_triangles_batch(dn_centers, a, theta + 180) if len(dn_centers) > 0 else np.empty((0, 3, 2))

    def _resolve_colors(colors, n):
        if colors is None:
            return 'none'
        colors = np.asarray(colors)
        if colors.ndim == 1 and np.issubdtype(colors.dtype, np.number):
            _vmin = vmin if vmin is not None else colors.min()
            _vmax = vmax if vmax is not None else colors.max()
            norm = plt.Normalize(_vmin, _vmax)
            mapper = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
            return mapper.to_rgba(colors)
        return colors

    up_fc = _resolve_colors(up_colors, len(up_verts))
    dn_fc = _resolve_colors(dn_colors, len(dn_verts))

    up_poly = PolyCollection(up_verts, facecolors=up_fc, edgecolors=edgecolor,
                             linewidths=linewidth, closed=True)
    dn_poly = PolyCollection(dn_verts, facecolors=dn_fc, edgecolors=edgecolor,
                             linewidths=linewidth, closed=True)

    ax.add_collection(up_poly)
    ax.add_collection(dn_poly)

    return up_poly, dn_poly


def find_corner_points(points: Union[List[Tuple[float, float]], np.ndarray]) -> np.ndarray:
    """
    找出点集中的四个角落点（左下、右下、左上、右上）

    参数:
        points: 点集，格式为 [(x1,y1), (x2,y2), ...] 或二维数组

    返回:
        4x2 的 numpy 数组，按顺序 [左下, 右下, 左上, 右上]

    异常:
        ValueError: 点集数量不足 4 个
    """
    points = np.array(points)
    if len(points) < 4:
        raise ValueError("点集数量至少需要 4 个点")

    # 左下顶点：y 最小，x 最小
    min_y_mask = points[:, 1] == np.min(points[:, 1])
    min_y_points = points[min_y_mask]
    bottom_left = min_y_points[np.argmin(min_y_points[:, 0])]

    # 右下顶点：y 最小，x 最大
    bottom_right = min_y_points[np.argmax(min_y_points[:, 0])]

    # 左上顶点：y 最大，x 最小
    max_y_mask = points[:, 1] == np.max(points[:, 1])
    max_y_points = points[max_y_mask]
    top_left = max_y_points[np.argmin(max_y_points[:, 0])]

    # 右上顶点：y 最大，x 最大
    top_right = max_y_points[np.argmax(max_y_points[:, 0])]

    return np.array([bottom_left, bottom_right, top_left, top_right])


def shortest_path(start: Tuple[int, int],
                 end: Tuple[int, int],
                 first_direction: str = 'x') -> np.ndarray:
    """
    生成网格中两点间的最短路径（曼哈顿路径）

    支持多种优先方向策略:
        - 'x': 先沿列方向移动，再沿行方向移动
        - 'y': 先沿行方向移动，再沿列方向移动
        - 'xy': 斜向移动优先，适用于三角形网格坐标方向相反的情况
        - 'xxy': 先沿列方向到终点行/列对齐，再斜向移动

    参数:
        start: 起始位置坐标 (r, c)
        end: 终点位置坐标 (r, c)
        first_direction: 优先移动方向，'x' / 'y' / 'xy' / 'xxy'

    返回:
        路径点数组，形状为 (N, 2)，包含所有路径点的 (r, c) 坐标

    异常:
        ValueError: 无效的优先方向
    """
    dx = end[1] - start[1]  # 列方向差
    dy = end[0] - start[0]  # 行方向差

    step_x = 1 if dx > 0 else -1 if dx < 0 else 0
    step_y = 1 if dy > 0 else -1 if dy < 0 else 0

    path = [start]
    current_r, current_c = start

    if first_direction.lower() == 'xxy':
        # 先沿列方向移动到与终点行对齐，再斜向移动
        t1 = np.min([abs(dx), abs(dy)])
        for _ in range(abs(abs(dx) - abs(dy))):
            current_c += step_x
            path.append((current_r, current_c))
        for _ in range(t1):
            current_c += step_x
            current_r += step_y
            path.append((current_r, current_c))
    elif first_direction.lower() == 'xy' or (dx > 0 and dy < 0) or (dx < 0 and dy > 0):
        # 斜向移动优先
        t1 = np.min([abs(dx), abs(dy)])
        t2 = np.max([abs(dx), abs(dy)])
        for _ in range(t1):
            current_c += step_x
            current_r += step_y
            path.append((current_r, current_c))
        for _ in range(t2 - t1):
            if abs(dx) > abs(dy):
                current_c += step_x
            elif abs(dx) < abs(dy):
                current_r += step_y
            path.append((current_r, current_c))
    elif first_direction.lower() == 'x':
        # 先列后行
        for _ in range(abs(dx)):
            current_c += step_x
            path.append((current_r, current_c))
        for _ in range(abs(dy)):
            current_r += step_y
            path.append((current_r, current_c))
    elif first_direction.lower() == 'y':
        # 先行后列
        for _ in range(abs(dy)):
            current_r += step_y
            path.append((current_r, current_c))
        for _ in range(abs(dx)):
            current_c += step_x
            path.append((current_r, current_c))
    else:
        raise ValueError("无效的优先方向，请传入 'x', 'y', 'xy' 或 'xxy'")

    return np.array(path)


def path_loc_to_xy(path: np.ndarray, a: float) -> np.ndarray:
    """
    将路径的位置坐标转换为 XY 坐标

    参数:
        path: 路径位置坐标数组，形状为 (N, 2)，每个元素为 (r, c)
        a: 三角形边长

    返回:
        XY 坐标数组，形状为 (N, 2)
    """
    e1 = (a, 0)                   # 基向量 1（列方向）
    e2 = (a / 2, a / 2 * np.sqrt(3))  # 基向量 2（行方向）
    x = path[:, 1] * e1[0] + path[:, 0] * e2[0]
    y = path[:, 0] * e2[1]
    return np.column_stack((x, y))


def is_above_segment(point: Tuple[float, float],
                    seg_start: Tuple[float, float],
                    seg_end: Tuple[float, float]) -> bool:
    """
    判断点是否在直线段的上方

    参数:
        point: 待判断点 (x, y)
        seg_start: 线段起点 (x1, y1)
        seg_end: 线段终点 (x2, y2)

    返回:
        布尔值，True 表示点在线段上方
    """
    x, y = point
    x1, y1 = seg_start
    x2, y2 = seg_end

    if x2 == x1:  # 垂直线段
        return x > x1

    # 计算线段方程 y = slope * x + intercept
    slope = (y2 - y1) / (x2 - x1)
    intercept = y1 - slope * x1

    # 根据线段方向判断上下
    if x1 < x2:
        return y > (slope * x + intercept)
    else:
        return y < (slope * x + intercept)


def select_above(points: Union[List[Tuple[float, float]], np.ndarray],
                polyline: Union[List[Tuple[float, float]], np.ndarray]) -> np.ndarray:
    """
    筛选出位于折线所有线段上方的点

    参数:
        points: 待筛选点集
        polyline: 折线点集，至少包含 2 个点

    返回:
        筛选后的点集数组

    异常:
        ValueError: 折线点数量不足
    """
    if len(polyline) < 2:
        raise ValueError("折线至少需要 2 个点")

    points = np.array(points)
    polyline = np.array(polyline)
    above_points = []

    for point in points:
        is_above = True
        for i in range(len(polyline) - 1):
            if not is_above_segment(point, polyline[i], polyline[i + 1]):
                is_above = False
                break
        if is_above:
            above_points.append(point)

    return np.array(above_points)


def select_below(points: Union[List[Tuple[float, float]], np.ndarray],
                polyline: Union[List[Tuple[float, float]], np.ndarray]) -> np.ndarray:
    """
    筛选出位于折线所有线段下方的点

    参数:
        points: 待筛选点集
        polyline: 折线点集，至少包含 2 个点

    返回:
        筛选后的点集数组

    异常:
        ValueError: 折线点数量不足
    """
    if len(polyline) < 2:
        raise ValueError("折线至少需要 2 个点")

    points = np.array(points)
    polyline = np.array(polyline)
    below_points = []

    for point in points:
        is_below = True
        for i in range(len(polyline) - 1):
            if is_above_segment(point, polyline[i], polyline[i + 1]):
                is_below = False
                break
        if is_below:
            below_points.append(point)

    return np.array(below_points)


def point_in_polygon(point: Tuple[float, float],
                    polygon: Union[List[Tuple[float, float]], np.ndarray]) -> bool:
    """
    判断点是否在多边形内部（射线法）

    参数:
        point: 待判断点 (x, y)
        polygon: 多边形顶点数组，至少包含 3 个点

    返回:
        布尔值，True 表示点在多边形内部
    """
    x, y = point
    polygon = np.array(polygon)
    n = len(polygon)
    inside = False

    for i in range(n):
        j = (i + 1) % n
        xi, yi = polygon[i]
        xj, yj = polygon[j]

        # 检查射线与边的交点
        if (yi > y) != (yj > y):
            x_intersect = ((y - yi) * (xj - xi)) / (yj - yi + 1e-7) + xi
            if x < x_intersect:
                inside = not inside

    return inside


def select_inside(points: Union[List[Tuple[float, float]], np.ndarray],
                 polygon: Union[List[Tuple[float, float]], np.ndarray]) -> np.ndarray:
    """
    筛选出位于多边形内部的点

    参数:
        points: 待筛选点集
        polygon: 多边形顶点数组，至少包含 3 个点

    返回:
        筛选后的点集数组

    异常:
        ValueError: 多边形顶点数量不足
    """
    if len(polygon) < 3:
        raise ValueError("多边形至少需要 3 个顶点")

    points = np.array(points)
    inside_points = [p for p in points if point_in_polygon(p, polygon)]
    return np.array(inside_points)


def line_cal(point, slope, known_value, is_x=True):
    """
    根据直线上已知点、斜率和另一点的已知坐标，计算未知坐标

    参数:
        point: tuple (x0, y0)，直线上已知点的坐标
        slope: float，直线的斜率 (k)
        known_value: float，另一点已知的坐标值（X 或 Y）
        is_x: bool，若为 True 表示已知 X 求 Y，False 表示已知 Y 求 X

    返回:
        计算得到的未知坐标值，若无法计算则返回 None
    """
    x0 = point[0]
    y0 = point[1]
    try:
        if is_x:
            # 已知 X，求 Y：y = k * (x - x0) + y0
            return slope * (known_value - x0) + y0
        else:
            # 已知 Y，求 X：x = (y - y0) / k + x0
            if slope == 0:
                raise ValueError("当已知 Y 值时，斜率不能为 0（水平直线无法通过 Y 求 X）")
            return (known_value - y0) / slope + x0
    except ZeroDivisionError:
        print("错误：计算过程中出现除以零的情况")
        return None
    except Exception as e:
        print(f"计算出错: {str(e)}")
        return None


def test_triangle_grid():
    """测试三角形网格生成和坐标转换功能"""
    row_range = (-2, 2)
    col_range = (-1, 3)
    a = 1.0

    print(f"测试三角形网格 [{row_range[0]},{row_range[1]}]行×[{col_range[0]},{col_range[1]}]列")
    print("=" * 60)

    # 测试位置坐标到 XY 坐标的转换
    print("位置坐标到 XY 坐标的转换测试：")
    for r in range(row_range[0], row_range[1] + 1):
        for c in range(col_range[0], col_range[1] + 1):
            xy_up = pos_to_xy(row_range, col_range, a, r, c, 'up')
            xy_down = pos_to_xy(row_range, col_range, a, r, c, 'down')
            print(f"位置({r},{c}) - 朝上: {xy_up}, 朝下: {xy_down}")

    # 测试 XY 坐标到位置坐标的转换
    print("\nXY 坐标到位置坐标的转换测试：")
    test_points = [
        (-0.5, -np.sqrt(3), 'up'),        # (-2, -1)
        (0.0, -np.sqrt(3) / 2, 'up'),     # (-1, -1)
        (-0.5, 0, 'up'),                  # (0, -1)
        (0.0, np.sqrt(3) / 2, 'up'),      # (1, -1)
        (-0.5, np.sqrt(3), 'up'),         # (2, -1)
        (0.5, np.sqrt(3) / 6, 'down'),    # (-1, -1)
        (1.5, np.sqrt(3) / 6, 'down'),    # (-1, 0)
    ]

    for x, y, tri_type in test_points:
        pos = xy_to_pos(row_range, col_range, a, x, y, tri_type)
        print(f"XY({x:.2f},{y:.2f}) - {tri_type} -> 位置{pos}")

    # 生成可视化
    print("\n生成三角形网格可视化...")
    fig, ax = plot_triangle_grid(row_range, col_range, a, show_labels=True)
    plt.show()
