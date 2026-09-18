# -*- coding: utf-8 -*-
r"""
多端口馈源族（`lf4/lf5/lf6/wf2`）—— P5 取证与登记（离线）
========================================================

计划原文（`docs/next_plan/README.md` P5）：

> `MultiPortAntenna`、`PowerDivider`、`MZISwitch` 三类模板；
> **提取多端口 `lf4-lf6/wf2` 馈源族**、basic/cascade 拓扑差别。

本文件守住"提取"这部分里**不需要 CST 的那一半**：
参数语义、派生量的**表达式口径**、以及"缺参数会让 CST 弹模态框挂住"的前置拦截。

取证来源（只读解析 12 个多端口/功分 notebook 的 code cell，2026-09-17）
------------------------------------------------------------------------
`多端口\Ant6_undiretional\ANT6_undirectional.ipynb` 的**权威注释**：

```python
wf2 = 0.2   # 探针颈部宽度
lf4 = 0.2   # 探针颈部长度
lf5 = 3.0   # 椭圆过渡段长度
lf6 = 0.2   # 铜波导端口段长度
```

同族 `ANT6_C6_hexring.ipynb` 的 `CST_PARAMS` 表给出派生量：

```python
('wg_out', 'rin-lf4',        '铜波导径向外端 = 探针颈部起点'),
('wg_in',  'wg_out-lf5-lf6', '铜波导径向内端 = 波端口所在半径'),
```

⚠️ **本库此前没有登记 `lf6`**，而多端口族铜波导的 x 范围写法
`x_min='-lf5-lf6-lf4'` **引用它** —— 参数未定义时 CST 弹「请输入变量值」模态
对话框把脚本挂住（不是抛异常），所以这条登记是**防挂死**的，不只是补全。

运行方式::

    pytest topo_modeler/tests/test_multiport_feed.py -v
"""

import os
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from topo_modeler.builders import (                       # noqa: E402
    MULTIPORT_FAMILY_PARAMS,
    MULTIPORT_WG_X_MAX,
    MULTIPORT_WG_X_MIN,
    build_multiport_waveguide,
    register_multiport_params,
)


class _Recorder:
    """记录调用的假 app（`para` / `square` / `pick_face` 等）。"""

    def __init__(self):
        self.calls = []

    def __getattr__(self, item):
        def _f(*a, **k):
            self.calls.append((item, a, k))
            if item in ('get_picked_count',):
                return 1                              # 面拾取校验：假装选中 1 个面
            return None
        return _f

    # 便于断言
    def paras(self):
        return {c[1][0]: c[1][1] for c in self.calls if c[0] == 'para'}

    def para_kwargs(self, name):
        for op, args, kwargs in self.calls:
            if op == 'para' and args and args[0] == name:
                return kwargs
        return {}

    def ops(self, name):
        return [c for c in self.calls if c[0] == name]


# ============================================================
# 1. 参数语义与派生量口径
# ============================================================

def test_family_params_carry_the_evidence_based_meanings():
    """四个参数的含义必须写清（它们来自 notebook 里的权威注释）。"""
    assert set(MULTIPORT_FAMILY_PARAMS) == {'wf2', 'lf4', 'lf5', 'lf6'}
    assert '颈部宽度' in MULTIPORT_FAMILY_PARAMS['wf2']
    assert '颈部长度' in MULTIPORT_FAMILY_PARAMS['lf4']
    assert '过渡段' in MULTIPORT_FAMILY_PARAMS['lf5']
    assert '端口段' in MULTIPORT_FAMILY_PARAMS['lf6']


def test_default_values_match_the_reference_notebooks():
    """默认值取参考里最常见的组合（lf4/lf5/lf6/wf2 = 0.2/3.0/0.2/0.2）。"""
    app = _Recorder()
    register_multiport_params(app, rin='Rbig', rin_expression='2.91')
    got = app.paras()
    assert (got['wf2'], got['lf4'], got['lf5'], got['lf6']) == (0.2, 0.2, 3.0, 0.2)


def test_derived_params_are_expressions_not_baked_numbers():
    """
    `wg_out` / `wg_in` 必须是**表达式**（`rin-lf4` / `wg_out-lf5-lf6`），
    与参考 notebook 的 CST_PARAMS 表逐字一致 —— 烘成小数就丢了参数化
    （同 P4 §8.7「阵列次数必须是参数引用」的纪律）。
    """
    app = _Recorder()
    info = register_multiport_params(app, rin='Rbig', rin_expression='2.91')
    got = app.paras()
    assert got['wg_out'] == 'Rbig-lf4', got['wg_out']
    assert got['wg_in'] == 'wg_out-lf5-lf6', got['wg_in']
    assert info['derived'] == {'wg_out': 'Rbig-lf4', 'wg_in': 'wg_out-lf5-lf6'}
    # 表达式写在 para 的 expression 字段里（人类可读说明），不是数值
    assert app.para_kwargs('wg_out')['expression']


def test_rin_can_be_registered_by_expression():
    """没现成的 `rin` 时，可以传 `rin_expression` 让本函数登记。"""
    app = _Recorder()
    register_multiport_params(app, rin='rin', rin_expression='Rbig/2')
    assert app.paras()['rin'] == 'Rbig/2'


