# -*- coding: utf-8 -*-
r"""
进程内运行时：工作目录与服务单例（P3）
======================================

MCP 服务是一个**长驻进程**，工具之间共享同一份运行服务。这里集中管三件事：

1. **工作目录**：默认 ``$TPC_MCP_WORKDIR``，其次 ``<当前目录>/tpc_mcp_work``；
   所有产物都写在里面（`tpc_service` 的工作目录约束在 P2 已实现）。
2. **运行服务单例**：第一次真正需要执行时才创建 `RunService`（延迟加载），
   于是「能力发现 / 模板列表 / 预检」这些离线工具**不需要 CST 也不需要工作目录**。
3. **后端选择**：默认真实 CST 后端；``$TPC_MCP_BACKEND=fake`` 时用假后端
   （给协议测试与「无 CST 演示」用）。用了假后端必须在能力报告里**如实说明**，
   否则就是拿假结果冒充真仿真。

⚠️ 单例是**进程内**的：MCP 服务按本地 stdio 单进程运行，所以这是够的；
将来要做多客户端/远程，需要把这里换成真正的任务服务进程（计划 P2 之后的扩展）。
"""

import os
import threading
from typing import Any, Dict, Optional

__all__ = ['configure', 'reset', 'get_service', 'describe_runtime',
           'default_workdir', 'backend_name', 'service_ready']

_LOCK = threading.Lock()
_STATE: Dict[str, Any] = {'workdir': None, 'backend': None, 'service': None}


def default_workdir() -> str:
    """默认工作目录：``$TPC_MCP_WORKDIR`` 优先，否则 ``./tpc_mcp_work``。"""
    env = os.environ.get('TPC_MCP_WORKDIR')
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.abspath(os.path.join(os.getcwd(), 'tpc_mcp_work'))


def _backend_from_env() -> Optional[Any]:
    """``$TPC_MCP_BACKEND=fake`` → 假后端；其它/未设 → None（用真实后端）。"""
    value = (os.environ.get('TPC_MCP_BACKEND') or '').strip().lower()
    if value == 'fake':
        from tpc_service.backends.fake import FakeBackend
        return FakeBackend()
    return None


def configure(*, workdir: Optional[str] = None, backend: Optional[Any] = None,
              service: Optional[Any] = None) -> Dict[str, Any]:
    """
    覆盖运行时配置（测试与嵌入用）。

    :param workdir: str 可选, 工作目录
    :param backend: 对象 可选, 后端实例（None 表示按环境变量/真实 CST 决定）
    :param service: 对象 可选, 直接注入一个已建好的 RunService
    :return: dict, 当前运行时描述
    """
    with _LOCK:
        if workdir is not None:
            _STATE['workdir'] = os.path.abspath(os.path.expanduser(workdir))
        if backend is not None:
            _STATE['backend'] = backend
        if service is not None:
            _STATE['service'] = service
            _STATE['backend'] = getattr(service, 'backend', _STATE['backend'])
    return describe_runtime()


def reset() -> None:
    """清空单例（测试用；不会关闭已建的服务，调用方自己 ``shutdown()``）。"""
    with _LOCK:
        _STATE['service'] = None
        _STATE['backend'] = None
        _STATE['workdir'] = None


def backend_name() -> str:
    """当前后端的名字（未创建服务时按环境变量判断）。"""
    with _LOCK:
        service = _STATE['service']
        backend = _STATE['backend']
    if service is not None:
        return str(getattr(service.backend, 'name',
                           type(service.backend).__name__))
    if backend is not None:
        return str(getattr(backend, 'name', type(backend).__name__))
    return 'fake' if _backend_from_env() is not None else 'cst'


def service_ready() -> bool:
    """运行服务是否已经创建。"""
    with _LOCK:
        return _STATE['service'] is not None


def get_service():
    """
    取运行服务（**第一次调用时才创建**）。

    :return: RunService
    """
    with _LOCK:
        if _STATE['service'] is not None:
            return _STATE['service']
        from tpc_service import RunService
        workdir = _STATE['workdir'] or default_workdir()
        backend = _STATE['backend'] or _backend_from_env()
        kwargs = {} if backend is None else {'backend': backend}
        service = RunService(workdir, **kwargs)
        _STATE['workdir'] = workdir
        _STATE['backend'] = service.backend
        _STATE['service'] = service
        return service


def describe_runtime() -> Dict[str, Any]:
    """运行时快照（可 JSON 序列化；不含 CST 句柄）。"""
    with _LOCK:
        workdir = _STATE['workdir'] or default_workdir()
        service = _STATE['service']
    payload: Dict[str, Any] = {
        'workdir': workdir,
        'workdir_exists': os.path.isdir(workdir),
        'backend': backend_name(),
        'service_created': service is not None,
        'env': {'TPC_MCP_WORKDIR': os.environ.get('TPC_MCP_WORKDIR', ''),
                'TPC_MCP_BACKEND': os.environ.get('TPC_MCP_BACKEND', '')},
    }
    if service is not None:
        payload['service'] = service.describe()
    return payload
