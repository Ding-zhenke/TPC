# -*- coding: utf-8 -*-
r"""
MZISwitch —— MZI 开关（开关尝试\AB\MZI*，P5 模板）
==================================================

参考与口径
----------
按 4 个 MZI notebook 的**逐 cell 取证**（[复杂器件参考规格](../../docs/guides/complex_device_specs.md)
§4.2）与[设计记录](../../docs/guides/complex_device_templates_design.md)：

* 路径 6 点、方向序列 **0° → +120° → 0° → −120° → 0°**（`parallel` 是 10 点，见 `mzi_type`）；
* **2 个端口**，直接建在探针 `feed1` 的两个端面上（面 `'4'` → 端口 2、面 `'14'` → 端口 1，
  `shield='electric'`）；
* 附加结构：**耦合区/泵浦区矩形**（`ax` = 半宽[单位 a]、`ay` = 上抬[单位 e2]，镜像到另一条臂）
  + **圆柱**（`rc1` 半径，材料 `m1`：`Epsilon 11.9` / `Sigma=sigma1`）；
* 材料：`Copper (annealed)` / `Silicon (lossy)` / 自定义 `m1`；监视器 E 面 `310:2:320` GHz。

⚠️ **`basic` 与 `cascade` 在 CST 侧完全相同**（逐 cell 取证：只有预览用的 matplotlib 函数
与保存文件名不同，其返回值从未进入 CST）⇒ 本模板把两者实现成**同一几何**（`mzi_type`
只作来源标签记录，并写进 `summary()`），**不按"级联段数"造不同几何**。
`parallel`（10 点）与 `anti`（两组 `ax/ay` + 不对称泵浦）有**真实几何差别**，本模板尚未实现
（传入会明确报错，而不是静默当成 basic）。

⚠️ **不与参考 notebook 逐字节相同**（设计记录 §2 的 D1）：参考用闭合区域轮廓画 VPC，
本模板用本库口径（中心线 + `±y_margin` 派生）。验收判据是「端口/参数同类 + 只建模 0 消息」。

@author: PC
"""

import os

import numpy as np

from mesh_grid.tri_grid import TopoPath
from topo_modeler.name_manager import NameManager
from topo_modeler.modeler import TopoModeler
from topo_modeler.builders import (
    DEFAULT_D0_LAYERS,
    DEFAULT_RING_LAYERS,
    GrinLensSpec,
    build_feed,
    build_grin_lens,
    build_grin_lens_from_dxf,
    build_grin_lens_holes,
    build_grin_lens_insitu,
    build_materials,
    configure_solver,
    grin_lens_spec_from_cst_params,
    grin_ring_holes,
)

#: 端口面号（参考 notebook 逐字一致：`feed1` 的两个端面）
FEED_PORT_FACES = {'port1': '14', 'port2': '4'}
#: `m1`（开关材料）的默认电学参数（参考 notebook 逐字一致）
M1_EPSILON = 11.9

#: 已实现的类型（`basic` 与 `cascade` 同一几何；其余是真实几何差别，尚未实现）
SUPPORTED_MZI_TYPES = ('basic', 'cascade')

#: 透镜孔阵列来源（与其他三个模板同名同义）
LENS_METHODS = ('generate', 'dxf', 'insitu')
#: 透镜几何默认值 —— 与 `MultiPortAntenna` 同口径（参考 `para_init(yl=10, ratio=2)`：
#: `nx=int(10*1.15)*2+1=24`、`ny=10*2+1=21`、`r1_0=2*50.5e-3`）。
#: ⚠️ `r1_0` 是"ratio=1 时的孔半径"（本库约定 `r = r1_0/ratio`），所以是 **0.101**。
LENS_DEFAULTS = dict(ratio=2.0, nx=24, ny=21, r1_0=0.101, r2_0=0.1226,
                     n_small=12, lx1=8)


