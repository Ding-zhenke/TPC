# -*- coding: utf-8 -*-
r"""
首版 MCP 工具实现（P3）
=======================

十一个工具（计划的「首版工具」清单），**全部是纯函数**：吃 dict、吐 dict，
不导入 MCP SDK、不碰事件循环，因此可以离线单测。

设计口径
--------
* **所有执行都走共用 Python 能力**：预检 → `topo_modeler.preflight`，
  执行/任务 → `tpc_service.RunService`，判定与单位 → `cst_solver.run_contract`，
  报告 → `topo_modeler.report`。本层**不重写**几何、VBA 或数值逻辑。
* **失败就是失败**：错误用 ``{ok: False, error: {code, message, details,
  retryable}}`` 返回，**不把失败变成空数据**。
* **关键物理条件缺失时明确报缺**（``missing_requirement``），
  让 AI 去问用户，而不是拿模板默认值静默代替；默认值一律在
  ``list_templates`` / ``validate_model_spec`` 的 ``effective`` 里显式可见。
* **大结果走产物引用**：`get_results` / `analyze_s_parameters` / `export_report`
  只回小摘要 + 文件路径，不回整条曲线。

@author: PC
"""

import os
from typing import Any, Callable, Dict, List, Optional

from cst_mcp import runtime
from cst_mcp.analysis import analyze_series, read_series_csv
from cst_mcp.errors import ToolError, error_payload, tool_payload

__all__ = ['TOOL_SPECS', 'HANDLERS', 'dispatch', 'tool_names', 'WRITE_TOOLS', 'READ_TOOLS']


# ============================================================
# 写入口清单（计划 P1「MCP 写入口接入校验层」的落点）
# ============================================================
#
# **会改变 CST 工程状态**的工具，一律遵守三条（不得在 MCP 层另起一套）：
#   1. 经 `runtime.get_service()` 提交任务 —— MCP 层**不直接**调用 CST/建模 API；
#   2. 预检/校验用共用纯函数：`topo_modeler.preflight.validate_model_spec`
#      （配置/字段/单位/取值域）与 `cst_solver.expressions`（表达式、名称、VBA 文本）；
#   3. 成败判定用 `cst_solver.run_contract`（求解）与产物引用（结果），
#      不在本层重写「结果算不算数」。
#
# 这三条由两处**机器**守住（不是靠注释）：
#   * `scripts/check_api_consistency.py` 的 `mcp-write-guard` 检查（静态）：
#     写入口必须引用 `runtime.get_service`，且 `cst_mcp/` 里**不得**出现
#     CST 原语（`add_to_history` / `cst.interface` / `cst.results` / `model3d.` …）；
#   * `integrations/cst-mcp/tests/test_write_guard.py`（运行期）：用替身服务与
#     替身预检证明「先校验、经服务、再执行」这条路真的被走到。
WRITE_TOOLS = ('build_model', 'run_simulation', 'close_project')

# 只读工具：不改变 CST 工程状态（可随时调用，不需要写入口那三条约束）。
# `export_report` 只往服务工作目录写报告文件，不动 CST 工程，因此算只读。
READ_TOOLS = ('get_capabilities', 'list_templates', 'validate_model_spec',
              'get_project_state', 'get_job_status', 'get_results',
              'analyze_s_parameters', 'export_report')


# ============================================================
# 工具表（JSON Schema；MCP 客户端据此校验与生成参数）
# ============================================================

def _spec(name: str, description: str, properties: Dict[str, Any],
          required: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        'name': name,
        'description': description,
        'inputSchema': {'type': 'object', 'properties': properties,
                        'required': list(required or []),
                        'additionalProperties': False},
    }


_SPEC_PROP = {'type': 'object',
              'description': '模型规格（与 topo_modeler 的配置同构：model/'
                             'geometry/feed/waveguide/solver/output 小节）'}
_PATH_PROP = {'type': 'string', 'description': '工程 .cst 路径'}

