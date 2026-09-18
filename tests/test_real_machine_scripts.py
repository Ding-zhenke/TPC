# -*- coding: utf-8 -*-
r"""
真机脚本的**离线**自检（不启动 CST）
====================================

这些脚本本身要连 CST 才能真跑，但它们**内部的一致性**可以离线钉住 ——
否则文档里那句「一条命令同时收掉两个待办」很容易在后续改动里悄悄失效：

1. `verify_antenna_mapping.py` 的参考臂端常量必须与
   `topo_templates/tests/test_antenna_mapping.py` 断言的值**一致**
   （6.0625, ±2.94015624584816，来自参考工程 `Parameters.json`）；
2. 默认开启「求解控制 API 探针」，且能用 `--no-solver-api-probe` 关掉；
3. `probe_solver_control_api.probe_live_app(app)` 对任意「有 `cst_file.model3d`」
   的对象都能工作（用替身验证它真的逐个 `hasattr` 并取 docstring）。

运行方式::

    pytest tests/test_real_machine_scripts.py -v
"""

import importlib.util
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
_SCRIPTS = os.path.join(ROOT, 'scripts')
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import probe_solver_control_api as probe       # noqa: E402


def _load(name):
    path = os.path.join(_SCRIPTS, f'{name}.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def antenna():
    return _load('verify_antenna_mapping')


def test_reference_arm_endpoint_matches_the_documented_values(antenna):
    """臂端参考值必须就是参考工程 `Parameters.json` 里的 px3/py3。"""
    assert antenna.REF_ARM_END['AB'] == (6.0625, 2.94015624584816)
    assert antenna.REF_ARM_END['BA'] == (6.0625, -2.94015624584816)


def test_expected_array_ranges_match_the_reference_formulas(antenna):
    """阵列范围期望值 = 参考 notebook 的公式（AB 25 / BA 26，yup=ydn=14）。"""
    assert antenna.expected('AB') == {'xup': 25, 'yup': 14, 'ydn': 14}
    assert antenna.expected('BA') == {'xup': 26, 'yup': 14, 'ydn': 14}


def test_script_defaults_to_probing_the_solver_api(antenna):
    """默认在同一会话里顺带探求解控制 API；可通过 CLI 关掉。"""
    assert antenna._probe_solver_api is True
    source = open(os.path.join(_SCRIPTS, 'verify_antenna_mapping.py'),
                  encoding='utf-8').read()
    assert '--no-solver-api-probe' in source
    assert 'probe_live_app' in source


def test_solver_probe_candidates_cover_stop_and_run(probe_module=None):
    """候选名字要覆盖「停止」「运行」「查询」三类，否则探了个空。"""
    names = [name.lower() for name in probe.CANDIDATES]
    assert any('abort' in name or 'stop' in name for name in names)
    assert any('run' in name or 'start' in name for name in names)
    assert any('solver' in name for name in names)


class _FakeModel3D:
    """替身：只有 `run_solver` 存在，`abort_solver` 不存在。"""

    def run_solver(self):
        """跑求解。"""


class _FakeCstFile:
    def __init__(self):
        self.model3d = _FakeModel3D()


class _FakeApp:
    def __init__(self):
        self.cst_file = _FakeCstFile()


def test_probe_live_app_works_on_any_live_session():
    """`probe_live_app` 只依赖 `app.cst_file.model3d`，且逐个 hasattr 并取 docstring。"""
    results = probe.probe_live_app(_FakeApp())
    by_name = {item['name']: item for item in results}
    assert set(by_name) == set(probe.CANDIDATES)
    assert by_name['run_solver']['present'] is True
    assert '跑求解' in by_name['run_solver']['doc']
    assert by_name['abort_solver']['present'] is False
    assert by_name['abort_solver']['doc'] == ''
