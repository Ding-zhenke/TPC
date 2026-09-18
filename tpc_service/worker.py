# -*- coding: utf-8 -*-
r"""
单 CST worker（P2）
==================

只有一个后台线程
----------------
计划要求「单 CST worker，同一工程写操作串行」。本实现直接把它做成
**全局串行**：一个线程、一个队列，任何时刻最多一条任务在执行 ——
这比「同工程串行」更强，因此天然满足后者，也不需要额外加锁去协调多线程。

线程/进程归属（``cst_mcp.md`` §4 要求「明确对象线程/进程归属」）
--------------------------------------------------------------
* 队列与线程由本类拥有；``runner`` 回调**只在 worker 线程内**被调用；
* 后端会话对象只存在于该线程的调用栈与注册表里，**不跨线程传**；
* 提交方只拿 ``job_id``，通过状态查询与事件等待结果。

异常不吞
--------
``runner`` 抛出的异常会被记录到 :attr:`SingleWorker.errors`（含 job_id），
并写一条日志 —— 但**不改变任务状态**：状态由服务层的 ``runner`` 自己负责
（它才知道该记成 ``failed`` 还是 ``interrupted``）。worker 只保证
「异常不会让线程死掉、后续任务照跑」。
"""

import logging
import queue
import threading
from typing import Callable, List, Optional, Tuple

from tpc_service.errors import ServiceError

__all__ = ['SingleWorker']

_logger = logging.getLogger(__name__)

_STOP = object()


class SingleWorker:
    """
    单线程任务执行器。

    :param runner: 可调用, ``runner(job_id) -> None``；**只在 worker 线程内执行**
    :param name: str, 线程名（便于日志排查）
    """

    def __init__(self, runner: Callable[[str], None], *,
                 name: str = 'tpc-cst-worker'):
        self.runner = runner
        self.name = name
        self._queue: 'queue.Queue' = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._current: Optional[str] = None
        self._stopped = False
        self._started = False
        self._errors: List[Tuple[str, str]] = []

    # ---- 生命周期 ----

    def start(self) -> 'SingleWorker':
        """启动后台线程（幂等；已经关闭则报错）。"""
        with self._lock:
            if self._stopped:
                raise ServiceError('service_shutdown',
                                   'worker 已经关闭，不能再启动',
                                   worker=self.name)
            if not self._started:
                self._thread = threading.Thread(target=self._loop, name=self.name,
                                                daemon=True)
                self._thread.start()
                self._started = True
        return self

    def submit(self, job_id: str) -> None:
        """
        入队一条任务（**串行执行**；调用方不必加锁）。

        :param job_id: str, 任务 ID
        :raises ServiceError: ``service_shutdown``（worker 已关闭）
        """
        with self._lock:
            if self._stopped:
                raise ServiceError('service_shutdown',
                                   '服务已关闭，不再接受新任务',
                                   job_id=job_id)
        self.start()
        self._queue.put(job_id)

    def shutdown(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """
        停止 worker：不再接受新任务；``wait=True`` 时等在途任务跑完。

        :param wait: bool, 是否等待当前任务结束
        :param timeout: float 可选, 等待上限（秒）
        """
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            started = self._started
        if not started:
            return
        self._queue.put(_STOP)
        if wait and self._thread is not None:
            self._thread.join(timeout=timeout)

    # ---- 状态 ----

    @property
    def current(self) -> Optional[str]:
        """当前正在执行的 job_id（空闲为 None）。"""
        with self._lock:
            return self._current

    @property
    def pending(self) -> int:
        """队列里还没开始的任务数。"""
        return self._queue.qsize()

    @property
    def errors(self) -> List[Tuple[str, str]]:
        """``[(job_id, 异常字符串), ...]``：runner 抛出的异常（不吞）。"""
        with self._lock:
            return list(self._errors)

    @property
    def is_stopped(self) -> bool:
        """是否已关闭。"""
        with self._lock:
            return self._stopped

    # ---- 主循环 ----

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                self._queue.task_done()
                return
            job_id = str(item)
            with self._lock:
                self._current = job_id
            try:
                self.runner(job_id)
            except Exception as exc:                  # noqa: BLE001
                message = f'{type(exc).__name__}: {exc}'
                with self._lock:
                    self._errors.append((job_id, message))
                _logger.exception('worker 执行任务 %s 时异常（状态由服务层决定）',
                                  job_id)
            finally:
                with self._lock:
                    self._current = None
                self._queue.task_done()
