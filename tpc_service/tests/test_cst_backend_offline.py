# -*- coding: utf-8 -*-
r"""
`CstBackend` 的**离线编排测试**（P2 待办：真实 runner 的编排逻辑）
=================================================================

计划 P2 原话：*「`CstBackend` 的 `build` / `solve` / `study`（scan·batch·optimize 三路）
目前只通过离线导入与失败路径测试」*。

本文件把那半句补上 —— **不碰 CST**，但把真实后端的**编排与纪律**逐条钉住：

* `build`：预检未过就**不建模板**；建完必须 `close()`；`Rebuild` 验收失败不掩盖建模结果；
  产物路径必须落在服务工作目录内（`workdir_escape`）。
* `solve`：**先保存再读**（调用顺序 run_checked → save → 读取器）；
  运行契约没判 `succeeded` 时**绝不 save**；读结果失败**不改变「已保存」**但要说清楚；
  自己开的会话必须 `close()`。
* `study`：`scan` / `batch` / `optimize` 三路各自真的跑到既有的
  `ParameterScan` / `BatchModeler` / `GeneticOptimizer`（这些是离线可跑的），
  失败点进 `last_errors` 而任务不整体崩；未知 `kind` 与缺字段都要**结构化失败**。

⚠️ 这里验证的是**编排**：`cst_solver.setup` 与模板工厂都是假的。
「CST 真的会这么干吗」仍属计划 P4/V7（真机闭环），本文件不作任何真机结论。
"""

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tpc_service.backends.cst_backend import CstBackend      # noqa: E402

_SPEC = {'model': {'type': 'straight_waveguide'},
         'geometry': {'length': 18, 'topology': 'BA'}}


# ============================================================
# 替身
# ============================================================

class _FakeTemplate:
    """假模板：记录调用顺序，可选在某一步抛异常。"""

    def __init__(self, log, *, fail_on=None, validate_status='ok',
                 validate_raises=False, save_path=None):
        self.log = log
        self.fail_on = fail_on or set()
        self.validate_status = validate_status
        self.validate_raises = validate_raises
        self.save_path = save_path
        self.closed = False

    def build_all(self):
        self.log.append('build_all')
        if 'build_all' in self.fail_on:
            raise RuntimeError('假模板：建模失败')

    def save(self, path):
        self.log.append(f'save:{path}')
        if 'save' in self.fail_on:
            raise RuntimeError('假模板：保存失败')
        return path

    def validate(self):
        self.log.append('validate')
        if self.validate_raises:
            raise RuntimeError('假模板：验收调用失败')
        return {'status': self.validate_status}

    def close(self):
        self.log.append('close')
        self.closed = True


class _FakeApp:
    """假 CST 会话：记录 run_checked / save / close 的顺序。"""

    def __init__(self, log, *, outcome=None, fail_on=None):
        self.log = log
        self.outcome = outcome or {'status': 'succeeded', 'run_token': 'tok-1',
                                   'messages': ['ok']}
        self.fail_on = fail_on or set()

    def run_checked(self, **kwargs):
        self.log.append('run_checked')
        if 'run_checked' in self.fail_on:
            raise RuntimeError('假会话：run_checked 抛异常')
        return dict(self.outcome)

    def save(self, path):
        self.log.append(f'app.save:{path}')
        if 'save' in self.fail_on:
            raise RuntimeError('假会话：保存失败')
        return path

    def close(self):
        self.log.append('app.close')
        if 'close' in self.fail_on:
            raise RuntimeError('假会话：关闭失败')


class _FakeReader:
    """假结果读取器：`peak_position` / `value_at` 都给确定值。"""

    instances = []

    def __init__(self, path, names=None, run_id=0):
        self.path, self.names, self.run_id = path, list(names or []), run_id
        self.last_errors = {}
        _FakeReader.instances.append(self)

    def peak_position(self, name, kind='min'):
        return (330.0, -17.5)

    def value_at(self, name, freq, in_db=True):
        return -12.25


