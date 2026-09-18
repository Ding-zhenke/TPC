# -*- coding: utf-8 -*-
r"""
`builders/lens.py` 的**就地 hexagon 环透镜**（P5，覆盖参考 33 个 notebook）
============================================================================

这一半**完全不需要 CST**：孔集合（`grin_ring_holes()`）是纯几何，
`build_grin_lens_insitu()` 的下发序列用一个记录型假 `app` 就能逐条核对。

钉住的事实（都能追到参考 notebook `功分器加天线\1分4\…circle_DF.ipynb`）：

1. `HEX_SIZE = a/sqr(3)/2`、`a2 = HEX_SIZE*sqr(3)`、`d0 = d0_layers*HEX_SIZE*2*sqr(3)`、
   `N = n_layers`（参考 `(y[1]+2)*2`）；
2. 孔集合 = **N 层六边形网格的第一象限格点**（另一半靠 CST 侧 `mirror` 补齐）；
3. 半径分两段：`distance < d0` ⇒ 常量 `r1`；否则 ⇒ `r1+(r2-r1)*(dist-d0)/(N*a2-d0)`；
4. 下发序列：`hexagon` ×象限孔数 → `add` ×(孔数−1) → `mirror` → `Cylinder` +
   `Square` + `subtract` → `subtract`（取负形）→ `translate` → 放置（`translate` + `rotation`）；
5. 表达式里引用到的 6 个参数（`HEX_SIZE / a2 / N / d0 / r1 / r2`）必须**先登记** —— 
   缺一个 CST 就弹「请输入变量值」的模态对话框把脚本挂住（P4/V6 真机教训）；
6. 渐变区间为空（`N*a2 <= d0`）时**明确报错**，不默默退化成「全是 r1」。

真机（只建模、不求解）那一半见 `scripts/verify_grin_lens_insitu_real.py`。

运行方式::

    pytest topo_modeler/tests/test_grin_lens_insitu.py -v
"""

import os
import re
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from topo_modeler.builders import (                    # noqa: E402
    DEFAULT_D0_LAYERS,
    DEFAULT_RING_LAYERS,
    build_grin_lens_insitu,
    grin_ring_holes,
)

A = 0.2425
SMALL = dict(n_layers=10, d0_layers=3)                 # 91 个象限孔，测试跑得快


class _FakeApp:
    """记录下发顺序的假 app（魔术方法只能定义在类上，实例赋值不生效）。"""

    def __init__(self):
        self.ops = []

    def __getattr__(self, item):
        def _f(*a, **k):
            self.ops.append((item, a, k))
        return _f

    def para_names(self):
        return [c[1][0] for c in self.ops if c[0] == 'para']

    def count(self, name):
        return sum(1 for c in self.ops if c[0] == name)


# ============================================================
# 1. 离线几何：常数与参考逐值相同
# ============================================================

def test_ring_constants_match_reference():
    ring = grin_ring_holes(A)
    assert ring['hex_size'] == pytest.approx(A / 3 ** 0.5 / 2)
    assert ring['a2'] == pytest.approx(ring['hex_size'] * 3 ** 0.5)
    assert ring['a2'] == pytest.approx(A / 2)          # 巧合但可核：a2 = a/2
    assert ring['n_layers'] == DEFAULT_RING_LAYERS == 30
    assert ring['d0'] == pytest.approx(DEFAULT_D0_LAYERS * ring['hex_size'] * 2
                                       * 3 ** 0.5)
    assert ring['d0'] == pytest.approx(8 * A)
    assert ring['radius_outer'] == pytest.approx(30 * ring['a2'])


def test_ring_holes_are_first_quadrant_only():
    ring = grin_ring_holes(A)
    assert len(ring['holes']) == 721                   # 30 层网格的第一象限格点数
    assert all(h['center'][0] >= 0 and h['center'][1] >= 0 for h in ring['holes'])
    assert sum(1 for h in ring['holes'] if h['center'][0] == 0) == 16
    assert sum(1 for h in ring['holes'] if h['center'][1] == 0) == 31
    assert ring['quadrant_only'] is True


