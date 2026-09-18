# -*- coding: utf-8 -*-
r"""
`scripts/verify_service_mcp_real.py` 的离线自检
==============================================

这个脚本本身要连真 CST 才能真跑，但它有两条**必须离线钉住**的性质，否则
「只建模不求解」这句话很容易在后续改动里悄悄失效：

1. **不求解**：脚本只调用 `build_model`，**不得**出现 `run_simulation`
   （那是求解工具，会启动长求解）；
2. **接线正确**：真 stdio 服务进程的环境变量（工作目录、后端选择）、
   建模规格、任务记录路径、真工程识别都要按约定工作。

另外顺带把「重启恢复」用到的**伪造未完成记录**这一步也离线跑一遍
（`autostart=False` ⇒ 记录停在 `queued`，不执行任何后端动作）。

运行方式::

    pytest tests/test_service_mcp_real_script.py -v
"""

import importlib.util
import json
import os
import re
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_SCRIPTS = os.path.join(ROOT, 'scripts')
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

_SOURCE = os.path.join(_SCRIPTS, 'verify_service_mcp_real.py')


def _load_module():
    spec = importlib.util.spec_from_file_location('verify_service_mcp_real', _SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def real_script():
    return _load_module()


# ================================================================
# 「只建模、不求解」的护栏
# ================================================================

def test_script_never_calls_the_solve_tool(real_script):
    """脚本里不得出现求解工具 `run_simulation`（也不得调 solve/study）。"""
    source = open(_SOURCE, encoding='utf-8').read()
    # 说明文字里可以提它（文档里解释了为什么不碰），但**代码**里不许调用
    calls = re.findall(r"call_tool\(\s*'([a-z_]+)'", source)
    assert calls, '没有解析到任何工具调用'
    assert 'run_simulation' not in calls, f'不允许调用求解工具：{calls}'
    assert calls.count('build_model') == 1, calls


def test_script_only_submits_build_kind(real_script):
    """直接构造记录的那一步只允许 kind='build'。"""
    source = open(_SOURCE, encoding='utf-8').read()
    kinds = re.findall(r"service\.submit\('([a-z]+)'", source)
    assert kinds and set(kinds) == {'build'}, kinds


# ================================================================
# 接线
# ================================================================

def test_server_params_point_at_workdir_and_real_cst(real_script, tmp_path):
    """默认（不传 backend）⇒ 真 CST：设工作目录、**不设** `TPC_MCP_BACKEND`。"""
    mcp = pytest.importorskip('mcp')                     # noqa: F841
    params = real_script.server_params(tmp_path / 'svc', tmp_path)
    assert params.env['TPC_MCP_WORKDIR'] == str(tmp_path / 'svc')
    assert 'TPC_MCP_BACKEND' not in params.env
    assert params.env['PYTHONIOENCODING'] == 'utf-8'
    assert params.args == ['-m', 'cst_mcp']


def test_server_params_can_force_fake_backend(real_script, tmp_path):
    """`--no-cst` 走假后端（离线骨架验证用）。"""
    pytest.importorskip('mcp')
    params = real_script.server_params(tmp_path / 'svc', tmp_path, backend='fake')
    assert params.env['TPC_MCP_BACKEND'] == 'fake'


def test_spec_shape_matches_the_mcp_contract(real_script, tmp_path):
    """建模规格必须带 `model.type` / `geometry` / `output.template_cst`。"""
    template = tmp_path / 'tmp.cst'
    template.write_text('placeholder', encoding='utf-8')
    real_script.CLEAN_TEMPLATE = str(template)          # 用临时替身，不依赖真机模板
    spec = real_script.spec_for(str(tmp_path), str(tmp_path / 'svc'), 'BA', 18)
    assert spec['model'] == {'type': 'straight_waveguide'}
    assert spec['geometry']['topology'] == 'BA'
    assert spec['output']['template_cst'] == str(template)
    assert spec['output']['path'].endswith('BA18.cst')


def test_find_cst_projects_requires_parameters_json(real_script, tmp_path):
    """只有带 `Model/Parameters.json` 的目录才算「真 CST 工程产物」。"""
    real = tmp_path / 'BA18.cst' / 'Model'
    real.mkdir(parents=True)
    (real / 'Parameters.json').write_text('{}', encoding='utf-8')
    fake = tmp_path / 'not_a_project' / 'Model'
    fake.mkdir(parents=True)                             # 只有目录，没有参数表
    found = real_script.find_cst_projects(str(tmp_path))
    assert found == [str(tmp_path / 'BA18.cst')]


def test_job_record_reads_the_service_layout(real_script, tmp_path):
    """任务记录在 `<workdir>/jobs/<job_id>.json`；缺文件要给路径而不是抛异常。"""
    jobs = tmp_path / 'jobs'
    jobs.mkdir()
    (jobs / 'job-1.json').write_text(json.dumps({'job_id': 'job-1', 'status': 'queued'}),
                                     encoding='utf-8')
    record, path = real_script.job_record(str(tmp_path), 'job-1')
    assert record['status'] == 'queued'
    assert path.endswith('job-1.json')
    missing, path = real_script.job_record(str(tmp_path), 'job-404')
    assert missing is None and path.endswith('job-404.json')


# ================================================================
# 重启恢复用的「伪造未完成记录」（离线跑，不执行任何后端动作）
# ================================================================

def test_craft_queued_record_leaves_an_unfinished_record(real_script, tmp_path):
    """`autostart=False` ⇒ 记录停在 `queued`，且用的是另一份模板副本（不撞副本冲突）。"""
    template = tmp_path / 'tmp.cst'
    template.write_text('placeholder', encoding='utf-8')
    workdir = tmp_path / 'svc'
    spec = {'model': {'type': 'straight_waveguide'},
            'geometry': {'length': 18, 'topology': 'BA'},
            'output': {'template_cst': str(template)}}
    job_id, job = real_script.craft_queued_record(str(workdir), spec, 'crafted-1')
    assert job['status'] == 'queued'
    record, path = real_script.job_record(str(workdir), job_id)
    assert record['status'] == 'queued'
    assert os.path.isfile(path)
    # 另一份模板副本已生成（名字带 request_id），原模板未被动过
    assert (tmp_path / 'crafted_crafted-1.cst').is_file()
    assert template.read_text(encoding='utf-8') == 'placeholder'


def test_craft_queued_record_is_repeatable(real_script, tmp_path):
    """同一工作目录连续伪造两次不能报 `project_exists`（各自用独立副本名）。"""
    template = tmp_path / 'tmp.cst'
    template.write_text('placeholder', encoding='utf-8')
    workdir = tmp_path / 'svc'
    spec = {'model': {'type': 'straight_waveguide'},
            'geometry': {'length': 18, 'topology': 'BA'},
            'output': {'template_cst': str(template)}}
    first, _ = real_script.craft_queued_record(str(workdir), spec, 'c1')
    second, _ = real_script.craft_queued_record(str(workdir), spec, 'c2')
    assert first != second
