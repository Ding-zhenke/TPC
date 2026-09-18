# -*- coding: utf-8 -*-
r"""
配置 / 建模预检（P1）
=====================

为什么需要
----------
`topo_modeler.config` 已经把「取值域 → 可执行校验」这条做完（未知字段、类型、
范围、枚举、与模板签名对表），并且有 `template_from_config(validate_only=True)`
这个**不建实例**的入口。但作为「照用户描述建模」的入口，它还缺两件事：

1. **结构化的字段说明** —— `field_help()` 返回的是给人看的文本行，
   机器（MCP 工具 `list_templates` / AI 客户端）需要
   ``{字段, 类型, 单位, 取值范围, 默认值, 是否必填}`` 这样的结构；
2. **「能不能建」的明确结论** —— 语法上合法 ≠ 可以构建。
   :data:`topo_modeler.config.PLANNED_MODEL_TYPES` 里的类型（GRIN 透镜天线、
   功分器、MZI 开关…）当前**没有模板类**，`validate_config()` 出于兼容只给一条
   warning；预检层必须把它们报成 ``model_type_not_implemented``，
   不能宣布为可构建。

本模块就是这两件事的落点：**首版支持的模板**（``straight_waveguide`` /
``unit_antenna``）的字段、类型、单位、取值范围、默认值，以及一次不碰 CST 的
预检结果。

离线保证
--------
:func:`validate_model_spec` **不导入 CST、不创建设计环境（DE）**：

* 字段与默认值来自 :mod:`topo_modeler.config`（纯 Python，惰性导入模板类只看签名）；
* CST 可用性只用 :func:`cst_solver.environment.diagnose_environment`
  （``probe=False``，只解析路径与模块可发现性），并且**只是信息**，
  不影响 ``ok`` —— 离线机器上预检照样能给出结论。

用法::

    >>> from topo_modeler.preflight import list_templates, validate_model_spec
    >>> list_templates()[0]['fields'][0]
    {'section': 'geometry', 'name': 'lattice_constant', ...}
    >>> report = validate_model_spec({'model': {'type': 'straight_waveguide'},
    ...                               'geometry': {'length': 18}})
    >>> report['ok'], report['buildable']
    (True, True)

@author: PC
"""

import os
from typing import Any, Dict, List, Optional

from topo_modeler.config import (
    ALL_MODEL_TYPES,
    ConfigError,
    FIELD_SPECS,
    IMPLEMENTED_MODEL_TYPES,
    PLANNED_MODEL_TYPES,
    _MODEL_TYPE_INFO,
    accepted_fields,
    example_config,
    validate_config,
)

__all__ = [
    'list_templates',
    'describe_template',
    'validate_model_spec',
    'SUPPORTED_MODEL_TYPES',
    'NOT_IMPLEMENTED_CODE',
    'PREFLIGHT_ERROR_CODES',
]

#: 预检层**自己产出**的错误码（配置层透传的 `config_*` 见 `CONFIG_ERROR_CODES`）。
#: 一致性检查要求代码里用到的码必须出现在某个 `*_ERROR_CODES` 表里。
PREFLIGHT_ERROR_CODES = (
    'config_invalid',                  # 配置层给的兜底码
    'config_invalid_character',        # 字段值含危险字符（复用表达式校验层）
    'config_model_type_invalid',       # 模型类型未知/未实现
    'template_not_found',              # 模板 .cst 不存在
    'output_required',                 # 要求落盘但没给路径
    'output_not_writable',             # 输出目录不可写
)

#: 首版承诺支持的模板（= 真的有模板类、能被预检宣布为可构建的那些）
SUPPORTED_MODEL_TYPES = IMPLEMENTED_MODEL_TYPES

#: 模型类型尚未实现的错误码（MCP 客户端可按码分流）
NOT_IMPLEMENTED_CODE = 'model_type_not_implemented'


# ============================================================
# 结构化字段描述
# ============================================================