TOOL_SPECS: List[Dict[str, Any]] = [
    _spec(
        'get_capabilities',
        '报告当前环境能力：CST 是否可用、运行服务与后端、可构建模板、工具清单与'
        '已知限制。**先调用它**，再决定能不能真正建模/求解。它不会启动 CST。',
        {'probe': {'type': 'boolean',
                   'description': '是否尝试导入 CST 官方接口（默认 false，'
                                  '只做路径级诊断）'}},
    ),
    _spec(
        'list_templates',
        '列出模板及其**字段、类型、单位、取值范围与默认值**。'
        '只通过语法校验但尚未实现的类型会带 buildable=false，不得当成可构建。'
        '用户没给的关键物理条件（频段、单元尺寸、输出路径等）必须向用户确认，'
        '不要拿默认值静默代替。',
        {'model_type': {'type': 'string',
                        'description': '只看某一个模板（省略则全部）'},
         'include_planned': {'type': 'boolean',
                             'description': '是否连同尚未实现的类型一起列出'}},
    ),
    _spec(
        'validate_model_spec',
        '离线预检模型规格：字段/类型/单位/取值域校验 + 模板默认值合并 + '
        '路径检查。**不启动 CST、不建设计环境**，因此可以先反复预检再动手。',
        {'spec': _SPEC_PROP,
         'model_type': {'type': 'string', 'description': '覆盖 spec.model.type'},
         'require_output': {'type': 'boolean',
                            'description': '是否强制要求 spec.output.path'},
         'spec_base_dir': {'type': 'string',
                           'description': '解析 spec 内相对路径的基准目录'}},
        required=['spec'],
    ),
    _spec(
        'build_model',
        '按规格建模并保存工程（异步任务）：返回 job_id，用 get_job_status 查进度。'
        '需要工程模板路径：给 project_path，或在 spec.output.template_cst 里指定。',
        {'spec': _SPEC_PROP,
         'output': {'type': 'string', 'description': '输出 .cst 路径（可选）'},
         'project_id': {'type': 'string', 'description': '已注册工程 ID'},
         'project_path': _PATH_PROP,
         'request_id': {'type': 'string',
                        'description': '幂等键；同 ID 同参数不会重复建模'},
         'note': {'type': 'string'}},
        required=['spec'],
    ),
    _spec(
        'get_project_state',
        '查看工程状态：工作副本路径、是否服务创建的会话、最近的任务与产物。',
        {'project_id': {'type': 'string',
                        'description': '省略时列出全部工程'}},
    ),
    _spec(
        'run_simulation',
        '对已有工程启动求解（异步任务）：返回 job_id。'
        '求解耗时较长，必须用 get_job_status 轮询；'
        '结果只有在任务 succeeded 且结果确属本次运行时才可采信。',
        {'project_id': {'type': 'string', 'description': '已注册工程 ID'},
         'project_path': _PATH_PROP,
         'request_id': {'type': 'string', 'description': '幂等键'},
         'run_id': {'type': 'integer',
                    'description': '结果 run_id（0=当前最新；历史任务需真机确认）'},
         'note': {'type': 'string'}},
    ),
    _spec(
        'get_job_status',
        '查询任务状态（queued/running/succeeded/failed/interrupted）、'
        '日志与错误。interrupted 不等于成功，也不会自动重跑。',
        {'job_id': {'type': 'string'}},
        required=['job_id'],
    ),
    _spec(
        'get_results',
        '取任务结果**摘要**与产物路径（大结果给文件，不回整条曲线）。'
        '任务失败或结果缺失时返回结构化错误，而不是空数据。',
        {'job_id': {'type': 'string'}},
        required=['job_id'],
    ),
    _spec(
        'analyze_s_parameters',
        '分析 S 参数曲线：dB 口径 20·log10|S|（零值 −300 dB）、'
        '按阈值找出**多段连续合格区间**（相邻不合格点会断开，绝不合并成一段）、'
        '并可给出谐振/极值位置。数据来自 CSV 产物或工程结果。',
        {'csv_path': {'type': 'string',
                      'description': 'S 参数 CSV（第一列频率 GHz，其余列 S 参数）'},
         'project_path': _PATH_PROP,
         'job_id': {'type': 'string',
                    'description': '从该任务的产物里找 CSV'},
         'metric': {'type': 'string',
                    'description': '要分析的曲线名，如 S2,1（默认 S1,1）'},
         'threshold_db': {'type': 'number',
                          'description': '阈值（dB），必填'},
         'criterion': {'type': 'string', 'enum': ['below', 'above'],
                       'description': 'below=小于等于阈值合格（回波损耗）；'
                                      'above=大于等于阈值合格（插损）'},
         'band': {'type': 'array', 'items': {'type': 'number'},
                  'description': '[fmin, fmax] GHz，只在该频段内分析'},
         'max_gap_ghz': {'type': 'number',
                         'description': '相邻两点频差超过它即断开（默认只按采样相邻性）'},
         'resonance_kind': {'type': 'string', 'enum': ['min', 'max'],
                            'description': '是否同时找极值（谷/峰）'},
         'min_prominence_db': {'type': 'number',
                               'description': '极值最小幅度（dB），默认 0'},
         'run_id': {'type': 'integer'},
         'names': {'type': 'array', 'items': {'type': 'string'},
                   'description': '从工程读结果时要读的 S 参数名'}},
        required=['threshold_db'],
    ),
    _spec(
        'export_report',
        '生成 HTML / CSV 报告产物，返回文件路径。'
        '可以基于已有分析结果，也可以直接给 CSV 一次性「分析 + 出报告」。',
        {'analysis': {'type': 'object',
                      'description': 'analyze_s_parameters 的结果（可选）'},
         'csv_path': {'type': 'string', 'description': '没有 analysis 时用它现算'},
         'job_id': {'type': 'string', 'description': '从任务产物里找 CSV'},
         'threshold_db': {'type': 'number',
                          'description': '配合 csv_path 现算分析时使用'},
         'criterion': {'type': 'string', 'enum': ['below', 'above']},
         'metric': {'type': 'string'},
         'title': {'type': 'string'},
         'formats': {'type': 'array', 'items': {'type': 'string',
                                                'enum': ['html', 'csv']}},
         'out_dir': {'type': 'string',
                     'description': '产物目录（默认服务工作目录/reports）'}},
    ),
    _spec(
        'close_project',
        '关闭工程：只关闭本服务创建的会话，外部已有会话只解除注册。',
        {'project_id': {'type': 'string'},
         'save': {'type': 'boolean', 'description': '关闭前是否保存（默认 true）'}},
        required=['project_id'],
    ),
]


