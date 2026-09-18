# -*- coding: utf-8 -*-
r"""
结构化失败通道（P1）
====================

问题
----
封装层里有若干**旧兼容接口**失败时不抛异常，只写一条 ``logging.warning`` 就返回：
材料名不认识（``new_material``）、材料库路径不存在（``list_library_materials``）、
``.mtd`` 里没有有效定义（``load_material_from_file``）…。调用方拿到的返回值
（``None`` / ``[]`` / ``False``）与「正常但没有数据」**区分不开** ——
这正是 ``docs/architecture/cst_mcp.md`` §5 点名要禁止的
「把失败或缺失结果变成空数据后声称成功」。

本模块在**不改这些接口返回值**的前提下，加一条结构化失败通道：

1. :func:`record_failure` —— 静默失败发生时记录
   ``{code, message, details, retryable}``（照旧写 logging，同时进入当前收集器）；
2. :func:`collect_failures` —— 上下文管理器，把一段代码里的静默失败**一网打尽**；
   共用运行服务（P2）与 MCP 写入口（P3）用它把「这一步有没有静默失败」
   变成可判定的事实；
3. :func:`set_failure_strict` —— 可选严格模式：静默失败**直接抛**
   :class:`CstOperationError`。默认关闭。

为什么默认不抛异常
------------------
``new_material('Gold')`` 在旧 notebook 里是「提示一句后继续跑」；
直接改成异常会破坏既有兼容（P1 验收判据之一「旧 notebook 导入兼容」）。
所以默认行为一字不变，**要不要升级成异常由调用方决定** ——
这正是 `docs/next_plan/README.md` P1 第 4 条「在兼容现有 API 的前提下，
给共用服务提供结构化失败」的落点。

错误结构统一
------------
``{code, message, details, retryable}`` 是 ``cst_mcp.md`` §5 的唯一口径。
本模块的 :func:`structured_error` 是它的唯一实现，
``cst_solver.expressions`` / ``cst_solver.run_contract`` / ``topo_modeler.preflight``
都复用它（避免同仓库出现第二套错误结构）。

@author: PC
"""

import logging
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List

__all__ = [
    'CstOperationError',
    'structured_error',
    'record_failure',
    'collect_failures',
    'recent_failures',
    'set_failure_strict',
    'failure_strict_enabled',
    'reset_failure_state',
]

_logger = logging.getLogger(__name__)


# ============================================================
# 统一错误结构
# ============================================================

def structured_error(code: str, message: str, *, retryable: bool = False,
                     **details) -> Dict[str, Any]:
    """
    构造 ``code/message/details/retryable`` 结构（``cst_mcp.md`` §5 口径）。

    :param code: str, 机器可读错误码
    :param message: str, 给人看的说明（不要只放错误码）
    :param retryable: bool, 原样重试是否有意义（参数写错=False，临时占用=True）
    :param details: 任意键值对，放进 ``details``（必须 JSON 可序列化）
    :return: dict
    """
    return {'code': code, 'message': message, 'details': dict(details),
            'retryable': bool(retryable)}


class CstOperationError(RuntimeError):
    """
    CST 操作失败的结构化异常（严格模式下由 :func:`record_failure` 抛出）。

    :param code: str, 错误码
    :param message: str, 说明
    :param retryable: bool, 是否值得原样重试
    :param operation: str, 发生失败的操作名（如 ``new_material``）
    :param details: 任意键值对
    """

    def __init__(self, code: str, message: str, *, retryable: bool = False,
                 operation: str = '', **details):
        super().__init__(message)
        self.code = code
        self.retryable = bool(retryable)
        self.operation = operation
        self.details = dict(details)

    def to_dict(self) -> Dict[str, Any]:
        """转成结构化错误字典（``operation`` 也放进 details）。"""
        details = dict(self.details)
        if self.operation:
            details.setdefault('operation', self.operation)
        return structured_error(self.code, str(self), retryable=self.retryable,
                                **details)


# ============================================================
# 收集器与严格模式
# ============================================================

_collectors: List[List[Dict[str, Any]]] = []
_recent: List[Dict[str, Any]] = []
_strict = False


def record_failure(operation: str, code: str, message: str, *,
                   retryable: bool = False, log: bool = True,
                   **details) -> Dict[str, Any]:
    """
    记录一次**静默失败**：写 logging、放进当前收集器，严格模式下抛异常。

    :param operation: str, 操作名（如 ``new_material``）
    :param code: str, 错误码（如 ``material_not_preset``）
    :param message: str, 说明（与旧的 warning 文案保持一致，便于日志对照）
    :param retryable: bool, 是否值得原样重试
    :param log: bool, 是否顺便写一条 warning（调用方自己已写日志时传 False）
    :param details: 任意键值对
    :return: dict, 结构化错误（严格模式下不会返回，而是抛异常）
    :raises CstOperationError: 严格模式已开启时
    """
    error = structured_error(code, message, retryable=retryable,
                             operation=operation, **details)
    if log:
        _logger.warning('%s 失败：%s', operation, message)
    for bucket in _collectors:
        bucket.append(error)
    _recent.append(error)
    if _strict:
        raise CstOperationError(code, message, retryable=retryable,
                                operation=operation, **details)
    return error


@contextmanager
def collect_failures() -> Iterator[List[Dict[str, Any]]]:
    """
    收集本段代码里发生的静默失败（可嵌套）。

    用法::

        with collect_failures() as failures:
            app.new_material('Gold')
        if failures:
            ...   # 不要在这里假装成功

    :return: 上下文管理器，``as`` 得到的就是本次收集到的错误列表（实时追加）
    """
    bucket: List[Dict[str, Any]] = []
    _collectors.append(bucket)
    try:
        yield bucket
    finally:
        try:
            _collectors.remove(bucket)
        except ValueError:                             # pragma: no cover
            pass


def recent_failures(*, clear: bool = False) -> List[Dict[str, Any]]:
    """
    最近发生的静默失败（**包括**没有放进收集器的那些）。

    :param clear: bool, True 时读取后清空
    :return: list[dict]
    """
    global _recent
    snapshot = list(_recent)
    if clear:
        _recent = []
    return snapshot


def set_failure_strict(enabled: bool) -> bool:
    """
    开关严格模式：开启后静默失败直接抛 :class:`CstOperationError`。

    :param enabled: bool
    :return: bool, 之前的设置
    """
    global _strict
    previous = _strict
    _strict = bool(enabled)
    return previous


def failure_strict_enabled() -> bool:
    """当前是否处于严格模式。"""
    return _strict


def reset_failure_state() -> None:
    """清空收集器与最近记录（测试用；**不改**严格模式）。"""
    _collectors.clear()
    _recent.clear()
