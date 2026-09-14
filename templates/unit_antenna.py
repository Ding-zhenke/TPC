# -*- coding: utf-8 -*-
"""
UnitAntenna — 单元天线端到端模板
================================
复现旧代码 Ant1_D_BA_120D / Ant3_epc 等单元天线的完整建模流程。

内部流程：
  1. 构建 TopoPath（直段 + 拐弯 + 臂）
  2. 定义 CST 参数
  3. build_substrate → build_vpc_regions → build_topological_crystal
  4. build_feed(ba_tapered) → build_waveguide
  5. 可选：圆柱辐射体
  6. add_port(1 个端口)
  7. integrate
  8. configure_solver（含 Farfield）

用户使用：
    >>> from templates import UnitAntenna
    >>> ant = UnitAntenna(bend_angle=120, straight_length=18, arm_length=14,
    ...                   output_path=r'D:\out\ant.cst')
    >>> ant.preview()
    >>> ant.build_all()
    >>> ant.save()

@author: PC
"""

import os
import numpy as np
from typing import Optional, Tuple

from mesh_grid.tri_grid import TopoPath
from topo_modeler import TopoModeler, NameManager
from topo_modeler.builders import (
    build_substrate,
    build_vpc_regions,
    build_topological_crystal,
    build_feed,
    build_cylinder_feed,
    build_waveguide,
    add_port_for_antenna,
    configure_solver,
)


