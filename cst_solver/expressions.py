# -*- coding: utf-8 -*-
r"""
CST 表达式与名称校验（P1）
==========================

为什么需要
----------
CST 的建模调用最终都会拼成 VBA 字符串下发，例如::

    app.para('l1', '0.65*a')
    app.square('-lf5-lf6-lf4', '-lf4', ..., name='wg2')

在此之前这些字符串**只检查了类型**（是不是 ``str``），没有任何语法或引用检查：

* 参数名写错（``'0.65*aa'``）在 Python 侧完全无声，要等 CST 在消息队列里
  悄悄写一条 ``Unable to evaluate expression``；
* 名称里带引号或换行会**破坏 VBA 语句**（属于注入面）；
* 反过来，最容易犯的错是**校验写得过严** —— 只允许单个参数名，
  于是 ``a/2``、``a/2*sqr(3)``、``int(y1/2)``、``0.65*a`` 这些**完全合法**
  的 CST 表达式被误拒。本模块的语法覆盖就是按这个反面要求设计的。

本模块**完全离线**：不导入 CST、不创建设计环境、不需要配置文件。
MCP 写入口、`topo_modeler.config` 的预检以及底层 ``para()`` 都复用它。

三层接口
--------
1. :func:`check_expression` / :func:`check_name` —— 返回结构化结论
   （``ok`` + ``errors[{code, message, details, retryable}]``），供 MCP 直接回给客户端；
2. :func:`validate_expression` / :func:`validate_name` —— 同上，非法即抛
   :class:`CstExpressionError` / :class:`CstNameError`，供库内部使用；
3. :func:`tokenize` / :func:`parse_expression` —— 需要自己遍历语法树时使用。

语法范围（与 CST 数值表达式一致）
---------------------------------
四则运算 ``+ - * /``、幂 ``^``、括号、一元正负号、数值字面量
（``18``、``.5``、``0.65``、``1e-3``）、常量 ``pi`` / ``e``，
以及白名单函数 ``sqr``/``sqrt``/``sin``/``int``/``min``/``max`` …。
``sqr(3)`` 是 CST 的平方根写法（**不是** Python 的 ``sqrt``），两者都在白名单里。

名称校验的口径
--------------
只拦截**真正会破坏 VBA 或 CST 解析**的东西：引号、换行、控制字符、空名、
超长名。**不**因为名字里有括号、空格或中文就拒绝 ——
``Copper (annealed)``、``Silicon (lossy)``、``vpc_A``、``Port 2`` 都合法。

@author: PC
"""

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    'CstExpressionError',
    'CstNameError',
    'ExpressionCheck',
    'NameCheck',
    'KNOWN_FUNCTIONS',
    'KNOWN_CONSTANTS',
    'MAX_NAME_LENGTH',
    'EXPRESSION_ERROR_CODES',
    'tokenize',
    'parse_expression',
    'expression_identifiers',
    'check_expression',
    'validate_expression',
    'check_name',
    'validate_name',
    'check_path',
    'validate_path',
    'validate_parameter_name',
    'check_material_name',
    'validate_material_name',
    'check_vba_text',
    'validate_vba_text',
]

#: 本模块可能产出的错误码（表达式 / 名称 / 路径 / VBA 文本四类）。
#: 一致性检查（`scripts/check_api_consistency.py` 的 `error-codes` 项）要求
#: **代码里用到的码必须出现在某个 `*_ERROR_CODES` 表里**，这张表就是本模块的来源。
EXPRESSION_ERROR_CODES = (
    'expression_empty',                # 空表达式
    'expression_not_string',           # 不是字符串
    'expression_syntax_error',         # 括号/运算符语法错
    'expression_forbidden_character',  # 含注入字符（引号、反斜杠、分号…）
    'expression_unknown_function',     # 用了不在白名单里的函数
    'expression_unknown_parameter',    # 引用了未定义的参数
    'name_empty',
    'name_not_string',
    'name_not_identifier',
    'name_forbidden_character',
    'name_too_long',
    'name_unknown_value',              # 枚举取值不在允许集合里
)


# ============================================================
# 异常
# ============================================================

