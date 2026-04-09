# -*- coding: utf-8 -*-
"""
六边形网格核心算法库（最终稳定版）
核心修复：
1. 严格匹配行列与坐标轴对应：行=Y轴、列=X轴（支持正负范围）
2. 保留原有所有逻辑，仅修正Flat朝向行列映射关系
3. 两种核心排布：正六边形排布 + 带负数范围的交错类矩形排布
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


#写入dxf
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
    
    # 标准朝向定义（遵循Hex Grid Standard）
    LAYOUT_FLAT = Orientation(
        3.0/2.0, 0.0,
        np.sqrt(3.0)/2.0, np.sqrt(3.0),
        2.0/3.0, 0.0,
        -1.0/3.0, np.sqrt(3.0)/3.0,
        0.0
    )
    LAYOUT_POINTY = Orientation(
        np.sqrt(3.0), np.sqrt(3.0)/2.0,
        0.0, 3.0/2.0,
        np.sqrt(3.0)/3.0, -1.0/3.0,
        0.0, 2.0/3.0,
        0.5
    )
    
    EVEN = 1
    ODD = -1

    def __init__(self, hex_size=20, orientation="pointy", origin=(0, 0)):
        """初始化六边形网格参数
        Args:
            hex_size: int，六边形单元边长（像素）
            orientation: str，朝向类型（pointy/flat）
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
        """创建有效的立方体六边形坐标"""
        if s is None:
            s = -q - r
        assert np.round(q + r + s) == 0, "Hex coordinates must satisfy q + r + s = 0"
        return Hex(q, r, s)

    def hex_add(self, a, b):
        """立方体坐标加法"""
        return self.create_hex(a.q + b.q, a.r + b.r, a.s + b.s)

    def hex_subtract(self, a, b):
        """立方体坐标减法"""
        return self.create_hex(a.q - b.q, a.r - b.r, a.s - b.s)

    def hex_rotate_left(self, a):
        """立方体坐标向左旋转60度"""
        return self.create_hex(-a.s, -a.q, -a.r)

    def hex_rotate_right(self, a):
        """立方体坐标向右旋转60度"""
        return self.create_hex(-a.r, -a.s, -a.q)

    # ===================== 邻居/距离计算 =====================
    def get_hex_direction(self, direction):
        """获取指定方向的偏移量"""
        directions = [
            self.create_hex(1, 0, -1),  # 右
            self.create_hex(1, -1, 0),  # 右上
            self.create_hex(0, -1, 1),  # 左上
            self.create_hex(-1, 0, 1),  # 左
            self.create_hex(-1, 1, 0),  # 左下
            self.create_hex(0, 1, -1)   # 右下
        ]
        return directions[direction % 6]

    def get_hex_neighbor(self, hex_coord, direction):
        """获取相邻六边形坐标"""
        return self.hex_add(hex_coord, self.get_hex_direction(direction))

    def get_hex_length(self, hex_coord):
        """计算坐标到原点的曼哈顿距离"""
        return (abs(hex_coord.q) + abs(hex_coord.r) + abs(hex_coord.s)) // 2

    def get_hex_distance(self, a, b):
        """计算两个六边形的距离"""
        return self.get_hex_length(self.hex_subtract(a, b))

    # ===================== 坐标取整/插值 =====================
    def hex_round(self, hex_coord):
        """浮点型立方体坐标取整为整数坐标"""
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
        """立方体坐标线性插值"""
        q = a.q * (1 - t) + b.q * t
        r = a.r * (1 - t) + b.r * t
        s = a.s * (1 - t) + b.s * t
        return self.create_hex(q, r, s)

    def hex_linedraw(self, a, b):
        """生成两点间的六边形路径"""
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
        """立方体坐标转Q轴偏移坐标"""
        if offset_type not in [self.EVEN, self.ODD]:
            raise ValueError("offset_type must be EVEN(1) or ODD(-1)")
        
        parity = hex_coord.q & 1
        col = hex_coord.q
        row = hex_coord.r + (hex_coord.q + offset_type * parity) // 2
        return OffsetCoord(col, row)

    def qoffset_to_cube(self, offset_type, offset_coord):
        """Q轴偏移坐标转立方体坐标"""
        if offset_type not in [self.EVEN, self.ODD]:
            raise ValueError("offset_type must be EVEN(1) or ODD(-1)")
        
        parity = offset_coord.col & 1
        q = offset_coord.col
        r = offset_coord.row - (offset_coord.col + offset_type * parity) // 2
        return self.create_hex(q, r)

    def roffset_from_cube(self, offset_type, hex_coord):
        """立方体坐标转R轴偏移坐标"""
        if offset_type not in [self.EVEN, self.ODD]:
            raise ValueError("offset_type must be EVEN(1) or ODD(-1)")
        
        parity = hex_coord.r & 1
        col = hex_coord.q + (hex_coord.r + offset_type * parity) // 2
        row = hex_coord.r
        return OffsetCoord(col, row)

    def roffset_to_cube(self, offset_type, offset_coord):
        """R轴偏移坐标转立方体坐标"""
        if offset_type not in [self.EVEN, self.ODD]:
            raise ValueError("offset_type must be EVEN(1) or ODD(-1)")
        
        parity = offset_coord.row & 1
        q = offset_coord.col - (offset_coord.row + offset_type * parity) // 2
        r = offset_coord.row
        return self.create_hex(q, r)

    # ===================== 笛卡尔坐标转换（核心保留） =====================
    def hex_to_pixel(self, hex_coord):
        """立方体坐标转笛卡尔坐标（严格保留原有逻辑）"""
        m = self.layout.orientation
        size = self.layout.size
        origin = self.layout.origin
        
        x = (m.f0 * hex_coord.q + m.f1 * hex_coord.r) * size.x
        y = (m.f2 * hex_coord.q + m.f3 * hex_coord.r) * size.y
        
        return Point(x + origin.x, y + origin.y)

    def pixel_to_hex_fractional(self, pixel_coord):
        """笛卡尔坐标转浮点型立方体坐标"""
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
        """笛卡尔坐标转整数型立方体坐标"""
        return self.hex_round(self.pixel_to_hex_fractional(pixel_coord))

    def get_hex_corners(self, hex_coord):
        """获取六边形顶点坐标（用于绘制）"""
        center = self.hex_to_pixel(hex_coord)
        corners = []
        for i in range(6):
            angle = 2 * np.pi * (self.orientation.start_angle - i) / 6
            x = center.x + self.hex_size * np.cos(angle)
            y = center.y + self.hex_size * np.sin(angle)
            corners.append(Point(x, y))
        return corners

    # ===================== 网格生成（核心修复：行列与Q/R严格对应） =====================
    def create_staggered_grid(self, col_range, row_range):
        """创建带负数范围的交错类矩形网格
        核心修正：
        - 针对不同朝向使用不同的交错规则
        - Flat朝向：偶数列偏移；Pointy朝向：奇数行偏移
        """
        grid_hexes = []
        min_col, max_col = col_range  # Q轴范围（列/X轴）
        min_row, max_row = row_range  # R轴范围（行/Y轴）
        
        # 根据朝向使用不同的交错规则
        if self.layout_type == "flat":
            # Flat朝向：偶数列偏移（列影响行）
            for col in range(min_col, max_col + 1):
                offset = col // 2  # 列偏移计算
                for row in range(min_row, max_row + 1):
                    actual_row = row - offset  # R轴坐标 = 行号 - 列偏移
                    grid_hexes.append(self.create_hex(col, actual_row))
        else:
            # Pointy朝向：奇数行偏移（行影响列）
            for row in range(min_row, max_row + 1):
                offset = row // 2  # 行偏移计算
                for col in range(min_col, max_col + 1):
                    actual_col = col - offset  # Q轴坐标 = 列号 - 行偏移
                    grid_hexes.append(self.create_hex(actual_col, row))
        
        print(f"\n=== 交错类矩形网格信息 ===")
        print(f"朝向: {self.layout_type} | 列范围(X/Q): {min_col} ~ {max_col} | 行范围(Y/R): {min_row} ~ {max_row}")
        print(f"总六边形数量: {len(grid_hexes)}")
        return grid_hexes

    def create_hex_grid_hexagonal(self, N):
        """创建正六边形排布网格（保留原有逻辑）"""
        grid_hexes = []
        for q in range(-N, N + 1):
            for r in range(-N, N + 1):
                hex_coord = self.create_hex(q, r)
                if self.get_hex_length(hex_coord) <= N:
                    grid_hexes.append(hex_coord)
        return grid_hexes

    def get_hex_ring(self, radius):
        """生成指定半径的单层六边形环"""
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
    """六边形网格可视化类（仅修正行列参数名）"""
    
    def __init__(self, hex_size=30, orientation="pointy", origin=(0, 0)):
        """初始化可视化器"""
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
        """设置要绘制的网格坐标"""
        self.grid_hexes = grid_hexes

    def set_hex_color(self, hex_coord, color):
        """设置单个六边形颜色"""
        self.hex_colors[hex_coord] = color

    def batch_set_color(self, color_map):
        """批量设置颜色"""
        self.hex_colors.update(color_map)

    def toggle_coord_display(self, show):
        """开关坐标显示"""
        self.show_coord = show

    def set_coord_type(self, coord_type):
        """设置坐标显示类型"""
        valid_types = ["cube", "offset_r", "offset_q", "pixel"]
        if coord_type not in valid_types:
            raise ValueError(f"coord_type must be one of {valid_types}")
        self.coord_type = coord_type

    def _get_coord_text(self, hex_coord):
        """获取坐标显示文本（内部方法）"""
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

    def draw(self, title="Hex Grid"):
        """绘制网格（保留原有逻辑）"""
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
            
            codes = [self.Path.MOVETO] + [self.Path.LINETO]*5 + [self.Path.CLOSEPOLY]
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
        self.plt.show()
    
    def draw_hexagonal_grid(self, N, highlight_boundary=True, color_layers=True):
        """绘制正六边形网格（保留原有逻辑）"""
        grid_hexes = self.hex_lib.create_hex_grid_hexagonal(N)
        self.set_grid(grid_hexes)
        
        # 分层着色
        if color_layers:
            color_map = {
                0: "red",    # 中心层
                1: "yellow", # 第一层
                2: "green",  # 第二层
                3: "blue",   # 第三层
                4: "purple"  # 第四层
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
        """绘制交错类矩形网格（参数名修正：列/行范围）
        Args:
            col_range: tuple，列范围（X/Q轴）(min_col, max_col)
            row_range: tuple，行范围（Y/R轴）(min_row, max_row)
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


def create_hex_polygon(center, cell_width,theta=np.pi/6):
    """创建一个六边形多边形"""
    xc, yc = center
    angles = np.linspace(0, 2*np.pi, 7)[:-1] + theta  # 旋转30度使六边形平顶
    points = [(xc + cell_width * np.cos(angle), 
                yc + cell_width * np.sin(angle)) for angle in angles]
    return Polygon(points)


def save_to_dxf(hex_all, filename="hex_grid.dxf",layer_name="hexgrid"):
    """将六边形网格个体组件保存为DXF文件，多个连成一大片不适用"""
    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()
    # 添加图层
    doc.layers.new(name=layer_name, dxfattribs={"color": 1})  # 红色
    
    all = unary_union(hex_all)
    all=all.buffer(1e-6).buffer(-1e-6)
    
    # 如果是 MultiPolygon，需要遍历
    if all.geom_type == 'MultiPolygon':
        for poly in all.geoms:
            points = list(poly.exterior.coords[:-1])
            msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer_name})
    else:
        points = list(all.exterior.coords[:-1])
        msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer_name})
    
    doc.saveas(filename)
    print(f"DXF文件已保存: {filename}")
    
def read_and_display_dxf_matplotlib(filename="hex_grid.dxf"):
    """使用matplotlib读取并显示DXF文件"""
    try:
        doc = ezdxf.readfile(filename)
        msp = doc.modelspace()
        fig, ax = plt.subplots(figsize=(12, 10))
        # 提取所有线条
        for entity in msp.query("LWPOLYLINE"):
            points = list(entity.get_points())
            x_coords = [p[0] for p in points]
            y_coords = [p[1] for p in points]
            # 闭合多边形
            x_coords.append(x_coords[0])
            y_coords.append(y_coords[0])
            ax.plot(x_coords, y_coords, 'b-', linewidth=1.5)
        # 设置图形属性
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
        ax.set_xlabel('X (mm)', fontsize=12)
        ax.set_ylabel('Y (mm)', fontsize=12)
        ax.set_title(f'DXF文件: {filename}\n六边形网格', fontsize=14)
        plt.tight_layout()
        plt.show()
    except Exception as e:
        print(f"读取DXF文件时出错: {e}")
        
print('reloaded optimizer.py2ssss32')