# -*- coding: utf-8 -*-
r"""
共用运行服务（P2）
==================

这一层做什么
------------
`cst_solver` 管「一次 CST 操作」，`topo_modeler` 管「一个器件怎么建」，
本包补上中间缺的那层：**工程注册 + 任务服务**，让 Python 用户和（P3 的）MCP
服务共用同一套执行与记录能力。

它**不依赖 MCP**（`cst_mcp.md` §2），也不重写几何/VBA/数值逻辑 ——
只负责「谁在执行、执行到哪一步了、结果在哪、失败长什么样」。

关键约束（都来自 `docs/next_plan/README.md` P2 与 `cst_mcp.md` §4–5）
------------------------------------------------------------------
1. **单 CST worker**：所有后端操作在一个专用线程里串行执行；
   比「同工程写操作串行」更强，因此天然满足后者。
   CST 对象**不跨线程、不出服务**：调用方拿到的只有 JSON 记录与产物路径。
2. **任务 ID + 状态机**：``queued`` / ``running`` / ``succeeded`` / ``failed``
   / ``interrupted``。重启后无法确认的任务标记 ``interrupted``，
   **不自动重跑仿真**。
3. **请求 ID 去重**：同 ID 同参数返回既有任务；同 ID 不同参数报
   ``request_id_conflict``。
4. **工作目录约束**：所有产物写在服务工作目录内，路径逃逸直接失败。
5. **只释放自己创建的会话**：外部已有会话只解除注册，不关闭。
6. **不提供虚假的"已取消"**：CST 的停止接口尚未核实，
   ``cancel()`` 只对**还没开始**的任务生效，运行中的任务返回
   ``cancel_not_supported``。

用法（离线可跑，用假后端）::

    >>> from tpc_service import RunService
    >>> from tpc_service.backends.fake import FakeBackend
    >>> service = RunService(r'D:\work', backend=FakeBackend())
    >>> job = service.submit('build', project_path=r'D:\work\tmp.cst', params={'a': 1})
    >>> service.wait(job['job_id'])['status']
    'succeeded'

@author: PC
"""

from tpc_service.errors import ServiceError, error_dict
from tpc_service.registry import ProjectRecord, ProjectRegistry
from tpc_service.service import RunService
from tpc_service.state import (
    JOB_KINDS,
    JOB_STATUSES,
    TERMINAL_STATUSES,
    JobRecord,
    params_digest,
)
from tpc_service.worker import SingleWorker

__all__ = [
    'RunService',
    'SingleWorker',
    'ProjectRegistry',
    'ProjectRecord',
    'JobRecord',
    'ServiceError',
    'error_dict',
    'JOB_KINDS',
    'JOB_STATUSES',
    'TERMINAL_STATUSES',
    'params_digest',
]
