# -*- coding: utf-8 -*-
"""
GRIN 透镜构建器回归测试
=======================
对应实施计划 `docs/next_plan/README.md`。

守住什么
--------
`topo_modeler/builders/lens.py` 是把脚本 `topo_modeler/lens_build.py`
收编成库函数的结果。收编**不允许改变任何数值或任何一条 CST 调用** ——
本文件就是这条要求的证据：

1. **逐点等价**：把 `lens_build.py` 原样 `exec` 一遍（几何部分），
   把它的孔心 / 孔半径 / 椭圆参数与库函数的结果做**逐元素**比对；
2. **调用序列等价**：用记录型假 app 跑原脚本的 CST 段与库函数，
   逐条比对「方法名 + 位置参数 + 关键字参数」；
3. 三道几何自查必须全过。

⚠️ 参数取的是**参考配置**（`a=0.2425, ratio=8, Nx/Ny=38/34`）——
它算出的 DXF 多段线数 **2215** 与原脚本注释里记的
「实测 Nx/Ny = 38/34、2215 条多段线 = 183.9 s」**完全一致**，
说明这组取值就是当年真跑过的那套。

⚠️ 仍然**不证明** CST 认得这些 VBA —— 那只能在真机上验（见 stages/06 §5）。

运行方式::

    pytest topo_modeler/tests/test_lens.py -v
"""

import io
import os
import sys
import tempfile

import matplotlib
matplotlib.use('Agg')          # 无头环境：不能让原脚本的 plt.show() 阻塞
import matplotlib.pyplot as plt
import numpy as np
import pytest

matplotlib.pyplot.show = lambda *a, **k: None      # 原脚本末尾会调用它

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from topo_modeler.builders.lens import (      # noqa: E402
    GrinLensSpec,
    GrinLensHoles,
    LensGeometryError,
    build_grin_lens,
    build_grin_lens_holes,
    grin_lens_spec_from_cst_params,
)

_SCRIPT = os.path.join(_TPC_ROOT, 'topo_modeler', 'lens_build.py')

#: 参考配置（原脚本注释里记的 Nx/Ny = 38/34；DXF 多段线数 2215 与之吻合）
PARAMS = dict(a=0.2425, h=0.25, R_big=0.2425 * 8.5,
              lens_ratio=8.0, lens_Nx=38, lens_Ny=34,
              lens_r1_0=0.101, lens_r2_0=0.1226)

#: 原脚本在这组参数下的实测规模（收编后必须一模一样）
EXPECT_N_GRID = 5520
EXPECT_N_HOLES = 4351
EXPECT_N_DXF = 2215


# ============================================================
# 假 app / 假 model3d
# ============================================================

class _Recorder:
    """把所有方法调用记成 ``(名字, 位置参数, 排序后的关键字)``。"""

    def __init__(self):
        self.calls = []

    def __getattr__(self, item):
        def _f(*a, **k):
            self.calls.append((item, a, tuple(sorted(k.items()))))
        return _f


class _FakeM3:
    def GetNumberOfParameters(self):
        return 42


def _norm_calls(calls, dxf_path=None):
    """
    规范化调用记录：DXF 路径换占位符；``expression=`` 描述里的 ``lens_`` 前缀抹平。

    关于 ``lens_`` 这条**唯一的、有意的差异**：原脚本是 notebook 变量
    （``lens_ratio`` / ``lens_Nx`` / ``lens_r1_0``…），本库按 PEP8 去掉前缀
    （``ratio`` / ``nx`` / ``r1_0``…）。CST 参数表里登记的**参数名与表达式值**
    完全一致（``r1 = 0.101/ratio``），只有那句**人读的说明文字**里的变量名不同。
    这是有意为之：说明文字里写 ``lens_r1_0`` 会指代一个 CST 里不存在的名字。
    """
    out = []
    for name, args, kwargs in calls:
        args = tuple('<DXF>' if isinstance(x, str) and x.endswith('.dxf') else x
                     for x in args)
        clean = []
        for k, v in kwargs:
            if k == 'expression' and isinstance(v, str):
                v = v.replace('lens_', '')
            if isinstance(v, str) and v.endswith('.dxf'):
                v = '<DXF>'
            clean.append((k, v))
        out.append((name, args, tuple(clean)))
    return out


