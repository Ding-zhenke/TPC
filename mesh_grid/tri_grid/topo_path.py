# -*- coding: utf-8 -*-
"""
拓扑路径统一管理与声明式 DSL
============================
唯一数据源是三角晶格坐标 (r, c)，所有直角坐标（matplotlib 预览 + CST 表达式）
全部自动推导，消除 path_points 和 (px,py) 两套坐标的重复维护。

支持符号坐标（CST 参数变量）：
    >>> path = (TopoPath.builder(a=0.2425)
    ...         .start(0, 0)
    ...         .move('x1', 'c')        # x1 是 CST 参数，可在 CST 中调整
    ...         .turn(120)
    ...         .move('y1', 'along')    # y1 是 CST 参数
    ...         .build(param_values={'x1': 18, 'y1': 14}))
    >>> path.auto_define_cst_params(app)
    # 生成: px2='x1*a', py2='0'
    #       px3='(x1-y1)*a+y1*a/2', py3='y1*a/2*sqr(3)'
    # 在 CST 中修改 x1/y1 即可调整路径长度！

用法:
    >>> from mesh_grid.tri_grid import TopoPath
    >>> path = (TopoPath.builder(a=0.2425)
    ...         .start(0, -1)
    ...         .move(19, 'c')
    ...         .turn(120)
    ...         .move(14, 'along')
    ...         .build())
    >>> path.xy          # 直角坐标 (N, 2)
    >>> path.preview()   # matplotlib 预览
    >>> path.auto_define_cst_params(app)  # 自动在 CST 中定义 p1x,p1y,...

数学基础（与 mesh_grid/tri_grid/core.py 的 path_loc_to_xy 完全一致）:
    x = c * a + r * (a/2)
    y = r * (a/2 * sqrt(3))

6 个晶格方向（逆时针从 0 度开始）:
    0度:   (0, +1)  +c
    60度:  (+1, 0)  +r
    120度: (+1, -1) +r-c
    180度: (0, -1)  -c
    240度: (-1, 0)  -r
    300度: (-1, +1) -r+c

@author: PC
"""

import numpy as np
import matplotlib.pyplot as plt
from typing import List, Tuple, Optional, Union


# ============================================================
# 符号运算辅助函数（支持 CST 参数表达式）
# ============================================================
def _is_numeric(x):
    """判断是否为数值类型（int/float，不包括 bool）。"""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _is_zero(x):
    """判断是否为数值 0。"""
    return _is_numeric(x) and x == 0


def _symbolic_add(a, b):
    """
    符号加法：a + b，其中 a/b 可以是 int/float 或 str（CST参数表达式）。

    简化规则：
      - 数值+数值 → 数值
      - 任一为0 → 返回另一个
      - 负数+正数 → 'a-b' 形式
      - 其他 → 'a+b' 形式
    """
    if _is_numeric(a) and _is_numeric(b):
        return a + b
    if _is_zero(a):
        return b
    if _is_zero(b):
        return a
    # 简化负数加法
    if _is_numeric(b) and b < 0:
        return f'{a}-{abs(b)}'
    if _is_numeric(a) and a < 0:
        return f'{b}-{abs(a)}'
    # 处理带负号的字符串（如 '-y1'）
    if isinstance(b, str) and b.startswith('-') and len(b) > 1:
        return f'{a}-{b[1:]}'
    if isinstance(a, str) and a.startswith('-') and len(a) > 1:
        return f'{b}-{a[1:]}'
    return f'{a}+{b}'


def _symbolic_mul(a, b):
    """
    符号乘法：a * b，其中 a/b 可以是 int/float 或 str。

    简化规则：
      - 数值*数值 → 数值
      - 任一为0 → 0
      - 任一为1 → 另一个
      - 任一为-1 → 取负
      - 其他 → '(a)*(b)' 形式
    """
    if _is_numeric(a) and _is_numeric(b):
        return a * b
    if _is_zero(a) or _is_zero(b):
        return 0
    if a == 1:
        return b
    if b == 1:
        return a
    if a == -1:
        return f'-{b}' if isinstance(b, str) else -b
    if b == -1:
        return f'-{a}' if isinstance(a, str) else -a
    return f'({a})*({b})'


