# -*- coding: utf-8 -*-
r"""
P2↔P3 衔接：**真实 `CstBackend` 的错误码必须原样到达客户端**（P3 契约）
=====================================================================

为什么单独有这个文件
--------------------
`tests/test_tools.py` 走的是**假后端**（`FakeBackend`）—— 它验证协议与工具语义，
但**绕过了真实后端**。而计划里 P2↔P3 的硬要求是「底层错误码**原样透传，不重编号**」，
链路上有三层：`cst_solver`（运行契约）→ `tpc_service`（任务/结构化错误）→ `cst_mcp`（客户端）。

本文件把这条链**整条跑通**，只在 **CST 边界**打桩（`cst_solver.setup` 等），
其余全是真实现：真 `CstBackend`、真 `RunService`、真工具、真协议会话。

⚠️ 不碰 CST：所有会开设计环境的调用都被替身替换；这里验证的是**错误传播**，
不是物理解算（真机闭环属计划 P4/V7/V9）。
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

from mcp.shared.memory import (          # noqa: E402
    create_connected_server_and_client_session,
)

from cst_mcp import runtime, tools                    # noqa: E402
from cst_mcp.server import build_server               # noqa: E402
from tpc_service.backends.cst_backend import CstBackend   # noqa: E402
from tpc_service.errors import ERROR_CODES            # noqa: E402

_POLL_DEADLINE = 20.0
_SPEC = {'model': {'type': 'straight_waveguide'},
         'geometry': {'length': 18, 'topology': 'BA'}}


# ============================================================
# 环境与替身
# ============================================================

@pytest.fixture
def env(tmp_path):
    template = tmp_path / 'tmp.cst'
    template.write_text('project-placeholder', encoding='utf-8')
    runtime.reset()
    runtime.configure(workdir=str(tmp_path / 'svc'), backend=CstBackend())
    yield {'work': tmp_path, 'template': template}
    runtime.get_service().shutdown()
    runtime.reset()


def _run(coro):
    return asyncio.run(coro)


async def _payload(result):
    if result.structuredContent is not None:
        return result.structuredContent
    if result.content:
        return json.loads(result.content[0].text)
    return {}


async def _call(session, name, arguments=None):
    result = await session.call_tool(name, arguments or {})
    return result.isError, await _payload(result)


async def _wait_terminal(session, job_id):
    """轮询到终态（真实服务 + 真后端，任务在 worker 线程里跑）。"""
    deadline = time.time() + _POLL_DEADLINE
    payload = {}
    while time.time() < deadline:
        _, payload = await _call(session, 'get_job_status', {'job_id': job_id})
        if payload.get('status') in ('succeeded', 'failed', 'interrupted'):
            return payload
        await asyncio.sleep(0.1)
    return payload


def _patch_preflight(monkeypatch, report):
    import topo_modeler.preflight as preflight
    monkeypatch.setattr(preflight, 'validate_model_spec', lambda spec, **kw: report)


def _ok_preflight():
    return {'ok': True, 'valid': True, 'model_type': 'straight_waveguide',
            'errors': [], 'warnings': [], 'ctor_kwargs': {'length': 18}}


def _submit_and_check(scenario, env):
    async def runner():
        async with create_connected_server_and_client_session(build_server()) as session:
            await session.initialize()
            return await scenario(session)

    return _run(runner())


# ============================================================
# 1. 建模：预检失败 → 码原样到客户端
# ============================================================

def test_build_preflight_failure_reaches_client_unchanged(env, monkeypatch):
    _patch_preflight(monkeypatch, {
        'ok': False, 'valid': False, 'model_type': 'straight_waveguide',
        'warnings': [],
        'errors': [{'code': 'config_value_out_of_range',
                    'message': 'geometry.length 超出取值范围'}]})

    async def scenario(session):
        is_error, submitted = await _call(session, 'build_model', {
            'spec': dict(_SPEC, output={'template_cst': str(env['template'])})})
        assert is_error is False, submitted          # 提交成功（任务异步）
        status = await _wait_terminal(session, submitted['job_id'])
        results_error, results = await _call(
            session, 'get_results', {'job_id': submitted['job_id']})
        return status, results_error, results

    status, results_error, results = _submit_and_check(scenario, env)
    assert status['status'] == 'failed'
    assert status['error']['code'] == 'config_value_out_of_range'
    # 取结果必须是**结构化错误**（不是空数据），且码一致
    assert results_error is True
    assert results['error']['code'] == 'config_value_out_of_range'


# ============================================================
# 2. 建模：产物逃出工作目录 → workdir_escape 原样透传
# ============================================================

def test_build_workdir_escape_is_not_renumbered(env, monkeypatch, tmp_path):
    """`CstBackend.build` 抛 `ServiceError('workdir_escape')` ⇒ 客户端看到同一个码。"""
    _patch_preflight(monkeypatch, _ok_preflight())
    outside = str(tmp_path / 'outside.cst')          # 服务工作目录是 tmp/service_*

    async def scenario(session):
        _, submitted = await _call(session, 'build_model', {
            'spec': dict(_SPEC, output={'template_cst': str(env['template'])}),
            'output': outside})
        return await _wait_terminal(session, submitted['job_id'])

    status = _submit_and_check(scenario, env)
    assert status['status'] == 'failed'
    assert status['error']['code'] == 'workdir_escape'
    assert status['error']['code'] in ERROR_CODES    # 服务层码表里的码


# ============================================================
# 3. 求解：运行契约失败 → run_messages 原样透传，且**绝不保存**
# ============================================================

def test_solve_run_contract_failure_reaches_client(env, monkeypatch, tmp_path):
    project = tmp_path / 'proj.cst'
    project.write_text('placeholder', encoding='utf-8')
    calls = []

    class _App:
        def run_checked(self, **kwargs):
            calls.append('run_checked')
            return {'status': 'failed', 'run_token': 'tok-x', 'messages': ['收敛失败'],
                    'errors': [{'code': 'run_messages',
                                'message': '提交后 CST 有失败消息'}]}

        def save(self, path):
            calls.append('save')
            return path

        def close(self):
            calls.append('close')

    import cst_solver
    monkeypatch.setattr(cst_solver, 'setup', lambda path: _App())

    async def scenario(session):
        _, submitted = await _call(session, 'run_simulation',
                                   {'project_path': str(project)})
        status = await _wait_terminal(session, submitted['job_id'])
        results_error, results = await _call(
            session, 'get_results', {'job_id': submitted['job_id']})
        return status, results_error, results

    status, results_error, results = _submit_and_check(scenario, env)
    assert status['status'] == 'failed'
    assert status['error']['code'] == 'run_messages'          # 底层码，未重编号
    assert status['error']['details']['run_identity']['run_token'] == 'tok-x'
    assert results_error is True
    assert results['error']['code'] == 'run_messages'
    # 「先保存再读」的反面：运行契约没判成功，就**不能**保存、也不读结果
    assert calls == ['run_checked', 'close']


# ============================================================
# 4. 求解：工程在工作副本被删掉 → project_not_found
# ============================================================

def test_solve_missing_working_copy_reports_project_not_found(env, monkeypatch):
    service = runtime.get_service()
    source = env['work'] / 'gone.cst'
    source.write_text('placeholder', encoding='utf-8')
    record = service.open_project(str(source))
    os.remove(record['path'])                        # 删掉工作副本

    import cst_solver
    opened = []
    monkeypatch.setattr(cst_solver, 'setup', lambda path: opened.append(path))

    async def scenario(session):
        _, submitted = await _call(session, 'run_simulation',
                                   {'project_id': record['project_id']})
        return await _wait_terminal(session, submitted['job_id'])

    status = _submit_and_check(scenario, env)
    assert status['status'] == 'failed'
    assert status['error']['code'] == 'project_not_found'
    assert opened == []                              # 连会话都没开


# ============================================================
# 5. 后端抛异常 → backend_failed（可重试），且消息保留原因
# ============================================================

def test_backend_exception_is_reported_as_retryable_backend_failed(env, monkeypatch,
                                                                  tmp_path):
    project = tmp_path / 'boom.cst'
    project.write_text('placeholder', encoding='utf-8')

    import cst_solver

    def boom(path):
        raise RuntimeError('CST 接口不可用（模拟）')

    monkeypatch.setattr(cst_solver, 'setup', boom)

    async def scenario(session):
        _, submitted = await _call(session, 'run_simulation',
                                   {'project_path': str(project)})
        return await _wait_terminal(session, submitted['job_id'])

    status = _submit_and_check(scenario, env)
    assert status['status'] == 'failed'
    error = status['error']
    assert error['code'] == 'backend_failed'
    assert error['retryable'] is True
    assert 'RuntimeError' in error['message']


# ============================================================
# 6. 客户端侧：能力报告必须如实说明「真机后端未被验证过」
# ============================================================

def test_capabilities_flag_unverified_real_backend(env):
    async def scenario(session):
        _, payload = await _call(session, 'get_capabilities')
        return payload

    payload = _submit_and_check(scenario, env)
    assert payload['backend'] == 'cst'
    # 真后端下必须**按任务种类**如实标注：建模已真机验证，求解/study 尚未
    verified = payload['limits']['real_cst_backend_verified']
    assert verified['build'] is True
    assert verified['solve'] is False and verified['study'] is False
    # 运行中任务的取消仍是不支持（停止语义要在运行中的求解里才能观测），
    # 不能在文档之外偷偷"支持"
    assert 'cancel_running_job' in payload['limits']
    assert tools.tool_names() == payload['tools']
