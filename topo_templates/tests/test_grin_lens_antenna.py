# -*- coding: utf-8 -*-
r"""
GRINLensAntenna 模板（P5）：离线部分
===================================

计划原文（`docs/next_plan/README.md` P5）：

> `GRINLensAntenna` 模板；复用已有 `GrinLensSpec/build_grin_lens`，**增加现有 DXF 入口**；
> 不要重做孔阵列算法。

本文件守住**不需要 CST 的那一半**：

1. **几何一致**：模板算出的 `GrinLensSpec` 与 V6 真机验收过的那组参数**逐值相同**
   （`ec_a=3.88`、`r_big=2.91`、`ec_c=2.7569…`、`r_in=0.052`、`r_out=0.066`）；
2. **两条入口**：`lens_method='generate'` 能离线算出孔阵列并落 DXF；
   `lens_method='dxf'` 要求给出现成 DXF（缺文件/缺参数都要**明确报错**）；
3. **`Rbig` / `Ls` 必须被登记**：这两个量是 `build_grin_lens()` 的前置条件
   （缺了它们 CST 会弹「输入变量值」模态对话框把脚本挂住，P4/V6 教训）；
4. **天线部分没被改坏**：路径/阵列范围与 `UnitAntenna` 逐值相同；
5. **无 CST 时明确失败**（不是静默跳过）。

⚠️ 需要 CST 的那一半（真正的 VBA 下发）走真机脚本
`scripts/verify_grin_lens_antenna_real.py`（只建模、不求解）。

运行方式::

    pytest topo_templates/tests/test_grin_lens_antenna.py -v
"""

import os
import sys
import warnings

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from topo_templates import GRINLensAntenna, UnitAntenna       # noqa: E402

# V6 真机验收（scripts/verify_grin_multipath.py：nx=16/ny=13/r1_0=0.052/r2_0=0.066/
# n_small=8/lx1=6，a=0.2425）算出来的规格 —— 模板默认值必须给出同一组数
REF_SPEC = {'a2': 0.2425, 'nx': 16, 'ny': 13,
            'ec_a': 3.88, 'ec_c': 2.756938122718753,
            'r_in': 0.052, 'r_out': 0.066, 'r_big': 2.91}
REF_ARM_END = {'AB': (6.0625, +2.94015624584816),
               'BA': (6.0625, -2.94015624584816)}


def _antenna(tmp_path, topology='AB', **kwargs):
    """构造模板（无 CST 环境时 `app` 为 None，但路径/几何照算）。"""
    params = dict(bend_angle=120, straight_length=18, arm_length=14,
                  topology=topology,
                  lens_dxf_out=str(tmp_path / 'lens.dxf'))
    params.update(kwargs)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')              # 「CST 初始化失败」的告警
        return GRINLensAntenna(**params)


class _Recorder:
    """记录 `para` 等调用的假 app。"""

    def __init__(self):
        self.calls = []

    def __getattr__(self, item):
        def _f(*a, **k):
            self.calls.append((item, a, k))
        return _f

    def paras(self, mapping, *_a, **_k):
        for name, value in dict(mapping).items():
            self.calls.append(('para', (name, value), {}))

    def para_names(self):
        return [c[1][0] for c in self.calls if c[0] == 'para']

    def para_kwargs(self, name):
        for op, args, kwargs in self.calls:
            if op == 'para' and args and args[0] == name:
                return kwargs
        return None


# ============================================================
# 1. 几何：与真机验收过的规格逐值相同
# ============================================================

def test_default_lens_spec_matches_the_verified_configuration(tmp_path):
    antenna = _antenna(tmp_path)
    summary = antenna.lens_summary()
    for key, want in REF_SPEC.items():
        if key in ('nx', 'ny'):
            assert summary[key] == want, (key, summary[key], want)
        else:
            assert summary[key] == pytest.approx(want, rel=1e-12), (key, summary[key])