def _resolve_symbol(value, param_values):
    """
    将符号值解析为数值。如果 value 是 str 且在 param_values 中，返回对应数值；
    否则尝试 eval（简单表达式如 'x1-y1'）；都失败则返回原值。
    """
    if _is_numeric(value):
        return int(value)
    if isinstance(value, str):
        if value in param_values:
            return int(param_values[value])
        # 尝试简单表达式求值（如 'x1-y1', 'x1+1'）
        try:
            return int(eval(value, {"__builtins__": {}}, param_values))
        except Exception:
            return value  # 无法解析，返回原值
    return value


# ============================================================
# 方向常量：6 个晶格方向，逆时针从 0 度开始
# ============================================================
DIRECTIONS = [
    (0, 1),    # 0   — +c
    (1, 0),    # 60  — +r
    (1, -1),   # 120 — +r, -c
    (0, -1),   # 180 — -c
    (-1, 0),   # 240 — -r
    (-1, 1),   # 300 — -r, +c
]

DIRECTION_NAMES = ['+c', '+r', '+r-c', '-c', '-r', '-r+c']

_NAME_TO_IDX = {
    'c': 0, '+c': 0, 'c+': 0,
    'r': 1, '+r': 1, 'r+': 1,
    'rc': 2, 'r+c-': 2, '+r-c': 2,
    '-c': 3, 'c-': 3,
    '-r': 4, 'r-': 4,
    '-rc': 5, 'r-c+': 5, '-r+c': 5,
}


def _resolve_direction(direction):
    """将方向参数解析为 (dr, dc)。'along'/None 返回 None 表示当前方向。"""
    if direction is None or direction == 'along':
        return None
    if isinstance(direction, str):
        key = direction.strip().lower()
        if key in _NAME_TO_IDX:
            return DIRECTIONS[_NAME_TO_IDX[key]]
        raise ValueError(f"未知方向名 '{direction}'，支持: {list(_NAME_TO_IDX.keys())}")
    if isinstance(direction, (tuple, list)) and len(direction) == 2:
        dr, dc = int(direction[0]), int(direction[1])
        if (dr, dc) not in DIRECTIONS:
            raise ValueError(f"方向向量 ({dr},{dc}) 不是三角晶格的 6 个主方向之一")
        return (dr, dc)
    raise ValueError(f"无法解析方向: {direction!r}")


def _direction_to_index(dr, dc):
    return DIRECTIONS.index((dr, dc))


