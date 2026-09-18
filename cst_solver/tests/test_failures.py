# -*- coding: utf-8 -*-
"""
结构化失败通道测试（P1：剩余静默失败审计）
==========================================

守住什么
--------
`docs/next_plan/README.md` P1 第 4 条：材料缺失等旧接口仍可能「记 warning 后返回」，
必须**在兼容现有 API 的前提下**给共用服务提供结构化失败。

本测试钉住三条：

1. 旧行为**一字不变** —— 返回值仍是 ``None`` / ``[]`` / ``False``，
   不抛异常（旧 notebook 兼容）；
2. 同一件事**现在也能被结构化地看见** —— ``collect_failures()`` 能拿到
   ``code/message/details/retryable``；
3. 可选严格模式下**直接抛** ``CstOperationError``（复用同一错误结构）。

另外钉住 `TopoModeler` 在 ``app is None`` 时不再「静默 no-op 却返回成功」。

运行方式::

    pytest cst_solver/tests/test_failures.py -v
"""

import os
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from cst_solver.failures import (          # noqa: E402
    CstOperationError,
    collect_failures,
    failure_strict_enabled,
    recent_failures,
    record_failure,
    reset_failure_state,
    set_failure_strict,
    structured_error,
)


@pytest.fixture(autouse=True)
def _clean_state():
    reset_failure_state()
    previous = set_failure_strict(False)
    yield
    set_failure_strict(previous)
    reset_failure_state()


# ============================================================
# 1. 错误结构与收集器
# ============================================================

def test_structured_error_shape():
    error = structured_error('some_code', '说明', retryable=True, field='a.b')
    assert error == {'code': 'some_code', 'message': '说明',
                     'details': {'field': 'a.b'}, 'retryable': True}
    # 单一实现：其它模块的 _error 也走这里
    from cst_solver.expressions import _error as expr_error
    from cst_solver.run_contract import _error as run_error
    from topo_modeler.preflight import _error as preflight_error
    for helper in (expr_error, run_error, preflight_error):
        assert helper('x', 'y') == structured_error('x', 'y')


def test_collect_failures_gathers_records():
    with collect_failures() as failures:
        record_failure('op_a', 'code_a', '第一条')
        record_failure('op_b', 'code_b', '第二条', retryable=True, field='f')
    assert [f['code'] for f in failures] == ['code_a', 'code_b']
    assert failures[1]['retryable'] is True
    assert failures[1]['details']['operation'] == 'op_b'
    assert failures[1]['details']['field'] == 'f'


def test_nested_collectors_both_see_the_failure():
    with collect_failures() as outer:
        with collect_failures() as inner:
            record_failure('op', 'code', 'msg')
        assert len(inner) == 1
    assert len(outer) == 1 and len(inner) == 1


def test_recent_failures_track_everything():
    record_failure('op', 'code', 'msg')
    assert recent_failures()[0]['code'] == 'code'
    assert recent_failures(clear=True)
    assert recent_failures() == []


def test_strict_mode_raises_structured_error():
    assert failure_strict_enabled() is False
    previous = set_failure_strict(True)
    assert previous is False
    with pytest.raises(CstOperationError) as excinfo:
        record_failure('op', 'code_x', '炸了', retryable=True, material='Gold')
    error = excinfo.value
    assert error.code == 'code_x'
    assert error.operation == 'op'
    assert error.to_dict()['details'] == {'material': 'Gold', 'operation': 'op'}
    assert error.to_dict()['retryable'] is True
    set_failure_strict(False)
    assert record_failure('op', 'code_x', '不炸了')['code'] == 'code_x'


# ============================================================
# 2. 材料接口：旧行为不变，但失败可见
# ============================================================

class _FakeModel3D:
    def __init__(self):
        self.history = []

    def add_to_history(self, caption, vba):
        self.history.append((caption, vba))


class _FakeCstFile:
    def __init__(self):
        self.model3d = _FakeModel3D()


class _MaterialHost:
    """只带 MaterialMixin 的宿主。"""

    def __init__(self):
        from cst_solver.material.materials import MaterialMixin

        class _Host(MaterialMixin):
            pass

        self.__class__ = type('_MaterialHostImpl', (_Host,), {})
        self.cst_file = _FakeCstFile()


def test_new_material_unknown_name_keeps_old_behaviour_but_records():
    host = _MaterialHost()
    with collect_failures() as failures:
        result = host.new_material('Gold')
    assert result is None                       # 旧行为：不抛异常、返回 None
    assert host.cst_file.model3d.history == []  # 什么都没建（和旧版一致）
    assert [f['code'] for f in failures] == ['material_not_preset']
    assert failures[0]['details']['material'] == 'Gold'


def test_new_material_known_name_records_nothing():
    host = _MaterialHost()
    with collect_failures() as failures:
        host.new_material('Silicon (lossy)')
    assert failures == []
    assert host.cst_file.model3d.history[0][0] == 'Silicon (lossy)'


