# -*- coding: utf-8 -*-
"""
六边形网格核心算法库
===================
提供六边形网格的坐标系统、网格生成、可视化和 DXF 导出功能。

核心类:
    HexLib — 六边形网格核心算法（坐标操作、网格生成、坐标转换）
    HexGridVisualizer — 基于 matplotlib 的六边形网格可视化

工具函数:
    create_hex_polygon — 创建 Shapely 六边形多边形
    save_to_dxf — 将合并后的六边形网格导出为 DXF
    save_multi_dxf — 将多组六边形分别导出为 DXF（多层）
    read_and_display_dxf_matplotlib — 读取并显示 DXF 文件

@author: PC
"""
from __future__ import division
from __future__ import print_function
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.path import Path
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
import collections
import numpy as np
from tqdm import tqdm

# 写入 dxf
from matplotlib.patches import RegularPolygon
import ezdxf
from ezdxf.addons.drawing import matplotlib as drawing
from ezdxf.addons.drawing.config import Configuration
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

# ===================== 基础数据结构定义 =====================
Point = collections.namedtuple("Point", ["x", "y"])
Hex = collections.namedtuple("Hex", ["q", "r", "s"])
OffsetCoord = collections.namedtuple("OffsetCoord", ["col", "row"])
DoubledCoord = collections.namedtuple("DoubledCoord", ["col", "row"])
Orientation = collections.namedtuple(
    "Orientation",
    ["f0", "f1", "f2", "f3", "b0", "b1", "b2", "b3", "start_angle"]
)
Layout = collections.namedtuple("Layout", ["orientation", "size", "origin"])


