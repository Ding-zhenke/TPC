# -*- coding: utf-8 -*-
"""
RunService 行为测试（P2 验收）
==============================

计划要求「可注入假后端覆盖**失败、重复请求、竞争、重启中断、旧结果和清理**」。
本文件逐条覆盖（竞争/串行在 `test_worker_serial.py`）：

* 失败：后端抛异常 / 返回结构化失败 / 求解未确认保存 ⇒ 一律 `failed`；
* 重复请求：同 request_id 同参数 ⇒ 返回既有任务且**不再执行一次**；
* 冲突：同 request_id 不同参数 ⇒ `request_id_conflict`；
* 重启中断：磁盘上未完成的任务 ⇒ `interrupted` + `service_restarted`，**不自动重跑**；
* 旧结果：假后端标记 `stale=True` 时，摘要如实带出，不会假装是新的；
* 清理：只关闭自有会话；取消只对未开始的任务生效。

⚠️ 全部离线（假后端），真机判据属计划 P4/V7。
"""

import json
import os
import sys
import time

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tpc_service import RunService                     # noqa: E402
from tpc_service.backends.fake import FakeBackend      # noqa: E402
from tpc_service.errors import ServiceError            # noqa: E402
from tpc_service.state import JobRecord                # noqa: E402
from tpc_service.store import JobStore                 # noqa: E402


@pytest.fixture()
def work(tmp_path):
    """带一个假模板工程的临时工作目录。"""
    template = tmp_path / 'tmp.cst'
    template.write_text('project-placeholder', encoding='utf-8')
    return tmp_path


@pytest.fixture()
def service(work):
    backend = FakeBackend()
    svc = RunService(str(work), backend=backend)
    yield svc
    svc.shutdown()


# ============================================================
# 基本流程
# ============================================================

def test_build_job_end_to_end(service, work):
    job = service.submit('build', project_path=str(work / 'tmp.cst'),
                         params={'spec': {'model': {'type': 'straight_waveguide'}}})
    assert job['status'] == 'queued'
    finished = service.wait(job['job_id'], timeout=10)
    assert finished['status'] == 'succeeded'
    assert finished['error'] is None
    assert finished['started_at'] and finished['finished_at']
    assert finished['log']
    assert finished['artifacts']
    assert finished['params_digest'] == job['params_digest']


def test_get_unknown_job(service):
    with pytest.raises(ServiceError) as excinfo:
        service.get('job-nope')
    assert excinfo.value.code == 'unknown_job'


def test_unknown_kind_is_rejected_before_anything_runs(service, work):
    with pytest.raises(ServiceError) as excinfo:
        service.submit('explode', project_path=str(work / 'tmp.cst'))
    assert excinfo.value.code == 'unknown_job_kind'
    assert service.backend.calls == []


# ============================================================
# 失败路径
# ============================================================

def test_backend_exception_becomes_failed_job(work):
    service = RunService(str(work), backend=FakeBackend(fail_on={'build'}))
    try:
        job = service.submit('build', project_path=str(work / 'tmp.cst'))
        done = service.wait(job['job_id'], timeout=10)
        assert done['status'] == 'failed'
        assert done['error']['code'] == 'backend_failed'
        assert '故意抛异常' in done['error']['message']
    finally:
        service.shutdown()


def test_backend_structured_failure_is_preserved(work):
    service = RunService(str(work), backend=FakeBackend(fail_result_on={'build'}))
    try:
        job = service.submit('build', project_path=str(work / 'tmp.cst'))
        done = service.wait(job['job_id'], timeout=10)
        assert done['status'] == 'failed'
        assert done['error']['retryable'] is True
    finally:
        service.shutdown()


def test_solve_without_confirmed_save_fails(work):
    """计划要求：保存求解后的结果再交给读取器 —— 没确认保存就不能算成功。"""
    service = RunService(str(work), backend=FakeBackend(confirm_save=False))
    try:
        job = service.submit('solve', project_path=str(work / 'tmp.cst'))
        done = service.wait(job['job_id'], timeout=10)
        assert done['status'] == 'failed'
        assert '已保存' in done['error']['message']
    finally:
        service.shutdown()


def test_stale_results_are_flagged_not_hidden(work):
    """旧结果必须如实带出（调用方要能看出「这不是本轮结果」）。"""
    service = RunService(str(work), backend=FakeBackend(stale=True))
    try:
        job = service.submit('solve', project_path=str(work / 'tmp.cst'))
        done = service.wait(job['job_id'], timeout=10)
        assert done['status'] == 'succeeded'
        assert done['result_summary']['stale'] is True
    finally:
        service.shutdown()


# ============================================================
# 重复请求与冲突
# ============================================================

def test_duplicate_request_returns_existing_job_without_rerunning(service, work):
    params = {'spec': {'model': {'type': 'straight_waveguide'}}}
    first = service.submit('build', project_path=str(work / 'tmp.cst'),
                           params=params, request_id='req-1')
    service.wait(first['job_id'], timeout=10)
    calls = len(service.backend.calls)

    again = service.submit('build', project_id=first['project_id'],
                           params=params, request_id='req-1')
    assert again['duplicate'] is True
    assert again['job_id'] == first['job_id']
    assert len(service.backend.calls) == calls        # 没有再执行一次


