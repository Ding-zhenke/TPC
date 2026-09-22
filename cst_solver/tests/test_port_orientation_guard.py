# -*- coding: utf-8 -*-
"""端口朝向防呆回归测试（2026-09-20 加固）

背景
----
`Port.Orientation` **只接受 CST 的位置枚举** `xmin/xmax/ymin/ymax/zmin/zmax`
（含义：激励波传入器件的方向）。但本库旧签名把它默认成 `'positive'`，
老 notebook 里也满篇 `orientation='positive'/'negative'` ——

    CST 对非法值**不报错**（`get_messages()` 也是干净的），它把这一行静默忽略、
    退回默认朝向 ⇒ 端口箭头朝外、S21 与预期相反，而建模脚本"看起来一切正常"。

这就是"模型 1 的端口 2 朝向反了"的根因。本文件守住加固后的三条行为：

1. 合法枚举**归一化**后原样下发（大小写/空格不敏感）；
2. `'positive'/'negative'` 等历史误用值 ⇒ 当场 `ValueError`，错误信息里带改法；
3. `orientation=None` ⇒ **不下发** `.Orientation` 行（= 改动前 CST 的实际行为，
   保证既有代码建模结果不变）+ 一条 `UserWarning` 提示"你没说朝向"。

另外守住两份常量不漂移：`cst_solver.simulation.ports.PORT_ORIENTATIONS`
与离线模块 `cst_solver.vba_specs.PORT_ORIENTATIONS`。

运行方式::

    pytest cst_solver/tests/test_port_orientation_guard.py -v
"""

import os
import sys
import warnings

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from cst_solver.simulation.ports import (PORT_ORIENTATIONS,  # noqa: E402
                                         check_port_orientation)
from cst_solver import vba_specs  # noqa: E402


def _capture(method, *args, **kwargs):
    """调用 PortMixin 的方法，返回下发的 VBA 字符串。"""
    calls = []

    class _Model3D:
        def add_to_history(self, label, vba):
            calls.append((label, vba))

    class _CstFile:
        model3d = _Model3D()

    from cst_solver.simulation.ports import PortMixin

    inst = PortMixin()
    inst.cst_file = _CstFile()
    getattr(inst, method)(*args, **kwargs)
    assert len(calls) == 1
    return calls[0][1]


# ============================================================
# 常量
# ============================================================

def test_orientation_enum_is_the_cst_position_enum():
    assert PORT_ORIENTATIONS == ('xmin', 'xmax', 'ymin', 'ymax', 'zmin', 'zmax')


def test_offline_spec_enum_matches_library_enum():
    """离线契约模块故意不 import simulation 包 ⇒ 用测试守住两份常量一致。"""
    assert tuple(vba_specs.PORT_ORIENTATIONS) == PORT_ORIENTATIONS


# ============================================================
# ① 合法值透传 / 归一化
# ============================================================

@pytest.mark.parametrize('value', PORT_ORIENTATIONS)
def test_legal_orientation_is_emitted(value):
    vba = _capture('add_port', 1, value)
    assert f'.Orientation "{value}"' in vba


@pytest.mark.parametrize('raw,expected', [
    ('XMAX', 'xmax'),
    (' Xmin ', 'xmin'),
    ('ZMax', 'zmax'),
])
def test_orientation_is_normalized(raw, expected):
    assert check_port_orientation(raw) == expected
    vba = _capture('add_port', 1, raw)
    assert f'.Orientation "{expected}"' in vba
    # 只应出现一次（别把原始大小写又漏进去）
    assert vba.count('.Orientation') == 1


def test_free_port_emits_legal_orientation():
    vba = _capture('create_waveguide_port_free', 1, xrange=('0', 'a'),
                   yrange=('-b', 'b'), orientation='xmin', shield='electric')
    assert '.Coordinates "Free"' in vba
    assert '.Orientation "xmin"' in vba


# ============================================================
# ② 历史误用值 ⇒ 当场报错（不许静默）
# ============================================================

@pytest.mark.parametrize('bad', ['positive', 'negative', 'Positive', 'NEGATIVE'])
def test_mistaken_orientation_raises(bad):
    with pytest.raises(ValueError) as exc:
        check_port_orientation(bad)
    msg = str(exc.value)
    assert 'position' in msg.lower() or '位置枚举' in msg
    assert 'xmin' in msg and 'xmax' in msg      # 错误信息要给改法
    assert '静默' in msg                        # 说清为什么危险


def test_add_port_rejects_mistaken_orientation():
    with pytest.raises(ValueError, match='xmin'):
        _capture('add_port', 1, 'positive')


def test_free_port_rejects_mistaken_orientation():
    with pytest.raises(ValueError, match='xmin'):
        _capture('create_waveguide_port_free', 1, xrange=('0', 'a'),
                 orientation='negative')


def test_unknown_orientation_raises():
    with pytest.raises(ValueError, match='不认识'):
        check_port_orientation('towards_the_device')


def test_non_string_orientation_raises():
    with pytest.raises(ValueError):
        check_port_orientation(1)


# ============================================================
# ③ 不传朝向 ⇒ 不下发该行 + 告警（既有代码行为不变）
# ============================================================

def test_none_orientation_warns_and_omits_the_line():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        vba = _capture('add_port', 1)
    assert '.Orientation' not in vba
    assert '.Coordinates "Picks"' in vba            # 其余端口定义照旧
    assert len(caught) == 1 and issubclass(caught[0].category, UserWarning)
    assert 'orientation' in str(caught[0].message).lower()


def test_none_orientation_on_free_port_also_warns_and_omits():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        vba = _capture('create_waveguide_port_free', 1, zrange=('0', 'h'))
    assert '.Orientation' not in vba
    assert '.Zrange 0, h' in vba
    assert len(caught) == 1


def test_omitted_line_keeps_the_rest_of_the_block_intact():
    """不下发该行时，VBA 其余部分必须与有该行时**只差那一行**。"""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        without = _capture('add_port', 1)
    with_line = _capture('add_port', 1, 'xmin')
    assert without.splitlines() == [l for l in with_line.splitlines()
                                    if '.Orientation' not in l]


# ============================================================
# 离线契约（vba_specs.PortSpec）
# ============================================================

def test_portspec_accepts_legal_orientation():
    assert vba_specs.PortSpec('waveguide', number=1,
                              orientation='xmin').validate() is not None


def test_portspec_rejects_mistaken_orientation():
    with pytest.raises(ValueError, match='unsupported port orientation'):
        vba_specs.PortSpec('waveguide', number=1,
                           orientation='positive').validate()


def test_portspec_still_requires_orientation_for_waveguide():
    with pytest.raises(ValueError, match='orientation is required'):
        vba_specs.PortSpec('waveguide', number=1).validate()
