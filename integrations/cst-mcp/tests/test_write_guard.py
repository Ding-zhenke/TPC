# -*- coding: utf-8 -*-
r"""
写入口纪律（计划 P1「MCP 写入口接入校验层」）
==============================================

计划要求：*「P3 的写入口必须**先调用** P1 做好的校验层（表达式/名称/配置的离线纯函数）
再下发 VBA，**不得另写一套规则**」*。

本文件把这条要求变成**可执行的检查**（不是注释）：

1. **清单自洽**：`WRITE_TOOLS` 与 `READ_TOOLS` 不重叠、并集正好是全部 11 个工具；
2. **经服务**：写入口必须走 `runtime.get_service()` 提交任务 —— MCP 层不直接碰 CST；
3. **先校验**：预检工具真的调用共用纯函数 `topo_modeler.preflight.validate_model_spec`；
4. **不重写**：`cst_mcp/` 的源码里**不得**出现 CST 原语
   （`add_to_history` / `cst.interface` / `cst.results` / `model3d.` …），
   也不得自带一套「禁止字符」「非法名字」规则。

⚠️ 第 2/3 条用**替身**（替身服务、替身预检）证明调用真的发生；
第 4 条是静态源码扫描 —— 结构不变式，防止以后有人在 MCP 层偷偷加一条 VBA 通道。
"""

import os
import pathlib
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, '..', 'src'))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from cst_mcp import runtime, tools      # noqa: E402


# ============================================================
# 1. 清单自洽
# ============================================================

def test_write_and_read_tools_partition_all_tools():
    """写入口 + 只读 = 全部工具，且两者不相交（新增工具必须显式归类）。"""
    write, read = set(tools.WRITE_TOOLS), set(tools.READ_TOOLS)
    assert not (write & read), f'同时被标为写和只读：{write & read}'
    assert write | read == set(tools.tool_names()), \
        f'未归类的工具：{set(tools.tool_names()) - (write | read)}'
    assert 'build_model' in write and 'run_simulation' in write


# ============================================================
# 2. 写入口经共用运行服务
# ============================================================

class _SpyService:
    """替身服务：记录 submit / close_project 调用，不执行任何东西。"""

    def __init__(self):
        self.submitted = []
        self.closed = []

    def submit(self, kind, **kwargs):
        self.submitted.append({'kind': kind, **kwargs})
        return {'job_id': 'job-1', 'status': 'queued', 'kind': kind}

    def close_project(self, project_id, save=True):
        self.closed.append({'project_id': project_id, 'save': save})
        return {'project_id': project_id, 'closed_session': True,
                'released': True}


@pytest.fixture
def spy_service(monkeypatch):
    spy = _SpyService()
    monkeypatch.setattr(runtime, 'get_service', lambda: spy)
    return spy


def test_build_model_goes_through_service(spy_service, tmp_path):
    """建模写入口必须提交给服务（而不是自己开 CST 建模）。"""
    template = tmp_path / 'tmp.cst'
    template.write_text('x', encoding='utf-8')
    out = tools.dispatch('build_model', {
        'spec': {'model': {'type': 'straight_waveguide'},
                 'output': {'template_cst': str(template)}}})
    assert out['ok'] is True
    assert len(spy_service.submitted) == 1
    call = spy_service.submitted[0]
    assert call['kind'] == 'build'
    assert call['params']['spec']['model']['type'] == 'straight_waveguide'
    assert call['project_path'] == str(template)


def test_run_simulation_goes_through_service(spy_service, tmp_path):
    template = tmp_path / 'tmp.cst'
    template.write_text('x', encoding='utf-8')
    out = tools.dispatch('run_simulation', {'project_path': str(template),
                                            'run_id': 2})
    assert out['ok'] is True
    call = spy_service.submitted[0]
    assert call['kind'] == 'solve'
    assert call['params']['run_id'] == 2


def test_close_project_goes_through_service(spy_service):
    out = tools.dispatch('close_project', {'project_id': 'p-1', 'save': False})
    assert out['ok'] is True
    assert spy_service.closed == [{'project_id': 'p-1', 'save': False}]


# ============================================================
# 3. 预检走共用纯函数
# ============================================================

def test_validate_model_spec_tool_uses_shared_preflight(monkeypatch, tmp_path):
    """预检工具必须是 `topo_modeler.preflight` 的**同一份**实现。"""
    import topo_modeler.preflight as preflight
    seen = []

    def spy(spec, **kwargs):
        seen.append({'spec': spec, 'kwargs': kwargs})
        return {'ok': True, 'valid': True, 'model_type': 'straight_waveguide',
                'errors': [], 'warnings': [], 'assumptions': [], 'effective': {},
                'field_sources': {}, 'checks': [], 'required_fields': [],
                'ctor_kwargs': {}, 'buildable': True, 'notes': []}

    monkeypatch.setattr(preflight, 'validate_model_spec', spy)
    out = tools.dispatch('validate_model_spec',
                         {'spec': {'model': {'type': 'straight_waveguide'}},
                          'spec_base_dir': str(tmp_path)})
    assert out['ok'] is True
    assert len(seen) == 1
    assert seen[0]['kwargs'].get('base_dir') == str(tmp_path)


# ============================================================
# 4. 静态：MCP 层不得自带 CST 原语或第二套校验规则
# ============================================================

# MCP 层一旦出现这些，就说明有人绕开共用能力自己下发/读取 CST
_FORBIDDEN_PRIMITIVES = ('add_to_history', 'cst.interface', 'cst.results',
                         'model3d.', 'full_history_rebuild', 'StoreParameter')

# 也不得自带一套「非法字符/非法名字」规则（应该调用 cst_solver.expressions）
_FORBIDDEN_VALIDATION = ('invalid_char', 'illegal_char', 'forbidden_char',
                         '名称非法', 'invalid_name')


def _source_files():
    return sorted(pathlib.Path(_SRC, 'cst_mcp').glob('*.py'))


def _code_lines(path):
    """
    只取**代码行**（丢掉整行注释）。

    `tools.py` 顶部的规则注释里会**引用**这些被禁的 token 作为说明，
    静态检查要禁的是「真的用了」，不是「提到了」。
    """
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.lstrip().startswith('#'):
            continue
        yield line


def test_mcp_layer_has_no_cst_primitives():
    offenders = []
    for path in _source_files():
        text = '\n'.join(_code_lines(path))
        for token in _FORBIDDEN_PRIMITIVES:
            if token in text:
                offenders.append(f'{path.name}: 出现 CST 原语 {token!r}')
    assert offenders == [], 'MCP 层不得直接操作 CST：' + '; '.join(offenders)


def test_mcp_layer_does_not_duplicate_validation_rules():
    """第二套校验规则是常见的漂移来源：名称/字符校验只能来自 cst_solver.expressions。"""
    offenders = []
    for path in _source_files():
        text = '\n'.join(_code_lines(path))
        for token in _FORBIDDEN_VALIDATION:
            if token in text:
                offenders.append(f'{path.name}: 疑似自带校验 {token!r}')
    assert offenders == [], '校验规则必须共用：' + '; '.join(offenders)


def test_mcp_layer_reuses_shared_validation_modules():
    """正着再钉一遍：MCP 层确实**引用**了共用校验/契约模块。"""
    blob = '\n'.join(path.read_text(encoding='utf-8') for path in _source_files())
    assert 'topo_modeler.preflight' in blob          # 配置/字段预检
    assert 'cst_solver.run_contract' in blob         # 运行判定与单位口径
    assert 'tpc_service' in blob                     # 执行与任务
