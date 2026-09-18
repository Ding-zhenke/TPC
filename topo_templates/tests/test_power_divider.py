# -*- coding: utf-8 -*-
r"""
PowerDivider 模板（P5，α2 族）—— 离线部分
=========================================

计划原文（`docs/next_plan/README.md` P5）：`MultiPortAntenna`、`PowerDivider`、
`MZISwitch` 三类模板。本文件守住 `PowerDivider` **不需要 CST 的那一半**。

参考与口径（[复杂器件参考规格](../../docs/guides/complex_device_specs.md) §4.3–§4.5、
[设计记录](../../docs/guides/complex_device_templates_design.md)）：

* **只有分路数有数据依据**：1分2 / 1分3 / 1分4 / 1分6；`divider_type('y'/'t'/'cascade'/'mmi')`
  在参考参数表里**没有出处**（已由 `tests/test_complex_device_scope.py` 的护栏挡住）；
* **单馈源 + 单铜波导 ⇒ 1 个端口**（参考就是这么建的）；级联：4 = 2×2（参考 `1d2d4`）、6 = 2×3；
* 可选透镜（DXF）与相位（`dphi`）—— 相位是"把透镜绕 z 转 dphi"，**不是**几何长度差。

⚠️ 本模板**不与参考 notebook 逐字节相同**（设计记录 D1：参考用闭合区域轮廓，
本模板用本库的中心线派生 + 多路径并集）。

运行方式::

    pytest topo_templates/tests/test_power_divider.py -v
"""

import os
import sys
import warnings

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from topo_templates import PowerDivider                       # noqa: E402
from topo_templates.power_divider import (                    # noqa: E402
    CASCADE_FACTORS, SUPPORTED_SPLIT_RATIOS)


def _divider(**kwargs):
    params = dict(trunk_length=6, arm_length=4, sub_length=3)
    params.update(kwargs)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return PowerDivider(**params)


class _Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, item):
        def _f(*a, **k):
            self.calls.append((item, a, k))
            return None
        return _f

    def registered(self):
        return {c[1][0] for c in self.calls if c[0] == 'para'}


# ============================================================
# 1. 分路数：只有 2/3/4/6 有数据依据
# ============================================================

def test_supported_split_ratios_are_the_evidenced_ones():
    assert SUPPORTED_SPLIT_RATIOS == (2, 3, 4, 6)
    assert CASCADE_FACTORS == {2: (2, 1), 3: (3, 1), 4: (2, 2), 6: (2, 3)}


@pytest.mark.parametrize('split_ratio', (2, 3, 4, 6))
def test_output_path_count_equals_the_split_ratio(split_ratio):
    """1 分 N ⇒ **N 条输出路径**（每条都从输入端走到一个输出端）。"""
    divider = _divider(split_ratio=split_ratio)
    assert len(divider.output_paths()) == split_ratio
    assert 'trunk' in divider.paths, '主干必须在（VPC/晶体覆盖要用）'
    for name in divider.output_paths():
        lattice = list(divider.paths[name].path_lattice)
        assert lattice[0] == (0, 0), name          # 都从输入端出发
        assert len(lattice) >= 3, name


@pytest.mark.parametrize('split_ratio', (1, 5, 8, 0))
def test_unsupported_split_ratio_fails_loudly(split_ratio):
    """没有证据的分路数必须报错，不能"看着像"就支持。"""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with pytest.raises(ValueError, match='split_ratio'):
            PowerDivider(split_ratio=split_ratio)


def test_fan_angles_are_lattice_directions():
    """臂方向必须是三角晶格的 60° 方向（`turn(±60)` / `turn(0)`）。"""
    two = _divider(split_ratio=2)
    ends = sorted(round(float(p.xy[-1][1]), 6) for p in
                  (two.paths[n] for n in two.output_paths()))
    assert ends[0] < 0 < ends[-1], ends              # 两条臂分居上下
    three = _divider(split_ratio=3)
    middle = [p for n, p in three.paths.items() if n == 'arm1'][0]
    assert abs(float(middle.xy[-1][1])) < 1e-9, '三分路的中间臂应沿原方向'


def test_cascade_paths_share_their_first_stage_arm():
    """级联结构：**同源**的两条输出路径必须共享第一阶段（主干 + 第一级臂）。"""
    divider = _divider(split_ratio=4)
    left = list(divider.paths['arm0_0'].path_lattice)
    right = list(divider.paths['arm0_1'].path_lattice)
    # 前 3 个点 = 起点 + 主干末点 + 第一级臂末点
    assert left[:3] == right[:3], (left, right)
    assert left[3] != right[3], '第二阶段必须分叉（否则不是级联）'