@pytest.fixture(autouse=True)
def _reset_reader():
    _FakeReader.instances = []
    yield
    _FakeReader.instances = []


@pytest.fixture
def project(tmp_path):
    """一个存在的工程文件（`solve` 会先 os.path.isfile）。"""
    path = tmp_path / 'proj.cst'
    path.write_text('x', encoding='utf-8')
    return {'path': str(path)}


def _patch_preflight(monkeypatch, report):
    calls = []

    def fake(spec, **kwargs):
        calls.append({'spec': spec, 'kwargs': kwargs})
        return report

    import topo_modeler.preflight as preflight
    monkeypatch.setattr(preflight, 'validate_model_spec', fake)
    return calls


def _ok_report(model_type='straight_waveguide'):
    return {'ok': True, 'valid': True, 'model_type': model_type,
            'errors': [], 'warnings': [], 'ctor_kwargs': {'length': 18}}


# ============================================================
# build
# ============================================================

def test_build_rejects_non_dict_spec():
    backend = CstBackend()
    out = backend.build(project={'path': 'x.cst'}, params={'spec': 'oops'},
                        job={})
    assert out['ok'] is False
    assert out['error']['code'] == 'backend_failed'
    assert out['error']['details']['got'] == 'str'


def test_build_stops_before_creating_template_when_preflight_fails(monkeypatch,
                                                                  tmp_path):
    """预检不过 ⇒ 不建模板（离线预检的价值就在这里）。"""
    _patch_preflight(monkeypatch, {
        'ok': False, 'valid': False, 'model_type': 'straight_waveguide',
        'errors': [{'code': 'invalid_field', 'message': 'length 必须是正整数'}]})
    built = []
    import topo_modeler.config as config
    monkeypatch.setattr(config, 'template_from_config',
                        lambda *a, **k: built.append('called'))

    out = CstBackend().build(project={'path': str(tmp_path / 'p.cst')},
                             params={'spec': _SPEC}, job={})
    assert out['ok'] is False
    assert out['error']['code'] == 'invalid_field'
    assert built == []                                   # 一次都没建
    assert out['error']['details']['preflight']['valid'] is False


def test_build_happy_path_saves_and_closes(monkeypatch, tmp_path):
    _patch_preflight(monkeypatch, _ok_report())
    log = []
    template = _FakeTemplate(log)
    import topo_modeler.config as config
    monkeypatch.setattr(config, 'template_from_config',
                        lambda *a, **k: template)

    out = CstBackend().build(project={'path': str(tmp_path / 'p.cst')},
                             params={'spec': _SPEC}, job={})
    assert out['ok'] is True and out['saved'] is True
    assert out['artifacts'][0]['kind'] == 'project'
    assert os.path.basename(out['artifacts'][0]['path']).startswith('straight_waveguide')
    assert template.closed is True
    assert log == ['build_all', f"save:{out['artifacts'][0]['path']}", 'validate', 'close']
    assert out['result_summary']['validation'] == 'ok'


def test_build_validation_failure_does_not_mask_success(monkeypatch, tmp_path):
    """`Rebuild` 验收调用失败时，建模结果照旧算成功，但日志必须写明。"""
    _patch_preflight(monkeypatch, _ok_report())
    log = []
    template = _FakeTemplate(log, validate_raises=True)
    import topo_modeler.config as config
    monkeypatch.setattr(config, 'template_from_config',
                        lambda *a, **k: template)

    out = CstBackend().build(project={'path': str(tmp_path / 'p.cst')},
                             params={'spec': _SPEC}, job={})
    assert out['ok'] is True
    assert out['result_summary']['validation'] == 'unknown'
    assert any('验收调用失败' in line for line in out['log'])
    assert template.closed is True                        # 失败也要收尾


