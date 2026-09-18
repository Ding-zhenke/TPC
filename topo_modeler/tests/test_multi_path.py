# -*- coding: utf-8 -*-
r"""
多路径支持测试（阶段 8 模块 6.1）
================================
对应 `TopoModeler` 的多路径管理 / 并集几何查询，与
`builders/substrate.py::build_substrate_multi`。

**为什么这是阶段 8 里最能离线验证的一块**：多路径的核心是**几何范围决策** ——
「基板 / VPC / 晶体阵列要按所有路径的**并集**取」。这是个纯计算问题，
不需要 CST 就能验；只有最后「把并集发成 VBA」那一步需要。

⚠️ 仍未验证：`build_substrate_multi` 生成的 VBA 序列**没有在真 CST 上跑过**
（用记录型假 app 验的是调用序列与参数前缀，不是 CST 是否接受）。

运行方式::

    pytest topo_modeler/tests/test_multi_path.py -v
"""

import os
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from mesh_grid.tri_grid import TopoPath                     # noqa: E402
from topo_modeler.builders import build_substrate_multi     # noqa: E402
from topo_modeler.modeler import TopoModeler                # noqa: E402

A = 0.2425


def _straight(name='p', length=18):
    return TopoPath.builder(A, name=name).start(0, 0).move(length, 'c').build()


def _bent(name='q', length=18, arm=14, turn=120):
    return (TopoPath.builder(A, name=name).start(0, 0).move(length, 'c')
            .turn(turn).move(arm, 'along').build())


def _modeler():
    """不碰 CST 的 TopoModeler 实例（绕开 __init__ 打开工程那一步）。"""
    m = TopoModeler.__new__(TopoModeler)
    m.template_cst = 'x'
    m.app = None
    m.path = None
    m._paths = {}
    m.topology = None
    m.model_type = None
    m.params = {}
    m.nm = None
    m._built_parts = {}
    m._cst_path = None
    return m


class _Recorder:
    """记录所有调用的假 app。"""

    def __init__(self):
        self.calls = []

    def __getattr__(self, item):
        def _f(*a, **k):
            self.calls.append((item, a, tuple(sorted(k.items()))))
        return _f


# ============================================================
# 1. 路径管理
# ============================================================

def test_set_path_is_single_path_under_the_name_main():
    """向后兼容：set_path() 等价于 set_paths({'main': path})。"""
    m = _modeler()
    m.set_path(_straight())
    assert m.path_names == ['main']
    assert m.is_multi_path is False
    assert m.path is m.paths['main']


def test_set_paths_and_add_remove():
    m = _modeler()
    m.set_paths({'main': _straight(), 'arm': _bent()})
    assert m.path_names == ['main', 'arm']
    assert m.is_multi_path is True
    m.add_path('arm2', _bent(name='r', turn=240))
    assert m.path_names == ['main', 'arm', 'arm2']
    m.remove_path('arm2')
    assert m.path_names == ['main', 'arm']


def test_paths_property_returns_a_copy():
    m = _modeler()
    m.set_paths({'main': _straight()})
    snapshot = m.paths
    snapshot['sneaky'] = _straight()
    assert 'sneaky' not in m.paths          # 外部改不动内部状态


def test_add_path_rejects_duplicate_name():
    m = _modeler()
    m.set_paths({'main': _straight()})
    with pytest.raises(ValueError, match='已存在'):
        m.add_path('main', _straight())


def test_add_path_rejects_non_topopath():
    m = _modeler()
    with pytest.raises(TypeError, match='TopoPath'):
        m.add_path('x', 'not-a-path')


def test_remove_path_refuses_to_empty():
    m = _modeler()
    m.set_paths({'main': _straight()})
    with pytest.raises(ValueError, match='至少'):
        m.remove_path('main')


def test_set_paths_rejects_empty_and_bad_values():
    m = _modeler()
    with pytest.raises(ValueError, match='至少一条'):
        m.set_paths({})
    with pytest.raises(TypeError, match='TopoPath'):
        m.set_paths({'main': 42})


# ============================================================
# 2. 并集几何（判据：「多路径基板/VPC 区域正确覆盖所有分支」的计算部分）
# ============================================================

