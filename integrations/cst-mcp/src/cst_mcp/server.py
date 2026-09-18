# -*- coding: utf-8 -*-
r"""
MCP 协议装配（P3）
==================

把 :mod:`cst_mcp.tools` 的纯函数挂到 MCP 的低层 ``Server`` 上：

* ``list_tools`` → 工具表（JSON Schema 一并给出，客户端可据此生成参数）
* ``call_tool`` → 结构化结果（``structuredContent`` + JSON 文本 + ``isError``）

两处刻意的取舍
--------------
1. **关闭 SDK 侧输入校验**（``validate_input=False``）：SDK 自带的 jsonschema
   校验失败只会给一句纯文本，而计划要求「统一结构化错误」。
   schema 仍然照常发布给客户端；参数校验由工具自己用结构化错误码完成。
2. **每次调用都套 stdout 隔离**（:func:`cst_mcp.isolation.protocol_stdout`）：
   工具与底层库的 `print` 一律落到 stderr，stdout 只留给 JSON-RPC。

@author: PC
"""

import json
from typing import Any, Dict

import mcp.types as types
from mcp.server import Server

from cst_mcp import __version__
from cst_mcp.isolation import protocol_stdout
from cst_mcp.tools import TOOL_SPECS, dispatch

__all__ = ['build_server', 'SERVER_NAME']

SERVER_NAME = 'tpc-cst-mcp'


def _tool_definitions() -> list:
    """把工具表转成 MCP ``Tool``。"""
    return [types.Tool(name=spec['name'], description=spec['description'],
                       inputSchema=spec['inputSchema'])
            for spec in TOOL_SPECS]


def build_server() -> Server:
    """
    构造 MCP 服务（工具注册完成，尚未运行）。

    :return: ``mcp.server.Server``
    """
    server = Server(SERVER_NAME, version=__version__)

    @server.list_tools()
    async def list_tools() -> list:
        """列出工具。"""
        return _tool_definitions()

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: Dict[str, Any]) -> types.CallToolResult:
        """执行一个工具，返回结构化结果。"""
        with protocol_stdout():                     # 工具的 print 全部去 stderr
            payload = dispatch(name, arguments)
        ok = bool(payload.get('ok'))
        text = json.dumps(payload, ensure_ascii=False, default=str)
        return types.CallToolResult(
            content=[types.TextContent(type='text', text=text)],
            structuredContent=payload,
            isError=not ok)

    return server
