# -*- coding: utf-8 -*-
"""
求解运行契约测试（P1：运行/结果契约）
=====================================

守住什么
--------
`docs/next_plan/README.md` P1 第 3 条要求把四件事分开：
**`run()` 的返回**、**真正求解完成**、**结果存在**、**结果属于本次运行**。

本测试用假探测函数（不碰 CST）把判定矩阵钉住：只有
「提交未抛异常 + CST 消息为空 + 结果存在 + 结果指纹发生变化」四条同时成立
才允许 ``status='succeeded'``；其余一律 ``failed`` / ``unverified``，
**不得**出现「没有结果却报成功」。

另外钉住两件容易漂移的事：

* `result_conventions()` 的口径必须与 `_result_core._to_db` 的**实现**一致
  （单位与 dB 口径原先只存在于命名和 docstring 里）；
* `run()` 的公开行为**没有变**（仍返回 ``None``）—— `run_checked()` 是 opt-in。

运行方式::

    pytest cst_solver/tests/test_run_contract.py -v
"""

import json
import os
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from cst_solver.run_contract import (         # noqa: E402
    JsonlSink,
    RunContract,
    disk_result_probe,
    project_path_of,
    result_conventions,
    result_fingerprint,
    run_log_path,
)


# ============================================================
# 假件：可变的探测函数 + 落盘器
# ============================================================

class _Probe:
    """可切换返回值的假探测函数。"""

    def __init__(self, value):
        self.value = value
        self.calls = 0

    def __call__(self, project_path):
        self.calls += 1
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


class _Sink:
    """内存落盘器，可选地模拟写失败。"""

    def __init__(self, fail=False):
        self.records = []
        self.fail = fail

    def write(self, record):
        if self.fail:
            raise OSError('磁盘满了')
        self.records.append(record)
        return 'memory://run_contract'


def _fingerprint(items=(), run_ids=()):
    return {'kind': 'disk', 'items': [list(i) for i in items],
            'run_ids': list(run_ids)}


def _contract(probe_value, after_value=None, sink=None):
    """
    构造一个 RunContract：before 用 probe_value，after 用 after_value。

    实现方式：先取一次指纹（before），再把探测值换成 after。
    """
    probe = _Probe(probe_value)
    contract = RunContract(r'D:\fake\proj.cst', probe=probe, sink=sink)
    return contract, probe, after_value


# ============================================================
# 1. 结果口径与实现一致
# ============================================================

def test_conventions_match_implementation():
    """dB 口径与零值处理必须与 _result_core._to_db 的实现一致。"""
    from cst_solver._result_core import _to_db

    conventions = result_conventions()
    assert conventions['frequency_unit'] == 'GHz'
    assert conventions['s_db'] == '20*log10(abs(S))'
    assert conventions['zero_magnitude_db'] == -300.0
    assert float(_to_db(0.0)) == conventions['zero_magnitude_db']
    assert float(_to_db(0.1)) == pytest.approx(-20.0)
    assert conventions['run_id_default'] == 0
    assert '当前最新结果' in conventions['run_id_semantics']


# ============================================================
# 2. 工程路径与磁盘指纹
# ============================================================

def test_project_path_of_supports_method_and_attribute():
    class WithMethod:
        class cst_file:  # noqa: N801
            @staticmethod
            def filename():
                return r'D:\a\b.cst'

    class WithAttribute:
        class cst_file:  # noqa: N801
            filename = r'D:\a\c.cst'

    class Nothing:
        cst_file = None

    assert project_path_of(WithMethod()) == r'D:\a\b.cst'
    assert project_path_of(WithAttribute()) == r'D:\a\c.cst'
    assert project_path_of(Nothing()) is None
    assert project_path_of(None) is None


def test_disk_probe_sees_results_and_model_cache(tmp_path):
    project = tmp_path / 'proj.cst'
    project.write_bytes(b'')
    folder = tmp_path / 'proj'
    (folder / 'Result').mkdir(parents=True)
    (folder / 'ModelCache').mkdir()
    (folder / 'Result' / 'Model.res').write_text('x')
    (folder / 'ModelCache' / 'Model.sab').write_text('y')

    fingerprint = disk_result_probe(str(project))
    names = {item[0] for item in fingerprint['items']}
    assert names == {'Result/Model.res', 'ModelCache/Model.sab'}


