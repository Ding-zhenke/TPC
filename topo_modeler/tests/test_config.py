# -*- coding: utf-8 -*-
"""
YAML 配置驱动测试（阶段 7 模块 5.2）
===================================
对应 `topo_modeler/config.py`，以及计划 §14.3 那条「YAML 取值域只列了 3 个取值加省略号」
的缺口 —— 本文件守的就是「取值域必须**可执行**」。

⚠️ 全部用例都**不碰 CST**（用 `validate_only=True` / 只读签名）。

运行方式::

    pytest topo_modeler/tests/test_config.py -v
"""

import inspect
import os
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from topo_modeler.config import (          # noqa: E402
    ALL_MODEL_TYPES,
    FIELD_SPECS,
    IMPLEMENTED_MODEL_TYPES,
    MONITOR_CHOICES,
    PLANNED_MODEL_TYPES,
    SECTIONS,
    ConfigError,
    accepted_fields,
    available_model_types,
    dump_config,
    example_config,
    field_help,
    load_config,
    template_from_config,
    validate_config,
)


def _cfg(model_type='straight_waveguide', **sections):
    cfg = example_config(model_type)
    for section, values in sections.items():
        cfg.setdefault(section, {}).update(values)
    return cfg


# ============================================================
# 1. 取值域完整性
# ============================================================

def test_model_type_enum_is_complete_and_covers_both_sets():
    """model.type 必须是完整枚举，且已实现/计划中两类都列全。"""
    assert 'straight_waveguide' in ALL_MODEL_TYPES
    assert 'unit_antenna' in ALL_MODEL_TYPES
    assert set(PLANNED_MODEL_TYPES).issubset(ALL_MODEL_TYPES)
    assert not (set(IMPLEMENTED_MODEL_TYPES) & set(PLANNED_MODEL_TYPES))
    assert available_model_types(implemented_only=True) == IMPLEMENTED_MODEL_TYPES


def test_every_field_spec_has_doc_and_section():
    """每个字段都要有说明、都在合法小节里 —— 免得加了字段却没人知道怎么填。"""
    for spec in FIELD_SPECS:
        assert spec.section in SECTIONS, spec
        assert spec.doc, f'{spec.dotted} 缺少说明'
        if spec.kind == 'enum':
            assert spec.choices, f'{spec.dotted} 是 enum 却没有 choices'


def test_field_help_lists_each_section():
    lines = field_help('straight_waveguide')
    text = '\n'.join(lines)
    for section in ('geometry', 'feed', 'waveguide', 'solver', 'output'):
        assert f'[{section}]' in text


# ============================================================
# 2. 正常路径
# ============================================================

@pytest.mark.parametrize('model_type', IMPLEMENTED_MODEL_TYPES)
def test_example_config_is_valid(model_type):
    """每种已实现类型的示例配置都要能通过自己的校验。"""
    cfg = example_config(model_type)
    out = validate_config(cfg)
    assert out['model']['type'] == model_type
    assert out['geometry']['topology'] in ('AB', 'BA')


def test_validate_normalizes_types():
    """数值字段会被规范化（int 保持 int、float 转 float）。"""
    cfg = _cfg(geometry={'length': 18, 'lattice_constant': 0.2425})
    out = validate_config(cfg)
    assert out['geometry']['length'] == 18
    assert isinstance(out['geometry']['length'], int)
    assert isinstance(out['geometry']['lattice_constant'], float)


def test_numeric_string_is_rejected_with_type_hint():
    with pytest.raises(ConfigError, match='应为整数'):
        validate_config(_cfg(geometry={'length': '18'}))


def test_yaml_round_trip(tmp_path):
    """dump → load → validate 应完全一致。"""
    cfg = example_config('unit_antenna')
    cfg['output']['path'] = str(tmp_path / 'ant.cst')
    p = dump_config(cfg, str(tmp_path / 'cfg.yaml'), header='自动生成')
    reloaded = load_config(p)
    assert validate_config(reloaded) == validate_config(cfg)


def test_load_config_accepts_dict():
    cfg = example_config('straight_waveguide')
    assert load_config(cfg) == cfg


# ============================================================
# 3. 反例：每一条都必须报错，且报错要说清怎么改
# ============================================================

def test_unknown_section_rejected():
    cfg = example_config('straight_waveguide')
    cfg['geomtry'] = {'length': 18}          # 拼错
    with pytest.raises(ConfigError, match='未知的顶层小节'):
        validate_config(cfg)


