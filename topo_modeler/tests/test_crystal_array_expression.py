# -*- coding: utf-8 -*-
r"""
晶体阵列「参数引用 vs 烘数值」回归测试
======================================

守住什么
--------
2026-09-17 真机取证（`ant_AB_120` 的 `ModelHistory.json`，见
`docs/validation/p4_real_machine_evidence.md` §8.7）发现：

* 参考工程 `Ant1_D_AB_120_Feed_antenna-DF` 的历史里是
  ``"int(xup)"`` / ``"int(yup/2)"`` / ``"int(ydn/2)"`` —— **引用 CST 参数**；
* 本库当时是 ``"int(25)"`` / ``"int(14/2)"`` / ``"int(14/2)"`` —— f-string
  把 Python 值烘成了数字，于是整份历史里 `xup|yup|ydn` 出现 **0 次**：
  参数表里的阵列范围**形同备注**，在 CST 里改它不动几何。

`topo_modeler/builders/crystal.py::repeat_expression` 现在按入参类型分流：

=========================  ==================  ==================
入参                        产物                语义
=========================  ==================  ==================
``'xup'``（str）            ``int(xup)``        引用 CST 参数（模板走这条）
``25``（int，旧行为）        ``int(25)``         烘成数值（字节级兼容）
``('yup', 2)``              ``int(yup/2)``      引用参数 + 分母
``(14, 2)``（旧行为）        ``int(14/2)``       烘成数值 + 分母
=========================  ==================  ==================

运行方式::

    pytest topo_modeler/tests/test_crystal_array_expression.py -v
"""

import inspect
import os
import re
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from topo_modeler.builders.crystal import (      # noqa: E402
    build_topological_crystal, repeat_expression)


class _FakeApp:
    """只记录 `translate` 的 repetitions，够验证阵列表达式。"""

    def __init__(self):
        self.repetitions = []
        self.calls = []

    def triangle(self, *args, **kwargs):
        self.calls.append(('triangle', args, kwargs))

    def add(self, *args, **kwargs):
        self.calls.append(('add', args, kwargs))

    def subtract(self, *args, **kwargs):
        self.calls.append(('subtract', args, kwargs))

    def rotation(self, *args, **kwargs):
        self.calls.append(('rotation', args, kwargs))

    def translate(self, name, vector, repetitions=None, **kwargs):
        self.repetitions.append(repetitions)
        self.calls.append(('translate', (name, vector), kwargs))


class _FakePath:
    """最小路径替身：`None` 分支才会用到 `get_array_range()`。"""

    def get_array_range(self):
        return (7, 8, 9)


# --- 1. 表达式分支本身 ---------------------------------------------------

@pytest.mark.parametrize('value, divisor, want', [
    ('xup', 1, 'int(xup)'),          # 参数名：X 方向
    ('yup', 2, 'int(yup/2)'),        # 参数名：Y+/Y- 方向（含分母）
    ('ydn', 2, 'int(ydn/2)'),
    (25, 1, 'int(25)'),              # 旧行为：数字
    (14, 2, 'int(14/2)'),
    (0, 2, 'int(0/2)'),              # 不做整除，交给 CST 求值（保留旧写法）
])
def test_repeat_expression_branches(value, divisor, want):
    """str ⇒ 参数引用；数字 ⇒ 烘数值（旧行为不变）。"""
    assert repeat_expression(value, divisor) == want


def test_repeat_expression_string_is_not_quoted_away():
    """参数名必须**不加引号**地进入 CST 表达式，否则 CST 会当字符串常量。"""
    expr = repeat_expression('xup')
    assert expr == 'int(xup)'
    assert "'" not in expr and '"' not in expr


# --- 2. 构建器行为：三个方向的复制都要走参数引用 -------------------------

def test_builder_emits_parameter_references():
    """传参数名：X/Y+/Y- 三个方向的 repetitions 全是 CST 参数引用。"""
    app = _FakeApp()
    build_topological_crystal(app, _FakePath(), topology='AB',
                              xup='xup', yup='yup', ydn='ydn')
    # 两个晶体（A/B）各 3 次 translate，顺序固定：X → Y+ → Y-
    assert app.repetitions == ['int(xup)', 'int(yup/2)', 'int(ydn/2)'] * 2


def test_builder_keeps_numeric_behaviour():
    """传数字：与改动前逐字节一致（``int(25)`` / ``int(14/2)``）。"""
    app = _FakeApp()
    build_topological_crystal(app, _FakePath(), topology='AB',
                              xup=25, yup=14, ydn=14)
    assert app.repetitions == ['int(25)', 'int(14/2)', 'int(14/2)'] * 2


def test_builder_falls_back_to_path_array_range():
    """`None` 仍回退到路径推断（旧默认路径，不受本次改动影响）。"""
    app = _FakeApp()
    build_topological_crystal(app, _FakePath(), topology='AB')
    assert app.repetitions == ['int(7)', 'int(8/2)', 'int(9/2)'] * 2


# --- 3. 模板接线：必须真的把参数名传下去（防止回退） ---------------------

_NAMES = re.compile(r"xup\s*=\s*'xup'|xup\s*=\s*\"xup\"")
_NUMERIC = re.compile(r"xup\s*=\s*self\.xup")


@pytest.mark.parametrize('module_name, class_name', [
    ('topo_templates.unit_antenna', 'UnitAntenna'),
    ('topo_templates.straight_waveguide', 'StraightWaveguide'),
])
def test_template_passes_parameter_names(module_name, class_name):
    """模板 `build_all()` 必须传 `xup='xup'` 这类参数名，而不是 `self.xup` 数值。

    这里查源码而不是跑构建：模板 `build_all()` 需要真 CST 会话才能执行，
    离线只能查接线；真机确认见 `scripts/verify_antenna_mapping.py`
    （同一次会话里核对历史里是否出现 `int(xup)`）。
    """
    import importlib

    module = importlib.import_module(module_name)
    source = inspect.getsource(getattr(module, class_name).build_all)
    assert _NAMES.search(source), f'{class_name}.build_all 没有传参数名 xup'
    assert not _NUMERIC.search(source), (
        f'{class_name}.build_all 又退回传数值 self.xup（阵列将不随参数变）')