def test_ring_holes_full_quadrant_when_disabled():
    """`quadrant_only=False` 时铺满整个六边形（含负坐标）。"""
    full = grin_ring_holes(A, n_layers=10, d0_layers=3, quadrant_only=False)
    quad = grin_ring_holes(A, n_layers=10, d0_layers=3, quadrant_only=True)
    assert len(full['holes']) == 1 + 3 * 10 * 11       # 331 = 1+3N(N+1)
    assert len(quad['holes']) < len(full['holes'])
    assert any(h['center'][0] < 0 for h in full['holes'])


def test_ring_radius_expression_two_segments():
    ring = grin_ring_holes(A)
    fixed = [h for h in ring['holes'] if h['r1_fixed']]
    graded = [h for h in ring['holes'] if not h['r1_fixed']]
    assert fixed and graded
    # 分界严格按 d0
    assert all(h['distance'] < ring['d0'] for h in fixed)
    assert all(h['distance'] >= ring['d0'] for h in graded)
    assert all(h['radius_expr'] == 'r1' for h in fixed)
    for hole in graded:
        assert hole['radius_expr'].startswith('r1+(r2-r1)*(')
        assert hole['radius_expr'].endswith(')/(N*a2-d0)')
        names = set(re.findall(r'[A-Za-z_]\w*', hole['radius_expr']))
        assert names <= {'r1', 'r2', 'd0', 'N', 'a2'}, names
    # 渐变**单调增**：距离越大半径越大
    radii = [float(re.search(r'\(([-0-9.eE+]+)-d0\)/', h['radius_expr']).group(1))
             for h in graded]
    assert radii == sorted(radii)
    assert radii[0] >= ring['d0']


def test_ring_radius_sequence_uses_both_branches():
    """内圈孔半径恒为 r1（50.5 µm ⇒ 与参考 `r=[50.5,61.3]/1e3` 同口径）。"""
    ring = grin_ring_holes(A)
    assert ring['r1_0'] == pytest.approx(0.0505)
    assert ring['r2_0'] == pytest.approx(0.0613)
    assert ring['d0_layers'] == DEFAULT_D0_LAYERS == 8


def test_ring_holes_are_sorted_by_distance():
    ring = grin_ring_holes(A, **SMALL)
    distances = [h['distance'] for h in ring['holes']]
    assert distances == sorted(distances)


@pytest.mark.parametrize('layers,d0_layers', ((4, 8), (16, 8), (8, 4)))
def test_ring_empty_gradient_raises(layers, d0_layers):
    """渐变区间为空（N*a2 <= d0）必须报错 —— 否则几何名不副实。"""
    with pytest.raises(ValueError, match='渐变区间'):
        grin_ring_holes(A, n_layers=layers, d0_layers=d0_layers)


def test_ring_hex_size_override():
    ring = grin_ring_holes(A, n_layers=10, d0_layers=3, hex_size=0.1)
    assert ring['hex_size'] == pytest.approx(0.1)
    assert ring['a2'] == pytest.approx(0.1 * 3 ** 0.5)


def test_ring_small_profile_counts():
    """真机脚本默认用的那个小孔阵（91 象限孔 ⇒ 共 176 孔）。"""
    ring = grin_ring_holes(A, **SMALL)
    assert len(ring['holes']) == 91
    on_axis = sum(1 for h in ring['holes'] if h['center'][0] == 0)
    assert 2 * len(ring['holes']) - on_axis == 176


# ============================================================
# 2. 构造校验
# ============================================================

def test_insitu_requires_app():
    with pytest.raises(ValueError, match='cst_solver'):
        build_grin_lens_insitu(None, grin_ring_holes(A, **SMALL))


def test_insitu_requires_holes():
    app = _FakeApp()
    with pytest.raises(ValueError, match='至少一个孔'):
        build_grin_lens_insitu(app, {'holes': []})
    with pytest.raises(ValueError, match='至少一个孔'):
        build_grin_lens_insitu(app, None)


# ============================================================
# 3. 下发序列（与参考逐条对应）
# ============================================================

