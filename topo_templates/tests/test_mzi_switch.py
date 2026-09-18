# -*- coding: utf-8 -*-
r"""
MZISwitch 模板（P5）—— 离线部分
===============================

计划原文（`docs/next_plan/README.md` P5）：`MultiPortAntenna`、`PowerDivider`、
`MZISwitch` 三类模板。本文件守住 `MZISwitch` **不需要 CST 的那一半**。

参考与口径（[复杂器件参考规格](../../docs/guides/complex_device_specs.md) §4.2、
[设计记录](../../docs/guides/complex_device_templates_design.md)）：

* 路径 6 点，方向序列 **0° → +120° → 0° → −120° → 0°**（参考 `MZI.ipynb` 的 `px/py` 链）；
* 阵列范围用**参考公式**：`xup = x1*2+x2-int(y1)+1`、`yup = ydn = y1+y2`；
  ⚠️ **不能**用 `path.get_array_range()` —— 单边偏置路径会给 `ydn=1`，
  于是晶体复制次数 `int(ydn/2)=0`，CST 直接报 `Invalid number of repetitions`（P4/V1 同类坑）；
* **`basic` 与 `cascade` 在 CST 侧是同一几何**（逐 cell 取证）⇒ 模板里是同一份几何，
  `mzi_type` 只作来源标签；`parallel` / `anti` 是真实几何差别，**未实现** ⇒ 传了要报错。

运行方式::

    pytest topo_templates/tests/test_mzi_switch.py -v
"""

import os
import sys
import warnings

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from topo_templates import MZISwitch                          # noqa: E402


def _mzi(**kwargs):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return MZISwitch(**kwargs)


class _Recorder:
    """记录调用的假 app。"""

    def __init__(self):
        self.calls = []

    def __getattr__(self, item):
        def _f(*a, **k):
            self.calls.append((item, a, k))
            return None
        return _f

    def registered(self):
        return {c[1][0] for c in self.calls if c[0] == 'para'}

    def values(self):
        return {c[1][0]: c[1][1] for c in self.calls if c[0] == 'para'}


# ============================================================
# 1. 路径形状：0° → +120° → 0° → −120° → 0°
# ============================================================

def test_path_has_six_points_and_the_reference_direction_sequence():
    """6 个点、5 段；第 2 段往上折、第 4 段往下折（参考的方向序列）。"""
    mzi = _mzi()
    lattice = list(mzi.path.path_lattice)
    assert len(lattice) == 6, lattice
    xy = mzi.path.xy
    assert xy[1][1] == pytest.approx(0.0)          # 第 1 段沿 x
    assert xy[2][1] > 0                            # 第 2 段往上（+y）
    assert xy[3][1] == pytest.approx(xy[2][1])     # 第 3 段沿 x（两条臂的间距）
    assert xy[4][1] == pytest.approx(0.0)          # 第 4 段往下
    assert xy[5][1] == pytest.approx(0.0)          # 第 5 段沿 x


def test_geometry_scales_with_the_three_length_parameters():
    small = _mzi(arm_x1=3, mid_x2=4, arm_gap_y1=2)
    big = _mzi(arm_x1=9, mid_x2=9, arm_gap_y1=5)
    assert len(small.path) == len(big.path) == 6
    assert big.path.xy[-1][0] > small.path.xy[-1][0]


# ============================================================
# 2. 阵列范围：必须用参考公式（避免 ydn=1 的坑）
# ============================================================

def test_array_range_uses_the_reference_formula():
    mzi = _mzi(arm_x1=9, mid_x2=9, arm_gap_y1=5)
    app = _Recorder()
    mzi.app = app
    mzi._define_all_params()
    values = app.values()
    assert values['xup'] == 9 * 2 + 9 - 5 + 1, values['xup']
    assert values['yup'] == values['ydn'] == 5 * 2, (values['yup'], values['ydn'])


def test_array_range_never_gives_zero_repetitions():
    """
    回归（P4/V1 同类坑）：`yup`/`ydn` 必须 ≥ 2，否则 `int(ydn/2) = 0`
    ⇒ CST 报 `Invalid number of repetitions`。
    """
    for gap in (1, 2, 3, 5):
        mzi = _mzi(arm_gap_y1=gap)
        app = _Recorder()
        mzi.app = app
        mzi._define_all_params()
        values = app.values()
        assert values['yup'] >= 2 and values['ydn'] >= 2, (gap, values['yup'])