def _effective_defaults(model_type: str) -> Dict[str, Any]:
    """
    该模型类型下**每个字段的生效默认值**（``{section: {name: value}}``）。

    复用 :func:`topo_modeler.config.example_config`：它优先取模板构造签名的
    默认值，其次取 :data:`topo_modeler.config.FIELD_SPECS` 的 ``default``，
    因此「模板默认值」在预检结果里始终可见（``cst_mcp.md`` §5 的要求）。

    :param model_type: str, 模型类型
    :return: dict；未实现的类型返回空字典（没有签名可查）
    """
    if model_type not in IMPLEMENTED_MODEL_TYPES:
        return {}
    defaults = example_config(model_type)
    return {k: v for k, v in defaults.items() if k != 'model'}


def _field_dict(spec, model_type: str, defaults: Dict[str, Any],
                ok_names: Optional[set]) -> Dict[str, Any]:
    """把一条 :class:`~topo_modeler.config.FieldSpec` 转成结构化字典。"""
    default = None
    has_default = False
    section_defaults = defaults.get(spec.section) or {}
    if spec.name in section_defaults:
        default = section_defaults[spec.name]
        has_default = True

    return {
        'section': spec.section,
        'name': spec.name,
        'dotted': spec.dotted,
        'kind': spec.kind,
        'unit': spec.unit,
        'ctor': spec.ctor,
        'choices': list(spec.choices),
        'min_value': spec.min_value,
        'max_value': spec.max_value,
        'exclusive_min': spec.exclusive_min,
        'default': default,
        'has_default': has_default,
        # 「必填」= 该模板支持这个字段、但没有默认值可用（如 output.path）
        'required': bool(ok_names is not None
                         and spec.name in ok_names and not has_default),
        'supported': bool(ok_names is None or spec.name in ok_names),
        'doc': spec.doc,
    }


def describe_template(model_type: str) -> Dict[str, Any]:
    """
    单个模板的完整结构化说明（字段 / 类型 / 单位 / 取值范围 / 默认值 / 必填）。

    :param model_type: str, 模型类型（``straight_waveguide`` / ``unit_antenna`` …）
    :return: dict::

        {
          "model_type": "straight_waveguide",
          "class": "StraightWaveguide",     # 未实现时为 None
          "stage": "阶段 3",
          "buildable": True,                # 现在真的能构建
          "reason": "",                     # buildable=False 时说明原因
          "required": ["output.path", ...], # 无默认值的字段
          "sections": ["geometry", ...],
          "fields": [ {...}, ... ],         # 该模板支持的字段
        }

    :raises ConfigError: 未知 model_type
    """
    if model_type not in ALL_MODEL_TYPES:
        raise ConfigError(
            f"未知 model.type={model_type!r}；合法取值：{' | '.join(ALL_MODEL_TYPES)}",
            code='config_model_type_invalid', model_type=model_type)

    class_name, stage = _MODEL_TYPE_INFO[model_type]
    buildable = model_type in IMPLEMENTED_MODEL_TYPES
    defaults = _effective_defaults(model_type)

    if buildable:
        try:
            ok_names: Optional[set] = set(accepted_fields(model_type))
        except ConfigError:
            ok_names, buildable = None, False
    else:
        ok_names = None                          # 没有签名可对，全部标 supported=True

    fields = [_field_dict(spec, model_type, defaults, ok_names)
              for spec in FIELD_SPECS if spec.section != 'model'
              and (ok_names is None or spec.name in ok_names)]

    required = [f['dotted'] for f in fields if f['required']]
    sections: List[str] = []
    for field in fields:
        if field['section'] not in sections:
            sections.append(field['section'])

    return {
        'model_type': model_type,
        'class': class_name if buildable else None,
        'stage': stage,
        'buildable': buildable,
        'reason': '' if buildable else (
            f'{class_name} 模板尚未实现（{stage}）；'
            f'当前可构建的类型：{" | ".join(IMPLEMENTED_MODEL_TYPES)}'),
        'required': required,
        'sections': sections,
        'defaults': {k: dict(v) for k, v in defaults.items()},
        'fields': fields,
    }


