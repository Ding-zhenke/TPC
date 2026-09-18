# -*- coding: utf-8 -*-
r"""
RunService —— 工程注册 + 任务服务（P2）
=====================================

对外只暴露「提交任务 / 查状态 / 取产物 / 管工程」四类操作，
内部由 **单 worker 线程串行执行**，状态与记录落盘可追溯。

任务种类
--------
============================  ==========================================
``build``                     按模型规格建模（走预检 + 模板）
``solve``                     求解已有工程，**保存后再读结果**
``study``                     参数扫描 / 批量 / 优化（后端注入 runner）
============================  ==========================================

后端契约（:mod:`tpc_service.backends.base`）
--------------------------------------------
后端只需实现 ``build`` / ``solve`` / ``study`` 三个方法，收关键字参数
``project``（dict）、``params``（dict）、``job``（dict），返回 dict：

.. code-block:: python

    {
      'ok': bool,                 # 显式成败；False 时用 error 说明
      'error': dict | None,       # 结构化错误
      'log': [str, ...],          # 执行日志（落进任务记录）
      'artifacts': [ {kind, path, note}, ... ],
      'run_identity': {...},      # 运行标识（如 run_contract 的 run_token）
      'result_summary': {...},    # 小结果摘要（大结果给 artifacts 路径）
      'saved': bool,              # solve/study **必须**为 True（先保存再读）
    }

``solve`` / ``study`` 返回 ``saved`` 不为 True 时，服务直接把任务判为
``failed``（``backend_failed``）—— 计划明确要求「保存求解后的结果再交给读取器」，
否则读到的可能是上一轮的结果。

@author: PC
"""

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from tpc_service.errors import ServiceError, error_dict
from tpc_service.registry import ProjectRecord, ProjectRegistry, copy_project
from tpc_service.state import (
    JOB_KINDS,
    JOB_STATUSES,
    TERMINAL_STATUSES,
    JobRecord,
    params_digest,
)
from tpc_service.store import JobStore
from tpc_service.worker import SingleWorker

__all__ = ['RunService']

_logger = logging.getLogger(__name__)

#: 任务种类 → 后端方法名
_HANDLERS = {'build': 'build', 'solve': 'solve', 'study': 'study'}