class UnitAntenna:
    """
    单元天线端到端模板（直段 + 拐弯 + 臂 + 辐射体）。

    :param bend_angle: int, 拐弯角度（60 的倍数，0 表示直波导型天线）
    :param straight_length: int, 直段长度（晶格数）
    :param arm_length: int, 臂长（拐弯后长度，晶格数）
    :param topology: str, 'AB' 或 'BA'（默认 'BA'，天线常用）
    :param lattice_constant: float, 晶格常数 a (mm)
    :param height: float, 硅片厚度 h (mm)
    :param large_hole_ratio: float, 大孔比例
    :param small_hole_ratio: float, 小孔比例
    :param feed_type: str, 馈源类型（默认 'ba_tapered'）
    :param radiator: str, 辐射体类型（None / 'cylinder'）
    :param radiator_radius: float, 圆柱辐射体半径 (mm)
    :param freq_range: tuple, 频率范围
    :param monitors: tuple, 监视器（默认含 Farfield）
    :param template_cst: str, CST 模板文件
    :param output_path: str, 输出路径
    """

    def __init__(self, bend_angle=120, straight_length=18, arm_length=14,
                 topology='BA', lattice_constant=0.2425, height=0.25,
                 large_hole_ratio=0.65, small_hole_ratio=0.35,
                 feed_type='ba_tapered',
                 radiator=None, radiator_radius=0.3,
                 wg_a=0.7312, wg_b=0.3756, wg_t=0.2,
                 freq_range=(300, 380), monitors=('E', 'Farfield'),
                 template_cst='tmp.cst', output_path=None):
        """
        :param radiator: str/None, 辐射体类型（None 或 'cylinder'）
        :param radiator_radius: float, 圆柱辐射体半径（mm）
        :param wg_a: float, 空心波导内腔 z 向高度（mm），参考模型为 0.7312
        :param wg_b: float, 空心波导内腔 y 向宽度（mm），参考模型为 0.3756
        :param wg_t: float, 波导壁厚（mm），参考模型为 0.2
        """
        if topology not in ('AB', 'BA'):
            raise ValueError(f"topology 必须是 'AB' 或 'BA'，收到 '{topology}'")
        if bend_angle != 0 and bend_angle % 60 != 0:
            raise ValueError(f"bend_angle 必须是 60 的倍数，收到 {bend_angle}")

        self.bend_angle = bend_angle
        self.straight_length = straight_length
        self.arm_length = arm_length
        self.topology = topology
        self.a = lattice_constant
        self.h = height
        self.l1 = large_hole_ratio * self.a
        self.l2 = small_hole_ratio * self.a
        self.feed_type = feed_type
        self.radiator = radiator
        self.radiator_radius = radiator_radius
        self.freq_range = freq_range
        self.monitors = monitors
        self.template_cst = template_cst
        self.output_path = output_path

        # 空心波导参数（默认值取自参考模型，保证默认参数下几何一致）
        self.wg_a = wg_a
        self.wg_b = wg_b
        self.wg_t = wg_t

        # 三角晶格几何参数
        self.e1 = self.a / 2
        self.e2 = self.a * np.sqrt(3) / 2

        # 构建路径：起点 (0,-1) → 直段 → 拐弯 → 臂
        b = (TopoPath.builder(self.a, name='p')
             .start(0, -1)
             .move(straight_length + 1, 'c'))
        if bend_angle != 0:
            b.turn(bend_angle).move(arm_length + 1, 'along')
        self.path = b.build()

        # 阵列范围
        self.xup, self.yup, self.ydn = self.path.get_array_range()

        # TopoModeler
        self.modeler = TopoModeler(template_cst=template_cst)
        self.modeler.set_path(self.path)
        self.modeler.set_parameters({
            'a': self.a, 'h': self.h,
            'l1': self.l1, 'l2': self.l2,
            'e1': self.e1, 'e2': self.e2,
        })
        self.app = self.modeler.app
        self.nm = NameManager()

        self._built = False

    # ---- CST 参数定义 ----

    def _define_all_params(self):
        """定义所有 CST 参数。"""
        app = self.app

        # 基础参数
        app.para('a', self.a)
        app.para('h', self.h)
        app.para('l1', self.l1)
        app.para('l2', self.l2)
        app.para('e1', self.e1)
        app.para('e2', self.e2)

        # 路径参数
        self.path.auto_define_cst_params(app, prefix='p')

        # 阵列范围
        app.para('xup', self.xup)
        app.para('yup', self.yup)
        app.para('ydn', self.ydn)

        # BA 型 feed 参数（默认值与参考模型 Ant1_D_BA_120D_circle_DF.ipynb 一致）
        app.para('x01', 0)
        app.para('wf2', 0.2)
        app.para('lf4', 0.2)
        app.para('lf5', 3.0)

        # waveguide 参数
        app.para('wg_a', self.wg_a)
        app.para('wg_b', self.wg_b)
        app.para('wg_t', self.wg_t)

    # ---- 预览 ----

    def preview(self, ax=None, show_grid=True):
        """matplotlib 预览。"""
        return self.path.preview(ax=ax, show_grid=show_grid,
                                  label=f'UnitAntenna ({self.topology}, {self.bend_angle}°, '
                                        f'L={self.straight_length}, arm={self.arm_length})')

    # ---- 端到端建模 ----

    def build_all(self):
        """端到端建模。"""
        if self.app is None:
            raise RuntimeError("CST 初始化失败，无法建模。")

        app = self.app

        # 1. 定义所有 CST 参数
        self._define_all_params()

        # 2. 基板
        build_substrate(app, self.path, name='substrate')

        # 3. VPC 区域
        #    注意：AB/BA 的大孔小孔分配由 build_topological_crystal 负责，
        #    build_vpc_regions 只按路径上/下半区生成区域，不接受 topology 参数。
        vpca_name, vpcb_name = build_vpc_regions(app, self.path)

        # 4. 光子晶体阵列
        build_topological_crystal(app, self.path, topology=self.topology,
                                   xup=self.xup, yup=self.yup, ydn=self.ydn)

        # 5. 馈源（BA 型对称渐变）
        feed_name = build_feed(app, feed_type=self.feed_type, name='feed2')

        # 6. 空心矩形波导
        wg_name = build_waveguide(app, name='wg1')

        # 7. 可选辐射体（圆柱）
        if self.radiator == 'cylinder':
            # 辐射体位于路径末端
            end_xy = self.path.xy[-1]
            cyl_name = build_cylinder_feed(
                app, name='radiator', radius=self.radiator_radius,
                position=[str(end_xy[0]), str(end_xy[1]), '-h/2'],
            )
            app.add(vpca_name, cyl_name)

        # 8. 端口（仅 1 个入口）
        add_port_for_antenna(app, waveguide_name=wg_name)

        # 9. 整合
        app.add(vpca_name, feed_name)
        app.add(vpca_name, vpcb_name)

        # 10. 求解器（含 Farfield）
        configure_solver(app, freq_range=self.freq_range, monitors=self.monitors)

        self._built = True
        return self

    # ---- 保存 / 运行 ----

    def save(self, output_path=None):
        """保存 .cst 文件。"""
        path = output_path or self.output_path
        if path is None:
            raise ValueError("请指定 output_path")
        if not self._built:
            self.build_all()
        self.app.cst_file.save(path, include_results=False, allow_overwrite=True)
        print(f"已保存: {path}")
        return path

    def run(self):
        """运行仿真。"""
        if not self._built:
            self.build_all()
        # 库的求解入口是 setup.run()；旧写法 self.app.start_solver() 在全库中不存在。
        self.app.run()
        return self

    def __repr__(self):
        return (f"UnitAntenna(topology='{self.topology}', bend={self.bend_angle}°, "
                f"L={self.straight_length}, arm={self.arm_length}, built={self._built})")
