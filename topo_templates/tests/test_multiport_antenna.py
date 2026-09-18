# -*- coding: utf-8 -*-
r"""
MultiPortAntenna 模板（P5，α1 族）—— 离线部分
=============================================

计划原文（`docs/next_plan/README.md` P5）：`MultiPortAntenna`、`PowerDivider`、
`MZISwitch` 三类模板。本文件守住 `MultiPortAntenna` **不需要 CST 的那一半**。

参考与口径（[设计记录](../../docs/guides/complex_device_templates_design.md)）：
α1 族 = `Ant3_1W2N` + `MPMBA\Ant3_*`（4 个 notebook 命令序列同构）：
**1 分 2**、**双馈源**（AB `feed1` + BA `feed2`）、**两条铜波导**、**3 个端口**。

⚠️ 本模板**不与参考 notebook 逐字节相同**（设计记录 §2 的口径决策 D1：参考用闭合
区域轮廓，本模板用本库的中心线派生 + 多路径并集），所以这里验的是：
拓扑/端口/参数登记，而不是"与参考几何等价"。

运行方式::

    pytest topo_templates/tests/test_multiport_antenna.py -v
"""

import os
import sys
import warnings

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from topo_templates import MultiPortAntenna                   # noqa: E402


def _antenna(**kwargs):
    params = dict(straight_length=6, arm_length=4)
    params.update(kwargs)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return MultiPortAntenna(**params)


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
# 1. 拓扑：1 分 2（主干 + 两条分支）
# ============================================================

def test_has_a_main_path_and_two_mirrored_arms():
    """1分2 ⇒ 三条中心线；两条分支必须**物理镜像**（同一 x、±y）。"""
    antenna = _antenna()
    assert set(antenna.paths) == {'main', 'arm_up', 'arm_dn'}
    up = antenna.paths['arm_up'].xy[-1]
    dn = antenna.paths['arm_dn'].xy[-1]
    assert up[0] == pytest.approx(dn[0]), (up, dn)
    assert up[1] == pytest.approx(-dn[1]), (up, dn)
    # 主干是直线
    assert antenna.paths['main'].is_straight()


def test_arms_branch_off_the_end_of_the_main_path():
    antenna = _antenna()
    main = list(antenna.paths['main'].path_lattice)
    for name in ('arm_up', 'arm_dn'):
        lattice = list(antenna.paths[name].path_lattice)
        assert lattice[:len(main)] == main, (name, lattice)


@pytest.mark.parametrize('topology', ('AB', 'BA'))
def test_topologies_are_mirrors(topology):
    """AB / BA 的臂端互为镜像（与 `UnitAntenna` 同一口径）。"""
    antenna = _antenna(topology=topology)
    up = antenna.paths['arm_up'].xy[-1]
    dn = antenna.paths['arm_dn'].xy[-1]
    assert up[1] > 0 and dn[1] < 0, (topology, up, dn)


def test_array_range_is_the_union_over_the_three_paths():
    """阵列范围取**所有路径的并集**（ARCHITECTURE §6 硬约定 3）。"""
    antenna = _antenna(straight_length=6, arm_length=4)
    per_path = {n: p.get_array_range() for n, p in antenna.paths.items()}
    union = tuple(max(v[i] for v in per_path.values()) for i in range(3))
    assert tuple(antenna.modeler.array_range()) == union


# ============================================================
# 2. 端口：3 个，编号由调用方给
# ============================================================

def test_three_ports_with_caller_given_numbers():
    antenna = _antenna(port_numbers=(5, 6, 7))
    assert antenna.port_numbers == (5, 6, 7)


def test_port_numbers_must_be_three():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with pytest.raises(ValueError, match='port_numbers'):
            MultiPortAntenna(port_numbers=(1, 2))


def test_unknown_topology_rejected():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with pytest.raises(ValueError, match='topology'):
            MultiPortAntenna(topology='XY')


# ============================================================
# 3. 参数登记：两个馈源族 + 每条路径自己的前缀
# ============================================================