def test_cascade_second_stage_fans_out_from_the_first_stage():
    """第二级扇出的方向是 60° 家族的晶格方向（切比雪夫步长一致）。"""
    divider = _divider(split_ratio=6)
    names = [n for n in divider.paths if n.startswith('arm0_')]
    assert len(names) == 3, names
    ends = [divider.paths[n].path_lattice[-1] for n in names]
    assert len(set(map(tuple, ends))) == 3, ends


# ============================================================
# 2. 端口与馈源：单端口 + 单波导
# ============================================================

def test_single_port_and_single_waveguide():
    """参考 α2 就是**单馈源 + 单铜波导 + 1 端口**。"""
    divider = _divider(split_ratio=2)
    assert divider.port_number == 1
    summary = divider.summary()
    assert summary['port'] == 1
    assert summary['has_lens'] is False


def test_feed_params_reject_unknown_names():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with pytest.raises(ValueError, match='未知参数名'):
            PowerDivider(feed_params={'lf5': 0.2})       # BA 族的键，本器件不用


# ============================================================
# 3. 透镜与相位（可选）
# ============================================================

def test_phase_without_lens_is_rejected():
    """相位作用在透镜上 ⇒ 没透镜却给相位是无效输入（必须报错，不静默忽略）。"""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with pytest.raises(ValueError, match='lens_phase'):
            PowerDivider(lens_phase=(30, 10))