def test_unknown_field_rejected_and_lists_legal_ones():
    with pytest.raises(ConfigError) as exc:
        validate_config(_cfg(geometry={'lengh': 18}))     # 拼错
    msg = str(exc.value)
    assert 'lengh' in msg and 'length' in msg


def test_out_of_range_rejected():
    with pytest.raises(ConfigError, match='必须'):
        validate_config(_cfg(geometry={'large_hole_ratio': 1.5}))
    with pytest.raises(ConfigError, match='必须'):
        validate_config(_cfg(geometry={'length': 0}))


def test_enum_outside_choices_rejected():
    with pytest.raises(ConfigError, match='合法取值'):
        validate_config(_cfg(geometry={'topology': 'ab'}))


def test_fmax_must_exceed_fmin():
    with pytest.raises(ConfigError, match='必须大于'):
        validate_config(_cfg(solver={'fmin': 380, 'fmax': 300}))


def test_monitors_must_be_a_list_not_a_string():
    """YAML 里最容易写错的一处：monitors: E 而不是 [E]。"""
    with pytest.raises(ConfigError, match=r'\[E\]'):
        validate_config(_cfg(solver={'monitors': 'E'}))


def test_monitors_value_domain():
    assert validate_config(_cfg(solver={'monitors': ['E', 'Farfield']}))
    with pytest.raises(ConfigError, match='Farfield'):
        validate_config(_cfg(solver={'monitors': ['Efield']}))
    with pytest.raises(ConfigError, match='不能为空'):
        validate_config(_cfg(solver={'monitors': []}))
    assert MONITOR_CHOICES == ('E', 'H', 'Farfield')


def test_cross_type_field_rejected():
    """给直波导写 bend_angle 必须报错，并指出那是谁的字段。"""
    with pytest.raises(ConfigError) as exc:
        validate_config(_cfg('straight_waveguide', geometry={'bend_angle': 120}))
    msg = str(exc.value)
    assert 'bend_angle' in msg and 'unit_antenna' in msg
    # 反过来，天线接受 bend_angle
    assert validate_config(_cfg('unit_antenna', geometry={'bend_angle': 240}))


def test_bend_angle_must_be_multiple_of_120():
    """
    `bend_angle` 是张角：单臂偏角 = bend_angle/2 必须是 60° 的整数倍，
    所以合法值只有 120 的整数倍 —— 60/90/180/300 都要在配置层就被拒。
    """
    for bad in (90, 60, 180, 300):
        with pytest.raises(ConfigError, match='合法取值'):
            validate_config(_cfg('unit_antenna', geometry={'bend_angle': bad}))
    for good in (0, 120, 240, 360):
        assert validate_config(_cfg('unit_antenna',
                                    geometry={'bend_angle': good}))


def test_planned_model_type_reports_it_is_not_implemented(monkeypatch):
    """
    计划中的类型**语法上合法**（配置可以先写出来），但：
    - `validate_config` 会标明「字段未与模板签名核对」；
    - 建实例时必须说清「属于哪个阶段、类名叫什么」，不能静默变成别的模型。

    ⚠️ 2026-09-17：P5 三类模板全部落地后 `PLANNED_MODEL_TYPES` 为空，
    这里用**合成**的计划类型来继续覆盖机制（将来加新器件时直接可用）。
    """
    import dataclasses

    import topo_modeler.config as cfg_mod

    # ⚠️ `model.type` 是 enum 字段，choices 在**导入期**固化 ⇒ 连 FieldSpec 一起换
    spec = cfg_mod.FIELD_INDEX[('model', 'type')]
    new_spec = dataclasses.replace(spec,
                                   choices=tuple(spec.choices) + ('fake_device',))
    monkeypatch.setitem(cfg_mod.FIELD_INDEX, ('model', 'type'), new_spec)
    monkeypatch.setattr(cfg_mod, 'FIELD_SPECS',
                        tuple(new_spec if s is spec else s
                              for s in cfg_mod.FIELD_SPECS))
    monkeypatch.setattr(cfg_mod, 'PLANNED_MODEL_TYPES', ('fake_device',))
    monkeypatch.setattr(cfg_mod, 'ALL_MODEL_TYPES',
                        cfg_mod.IMPLEMENTED_MODEL_TYPES + ('fake_device',))
    monkeypatch.setitem(cfg_mod._MODEL_TYPE_INFO, 'fake_device',
                        ('FakeDevice', '阶段 X（测试用）'))

    cfg = {'model': {'type': 'fake_device'},
           'geometry': {'lattice_constant': 0.2425}}
    out = validate_config(cfg)
    assert out['model']['type'] == 'fake_device'
    assert '_warnings' in out
    assert any('尚未实现' in w for w in out['_warnings'])
    with pytest.raises(ConfigError) as exc:
        template_from_config(cfg)
    msg = str(exc.value)
    assert 'FakeDevice' in msg and '阶段' in msg


