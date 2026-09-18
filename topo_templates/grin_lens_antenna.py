# -*- coding: utf-8 -*-
r"""
GRINLensAntenna —— 单元天线 + GRIN 椭圆透镜（阶段 6 几何 + P5 模板）
===================================================================

用途
----
把已经存在的那套几何（`builders/lens.py`：`GrinLensSpec` / `build_grin_lens_holes` /
`build_grin_lens`）接到天线流水线上，做成一个可配置的器件：

* **复用** `UnitAntenna` 的路径 / 基板 / VPC / 光子晶体 / 馈源 / 波导 / 端口 全流程；
* 额外在片子六边形的顶点处建 **6 个 GRIN 椭圆透镜**（旋转复制，`unite=False`）；
* **不重做孔阵列算法** —— 孔阵列与 DXF 导出都走 `builders/lens.py`。

两条入口（计划 P5 明确要求「增加现有 DXF 入口」）
------------------------------------------------
============================  ==============================================
`lens_method='generate'`      由 `GrinLensSpec` 现算孔阵列 → 导出 DXF → 建透镜
`lens_method='dxf'`           直接用 `lens_dxf` 指向的**现成 DXF**（不回头算几何）
`lens_method='insitu'`        **不落 DXF**，直接在 CST 里逐个 `hexagon` 建孔
============================  ==============================================

`lens_method='insitu'` 走的是参考 notebook（`功分器加天线\1分4\…circle_DF.ipynb`）
里那套「GRIB 环透镜」做法：`HEX_SIZE = a/sqr(3)/2` 的六边形网格取**第一象限**，
半径 `< d0` 的孔用固定 `r1`，其余按 `r1+(r2-r1)*(dist-d0)/(N*a2-d0)` 渐变，
建完 `mirror` 补齐另一半，再用「圆柱切半 − 孔阵」取负形。
⚠️ 孔径渐变的公式里带**烘死的距离数字**（参考 notebook 原本如此），因此 `insitu`
**不是全参量化**的：改 `lens_layers` / `lens_d0_layers` 会改变孔集合，必须整枚重建
（孔集合由 `grin_ring_holes()` 离线重算，不缓存）。

⚠️ **孔数提醒**：`insitu` 的孔数 = 六边形网格第一象限格点数 ——
`lens_layers=30`（参考值）时 = **721 孔**（≈ 1500 条建模指令），
比 DXF 路线（`lens_nx=16, ratio=1` ⇒ 181 孔）重得多。想提速就降 `lens_layers`。

两种方式在下发 CST 之前都会做同一步：**登记 `Rbig` / `Ls` 两个参数**
（`Rbig = a*(3*n_small/4 + lx1)`、`Ls = 2.2*Rbig`）。
⚠️ 这一步不能省：`build_grin_lens()` 里对它们有前置拦截 —— 缺了它们 CST 会弹出
「请输入变量值」的**模态对话框**把脚本永久挂住（P4/V6 真机教训）。
（`insitu` 路线自己还会登记 `HEX_SIZE / a2 / N / d0 / r1 / r2`，同样是为避免那个对话框。）

⚠️ 耗时提醒（真机实测）：DXF 导入是「每条多段线一个实体」，耗时随孔数**超线性**增长
（参考配置 2215 条 ≈ 184 s）。**想减少孔数要「降 `lens_ratio` + 同比缩小 `lens_nx/ny`」**
（固定物理尺寸时孔数 ∝ ratio²，抬高 ratio 只会更慢），且 `lens_nx > 12` 是硬约束 —— 
细节与实测数据见 [几何规格](../docs/guides/grin_lens_geometry.md) 与
`builders/lens.py::GrinLensSpec` 的 `ratio` 说明。

⚠️ **本模板的步骤顺序是本库定的**（参考工程里没有「单元天线 + GRIN 透镜」这个组合）：
材料 → 基板 → VPC → 晶体 → 馈源 → 波导 → **透镜** → 端口 → 整合 → 求解器。
透镜与天线实体**没有布尔耦合**（透镜自带椭圆包络 + 楔形裁剪），放在波导之后是为了
让「片子上的硅」先建完。

@author: PC
"""

import os

from topo_modeler.builders import (
    GrinLensSpec,
    build_grin_lens,
    build_grin_lens_from_dxf,
    build_grin_lens_holes,
    build_grin_lens_insitu,
    grin_lens_spec_from_cst_params,
    grin_ring_holes,
    DEFAULT_RING_LAYERS,
    DEFAULT_D0_LAYERS,
)
from topo_templates.unit_antenna import UnitAntenna