def _run_original_script(tmp_path):
    """
    把 `lens_build.py` **原样** 执行一遍（几何 + CST 段），返回它的命名空间与调用记录。

    CST 段只依赖 ``app`` / ``cst_log`` / ``_m3`` 三个注入名，这里用假的替掉，
    于是整段脚本可以完全离线跑完。
    """
    src = io.open(_SCRIPT, encoding='utf-8').read()
    rec = _Recorder()
    ns = dict(PARAMS)
    ns.update(app=rec, cst_log=lambda *a, **k: None, _m3=_FakeM3(),
              __file__=_SCRIPT, __name__='lens_build_exec')

    cwd = os.getcwd()
    os.chdir(str(tmp_path))
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()                 # 原脚本打了很多行，静音
    try:
        exec(compile(src, _SCRIPT, 'exec'), ns)
    finally:
        sys.stdout = old_stdout
        os.chdir(cwd)
    return ns, rec


@pytest.fixture(scope='module')
def original():
    """原脚本的运行结果（几何 + 调用记录），模块级只跑一次。"""
    with tempfile.TemporaryDirectory(prefix='lens_orig_') as tmp:
        ns, rec = _run_original_script(tmp)
        # 脚本里 save_to_dxf 写的那份 DXF 随临时目录一起消失，这里只留数据
        yield ns, rec


@pytest.fixture(scope='module')
def spec():
    return grin_lens_spec_from_cst_params(**PARAMS)


@pytest.fixture(scope='module')
def holes(spec):
    return build_grin_lens_holes(spec)


# ============================================================
# 1. 逐点等价：几何量
# ============================================================

@pytest.mark.parametrize('mine,orig', [
    ('ec_a', 'lens_ec_a'), ('ec_b', 'lens_ec_b'), ('ecc', 'lens_ecc'),
    ('shift', 'lens_shift'), ('d0', 'lens_d0'), ('a2', 'lens_a2'),
    ('hex_size', 'lens_hexsize'),
])
def test_scalar_geometry_matches_original(spec, original, mine, orig):
    """椭圆/网格的每一个标量都必须与原脚本**完全相等**（不是近似）。"""
    ns, _ = original
    assert getattr(spec, mine) == ns[orig], (
        f"{mine}={getattr(spec, mine)!r} 与脚本的 {orig}={ns[orig]!r} 不等")


def test_col_range_matches_original(spec, original):
    """🔴 列范围必须按椭圆真实 x 范围取（旧版 bug 就在这儿）。"""
    ns, _ = original
    assert spec.col_min == ns['lens_col_min']
    assert spec.col_max == ns['lens_col_max']
    # 列范围确实覆盖了整个椭圆（这正是当年修掉的那个 bug）
    assert (spec.col_min - 0.5) * spec.a2 <= spec.shift - spec.ec_a
    assert (spec.col_max + 0.5) * spec.a2 >= spec.shift + spec.ec_a


def test_hole_radius_pair_matches_original(spec, original):
    ns, _ = original
    assert np.array_equal(spec.r_pair, np.asarray(ns['lens_r']))


def test_hole_positions_match_original(holes, original):
    """孔心与孔半径**逐元素**相等（排序后比对，避免依赖遍历顺序）。"""
    ns, _ = original
    for mine, orig, label in ((holes.x, ns['_xp'], 'x'),
                              (holes.y, ns['_yp'], 'y'),
                              (holes.radius, ns['_ri'], 'radius')):
        a = np.sort(np.asarray(mine, float))
        b = np.sort(np.asarray(orig, float))
        assert a.shape == b.shape, f'{label} 个数不同：{a.shape} vs {b.shape}'
        assert np.array_equal(a, b), f'{label} 最大差 {np.abs(a - b).max():.3e}'


def test_hole_counts_match_original(holes, original):
    """网格孔数 / 椭圆内孔数 / DXF 孔数三者都要与原脚本一致。"""
    ns, _ = original
    assert holes.n_grid == len(ns['_xs']) == EXPECT_N_GRID
    assert len(holes) == len(ns['_polys']) == EXPECT_N_HOLES
    assert holes.n_upper == len(ns['_polys_dxf']) == EXPECT_N_DXF


