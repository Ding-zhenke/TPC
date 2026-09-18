# -*- coding: utf-8 -*-
r"""
任务状态机与任务记录（P2）
==========================

状态词表（``cst_mcp.md`` §4 + ``next_plan`` P2）
------------------------------------------------
::

    queued ──► running ──► succeeded
       │          │
       │          ├──► failed          （后端抛异常 / 判定为失败）
       │          └──► interrupted     （进程重启后无法确认；或取消尚未开始的任务）
       └──────────────► interrupted    （排队中被取消 / 重启时仍未开始）

硬规则：

* ``interrupted`` **不得**被当成成功，也**不自动重跑**（重启后由调用方决定）；
* 终态（``succeeded`` / ``failed`` / ``interrupted``）不可再迁移；
* 状态迁移非法直接抛 ``invalid_transition``（内部一致性错误，宁可炸也不写坏记录）。

参数摘要与「同 ID 不同参数」
----------------------------
:func:`params_digest` 把参数规范化成稳定 JSON 再取 sha256 ——
字典顺序、缩进都不影响结果，因此「同一请求 ID 换个写法重发」不会被误判成冲突。
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

from tpc_service.errors import ServiceError

__all__ = [
    'JOB_STATUSES',
    'TERMINAL_STATUSES',
    'JOB_KINDS',
    'ACTIVE_STATUSES',
    'params_digest',
    'can_transition',
    'JobRecord',
]

#: 全部任务状态
JOB_STATUSES = ('queued', 'running', 'succeeded', 'failed', 'interrupted')

#: 终态（不可再迁移）
TERMINAL_STATUSES = ('succeeded', 'failed', 'interrupted')

#: 非终态
ACTIVE_STATUSES = ('queued', 'running')

#: 任务种类：建模 / 求解 / 参数研究（扫描·批量·优化）
JOB_KINDS = ('build', 'solve', 'study')

#: 合法的状态迁移
_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    'queued': ('running', 'interrupted'),
    'running': ('succeeded', 'failed', 'interrupted'),
    'succeeded': (),
    'failed': (),
    'interrupted': (),
}


def params_digest(params: Any) -> str:
    """
    参数摘要：稳定 JSON 的 sha256（字典顺序无关）。

    :param params: 任意 JSON 可序列化对象
    :return: str, 16 进制摘要
    """
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=True,
                           separators=(',', ':'), default=str)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def can_transition(old: str, new: str) -> bool:
    """``old → new`` 是否为合法迁移。"""
    return new in _TRANSITIONS.get(old, ())


@dataclass
class JobRecord:
    """
    一条任务记录（可 JSON 序列化，落盘后重启仍可读回）。

    :param job_id: str, 任务 ID（服务生成，全局唯一）
    :param kind: str, 任务种类，见 :data:`JOB_KINDS`
    :param project_id: str 可选, 关联的工程 ID
    :param project_path: str 可选, 执行时使用的工程路径（工作副本或原路径）
    :param request_id: str 可选, 调用方给的幂等键
    :param params: dict, 本次任务的参数（原样保存，便于复现）
    :param params_digest: str, :func:`params_digest` 的结果（用于冲突判定）
    :param status: str, 见 :data:`JOB_STATUSES`
    :param created_at: str, 创建时间
    :param started_at: str 可选, 开始执行时间
    :param finished_at: str 可选, 结束时间
    :param error: dict 可选, 结构化错误（``code/message/details/retryable``）
    :param log: list[str], 执行日志（后端与服务的说明都进这里）
    :param artifacts: list[dict], 产物（``{kind, path, note}``）
    :param run_identity: dict, 运行标识（如 ``run_contract`` 的 ``run_token``）
    :param result_summary: dict, 结果摘要（小、可 JSON 化；大结果给产物路径）
    :param duplicate_of: str 可选, 本次提交是重复请求时指向既有任务 ID
    """

    job_id: str
    kind: str
    status: str = 'queued'
    project_id: Optional[str] = None
    project_path: Optional[str] = None
    request_id: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    params_digest: str = ''
    created_at: str = ''
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[Dict[str, Any]] = None
    log: List[str] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    run_identity: Dict[str, Any] = field(default_factory=dict)
    result_summary: Dict[str, Any] = field(default_factory=dict)
    duplicate_of: Optional[str] = None

    def __post_init__(self):
        if self.params_digest == '':
            self.params_digest = params_digest(self.params)

    # ---- 状态 ----

    @property
    def is_terminal(self) -> bool:
        """是否已到终态。"""
        return self.status in TERMINAL_STATUSES

    def transition(self, new_status: str, *, at: str,
                   error: Optional[Dict[str, Any]] = None) -> None:
        """
        迁移到新状态（非法迁移抛异常）。

        :param new_status: str, 目标状态
        :param at: str, 时间戳
        :param error: dict 可选, 失败时的结构化错误
        :raises ServiceError: 非法迁移（``invalid_transition``）
        """
        if not can_transition(self.status, new_status):
            raise ServiceError(
                'invalid_transition',
                f'任务 {self.job_id} 不能从 {self.status} 迁移到 {new_status}',
                job_id=self.job_id, old=self.status, new=new_status)
        self.status = new_status
        if new_status == 'running':
            self.started_at = at
        if new_status in TERMINAL_STATUSES:
            self.finished_at = at
            if error is not None:
                self.error = error

    # ---- 记录 ----

    def note(self, message: str) -> None:
        """追加一行日志。"""
        self.log.append(message)

    def add_artifact(self, path: str, *, kind: str = 'file',
                     note: str = '') -> Dict[str, Any]:
        """
        登记一个产物。

        :param path: str, 产物路径（应在服务工作目录内）
        :param kind: str, 产物类型（``file`` / ``project`` / ``csv`` …）
        :param note: str, 说明
        :return: dict, 登记的产物条目
        """
        entry = {'kind': kind, 'path': path, 'note': note}
        self.artifacts.append(entry)
        return entry

    # ---- 序列化 ----

    def to_dict(self) -> Dict[str, Any]:
        """JSON 友好字典（可直接回给 MCP 客户端）。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JobRecord':
        """从落盘字典恢复（未知键忽略，缺失键用默认值）。"""
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in allowed})