def test_same_request_id_with_different_params_conflicts(service, work):
    first = service.submit('build', project_path=str(work / 'tmp.cst'),
                           params={'spec': {'geometry': {'length': 18}}},
                           request_id='req-2')
    service.wait(first['job_id'], timeout=10)
    with pytest.raises(ServiceError) as excinfo:
        service.submit('build', project_id=first['project_id'],
                       params={'spec': {'geometry': {'length': 20}}},
                       request_id='req-2')
    assert excinfo.value.code == 'request_id_conflict'
    assert excinfo.value.details['existing_job_id'] == first['job_id']


def test_equivalent_params_do_not_conflict(service, work):
    """换一种等价的写法（键顺序不同）不该被判成冲突。"""
    first = service.submit('build', project_path=str(work / 'tmp.cst'),
                           params={'a': 1, 'b': {'c': 2}}, request_id='req-3')
    service.wait(first['job_id'], timeout=10)
    again = service.submit('build', project_id=first['project_id'],
                           params={'b': {'c': 2}, 'a': 1}, request_id='req-3')
    assert again['duplicate'] is True


# ============================================================
# 重启中断
# ============================================================

def test_recover_marks_unfinished_jobs_interrupted_without_rerunning(work):
    store = JobStore(str(work)).ensure()
    running = JobRecord(job_id='job-left-running', kind='solve', status='running',
                        created_at='2026-09-17T00:00:00+00:00')
    queued = JobRecord(job_id='job-left-queued', kind='build', status='queued',
                       created_at='2026-09-17T00:00:01+00:00')
    done = JobRecord(job_id='job-done', kind='build', status='succeeded',
                     created_at='2026-09-17T00:00:02+00:00')
    for record in (running, queued, done):
        store.save(record)

    backend = FakeBackend()
    service = RunService(str(work), backend=backend)     # recover=True 默认
    try:
        assert sorted(service.recovery['interrupted']) == ['job-left-queued',
                                                           'job-left-running']
        assert service.get('job-left-running')['status'] == 'interrupted'
        assert service.get('job-left-running')['error']['code'] == 'service_restarted'
        assert service.get('job-left-queued')['status'] == 'interrupted'
        assert service.get('job-done')['status'] == 'succeeded'   # 终态不动
        assert backend.calls == []                       # ← 没有自动重跑
    finally:
        service.shutdown()


def test_history_survives_restart(work):
    service = RunService(str(work), backend=FakeBackend())
    job = service.submit('build', project_path=str(work / 'tmp.cst'))
    service.wait(job['job_id'], timeout=10)
    service.shutdown()

    reopened = RunService(str(work), backend=FakeBackend())
    try:
        history = {item['job_id']: item for item in reopened.list_jobs()}
        assert history[job['job_id']]['status'] == 'succeeded'
    finally:
        reopened.shutdown()


# ============================================================
# 取消与清理
# ============================================================

def test_cancel_queued_job_really_cancels(work):
    service = RunService(str(work), backend=FakeBackend(), autostart=False)
    try:
        job = service.submit('build', project_path=str(work / 'tmp.cst'))
        assert job['status'] == 'queued'
        cancelled = service.cancel(job['job_id'])
        assert cancelled['status'] == 'interrupted'
        assert cancelled['error']['code'] == 'cancelled_before_start'
    finally:
        service.shutdown(wait=False)


def test_cancel_running_job_is_refused_not_faked(work):
    """计划：未验证前不提供虚假的「已取消」。"""
    service = RunService(str(work), backend=FakeBackend(delay=0.4))
    try:
        job = service.submit('build', project_path=str(work / 'tmp.cst'))
        deadline = time.time() + 5
        while time.time() < deadline and service.get(job['job_id'])['status'] != 'running':
            time.sleep(0.02)
        assert service.get(job['job_id'])['status'] == 'running'
        with pytest.raises(ServiceError) as excinfo:
            service.cancel(job['job_id'])
        assert excinfo.value.code == 'cancel_not_supported'
    finally:
        service.shutdown()


def test_close_project_uses_ownership_rules(work):
    backend = FakeBackend()
    service = RunService(str(work), backend=backend)
    other = work / 'other.cst'
    other.write_text('project-placeholder', encoding='utf-8')
    try:
        owned = service.open_project(str(work / 'tmp.cst'), session=object(),
                                     session_owned=True)
        external = service.open_project(str(other), session=object(),
                                        session_owned=False)
        result = service.close_project(owned['project_id'])
        assert result['closed_session'] is True
        assert len(backend.closed) == 1
        result_external = service.close_project(external['project_id'])
        assert result_external['closed_session'] is False
        assert len(backend.closed) == 1               # 外部会话没被关
    finally:
        service.shutdown()


def test_describe_and_results_are_json_serializable(service, work):
    job = service.submit('solve', project_path=str(work / 'tmp.cst'))
    service.wait(job['job_id'], timeout=10)
    json.dumps(service.describe(), ensure_ascii=False)
    payload = service.result(job['job_id'])
    json.dumps(payload, ensure_ascii=False)
    assert payload['result_summary']['S1,1_min_db'] == -18.5
    assert payload['run_identity']['run_id'] == 0