class HexLib:
    """六边形网格核心算法类"""

    # 标准朝向定义（遵循 Hex Grid Standard）
    LAYOUT_FLAT = Orientation(
        3.0 / 2.0, 0.0,
        np.sqrt(3.0) / 2.0, np.sqrt(3.0),
        2.0 / 3.0, 0.0,
        -1.0 / 3.0, np.sqrt(3.0) / 3.0,
        0.0
    )
    LAYOUT_POINTY = Orientation(
        np.sqrt(3.0), np.sqrt(3.0) / 2.0,
        0.0, 3.0 / 2.0,
        np.sqrt(3.0) / 3.0, -1.0 / 3.0,
        0.0, 2.0 / 3.0,
        0.5
    )

    EVEN = 1
    ODD = -1

    def __init__(self, hex_size=20, orientation="pointy", origin=(0, 0)):
        """初始化六边形网格参数

        Args:
            hex_size: int，六边形单元边长（像素）
            orientation: str，朝向类型（pointy / flat）
            origin: tuple，网格原点坐标 (x, y)
        """
        if orientation not in ["pointy", "flat"]:
            raise ValueError("orientation must be 'pointy' or 'flat'")

        self.hex_size = hex_size
        self.origin = Point(origin[0], origin[1])
        self.layout_type = orientation

        # 初始化朝向相关参数
        if orientation == "pointy":
            self.orientation = self.LAYOUT_POINTY
            self.x_step = hex_size * np.sqrt(3)
            self.y_step = hex_size * 1.5
        else:
            self.orientation = self.LAYOUT_FLAT
            self.x_step = hex_size * 1.5
            self.y_step = hex_size * np.sqrt(3)

        self.layout = Layout(
            self.orientation,
            Point(hex_size, hex_size),
            self.origin
        )

    # ===================== 基础坐标操作 =====================
    def create_hex(self, q, r, s=None):
        """创建有效的立方体六边形坐标

        Args:
            q: int/float，Q 轴坐标
            r: int/float，R 轴坐标
            s: int/float 可选，S 轴坐标（默认自动计算 s = -q - r）

        Returns:
            Hex: 立方体六边形坐标 (q, r, s)
        """
        if s is None:
            s = -q - r
        assert np.round(q + r + s) == 0, "Hex coordinates must satisfy q + r + s = 0"
        return Hex(q, r, s)

    def hex_add(self, a, b):
        """立方体坐标加法

        Args:
            a: Hex，被加数
            b: Hex，加数

        Returns:
            Hex: 坐标之和
        """
        return self.create_hex(a.q + b.q, a.r + b.r, a.s + b.s)

    def hex_subtract(self, a, b):
        """立方体坐标减法

        Args:
            a: Hex，被减数
            b: Hex，减数

        Returns:
            Hex: 坐标之差
        """
        return self.create_hex(a.q - b.q, a.r - b.r, a.s - b.s)

    def hex_rotate_left(self, a):
        """立方体坐标向左旋转60度

        Args:
            a: Hex，原始坐标

        Returns:
            Hex: 旋转后的坐标
        """
        return self.create_hex(-a.s, -a.q, -a.r)

    def hex_rotate_right(self, a):
        """立方体坐标向右旋转60度

        Args:
            a: Hex，原始坐标

        Returns:
            Hex: 旋转后的坐标
        """
        return self.create_hex(-a.r, -a.s, -a.q)

    # ===================== 邻居 / 距离计算 =====================
    def get_hex_direction(self, direction):
        """获取指定方向的偏移量

        Args:
            direction: int，方向索引 (0~5)
                      0=右, 1=右上, 2=左上, 3=左, 4=左下, 5=右下

        Returns:
            Hex: 该方向的单位偏移量
        """
        directions = [
            self.create_hex(1, 0, -1),   # 右
            self.create_hex(1, -1, 0),   # 右上
            self.create_hex(0, -1, 1),   # 左上
            self.create_hex(-1, 0, 1),   # 左
            self.create_hex(-1, 1, 0),   # 左下
            self.create_hex(0, 1, -1),   # 右下
        ]
        return directions[direction % 6]

    def get_hex_neighbor(self, hex_coord, direction):
        """获取相邻六边形坐标

        Args:
            hex_coord: Hex，当前六边形坐标
            direction: int，方向索引 (0~5)

        Returns:
            Hex: 相邻六边形的坐标
        """
        return self.hex_add(hex_coord, self.get_hex_direction(direction))

    def get_hex_length(self, hex_coord):
        """计算坐标到原点的曼哈顿距离

        Args:
            hex_coord: Hex，六边形坐标

        Returns:
            int: 到原点的距离（六边形网格步数）
        """
        return (abs(hex_coord.q) + abs(hex_coord.r) + abs(hex_coord.s)) // 2

    def get_hex_distance(self, a, b):
        """计算两个六边形的距离

        Args:
            a: Hex，第一个六边形
            b: Hex，第二个六边形

        Returns:
            int: 两个六边形之间的步数距离
        """
        return self.get_hex_length(self.hex_subtract(a, b))

    # ===================== 坐标取整 / 插值 =====================
    def hex_round(self, hex_coord):
        """浮点型立方体坐标取整为整数坐标

        Args:
            hex_coord: Hex，浮点型坐标

        Returns:
            Hex: 取整后的整数坐标
        """
        qi = int(np.round(hex_coord.q))
        ri = int(np.round(hex_coord.r))
        si = int(np.round(hex_coord.s))

        q_diff = abs(qi - hex_coord.q)
        r_diff = abs(ri - hex_coord.r)
        s_diff = abs(si - hex_coord.s)

        if q_diff > r_diff and q_diff > s_diff:
            qi = -ri - si
        elif r_diff > s_diff:
            ri = -qi - si
        else:
            si = -qi - ri

        return self.create_hex(qi, ri, si)

    def hex_lerp(self, a, b, t):
        """立方体坐标线性插值

        Args:
            a: Hex，起点坐标
            b: Hex，终点坐标
            t: float，插值参数 [0, 1]

        Returns:
            Hex: 插值后的浮点坐标
        """
        q = a.q * (1 - t) + b.q * t
        r = a.r * (1 - t) + b.r * t
        s = a.s * (1 - t) + b.s * t
        return self.create_hex(q, r, s)

    def hex_linedraw(self, a, b):
        """生成两点间的六边形路径

        使用微扰避免边界模糊，返回经过的所有六边形坐标。

        Args:
            a: Hex，起点
            b: Hex，终点

        Returns:
            list[Hex]: 路径上的六边形坐标列表
        """
        distance = self.get_hex_distance(a, b)
        a_nudge = self.create_hex(a.q + 1e-6, a.r + 1e-6, a.s - 2e-6)
        b_nudge = self.create_hex(b.q + 1e-6, b.r + 1e-6, b.s - 2e-6)

        path = []
        step = 1.0 / max(distance, 1)
        for i in range(distance + 1):
            path.append(self.hex_round(self.hex_lerp(a_nudge, b_nudge, step * i)))
        return path

    # ===================== 偏移坐标转换 =====================
    def qoffset_from_cube(self, offset_type, hex_coord):
        """立方体坐标转 Q 轴（列）偏移坐标

        Args:
            offset_type: int，EVEN(1) 或 ODD(-1)
            hex_coord: Hex，立方体坐标

        Returns:
            OffsetCoord: (col, row) 偏移坐标
        """
        if offset_type not in [self.EVEN, self.ODD]:
            raise ValueError("offset_type must be EVEN(1) or ODD(-1)")

        parity = hex_coord.q & 1
        col = hex_coord.q
        row = hex_coord.r + (hex_coord.q + offset_type * parity) // 2
        return OffsetCoord(col, row)

    def qoffset_to_cube(self, offset_type, offset_coord):
        """Q 轴偏移坐标转立方体坐标

        Args:
            offset_type: int，EVEN(1) 或 ODD(-1)
            offset_coord: OffsetCoord，(col, row) 偏移坐标

        Returns:
            Hex: 立方体坐标
        """
        if offset_type not in [self.EVEN, self.ODD]:
            raise ValueError("offset_type must be EVEN(1) or ODD(-1)")

        parity = offset_coord.col & 1
        q = offset_coord.col
        r = offset_coord.row - (offset_coord.col + offset_type * parity) // 2
        return self.create_hex(q, r)

    def roffset_from_cube(self, offset_type, hex_coord):
        """立方体坐标转 R 轴（行）偏移坐标

        Args:
            offset_type: int，EVEN(1) 或 ODD(-1)
            hex_coord: Hex，立方体坐标

        Returns:
            OffsetCoord: (col, row) 偏移坐标
        """
        if offset_type not in [self.EVEN, self.ODD]:
            raise ValueError("offset_type must be EVEN(1) or ODD(-1)")

        parity = hex_coord.r & 1
        col = hex_coord.q + (hex_coord.r + offset_type * parity) // 2
        row = hex_coord.r
        return OffsetCoord(col, row)

    def roffset_to_cube(self, offset_type, offset_coord):
        """R 轴偏移坐标转立方体坐标

        Args:
            offset_type: int，EVEN(1) 或 ODD(-1)
            offset_coord: OffsetCoord，(col, row) 偏移坐标

        Returns:
            Hex: 立方体坐标
        """
        if offset_type not in [self.EVEN, self.ODD]:
            raise ValueError("offset_type must be EVEN(1) or ODD(-1)")

        parity = offset_coord.row & 1
        q = offset_coord.col - (offset_coord.row + offset_type * parity) // 2
        r = offset_coord.row
        return self.create_hex(q, r)

    # ===================== 笛卡尔坐标转换（核心保留） =====================
    def hex_to_pixel(self, hex_coord):
        """立方体坐标转笛卡尔像素坐标

        Args:
            hex_coord: Hex，立方体坐标

        Returns:
            Point: (x, y) 像素坐标
        """
        m = self.layout.orientation
        size = self.layout.size
        origin = self.layout.origin

        x = (m.f0 * hex_coord.q + m.f1 * hex_coord.r) * size.x
        y = (m.f2 * hex_coord.q + m.f3 * hex_coord.r) * size.y

        return Point(x + origin.x, y + origin.y)

    def pixel_to_hex_fractional(self, pixel_coord):
        """笛卡尔坐标转浮点型立方体坐标

        Args:
            pixel_coord: Point 或 tuple，(x, y) 像素坐标

        Returns:
            Hex: 浮点型立方体坐标
        """
        if isinstance(pixel_coord, tuple):
            pixel_coord = Point(pixel_coord[0], pixel_coord[1])

        m = self.layout.orientation
        size = self.layout.size
        origin = self.layout.origin

        pt = Point(
            (pixel_coord.x - origin.x) / size.x,
            (pixel_coord.y - origin.y) / size.y
        )
        q = m.b0 * pt.x + m.b1 * pt.y
        r = m.b2 * pt.x + m.b3 * pt.y

        return self.create_hex(q, r)

    def pixel_to_hex(self, pixel_coord):
        """笛卡尔坐标转整数型立方体坐标

        Args:
            pixel_coord: Point 或 tuple，(x, y) 像素坐标

        Returns:
            Hex: 取整后的立方体坐标
        """
        return self.hex_round(self.pixel_to_hex_fractional(pixel_coord))

    def get_hex_corners(self, hex_coord):
        """获取六边形顶点坐标（用于绘制）

        Args:
            hex_coord: Hex，六边形坐标

        Returns:
            list[Point]: 6 个顶点坐标（逆时针顺序）
        """
        center = self.hex_to_pixel(hex_coord)
        corners = []
        for i in range(6):
            angle = 2 * np.pi * (self.orientation.start_angle - i) / 6
            x = center.x + self.hex_size * np.cos(angle)
            y = center.y + self.hex_size * np.sin(angle)
            corners.append(Point(x, y))
        return corners

    # ===================== 网格生成 =====================
    def create_staggered_grid(self, col_range, row_range):
        """创建带负数范围的交错类矩形网格

        核心逻辑：
        - Flat朝向后：偶数列偏移（列影响行）
        - Pointy朝向：奇数行偏移（行影响列）

        Args:
            col_range: tuple，(min_col, max_col)，列（Q 轴）范围
            row_range: tuple，(min_row, max_row)，行（R 轴）范围

        Returns:
            list[Hex]: 网格中所有六边形的坐标列表
        """
        grid_hexes = []
        min_col, max_col = col_range  # Q 轴范围（列 / X 轴）
        min_row, max_row = row_range  # R 轴范围（行 / Y 轴）

        # 根据朝向使用不同的交错规则
        if self.layout_type == "flat":
            # Flat朝向：偶数列偏移（列影响行）
            for col in range(min_col, max_col + 1):
                offset = col // 2  # 列偏移计算
                for row in range(min_row, max_row + 1):
                    actual_row = row - offset  # R 轴坐标 = 行号 - 列偏移
                    grid_hexes.append(self.create_hex(col, actual_row))
        else:
            # Pointy朝向：奇数行偏移（行影响列）
            for row in range(min_row, max_row + 1):
                offset = row // 2  # 行偏移计算
                for col in range(min_col, max_col + 1):
                    actual_col = col - offset  # Q 轴坐标 = 列号 - 行偏移
                    grid_hexes.append(self.create_hex(actual_col, row))

        print(f"\n=== 交错类矩形网格信息 ===")
        print(f"朝向: {self.layout_type} | 列范围(X/Q): {min_col} ~ {max_col} | 行范围(Y/R): {min_row} ~ {max_row}")
        print(f"总六边形数量: {len(grid_hexes)}")
        return grid_hexes

    def create_hex_grid_hexagonal(self, N):
        """创建正六边形排布网格

        Args:
            N: int，半径（层数），原点为第 0 层

        Returns:
            list[Hex]: 正六边形网格中所有六边形的坐标
        """
        grid_hexes = []
        for q in range(-N, N + 1):
            for r in range(-N, N + 1):
                hex_coord = self.create_hex(q, r)
                if self.get_hex_length(hex_coord) <= N:
                    grid_hexes.append(hex_coord)
        return grid_hexes

    def get_hex_ring(self, radius):
        """生成指定半径的单层六边形环

        Args:
            radius: int，环的半径（0 时仅返回原点）

        Returns:
            list[Hex]: 环上的六边形坐标列表
        """
        if radius == 0:
            return [self.create_hex(0, 0)]

        ring = []
        current = self.create_hex(radius, -radius, 0)

        for i in range(6):
            for _ in range(radius):
                ring.append(current)
                current = self.get_hex_neighbor(current, i)

        return ring


