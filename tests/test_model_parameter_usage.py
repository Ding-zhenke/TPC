# -*- coding: utf-8 -*-
r"""
`scripts/verify_model_parameter_usage.py` 的离线自检
===================================================

这个脚本是 2026-09-17 V1 真机取证挖出缺陷后补的「参数表 ↔ 建模历史」闭合性检查，
它自己的判据必须钉住，否则很容易在后续改动里退化成一片假绿/假红。本文件用
**合成工程**（手写 `Parameters.json` + `ModelHistory.json`）覆盖每一条判据：

=========================  ============================================  ========
场景                        期望                                          状态
=========================  ============================================  ========
在用公式引用未定义名字      `A 表达式闭合` 报 FAIL                               FAIL
死参数的坏公式              `A 表达式闭合` 报 WARN（CST 实测容忍）               WARN
公式求值为空                `A2 参数求值` 报 WARN 并点名                        WARN
库写过的常量没人引用        `C 未引用分类` 报 FAIL（死写入）                    FAIL
值与模板一致的未引用常量    算「模板遗留」，不算死写入                          INFO
常量参数 expr = 数字文本    **不能**被当成公式（CST 的存储约定）                  —
`.Xmax` vs 参数 `xmax`     大小写敏感 ⇒ `xmax` 仍算「未被引用」               —
`--no-template`            不判死写入，只给样例                                UNKNOWN
=========================  ============================================  ========

运行方式::

    pytest tests/test_model_parameter_usage.py -v
"""

import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_SCRIPTS = os.path.join(ROOT, 'scripts')
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)


