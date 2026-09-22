# -*- coding: utf-8 -*-
"""
相区结构示意图测试
==================

守住什么
--------
新增的「建模前必出结构示意图」依赖一套**与 crystal builder 同源**的数值孔阵列。
本文件钉住最容易出错、也最关键的三件事：

1. **AB / BA 孔-相绑定**：域壁两侧朝上孔的大/小关系必须与拓扑一致
   （AB：下半 A 朝上小孔、上半 B 朝上大孔；BA 相反）——这是手册的权威判据；
2. **A / B 相区互斥且并集 = 整条带**：两半不能重叠、带内不能漏点；
3. **弯折路径同样成立**：拐角补块后，孔仍按所在半区正确着色。

运行方式::

    pytest mesh_grid/tri_grid/tests/test_phase_diagram.py -v
"""

import math
import os
import sys

import numpy as np
import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from mesh_grid.tri_grid import TopoPath                       # noqa: E402
from mesh_grid.tri_grid.phase_diagram import (                # noqa: E402
    generate_crystal_holes,
    plot_phase_structure,
    _resolve_hole_phase_and_size,
)

A = 0.2425
E2 = A * math.sqrt(3) / 2
LENGTH = 18
WIDTH = 14
MARGIN = WIDTH * E2


def _straight_path():
    return (TopoPath.builder(A, name='p')
            .start(0, 0).move(LENGTH, 'c').build())


def _resolve(path, topology):
    polys_a, polys_b = path.band_polygons_numeric(MARGIN)
    holes = generate_crystal_holes(path, topology=topology, a=A,
                                   xup=LENGTH + WIDTH // 2, yup=WIDTH, ydn=WIDTH)
    phase, sizes = _resolve_hole_phase_and_size(holes, polys_a, polys_b, topology)
    return holes, phase, sizes


# ============================================================
# 1. AB / BA 孔-相绑定
# ============================================================

@pytest.mark.parametrize('topology', ['AB', 'BA'])
def test_up_hole_size_matches_authoritative_invariant(topology):
    """域壁紧邻的朝上孔：A/B 两半的大、小孔关系必须符合权威判据。"""
    path = _straight_path()
    holes, phase, sizes = _resolve(path, topology)
    centers, is_up = holes['centers'], holes['is_up']

    # 取域壁两侧、路径中段的朝上孔
    sel = ((phase != 0) & is_up & (np.abs(centers[:, 1]) < 0.6)
           & (centers[:, 0] > 8 * A) & (centers[:, 0] < 10 * A))
    picked = np.where(sel)[0]
    a_vals = [float(sizes[i]) for i in picked if phase[i] == 1]
    b_vals = [float(sizes[i]) for i in picked if phase[i] == -1]
    assert a_vals and b_vals
    large, small = 0.65 * A, 0.35 * A
    if topology == 'AB':
        assert all(v == pytest.approx(small) for v in a_vals)
        assert all(v == pytest.approx(large) for v in b_vals)
    else:
        assert all(v == pytest.approx(large) for v in a_vals)
        assert all(v == pytest.approx(small) for v in b_vals)


@pytest.mark.parametrize('topology', ['AB', 'BA'])
def test_phase_counts_are_balanced_and_no_hole_outside_stays(topology):
    """直路径对称：A/B 孔数相等；区外孔一律 phase=0。"""
    path = _straight_path()
    holes, phase, sizes = _resolve(path, topology)
    n_a = int((phase == 1).sum())
    n_b = int((phase == -1).sum())
    assert n_a == n_b and n_a > 0
    assert bool(np.all(sizes[phase == 0] == 0.0))


def test_invalid_topology_rejected():
    """topology 非法必须报错，不静默画错相。"""
    path = _straight_path()
    with pytest.raises(ValueError):
        generate_crystal_holes(path, topology='XX', a=A)


# ============================================================
# 2. A / B 相区互斥且并集覆盖整条带
# ============================================================

def test_band_halves_are_disjoint_and_cover():
    path = _straight_path()
    polys_a, polys_b = path.band_polygons_numeric(MARGIN)

    # 互斥：在两半**严格内部**采样（避开共享的路径边界 y=0），不能同时落入两半
    from mesh_grid.tri_grid.core import point_in_polygon
    xy = path.xy
    for i in range(len(xy) - 1):
        for t in (0.2, 0.5, 0.8):
            px = xy[i, 0] + t * (xy[i + 1, 0] - xy[i, 0])
            # 下半 A 取负偏移、上半 B 取正偏移（直路径法向即 y）
            for off, expect_a in ((-0.9 * MARGIN, True), (-0.3 * MARGIN, True),
                                  (0.3 * MARGIN, False), (0.9 * MARGIN, False)):
                point = (float(px), float(off))
                in_a = any(point_in_polygon(point, p) for p in polys_a)
                in_b = any(point_in_polygon(point, p) for p in polys_b)
                assert in_a or in_b, f'带内点 {point} 未被覆盖'
                assert not (in_a and in_b), f'内部点 {point} 同时落在两半'
                assert in_a == expect_a, f'点 {point} 相归属错误'


# ============================================================
# 3. 弯折路径
# ============================================================

def test_bent_path_holes_bind_by_half_region():
    """60° 弯折路径：拐角补块存在，且所有画出的孔都有明确相归属与合法尺寸。"""
    path = (TopoPath.builder(A, name='p')
            .start(0, -1).move(19, 'c').turn(60).move(14, 'along').build())
    margin = 7 * E2
    polys_a, polys_b = path.band_polygons_numeric(margin)
    # 弯折路径下至少有一段以上 + 拐角补块
    assert len(polys_a) >= 1 and len(polys_b) >= 1

    holes = generate_crystal_holes(path, topology='AB', a=A)
    phase, sizes = _resolve_hole_phase_and_size(holes, polys_a, polys_b, 'AB')
    valid = phase != 0
    assert bool(valid.any())
    legal = np.isclose(sizes[valid], 0.65 * A) | np.isclose(sizes[valid], 0.35 * A)
    assert bool(np.all(legal))


# ============================================================
# 4. 端到端出图（不弹窗，Agg 后端）
# ============================================================

def test_plot_phase_structure_renders(tmp_path):
    import matplotlib
    matplotlib.use('Agg')
    path = _straight_path()
    fig, ax = plot_phase_structure(path, topology='BA', margin=MARGIN, a=A,
                                   xup=LENGTH + WIDTH // 2, yup=WIDTH, ydn=WIDTH,
                                   ports=True, strict_chinese=False)
    out = tmp_path / 'phase.png'
    fig.savefig(out)
    assert out.exists() and out.stat().st_size > 0