def list_templates(*, include_planned: bool = False) -> List[Dict[str, Any]]:
    """
    首版支持的模板清单（MCP ``list_templates`` 的底层实现）。

    :param include_planned: bool, True 时把**尚未实现**的类型也列出来，
        但它们带 ``buildable=False`` 与 ``reason``；默认 False 只列可构建的
    :return: list[dict], 每项见 :func:`describe_template`
    """
    types = ALL_MODEL_TYPES if include_planned else SUPPORTED_MODEL_TYPES
    return [describe_template(t) for t in types]


# ============================================================
# 预检
# ============================================================

def _error(code: str, message: str, *, retryable: bool = False, **details) -> Dict:
    """统一错误结构（唯一实现在 ``cst_solver.failures.structured_error``）。"""
    from cst_solver.failures import structured_error
    return structured_error(code, message, retryable=retryable, **details)


def _resolve(path: str, base_dir: Optional[str]) -> str:
    """相对路径按 ``base_dir``（默认进程工作目录）解析成绝对路径。"""
    if os.path.isabs(path):
        return os.path.abspath(path)
    return os.path.abspath(os.path.join(base_dir or os.getcwd(), path))


def _check_template_cst(path: str, base_dir: Optional[str]) -> Dict:
    """检查 ``output.template_cst`` 是否存在（模板工程是建模的前提）。"""
    resolved = _resolve(path, base_dir)
    if os.path.isdir(resolved):
        return {'name': 'template_cst', 'status': 'error', 'detail':
                f'{resolved} 是目录，不是 .cst 工程文件'}
    if not os.path.exists(resolved):
        return {'name': 'template_cst', 'status': 'error', 'detail':
                f'模板工程不存在：{resolved}（模板是先建实例再建模的前提）',
                'path': resolved}
    return {'name': 'template_cst', 'status': 'ok', 'detail': resolved,
            'path': resolved}


def _check_output_dir(path: str, base_dir: Optional[str]) -> Dict:
    """
    检查输出路径的目录是否可写。

    只在目录**已存在**时用临时探测文件判断（Windows 上 ``os.access`` 不可靠），
    探测文件写完立即删除；目录不存在时只提示「建模时会创建」，
    **不创建目录本身**。
    """
    resolved = _resolve(path, base_dir)
    parent = os.path.dirname(resolved) or '.'
    if not os.path.isdir(parent):
        return {'name': 'output_dir', 'status': 'ok',
                'detail': f'目录 {parent} 尚不存在，建模时会创建',
                'path': parent, 'created_later': True}
    probe = os.path.join(parent, '.tpc_preflight_write_probe')
    try:
        with open(probe, 'w', encoding='utf-8') as handle:
            handle.write('ok')
        os.remove(probe)
    except OSError as exc:
        return {'name': 'output_dir', 'status': 'error',
                'detail': f'目录 {parent} 不可写：{exc}', 'path': parent}
    return {'name': 'output_dir', 'status': 'ok', 'detail': parent, 'path': parent}


def _diagnose_cst() -> Dict:
    """CST 可用性诊断（``probe=False``：不导入 CST、不建 DE）；失败不抛异常。"""
    try:
        from cst_solver.environment import diagnose_environment
    except Exception as exc:                          # noqa: BLE001
        return {'status': 'diagnosis_failed', 'error': str(exc)}
    try:
        return diagnose_environment(probe=False)
    except Exception as exc:                          # noqa: BLE001
        return {'status': 'diagnosis_failed', 'error': str(exc)}


