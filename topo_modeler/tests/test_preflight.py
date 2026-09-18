# -*- coding: utf-8 -*-
"""
配置 / 建模预检测试（P1：配置与建模预检）
=========================================

守住什么
--------
`docs/next_plan/README.md` 的 P1 第 1 条要求「为首版支持的模板提供字段、类型、
单位、取值范围与默认值的结构化描述；复用 `topo_modeler.config`，但**不得把只通过
语法校验的未实现模型类型宣布为可构建**」，验收判据里还有一条
「**离线预检不创建 DE**」。本文件把这三件事钉住：

1. `list_templates()` / `describe_template()` 给出的结构化字段描述
   （类型 / 单位 / 取值范围 / 默认值 / 是否必填）；
2. `validate_model_spec()` 对无效输入给出**结构化错误码**，对未实现类型
   给出 `model_type_not_implemented`；
3. **离线**：在一个禁止导入 `cst` 的子进程里跑完整预检仍然成功 —— 证明预检
   不需要 CST，也不可能创建设计环境（DE 必须经 `cst.interface` 才能建）。

运行方式::

    pytest topo_modeler/tests/test_preflight.py -v
"""

import json
import os
import subprocess
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from topo_modeler.preflight import (        # noqa: E402
    SUPPORTED_MODEL_TYPES,
    describe_template,
    list_templates,
    validate_model_spec,
)


@pytest.fixture()
def workdir(tmp_path):
    """一个含干净模板占位文件的临时目录。"""
    template = tmp_path / 'tmp.cst'
    template.write_bytes(b'placeholder')
    return tmp_path


def _spec(workdir, **geometry):
    geom = {'lattice_constant': 0.2425, 'height': 0.25, 'topology': 'AB',
            'length': 18, 'width': 14}
    geom.update(geometry)
    return {
        'model': {'type': 'straight_waveguide'},
        'geometry': geom,
        'output': {'path': str(workdir / 'out.cst'),
                   'template_cst': str(workdir / 'tmp.cst')},
    }


# ============================================================
# 1. 结构化字段描述
# ============================================================

def test_list_templates_only_lists_buildable_by_default():
    """默认只列可构建的模板；未实现的类型不许混进来。"""
    templates = list_templates()
    assert [t['model_type'] for t in templates] == list(SUPPORTED_MODEL_TYPES)
    assert all(t['buildable'] for t in templates)
    assert all(t['class'] for t in templates)


def _install_fake_planned(monkeypatch):
    """把合成类型装进配置（**仅供 config 层**的机制用例参考，见下方说明）。

    ⚠️ 只 patch `ALL_MODEL_TYPES` **不够**：`model.type` 是 `enum` 字段，它的
    `choices` 在**模块导入时**就固化了 ⇒ 必须连 `FIELD_INDEX/FIELD_SPECS` 里的
    那条 FieldSpec 一起换（`FieldSpec` 是 frozen dataclass，用 `dataclasses.replace`）。
    ⚠️ 而且 `preflight` 是**按值导入** `config` 常量的，所以这个合成类型
    到不了 `validate_model_spec`/`list_templates` —— 那些用例改用真正的未知类型。
    """
    import dataclasses

    from topo_modeler import config as c

    spec = c.FIELD_INDEX[('model', 'type')]
    new_spec = dataclasses.replace(spec, choices=tuple(spec.choices) + ('fake_device',))
    monkeypatch.setitem(c.FIELD_INDEX, ('model', 'type'), new_spec)
    monkeypatch.setattr(c, 'FIELD_SPECS',
                        tuple(new_spec if s is spec else s for s in c.FIELD_SPECS))
    monkeypatch.setattr(c, 'PLANNED_MODEL_TYPES', ('fake_device',))
    monkeypatch.setattr(c, 'ALL_MODEL_TYPES',
                        c.IMPLEMENTED_MODEL_TYPES + ('fake_device',))
    monkeypatch.setitem(c._MODEL_TYPE_INFO, 'fake_device',
                        ('FakeDevice', '阶段 X（测试用）'))


def test_no_planned_types_remain_after_p5(monkeypatch):
    """P5 三类模板全部落地 ⇒ 计划表为空；`include_planned` 也只列已实现的。

    ⚠️ 这里**不**用合成类型：`preflight` 是按值导入 `config` 常量的，
    临时注册的类型到不了它那里（会得到"未知 model.type"而不是"尚未实现"）。
    「计划中类型」的机制仍由
    `tests/test_config.py::test_planned_model_type_reports_it_is_not_implemented`
    （在 config 层用合成类型）继续覆盖。
    """
    from topo_modeler import config

    assert config.PLANNED_MODEL_TYPES == (), config.PLANNED_MODEL_TYPES
    listed = {t['model_type'] for t in list_templates(include_planned=True)}
    assert listed == set(config.IMPLEMENTED_MODEL_TYPES)
    assert all(t['buildable'] for t in list_templates(include_planned=True))