def test_array_range_is_the_elementwise_max_over_paths():
    """
    🔴 核心：并集阵列范围必须取各路径的**逐项最大值** ——
    否则短主干 + 长分支时，分支会露在基板/阵列之外。
    """
    m = _modeler()
    m.set_paths({'main': _straight(), 'arm1': _bent(turn=120),
                 'arm2': _bent(name='r', turn=240)})
    per_path = {n: m.array_range([n]) for n in m.path_names}
    assert per_path['main'] == (19, 1, 1)
    xup, yup, ydn = m.array_range()
    assert xup == max(v[0] for v in per_path.values())
    assert yup == max(v[1] for v in per_path.values())
    assert ydn == max(v[2] for v in per_path.values())
    # 单主干根本不够：分支的 yup/ydn 都是 15
    assert yup >= per_path['arm1'][1]


def test_array_range_covers_every_paths_own_range():
    m = _modeler()
    m.set_paths({'main': _straight(), 'arm': _bent()})
    ux, uy, ud = m.array_range()
    for name in m.path_names:
        px, py, pd = m.array_range([name])
        assert ux >= px and uy >= py and ud >= pd


def test_array_range_rejects_unknown_path():
    m = _modeler()
    m.set_paths({'main': _straight()})
    with pytest.raises(KeyError, match='nope'):
        m.array_range(['nope'])


def test_bounding_box_covers_all_paths():
    m = _modeler()
    m.set_paths({'main': _straight(), 'arm1': _bent(turn=120),
                 'arm2': _bent(name='r', turn=240)})
    xmin, xmax, ymin, ymax = m.bounding_box()
    assert xmin < 0 and xmax > 4.3                    # 主干 x ∈ [0, 18a]
    assert ymax > 1.0 and ymin < -1.0                 # 两条臂朝上下分开
    for name in m.path_names:
        bx0, bx1, by0, by1 = m.paths[name].get_bounding_box()
        assert xmin <= bx0 and xmax >= bx1
        assert ymin <= by0 and ymax >= by1


def test_all_lattice_points_is_a_sorted_union():
    """并集必须**恰好**等于各路径晶格点集合的并（不多不少）。"""
    m = _modeler()
    m.set_paths({'main': _straight(), 'arm1': _bent(turn=120),
                 'arm2': _bent(name='r', turn=240)})
    pts = m.all_lattice_points()
    expected = set()
    for path in m.paths.values():
        expected.update(path.path_lattice)
    assert set(pts) == expected
    assert len(pts) == len(expected)                  # 无重复
    assert pts == sorted(pts)                         # 有序
    assert (0, 0) in pts and (0, 18) in pts


def test_single_path_union_equals_that_path():
    m = _modeler()
    m.set_paths({'main': _straight()})
    assert m.array_range() == m.paths['main'].get_array_range()
    xmin, xmax, ymin, ymax = m.bounding_box()
    assert (xmin, xmax, ymin, ymax) == m.paths['main'].get_bounding_box()


def test_symbolic_path_without_param_values_reports_clearly():
    """符号路径算不出数值量时，报错要说清原因（而不是抛个裸异常）。"""
    sym = (TopoPath.builder(A, name='p').start(0, 0).move('x1', 'c').build())
    m = _modeler()
    m.set_paths({'main': _straight(), 'sym': sym})
    # 符号路径在 get_array_range 上同样需要 param_values
    with pytest.raises(Exception) as exc:
        m.bounding_box()
    assert 'param_values' in str(exc.value) or '符号' in str(exc.value)


# ============================================================
# 3. 多路径基板构建器的调用序列（离线可验的部分）
# ============================================================

def test_build_substrate_multi_gives_each_path_its_own_param_prefix():
    """
    两条路径都用 `p1x/p1y…` 会互相覆盖 —— 所以每条路径必须有**独立前缀**。
    """
    app = _Recorder()
    paths = {'main': _straight(), 'arm': _bent()}
    build_substrate_multi(app, paths, name='sub')

    para_names = [a[0] for n, a, _k in app.calls if n == 'para']
    assert para_names, '应当为路径点登记 CST 参数'
    # 前缀按序号区分：p0* / p1*
    assert any(n.startswith('p0') for n in para_names)
    assert any(n.startswith('p1') for n in para_names)
    assert not any(n.startswith('p2') for n in para_names)
    # 不存在重复登记
    assert len(para_names) == len(set(para_names))


