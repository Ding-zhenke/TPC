import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from typing import Tuple, List, Dict, Union, Optional
from tqdm import tqdm
import matplotlib
matplotlib.rc("font", family='Microsoft YaHei')

def find_different_points(P1, P2, eps=1e-9):
    """
    筛选出P1中与P2所有点在误差范围内不相等的点
    
    参数：
        P1: numpy数组，形状为(N, D)，N个D维数据点
        P2: numpy数组，形状为(M, D)，M个D维数据点
        eps: 允许的绝对误差阈值（默认1e-6）
    
    返回：
        P3: numpy数组，形状为(K, D)，P1中与P2所有点都不同的点
    """
    # 确保输入是二维数组（避免一维点的维度问题）
    P1 = np.atleast_2d(P1)
    P2 = np.atleast_2d(P2)
    
    # 计算P1中每个点与P2中每个点的误差（平方和，避免开方加速计算）
    # 利用广播：(N,1,D) - (M,D) → (N,M,D)，再求每个维度误差的平方和
    errors = np.sum((P1[:, np.newaxis, :] - P2) **2, axis=2)
    
    # 判断P1中的点是否与P2中任何点的误差小于阈值（平方误差 < eps²）
    # any(axis=1)：对每个P1点，判断是否与P2中至少一个点近似相等
    is_equal = np.any(errors < eps** 2, axis=1)
    
    # 筛选出不相等的点（取反）
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
        theta: 旋转角度（度），默认0度（朝上）
    
    返回:
        3x2的numpy数组，包含三个顶点的(x, y)坐标
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
        matplotlib的Polygon对象
    """
    vertices = equilateral_triangle_vertices(center, a, theta)
    return Polygon(
        vertices,
        facecolor=color,
        edgecolor=color,
        linewidth=2
    )


def build_triangle_lattice(row_range: Tuple[int, int],
                          col_range: Tuple[int, int],
                          a: float,
                          offset: Tuple[float, float] = (0.0, 0.0),
                          theta: float = 0.0) -> Tuple[List[np.ndarray], List[Tuple[float, float]], 
                                                    List[Tuple[float, float]], Dict[Tuple[int, int], Tuple[float, float]], 
                                                    Dict[Tuple[int, int], Tuple[float, float]]]:
    """
    生成三角形网格结构数据
    
    参数:
        row_range: 行号范围 (start_row, end_row)，包含端点
        col_range: 列号范围 (start_col, end_col)，包含端点
        a: 三角形边长
        offset: 网格整体偏移量 (dx, dy)
        theta: 旋转角度（度）
    
    返回:
        triangles: 三角形顶点列表
        centers_up: 朝上三角形中心坐标列表
        centers_dn: 朝下三角形中心坐标列表
        pos_to_center_up: 朝上三角形位置坐标到中心坐标的映射
        pos_to_center_dn: 朝下三角形位置坐标到中心坐标的映射
    """
    h = a * np.sqrt(3) / 2  # 三角形高
    triangles, centers_up, centers_dn = [], [], []
    pos_to_center_up: Dict[Tuple[int, int], Tuple[float, float]] = {}
    pos_to_center_dn: Dict[Tuple[int, int], Tuple[float, float]] = {}
    
    start_row, end_row = row_range
    start_col, end_col = col_range
    
    for r in tqdm(range(start_row, end_row + 1)):
        for c in range(start_col, end_col + 1):
            # 计算朝上三角形中心
            cx_up = offset[0] + c * a + (r % 2) * (a / 2)
            cy_up = offset[1] + r * h
            tri = equilateral_triangle_vertices((cx_up, cy_up), a, theta)
            
            # 存储数据
            triangles.append(tri)
            centers_up.append((cx_up, cy_up))
            pos_to_center_up[(r, c)] = (cx_up, cy_up)
            
            # 计算朝下三角形中心（与朝上三角形共享底边）
            cx_dn = cx_up
            cy_dn = cy_up - h * 2 / 3  # 重心位置
            centers_dn.append((cx_dn, cy_dn))
            pos_to_center_dn[(r, c)] = (cx_dn, cy_dn)
    
    return triangles, centers_up, centers_dn, pos_to_center_up, pos_to_center_dn


def pos_to_xy(row_range: Tuple[int, int],
             col_range: Tuple[int, int],
             a: float,
             r: int,
             c: int,
             triangle_type: str = 'up',
             offset: Tuple[float, float] = (0.0, 0.0)) -> Tuple[float, float]:
    """
    将位置坐标(r, c)转换为实际XY坐标
    
    参数:
        row_range: 行号范围 (start_row, end_row)
        col_range: 列号范围 (start_col, end_col)
        a: 三角形边长
        r: 行号
        c: 列号
        triangle_type: 三角形类型，'up'（朝上）或'down'（朝下）
        offset: 网格偏移量
    
    返回:
        三角形中心的(x, y)坐标
    
    异常:
        ValueError: 行号或列号超出范围，或三角形类型无效
    """
    start_row, end_row = row_range
    start_col, end_col = col_range
    
    # 范围校验
    if not (start_row <= r <= end_row):
        raise ValueError(f"行号r={r}超出范围[{start_row}, {end_row}]")
    if not (start_col <= c <= end_col):
        raise ValueError(f"列号c={c}超出范围[{start_col}, {end_col}]")
    
    h = a * np.sqrt(3) / 2  # 三角形高
    offset=[a/2,h-a/np.sqrt(3)]
    if triangle_type == 'up':
        x = offset[0] + c * a + (r % 2) * (a / 2)
        y = offset[1] + r * h
    elif triangle_type == 'down':
        x = offset[0] + c * a + (r % 2) * (a / 2)
        y = offset[1] + r * h - h * 2 / 3
    else:
        raise ValueError("triangle_type必须是'up'或'down'")
    
    return (x, y)


def xy_to_pos(row_range: Tuple[int, int],
             col_range: Tuple[int, int],
             a: float,
             x: float,
             y: float,
             triangle_type: str = 'up',
             offset: Tuple[float, float] = (0.0, 0.0)) -> Tuple[int, int]:
    """
    将XY坐标转换为位置坐标(r, c)
    
    参数:
        row_range: 行号范围 (start_row, end_row)
        col_range: 列号范围 (start_col, end_col)
        a: 三角形边长
        x: X坐标
        y: Y坐标
        triangle_type: 三角形类型，'up'（朝上）或'down'（朝下）
        offset: 网格偏移量
    
    返回:
        位置坐标(r, c)
    """
    start_row, end_row = row_range
    start_col, end_col = col_range
    h = a * np.sqrt(3) / 2  # 三角形高
    
    # 去除偏移量影响
    x -= offset[0]
    y -= offset[1]
    
    if triangle_type == 'up':
        r = int(round(y / h))
        c = int(round(x / a)) if r % 2 == 0 else int(round((x - a/2) / a))
    elif triangle_type == 'down':
        adjusted_y = y + (2 * h / 3)  # 转换为对应朝上三角形的y坐标
        r = int(round(adjusted_y / h))
        c = int(round(x / a)) if r % 2 == 0 else int(round((x - a/2) / a))
    else:
        raise ValueError("triangle_type必须是'up'或'down'")
    
    # 限制在有效范围内
    r = max(start_row, min(r, end_row))
    c = max(start_col, min(c, end_col))
    
    return (r, c)

def plot_triangle_grid(row_range: Tuple[int, int],
                      col_range: Tuple[int, int],
                      a: float = 1.0,
                      offset: Tuple[float, float] = (0.0, 0.0),
                      theta: float = 0.0,
                      show_labels: bool = True,
                      show_points: bool = True) -> Tuple[plt.Figure, plt.Axes]:
    """
    绘制三角形网格并标记中心（修复右侧三角形重叠问题）
    
    参数:
        row_range: 行号范围 (start_row, end_row)
        col_range: 列号范围 (start_col, end_col)
        a: 三角形边长
        offset: 网格偏移量
        theta: 旋转角度（度）
        show_labels: 是否显示位置坐标标签
        show_points: 是否显示中心标记点
    
    返回:
        fig: 图形对象
        ax: 坐标轴对象
    """
    # 生成网格数据
    triangles, centers_up, centers_dn, pos_to_center_up, pos_to_center_dn = \
        build_triangle_lattice(row_range, col_range, a, offset, theta)
    
    # 创建图形
    fig, ax = plt.subplots(figsize=(10, 8))
    h = a * np.sqrt(3) / 2  # 三角形高
    
    # 绘制朝上三角形
    for tri in tqdm(triangles):
        polygon = Polygon(tri, fill=False, edgecolor='black', linewidth=1)
        ax.add_patch(polygon)
    
    # 绘制朝下三角形（修复右侧重叠问题）
    start_row, end_row = row_range
    start_col, end_col = col_range
    for r in tqdm(range(start_row, end_row)):  # 注意：只到end_row-1，避免越界
        for c in range(start_col, end_col + 1):
            # 关键修复：限制列号范围，避免右侧超出边界的朝下三角形
            if r % 2 == 0:
                # 偶数行：朝下三角形仅在c < end_col时绘制（避免右侧重叠）
                if c < end_col:
                    cx_dn = offset[0] + c * a + a/2
                    cy_dn = offset[1] + r * h + h/3
                    tri = equilateral_triangle_vertices((cx_dn, cy_dn), a, theta + 180)
                    ax.add_patch(Polygon(tri, fill=False, edgecolor='black', linewidth=1))
            else:
                # 奇数行：朝下三角形在所有有效列绘制（不会重叠）
                cx_dn = offset[0] + c * a
                cy_dn = offset[1] + r * h + h/3
                tri = equilateral_triangle_vertices((cx_dn, cy_dn), a, theta + 180)
                ax.add_patch(Polygon(tri, fill=False, edgecolor='black', linewidth=1))
    
    # 标记中心和标签（保持不变）
    if show_points:
        # 朝上三角形中心（红色）
        for (r, c), (x, y) in pos_to_center_up.items():
            ax.scatter(x, y, color='red', s=50, zorder=5)
            if show_labels:
                ax.annotate(f'({r},{c})', (x, y), xytext=(5, 5),
                           textcoords='offset points', fontsize=8)
        
        # 朝下三角形中心（橙色）
        for (r, c), (x, y) in pos_to_center_dn.items():
            # 仅显示有效范围内的朝下三角形（避免右侧重叠的点）
            valid = (r <= end_row) and (
                (r % 2 == 1) or  # 奇数行全部有效
                (r % 2 == 0 and c < end_col)  # 偶数行仅c < end_col有效
            )
            if valid:
                ax.scatter(x, y, color='orange', s=50, zorder=5)
                if show_labels:
                    ax.annotate(f'd({r},{c})', (x, y), xytext=(5, 5),
                               textcoords='offset points', fontsize=8, color='orange')
    
    # 设置坐标轴（保持不变）
    min_x = min(p[0] for tri in triangles for p in tri)
    max_x = max(p[0] for tri in triangles for p in tri)
    min_y = min(p[1] for tri in triangles for p in tri)
    max_y = max(p[1] for tri in triangles for p in tri)
    
    ax.set_aspect('equal')
    ax.set_xlim(min_x - a, max_x + a)
    ax.set_ylim(min_y - h, max_y + h)
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_title(f'三角形网格 [{start_row},{end_row}]×[{start_col},{end_col}]')
    ax.grid(True, linestyle='--', alpha=0.7)
    # plt.tight_layout()
    
    return fig, ax


def find_corner_points(points: Union[List[Tuple[float, float]], np.ndarray]) -> np.ndarray:
    """
    找出点集中的四个角落点（左下、右下、左上、右上）
    
    参数:
        points: 点集，格式为[(x1,y1), (x2,y2), ...]或二维数组
    
    返回:
        4x2的numpy数组，按顺序[左下, 右下, 左上, 右上]
    
    异常:
        ValueError: 点集数量不足4个
    """
    points = np.array(points)
    if len(points) < 4:
        raise ValueError("点集数量至少需要4个点")
    
    # 左下顶点：y最小，x最小
    min_y_mask = points[:, 1] == np.min(points[:, 1])
    min_y_points = points[min_y_mask]
    bottom_left = min_y_points[np.argmin(min_y_points[:, 0])]
    
    # 右下顶点：y最小，x最大
    bottom_right = min_y_points[np.argmax(min_y_points[:, 0])]
    
    # 左上顶点：y最大，x最小
    max_y_mask = points[:, 1] == np.max(points[:, 1])
    max_y_points = points[max_y_mask]
    top_left = max_y_points[np.argmin(max_y_points[:, 0])]
    
    # 右上顶点：y最大，x最大
    top_right = max_y_points[np.argmax(max_y_points[:, 0])]
    
    return np.array([bottom_left, bottom_right, top_left, top_right])


def shortest_path(start: Tuple[int, int],
                 end: Tuple[int, int],
                 first_direction: str = 'x') -> np.ndarray:
    """
    生成网格中两点间的最短路径（曼哈顿路径）
    
    参数:
        start: 起始位置坐标 (r, c)
        end: 终点位置坐标 (r, c)
        first_direction: 优先移动方向，'x'（列方向优先）或'y'（行方向优先）
    
    返回:
        路径点数组，形状为(N, 2)，包含所有路径点的(r, c)坐标
    
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
        # 先列后行,行下
        t1=np.min([abs(dx),abs(dy)])
        for _ in range(abs(abs(dx)-abs(dy))):
            current_c += step_x
            path.append((current_r, current_c))
        for _ in range(t1):
            current_c += step_x
            current_r += step_y
            path.append((current_r, current_c))
    # 根据优先方向移动
    elif first_direction.lower() == 'xy' or (dx>0 and dy<0) or (dx<0 and dy>0) :
        # 先列后行
        t1=np.min([abs(dx),abs(dy)])
        t2=np.max([abs(dx),abs(dy)])
        for _ in range(t1):
            current_c += step_x
            current_r += step_y
            path.append((current_r, current_c))
        for _ in range(t2-t1):
            if abs(dx)>abs(dy):
                current_c += step_x       
            elif abs(dx)<abs(dy):
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
        raise ValueError("无效的优先方向，请传入'x'或'y'")
    
    return np.array(path)


