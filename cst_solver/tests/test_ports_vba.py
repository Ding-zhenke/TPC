# -*- coding: utf-8 -*-
"""
波导端口 VBA 生成回归测试
=========================
对应实施计划 `docs/next_plan/README.md` 的 5.8（优先级 1）。

守住什么
--------
`add_port()` / `create_waveguide_port_free()` 在阶段 5.8 把四行**写死的属性**
（`NumberOfModes` / `AdjustPolarization` / `PolarizationAngle` / `ReferencePlaneDistance`）
开放成了关键字参数。这类「开放写死项」的改动有一条硬要求：

    **不传新参数时，生成的 VBA 必须与改动前逐字节相同。**

否则就等于悄悄改了所有既有模型。基线取自改动前的 `git HEAD:cst_solver/simulation/ports.py`，
逐字节存进 `tests/data/expected_port_vba.json`（由一次性脚本
`scripts/_check_port_vba_identity.py` 对比 HEAD 生成，已实测 7/7 相同）。

⚠️ 顺带说明：本测试只证明**字符串**没变，不证明 CST 认得这些命令 ——
后者只能在真 CST 上验（阶段 5.8 的 CST 验证尚未做，见 stages/05 的风险登记）。

运行方式::

    pytest cst_solver/tests/test_ports_vba.py -v
"""

import json
import os
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from cst_solver.simulation.ports import PortMixin


_FIXTURE = os.path.join(os.path.dirname(__file__), 'data', 'expected_port_vba.json')


def _load_fixture():
    with open(_FIXTURE, encoding='utf-8') as fh:
        return json.load(fh)


_FIX = _load_fixture()
_TUPLE_KEYS = set(_FIX.get('_tuple_keys', ('xrange', 'yrange', 'zrange')))


def _restore_kwargs(raw_kwargs, tuple_keys=_TUPLE_KEYS):
    """JSON 里元组会变成 list，这里按 `_tuple_keys` 还原（标量如 shield 保持原样）。"""
    out = {}
    for key, value in raw_kwargs.items():
        if key in tuple_keys and isinstance(value, list):
            out[key] = tuple(value)
        else:
            out[key] = value
    return out


def _capture(method, *args, **kwargs):
    """调用 PortMixin 的方法，返回 (历史标签, VBA 字符串)。"""
    calls = []

    class _Model3D:
        def add_to_history(self, label, vba):
            calls.append((label, vba))

    class _CstFile:
        model3d = _Model3D()

    inst = PortMixin()
    inst.cst_file = _CstFile()
    getattr(inst, method)(*args, **kwargs)
    assert len(calls) == 1, f"{method} 应只下发一条历史，实际 {len(calls)} 条"
    return calls[0]


_CASES = sorted(_FIX['cases'].items())


@pytest.mark.parametrize('name,case', _CASES, ids=[c[0] for c in _CASES])
def test_port_vba_byte_identical_to_baseline(name, case):
    """不传新关键字参数 → VBA 与改动前逐字节相同（含缩进与行尾空格）。"""
    kwargs = _restore_kwargs(case['kwargs'])
    label, vba = _capture(case['method'], *case['args'], **kwargs)
    assert label == case['label'], f"历史标签变了：{label!r} != {case['label']!r}"
    assert vba == case['vba'], (
        f"{name}: VBA 与基线不再相同 —— 开放写死项不能改变默认输出。\n"
        f"长度 现在={len(vba)} 基线={len(case['vba'])}")


def test_fixture_covers_both_port_flavours():
    """基线必须同时覆盖 Picks 与 Free 两种端口，否则回归测试有盲区。"""
    methods = {c['method'] for c in _FIX['cases'].values()}
    assert methods == {'add_port', 'create_waveguide_port_free'}


# ============================================================
# 新开放的关键字参数确实生效
# ============================================================

def test_number_of_modes_is_effective():
    _, vba = _capture('add_port', 1, number_of_modes=3)
    assert '.NumberOfModes "3"' in vba


def test_polarization_fields_are_effective():
    _, vba = _capture('add_port', 1, adjust_polarization='True',
                      polarization_angle='45')
    assert '.AdjustPolarization "True"' in vba
    assert '.PolarizationAngle "45"' in vba


def test_reference_plane_distance_is_effective():
    _, vba = _capture('add_port', 1, reference_plane_distance='0.5')
    assert '.ReferencePlaneDistance "0.5"' in vba


def test_free_port_accepts_the_same_keywords():
    _, vba = _capture('create_waveguide_port_free', 1, xrange=('0', 'a'),
                      number_of_modes=2, polarization_angle='90',
                      reference_plane_distance='1.5')
    assert '.Coordinates "Free"' in vba
    assert '.NumberOfModes "2"' in vba
    assert '.PolarizationAngle "90"' in vba
    assert '.ReferencePlaneDistance "1.5"' in vba


def test_create_waveguide_port_forwards_kwargs():
    """create_waveguide_port 是 add_port 的别名，关键字参数要能透传。"""
    _, vba = _capture('create_waveguide_port', 7, number_of_modes=4)
    assert '.PortNumber "7"' in vba
    assert '.NumberOfModes "4"' in vba


def test_free_port_requires_at_least_one_range():
    with pytest.raises(ValueError, match='至少需要给出一个方向的范围'):
        _capture('create_waveguide_port_free', 1)