def test_all_implemented_types_are_buildable_with_a_class():
    """已实现的每个类型在能力发现里都必须 buildable=True 且带类名。"""
    for entry in list_templates(include_planned=True):
        assert entry['buildable'] is True, entry
        assert entry['class'], entry
        assert entry['fields'], entry


def test_grin_lens_antenna_is_listed_as_buildable():
    """已实现的类型必须在能力发现里 buildable=True 且带类名（含透镜字段）。"""
    templates = {t['model_type']: t for t in list_templates(include_planned=True)}
    entry = templates['grin_lens_antenna']
    assert entry['buildable'] is True
    assert entry['class'] == 'GRINLensAntenna'
    fields = {f['name'] for f in entry['fields']}
    assert {'lens_method', 'lens_ratio', 'lens_nx', 'lens_ny'} <= fields


def test_field_description_carries_type_unit_range_and_default():
    """字段必须同时给出类型、单位、取值范围与默认值。"""
    info = describe_template('straight_waveguide')
    fields = {f['name']: f for f in info['fields']}

    constant = fields['lattice_constant']
    assert constant['kind'] == 'float'
    assert constant['unit'] == 'mm'
    assert constant['exclusive_min'] is True
    assert constant['default'] == 0.2425
    assert constant['source_of_default' if 'source_of_default' in constant
           else 'has_default'] is True

    topo = fields['topology']
    assert topo['kind'] == 'enum'
    assert topo['choices'] == ['AB', 'BA']

    length = fields['length']
    assert length['kind'] == 'int'
    assert length['unit'] == '格'
    assert length['min_value'] == 1
    assert length['default'] == 18


def test_defaults_come_from_template_signature():
    """默认值取模板签名，而不是另抄一份常量。"""
    info = describe_template('straight_waveguide')
    assert info['defaults']['geometry']['length'] == 18
    assert info['defaults']['waveguide']['wg_a'] == 0.7312
    assert info['defaults']['output']['template_cst'] == 'tmp.cst'


def test_required_fields_are_those_without_default():
    """必填 = 该模板支持、但没有默认值的字段（直波导只有 output.path）。"""
    info = describe_template('straight_waveguide')
    assert info['required'] == ['output.path']
    fields = {f['name']: f for f in info['fields']}
    assert fields['path']['required'] is True
    assert fields['length']['required'] is False


def test_unsupported_fields_are_not_listed_for_a_template():
    """直波导没有 bend_angle，结构描述里就不该出现它。"""
    names = {f['name'] for f in describe_template('straight_waveguide')['fields']}
    assert 'bend_angle' not in names
    antenna_names = {f['name'] for f in describe_template('unit_antenna')['fields']}
    assert 'bend_angle' in antenna_names


def test_unknown_model_type_raises():
    from topo_modeler.config import ConfigError
    with pytest.raises(ConfigError) as excinfo:
        describe_template('not_a_device')
    assert excinfo.value.code == 'config_model_type_invalid'


# ============================================================
# 2. 预检结论
# ============================================================

def test_valid_spec_is_buildable_and_shows_effective_defaults(workdir):
    report = validate_model_spec(_spec(workdir))
    assert report['ok'] is True
    assert report['buildable'] is True
    assert report['errors'] == []
    # 模板默认值必须在结果里可见
    assert report['effective']['geometry']['lattice_constant'] == 0.2425
    assert report['effective']['waveguide']['wg_b'] == 0.3756
    assert report['field_sources']['geometry.lattice_constant'] == 'user'
    assert report['field_sources']['waveguide.wg_b'] == 'default'
    assert any('默认值' in a for a in report['assumptions'])
    assert report['ctor_kwargs']['length'] == 18
    # 未在输入里给出的字段：算出的**生效值**仍在 effective 里可见
    # （ctor_kwargs 只装用户显式给出的参数，模板自己的默认值由模板兜底）
    assert report['effective']['solver']['fmin'] == 300.0
    assert report['effective']['solver']['fmax'] == 380.0
    assert 'freq_range' not in report['ctor_kwargs']
    assert [c['name'] for c in report['checks']] == [
        'template_cst', 'output_dir', 'cst_availability']


def test_solver_fields_become_freq_range(workdir):
    """给了 solver.fmin/fmax 时，要合成模板真正接受的 freq_range。"""
    spec = _spec(workdir)
    spec['solver'] = {'fmin': 300, 'fmax': 380, 'monitors': ['E']}
    report = validate_model_spec(spec)
    assert report['ok'] is True
    assert report['ctor_kwargs']['freq_range'] == (300.0, 380.0)
    assert report['ctor_kwargs']['monitors'] == ['E']


def test_user_value_overrides_default(workdir):
    report = validate_model_spec(_spec(workdir, length=24))
    assert report['effective']['geometry']['length'] == 24
    assert report['field_sources']['geometry.length'] == 'user'
    assert report['ctor_kwargs']['length'] == 24