def test_path_get_array_range_would_be_wrong_here():
    """把"为什么不能用 `get_array_range()`"钉住：它给的是单边偏置的 ydn。"""
    mzi = _mzi()
    _xup, _yup, ydn = mzi.path.get_array_range()
    assert int(ydn) < 2, f'路径推断的 ydn={ydn} 会导致 0 次复制（这正是要避免的）'


# ============================================================
# 3. mzi_type：basic 与 cascade 同一几何；未实现类型必须报错
# ============================================================

@pytest.mark.parametrize('mzi_type', ('basic', 'cascade'))
def test_basic_and_cascade_share_the_same_geometry(mzi_type):
    """逐 cell 取证：两者在 CST 侧完全相同 ⇒ 模板里几何必须一致。"""
    a = _mzi(mzi_type='basic')
    b = _mzi(mzi_type='cascade')
    assert [tuple(p) for p in a.path.path_lattice] == \
        [tuple(p) for p in b.path.path_lattice]
    assert a.summary()['array_range'] == b.summary()['array_range']
    assert a.mzi_type == 'basic' and b.mzi_type == 'cascade'


@pytest.mark.parametrize('mzi_type', ('parallel', 'anti'))
def test_unimplemented_types_fail_loudly(mzi_type):
    """`parallel` / `anti` 是真实几何差别、尚未实现 —— 不能静默当成 basic。"""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with pytest.raises(ValueError, match='尚未实现'):
            MZISwitch(mzi_type=mzi_type)


def test_summary_records_the_source_label():
    summary = _mzi(mzi_type='cascade').summary()
    assert summary['mzi_type'] == 'cascade'
    assert '同一几何' in summary['note']


# ============================================================
# 4. 参数登记：耦合区/圆柱/馈源/阵列
# ============================================================

def test_registers_pump_cylinder_and_feed_params():
    mzi = _mzi()
    app = _Recorder()
    mzi.app = app
    mzi._define_all_params()
    registered = app.registered()
    assert {'ax', 'ay', 'rc1', 'sigma1'} <= registered
    assert {'x0', 'wf1', 'lf1', 'lf2', 'lf3'} <= registered
    assert {'xup', 'yup', 'ydn', 'a', 'h', 'l1', 'l2', 'e1', 'e2'} <= registered


def test_path_params_are_registered():
    mzi = _mzi()
    app = _Recorder()
    mzi.app = app
    mzi._define_all_params()
    names = app.registered()
    assert {'p1x', 'p1y', 'p6x', 'p6y'} <= names, sorted(names)[:20]


def test_feed_params_reject_unknown_names():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with pytest.raises(ValueError, match='未知参数名'):
            MZISwitch(feed_params={'lf5': 0.2})       # BA 族的键，本器件不用


# ============================================================
# 5. 端口与无 CST 行为
# ============================================================

def test_port_faces_match_the_reference_record():
    """参考用的面号 `'14'`/`'4'` 记在 `FEED_PORT_FACES` 里（**仅作取证记录**）。"""
    from topo_templates.mzi_switch import FEED_PORT_FACES
    assert FEED_PORT_FACES == {'port1': '14', 'port2': '4'}


def test_ports_are_built_with_free_coordinates_not_face_ids():
    """
    端口必须走 **Free 模式（给坐标范围）**，不许用面号。

    真机实测（2026-09-17）：参考的面号 `'14'` 在**我们的构序**下 `pick_face`
    选中 **0 个面**（面号与几何/构序强相关，见仓库 `picks.py` 的说明），
    被 `add_waveguide_port` 的校验挡下 ⇒ 改用 `create_waveguide_port_free()`，
    它不产生拾取动作，几何微调也不会指错面。
    """
    mzi = _mzi()
    assert hasattr(mzi, 'port_specs'), '模板应给出端口规格（便于离线核对）'
    for spec in mzi.port_specs():
        assert spec['face'] == 'Free', spec
        assert 'x' in spec and spec['x'], spec
    # 断言端口规格的**数量与编号**来自可配置的来源，而不是硬编码面号
    numbers = [spec['port'] for spec in mzi.port_specs()]
    assert numbers == [1, 2], numbers


def test_build_without_cst_raises():
    mzi = _mzi()
    if mzi.app is not None:
        pytest.skip('本机有 CST 环境，跳过"无 CST"分支')
    with pytest.raises(RuntimeError, match='CST'):
        mzi.build_all()


# ============================================================
# 7. 透镜（三条路线；参考口径 = **单枚、近焦点在原点**）
# ============================================================
#
# 参考依据（`开关尝试\AB\MZI-GRIB.ipynb`）：整段 GRIB 环透镜建环是**活代码**
# （`HEX_SIZE=a/sqr(3)/2`、`N=(y[1]+2)*2`、`r=[50.5,61.3]/1e3`、镜像补另一半）
# ⇒ 本模板用 `lens_method='insitu'` + `place=False` 覆盖。

