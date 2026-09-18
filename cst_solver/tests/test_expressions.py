# -*- coding: utf-8 -*-
"""
CST 表达式与名称校验测试（P1：表达式和名称校验）
================================================

守住什么
--------
`docs/next_plan/README.md` 的 P1 要求给参数引用、几何名称、材料名和 CST 表达式
加校验，并明确了一句反面要求：

    保留 `a/2`、`sqr(3)` 等合法表达式，**不能**照搬只允许单个参数名的检查器。

所以本测试有**两组**同等重要的用例：

1. **必须放行**：本仓库与真实 notebook 里正在用的表达式与名称
   （`a/2*sqr(3)`、`-lf5-lf6-lf4`、`int(y1/2)`、`Copper (annealed)`、`Port 2` …）——
   误拒会让所有既有 notebook 无法运行；
2. **必须拦下**：参数名写错、语法不完整、引号/换行/分号等注入字符。

运行方式::

    pytest cst_solver/tests/test_expressions.py -v
"""

import os
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from cst_solver.expressions import (          # noqa: E402
    CstExpressionError,
    CstNameError,
    check_expression,
    check_material_name,
    check_name,
    expression_identifiers,
    tokenize,
    validate_expression,
    validate_name,
    validate_parameter_name,
)


# ============================================================
# 1. 真实表达式必须放行
# ============================================================

#: 取自本仓库源码与参考 notebook 的**真实**表达式（逐条都在 CST 里跑通过）
REAL_EXPRESSIONS = (
    '0.2425', '18', '0.25',
    'a/2', 'a/2*sqr(3)', '0.65*a', '0.35*a',
    '18*a', '-a/2', '2*a',
    '-lf5-lf6-lf4', '-lf4', '0',
    'e1+x01*a', 'e2*2', '-e2*2', '-h/2', 'h/2',
    'px1+x1*a', 'py1', 'int(xup)', 'int(yup/2)', 'int(ydn/2)', 'int((y1)/2)',
    '(xup+4)*2', '(x1-y1)*a', '2*2.2*(nrin+lx1)*a',
    'sqr(ec_a^2-ec_b^2)', 'Nx*a2', 'Ny*a2*sind(60)',
    'pi', 'e', 'a^2', '1e-3', '.5', '-.5',
)


@pytest.mark.parametrize('expr', REAL_EXPRESSIONS)
def test_real_expressions_pass(expr):
    """真实表达式必须通过（且返回规范化后的原文）。"""
    assert validate_expression(expr) == expr.strip()
    assert check_expression(expr).ok


def test_parameter_reference_uses_real_table():
    """给出参数表时，真实引用的名字全部能在表里找到。"""
    table = ('a', 'h', 'e1', 'e2', 'l1', 'l2', 'lf4', 'lf5', 'lf6',
             'wf2', 'wg_a', 'wg_b', 'wg_t', 'x0', 'x01', 'xup', 'yup', 'ydn',
             'x1', 'y1', 'px1', 'p2x', 'nrin', 'lx1', 'ec_a', 'ec_b', 'Nx', 'Ny', 'a2')
    for expr in ('0.65*a', 'a/2*sqr(3)', '-lf5-lf6-lf4', 'px1+x1*a',
                 'int(yup/2)', 'sqr(ec_a^2-ec_b^2)'):
        result = check_expression(expr, table)
        assert result.ok, (expr, result.errors)
        assert not result.unknown_parameters


def test_expression_identifiers_split_functions():
    """标识符与函数名要能分开取出。"""
    idents, funcs = expression_identifiers('int(y1/2)+a*sqr(3)')
    assert set(idents) == {'int', 'y1', 'a', 'sqr'}
    assert set(funcs) == {'int', 'sqr'}


def test_whitespace_is_normalized():
    """首尾空白被规范化掉，内部空白不影响结果。"""
    assert validate_expression('  a/2  ') == 'a/2'


# ============================================================
# 2. 非法表达式必须拦下
# ============================================================

@pytest.mark.parametrize('expr', ('', '   ', 'a+', '(a', 'a)', 'a/2*', '()',
                                  'sqr(3', 'a b', '*a', 'a,,b'))
def test_syntax_errors_rejected(expr):
    result = check_expression(expr)
    assert not result.ok, expr
    assert result.errors[0]['code'] in ('expression_empty',
                                       'expression_syntax_error')
    with pytest.raises(CstExpressionError):
        validate_expression(expr)


@pytest.mark.parametrize('expr', ('"a"', "a'", 'a;b', 'a$b', 'a\nb', 'a\rb',
                                  'a`b', 'a\\b'))