class HexGridVisualizer:
    """六边形网格可视化类（基于 matplotlib）"""

    def __init__(self, hex_size=30, orientation="pointy", origin=(0, 0)):
        """初始化可视化器

        Args:
            hex_size: int，六边形边长（像素）
            orientation: str，朝向类型（pointy / flat）
            origin: tuple，原点坐标 (x, y)
        """
        self.hex_lib = HexLib(hex_size, orientation, origin)
        self.hex_size = hex_size
        self.origin = origin

        self.plt = plt
        self.patches = patches
        self.Path = Path

        self.fig, self.ax = self.plt.subplots(figsize=(14, 12))
        self.ax.set_aspect("equal")
        self.ax.grid(True, alpha=0.3)
        self.ax.axhline(y=0, color='k', linestyle='--', alpha=0.5)
        self.ax.axvline(x=0, color='k', linestyle='--', alpha=0.5)

        self.show_coord = True
        self.coord_type = "cube"
        self.hex_colors = {}
        self.grid_hexes = []

    def set_grid(self, grid_hexes):
        """设置要绘制的网格坐标

        Args:
            grid_hexes: list[Hex]，六边形坐标列表
        """
        self.grid_hexes = grid_hexes

    def set_hex_color(self, hex_coord, color):
        """设置单个六边形颜色

        Args:
            hex_coord: Hex，六边形坐标
            color: str，颜色名称或代码
        """
        self.hex_colors[hex_coord] = color

    def batch_set_color(self, color_map):
        """批量设置颜色

        Args:
            color_map: dict，{Hex: color_str} 映射
        """
        self.hex_colors.update(color_map)

    def toggle_coord_display(self, show):
        """开关坐标显示

        Args:
            show: bool，True 显示坐标，False 隐藏
        """
        self.show_coord = show

    def set_coord_type(self, coord_type):
        """设置坐标显示类型

        Args:
            coord_type: str，可选 "cube" / "offset_r" / "offset_q" / "pixel"
        """
        valid_types = ["cube", "offset_r", "offset_q", "pixel"]
        if coord_type not in valid_types:
            raise ValueError(f"coord_type must be one of {valid_types}")
        self.coord_type = coord_type

    def _get_coord_text(self, hex_coord):
        """获取坐标显示文本（内部方法）

        Args:
            hex_coord: Hex，六边形坐标

        Returns:
            str: 坐标文本
        """
        if self.coord_type == "cube":
            return f"({hex_coord.q},{hex_coord.r},{hex_coord.s})"
        elif self.coord_type == "offset_r":
            offset = self.hex_lib.roffset_from_cube(self.hex_lib.ODD, hex_coord)
            return f"R({offset.col},{offset.row})"
        elif self.coord_type == "offset_q":
            offset = self.hex_lib.qoffset_from_cube(self.hex_lib.ODD, hex_coord)
            return f"Q({offset.col},{offset.row})"
        elif self.coord_type == "pixel":
            pixel = self.hex_lib.hex_to_pixel(hex_coord)
            return f"P({pixel.x:.0f},{pixel.y:.0f})"

    def draw(self, title="Hex Grid",show_on=True):
        """绘制网格

        Args:
            title: str，图表标题
            show_on: int，是否显示图表
        """
        self.ax.clear()
        self.ax.set_title(title, fontsize=14)
        self.ax.set_aspect("equal")
        self.ax.grid(True, alpha=0.3)
        self.ax.axhline(y=0, color='k', linestyle='--', alpha=0.5)
        self.ax.axvline(x=0, color='k', linestyle='--', alpha=0.5)

        centers_x = []
        centers_y = []

        for hex_coord in self.grid_hexes:
            # 绘制六边形
            corners = self.hex_lib.get_hex_corners(hex_coord)
            verts = [(p.x, p.y) for p in corners]
            verts.append(verts[0])

            codes = [self.Path.MOVETO] + [self.Path.LINETO] * 5 + [self.Path.CLOSEPOLY]
            path = self.Path(verts, codes)

            face_color = self.hex_colors.get(hex_coord, "white")
            patch = self.patches.PathPatch(
                path, facecolor=face_color, edgecolor="black", linewidth=0.8, alpha=0.8
            )
            self.ax.add_patch(patch)

            # 记录中心坐标
            center = self.hex_lib.hex_to_pixel(hex_coord)
            centers_x.append(center.x)
            centers_y.append(center.y)

            # 显示坐标
            if self.show_coord:
                self.ax.text(
                    center.x, center.y, self._get_coord_text(hex_coord),
                    ha="center", va="center", fontsize=7, color="black"
                )

        # 绘制边界框
        if centers_x and centers_y:
            min_x, max_x = min(centers_x), max(centers_x)
            min_y, max_y = min(centers_y), max(centers_y)
            rect_x = [min_x, max_x, max_x, min_x, min_x]
            rect_y = [min_y, min_y, max_y, max_y, min_y]
            self.ax.plot(rect_x, rect_y, 'r--', alpha=0.5, label="Bounding Box")
            self.ax.legend()

        # 调整视图范围
        margin = self.hex_size * 2
        self.ax.set_xlim(min(centers_x) - margin, max(centers_x) + margin)
        self.ax.set_ylim(min(centers_y) - margin, max(centers_y) + margin)

        self.plt.tight_layout()
        if show_on:
            self.plt.show()

    def draw_hexagonal_grid(self, N, highlight_boundary=True, color_layers=True):
        """绘制正六边形网格

        Args:
            N: int，半径（层数）
            highlight_boundary: bool，是否高亮边界层
            color_layers: bool，是否按层着色
        """
        grid_hexes = self.hex_lib.create_hex_grid_hexagonal(N)
        self.set_grid(grid_hexes)

        # 分层着色
        if color_layers:
            color_map = {
                0: "red",      # 中心层
                1: "yellow",   # 第一层
                2: "green",    # 第二层
                3: "blue",     # 第三层
                4: "purple",   # 第四层
            }
            for hex_coord in grid_hexes:
                distance = self.hex_lib.get_hex_length(hex_coord)
                self.set_hex_color(hex_coord, color_map.get(distance, "white"))

        # 边界高亮
        if highlight_boundary:
            for hex_coord in grid_hexes:
                if self.hex_lib.get_hex_length(hex_coord) == N:
                    self.set_hex_color(hex_coord, "orange")

        self.draw(title=f"正六边形网格 (N={N}, 朝向={self.hex_lib.layout_type})")

    def draw_staggered_grid(self, col_range, row_range, highlight_origin=True):
        """绘制交错类矩形网格

        Args:
            col_range: tuple，列范围 (X/Q 轴) (min_col, max_col)
            row_range: tuple，行范围 (Y/R 轴) (min_row, max_row)
            highlight_origin: bool，是否高亮原点
        """
        grid_hexes = self.hex_lib.create_staggered_grid(col_range, row_range)
        self.set_grid(grid_hexes)

        # 高亮原点
        if highlight_origin:
            origin_hex = self.hex_lib.create_hex(0, 0)
            if origin_hex in grid_hexes:
                self.set_hex_color(origin_hex, "red")

        self.draw(title=f"交错类矩形网格 (列{col_range}, 行{row_range}, 朝向={self.hex_lib.layout_type})")