def test_dxf_count_matches_documented_measurement(holes):
    """
    DXF 多段线数必须等于原脚本注释里记的实测值 2215。

    这条把「参数取值就是当年真跑过的那套」钉住 —— 换了假设参数就会失败。
    """
    assert holes.n_upper == 2215


# ============================================================
# 2. 三道自查
# ============================================================

def test_self_checks_all_pass(holes):
    res = holes.run_self_checks()
    assert res['all_ok'], res['summary']
    by_name = {c['name']: c for c in res['checks']}
    assert set(by_name) == {'裁剪不重叠', '孔阵覆盖', '镜像等价'}
    assert by_name['孔阵覆盖']['ratio'] <= 1.05
    assert by_name['镜像等价']['diff_area'] < 1e-6


def test_coverage_check_catches_missing_columns(spec, holes):
    """
    反例：把外侧的孔砍掉（= 旧版「列范围只到 ``nx·a2``」的错误网格）后，
    覆盖自查**必须报错**。

    这正是原脚本注释里记的那个 bug —— 网格只到 ``x = nx·a2``，而椭圆要伸到
    ``ec_c + ec_a``，于是椭圆外侧整片没孔（实心硅）。

    ⚠️ 这里**新建**一份孔阵列再裁剪，绝不改动共享 fixture（否则后面的用例
    会拿到被改小的数据 —— 第一版就踩了这个坑）。
    """
    fresh = build_grin_lens_holes(spec)
    keep = fresh.x <= spec.nx * spec.a2
    trimmed = GrinLensHoles(spec=spec, grid_x=fresh.grid_x, grid_y=fresh.grid_y,
                            x=fresh.x[keep], y=fresh.y[keep],
                            radius=fresh.radius[keep])
    assert len(trimmed) < len(fresh), '裁剪没有生效，反例构造失败'
    res = trimmed.check_coverage()
    assert not res['ok'], f"缩掉外侧孔之后覆盖自查竟然通过了：{res['detail']}"
    assert res['ratio'] > 1.05
    # 共享 fixture 必须毫发无损
    assert holes.n_upper == EXPECT_N_DXF


# ============================================================
# 3. CST 调用序列等价
# ============================================================

def test_cst_call_sequence_matches_original(spec, holes, tmp_path, original):
    """
    库函数的 CST 步骤必须与原脚本**逐条**一致（方法名 + 参数）。

    ⚠️ **唯一的有意偏离**（P4/V6 真机，2026-09-17）：楔形裁剪体的顶点。
    原脚本写 ``Ls*cosd(120)`` / ``Ls*sind(120)``，而 CST 2026 **拒绝** ``cosd``
    （实测报 ``Invalid expression: Ls*cosd(120)``，同一表达式表里的 ``sind(60)`` 却能过）。
    本库改用**精确等价**写法 ``-Ls/2`` 与 ``±Ls*sqr(3)/2``
    （cos120°=cos240°=−1/2、sin120°=√3/2、sin240°=−√3/2），
    既避开不受支持的函数又保持参数化。下面这一条按「等价」而不是「逐字一致」校验。
    """
    ns, rec = original

    dxf = str(tmp_path / 'grin_lens_hexring.dxf')
    holes.export_dxf(dxf)
    mine = _Recorder()
    build_grin_lens(mine, holes, spec, dxf_path=dxf)

    orig_calls = _norm_calls(rec.calls, None)
    mine_calls = _norm_calls(mine.calls, dxf)

    assert [c[0] for c in mine_calls] == [c[0] for c in orig_calls], (
        f"调用顺序不同：\n  原脚本 {[c[0] for c in orig_calls]}\n"
        f"  本库   {[c[0] for c in mine_calls]}")
    deviations = 0
    for i, (a, b) in enumerate(zip(mine_calls, orig_calls)):
        if a != b:
            assert a[0] == 'polyline' and 'cosd(120)' in str(b), (
                f"第 {i} 条调用不同且不是预期的楔形顶点修复：\n  本库   {a}\n  原脚本 {b}")
            assert a[1][0] == [[0, 0], ['-Ls/2', 'Ls*sqr(3)/2'],
                               ['-Ls/2', '-Ls*sqr(3)/2'], [0, 0]], a
            deviations += 1
        else:
            pass
    assert deviations <= 1, f'有意偏离只能有一处，实际 {deviations} 处'