def path_loc_to_xy(path: np.ndarray, a: float) -> np.ndarray:
    """
    将路径的位置坐标转换为XY坐标
    
    参数:
        path: 路径位置坐标数组，形状为(N, 2)，每个元素为(r, c)
        a: 三角形边长
    
    返回:
        XY坐标数组，形状为(N, 2)
    """
    e1 = (a, 0)  # 基向量1
    e2 = (a/2, a/2 * np.sqrt(3))  # 基向量2
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
        布尔值，True表示点在线段上方
    """
    x, y = point
    x1, y1 = seg_start
    x2, y2 = seg_end

    if x2 == x1:  # 垂直线段
        return x > x1
    
    # 计算线段方程 y = slope*x + intercept
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
        polyline: 折线点集，至少包含2个点
    
    返回:
        筛选后的点集数组
    
    异常:
        ValueError: 折线点数量不足
    """
    if len(polyline) < 2:
        raise ValueError("折线至少需要2个点")
    
    points = np.array(points)
    polyline = np.array(polyline)
    above_points = []
    
    for point in points:
        is_above = True
        for i in range(len(polyline) - 1):
            if not is_above_segment(point, polyline[i], polyline[i+1]):
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
        polyline: 折线点集，至少包含2个点
    
    返回:
        筛选后的点集数组
    
    异常:
        ValueError: 折线点数量不足
    """
    if len(polyline) < 2:
        raise ValueError("折线至少需要2个点")
    
    points = np.array(points)
    polyline = np.array(polyline)
    below_points = []
    
    for point in points:
        is_below = True
        for i in range(len(polyline) - 1):
            if is_above_segment(point, polyline[i], polyline[i+1]):
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
        polygon: 多边形顶点数组，至少包含3个点
    
    返回:
        布尔值，True表示点在多边形内部
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
        if ((yi > y) != (yj > y)):
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
        polygon: 多边形顶点数组，至少包含3个点
    
    返回:
        筛选后的点集数组
    
    异常:
        ValueError: 多边形顶点数量不足
    """
    if len(polygon) < 3:
        raise ValueError("多边形至少需要3个顶点")
    
    points = np.array(points)
    inside_points = [p for p in points if point_in_polygon(p, polygon)]
    return np.array(inside_points)