def test_all_p5_templates_are_implemented_and_configurable():
    """
    反向确认：P5 的三类模板都已从「计划中」挪进「已实现」，且字段可配。
    """
    from topo_modeler.config import (IMPLEMENTED_MODEL_TYPES, PLANNED_MODEL_TYPES,
                                     accepted_fields)

    assert PLANNED_MODEL_TYPES == (), PLANNED_MODEL_TYPES
    for model_type in ('grin_lens_antenna', 'multiport_antenna', 'mzi_switch',
                       'power_divider'):
        assert model_type in IMPLEMENTED_MODEL_TYPES, model_type
        assert accepted_fields(model_type), model_type          # 有可配字段
    # 透镜字段只在**含透镜的模板**身上（避免"写了但没用"）：
    # 2026-09-18 起四个 P5 模板都能建透镜（`mzi_switch` 补上了 `MZI-GRIB` 的环透镜），
    # 所以判据改成"这四个都接受 `lens_dxf`"，并另外钉住**不含透镜**的模板拒绝它。
    for model_type in ('grin_lens_antenna', 'multiport_antenna', 'mzi_switch',
                       'power_divider'):
        assert 'lens_dxf' in set(accepted_fields(model_type)), model_type
    for model_type in ('straight_waveguide', 'unit_antenna'):
        assert 'lens_dxf' not in set(accepted_fields(model_type)), model_type


def test_grin_lens_antenna_is_now_implemented_and_configurable():
    """
    反向确认：`grin_lens_antenna` 已经从「计划中」挪进「已实现」，
    且透镜字段真的可配置（否则 YAML 写了也会被拒）。
    """
    from topo_modeler.config import IMPLEMENTED_MODEL_TYPES, accepted_fields

    assert 'grin_lens_antenna' in IMPLEMENTED_MODEL_TYPES
    fields = set(accepted_fields('grin_lens_antenna'))
    assert {'lens_method', 'lens_ratio', 'lens_nx', 'lens_ny'} <= fields
    # 单端口/单天线模板不该接受透镜字段（避免"写了但没用"）
    assert 'lens_ratio' not in set(accepted_fields('unit_antenna'))
    kwargs = template_from_config(
        {'model': {'type': 'grin_lens_antenna'},
         'geometry': {'lens_method': 'generate', 'lens_ratio': 2.0}},
        validate_only=True)
    assert kwargs['lens_method'] == 'generate'
    assert kwargs['lens_ratio'] == 2.0


def test_insitu_lens_is_configurable():
    """`lens_method='insitu'`（**不落 DXF**）必须能从 YAML 配置用起来。

    否则新加的第三条入口在配置文件路线上等于不存在 —— 这类"库里有、配置里没有"
    的缺口会让 YAML 用户以为库做不到。
    """
    from topo_modeler.config import accepted_fields

    fields = set(accepted_fields('grin_lens_antenna'))
    assert {'lens_layers', 'lens_d0_layers'} <= fields
    kwargs = template_from_config(
        {'model': {'type': 'grin_lens_antenna'},
         'geometry': {'lens_method': 'insitu', 'lens_layers': 10,
                      'lens_d0_layers': 3}},
        validate_only=True)
    assert kwargs['lens_method'] == 'insitu'
    assert kwargs['lens_layers'] == 10
    assert kwargs['lens_d0_layers'] == 3
    # 默认值 = 参考 notebook 的 N=(y[1]+2)*2 / d0=8 层（直接查字段规格，
    # 因为 `validate_only=True` 只回填**显式给了**的字段）
    from topo_modeler.config import FIELD_INDEX

    assert FIELD_INDEX[('geometry', 'lens_layers')].default == 30
    assert FIELD_INDEX[('geometry', 'lens_d0_layers')].default == 8
    assert 'insitu' in FIELD_INDEX[('geometry', 'lens_method')].choices
    # 非法的 lens_method 仍然被拒（不能因为多了一个取值就放松校验）
    with pytest.raises(ConfigError):
        validate_config({'model': {'type': 'grin_lens_antenna'},
                         'geometry': {'lens_method': 'in-situ'}})


def test_unknown_model_type_rejected():
    with pytest.raises(ConfigError, match='非法'):
        validate_config({'model': {'type': 'straightwaveguide'}})


