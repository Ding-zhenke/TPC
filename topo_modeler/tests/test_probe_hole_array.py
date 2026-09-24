# -*- coding: utf-8 -*-
r"""
BA 微锥条 + 椭圆孔阵列探针（P′ 系列）—— 离线验收
================================================

本文件守住**不需要 CST 的那一半**：参数口径、预设数值、几何顶点（绕向/闭合）、
孔心必须是**累加表达式**而不是烘好的小数、以及「缺参数会让 CST 弹模态框挂住」
的前置拦截。

取证来源（只读引用下游工作区 `拓扑光子晶体模型\硅基\探针问题`，2026-09-24）
------------------------------------------------------------------------
* 建模脚本 `_work\probe_build.py`：`_probe_outline()` + `build_custom_probe()`
* 优化报告 `分析报告\REPORT_Pp4.md`
* 最优工程 `_work\opt\Pp4_L0.60\opt_Pp4_L0.60.cst` 的 `Model/Parameters.json`

真机侧（`Rebuild()` 后 `get_messages()` 为空、实际求解）属于 P4 验收项，不在本文件。

运行方式::

    pytest topo_modeler/tests/test_probe_hole_array.py -v
"""

import os
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from topo_modeler.builders import (                        # noqa: E402
    PROBE_HOLE_ARRAY_PARAMS,
    PROBE_PRESETS,
    build_ba_hole_array_feed,
    build_feed,
    probe_param_names,
    probe_param_note,
    register_probe_params,
)


class _Recorder:
    """记录调用的假 app（与 `test_multiport_feed.py` 同一套路）。"""

    def __init__(self):
        self.calls = []

    def __getattr__(self, item):
        def _f(*a, **k):
            self.calls.append((item, a, k))
            return None
        return _f

    def paras(self):
        return {c[1][0]: c[1][1] for c in self.calls if c[0] == 'para'}

    def para_kwargs(self, name):
        for op, args, kwargs in self.calls:
            if op == 'para' and args and args[0] == name:
                return kwargs
        return {}

    def ops(self, name):
        return [c for c in self.calls if c[0] == name]


#: 用来把顶点里的 CST 表达式**数值化**（只为算绕向，不代表真机取值）
_CTX = {'a': 0.2425, 'e1': 0.2425 / 2, 'e2': 0.2425 * 3 ** 0.5 / 2,
        'x01': 0, 'wf2': 0.2, 'lf4': 0.2,
        'pb_L_in': PROBE_PRESETS['Pp4']['values']['pb_L_in'],
        'pb_w_tip': PROBE_PRESETS['Pp4']['values']['pb_w_tip']}


def _poly_pts(recorder):
    """取 `polyline` 的顶点列表（数值化）。"""
    calls = recorder.ops('polyline')
    assert len(calls) == 1, f'polyline 应只调一次，实际 {len(calls)} 次'
    data = calls[0][1][0]
    return [(float(eval(str(x), {'__builtins__': {}}, _CTX)),
             float(eval(str(y), {'__builtins__': {}}, _CTX))) for x, y in data]


def _signed_area(pts):
    """有向面积：> 0 = 逆时针 CCW（CST 的 ExtrudeCurve 沿法向拉伸）。"""
    s = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        s += x1 * y2 - x2 * y1
    return s / 2.0


# ============================================================
# 1. 参数口径与预设
# ============================================================

def test_param_names_are_the_cumulative_offsets_of_the_workspace():
    """逐孔参数名 = 首孔位置 + (n−1) 个孔距 + n 个长轴 + n 个短轴。"""
    n = probe_param_names(4)
    assert n[0] == 'pb_x_h0'
    assert [x for x in n if x.startswith('pb_p_e')] == \
        ['pb_p_e1', 'pb_p_e2', 'pb_p_e3']
    assert [x for x in n if x.startswith('pb_d_ex')] == \
        ['pb_d_ex1', 'pb_d_ex2', 'pb_d_ex3', 'pb_d_ex4']
    assert [x for x in n if x.startswith('pb_d_ey')] == \
        ['pb_d_ey1', 'pb_d_ey2', 'pb_d_ey3', 'pb_d_ey4']
    with pytest.raises(ValueError):
        probe_param_names(0)