def line_cal(point, slope, known_value, is_x=True):
    """
    根据直线上已知点、斜率和另一点的已知坐标，计算未知坐标
    
    参数:
    x0, y0 -- 直线上已知点的坐标
    slope -- 直线的斜率（k）
    known_value -- 另一点已知的坐标值（X或Y）
    is_x -- 若为True，表示已知的是X值，需要计算Y值；若为False，表示已知的是Y值，需要计算X值
    
    返回:
    计算得到的未知坐标值，若无法计算则返回None
    """
    x0=point[0]
    y0=point[1]
    try:
        if is_x:
            # 已知X，求Y：y = k*(x - x0) + y0
            return slope * (known_value - x0) + y0
        else:
            # 已知Y，求X：x = (y - y0)/k + x0
            if slope == 0:
                raise ValueError("当已知Y值时，斜率不能为0（水平直线无法通过Y求X）")
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
    
    # 测试位置坐标到XY坐标的转换
    print("位置坐标到XY坐标的转换测试：")
    for r in range(row_range[0], row_range[1] + 1):
        for c in range(col_range[0], col_range[1] + 1):
            xy_up = pos_to_xy(row_range, col_range, a, r, c, 'up')
            xy_down = pos_to_xy(row_range, col_range, a, r, c, 'down')
            print(f"位置({r},{c}) - 朝上: {xy_up}, 朝下: {xy_down}")
    
    # 测试XY坐标到位置坐标的转换
    print("\nXY坐标到位置坐标的转换测试：")
    test_points = [
        (-0.5, -np.sqrt(3), 'up'),   # (-2, -1)
        (0.0, -np.sqrt(3)/2, 'up'),  # (-1, -1)
        (-0.5, 0, 'up'),             # (0, -1)
        (0.0, np.sqrt(3)/2, 'up'),   # (1, -1)
        (-0.5, np.sqrt(3), 'up'),    # (2, -1)
        (0.5, np.sqrt(3)/6, 'down'), # (-1, -1)
        (1.5, np.sqrt(3)/6, 'down'), # (-1, 0)
    ]
    
    for x, y, tri_type in test_points:
        pos = xy_to_pos(row_range, col_range, a, x, y, tri_type)
        print(f"XY({x:.2f},{y:.2f}) - {tri_type} -> 位置{pos}")
    
    # 生成可视化
    print("\n生成三角形网格可视化...")
    fig, ax = plot_triangle_grid(row_range, col_range, a, show_labels=True)
    plt.show()