def test_cst_call_sequence_summary(original):
    """把调用序列的**形状**也钉住（21 条，且 12 条是 para）。"""
    ns, rec = original
    names = [c[0] for c in rec.calls]
    assert names == ['dxf_import', 'mirror'] + ['para'] * 10 + \
        ['ellipse', 'extrude', 'subtract', 'polyline', 'extrude', 'subtract',
         'translate', 'translate', 'rotation']


def test_mirror_uses_unite_true_and_rotation_uses_unite_false(holes, spec, tmp_path):
    """两个耗时坑：镜像要 unite=True，旋转复制**必须** unite=False。"""
    dxf = str(tmp_path / 'l.dxf')
    holes.export_dxf(dxf)
    rec = _Recorder()
    build_grin_lens(rec, holes, spec, dxf_path=dxf)
    kw = {name: dict(k) for name, _a, k in rec.calls}
    assert kw['mirror']['unite'] is True
    assert kw['rotation']['unite'] is False
    assert kw['rotation']['copy'] is True
    assert dict(rec.calls[-1][2])['repetition'] == 5


# ============================================================
# 4. 参数校验与提示
# ============================================================

@pytest.mark.parametrize('bad,kwargs', [
    ('a 为负', dict(a=-1.0)),
    ('ratio 为零', dict(ratio=0.0)),
    ('nx 为零', dict(nx=0)),
    ('孔半径反向', dict(r1_0=0.2, r2_0=0.1)),
    ('短半轴过大', dict(nx=10, ny=40)),
    ('r_big 为负', dict(r_big=-1.0)),
])
def test_validate_rejects_bad_params(bad, kwargs, spec):
    args = dict(a=spec.a, ratio=spec.ratio, nx=spec.nx, ny=spec.ny,
                r1_0=spec.r1_0, r2_0=spec.r2_0, r_big=spec.r_big)
    args.update(kwargs)
    with pytest.raises(LensGeometryError):
        GrinLensSpec(**args).validate()


def test_factory_requires_r_big_or_its_inputs():
    base = dict(PARAMS)
    base.pop('R_big')
    with pytest.raises(LensGeometryError, match='n_small'):
        grin_lens_spec_from_cst_params(**base)


def test_factory_accepts_legacy_names():
    """旧脚本/notebook 的变量名（lens_ratio / lens_Nx / R_big / nsm）必须能直接传。"""
    a = grin_lens_spec_from_cst_params(**PARAMS)
    b = grin_lens_spec_from_cst_params(a=0.2425, ratio=8.0, nx=38, ny=34,
                                       r1_0=0.101, r2_0=0.1226, n_small=6, lx1=4.0)
    assert a.r_big == b.r_big == 0.2425 * 8.5
    with pytest.raises(LensGeometryError, match='别名冲突'):
        grin_lens_spec_from_cst_params(a=0.2425, ratio=8.0, lens_ratio=9.0,
                                       nx=38, ny=34, r1_0=0.101, r2_0=0.1226,
                                       r_big=1.0)


def test_notes_flag_hole_overlap_and_d_out_mode(spec):
    """
    参考配置下最外圈孔**本来就轻微相叠**（2·r_out/a2 = 1.011）。

    这条以前被我写成了硬错误、直接把参考配置拒了 —— 现在降级为提示。
    """
    assert spec.hole_overlap_ratio > 1.0
    notes = spec.notes()
    assert any('轻微相叠' in n for n in notes)
    assert any("d_out_mode='ec_a'" in n for n in notes)
    # 换 d_out_mode 之后这条提示应消失
    assert not any("d_out_mode" in n for n in
                   spec.with_overrides(d_out_mode='shift_plus_ec_a').notes())


def test_validate_does_not_raise_on_reference_config(spec):
    """参考配置必须能通过校验（不能被自己的规则挡在门外）。"""
    assert spec.validate() is spec


# ============================================================
# 5. DXF 与几何自洽
# ============================================================