def test_missing_rin_is_rejected_before_it_can_hang_cst():
    """
    缺 `rin` 时**提前失败**：CST 遇到未定义参数会弹模态对话框把脚本挂住
    （P4/V6 的 Rbig/Ls 教训），所以这里必须抛 ValueError 而不是让它撞到 CST。
    """
    class _Guard:
        _param_probe = object()                   # 假装真机（探针已接上）

        def param_existed(self, name):
            return False                          # 查不到 ⇒ 未定义

    app = _Recorder()
    app.para('x', 1)                              # 触发"第一次 para"（真实 app 在此接探针）
    import cst_solver._guards as guards
    original = guards.get_guard_state
    guards.get_guard_state = lambda _app: _Guard()
    try:
        with pytest.raises(ValueError, match='rin'):
            register_multiport_params(app, rin='rin')
    finally:
        guards.get_guard_state = original


def test_offline_fake_app_skips_the_probe_check():
    """离线假 app 没有探针 ⇒ 不做拦截（否则单测全误报）。"""
    app = _Recorder()
    register_multiport_params(app, rin='rin')     # 不抛异常
    assert app.paras()['wg_out'] == 'rin-lf4'


# ============================================================
# 2. 多端口族铜波导
# ============================================================

def test_waveguide_defaults_come_from_the_family_geometry():
    """x 范围默认 `[-lf5-lf6-lf4, -lf4]`（椭圆过渡段之外那段），逐字同参考。"""
    assert (MULTIPORT_WG_X_MIN, MULTIPORT_WG_X_MAX) == ('-lf5-lf6-lf4', '-lf4')
    app = _Recorder()
    info = build_multiport_waveguide(app, name='wg2')
    assert info['x_min'] == '-lf5-lf6-lf4' and info['x_max'] == '-lf4'
    squares = app.ops('square')
    assert squares, '波导应当由外方体 + 内方体组成'
    assert squares[0][1][0] == '-lf5-lf6-lf4'     # 外方体 xmin
    assert squares[0][1][1] == '-lf4'             # 外方体 xmax
    assert app.ops('subtract'), '空心波导 = 外方体 − 内方体'


def test_waveguide_can_add_its_port_with_the_reference_face():
    """多端口族的端口面用 `'10'`（轴向口径端面，12/12 notebook 一致）。"""
    app = _Recorder()
    info = build_multiport_waveguide(app, name='wg2', port_number=1)
    assert info['port'] == 1
    picked = app.ops('pick_face')
    assert picked and picked[0][1] == ('wg2', '10'), picked
    assert app.ops('add_port'), '应当真的调用了 add_port'


def test_waveguide_without_port_number_adds_no_port():
    app = _Recorder()
    build_multiport_waveguide(app, name='wg2')
    assert not app.ops('add_port') and not app.ops('pick_face')


# ============================================================
# 3. 多端口端口组（α1 族：双馈源 ⇒ 3 端口）
# ============================================================

def test_multiport_port_set_uses_the_numbers_the_caller_gives():
    """
    ⚠️ 端口编号在参考 notebook 之间**有对调** ⇒ 编号必须由调用方给，
    本函数不许猜（猜错会把激励端口搞反，而 CST 不会报错）。
    """
    from topo_modeler.builders import add_multiport_port_set

    app = _Recorder()
    created = add_multiport_port_set(app, [('wg2', 1, '10'),
                                           ('wg1', 3, '10'),
                                           ('wg1', 2, '22')])
    assert [c['port'] for c in created] == [1, 3, 2]
    picked = [c[1] for c in app.ops('pick_face')]
    assert picked == [('wg2', '10'), ('wg1', '10'), ('wg1', '22')]
    assert [c[1][0] for c in app.ops('add_port')] == [1, 3, 2]


def test_multiport_port_set_defaults_to_electric_shield():
    """多端口族用 `shield='electric'`（12 个参考 notebook 一致）。"""
    from topo_modeler.builders import add_multiport_port_set

    app = _Recorder()
    created = add_multiport_port_set(app, [('wg1', 1, '10')])
    assert created[0]['shield'] == 'electric'
    # `add_waveguide_port()` 是模块函数（不是 app 方法），它最终调 `app.add_port(n, shield=…)`
    shields = [dict(c[2]).get('shield') for c in app.ops('add_port')]
    assert shields == ['electric'], shields


def test_multiport_port_set_accepts_an_explicit_shield():
    from topo_modeler.builders import add_multiport_port_set

    app = _Recorder()
    created = add_multiport_port_set(app, [('wg1', 2, '22', 'magnetic')])
    assert created[0]['shield'] == 'magnetic'


def test_multiport_port_set_rejects_bad_input():
    from topo_modeler.builders import add_multiport_port_set

    app = _Recorder()
    with pytest.raises(ValueError, match='至少一个'):
        add_multiport_port_set(app, [])
    with pytest.raises(ValueError, match='条目必须是'):
        add_multiport_port_set(app, [('wg1', 1)])
