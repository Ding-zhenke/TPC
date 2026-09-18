# -*- coding: utf-8 -*-
"""
协议集成测试（P3）
==================

计划要求的六项全覆盖：

| 计划要求 | 用例 |
|---|---|
| 握手 | `test_handshake` |
| 工具发现 | `test_tools_are_discoverable` |
| 无 CST 能力报告 | `test_capabilities_without_cst` |
| 非法参数 | `test_invalid_arguments_are_error_results` |
| 长任务状态 | `test_long_task_status_flow` |
| 失败结果 | `test_failed_result_is_an_error` |
| stdout 无杂讯 | `test_stdout_stays_protocol_only`（子进程真 stdio） |

传输用 SDK 自带的内存会话（``create_connected_server_and_client_session``），
**不用真 CST、不起真进程**；唯一起子进程的是 stdout 杂讯测试 —— 它必须走
真实 stdio 才能验证协议通道。

⚠️ 这里验证的是**协议与工具语义**，不是物理正确性（真机闭环属计划 P4/V9）。
"""

import asyncio
import json
import os
import subprocess
import sys
import threading

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from mcp.shared.memory import (          # noqa: E402
    create_connected_server_and_client_session,
)

from cst_mcp import __version__, runtime, tools     # noqa: E402
from cst_mcp.server import SERVER_NAME, build_server   # noqa: E402
from tpc_service.backends.fake import FakeBackend      # noqa: E402

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture()
def env(tmp_path):
    template = tmp_path / 'tmp.cst'
    template.write_text('project-placeholder', encoding='utf-8')
    runtime.reset()
    runtime.configure(workdir=str(tmp_path / 'service'), backend=FakeBackend())
    yield {'work': tmp_path, 'template': template}
    runtime.get_service().shutdown()
    runtime.reset()


def _run(coro):
    """在同步测试里跑异步场景（不引入 pytest-asyncio 依赖）。"""
    return asyncio.run(coro)


def _spec(env):
    return {'model': {'type': 'straight_waveguide'},
            'geometry': {'length': 18, 'topology': 'BA'},
            'output': {'template_cst': str(env['template']),
                       'path': str(env['work'] / 'BA18.cst')}}


async def _call(session, name, arguments=None):
    """调一次工具，返回 ``(ok, payload)``。"""
    result = await session.call_tool(name, arguments or {})
    payload = result.structuredContent
    if payload is None and result.content:
        payload = json.loads(result.content[0].text)
    return (not result.isError), payload


# ============================================================
# 握手 / 发现
# ============================================================

def test_handshake(env):
    async def scenario():
        async with create_connected_server_and_client_session(build_server()) as session:
            result = await session.initialize()
            return result
    result = _run(scenario())
    assert result.serverInfo.name == SERVER_NAME
    assert result.serverInfo.version == __version__
    assert result.capabilities.tools is not None


def test_tools_are_discoverable(env):
    async def scenario():
        async with create_connected_server_and_client_session(build_server()) as session:
            await session.initialize()
            return await session.list_tools()
    result = _run(scenario())
    names = [tool.name for tool in result.tools]
    assert names == tools.tool_names()
    assert len(names) == 11
    for tool in result.tools:
        assert tool.description
        assert tool.inputSchema['type'] == 'object'


def test_capabilities_without_cst(env):
    """无 CST 也要能报告能力（离线工具不受影响）。"""
    async def scenario():
        async with create_connected_server_and_client_session(build_server()) as session:
            await session.initialize()
            return await _call(session, 'get_capabilities')
    ok, payload = _run(scenario())
    assert ok is True
    assert payload['ok'] is True
    assert 'status' in payload['cst']
    assert payload['backend'] == 'fake'


# ============================================================
# 非法参数 / 失败结果
# ============================================================

def test_invalid_arguments_are_error_results(env):
    async def scenario():
        async with create_connected_server_and_client_session(build_server()) as session:
            await session.initialize()
            return await _call(session, 'analyze_s_parameters', {'threshold_db': 'x'})
    ok, payload = _run(scenario())
    assert ok is False
    assert payload['ok'] is False
    assert payload['error']['code'] == 'invalid_arguments'
    assert payload['error']['retryable'] is False


def test_unknown_tool_is_an_error_result(env):
    async def scenario():
        async with create_connected_server_and_client_session(build_server()) as session:
            await session.initialize()
            return await _call(session, 'no_such_tool')
    ok, payload = _run(scenario())
    assert ok is False
    assert payload['error']['code'] == 'unknown_tool'