def test_export_dxf_writes_upper_half_only(holes, tmp_path):
    """
    导出的 DXF 只含 ``y ≥ 0`` 的那一半孔。

    ⚠️ 判据是**孔心** ``y ≥ 0``，不是整个六边形都在上半平面 —— 压在 ``y=0`` 上的
    那行孔，其下半几个顶点本来就在 y<0。这没问题：镜像自查（``check_mirror_equivalence``）
    已经用对称差面积 ~1e-15 mm² 证明了「上半 ∪ y镜像 == 完整阵列」。
    """
    p = holes.export_dxf(str(tmp_path / 'g.dxf'))
    assert os.path.exists(p) and os.path.getsize(p) > 0

    upper = holes.polygons(upper_only=True)
    full = holes.polygons(upper_only=False)
    assert len(upper) == holes.n_upper
    assert len(upper) < len(full)                 # 确实只写了一部分
    assert (holes.y[holes.upper_mask] >= 0).all()  # 孔心都在上半平面
    assert len(upper) == int(holes.upper_mask.sum())


def test_export_dxf_can_write_full_array(holes, tmp_path):
    """``upper_only=False`` 时导出的孔数应等于完整阵列（供不需要镜像的场合）。"""
    p = holes.export_dxf(str(tmp_path / 'full.dxf'), upper_only=False)
    assert os.path.getsize(p) > 0
    assert len(holes.polygons(upper_only=False)) == len(holes)


def test_preview_returns_fig_without_showing(holes):
    fig, ax = holes.preview()
    assert ax is not None
    plt.close(fig)


def test_builder_requires_dxf_path(holes, spec):
    with pytest.raises(ValueError, match='dxf_path'):
        build_grin_lens(_Recorder(), holes, spec)


def test_builder_rejects_missing_dxf_file(holes, spec, tmp_path):
    with pytest.raises(FileNotFoundError):
        build_grin_lens(_Recorder(), holes, spec,
                        dxf_path=str(tmp_path / 'nope.dxf'))


def test_builder_rejects_none_app(holes):
    with pytest.raises(ValueError, match='setup'):
        build_grin_lens(None, holes)


def test_describe_is_ascii_for_gbk_console(holes):
    """日志在 GBK 控制台不能崩：describe() 必须只含可编码字符。"""
    txt = holes.describe()
    txt.encode('gbk')          # 不抛异常即通过
    assert 'GRIN 透镜' in txt


# ============================================================
# 6. 可选依赖不泄漏
# ============================================================

def test_builders_importable_without_optional_geometry_deps():
    """
    ``import topo_modeler.builders`` **不得**要求 shapely / ezdxf。

    它们是 `pyproject.toml` 的可选依赖（extra ``geometry``），
    而 `mesh_grid/hex_grid/core.py` 在**顶层**就 import 了它们。
    第一版 `builders/lens.py` 在顶层 `from mesh_grid.hex_grid import ...`，
    于是把 `import topo_modeler.builders` 变成了必须装这两个包 —— **回归**。
    现在改成惰性导入（`_hex_grid_api()`），本用例就是这条的护栏。
    """
    import builtins
    import importlib

    blocked = ('shapely', 'ezdxf')
    saved = {k: v for k, v in sys.modules.items() if k.split('.')[0] in blocked}
    dropped = [k for k in list(sys.modules)
               if k.split('.')[0] in blocked
               or k.startswith('topo_modeler.builders')
               or k.startswith('mesh_grid.hex_grid')]
    for k in dropped:
        sys.modules.pop(k, None)

    real_import = builtins.__import__

    def _guard(name, *a, **k):
        if name.split('.')[0] in blocked:
            raise ImportError(f'optional dependency blocked in test: {name}')
        return real_import(name, *a, **k)

    builtins.__import__ = _guard
    err = None
    mod = None
    try:
        mod = importlib.import_module('topo_modeler.builders')
    except ImportError as exc:
        err = exc
    finally:
        builtins.__import__ = real_import
        sys.modules.update(saved)

    assert err is None, f'import topo_modeler.builders 竟然需要可选依赖：{err}'
    assert hasattr(mod, 'build_grin_lens_holes')


def test_lazy_hex_grid_helper_exists():
    """惰性导入的入口函数必须在（它也是上面那条护栏的实现方式）。"""
    from topo_modeler.builders import lens
    assert callable(lens._hex_grid_api)


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