# ============================================================
# TopoPathBuilder — 声明式构建器（支持符号步数）
# ============================================================
class TopoPathBuilder:
    """
    链式构建器：.start().move().turn().build()
    用户不需要手算每个拐点的 (r,c)，只说"走多远、转多少度"。

    步数支持数值（int）或符号（str，CST参数名）：
        .move(19, 'c')          # 数值步数，硬编码
        .move('x1', 'c')        # 符号步数，生成参数化 CST 表达式
    """

    def __init__(self, a, name='path'):
        self.a = a
        self.name = name
        self._points = []
        self._current_r = None
        self._current_c = None
        self._current_dir = None
        self._dirty_turn = False

    def start(self, r, c, direction=(0, 1)):
        """
        设置起点。r/c 可以是数值（int）或符号（str，CST参数名）。

        :param r: int/str, 起点行坐标
        :param c: int/str, 起点列坐标
        :param direction: 初始行进方向，默认 +c（0度，从左到右）
        """
        self._points = [(r, c)]
        self._current_r, self._current_c = r, c
        self._current_dir = _resolve_direction(direction) or (0, 1)
        self._dirty_turn = False
        return self

    def move(self, steps, direction='along'):
        """
        从当前位置沿指定方向移动 steps 格，将新位置加入路径。

        :param steps: int/str, 移动步数。数值为硬编码，字符串为 CST 参数名（符号）
        :param direction: 'along'（当前方向）/ 'c'/'r'/'rc' 等名称 / (dr,dc) tuple
        """
        if self._current_r is None:
            raise RuntimeError("请先调用 .start(r, c) 设置起点")
        if _is_numeric(steps) and steps <= 0:
            return self
        dr, dc = self._resolve_move_direction(direction)
        # 符号运算：new_r = current_r + steps * dr, new_c = current_c + steps * dc
        new_r = _symbolic_add(self._current_r, _symbolic_mul(steps, dr))
        new_c = _symbolic_add(self._current_c, _symbolic_mul(steps, dc))
        new_point = (new_r, new_c)
        if not self._points or new_point != self._points[-1]:
            self._points.append(new_point)
        self._current_r, self._current_c = new_r, new_c
        self._current_dir = (dr, dc)
        self._dirty_turn = False
        return self

    def turn(self, angle):
        """
        旋转当前行进方向，不移动。
        angle: 60 的整数倍，正值逆时针，负值顺时针。
        """
        if self._current_dir is None:
            raise RuntimeError("请先调用 .start() 设置初始方向")
        if angle % 60 != 0:
            raise ValueError(f"转角必须是 60 度的整数倍，收到 {angle} 度")
        idx = _direction_to_index(*self._current_dir)
        new_idx = (idx + angle // 60) % 6
        self._current_dir = DIRECTIONS[new_idx]
        self._dirty_turn = True
        return self

    def line_to(self, r, c):
        """
        直接移动到指定 (r,c)，自动推断并更新行进方向。
        r/c 可以是数值或符号。
        """
        if self._current_r is None:
            raise RuntimeError("请先调用 .start(r, c) 设置起点")
        dr = _symbolic_add(r, _symbolic_mul(self._current_r, -1)) if isinstance(r, str) or isinstance(self._current_r, str) else int(r) - int(self._current_r)
        dc = _symbolic_add(c, _symbolic_mul(self._current_c, -1)) if isinstance(c, str) or isinstance(self._current_c, str) else int(c) - int(self._current_c)
        if _is_numeric(dr) and _is_numeric(dc) and dr == 0 and dc == 0:
            return self
        # 对于数值位移，推断方向
        if _is_numeric(dr) and _is_numeric(dc):
            gcd = abs(int(np.gcd(dr, dc))) if (dr != 0 or dc != 0) else 1
            unit_dr, unit_dc = dr // gcd, dc // gcd
            if (unit_dr, unit_dc) in DIRECTIONS:
                self._current_dir = (unit_dr, unit_dc)
            else:
                import warnings
                warnings.warn(f"从 ({self._current_r},{self._current_c}) 到 ({r},{c}) "
                              f"的方向 ({unit_dr},{unit_dc}) 不在 6 个主方向上")
                self._current_dir = None
        new_point = (r, c)
        if new_point != self._points[-1]:
            self._points.append(new_point)
        self._current_r, self._current_c = r, c
        self._dirty_turn = False
        return self

    def close(self):
        """闭合路径：将最后一个点连接回起点。"""
        if len(self._points) < 2:
            return self
        start = self._points[0]
        if self._points[-1] != start:
            self._points.append(start)
            self._current_r, self._current_c = start
        return self

    def _resolve_move_direction(self, direction):
        if direction == 'along' or direction is None:
            if self._current_dir is None:
                raise RuntimeError("当前方向未定义，无法使用 'along'，请指定方向或先 turn()")
            return self._current_dir
        return _resolve_direction(direction)

    def build(self, param_values=None):
        """
        构建 TopoPath 实例。

        :param param_values: dict, 符号参数的数值（用于预览和计算），
                             如 {'x1': 18, 'y1': 14}。纯数值路径不需要。
        """
        if not self._points:
            raise RuntimeError("路径为空，请先调用 .start()")
        if self._dirty_turn:
            import warnings
            warnings.warn("最后一次 turn() 之后没有 move()，旋转未产生新的路径点")
        return TopoPath(self._points, a=self.a, name=self.name, param_values=param_values)


# ============================================================
# TopoPath — 路径统一管理类（支持符号坐标）
# ============================================================
class TopoPath:
    """
    拓扑路径统一坐标管理。
    唯一数据源是三角晶格坐标 (r, c)，直角坐标和 CST 表达式自动推导。

    支持两种坐标模式：
      1. 数值坐标：r/c 为 int，直接计算，CST 表达式为硬编码（如 '18*a'）
      2. 符号坐标：r/c 为 str（CST参数名），CST 表达式参数化（如 'x1*a'），
         预览和计算需要 param_values 提供数值
    """

    def __init__(self, path_lattice, a, name='path', param_values=None):
        """
        :param path_lattice: list of (r, c)，r/c 可以是 int（数值）或 str（符号/CST参数名）
        :param a: float, 晶格常数 mm
        :param name: str, 路径名称，用于 CST 参数前缀
        :param param_values: dict, 符号参数的数值，如 {'x1': 18, 'y1': 14}
        """
        self.path_lattice = list(path_lattice)  # 原始坐标（可能含符号）
        if len(self.path_lattice) == 0 or len(self.path_lattice[0]) != 2:
            raise ValueError(f"path_lattice 应为 (N,2) 列表，收到 {self.path_lattice}")
        self.a = float(a)
        self.name = name
        self.param_values = param_values or {}

        # 数值化路径（用于预览和计算）
        self._path_numeric = self._resolve_numeric(self.path_lattice, self.param_values)
        if self._path_numeric is not None:
            self._xy = self._lattice_to_xy(self._path_numeric, self.a)
        else:
            self._xy = None

    # ---- 符号解析 ----

    @staticmethod
    def _resolve_numeric(path_lattice, param_values):
        """
        将符号坐标解析为数值坐标。如果有无法解析的符号，返回 None。
        """
        numeric = []
        for r, c in path_lattice:
            rn = _resolve_symbol(r, param_values)
            cn = _resolve_symbol(c, param_values)
            if not _is_numeric(rn) or not _is_numeric(cn):
                return None  # 仍有未解析的符号
            numeric.append((int(rn), int(cn)))
        return np.array(numeric, dtype=int)

    @property
    def has_symbols(self):
        """是否包含符号坐标。"""
        return any(isinstance(r, str) or isinstance(c, str) for r, c in self.path_lattice)

    # ---- 静态工具 ----

    @staticmethod
    def _lattice_to_xy(path, a):
        """(r,c) -> (x,y)，与 path_loc_to_xy 完全一致"""
        r = path[:, 0].astype(float)
        c = path[:, 1].astype(float)
        x = c * a + r * (a / 2)
        y = r * (a / 2 * np.sqrt(3))
        return np.column_stack((x, y))

    @staticmethod
    def lattice_to_cst_expr(r, c):
        """
        (r,c) -> CST 表达式字符串 (px, py)。
        支持 r/c 为数值（int）或符号（str，CST参数表达式）。

        简化规则：r=0 时 py='0'，r=0 时 px 不含 r 项。
        含运算符的符号表达式自动加括号（如 'x1-y1' -> '(x1-y1)*a'）。
        """
        def _wrap(s):
            """如果字符串包含 + 或 -（非开头负号），则加括号确保运算优先级。"""
            if isinstance(s, str):
                has_plus = '+' in s
                has_minus_internal = s.count('-') > 0 and not s.startswith('-')
                if has_plus or has_minus_internal:
                    return f'({s})'
            return s

        c_w = _wrap(c)
        r_w = _wrap(r)

        if _is_zero(r):
            px = f'{c_w}*a'
        elif _is_zero(c):
            px = f'{r_w}*a/2'
        else:
            px = f'{c_w}*a+{r_w}*a/2'
        py = '0' if _is_zero(r) else f'{r_w}*a/2*sqr(3)'
        return px, py

    # ---- 属性 ----

    @property
    def xy(self):
        """直角坐标（数值路径可用；符号路径需要 param_values）。"""
        if self._xy is None:
            raise RuntimeError("符号路径无法直接计算 xy，请提供 param_values 或使用 lattice_symbolic")
        return self._xy.copy()

    @property
    def lattice(self):
        """数值化的晶格坐标（用于计算）。"""
        if self._path_numeric is None:
            raise RuntimeError("符号路径无法直接获取数值 lattice，请提供 param_values")
        return self._path_numeric.copy()

    @property
    def lattice_symbolic(self):
        """原始晶格坐标（可能含符号，用于 CST 表达式生成）。"""
        return list(self.path_lattice)

    def __len__(self):
        return len(self.path_lattice)

    def __getitem__(self, idx):
        return tuple(self.path_lattice[idx])

    def __repr__(self):
        pts = ', '.join(f'({r},{c})' for r, c in self.path_lattice)
        sym = ' [symbolic]' if self.has_symbols else ''
        return f"TopoPath(name='{self.name}', a={self.a}{sym}, points=[{pts}])"

    # ---- CST 集成 ----

    def auto_define_cst_params(self, app, prefix=None):
        """
        自动在 CST 中定义所有路径点的 px/py 参数（p1x,p1y,p2x,p2y,...）。
        使用符号坐标生成参数化表达式（如 'x1*a'），可在 CST 中调整参数。
        """
        pfx = prefix or self.name
        for i, (r, c) in enumerate(self.path_lattice):
            px, py = self.lattice_to_cst_expr(r, c)
            app.para(f'{pfx}{i+1}x', px)
            app.para(f'{pfx}{i+1}y', py)

    def get_cst_point(self, idx, prefix=None):
        """获取第 idx 个点的 CST 参数名元组 ('p1x', 'p1y')"""
        pfx = prefix or self.name
        return (f'{pfx}{idx+1}x', f'{pfx}{idx+1}y')

    def get_cst_polygon(self, indices, prefix=None):
        """获取指定索引点组成的多边形顶点列表（CST 表达式格式）。"""
        pfx = prefix or self.name
        return [[f'{pfx}{i+1}x', f'{pfx}{i+1}y'] for i in indices]

    # ---- 边界（需要数值坐标） ----

    def get_bounding_box(self, margin_c=1, margin_r=1):
        """从路径自动推导边界范围，返回 (xmin, xmax, ymin, ymax)。需要数值坐标。"""
        if self._path_numeric is None:
            raise RuntimeError("符号路径无法计算边界框，请提供 param_values")
        r_min = self._path_numeric[:, 0].min() - margin_r
        r_max = self._path_numeric[:, 0].max() + margin_r
        c_min = self._path_numeric[:, 1].min() - margin_c
        c_max = self._path_numeric[:, 1].max() + margin_c
        corners = np.array([
            [r_min, c_min], [r_min, c_max],
            [r_max, c_min], [r_max, c_max],
        ])
        xy_corners = self._lattice_to_xy(corners, self.a)
        return (float(xy_corners[:, 0].min()), float(xy_corners[:, 0].max()),
                float(xy_corners[:, 1].min()), float(xy_corners[:, 1].max()))

    def get_array_range(self):
        """自动推导光子晶体阵列的复制范围，返回 (xup, yup, ydn)。需要数值坐标。"""
        if self._path_numeric is None:
            raise RuntimeError("符号路径无法计算阵列范围，请提供 param_values")
        r_vals = self._path_numeric[:, 0]
        c_vals = self._path_numeric[:, 1]
        xup = int(c_vals.max()) + int(abs(r_vals.max()) / 2) + 1
        yup = int(abs(r_vals.max())) + 1
        ydn = int(abs(r_vals.min())) + 1
        return xup, yup, ydn

    # ---- 区域多边形（使用符号坐标，生成参数化表达式） ----

    def build_substrate_polygon(self, y_margin='e2', prefix=None):
        """
        自动生成基板的 polyline 顶点（路径上下各扩展 y_margin 的带状区域）。

        **顶点绕向固定为逆时针（CCW）**，这是本库的硬约定：
        CST 的 ``ExtrudeCurve`` 沿多边形**法向**拉伸，而法向由顶点绕向决定 ——
        CCW（有向面积 > 0）拉伸到 **+z**，CW 拉伸到 **−z**。
        调用方统一「CCW + 内部 ``translate -h/2``」把实体在 z 方向居中；
        绕向反了会让实体与其它部件在 z 上差一个 ``h``，
        布尔求交得到空集却**不会报错**。

        顶点顺序：**下侧偏移链正向** → **上侧偏移链反向** → 回到起点。
        两条偏移链都包含**每一个**路径点，因此对拐弯路径也能得到确定绕向的带状多边形
        （只取两端偏移点的稀疏写法，其绕向会随路径拐弯方向翻转，不能保证 CCW）。

        :param y_margin: str, 路径上下扩展量（CST 参数名或表达式），默认 'e2'
        :param prefix: str/None, CST 参数名前缀，None 时用 ``self.name``
        :return: list, 闭合的顶点列表（首尾相同）
        """
        pfx = prefix or self.name
        n = len(self.path_lattice)
        pts = []
        for i in range(n):
            px, py = self.get_cst_point(i, pfx)
            pts.append([px, f'{py}-{y_margin}'])
        for i in range(n - 1, -1, -1):
            px, py = self.get_cst_point(i, pfx)
            pts.append([px, f'{py}+{y_margin}'])
        pts.append(pts[0])
        return pts

    def build_vpc_area_polygon(self, side='upper', y_margin='e2', prefix=None):
        """
        自动生成 VPC-A/B 区域的裁剪多边形。``side='upper'`` 或 ``'lower'``。

        与 :meth:`build_substrate_polygon` 相同，**顶点绕向固定为逆时针（CCW）**，
        且两条边界链都包含每一个路径点（拐弯路径下绕向才确定）。

        - ``'upper'``：**路径链正向** → **上侧偏移链反向**（路径是下边界）
        - ``'lower'``：**下侧偏移链正向** → **路径链反向**（路径是上边界）

        :param side: str, 'upper'（基板路径以上）或 'lower'（路径以下）
        :param y_margin: str, 扩展量，默认 'e2'
        :param prefix: str/None, CST 参数名前缀，None 时用 ``self.name``
        :return: list, 闭合的顶点列表（首尾相同）
        :raises ValueError: ``side`` 不是 'upper' / 'lower'
        """
        if side not in ('upper', 'lower'):
            raise ValueError(f"side 必须是 'upper' 或 'lower'，收到 '{side}'")

        pfx = prefix or self.name
        n = len(self.path_lattice)
        pts = []
        if side == 'upper':
            for i in range(n):
                pts.append(list(self.get_cst_point(i, pfx)))
            for i in range(n - 1, -1, -1):
                px, py = self.get_cst_point(i, pfx)
                pts.append([px, f'{py}+{y_margin}'])
        else:
            for i in range(n):
                px, py = self.get_cst_point(i, pfx)
                pts.append([px, f'{py}-{y_margin}'])
            for i in range(n - 1, -1, -1):
                pts.append(list(self.get_cst_point(i, pfx)))
        pts.append(pts[0])
        return pts

    # ---- 方向分析（需要数值坐标） ----

    def segment_directions(self):
        """返回每段路径的方向向量 (dr, dc) 列表。需要数值坐标。"""
        if self._path_numeric is None:
            raise RuntimeError("符号路径无法计算方向，请提供 param_values")
        dirs = []
        for i in range(len(self._path_numeric) - 1):
            dr = self._path_numeric[i + 1, 0] - self._path_numeric[i, 0]
            dc = self._path_numeric[i + 1, 1] - self._path_numeric[i, 1]
            gcd = abs(int(np.gcd(dr, dc))) if (dr != 0 or dc != 0) else 1
            dirs.append((int(dr // gcd), int(dc // gcd)))
        return dirs

    def segment_angles(self):
        """返回每段路径的物理角度（度）。需要数值坐标。"""
        if self._path_numeric is None:
            raise RuntimeError("符号路径无法计算角度，请提供 param_values")
        angles = []
        for dr, dc in self.segment_directions():
            x = dc * self.a + dr * (self.a / 2)
            y = dr * (self.a / 2 * np.sqrt(3))
            angles.append(float(np.degrees(np.arctan2(y, x))))
        return angles

    def is_straight(self):
        return len(self.path_lattice) <= 2

    def has_bend(self):
        return len(self.path_lattice) > 2

    # ---- 预览（需要数值坐标） ----

    def preview(self, ax=None, show_grid=True, color='green', marker='o',
                linewidth=2, markersize=6, label=None,
                lattice_rows=None, lattice_cols=None):
        """matplotlib 预览：画出路径 + 可选晶格背景。返回 (fig, ax)。需要数值坐标。"""
        if self._xy is None:
            raise RuntimeError("符号路径无法预览，请在 build() 时提供 param_values")
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 8))
        else:
            fig = ax.figure

        if show_grid:
            try:
                from mesh_grid.tri_grid import plot_triangle_grid
                if lattice_rows is None:
                    r_min = self._path_numeric[:, 0].min() - 2
                    r_max = self._path_numeric[:, 0].max() + 2
                    lattice_rows = (r_min, r_max)
                if lattice_cols is None:
                    c_min = self._path_numeric[:, 1].min() - 2
                    c_max = self._path_numeric[:, 1].max() + 2
                    lattice_cols = (c_min, c_max)
                h = self.a * np.sin(np.deg2rad(60))
                r = self.a / np.sqrt(3)
                offset = (self.a / 2, h - r)
                plot_triangle_grid(lattice_rows, lattice_cols, self.a,
                                   offset=offset, show_labels=False, show_points=False, ax=ax)
            except ImportError:
                pass

        lbl = label or f'{self.name} ({len(self)} points)'
        ax.plot(self._xy[:, 0], self._xy[:, 1], color=color, lw=linewidth,
                marker=marker, markersize=markersize, label=lbl)

        for i, ((r, c), (x, y)) in enumerate(zip(self._path_numeric, self._xy)):
            ax.annotate(f'({r},{c})', (x, y), textcoords="offset points",
                        xytext=(8, 8), fontsize=8, color=color)

        ax.set_aspect('equal')
        ax.set_xlabel('x (mm)')
        ax.set_ylabel('y (mm)')
        ax.set_title(f'TopoPath: {self.name}  (a={self.a} mm)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        return fig, ax

    # ---- 构建器入口 ----

    @staticmethod
    def builder(a, name='path'):
        return TopoPathBuilder(a, name)

    @staticmethod
    def from_lattice(points, a, name='path', param_values=None):
        """从 (r,c) 列表直接创建（兼容旧代码）。"""
        return TopoPath(list(points), a=a, name=name, param_values=param_values)
