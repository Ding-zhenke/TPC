# -*- coding: utf-8 -*-
r"""
MultiPortAntenna —— 多端口天线（α1 族：双馈源 + 两条铜波导 ⇒ 3 端口）
=====================================================================

参考与口径
----------
按 19 个参考 notebook 的逐 cell 取证（[复杂器件参考规格](../../docs/guides/complex_device_specs.md)
§4.5）与[设计记录](../../docs/guides/complex_device_templates_design.md)：

* α1 族 = `多端口\Ant3_1W2N\Ant3_{240D3, BA_240D}_epc` + `MPMBA\Ant3_{epc, epc2}`（4 个，命令序列同构）；
* **1 分 2**（主干 + 两条分支）；**双馈源**：AB 型椭圆探针 `feed1` + BA 型渐变探针 `feed2`；
  **两条铜波导**（AB 范围 `[-lf1-lf2-lf3, -lf1]` 与 BA 范围 `[-lf5-lf6-lf4, -lf4]`）⇒ **3 个端口**；
* 端口编号在参考 notebook 之间**有对调** ⇒ 由构造参数给（默认按 B/K 的 `wg2→1, wg1→2, wg1→3`）；
* 可选**透镜**（2026-09-18 补）：参考里 6 个多端口 notebook 用
  `dxf_import(..., component='gridlens')` 导入椭圆相位透镜（`ec_a/ec_b/ec_c` +
  `ratio=2` / `Nx=int(yl*1.15)*ratio+1` / `Ny=yl*ratio+1` 的 `para_init` 家族）。
  ⚠️ **参考把透镜放在原点**（`ellipse(..., [0,0])` → `translate(['ec_c','0','0'])` → 剪孔），
  **没有** `Rbig` 平移、也**没有** 6 份旋转复制 ⇒ 本模板用
  `build_grin_lens(..., place=False)` 复刻这个口径（单枚、近焦点在原点）。
  三条路线与 `GRINLensAntenna` / `PowerDivider` **同名同义**：
  `generate`（现算 + 落 DXF）/ `dxf`（现成 DXF）/ `insitu`（**不落 DXF**，CST 内逐 `hexagon` 建环）。

⚠️ **本模板不与参考 notebook 逐字节相同**（设计记录 §2 的 D1）：
参考用**闭合区域轮廓**画 VPC，本模板用本库口径 —— 多条 `TopoPath` 中心线 +
`±y_margin` 派生区域 + 多路径布尔并（P5-79 的能力）。因此验收判据是
「端口/参数同类 + **只建模 0 条 CST 消息**」，**不是**几何等价。

⚠️ **耗时**：晶体阵列按**并集范围**建，三条分支各一套 A/B 晶体。要真机快速验证请把
`straight_length / arm_length` 调小（阵列次数随之变小）。

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
    add_multiport_port_set,
    build_feed,
    build_grin_lens,
    build_grin_lens_from_dxf,
    build_grin_lens_holes,
    build_grin_lens_insitu,
    build_materials,
    build_multiport_waveguide,
    build_substrate_multi,
    build_waveguide,
    configure_solver,
    grin_lens_spec_from_cst_params,
    grin_ring_holes,
    register_multiport_params,
)

import numpy as np                                        # noqa: E402

#: 参考里最常见的端口组（B/K 家族：BA 侧 wg2 → 1，AB 侧 wg1 → 2 / 3）
DEFAULT_PORT_NUMBERS = (1, 2, 3)
#: 端口面号：`'10'` 是轴向口径端面（12/12 参考一致）
AXIAL_FACE = '10'
SIDE_FACE = '22'
#: 透镜孔阵列来源（与 `GRINLensAntenna` / `PowerDivider` 同名同义）
LENS_METHODS = ('generate', 'dxf', 'insitu')
#: 透镜几何默认值 —— **来自参考**（`MPMBA/Ant3_*` 的 `para_init(yl=10, ratio=2)`：
#: `Nx=int(yl*1.15)*ratio+1=24`、`Ny=yl*ratio+1=21`、
#: `r=[50.5,61.3]/1e3/ratio*2` ⇒ **等效半径 0.0505 / 0.0613**）。
#: ⚠️ 本库 `GrinLensSpec` 的约定是 ``r = r1_0 / ratio``，而参考是
#: ``r = 2*r_raw / ratio`` ⇒ 要给出**同样的等效半径**，`r1_0` 必须写成 `2*50.5e-3 = 0.101`
#: （`0.0505` 会小一倍 —— 这是个容易按"看着像"就抄错的数）。
LENS_DEFAULTS = dict(ratio=2.0, nx=24, ny=21, r1_0=0.101, r2_0=0.1226,
                     n_small=12, lx1=8)


class MultiPortAntenna:
    """
    多端口天线（1 分 2 + 双馈源 + 3 端口）。

    :param straight_length: int, 主干长度（晶格周期数）
    :param arm_length: int, 两条分支的长度（晶格周期数）
    :param topology: str, 'AB' / 'BA'（决定大/小三角形的 A/B 归属）
    :param feed1: str, AB 侧探针类型（默认 'ab_elliptical'）
    :param feed2: str, BA 侧探针类型（默认 'ba_tapered'）
    :param port_numbers: tuple, ``(ba_side, ab_axial, ab_side)`` 三个端口的编号
    :param feed_params: dict 可选, 馈源族参数覆盖（两组族的键都接受，见 `_check_feed_params`）
    :param lens_method: str 可选, ``None``（不建透镜）/ ``'generate'``（现算孔阵列 →
        落 DXF → 建）/ ``'dxf'``（用现成 DXF）/ ``'insitu'``（**不落 DXF**，CST 内
        逐个 `hexagon` 建环）。默认 ``None``：给了 `lens_dxf` 就等价于 ``'dxf'``
    :param lens_dxf: str 可选, 现成的孔阵列 DXF（``lens_method='dxf'`` 时必给）
    :param lens_dxf_out: str 可选, ``'generate'`` 时导出的 DXF 路径
    :param lens_layers: int, ``'insitu'`` 的六边形网格层数（参考 `MZI-GRIB` 族为 30）
    :param lens_d0_layers: int, ``'insitu'`` 的 `d0` 层数系数（参考 8）
    :param lens_name: str, 透镜实体名
    :param lens_component: str, 透镜组件名（DXF 路线上也是层名）
    :param lens_kwargs: dict 可选, 覆盖 :data:`LENS_DEFAULTS`（``ratio/nx/ny/r1_0/r2_0/n_small/lx1``）
    :param template_cst: str, CST 模板
    :param output_path: str, 输出 .cst
    """

    #: `feed_params` 允许覆盖的参数名（两个族都接受 —— 本器件两个族都用）
    _FEED_PARAM_NAMES = {
        'ab_elliptical': ('x0', 'wf1', 'lf1', 'lf2', 'lf3'),
        'ba_tapered': ('x01', 'wf2', 'lf4', 'lf5', 'lf6'),
    }

    #: 透镜孔阵列来源（与 :data:`LENS_METHODS` 同值；挂成类属性便于自省与护栏校验）
    LENS_METHODS = LENS_METHODS

    def __init__(self, straight_length=18, arm_length=9, topology='AB',
                 lattice_constant=0.2425, height=0.25,
                 large_hole_ratio=0.65, small_hole_ratio=0.35,
                 feed1='ab_elliptical', feed2='ba_tapered',
                 port_numbers=DEFAULT_PORT_NUMBERS,
                 wg_a=0.7312, wg_b=0.3756, wg_t=0.2,
                 lens_method=None, lens_dxf=None, lens_dxf_out=None,
                 lens_layers=DEFAULT_RING_LAYERS,
                 lens_d0_layers=DEFAULT_D0_LAYERS,
                 lens_name='lens_epc', lens_component='gridlens',
                 lens_kwargs=None,
                 freq_range=(290, 380), monitors=('E', 'Farfield'),
                 template_cst='tmp.cst', output_path=None,
                 feed_params=None):
        if topology not in ('AB', 'BA'):
            raise ValueError(f"topology 必须是 'AB' 或 'BA'，收到 '{topology}'")
        if len(tuple(port_numbers)) != 3:
            raise ValueError(f'port_numbers 必须是 3 个端口编号，收到 {port_numbers!r}')
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

        self.topology = topology
        self.straight_length = int(straight_length)
        self.arm_length = int(arm_length)
        self.a = float(lattice_constant)
        self.h = float(height)
        self.l1 = large_hole_ratio * self.a
        self.l2 = small_hole_ratio * self.a
        self.feed1 = feed1
        self.feed2 = feed2
        self.port_numbers = tuple(int(n) for n in port_numbers)
        self.wg_a = wg_a
        self.wg_b = wg_b
        self.wg_t = wg_t
        self.freq_range = freq_range
        self.monitors = monitors
        self.template_cst = template_cst
        self.output_path = output_path
        self.feed_params = self._check_feed_params(feed_params)
        self.lens_method = effective_method
        self.lens_dxf = lens_dxf
        self.lens_dxf_out = lens_dxf_out or os.path.join(
            os.getcwd(), 'multiport_lens_hexring.dxf')
        self.lens_layers = int(lens_layers)
        self.lens_d0_layers = int(lens_d0_layers)
        self.lens_name = lens_name
        self.lens_component = lens_component
        self.lens_kwargs = dict(LENS_DEFAULTS, **(lens_kwargs or {}))
        self.lens_holes = None       # 'insitu' 的孔集合（离线算）
        self.lens_dxf_generated = None
        self.lens_info = None        # `build_lens()` 的返回

        self.e1 = self.a / 2
        self.e2 = self.a * np.sqrt(3) / 2

        # ---- 三条中心线：主干 + 两条分支（1分2 ⇒ 共 3 条路径）----
        #
        # 分支角度用 ±60°：与 `UnitAntenna` 已真机验证过的臂方向口径一致
        # （`turn(±bend_angle/2)`，bend_angle=120 ⇒ ±60°）。
        # ⚠️ 这里**不乘拓扑符号**：`arm_up` / `arm_dn` 是按**物理**上下命名的，
        #    与 AB/BA 无关（拓扑只决定大/小三角形归属，由晶体构建器处理）。
        #    对称结构的正负号若跟着拓扑翻，命名会与物理方向相反（踩过一次）。
        main = (TopoPath.builder(self.a, name='main')
                .start(0, 0).move(self.straight_length, 'c').build())
        arm_up = (TopoPath.builder(self.a, name='arm_up')
                  .start(0, 0).move(self.straight_length, 'c')
                  .turn(+60).move(self.arm_length, 'along').build())
        arm_dn = (TopoPath.builder(self.a, name='arm_dn')
                  .start(0, 0).move(self.straight_length, 'c')
                  .turn(-60).move(self.arm_length, 'along').build())
        self.paths = {'main': main, 'arm_up': arm_up, 'arm_dn': arm_dn}
        #: 向后兼容：`path` 指向主干
        self.path = main

        self.modeler = TopoModeler(template_cst=template_cst)
        self.modeler.set_paths(self.paths)
        self.modeler.set_parameters({
            'a': self.a, 'h': self.h, 'l1': self.l1, 'l2': self.l2,
            'e1': self.e1, 'e2': self.e2,
        })
        self.app = self.modeler.app
        self.nm = NameManager()
        self._built = False
        self._parts = {}

    # ---- 参数校验 ----

    def _arm_end_expr(self, path_name='arm_up'):
        """分支末点的 **y 坐标 CST 参数名**（如 `p13y`）—— 用来把 `wg1` 平移到分支高度。

        `TopoPath.auto_define_cst_params(prefix='p<i>')` 生成的是
        ``p<i>{点序号}{x|y}``（点序号从 1 起，见 `docs/packages/mesh_grid.md`）。
        """
        names = list(self.paths)
        index = names.index(path_name)
        points = len(self.paths[path_name].path_lattice)
        return f'p{index}{points}y'

    def _check_feed_params(self, feed_params):
        """校验 `feed_params` 键名（两个族的键都接受）；写错必须报错。"""
        params = dict(feed_params or {})
        if not params:
            return params
        allowed = set()
        for names in self._FEED_PARAM_NAMES.values():
            allowed |= set(names)
        unknown = sorted(set(params) - allowed)
        if unknown:
            raise ValueError(
                f'feed_params 里有未知参数名 {unknown}；可覆盖：{sorted(allowed)}')
        return params

    # ---- 透镜（可选；三条路线，离线几何可算）----

    @property
    def has_lens(self):
        """是否要建透镜（`lens_method` 为 `None` 时不建）。"""
        return self.lens_method is not None

    def make_lens_spec(self) -> GrinLensSpec:
        """透镜几何规格（离线可算）。默认值来自参考 `MPMBA/Ant3_*` 的 `para_init`。"""
        return grin_lens_spec_from_cst_params(a=self.a, **self.lens_kwargs)

    def make_lens_dxf(self, path=None) -> str:
        """``lens_method='generate'`` 的孔阵列 DXF（**离线**）。"""
        target = path or self.lens_dxf_out
        holes = build_grin_lens_holes(self.make_lens_spec())
        holes.export_dxf(target)
        self.lens_dxf_generated = target
        return target

    def make_lens_ring(self) -> dict:
        """``lens_method='insitu'`` 的环透镜孔集合（**纯几何，不需要 CST**）。"""
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

    # ---- CST 参数 ----

    def _define_all_params(self):
        """登记基础/路径/阵列/两个馈源族/波导参数。"""
        app = self.app
        app.para('a', self.a)
        app.para('h', self.h)
        app.para('l1', self.l1)
        app.para('l2', self.l2)
        app.para('e1', self.e1)
        app.para('e2', self.e2)

        # 每条路径用**自己的**参数前缀（p0/p1/p2…），否则互相覆盖
        for index, path in enumerate(self.paths.values()):
            path.auto_define_cst_params(app, prefix=f'p{index}')

        # 阵列范围：按**所有路径的并集**（ARCHITECTURE §6 硬约定 3）
        xup, yup, ydn = self.modeler.array_range()
        self.xup, self.yup, self.ydn = int(xup), int(yup), int(ydn)
        app.para('xup', self.xup)
        app.para('yup', self.yup)
        app.para('ydn', self.ydn)

        # 两个馈源族：AB 族（feed1）+ BA 族（feed2，含波导范围引用的 lf6）
        fp = self.feed_params
        app.para('x0', fp.get('x0', 4))
        app.para('wf1', fp.get('wf1', 0.2))
        app.para('lf1', fp.get('lf1', 0.2))
        app.para('lf2', fp.get('lf2', 3.0))
        app.para('lf3', fp.get('lf3', 0.2))
        from topo_modeler.builders import register_multiport_params
        register_multiport_params(
            app, wf2=fp.get('wf2', 0.2), lf4=fp.get('lf4', 0.2),
            lf5=fp.get('lf5', 3.0), lf6=fp.get('lf6', 0.2))
        app.para('x01', fp.get('x01', 0))

        # 铜波导
        app.para('wg_a', self.wg_a)
        app.para('wg_b', self.wg_b)
        app.para('wg_t', self.wg_t)

        # 透镜：椭圆路线要 `Ls`（楔形裁剪体边长）。
        # ⚠️ 本模板把透镜放在**原点**（`place=False`，见类 docstring）⇒ **不需要**
        #    `Rbig` —— 登记它就是死写入（真机上会被 verify_model_parameter_usage 抓到）。
        #    所以 `Ls` 直接写成"2.2×Rbig"的**等价表达式**（Rbig = a*(3*n_small/4+lx1)），
        #    不再引用一个不登记的 `Rbig`。
        if self.has_lens and self.lens_method != 'insitu':
            spec = self.make_lens_spec()
            app.para('Ls', f'{2.2 * spec.r_big / self.a:g}*a',
                     expression='楔形裁剪体边长（约定 = 2.2·Rbig）')

    # ---- 建模 ----

    def build_all(self):
        """端到端建模：材料 → 多路径基板/VPC → 逐分支晶体 → 裁剪 → 双馈源 → 双波导 → 3 端口。"""
        if self.app is None:
            raise RuntimeError('CST 初始化失败，无法建模。')
        app = self.app
        self._define_all_params()

        build_materials(app)

        # 1) 多路径基板（VPC 区域即硅本体；这里保留 substrate 以便覆盖三条分支）
        y_margin = f'{self.yup}*e2'
        substrate = build_substrate_multi(app, self.paths, name='substrate',
                                          y_margin=y_margin)
        # 2) 多路径 VPC 区域（上下半区各并成一个实体）
        vpca, vpcb = self.modeler.build_vpc_regions(y_margin=y_margin)
        # 3) 每个分支各一套晶体（阵列次数走**参数引用**）
        crystals = self.modeler.build_crystals_multi(topology=self.topology,
                                                     xup='xup', yup='yup',
                                                     ydn='ydn')
        # 4) 逐分支裁剪进并集后的 VPC 区域
        clip = self.modeler.clip_crystals_with_vpc()

        # 5) 双馈源
        feed1_name = build_feed(app, feed_type=self.feed1, name='feed1')
        feed2_name = build_feed(app, feed_type=self.feed2, name='feed2')

        # 6) 两条铜波导
        #    AB 侧（`wg1`）：参考做法是 `translate([0, py6, 0])` + **关于 y 镜像**
        #    （`copy=True, unite=True`）⇒ 并成**一个双端实体**，两端面分别给端口 2/3。
        #    ⚠️ 不镜像就没有面 `'22'` —— 真机实测过：`pick_face('wg1','22')` 选中 0 个面，
        #       `add_waveguide_port` 的校验直接把它挡下来了（面号与几何强相关）。
        wg_ab = build_waveguide(app, name='wg1', material='Copper (annealed)')
        app.translate('wg1', ['0', self._arm_end_expr(), '0'],
                      copy=False, unite=False, log_flag=1)
        app.mirror('wg1', [0, 0, 0], [0, 1, 0], copy=True, unite=True)
        #    BA 侧（`wg2`）：在轴线上，范围 `[-lf5-lf6-lf4, -lf4]`
        wg_ba = build_multiport_waveguide(app, name='wg2')

        # 7) 三个端口（编号由调用方给；面号 `'10'` 为轴向口径端面）
        ports = add_multiport_port_set(app, [
            ('wg2', self.port_numbers[0], AXIAL_FACE),
            ('wg1', self.port_numbers[1], AXIAL_FACE),
            ('wg1', self.port_numbers[2], SIDE_FACE),
        ])

        # 8) 整合：硅（子分支）+ 两个馈源 + 波导
        app.add(vpca, feed1_name)
        app.add(vpca, feed2_name)
        app.add(vpca, vpcb)

        # 9) 可选透镜（参考口径：**单枚、近焦点在原点** —— `place=False`）
        lens = None
        if self.has_lens:
            lens = self.build_lens()

        self._parts = {'substrate': substrate, 'vpca': vpca, 'vpcb': vpcb,
                       'crystals': crystals, 'clip': clip,
                       'feed1': feed1_name, 'feed2': feed2_name,
                       'wg1': wg_ab, 'wg2': wg_ba, 'ports': ports,
                       'lens': lens}
        if self.freq_range:
            from topo_modeler.builders import configure_solver
            configure_solver(app, freq_range=self.freq_range,
                             monitors=self.monitors)
        self._built = True
        return self

    def build_lens(self):
        """建透镜（三条路线；参考口径 = **单枚透镜、近焦点在原点**）。

        * ``'generate'``：现算孔阵列 → 落 DXF → `build_grin_lens(place=False)`；
        * ``'dxf'``：用现成 DXF，同样 `place=False`；
        * ``'insitu'``：**不落 DXF**，`build_grin_lens_insitu(place=False)`。

        ⚠️ **不复制 6 份**（参考的多端口 notebook 只有一枚，放在原点），所以
        `place=False`；也因此不需要 `Rbig`（那个参数只服务于"移到顶点 + 旋转复制"）。
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
        """结构化验收（读消息 + Rebuild），见 `cst_solver.validate_model`。"""
        if not self._built:
            self.build_all()
        return self.app.validate_model()

    def close(self):
        """关闭会话（**先 save 再 close**）。"""
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
        return {'topology': self.topology,
                'straight_length': self.straight_length,
                'arm_length': self.arm_length,
                'paths': {name: list(path.path_lattice)
                          for name, path in self.paths.items()},
                'array_range': list(self.modeler.array_range()),
                'ports': self.port_numbers,
                'feed_params': dict(self.feed_params),
                'has_lens': self.has_lens,
                'lens_method': self.lens_method,
                'lens': self.lens_summary()}

    def __repr__(self):
        return (f"MultiPortAntenna(topology='{self.topology}', "
                f"L={self.straight_length}, arm={self.arm_length}, "
                f"ports={self.port_numbers})")