class CstExpressionError(ValueError):
    """
    CST 表达式非法（空、语法错、引用了不存在的参数、含注入字符）。

    :param code: str, 机器可读错误码（``expression_syntax_error`` /
        ``expression_forbidden_character`` / ``expression_empty`` …），
        与结构化结果里的 ``errors[0]['code']`` 一致
    """

    def __init__(self, message, code: str = 'expression_syntax_error'):
        super().__init__(message)
        self.code = code


class CstNameError(ValueError):
    """CST 名称非法（空、超长、含引号/换行/控制字符、参数名不是标识符）。"""


# ============================================================
# 白名单：函数与常量
# ============================================================

#: CST 表达式里允许的函数名（**小写**比较；CST 本身大小写不敏感）。
#: 取的是 CST/VBA 常见数学函数；不在表里的函数名默认**不报错**，
#: 只在结构化结果里记进 ``unknown_functions``（见 ``allow_unknown_functions``），
#: 这样不会因为 CST 新增函数而误拒既有 notebook。
KNOWN_FUNCTIONS = frozenset({
    'abs', 'sgn', 'sign', 'sqr', 'sqrt', 'pow', 'exp', 'log', 'ln', 'log10', 'log2',
    'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'atan2',
    'sind', 'cosd', 'tand', 'asind', 'acosd', 'atand',
    'sinh', 'cosh', 'tanh', 'asinh', 'acosh', 'atanh',
    'int', 'fix', 'round', 'floor', 'ceil', 'trunc',
    'min', 'max', 'mod', 'deg', 'rad',
})

#: 常量名（同样小写比较）。参数表里存在同名参数时**参数优先**。
KNOWN_CONSTANTS = frozenset({'pi', 'e'})

#: 表达式里出现即判定为「注入/非法」的字符（不只是语法错）。
_FORBIDDEN_EXPR_CHARS = {
    '"': '双引号会把后面的内容挤出 VBA 字符串字面量',
    "'": '单引号在 VBA 里是注释起始符，会截断语句',
    '\n': '换行会截断 VBA 语句',
    '\r': '回车会截断 VBA 语句',
    ';': '分号在 VBA 里是语句分隔符',
    '$': '美元符号是 VBA 类型后缀',
    '`': '反引号不是合法表达式字符',
    '\\': '反斜杠不是合法表达式字符',
}

#: 名称里出现即判非法的字符 —— **只拦真正会破坏 VBA 的**
_FORBIDDEN_NAME_CHARS = {
    '"': '双引号会破坏 VBA 字符串字面量',
    "'": '单引号在 VBA 里是注释起始符',
    '\n': '换行会截断 VBA 语句',
    '\r': '回车会截断 VBA 语句',
    '\t': '制表符会破坏 CST 名称解析',
    '\\': '反斜杠不是合法名称字符',
}

#: 路径里出现即判非法的字符。
#: 与名称的区别：**反斜杠与冒号合法**（``D:\out\x.cst`` 是正常路径），
#: 只有真正会破坏 VBA 字面量的字符才拦。
_FORBIDDEN_PATH_CHARS = {
    '"': '双引号会破坏 VBA 字符串字面量',
    "'": '单引号在 VBA 里是注释起始符',
    '\n': '换行会截断 VBA 语句',
    '\r': '回车会截断 VBA 语句',
    '\t': '制表符会破坏路径解析',
    '\x00': '空字符不是合法路径字符',
}

#: 会拼进 **VBA 字符串字面量内部** 的自由文本（如参数说明）。
#: 这里比名称宽松得多，因为文本就在一对引号里面：单引号、反斜杠、制表符、
#: 中文、空格都是安全的；能逃出引号的只有双引号与换行。
_FORBIDDEN_TEXT_CHARS = {
    '"': '双引号会提前闭合 VBA 字符串字面量',
    '\n': '换行会截断 VBA 语句',
    '\r': '回车会截断 VBA 语句',
}

#: 名称长度上限（CST 自身没有明确上限，这里取一个宽松但有限的值）
MAX_NAME_LENGTH = 128

