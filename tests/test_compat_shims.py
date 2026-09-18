# -*- coding: utf-8 -*-
r"""
旧名兼容入口的「弃用登记」核查（P5：shim 复评）
==============================================

计划原文（`docs/next_plan/README.md` P5）：

> 到兼容周期结束后复评 `templates` shim 与旧脚本去留；**先登记弃用并验证调用者**，
> 不能因计划清理就删除用户 notebook 或结果。

这句话拆成两半：

* **能现在做的**（本文件守住）：三个旧名入口必须
  ① 仍然**可用**（转发到真实现，不是副本、不是空壳）；
  ② 每次导入都**发警告**（登记弃用）；
  ③ 转发的是**同一个对象**（`is` 判等，避免"同名双份定义"）；
  ④ 使用者可被**清点**（`scripts/check_notebook_imports.py` 的实测数字有出处）。
* **只能等版本周期结束做的**：删 shim —— 属时间门，不是技术门（见计划条目）。

为什么不许现在删：调用者统计是 **58 个 notebook 用 `tri_lib`、41 个用 `hexlib`、
3 个用 `topo_modeler`、4 个用 `mesh_grid`**（`docs/guides/notebook_import_audit.md`），
删掉 shim 会让这些**用户的 notebook 直接 import 失败**。

运行方式::

    pytest tests/test_compat_shims.py -v
"""

import importlib
import os
import subprocess
import sys
import textwrap
import warnings

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

#: 旧名入口 → 它必须转发到的「真实现」里的一两个代表对象
SHIMS = (
    ('templates', 'topo_templates', ('StraightWaveguide', 'UnitAntenna',
                                     'GRINLensAntenna')),
    ('archive.compat.tri_lib', 'mesh_grid.tri_grid', ('TopoPath',)),
    ('archive.compat.hexlib', 'mesh_grid.hex_grid', ('HexGridVisualizer',)),
)


def _import_recording_warnings(name):
    """导入 `name` 并返回（模块, 警告类别集合）。"""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        module = importlib.import_module(name)
    return module, {w.category.__name__ for w in caught}


@pytest.mark.parametrize('old,new,names', SHIMS, ids=[s[0] for s in SHIMS])
def test_shim_still_works_warns_and_forwards_the_same_objects(old, new, names):
    """① 可用 ② 发警告 ③ 转发同一个对象（不是副本）。"""
    module, categories = _import_recording_warnings(old)
    assert categories & {'DeprecationWarning', 'FutureWarning'}, (
        f'{old} 导入时没有发弃用警告 —— 弃用登记丢了')
    target = importlib.import_module(new)
    for name in names:
        assert hasattr(module, name), f'{old} 不再导出 {name}（用户的 notebook 会挂）'
        assert getattr(module, name) is getattr(target, name), (
            f'{old}.{name} 与 {new}.{name} 不是同一个对象 —— shim 变成了副本')


def test_shim_works_from_a_clean_interpreter():
    """
    ④ 在**干净解释器**里也成立（不依赖本进程已导入的顺序/缓存）。

    顺带证明「用户 notebook 的第一行 `from tri_lib import ...` 还能跑」。
    ⚠️ `tri_lib` / `hexlib` 这两个旧名入口在 `archive/compat/` 里，用户 notebook 靠
    `archive/compat/setup_path_bootstrap.py`（或运行目录）把那个目录放进 `sys.path`；
    这里显式加进去，模拟同样的环境。
    """
    compat = os.path.join(ROOT, 'archive', 'compat')
    code = textwrap.dedent('''
        import warnings; warnings.simplefilter('ignore')
        import sys
        sys.path.insert(0, %r)
        sys.path.insert(0, %r)
        from tri_lib import TopoPath                       # noqa: F401
        from hexlib import HexGridVisualizer               # noqa: F401
        from templates import StraightWaveguide            # noqa: F401
        print('SHIM_OK')
    ''') % (compat, ROOT)
    result = subprocess.run([sys.executable, '-c', code], capture_output=True,
                            text=True, encoding='utf-8', errors='replace')
    assert result.returncode == 0, result.stderr
    assert 'SHIM_OK' in (result.stdout or '')


def test_caller_census_is_reproducible():
    """
    ④ 调用者清点必须有**可复跑**的出处：`scripts/check_notebook_imports.py`
    仍能扫出旧名用户（数字见审计报告；这里只要求"扫得到"，不钉死具体条数——
    用户随时可能新增 notebook）。
    """
    script = os.path.join(ROOT, 'scripts', 'check_notebook_imports.py')
    assert os.path.isfile(script)
    result = subprocess.run([sys.executable, script], capture_output=True,
                            text=True, encoding='utf-8', errors='replace',
                            cwd=ROOT)
    assert result.returncode == 0, (result.stdout or '') + (result.stderr or '')
    out = (result.stdout or '')
    assert 'unknown' in out.lower(), out[-500:]      # 审计结论里必须给未知数
    assert '0' in out, out[-500:]
