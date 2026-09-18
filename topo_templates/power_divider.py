# -*- coding: utf-8 -*-
r"""
PowerDivider —— 1 分 N 功分器（α2 族，P5 模板）
===============================================

参考与口径
----------
按 α2 族 5 个 notebook 的逐 cell 取证（[复杂器件参考规格](../../docs/guides/complex_device_specs.md)
§4.3–§4.5）与[设计记录](../../docs/guides/complex_device_templates_design.md)：

* **只有分路数有数据依据**：1分2（`Ant2_1div2_*`）、1分3（`Ant3_1div3_BA_120D_epc`）、
  1分4（`Ant4_1div4_BA_120D_epc`、`Ant4_1d2d4_2f2s_circle_DF`）、1分6（`Ant6_2H4L_epc`）；
  ⚠️ `divider_type('y'/'t'/'cascade'/'mmi')` **在参考参数表里没有出处**，
  `tests/test_complex_device_scope.py` 已用机器护栏挡住这类"没有依据就宣称支持"；
* **单馈源 + 单铜波导 ⇒ 1 个端口**（参考就是这么建的，端口在铜波导的轴向面 `'10'`）；
* 可选**透镜**，两条路线（与 `GRINLensAntenna` 同口径）：
  ``lens_method='dxf'`` 用现成孔阵列 DXF；``lens_method='insitu'`` **不落 DXF**，
  在 CST 内逐个 `hexagon` 建环（参考 `Ant4_1d2d4_2f2s_circle_DF` 就是这种做法）；
* 可选**相位** `lens_phase`：`dphi1/dphi2` 只在 1div4 / 2H4L 出现，
  语义 = **把同一枚透镜绕 z 转 dphi 后放到不同输出臂**（不是几何长度差）。
* 可选**开关/泵浦区**（2026-09-18 补，覆盖 `pump_switching` 特征）：参考做法是
  **自定义材料 + 圆柱 + 与区域副本求交后 `insert` 回区域**：

  ```text
  app1.para('sigma1','0')
  app1.create_material_custom(name='switch1', epsilon=11.9, mu=1, kappa='sigma1', …)
  app1.para('rc1','0.4')
  for i in range(4):                       # 2H4L 是 4 个开关
      app1.translate('vpca',['0','0','0'],copy=True,unite=False,log_flag=1)
      app1.intersect(f'sw{i+1}','vpca_1')  # 逐个求交（副本名恒为 `vpca_1`）
      app1.insert('vpca',f'sw{i+1}')
  ```

  ⚠️ 参考的开关位置是它**闭合区域轮廓**的角点中点（`(px4+px5)/2` 等）；本库用
  **中心线派生**（D1）⇒ 默认位置是**每条第一级输出臂最后一段的中点**
  （`switch_mode='arm_mid'`），也可以由调用方按表达式直接给（`switch_xy=`）。
  两者都只保证"开关在硅里"，**不保证与参考同一坐标**。

⚠️ **`Rbig` / `Ls` 必须登记**（2026-09-17 修）：`build_grin_lens_from_dxf` 对它们有
前置拦截（缺了 CST 会弹「请输入变量值」的模态对话框把脚本挂住）。本模板原先**一个都
没登记** ⇒ 透镜路线在真机上根本走不通（会抛我们自己的 preflight ValueError）。
现在按路线登记：`Rbig` 两条路线都要，`Ls` **只有 DXF 路线**要（就地路线没有楔形裁剪，
登记它就是死写入）。

⚠️ 本模板**不与参考 notebook 逐字节相同**（设计记录 §2 的 D1）：参考用闭合区域轮廓，
本模板用本库口径（多条 `TopoPath` 中心线 + `±y_margin` 派生 + 多路径布尔并）。
验收判据是「分路数/端口/参数同类 + 只建模 0 条 CST 消息」，**不是**几何等价。

⚠️ **级联结构**：`split_ratio=4` 用 **2×2**（= 参考 `1d2d4` 的两级）、`6` 用 **2×3**；
`2`/`3` 是单级扇出。臂方向取三角晶格的 60° 方向（`turn(±60)` / `turn(0)`）。

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
    build_grin_lens_from_dxf,
    build_grin_lens_insitu,
    build_materials,
    build_waveguide,
    configure_solver,
    grin_lens_spec_from_cst_params,
    grin_ring_holes,
)

#: 有数据依据的分路数（1分2/3/4/6）；其余取值在参考里没有出处
SUPPORTED_SPLIT_RATIOS = (2, 3, 4, 6)
#: 分路数 → （第一级扇出数, 第二级每臂扇出数）：4 = 参考的 `1d2d4` 两级结构
CASCADE_FACTORS = {2: (2, 1), 3: (3, 1), 4: (2, 2), 6: (2, 3)}
#: 单级扇出的臂方向（度）：2 路 ⇒ ±60°；3 路 ⇒ −60°/0°/+60°
FAN_ANGLES = {2: (-60, 60), 3: (-60, 0, 60)}
#: 端口面号（参考里是铜波导的轴向口径端面）
AXIAL_FACE = '10'
#: 透镜孔阵列来源（与 `GRINLensAntenna` **同名同义**：
#: `generate` 现算 + 落 DXF；`dxf` 用现成 DXF；`insitu` **不落 DXF**，CST 内逐环建）
LENS_METHODS = ('generate', 'dxf', 'insitu')
#: 开关/泵浦区的放置方式：
#: ``None`` 不建；``'arm_mid'`` 每条第一级输出臂最后一段的中点（本库口径）；
#: ``'explicit'`` 由调用方给坐标（`switch_xy=`，元素是 (x, y) 数值或 CST 表达式）
SWITCH_MODES = (None, 'arm_mid', 'explicit')
#: 开关材料的相对介电常数（参考 `create_material_custom(…, epsilon=11.9, …)`）
SWITCH_EPSILON = 11.9


class PowerDivider:
    """
    1 分 N 功分器（N ∈ {2, 3, 4, 6}；可选透镜与相位）。

    :param split_ratio: int, 分路数（只支持 2/3/4/6 —— 参考里有数据依据的取值）
    :param trunk_length: int, 主干长度（晶格周期数），参考 x1 = 14/8/18
    :param arm_length: int, 第一级臂长（晶格周期数）
    :param sub_length: int, 第二级臂长（仅 4/6 的级联结构用）
    :param topology: str, 'AB' / 'BA'
    :param port_number: int, 端口编号（单端口，默认 1）
    :param lens_method: str 可选, ``None``（不建透镜）/ ``'generate'``（现算孔阵列 →
        落 DXF → 建）/ ``'dxf'``（用现成 DXF）/ ``'insitu'``（**不落 DXF**，
        在 CST 内逐个 `hexagon` 建环）。默认 ``None``：给了 `lens_dxf` 就等价于
        ``'dxf'``，否则不建透镜
    :param lens_dxf: str 可选, 现成的孔阵列 DXF（``lens_method='dxf'`` 时必给）
    :param lens_dxf_out: str 可选, ``'generate'`` 时导出的 DXF 路径
        （默认当前目录的 ``divider_lens_hexring.dxf``）
    :param lens_ratio: float, 孔网格细化倍率（格距 = a/ratio；透传给 `GrinLensSpec`）
    :param lens_nx: int 可选, 椭圆长半轴 = nx 个格距（默认取 `make_lens_spec` 的值）
    :param lens_ny: int 可选, 椭圆短半轴 = ny 个格距（同上）
    :param lens_layers: int, ``'insitu'`` 的六边形网格层数（参考 30）
    :param lens_d0_layers: int, ``'insitu'`` 的 `d0` 层数系数（参考 8）
    :param lens_phase: tuple 可选, 两个相位角（度），参考 1div4 = (30, 10)、2H4L = (15, 5)
    :param lens_kwargs: dict 可选, 透镜几何参数（同 `GRINLensAntenna`）
    :param switch_mode: str 可选, 开关/泵浦区放置方式：``None``（不建，默认）/
        ``'arm_mid'``（每条第一级输出臂最后一段的中点 —— 本库口径）/
        ``'explicit'``（用 `switch_xy` 给的坐标）
    :param switch_xy: 序列 可选, ``[(x, y), …]``（数值或 CST 表达式字符串）；
        给了它就等价于 ``switch_mode='explicit'``
    :param switch_radius: float, 开关圆柱半径 [mm]（参考 `rc1 = 0.4`）
    :param switch_sigma: float, 开关材料电导率 [S/m]（参考 `sigma1 = 0`）
    :param switch_material: str, 开关材料名（默认 `switch1`）
    """

    _FEED_PARAM_NAMES = {'ab_elliptical': ('x0', 'wf1', 'lf1', 'lf2', 'lf3')}

    #: 透镜孔阵列来源（与 :data:`LENS_METHODS` 同值；挂成类属性便于自省与护栏校验）
    LENS_METHODS = LENS_METHODS
    #: 有数据依据的分路数（与 :data:`SUPPORTED_SPLIT_RATIOS` 同值）
    SUPPORTED_SPLIT_RATIOS = SUPPORTED_SPLIT_RATIOS
    #: 开关/泵浦区的放置方式（与 :data:`SWITCH_MODES` 同值）
    SWITCH_MODES = SWITCH_MODES

    def __init__(self, split_ratio=2, trunk_length=14, arm_length=8, sub_length=6,
                 topology='AB', lattice_constant=0.2425, height=0.25,
                 large_hole_ratio=0.65, small_hole_ratio=0.35,
                 port_number=1, feed_type='ab_elliptical',
                 wg_a=0.7312, wg_b=0.3756, wg_t=0.2,
                 lens_method=None, lens_dxf=None, lens_dxf_out=None,
                 lens_ratio=2.0, lens_nx=None, lens_ny=None,
                 lens_layers=DEFAULT_RING_LAYERS,
                 lens_d0_layers=DEFAULT_D0_LAYERS,
                 lens_phase=None, lens_name='lens_epc',
                 lens_component='gridlens', lens_kwargs=None,
                 switch_mode=None, switch_xy=None, switch_radius=0.4,
                 switch_sigma=0.0, switch_material='switch1',
                 freq_range=(300, 380), monitors=('E',),
                 template_cst='tmp.cst', output_path=None, feed_params=None):
        if split_ratio not in SUPPORTED_SPLIT_RATIOS:
            raise ValueError(
                f'split_ratio={split_ratio!r} 不支持；有数据依据的取值是 '
                f'{list(SUPPORTED_SPLIT_RATIOS)}（1分2/3/4/6）。'
                f'⚠️ `divider_type("y"/"t"/"cascade"/"mmi")` 在参考参数表里'
                f'**没有出处**，不要按它造几何 —— 见 '
                f'docs/guides/complex_device_specs.md §4.3。')
        if topology not in ('AB', 'BA'):
            raise ValueError(f"topology 必须是 'AB' 或 'BA'，收到 '{topology}'")
        if lens_method is not None and lens_method not in LENS_METHODS:
            raise ValueError(f"lens_method 必须是 None / {' / '.join(LENS_METHODS)}，"
                             f"收到 {lens_method!r}")
        if lens_method == 'dxf' and not lens_dxf:
            raise ValueError("lens_method='dxf' 必须给 lens_dxf（现成孔阵列 DXF 的路径）")
        if lens_method != 'dxf' and lens_dxf is not None and lens_method is not None:
            raise ValueError(
                f"lens_method={lens_method!r} 与 lens_dxf 互斥 —— "
                "'insitu' 就地建环**不落 DXF**；'generate' 会自己算孔阵列并落 DXF。"
                '想用现成 DXF 请用 lens_method="dxf"')
        if lens_method == 'insitu' and int(lens_layers) <= 0:
            raise ValueError(f"lens_method='insitu' 需要 lens_layers >= 1，"
                             f"收到 {lens_layers!r}")
        if lens_dxf is not None and not os.path.isfile(lens_dxf):
            raise FileNotFoundError(f'透镜 DXF 不存在：{lens_dxf}')
        # 不带 `lens_method` 时的历史行为：给了 DXF 就等于 'dxf'
        effective_method = lens_method or ('dxf' if lens_dxf else None)
        if effective_method is None and lens_phase is not None:
            # 相位是**作用在透镜上**的；没透镜时给相位是无效输入
            raise ValueError(
                'lens_phase 只有在建透镜时才有意义 —— '
                '相位是"把透镜绕 z 转 dphi"实现的，不是几何长度差')
        # 开关/泵浦区：给了坐标就等于 'explicit'
        if switch_xy is not None:
            if switch_mode not in (None, 'explicit'):
                raise ValueError(f"switch_xy 与 switch_mode={switch_mode!r} 冲突："
                                 f"给坐标请用 switch_mode='explicit'")
            switch_mode = 'explicit'
        if switch_mode not in SWITCH_MODES:
            raise ValueError(f"switch_mode 必须是 {list(SWITCH_MODES)}，"
                             f"收到 {switch_mode!r}")
        if switch_mode == 'explicit' and not switch_xy:
            raise ValueError("switch_mode='explicit' 必须给 switch_xy=[(x, y), …]")
        if switch_mode is not None:
            if float(switch_radius) <= 0:
                raise ValueError(f'开关圆柱半径必须 > 0，收到 {switch_radius!r}')
            for pair in (switch_xy or []):
                if len(tuple(pair)) != 2:
                    raise ValueError(f'switch_xy 的每一项必须是 (x, y)，收到 {pair!r}')

        self.split_ratio = int(split_ratio)
        self.topology = topology
        self.trunk_length = int(trunk_length)
        self.arm_length = int(arm_length)
        self.sub_length = int(sub_length)
        self.a = float(lattice_constant)
        self.h = float(height)
        self.l1 = large_hole_ratio * self.a
        self.l2 = small_hole_ratio * self.a
        self.port_number = int(port_number)
        self.feed_type = feed_type
        self.wg_a = wg_a
        self.wg_b = wg_b
        self.wg_t = wg_t
        self.lens_method = effective_method
        self.lens_dxf = lens_dxf
        self.lens_dxf_out = lens_dxf_out or os.path.join(
            os.getcwd(), 'divider_lens_hexring.dxf')
        self.lens_ratio = lens_ratio
        self.lens_nx = lens_nx
        self.lens_ny = lens_ny
        self.lens_layers = int(lens_layers)
        self.lens_d0_layers = int(lens_d0_layers)
        self.lens_phase = tuple(lens_phase or ())
        self.lens_name = lens_name
        self.lens_component = lens_component
        self.lens_kwargs = dict(lens_kwargs or {})
        if lens_ratio is not None:
            self.lens_kwargs.setdefault('ratio', lens_ratio)
        if lens_nx is not None:
            self.lens_kwargs.setdefault('nx', lens_nx)
        if lens_ny is not None:
            self.lens_kwargs.setdefault('ny', lens_ny)
        self.lens_holes = None       # 'insitu' 的孔集合（离线算，不缓存到磁盘）
        self.lens_info = None        # `build_lens()` 的返回
        self.switch_mode = switch_mode
        self.switch_xy = [tuple(p) for p in (switch_xy or [])]
        self.switch_radius = float(switch_radius)
        self.switch_sigma = float(switch_sigma)
        self.switch_material = switch_material
        self.freq_range = freq_range
        self.monitors = monitors
        self.template_cst = template_cst
        self.output_path = output_path
        self.feed_params = self._check_feed_params(feed_params)

        self.e1 = self.a / 2
        self.e2 = self.a * np.sqrt(3) / 2

        self.fan1, self.fan2 = CASCADE_FACTORS[self.split_ratio]
        self.paths = self._build_paths()
        self.path = self.paths['trunk']

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

    # ---- 路径 ----

    def _build_paths(self):
        """所有**输出路径**（每条都从输入端走到一个输出端）+ 主干。

        多路径机制要求"每条输出路径"都在 `paths` 里，这样 VPC/晶体才能覆盖整个器件。
        """
        paths = {}
        paths['trunk'] = (TopoPath.builder(self.a, name='trunk')
                          .start(0, 0).move(self.trunk_length, 'c').build())
        for i, angle1 in enumerate(FAN_ANGLES[self.fan1]):
            base = (TopoPath.builder(self.a, name=f'stage1_{i}')
                    .start(0, 0).move(self.trunk_length, 'c')
                    .turn(angle1).move(self.arm_length, 'along'))
            if self.fan2 == 1:
                paths[f'arm{i}'] = base.build()
                continue
            for j, angle2 in enumerate(FAN_ANGLES[self.fan2]):
                # `turn` 是**相对当前朝向**的 ⇒ 第二级要转 (angle2 - angle1)
                branch = (TopoPath.builder(self.a, name=f'stage2_{i}_{j}')
                          .start(0, 0).move(self.trunk_length, 'c')
                          .turn(angle1).move(self.arm_length, 'along')
                          .turn(angle2 - angle1).move(self.sub_length, 'along'))
                paths[f'arm{i}_{j}'] = branch.build()
        return paths

    def output_paths(self):
        """输出路径的名字（不含主干）—— 数量必须等于 `split_ratio`。"""
        return [name for name in self.paths if name != 'trunk']

    # ---- 校验 ----

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

    # ---- 透镜（可选，离线可算）----

    @property
    def has_lens(self):
        """是否要建透镜（`lens_method` 为 `None` 时不建）。"""
        return self.lens_method is not None

    def make_lens_spec(self) -> GrinLensSpec:
        """透镜几何规格（离线可算）。参考的 `para_init` 公式
        （`功分器加天线/椭圆透镜1div3/Ant2_1div2_*` 逐行取证）：

        ```text
        def para_init(yl=10, l=[50.5, 61.3], a=0.2425, ratio=2):
            r = np.array(l)/1e3/ratio*2                      # ⇒ 等效 0.0505 / 0.0613
            hexsize = a/np.sqrt(3)/ratio                     # ⇒ 本库 a2 = a/ratio
            Nx = int(yl*1.15)*ratio+1                        # yl=10, ratio=2 ⇒ 24
            Ny = yl*ratio+1                                  #             ⇒ 21
            d0 = 6*hexsize*2*np.sqrt(3)                      # ⇒ 本库 d0 = 12*a2
        ```

        ⚠️ **`r1_0` 的换算容易错一倍**（2026-09-18 更正）：参考的有效半径是
        ``2*r_raw/ratio``，而本库 `GrinLensSpec` 是 ``r1_0/ratio`` ⇒
        要在 ratio=2 时得到参考的 0.0505，必须传 `r1_0 = 0.101`（原先写的 0.0505
        会让孔半径**小一半**）。
        """
        kwargs = dict(ratio=2.0, nx=24, ny=21, r1_0=0.101, r2_0=0.1226,
                      n_small=12, lx1=8)
        kwargs.update(self.lens_kwargs)
        return grin_lens_spec_from_cst_params(a=self.a, **kwargs)

    def make_lens_dxf(self, path=None) -> str:
        """``lens_method='generate'`` 的孔阵列 DXF（**离线**）。

        :param path: str 可选, 输出路径（默认 `self.lens_dxf_out`）
        :return: str, DXF 路径
        """
        from topo_modeler.builders import build_grin_lens_holes

        target = path or self.lens_dxf_out
        holes = build_grin_lens_holes(self.make_lens_spec())
        holes.export_dxf(target)
        self.lens_dxf_generated = target
        return target

    def make_lens_ring(self) -> dict:
        """``lens_method='insitu'`` 的环透镜孔集合（**纯几何，不需要 CST**）。

        参数与 `GRINLensAntenna` 同口径：`HEX_SIZE = a/sqr(3)/2`、`N = lens_layers`、
        `d0 = lens_d0_layers*HEX_SIZE*2*sqr(3)`；半径取 `lens_kwargs` 的
        `r1_0 / r2_0`（默认 = 参考 50.5 / 61.3 µm）。

        :return: dict, `grin_ring_holes()` 的返回
        """
        if self.lens_holes is None:
            self.lens_holes = grin_ring_holes(
                self.a, n_layers=self.lens_layers,
                r1_0=self.lens_kwargs.get('r1_0', 0.0505),
                r2_0=self.lens_kwargs.get('r2_0', 0.0613),
                d0_layers=self.lens_d0_layers)
        return self.lens_holes

    def lens_summary(self) -> dict:
        """透镜摘要（离线可算；没透镜时返回 ``{'method': None}``）。"""
        if not self.has_lens:
            return {'method': None, 'phase': list(self.lens_phase)}
        summary = {'method': self.lens_method,
                   'phase': list(self.lens_phase),
                   'name': self.lens_name,
                   'component': self.lens_component}
        if self.lens_method == 'insitu':
            ring = self.make_lens_ring()
            summary.update({'dxf': None, 'layers': ring['n_layers'],
                            'hex_size': ring['hex_size'],
                            'ring_a2': ring['a2'], 'ring_d0': ring['d0'],
                            'radius_outer': ring['radius_outer'],
                            'n_holes': len(ring['holes'])})
        else:
            spec = self.make_lens_spec()
            summary.update({'dxf': self.lens_dxf or self.lens_dxf_out,
                            'ec_a': spec.ec_a, 'ec_b': spec.ec_b,
                            'r_big': spec.r_big, 'n_holes': None})
        return summary

    # ---- 开关/泵浦区（可选，离线可算位置）----

    @property
    def has_switch(self):
        """是否要建开关/泵浦区（`switch_mode` 为 `None` 时不建）。"""
        return self.switch_mode is not None

    def switch_positions(self):
        """开关圆柱中心坐标（**离线可核对**）。

        * ``switch_mode='explicit'`` ⇒ 原样返回 `switch_xy`（数值或 CST 表达式）；
        * ``switch_mode='arm_mid'`` ⇒ 每条**第一级输出臂**最后一段的中点，
          坐标写成**该路径已登记的 CST 参数**表达式
          （``(p<i>{n-1}x+p<i>{n}x)/2``）—— 与参考"取区域角点中点"同思路，
          只是本库的坐标来自中心线派生（D1）。

        :return: list[tuple], ``[(x_expr, y_expr), …]``
        """
        if not self.has_switch:
            return []
        if self.switch_mode == 'explicit':
            return [(str(x), str(y)) for x, y in self.switch_xy]
        names = list(self.paths)
        positions = []
        for path_name in self.output_paths():
            index = names.index(path_name)
            points = len(self.paths[path_name].path_lattice)
            if points < 2:
                continue
            positions.append((f'(p{index}{points - 1}x+p{index}{points}x)/2',
                              f'(p{index}{points - 1}y+p{index}{points}y)/2'))
        return positions

    def build_switches(self, vpca=None):
        """建开关/泵浦区（参考做法：自定义材料 + 圆柱 + 区域副本求交 + `insert`）。

        返回被插入的实体名列表。⚠️ CST 的 `Intersect` **结果留在第一个操作数**、
        第二个被**消耗** ⇒ 必须像参考那样**每个开关各拷一次区域**（副本名恒为
        `<区域>_1`，因为上一次的副本已经被求交吃掉）。

        :param vpca: str 可选, VPC 区域实体名（默认取 `self._parts['vpca']`）
        """
        if not self.has_switch:
            return []
        app = self.app
        vpca = vpca or self._parts.get('vpca')
        if vpca is None:
            raise ValueError('build_switches 需要 VPC 区域名（build_all 里的 vpca）')
        app.create_material_custom(self.switch_material, SWITCH_EPSILON, 1,
                                   'sigma1', material_type='Normal')
        made = []
        for i, (x, y) in enumerate(self.switch_positions(), start=1):
            name = f'switch{i}'
            app.create_cylinder(center=[x, y], r=['rc1', '0'],
                                h=['-h/2', 'h/2'], name=name,
                                axis='z', component='component1',
                                material=self.switch_material)
            app.translate(vpca, ['0', '0', '0'], copy=True, unite=False, log_flag=1)
            app.intersect(name, f'{vpca}_1')
            app.insert(vpca, name)
            made.append(name)
        return made

    # ---- CST 参数 ----

    def _define_all_params(self):
        """登记基础/路径/阵列/AB 族馈源/波导参数。"""
        app = self.app
        app.para('a', self.a)
        app.para('h', self.h)
        app.para('l1', self.l1)
        app.para('l2', self.l2)
        app.para('e1', self.e1)
        app.para('e2', self.e2)

        for index, path in enumerate(self.paths.values()):
            path.auto_define_cst_params(app, prefix=f'p{index}')

        xup, yup, ydn = self.modeler.array_range()
        self.xup, self.yup, self.ydn = int(xup), int(yup), int(ydn)
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

        if self.has_lens:
            # ⚠️ `Rbig` 三条路线都要：`generate`/`dxf` 把它用在"移到 0° 顶点"，
            #    就地路线用它做放置。缺了它们 `build_grin_lens*` 会提前抛
            #    ValueError（不是弹模态框 —— 那是更早版本的坑，见 docstring）。
            #    `Ls` 则**只有椭圆透镜路线**（generate/dxf 的楔形裁剪）要。
            spec = self.make_lens_spec()
            app.para('Rbig', f'{spec.r_big / self.a:g}*a',
                     expression='大六边形外接圆半径（透镜定位用）')
            # `Ls` **只有"要建椭圆透镜"的路线**要（`generate` / `dxf` 都有楔形裁剪）；
            # 就地路线没有楔形裁剪，登记它就是死写入（真机上会被
            # verify_model_parameter_usage 抓到）。
            if self.lens_method != 'insitu':
                app.para('Ls', '2.2*Rbig',
                         expression='楔形裁剪体边长（约定 2.2*Rbig）')
            app.para('dphi1', self.lens_phase[0] if self.lens_phase else 0,
                     expression='输出臂 1 的透镜相位角 [deg]')
            app.para('dphi2', self.lens_phase[1] if len(self.lens_phase) > 1 else 0,
                     expression='输出臂 2 的透镜相位角 [deg]')

        # 开关/泵浦区：半径与电导率只有**真的要建开关**时才登记（否则是死写入）
        if self.has_switch:
            app.para('rc1', self.switch_radius,
                     expression='开关圆柱半径 [mm]（参考 rc1=0.4）')
            app.para('sigma1', self.switch_sigma,
                     expression='开关材料电导率 [S/m]（开关态用 100/2000）')

    # ---- 建模 ----

    def build_all(self):
        """端到端建模：材料 → 多路径 VPC（含基板覆盖）→ 逐分支晶体 → 裁剪 → 馈源 → 波导 → 端口（→ 可选透镜）。"""
        if self.app is None:
            raise RuntimeError('CST 初始化失败，无法建模。')
        app = self.app
        self._define_all_params()
        build_materials(app)

        y_margin = f'{self.yup}*e2'
        from topo_modeler.builders import build_substrate_multi
        substrate = build_substrate_multi(app, self.paths, name='substrate',
                                          y_margin=y_margin)
        vpca, vpcb = self.modeler.build_vpc_regions(y_margin=y_margin)
        crystals = self.modeler.build_crystals_multi(topology=self.topology,
                                                    xup='xup', yup='yup',
                                                    ydn='ydn')
        clip = self.modeler.clip_crystals_with_vpc()

        feed_name = build_feed(app, feed_type=self.feed_type, name='feed1')
        wg_name = build_waveguide(app, name='wg1', material='Copper (annealed)')
        ports = add_multiport_port_set(app, [(wg_name, self.port_number,
                                             AXIAL_FACE)])

        app.add(vpca, feed_name)
        app.add(vpca, vpcb)

        # 开关/泵浦区（可选）：必须在 `vpc_A` 还"活着"的时候做（求交要拷它的副本）
        switches = []
        lens = None
        if self.has_switch:
            switches = self.build_switches(vpca=vpca)

        if self.has_lens:
            lens = self.build_lens()

        configure_solver(app, freq_range=self.freq_range, monitors=self.monitors)

        self._parts = {'substrate': substrate, 'vpca': vpca, 'vpcb': vpcb,
                       'crystals': crystals, 'clip': clip, 'feed': feed_name,
                       'wg1': wg_name, 'ports': ports, 'lens': lens,
                       'switches': switches}
        self._built = True
        return self

    def build_lens(self):
        """按选定的路线建透镜，并（给了两个相位角时）再转出一枚相位副本。

        * ``lens_method='dxf'``：导入孔阵列 DXF + 椭圆包络（`build_grin_lens_from_dxf`）；
        * ``lens_method='insitu'``：**不落 DXF**，在 CST 内逐个 `hexagon` 建环
          （`build_grin_lens_insitu`，孔集合由 `make_lens_ring()` 离线算）。

        ⚠️ 参考是**每个输出臂各放一枚**（各自 `rotation(..., dphiN)` + `translate`
        到臂端）；本模板只做「建 + 相位旋转」，**per-arm 定位尚未实现**
        （需要臂端定位，属 D1 的待补项，已在证据文档记录）。就地路线的 `place=True`
        只做「平移到 0° 顶点 + 绕原点旋转复制 ×5」（与 `GRINLensAntenna` 同口径），
        **不等于**参考的 per-arm 定位。
        """
        if self.lens_method == 'insitu':
            info = build_grin_lens_insitu(
                self.app, self.make_lens_ring(), name=self.lens_name,
                height='h', material='Silicon (lossy)',
                component=self.lens_component)
        else:
            dxf = self.lens_dxf
            if self.lens_method == 'generate':
                dxf = self.make_lens_dxf()
            info = build_grin_lens_from_dxf(app=self.app, dxf_path=dxf,
                                            spec=self.make_lens_spec(),
                                            name=self.lens_name,
                                            component=self.lens_component)
        self.lens_info = info
        if len(self.lens_phase) > 1:
            # ⚠️ 用**实际实体组件**，不是 `lens_component`：DXF 路线为了与旧脚本
            #    逐字节一致，透镜实体落在 `component1`（见 `build_grin_lens` 的
            #    `entity_component`）。按 `lens_component` 寻址会报
            #    `Shape does not exist: gridlens:lens_epc`（2026-09-17 真机）。
            self.app.rotation(self.lens_name, [0, 0, 1],
                              component=info.get('entity_component',
                                                 self.lens_component),
                              repetition=1, copy=True, unite=False)
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
        return {'split_ratio': self.split_ratio,
                'cascade': {'fan1': self.fan1, 'fan2': self.fan2},
                'topology': self.topology,
                'n_output_paths': len(self.output_paths()),
                'paths': {name: [[int(r), int(c)] for r, c in path.path_lattice]
                          for name, path in self.paths.items()},
                'array_range': [int(v) for v in self.modeler.array_range()],
                'port': self.port_number,
                'has_lens': self.has_lens,
                'lens_method': self.lens_method,
                'lens_phase': list(self.lens_phase),
                'lens': self.lens_summary(),
                'switch_mode': self.switch_mode,
                'switch_radius': self.switch_radius,
                'switch_sigma': self.switch_sigma,
                'switch_positions': self.switch_positions()}
