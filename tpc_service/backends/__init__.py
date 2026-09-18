# -*- coding: utf-8 -*-
r"""
后端实现（P2）
==============

* :class:`~tpc_service.backends.base.Backend` —— 契约与返回结构（离线可导入）
* :class:`~tpc_service.backends.fake.FakeBackend` —— 假后端（离线验收用）
* :class:`~tpc_service.backends.cst_backend.CstBackend` —— 真实 CST 接线

⚠️ 真实 CST 后端**只在真正调用时才导入 CST 相关库**（模块可以离线导入），
且其行为尚未在真机上验证（计划 P4/V7）。
"""

from tpc_service.backends.base import Backend, artifact, fail_result, ok_result
from tpc_service.backends.fake import FakeBackend

__all__ = ['Backend', 'FakeBackend', 'artifact', 'fail_result', 'ok_result',
           'CstBackend']


def __getattr__(name):                                # pragma: no cover
    """惰性暴露 ``CstBackend``（导入它不会连带导入 CST）。"""
    if name == 'CstBackend':
        from tpc_service.backends.cst_backend import CstBackend
        return CstBackend
    raise AttributeError(name)