def test_missing_model_type_rejected():
    with pytest.raises(ConfigError, match='缺少 model.type'):
        validate_config({'geometry': {'length': 18}})


# ============================================================
# 4. 与模板签名的映射
# ============================================================

def test_accepted_fields_differ_between_types():
    straight = set(accepted_fields('straight_waveguide'))
    antenna = set(accepted_fields('unit_antenna'))
    assert {'length', 'width'} <= straight
    assert 'bend_angle' not in straight
    assert {'bend_angle', 'straight_length', 'arm_length'} <= antenna
    assert 'length' not in antenna


def test_validate_only_returns_ctor_kwargs_with_renames():
    """三处改名必须正确：feed.type→feed_type、output.path→output_path、fmin/fmax→freq_range。"""
    cfg = _cfg('unit_antenna',
               feed={'type': 'ba_tapered'},
               solver={'fmin': 300, 'fmax': 400},
               output={'path': r'D:\out\ant.cst'})
    kwargs = template_from_config(cfg, validate_only=True)
    assert kwargs['feed_type'] == 'ba_tapered'
    assert kwargs['output_path'] == r'D:\out\ant.cst'
    assert kwargs['freq_range'] == (300.0, 400.0)
    assert kwargs['bend_angle'] == 120
    # validate_only 只回参数字典，不回实例；这两个下划线键是给调用方做提示用的
    assert kwargs['_model_type'] == 'unit_antenna'
    assert kwargs['_class'] == 'UnitAntenna'


def test_partial_solver_section_fills_the_other_end():
    """只给 fmin 或只给 fmax 时，另一端用默认值补上（而不是半个 freq_range）。"""
    only_min = template_from_config(_cfg(solver={'fmin': 320}), validate_only=True)
    assert only_min['freq_range'][0] == 320.0
    assert only_min['freq_range'][1] > 320.0
    only_max = template_from_config(_cfg(solver={'fmax': 360}), validate_only=True)
    assert only_max['freq_range'][1] == 360.0
    assert only_max['freq_range'][0] < 360.0


def test_ctor_kwargs_have_no_yaml_only_keys():
    cfg = _cfg('straight_waveguide', output={'path': 'x.cst'})
    kwargs = template_from_config(cfg, validate_only=True)
    for bad in ('type', 'path', 'fmin', 'fmax', '_model_type', '_class'):
        assert bad not in {k for k in kwargs if not k.startswith('_')}, bad


def test_overrides_win_over_yaml():
    kwargs = template_from_config(_cfg(geometry={'length': 18}),
                                  validate_only=True, length=99)
    assert kwargs['length'] == 99


def test_strict_false_drops_unknown_fields():
    """strict=False 时未知字段被丢弃并记进 `_dropped`（不会静默当成合法字段）。"""
    cfg = {'model': {'type': 'straight_waveguide'},
           'geometry': {'lengh': 18, 'width': 14}}
    out = validate_config(cfg, strict=False)
    assert '_warnings' in out and '_dropped' in out
    assert 'geometry.lengh' in out['_dropped']
    assert out['geometry']['width'] == 14
    # 关键：拼错的 `lengh` 不会被当成 `length`
    assert 'length' not in out['geometry']


def test_model_type_argument_overrides_yaml():
    cfg = example_config('unit_antenna')
    out = validate_config({'geometry': cfg['geometry']},
                          model_type='unit_antenna')
    assert out['model']['type'] == 'unit_antenna'


# ============================================================
# 配置 ↔ 模板构造参数的**一致性护栏**
# ============================================================

#: 模板构造签名里**故意不做成 YAML 字段**的参数 → 原因。
#: 判据：不是"实现漏了"，而是"配置语言表达不了或不该表达"。
NON_CONFIGURABLE = {
    # 值是**结构**（dict / 列表），当前配置只有标量字段类型；要做就得先扩字段系统
    'feed_params': '馈源参数覆盖是个 dict（键随馈源类型变），配置语言表达不了',
    'lens_kwargs': '透镜几何覆盖是个 dict，同上',
    'feed1': '多端口模板的馈源 1 参数是个 dict，同上',
    'feed2': '多端口模板的馈源 2 参数是个 dict，同上',
    'port_numbers': '多端口模板的端口编号是个 int 列表，同上',
    'monitor_freqs': '监视器频点是个 float 列表，同上',
    'switch_xy': '功分器开关的坐标是 [(x, y), …]（元素还可以是 CST 表达式），'
                 '配置语言表达不了坐标对列表；要用就写 Python（`switch_mode='
                 "'explicit'` + `switch_xy=`），或在 YAML 里用 `switch_mode='arm_mid'`",
}
#: 由**别的字段合成**的构造参数（不是缺口）：ctor 参数名 → 配置字段名
SYNTHESIZED = {
    'freq_range': 'solver.fmin + solver.fmax',
    'lens_phase': 'geometry.dphi1 + geometry.dphi2',
    'feed_type': 'feed.type',
    'output_path': 'output.path',
}