def test_insitu_sequence_counts():
    ring = grin_ring_holes(A, **SMALL)
    app = _FakeApp()
    info = build_grin_lens_insitu(app, ring, name='grib', component='grib')
    n = len(ring['holes'])
    assert app.count('hexagon') == n
    assert app.count('add') == n - 1
    assert app.count('mirror') == 1
    assert app.count('create_cylinder') == 1
    assert app.count('square') == 1
    assert app.count('subtract') == 2
    assert app.count('translate') == 2          # 平边对到原点 + 移到顶点
    assert app.count('rotation') == 1
    assert info['n_holes'] == n
    assert info['n_lenses'] == 6
    assert info['method'] == 'insitu'
    assert info['holes_generated'] is True and info['holes_imported'] is False


def test_insitu_order_matches_reference():
    """顺序：hexagon（每建一个就 `add` 进孔阵）→ mirror → cylinder/square/
    subtract → 取负形 → 平移 → 放置。"""
    ring = grin_ring_holes(A, **SMALL)
    app = _FakeApp()
    build_grin_lens_insitu(app, ring, name='grib', component='grib')
    ops = [c[0] for c in app.ops]
    n = len(ring['holes'])
    assert ops[:6] == ['para'] * 6                    # 先登记参数
    # 第 0 个孔单独建；之后「建一个孔 + 并进孔阵」成对
    assert ops[6] == 'hexagon'
    for i in range(1, n):
        assert ops[6 + 2 * i - 1] == 'hexagon', f'第 {i} 个孔的位置不对'
        assert ops[6 + 2 * i] == 'add', f'第 {i} 个 add 的位置不对'
    tail = ops[6 + 2 * n - 1:]
    assert tail == ['mirror', 'create_cylinder', 'square', 'subtract',
                    'subtract', 'translate', 'translate', 'rotation'], tail


def test_insitu_registers_expression_params_first():
    """6 个参数必须在**任何 hexagon 之前**登记（否则 CST 弹模态框挂住脚本）。"""
    ring = grin_ring_holes(A, **SMALL)
    app = _FakeApp()
    build_grin_lens_insitu(app, ring, name='grib', component='grib')
    names = app.para_names()
    assert names == ['HEX_SIZE', 'a2', 'N', 'd0', 'r1', 'r2']
    values = {c[1][0]: c[1][1] for c in app.ops if c[0] == 'para'}
    assert values['HEX_SIZE'] == pytest.approx(ring['hex_size'])
    assert values['N'] == ring['n_layers']
    assert values['d0'] == pytest.approx(ring['d0'])
    assert values['r1'] == pytest.approx(ring['r1_0'])
    assert values['r2'] == pytest.approx(ring['r2_0'])
    assert values['a2'] == 'HEX_SIZE*sqr(3)'
    # `N` 的说明里要写清 d0 的来历（不然下次没人知道 8 是哪来的）
    n_kwargs = [c[2] for c in app.ops if c[0] == 'para' and c[1][0] == 'N'][0]
    assert 'HEX_SIZE' in n_kwargs.get('expression', '')


def test_insitu_hexagon_calls_use_expression_and_theta_90():
    """每个孔：半径走表达式、`theta=[0,0,90]`、厚度沿 z 居中。"""
    ring = grin_ring_holes(A, **SMALL)
    app = _FakeApp()
    build_grin_lens_insitu(app, ring, name='grib', height='h',
                           component='grib')
    hexes = [c for c in app.ops if c[0] == 'hexagon']
    assert len(hexes) == len(ring['holes'])
    by_expr = {c[1][0] for c in hexes}
    assert 'r1' in by_expr
    assert any(e.startswith('r1+(r2-r1)*(') for e in by_expr)
    for _, args, kwargs in hexes:
        assert args[1] == 'h'
        assert kwargs['theta'] == [0, 0, 90]
        assert kwargs['center'][2] == '-h/2'
        assert kwargs['component'] == 'grib'
        assert kwargs['name'].startswith('grib-')
    # 孔名唯一（否则 CST 会把后一个覆盖前一个）
    names = [c[2]['name'] for c in hexes]
    assert len(set(names)) == len(names)