#: 参数名必须是标识符：字母或下划线开头，后接字母/数字/下划线
_PARAMETER_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z_0-9]*$')


# ============================================================
# 结构化结果
# ============================================================

@dataclass(frozen=True)
class ExpressionCheck:
    """
    一次表达式校验的结构化结论（可 JSON 序列化）。

    :param ok: bool, 是否通过
    :param expression: str, 原表达式（去首尾空白后）
    :param identifiers: tuple, 出现的所有标识符（含参数引用与函数名）
    :param functions: tuple, 被当函数调用的名字
    :param unknown_parameters: tuple, 参数表里查不到的引用
    :param unknown_functions: tuple, 不在 :data:`KNOWN_FUNCTIONS` 里的函数名
    :param errors: tuple[dict], 每条含 ``code/message/details/retryable``
    :param warnings: tuple[str], 不阻断但需注意的说明
    """

    ok: bool
    expression: str = ''
    identifiers: Tuple[str, ...] = ()
    functions: Tuple[str, ...] = ()
    unknown_parameters: Tuple[str, ...] = ()
    unknown_functions: Tuple[str, ...] = ()
    errors: Tuple[Dict, ...] = ()
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> Dict:
        """JSON 友好字典。"""
        return {
            'ok': self.ok,
            'expression': self.expression,
            'identifiers': list(self.identifiers),
            'functions': list(self.functions),
            'unknown_parameters': list(self.unknown_parameters),
            'unknown_functions': list(self.unknown_functions),
            'errors': [dict(e) for e in self.errors],
            'warnings': list(self.warnings),
        }


@dataclass(frozen=True)
class NameCheck:
    """
    一次名称校验的结构化结论。

    :param ok: bool, 是否通过
    :param name: str, 规范化后的名称（已去首尾空白）
    :param kind: str, ``'geometry'`` / ``'parameter'`` / ``'material'`` / ``'component'`` / ``'text'``
    :param value: str, 规范化后的值（与 ``name`` 相同，便于统一取值）
    :param errors: tuple[dict], 同 :class:`ExpressionCheck`
    :param warnings: tuple[str]
    """

    ok: bool
    name: str = ''
    kind: str = 'geometry'
    errors: Tuple[Dict, ...] = ()
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> Dict:
        """JSON 友好字典。"""
        return {
            'ok': self.ok,
            'name': self.name,
            'kind': self.kind,
            'errors': [dict(e) for e in self.errors],
            'warnings': list(self.warnings),
        }


def _error(code: str, message: str, *, retryable: bool = False, **details) -> Dict:
    """统一错误结构（唯一实现在 ``cst_solver.failures.structured_error``）。"""
    from cst_solver.failures import structured_error
    return structured_error(code, message, retryable=retryable, **details)


# ============================================================
# 词法分析
# ============================================================

#: 词法规则：空白 / 数值 / 标识符 / 运算符
#: 标识符允许 Unicode 字母（CST 参数名一般是 ASCII，但不该因此拒绝中文名）
_TOKEN_RE = re.compile(r"""
    (?P<space>\s+)
  | (?P<number>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)
  | (?P<ident>[^\W\d]\w*)
  | (?P<op>[+\-*/^(),])
""", re.VERBOSE | re.UNICODE)

_TOKEN_TYPES = ('number', 'ident', 'op')


def tokenize(expression: str) -> List[Tuple[str, str, int]]:
    """
    把表达式切成 ``[(kind, text, position), ...]``。

    :param expression: str, 表达式
    :return: list[tuple[str, str, int]], ``kind`` ∈ ``number`` / ``ident`` / ``op``
    :raises CstExpressionError: 含非法字符
    """
    if not isinstance(expression, str):
        raise CstExpressionError(
            f'表达式应为字符串，收到 {type(expression).__name__}')
    tokens: List[Tuple[str, str, int]] = []
    pos = 0
    length = len(expression)
    while pos < length:
        ch = expression[pos]
        if ch in _FORBIDDEN_EXPR_CHARS:
            raise CstExpressionError(
                f'表达式第 {pos + 1} 个字符 {ch!r} 非法：'
                f'{_FORBIDDEN_EXPR_CHARS[ch]}',
                code='expression_forbidden_character')
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            raise CstExpressionError(
                f'表达式第 {pos + 1} 个字符是控制字符（0x{ord(ch):02X}），非法',
                code='expression_forbidden_character')
        match = _TOKEN_RE.match(expression, pos)
        if match is None or match.end() == pos:
            raise CstExpressionError(
                f'表达式第 {pos + 1} 个字符 {ch!r} 不是合法字符；'
                f'合法字符为数字、字母、下划线、``+ - * / ^ ( ) ,``')
        for kind in _TOKEN_TYPES:
            if match.group(kind) is not None:
                tokens.append((kind, match.group(kind), pos))
                break
        pos = match.end()
    return tokens


