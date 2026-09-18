# -*- coding: utf-8 -*-
r"""
后端契约（P2）
==============

服务层不关心「谁来执行」，只关心三件事：**成功没成功、日志与产物在哪、
是否确认保存**。因此后端只要实现三个方法：

============================  ==================================================
``build(project, params)``    按 ``params['spec']`` 建模并保存工程
``solve(project, params)``    求解工程，**先保存结果再读**
``study(project, params)``    参数研究（扫描 / 批量 / 优化），内部串行
============================  ==================================================

返回值统一是 dict：

.. code-block:: python

    {'ok': bool, 'error': dict | None, 'log': [str, ...],
     'artifacts': [{'kind': ..., 'path': ..., 'note': ...}],
     'run_identity': {...}, 'result_summary': {...}, 'saved': bool}

两条硬要求
----------
1. ``solve`` / ``study`` 必须把 ``saved`` 置为 ``True``（真的保存过结果）；
   服务层看到不是 ``True`` 就判失败 —— 否则读到的可能是**上一轮**的结果。
2. 后端**不要把失败变成空数据**：``ok=False`` + 结构化 ``error``，
   或者直接抛异常（服务层会包成 ``backend_failed``）。

@author: PC
"""

from typing import Any, Dict, List, Optional

__all__ = ['Backend', 'ok_result', 'fail_result', 'artifact']


def artifact(path: str, *, kind: str = 'file', note: str = '') -> Dict[str, Any]:
    """构造一个产物条目。"""
    return {'kind': kind, 'path': path, 'note': note}


def ok_result(*, log: Optional[List[str]] = None, artifacts: Optional[List[Dict]] = None,
              run_identity: Optional[Dict[str, Any]] = None,
              result_summary: Optional[Dict[str, Any]] = None,
              saved: bool = True) -> Dict[str, Any]:
    """构造成功返回（字段齐全，避免调用方到处 ``.get``）。"""
    return {'ok': True, 'error': None, 'log': list(log or []),
            'artifacts': list(artifacts or []),
            'run_identity': dict(run_identity or {}),
            'result_summary': dict(result_summary or {}),
            'saved': bool(saved)}


def fail_result(code: str, message: str, *, retryable: bool = False,
                log: Optional[List[str]] = None, **details) -> Dict[str, Any]:
    """构造失败返回（结构化错误，**不是**空数据）。"""
    from tpc_service.errors import error_dict
    return {'ok': False, 'error': error_dict(code, message,
                                             retryable=retryable, **details),
            'log': list(log or []), 'artifacts': [],
            'run_identity': {}, 'result_summary': {}, 'saved': False}


class Backend:
    """
    后端基类：默认所有方法都明确报「未实现」，而不是静默返回 ``{}``。

    :param name: str, 后端名（进日志与 ``describe()``）
    """

    name = 'backend'

    def build(self, *, project: Dict[str, Any], params: Dict[str, Any],
              job: Dict[str, Any]) -> Dict[str, Any]:
        """建模。见模块 docstring 的返回值契约。"""
        return fail_result('backend_failed',
                           f'{type(self).__name__} 未实现 build()')

    def solve(self, *, project: Dict[str, Any], params: Dict[str, Any],
              job: Dict[str, Any]) -> Dict[str, Any]:
        """求解。见模块 docstring 的返回值契约。"""
        return fail_result('backend_failed',
                           f'{type(self).__name__} 未实现 solve()')

    def study(self, *, project: Dict[str, Any], params: Dict[str, Any],
              job: Dict[str, Any]) -> Dict[str, Any]:
        """参数研究。见模块 docstring 的返回值契约。"""
        return fail_result('backend_failed',
                           f'{type(self).__name__} 未实现 study()')

    def close_project(self, *, project: Dict[str, Any], save: bool = True) -> None:
        """
        关闭工程会话。

        ⚠️ 服务层只会对**自己创建的会话**调用本方法（``session_owned=True``）。
        """
        return None
