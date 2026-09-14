# -*- coding: utf-8 -*-
"""
StraightWaveguide — 直波导端到端模板
====================================
第一个端到端模板，复现旧代码 AB_feed.ipynb / BA_feed.ipynb 的完整建模流程。

内部流程：
  1. 构建 TopoPath（直线路径）
  2. 定义 CST 参数（基础 + 路径 + 阵列 + feed + waveguide）
  3. build_substrate → build_vpc_regions → build_topological_crystal
  4. build_feed(ab_elliptical) → build_waveguide
  5. mirror(feed + waveguide 到右端)
  6. add_ports(2 个端口)
  7. integrate（合并 vpca + feed + vpcb）
  8. configure_solver

用户使用（约 10 行）：
    >>> from templates import StraightWaveguide
    >>> wg = StraightWaveguide(topology='AB', length=18, output_path=r'D:\out\wg.cst')
    >>> wg.preview()
    >>> wg.build_all()
    >>> wg.save()

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
    build_waveguide,
    add_ports_for_straight_waveguide,
    configure_solver,
)


class StraightWaveguide:
    """
    直波导端到端模板。

    :param topology: str, 'AB' 或 'BA'
    :param length: int, 波导长度（晶格数，不含起点偏移）
    :param width: int, 波导宽度（预留，当前由 VPC 区域决定）
    :param lattice_constant: float, 晶格常数 a (mm)
    :param height: float, 硅片厚度 h (mm)
    :param large_hole_ratio: float, 大孔比例（l1 = ratio * a）
    :param small_hole_ratio: float, 小孔比例（l2 = ratio * a）
    :param feed_type: str, 馈源类型（默认 'ab_elliptical'）
    :param freq_range: tuple, 频率范围 (fmin, fmax) GHz
    :param monitors: tuple, 监视器类型 ('E',) 或 ('E', 'Farfield')
    :param template_cst: str, CST 模板文件路径
    :param output_path: str, 输出 .cst 文件路径
    """

    def __init__(self, topology='AB', length=18, width=14,
                 lattice_constant=0.2425, height=0.25,
                 large_hole_ratio=0.65, small_hole_ratio=0.35,
                 feed_type='ab_elliptical',
                 x0=4, wf1=0.2, lf1=0.2, lf2=3.0, lf3=0.2,
                 wg_a=0.7312, wg_b=0.3756, wg_t=0.2,
                 freq_range=(300, 380), monitors=('E',),
                 template_cst='tmp.cst', output_path=None):
        """
        :param x0: float, 探针起点（晶格数），参考模型 AB_feed.ipynb 为 4
        :param wf1: float, 探针宽度（mm），参考为 0.2
        :param lf1: float, 探针长度 1（mm），参考为 0.2
        :param lf2: float, 椭圆过渡半轴（mm），参考为 3.0
        :param lf3: float, 探针长度 3（mm），参考为 0.2
        :param wg_a: float, 空心波导内腔 z 向高度（mm），参考为 0.7312
        :param wg_b: float, 空心波导内腔 y 向宽度（mm），参考为 0.3756
        :param wg_t: float, 波导壁厚（mm），参考为 0.2

        注：feed / waveguide 的默认值取自参考模型 ``AB_feed.ipynb`` 的 CST 参数，
        以保证默认参数下几何与参考工程一致（差异 < 0.1%）。
        """
        if topology not in ('AB', 'BA'):
            raise ValueError(f"topology 必须是 'AB' 或 'BA'，收到 '{topology}'")

        self.topology = topology
        self.length = length
        self.width = width
        self.a = lattice_constant
        self.h = height
        self.l1 = large_hole_ratio * self.a
        self.l2 = small_hole_ratio * self.a
        self.feed_type = feed_type
        self.freq_range = freq_range
        self.monitors = monitors
        self.template_cst = template_cst
        self.output_path = output_path

        # feed / waveguide 参数（默认值见 __init__ docstring）
        self.x0 = x0
        self.wf1 = wf1
        self.lf1 = lf1
        self.lf2 = lf2
        self.lf3 = lf3
        self.wg_a = wg_a
        self.wg_b = wg_b
        self.wg_t = wg_t

        # 三角晶格几何参数
        self.e1 = self.a / 2
        self.e2 = self.a * np.sqrt(3) / 2

        # 构建路径：起点 (0,-1)，沿 +c 走 length+1 步
        # 终点 c = -1 + (length+1) = length，与旧代码 x1=length 对应
        self.path = (TopoPath.builder(self.a, name='p')
                     .start(0, -1)
                     .move(length + 1, 'c')
                     .build())

        # 阵列范围
        self.xup, self.yup, self.ydn = self.path.get_array_range()

        # TopoModeler（智能推断 + 流水线）
        self.modeler = TopoModeler(template_cst=template_cst)
        self.modeler.set_path(self.path)
        self.modeler.set_parameters({
            'a': self.a, 'h': self.h,
            'l1': self.l1, 'l2': self.l2,
            'e1': self.e1, 'e2': self.e2,
        })
        self.app = self.modeler.app
        self.nm = NameManager()

        # 构建状态
        self._built = False

    # ---- CST 参数定义 ----

    def _define_all_params(self):
        """定义所有 CST 参数（基础 + 路径 + 阵列 + feed + waveguide）。"""
        app = self.app

        # 基础参数
        app.para('a', self.a)
        app.para('h', self.h)
        app.para('l1', self.l1)
        app.para('l2', self.l2)
        app.para('e1', self.e1)
        app.para('e2', self.e2)

        # 路径参数（p1x, p1y, p2x, p2y, ...）
        self.path.auto_define_cst_params(app, prefix='p')

        # 阵列范围
        app.para('xup', self.xup)
        app.para('yup', self.yup)
        app.para('ydn', self.ydn)

        # feed 参数（AB 型椭圆探针，默认值与参考模型 AB_feed.ipynb 一致）
        app.para('x0', self.x0)
        app.para('wf1', self.wf1)
        app.para('lf1', self.lf1)
        app.para('lf2', self.lf2)
        app.para('lf3', self.lf3)

        # waveguide 参数（铜波导尺寸，默认值与参考模型一致）
        app.para('wg_a', self.wg_a)
        app.para('wg_b', self.wg_b)
        app.para('wg_t', self.wg_t)

    # ---- 预览 ----

    def preview(self, ax=None, show_grid=True):
        """matplotlib 预览路径 + 晶格背景。"""
        return self.path.preview(ax=ax, show_grid=show_grid,
                                  label=f'StraightWaveguide ({self.topology}, L={self.length})')

    # ---- 端到端建模 ----

    def build_all(self):
        """
        端到端建模：参数定义 → 基板 → VPC → 晶体 → feed → waveguide → mirror → ports → 整合 → 求解器。
        """
        if self.app is None:
            raise RuntimeError("CST 初始化失败，无法建模。请检查 template_cst 路径。")

        app = self.app

        # 1. 定义所有 CST 参数
        self._define_all_params()

        # 2. 基板
        build_substrate(app, self.path, name='substrate')

        # 3. VPC 区域（A + B）
        #    注意：AB/BA 的大孔小孔分配由 build_topological_crystal 负责，
        #    build_vpc_regions 只按路径上/下半区生成区域，不接受 topology 参数。
        vpca_name, vpcb_name = build_vpc_regions(app, self.path)

        # 4. 光子晶体阵列
        build_topological_crystal(app, self.path, topology=self.topology,
                                   xup=self.xup, yup=self.yup, ydn=self.ydn)

        # 5. 馈源（AB 型椭圆探针）
        feed_name = build_feed(app, feed_type=self.feed_type, name='feed1')

        # 6. 空心矩形波导
        wg_name = build_waveguide(app, name='wg1')

        # 7. mirror feed + waveguide 到右端（中心点 p2x/2，法向量 x）
        mirror_center = ['p2x/2', '0', '0']
        app.mirror(feed_name, mirror_center, ['1', '0', '0'], copy=True, unite=True)
        app.mirror(wg_name, mirror_center, ['1', '0', '0'], copy=True, unite=True)

        # 8. 端口（2 个：入口 + 出口）
        add_ports_for_straight_waveguide(app, waveguide_name=wg_name)

        # 9. 整合：vpca + feed + vpcb
        app.add(vpca_name, feed_name)
        app.add(vpca_name, vpcb_name)

        # 10. 求解器配置
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
        # 库的求解入口是 setup.run()（下发 Solver 历史并启动仿真）。
        # 旧写法 self.app.start_solver() 在全库中并不存在，会抛 AttributeError。
        self.app.run()
        return self

    def __repr__(self):
        return (f"StraightWaveguide(topology='{self.topology}', length={self.length}, "
                f"a={self.a}, h={self.h}, built={self._built})")