class MZISwitch:
    """
    MZI 开关（单路径中心线 + 耦合区 + 圆柱 + 2 端口）。

    :param arm_x1: int, 入/出直段长度（晶格周期数），参考 x1 = 9
    :param mid_x2: int, 中间直段长度，参考 x2 = 9
    :param arm_gap_y1: int, 两条对角连接段的长度，参考 y1 = 5
    :param topology: str, 'AB' / 'BA'
    :param mzi_type: str, ``'basic'`` / ``'cascade'``（**同一几何**，只作来源标签）；
        其余取值（`parallel` / `anti`）是真实几何差别，本模板未实现 ⇒ 明确报错
    :param pump_ax: float, 耦合区半宽（单位 a），参考 ax = 2
    :param pump_ay: float, 耦合区上抬高度（单位 e2），参考 ay = 1
    :param cylinder_radius: float, 圆柱半径（mm），参考 rc1 = 0.4
    :param sigma1: float, 开关材料电导率（S/m），参考 0（F 组用 200）
    :param monitor_freqs: 序列 可选, 额外监视频点（GHz），默认 310:2:320
    :param lens_method: str 可选, ``None``（不建透镜）/ ``'generate'`` / ``'dxf'`` /
        ``'insitu'``（**不落 DXF**，CST 内逐 `hexagon` 建环 —— 参考
        `开关尝试/AB/MZI-GRIB.ipynb` 就是这么做的）
    :param lens_dxf: str 可选, 现成的孔阵列 DXF（``lens_method='dxf'`` 时必给）
    :param lens_layers: int, ``'insitu'`` 的六边形网格层数（参考 30）
    :param lens_d0_layers: int, ``'insitu'`` 的 `d0` 层数系数（参考 8）
    :param lens_name: str, 透镜实体名
    :param lens_component: str, 透镜组件名
    :param lens_kwargs: dict 可选, 覆盖 :data:`LENS_DEFAULTS`
    """

    #: 透镜孔阵列来源（与 `GRINLensAntenna`/`MultiPortAntenna`/`PowerDivider` 同名同义）
    LENS_METHODS = LENS_METHODS

    def __init__(self, arm_x1=9, mid_x2=9, arm_gap_y1=5, topology='AB',
                 mzi_type='basic', lattice_constant=0.2425, height=0.25,
                 large_hole_ratio=0.65, small_hole_ratio=0.35,
                 pump_ax=2.0, pump_ay=1.0, cylinder_radius=0.4, sigma1=0.0,
                 feed_params=None,
                 wg_a=0.7312, wg_b=0.3756, wg_t=0.2,
                 lens_method=None, lens_dxf=None, lens_dxf_out=None,
                 lens_layers=DEFAULT_RING_LAYERS,
                 lens_d0_layers=DEFAULT_D0_LAYERS,
                 lens_name='lens_epc', lens_component='gridlens',
                 lens_kwargs=None,
                 freq_range=(300, 380), monitors=('E',),
                 monitor_freqs=None, template_cst='tmp.cst', output_path=None):
        if topology not in ('AB', 'BA'):
            raise ValueError(f"topology 必须是 'AB' 或 'BA'，收到 '{topology}'")
        if lens_method is not None and lens_method not in LENS_METHODS:
            raise ValueError(f"lens_method 必须是 None / {' / '.join(LENS_METHODS)}，"
                             f"收到 {lens_method!r}")
        if lens_method == 'dxf' and not lens_dxf:
            raise ValueError("lens_method='dxf' 必须给 lens_dxf（现成孔阵列 DXF 的路径）")
        if lens_method is not None and lens_method != 'dxf' and lens_dxf is not None:
            raise ValueError(
                f"lens_method={lens_method!r} 与 lens_dxf 互斥 —— "
                "'insitu' 就地建环**不落 DXF**；'generate' 会自己算孔阵列并落 DXF。"
                '想用现成 DXF 请用 lens_method="dxf"')
        if lens_method == 'insitu' and int(lens_layers) <= 0:
            raise ValueError(f"lens_method='insitu' 需要 lens_layers >= 1，"
                             f"收到 {lens_layers!r}")
        if lens_dxf is not None and not os.path.isfile(lens_dxf):
            raise FileNotFoundError(f'透镜 DXF 不存在：{lens_dxf}')
        effective_method = lens_method or ('dxf' if lens_dxf else None)
        if mzi_type not in SUPPORTED_MZI_TYPES:
            raise ValueError(
                f"mzi_type={mzi_type!r} 尚未实现：本模板只支持 "
                f"{list(SUPPORTED_MZI_TYPES)}（二者在 CST 侧是**同一几何**，"
                f"逐 cell 取证见 docs/guides/complex_device_specs.md §4.2.1）。"
                f"'parallel'（10 点路径 + 基板无 ymax_dn 分支）与 "
                f"'anti'（两组 ax/ay + 不对称泵浦）是真实几何差别，需要单独实现。")

        self.topology = topology
        self.mzi_type = mzi_type
        self.arm_x1 = int(arm_x1)
        self.mid_x2 = int(mid_x2)
        self.arm_gap_y1 = int(arm_gap_y1)
        self.a = float(lattice_constant)
        self.h = float(height)
        self.l1 = large_hole_ratio * self.a
        self.l2 = small_hole_ratio * self.a
        self.pump_ax = float(pump_ax)
        self.pump_ay = float(pump_ay)
        self.cylinder_radius = float(cylinder_radius)
        self.sigma1 = float(sigma1)
        self.wg_a = wg_a
        self.wg_b = wg_b
        self.wg_t = wg_t
        self.freq_range = freq_range
        self.monitors = monitors
        self.monitor_freqs = tuple(monitor_freqs if monitor_freqs is not None
                                   else np.arange(310, 322, 2))
        self.template_cst = template_cst
        self.output_path = output_path
        self.feed_params = self._check_feed_params(feed_params)
        self.lens_method = effective_method
        self.lens_dxf = lens_dxf
        self.lens_dxf_out = lens_dxf_out or os.path.join(
            os.getcwd(), 'mzi_lens_hexring.dxf')
        self.lens_layers = int(lens_layers)
        self.lens_d0_layers = int(lens_d0_layers)
        self.lens_name = lens_name
        self.lens_component = lens_component
        self.lens_kwargs = dict(LENS_DEFAULTS, **(lens_kwargs or {}))
        self.lens_holes = None
        self.lens_info = None

        self.e1 = self.a / 2
        self.e2 = self.a * np.sqrt(3) / 2

        # ---- 中心线：0° → +120° → 0° → −120° → 0°（参考 notebook 的方向序列）----
        b = (TopoPath.builder(self.a, name='p')
             .start(0, 0).move(self.arm_x1, 'c')
             .turn(120).move(self.arm_gap_y1, 'along')
             .turn(-120).move(self.mid_x2, 'along')
             .turn(-120).move(self.arm_gap_y1, 'along')
             .turn(120).move(self.arm_x1, 'along'))
        self.path = b.build()

        # 阵列范围（**纯计算**，构造期就算好 ⇒ 离线摘要/端口规格也能用）
        # ⚠️ 不能用 `path.get_array_range()`：单边偏置路径会给 `ydn=1`
        #    ⇒ 晶体复制次数 `int(ydn/2)=0` ⇒ CST 报 `Invalid number of repetitions`
        #    （P4/V1 与 P5 MZI 各踩过一次）。参考 notebook 的权威公式：
        #      xup = x1*2 + x2 - int(y1) + 1 ；yup = ydn = y1 + y2（对称）
        self.xup = int(self.arm_x1 * 2 + self.mid_x2 - self.arm_gap_y1 + 1)
        rows = [r for r, _c in self.path.path_lattice]
        self.yup = self.ydn = max(int(self.arm_gap_y1 * 2),
                                  abs(min(rows)) + abs(max(rows)))
        assert self.yup >= 2 and self.ydn >= 2, (self.yup, self.ydn)

        self.modeler = TopoModeler(template_cst=template_cst)
        self.modeler.set_path(self.path)
        self.modeler.set_parameters({
            'a': self.a, 'h': self.h, 'l1': self.l1, 'l2': self.l2,
            'e1': self.e1, 'e2': self.e2,
        })
        self.app = self.modeler.app
        self.nm = NameManager()
        self._built = False
        self._parts = {}

    # ---- 校验 ----

    #: `feed_params` 允许覆盖的参数名（本器件用 AB 族探针）
    _FEED_PARAM_NAMES = {
        'ab_elliptical': ('x0', 'wf1', 'lf1', 'lf2', 'lf3'),
    }

    def _check_feed_params(self, feed_params):
        params = dict(feed_params or {})
        if not params:
            return params
        allowed = set(self._FEED_PARAM_NAMES['ab_elliptical'])
        unknown = sorted(set(params) - allowed)
        if unknown:
            raise ValueError(
                f'feed_params 里有未知参数名 {unknown}；可覆盖：{sorted(allowed)}')
        return params

    # ---- CST 参数 ----

    def _define_all_params(self):
        """登记基础/路径/阵列/AB 族馈源/波导/开关材料相关参数。"""
        app = self.app
        app.para('a', self.a)
        app.para('h', self.h)
        app.para('l1', self.l1)
        app.para('l2', self.l2)
        app.para('e1', self.e1)
        app.para('e2', self.e2)

        self.path.auto_define_cst_params(app, prefix='p')

        xup, yup, ydn = self.path.get_array_range()
        # 阵列范围已在构造期按参考公式算好（见 `__init__`），这里只做登记；
        # 下面这行保留为**对照**：`get_array_range()` 只按路径推，对 MZI 不可用。
        _ = (xup, yup, ydn)
        app.para('xup', self.xup)
        app.para('yup', self.yup)
        app.para('ydn', self.ydn)

        fp = self.feed_params
        app.para('x0', fp.get('x0', 4))
        app.para('wf1', fp.get('wf1', 0.2))
        app.para('lf1', fp.get('lf1', 0.2))
        app.para('lf2', fp.get('lf2', 3.0))
        app.para('lf3', fp.get('lf3', 0.2))

        app.para('wg_a', self.wg_a)
        app.para('wg_b', self.wg_b)
        app.para('wg_t', self.wg_t)

        # 耦合区/泵浦区尺寸 + 开关材料参数（参考 notebook 的 ax/ay/rc1/sigma1）
        app.para('ax', self.pump_ax, expression='耦合区半宽（单位 a）')
        app.para('ay', self.pump_ay, expression='耦合区上抬高度（单位 e2）')
        app.para('rc1', self.cylinder_radius, expression='开关圆柱半径 [mm]')
        app.para('sigma1', self.sigma1, expression='开关材料电导率 [S/m]')

        # 透镜：椭圆路线要 `Ls`（楔形裁剪体边长）。本模板按参考口径把透镜放在**原点**
        # （`place=False`）⇒ **不需要** `Rbig`，登记它就是死写入；`Ls` 用等价表达式写。
        if self.has_lens and self.lens_method != 'insitu':
            spec = self.make_lens_spec()
            app.para('Ls', f'{2.2 * spec.r_big / self.a:g}*a',
                     expression='楔形裁剪体边长（约定 = 2.2·Rbig）')

    # ---- 透镜（可选；三条路线，离线几何可算）----

    @property
    def has_lens(self):
        """是否要建透镜（`lens_method` 为 `None` 时不建）。"""
        return self.lens_method is not None

    def make_lens_spec(self) -> GrinLensSpec:
        """透镜几何规格（离线可算；默认值与 `MultiPortAntenna` 同口径）。"""
        return grin_lens_spec_from_cst_params(a=self.a, **self.lens_kwargs)

    def make_lens_dxf(self, path=None) -> str:
        """``lens_method='generate'`` 的孔阵列 DXF（**离线**）。"""
        target = path or self.lens_dxf_out
        holes = build_grin_lens_holes(self.make_lens_spec())
        holes.export_dxf(target)
        self.lens_dxf_generated = target
        return target

    def make_lens_ring(self) -> dict:
        """``lens_method='insitu'`` 的环透镜孔集合（**纯几何，不需要 CST**）。

        参考 `开关尝试/AB/MZI-GRIB.ipynb` 就是用这套「GRIB 环」做法
        （`HEX_SIZE=a/sqr(3)/2`、`N=(y[1]+2)*2`、`r=[50.5,61.3]/1e3`）。
        """
        if self.lens_holes is None:
            self.lens_holes = grin_ring_holes(
                self.a, n_layers=self.lens_layers,
                r1_0=self.lens_kwargs.get('r1_0', 0.0505),
                r2_0=self.lens_kwargs.get('r2_0', 0.0613),
                d0_layers=self.lens_d0_layers)
        return self.lens_holes

    def lens_summary(self) -> dict:
        """透镜摘要（离线可算；没透镜时 ``{'method': None}``）。"""
        if not self.has_lens:
            return {'method': None}
        summary = {'method': self.lens_method, 'name': self.lens_name,
                   'component': self.lens_component, 'placed': False}
        if self.lens_method == 'insitu':
            ring = self.make_lens_ring()
            summary.update({'dxf': None, 'layers': ring['n_layers'],
                            'hex_size': ring['hex_size'], 'ring_a2': ring['a2'],
                            'ring_d0': ring['d0'],
                            'radius_outer': ring['radius_outer'],
                            'n_holes': len(ring['holes'])})
        else:
            spec = self.make_lens_spec()
            summary.update({'dxf': self.lens_dxf or self.lens_dxf_out,
                            'ec_a': spec.ec_a, 'ec_b': spec.ec_b,
                            'ec_c': spec.shift, 'r_big': spec.r_big,
                            'nx': spec.nx, 'ny': spec.ny, 'ratio': spec.ratio,
                            'n_holes': None})
        return summary

    def build_lens(self):
        """建透镜（三条路线；口径 = **单枚、近焦点在原点**，同参考 `MZI-GRIB`）。

        ⚠️ `place=False` ⇒ 不登记 `Rbig`（那个参数只服务于"移到顶点 + 6 份复制"）。
        """
        if self.lens_method == 'insitu':
            info = build_grin_lens_insitu(
                self.app, self.make_lens_ring(), name=self.lens_name,
                height='h', material='Silicon (lossy)',
                component=self.lens_component, place=False)
        else:
            dxf = self.lens_dxf
            if self.lens_method == 'generate':
                dxf = self.make_lens_dxf()
            info = build_grin_lens_from_dxf(
                app=self.app, dxf_path=dxf, spec=self.make_lens_spec(),
                name=self.lens_name, component=self.lens_component,
                place=False)
        self.lens_info = info
        return info

    # ---- 端口规格（离线可核对；真机建端口时按同一份规格下发）----

    def port_specs(self):
        """两个端口的规格（**Free 模式**：给坐标范围，不用面号）。

        为什么不用参考的面号 `'14'`/`'4'`：真机实测（2026-09-17）在**我们的构序**下
        `pick_face('feed1','14')` 选中 **0 个面**（面号与实体几何/生成顺序强相关），
        被 `add_waveguide_port` 的校验挡下 ⇒ 改用 `create_waveguide_port_free()`。

        :return: list[dict], 每项 ``{'port': 编号, 'x': x 端面表达式, 'face': 'Free'}``
        """
        mid_expr = f'{self.arm_x1*2 + self.mid_x2 - 2*self.arm_gap_y1}*a/2'
        reach = 'lf1+lf2+lf3'
        return [{'port': 1, 'x': f'-({reach})', 'face': 'Free'},
                {'port': 2, 'x': f'2*({mid_expr})+({reach})', 'face': 'Free'}]

    def _port_ranges(self):
        """端口矩形在截面上的范围（y 跨整个阵列、z 跨片厚）。"""
        half_width = f'{self.yup}*e2'
        return {'yrange': (f'-{half_width}', half_width),
                'zrange': ('-h/2', 'h/2')}

    # ---- 建模 ----

    def build_all(self):
        """端到端建模：材料 → 基板/VPC → 晶体 → 裁剪 → 探针（镜像）→ 耦合区/圆柱 → 2 端口。"""
        if self.app is None:
            raise RuntimeError('CST 初始化失败，无法建模。')
        app = self.app
        self._define_all_params()
        build_materials(app)
        app.create_material_custom('m1', M1_EPSILON, 1, f'sigma1')

        y_margin = f'{self.width_rows()}*e2'
        vpca, vpcb = self.modeler.build_vpc_regions(y_margin=y_margin)
        # 阵列次数必须走**参数引用**（`xup/yup/ydn` 已按参考公式登记）：
        # 不传会回退到 `path.get_array_range()`，而 MZI 这种单边偏置路径会给
        # `ydn=1` ⇒ `int(ydn/2)=0` ⇒ CST 报 `Invalid number of repetitions`
        # （真机实测踩过一次；已给 `TopoModeler.build_crystal` 补上 kwargs 透传）。
        crystals = self.modeler.build_crystal(topology=self.topology,
                                              xup='xup', yup='yup', ydn='ydn')
        clip = self.modeler.clip_crystals_with_vpc()

        # 探针（AB 族）+ 关于 x 中点镜像 ⇒ 两个端口臂
        feed_name = build_feed(app, feed_type='ab_elliptical', name='feed1')
        mid = f'({self.arm_x1*2 + self.mid_x2 - 2*self.arm_gap_y1})/2*a'
        app.mirror(feed_name, [mid, 0, 0], [1, 0, 0], copy=True, unite=True)

        # 耦合区/泵浦区：以中间直段的中点为心的矩形 + 镜像到另一条臂
        center_x = f'(p3x+p4x)/2'
        center_y = 'p3y'
        app.square(f'{center_x}-ax*a', f'{center_x}+ax*a',
                   f'{center_y}-ay*e2', f'{center_y}+ay*e2',
                   '-h/2', 'h/2', name='pump1',
                   material='Silicon (lossy)')
        app.mirror('pump1', [0, 0, 0], [0, 1, 0], copy=True, unite=True)
        app.add(vpca, 'pump1')

        # 开关圆柱（材料 m1）⇒ 与 **VPC 区域副本**求交后 insert 回原区域
        #
        # ⚠️ 真机实测（2026-09-17）：CST 的 `Intersect` **结果留在第一个操作数**，
        #    第二个被**消耗**。若写成 `intersect('pump2', vpc_A)`，`vpc_A` 就没了，
        #    下一步 `insert(vpc_A, 'pump2')` 直接报 `Shape does not exist: vpc_A`。
        #    参考 notebook 的做法正是先 `translate(vpca, copy=True)` 拿到副本
        #    （`vpca_1`），拿副本去求交，再 insert 回 `vpca` —— 这里照做。
        app.create_cylinder(center=[center_x, f'{center_y}+e2/2', '-h/2'],
                            r=['rc1', 0], h=['0', 'h'],
                            name='pump2', axis='z', material='m1')
        app.translate(vpca, ['0', '0', '0'], copy=True, unite=False, log_flag=1)
        app.intersect('pump2', f'{vpca}_1')
        app.insert(vpca, 'pump2')

        # 端口：**用坐标范围建（Free 模式），不用面号**
        #
        # ⚠️ 真机实测（2026-09-17）：参考 notebook 用的是 `pick_face('feed1','4'/'14')`，
        #    但**面号与实体几何/生成顺序强相关**（仓库 `picks.py` 自己的说明）——
        #    我们的构序与参考不同，`pick_face('feed1','14')` 实测**选中 0 个面**，
        #    被 `add_waveguide_port` 的校验挡下。
        #    ⇒ 改用 `create_waveguide_port_free()`：给出端口矩形在**截面上的范围**，
        #      不产生拾取动作，几何微调也不会指错面。
        #    端口面取器件两端的**图形化硅截面**（y 跨整个阵列、z 跨片厚），
        #    参考是把端口建在探针端面上（口径不同，属设计记录 D1 的口径差异）。
        mid_expr = f'{self.arm_x1*2 + self.mid_x2 - 2*self.arm_gap_y1}*a/2'
        ranges = self._port_ranges()
        ports = []
        for spec in self.port_specs():
            app.create_waveguide_port_free(
                spec['port'], xrange=(spec['x'], spec['x']),
                yrange=ranges['yrange'], zrange=ranges['zrange'],
                shield='electric')
            ports.append(spec)

        app.add(vpca, feed_name)
        app.add(vpca, vpcb)

        # 可选透镜（参考口径：**单枚、近焦点在原点** —— `place=False`）
        lens = None
        if self.has_lens:
            lens = self.build_lens()

        configure_solver(app, freq_range=self.freq_range, monitors=self.monitors)
        app.define_monitor('E', list(self.monitor_freqs))

        self._parts = {'vpca': vpca, 'vpcb': vpcb, 'crystals': crystals,
                       'clip': clip, 'feed': feed_name, 'pump1': 'pump1',
                       'pump2': 'pump2', 'ports': ports, 'material': 'm1',
                       'lens': lens}
        self._built = True
        return self

    def width_rows(self):
        """VPC 区域半宽要覆盖的行数 —— 用**阵列范围**（对称的 `yup`），不是路径行范围。

        路径是单边偏置的（行 0…5），拿它当半宽会让下半区只剩 1 行。
        """
        if getattr(self, 'yup', None):
            return int(self.yup)
        rows = [r for r, _c in self.path.path_lattice]
        return max(abs(min(rows)), abs(max(rows))) + 1

    # ---- 保存 / 验收 / 关闭 ----

    def save(self, output_path=None):
        path = output_path or self.output_path
        if path is None:
            raise ValueError('请指定 output_path')
        if not self._built:
            self.build_all()
        self.app.cst_file.save(path, include_results=False, allow_overwrite=True)
        print(f'已保存: {path}')
        return path

    def validate(self):
        if not self._built:
            self.build_all()
        return self.app.validate_model()

    def close(self):
        self.modeler.close()
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.close()
        except Exception:
            if exc_type is None:
                raise
        return False

    def summary(self):
        """离线摘要（不碰 CST）。"""
        return {'mzi_type': self.mzi_type,
                'note': 'basic 与 cascade 在 CST 侧是同一几何（逐 cell 取证）',
                'topology': self.topology,
                'lattice': [[int(r), int(c)] for r, c in self.path.path_lattice],
                'array_range': [self.xup, self.yup, self.ydn],
                'path_get_array_range': [int(v) for v in
                                         self.path.get_array_range()],
                'ports': self.port_specs(),
                'pump': {'ax': self.pump_ax, 'ay': self.pump_ay},
                'cylinder_radius': self.cylinder_radius,
                'sigma1': self.sigma1,
                'monitor_freqs': [float(v) for v in self.monitor_freqs],
                'port_faces': dict(FEED_PORT_FACES),
                'has_lens': self.has_lens,
                'lens_method': self.lens_method,
                'lens': self.lens_summary()}

    def __repr__(self):
        return (f"MZISwitch(mzi_type='{self.mzi_type}', topology='{self.topology}', "
                f"x1={self.arm_x1}, x2={self.mid_x2}, y1={self.arm_gap_y1})")