def test_disk_probe_reports_missing_folder_without_raising(tmp_path):
    fingerprint = disk_result_probe(str(tmp_path / 'ghost.cst'))
    assert 'error' in fingerprint
    assert 'CST 工程目录不存在' in fingerprint['error']


def test_result_fingerprint_swallows_probe_errors():
    def boom(_path):
        raise RuntimeError('探测器坏了')

    fingerprint = result_fingerprint(r'D:\x\y.cst', probe=boom)
    assert 'error' in fingerprint and '探测器坏了' in fingerprint['error']


def test_run_log_path_falls_back_next_to_project_file(tmp_path):
    project = tmp_path / 'ghost.cst'
    assert run_log_path(str(project)).endswith('ghost.cst.run_contract.jsonl')
    folder = tmp_path / 'ghost'
    folder.mkdir()
    assert run_log_path(str(project)) == os.path.join(str(folder),
                                                      'run_contract.jsonl')


# ============================================================
# 3. 判定矩阵
# ============================================================

def _run(contract, probe, after_value, messages=(), error=None, submit=None):
    """走一遍 before → submit → after，并允许切换探测值。"""
    record = contract.before_submit()
    probe.value = after_value
    if submit is not None:
        try:
            submit()
            record['submitted'] = True
        except Exception as exc:                      # noqa: BLE001
            error = f'{type(exc).__name__}: {exc}'
    return contract.after_submit(record, messages=messages, error=error)


def test_success_requires_changed_results_and_clean_messages():
    before = _fingerprint([('Result/Model.res', 10, 1)])
    after = _fingerprint([('Result/Model.res', 20, 2)])
    sink = _Sink()
    contract, probe, _ = _contract(before, sink=sink)
    outcome = _run(contract, probe, after)

    assert outcome['status'] == 'succeeded'
    assert outcome['results_exist'] is True
    assert outcome['results_changed'] is True
    assert outcome['messages_clean'] is True
    assert outcome['errors'] == []
    assert outcome['persisted'] is True
    assert sink.records[-1]['status'] == 'succeeded'


def test_messages_make_it_failed():
    before = _fingerprint([('Result/Model.res', 10, 1)])
    after = _fingerprint([('Result/Model.res', 20, 2)])
    contract, probe, _ = _contract(before, sink=_Sink())
    outcome = _run(contract, probe, after, messages=['10091 no such property'])

    assert outcome['status'] == 'failed'
    assert outcome['errors'][0]['code'] == 'run_messages'


def test_exception_makes_it_failed():
    contract, probe, _ = _contract(_fingerprint(), sink=_Sink())
    outcome = _run(contract, probe, _fingerprint([('Result/x', 1, 1)]),
                   error='RuntimeError: VBA 炸了')
    assert outcome['status'] == 'failed'
    assert outcome['errors'][0]['code'] == 'run_exception'


def test_unchanged_results_are_never_success():
    """结果没变 ⇒ 很可能是上一轮的结果，必须 unverified。"""
    same = _fingerprint([('Result/Model.res', 10, 1)])
    contract, probe, _ = _contract(same, sink=_Sink())
    outcome = _run(contract, probe, same)
    assert outcome['status'] == 'unverified'
    assert outcome['errors'][0]['code'] == 'results_unchanged'
    assert outcome['results_exist'] is True


def test_missing_results_are_unverified_not_success():
    contract, probe, _ = _contract(_fingerprint(), sink=_Sink())
    outcome = _run(contract, probe, _fingerprint())
    assert outcome['status'] == 'unverified'
    assert outcome['errors'][0]['code'] == 'results_missing'
    assert outcome['results_exist'] is False


def test_unusable_fingerprint_is_unverified():
    project = _Probe({'error': '探测失败'})
    contract = RunContract(r'D:\fake\proj.cst', probe=project, sink=_Sink())
    outcome = contract.run_and_record(lambda: None, read_messages=lambda: [])
    assert outcome['status'] == 'unverified'
    assert outcome['errors'][0]['code'] == 'results_not_verified'


