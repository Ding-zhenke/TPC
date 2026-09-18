# -*- coding: utf-8 -*-
"""
真实 MCP **客户端**接入验证（计划 P3「真实 AI 客户端接入验证」）
================================================================

与 `test_protocol.py` 的区别
----------------------------
`test_protocol.py` 有两条通道：

* 大部分用例走 SDK 的**内存会话**（`create_connected_server_and_client_session`）；
* stdout 用例走真 stdio 子进程，但**手写 JSON-RPC 行**（只验协议通道干净）。

本文件补上缺的那一环：用 **SDK 自带的真客户端**（`mcp.client.stdio.stdio_client`
+ `mcp.ClientSession`）连到 **真 stdio 子进程** 上的 `python -m cst_mcp`，
走**完整客户端路径**（初始化协商 → 工具发现 → 调用 → 长任务轮询 → 产物获取 → 分析 → 报告），
即计划里说的「握手、工具发现、长任务轮询与产物获取的实际体验」。

覆盖（全部离线，用假后端，不是物理正确性证据）
-----------------------------------------------
| 计划要求 | 用例 |
|---|---|
| 握手 | `test_real_client_handshake` |
| 工具发现 | `test_real_client_discovers_all_tools` |
| 离线工具调用与结构化错误 | `test_real_client_calls_offline_tools` |
| 长任务轮询 | `test_real_client_long_task_polling` |
| 产物获取 / S 参数分析 / 报告 | `test_real_client_result_analysis_report_loop` |

⚠️ 这里验证的是**客户端接入与协议语义**；假后端产出的是**合成曲线**，
真机闭环仍属计划 P4/V9。
"""

import asyncio
import json
import os
import sys
import time

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, '..', 'src'))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from mcp import ClientSession, StdioServerParameters      # noqa: E402
from mcp.client.stdio import stdio_client                 # noqa: E402

from cst_mcp import __version__, tools                    # noqa: E402
from cst_mcp.server import SERVER_NAME                    # noqa: E402

_POLL_DEADLINE = 30.0


def _server_params(tmp_path):
    """起真 stdio 服务进程的参数（假后端 + 独立工作目录）。"""
    env = dict(os.environ)
    env['PYTHONPATH'] = _SRC + os.pathsep + env.get('PYTHONPATH', '')
    env['TPC_MCP_WORKDIR'] = str(tmp_path / 'svc')
    env['TPC_MCP_BACKEND'] = 'fake'
    env['PYTHONIOENCODING'] = 'utf-8'
    return StdioServerParameters(
        command=sys.executable, args=['-m', 'cst_mcp'],
        env=env, cwd=str(tmp_path))


def _template(tmp_path):
    path = tmp_path / 'tmp.cst'
    path.write_text('project-placeholder', encoding='utf-8')
    return path


def _spec(tmp_path):
    """直波导模型规格（与 README 走查示例同构）。"""
    return {'model': {'type': 'straight_waveguide'},
            'geometry': {'length': 18, 'topology': 'BA'},
            'output': {'template_cst': str(_template(tmp_path)),
                       'path': str(tmp_path / 'BA18.cst')}}


def with_client(scenario, tmp_path):
    """
    用真 stdio 客户端跑一个场景。

    :param scenario: callable(session, tmp_path) -> awaitable
    :param tmp_path: pytest 临时目录
    :return: 场景返回值
    """
    params = _server_params(tmp_path)
    _template(tmp_path)

    async def runner():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await scenario(session, tmp_path)

    return asyncio.run(runner())


async def _payload(result):
    """把 CallToolResult 归一成结构化 dict。"""
    if result.structuredContent is not None:
        return result.structuredContent
    if result.content:
        return json.loads(result.content[0].text)
    return {}


# ============================================================
# 握手 / 工具发现
# ============================================================

def test_real_client_handshake(tmp_path):
    """真客户端 initialize：服务名/版本/协议版本与工具能力都要协商成功。"""
    async def scenario(session, _tmp):
        return await session.initialize()

    result = with_client(scenario, tmp_path)
    assert result.serverInfo.name == SERVER_NAME
    assert result.serverInfo.version == __version__
    assert result.capabilities.tools is not None
    assert result.protocolVersion


def test_real_client_discovers_all_tools(tmp_path):
    """真客户端 tools/list：11 个工具，且每个都有描述与对象型入参 schema。"""
    async def scenario(session, _tmp):
        return await session.list_tools()

    result = with_client(scenario, tmp_path)
    names = [tool.name for tool in result.tools]
    assert names == tools.tool_names()
    assert len(names) == 11
    for tool in result.tools:
        assert tool.description
        assert tool.inputSchema['type'] == 'object'


# ============================================================
# 离线工具与结构化错误
# ============================================================

def test_real_client_calls_offline_tools(tmp_path):
    """
    真客户端调用三个**不启动 CST** 的工具：
    `get_capabilities`（能力）、`list_templates`（字段/单位/默认值）、
    `validate_model_spec`（离线预检：合法通过、非法给出结构化错误码）。
    """
    async def scenario(session, tmp):
        caps = await _payload(await session.call_tool('get_capabilities', {}))
        templates = await _payload(await session.call_tool(
            'list_templates', {'model_type': 'straight_waveguide'}))
        good = await _payload(await session.call_tool(
            'validate_model_spec', {'spec': _spec(tmp)}))
        bad_result = await session.call_tool(
            'validate_model_spec',
            {'spec': {'model': {'type': 'straight_waveguide'},
                      'geometry': {'length': 'eighteen'}}})
        return caps, templates, good, bad_result.isError, await _payload(bad_result)

    caps, templates, good, bad_is_error, bad = with_client(scenario, tmp_path)
    assert caps['ok'] is True
    assert caps['backend'] == 'fake'
    assert 'cst' in caps

    assert templates['ok'] is True
    assert templates['templates']
    straight = [t for t in templates['templates']
                if t.get('model_type') == 'straight_waveguide']
    assert straight and straight[0]['buildable'] is True
    assert straight[0]['fields']

    assert good['ok'] is True
    assert good['valid'] is True
    # 离线预检不创建 DE：CST 相关检查必须是「未探测/跳过」而不是真的连过 CST
    checks = {c['name']: c for c in good['checks']}
    assert 'cst_availability' in checks
    assert checks['cst_availability']['status'] != 'failed'
    assert all(c['status'] != 'failed' for c in good['checks'])

    assert bad_is_error is True
    assert bad['ok'] is False
    assert bad['error']['code']
    assert bad['error']['retryable'] in (True, False)


