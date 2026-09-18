# -*- coding: utf-8 -*-
r"""
多路径 VPC 区域并集与晶体裁剪（P5：多路径 VPC 与晶体裁剪）
=========================================================

计划原文（`docs/next_plan/README.md` P5）：

> 多路径 VPC 区域并集与晶体裁剪；基板并集已存在，需增加 VPC 的对应组合并真机验收。

**为什么值得单独测**：多路径的核心是**几何范围与实体命名的决策** ——
「VPC 区域要按所有分支取并集」「每条分支的晶体都要被裁到」—— 这是纯逻辑，
不需要 CST 就能验；只有最后「把并集发成 VBA、CST 是否接受」那一步需要真机。

守住的性质
----------
1. **单路径等价**：`build_vpc_regions_multi(paths={一条})` 与 `build_vpc_regions`
   **调用序列与参数名逐条相同**（这样 `TopoModeler` 才能安全地按路径数自动分流）；
2. **命名不与路径数耦合**：第一条路径的第一段永远叫 `vpc_A` / `vpc_B`
   （不是 `vpc_A_part0`），下游裁剪才能拿到稳定名字；
3. **各段/各路径实体名唯一**，且布尔并的目标**始终是规范名**（CST 的 `Add`
   结果留在第一个操作数）；
4. **每条路径用自己的 CST 参数前缀**（`p0`/`p1`…）—— 共用 `p1x` 会互相覆盖；
5. **裁剪吸收每一条分支**：每条路径的 A/B 晶体各被 `Intersect` 一次，
   操作数顺序是 `(vpc, crystal)`，VPC 区域名在整个过程里保持不变。

⚠️ 仍未真机验证：这些 VBA 序列**没有在真 CST 上跑过**（用记录型假 app 验的是调用
序列与命名，不是 CST 是否接受）；真机（只建模、不求解）见
`scripts/verify_vpc_multi_real.py`。

运行方式::

    pytest topo_modeler/tests/test_vpc_crystal_multi.py -v
"""

import os
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from mesh_grid.tri_grid import TopoPath                          # noqa: E402
from topo_modeler.builders import (                              # noqa: E402
    build_crystals_multi,
    build_vpc_regions,
    build_vpc_regions_multi,
    clip_crystals_with_vpc,
)
from topo_modeler.modeler import TopoModeler                     # noqa: E402

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
    """记录所有调用的假 app（与 `test_multi_path.py` 同款）。

    ⚠️ 注意实参形态：`app.extrude(..., name=…)` 与
    `app.translate(..., repetitions=…)` 都是**关键字**传的，
    直接取位置参数会 IndexError（写这几条断言时踩过一次）。

    ⚠️ 另外：`__getattr__` 会把**写错的助手名**静默变成「一个啥都不做的假 CST 方法」，
    于是断言里写 `app.repetitions()`（少了 `reps`）会返回 `None` 而不是报错
    —— 用 -q 跑出 `TypeError: 'NoneType' is not subscriptable` 时先怀疑拼写。
    """

    def __init__(self):
        self.calls = []

    def __getattr__(self, item):
        def _f(*a, **k):
            self.calls.append((item, a, tuple(sorted(k.items()))))
        return _f

    # --- 便于断言的助手 ---
    def ops(self, name):
        return [c for c in self.calls if c[0] == name]

    @staticmethod
    def _kw(call, key):
        return dict(call[2]).get(key)

    def targets(self, op):
        """某个布尔操作的第一位置参数（= 结果落在谁身上）。"""
        return [c[1][0] for c in self.calls if c[0] == op]

    def extrude_names(self):
        return [self._kw(c, 'name') for c in self.ops('extrude')]

    def reps(self):
        return [self._kw(c, 'repetitions') for c in self.ops('translate')]

    def para_names(self):
        """`app.para(name, value)` 的第一个位置参数（路径点参数在这里）。

        ⚠️ `TopoPath.auto_define_cst_params()` **不是**调用 `app.auto_define_cst_params`，
        而是逐点 `app.para(f'{prefix}{i+1}x', …)`（见 `docs/packages/mesh_grid.md`），
        所以「前缀有没有分开」要看 `para` 的名字，而不是找同名方法。
        """
        return [c[1][0] for c in self.ops('para')]

    def shape_names(self):
        """所有被创建过的几何实体名（triangle / extrude 的 `name=`）。"""
        names = []
        for op in ('triangle', 'extrude'):
            names.extend(n for n in (self._kw(c, 'name') for c in self.ops(op)) if n)
        return names


# ============================================================
# 1. 单路径等价：可以安全地按路径数自动分流
# ============================================================

def test_single_path_multi_matches_single_path_builder():
    """
    一条路径时，多路径版本的调用序列与参数名必须与单路径版本**逐条相同**。

    这正是 `TopoModeler.build_vpc_regions()` 敢按 `len(paths) > 1` 分流的依据。
    """
    single_app = _Recorder()
    build_vpc_regions(single_app, _straight())

    multi_app = _Recorder()
    build_vpc_regions_multi(multi_app, {'main': _straight()})

    assert multi_app.calls == single_app.calls