def test_registers_both_feed_families():
    """双馈源 ⇒ AB 族与 BA 族**都要登记**（含 BA 波导范围引用的 lf6）。"""
    antenna = _antenna()
    app = _Recorder()
    antenna.app = app
    antenna._define_all_params()
    registered = app.registered()
    ab = {'x0', 'wf1', 'lf1', 'lf2', 'lf3'}
    ba = {'x01', 'wf2', 'lf4', 'lf5', 'lf6'}
    assert not (ab - registered), sorted(ab - registered)
    assert not (ba - registered), sorted(ba - registered)


def test_each_path_gets_its_own_parameter_prefix():
    """三条路径必须各用各的 CST 参数前缀，否则互相覆盖。"""
    antenna = _antenna()
    app = _Recorder()
    antenna.app = app
    antenna._define_all_params()
    names = [c[1][0] for c in app.calls if c[0] == 'para']
    groups = {n[:2] for n in names if n.endswith('x') and n[:1] == 'p'}
    assert groups == {'p0', 'p1', 'p2'}, sorted(groups)


def test_registers_union_array_range_and_waveguide_params():
    antenna = _antenna()
    app = _Recorder()
    antenna.app = app
    antenna._define_all_params()
    registered = app.registered()
    assert {'xup', 'yup', 'ydn', 'wg_a', 'wg_b', 'wg_t', 'a', 'h',
            'l1', 'l2', 'e1', 'e2'} <= registered


# ============================================================
# 4. 馈源族覆盖入口（两个族的键都接受；写错要报错）
# ============================================================

def test_feed_params_accept_both_families():
    antenna = _antenna(feed_params={'lf2': 0.2, 'lf5': 0.2})
    app = _Recorder()
    antenna.app = app
    antenna._define_all_params()
    values = app.values()
    assert values['lf2'] == 0.2 and values['lf5'] == 0.2


def test_feed_params_reject_unknown_names():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with pytest.raises(ValueError, match='未知参数名'):
            MultiPortAntenna(feed_params={'nope': 1})


# ============================================================
# 5. 无 CST 时明确失败 / 离线摘要
# ============================================================

def test_build_without_cst_raises():
    antenna = _antenna()
    if antenna.app is not None:
        pytest.skip('本机有 CST 环境，跳过"无 CST"分支')
    with pytest.raises(RuntimeError, match='CST'):
        antenna.build_all()


def test_summary_is_offline_and_complete():
    antenna = _antenna()
    summary = antenna.summary()
    assert set(summary['paths']) == {'main', 'arm_up', 'arm_dn'}
    assert summary['ports'] == (1, 2, 3)
    assert len(summary['array_range']) == 3


# ============================================================
# 6. 透镜（三条路线；参考口径 = **单枚、近焦点在原点**）
# ============================================================
#
# 参考依据（`MPMBA\Ant3_epc.ipynb` / `多端口\Ant3_1W2N\Ant3_240D3_epc.ipynb`）：
#   ratio=2 ; r=[50.5,61.3]/1e3/ratio*2 ; Nx=int(yl*1.15)*ratio+1 ; Ny=yl*ratio+1
#   app1.dxf_import(..., component='gridlens') → mirror y → mirror x
#   app1.ellipse('ec_a','ec_b',[0,0],'epc1') → translate(['ec_c','0','0']) → 剪孔
#   ⇒ **没有** Rbig 平移、**没有** 6 份旋转复制（单枚透镜，近焦点在原点）。

def _mp(**kwargs):
    params = dict(straight_length=4, arm_length=3)
    params.update(kwargs)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return MultiPortAntenna(**params)


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


def test_multiport_default_has_no_lens():
    antenna = _mp()
    assert antenna.has_lens is False
    assert antenna.lens_method is None
    assert antenna.lens_summary() == {'method': None}
    app = _ParaRecorder()
    antenna.app = app
    antenna._define_all_params()
    names = app.para_names()
    assert 'Ls' not in names and 'Rbig' not in names


def test_multiport_lens_validation(tmp_path):
    dxf = tmp_path / 'lens.dxf'
    dxf.write_text('0\n', encoding='utf-8')
    with pytest.raises(ValueError, match='必须给 lens_dxf'):
        _mp(lens_method='dxf')
    with pytest.raises(FileNotFoundError):
        _mp(lens_method='dxf', lens_dxf=str(tmp_path / 'nope.dxf'))
    with pytest.raises(ValueError, match='互斥'):
        _mp(lens_method='insitu', lens_dxf=str(dxf))
    with pytest.raises(ValueError, match='lens_method'):
        _mp(lens_method='in-situ')
    with pytest.raises(ValueError, match='lens_layers'):
        _mp(lens_method='insitu', lens_layers=0)
    # 只给 lens_dxf ⇒ 等价于 'dxf'（历史行为）
    assert _mp(lens_dxf=str(dxf)).lens_method == 'dxf'


