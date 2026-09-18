# -*- coding: utf-8 -*-
"""
任务状态机与记录测试（P2）
==========================

守住 `docs/next_plan/README.md` P2 里最容易写坏的三件事：
状态词表、**终态不可回退**、以及「同一请求换种写法重发不算冲突」的稳定摘要。
"""

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tpc_service.errors import ServiceError            # noqa: E402
from tpc_service.state import (                        # noqa: E402
    JOB_KINDS,
    JOB_STATUSES,
    TERMINAL_STATUSES,
    JobRecord,
    can_transition,
    params_digest,
)


def test_status_vocabulary_matches_the_plan():
    """状态词表必须与 cst_mcp.md §4 / 计划一致。"""
    assert JOB_STATUSES == ('queued', 'running', 'succeeded', 'failed',
                            'interrupted')
    assert TERMINAL_STATUSES == ('succeeded', 'failed', 'interrupted')
    assert JOB_KINDS == ('build', 'solve', 'study')


def test_params_digest_is_order_and_format_independent():
    """字典顺序/嵌套不影响摘要 —— 否则同 ID 重发会被误判成冲突。"""
    a = {'geometry': {'length': 18, 'topology': 'BA'}, 'solver': {'fmin': 300}}
    b = {'solver': {'fmin': 300}, 'geometry': {'topology': 'BA', 'length': 18}}
    assert params_digest(a) == params_digest(b)
    assert params_digest(a) != params_digest({'geometry': {'length': 19}})
    assert len(params_digest(a)) == 64


def test_transition_matrix():
    assert can_transition('queued', 'running')
    assert can_transition('queued', 'interrupted')
    assert can_transition('running', 'succeeded')
    assert can_transition('running', 'failed')
    assert can_transition('running', 'interrupted')
    for terminal in TERMINAL_STATUSES:
        for target in JOB_STATUSES:
            assert not can_transition(terminal, target)


def test_terminal_state_cannot_move_again():
    """终态不可再迁移：宁可炸，也不写坏记录。"""
    record = JobRecord(job_id='j1', kind='solve')
    record.transition('running', at='t1')
    record.transition('succeeded', at='t2')
    assert record.is_terminal
    with pytest.raises(ServiceError) as excinfo:
        record.transition('failed', at='t3')
    assert excinfo.value.code == 'invalid_transition'


def test_records_timestamps_and_error():
    record = JobRecord(job_id='j2', kind='solve')
    record.transition('running', at='2026-09-17T00:00:00+00:00')
    assert record.started_at == '2026-09-17T00:00:00+00:00'
    error = {'code': 'backend_failed', 'message': 'x', 'details': {},
             'retryable': True}
    record.transition('failed', at='2026-09-17T00:01:00+00:00', error=error)
    assert record.finished_at == '2026-09-17T00:01:00+00:00'
    assert record.error == error
    assert record.is_terminal


def test_digest_is_filled_automatically():
    record = JobRecord(job_id='j3', kind='build', params={'a': 1})
    assert record.params_digest == params_digest({'a': 1})


def test_json_roundtrip_ignores_unknown_keys():
    record = JobRecord(job_id='j4', kind='study', params={'x': [1, 2]})
    record.note('hello')
    record.add_artifact('D:/w/x.cst', kind='project', note='n')
    data = record.to_dict()
    data['future_field'] = 'ignored'
    restored = JobRecord.from_dict(data)
    assert restored.job_id == 'j4'
    assert restored.log == ['hello']
    assert restored.artifacts[0]['kind'] == 'project'
    assert restored.params_digest == record.params_digest
