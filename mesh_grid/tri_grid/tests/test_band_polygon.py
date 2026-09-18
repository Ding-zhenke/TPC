# -*- coding: utf-8 -*-
"""
弯折路径的带状多边形测试（P4/V1 修复）
=======================================

守住什么
--------
真机实测（CST 2026，2026-09）发现：基板/VPC 的偏移多边形原先**只在 y 方向偏移**
（``py ± y_margin``），直线路径没问题，但**拐弯路径**上两条链互相穿插 → 自交多边形
→ CST 直接拒绝拉伸：

    (&H8000ffff) The specified curve is not closed and planar.

修复：按**段法向 + miter 连接**偏移（`mesh_grid/tri_grid/topo_path.py` 的
`_offset_chains()`），带宽处处一致，且偏移量仍全部由 CST 表达式
（``sqr(3)`` / ``y_margin``）表达，不引入硬编码数值。

本文件钉住三件事：

1. **直线路径逐字节不变**（向后兼容，直波导不受影响）；
2. **弯折路径的多边形是简单多边形**（数值化后不存在自交边）；
3. **180° 折返**给出明确错误，而不是悄悄产出一个坏多边形。

运行方式::

    pytest mesh_grid/tri_grid/tests/test_band_polygon.py -v
"""

import math
import os
import re
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from mesh_grid.tri_grid import TopoPath          # noqa: E402

A = 0.2425
E2 = A * math.sqrt(3) / 2
MARGIN = E2                                      # 真实用量就是 e2 量级（窄带）


def _numeric(pts, param_values):
    """把 CST 表达式顶点数值化（参数替换 + sqr(3)），返回 [(x, y), ...]。"""
    out = []
    for x_expr, y_expr in pts:
        pair = []
        for token in (x_expr, y_expr):
            expr = str(token)
            for name in sorted(param_values, key=len, reverse=True):
                expr = re.sub(rf'\b{re.escape(name)}\b',
                              str(float(param_values[name])), expr)
            expr = expr.replace('sqr(3)', f'({math.sqrt(3)!r})').replace('^', '**')
            pair.append(float(eval(expr, {'__builtins__': {}}, {})))  # noqa: S307
        out.append(tuple(pair))
    return out