LENS_METHODS = ('generate', 'dxf', 'insitu')

#: 透镜几何的默认值（与 `scripts/verify_grin_multipath.py` 里真机验收过的小模型一致）
LENS_DEFAULTS = dict(ratio=1.0, nx=16, ny=13, r1_0=0.052, r2_0=0.066,
                     n_small=8, lx1=6)


class GRINLensAntenna(UnitAntenna):
    """
    单元天线 + GRIN 椭圆透镜（六边形顶点 6 个）。

    :param bend_angle: 张角（两侧臂夹角，120 的整数倍），透传给 `UnitAntenna`
    :param lens_method: str，``'generate'``（现算孔阵列 + DXF）、``'dxf'``（用现成 DXF）
        或 ``'insitu'``（不落 DXF，直接在 CST 里逐个 `hexagon` 建孔，参考 GRIB 做法）
    :param lens_dxf: str 可选，``lens_method='dxf'`` 时**必给**的 DXF 路径
    :param lens_dxf_out: str 可选，``'generate'`` 时导出的 DXF 路径
        （默认落在当前目录的 ``grin_lens_hexring.dxf``）
    :param lens_ratio: float，孔网格细化倍率（格距 = a/ratio）。
        ⚠️ 孔数与它的关系容易说反：**固定 `lens_nx/ny` 时孔数与 ratio 无关**
        （器件物理尺寸随之变）；**固定物理尺寸**时孔数 ∝ ratio²。
        ⇒ 想减少孔数（提速）要**降 ratio 并把 nx/ny 同比缩小**；
        `lens_nx > 12` 是硬约束（`d_out > d0 = 12·a2`）。
        （仅 `'generate'` / `'dxf'` 路线使用）
    :param lens_nx: int，椭圆长半轴 = nx 个格距（仅 DXF 路线使用）
    :param lens_ny: int，椭圆短半轴 = ny 个格距（仅 DXF 路线使用）
    :param lens_layers: int，``'insitu'`` 的六边形网格层数 `N`（参考 30）
    :param lens_d0_layers: int，``'insitu'`` 的 `d0 = lens_d0_layers*HEX_SIZE*2*sqr(3)`
        （参考 8）
    :param lens_name: str，透镜实体名
    :param lens_component: str，透镜组件名（= DXF 图层名）
    :param lens_rotation: float，**透镜绕自身近焦点自转角** `dphi`（度）。
        对应参考 `椭圆透镜单元天线/…/*_rotation.ipynb` 的做法：
        `para('dphi','10')` → `rotation('epc1', ['0',0,'dphi'], [顶点])`
        —— 注意它是**绕顶点（= 近焦点）自转透镜**，不是"把透镜挪到别的臂"。
        默认 0 ⇒ 不下发这一步（默认序列与旧脚本逐字节一致）。
    :param lens_kwargs: 覆盖 :data:`LENS_DEFAULTS` 里其余项
        （``r1_0 / r2_0 / n_small / lx1``，也接受旧脚本别名 ``R_big / nsm`` 等，
        由 `grin_lens_spec_from_cst_params` 解析）
    """

    #: 透镜孔阵列来源（与 :data:`LENS_METHODS` 同值；挂成类属性便于自省与护栏校验）
    LENS_METHODS = LENS_METHODS

    def __init__(self, bend_angle=120, straight_length=18, arm_length=14,
                 topology='BA', lattice_constant=0.2425, height=0.25,
                 large_hole_ratio=0.65, small_hole_ratio=0.35,
                 feed_type='ba_tapered',
                 radiator=None, radiator_radius=0.3,
                 wg_a=0.7312, wg_b=0.3756, wg_t=0.2,
                 freq_range=(300, 380), monitors=('E', 'Farfield'),
                 template_cst='tmp.cst', output_path=None,
                 lens_method='generate', lens_dxf=None, lens_dxf_out=None,
                 lens_ratio=1.0, lens_nx=16, lens_ny=13,
                 lens_layers=DEFAULT_RING_LAYERS,
                 lens_d0_layers=DEFAULT_D0_LAYERS,
                 lens_name='lens_epc', lens_component='gridlens',
                 lens_rotation=0, lens_kwargs=None):
        if lens_method not in LENS_METHODS:
            raise ValueError(f"lens_method 必须是 {' / '.join(LENS_METHODS)}，"
                             f"收到 {lens_method!r}")
        if lens_method == 'dxf':
            if not lens_dxf:
                raise ValueError(
                    "lens_method='dxf' 必须给 lens_dxf（现成孔阵列 DXF 的路径）")
            if not os.path.isfile(lens_dxf):
                raise FileNotFoundError(f'透镜 DXF 不存在：{lens_dxf}')
        if lens_method == 'insitu' and int(lens_layers) <= 0:
            raise ValueError(f"lens_method='insitu' 需要 lens_layers >= 1，"
                             f"收到 {lens_layers!r}")
        super().__init__(
            bend_angle=bend_angle, straight_length=straight_length,
            arm_length=arm_length, topology=topology,
            lattice_constant=lattice_constant, height=height,
            large_hole_ratio=large_hole_ratio,
            small_hole_ratio=small_hole_ratio,
            feed_type=feed_type, radiator=radiator,
            radiator_radius=radiator_radius, wg_a=wg_a, wg_b=wg_b, wg_t=wg_t,
            freq_range=freq_range, monitors=monitors,
            template_cst=template_cst, output_path=output_path)

        self.lens_method = lens_method
        self.lens_dxf = lens_dxf
        self.lens_dxf_out = lens_dxf_out or os.path.join(
            os.getcwd(), 'grin_lens_hexring.dxf')
        self.lens_ratio = lens_ratio
        self.lens_nx = lens_nx
        self.lens_ny = lens_ny
        self.lens_layers = int(lens_layers)
        self.lens_d0_layers = int(lens_d0_layers)
        self.lens_name = lens_name
        self.lens_component = lens_component
        self.lens_rotation = lens_rotation
        # 其余项（r1_0 / r2_0 / n_small / lx1 或旧脚本别名）走 kwargs
        self.lens_kwargs = dict(LENS_DEFAULTS, ratio=lens_ratio, nx=lens_nx,
                                ny=lens_ny, **(lens_kwargs or {}))

        self.lens_spec = None       # 惰性算：`make_lens_spec()` / `build_all()` 时才有
        self.lens_holes = None
        self.lens_ring = None       # `insitu` 的孔集合（`grin_ring_holes()` 的返回）
        self.lens_info = None       # `build_lens()` 的返回（含实体名与参数）

    # ---- 离线部分：几何（不碰 CST） ----

    def make_lens_spec(self) -> GrinLensSpec:
        """
        算 GRIN 透镜几何规格（**纯 numpy/shapely，不需要 CST**）。

        :return: GrinLensSpec
        """
        if self.lens_spec is None:
            self.lens_spec = grin_lens_spec_from_cst_params(
                a=self.a, **self.lens_kwargs)
        return self.lens_spec

    def make_lens_dxf(self, path=None) -> str:
        """
        生成孔阵列 DXF（**离线**，给 `lens_method='generate'` 用）。

        :param path: str 可选，输出路径（默认 `self.lens_dxf_out`）
        :return: str，DXF 路径
        """
        target = path or self.lens_dxf_out
        spec = self.make_lens_spec()
        self.lens_holes = build_grin_lens_holes(spec)
        self.lens_holes.export_dxf(target)
        return target

    def lens_summary(self) -> dict:
        """透镜几何摘要（日志/报告用；离线可算）。"""
        spec = self.make_lens_spec()
        n_holes = len(self.lens_holes) if self.lens_holes is not None else None
        summary = {'method': self.lens_method,
                   'dxf': self.lens_dxf or self.lens_dxf_out,
                   'a2': spec.a2, 'nx': spec.nx, 'ny': spec.ny,
                   'ec_a': spec.ec_a, 'ec_b': spec.ec_b, 'ec_c': spec.shift,
                   'r_in': spec.r_in, 'r_out': spec.r_out, 'r_big': spec.r_big,
                   'n_holes': n_holes}
        if self.lens_method == 'insitu':
            ring = self.make_lens_ring()
            summary.update({'dxf': None,
                            'hex_size': ring['hex_size'],
                            'ring_a2': ring['a2'],
                            'layers': ring['n_layers'],
                            'ring_d0': ring['d0'],
                            'radius_outer': ring['radius_outer'],
                            'n_holes': len(ring['holes']),
                            'quadrant_only': ring['quadrant_only']})
        return summary

    # ---- 离线部分（`insitu` 路线）：环透镜孔集合 ----

    def make_lens_ring(self) -> dict:
        """
        算 ``insitu`` 路线的环透镜孔集合（**纯几何，不需要 CST**）。

        :return: dict，`grin_ring_holes()` 的返回
        """
        if self.lens_ring is None:
            self.lens_ring = grin_ring_holes(
                self.a, n_layers=self.lens_layers,
                r1_0=self.lens_kwargs.get('r1_0', 0.0505),
                r2_0=self.lens_kwargs.get('r2_0', 0.0613),
                d0_layers=self.lens_d0_layers)
        return self.lens_ring

    # ---- CST 参数 ----

    def _define_all_params(self):
        """天线参数 + 透镜要用的 `Rbig`（DXF 路线还要 `Ls`）。"""
        super()._define_all_params()
        app = self.app
        spec = self.make_lens_spec()
        # ⚠️ `Rbig` / `Ls` **必须**在 `build_grin_lens()` 之前存在：
        #    `build_grin_lens` 对它们有前置拦截（缺参数时 CST 会弹「输入变量值」
        #    模态对话框把脚本挂住，而不是抛异常）。表达式口径见 P4/V6 证据 §6.1。
        app.para('Rbig', f'{spec.r_big / self.a:g}*a',
                 expression='大六边形外接圆半径')
        # `Ls` **只被 DXF 路线的「楔形裁剪」用到**（`build_grin_lens` 步骤 ③）。
        # 就地路线（`insitu`）没有楔形裁剪 ⇒ 登记它就变成**死写入**
        # （2026-09-17 真机跑 `verify_grin_lens_insitu_real.py` 时被
        # `verify_model_parameter_usage.py` 抓到 `Ls` 未被引用），所以按路线登记。
        if self.lens_method != 'insitu':
            app.para('Ls', '2.2*Rbig', expression='楔形裁剪体边长（约定 2.2*Rbig）')
        # 透镜自转角（参考就叫 `dphi`，见 `*_rotation.ipynb`）。登记成**参数**而不是
        # 把角度烘进 VBA，符合 P4 §8.7 的"只用 CST 表达式"口径。
        # ⚠️ 为 0 时**不登记** —— 没有自转步骤引用它，登记就是死写入（D9 的教训）。
        if self.lens_rotation:
            app.para('dphi', self.lens_rotation,
                     expression='透镜绕自身近焦点自转角 [deg]（参考 notebook 的 dphi）')

    # ---- CST 步骤 ----

    def build_lens(self):
        """
        建 GRIN 透镜（CST 步骤）。

        :return: dict，`build_grin_lens` / `build_grin_lens_from_dxf` 的返回
        :raises RuntimeError: 无 CST 环境
        """
        if self.app is None:
            raise RuntimeError('CST 初始化失败，无法建模。')
        spec = self.make_lens_spec()

        def log(tag=''):
            if tag:
                print(f'  · {tag}')

        if self.lens_method == 'dxf':
            # 现成 DXF：不回头算几何，孔数统计为 None（不猜数字）
            self.lens_info = build_grin_lens_from_dxf(
                self.app, self.lens_dxf, spec=spec, name=self.lens_name,
                component=self.lens_component, self_rotation=self._dphi_expr(),
                log=log)
        elif self.lens_method == 'insitu':
            # 就地 hexagon 环透镜：不落 DXF，孔集合离线现算
            ring = self.make_lens_ring()
            self.lens_info = build_grin_lens_insitu(
                self.app, ring, name=self.lens_name,
                height='h', material='Silicon (lossy)',
                component=self.lens_component, self_rotation=self._dphi_expr(),
                log=log)
        else:
            dxf = self.make_lens_dxf()
            self.lens_info = build_grin_lens(
                self.app, self.lens_holes, spec=spec, name=self.lens_name,
                component=self.lens_component, dxf_path=dxf,
                self_rotation=self._dphi_expr(), log=log)
        return self.lens_info

    def _dphi_expr(self):
        """自转角要下发时**用 CST 参数名** `dphi`（不把角度烘进 VBA）。

        :return: str 或 0（0 ⇒ 不登记/不下发这一步）
        """
        return 'dphi' if self.lens_rotation else 0

    def build_all(self):
        """端到端建模：天线流水线 + GRIN 透镜。"""
        super().build_all()
        self.build_lens()
        return self

    def __repr__(self):
        return (f"GRINLensAntenna(topology='{self.topology}', "
                f"bend={self.bend_angle}°, L={self.straight_length}, "
                f"arm={self.arm_length}, lens={self.lens_method})")
