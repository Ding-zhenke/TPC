# -*- coding: utf-8 -*-
r"""
协议通道保护：stdout 隔离（P3）
===============================

问题
----
MCP 的 stdio 传输用 **stdout** 传 JSON-RPC，`stderr` 才是日志。
而 Python 侧到处可能有 `print`（`topo_templates` 的「已保存: …」、
`topo_modeler/lens_build.py` 约 20 处、`batch`/`scanner`/`audit` 的进度输出…）。
哪怕只有一行杂讯混进 stdout，客户端解析就会失败 —— 属于「协议层被业务日志污染」。

做法
----
每次工具调用都在 :func:`protocol_stdout` 上下文里执行：把 ``sys.stdout``
临时指向 ``sys.stderr``，工具返回后再恢复。于是：

* 工具/底层库的 `print` 全部落到 stderr（客户端日志里能看到，不丢）；
* stdout 只由协议层写 JSON-RPC。

⚠️ 两个必须说清的边界（不夸大）
------------------------------
1. 这是**进程内重定向**：它管得住 Python 的 `print`，管不住 **CST 进程自己的
   原生 stdout**（那是另一个进程的句柄）。CST 的原生输出由 CST 会话管理，
   不在本层的控制范围内 —— 真机验收（P4/V9）必须用「stdout 无杂讯」测试实测。
2. 它是**进程级全局状态**：并发线程里的 `print` 也会一起被重定向。
   本服务本来就按单 worker 串行设计（P2），因此可以接受。
"""

import contextlib
import sys
from typing import Iterator

__all__ = ['protocol_stdout', 'stdout_is_protocol_only']


@contextlib.contextmanager
def protocol_stdout() -> Iterator[None]:
    """
    在上下文内把 ``sys.stdout`` 重定向到 ``sys.stderr``（协议通道保护）。

    用法::

        with protocol_stdout():
            payload = handler(arguments)      # 期间任何 print 都去 stderr
    """
    with contextlib.redirect_stdout(sys.stderr):
        yield


def stdout_is_protocol_only(lines) -> bool:
    """
    检查一批 stdout 行是否**只**包含 JSON 对象（协议层允许的形态）。

    给「stdout 无杂讯」测试用：任何一行不是合法 JSON 对象，就说明有杂讯。

    :param lines: 可迭代的字符串行
    :return: bool, True 表示干净
    """
    import json
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return False
        if not isinstance(payload, dict):
            return False
    return True