def test_new_material_strict_mode_raises():
    host = _MaterialHost()
    set_failure_strict(True)
    with pytest.raises(CstOperationError) as excinfo:
        host.new_material('Gold')
    assert excinfo.value.code == 'material_not_preset'


def test_get_material_filepath_missing_records(monkeypatch):
    host = _MaterialHost()
    monkeypatch.setattr(host, '_get_material_library_path', lambda: os.getcwd())
    with collect_failures() as failures:
        assert host.get_material_filepath('No Such Material') is None
    assert [f['code'] for f in failures] == ['material_file_missing']


def test_load_material_from_file_missing_records(tmp_path):
    host = _MaterialHost()
    missing = str(tmp_path / 'ghost.mtd')
    with collect_failures() as failures:
        assert host.load_material_from_file(missing) is False
    assert [f['code'] for f in failures] == ['material_file_not_found']


def test_load_material_from_file_empty_definition_records(tmp_path):
    host = _MaterialHost()
    empty = tmp_path / 'empty.mtd'
    empty.write_text('[Definition]\n\n[Other]\n', encoding='utf-8')
    with collect_failures() as failures:
        assert host.load_material_from_file(str(empty)) is False
    assert [f['code'] for f in failures] == ['material_definition_empty']


# ============================================================
# 4. 参数入口：校验只记录、不改行为（P1 第 2 条落到最底层）
# ============================================================

class _ParamModel3D:
    def __init__(self):
        self.stored = []
        self.history = []

    def StoreParameter(self, name, value):        # noqa: N802 (CST 接口原名)
        self.stored.append((name, value))

    def StoreParameters(self, names, values):     # noqa: N802
        self.stored.extend(zip(names, values))

    def full_history_rebuild(self):
        self.history.append('rebuild')

    def add_to_history(self, caption, vba):
        self.history.append(caption)


class _ParamHost:
    """只带 ParametersMixin 的宿主。"""

    def __init__(self):
        from cst_solver.parameters import ParametersMixin

        class _Host(ParametersMixin):
            def _guard_param_probe(self, name):
                return False

        self.__class__ = type('_ParamHostImpl', (_Host,), {})
        self.cst_file = type('_Fake', (), {'model3d': _ParamModel3D()})()


def test_para_still_sends_valid_inputs():
    host = _ParamHost()
    with collect_failures() as failures:
        host.para('l1', '0.65*a', expression='BA 型大孔边长')
    assert failures == []
    assert host.cst_file.model3d.stored == [('l1', '0.65*a')]


def test_para_records_bad_expression_without_changing_behaviour():
    """坏表达式照旧下发（旧行为不变），但结构化失败里看得见。"""
    host = _ParamHost()
    with collect_failures() as failures:
        host.para('l1', '0.65*aa +')
    assert host.cst_file.model3d.stored == [('l1', '0.65*aa +')]
    assert [f['code'] for f in failures] == ['expression_syntax_error']
    assert failures[0]['details']['field'] == 'value'


def test_para_records_dangerous_description_text():
    """说明文本里带双引号会破坏 VBA 字面量，必须能看见。"""
    host = _ParamHost()
    with collect_failures() as failures:
        host.para('l1', 1.0, expression='备注"\nRemarks: hacked')
    assert failures[0]['code'] == 'name_forbidden_character'
    assert failures[0]['details']['field'] == 'expression'


def test_para_records_non_identifier_name():
    host = _ParamHost()
    with collect_failures() as failures:
        host.para('bad name', 1.0)
    assert failures[0]['code'] == 'name_not_identifier'


def test_para_strict_mode_raises_on_bad_expression():
    host = _ParamHost()
    set_failure_strict(True)
    with pytest.raises(CstOperationError):
        host.para('l1', '0.65*aa +')


# ============================================================
# 5. TopoModeler：app is None 时不再静默成功
# ============================================================

def _modeler_without_cst(tmp_path):
    from topo_modeler.modeler import TopoModeler
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        modeler = TopoModeler(template_cst=str(tmp_path / 'missing.cst'))
    return modeler


def test_modeler_run_without_cst_raises_structured_error(tmp_path):
    modeler = _modeler_without_cst(tmp_path)
    assert modeler.app is None
    with pytest.raises(CstOperationError) as excinfo:
        modeler.run()
    assert excinfo.value.code == 'cst_unavailable'
    assert excinfo.value.operation == 'TopoModeler.run'


def test_modeler_save_without_cst_raises_and_does_not_lie(tmp_path):
    modeler = _modeler_without_cst(tmp_path)
    with pytest.raises(CstOperationError):
        modeler.save(str(tmp_path / 'out.cst'))
    assert modeler._cst_path is None       # 不能声称「已保存到某路径」


def test_modeler_init_failure_is_visible_in_failure_channel(tmp_path):
    reset_failure_state()
    _modeler_without_cst(tmp_path)
    codes = [f['code'] for f in recent_failures()]
    assert 'cst_unavailable' in codes