_TEMPLATES = ('straight_waveguide', 'unit_antenna', 'grin_lens_antenna',
              'multiport_antenna', 'mzi_switch', 'power_divider')


def _ctor_targets(model_type):
    """配置**能写进构造参数**的那些名字（含合成项）。"""
    from topo_modeler.config import FIELD_SPECS

    params = set(inspect.signature(_template_class(model_type).__init__).parameters)
    params.discard('self')
    targets = set()
    for spec in FIELD_SPECS:
        if spec.section == 'model':
            continue
        if spec.ctor and spec.ctor in params:
            targets.add(spec.ctor)
        elif spec.name in ('fmin', 'fmax') and 'freq_range' in params:
            targets.add('freq_range')
        elif spec.name in ('dphi1', 'dphi2') and 'lens_phase' in params:
            targets.add('lens_phase')
    return params, targets


def _template_class(model_type):
    from topo_modeler.config import _template_class as _cls
    return _cls(model_type)


@pytest.mark.parametrize('model_type', _TEMPLATES)
def test_every_ctor_param_is_configurable_or_explicitly_excluded(model_type):
    """**机器护栏**：模板构造参数要么能从 YAML 配出来，要么在 `NON_CONFIGURABLE`
    里写明原因 —— 不允许出现"库里有、配置里没有、还没人知道"的参数。

    （2026-09-17 就是靠这条发现 `power_divider` 连 `split_ratio` 都配不了 ⇒
    YAML 根本表达不出"1分4"。）
    """
    params, targets = _ctor_targets(model_type)
    gaps = sorted(params - targets - set(NON_CONFIGURABLE) - set(SYNTHESIZED))
    assert not gaps, (
        f'{model_type}: 这些构造参数既不在 YAML 字段里，也没在 NON_CONFIGURABLE '
        f'里登记原因：{gaps}')


@pytest.mark.parametrize('model_type', _TEMPLATES)
def test_non_configurable_entries_still_exist(model_type):
    """`NON_CONFIGURABLE` 不能变成"过期借口"：登记的参数必须真的还在签名里。"""
    params, _targets = _ctor_targets(model_type)
    stale = sorted(set(NON_CONFIGURABLE) & set(SYNTHESIZED) - params)
    assert not stale, f'NON_CONFIGURABLE/SYNTHESIZED 里有已不存在的参数：{stale}'


def test_enum_choices_are_accepted_by_the_template():
    """配置里给的 `enum` 取值，模板必须真的接受（否则是"写得出来但一用就报错"）。"""
    from topo_modeler.config import FIELD_INDEX

    from topo_templates import GRINLensAntenna, MultiPortAntenna, PowerDivider

    lens_choices = FIELD_INDEX[('geometry', 'lens_method')].choices
    assert 'insitu' in lens_choices and 'generate' in lens_choices
    for choices, allowed in ((lens_choices, GRINLensAntenna.LENS_METHODS),
                             (lens_choices, PowerDivider.LENS_METHODS),
                             (lens_choices, MultiPortAntenna.LENS_METHODS)):
        extra = set(choices) - set(allowed)
        assert not extra, f'配置允许 {extra}，但模板只接受 {allowed}'
    from topo_modeler.config import IMPLEMENTED_MODEL_TYPES

    assert set(IMPLEMENTED_MODEL_TYPES) == set(_TEMPLATES)


def test_split_ratio_yaml_round_trip():
    """YAML 能表达 1分4（`split_ratio`）—— 这就是 `PowerDivider` 的主旋钮。"""
    kwargs = template_from_config(
        {'model': {'type': 'power_divider'},
         'geometry': {'split_ratio': 4, 'trunk_length': 8, 'sub_length': 6,
                      'dphi1': 30, 'dphi2': 10}},
        validate_only=True)
    assert kwargs['split_ratio'] == 4
    assert kwargs['trunk_length'] == 8
    assert kwargs['sub_length'] == 6
    assert kwargs['lens_phase'] == (30.0, 10.0)
    with pytest.raises(ConfigError):
        validate_config({'model': {'type': 'power_divider'},
                         'geometry': {'split_ratio': 5}})