@pytest.mark.parametrize('geometry,code', [
    ({'length': 0}, 'config_value_out_of_range'),
    ({'topology': 'ab'}, 'config_enum_invalid'),
    ({'height': 'thick'}, 'config_type_error'),
])
def test_invalid_values_fail_with_structured_code(workdir, geometry, code):
    report = validate_model_spec(_spec(workdir, **geometry))
    assert report['ok'] is False
    assert report['errors'][0]['code'] == code
    assert report['errors'][0]['retryable'] is False
    assert report['errors'][0]['message']


def test_unknown_field_fails_before_any_cst_work(workdir):
    spec = _spec(workdir)
    spec['geometry']['bend_angle'] = 120          # 直波导没有这个字段
    report = validate_model_spec(spec)
    assert report['ok'] is False
    assert report['errors'][0]['code'] in ('config_unknown_field',
                                           'config_field_not_accepted')


def test_unknown_type_is_rejected_without_any_cst_work(workdir):
    """未知类型必须**在动 CST 之前**被明确拒绝（不是静默当别的模型）。

    ⚠️ P5 全部落地后没有"计划中"类型可用，这里改用真正的未知类型；
    「计划中类型 → 尚未实现」那条路径由 `test_config.py` 的合成类型用例覆盖
    （`preflight` 按值导入常量，合成类型到不了它这里）。
    """
    spec = {'model': {'type': 'totally_unknown_device'},
            'output': {'path': str(workdir / 'out.cst'),
                       'template_cst': str(workdir / 'tmp.cst')}}
    report = validate_model_spec(spec)
    assert report['buildable'] is False
    assert report['ok'] is False
    codes = [e['code'] for e in report['errors']]
    assert 'config_model_type_invalid' in codes
    assert report['class'] is None


def test_missing_template_is_reported(workdir):
    spec = _spec(workdir)
    spec['output']['template_cst'] = str(workdir / 'nope.cst')
    report = validate_model_spec(spec)
    assert report['ok'] is False
    assert report['errors'][0]['code'] == 'template_not_found'


def test_output_path_is_optional_unless_required(workdir):
    spec = _spec(workdir)
    spec['output'].pop('path')
    optional = validate_model_spec(spec)
    assert optional['ok'] is True
    assert any('output.path' in a for a in optional['assumptions'])
    strict = validate_model_spec(spec, require_output=True)
    assert strict['ok'] is False
    assert strict['errors'][0]['code'] == 'output_required'


def test_injection_character_in_string_field_is_rejected(workdir):
    """字符串字段里的引号/换行属于注入面，预检要拦下（P1 第 2 条的前置）。"""
    spec = _spec(workdir)
    spec['output']['template_cst'] = 'tmp.cst"\nRemarks: hacked'
    report = validate_model_spec(spec)
    assert report['ok'] is False
    assert report['errors'][0]['code'] == 'config_invalid_character'


def test_output_dir_check_does_not_create_directories(workdir):
    """目录不存在时只提示，**不创建**；这是「预检无副作用」的一部分。"""
    target = workdir / 'not_yet' / 'out.cst'
    spec = _spec(workdir)
    spec['output']['path'] = str(target)
    report = validate_model_spec(spec)
    assert report['ok'] is True
    assert not (workdir / 'not_yet').exists()
    check = [c for c in report['checks'] if c['name'] == 'output_dir'][0]
    assert check.get('created_later') is True


def test_report_is_json_serializable(workdir):
    report = validate_model_spec(_spec(workdir))
    json.dumps(report, ensure_ascii=False)        # 不抛异常即通过


# ============================================================
# 3. 离线保证：禁止导入 cst 的子进程里跑完整预检
# ============================================================

_OFFLINE_SCRIPT = '''
import json, sys
sys.path.insert(0, r"{root}")

class _BlockCst:
    """任何 `import cst*` 都直接失败 —— 这样预检不可能建 DE。"""
    def find_module(self, name, path=None):
        return self if name.split(".")[0] == "cst" else None
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] == "cst":
            raise ImportError("blocked: " + name)
        return None

sys.meta_path.insert(0, _BlockCst())

from topo_modeler.preflight import validate_model_spec, list_templates
report = validate_model_spec({{
    "model": {{"type": "straight_waveguide"}},
    "geometry": {{"length": 18}},
    "output": {{"path": r"{out}", "template_cst": r"{template}"}},
}})
assert "cst" not in sys.modules, "预检过程不许导入 cst"
assert report["ok"], report["errors"]
assert len(list_templates()) >= 2
print(json.dumps({{"ok": True, "buildable": report["buildable"]}}))
'''


def test_preflight_runs_without_cst_import(workdir):
    """在禁止 `import cst` 的解释器里，预检仍应给出正确结论。"""
    script = _OFFLINE_SCRIPT.format(
        root=_TPC_ROOT, out=workdir / 'out.cst', template=workdir / 'tmp.cst')
    proc = subprocess.run([sys.executable, '-c', script],
                          capture_output=True, text=True, cwd=str(workdir))
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload == {'ok': True, 'buildable': True}