def test_build_failure_still_closes_template(monkeypatch, tmp_path):
    _patch_preflight(monkeypatch, _ok_report())
    log = []
    template = _FakeTemplate(log, fail_on={'build_all'})
    import topo_modeler.config as config
    monkeypatch.setattr(config, 'template_from_config',
                        lambda *a, **k: template)

    out = CstBackend().build(project={'path': str(tmp_path / 'p.cst')},
                             params={'spec': _SPEC}, job={})
    assert out['ok'] is False
    assert out['error']['retryable'] is True
    assert template.closed is True


def test_build_reports_template_construction_failure(monkeypatch, tmp_path):
    _patch_preflight(monkeypatch, _ok_report())
    import topo_modeler.config as config

    def boom(*a, **k):
        raise ValueError('规格里的 relative path 解析失败')

    monkeypatch.setattr(config, 'template_from_config', boom)
    out = CstBackend().build(project={'path': str(tmp_path / 'p.cst')},
                             params={'spec': _SPEC}, job={})
    assert out['ok'] is False
    assert out['error']['code'] == 'backend_failed'
    assert 'ValueError' in out['error']['message']


def test_build_output_escaping_workdir_is_refused(monkeypatch, tmp_path):
    """产物必须落在服务工作目录内（`ensure_within`）——当前实现直接抛，由服务层包成失败。"""
    _patch_preflight(monkeypatch, _ok_report())
    workdir = tmp_path / 'work'
    workdir.mkdir()
    outside = tmp_path / 'elsewhere.cst'
    with pytest.raises(Exception) as caught:
        CstBackend().build(project={'path': str(workdir / 'p.cst')},
                           params={'spec': _SPEC, 'output': str(outside)}, job={})
    assert getattr(caught.value, 'code', None) == 'workdir_escape'


# ============================================================
# solve
# ============================================================

def _patch_solve_env(monkeypatch, app, reader=_FakeReader):
    import cst_solver
    import topo_modeler.result_reader as reader_mod
    monkeypatch.setattr(cst_solver, 'setup', lambda path: app)
    monkeypatch.setattr(reader_mod, 'ResultReader', reader)
    return app


def test_solve_requires_existing_project(monkeypatch, tmp_path):
    import cst_solver
    called = []
    monkeypatch.setattr(cst_solver, 'setup', lambda path: called.append(path))
    out = CstBackend().solve(project={'path': str(tmp_path / 'missing.cst')},
                             params={}, job={})
    assert out['ok'] is False
    assert out['error']['code'] == 'project_not_found'
    assert called == []                                  # 连会话都没开


def test_solve_saves_before_reading_and_closes(monkeypatch, project):
    """核心纪律：run_checked → save → 读取器；顺序不可颠倒。"""
    log = []
    app = _FakeApp(log)
    _patch_solve_env(monkeypatch, app)

    out = CstBackend().solve(project=project, params={}, job={})
    assert out['ok'] is True and out['saved'] is True
    assert log == ['run_checked', f"app.save:{project['path']}", 'app.close']
    assert out['run_identity']['run_token'] == 'tok-1'
    assert out['artifacts'][0]['kind'] == 'result'

    metrics = out['result_summary']['metrics']
    assert metrics['S1,1_min_db'] == {'freq_ghz': 330.0, 'db': -17.5}
    assert metrics['S2,1_at_330GHz_db'] == -12.25
    assert out['result_summary']['conventions']['frequency_unit'] == 'GHz'
    # 读取器拿到的名字与 run_id 与后端声明一致
    reader = _FakeReader.instances[-1]
    assert reader.names == ['S1,1', 'S2,1'] and reader.run_id == 0