def _load_module():
    path = os.path.join(_SCRIPTS, 'verify_model_parameter_usage.py')
    spec = importlib.util.spec_from_file_location('verify_model_parameter_usage',
                                                  path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def checker():
    return _load_module()


def _write_project(root, name, params, history):
    """写一个合成的文件夹形式工程：`<name>/Model/Parameters.json` + 历史。"""
    project = os.path.join(root, name)
    model = os.path.join(project, 'Model')
    history_dir = os.path.join(model, '3D')
    os.makedirs(history_dir, exist_ok=True)
    with open(os.path.join(model, 'Parameters.json'), 'w', encoding='utf-8') as fh:
        json.dump({'version': 1, 'parameters': params}, fh, ensure_ascii=False)
    with open(os.path.join(history_dir, 'ModelHistory.json'), 'w',
              encoding='utf-8') as fh:
        json.dump(history, fh, ensure_ascii=False)
    return project


def _param(name, value, expr=None):
    if expr is None:
        expr = str(value)
    return {'name': name, 'value': value, 'expr': expr}


def _load_table(checker, project):
    table, _ = checker._load_parameters(project)
    return table


def _status(checker, marker):
    """取「item 里含 marker」那条结论的状态（item 形如 `<工程> A 表达式闭合`）。"""
    hits = [r for r in checker._results if marker in r['item']]
    assert hits, f'没有找到含 {marker!r} 的结论：' \
                 f'{[r["item"] for r in checker._results]}'
    return hits[0]['status']


# --- 参数表解析：expr 是表达式原文，不是描述 ---------------------------------

def test_constant_param_is_not_a_formula(checker, tmp_path):
    """常量参数的 expr 就是它自己的数字文本 ⇒ `is_formula` 必须为 False。"""
    project = _write_project(str(tmp_path), 'p1',
                             [_param('xup', 25), _param('p1x', -0.2425, '-a')],
                             {'commands': ['.Repetitions "int(xup)"']})
    table = _load_table(checker, project)
    assert table['xup']['is_formula'] is False
    assert table['p1x']['is_formula'] is True


def test_missing_value_is_flagged(checker, tmp_path):
    """`value` 为空串 = CST 求值失败的指纹（模板自带 `N=(y0+4)*2`）。"""
    project = _write_project(str(tmp_path), 'p2',
                             [_param('N', '', '(y0+4)*2')],
                             {'commands': ['.Repetitions "1"']})
    table = _load_table(checker, project)
    assert table['N']['value_missing'] is True
    assert table['N']['is_formula'] is True


# --- A：公式闭合的严重度分流 ------------------------------------------------

def test_undefined_reference_in_used_formula_fails(checker, tmp_path):
    """在用的公式引用未定义名字 ⇒ FAIL。"""
    project = _write_project(
        str(tmp_path), 'used_bad',
        [_param('a', 1.0), _param('b', 2.0, 'a+c')],
        {'commands': ['.Xrange "0", "b"']})          # b 被引用 ⇒ 在用
    result = checker.audit_project(project)
    statuses = {r['item'].split()[-1]: r['status'] for r in checker._results}
    assert result['undefined_refs'] == {'b': ['c']}
    assert _status(checker, '表达式闭合') == 'FAIL'


def test_undefined_reference_in_dead_formula_warns(checker, tmp_path):
    """死参数里的坏公式 ⇒ WARN（CST 实测容忍，模板自带这种）。"""
    checker._results.clear()
    project = _write_project(
        str(tmp_path), 'dead_bad',
        [_param('a', 1.0), _param('N', '', '(y0+4)*2')],
        {'commands': ['.Xrange "0", "a"']})
    result = checker.audit_project(project)
    statuses = {r['item'].split()[-1]: r['status'] for r in checker._results}
    assert result['dead_undefined_exprs'] == {'N': ['y0']}
    assert _status(checker, '表达式闭合') == 'WARN'
    assert _status(checker, '参数求值') == 'WARN'


def test_cst_builtin_functions_are_not_undefined_names(checker, tmp_path):
    """`sqr/int/sind` 是 CST 内置函数，不能当成未定义参数。"""
    checker._results.clear()
    project = _write_project(
        str(tmp_path), 'builtins',
        [_param('a', 1.0), _param('e2', 0.21, 'sqr(3)/2*a'),
         _param('xup', 25, 'int(2*a)+sind(60)')],
        {'commands': ['.Repetitions "int(xup)"']})
    result = checker.audit_project(project)
    statuses = {r['item'].split()[-1]: r['status'] for r in checker._results}
    assert result['undefined_refs'] == {}
    assert _status(checker, '表达式闭合') == 'OK'


# --- B/C：引用统计与死写入 --------------------------------------------------

def test_dead_write_detected_by_changed_value(checker, tmp_path):
    """模板里 `xup=37`、本次写成 25、而历史里没人引用 ⇒ 死写入（FAIL）。"""
    checker._results.clear()
    template = _load_table(checker, _write_project(
        str(tmp_path), 'tpl', [_param('xup', 37), _param('a', 1.0)],
        {'commands': ['.Xrange "0","a"']}))
    project = _write_project(
        str(tmp_path), 'built',
        [_param('xup', 25), _param('a', 1.0)],
        {'commands': ['.Xrange "0","a"']})           # 只引用 a，不引用 xup
    result = checker.audit_project(project, template)
    statuses = {r['item'].split()[-1]: r['status'] for r in checker._results}
    assert result['dead_writes'] == ['xup']
    assert _status(checker, '未引用分类') == 'FAIL'


def test_legacy_param_same_value_is_not_a_dead_write(checker, tmp_path):
    """值与模板逐字一致的未引用常量 ⇒ 模板遗留（INFO），不是死写入。"""
    checker._results.clear()
    template = _load_table(checker, _write_project(
        str(tmp_path), 'tpl2', [_param('cell_h0', -0.25), _param('a', 1.0)],
        {'commands': ['.Xrange "0","a"']}))
    project = _write_project(
        str(tmp_path), 'built2',
        [_param('cell_h0', -0.25), _param('a', 1.0)],
        {'commands': ['.Xrange "0","a"']})
    result = checker.audit_project(project, template)
    statuses = {r['item'].split()[-1]: r['status'] for r in checker._results}
    assert result['dead_writes'] == []
    assert _status(checker, '未引用分类') == 'INFO'


def test_numeric_equivalence_is_not_a_rewrite(checker, tmp_path):
    """`3` vs `3.0` 是同一个值：不能误判成「被重写过」。"""
    checker._results.clear()
    template = _load_table(checker, _write_project(
        str(tmp_path), 'tpl3', [_param('lf2', 3), _param('a', 1.0)],
        {'commands': ['.Xrange "0","a"']}))
    project = _write_project(
        str(tmp_path), 'built3',
        [_param('lf2', 3.0), _param('a', 1.0)],
        {'commands': ['.Xrange "0","a"']})
    result = checker.audit_project(project, template)
    assert result['dead_writes'] == []


def test_new_param_never_referenced_is_a_dead_write(checker, tmp_path):
    """模板里没有、本次新增、却没人引用 ⇒ 死写入。"""
    checker._results.clear()
    template = _load_table(checker, _write_project(
        str(tmp_path), 'tpl4', [_param('a', 1.0)],
        {'commands': ['.Xrange "0","a"']}))
    project = _write_project(
        str(tmp_path), 'built4',
        [_param('a', 1.0), _param('ghost', 7)],
        {'commands': ['.Xrange "0","a"']})
    result = checker.audit_project(project, template)
    assert result['dead_writes'] == ['ghost']


def test_formula_param_unused_is_not_judged(checker, tmp_path):
    """公式参数的值随输入变，不能拿「值不同」当写过它的证据 ⇒ 单独归类。"""
    checker._results.clear()
    template = _load_table(checker, _write_project(
        str(tmp_path), 'tpl5', [_param('a', 1.0), _param('d', 1.0, '2*a')],
        {'commands': ['.Xrange "0","a"']}))
    project = _write_project(
        str(tmp_path), 'built5',
        [_param('a', 2.0), _param('d', 4.0, '2*a')],
        {'commands': ['.Xrange "0","a"']})
    result = checker.audit_project(project, template)
    assert result['dead_writes'] == []


# --- 大小写敏感 --------------------------------------------------------------

def test_parameter_matching_is_case_sensitive(checker, tmp_path):
    """历史里的 `.Xmax "expanded open"` 是边界设置，不等于参数 `xmax` 被引用。"""
    checker._results.clear()
    template = _load_table(checker, _write_project(
        str(tmp_path), 'tpl6', [_param('xmax', 8.85125)],
        {'commands': ['.Xmax "expanded open"']}))
    project = _write_project(
        str(tmp_path), 'built6',
        [_param('xmax', 8.85125)],
        {'commands': ['.Xmax "expanded open"']})
    result = checker.audit_project(project, template)
    assert 'xmax' in result['unused']


# --- 无模板模式 --------------------------------------------------------------

def test_without_template_dead_writes_are_not_claimed(checker, tmp_path):
    """没给模板 ⇒ 不猜死写入（`classified=False`，状态 UNKNOWN）。"""
    checker._results.clear()
    project = _write_project(
        str(tmp_path), 'no_tpl', [_param('a', 1.0), _param('unused', 5)],
        {'commands': ['.Xrange "0","a"']})
    result = checker.audit_project(project, None)
    statuses = {r['item'].split()[-1]: r['status'] for r in checker._results}
    assert result['classified'] is False
    assert result['dead_writes'] == []
    assert _status(checker, '未引用分类') == 'UNKNOWN'


def test_missing_parameter_table_is_reported(checker, tmp_path):
    """没有参数表 ⇒ FAIL，且不抛异常。"""
    checker._results.clear()
    empty = os.path.join(str(tmp_path), 'empty')
    os.makedirs(empty, exist_ok=True)
    result = checker.audit_project(empty)
    assert result is None
    assert checker._results[-1]['status'] == 'FAIL'


@pytest.fixture(autouse=True)
def _clear_results(checker):
    """每条用例前清掉上一条的结论列表，避免串味。"""
    checker._results.clear()
    yield
    checker._results.clear()