def test_build_substrate_multi_unites_bands_and_translates_once():
    app = _Recorder()
    paths = {'main': _straight(), 'arm1': _bent(turn=120),
             'arm2': _bent(name='r', turn=240)}
    result = build_substrate_multi(app, paths, name='sub')

    polylines = [a[0] for n, a, _k in app.calls if n == 'polyline']    # 顶点列表是唯一位置参数
    extrudes = [a[1] for n, a, _k in app.calls if n == 'extrude']      # (curve, name)
    adds = [a for n, a, _k in app.calls if n == 'add']
    translates = [a for n, a, _k in app.calls if n == 'translate']

    # 弯折路径按「每段一个四边形 + 拐角补块」建（P4/V6 真机修复）：
    # 每段一个 polyline/extrude，因此数量 ≥ 路径数，而不是恒定相等。
    assert len(polylines) == len(extrudes) >= 3
    assert all(isinstance(p, (list, tuple)) and p for p in polylines)
    assert len(adds) == len(extrudes) - 1        # N 个实体并成 1 个 ⇒ N-1 次 Add
    assert len(translates) == 1                  # 只在最后 z 居中一次
    assert extrudes[0] == 'sub_part0'
    assert {'sub_part1', 'sub_part2'} <= set(extrudes)
    # Add 的结果留在**第一个操作数**（ARCHITECTURE §6 硬约定 2）
    assert all(a[0] == 'sub_part0' for a in adds)
    assert result == 'sub_part0'
    assert translates[0][0] == 'sub_part0'


def test_build_substrate_multi_can_keep_parts_separate():
    """unite=False 时不并，方便排错（能分别看到每条带）。"""
    app = _Recorder()
    build_substrate_multi(app, {'a': _straight(), 'b': _bent()}, unite=False)
    assert not [c for c in app.calls if c[0] == 'add']


def test_build_substrate_multi_rejects_empty():
    with pytest.raises(ValueError, match='不能为空'):
        build_substrate_multi(_Recorder(), {})


def test_build_substrate_multi_single_path_still_works():
    app = _Recorder()
    r = build_substrate_multi(app, {'only': _straight()}, name='s')
    assert r == 's_part0'
    assert not [c for c in app.calls if c[0] == 'add']


# ============================================================
# 4. Modeler 层的分派
# ============================================================

def test_modeler_build_substrate_dispatches_to_multi_when_multi_path(monkeypatch):
    import topo_modeler.modeler as M

    seen = {}

    def fake_single(app, path, **kw):
        seen['single'] = True
        return 'single_solid'

    def fake_multi(app, paths, **kw):
        seen['multi'] = list(paths)
        return 'multi_solid'

    monkeypatch.setattr(M, 'build_substrate', fake_single)
    monkeypatch.setattr(M, 'build_substrate_multi', fake_multi)

    m = _modeler()
    m.set_paths({'main': _straight()})
    assert m.build_substrate() == 'single_solid'
    assert seen.get('single') and 'multi' not in seen

    seen.clear()
    m.set_paths({'main': _straight(), 'arm': _bent()})
    assert m.build_substrate() == 'multi_solid'
    assert seen['multi'] == ['main', 'arm']


def test_modeler_build_substrate_can_target_a_subset(monkeypatch):
    import topo_modeler.modeler as M
    seen = {}
    monkeypatch.setattr(M, 'build_substrate_multi',
                        lambda app, paths, **kw: seen.setdefault('p', list(paths)) or 'x')
    m = _modeler()
    m.set_paths({'main': _straight(), 'arm1': _bent(turn=120),
                 'arm2': _bent(name='r', turn=240)})
    m.build_substrate(paths={'arm1': m.paths['arm1'], 'arm2': m.paths['arm2']})
    assert seen['p'] == ['arm1', 'arm2']


def test_describe_paths_is_readable_and_gbk_safe():
    m = _modeler()
    m.set_paths({'main': _straight(), 'arm': _bent()})
    text = m.describe_paths()
    text.encode('gbk')                       # 不能崩在 GBK 控制台
    assert '路径数：2' in text and 'main' in text and 'arm' in text


def test_single_path_describe_has_no_union_lines():
    m = _modeler()
    m.set_paths({'main': _straight()})
    text = m.describe_paths()
    assert '单路径' in text and '并集包围盒' not in text