def test_single_path_keeps_canonical_entity_names():
    """规范名不能被路径下标污染：`vpc_A`/`vpc_B`，不是 `vpc_A_p0_seg1`。"""
    app = _Recorder()
    vpca, vpcb = build_vpc_regions_multi(app, {'main': _straight()})
    assert (vpca, vpcb) == ('vpc_A', 'vpc_B')
    assert {'vpc_A', 'vpc_B'} <= set(app.extrude_names())
    assert not any('_p' in n for n in app.extrude_names()), app.extrude_names()


# ============================================================
# 2. 两条路径：并集、命名与前缀
# ============================================================

def _two_paths():
    return {'main': _straight(), 'arm': _bent(name='r')}


def test_union_targets_are_the_canonical_names():
    """布尔并的目标始终是 `vpc_A` / `vpc_B`（Add 结果留第一个操作数）。"""
    app = _Recorder()
    build_vpc_regions_multi(app, _two_paths())
    adds = app.ops('add')
    assert adds, '两条路径必须产生布尔并'
    assert set(app.targets('add')) == {'vpc_A', 'vpc_B'}


def test_every_segment_of_every_path_is_united_once():
    """
    Add 次数 = 实体总数 − 2（两侧各留一个规范名当承载者），
    且被并掉的实体名两两不同（没有覆盖别人的段）。
    """
    app = _Recorder()
    build_vpc_regions_multi(app, _two_paths())
    solids = app.extrude_names()
    assert len(solids) == len(set(solids)), f'实体名撞车：{solids}'
    assert len(app.ops('add')) == len(solids) - 2
    assert 'vpc_A' in solids and 'vpc_B' in solids


def test_each_path_gets_its_own_parameter_prefix():
    """两条路径必须各用各的 CST 参数前缀（`p0`/`p1`），否则参数互相覆盖。"""
    app = _Recorder()
    build_vpc_regions_multi(app, _two_paths())
    names = app.para_names()
    assert names, '路径点参数必须被登记'
    first = [n for n in names if n.startswith('p0')]
    second = [n for n in names if n.startswith('p1')]
    assert first and second, names[:10]
    assert not set(first) & set(second), '两条路径的参数名前缀必须互不相交'


def test_unite_false_keeps_separate_solids():
    """`unite=False` 只建不并（排错用），此时不应出现任何 add。"""
    app = _Recorder()
    build_vpc_regions_multi(app, _two_paths(), unite=False)
    assert app.ops('add') == []
    assert len(app.ops('extrude')) >= 4


def test_empty_paths_is_rejected():
    app = _Recorder()
    with pytest.raises(ValueError, match='paths 不能为空'):
        build_vpc_regions_multi(app, {})


def test_thickness_offset_is_applied_to_every_solid():
    """每块带都要 `translate 0 0 -h/2`（z 平面对齐 hard 约定）。"""
    app = _Recorder()
    build_vpc_regions_multi(app, _two_paths())
    trans = app.ops('translate')
    assert len(trans) == len(app.ops('extrude'))


# ============================================================
# 3. 多路径晶体：命名不冲突 + 阵列次数可走参数引用
# ============================================================

def test_crystals_multi_names_are_unique_and_first_path_canonical():
    """
    命名规则：**第 1 条分支用规范名**（`g1A`/`g1B`，与单路径逐名相同），
    第 k≥2 条在名字里带上分支号（`g{k}1A`）—— 否则两条分支的 `tri_up_A`
    这种内部实体名会撞车。
    """
    app = _Recorder()
    crystals = build_crystals_multi(app, _two_paths())
    assert list(crystals) == ['main', 'arm']                 # 保持传入顺序
    assert crystals['main'] == ('g1A', 'g1B')                # 第一条 = 单路径命名
    assert crystals['arm'] == ('g21A', 'g21B')
    assert len(set(crystals['main']) | set(crystals['arm'])) == 4


def test_crystals_multi_has_no_entity_name_collisions():
    """所有实体名（含内部小三角形）必须两两不同。"""
    app = _Recorder()
    build_crystals_multi(app, _two_paths())
    shapes = app.shape_names()
    assert len(shapes) == len(set(shapes)), f'实体名撞车：{shapes}'
    # 小三角形必须带上分支号，否则第二分支会复用第一分支的孔
    assert any(n.startswith('tri_up_A2') for n in shapes), shapes[:12]


def test_crystals_multi_can_reference_cst_parameters():
    """传参数名 ⇒ 阵列次数写成 `int(xup)` 而不是 `int(25)`（P4 §8.7 的口径）。"""
    app = _Recorder()
    build_crystals_multi(app, {'main': _straight()},
                         xup='xup', yup='yup', ydn='ydn')
    reps = app.reps()
    assert reps[:3] == ['int(xup)', 'int(yup/2)', 'int(ydn/2)'], reps


def test_crystals_multi_rejects_empty():
    app = _Recorder()
    with pytest.raises(ValueError, match='paths 不能为空'):
        build_crystals_multi(app, {})