def tool_names() -> List[str]:
    """工具名清单。"""
    return [spec['name'] for spec in TOOL_SPECS]


# ============================================================
# 参数小工具
# ============================================================

def _require(arguments: Dict[str, Any], key: str, types=(str,),
             message: Optional[str] = None) -> Any:
    value = (arguments or {}).get(key)
    if value is None or value == '':
        raise ToolError('missing_requirement',
                        message or f'缺少必需参数 {key!r}', missing=key)
    if types and not isinstance(value, types):
        raise ToolError('invalid_arguments',
                        f'{key} 类型不对：期望 '
                        f'{"|".join(t.__name__ for t in types)}，'
                        f'收到 {type(value).__name__}',
                        argument=key, got=type(value).__name__)
    return value


def _optional_band(arguments: Dict[str, Any]) -> Optional[tuple]:
    band = (arguments or {}).get('band')
    if band is None:
        return None
    if (not isinstance(band, (list, tuple)) or len(band) != 2
            or not all(isinstance(v, (int, float)) for v in band)):
        raise ToolError('invalid_arguments', 'band 应为 [fmin, fmax]（GHz）',
                        band=band)
    if float(band[0]) >= float(band[1]):
        raise ToolError('invalid_arguments', 'band 的 fmin 必须小于 fmax', band=band)
    return (float(band[0]), float(band[1]))


