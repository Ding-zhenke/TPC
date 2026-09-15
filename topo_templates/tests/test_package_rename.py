# -*- coding: utf-8 -*-
r"""
包改名回归测试（T10：`templates` → `topo_templates`）
==================================================

守住什么
--------
1. **新名可用**：`import topo_templates` 正常，且导出两个模板类；
2. **旧名是 shim 而不是副本**：`import templates` 拿到的必须是**同一个类对象**
   （`is` 判断）—— 如果是两份定义，`isinstance` 会莫名其妙地失败；
3. **旧名必须发 `DeprecationWarning`**：不发就等于静默保留了两个包名，
   做不到「一个版本周期后移除」；
4. **新名不得产生任何来自本库的告警**（曾经有过：模板 docstring 里的
   ``r'D:\out\wg.cst'`` 是非 raw 字符串，`\o` 是无效转义序列 ——
   在 Python 3.12+ 会变成 SyntaxWarning，在严格告警过滤下直接报错）。

⚠️ 本文件需要可导入的 `cst_solver`（模板依赖 `topo_modeler` → `cst_solver`）。

运行方式::

    pytest topo_templates/tests/test_package_rename.py -v
"""

import os
import sys
import warnings

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

_EXPECTED = ('StraightWaveguide', 'UnitAntenna')


@pytest.fixture(scope='module')
def new_pkg():
    try:
        import topo_templates
    except Exception as exc:                       # pragma: no cover - 环境相关
        pytest.skip(f'需要可导入的 topo_templates（含 CST python 库）：{exc!r}')
    return topo_templates


def test_new_package_imports_and_exports(new_pkg):
    """新包名可用，且导出两个模板类。"""
    assert set(new_pkg.__all__) == set(_EXPECTED)
    for name in _EXPECTED:
        assert getattr(new_pkg, name) is not None


def test_new_package_emits_no_warning_from_our_code(new_pkg):
    """
    重新导入新包时，不得产生任何**来自本库**的告警。

    第三方的 `fontTools.py23` 会发一条 DeprecationWarning（matplotlib 引入的），
    与本库无关，这里按模块名过滤掉。
    """
    import importlib
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        importlib.reload(new_pkg)
    ours = [w for w in caught if 'fontTools' not in str(getattr(w, 'filename', ''))]
    assert not ours, '本库产生了告警：' + '; '.join(
        f'{w.category.__name__}: {w.message}' for w in ours)


def test_old_name_is_a_shim_not_a_copy(new_pkg):
    """`import templates` 必须转发到同一个类对象（不是第二份定义）。"""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DeprecationWarning)
        import templates
    for name in _EXPECTED:
        assert getattr(templates, name) is getattr(new_pkg, name), (
            f'{name} 在旧名与新名下不是同一个对象 —— 说明 shim 变成了副本')


def test_old_name_warns_deprecation():
    """旧名必须发 DeprecationWarning（否则「一个版本周期后移除」无从执行）。"""
    import importlib
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        import templates
        importlib.reload(templates)
    deps = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deps, 'import templates 没有发出 DeprecationWarning'
    assert any('topo_templates' in str(w.message) for w in deps), \
        '弃用告警里应指明新包名'


def test_template_modules_have_no_invalid_escape_in_docstring():
    """
    模板模块的 docstring 里含 Windows 路径示例（``r'D:\\out\\wg.cst'``），
    必须写成 raw 字符串，否则 `\\o` 是无效转义序列（3.12+ 变 SyntaxWarning）。
    """
    import importlib.util
    for fname in ('straight_waveguide.py', 'unit_antenna.py'):
        path = os.path.join(_TPC_ROOT, 'topo_templates', fname)
        src = open(path, encoding='utf-8').read()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            compile(src, path, 'exec')
        bad = [w for w in caught if 'invalid escape sequence' in str(w.message)]
        assert not bad, f'{fname} 的 docstring 里有无效转义序列：{bad[0].message}'


def test_package_directory_is_top_level():
    """目录名必须是 `topo_templates`，且 `templates/` 只剩一个 shim 文件。"""
    tt = os.path.join(_TPC_ROOT, 'topo_templates')
    assert os.path.isdir(tt)
    assert os.path.isfile(os.path.join(tt, '__init__.py'))
    old = os.path.join(_TPC_ROOT, 'templates')
    assert os.path.isdir(old), 'shim 目录应当还在'
    files = [f for f in os.listdir(old) if f.endswith('.py')]
    assert files == ['__init__.py'], f'shim 目录里不该有别的模块：{files}'


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