# ============================================================
# 长任务轮询
# ============================================================

def test_real_client_long_task_polling(tmp_path):
    """建模是异步长任务：客户端提交 → 轮询 get_job_status 直到终态。"""
    async def scenario(session, tmp):
        build = await _payload(await session.call_tool(
            'build_model', {'spec': _spec(tmp), 'request_id': 'client-1'}))
        assert build['job_id']
        job_id = build['job_id']
        deadline = time.time() + _POLL_DEADLINE
        status = None
        while time.time() < deadline:
            status = await _payload(await session.call_tool(
                'get_job_status', {'job_id': job_id}))
            if status['status'] in ('succeeded', 'failed', 'interrupted'):
                break
            await asyncio.sleep(0.2)
        return job_id, status

    job_id, status = with_client(scenario, tmp_path)
    assert status is not None, '轮询超时，任务一直没到终态'
    assert status['job_id'] == job_id
    assert status['status'] == 'succeeded'
    assert status['finished_at']


def test_real_client_result_analysis_report_loop(tmp_path):
    """
    闭环（离线、假后端）：建模 → 求解 → 取结果产物 → 分析 S 参数 → 出 HTML/CSV 报告，
    并核对产物确实是**文件**（大结果走产物引用，不回整条曲线）。

    ⚠️ 求解出来的是**合成曲线**（假后端写的 `fake_sparams_*.csv`，S11 在 330 GHz 附近
    下探到约 −17 dB），只用于验证闭环能力，不是物理结论。
    """
    async def poll(session, job_id):
        deadline = time.time() + _POLL_DEADLINE
        status = None
        while time.time() < deadline:
            status = await _payload(await session.call_tool(
                'get_job_status', {'job_id': job_id}))
            if status['status'] in ('succeeded', 'failed', 'interrupted'):
                return status
            await asyncio.sleep(0.2)
        return status

    async def scenario(session, tmp):
        build = await _payload(await session.call_tool(
            'build_model', {'spec': _spec(tmp), 'request_id': 'client-loop'}))
        build_status = await poll(session, build['job_id'])
        assert build_status['status'] == 'succeeded'

        state = await _payload(await session.call_tool('get_project_state', {}))
        assert state['projects'], '建模后工程没有被注册'
        project_id = state['projects'][0]['project_id']

        solve = await _payload(await session.call_tool(
            'run_simulation', {'project_id': project_id,
                               'request_id': 'client-loop-solve'}))
        solve_status = await poll(session, solve['job_id'])
        assert solve_status['status'] == 'succeeded', solve_status

        results = await _payload(await session.call_tool(
            'get_results', {'job_id': solve['job_id']}))
        assert results['ok'] is True
        assert results['artifacts']

        analysis = await _payload(await session.call_tool(
            'analyze_s_parameters',
            {'job_id': solve['job_id'], 'threshold_db': -10.0,
             'criterion': 'below', 'metric': 'S1,1',
             'resonance_kind': 'min'}))

        report = await _payload(await session.call_tool(
            'export_report',
            {'job_id': solve['job_id'], 'threshold_db': -10.0,
             'metric': 'S1,1', 'formats': ['html', 'csv'],
             'title': '客户端闭环测试'}))
        return results, analysis, report

    results, analysis, report = with_client(scenario, tmp_path)
    # 分析结果：合成曲线在 330 GHz 附近下探，阈值 −10 dB 应给出一段合格带
    assert analysis['ok'] is True
    detail = analysis['analysis']
    assert detail['metric'] == 'S1,1'
    assert detail['criterion']['threshold_db'] == -10.0
    assert detail['n_points'] == 81
    assert detail['n_bands'] >= 1
    assert detail['bands'][0]['best_freq_ghz'] == 330.0

    assert report['ok'] is True
    files = report['artifacts']
    assert len(files) >= 2                                    # HTML + CSV
    kinds = {item['kind'] for item in files}
    assert {'html', 'csv'} <= kinds
    for item in files:
        assert os.path.isfile(item['path']), f"报告产物不存在：{item['path']}"
    # 报告要能自查数据来源：说清是假后端的合成曲线，不能冒充仿真结论
    blob = json.dumps(report, ensure_ascii=False).lower()
    assert 'fake' in blob or '合成' in blob
    assert report['summary']['csv_rows'] == 82                # 81 点 + 表头


# ============================================================
# 失败路径也走真客户端
# ============================================================

def test_real_client_unknown_tool_is_structured_error(tmp_path):
    """未知工具在真客户端里也必须是结构化错误结果，而不是断连接。"""
    async def scenario(session, _tmp):
        return await session.call_tool('no_such_tool', {})

    result = with_client(scenario, tmp_path)
    assert result.isError is True
    payload = json.loads(result.content[0].text)
    assert payload['error']['code'] == 'unknown_tool'