# ============================================================
# 语法分析（递归下降）
# ============================================================

class _Parser:
    """把 token 流解析成表达式；只做校验与标识符收集，不计算结果。"""

    def __init__(self, tokens: Sequence[Tuple[str, str, int]]):
        self.tokens = list(tokens)
        self.index = 0
        self.identifiers: List[str] = []
        self.functions: List[str] = []
        self.calls: List[bool] = []          # 与 identifiers 等长：该标识符是否被调用

    # ---- 基础 ----

    def _peek(self) -> Optional[Tuple[str, str, int]]:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def _next(self) -> Optional[Tuple[str, str, int]]:
        token = self._peek()
        if token is not None:
            self.index += 1
        return token

    def _expect_op(self, op: str):
        token = self._peek()
        if token is None:
            raise CstExpressionError(f'表达式在结尾处缺少 {op!r}（括号不配平？）')
        if token[0] != 'op' or token[1] != op:
            raise CstExpressionError(
                f'表达式第 {token[2] + 1} 个字符处应为 {op!r}，'
                f'实际是 {token[1]!r}')
        self.index += 1

    # ---- 文法 ----

    def parse(self):
        """``expr`` 后必须到达结尾。"""
        self._expression()
        token = self._peek()
        if token is not None:
            raise CstExpressionError(
                f'表达式第 {token[2] + 1} 个字符处出现多余的 {token[1]!r}'
                f'（表达式在它之前已经完整）')

    def _expression(self):
        self._term()
        while True:
            token = self._peek()
            if token is not None and token[0] == 'op' and token[1] in '+-':
                self.index += 1
                self._term()
            else:
                return

    def _term(self):
        self._power()
        while True:
            token = self._peek()
            if token is not None and token[0] == 'op' and token[1] in '*/':
                self.index += 1
                self._power()
            else:
                return

    def _power(self):
        self._unary()
        token = self._peek()
        if token is not None and token[0] == 'op' and token[1] == '^':
            self.index += 1
            self._unary()                    # 右结合：a^b^c 视为 a^(b^c)

    def _unary(self):
        token = self._peek()
        while token is not None and token[0] == 'op' and token[1] in '+-':
            self.index += 1
            token = self._peek()
        self._primary()

    def _primary(self):
        token = self._next()
        if token is None:
            raise CstExpressionError('表达式不完整（缺少数值、参数名或括号）')
        kind, text, pos = token
        if kind == 'number':
            return
        if kind == 'ident':
            self.identifiers.append(text)
            following = self._peek()
            is_call = (following is not None and following[0] == 'op'
                       and following[1] == '(')
            self.calls.append(is_call)
            if is_call:
                self.functions.append(text)
                self.index += 1                    # 吃掉 '('
                following = self._peek()
                if following is not None and following[0] == 'op' and following[1] == ')':
                    self.index += 1                # 零参调用，如 f()
                else:
                    self._expression()
                    while True:
                        nxt = self._peek()
                        if nxt is not None and nxt[0] == 'op' and nxt[1] == ',':
                            self.index += 1
                            self._expression()
                        else:
                            break
                    self._expect_op(')')
            return
        if text == '(':
            self._expression()
            self._expect_op(')')
            return
        raise CstExpressionError(
            f'表达式第 {pos + 1} 个字符处不应出现 {text!r}')