def test_failed_result_is_an_error(env):
    """失败的求解：get_results 必须报错，不能返回空数据。"""
    async def scenario():
        async with create_connected_server_and_client_session(build_server()) as session:
            await session.initialize()
            runtime.reset()
            runtime.configure(workdir=str(env['work'] / 'svc2'),
                              backend=FakeBackend(fail_on={'solve'}))
            service = runtime.get_service()
            job = service.submit('solve', project_path=str(env['template']))
            service.wait(job['job_id'], timeout=15)
            return await _call(session, 'get_results', {'job_id': job['job_id']})
    ok, payload = _run(scenario())
    assert ok is False
    assert payload['error']['code'] == 'backend_failed'
    assert payload['error']['details']['status'] == 'failed'


# ============================================================
# 长任务
# ============================================================

def test_long_task_status_flow(env):
    """建模/求解是异步长任务：提交 → 查状态 → 取结果。"""
    async def scenario():
        async with create_connected_server_and_client_session(build_server()) as session:
            await session.initialize()
            ok, build = await _call(session, 'build_model',
                                    {'spec': _spec(env), 'request_id': 'p-1'})
            assert ok and build['job_id']
            job_id = build['job_id']
            service = runtime.get_service()
            service.wait(job_id, timeout=15)
            _, status = await _call(session, 'get_job_status', {'job_id': job_id})
            _, results = await _call(session, 'get_results', {'job_id': job_id})
            return build, status, results
    build, status, results = _run(scenario())
    assert build['status'] in ('queued', 'running', 'succeeded')
    assert status['status'] == 'succeeded'
    assert status['finished_at']
    assert results['ok'] is True
    assert results['artifacts']


# ============================================================
# stdout 无杂讯（真实 stdio 子进程）
# ============================================================

def test_stdout_stays_protocol_only(tmp_path):
    """
    真 stdio 起服务进程，发 initialize + tools/list + tools/call，
    断言 **stdout 每一行都是合法 JSON**（杂讯会破坏协议）。
    """
    template = tmp_path / 'tmp.cst'
    template.write_text('x', encoding='utf-8')
    env = dict(os.environ)
    env['PYTHONPATH'] = _SRC + os.pathsep + env.get('PYTHONPATH', '')
    env['TPC_MCP_WORKDIR'] = str(tmp_path / 'svc')
    env['TPC_MCP_BACKEND'] = 'fake'
    env['PYTHONIOENCODING'] = 'utf-8'

    proc = subprocess.Popen(
        [sys.executable, '-m', 'cst_mcp'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=str(tmp_path), env=env, text=True, encoding='utf-8', bufsize=1)

    stdout_lines = []

    def _reader():
        for line in proc.stdout:
            stdout_lines.append(line)

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()
    try:
        requests = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
             'params': {'protocolVersion': '2025-06-18',
                        'capabilities': {},
                        'clientInfo': {'name': 'pytest', 'version': '0'}}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
             'params': {'name': 'get_capabilities', 'arguments': {}}},
        ]
        for request in requests:
            proc.stdin.write(json.dumps(request) + '\n')
        proc.stdin.flush()

        deadline = 30
        import time
        start = time.time()
        while len(stdout_lines) < 3 and time.time() - start < deadline:
            time.sleep(0.05)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:             # pragma: no cover
            proc.kill()
        reader.join(timeout=5)
        stderr = proc.stderr.read() if proc.stderr else ''

    assert stdout_lines, f'协议通道没有任何响应；stderr:\n{stderr[:2000]}'
    from cst_mcp.isolation import stdout_is_protocol_only
    assert stdout_is_protocol_only(stdout_lines), \
        f'stdout 混入非 JSON 内容：{stdout_lines[:5]}'

    replies = [json.loads(line) for line in stdout_lines if line.strip()]
    by_id = {r.get('id'): r for r in replies if 'id' in r}
    assert by_id[1]['result']['serverInfo']['name'] == SERVER_NAME
    assert len(by_id[2]['result']['tools']) == 11
    assert by_id[3]['result']['structuredContent']['ok'] is True


def test_print_inside_tool_goes_to_stderr(capsys):
    """工具里的 print 必须落在 stderr，不许污染协议通道。"""
    from cst_mcp.isolation import protocol_stdout

    with protocol_stdout():
        print('这条不该出现在 stdout')
    captured = capsys.readouterr()
    assert '这条不该出现在 stdout' not in captured.out
    assert '这条不该出现在 stdout' in captured.err