def test_solve_never_saves_when_run_contract_fails(monkeypatch, project):
    """运行契约没判 succeeded ⇒ 不 save（否则会把上一轮结果当本轮）。"""
    log = []
    app = _FakeApp(log, outcome={'status': 'failed', 'run_token': 'tok-x',
                                 'messages': ['收敛失败'],
                                 'errors': [{'code': 'run_messages',
                                             'message': 'CST 有失败消息'}]})
    _patch_solve_env(monkeypatch, app)

    out = CstBackend().solve(project=project, params={}, job={})
    assert out['ok'] is False
    assert out['error']['code'] == 'run_messages'
    assert out['error']['details']['run_identity']['run_token'] == 'tok-x'
    assert not any(line.startswith('app.save') for line in log)
    assert log == ['run_checked', 'app.close']           # 仍然要收尾
    assert _FakeReader.instances == []                   # 也没读结果


def test_solve_setup_exception_is_structured(monkeypatch, project):
    import cst_solver

    def boom(path):
        raise RuntimeError('CST 接口不可用')

    monkeypatch.setattr(cst_solver, 'setup', boom)
    out = CstBackend().solve(project=project, params={}, job={})
    assert out['ok'] is False
    assert out['error']['retryable'] is True
    assert 'RuntimeError' in out['error']['message']


def test_solve_reader_failure_keeps_saved_fact(monkeypatch, project):
    """读结果失败**不能**把「求解并已保存」说成失败，但要在摘要与日志里说清楚。"""
    log = []
    app = _FakeApp(log)

    class _BoomReader:
        def __init__(self, *a, **k):
            raise RuntimeError('结果文件被锁')

    _patch_solve_env(monkeypatch, app, reader=_BoomReader)
    out = CstBackend().solve(project=project, params={}, job={})
    assert out['ok'] is True and out['saved'] is True
    assert 'read_error' in out['result_summary']
    assert any('结果读取失败' in line for line in out['log'])


def test_solve_close_failure_does_not_mask_result(monkeypatch, project):
    log = []
    app = _FakeApp(log, fail_on={'close'})
    _patch_solve_env(monkeypatch, app)
    out = CstBackend().solve(project=project, params={}, job={})
    assert out['ok'] is True and out['saved'] is True
    assert any('关闭会话失败' in line for line in out['log'])


# ============================================================
# study：三路分派
# ============================================================

def _patch_runner(monkeypatch, backend, metrics=None):
    """把 build/solve 换成假的，让 study 的分派逻辑可以离线跑。"""
    calls = []
    payload = metrics or {'S2,1_at_330GHz_db': -3.0, 'S1,1_min_db': -20.0}

    def fake_build(*, project, params, job):
        calls.append(('build', params.get('output')))
        return {'ok': True, 'saved': True, 'artifacts': [], 'log': [],
                'result_summary': {}, 'error': None}

    def fake_solve(*, project, params, job):
        calls.append(('solve', project.get('path')))
        return {'ok': True, 'saved': True, 'artifacts': [], 'log': [],
                'result_summary': {'metrics': dict(payload)}, 'error': None}

    monkeypatch.setattr(backend, 'build', fake_build)
    monkeypatch.setattr(backend, 'solve', fake_solve)
    return calls


def test_study_scan_runs_real_parameter_scan(tmp_path, monkeypatch):
    backend = CstBackend()
    calls = _patch_runner(monkeypatch, backend)
    out = backend.study(
        project={'path': str(tmp_path / 'base.cst')},
        params={'study': {'kind': 'scan',
                          'base_config': _SPEC,
                          'params': {'length': [16, 18, 20]},
                          'apply_to': 'geometry'}},
        job={'job_id': 'j1'})
    assert out['ok'] is True and out['saved'] is True
    assert out['result_summary']['n_points'] == 3
    assert [p['status'] for p in out['result_summary']['points']] == ['ok'] * 3
    assert [c[0] for c in calls] == ['build', 'solve'] * 3      # 串行、逐点
    assert os.path.isdir(out['artifacts'][0]['path'])