# ===================== 模块级工具函数 =====================

def create_hex_polygon(center, cell_width, theta=np.pi / 6):
    """创建一个 Shapely 六边形多边形

    默认旋转 30° 使六边形平顶（flat-top）。

    Args:
        center: tuple (x, y)，六边形中心坐标
        cell_width: float，六边形外接圆半径（中心到顶点距离）
        theta: float，旋转角度（弧度），默认 np.pi/6

    Returns:
        shapely.geometry.Polygon: 六边形多边形
    """
    xc, yc = center
    angles = np.linspace(0, 2 * np.pi, 7)[:-1] + theta
    points = [(xc + cell_width * np.cos(angle),
               yc + cell_width * np.sin(angle)) for angle in angles]
    return Polygon(points)


def save_to_dxf(hex_all, filename="hex_grid.dxf", layer_name="hexgrid"):
    """将六边形网格合并后导出为 DXF 文件

    多个六边形先通过 unary_union 合并再导出，
    适用于六边形连成一片的场景。

    Args:
        hex_all: list[shapely.geometry.Polygon]，六边形多边形列表
        filename: str，输出 DXF 文件名
        layer_name: str，DXF 图层名
    """
    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()
    # 添加图层
    doc.layers.new(name=layer_name, dxfattribs={"color": 1})  # 红色

    all_poly = unary_union(hex_all)
    all_poly = all_poly.buffer(1e-6).buffer(-1e-6)

    # 如果是 MultiPolygon，需要遍历
    if all_poly.geom_type == 'MultiPolygon':
        for poly in all_poly.geoms:
            points = list(poly.exterior.coords[:-1])
            msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer_name})
    else:
        points = list(all_poly.exterior.coords[:-1])
        msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer_name})

    doc.saveas(filename)
    print(f"DXF 文件已保存: {filename}")