def parse_expression(expression: str):
    """
    校验语法并收集标识符。

    :param expression: str
    :return: tuple, ``(identifiers, functions, calls)``；``calls[i]`` 表示
        ``identifiers[i]`` 是否被当函数调用
    :raises CstExpressionError: 语法非法
    """
    parser = _Parser(tokenize(expression))
    parser.parse()
    return tuple(parser.identifiers), tuple(parser.functions), tuple(parser.calls)


def expression_identifiers(expression: str) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """
    取出表达式里的参数引用与函数名。

    :param expression: str
    :return: tuple, ``(identifiers, functions)``
    :raises CstExpressionError: 语法非法
    """
    identifiers, functions, _ = parse_expression(expression)
    return identifiers, functions


# ============================================================
# 表达式校验
# ============================================================

def check_expression(expression, parameters: Optional[Iterable[str]] = None,
                     *, allow_unknown_functions: bool = True) -> ExpressionCheck:
    """
    校验一个 CST 表达式，**不抛异常**。

    :param expression: str, 表达式（如 ``'a/2*sqr(3)'``、``'-lf5-lf6-lf4'``）
    :param parameters: 可迭代参数名，提供时**逐个核对参数引用**；
        ``None`` 表示不做引用检查（没有参数表时仍然能查语法）
    :param allow_unknown_functions: bool, True（默认）时白名单外的函数名只记
        ``unknown_functions`` 不报错 —— CST 的函数集比本表大，误拒比漏拒更糟
    :return: :class:`ExpressionCheck`
    """
    if not isinstance(expression, str):
        return ExpressionCheck(ok=False, errors=(_error(
            'expression_not_string',
            f'表达式应为字符串，收到 {type(expression).__name__}',
            actual_type=type(expression).__name__),))
    text = expression.strip()
    if not text:
        return ExpressionCheck(ok=False, expression=text, errors=(_error(
            'expression_empty', '表达式为空字符串'),))

    try:
        identifiers, functions, calls = parse_expression(text)
    except CstExpressionError as exc:
        code = getattr(exc, 'code', 'expression_syntax_error')
        return ExpressionCheck(ok=False, expression=text,
                               errors=(_error(code, str(exc), expression=text),))

    known = None
    if parameters is not None:
        known = {str(p).lower() for p in parameters}

    unknown_parameters: List[str] = []
    unknown_functions: List[str] = []
    warnings: List[str] = []
    for ident, is_call in zip(identifiers, calls):
        lowered = ident.lower()
        if is_call:
            if lowered not in KNOWN_FUNCTIONS:
                unknown_functions.append(ident)
        elif known is not None and lowered not in known and lowered not in KNOWN_CONSTANTS:
            unknown_parameters.append(ident)

    if unknown_parameters:
        hint = ''
        if known:
            names = sorted(known)
            shown = ', '.join(names[:12])
            if len(names) > 12:
                shown += f' …（共 {len(names)} 个）'
            hint = f'；当前参数表里的名字：{shown}'
        return ExpressionCheck(
            ok=False, expression=text, identifiers=tuple(identifiers),
            functions=tuple(functions),
            unknown_parameters=tuple(sorted(set(unknown_parameters))),
            unknown_functions=tuple(sorted(set(unknown_functions))),
            errors=(_error(
                'expression_unknown_parameter',
                f'表达式 {text!r} 引用了不存在的参数：'
                f'{", ".join(sorted(set(unknown_parameters)))}' + hint,
                expression=text, parameters=sorted(set(unknown_parameters))),),
            warnings=tuple(warnings))
    if unknown_functions and not allow_unknown_functions:
        return ExpressionCheck(
            ok=False, expression=text, identifiers=tuple(identifiers),
            functions=tuple(functions),
            unknown_functions=tuple(sorted(set(unknown_functions))),
            errors=(_error(
                'expression_unknown_function',
                f'表达式 {text!r} 调用了不在白名单里的函数：'
                f'{", ".join(sorted(set(unknown_functions)))}',
                expression=text, functions=sorted(set(unknown_functions))),))
    if unknown_functions:
        warnings.append(
            f'函数 {", ".join(sorted(set(unknown_functions)))} 不在已知函数表里，'
            f'已放行（CST 可能支持）；若 CST 报错请核对拼写')

    return ExpressionCheck(
        ok=True, expression=text, identifiers=tuple(identifiers),
        functions=tuple(functions),
        unknown_functions=tuple(sorted(set(unknown_functions))),
        warnings=tuple(warnings))