def test_common_param_meanings_are_documented():
    """三个公共参数的含义必须写清（工作区的结构图就是按这个口径标注的）。"""
    assert set(PROBE_HOLE_ARRAY_PARAMS) == {'pb_L_in', 'pb_w_tip', 'pb_x_h0'}
    assert '插入' in PROBE_HOLE_ARRAY_PARAMS['pb_L_in']
    assert '末端宽度' in PROBE_HOLE_ARRAY_PARAMS['pb_w_tip']
    assert '末端的距离' in PROBE_HOLE_ARRAY_PARAMS['pb_x_h0']
    # 逐孔参数也要有中文说明（写进 CST 参数表）
    assert '孔心距' in probe_param_note('pb_p_e2')
    assert '长轴' in probe_param_note('pb_d_ex3')
    assert '短轴' in probe_param_note('pb_d_ey1')


def test_preset_covers_exactly_the_declared_parameter_names():
    """预设的键集合必须与 `probe_param_names` 完全对上（漏/多都是 bug）。"""
    spec = PROBE_PRESETS['Pp4']
    expected = set(probe_param_names(spec['n_holes'])) | {'pb_L_in',
                                                          'pb_w_tip'}
    assert set(spec['values']) == expected
    assert spec['n_holes'] == 4


def test_preset_values_match_the_delivered_project():
    """数值必须与交付工程一致（四位小数，与工作区报告表格逐位对得上）。"""
    v = PROBE_PRESETS['Pp4']['values']
    assert v['pb_L_in'] == pytest.approx(0.5988)
    assert v['pb_w_tip'] == pytest.approx(0.1610)
    assert v['pb_x_h0'] == pytest.approx(0.0646)
    assert v['pb_p_e3'] == pytest.approx(0.1394)
    assert v['pb_d_ex2'] == pytest.approx(0.1295)
    assert v['pb_d_ey4'] == pytest.approx(0.0458)
    # 四位小数：不能有更细的尾巴（否则报告表格与库里的值会逐位对不上）
    for name, value in v.items():
        assert round(value, 4) == value, f'{name}={value!r} 不是四位小数'


def test_preset_records_its_metrics_and_provenance():
    """预设要自带指标与出处 —— 否则事后没人知道这串数字是哪来的。"""
    spec = PROBE_PRESETS['Pp4']
    assert spec['metrics']['RL_dB'] > spec['metrics']['baseline_A_RL_dB']
    assert spec['metrics']['IL_dB'] < spec['metrics']['baseline_A_IL_dB']
    assert 'Trust Region' in spec['provenance']
    assert spec['report'] and spec['project']


def test_register_probe_params_writes_every_value_and_a_note():
    """登记时每个 `pb_*` 都要落参数表，并带上说明文本。"""
    app = _Recorder()
    info = register_probe_params(app)
    got = app.paras()
    assert got == PROBE_PRESETS['Pp4']['values']
    assert info['n_holes'] == 4
    for name in got:
        assert app.para_kwargs(name)['expression'], f'{name} 缺说明文本'


def test_register_probe_params_supports_overrides_and_rejects_unknown():
    """`overrides` 只改指定项；未知预设名要抛 ValueError 而不是静默。"""
    app = _Recorder()
    register_probe_params(app, overrides={'pb_L_in': 0.60})
    assert app.paras()['pb_L_in'] == 0.60
    assert app.paras()['pb_w_tip'] == PROBE_PRESETS['Pp4']['values']['pb_w_tip']
    with pytest.raises(ValueError):
        register_probe_params(app, preset='NotAPreset')


# ============================================================
# 2. 几何：顶点、绕向、孔阵列
# ============================================================

def test_outline_is_closed_and_counter_clockwise():
    """闭合 + CCW（绕向错会让 ExtrudeCurve 沿 −z 拉伸，与晶体差一个 h）。"""
    app = _Recorder()
    build_ba_hole_array_feed(app, n_holes=4)
    pts = _poly_pts(app)
    assert len(pts) == 12, f'顶点数应为 12（含闭合点），实际 {len(pts)}'
    assert pts[0] == pts[-1], '最后一点必须回到首点（CST 曲线要闭合）'
    assert _signed_area(pts) > 0, '多边形应为逆时针 CCW'


