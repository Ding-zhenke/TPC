# -*- coding: utf-8 -*-
r"""
旧 notebook 导入兼容的回归测试（P1 验收判据「旧 notebook 导入兼容」）
====================================================================

守住两件事：

1. **旧名真的能导入**：旧 notebook 写的是 `import tri_lib` / `import hexlib`
   （实测 58 + 41 个 notebook）。此前 `archive/compat/` 里只有 `*_shim.py`，
   文件名对不上，`import tri_lib` 依然 `ModuleNotFoundError` —— 现在由
   `archive/compat/tri_lib.py`、`hexlib.py`（**以旧名命名**）转发，
   本文件把它钉住（含 `FutureWarning`、同一对象、旧名里的具体符号）。
2. **审计本身可靠**：`scripts/check_notebook_imports.py` 的解析/分类函数
   单独可测（IPython 魔法、`import x as y`、`ast` 解析失败时的正则兜底），
   并在真 notebook 目录存在时整体跑一遍：`current`/`legacy` 的导入**不得有缺口**，
   `unknown` 只允许出现在**已交代**清单里（新增未知模块必须逐个说明）。

运行方式::

    pytest tests/test_notebook_import_audit.py -v
"""

import importlib
import importlib.util
import os
import sys
import warnings

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_SCRIPT = os.path.join(ROOT, 'scripts', 'check_notebook_imports.py')
_spec = importlib.util.spec_from_file_location('check_notebook_imports', _SCRIPT)
auditor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(auditor)

COMPAT_DIR = auditor.COMPAT_DIR
_LEGACY_NAMES = ('tri_lib', 'hexlib')


# ============================================================
# 1. 解析与分类（纯函数）
# ============================================================

def test_strip_magics_keeps_line_numbers():
    source = '%matplotlib inline\nimport numpy\n!pip install x\nfrom cst_solver import setup'
    stripped = auditor.strip_magics(source)
    assert stripped.splitlines()[1] == 'import numpy'
    assert stripped.splitlines()[3] == 'from cst_solver import setup'
    assert len(stripped.splitlines()) == len(source.splitlines())


def test_parse_imports_handles_common_forms():
    source = '\n'.join([
        'import numpy as np',
        'import os',
        'from cst_solver import setup, result',
        'from mesh_grid.tri_grid import TopoPath',
    ])
    refs = auditor.parse_imports(source)
    by_module = {ref['module']: ref for ref in refs}
    assert by_module['numpy']['asname'] == 'np'
    assert by_module['numpy']['names'] is None            # import X：不核对符号
    assert by_module['cst_solver']['names'] == ['setup', 'result']
    assert by_module['mesh_grid.tri_grid']['names'] == ['TopoPath']


def test_parse_imports_falls_back_to_regex_on_broken_cell():
    """单元格里有非 Python 片段（`ast` 解析失败）时仍要抓到导入行。"""
    source = 'import numpy as np\nthis is not python at all (((\nfrom hexlib import HexLib'
    refs = auditor.parse_imports(source)
    modules = {ref['module'] for ref in refs}
    assert modules == {'numpy', 'hexlib'}
    hexlib = [ref for ref in refs if ref['module'] == 'hexlib'][0]
    assert hexlib['names'] == ['HexLib']


@pytest.mark.parametrize('module,kind', [
    ('os', 'stdlib'),
    ('numpy', 'third-party'),
    ('cst.interface', 'cst'),
    ('cst_solver', 'current'),
    ('mesh_grid.tri_grid', 'current'),
    ('templates', 'current'),
    ('tri_lib', 'legacy'),
    ('hexlib', 'legacy'),
    ('metalen', 'migrated'),
    ('cst_solver.result', 'migrated'),
    ('some_unknown_thing', 'unknown'),
])
def test_classify(module, kind):
    assert auditor.classify(module) == kind


# ============================================================
# 2b. 审计必须**按模块**统计（第一版按顶层包合并，漏过一个真缺口）
# ============================================================

def _fake_notebook(tmp_path, name, code):
    import json
    path = tmp_path / name
    path.write_text(json.dumps({'cells': [{'cell_type': 'code',
                                           'source': code.splitlines(True)}]}),
                    encoding='utf-8')
    return path


def test_audit_keeps_submodules_separate(tmp_path):
    """`cst_solver` 与 `cst_solver.result` 要分别统计，不能混成一个包。"""
    _fake_notebook(tmp_path, 'a.ipynb', 'from cst_solver import setup\n')
    _fake_notebook(tmp_path, 'b.ipynb', 'from cst_solver.result import result\n')
    report = auditor.audit(str(tmp_path))
    assert set(report['per_module']) == {'cst_solver', 'cst_solver.result'}
    assert report['per_module']['cst_solver']['names'] == {'setup'}
    assert report['per_module']['cst_solver.result']['names'] == {'result'}