def _segments_intersect(p1, p2, p3, p4):
    """两线段是否真正相交（忽略共享端点）。"""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1, d2 = cross(p3, p4, p1), cross(p3, p4, p2)
    d3, d4 = cross(p1, p2, p3), cross(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    return False


def _self_intersections(points):
    """返回自交边对数（相邻边共享端点不算）。"""
    n = len(points)
    hits = []
    for i in range(n - 1):
        for j in range(i + 1, n - 1):
            if abs(i - j) <= 1 or (i == 0 and j == n - 2):
                continue                              # 相邻边 / 闭合边
            if _segments_intersect(points[i], points[i + 1],
                                   points[j], points[j + 1]):
                hits.append((i, j))
    return hits


def _antenna_path(bend=60):
    """
    天线路径：直段 + 拐弯臂。

    2026-09-17 `UnitAntenna` 的 `bend_angle` 改为**张角**语义后，模板实际下发的
    单臂偏角是 ``±bend_angle/2``：AB = `turn(+60)`、BA = `turn(-60)`。
    这里默认给**新路径**（AB），并把旧的 120° 折回路径也保留为参数，
    免得改语义后几何回归测试还只覆盖旧形状。
    """
    return (TopoPath.builder(A, name='p')
            .start(0, -1).move(19, 'c').turn(bend).move(14, 'along').build())


#: 三种弯折形状：新 AB、新 BA（镜像）、旧 120°（折回，曾经真机跑过的那条）
BENT_PATHS = {
    'ab60': 60,
    'ba-60': -60,
    'legacy120': 120,
}


def _values(path):
    """路径点的数值坐标（供表达式数值化用）。"""
    values = {'e2': E2, 'y_margin': MARGIN}
    for index, (x, y) in enumerate(path.xy):
        values[f'p{index + 1}x'] = float(x)
        values[f'p{index + 1}y'] = float(y)
    return values


# ============================================================
# 1. 直线路径：逐字节向后兼容
# ============================================================

def test_straight_substrate_polygon_unchanged():
    """直波导的多边形必须与旧实现逐字节相同（这是向后兼容的硬要求）。"""
    path = TopoPath.builder(A, name='p').start(0, -1).move(19, 'c').build()
    assert path.build_substrate_polygon() == [
        ['p1x', 'p1y-e2'], ['p2x', 'p2y-e2'],
        ['p2x', 'p2y+e2'], ['p1x', 'p1y+e2'], ['p1x', 'p1y-e2']]


def test_straight_vpc_polygons_unchanged():
    """VPC 的上/下半区多边形同样逐字节不变。"""
    path = TopoPath.builder(A, name='p').start(0, -1).move(19, 'c').build()
    assert path.build_vpc_area_polygon('upper') == [
        ['p1x', 'p1y'], ['p2x', 'p2y'],
        ['p2x', 'p2y+e2'], ['p1x', 'p1y+e2'], ['p1x', 'p1y']]
    assert path.build_vpc_area_polygon('lower') == [
        ['p1x', 'p1y-e2'], ['p2x', 'p2y-e2'],
        ['p2x', 'p2y'], ['p1x', 'p1y'], ['p1x', 'p1y-e2']]


# ============================================================
# 2. 弯折路径：每段一个简单四边形（构建器实际使用的形式）
# ============================================================

@pytest.mark.parametrize('name,bend', sorted(BENT_PATHS.items()))
def test_segment_quads_are_simple_for_bent_path(name, bend):
    """核心回归：弯折路径必须拆成每段一个**不自交**的四边形（三种弯折形状都要）。"""
    path = _antenna_path(bend)
    for side in (None, 'upper', 'lower'):
        rings = path.build_segment_band_polygons(y_margin='y_margin', side=side)
        assert len(rings) >= len(path.path_lattice) - 1, \
            '至少每段一个四边形（拐角处还会补一块）'
        values = _values(path)
        for ring in rings:
            numeric = _numeric(ring, values)
            assert not _self_intersections(numeric), \
                f'{name} side={side} 的四边形自交：{numeric}'


@pytest.mark.parametrize('name,bend', sorted(BENT_PATHS.items()))
def test_segment_quads_are_ccw(name, bend):
    """每个四边形都要 CCW（否则拉伸方向反了，实体在 z 上错开一个 h）。"""
    path = _antenna_path(bend)
    values = _values(path)
    for side in (None, 'upper', 'lower'):
        for ring in path.build_segment_band_polygons(y_margin='y_margin',
                                                     side=side):
            numeric = _numeric(ring, values)
            area = 0.5 * sum(numeric[i][0] * numeric[i + 1][1]
                             - numeric[i + 1][0] * numeric[i][1]
                             for i in range(len(numeric) - 1))
            assert area > 0, f'{name} side={side} 的四边形不是 CCW：{numeric}'


def test_new_antenna_paths_are_mirror_images():
    """
    新语义下 AB / BA 的路径必须互为镜像（这是 `bend_angle` 张角口径的直接后果）。

    AB `turn(+60)` → 臂端 (6.0625, +2.9402)；BA `turn(-60)` → (6.0625, -2.9402)，
    与参考工程的 `px3/py3` 逐位一致（见 `docs/validation/p4_real_machine_evidence.md` §4.5）。
    """
    ab = _antenna_path(60)
    ba = _antenna_path(-60)
    assert list(ab.path_lattice[:2]) == list(ba.path_lattice[:2])
    (ab_end_x, ab_end_y) = (float(ab.xy[-1][0]), float(ab.xy[-1][1]))
    (ba_end_x, ba_end_y) = (float(ba.xy[-1][0]), float(ba.xy[-1][1]))
    assert ab_end_x == pytest.approx(ba_end_x, abs=1e-9)
    assert ab_end_y == pytest.approx(-ba_end_y, abs=1e-9)
    assert ab_end_x == pytest.approx(6.0625, abs=1e-9)


def test_straight_path_quads_equal_legacy_polygons():
    """直线路径：四边形与旧的多边形**逐字节相同**（向后兼容）。"""
    path = TopoPath.builder(A, name='p').start(0, -1).move(19, 'c').build()
    band = path.build_segment_band_polygons(side=None)
    assert len(band) == 1
    assert band[0] == path.build_substrate_polygon()
    assert path.build_segment_band_polygons(side='upper')[0] == \
        path.build_vpc_area_polygon('upper')
    assert path.build_segment_band_polygons(side='lower')[0] == \
        path.build_vpc_area_polygon('lower')


@pytest.mark.parametrize('name,bend', sorted(BENT_PATHS.items()))
def test_quads_union_covers_the_band(name, bend):
    """
    覆盖性检查（比面积求和更有意义）：带内的采样点必须落在**至少一个**四边形内。

    采样：沿路径取点、再沿该点法向在 ``[-margin, +margin]`` 上取若干位置。
    """
    path = _antenna_path(bend)
    xy = [(float(x), float(y)) for x, y in path.xy]
    for factor in (1.0, 3.0, 7.0):
        margin = E2 * factor
        values = _values(path)
        values['y_margin'] = margin
        rings = [_numeric(r, values) for r in
                 path.build_segment_band_polygons(y_margin='y_margin', side=None)]
        # 沿每段采样
        for i in range(len(xy) - 1):
            for t in (0.1, 0.3, 0.5, 0.7, 0.9):
                px = xy[i][0] + t * (xy[i + 1][0] - xy[i][0])
                py = xy[i][1] + t * (xy[i + 1][1] - xy[i][1])
                dx = xy[i + 1][0] - xy[i][0]
                dy = xy[i + 1][1] - xy[i][1]
                length = math.hypot(dx, dy)
                # 左法向（与库的约定一致）
                nx, ny = -dy / length, dx / length
                for offset in (-0.9 * margin, -0.4 * margin, 0.0,
                               0.4 * margin, 0.9 * margin):
                    point = (px + nx * offset, py + ny * offset)
                    assert any(_point_in_polygon(point, ring)
                               for ring in rings), \
                        (f'{name} 带内点 {point}（margin={margin:.4f}）'
                         f'没有被任何四边形覆盖；rings={rings}')


def _point_in_polygon(point, polygon):
    """射线法：点是否在多边形内（含边界附近）。"""
    x, y = point
    inside = False
    n = len(polygon) - 1                          # 首尾重复
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x_cross > x:
                inside = not inside
    return inside


@pytest.mark.parametrize('name,bend', sorted(BENT_PATHS.items()))
def test_bent_polygon_expression_has_miter_and_no_hardcoded_numbers(name, bend):
    """偏移表达式必须含 sqr(3)（miter），且不得出现硬编码小数。"""
    path = _antenna_path(bend)
    rings = path.build_segment_band_polygons(y_margin='y_margin', side=None)
    joined = ' '.join(x for ring in rings for pair in ring for x in pair)
    assert 'sqr(3)' in joined, f'{name} 没有 miter 偏移：{joined}'
    assert not re.search(r'(?<![\w.])\d+\.\d+(?![\w.])', joined), \
        f'{name} 表达式里出现硬编码小数：{joined}'


# ============================================================
# 3. 退化情形
# ============================================================

def test_fold_back_path_is_rejected_clearly():
    """180° 折返（沿原路返回）时带宽无定义，要给出明确错误。"""
    path = (TopoPath.builder(A, name='p')
            .start(0, 0).move(10, 'c').turn(180).move(5, 'along').build())
    with pytest.raises(ValueError) as excinfo:
        path.build_substrate_polygon()
    assert '180' in str(excinfo.value)


def test_single_step_path_still_works():
    """只有一段的路径（两点）走法向偏移，与旧行为一致。"""
    path = TopoPath.builder(A, name='p').start(0, 0).move(5, 'c').build()
    assert path.build_substrate_polygon() == [
        ['p1x', 'p1y-e2'], ['p2x', 'p2y-e2'],
        ['p2x', 'p2y+e2'], ['p1x', 'p1y+e2'], ['p1x', 'p1y-e2']]
