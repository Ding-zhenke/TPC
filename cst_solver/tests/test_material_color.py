# -*- coding: utf-8 -*-
"""
create_material_custom() 颜色参数单元测试
=========================================

离线用例（假 CST 对象），验证：

* 不传颜色时 VBA **与旧版完全一致**（向后兼容）
* 三种颜色写法都能归一化成 CST 的 ``.Colour "r", "g", "b"``
* ``color`` / ``colour`` 拼写别名
* 非法输入抛 ``ValueError``（不静默写错颜色）
* 与 ``tand`` / ``material_type`` 共存，且 ``.Colour`` 必须在 ``.Create`` 之前

⚠️ 本文件不替代真机冒烟：颜色最终由 CST 渲染，需在真机上确认
「消息为空 + Rebuild 后仍为空」（见开发宪法 §7）。

@author: PC
"""

import os
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from cst_solver.material.materials import MaterialMixin              # noqa: E402


# ============================================================
# 假 CST 对象（只实现本条子用到的 add_to_history）
# ============================================================

class _FakeModel3D:
    def __init__(self):
        self.history = []          # [(label, vba), ...]

    def add_to_history(self, label, vba):
        self.history.append((str(label), str(vba)))


class _FakeCstFile:
    def __init__(self):
        self.model3d = _FakeModel3D()


class _App(MaterialMixin):
    def __init__(self):
        self.cst_file = _FakeCstFile()


def _make(**kwargs):
    """建一个自定义材料，返回 (app, label, vba)。"""
    app = _App()
    app.create_material_custom('mTest', 11.9, 1, 0, **kwargs)
    label, vba = app.cst_file.model3d.history[-1]
    return label, vba


# ============================================================
# 向后兼容
# ============================================================

def test_no_color_matches_legacy_vba():
    label, vba = _make()
    assert '.Colour' not in vba
    assert '.Epsilon "11.9"' in vba
    assert '.Kappa "0"' in vba
    assert vba.rstrip().endswith('End With')
    # 历史标签必须保持旧值（旧工程历史里有同名条目，改了会让对比历史失配）
    assert label == 'Material: mTest'


# ============================================================
# 三种颜色写法
# ============================================================

def test_color_float_tuple():
    _, vba = _make(color=(0.3, 0.75, 0.35))
    assert '.Colour "0.3", "0.75", "0.35"' in vba


def test_color_hex_string():
    _, vba = _make(color='#4EC9B0')
    assert '.Colour "0.305882", "0.788235", "0.690196"' in vba


def test_color_int_tuple_equivalent_to_hex():
    _, a = _make(color=(78, 201, 176))
    _, b = _make(color='#4EC9B0')
    assert a == b


def test_color_short_hex_and_no_hash():
    assert '.Colour "1", "0", "0"' in _make(color='#f00')[1]
    assert '.Colour "1", "0", "0"' in _make(color='FF0000')[1]


def test_colour_british_alias():
    assert '.Colour "0", "1", "0"' in _make(colour=(0, 1, 0))[1]


def test_list_input_accepted():
    assert '.Colour "0.2", "0.4", "0.6"' in _make(color=[0.2, 0.4, 0.6])[1]


# ============================================================
# 与其它参数共存 + VBA 结构
# ============================================================

def test_color_with_tand_and_material_type():
    _, vba = _make(tand=0.01, material_type='Lossy metal', color='#00ff00')
    assert '.TanD "0.01"' in vba
    assert '.TanDGiven "True"' in vba
    assert '.Type "Lossy metal"' in vba
    assert '.Colour "0", "1", "0"' in vba
    # .Colour 必须在 .Create 之前（CST 要求颜色在建材料时给定）
    assert vba.index('.Colour') < vba.index('.Create')
    assert vba.count('.Create') == 1


def test_unknown_material_type_still_passed_through():
    """material_type 是自由字符串（旧行为），不因新增参数而加校验。"""
    _, vba = _make(material_type='Normal', color=(0, 0, 0))
    assert '.Type "Normal"' in vba
    assert '.Colour "0", "0", "0"' in vba


# ============================================================
# 非法输入：必须报错，不静默
# ============================================================

@pytest.mark.parametrize('bad', [
    (1, 2),                    # 分量数不对
    (1, 2, 3, 4),
    '#12345',                  # 十六进制位数不对
    'xyz',                     # 非十六进制
    (0.5, 0.5, 300),           # 超 0~255
    (-1, 0, 0),                # 负值
    (float('nan'), 0, 0),      # NaN
    (float('inf'), 0, 0),      # Inf
    ('a', 'b', 'c'),           # 分量不是数值
    {'r': 1},                  # 类型不支持
    123,                       # 类型不支持
])
def test_bad_color_raises_value_error(bad):
    with pytest.raises(ValueError):
        _make(color=bad)


def test_both_color_and_colour_raise():
    with pytest.raises(ValueError, match='只能给一个'):
        _make(color=(1, 0, 0), colour=(0, 1, 0))


def test_error_message_is_actionable():
    """报错信息里要能看出「支持什么写法」，便于用户自查。"""
    with pytest.raises(ValueError, match='RRGGBB'):
        _make(color='#zzzzzz')
