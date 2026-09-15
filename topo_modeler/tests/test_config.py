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


def test_bend_angle_must_be_multiple_of_60():
    with pytest.raises(ConfigError, match='合法取值'):
        validate_config(_cfg('unit_antenna', geometry={'bend_angle': 90}))


def test_planned_model_type_reports_it_is_not_implemented():
    """
    计划中的类型**语法上合法**（配置可以先写出来），但：
    - `validate_config` 会标明「字段未与模板签名核对」；
    - 建实例时必须说清「属于哪个阶段、类名叫什么」，不能静默变成别的模型。
    """
    cfg = {'model': {'type': 'grin_lens_antenna'},
           'geometry': {'lattice_constant': 0.2425}}
    out = validate_config(cfg)
    assert out['model']['type'] == 'grin_lens_antenna'
    assert '_warnings' in out
    assert any('尚未实现' in w for w in out['_warnings'])
    with pytest.raises(ConfigError) as exc:
        template_from_config(cfg)
    msg = str(exc.value)
    assert 'GRINLensAntenna' in msg and '阶段' in msg


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