def test_lens_ratio_does_not_change_hole_count(tmp_path):
    """
    **实测钉住的定律（2026-09-17）**：固定 `nx/ny` 时，孔数与 `ratio` **无关**。

    为什么值得钉：库里（`modeler.build_lens` / `config` / `lens_build.py` 注释）
    原先写的是「抬高 ratio（格距 ×k ⇒ 孔数 ÷k²）是唯一提速手段」——**方向反了**。
    实测 ratio 0.5→4（nx/ny 不动）孔数恒为 713：`ec_a = nx·a2` 与格距同比缩放，
    器件物理尺寸跟着变，所以孔数不变。

    **要减少孔数（提速）**：固定物理尺寸时孔数 ∝ ratio² ⇒ 降 ratio 并把 nx/ny
    同比缩小；且 `nx > 12` 是硬约束（`d_out > d0 = 12·a2`）。
    """
    counts = []
    for ratio in (0.5, 1.0, 2.0, 4.0):
        antenna = _antenna(tmp_path, lens_ratio=ratio)
        antenna.make_lens_dxf(str(tmp_path / f'lens_{ratio}.dxf'))
        counts.append(len(antenna.lens_holes))
    assert counts == [713] * 4, counts


def test_hole_count_scales_with_ratio_squared_at_fixed_size(tmp_path):
    """固定**物理尺寸**（nx/ny 随 ratio 同步缩放）时，孔数 ∝ ratio²。"""
    def holes(ratio, nx, ny):
        antenna = _antenna(tmp_path, lens_ratio=ratio, lens_nx=nx, lens_ny=ny)
        antenna.make_lens_dxf(str(tmp_path / f'lens_{ratio}_{nx}.dxf'))
        return len(antenna.lens_holes)

    one = holes(1.0, 16, 13)                  # ec_a = 3.88
    two = holes(2.0, 32, 26)                  # ec_a 也是 3.88
    assert 4 * one - 100 <= two <= 4 * one + 100, (one, two)   # 取整带来的偏差


def test_small_ellipse_is_rejected_by_geometry_constraint(tmp_path):
    """
    `nx ≤ 12` 会被几何约束拒绝（`d_out > d0 = 12·a2`）—— 提速的下限在这。

    ⚠️ 这里**不按类对象判**而是按「消息 + 类名」判：`topo_modeler/tests/test_lens.py`
    会临时把 `topo_modeler*` 从 `sys.modules` 里摘掉再放回（用来验"几何层不导入 CST"），
    于是**全量跑**时本模块持有的是旧类对象、而 `from ... import LensGeometryError`
    拿到的是新类对象 —— 类身份判等会失败。消息与类名是稳定的接口。
    """
    antenna = _antenna(tmp_path, lens_nx=12, lens_ny=10)
    with pytest.raises(Exception, match='渐变区间为空') as excinfo:
        antenna.make_lens_dxf(str(tmp_path / 'too_small.dxf'))
    assert type(excinfo.value).__name__ == 'LensGeometryError', excinfo.value


def test_generate_writes_a_real_dxf(tmp_path):
    antenna = _antenna(tmp_path)
    path = antenna.make_lens_dxf()
    assert os.path.isfile(path) and os.path.getsize(path) > 0
    assert len(antenna.lens_holes) > 0
    # DXF 约定：只写 y≥0 的一半（另一半由 CST 侧镜像补齐）
    assert 0 < antenna.lens_holes.n_upper < len(antenna.lens_holes)


# ============================================================
# 2. 两条入口
# ============================================================

def test_default_method_is_generate(tmp_path):
    antenna = _antenna(tmp_path)
    assert antenna.lens_method == 'generate'
    assert antenna.lens_summary()['method'] == 'generate'


def test_dxf_method_requires_an_existing_file(tmp_path):
    """`lens_method='dxf'` 缺参数 ⇒ ValueError；给了不存在的路径 ⇒ FileNotFoundError。"""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with pytest.raises(ValueError, match='lens_dxf'):
            GRINLensAntenna(lens_method='dxf')
        with pytest.raises(FileNotFoundError, match='DXF 不存在'):
            GRINLensAntenna(lens_method='dxf',
                            lens_dxf=str(tmp_path / 'nope.dxf'))


def test_dxf_method_accepts_an_existing_file(tmp_path):
    """现成 DXF 入口：把 generate 出来的那份当"别人的 DXF"再喂回去。"""
    dxf = _antenna(tmp_path).make_lens_dxf(str(tmp_path / 'shared.dxf'))
    antenna = _antenna(tmp_path, lens_method='dxf', lens_dxf=dxf)
    assert antenna.lens_dxf == dxf
    # 不回头算几何 ⇒ 孔数统计为 None（不猜数字）
    assert antenna.lens_summary()['n_holes'] is None
    assert antenna.lens_holes is None