#: 必须在返回前确认「已保存」的种类（否则读到的可能是上一轮结果）
_NEEDS_SAVE = ('solve', 'study')


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class RunService:
    """
    共用运行服务（不依赖 MCP，Python 用户可直接用）。

    :param workdir: str, 服务工作目录（记录、工作副本、产物都写在这里）
    :param backend: 后端对象 可选, 见模块 docstring 的后端契约；
        不传则用真实 CST 后端（``cst_solver``/``topo_modeler``），
        离线测试请注入 :class:`tpc_service.backends.fake.FakeBackend`
    :param clock: 可调用 可选, 返回时间字符串（测试注入）
    :param recover: bool, 构造时是否把上次未完成的任务标记为 ``interrupted``
    :param autostart: bool, 是否在首次提交时自动启动 worker 线程
    """

    def __init__(self, workdir: str, backend: Any = None, *,
                 clock: Optional[Callable[[], str]] = None,
                 recover: bool = True, autostart: bool = True):
        self.workdir = os.path.abspath(workdir)
        os.makedirs(self.workdir, exist_ok=True)
        self.clock = clock or _utcnow
        self.store = JobStore(self.workdir).ensure()
        self.registry = ProjectRegistry(self.workdir, clock=self.clock)
        self.backend = backend if backend is not None else _default_backend()
        self.autostart = autostart

        self._lock = threading.RLock()
        self._jobs: Dict[str, JobRecord] = {}
        self._requests: Dict[str, str] = {}
        self._events: Dict[str, threading.Event] = {}
        self.worker = SingleWorker(self._execute, name='tpc-cst-worker')

        self.recovery: Dict[str, Any] = {'interrupted': [], 'recovered_at': None}
        if recover:
            self.recover()

    # ================================================================
    # 提交与查询
    # ================================================================

    def submit(self, kind: str, *, project_id: Optional[str] = None,
               project_path: Optional[str] = None,
               params: Optional[Dict[str, Any]] = None,
               request_id: Optional[str] = None, copy: bool = True,
               overwrite: bool = False, note: str = '') -> Dict[str, Any]:
        """
        提交一条任务。

        :param kind: str, ``build`` / ``solve`` / ``study``
        :param project_id: str 可选, 已注册工程 ID（与 ``project_path`` 二选一）
        :param project_path: str 可选, 工程路径（未注册时自动注册；``copy`` 决定是否复制）
        :param params: dict 可选, 任务参数（必须 JSON 可序列化；原样保存以便复现）
        :param request_id: str 可选, 幂等键：同 ID 同参数返回既有任务，
            同 ID 不同参数报 ``request_id_conflict``
        :param copy: bool, 自动注册时是否复制到工作目录（默认 True）
        :param overwrite: bool, 工作副本已存在时是否删除重建
        :param note: str, 备注
        :return: dict, 任务记录（重复提交时额外带 ``duplicate=True``）
        :raises ServiceError: ``unknown_job_kind`` / ``request_id_conflict`` /
            ``project_not_found`` / ``project_exists`` / ``service_shutdown``
        """
        if kind not in JOB_KINDS:
            raise ServiceError('unknown_job_kind',
                               f'未知任务种类 {kind!r}；可选：{" | ".join(JOB_KINDS)}',
                               kind=kind, allowed=list(JOB_KINDS))
        if params is not None and not isinstance(params, dict):
            raise ServiceError('backend_failed',
                               'params 必须是 dict（或省略）',
                               actual_type=type(params).__name__)
        payload = dict(params or {})
        digest = params_digest(payload)

        with self._lock:
            if request_id:
                existing_id = self._requests.get(request_id)
                if existing_id is not None:
                    existing = self._jobs[existing_id]
                    if (existing.params_digest == digest
                            and existing.kind == kind):
                        out = existing.to_dict()
                        out['duplicate'] = True
                        return out
                    raise ServiceError(
                        'request_id_conflict',
                        f'请求 ID {request_id!r} 已经用在任务 {existing_id} 上，'
                        f'但参数/种类不同；同 ID 不同参数会被拒绝，'
                        f'请换一个 request_id',
                        request_id=request_id, existing_job_id=existing_id,
                        existing_digest=existing.params_digest, new_digest=digest)

            record_project_id, record_project_path = self._resolve_project(
                project_id, project_path, copy=copy, overwrite=overwrite)

            job_id = f'job-{uuid4().hex[:12]}'
            record = JobRecord(job_id=job_id, kind=kind, status='queued',
                               project_id=record_project_id,
                               project_path=record_project_path,
                               request_id=request_id, params=payload,
                               params_digest=digest, created_at=self.clock())
            if note:
                record.note(note)
            record.note(f'提交任务：kind={kind}, project={record_project_path}')
            self.store.save(record)
            self.store.append_event(record, 'created')
            self._jobs[job_id] = record
            if request_id:
                self._requests[request_id] = job_id
            self._events[job_id] = threading.Event()

        if self.autostart:
            self.worker.submit(job_id)
        out = record.to_dict()
        out['duplicate'] = False
        return out

    def get(self, job_id: str) -> Dict[str, Any]:
        """
        取任务记录（内存优先，缺失则从磁盘读）。

        :raises ServiceError: ``unknown_job``
        """
        with self._lock:
            record = self._jobs.get(job_id)
        if record is None:
            record = self.store.load(job_id)
        if record is None:
            raise ServiceError('unknown_job', f'任务 ID {job_id!r} 不存在',
                               job_id=job_id)
        return record.to_dict()

    def list_jobs(self, *, status: Optional[str] = None,
                  kind: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出任务（可按状态/种类过滤；含磁盘上重启前留下的历史）。

        :param status: str 可选, 过滤状态
        :param kind: str 可选, 过滤种类
        :return: list[dict]
        """
        records: Dict[str, JobRecord] = {r.job_id: r for r in self.store.all()}
        with self._lock:
            for job_id, record in self._jobs.items():
                records[job_id] = record
        out = []
        for record in sorted(records.values(), key=lambda r: (r.created_at,
                                                              r.job_id)):
            if status is not None and record.status != status:
                continue
            if kind is not None and record.kind != kind:
                continue
            out.append(record.to_dict())
        return out

    def wait(self, job_id: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        等任务到达终态。

        :param job_id: str, 任务 ID
        :param timeout: float 可选, 等待上限（秒）；超时不抛异常，
            返回当前状态（可能仍是 ``running``）
        :return: dict, 任务记录
        """
        with self._lock:
            event = self._events.get(job_id)
        if event is None:
            return self.get(job_id)          # 重启前留下的任务：直接读盘
        event.wait(timeout)
        return self.get(job_id)

    def logs(self, job_id: str) -> List[str]:
        """任务日志（执行过程中逐步追加）。"""
        return list(self.get(job_id)['log'])

    def artifacts(self, job_id: str) -> List[Dict[str, Any]]:
        """任务产物清单。"""
        return list(self.get(job_id)['artifacts'])

    def result(self, job_id: str) -> Dict[str, Any]:
        """结果摘要 + 运行标识（**不含大数据**，大数据在产物路径里）。"""
        record = self.get(job_id)
        return {'job_id': job_id, 'status': record['status'],
                'result_summary': record['result_summary'],
                'run_identity': record['run_identity'],
                'artifacts': record['artifacts'],
                'error': record['error']}

    # ================================================================
    # 工程
    # ================================================================

    def open_project(self, path: str, *, copy: bool = True,
                     overwrite: bool = False,
                     project_id: Optional[str] = None,
                     session: Any = None, session_owned: bool = False,
                     note: str = '') -> Dict[str, Any]:
        """
        注册一个工程（默认复制到工作目录）。

        :param path: str, 工程 ``.cst`` 路径
        :param copy: bool, 是否复制（False 表示就地执行，风险自负）
        :param overwrite: bool, 工作副本已存在时是否删除重建
        :param project_id: str 可选, 指定 ID
        :param session: 后端会话对象（不落盘、不出 worker 线程）
        :param session_owned: bool, 该会话是否由服务创建（决定释放时是否关闭）
        :param note: str, 备注
        :return: dict, 工程记录
        """
        record = self.registry.register(path, copy=copy, overwrite=overwrite,
                                        project_id=project_id, session=session,
                                        session_owned=session_owned, note=note)
        return record.to_dict()

    def projects(self) -> List[Dict[str, Any]]:
        """已注册工程列表。"""
        return [r.to_dict() for r in self.registry.list()]

    def close_project(self, project_id: str, *, save: bool = True) -> Dict[str, Any]:
        """
        释放一个工程：**只关闭服务自己创建的会话**；外部会话只解除注册。

        :param project_id: str, 工程 ID
        :param save: bool, 关闭前是否保存（真实后端会用到）
        :return: dict, 释放结果
        :raises ServiceError: ``project_not_registered``
        """
        def closer(record: ProjectRecord):
            handler = getattr(self.backend, 'close_project', None)
            if handler is not None:
                handler(project=record.to_dict(), save=save)
        return self.registry.release(project_id, closer)

    # ================================================================
    # 生命周期
    # ================================================================

    def recover(self) -> Dict[str, Any]:
        """
        重启恢复：把磁盘上**未完成任务**标记为 ``interrupted``。

        计划要求「重启后无法确认的任务标记中断，**不自动重跑仿真**」——
        这里既不自动重跑，也不假装成功；被标记的任务会带
        ``service_restarted`` 错误与说明，由调用方决定是否重新提交。
        """
        interrupted: List[str] = []
        for record in self.store.all():
            if record.status in TERMINAL_STATUSES:
                continue
            previous = record.status
            record.transition('interrupted', at=self.clock(), error=error_dict(
                'service_restarted',
                f'服务重启时任务处于 {previous}，无法确认是否仍在执行/是否已算完；'
                f'已标记中断，**不会自动重跑**',
                retryable=True, previous_status=previous,
                resumed_at=self.clock()))
            record.note(f'重启恢复：{previous} → interrupted（不自动重跑）')
            self.store.save(record)
            self.store.append_event(record, 'recovered',
                                    previous_status=previous)
            interrupted.append(record.job_id)
        self.recovery = {'interrupted': interrupted, 'recovered_at': self.clock()}
        return self.recovery

    def cancel(self, job_id: str) -> Dict[str, Any]:
        """
        取消任务。

        * **还没开始**（``queued``）的任务：真的取消 —— 标记 ``interrupted``，
          不涉及任何 CST 操作；
        * **正在执行**的任务：返回 ``cancel_not_supported``。
          CST 的停止接口尚未核实（计划明确「未验证前不提供虚假的「已取消」」），
          终止等待**不等于**停止了 CST。

        :param job_id: str, 任务 ID
        :return: dict, 取消后的任务记录
        :raises ServiceError: ``cancel_not_supported`` / ``unknown_job``
        """
        record = self._record(job_id)
        with self._lock:
            if record.status == 'queued':
                record.transition('interrupted', at=self.clock(), error=error_dict(
                    'cancelled_before_start',
                    '任务尚未开始执行，已取消（未涉及任何 CST 操作）',
                    retryable=True, job_id=job_id))
                record.note('取消：queued → interrupted（尚未开始）')
                self._persist(record, 'cancelled')
                self._signal(job_id)
                return record.to_dict()
        raise ServiceError(
            'cancel_not_supported',
            f'任务 {job_id} 状态为 {record.status}，无法取消：'
            f'CST 的停止/取消接口尚未核实，本服务不提供虚假的「已取消」',
            retryable=False, job_id=job_id, status=record.status)

    def shutdown(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """
        关闭服务：不再接受新任务，``wait=True`` 时等在途任务结束。

        :param wait: bool, 是否等待
        :param timeout: float 可选, 等待上限（秒）
        """
        self.worker.shutdown(wait=wait, timeout=timeout)

    def describe(self) -> Dict[str, Any]:
        """服务快照（可 JSON 序列化；CST 句柄不出现）。"""
        return {
            'workdir': self.workdir,
            'worker': {'name': self.worker.name, 'current': self.worker.current,
                       'pending': self.worker.pending,
                       'stopped': self.worker.is_stopped,
                       'errors': self.worker.errors},
            'backend': getattr(self.backend, 'name', type(self.backend).__name__),
            'jobs': {status: len(self.list_jobs(status=status))
                     for status in JOB_STATUSES},
            'projects': [r.to_dict() for r in self.registry.list()],
            'recovery': self.recovery,
        }

    # ================================================================
    # 内部
    # ================================================================

    def _record(self, job_id: str) -> JobRecord:
        with self._lock:
            record = self._jobs.get(job_id)
        if record is None:
            record = self.store.load(job_id)
        if record is None:
            raise ServiceError('unknown_job', f'任务 ID {job_id!r} 不存在',
                               job_id=job_id)
        return record

    def _resolve_project(self, project_id: Optional[str],
                         project_path: Optional[str], *, copy: bool,
                         overwrite: bool):
        """
        把 ``project_id`` / ``project_path`` 解析成 (project_id, path)。

        **同一源工程重复提交只注册一次**：先按执行路径找，再按源路径找 ——
        否则第二次提交会再复制一遍工作副本、撞上 ``project_exists``
        （那是误报：用户只是又提交了同一个工程）。
        只有显式 ``overwrite=True`` 才会刷新工作副本。
        """
        if project_id:
            record = self.registry.get(project_id)
            return record.project_id, record.path
        if not project_path:
            raise ServiceError('project_not_found',
                               '必须给出 project_id 或 project_path')
        existing = self.registry.find_by_path(project_path)
        if existing is None and copy:
            existing = self.registry.find_by_source(project_path)
        if existing is not None:
            if overwrite and existing.owned_copy and existing.source_path:
                copy_project(existing.source_path, existing.path, overwrite=True)
            return existing.project_id, existing.path
        record = self.registry.register(project_path, copy=copy,
                                        overwrite=overwrite)
        return record.project_id, record.path

    def _persist(self, record: JobRecord, event: str, **extra) -> None:
        self.store.save(record)
        self.store.append_event(record, event, **extra)

    def _signal(self, job_id: str) -> None:
        with self._lock:
            event = self._events.get(job_id)
        if event is not None:
            event.set()

    def _project_payload(self, record: JobRecord) -> Dict[str, Any]:
        if not record.project_id:
            return {'project_id': None, 'path': record.project_path}
        try:
            return self.registry.get(record.project_id).to_dict()
        except ServiceError:
            return {'project_id': record.project_id, 'path': record.project_path}

    def _execute(self, job_id: str) -> None:
        """worker 线程里的执行体：状态迁移 + 后端调用 + 落盘。"""
        record = self._record(job_id)
        with self._lock:
            if record.status == 'interrupted':        # 排队期间被取消
                self._persist(record, 'skipped')
                self._signal(job_id)
                return
            record.transition('running', at=self.clock())
            record.note('开始执行')
            self._persist(record, 'started')

        try:
            outcome = self._invoke_backend(record)
        except ServiceError as exc:
            outcome = {'ok': False, 'error': exc.to_dict()}
        except Exception as exc:                      # noqa: BLE001
            _logger.exception('后端执行任务 %s 失败', job_id)
            outcome = {'ok': False, 'error': error_dict(
                'backend_failed', f'{type(exc).__name__}: {exc}',
                retryable=True, job_id=job_id)}

        ok = bool(outcome.get('ok', True)) and outcome.get('error') is None
        with self._lock:
            for line in outcome.get('log') or []:
                record.note(str(line))
            for artifact in outcome.get('artifacts') or []:
                record.artifacts.append(dict(artifact))
            record.run_identity.update(outcome.get('run_identity') or {})
            record.result_summary.update(outcome.get('result_summary') or {})

            if ok and record.kind in _NEEDS_SAVE and outcome.get('saved') is not True:
                # 计划要求：保存求解后的结果再交给读取器；没确认保存就不能算成功
                outcome['error'] = error_dict(
                    'backend_failed',
                    f'{record.kind} 任务返回时没有确认「已保存」'
                    f'（saved 不为 True）：读到的结果可能来自上一轮，'
                    f'因此判为失败',
                    retryable=True, kind=record.kind)
                ok = False

            if ok:
                record.transition('succeeded', at=self.clock())
                record.note('执行完成')
            else:
                error = outcome.get('error') or error_dict(
                    'backend_failed', '后端未给出成功标记，也没有错误详情')
                record.transition('failed', at=self.clock(), error=error)
                record.note(f'执行失败：{error.get("code")} {error.get("message")}')
            self._persist(record, 'finished')
        self._signal(job_id)

    def _invoke_backend(self, record: JobRecord) -> Dict[str, Any]:
        """调用后端对应方法（唯一入口，便于统一异常与日志）。"""
        handler_name = _HANDLERS[record.kind]
        handler = getattr(self.backend, handler_name, None)
        if handler is None:
            raise ServiceError('backend_failed',
                               f'后端 {type(self.backend).__name__} 没有 '
                               f'{handler_name}() 方法',
                               kind=record.kind)
        project = self._project_payload(record)
        return dict(handler(project=project, params=record.params,
                            job=record.to_dict()) or {})


def _default_backend():
    """默认后端：真实 CST（离线环境请显式注入假后端）。"""
    from tpc_service.backends.cst_backend import CstBackend
    return CstBackend()