def test_audit_reports_a_missing_submodule_as_a_gap(tmp_path):
    """
    真正不存在的子模块必须报成缺口 —— 第一版把顶层包下所有名字合并、
    子模块不带名字时跳过核对，于是这种情况**静默通过**（已修）。
    """
    _fake_notebook(tmp_path, 'a.ipynb', 'from cst_solver.result import result\n')
    _fake_notebook(tmp_path, 'b.ipynb', 'from cst_solver.nope import thing\n')
    report = auditor.audit(str(tmp_path))
    gaps = {gap['module']: gap['missing'] for gap in report['symbol_gaps']}
    assert 'cst_solver.nope' in gaps
    assert any('No module named' in str(item) for item in gaps['cst_solver.nope'])
    assert 'cst_solver.result' not in gaps          # 这一条已登记为「已迁移」


def test_migrated_module_targets_really_exist():
    """
    旧名迁移表必须指向**真的存在且 API 相同**的模块。

    这张表的意义是「不需要找回旧模块，改一行导入即可」—— 目标一旦改名/删函数，
    这条结论就不成立，所以这里逐名核对（比注释可靠）。
    """
    for old_name, info in auditor.MIGRATED_MODULES.items():
        target = info['target']
        module = importlib.import_module(target)
        missing = [name for name in info['names'] if not hasattr(module, name)]
        assert missing == [], f'{old_name} → {target} 缺 {missing}'
        assert info['note'], f'{old_name} 的迁移说明不能为空'


# ============================================================
# 2. 旧名真的能导入（这才是「旧 notebook 导入兼容」）
# ============================================================

@pytest.fixture
def compat_on_path():
    """按文档做法把 `archive/compat` 加进 sys.path，并在结束后清理旧名缓存。"""
    saved_path = list(sys.path)
    saved_modules = {name: sys.modules.pop(name, None) for name in _LEGACY_NAMES}
    sys.path.insert(0, COMPAT_DIR)
    try:
        yield
    finally:
        sys.path[:] = saved_path
        for name, original in saved_modules.items():
            sys.modules.pop(name, None)
            if original is not None:
                sys.modules[name] = original


def test_legacy_names_import_with_warning(compat_on_path):
    for name in _LEGACY_NAMES:
        with pytest.warns(FutureWarning):
            module = importlib.import_module(name)
        assert module is not None, name


def test_legacy_names_are_the_same_objects_as_new_packages(compat_on_path):
    """旧名必须是**同一批对象**（转发），不是第二份实现。"""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        tri_lib = importlib.import_module('tri_lib')
        hexlib = importlib.import_module('hexlib')
        tri_grid = importlib.import_module('mesh_grid.tri_grid')
        hex_grid = importlib.import_module('mesh_grid.hex_grid')
    assert tri_lib.TopoPath is tri_grid.TopoPath
    assert hexlib.HexLib is hex_grid.HexLib


def test_legacy_hexlib_exposes_the_names_notebooks_use(compat_on_path):
    """`hexlib` 上被旧 notebook 实际用到的 5 个名字都要在（扫描结果见审计脚本）。"""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        hexlib = importlib.import_module('hexlib')
    for name in ('HexLib', 'HexGridVisualizer', 'create_hex_polygon',
                 'save_to_dxf', 'read_and_display_dxf_matplotlib'):
        assert hasattr(hexlib, name), f'hexlib 缺 {name}'


def test_shim_files_delegate_to_legacy_named_modules(compat_on_path):
    """`*_shim.py` 仍在，但只是转发（防止两份实现漂移）。"""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        shim = importlib.import_module('tri_lib_shim')
        real = importlib.import_module('tri_lib')
    assert shim.TopoPath is real.TopoPath


# ============================================================
# 3. 整体审计（需要本机旧 notebook 目录；没有就跳过）
# ============================================================

@pytest.mark.skipif(not os.path.isdir(auditor.SRC_DEFAULT),
                    reason='本机没有旧 notebook 目录，跳过整体审计')
def test_real_notebooks_have_no_repo_side_import_gaps():
    report = auditor.audit(auditor.SRC_DEFAULT)
    summary = auditor.summarize(report)
    assert report['notebooks'] > 0
    assert summary['symbol_gaps'] == [], (
        '旧 notebook 里出现了**仓库侧**的导入缺口：'
        + '; '.join(f"{g['module']} 缺 {g['missing']}" for g in summary['symbol_gaps']))
    undeclared = [m for m in summary['unknown'] if m not in auditor.KNOWN_MISSING]
    assert undeclared == [], (
        '出现了未交代的未知模块，请在 KNOWN_MISSING / MIGRATED_MODULES 里逐条说明：'
        + repr(undeclared))
    # 至少要确认旧名确实被用到（否则这个测试其实没验到什么）
    assert {'tri_lib', 'hexlib'} <= set(report['per_module'])