def _csv_from_job(job_id: str) -> Optional[str]:
    """从某个任务的产物里找 CSV。"""
    service = runtime.get_service()
    job = service.get(job_id)
    for artifact in job.get('artifacts') or []:
        path = str(artifact.get('path') or '')
        if path.lower().endswith('.csv') and os.path.isfile(path):
            return path
    return None


# ============================================================
# 工具实现
# ============================================================

def handle_get_capabilities(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """能力发现：CST 可用性、后端、模板、工具与限制（不启动 CST）。"""
    from cst_solver.environment import diagnose_environment
    from topo_modeler.config import IMPLEMENTED_MODEL_TYPES, PLANNED_MODEL_TYPES

    probe = bool((arguments or {}).get('probe', False))
    try:
        cst = diagnose_environment(probe=probe)
    except Exception as exc:                          # noqa: BLE001
        cst = {'status': 'diagnosis_failed', 'error': str(exc)}

    run = runtime.describe_runtime()
    notes = []
    if run['backend'] == 'fake':
        notes.append('当前使用**假后端**（TPC_MCP_BACKEND=fake）：'
                     '建模/求解返回的是合成结果，不能当作真实仿真结论。')
    if cst.get('status') in ('unavailable', 'configuration_error'):
        notes.append('当前环境 CST 不可用；离线工具（能力发现/模板列表/预检/'
                     'CSV 分析/报告）仍可用，建模与求解会失败。')
    return tool_payload({
        'cst': {k: cst.get(k) for k in
                ('status', 'python_executable', 'python_version', 'probe',
                 'python_lib_exists', 'module_discoverable', 'errors',
                 'paths', 'error')},
        # 顶层再给一份最常用的信息，客户端不必先钻进 runtime 里找
        'backend': run['backend'],
        'workdir': run['workdir'],
        'runtime': run,
        'templates': {'implemented': list(IMPLEMENTED_MODEL_TYPES),
                      'planned_not_buildable': list(PLANNED_MODEL_TYPES)},
        'tools': tool_names(),
        'limits': {
            'single_worker_serial': '所有执行串行（单 CST worker）',
            'cancel_running_job': '不支持：**运行中**的任务无法取消（不提供虚假的「已取消」）。'
                                  '2026-09-17 真机探针已确认 CST 侧**存在** '
                                  '`abort_solver` / `start_solver` / `get_solver_run_info` '
                                  '（不存在 `AbortSolver` / `stop_solver` / `IsSolving`）；'
                                  '但「调用后求解**真的**停下」必须在**一次运行中的求解**里观测，'
                                  '在那之前接口保持关闭。'
                                  '探针：python scripts/probe_solver_control_api.py --live',
            # ⚠️ 这里**按任务种类**如实标注：真机只验证到「建模」这一段，
            #    求解与扫描/批量/优化仍只有离线编排证据（需要真实求解）。
            'real_cst_backend_verified': {
                'build': True,                       # 真 CST 建模 succeeded + Rebuild 验收 success
                'solve': False,
                'study': False,
                'note': 'build 已真机验证（2026-09-17，真 CST + 真 stdio）；'
                        'solve/study 需要真实求解，尚未验证；'
                        '见 docs/SUPPORT_MATRIX.md',
            },
            'solver_progress': '不提供百分比进度：CST 的进度回调**未核实**'
                               '（只确认了 `get_solver_run_info` / `get_active_solver_name` '
                               '这类接口在真机上存在，其语义要等一次运行中的求解才能观测）。'
                               '当前只给：任务状态 + 日志尾部 + 时间戳 —— 不编造进度。',
            'long_running': '求解是长任务；用 get_job_status 轮询，不要假设立即完成',
        },
    }, notes=notes)


def handle_list_templates(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """模板列表（含字段/单位/取值域/默认值/必填项）。"""
    from topo_modeler.preflight import describe_template, list_templates

    model_type = (arguments or {}).get('model_type')
    include_planned = bool((arguments or {}).get('include_planned', False))
    if model_type:
        template = describe_template(model_type)      # 未知类型会抛 ConfigError
        templates = [template]
    else:
        templates = list_templates(include_planned=include_planned)
    buildable = [t['model_type'] for t in templates if t['buildable']]
    notes = []
    if not include_planned:
        notes.append('默认只列可构建的模板；要连尚未实现的类型一起看，'
                     '传 include_planned=true。')
    return tool_payload({'templates': templates, 'buildable': buildable},
                        notes=notes)


def handle_validate_model_spec(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """离线预检（不创建 DE）。"""
    from topo_modeler.preflight import validate_model_spec

    spec = _require(arguments, 'spec', (dict,))
    report = validate_model_spec(
        spec,
        model_type=(arguments or {}).get('model_type'),
        base_dir=(arguments or {}).get('spec_base_dir'),
        require_output=bool((arguments or {}).get('require_output', False)))
    if not report['ok']:
        first = (report['errors'] or [{}])[0]
        return error_payload(first.get('code', 'invalid_arguments'),
                             first.get('message', '预检未通过'),
                             report=report)
    return tool_payload({'valid': True, 'buildable': report['buildable'],
                         'model_type': report['model_type'],
                         'effective': report['effective'],
                         'field_sources': report['field_sources'],
                         'ctor_kwargs': report['ctor_kwargs'],
                         'required_fields': report['required_fields'],
                         'assumptions': report['assumptions'],
                         'warnings': report['warnings'],
                         'checks': report['checks']},
                        notes=report['assumptions'])


def handle_build_model(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """建模任务（异步）。"""
    spec = _require(arguments, 'spec', (dict,))
    project_path = (arguments or {}).get('project_path') or \
        ((spec.get('output') or {}).get('template_cst'))
    project_id = (arguments or {}).get('project_id')
    if not project_id and not project_path:
        raise ToolError(
            'missing_requirement',
            '建模需要工程模板路径：请提供 project_path，'
            '或在 spec.output.template_cst 里指定模板 .cst。'
            '（请向用户确认模板工程位置，不要凭空假定）',
            missing='project_path')
    service = runtime.get_service()
    job = service.submit('build', project_id=project_id,
                         project_path=project_path,
                         params={'spec': spec,
                                 'output': (arguments or {}).get('output')},
                         request_id=(arguments or {}).get('request_id'),
                         note=(arguments or {}).get('note', ''))
    return _job_payload(job, 'build')


def handle_get_project_state(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """工程状态（工作副本、会话归属、最近任务）。"""
    service = runtime.get_service()
    project_id = (arguments or {}).get('project_id')
    jobs = service.list_jobs()
    if project_id:
        record = service.registry.get(project_id)     # 未注册会抛 ServiceError
        payload = {'project': record.to_dict(),
                   'jobs': [j for j in jobs if j.get('project_id') == project_id],
                   'workdir': service.workdir}
        path = record.path
        payload['exists'] = os.path.exists(path)
        payload['size_bytes'] = os.path.getsize(path) if os.path.isfile(path) else None
        return tool_payload(payload)
    return tool_payload({'projects': service.projects(),
                         'jobs': jobs[-20:], 'workdir': service.workdir,
                         'n_jobs': len(jobs)})


def handle_run_simulation(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """求解任务（异步）。"""
    project_id = (arguments or {}).get('project_id')
    project_path = (arguments or {}).get('project_path')
    if not project_id and not project_path:
        raise ToolError('missing_requirement',
                        '求解需要 project_id 或 project_path '
                        '（先建模，或把已有工程注册进来）',
                        missing='project_id|project_path')
    params = {}
    if (arguments or {}).get('run_id') is not None:
        params['run_id'] = int(arguments['run_id'])
    if (arguments or {}).get('note'):
        params['note'] = arguments['note']
    service = runtime.get_service()
    job = service.submit('solve', project_id=project_id,
                         project_path=project_path, params=params,
                         request_id=(arguments or {}).get('request_id'),
                         note=(arguments or {}).get('note', ''))
    return _job_payload(job, 'solve')


def _job_payload(job: Dict[str, Any], kind: str) -> Dict[str, Any]:
    notes = []
    if job.get('duplicate'):
        notes.append('这是重复请求：返回既有任务，不会再执行一次。')
    if kind in ('solve', 'build'):
        notes.append('这是异步长任务：请用 get_job_status 轮询，'
                     'succeeded 之后再用 get_results。')
    return tool_payload({'job_id': job['job_id'], 'status': job['status'],
                         'kind': job['kind'], 'duplicate': job.get('duplicate', False),
                         'project_id': job.get('project_id'),
                         'project_path': job.get('project_path'),
                         'request_id': job.get('request_id')}, notes=notes)


def handle_get_job_status(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """任务状态。"""
    job_id = _require(arguments, 'job_id', (str,))
    job = runtime.get_service().get(job_id)
    payload = {'job_id': job['job_id'], 'kind': job['kind'],
               'status': job['status'], 'created_at': job['created_at'],
               'started_at': job['started_at'], 'finished_at': job['finished_at'],
               'error': job['error'], 'n_log_lines': len(job.get('log') or []),
               'log_tail': (job.get('log') or [])[-5:],
               'artifacts': job.get('artifacts') or [],
               'run_identity': job.get('run_identity') or {}}
    notes = []
    if job['status'] == 'interrupted':
        notes.append('任务被中断（例如服务重启或尚未开始即被取消）：'
                     '**不得**当作成功，也不会自动重跑。')
    if job['status'] == 'failed':
        notes.append('任务失败：错误见 error 字段，不要用空数据代替。')
    return tool_payload(payload, notes=notes)


def handle_get_results(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """结果摘要 + 产物（失败就是失败）。"""
    job_id = _require(arguments, 'job_id', (str,))
    service = runtime.get_service()
    job = service.get(job_id)
    if job['status'] != 'succeeded':
        error = job.get('error') or {}
        return error_payload(
            error.get('code', 'not_found'),
            f"任务 {job_id} 状态为 {job['status']}，没有可采信的结果："
            f"{error.get('message', '')}",
            job_id=job_id, status=job['status'], job_error=job.get('error'))
    payload = service.result(job_id)
    return tool_payload(payload, notes=[
        'result_summary 是小摘要；完整数据在 artifacts 指向的文件里。',
        'run_identity 标明结果属于哪次运行；run_id=0 指当前最新结果。',
    ])


def handle_analyze_s_parameters(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """S 参数分析（连续合格区间 + 极值）。"""
    arguments = arguments or {}
    threshold = arguments.get('threshold_db')
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise ToolError('invalid_arguments', 'threshold_db 必须是数值（dB）',
                        got=type(threshold).__name__)
    metric = str(arguments.get('metric') or 'S1,1')
    criterion = str(arguments.get('criterion') or 'below')
    band = _optional_band(arguments)
    source = _load_series_for_analysis(arguments, metric)
    series = source['series']
    column = _pick_column(series, metric)

    analysis = analyze_series(
        series['freqs'], column, metric=metric, threshold_db=float(threshold),
        criterion=criterion, band=band,
        max_gap_ghz=(float(arguments['max_gap_ghz'])
                     if arguments.get('max_gap_ghz') is not None else None),
        resonance_kind=arguments.get('resonance_kind'),
        min_prominence_db=float(arguments.get('min_prominence_db') or 0.0),
        data_source=source['data_source'],
        series_reference={'path': series.get('path'),
                          'n_points': len(series['freqs']),
                          'note': '完整曲线在产物文件里，摘要不回整条曲线'})
    return tool_payload({'analysis': analysis}, notes=[
        'total_bandwidth_ghz 是**各段带宽之和**，不是一段连续带宽。',
        '谐振是采样点级局部极值（不做插值）：比较两个模型时要使用同一套频点。',
    ])


def _load_series_for_analysis(arguments: Dict[str, Any], metric: str) -> Dict[str, Any]:
    """把三种数据来源（CSV / 工程结果 / 任务产物）统一成曲线字典。"""
    csv_path = arguments.get('csv_path')
    if not csv_path and arguments.get('job_id'):
        csv_path = _csv_from_job(str(arguments['job_id']))
        if csv_path:
            arguments = dict(arguments)
            arguments['csv_path'] = csv_path
    if csv_path:
        series = read_series_csv(str(csv_path))
        return {'series': series,
                'data_source': {'kind': 'csv', 'path': series['path'],
                                'column_units': series.get('column_units')}}

    project_path = arguments.get('project_path')
    if project_path:
        names = list(arguments.get('names') or [metric])
        run_id = int(arguments.get('run_id') or 0)
        try:
            from topo_modeler.result_reader import ResultReader
            reader = ResultReader(str(project_path), names=names, run_id=run_id)
            freqs: List[float] = []
            columns: Dict[str, List[float]] = {}
            for name in names:
                data = reader.read_s_parameters_db(name=name, run_id=run_id)
                pairs = _pairs_from_reader(data)
                if not pairs:
                    continue
                if not freqs:
                    freqs = [p[0] for p in pairs]
                columns[name] = [p[1] for p in pairs]
        except Exception as exc:                          # noqa: BLE001
            raise ToolError('analysis_failed',
                            f'从工程读 S 参数失败：{type(exc).__name__}: {exc}',
                            retryable=True, project_path=str(project_path)) from exc
        if not columns:
            raise ToolError('analysis_failed',
                            '工程里没有读到 S 参数曲线（检查 names / run_id）',
                            project_path=str(project_path))
        return {'series': {'freqs': freqs, 'columns': columns,
                           'path': str(project_path),
                           'column_units': {n: 'dB' for n in columns}},
                'data_source': {'kind': 'project', 'path': str(project_path),
                                'run_id': run_id, 'names': names}}

    raise ToolError('missing_requirement',
                    '分析需要数据来源：请给 csv_path（推荐，用产物文件）、'
                    'job_id（从任务产物里找 CSV）或 project_path + names。'
                    '不要凭记忆编造曲线。',
                    missing='csv_path|job_id|project_path')


def _pairs_from_reader(data: Any) -> List[tuple]:
    """把 ResultReader 的返回归一成 ``[(freq, dB), ...]``。"""
    if data is None:
        return []
    if isinstance(data, tuple) and len(data) == 2:
        xs, ys = data
        return list(zip((float(x) for x in xs), (float(y) for y in ys)))
    rows = list(data)
    out = []
    for row in rows:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            out.append((float(row[0]), float(row[1])))
    return out


def _pick_column(series: Dict[str, Any], metric: str) -> List[float]:
    """按名字取列；名字对不上时给出**可选项清单**而不是猜。"""
    columns = series.get('columns') or {}
    if metric in columns:
        return columns[metric]
    for name, values in columns.items():          # S2,1 / S21 / S(2,1) 宽容匹配
        if _same_metric(name, metric):
            return values
    if len(columns) == 1:
        return next(iter(columns.values()))
    raise ToolError('invalid_arguments',
                    f'CSV 里没有曲线 {metric!r}；可用的有：{list(columns)}',
                    metric=metric, available=list(columns))


def _same_metric(a: str, b: str) -> bool:
    def norm(text: str) -> str:
        return ''.join(ch for ch in text.lower() if ch.isalnum())
    return norm(a) == norm(b)


def handle_export_report(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """导出 HTML/CSV 报告产物。"""
    from cst_mcp.reporting import export_report

    arguments = arguments or {}
    analysis = arguments.get('analysis')
    series = None
    if not analysis:
        threshold = arguments.get('threshold_db')
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            raise ToolError('missing_requirement',
                            '没有 analysis 时必须给出 threshold_db（用来现算）',
                            missing='analysis|threshold_db')
        metric = str(arguments.get('metric') or 'S1,1')
        source = _load_series_for_analysis(arguments, metric)
        series = source['series']
        analysis = analyze_series(
            series['freqs'], _pick_column(series, metric), metric=metric,
            threshold_db=float(threshold),
            criterion=str(arguments.get('criterion') or 'below'),
            data_source=source['data_source'])
    else:
        csv_path = arguments.get('csv_path')
        if not csv_path and arguments.get('job_id'):
            csv_path = _csv_from_job(str(arguments['job_id']))
        if csv_path:
            series = read_series_csv(str(csv_path))

    service = runtime.get_service()
    out_dir = arguments.get('out_dir') or os.path.join(service.workdir, 'reports')
    result = export_report(
        analysis=analysis, workdir=service.workdir, out_dir=str(out_dir),
        title=str(arguments.get('title') or 'TPC S 参数报告'),
        formats=arguments.get('formats') or ('html', 'csv'),
        series=series,
        meta={'工作目录': service.workdir,
              '后端': getattr(service.backend, 'name', 'unknown')})
    return tool_payload({'artifacts': result['artifacts'],
                         'summary': result['summary'],
                         'analysis': analysis}, notes=[
        '报告是产物文件：把路径交给用户或客户端去取，不要把整份 HTML 塞回对话。',
    ])


def handle_close_project(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """关闭工程（只关自有会话）。"""
    project_id = _require(arguments, 'project_id', (str,))
    save = bool((arguments or {}).get('save', True))
    service = runtime.get_service()
    result = service.close_project(project_id, save=save)
    notes = []
    if not result['closed_session']:
        notes.append('该工程不是本服务创建的会话：只解除注册，没有关闭外部 CST。')
    return tool_payload(result, notes=notes)


HANDLERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    'get_capabilities': handle_get_capabilities,
    'list_templates': handle_list_templates,
    'validate_model_spec': handle_validate_model_spec,
    'build_model': handle_build_model,
    'get_project_state': handle_get_project_state,
    'run_simulation': handle_run_simulation,
    'get_job_status': handle_get_job_status,
    'get_results': handle_get_results,
    'analyze_s_parameters': handle_analyze_s_parameters,
    'export_report': handle_export_report,
    'close_project': handle_close_project,
}


def dispatch(name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    调用一个工具并返回**结构化结果**（永不抛异常）。

    :param name: str, 工具名
    :param arguments: dict 可选, 工具参数
    :return: dict, ``{'ok': True, ...}`` 或 ``{'ok': False, 'error': {...}}``
    """
    handler = HANDLERS.get(name)
    if handler is None:
        return error_payload('unknown_tool',
                             f'未知工具 {name!r}；可用：{tool_names()}',
                             tool=name, available=tool_names())
    try:
        return handler(dict(arguments or {}))
    except ToolError as exc:
        return error_payload(exc.code, str(exc), retryable=exc.retryable,
                             **exc.details)
    except Exception as exc:                          # noqa: BLE001
        # 底层异常（ServiceError / ConfigError / OSError …）也要变成结构化失败，
        # 并保留它自己的错误码 —— 不吞、不变成空数据
        code = getattr(exc, 'code', None)
        details = dict(getattr(exc, 'details', {}) or {})
        retryable = bool(getattr(exc, 'retryable', False))
        if code is None:
            code = 'tool_failed'
            details = {'exception': f'{type(exc).__name__}: {exc}'}
        return error_payload(str(code), str(exc), retryable=retryable,
                             tool=name, **details)