# ============================================================
# 4. 裁剪：每条分支的晶体都要被吸收
# ============================================================

def test_clip_absorbs_every_branch():
    app = _Recorder()
    crystals = {'main': ('g1A', 'g1B'), 'arm': ('g2A', 'g2B')}
    info = clip_crystals_with_vpc(app, 'vpc_A', 'vpc_B', crystals)
    intersects = app.ops('intersect')
    assert len(intersects) == 4
    # 操作数顺序必须是 (vpc, crystal)：结果留在 vpc 上（参考工程 AB_feed.cst）
    assert [c[1][0] for c in intersects] == ['vpc_A', 'vpc_B', 'vpc_A', 'vpc_B']
    assert [c[1][1] for c in intersects] == ['g1A', 'g1B', 'g2A', 'g2B']
    assert info['pairs'] == 2
    assert info['consumed'] == ['g1A', 'g1B', 'g2A', 'g2B']
    assert (info['vpc_a'], info['vpc_b']) == ('vpc_A', 'vpc_B')


def test_clip_accepts_a_list_of_pairs():
    app = _Recorder()
    info = clip_crystals_with_vpc(app, 'vpc_A', 'vpc_B',
                                  [('g1A', 'g1B'), ('g2A', 'g2B')])
    assert info['pairs'] == 2 and len(app.ops('intersect')) == 4


def test_clip_rejects_empty():
    app = _Recorder()
    with pytest.raises(ValueError, match='crystals 不能为空'):
        clip_crystals_with_vpc(app, 'vpc_A', 'vpc_B', {})


def test_clip_keeps_vpc_names_stable_across_branches():
    """全程只对 `vpc_A`/`vpc_B` 求交 —— 名字不能中途被消耗掉。"""
    app = _Recorder()
    clip_crystals_with_vpc(app, 'vpc_A', 'vpc_B',
                           [('g1A', 'g1B'), ('g2A', 'g2B'), ('g3A', 'g3B')])
    firsts = {c[1][0] for c in app.ops('intersect')}
    assert firsts == {'vpc_A', 'vpc_B'}


# ============================================================
# 5. TopoModeler 接线：按路径数自动分流
# ============================================================

def test_modeler_auto_uses_multi_when_several_paths():
    m = _modeler()
    m.app = _Recorder()
    m.set_paths(_two_paths())
    vpca, vpcb = m.build_vpc_regions()
    assert (vpca, vpcb) == ('vpc_A', 'vpc_B')
    names = m.app.para_names()
    assert any(n.startswith('p0') for n in names), '多路径没走并集分支'
    assert any(n.startswith('p1') for n in names)
    assert m._built_parts['vpca'] == 'vpc_A'


def test_modeler_single_path_uses_the_single_path_builder():
    m = _modeler()
    m.app = _Recorder()
    m.set_paths({'main': _straight()})
    m.build_vpc_regions()
    names = m.app.para_names()
    assert names, '路径点参数必须被登记'
    # 单路径必须用旧前缀 `p`（`p1x/p2x…`），不带路径下标 `p0`
    assert not any(n.startswith('p0') for n in names), names[:8]
    assert any(n.startswith('p1') for n in names)


def test_modeler_multi_crystals_and_clip_roundtrip():
    m = _modeler()
    m.app = _Recorder()
    m.set_paths(_two_paths())
    m.build_vpc_regions()
    crystals = m.build_crystals_multi()
    assert set(crystals) == {'main', 'arm'}
    assert m._built_parts['crystals'] is crystals
    info = m.clip_crystals_with_vpc()
    assert info['consumed'] == ['g1A', 'g1B', 'g21A', 'g21B']
    assert m._built_parts['clipped'] is info


def test_modeler_clip_can_be_limited_to_some_paths():
    m = _modeler()
    m.app = _Recorder()
    m.set_paths(_two_paths())
    m.build_vpc_regions()
    m.build_crystals_multi()
    info = m.clip_crystals_with_vpc(paths={'arm'})
    assert info['consumed'] == ['g21A', 'g21B']


def test_modeler_clip_works_with_single_path_crystal():
    """单路径走 `build_crystal()` 也要能裁剪（向后兼容）。"""
    m = _modeler()
    m.app = _Recorder()
    m.set_paths({'main': _straight()})
    m._built_parts['crystal_a'] = 'g1A'
    m._built_parts['crystal_b'] = 'g1B'
    m.build_vpc_regions()
    info = m.clip_crystals_with_vpc()
    assert info['consumed'] == ['g1A', 'g1B']


def test_modeler_clip_reports_missing_pieces():
    m = _modeler()
    m.app = _Recorder()
    m.set_paths({'main': _straight()})
    with pytest.raises(RuntimeError, match='晶体'):
        m.clip_crystals_with_vpc()
    m._built_parts['crystal_a'] = 'g1A'
    m._built_parts['crystal_b'] = 'g1B'
    with pytest.raises(RuntimeError, match='VPC'):
        m.clip_crystals_with_vpc()