def test_multiport_lens_defaults_come_from_reference():
    """默认值必须来自参考 `para_init(yl=10, ratio=2)`，不是随手挑的。"""
    antenna = _mp(lens_method='generate')
    spec = antenna.make_lens_spec()
    assert spec.ratio == 2.0
    assert spec.nx == 24          # int(10*1.15)*2+1
    assert spec.ny == 21          # 10*2+1
    assert spec.r_in == pytest.approx(0.0505)
    assert spec.r_out == pytest.approx(0.0613)
    info = antenna.lens_summary()
    assert info['method'] == 'generate'
    assert info['ratio'] == 2.0 and info['nx'] == 24 and info['ny'] == 21
    assert info['placed'] is False, '参考是单枚放原点，不该有 6 份复制'


def test_multiport_lens_ls_registered_but_not_rbig(tmp_path):
    """椭圆路线要 `Ls`（楔形裁剪）；**不要** `Rbig`（透镜留在原点 ⇒ 用不到）。

    登记 `Rbig` 会是死写入（`verify_model_parameter_usage.py` 会抓），
    而且 `place=False` 时 `build_grin_lens` 的前置拦截也不再要它。
    """
    for method, kwargs in (('generate', {}),
                           ('insitu', {'lens_layers': 10, 'lens_d0_layers': 3})):
        antenna = _mp(lens_method=method, **kwargs)
        app = _ParaRecorder()
        antenna.app = app
        antenna._define_all_params()
        names = app.para_names()
        assert 'Rbig' not in names, f'{method}: 不该登记 Rbig'
        assert ('Ls' in names) is (method != 'insitu'), (method, names)


def test_multiport_insitu_ring_geometry():
    antenna = _mp(lens_method='insitu', lens_layers=10, lens_d0_layers=3)
    ring = antenna.make_lens_ring()
    assert ring['hex_size'] == pytest.approx(antenna.a / 3 ** 0.5 / 2)
    assert len(ring['holes']) == 91
    info = antenna.lens_summary()
    assert info['method'] == 'insitu' and info['dxf'] is None
    assert info['n_holes'] == 91 and info['placed'] is False


def test_multiport_generate_route_writes_dxf(tmp_path):
    antenna = _mp(lens_method='generate',
                  lens_dxf_out=str(tmp_path / 'mp.dxf'))
    path = antenna.make_lens_dxf()
    assert path == str(tmp_path / 'mp.dxf')
    assert os.path.isfile(path) and os.path.getsize(path) > 1024


def test_multiport_insitu_build_sequence_is_single_lens():
    """就地路线 `place=False` ⇒ 只有 1 次 rotation（自转槽位不用时不下发）、1 枚透镜。"""
    from topo_modeler.builders import build_grin_lens_insitu
    antenna = _mp(lens_method='insitu', lens_layers=10, lens_d0_layers=3,
                  lens_name='lens_epc', lens_component='gridlens')

    class _OpRecorder:
        def __init__(self):
            self.ops = []

        def __getattr__(self, item):
            def _f(*a, **k):
                self.ops.append((item, k))
            return _f

    app = _OpRecorder()
    info = build_grin_lens_insitu(app, antenna.make_lens_ring(),
                                  name=antenna.lens_name, place=False,
                                  component=antenna.lens_component)
    ops = [c[0] for c in app.ops]
    assert ops.count('hexagon') == 91
    assert ops.count('rotation') == 0, 'place=False 不该有旋转复制'
    assert ops.count('translate') == 1, 'place=False 只剩"平边对到原点"'
    assert info['n_lenses'] == 1 and info['placed'] is False
    assert info['name'] == 'lens_epc'


def test_multiport_summary_reports_lens():
    antenna = _mp(lens_method='insitu', lens_layers=10, lens_d0_layers=3)
    summary = antenna.summary()
    assert summary['has_lens'] is True
    assert summary['lens_method'] == 'insitu'
    assert summary['lens']['n_holes'] == 91