def test_run_ids_alone_count_as_results():
    contract, probe, _ = _contract(_fingerprint(run_ids=[0]), sink=_Sink())
    outcome = _run(contract, probe, _fingerprint(run_ids=[0, 1]))
    assert outcome['status'] == 'succeeded'


# ============================================================
# 4. 落盘与读消息失败
# ============================================================

def test_sink_failure_is_reported_but_does_not_hide_the_verdict():
    before = _fingerprint([('Result/Model.res', 10, 1)])
    after = _fingerprint([('Result/Model.res', 20, 2)])
    contract, probe, _ = _contract(before, sink=_Sink(fail=True))
    outcome = _run(contract, probe, after)

    assert outcome['status'] == 'succeeded'      # 结论本身有效
    assert outcome['persisted'] is False
    assert outcome['errors'][0]['code'] == 'audit_write_failed'
    assert any('未能落盘' in w for w in outcome['warnings'])


def test_missing_sink_is_announced():
    before = _fingerprint([('Result/Model.res', 10, 1)])
    after = _fingerprint([('Result/Model.res', 20, 2)])
    contract, probe, _ = _contract(before, sink=None)
    outcome = _run(contract, probe, after)
    assert outcome['persisted'] is False
    assert any('没有落盘' in w for w in outcome['warnings'])


def test_unreadable_messages_downgrade_success():
    before = _fingerprint([('Result/Model.res', 10, 1)])
    after = _fingerprint([('Result/Model.res', 20, 2)])
    contract, probe, _ = _contract(before, sink=_Sink())
    record = contract.before_submit()
    probe.value = after
    record['messages_read_error'] = 'OSError: 会话断了'
    outcome = contract.after_submit(record, messages=[])
    assert outcome['status'] == 'unverified'
    assert [e['code'] for e in outcome['errors']] == ['messages_unreadable']


def test_run_and_record_persists_jsonl(tmp_path):
    project = tmp_path / 'proj.cst'
    path = run_log_path(str(project))
    contract = RunContract(str(project), probe=_Probe(_fingerprint()),
                           sink=JsonlSink(path))
    calls = []

    def submit():
        calls.append(1)

    outcome = contract.run_and_record(submit, read_messages=lambda: [])
    assert calls == [1]
    assert outcome['persisted'] is True
    lines = open(path, encoding='utf-8').read().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])['run_token'] == outcome['run_token']


def test_outcome_is_json_serializable(tmp_path):
    contract, probe, _ = _contract(_fingerprint(), sink=_Sink())
    outcome = _run(contract, probe, _fingerprint([('Result/x', 1, 1)]))
    json.dumps(outcome, ensure_ascii=False)


# ============================================================
# 5. setup.run_checked：opt-in，且不改 run() 的行为
# ============================================================

class _FakeModel3D:
    def __init__(self):
        self.runs = 0
        self.messages = []

    def run_solver(self):
        self.runs += 1


class _FakeCstFile:
    def __init__(self, path):
        self.model3d = _FakeModel3D()
        self._path = path
        self._messages = []

    def filename(self):
        return self._path

    def get_messages(self):
        out = list(self._messages)
        self._messages = []
        return out


class _Host:
    """最小宿主：只带求解与验收 Mixin（与真实 setup 的用法一致）。"""

    def __init__(self, path):
        from cst_solver.simulation.solver import SolverMixin
        from cst_solver.validation import ValidationMixin

        class _Combined(SolverMixin, ValidationMixin):
            pass

        self.__class__ = type('_HostCombined', (_Combined,), {})
        self.cst_file = _FakeCstFile(path)


def test_run_still_returns_none(tmp_path):
    """向后兼容：run() 的行为一字未改。"""
    host = _Host(str(tmp_path / 'p.cst'))
    assert host.run() is None
    assert host.cst_file.model3d.runs == 1


def test_run_checked_reports_unverified_without_results(tmp_path):
    host = _Host(str(tmp_path / 'p.cst'))
    outcome = host.run_checked(sink=_Sink(), read_messages=True)
    assert outcome['status'] == 'unverified'
    assert host.cst_file.model3d.runs == 1            # 求解确实提交了
    assert outcome['errors'][0]['code'] in ('results_missing',
                                            'results_not_verified')
    assert outcome['submitted'] is True
