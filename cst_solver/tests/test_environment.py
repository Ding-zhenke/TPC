# -*- coding: utf-8 -*-
"""安装发现、离线导入、路径覆盖与诊断 CLI 的回归验证。"""

import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from cst_solver import environment
from cst_solver.material.materials import MaterialMixin


@pytest.fixture
def config(tmp_path, monkeypatch):
    filename = tmp_path / 'cst.json'
    filename.write_text('{}', encoding='utf-8')
    for key in ('CST_INSTALL_PATH', 'CST_PYTHON_LIB', 'CST_MATERIAL_LIB', 'CST_GUARD_MODE'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('CST_CONFIG_FILE', str(filename))
    return filename


def test_discovery_sorts_numeric_versions_and_ignores_incomplete_installs(tmp_path):
    for name in ('CST Studio Suite 2024', 'CST Studio Suite 2026', 'CST Studio Suite invalid'):
        (tmp_path / name / 'AMD64' / 'python_cst_libraries').mkdir(parents=True)
    (tmp_path / 'CST Studio Suite 2027').mkdir()
    found = environment.discover_cst_installations([tmp_path, tmp_path, tmp_path / 'missing'])
    assert [Path(path).name for path in found] == ['CST Studio Suite 2026', 'CST Studio Suite 2024']


def test_env_install_overrides_config_children(config, tmp_path):
    config.write_text(json.dumps({'CST_INSTALL_PATH': 'old', 'CST_PYTHON_LIB': 'old/lib',
                                  'CST_MATERIAL_LIB': 'old/material'}), encoding='utf-8')
    paths = environment.get_cst_paths(environ={'CST_CONFIG_FILE': str(config),
                                              'CST_INSTALL_PATH': str(tmp_path / 'new')})
    assert paths.install_path == str(tmp_path / 'new')
    assert paths.python_lib == str(tmp_path / 'new' / 'AMD64' / 'python_cst_libraries')
    assert paths.material_lib == str(tmp_path / 'new' / 'Library' / 'Materials')


def test_explicit_install_and_child_override(config, tmp_path):
    paths = environment.get_cst_paths(install_path=tmp_path / 'explicit', environ={
        'CST_CONFIG_FILE': str(config), 'CST_INSTALL_PATH': str(tmp_path / 'env'),
        'CST_PYTHON_LIB': str(tmp_path / 'custom-lib')})
    assert paths.install_path == str(tmp_path / 'explicit')
    assert paths.python_lib == str(tmp_path / 'custom-lib')


def test_config_relative_paths_use_config_directory(config):
    config.write_text('{"CST_INSTALL_PATH": "local-cst"}', encoding='utf-8')
    assert environment.get_cst_paths().install_path == str(config.parent / 'local-cst')


def test_legacy_configuration_still_works(tmp_path, monkeypatch):
    monkeypatch.setattr(environment, '__file__', str(tmp_path / 'environment.py'))
    (tmp_path / 'config.py').write_text("CST_INSTALL_PATH = 'legacy'\nCST_GUARD_MODE = 'strict'", encoding='utf-8')
    paths = environment.get_cst_paths(environ={})
    assert paths.install_path == str(tmp_path / 'legacy')
    assert paths.source.endswith('config.py')


@pytest.mark.parametrize('value', ['[]', '{broken', '{"CST_INSTALL_PATH": 5}'])
def test_invalid_configuration_is_reported(config, value):
    config.write_text(value, encoding='utf-8')
    with pytest.raises(environment.CSTConfigurationError):
        environment.get_cst_paths()
    assert environment.diagnose_environment()['status'] == 'configuration_error'


def test_discovery_fallback_and_no_install(config, tmp_path):
    assert environment.get_cst_paths(search_roots=[]).install_path is None
    (tmp_path / 'CST Studio Suite 2025' / 'AMD64' / 'python_cst_libraries').mkdir(parents=True)
    assert environment.get_cst_paths(search_roots=[tmp_path]).source == 'discovery'


def test_materials_follow_environment(config, monkeypatch, tmp_path):
    monkeypatch.setenv('CST_MATERIAL_LIB', str(tmp_path))
    (tmp_path / 'Silicon.mtd').touch()
    assert MaterialMixin().list_library_materials() == ['Silicon']


def test_import_failure_has_actionable_cause(config, monkeypatch, tmp_path):
    monkeypatch.setenv('CST_PYTHON_LIB', str(tmp_path))
    def fail(name):
        raise ImportError('DLL unavailable')
    monkeypatch.setattr(environment.importlib, 'import_module', fail)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    with pytest.raises(environment.CSTUnavailableError, match='DLL unavailable') as caught:
        environment._load_cst_module('cst.interface')
    assert isinstance(caught.value.__cause__, ImportError)
    report = environment.diagnose_environment(probe=True)
    assert report['status'] == 'unavailable'
    assert set(report['errors']) == {'cst.interface', 'cst.results'}


def test_import_uses_selected_path_once(config, monkeypatch, tmp_path):
    monkeypatch.setenv('CST_PYTHON_LIB', str(tmp_path))
    monkeypatch.setattr(sys, 'path', list(sys.path))
    fake = SimpleNamespace()
    monkeypatch.setattr(environment.importlib, 'import_module', lambda name: fake)
    assert environment._load_cst_module('cst.interface') is fake
    environment._load_cst_module('cst.interface')
    assert sys.path.count(str(tmp_path)) == 1


def test_offline_import_does_not_load_cst_or_change_path(config, tmp_path):
    # 阻止 cst 导入，即使测试机器恰好装有 CST 也能验证离线契约。
    code = '''
import importlib.abc, sys
class BlockCST(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname == 'cst' or fullname.startswith('cst.'):
            raise RuntimeError('CST must not be imported')
sys.meta_path.insert(0, BlockCST())
before = list(sys.path)
from cst_solver import setup, Result, result, get_cst_paths
from cst_solver._guards import GuardState
from cst_solver.simulation.ports import PortMixin
assert issubclass(result, Result)
assert before == sys.path
assert 'cst' not in sys.modules
'''
    run = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert run.stdout == ''


@pytest.mark.parametrize('broken', [False, True])
def test_doctor_is_json_even_when_configuration_is_broken(config, broken):
    if broken:
        config.write_text('not-json', encoding='utf-8')
    report, _run = _doctor()
    assert report['status'] == ('configuration_error' if broken else 'not_probed')


def _doctor():
    """
    跑一次 `python -m cst_solver doctor` 并解析 JSON。

    ⚠️ 必须**显式**用 UTF-8 收发：诊断里含中文（例如接口 ABI 的说明），
    而 Windows 默认 locale 是 GBK —— 依赖 locale 会让这个测试在设置
    `PYTHONIOENCODING=utf-8` 的环境里随机失败。
    """
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    run = subprocess.run([sys.executable, '-m', 'cst_solver', 'doctor'],
                         capture_output=True, text=True, encoding='utf-8',
                         errors='replace', env=env)
    assert run.returncode in (0, 1), run.stderr
    return json.loads(run.stdout), run


# ============================================================
# 解释器 ↔ CST 接口 ABI（P1 支持矩阵的离线判据，不启动 CST）
# ============================================================

def _fake_install(tmp_path, abis):
    """造一个只有 `_cst_interface.*.pyd` 的假安装目录。"""
    amd64 = tmp_path / 'CST Studio Suite 2026' / 'AMD64'
    amd64.mkdir(parents=True)
    for abi in abis:
        (amd64 / f'_cst_interface.{abi}-win_amd64.pyd').write_bytes(b'')
    (tmp_path / 'CST Studio Suite 2026' / 'AMD64' / 'python_cst_libraries').mkdir()
    return tmp_path / 'CST Studio Suite 2026'


def test_interpreter_abi_tag_matches_running_interpreter():
    """标签形如 cp311（CST 扩展名的写法），并与 Python 版本号一致。"""
    tag = environment.interpreter_abi_tag()
    assert tag == f'cp{sys.version_info[0]}{sys.version_info[1]}'
    assert tag.startswith('cp')


def test_interface_abi_match_is_reported_offline(tmp_path):
    """有同 ABI 的 .pyd ⇒ abi_match=True，但**不**声称「已验证组合」。"""
    install = _fake_install(tmp_path, ['cp38', 'cp39', environment.interpreter_abi_tag()])
    info = environment.describe_interface_abi(install)
    assert info['abi_match'] is True
    assert info['matching_abi'] == environment.interpreter_abi_tag()
    assert info['interfaces'] == sorted(['cp38', 'cp39',
                                         environment.interpreter_abi_tag()])
    assert '已验证组合' in info['note'] and '依赖 DLL' in info['note']


def test_interface_abi_mismatch_is_actionable(tmp_path):
    """只有别的 ABI ⇒ 明确说明当前解释器加载不了，并给出原因。"""
    install = _fake_install(tmp_path, ['cp38'])
    info = environment.describe_interface_abi(install)
    assert info['abi_match'] is False
    assert info['matching_abi'] is None
    assert '无法' in info['note'] and environment.interpreter_abi_tag() in info['note']


def test_interface_abi_without_pyd_or_install(tmp_path, monkeypatch):
    """既没有 .pyd 也没有安装目录时也要给出可读结论，而不是抛异常。"""
    empty = tmp_path / 'CST Studio Suite 2026' / 'AMD64'
    empty.mkdir(parents=True)
    info = environment.describe_interface_abi(tmp_path / 'CST Studio Suite 2026')
    assert info['abi_match'] is False
    assert info['interfaces'] == []
    assert '没找到' in info['note']

    missing = environment.describe_interface_abi(tmp_path / 'not-here')
    assert missing['abi_match'] is False
    assert '无法读取' in missing['note']

    # 没配安装目录时必须给出结论而不是异常（这里屏蔽真实发现，保证可复现）
    monkeypatch.setattr(environment, 'get_cst_paths',
                        lambda **kwargs: SimpleNamespace(install_path=None))
    unconfigured = environment.describe_interface_abi(None)
    assert unconfigured['abi_match'] is False
    assert unconfigured['install_path'] is None
    assert '无法比对' in unconfigured['note']


def test_doctor_reports_interface_abi(config, tmp_path):
    """`doctor` 的 JSON 里必须带上接口 ABI 段（离线信息，不影响 exit code）。"""
    (tmp_path / 'CST Studio Suite 2026' / 'AMD64' / 'python_cst_libraries').mkdir(parents=True)
    (tmp_path / 'CST Studio Suite 2026' / 'AMD64'
     / '_cst_interface.cp311-win_amd64.pyd').write_bytes(b'')
    config.write_text(json.dumps({'CST_INSTALL_PATH': str(tmp_path / 'CST Studio Suite 2026')}),
                      encoding='utf-8')
    report, run = _doctor()
    assert run.returncode == 0, run.stderr
    abi = report['interface_abi']
    assert abi['interfaces'] == ['cp311']
    assert abi['interpreter_abi'] == environment.interpreter_abi_tag()
    assert abi['abi_match'] == (environment.interpreter_abi_tag() == 'cp311')