def test_unknown_method_rejected(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with pytest.raises(ValueError, match='lens_method'):
            GRINLensAntenna(lens_method='magic')


# ============================================================
# 3. `Rbig` / `Ls` 必须被登记（否则真机会弹模态对话框挂住）
# ============================================================

def test_define_all_params_registers_rbig_and_ls(tmp_path):
    antenna = _antenna(tmp_path)
    fake = _Recorder()
    antenna.app = fake
    antenna._define_all_params()                    # 只写参数表，不下发几何

    names = fake.para_names()
    assert 'Rbig' in names and 'Ls' in names
    # 数值口径：Rbig = r_big/a * a（表达式，不写死小数）；Ls = 2.2*Rbig
    rbig_values = [c[1][1] for c in fake.calls
                   if c[0] == 'para' and c[1][0] == 'Rbig']
    assert rbig_values and '*a' in str(rbig_values[0]), rbig_values
    ls_args = [c[1][1] for c in fake.calls if c[0] == 'para' and c[1][0] == 'Ls']
    assert ls_args == ['2.2*Rbig'], ls_args


def test_define_all_params_keeps_the_antenna_params(tmp_path):
    """模板的 `_define_all_params` 是**扩展**天线那套，不能把它顶掉。"""
    antenna = _antenna(tmp_path)
    fake = _Recorder()
    antenna.app = fake
    antenna._define_all_params()
    names = set(fake.para_names())
    assert {'a', 'h', 'l1', 'l2', 'e1', 'e2', 'xup', 'yup', 'ydn',
            'wg_a', 'wg_b', 'wg_t'} <= names


# ============================================================
# 4. 天线部分没被改坏
# ============================================================

@pytest.mark.parametrize('topology', ('AB', 'BA'))
def test_antenna_geometry_is_unchanged(tmp_path, topology):
    antenna = _antenna(tmp_path, topology=topology)
    reference = _reference_antenna(tmp_path, topology)
    assert (antenna.xup, antenna.yup, antenna.ydn) == \
        (reference.xup, reference.yup, reference.ydn)
    assert list(antenna.path.path_lattice) == list(reference.path.path_lattice)
    end_x, end_y = antenna.path.xy[-1]
    ref_x, ref_y = REF_ARM_END[topology]
    assert abs(end_x - ref_x) < 1e-6 and abs(end_y - ref_y) < 1e-6


def _reference_antenna(tmp_path, topology):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return UnitAntenna(bend_angle=120, straight_length=18, arm_length=14,
                           topology=topology)


# ============================================================
# 5. 无 CST 时明确失败
# ============================================================

def test_build_without_cst_raises(tmp_path):
    antenna = _antenna(tmp_path)
    if antenna.app is not None:
        pytest.skip('本机有 CST 环境，跳过"无 CST"分支')
    with pytest.raises(RuntimeError, match='CST'):
        antenna.build_all()


# ============================================================
# 6. `lens_method='insitu'`：就地 hexagon 环透镜（P5，覆盖参考 33 个 notebook）
# ============================================================
#
# 参考：`功分器加天线\1分4\Ant4_1d2d4_2f2s_circle_DF.ipynb`
#   HEX_SIZE=a/sqr(3)/2 ; a2=HEX_SIZE*sqr(3) ; N=(y[1]+2)*2 ; d0=8*HEX_SIZE*2*sqr(3)
#   ⇒ 与我们离线复算的 `grin_ring_holes()` **逐值相同**（下面钉住这几个数）。

def test_insitu_is_a_valid_lens_method():
    from topo_templates.grin_lens_antenna import LENS_METHODS
    assert 'insitu' in LENS_METHODS


def test_insitu_rejects_bad_layers(tmp_path):
    with pytest.raises(ValueError, match='lens_layers'):
        _antenna(tmp_path, lens_method='insitu', lens_layers=0)


def test_insitu_ring_constants_match_reference():
    """环透镜的四个常数与参考 notebook 逐值相同（a=0.2425, N=30）。"""
    from topo_modeler.builders import grin_ring_holes
    ring = grin_ring_holes(0.2425)
    assert ring['hex_size'] == pytest.approx(0.2425 / 3 ** 0.5 / 2)   # 0.0700037…
    assert ring['a2'] == pytest.approx(0.2425 / 2)                   # HEX_SIZE*sqr(3)
    assert ring['n_layers'] == 30                                    # (y[1]+2)*2, y[1]=13
    assert ring['d0'] == pytest.approx(8 * 0.2425)                   # 8*HEX_SIZE*2*sqr(3)
    assert ring['radius_outer'] == pytest.approx(30 * ring['a2'])


def test_insitu_ring_quadrant_only_and_axis_counts():
    """只取第一象限；`x == 0` 上的孔在镜像时会落在自己身上（统计要减掉）。"""
    from topo_modeler.builders import grin_ring_holes
    ring = grin_ring_holes(0.2425)
    holes = ring['holes']
    assert holes, '孔集合不能为空'
    assert all(c['center'][0] >= 0 and c['center'][1] >= 0 for c in holes)
    assert len(holes) == 721                     # 30 层网格的第一象限格点数
    assert sum(1 for c in holes if c['center'][0] == 0) == 16
    assert all(c['distance'] <= ring['radius_outer'] + 1e-9 for c in holes)


def test_insitu_radius_expression_is_two_segment():
    """内圈用常量 `r1`、外圈才是渐变表达式（参考的分段写法）。"""
    from topo_modeler.builders import grin_ring_holes
    ring = grin_ring_holes(0.2425)
    fixed = [c for c in ring['holes'] if c['r1_fixed']]
    graded = [c for c in ring['holes'] if not c['r1_fixed']]
    assert fixed and graded
    assert all(c['radius_expr'] == 'r1' for c in fixed)
    assert all(c['distance'] < ring['d0'] for c in fixed)
    assert all(c['distance'] >= ring['d0'] for c in graded)
    assert all(c['radius_expr'].startswith('r1+(r2-r1)*(') for c in graded)
    assert all(c['radius_expr'].endswith(')/(N*a2-d0)') for c in graded)
    # ⚠️ 表达式里**不含** `HEX_SIZE`/裸数字之外的参数名（只有 r1/r2/d0/N/a2）
    assert all(set(__import__('re').findall(r'[A-Za-z_]\w*', c['radius_expr']))
               <= {'r1', 'r2', 'd0', 'N', 'a2'} for c in graded)


def test_insitu_gradient_is_empty_for_small_layers():
    """渐变区间为空（N*a2 <= d0）时必须明确报错，而不是默默全用 r1。"""
    from topo_modeler.builders import grin_ring_holes
    with pytest.raises(ValueError, match='渐变区间'):
        grin_ring_holes(0.2425, n_layers=4)


def test_insitu_registers_all_expression_params(tmp_path):
    """缺参数 ⇒ CST 弹「请输入变量值」模态框把脚本挂住 ⇒ 六个参数必须先登记。"""
    antenna = _antenna(tmp_path, lens_method='insitu')
    app = _Recorder()
    antenna.app = app
    from topo_modeler.builders import build_grin_lens_insitu
    build_grin_lens_insitu(app, antenna.make_lens_ring(), height='h',
                           component='gridlens')
    names = app.para_names()
    for name in ('HEX_SIZE', 'a2', 'N', 'd0', 'r1', 'r2'):
        assert name in names, f'{name} 未登记'


def test_insitu_build_sequence(tmp_path):
    """下发序列 = 逐个 hexagon → add → mirror → cylinder/square/subtract → 负形 → 放置。"""
    antenna = _antenna(tmp_path, lens_method='insitu')

    class _OpRecorder:
        """只记下发顺序的假 app（魔术方法必须定义在类上，实例赋值不生效）。"""

        def __init__(self):
            self.ops = []

        def __getattr__(self, item):
            def _f(*a, **k):
                self.ops.append(item)
            return _f

    app = _OpRecorder()
    ops = app.ops
    from topo_modeler.builders import build_grin_lens_insitu
    info = build_grin_lens_insitu(app, antenna.make_lens_ring(), name='lens_epc',
                                  height='h', component='gridlens')
    n = len(antenna.make_lens_ring()['holes'])
    assert ops.count('hexagon') == n
    assert ops.count('add') == n - 1
    assert ops[0] == 'para' and ops[1] == 'para'
    assert ops.index('mirror') > ops.index('add')
    for op in ('create_cylinder', 'square', 'subtract', 'translate'):
        assert op in ops
    assert ops.count('subtract') == 2
    assert ops.count('rotation') == 1
    assert info['n_holes'] == n and info['n_lenses'] == 6
    assert info['n_holes_total'] == 2 * n - info['n_holes_on_axis']
    assert info['method'] == 'insitu'
    # 非 DXF 路线：没有 dxf_import，也不落任何 DXF
    assert 'dxf_import' not in ops


def test_insitu_place_false_keeps_one_lens(tmp_path):
    from topo_modeler.builders import build_grin_lens_insitu
    antenna = _antenna(tmp_path, lens_method='insitu')
    app = _Recorder()
    info = build_grin_lens_insitu(app, antenna.make_lens_ring(),
                                  place=False, component='gridlens')
    assert info['placed'] is False and info['n_lenses'] == 1
    assert 'rotation' not in [c[0] for c in app.calls]


def test_insitu_lens_summary_reports_ring(tmp_path):
    """`make_lens_ring()` / `lens_summary()` 离线可算，且**不碰 CST**。"""
    antenna = _antenna(tmp_path, topology='BA', lens_method='insitu')
    ring = antenna.make_lens_ring()
    assert len(ring['holes']) == 721
    summary = antenna.lens_summary()
    assert summary['method'] == 'insitu'
    assert summary['dxf'] is None
    assert summary['layers'] == 30
    assert summary['n_holes'] == 721
    assert summary['hex_size'] == pytest.approx(ring['hex_size'])
    assert summary['radius_outer'] == pytest.approx(ring['radius_outer'])
    # 天线部分没被改动（与 UnitAntenna 逐值相同）
    reference = _reference_antenna(tmp_path, 'BA')
    assert (antenna.xup, antenna.yup, antenna.ydn) == \
        (reference.xup, reference.yup, reference.ydn)


def test_insitu_ring_cache_is_reused(tmp_path):
    antenna = _antenna(tmp_path, lens_method='insitu')
    assert antenna.make_lens_ring() is antenna.make_lens_ring()


def test_insitu_does_not_require_dxf(tmp_path):
    """`insitu` 不落 DXF：即便 lens_dxf 不存在也不报错（只有 'dxf' 路线才检查）。"""
    antenna = _antenna(tmp_path, lens_method='insitu',
                       lens_dxf=str(tmp_path / 'nope.dxf'))
    assert antenna.lens_dxf_out.endswith('.dxf')
    with pytest.raises(FileNotFoundError):
        _antenna(tmp_path, lens_method='dxf', lens_dxf=str(tmp_path / 'nope.dxf'))


def test_insitu_does_not_register_unused_ls(tmp_path):
    """`Ls` 只被 **DXF 路线的楔形裁剪** 用到 —— 就地路线登记它就是死写入。

    真机首跑（`scripts/verify_grin_lens_insitu_real.py`）被
    `verify_model_parameter_usage.py` 抓到 `Ls` 未被引用，据此改成按路线登记。
    """
    antenna = _antenna(tmp_path, lens_method='insitu')
    app = _Recorder()
    antenna.app = app
    antenna._define_all_params()
    names = [c[1][0] for c in app.calls if c[0] == 'para']
    assert 'Rbig' in names, '就地路线也要 Rbig（放置透镜时平移到顶点）'
    assert 'Ls' not in names, f'就地路线不该登记 Ls（用不到）：{names}'


def test_generate_still_registers_ls(tmp_path):
    """DXF 路线必须继续登记 `Ls` —— 楔形裁剪体用到它（缺了会弹模态框挂住）。"""
    antenna = _antenna(tmp_path, lens_method='generate')
    app = _Recorder()
    antenna.app = app
    antenna._define_all_params()
    names = [c[1][0] for c in app.calls if c[0] == 'para']
    assert 'Rbig' in names and 'Ls' in names, names


# ============================================================
# 7. `lens_rotation`（参考的 `dphi`：透镜绕自身近焦点自转）
# ============================================================
#
# 参考：`椭圆透镜单元天线/BA/.../*_rotation.ipynb`
#   app1.para('dphi','10') ; app1.rotation('epc1',['0',0,'dphi'],['px2','py2',0])
# ⇒ `dphi` 是**透镜绕顶点（= 近焦点）自转**，不是"把透镜挪到别的臂"。

def test_lens_rotation_registers_dphi_param(tmp_path):
    antenna = _antenna(tmp_path, topology='BA', lens_rotation=10)
    app = _Recorder()
    antenna.app = app
    antenna._define_all_params()
    names = app.para_names()
    assert 'dphi' in names, names
    assert antenna._dphi_expr() == 'dphi'


def test_lens_rotation_default_is_zero_and_sends_nothing(tmp_path):
    """默认 0 ⇒ 不登记 `dphi`、也不下发自转（保持与旧脚本逐字节一致）。"""
    antenna = _antenna(tmp_path, topology='BA')
    assert antenna.lens_rotation == 0
    assert antenna._dphi_expr() == 0
    app = _Recorder()
    antenna.app = app
    antenna._define_all_params()
    assert 'dphi' not in app.para_names()


def test_self_rotation_step_is_inserted_before_placement(tmp_path):
    """`build_grin_lens(self_rotation='dphi')` 只多一次 `rotation`，且**在平移之前**。

    放在平移之前的理由：椭圆由 `ec_c` 定位 ⇒ 此刻局部原点正是近焦点，
    转的就是透镜自己（参考绕顶点转，而顶点就是近焦点）。
    """
    from topo_modeler.builders import (build_grin_lens, build_grin_lens_holes,
                                       grin_lens_spec_from_cst_params)

    spec = grin_lens_spec_from_cst_params(a=0.2425, ratio=1.0, nx=16, ny=13,
                                          r1_0=0.052, r2_0=0.066,
                                          n_small=8, lx1=6)
    dxf = str(tmp_path / 'lens.dxf')
    build_grin_lens_holes(spec).export_dxf(dxf)

    class _OpRecorder:
        def __init__(self):
            self.ops = []

        def __getattr__(self, item):
            def _f(*a, **k):
                self.ops.append((item, a, k))
            return _f

    app = _OpRecorder()
    app.param_existed = lambda name: True          # 绕过 Rbig/Ls 前置探针
    info = build_grin_lens(app, None, spec, dxf_path=dxf,
                           self_rotation='dphi')
    ops = [c[0] for c in app.ops]
    assert ops.count('rotation') == 2, ops       # 自转一次 + 旋转复制一次
    self_rot = [c for c in app.ops if c[0] == 'rotation'][0]
    assert self_rot[1][1] == [0, 0, 'dphi'], self_rot
    assert self_rot[2].get('copy') is False, self_rot
    # 自转必须在"移到顶点"的 translate 之前
    idx_self = ops.index('rotation')
    idx_move = [i for i, c in enumerate(app.ops)
                if c[0] == 'translate' and c[1][1] == ['Rbig', '0', '0']]
    assert idx_move and idx_self < idx_move[0], (ops, idx_move)
    assert info['self_rotation'] == 'dphi'


def test_self_rotation_default_keeps_single_rotation(tmp_path):
    from topo_modeler.builders import (build_grin_lens, build_grin_lens_holes,
                                       grin_lens_spec_from_cst_params)

    spec = grin_lens_spec_from_cst_params(a=0.2425, ratio=1.0, nx=16, ny=13,
                                          r1_0=0.052, r2_0=0.066,
                                          n_small=8, lx1=6)
    dxf = str(tmp_path / 'lens.dxf')
    build_grin_lens_holes(spec).export_dxf(dxf)

    class _OpRecorder:
        def __init__(self):
            self.ops = []

        def __getattr__(self, item):
            def _f(*a, **k):
                self.ops.append((item, a, k))
            return _f

    app = _OpRecorder()
    app.param_existed = lambda name: True
    info = build_grin_lens(app, None, spec, dxf_path=dxf)
    assert [c[0] for c in app.ops].count('rotation') == 1
    assert info['self_rotation'] == 0
