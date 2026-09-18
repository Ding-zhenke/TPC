# -*- coding: utf-8 -*-
"""
工具层测试（P3，离线）
======================

工具是纯函数，因此这里不需要 MCP 协议也不需要 CST：

* 能力发现 / 模板列表 / 预检：离线可用；
* 建模 / 求解 / 结果：用**假后端**跑通「异步任务 + 状态 + 产物」；
* 失败路径：**失败就是结构化错误，不是空数据**；
* 关键物理条件缺失：报 ``missing_requirement``，让 AI 去问用户。
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from cst_mcp import runtime, tools                  # noqa: E402
from tpc_service.backends.fake import FakeBackend   # noqa: E402


@pytest.fixture()
def env(tmp_path):
    """把运行时指到临时工作目录 + 假后端，并准备一个模板工程。"""
    template = tmp_path / 'tmp.cst'
    template.write_text('project-placeholder', encoding='utf-8')
    runtime.reset()
    runtime.configure(workdir=str(tmp_path / 'service'), backend=FakeBackend())
    yield {'work': tmp_path, 'template': template, 'service_dir': tmp_path / 'service'}
    service = runtime.get_service()
    service.shutdown()
    runtime.reset()


def _spec(env, **geometry):
    geom = {'length': 18, 'topology': 'BA'}
    geom.update(geometry)
    return {'model': {'type': 'straight_waveguide'}, 'geometry': geom,
            'output': {'template_cst': str(env['template']),
                       'path': str(env['work'] / 'BA18.cst')}}


def _run_until_done(job_id, timeout=15):
    return runtime.get_service().wait(job_id, timeout=timeout)


# ============================================================
# 工具表
# ============================================================

def test_tool_table_matches_the_plan():
    """首版 11 个工具一个都不能少。"""
    expected = {'get_capabilities', 'list_templates', 'validate_model_spec',
                'build_model', 'get_project_state', 'run_simulation',
                'get_job_status', 'get_results', 'analyze_s_parameters',
                'export_report', 'close_project'}
    assert set(tools.tool_names()) == expected
    for spec in tools.TOOL_SPECS:
        assert spec['description'], spec['name']
        assert spec['inputSchema']['type'] == 'object'


def test_unknown_tool_is_a_structured_error():
    payload = tools.dispatch('teleport', {})
    assert payload['ok'] is False
    assert payload['error']['code'] == 'unknown_tool'
    assert 'get_capabilities' in payload['error']['message']


# ============================================================
# 离线工具
# ============================================================

def test_get_capabilities_reports_shape_and_limits(env):
    payload = tools.dispatch('get_capabilities', {})
    assert payload['ok'] is True
    assert payload['backend'] == 'fake'
    assert 'status' in payload['cst']
    assert set(payload['tools']) == set(tools.tool_names())
    verified = payload['limits']['real_cst_backend_verified']
    # 按任务种类如实标注：真机只验证到建模那一段，求解/study 未验证
    assert verified['build'] is True and verified['solve'] is False
    assert verified['study'] is False
    assert 'cancel_running_job' in payload['limits']
    assert 'solver_progress' in payload['limits']
    assert '进度' in payload['limits']['solver_progress']
    assert any('假后端' in note for note in payload['notes'])   # 不隐瞒在用假后端


def test_get_capabilities_claims_no_fake_progress(env):
    """
    「不提供虚假百分比进度」（计划 P3）：能力报告里**不许**出现进度百分比字段，
    而且必须写明进度回调未核实。
    """
    payload = tools.dispatch('get_capabilities', {})
    text = json.dumps(payload, ensure_ascii=False)
    for banned in ('progress_percent', 'percent', '完成度'):
        assert banned not in text, f'能力报告里出现了进度字段 {banned!r}'
    assert '未核实' in payload['limits']['solver_progress']


def test_list_templates_marks_unbuildable(env):
    """P5 三类模板全部落地后：**所有**类型都必须 buildable=True 且带类名。"""
    payload = tools.dispatch('list_templates', {'include_planned': True})
    by_type = {t['model_type']: t for t in payload['templates']}
    for model_type, class_name in (('straight_waveguide', 'StraightWaveguide'),
                                   ('unit_antenna', 'UnitAntenna'),
                                   ('grin_lens_antenna', 'GRINLensAntenna'),
                                   ('multiport_antenna', 'MultiPortAntenna'),
                                   ('mzi_switch', 'MZISwitch'),
                                   ('power_divider', 'PowerDivider')):
        assert by_type[model_type]['buildable'] is True, model_type
        assert by_type[model_type]['class'] == class_name, model_type
    assert payload['buildable'] == ['straight_waveguide', 'unit_antenna',
                                    'grin_lens_antenna', 'multiport_antenna',
                                    'mzi_switch', 'power_divider']


def test_list_templates_default_hides_planned(env):
    """没有"计划中"类型了 ⇒ 默认列表与 include_planned=True 一致。"""
    payload = tools.dispatch('list_templates', {})
    assert [t['model_type'] for t in payload['templates']] == \
        ['straight_waveguide', 'unit_antenna', 'grin_lens_antenna',
         'multiport_antenna', 'mzi_switch', 'power_divider']


def test_validate_model_spec_ok_and_defaults_visible(env):
    payload = tools.dispatch('validate_model_spec', {'spec': _spec(env)})
    assert payload['ok'] is True
    assert payload['valid'] is True and payload['buildable'] is True
    assert payload['effective']['geometry']['lattice_constant'] == 0.2425
    assert payload['field_sources']['geometry.length'] == 'user'


def test_validate_model_spec_invalid_input_fails_explicitly(env):
    bad = _spec(env, length=0)
    payload = tools.dispatch('validate_model_spec', {'spec': bad})
    assert payload['ok'] is False
    assert payload['error']['code'] == 'config_value_out_of_range'
    assert payload['error']['details']['report']['ok'] is False


def test_validate_model_spec_rejects_unknown_type(env):
    """未知类型必须结构化失败（P5 全部落地后没有"计划中"类型可用）。"""
    payload = tools.dispatch('validate_model_spec',
                             {'spec': {'model': {'type': 'totally_unknown'}}})
    assert payload['ok'] is False
    assert payload['error']['code'] == 'config_model_type_invalid'


def test_validate_model_spec_accepts_the_divider(env):
    """`power_divider` 现在是**可构建**类型（P5 模板），预检不再报未实现。"""
    payload = tools.dispatch('validate_model_spec',
                             {'spec': {'model': {'type': 'power_divider'},
                                       'geometry': {'straight_length': 14,
                                                    'arm_length': 8}}})
    # 预检可能因别的原因（缺 template_cst 等）失败，但**不该**是"未实现"
    code = (payload.get('error') or {}).get('code')
    assert code != 'model_type_not_implemented', payload


# ============================================================
# 任务闭环（假后端）
# ============================================================

def test_build_run_analyze_report_closed_loop(env):
    """验收闭环：预检 → 建模 → 求解 → S 参数 → 报告（全程离线）。"""
    spec = _spec(env)
    assert tools.dispatch('validate_model_spec', {'spec': spec})['ok']

    build = tools.dispatch('build_model', {'spec': spec, 'request_id': 'r-1'})
    assert build['ok'] and build['status'] == 'queued'
    assert _run_until_done(build['job_id'])['status'] == 'succeeded'

    run = tools.dispatch('run_simulation', {'project_id': build['project_id'],
                                            'request_id': 'r-2'})
    assert run['ok']
    assert _run_until_done(run['job_id'])['status'] == 'succeeded'

    results = tools.dispatch('get_results', {'job_id': run['job_id']})
    assert results['ok']
    assert results['result_summary']['S1,1_min_db'] == -18.5
    assert any(a['kind'] == 'csv' for a in results['artifacts'])

    analysis = tools.dispatch('analyze_s_parameters',
                              {'job_id': run['job_id'], 'metric': 'S2,1',
                               'threshold_db': -3.0, 'criterion': 'above',
                               'resonance_kind': 'min'})
    assert analysis['ok']
    assert analysis['analysis']['n_bands'] == 2                 # 两段，不合并
    assert analysis['analysis']['data_source']['kind'] == 'csv'

    report = tools.dispatch('export_report',
                            {'analysis': analysis['analysis'],
                             'job_id': run['job_id'], 'title': 'BA 直波导'})
    assert report['ok']
    kinds = {a['kind'] for a in report['artifacts']}
    assert kinds == {'html', 'csv'}
    for artifact in report['artifacts']:
        assert os.path.isfile(artifact['path'])


def test_build_requires_project_template(env):
    spec = {'model': {'type': 'straight_waveguide'}}
    payload = tools.dispatch('build_model', {'spec': spec})
    assert payload['ok'] is False
    assert payload['error']['code'] == 'missing_requirement'
    assert 'project_path' in payload['error']['message']


def test_build_missing_spec_is_structured_error(env):
    payload = tools.dispatch('build_model', {})
    assert payload['ok'] is False
    assert payload['error']['code'] == 'missing_requirement'


def test_duplicate_request_is_flagged_and_not_rerun(env):
    spec = _spec(env)
    first = tools.dispatch('build_model', {'spec': spec, 'request_id': 'dup'})
    _run_until_done(first['job_id'])
    calls = len(runtime.get_service().backend.calls)
    again = tools.dispatch('build_model', {'spec': spec, 'request_id': 'dup'})
    assert again['duplicate'] is True
    assert again['job_id'] == first['job_id']
    assert len(runtime.get_service().backend.calls) == calls


def test_job_status_reports_interrupted_honestly(env):
    service = runtime.get_service()
    job = service.submit('build', project_path=str(env['template']),
                         params={'spec': _spec(env)})
    service.cancel(job['job_id'])                       # 排队中取消 → interrupted
    payload = tools.dispatch('get_job_status', {'job_id': job['job_id']})
    assert payload['status'] == 'interrupted'
    assert any('不得' in note for note in payload['notes'])


def test_get_results_on_failed_job_is_an_error_not_empty_data(env):
    runtime.reset()
    runtime.configure(workdir=str(env['service_dir']),
                      backend=FakeBackend(fail_on={'solve'}))
    service = runtime.get_service()
    job = service.submit('solve', project_path=str(env['template']))
    service.wait(job['job_id'], timeout=15)
    payload = tools.dispatch('get_results', {'job_id': job['job_id']})
    assert payload['ok'] is False
    assert payload['error']['code'] == 'backend_failed'
    assert payload['error']['details']['status'] == 'failed'


def test_run_simulation_on_missing_project_reports_not_found(env):
    payload = tools.dispatch('run_simulation',
                             {'project_path': str(env['work'] / 'nope.cst')})
    assert payload['ok'] is False
    assert payload['error']['code'] == 'project_not_found'


def test_get_project_state_lists_jobs(env):
    build = tools.dispatch('build_model', {'spec': _spec(env)})
    _run_until_done(build['job_id'])
    state = tools.dispatch('get_project_state', {'project_id': build['project_id']})
    assert state['ok'] is True
    assert state['exists'] is True
    assert state['jobs'][0]['job_id'] == build['job_id']
    listing = tools.dispatch('get_project_state', {})
    assert listing['n_jobs'] >= 1


def test_close_project_reports_ownership(env):
    build = tools.dispatch('build_model', {'spec': _spec(env)})
    _run_until_done(build['job_id'])
    state = tools.dispatch('get_project_state', {})
    projects = state['projects']
    assert projects
    payload = tools.dispatch('close_project',
                             {'project_id': projects[0]['project_id']})
    assert payload['ok'] is True
    assert payload['closed_session'] is False        # 外部会话不该被关
    assert any('外部' in note for note in payload['notes'])


# ============================================================
# 分析与报告的失败路径
# ============================================================

def test_analyze_without_data_source_reports_missing_requirement(env):
    payload = tools.dispatch('analyze_s_parameters', {'threshold_db': -3.0})
    assert payload['ok'] is False
    assert payload['error']['code'] == 'missing_requirement'
    assert 'csv_path' in payload['error']['message']


def test_analyze_invalid_threshold_type(env):
    payload = tools.dispatch('analyze_s_parameters',
                             {'threshold_db': 'low', 'csv_path': 'x.csv'})
    assert payload['ok'] is False
    assert payload['error']['code'] == 'invalid_arguments'


def test_analyze_unknown_metric_lists_available(env, tmp_path):
    csv_path = tmp_path / 's.csv'
    csv_path.write_text('freq_GHz,S1,1,S2,1\n300,-10,-1\n301,-11,-1.2\n',
                        encoding='utf-8')
    payload = tools.dispatch('analyze_s_parameters',
                             {'csv_path': str(csv_path), 'metric': 'S3,3',
                              'threshold_db': -3.0})
    assert payload['ok'] is False
    assert payload['error']['code'] == 'invalid_arguments'
    assert 'S1,1' in payload['error']['message']


def test_export_report_can_analyze_from_csv_directly(env, tmp_path):
    csv_path = tmp_path / 's.csv'
    csv_path.write_text('freq_GHz,S2,1\n290,-1\n300,-1\n310,-20\n320,-1\n',
                        encoding='utf-8')
    payload = tools.dispatch('export_report',
                             {'csv_path': str(csv_path), 'metric': 'S2,1',
                              'threshold_db': -3.0, 'criterion': 'above',
                              'formats': ['html']})
    assert payload['ok'] is True
    assert payload['analysis']['n_bands'] == 2
    assert payload['artifacts'][0]['path'].endswith('.html')


def test_export_report_rejects_unknown_format(env, tmp_path):
    csv_path = tmp_path / 's.csv'
    csv_path.write_text('freq_GHz,S2,1\n300,-1\n', encoding='utf-8')
    payload = tools.dispatch('export_report',
                             {'csv_path': str(csv_path), 'threshold_db': -3.0,
                              'formats': ['pdf']})
    assert payload['ok'] is False
    assert payload['error']['code'] == 'invalid_arguments'
