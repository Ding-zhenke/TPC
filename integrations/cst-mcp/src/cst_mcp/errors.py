# -*- coding: utf-8 -*-
r"""
工具错误与结果封装（P3）
========================

分两层，别混：

* :class:`ToolError` —— **工具内部**抛出的结构化错误，带
  ``code/message/details/retryable``（与 ``cst_mcp.md`` §5 同一口径，
  底层实现仍复用 ``cst_solver.failures.structured_error``）；
* :func:`tool_payload` / :func:`error_payload` —— 交给协议层的规范化字典。

为什么不让工具直接返回 ``CallToolResult``
-----------------------------------------
工具实现要保持**可离线单测**：不导入 MCP SDK、不依赖事件循环，只吃 dict、
吐 dict。协议层（`cst_mcp.server`）再把它包成 `CallToolResult`。
"""

from typing import Any, Dict, Optional

from cst_solver.failures import structured_error

__all__ = ['ToolError', 'error_payload', 'tool_payload', 'TOOL_ERROR_CODES']

#: 本层可能产生的错误码（工具输入/流程层面；底层错误码原样透传）。
#: ⚠️ 2026-09-17 一致性检查发现两处漂移并已修：
#: ① `dispatch()` 在异常没有 `code` 时会产 `tool_failed`，但它原来不在表里；
#: ② `service_unavailable` 从未被产出过（运行服务不可用时底层会抛
#:    `tpc_service` 的 `service_shutdown`/`backend_failed`，此处再留一个码只是死表项），
#:    已删除。
TOOL_ERROR_CODES = (
    'unknown_tool',            # 工具名不在工具表里
    'invalid_arguments',       # 参数缺失/类型不对/取值越界
    'missing_requirement',     # 缺少关键物理条件（应让 AI 向用户补问）
    'not_found',               # 引用的任务/工程/文件不存在
    'analysis_failed',         # S 参数分析失败
    'report_failed',           # 报告导出失败
    'tool_failed',             # 底层异常没有自带 code（dispatch 兜底）
)


class ToolError(Exception):
    """
    工具层错误（结构化）。

    :param code: str, 错误码，见 :data:`TOOL_ERROR_CODES`
    :param message: str, 说明
    :param retryable: bool, 原样重试是否有意义
    :param details: 任意键值对（进结构化结果）
    """

    def __init__(self, code: str, message: str, *, retryable: bool = False,
                 **details):
        super().__init__(message)
        self.code = code
        self.retryable = bool(retryable)
        self.details = dict(details)

    def to_dict(self) -> Dict[str, Any]:
        """结构化错误字典。"""
        return structured_error(self.code, str(self),
                                retryable=self.retryable, **self.details)


def error_payload(code: str, message: str, *, retryable: bool = False,
                  **details) -> Dict[str, Any]:
    """构造「失败」工具返回值（**不是**空数据）。"""
    return {'ok': False, 'error': structured_error(code, message,
                                                   retryable=retryable,
                                                   **details)}


def tool_payload(data: Optional[Dict[str, Any]] = None, *,
                 notes: Optional[list] = None) -> Dict[str, Any]:
    """
    构造「成功」工具返回值。

    :param data: dict 可选, 结构化内容
    :param notes: list 可选, 给 AI 读的补充说明（例如「模板默认值已生效」）
    :return: dict, 一定含 ``ok``；``notes`` 非空才出现
    """
    payload: Dict[str, Any] = {'ok': True}
    if data:
        payload.update(data)
    if notes:
        payload['notes'] = list(notes)
    return payload