def _mzi(**kwargs):
    params = dict(arm_x1=4, mid_x2=4, arm_gap_y1=3)
    params.update(kwargs)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return MZISwitch(**params)


class _ParaRecorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, item):
        def _f(*a, **k):
            self.calls.append((item, a, k))
        return _f

    def paras(self, mapping, *_a, **_k):
        for name, value in dict(mapping).items():
            self.calls.append(('para', (name, value), {}))

    def para_names(self):
        return [c[1][0] for c in self.calls if c[0] == 'para']


def test_mzi_default_has_no_lens():
    switch = _mzi()
    assert switch.has_lens is False and switch.lens_method is None
    assert switch.lens_summary() == {'method': None}
    app = _ParaRecorder()
    switch.app = app
    switch._define_all_params()
    names = app.para_names()
    assert 'Ls' not in names and 'Rbig' not in names


def test_mzi_lens_validation(tmp_path):
    dxf = tmp_path / 'lens.dxf'
    dxf.write_text('0\n', encoding='utf-8')
    with pytest.raises(ValueError, match='必须给 lens_dxf'):
        _mzi(lens_method='dxf')
    with pytest.raises(FileNotFoundError):
        _mzi(lens_method='dxf', lens_dxf=str(tmp_path / 'nope.dxf'))
    with pytest.raises(ValueError, match='互斥'):
        _mzi(lens_method='insitu', lens_dxf=str(dxf))
    with pytest.raises(ValueError, match='lens_method'):
        _mzi(lens_method='in-situ')
    with pytest.raises(ValueError, match='lens_layers'):
        _mzi(lens_method='insitu', lens_layers=0)
    assert _mzi(lens_dxf=str(dxf)).lens_method == 'dxf'


def test_mzi_lens_ls_registered_but_not_rbig():
    """椭圆路线要 `Ls`；**不要** `Rbig`（透镜留在原点 ⇒ 用不到，登记就是死写入）。"""
    for method, kwargs in (('generate', {}),
                           ('insitu', {'lens_layers': 10, 'lens_d0_layers': 3})):
        switch = _mzi(lens_method=method, **kwargs)
        app = _ParaRecorder()
        switch.app = app
        switch._define_all_params()
        names = app.para_names()
        assert 'Rbig' not in names, f'{method}: 不该登记 Rbig'
        assert ('Ls' in names) is (method != 'insitu'), (method, names)


def test_mzi_insitu_ring_geometry_and_single_lens():
    from topo_modeler.builders import build_grin_lens_insitu
    switch = _mzi(lens_method='insitu', lens_layers=10, lens_d0_layers=3)
    ring = switch.make_lens_ring()
    assert ring['hex_size'] == pytest.approx(switch.a / 3 ** 0.5 / 2)
    assert len(ring['holes']) == 91
    info = switch.lens_summary()
    assert info['method'] == 'insitu' and info['dxf'] is None
    assert info['n_holes'] == 91 and info['placed'] is False

    class _OpRecorder:
        def __init__(self):
            self.ops = []

        def __getattr__(self, item):
            def _f(*a, **k):
                self.ops.append((item, k))
            return _f

    app = _OpRecorder()
    built = build_grin_lens_insitu(app, ring, name=switch.lens_name,
                                   place=False, component=switch.lens_component)
    ops = [c[0] for c in app.ops]
    assert ops.count('hexagon') == 91
    assert ops.count('rotation') == 0        # place=False ⇒ 没有 6 份复制
    assert built['n_lenses'] == 1 and built['placed'] is False


def test_mzi_generate_route_writes_dxf(tmp_path):
    switch = _mzi(lens_method='generate',
                  lens_dxf_out=str(tmp_path / 'mzi.dxf'))
    path = switch.make_lens_dxf()
    assert os.path.isfile(path) and os.path.getsize(path) > 1024
    # 与另外三个模板同口径：r1_0 是"ratio=1 时的半径"（参考等效 0.0505 @ ratio=2）
    spec = switch.make_lens_spec()
    assert spec.r_in == pytest.approx(0.0505)
    assert spec.nx == 24 and spec.ny == 21


def test_mzi_summary_reports_lens():
    switch = _mzi(lens_method='insitu', lens_layers=10, lens_d0_layers=3)
    summary = switch.summary()
    assert summary['has_lens'] is True
    assert summary['lens_method'] == 'insitu'
    assert summary['lens']['n_holes'] == 91