def test_insitu_cut_solid_uses_param_expressions():
    """半圆裁剪体：圆柱半径与方框都用参数表达式，没有烘死的数字。"""
    ring = grin_ring_holes(A, **SMALL)
    app = _FakeApp()
    build_grin_lens_insitu(app, ring, name='grib', height='h',
                           component='grib')
    cyl = [c for c in app.ops if c[0] == 'create_cylinder'][0]
    assert 'HEX_SIZE' in cyl[2]['r'][0] and 'N' in cyl[2]['r'][0]
    assert cyl[2]['name'] == 'grib'          # 最终透镜实体就叫 `name`
    sq = [c for c in app.ops if c[0] == 'square'][0]
    assert any('HEX_SIZE' in str(v) for v in sq[1])
    assert '-r1' in sq[1]                        # 平边到 y=-r1（参考同口径）
    assert sq[2]['name'] == 'grib-cut'


def test_insitu_subtract_order_takes_negative():
    """`subtract(裁剪体, 孔阵)` —— 结果是「孔阵的负形」，不是孔本身。"""
    ring = grin_ring_holes(A, **SMALL)
    app = _FakeApp()
    build_grin_lens_insitu(app, ring, name='grib', component='grib')
    subs = [c[1] for c in app.ops if c[0] == 'subtract']
    assert subs[0][:2] == ('grib', 'grib-cut')
    assert subs[1][:2] == ('grib', 'grib-0')
    assert all(c[2]['component2'] == 'grib' for c in app.ops
               if c[0] == 'subtract')


def test_insitu_mirror_is_copy_unite():
    ring = grin_ring_holes(A, **SMALL)
    app = _FakeApp()
    build_grin_lens_insitu(app, ring, name='grib', component='grib')
    mirror = [c for c in app.ops if c[0] == 'mirror'][0]
    assert mirror[1][0] == 'grib-0'
    assert mirror[1][2] == [1, 0, 0]              # 平面法向 x ⇒ 补 x 方向另一半
    assert mirror[2]['copy'] is True and mirror[2]['unite'] is True


def test_insitu_placement_uses_rbig_and_six_lenses():
    ring = grin_ring_holes(A, **SMALL)
    app = _FakeApp()
    info = build_grin_lens_insitu(app, ring, name='grib', component='grib')
    assert info['placed'] is True and info['n_lenses'] == 6
    move = [c for c in app.ops if c[0] == 'translate'][-1]
    assert move[1][0] == 'grib'
    assert move[1][1][0] == 'Rbig'
    rot = [c for c in app.ops if c[0] == 'rotation'][0]
    assert rot[1][1] == [0, 0, 60]                # 6 个顶点
    assert rot[2]['repetition'] == 5
    assert rot[2]['copy'] is True and rot[2]['unite'] is False


def test_insitu_place_false_keeps_single_lens():
    ring = grin_ring_holes(A, **SMALL)
    app = _FakeApp()
    info = build_grin_lens_insitu(app, ring, name='grib', place=False)
    assert info['placed'] is False and info['n_lenses'] == 1
    assert app.count('rotation') == 0
    assert app.count('translate') == 1             # 只剩「平边对到原点」


def test_insitu_custom_r_big_and_repetition():
    ring = grin_ring_holes(A, **SMALL)
    app = _FakeApp()
    info = build_grin_lens_insitu(app, ring, r_big='Rb', place=True,
                                  rotation_repetition=3)
    assert info['n_lenses'] == 4
    assert [c for c in app.ops if c[0] == 'translate'][-1][1][1][0] == 'Rb'


def test_insitu_names_can_be_overridden():
    ring = grin_ring_holes(A, **SMALL)
    app = _FakeApp()
    build_grin_lens_insitu(app, ring, name='lens_epc', clip_name='MY-CLIP',
                           component='gridlens')
    assert [c for c in app.ops if c[0] == 'create_cylinder'][0][2]['name'] == 'MY-CLIP'
    assert [c for c in app.ops if c[0] == 'mirror'][0][1][0] == 'lens_epc-0'
    assert [c for c in app.ops if c[0] == 'square'][0][2]['name'] == 'lens_epc-cut'