def test_forbidden_characters_rejected(expr):
    """引号 / 换行 / 分号等注入字符要有专门错误码。"""
    result = check_expression(expr)
    assert not result.ok
    assert result.errors[0]['code'] == 'expression_forbidden_character'


def test_unknown_parameter_rejected():
    """参数名写错要报出来，并列出当前参数表。"""
    result = check_expression('0.65*aa', ['a', 'l1'])
    assert not result.ok
    assert result.errors[0]['code'] == 'expression_unknown_parameter'
    assert result.unknown_parameters == ('aa',)
    assert 'a, l1' in result.errors[0]['message']


def test_unknown_parameter_not_checked_without_table():
    """没有参数表时只查语法，不做引用检查（离线预检的默认姿势）。"""
    assert check_expression('0.65*aa').ok


def test_case_insensitive_parameter_reference():
    """CST 参数名大小写不敏感，引用不该因此被判错。"""
    assert check_expression('0.65*A', ['a']).ok


def test_unknown_function_allowed_by_default_but_flagable():
    """白名单外的函数默认放行（CST 函数集更大），但可以要求严格。"""
    lenient = check_expression('myfunc(3)')
    assert lenient.ok
    assert lenient.unknown_functions == ('myfunc',)
    strict = check_expression('myfunc(3)', allow_unknown_functions=False)
    assert not strict.ok
    assert strict.errors[0]['code'] == 'expression_unknown_function'


def test_non_string_expression():
    result = check_expression(3.5)
    assert not result.ok
    assert result.errors[0]['code'] == 'expression_not_string'


def test_tokenize_reports_position():
    """词法错误要带位置，方便定位。"""
    with pytest.raises(CstExpressionError) as excinfo:
        tokenize('a#b')
    assert '第 2 个字符' in str(excinfo.value)
    assert excinfo.value.code == 'expression_syntax_error'


# ============================================================
# 3. 名称校验：真实名称放行
# ============================================================

REAL_NAMES = ('wg1', 'wg2', 'wg2_1', 'vpc_A', 'vpc_B', 'g1A', 'g1B',
              'feed1', 'feed2', 'feed2_epc', 'feed2_opt1', 'import_1',
              'Port 1', 'Port 2', 'component1', 'gridlens', 'lens_epc',
              'Copper (annealed)', 'Silicon (lossy)', 'Quartz (Fused) (lossy)',
              '晶体', '直波导BA-18a')


@pytest.mark.parametrize('name', REAL_NAMES)
def test_real_names_pass(name):
    assert validate_name(name) == name
    assert check_name(name).ok


def test_material_names_with_space_and_parens_pass():
    """材料名含空格与括号是合法的 —— 不要拿「标识符规则」去套材料名。"""
    assert check_material_name('Copper (annealed)').ok
    assert check_material_name(
        'Copper (annealed)', known=('Copper (annealed)', 'Silicon (lossy)')).ok


def test_material_unknown_value_rejected():
    result = check_material_name('Gold', known=('Copper (annealed)',))
    assert not result.ok
    assert result.errors[0]['code'] == 'name_unknown_value'


# ============================================================
# 4. 名称校验：非法名称拦下
# ============================================================

@pytest.mark.parametrize('name', ('', '   ', 'a"b', "a'b", 'a\nb', 'a\tb',
                                  'a\\b', 'x' * 200))
def test_bad_names_rejected(name):
    result = check_name(name)
    assert not result.ok, repr(name)
    assert result.errors[0]['code'] in ('name_empty', 'name_forbidden_character',
                                        'name_too_long')
    with pytest.raises(CstNameError):
        validate_name(name)


def test_non_string_name():
    result = check_name(None)
    assert not result.ok
    assert result.errors[0]['code'] == 'name_not_string'


def test_parameter_name_is_identifier():
    """参数名比几何名严格：必须是标识符。"""
    for good in ('a', 'h', 'l1', 'px2', 'HEX_SIZE', '_tmp'):
        assert validate_parameter_name(good) == good
    for bad in ('1a', 'a-1', 'a b', 'a.b', '参数'):
        with pytest.raises(CstNameError):
            validate_parameter_name(bad)


def test_name_kind_and_structure():
    """结构化结果要带上 kind 与规范化后的名字。"""
    result = check_name('  wg2  ', kind='geometry')
    assert result.ok
    assert result.name == 'wg2'
    assert result.kind == 'geometry'
    assert result.warnings, '首尾空白应给一条 warning'
    assert result.to_dict()['name'] == 'wg2'