def test_taper_end_width_is_the_tip_width_not_the_neck():
    """末端两个顶点必须用 `pb_w_tip/2`（微锥条），不是 `wf2/2`。"""
    app = _Recorder()
    build_ba_hole_array_feed(app, n_holes=4)
    data = app.ops('polyline')[0][1][0]
    tip_x = '-lf4-pb_L_in'
    tip_ys = sorted(str(p[1]) for p in data if str(p[0]) == tip_x)
    assert tip_ys == ['-pb_w_tip/2', 'pb_w_tip/2']


def test_holes_are_subtracted_with_cumulative_expressions():
    """
    孔心必须是**累加 CST 表达式**（`末端 + pb_x_h0 + pb_p_e1 + …`），
    且每孔长短轴独立 —— 烘成小数就丢了参数化（优化器扫不动）。
    """
    app = _Recorder()
    build_ba_hole_array_feed(app, n_holes=4)

    assert len(app.ops('create_elliptical_cylinder')) == 4
    assert len(app.ops('subtract')) == 4

    # 平移：前 4 次是孔心，最后一次是 z 居中（`translate(name, 向量, ...)`）
    moves = [c[1][1] for c in app.ops('translate')]
    assert moves[-1] == ['0', '0', '-h/2'], moves[-1]
    centers = [m[0] for m in moves[:4]]
    assert centers[0] == '-lf4-pb_L_in+pb_x_h0'
    assert centers[1] == '-lf4-pb_L_in+pb_x_h0+pb_p_e1'
    assert centers[2] == '-lf4-pb_L_in+pb_x_h0+pb_p_e1+pb_p_e2'
    assert centers[3] == '-lf4-pb_L_in+pb_x_h0+pb_p_e1+pb_p_e2+pb_p_e3'

    radii = [(c[2]['x_radius'], c[2]['y_radius'])
             for c in app.ops('create_elliptical_cylinder')]
    assert radii[0] == ('pb_d_ex1/2', 'pb_d_ey1/2')
    assert radii[3] == ('pb_d_ex4/2', 'pb_d_ey4/2')


def test_hole_count_is_a_discrete_argument():
    """孔数是**离散量**（改个数要重建模型）：3 孔就该只出 3 个孔。"""
    app = _Recorder()
    build_ba_hole_array_feed(app, n_holes=3)
    assert len(app.ops('subtract')) == 3
    assert len(app.ops('polyline')) == 1
    with pytest.raises(ValueError):
        build_ba_hole_array_feed(_Recorder(), n_holes=0)


def test_builder_can_register_the_preset_itself():
    """`register_preset='Pp4'` 时 builder 自己把参数写进工程（便利入口）。"""
    app = _Recorder()
    build_ba_hole_array_feed(app, n_holes=4, register_preset='Pp4')
    assert app.paras()['pb_L_in'] == PROBE_PRESETS['Pp4']['values']['pb_L_in']


def test_missing_params_are_rejected_before_they_can_hang_cst():
    """
    真机上缺参数时**提前失败**：CST 会弹模态对话框把脚本挂住（不是抛异常）。
    """
    from cst_solver._guards import get_guard_state

    class _App(_Recorder):
        pass

    app = _App()
    guard = get_guard_state(app)
    guard.attach_param_probe(lambda name: False)      # 假装「一个都不存在」
    with pytest.raises(ValueError) as ei:
        build_ba_hole_array_feed(app, n_holes=4)
    assert 'pb_L_in' in str(ei.value)
    guard.attach_param_probe(None)                    # 收尾：别把状态漏给别的测试


# ============================================================
# 3. 统一入口
# ============================================================

def test_build_feed_dispatches_ba_hole_array():
    """`build_feed` 要认得新类型，且默认名与 BA 族一致（`feed2`）。"""
    app = _Recorder()
    name = build_feed(app, feed_type='ba_hole_array', n_holes=4)
    assert name == 'feed2'
    assert len(app.ops('subtract')) == 4
    with pytest.raises(ValueError) as ei:
        build_feed(app, feed_type='nope')
    assert 'ba_hole_array' in str(ei.value)