def validate_model_spec(spec, *, model_type: Optional[str] = None,
                        base_dir: Optional[str] = None,
                        check_paths: bool = True,
                        require_output: bool = False,
                        diagnose_cst: bool = True) -> Dict[str, Any]:
    """
    预检一份模型规格（MCP ``validate_model_spec`` 的底层实现）。

    **不导入 CST、不创建设计环境**：字段校验走
    :func:`topo_modeler.config.validate_config`，模板签名只看 ``inspect``，
    CST 可用性只做路径级诊断。

    :param spec: dict 或 YAML 路径，结构同 ``topo_modeler.config`` 的配置
    :param model_type: str 可选, 覆盖 ``model.type``
    :param base_dir: str 可选, 解析相对路径的基准目录（默认进程工作目录）
    :param check_paths: bool, 是否检查 ``template_cst`` 与输出目录（默认 True）
    :param require_output: bool, True 时把「缺 ``output.path``」当错误；
        False（默认）时只作为假设记录下来 —— 只建模不落盘是合法用法
    :param diagnose_cst: bool, 是否附带 CST 可用性诊断（默认 True，只读）
    :return: dict::

        {
          "ok": bool,                # 规格是否可用（且类型可构建）
          "buildable": bool,         # 现在真的能建（类型已实现）
          "model_type": str | None,
          "class": str | None,
          "stage": str,
          "normalized": {...},       # 校验后的用户输入
          "effective": {...},        # 用户输入 + 模板默认值（默认值可见）
          "field_sources": {...},    # 每个字段来自 "user" 还是 "default"
          "ctor_kwargs": {...},      # 会真正传给模板构造的参数
          "required_fields": [...],  # 该模板无默认值的字段
          "errors": [ {code,message,details,retryable} ],
          "warnings": [...],
          "assumptions": [...],      # 预检替用户做的假设，必须回显
          "checks": [ {name,status,detail} ],
          "cst": {...},              # 诊断结果（信息，不影响 ok）
        }
    """
    errors: List[Dict] = []
    warnings: List[str] = []
    assumptions: List[str] = []
    checks: List[Dict] = []
    normalized: Dict[str, Any] = {}
    effective: Dict[str, Any] = {}
    sources: Dict[str, str] = {}
    ctor_kwargs: Dict[str, Any] = {}
    required_fields: List[str] = []

    # ---- 1. 取值域校验（不碰 CST）----
    try:
        normalized = validate_config(spec, model_type=model_type)
    except ConfigError as exc:
        errors.append(_error(getattr(exc, 'code', 'config_invalid'), str(exc),
                             retryable=False, **getattr(exc, 'details', {})))
        mtype = model_type or _peek_model_type(spec)
    except Exception as exc:                          # noqa: BLE001
        errors.append(_error('config_invalid', f'配置校验异常：{exc!r}'))
        mtype = model_type or _peek_model_type(spec)
    else:
        mtype = normalized.get('model', {}).get('type')

    info = describe_template(mtype) if mtype in ALL_MODEL_TYPES else None
    buildable = bool(info and info['buildable'])

    # ---- 2. 类型能不能建 ----
    if mtype in PLANNED_MODEL_TYPES:
        errors.append(_error(
            NOT_IMPLEMENTED_CODE,
            f'model.type={mtype!r} 尚未实现：{_MODEL_TYPE_INFO[mtype][0]} 模板不存在'
            f'（{_MODEL_TYPE_INFO[mtype][1]}）。'
            f'当前可构建的类型：{" | ".join(IMPLEMENTED_MODEL_TYPES)}',
            model_type=mtype, stage=_MODEL_TYPE_INFO[mtype][1],
            implemented=list(IMPLEMENTED_MODEL_TYPES)))
    elif info is None and not errors:
        errors.append(_error('config_model_type_invalid',
                             f'未知 model.type={mtype!r}'))
    elif info is None:
        pass                                          # 前面已有更具体的错误

    if info is not None:
        required_fields = list(info['required'])
        warnings.extend(normalized.get('_warnings', []) if normalized else [])

    # ---- 3. 默认值合并（模板默认值必须在结果里可见）----
    if info is not None and buildable:
        defaults = info['defaults']
        for section, values in defaults.items():
            for name, value in values.items():
                effective.setdefault(section, {})[name] = value
                sources[f'{section}.{name}'] = 'default'
        for section, values in (normalized or {}).items():
            if section.startswith('_') or section == 'model':
                continue
            for name, value in values.items():
                effective.setdefault(section, {})[name] = value
                sources[f'{section}.{name}'] = 'user'
        from topo_modeler.config import _to_ctor_kwargs
        ctor_kwargs = _to_ctor_kwargs(normalized)
        default_count = sum(1 for v in sources.values() if v == 'default')
        if default_count:
            assumptions.append(
                f'{default_count} 个字段未在输入里给出，将使用模板默认值'
                f'（见 effective / field_sources）')

    # ---- 4. 输入里的字符串字段：注入面检查 ----
    #
    #    ⚠️ 输出小节里的是**路径**，必须用 check_path：反斜杠在名称里非法，
    #    在路径里完全合法（`D:\out\wg.cst`）。用名称规则套路径会把所有
    #    Windows 路径判死 —— 这正是「校验过严」的典型翻车方式。
    from cst_solver.expressions import check_name, check_path
    for section, values in (normalized or {}).items():
        if section.startswith('_') or not isinstance(values, dict):
            continue
        is_path = section == 'output'
        for name, value in values.items():
            if not isinstance(value, str):
                continue
            result = check_path(value) if is_path else check_name(value, kind='text')
            if not result.ok:
                errors.append(_error(
                    'config_invalid_character',
                    f'{section}.{name} 含非法字符：{result.errors[0]["message"]}',
                    field=f'{section}.{name}', value=value))

    # ---- 5. 路径检查 ----
    out = (normalized or {}).get('output') or {}
    output_path = out.get('path')
    template_cst = out.get('template_cst')
    if require_output and not output_path:
        errors.append(_error(
            'output_required', '缺少 output.path：本入口要求给出 .cst 输出路径',
            field='output.path'))
    elif not output_path and info is not None:
        assumptions.append(
            '未给出 output.path：建模后需要显式 save(path) 才会落盘')

    if check_paths:
        if template_cst:
            check = _check_template_cst(template_cst, base_dir)
            checks.append(check)
            if check['status'] == 'error':
                errors.append(_error('template_not_found', check['detail'],
                                     path=check.get('path')))
        elif info is not None:
            checks.append({'name': 'template_cst', 'status': 'skipped',
                           'detail': '未给出 output.template_cst，默认 tmp.cst'})
        if output_path:
            check = _check_output_dir(output_path, base_dir)
            checks.append(check)
            if check['status'] == 'error':
                errors.append(_error('output_not_writable', check['detail'],
                                     path=check.get('path')))

    # ---- 6. CST 可用性（信息，不影响 ok）----
    cst_report = _diagnose_cst() if diagnose_cst else None
    if cst_report is not None:
        status = cst_report.get('status')
        checks.append({'name': 'cst_availability', 'status':
                       'ok' if status not in ('unavailable', 'configuration_error')
                       else 'info',
                       'detail': f'CST 诊断 status={status}（不启动 CST，'
                                 f'importable 只说明接口能加载）'})
        if status in ('unavailable', 'configuration_error'):
            warnings.append(
                f'当前环境 CST 不可用（status={status}）：在能跑 CST 的机器上'
                f'再执行建模；预检结论不受影响')

    return {
        'ok': not errors and buildable,
        'buildable': buildable,
        'model_type': mtype,
        'class': (info or {}).get('class'),
        'stage': (info or {}).get('stage', ''),
        'normalized': {k: v for k, v in (normalized or {}).items()
                       if not k.startswith('_')},
        'effective': effective,
        'field_sources': sources,
        'ctor_kwargs': {k: v for k, v in ctor_kwargs.items()
                        if not k.startswith('_')},
        'required_fields': required_fields,
        'errors': errors,
        'warnings': warnings,
        'assumptions': assumptions,
        'checks': checks,
        'cst': cst_report,
    }


def _peek_model_type(spec) -> Optional[str]:
    """校验失败时尽力取出 ``model.type``（只用于给出更准的提示）。"""
    if isinstance(spec, dict):
        model = spec.get('model')
        if isinstance(model, dict):
            return model.get('type')
    return None
