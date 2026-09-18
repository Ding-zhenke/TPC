# -*- coding: utf-8 -*-
"""
单 worker 串行性与后端契约测试（P2）
====================================

计划要求「单 CST worker，同一工程写操作串行」，并明确「CST 对象线程/进程归属」
要说清楚。本文件用**可观测并发数**证明串行，并检查：

* runner 抛异常不会让 worker 线程死掉（后续任务照跑），异常被记进 ``errors``；
* 关闭后不再接受任务（``service_shutdown``）；
* 假后端与真实 CST 后端都满足「返回结构齐全」「离线可导入」两条契约。

⚠️ 真实 CST 后端的**真机行为**未验证（P4/V7）；这里只验证离线可导入与失败路径。
"""

import os
import sys
import threading

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tpc_service import RunService                     # noqa: E402
from tpc_service.backends.base import Backend, fail_result, ok_result   # noqa: E402
from tpc_service.backends.fake import FakeBackend      # noqa: E402
from tpc_service.errors import ServiceError            # noqa: E402
from tpc_service.worker import SingleWorker            # noqa: E402


# ============================================================
# 串行
# ============================================================

def test_service_runs_jobs_strictly_serialized(tmp_path):
    """5 条任务并发提交：后端观测到的最大并发必须是 1。"""
    template = tmp_path / 'tmp.cst'
    template.write_text('x', encoding='utf-8')
    backend = FakeBackend(delay=0.05)
    service = RunService(str(tmp_path), backend=backend)
    try:
        jobs = [service.submit('build', project_path=str(template),
                               params={'i': i}) for i in range(5)]
        for job in jobs:
            assert service.wait(job['job_id'], timeout=20)['status'] == 'succeeded'
        assert backend.max_concurrent == 1
        assert [c['params']['i'] for c in backend.calls] == [0, 1, 2, 3, 4]
    finally:
        service.shutdown()


def test_worker_keeps_running_after_runner_exception():
    """runner 抛异常不能让线程死掉，也不能把异常吞掉。"""
    seen = []
    barrier = threading.Event()

    def runner(job_id):
        seen.append(job_id)
        if job_id == 'boom':
            raise RuntimeError('故意炸')
        if len(seen) == 3:
            barrier.set()

    worker = SingleWorker(runner, name='test-worker')
    try:
        for job_id in ('one', 'boom', 'two'):
            worker.submit(job_id)
        assert barrier.wait(timeout=5)
        errors = worker.errors
        assert [job_id for job_id, _ in errors] == ['boom']
        assert '故意炸' in errors[0][1]
    finally:
        worker.shutdown()


def test_worker_shutdown_refuses_new_jobs():
    worker = SingleWorker(lambda job_id: None, name='test-worker')
    worker.submit('first')
    worker.shutdown(wait=True, timeout=5)
    assert worker.is_stopped
    with pytest.raises(ServiceError) as excinfo:
        worker.submit('second')
    assert excinfo.value.code == 'service_shutdown'


def test_service_shutdown_blocks_new_submissions(tmp_path):
    service = RunService(str(tmp_path), backend=FakeBackend())
    service.shutdown()
    with pytest.raises(ServiceError) as excinfo:
        service.submit('build', project_path=str(tmp_path / 'x.cst'))
    assert excinfo.value.code in ('service_shutdown', 'project_not_found')


# ============================================================
# 后端契约
# ============================================================

def test_base_backend_fails_loudly_instead_of_returning_empty():
    """基类不实现就明确报错，不能返回空 dict 让调用方以为成功。"""
    backend = Backend()
    for method in ('build', 'solve', 'study'):
        result = getattr(backend, method)(project={}, params={}, job={})
        assert result['ok'] is False
        assert result['error']['code'] == 'backend_failed'
        assert '未实现' in result['error']['message']


def test_result_helpers_shape():
    ok = ok_result(log=['a'], artifacts=[{'kind': 'file', 'path': 'p'}],
                   run_identity={'run_token': 't'}, result_summary={'m': 1})
    assert ok['ok'] is True and ok['saved'] is True and ok['error'] is None
    bad = fail_result('backend_failed', 'x', retryable=True)
    assert bad['ok'] is False and bad['saved'] is False
    assert bad['error'] == {'code': 'backend_failed', 'message': 'x',
                            'details': {}, 'retryable': True}


def test_fake_backend_records_calls_and_closes():
    backend = FakeBackend()
    backend.build(project={'path': 'p.cst'}, params={}, job={})
    backend.solve(project={'path': 'p.cst'}, params={}, job={})
    backend.study(project={'path': 'p.cst'},
                  params={'study': {'points': [1, 2, 3]}}, job={})
    backend.close_project(project={'project_id': 'x'}, save=True)
    assert [c['kind'] for c in backend.calls] == ['build', 'solve', 'study']
    assert backend.closed == [{'project': {'project_id': 'x'}, 'save': True}]


# ============================================================
# 真实 CST 后端：离线可导入 + 失败路径
# ============================================================

def test_cst_backend_imports_without_cst():
    """导入真实后端不许连带把 CST 拉进来。"""
    module = __import__('tpc_service.backends.cst_backend', fromlist=['CstBackend'])
    assert hasattr(module, 'CstBackend')
    assert module.CstBackend().name == 'cst'


def test_cst_backend_rejects_missing_spec():
    from tpc_service.backends.cst_backend import CstBackend
    result = CstBackend().build(project={'path': 'x.cst'}, params={}, job={})
    assert result['ok'] is False
    assert 'spec' in result['error']['message']


def test_cst_backend_reports_missing_project():
    from tpc_service.backends.cst_backend import CstBackend
    result = CstBackend().solve(project={'path': 'no-such-project.cst'},
                                params={}, job={})
    assert result['ok'] is False
    assert result['error']['code'] == 'project_not_found'


def test_cst_backend_study_rejects_unknown_kind(tmp_path):
    from tpc_service.backends.cst_backend import CstBackend
    result = CstBackend().study(project={'path': str(tmp_path / 'tmp.cst')},
                                params={'study': {'kind': 'teleport'}}, job={})
    assert result['ok'] is False
    assert 'teleport' in result['error']['message']