def validate_expression(expression, parameters: Optional[Iterable[str]] = None,
                        *, allow_unknown_functions: bool = True) -> str:
    """
    校验表达式，非法即抛异常（库内部使用）。

    :param expression: str
    :param parameters: 可迭代参数名，提供时核对参数引用
    :param allow_unknown_functions: bool, 同 :func:`check_expression`
    :return: str, 去首尾空白后的表达式
    :raises CstExpressionError: 任何一项非法（错误信息里带位置与原因）
    """
    result = check_expression(expression, parameters,
                              allow_unknown_functions=allow_unknown_functions)
    if not result.ok:
        raise CstExpressionError(result.errors[0]['message'])
    return result.expression


# ============================================================
# 名称校验
# ============================================================

def check_name(name, kind: str = 'geometry',
               known: Optional[Iterable[str]] = None) -> NameCheck:
    """
    校验 CST 名称（几何体 / 组件 / 材料 / 参数），**不抛异常**。

    只拦截会破坏 VBA 或 CST 解析的字符与形式：

    * 空名、非字符串、只有空白；
    * 引号、换行、回车、制表符、反斜杠、控制字符；
    * 超长（> :data:`MAX_NAME_LENGTH`）；
    * ``kind='parameter'`` 时还要求是标识符（CST 参数名的语法）。

    **不**因为名字里有括号、空格、点、连字符或中文就拒绝。

    ⚠️ 路径**不要**用本函数校验 —— 反斜杠在路径里合法，请用 :func:`check_path`。

    :param name: str, 名称
    :param kind: str, ``'geometry'`` / ``'component'`` / ``'material'`` /
        ``'parameter'`` / ``'text'``
    :param known: 可迭代的已知取值（如材料预设表）；给出时额外核对是否在其中
    :return: :class:`NameCheck`
    """
    return _check_text(name, kind=kind, known=known,
                       forbidden=_FORBIDDEN_NAME_CHARS,
                       require_identifier=(kind == 'parameter'))


def check_path(path, kind: str = 'path',
               known: Optional[Iterable[str]] = None) -> NameCheck:
    """
    校验将要拼进 VBA 字符串字面量的**路径**，**不抛异常**。

    与 :func:`check_name` 的区别只有一处，但很关键：**反斜杠与冒号是合法字符**
    （``D:\\成电\\out.cst``、``C:/tmp/tmp.cst`` 都要能通过）。
    仍然拦下引号、换行、制表符与控制字符 —— 这些才是会破坏 VBA 的东西。

    :param path: str, 路径
    :param kind: str, 标记用途（默认 ``'path'``）
    :param known: 可迭代已知取值（一般不用）
    :return: :class:`NameCheck`
    """
    return _check_text(path, kind=kind, known=known,
                       forbidden=_FORBIDDEN_PATH_CHARS,
                       require_identifier=False)