def save_multi_dxf(hex_groups, filename="hex_grid.dxf", layer_name="hexgrid"):
    """将多组六边形分别导出为 DXF 文件（每组独立图层）

    适用于多组六边形需在不同图层导出的场景。
    每组先通过 unary_union 合并再导出到对应图层。

    Args:
        hex_groups: list[list[shapely.geometry.Polygon]]，多组六边形多边形列表
        filename: str，输出 DXF 文件名
        layer_name: str，DXF 图层名前缀
    """
    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()

    for i in tqdm(range(len(hex_groups))):
        group = hex_groups[i]
        merged = unary_union(group)
        merged = merged.buffer(1e-6).buffer(-1e-6)

        # 添加图层
        layer = layer_name + str(i)
        doc.layers.new(name=layer, dxfattribs={"color": 1})

        # 如果是 MultiPolygon，需要遍历
        if merged.geom_type == 'MultiPolygon':
            for poly in merged.geoms:
                points = list(poly.exterior.coords[:-1])
                msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})
        else:
            points = list(merged.exterior.coords[:-1])
            msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})

    doc.saveas(filename)
    print(f"DXF 文件已保存: {filename}")


def read_and_display_dxf_matplotlib(filename="hex_grid.dxf",show_on=True):
    """使用 matplotlib 读取并显示 DXF 文件

    Args:
        filename: str，DXF 文件路径
        show_on: bool，是否显示图表
    """
    try:
        doc = ezdxf.readfile(filename)
        msp = doc.modelspace()
        fig, ax = plt.subplots(figsize=(12, 10))
        # 提取所有线条
        for entity in msp.query("LWPOLYLINE"):
            pts = list(entity.get_points())
            x_coords = [p[0] for p in pts]
            y_coords = [p[1] for p in pts]
            # 闭合多边形
            x_coords.append(x_coords[0])
            y_coords.append(y_coords[0])
            ax.plot(x_coords, y_coords, 'b-', linewidth=1.5)
        # 设置图形属性
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
        ax.set_xlabel('X (mm)', fontsize=12)
        ax.set_ylabel('Y (mm)', fontsize=12)
        ax.set_title(f'DXF 文件: {filename}\n六边形网格', fontsize=14)
        plt.tight_layout()
        if show_on:
            plt.show()
    except Exception as e:
        print(f"读取 DXF 文件时出错: {e}")
