# -*- coding: utf-8 -*-
"""
守卫层误报回归测试（P4/V4）
===========================

守住什么
--------
真机实测（CST 2026，2026-09）发现：`UnitAntenna` 在 **warn 模式**下建模会刷出
**6 条** `[LOG_FLAG_NO_REBUILD]`（T7'/T13）噪声警告，针对 `p1x/p1y/p2x/p2y/p3x/p3y`。

根因：`build_substrate` / `build_vpc_regions` / 模板的 `_define_all_params` **都会**
调用 `TopoPath.auto_define_cst_params()`。第二次及以后登记时：

* 参数**已存在**（preexisting=True）⇒ 守卫认为「改了已存在参数」；
* 此时几何**也已经建了一部分**（`geometry_exists()` 为真）；
* 于是 `mark_params_changed()` 判脏并发出 T13 警告 —— 尽管值是**同一个表达式**。

修法：`auto_define_cst_params()` 改成**幂等** —— 同一个 `TopoPath` 在同一个 `app`
上只登记一次（晶格没变 ⇒ 表达式没变）。换 app 仍然会正常登记。

本文件用假 app 钉住这个行为（无需 CST）。
"""

import os
import sys

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from mesh_grid.tri_grid import TopoPath          # noqa: E402

A = 0.2425


class _FakeApp:
    """记录 para() 调用的假 app。"""

    def __init__(self):
        self.params = []

    def para(self, name, value, *args, **kwargs):
        self.params.append((name, value))


def _path():
    return TopoPath.builder(A, name='p').start(0, -1).move(19, 'c').build()


def test_repeated_call_on_same_app_is_idempotent():
    """核心回归：同一 path + 同一 app 重复调用只登记一次。"""
    path = _path()
    app = _FakeApp()
    path.auto_define_cst_params(app, prefix='p')
    first = list(app.params)
    assert first, '第一次应当登记参数'

    path.auto_define_cst_params(app, prefix='p')
    path.auto_define_cst_params(app, prefix='p')
    assert app.params == first, f'重复调用不应再登记：{app.params[len(first):]}'


def test_different_app_still_defines():
    """换一个 app 时必须重新登记（否则新工程里没有参数）。"""
    path = _path()
    first_app, second_app = _FakeApp(), _FakeApp()
    path.auto_define_cst_params(first_app, prefix='p')
    path.auto_define_cst_params(second_app, prefix='p')
    assert second_app.params == first_app.params
    assert len(second_app.params) == 4          # 2 个点 × (x, y)


def test_different_prefix_still_defines():
    """同一 app 上换前缀（例如另一条路径用 q 前缀）仍要登记。"""
    path = _path()
    app = _FakeApp()
    path.auto_define_cst_params(app, prefix='p')
    path.auto_define_cst_params(app, prefix='q')
    names = [name for name, _ in app.params]
    assert 'p1x' in names and 'q1x' in names


def test_expressions_are_still_parametric():
    """幂等不能把参数化弄丢：登记值仍必须是表达式，而不是数值。"""
    path = _path()
    app = _FakeApp()
    path.auto_define_cst_params(app, prefix='p')
    values = [value for _, value in app.params]
    assert '19*a' in values or any('*a' in str(v) for v in values), values
    assert not any(isinstance(v, float) for v in values)