def _check_text(name, *, kind: str, known: Optional[Iterable[str]],
                forbidden: Dict[str, str],
                require_identifier: bool) -> NameCheck:
    """名称/路径/文本共用的校验主体。"""
    errors: List[Dict] = []
    warnings: List[str] = []

    if not isinstance(name, str):
        return NameCheck(ok=False, kind=kind, errors=(_error(
            'name_not_string', f'名称应为字符串，收到 {type(name).__name__}',
            actual_type=type(name).__name__),))

    stripped = name.strip()
    if not stripped:
        return NameCheck(ok=False, kind=kind, errors=(_error(
            'name_empty', '名称不能为空或只有空白'),))
    if stripped != name:
        warnings.append(f'名称 {name!r} 首尾有空白，已规范化为 {stripped!r}')

    if len(stripped) > MAX_NAME_LENGTH:
        errors.append(_error(
            'name_too_long',
            f'名称长度 {len(stripped)} 超过上限 {MAX_NAME_LENGTH}',
            length=len(stripped), limit=MAX_NAME_LENGTH))

    for pos, ch in enumerate(stripped):
        if ch in forbidden:
            errors.append(_error(
                'name_forbidden_character',
                f'名称第 {pos + 1} 个字符 {ch!r} 非法：{forbidden[ch]}',
                position=pos, character=ch))
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            errors.append(_error(
                'name_forbidden_character',
                f'名称第 {pos + 1} 个字符是控制字符（0x{ord(ch):02X}），非法',
                position=pos))

    if require_identifier and not _PARAMETER_NAME_RE.match(stripped):
        errors.append(_error(
            'name_not_identifier',
            f'参数名 {stripped!r} 不是合法标识符：必须以字母或下划线开头，'
            f'只能包含字母、数字和下划线（例如 a、h、l1、px2、HEX_SIZE）',
            name=stripped))

    if known is not None and not errors:
        known_set = {str(k) for k in known}
        if stripped not in known_set:
            errors.append(_error(
                'name_unknown_value',
                f'{kind} 名 {stripped!r} 不在已知取值里；'
                f'已知取值：{", ".join(sorted(known_set))}',
                known=sorted(known_set)))

    return NameCheck(ok=not errors, name=stripped, kind=kind,
                     errors=tuple(errors), warnings=tuple(warnings))


def validate_name(name, kind: str = 'geometry',
                  known: Optional[Iterable[str]] = None) -> str:
    """
    校验名称，非法即抛 :class:`CstNameError`。

    :param name: str
    :param kind: str, 同 :func:`check_name`
    :param known: 可迭代已知取值
    :return: str, 规范化（去首尾空白）后的名称
    :raises CstNameError: 名称非法
    """
    result = check_name(name, kind=kind, known=known)
    if not result.ok:
        raise CstNameError(result.errors[0]['message'])
    return result.name


def validate_parameter_name(name) -> str:
    """校验 CST 参数名（必须是标识符）。"""
    return validate_name(name, kind='parameter')


def validate_path(path) -> str:
    """
    校验路径，非法即抛 :class:`CstNameError`。

    :param path: str, 路径（``D:\\out\\wg.cst``、``tmp.cst`` 都合法）
    :return: str, 去首尾空白后的路径
    :raises CstNameError: 含引号/换行/制表符/控制字符
    """
    result = check_path(path)
    if not result.ok:
        raise CstNameError(result.errors[0]['message'])
    return result.name


def check_material_name(name, known: Optional[Iterable[str]] = None) -> NameCheck:
    """
    校验材料名；给出 ``known``（如 ``cst_solver`` 的预设材料表）时核对存在性。

    ``Copper (annealed)`` / ``Silicon (lossy)`` 这类含空格与括号的名字**合法**。
    """
    return check_name(name, kind='material', known=known)


def validate_material_name(name, known: Optional[Iterable[str]] = None) -> str:
    """校验材料名，非法即抛 :class:`CstNameError`。"""
    return validate_name(name, kind='material', known=known)


def check_vba_text(text, kind: str = 'text') -> NameCheck:
    """
    校验将要拼进 **VBA 字符串字面量内部** 的任意文本（参数说明、备注等）。

    比 :func:`check_name` 宽松：只拦会**逃出引号**的字符（双引号、换行、回车）
    与控制字符。单引号、反斜杠、制表符、中文、空格都合法 ——
    说明文本本来就长这样，用名称规则去套会大面积误报。

    :param text: str, 文本
    :param kind: str, 标记用途（默认 ``'text'``）
    :return: :class:`NameCheck`
    """
    return _check_text(text, kind=kind, known=None,
                       forbidden=_FORBIDDEN_TEXT_CHARS,
                       require_identifier=False)


def validate_vba_text(text, kind: str = 'text') -> str:
    """校验 VBA 文本，非法即抛 :class:`CstNameError`。"""
    result = check_vba_text(text, kind=kind)
    if not result.ok:
        raise CstNameError(result.errors[0]['message'])
    return result.name