#: 每个操作该把组件写在哪个关键字里（`translate`/`rotation`/`mirror`/`square`/
#: `cylinder`/`hexagon` 是 `component=`，布尔运算是 `component1=/component2=`）
_COMPONENT_KWARG = {
    'hexagon': ('component',),
    'add': ('component1', 'component2'),
    'mirror': ('component',),
    'create_cylinder': ('component',),
    'square': ('component',),
    'subtract': ('component1', 'component2'),
    'translate': ('component',),
    'rotation': ('component',),
}


def test_insitu_never_relies_on_default_component():
    """**真机回归**（2026-09-17）：`translate` / `rotation` 的默认组件是
    `'component1'`，实体却在 `component` 里 —— 漏传时 CST 报
    ``Shape does not exist: component1:<name>``，整段透镜建不出来。
    """
    ring = grin_ring_holes(A, **SMALL)
    app = _FakeApp()
    build_grin_lens_insitu(app, ring, name='lens_epc', component='gridlens')
    offenders = []
    for op, _args, kwargs in app.ops:
        for key in _COMPONENT_KWARG.get(op, ()):
            if kwargs.get(key) != 'gridlens':
                offenders.append((op, key, kwargs.get(key)))
    assert not offenders, f'这些下发没带正确的 component：{offenders}'
    # 反向：默认组件下也不能多传（保持 VBA 与旧脚本一致）
    app2 = _FakeApp()
    build_grin_lens_insitu(app2, ring, name='lens_epc')
    for op, _args, kwargs in app2.ops:
        for key in _COMPONENT_KWARG.get(op, ()):
            assert kwargs.get(key) == 'component1', (op, key)


def test_insitu_total_holes_accounts_for_axis():
    """镜像后总孔数要减掉 `x == 0` 上落回自身的那些孔（unite 会吞掉重复）。"""
    ring = grin_ring_holes(A, **SMALL)
    app = _FakeApp()
    info = build_grin_lens_insitu(app, ring)
    on_axis = sum(1 for h in ring['holes'] if h['center'][0] == 0)
    assert info['n_holes_on_axis'] == on_axis
    assert info['n_holes_total'] == 2 * len(ring['holes']) - on_axis
    assert info['n_holes_total'] == 176


def test_insitu_reports_ring_geometry():
    ring = grin_ring_holes(A, **SMALL)
    app = _FakeApp()
    info = build_grin_lens_insitu(app, ring, name='grib')
    assert info['hex_size'] == pytest.approx(ring['hex_size'])
    assert info['a2'] == pytest.approx(ring['a2'])
    assert info['d0'] == pytest.approx(ring['d0'])
    assert info['layers'] == ring['n_layers']
    assert info['radius_outer'] == pytest.approx(ring['radius_outer'])
    assert info['n_holes_quadrant'] == len(ring['holes'])


def test_builders_report_the_real_entity_component(tmp_path):
    """两个 builder 必须报告**实体实际所在组件**（真机踩过两次）。

    * DXF 路线（`build_grin_lens`）为了与旧脚本 `lens_build.py` 逐字节一致，
      实体落在 `component1`；
    * 就地路线（`build_grin_lens_insitu`）整枚透镜在调用方给的 `component` 里。

    调用方（例如功分器的相位旋转）必须按这个值寻址，否则 CST 报
    ``Shape does not exist: <component>:<name>``。
    """
    from topo_modeler.builders import (build_grin_lens,
                                       build_grin_lens_holes,
                                       build_grin_lens_insitu,
                                       grin_lens_spec_from_cst_params,
                                       grin_ring_holes)

    spec = grin_lens_spec_from_cst_params(a=0.2425, ratio=1.0, nx=16, ny=13,
                                          r1_0=0.052, r2_0=0.066,
                                          n_small=8, lx1=6)
    dxf = str(tmp_path / 'lens.dxf')
    build_grin_lens_holes(spec).export_dxf(dxf)
    app = _FakeApp()
    app.param_existed = lambda name: True      # 绕过 Rbig/Ls 前置探针（只测返回值）
    info = build_grin_lens(app, None, spec, dxf_path=dxf, component='gridlens')
    assert info['component'] == 'gridlens'
    assert info['entity_component'] == 'component1', (
        'DXF 路线的实体在 component1（旧脚本等价性），必须如实报告')

    app2 = _FakeApp()
    ring = grin_ring_holes(0.2425, n_layers=10, d0_layers=3)
    info2 = build_grin_lens_insitu(app2, ring, name='lens_epc',
                                   component='gridlens')
    assert info2['entity_component'] == 'gridlens'
    assert info2['name'] == 'lens_epc'   # 最终实体名 = 调用方给的名字


