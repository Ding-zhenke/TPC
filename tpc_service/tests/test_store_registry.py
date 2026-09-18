# -*- coding: utf-8 -*-
"""
持久化与工程注册测试（P2）
==========================

守住三件事：

1. **工作目录约束**：「产物写到别处」必须直接失败（``workdir_escape``）；
2. **副本/覆盖策略**：默认复制、默认**不覆盖**，就地执行必须显式声明；
3. **会话归属**：只关闭服务自己创建的会话，外部会话只解除注册。

外加一条容易被忽略的：**读不出来的历史记录不能被静默丢掉**。
"""

import json
import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tpc_service.errors import ServiceError            # noqa: E402
from tpc_service.registry import ProjectRegistry, copy_project   # noqa: E402
from tpc_service.state import JobRecord                # noqa: E402
from tpc_service.store import JobStore, ensure_within, is_within   # noqa: E402


# ============================================================
# 工作目录约束
# ============================================================

def test_ensure_within_accepts_inside(tmp_path):
    inside = tmp_path / 'a' / 'b.cst'
    assert ensure_within(str(tmp_path), str(inside)) == os.path.abspath(inside)


def test_ensure_within_rejects_escape(tmp_path):
    outside = tmp_path.parent / 'elsewhere.cst'
    with pytest.raises(ServiceError) as excinfo:
        ensure_within(str(tmp_path), str(outside))
    assert excinfo.value.code == 'workdir_escape'
    assert is_within(str(tmp_path), str(outside)) is False


# ============================================================
# 任务持久化
# ============================================================

def test_store_roundtrip_and_events(tmp_path):
    store = JobStore(str(tmp_path)).ensure()
    record = JobRecord(job_id='j1', kind='build', params={'a': 1},
                       created_at='2026-09-17T00:00:00+00:00')
    path = store.save(record)
    assert os.path.exists(path)
    store.append_event(record, 'created')

    loaded = store.load('j1')
    assert loaded is not None
    assert loaded.params == {'a': 1}
    assert [r.job_id for r in store.all()] == ['j1']
    events = list(store.events())
    assert events and events[0]['event'] == 'created'


def test_store_reports_broken_records_instead_of_dropping_them(tmp_path):
    """坏记录必须能被看见 —— 静默丢掉会让调用方以为历史很干净。"""
    store = JobStore(str(tmp_path)).ensure()
    store.save(JobRecord(job_id='good', kind='build'))
    with open(store.job_path('broken'), 'w', encoding='utf-8') as handle:
        handle.write('{ not json')
    records = {r.job_id: r for r in store.all()}
    assert set(records) == {'good', 'broken'}
    assert records['broken'].status == 'failed'
    assert records['broken'].error['code'] == 'backend_failed'
    assert '损坏' in records['broken'].log[0]


# ============================================================
# 工程副本 / 覆盖
# ============================================================

def _make_project(root, name='tmp'):
    """造一个像 CST 工程的结构：``tmp.cst`` + ``tmp/`` 目录。"""
    path = root / f'{name}.cst'
    path.write_text('project-placeholder', encoding='utf-8')
    folder = root / name
    folder.mkdir(exist_ok=True)
    (folder / 'Model').mkdir(exist_ok=True)
    (folder / 'Model' / 'Parameters.json').write_text('{}', encoding='utf-8')
    return path


def test_copy_project_copies_file_and_folder(tmp_path):
    src = _make_project(tmp_path, 'src')
    dst = tmp_path / 'out' / 'dst.cst'
    result = copy_project(str(src), str(dst))
    assert os.path.isfile(result['project'])
    assert result['folder'] and os.path.isdir(result['folder'])
    assert os.path.isfile(os.path.join(result['folder'], 'Model',
                                       'Parameters.json'))


def test_copy_project_refuses_to_overwrite_by_default(tmp_path):
    src = _make_project(tmp_path, 'src')
    dst = tmp_path / 'dst.cst'
    copy_project(str(src), str(dst))
    with pytest.raises(ServiceError) as excinfo:
        copy_project(str(src), str(dst))
    assert excinfo.value.code == 'project_exists'
    copy_project(str(src), str(dst), overwrite=True)      # 显式才允许
    assert os.path.isfile(str(dst))


def test_register_defaults_to_a_working_copy(tmp_path):
    workdir = tmp_path / 'work'
    source = _make_project(tmp_path, 'tmp')
    registry = ProjectRegistry(str(workdir))
    record = registry.register(str(source))
    assert record.owned_copy is True
    assert os.path.abspath(record.path) != os.path.abspath(str(source))
    assert is_within(str(workdir), record.path)
    assert os.path.isfile(record.path)
    # 原工程没有被改动
    assert source.read_text(encoding='utf-8') == 'project-placeholder'


def test_register_in_place_is_explicit(tmp_path):
    source = _make_project(tmp_path, 'tmp')
    registry = ProjectRegistry(str(tmp_path / 'work'))
    record = registry.register(str(source), copy=False)
    assert record.owned_copy is False
    assert os.path.abspath(record.path) == os.path.abspath(str(source))


def test_register_missing_project(tmp_path):
    registry = ProjectRegistry(str(tmp_path / 'work'))
    with pytest.raises(ServiceError) as excinfo:
        registry.register(str(tmp_path / 'nope.cst'))
    assert excinfo.value.code == 'project_not_found'


def test_artifact_path_stays_inside_workdir(tmp_path):
    workdir = tmp_path / 'work'
    source = _make_project(tmp_path, 'tmp')
    registry = ProjectRegistry(str(workdir))
    record = registry.register(str(source))
    path = registry.artifact_path(record.project_id, 'out.csv')
    assert is_within(str(workdir), path)


# ============================================================
# 会话归属
# ============================================================

def test_release_closes_only_owned_sessions(tmp_path):
    workdir = tmp_path / 'work'
    source_a = _make_project(tmp_path, 'tmp')
    source_b = _make_project(tmp_path, 'tmp2')
    registry = ProjectRegistry(str(workdir))
    owned = registry.register(str(source_a), session=object(), session_owned=True)
    external = registry.register(str(source_b), session=object(),
                                 session_owned=False)
    closed = []

    result_owned = registry.release(owned.project_id,
                                    lambda record: closed.append(record.project_id))
    result_external = registry.release(external.project_id,
                                       lambda record: closed.append(record.project_id))

    assert result_owned['closed_session'] is True
    assert result_external['closed_session'] is False
    assert closed == [owned.project_id]           # 外部会话没有被关
    assert '外部' in result_external['reason']
    assert registry.list() == []


def test_release_unknown_project(tmp_path):
    registry = ProjectRegistry(str(tmp_path / 'work'))
    with pytest.raises(ServiceError) as excinfo:
        registry.release('nope')
    assert excinfo.value.code == 'project_not_registered'


def test_describe_is_json_serializable(tmp_path):
    workdir = tmp_path / 'work'
    source = _make_project(tmp_path, 'tmp')
    registry = ProjectRegistry(str(workdir))
    registry.register(str(source), session=object(), session_owned=True)
    payload = registry.describe()
    json.dumps(payload)                            # 不抛异常即通过
    assert payload['projects'][0]['has_session'] is True
    assert 'session' not in payload['projects'][0]  # CST 句柄不出服务
