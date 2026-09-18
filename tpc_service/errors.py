# -*- coding: utf-8 -*-
r"""
服务层错误（P2）
================

统一使用 ``cst_solver.failures.structured_error`` 的
``{code, message, details, retryable}`` 四件套 —— **全仓唯一实现**，
服务层不再自造第二套错误结构（``skills/developer/conventions.md`` 硬约定 5）。

错误码一览
----------
============================  ====================================================
``workdir_escape``            路径逃出服务工作目录
``project_not_found``         工程文件不存在
``project_exists``            目标工作副本已存在且未允许覆盖
``project_copy_failed``       工程复制失败
``project_not_registered``    工程 ID 没有注册
``request_id_conflict``       同一请求 ID 提交了不同参数
``unknown_job_kind``          任务种类不在 ``JOB_KINDS`` 里
``unknown_job``               任务 ID 不存在
``invalid_transition``        任务状态迁移非法（内部一致性错误）
``cancelled_before_start``    排队中的任务被取消（尚未开始，不涉及 CST）
``cancel_not_supported``      运行中的任务无法取消（CST 停止接口未核实）
``service_restarted``         服务重启后发现无法确认的任务，标记为中断
``backend_failed``            后端执行失败（假后端/真实 CST 都会用）
``service_shutdown``          后台 worker 已经关闭，不再接受任务
============================  ====================================================
"""

from cst_solver.failures import structured_error

__all__ = ['ServiceError', 'error_dict', 'ERROR_CODES']

ERROR_CODES = (
    'workdir_escape',
    'project_not_found',
    'project_exists',
    'project_copy_failed',
    'project_not_registered',
    'request_id_conflict',
    'unknown_job_kind',
    'unknown_job',
    'invalid_transition',
    'cancelled_before_start',
    'cancel_not_supported',
    'service_restarted',
    'backend_failed',
    'service_shutdown',
)


def error_dict(code: str, message: str, *, retryable: bool = False, **details):
    """
    构造结构化错误（转发到唯一实现）。

    :param code: str, 错误码
    :param message: str, 说明
    :param retryable: bool, 原样重试是否有意义
    :param details: 任意键值对
    :return: dict
    """
    return structured_error(code, message, retryable=retryable, **details)


class ServiceError(RuntimeError):
    """
    服务层错误：携带 ``code/message/details/retryable``，可 ``to_dict()`` 直接回给调用方。

    :param code: str, 错误码（见 :data:`ERROR_CODES`）
    :param message: str, 说明
    :param retryable: bool, 原样重试是否有意义
    :param details: 任意键值对
    """

    def __init__(self, code: str, message: str, *, retryable: bool = False,
                 **details):
        super().__init__(message)
        self.code = code
        self.retryable = bool(retryable)
        self.details = dict(details)

    def to_dict(self):
        """结构化错误字典。"""
        return error_dict(self.code, str(self), retryable=self.retryable,
                          **self.details)