# ============================================================
# 8. 参数前置拦截：`self_rotation` 给**参数名**时也要拦（防 CST 模态框挂住）
# ============================================================
#
# 2026-09-18 真机教训：真机脚本漏登记 `dphi` 就调 `self_rotation='dphi'`，
# CST 不报错、而是弹「请输入变量值」模态框把脚本**挂了 30+ 分钟**，
# 连 `EnumWindows` 都看不到那个框（`cst_dialog_guard` 抓不到）。
# ⇒ 必须在**下发之前**用「参数是否存在」探针拦下。

class _ProbeApp(_FakeApp):
    """带参数探针的假 app：`existing` 之外的参数一律"不存在"。"""

    def __init__(self, existing=()):
        super().__init__()
        self.existing = set(existing)

    def param_existed(self, name):
        return name in self.existing


def _guarded(app):
    """给 app 装上守卫（模拟真机：第一次 para() 后探针就位）。"""
    from cst_solver._guards import get_guard_state

    state = get_guard_state(app)
    state.attach_param_probe(app.param_existed)
    return state


def test_insitu_preflight_rejects_unregistered_rotation_param():
    from topo_modeler.builders import build_grin_lens_insitu, grin_ring_holes

    ring = grin_ring_holes(0.2425, n_layers=10, d0_layers=3)
    app = _ProbeApp(existing=('Rbig',))
    _guarded(app)
    with pytest.raises(ValueError, match='dphi'):
        build_grin_lens_insitu(app, ring, name='grib',
                               self_rotation='dphi', component='grib')
    # 登记之后就必须放行
    app2 = _ProbeApp(existing=('Rbig', 'dphi'))
    _guarded(app2)
    info = build_grin_lens_insitu(app2, ring, name='grib',
                                  self_rotation='dphi', component='grib')
    assert info['self_rotation'] == 'dphi'


def test_insitu_preflight_rejects_missing_rbig_when_placing():
    from topo_modeler.builders import build_grin_lens_insitu, grin_ring_holes

    ring = grin_ring_holes(0.2425, n_layers=10, d0_layers=3)
    app = _ProbeApp(existing=())          # 什么都没有
    _guarded(app)
    with pytest.raises(ValueError, match='Rbig'):
        build_grin_lens_insitu(app, ring, name='grib', component='grib')
    # 不放置就不需要 Rbig
    app2 = _ProbeApp(existing=())
    _guarded(app2)
    info = build_grin_lens_insitu(app2, ring, name='grib', place=False,
                                  component='grib')
    assert info['placed'] is False


def test_dxf_route_preflight_rejects_unregistered_rotation_param(tmp_path):
    from topo_modeler.builders import (build_grin_lens, build_grin_lens_holes,
                                       grin_lens_spec_from_cst_params)

    spec = grin_lens_spec_from_cst_params(a=0.2425, ratio=1.0, nx=16, ny=13,
                                          r1_0=0.052, r2_0=0.066,
                                          n_small=8, lx1=6)
    dxf = str(tmp_path / 'lens.dxf')
    build_grin_lens_holes(spec).export_dxf(dxf)
    app = _ProbeApp(existing=('Rbig', 'Ls'))
    _guarded(app)
    with pytest.raises(ValueError, match='dphi'):
        build_grin_lens(app, None, spec, dxf_path=dxf,
                        self_rotation='dphi', component='gridlens')
