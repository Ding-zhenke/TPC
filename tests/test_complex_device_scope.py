# -*- coding: utf-8 -*-
r"""
复杂器件的**宣称边界**（P5：功分器分类证据）
==========================================

计划原文（`docs/next_plan/README.md` P5）：

> 功分器分类以已查明的分路数、透镜、相位维度为准；`y/t/cascade/mmi` 在原参数表中
> 尚无对应证据，补齐前不能宣称支持。

依据（[复杂器件参考规格](../docs/guides/complex_device_specs.md) §4.3）：
所有分路 notebook 的参数表里**没有** `divider_type` 字段，只有 `lx1`/`nsm`/`Rbig`
这类通用参数；实测能区分的只有**分几路**（1分2 / 1分3 / 1分4 / 1分6），
以及「是否带透镜」「是否带相位差」。

本文件把这条结论**变成机器护栏**：不是靠"记得别写"，而是让人一旦真想支持
`y/t/cascade/mmi` 或把 `power_divider` 从"计划中"挪进"已实现"，就必须同时
更新这些地方（否则测试红）。

运行方式::

    pytest tests/test_complex_device_scope.py -v
"""

import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from topo_modeler import config                              # noqa: E402

SPEC_DOC = os.path.join(ROOT, 'docs', 'guides', 'complex_device_specs.md')

#: 没有数据依据、因而**不许**出现在任何输入字段取值域里的分路类型
UNSUPPORTED_DIVIDER_TYPES = ('y', 't', 'cascade', 'mmi')


def test_every_model_type_is_implemented_or_declared_planned():
    """
    **宣称与实现必须一致**：`IMPLEMENTED_MODEL_TYPES` 里的每个类型都要有真实模板类，
    `PLANNED_MODEL_TYPES` 里的**不许**有类。

    2026-09-17：P5 三类模板全部落地后 `PLANNED_MODEL_TYPES` **为空**（机制保留，
    行为由 `topo_modeler/tests/test_config.py` 的合成类型用例继续覆盖）。
    """
    import topo_templates

    implemented = set(config.IMPLEMENTED_MODEL_TYPES)
    planned = set(config.PLANNED_MODEL_TYPES)
    assert not (implemented & planned), implemented & planned
    assert config.ALL_MODEL_TYPES == (config.IMPLEMENTED_MODEL_TYPES
                                      + config.PLANNED_MODEL_TYPES)
    assert planned == set(), f'计划表应为空（P5 已全部落地），实际 {planned}'

    exported = set(getattr(topo_templates, '__all__', ()))
    for model_type in config.IMPLEMENTED_MODEL_TYPES:
        class_name = config._MODEL_TYPE_INFO[model_type][0]
        assert class_name in exported, (
            f'{model_type} 声明已实现（类名 {class_name}），但它不在 '
            f'topo_templates.__all__ 里 —— 宣称与实现不一致')


def test_unsupported_divider_type_is_still_guarded():
    """老护栏的意图保留：`y/t/cascade/mmi` 与这类"没有依据就宣称支持"仍被挡住。"""
    for model_type in config.IMPLEMENTED_MODEL_TYPES:
        assert 'divider_type' not in set(config.accepted_fields(model_type))


def test_no_unsupported_divider_type_field_anywhere():
    """
    配置层**不接受** `divider_type`（更没有 `'y'/'t'/'cascade'/'mmi'` 取值域）。

    这是「没有数据依据就不宣称」的硬边界：一旦有人在 `accepted_fields()` 里
    加了 `divider_type`，这条会红，逼着先补证据（参考工程参数表 / notebook）。
    """
    for model_type in config.IMPLEMENTED_MODEL_TYPES:
        fields = set(config.accepted_fields(model_type))
        assert 'divider_type' not in fields, (
            f'{model_type} 接受了 divider_type —— 参考参数表里没有这个字段，'
            f'先补证据再开口子（见 docs/guides/complex_device_specs.md §4.3）')

    # 计划中的类型连字段表都没有：问它必须**明确报「还没实现」**，
    # 而不是给出一张半成品字段表（那才是真正的"悄悄宣称支持"）
    for model_type in config.PLANNED_MODEL_TYPES:
        with pytest.raises(config.ConfigError) as excinfo:
            config.accepted_fields(model_type)
        assert getattr(excinfo.value, 'code', None) == \
            'config_model_type_not_implemented', excinfo.value

    source = open(os.path.join(ROOT, 'topo_modeler', 'config.py'),
                  encoding='utf-8').read()
    head = source.split('PLANNED_MODEL_TYPES')[0]
    for bad in UNSUPPORTED_DIVIDER_TYPES:
        assert f"'{bad}'" not in head, (
            f'config.py 里出现了未获证据的分路取值 {bad!r}')


def test_planned_types_are_reported_as_not_buildable():
    """能力报告必须把它们标成「计划中/不可构建」，而不是默默能建。"""
    from topo_modeler.preflight import list_templates

    templates = list_templates(include_planned=True)
    planned = {t['model_type'] for t in templates
               if t['model_type'] in config.PLANNED_MODEL_TYPES}
    assert planned == set(config.PLANNED_MODEL_TYPES), planned
    for entry in templates:
        if entry['model_type'] in config.PLANNED_MODEL_TYPES:
            assert entry['buildable'] is False, entry


def test_spec_doc_keeps_the_no_evidence_conclusion():
    """
    参考规格里那条「`y/t/cascade/mmi` 没有数据依据」的结论不能被悄悄删掉 ——
    否则下一个人只能从测试文件里才看得到这个边界。
    """
    text = open(SPEC_DOC, encoding='utf-8').read()
    assert 'divider_type' in text
    assert '没有数据依据' in text or '找不到对应字段' in text
    for bad in UNSUPPORTED_DIVIDER_TYPES:
        assert bad in text, f'规格文档里应逐个点名没有依据的取值：{bad}'
    # 真实可用的维度必须写出来（分路数 / 透镜 / 相位）
    assert '分几路' in text and '透镜' in text and '相位' in text


if __name__ == '__main__':                                  # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-v']))