def test_study_scan_records_failed_points_without_crashing(tmp_path, monkeypatch):
    """某个点失败时：任务仍算成功（continue_on_error），但必须如实记进 last_errors。"""
    backend = CstBackend()
    state = {'n': 0}

    def fake_build(*, project, params, job):
        state['n'] += 1
        if state['n'] == 1:                                  # 第一个点故意失败
            return {'ok': False, 'error': {'code': 'backend_failed',
                                           'message': '假建模失败'}}
        return {'ok': True, 'saved': True, 'artifacts': [], 'log': [],
                'result_summary': {}, 'error': None}

    def fake_solve(*, project, params, job):
        return {'ok': True, 'saved': True, 'artifacts': [], 'log': [],
                'result_summary': {'metrics': {'m': 1.0}}, 'error': None}

    monkeypatch.setattr(backend, 'build', fake_build)
    monkeypatch.setattr(backend, 'solve', fake_solve)

    out = backend.study(
        project={'path': str(tmp_path / 'base.cst')},
        params={'study': {'kind': 'scan', 'base_config': _SPEC,
                          'params': {'length': [16, 18]}, 'apply_to': 'geometry'}},
        job={'job_id': 'j2'})
    assert out['ok'] is True                                    # continue_on_error
    assert out['result_summary']['errors']                      # 但如实记录
    statuses = [p['status'] for p in out['result_summary']['points']]
    assert 'error' in statuses and 'ok' in statuses


def test_study_batch_runs_real_batch_modeler(tmp_path, monkeypatch):
    backend = CstBackend()
    _patch_runner(monkeypatch, backend)
    out = backend.study(
        project={'path': str(tmp_path / 'base.cst')},
        params={'study': {'kind': 'batch',
                          'entries': [{'name': 'a', 'config': _SPEC},
                                      {'name': 'b', 'config': _SPEC}]}},
        job={'job_id': 'j3'})
    assert out['ok'] is True
    assert out['result_summary']['summary']['模型数'] == 2
    assert out['artifacts'][0]['kind'] == 'dir'


def test_study_optimize_runs_real_optimizer(tmp_path, monkeypatch):
    """优化路：`objective.metric` 取自 metrics，`direction='min'` ⇒ 越小越好。"""
    backend = CstBackend()

    def fake_build(*, project, params, job):
        return {'ok': True, 'saved': True, 'artifacts': [], 'log': [],
                'result_summary': {}, 'error': None}

    def fake_solve(*, project, params, job):
        return {'ok': True, 'saved': True, 'artifacts': [], 'log': [],
                'result_summary': {'metrics': {'m': -3.0}}, 'error': None}

    monkeypatch.setattr(backend, 'build', fake_build)
    monkeypatch.setattr(backend, 'solve', fake_solve)

    out = backend.study(
        project={'path': str(tmp_path / 'base.cst')},
        params={'study': {'kind': 'optimize', 'base_config': _SPEC,
                          'variables': [{'name': 'length', 'lo': 16, 'hi': 20,
                                         'integer': True}],
                          'objective': {'metric': 'm', 'direction': 'min'},
                          'population_size': 4, 'generations': 2, 'seed': 1}},
        job={'job_id': 'j4'})
    assert out['ok'] is True
    assert out['result_summary']['best_fitness'] is not None
    summary = out['result_summary']
    assert summary['best_params']['length'] is not None
    assert summary['generations_run'] == 2
    assert summary['seed'] == 1
    assert any('优化完成' in line for line in out['log'])


def test_study_unknown_kind_and_missing_fields_are_structured(tmp_path):
    backend = CstBackend()
    unknown = backend.study(project={'path': str(tmp_path / 'b.cst')},
                            params={'study': {'kind': 'nope'}}, job={})
    assert unknown['ok'] is False
    assert unknown['error']['code'] == 'backend_failed'
    assert unknown['error']['details']['kind'] == 'nope'
    assert 'scan / batch / optimize' in unknown['error']['message']

    missing = backend.study(project={'path': str(tmp_path / 'b.cst')},
                            params={'study': {'kind': 'scan',
                                              'base_config': _SPEC}}, job={})
    assert missing['ok'] is False
    assert '缺少必需字段' in missing['error']['message']
