# -*- coding: utf-8 -*-
r"""
命令行入口：``python -m cst_mcp`` / ``tpc-cst-mcp``
====================================================

用法::

    python -m cst_mcp                    # 以 stdio 运行 MCP 服务（给 AI 客户端用）
    python -m cst_mcp --check            # 只做自检：打印能力报告后退出（不启动服务）
    python -m cst_mcp --workdir D:\w     # 指定服务工作目录

⚠️ **运行服务时 stdout 只承载 JSON-RPC**：本模块在服务模式下不向 stdout 打印
任何东西（自检模式 ``--check`` 例外，它是给人/脚本看的 CLI 输出）。
"""

import argparse
import json
import sys
from typing import Optional, Sequence

from cst_mcp import __version__, runtime
from cst_mcp.tools import dispatch

__all__ = ['main']


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='tpc-cst-mcp',
        description='TPC 的 CST MCP 服务（stdio 传输）')
    parser.add_argument('--workdir', default=None,
                        help='服务工作目录（默认 $TPC_MCP_WORKDIR 或 ./tpc_mcp_work）')
    parser.add_argument('--check', action='store_true',
                        help='只打印能力报告并退出，不启动 MCP 服务')
    parser.add_argument('--version', action='version',
                        version=f'tpc-cst-mcp {__version__}')
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """
    入口。

    :param argv: 序列 可选, 命令行参数（默认 ``sys.argv[1:]``）
    :return: int, 退出码（``--check`` 时 CST 不可用也返回 0 —— 离线工具仍可用）
    """
    args = _build_parser().parse_args(argv)
    if args.workdir:
        runtime.configure(workdir=args.workdir)

    if args.check:
        payload = dispatch('get_capabilities', {})
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    # 服务模式：stdout 只给协议
    import anyio
    from mcp.server.stdio import stdio_server

    from cst_mcp.server import build_server

    server = build_server()

    async def _serve() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream,
                             server.create_initialization_options())

    try:
        anyio.run(_serve)
    except KeyboardInterrupt:                      # pragma: no cover
        print('收到中断，退出', file=sys.stderr)
        return 130
    return 0


if __name__ == '__main__':                         # pragma: no cover
    raise SystemExit(main())