def test_lens_dxf_must_exist(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with pytest.raises(FileNotFoundError, match='DXF'):
            PowerDivider(lens_dxf=str(tmp_path / 'nope.dxf'))


def test_lens_spec_is_offline_computable():
    """透镜几何规格离线可算（参考的 `para_init` 那套公式）。"""
    divider = _divider(split_ratio=4)
    spec = divider.make_lens_spec()
    assert spec.ratio > 0 and spec.ec_a > 0 and spec.r_big > 0
    assert spec.r_out > spec.r_in


def test_lens_options_are_recorded_in_summary(tmp_path):
    dxf = tmp_path / 'lens.dxf'
    dxf.write_text('placeholder', encoding='utf-8')
    divider = _divider(split_ratio=4, lens_dxf=str(dxf), lens_phase=(30, 10))
    summary = divider.summary()
    assert summary['has_lens'] is True
    assert summary['lens_phase'] == [30, 10]


# ============================================================
# 4. 参数登记与无 CST 行为
# ============================================================

def test_registers_paths_array_range_and_feed_params():
    divider = _divider(split_ratio=4)
    app = _Recorder()
    divider.app = app
    divider._define_all_params()
    registered = app.registered()
    assert {'xup', 'yup', 'ydn', 'a', 'h', 'l1', 'l2', 'e1', 'e2'} <= registered
    assert {'x0', 'wf1', 'lf1', 'lf2', 'lf3'} <= registered
    assert {'wg_a', 'wg_b', 'wg_t'} <= registered
    # 5 条路径各用自己的前缀（trunk + 4 条输出）
    assert len([n for n in registered if n.endswith('x') and n[:1] == 'p']) >= 5


def test_build_without_cst_raises():
    divider = _divider(split_ratio=2)
    if divider.app is not None:
        pytest.skip('本机有 CST 环境，跳过"无 CST"分支')
    with pytest.raises(RuntimeError, match='CST'):
        divider.build_all()


# ============================================================
# 6. 透镜路线：`lens_method` 两条（`dxf` / `insitu`）
# ============================================================
#
# ⚠️ 本轮修掉的**真缺陷**：模板原先**没有登记 `Rbig`/`Ls`**，而
# `build_grin_lens_from_dxf` 对它们有前置拦截 ⇒ `lens_dxf=...` 这条路线
# 在真机上根本走不通（抛我们自己的 preflight ValueError）。

def _divider(**kwargs):
    """构造模板（无 CST 环境时 app=None，几何照算）。"""
    params = dict(split_ratio=4, trunk_length=8, arm_length=6, sub_length=6)
    params.update(kwargs)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return PowerDivider(**params)


class _ParaRecorder:
    """记录 `para` / 变换调用的假 app（**别与上面的 `_Recorder` 重名** —— 
    重名会覆盖掉前面测试用的那个，静默改掉它们的语义）。"""

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


def test_divider_default_has_no_lens():
    divider = _divider()
    assert divider.has_lens is False
    assert divider.lens_method is None
    assert divider.lens_summary() == {'method': None, 'phase': []}
    app = _ParaRecorder()
    divider.app = app
    divider._define_all_params()
    names = app.para_names()
    assert 'Rbig' not in names and 'Ls' not in names and 'dphi1' not in names


def test_divider_dxf_method_requires_dxf(tmp_path):
    with pytest.raises(ValueError, match='必须给 lens_dxf'):
        _divider(lens_method='dxf')
    with pytest.raises(FileNotFoundError):
        _divider(lens_method='dxf', lens_dxf=str(tmp_path / 'nope.dxf'))


def test_divider_legacy_lens_dxf_implies_dxf_method(tmp_path):
    """历史行为：只给 `lens_dxf`（不写 `lens_method`）等价于 `'dxf'`。"""
    dxf = tmp_path / 'lens.dxf'
    dxf.write_text('0\n', encoding='utf-8')
    divider = _divider(lens_dxf=str(dxf))
    assert divider.lens_method == 'dxf' and divider.has_lens is True
    assert divider.lens_summary()['dxf'] == str(dxf)


def test_divider_insitu_rejects_dxf_and_bad_layers(tmp_path):
    dxf = tmp_path / 'lens.dxf'
    dxf.write_text('0\n', encoding='utf-8')
    with pytest.raises(ValueError, match='互斥'):
        _divider(lens_method='insitu', lens_dxf=str(dxf))
    with pytest.raises(ValueError, match='lens_layers'):
        _divider(lens_method='insitu', lens_layers=0)
    with pytest.raises(ValueError, match='lens_method'):
        _divider(lens_method='in-situ')


def test_divider_phase_without_lens_is_rejected():
    with pytest.raises(ValueError, match='lens_phase'):
        _divider(lens_phase=(30, 10))


def test_divider_registers_rbig_for_both_lens_routes(tmp_path):
    """`Rbig` 三条路线都要；`Ls` 只有**椭圆透镜**路线要（就地路线登记它=死写入）。

    ⚠️ 真机首跑抓到的两个错（离线测试当时只覆盖了 `dxf`/`insitu`）：
    ① 模板一个前置参数都没登记 ⇒ `build_grin_lens_from_dxf` 直接抛 ValueError；
    ② `Ls` 只在 `lens_method == 'dxf'` 时登记 ⇒ **`generate` 路线漏登记**，
       而它走的 `build_grin_lens` 同样要 `Ls`（楔形裁剪）。
    判据因此是"就地路线不要、其余两条都要"。
    """
    dxf = tmp_path / 'lens.dxf'
    dxf.write_text('0\n', encoding='utf-8')
    for method, kwargs, want_ls in (('dxf', {'lens_dxf': str(dxf)}, True),
                                    ('generate', {}, True),
                                    ('insitu', {}, False)):
        divider = _divider(lens_method=method, lens_phase=(30, 10), **kwargs)
        app = _ParaRecorder()
        divider.app = app
        divider._define_all_params()
        names = app.para_names()
        assert 'Rbig' in names, f'{method} 路线必须登记 Rbig'
        assert ('Ls' in names) is want_ls, f'{method} 路线 Ls 登记错了：{names}'
        assert 'dphi1' in names and 'dphi2' in names
        # Rbig 的值 = 参考公式 a*(3*n_small/4+lx1)，用表达式而不是烘死的小数
        value = [c[1][1] for c in app.calls if c[0] == 'para' and c[1][0] == 'Rbig'][0]
        assert isinstance(value, str) and value.endswith('*a'), value


def test_divider_insitu_ring_geometry(tmp_path):
    """就地环透镜的孔集合离线可算；参数与 `GRINLensAntenna` 同口径。"""
    divider = _divider(lens_method='insitu', lens_layers=10, lens_d0_layers=3)
    ring = divider.make_lens_ring()
    assert ring['hex_size'] == pytest.approx(divider.a / 3 ** 0.5 / 2)
    assert ring['a2'] == pytest.approx(divider.a / 2)
    assert ring['n_layers'] == 10
    assert len(ring['holes']) == 91
    assert divider.make_lens_ring() is ring, '离线孔集合应缓存'
    info = divider.lens_summary()
    assert info['method'] == 'insitu' and info['dxf'] is None
    assert info['n_holes'] == 91 and info['layers'] == 10
    # 摘要里不能出现椭圆路线的量（那是另一套几何，混用会误导）
    assert 'ec_a' not in info


def test_divider_insitu_build_sequence(tmp_path):
    """就地路线下发序列（与 `GRINLensAntenna` 一致），且带相位时多一次 rotation。"""
    from topo_modeler.builders import build_grin_lens_insitu
    divider = _divider(lens_method='insitu', lens_layers=10, lens_d0_layers=3,
                       lens_phase=(30, 10), lens_name='lens_epc')

    class _OpRecorder:
        def __init__(self):
            self.ops = []

        def __getattr__(self, item):
            def _f(*a, **k):
                self.ops.append((item, k))
            return _f

    app = _OpRecorder()
    info = build_grin_lens_insitu(app, divider.make_lens_ring(),
                                  name=divider.lens_name,
                                  component=divider.lens_component)
    ops = [c[0] for c in app.ops]
    assert ops.count('hexagon') == 91
    assert ops.count('add') == 90
    assert ops.count('mirror') == 1 and ops.count('subtract') == 2
    assert info['n_lenses'] == 6 and info['method'] == 'insitu'
    # 组件必须一路带到变换上（真机踩过的坑）
    for op, kwargs in app.ops:
        if op in ('translate', 'rotation', 'mirror'):
            assert kwargs.get('component') == 'gridlens', (op, kwargs)


def test_divider_summary_reports_lens():
    divider = _divider(split_ratio=2, lens_method='insitu', lens_layers=10,
                       lens_d0_layers=3)
    summary = divider.summary()
    assert summary['has_lens'] is True
    assert summary['lens_method'] == 'insitu'
    assert summary['lens']['n_holes'] == 91
    assert summary['n_output_paths'] == 2


def test_divider_generate_method_writes_dxf(tmp_path):
    """`lens_method='generate'`：孔阵列**离线现算并落 DXF**（不需要 CST）。"""
    divider = _divider(lens_method='generate',
                       lens_dxf_out=str(tmp_path / 'gen.dxf'))
    path = divider.make_lens_dxf()
    assert path == str(tmp_path / 'gen.dxf')
    assert os.path.isfile(path) and os.path.getsize(path) > 1024
    info = divider.lens_summary()
    assert info['method'] == 'generate'
    assert info['dxf'] == path
    assert info['ec_a'] > 0 and info['r_big'] > 0


def test_divider_generate_conflicts_with_dxf(tmp_path):
    dxf = tmp_path / 'lens.dxf'
    dxf.write_text('0\n', encoding='utf-8')
    with pytest.raises(ValueError, match='互斥'):
        _divider(lens_method='generate', lens_dxf=str(dxf))


def test_divider_lens_defaults_match_the_reference_arithmetic():
    """参考 `para_init(yl=10, ratio=2)`：`r=[50.5,61.3]/1e3/ratio*2` ⇒ **等效 0.0505**。

    ⚠️ 这是一条**更正回归**（2026-09-18）：`GrinLensSpec` 的约定是 `r = r1_0/ratio`，
    参考是 `2*r_raw/ratio` ⇒ `r1_0` 必须写 **0.101**。原先写 0.0505 时孔半径小一半。
    """
    divider = _divider(lens_method='generate')
    spec = divider.make_lens_spec()
    assert spec.ratio == 2.0
    assert spec.nx == 24 and spec.ny == 21        # int(10*1.15)*2+1 / 10*2+1
    assert spec.r_in == pytest.approx(0.0505)     # 参考的等效半径
    assert spec.r_out == pytest.approx(0.0613)
    assert spec.d0 == pytest.approx(12 * spec.a2)  # 参考 `6*hexsize*2*sqr(3)`


# ============================================================
# 7. 开关/泵浦区（`pump_switching` 特征）
# ============================================================
#
# 参考做法（`功分器加天线\椭圆透镜1div3\Ant2_1div2_BA_120D_epc.ipynb` /
# `B5\Ant6_2H4L_epc.ipynb`）：
#   para('sigma1','0') → create_material_custom('switch1', epsilon=11.9, kappa='sigma1')
#   para('rc1','0.4')
#   for i in range(4):
#       translate('vpca',[0,0,0],copy=True,unite=False)
#       intersect(f'sw{i+1}','vpca_1')      # 副本名恒为 vpca_1
#       insert('vpca', f'sw{i+1}')

def test_divider_default_has_no_switch():
    divider = _divider()
    assert divider.has_switch is False
    assert divider.switch_positions() == []
    app = _ParaRecorder()
    divider.app = app
    divider._define_all_params()
    names = app.para_names()
    assert 'rc1' not in names and 'sigma1' not in names


def test_divider_switch_validation():
    with pytest.raises(ValueError, match='switch_mode'):
        _divider(switch_mode='arm')
    with pytest.raises(ValueError, match='switch_xy'):
        _divider(switch_mode='explicit')
    with pytest.raises(ValueError, match='冲突'):
        _divider(switch_mode='arm_mid', switch_xy=[(0, 0)])
    with pytest.raises(ValueError, match='半径'):
        _divider(switch_mode='arm_mid', switch_radius=0)
    with pytest.raises(ValueError, match='\\(x, y\\)'):
        _divider(switch_xy=[(0, 0, 0)])


def test_divider_switch_positions_use_registered_params():
    """`arm_mid` 的位置是**每条第一级输出臂最后一段的中点**（用已登记的路径参数表达）。"""
    divider = _divider(split_ratio=3, switch_mode='arm_mid')
    positions = divider.switch_positions()
    assert len(positions) == 3, positions
    names = list(divider.paths)
    for (x_expr, y_expr), path_name in zip(positions, divider.output_paths()):
        index = names.index(path_name)
        points = len(divider.paths[path_name].path_lattice)
        assert x_expr == f'(p{index}{points - 1}x+p{index}{points}x)/2'
        assert y_expr == f'(p{index}{points - 1}y+p{index}{points}y)/2'


def test_divider_explicit_switch_positions_are_passed_through():
    divider = _divider(switch_mode='explicit',
                       switch_xy=[('px2', 'py2'), (0.5, '-0.5')])
    assert divider.switch_positions() == [('px2', 'py2'), ('0.5', '-0.5')]


def test_divider_registers_rc1_and_sigma1_only_with_switches():
    divider = _divider(split_ratio=4, switch_mode='arm_mid', switch_sigma=100)
    app = _ParaRecorder()
    divider.app = app
    divider._define_all_params()
    values = {c[1][0]: c[1][1] for c in app.calls if c[0] == 'para'}
    assert values['rc1'] == 0.4
    assert values['sigma1'] == 100


def test_divider_switch_build_sequence():
    """下发序列 = 自定义材料 → 每个开关：圆柱 + 区域副本 + 求交 + insert。"""
    divider = _divider(split_ratio=2, switch_mode='arm_mid')

    class _OpRecorder:
        def __init__(self):
            self.ops = []

        def __getattr__(self, item):
            def _f(*a, **k):
                self.ops.append((item, a, k))
            return _f

    app = _OpRecorder()
    divider.app = app
    divider._parts = {'vpca': 'vpc_A'}
    made = divider.build_switches()
    ops = [c[0] for c in app.ops]
    assert made == ['switch1', 'switch2']
    assert ops.count('create_material_custom') == 1
    assert ops.count('create_cylinder') == 2
    assert ops.count('translate') == 2          # 每个开关各拷一次区域
    assert ops.count('intersect') == 2
    assert ops.count('insert') == 2
    # 求交的第二个操作数必须是**区域副本**（`vpc_A_1`），不是区域本身
    regions = [c[1][1] for c in app.ops if c[0] == 'intersect']
    assert regions == ['vpc_A_1', 'vpc_A_1'], regions
    assert [c[1][0] for c in app.ops if c[0] == 'intersect'] == ['switch1', 'switch2']
    # 圆柱用 `rc1` 参数（不是烘死的半径）
    cyls = [c for c in app.ops if c[0] == 'create_cylinder']
    assert all(c[2]['r'][0] == 'rc1' for c in cyls), cyls


def test_divider_switch_requires_vpc_region():
    divider = _divider(switch_mode='arm_mid')
    divider.app = _ParaRecorder()
    with pytest.raises(ValueError, match='VPC'):
        divider.build_switches()


def test_divider_summary_reports_switches():
    divider = _divider(split_ratio=2, switch_mode='arm_mid', switch_sigma=200)
    summary = divider.summary()
    assert summary['switch_mode'] == 'arm_mid'
    assert summary['switch_sigma'] == 200
    assert len(summary['switch_positions']) == 2
