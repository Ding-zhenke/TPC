# -*- coding: utf-8 -*-
"""
TopoModeler — 拓扑光子晶体核心建模器
====================================
智能推断 + 流水线编排，是所有模板的基类。

统一管理：路径(TopoPath)、拓扑相(AB/BA)、参数、建模流水线、仿真、结果读取。

@author: PC
"""

import os
import numpy as np

from topo_modeler.name_manager import NameManager
from topo_modeler.builders import (
    build_substrate,
    build_vpc_regions,
    build_topological_crystal,
    build_feed as _build_feed_func,
    build_waveguide as _build_waveguide_func,
    add_ports_for_straight_waveguide,
    add_port_for_antenna,
    configure_solver,
)


class TopoModeler:
    """
    拓扑光子晶体核心建模器。

    智能推断规则：
      - model_type: path.is_straight() → 'waveguide'，path.has_bend() → 'antenna'
      - topology: 波导默认 'AB'，天线默认 'BA'，可被用户参数覆盖
      - 端口数: 波导 2 端口，天线 1 端口
      - 监视器: 波导 E 场，天线 E 场 + Farfield

    使用示例:
        >>> from topo_modeler import TopoModeler
        >>> from mesh_grid.tri_grid import TopoPath
        >>> path = TopoPath.builder(a=0.2425).start(0, -1).move(19, 'c').build()
        >>> modeler = TopoModeler(template_cst='tmp.cst')
        >>> modeler.set_path(path)
        >>> modeler.set_topology('AB')
        >>> modeler.build_all()
        >>> modeler.save('waveguide.cst')
    """

    def __init__(self, template_cst='tmp.cst'):
        """
        初始化 TopoModeler。

        :param template_cst: str, CST 模板文件路径，默认 'tmp.cst'
        """
        self.template_cst = template_cst
        self.app = None
        self.path = None
        self.topology = None  # 'AB' / 'BA' / None(自动推断)
        self.model_type = None  # 'waveguide' / 'antenna' / None(自动推断)
        self.params = {}
        self.nm = NameManager()
        self._built_parts = {}  # 已构建的部件名称 {part_name: cst_name}
        self._cst_path = None

        # 延迟导入 cst_solver，避免在无 CST 环境下导入失败
        self._init_cst()

    def _init_cst(self):
        """初始化 CST 工程。"""
        try:
            from cst_solver import setup
            self.app = setup(self.template_cst)
        except Exception as e:
            # 无 CST 环境时（如单元测试），app 为 None
            self.app = None
            import warnings
            warnings.warn(f"CST 初始化失败（无 CST 环境？）: {e}。"
                          f"建模功能不可用，但路径/参数/推断功能可用。")

    # ================================================================
    # 配置方法
    # ================================================================

    def set_path(self, path):
        """
        设置拓扑路径，自动推断 model_type。

        :param path: TopoPath 实例
        :return: self（支持链式调用）
        """
        self.path = path
        self.model_type = self._infer_model_type()
        # 如果 topology 未设置，自动推断
        if self.topology is None:
            self.topology = self._infer_topology()
        return self

    def set_topology(self, topology):
        """
        设置拓扑相。

        :param topology: str, 'AB' 或 'BA'
        :return: self
        """
        if topology not in ('AB', 'BA'):
            raise ValueError(f"topology 必须是 'AB' 或 'BA'，收到 '{topology}'")
        self.topology = topology
        return self

    def set_parameters(self, params):
        """
        批量设置 CST 参数。

        cst_solver 的批量接口有两套签名，这里用的是**字典式**：
        ``app.paras({名称: 值}, None)`` —— ``paras(name, value, log_flag=0)``
        在 ``name`` 为 dict 时会忽略 ``value``。
        注意不要写成 ``app.set_parameters(params)``：那是
        ``set_parameters(name, value, log_flag=0)``，需要一个 dict 会直接抛 TypeError。

        :param params: dict, {参数名: 参数值, ...}
        :return: self
        """
        self.params.update(params)
        if self.app is not None:
            self.app.paras(params, None)
        return self

    def set_parameter(self, name, value):
        """
        设置单个 CST 参数。

        :param name: str, 参数名
        :param value: float/str, 参数值
        :return: self
        """
        self.params[name] = value
        if self.app is not None:
            self.app.para(name, value)
        return self

    # ================================================================
    # 智能推断
    # ================================================================

    def _infer_model_type(self):
        """从 path 判断模型类型：直线路径 → 波导，有拐弯 → 天线。"""
        if self.path is None:
            return None
        if self.path.is_straight():
            return 'waveguide'
        return 'antenna'

    def _infer_topology(self):
        """推断默认拓扑相：波导默认 AB，天线默认 BA。"""
        if self.model_type == 'waveguide':
            return 'AB'
        return 'BA'

    def _infer_monitors(self):
        """推断监视器类型：波导 E 场，天线 E 场 + Farfield。"""
        if self.model_type == 'waveguide':
            return ('E',)
        return ('E', 'Farfield')

    def _infer_ports(self):
        """推断端口数：波导 2 端口，天线 1 端口。"""
        if self.model_type == 'waveguide':
            return 2
        return 1

    # ================================================================
    # 流水线方法（按顺序调用 builders）
    # ================================================================

    def build_substrate(self, name='substrate', height='h',
                        material='Silicon (lossy)', y_margin='e2'):
        """
        构建基板。

        :param name: str, 基板名称
        :param height: str, 厚度参数名
        :param material: str, 材料
        :param y_margin: str, 半宽参数名
        :return: str, 基板 CST 名称
        """
        self._check_path()
        cst_name = build_substrate(self.app, self.path, name=name, height=height,
                                    material=material, y_margin=y_margin)
        self._built_parts['substrate'] = cst_name
        return cst_name

    def build_vpc_regions(self, name_prefix='vpc', height='h',
                           material='Silicon (lossy)', y_margin='e2'):
        """
        构建 VPC-A 和 VPC-B 区域。

        :param name_prefix: str, 名称前缀
        :param height: str, 厚度参数名
        :param material: str, 材料
        :param y_margin: str, 扩展量参数名
        :return: tuple, (vpca_name, vpcb_name)
        """
        self._check_path()
        vpca, vpcb = build_vpc_regions(self.app, self.path, name_prefix=name_prefix,
                                         height=height, material=material, y_margin=y_margin)
        self._built_parts['vpca'] = vpca
        self._built_parts['vpcb'] = vpcb
        return vpca, vpcb

    def build_crystal(self, topology=None, lattice='a', height='h',
                      large_hole='l1', small_hole='l2', y_margin='e2'):
        """
        构建光子晶体三角孔阵列。

        :param topology: str, 'AB'/'BA'，默认使用 self.topology
        :param lattice: str, 晶格常数参数名
        :param height: str, 厚度参数名
        :param large_hole: str, 大孔参数名
        :param small_hole: str, 小孔参数名
        :param y_margin: str, Y方向步长参数名
        :return: tuple, (crystal_a_name, crystal_b_name)
        """
        self._check_path()
        topo = topology or self.topology or 'AB'
        ca, cb = build_topological_crystal(self.app, self.path, topology=topo,
                                            lattice=lattice, height=height,
                                            large_hole=large_hole, small_hole=small_hole,
                                            y_margin=y_margin)
        self._built_parts['crystal_a'] = ca
        self._built_parts['crystal_b'] = cb
        return ca, cb

    def build_feed(self, feed_type=None, name=None, **params):
        """
        构建探针/馈电。

        智能推断：waveguide 默认 'ab_elliptical'，antenna 默认 'ba_tapered'。

        :param feed_type: str, 'ab_elliptical' / 'ba_tapered' / 'cylinder'
        :param name: str, 馈源名称（None 则按类型默认）
        :param params: 传递给 build_feed 的额外参数
        :return: str, 馈源 CST 名称
        """
        self._check_path()
        if feed_type is None:
            feed_type = 'ab_elliptical' if self.model_type == 'waveguide' else 'ba_tapered'
        cst_name = _build_feed_func(self.app, feed_type=feed_type, name=name, **params)
        self._built_parts['feed'] = cst_name
        return cst_name

    def build_waveguide(self, name='wg1', material='Copper (annealed)', **params):
        """
        构建空心矩形波导（外方体 - 内方体）。

        :param name: str, 波导名称
        :param material: str, 材料
        :param params: 传递给 build_waveguide 的额外参数
        :return: str, 波导 CST 名称
        """
        self._check_path()
        cst_name = _build_waveguide_func(self.app, name=name, material=material, **params)
        self._built_parts['waveguide'] = cst_name
        return cst_name

    def build_lens(self, lens_type='grin', method='hexagon', **params):
        """
        构建 GRIN 透镜。

        注意：阶段 2 暂未实现，将在阶段 4 完成。

        :raises NotImplementedError: 阶段 2 未实现
        """
        raise NotImplementedError("build_lens 将在阶段 4 实现")

    def add_ports(self, auto=True, waveguide_name=None, **params):
        """
        添加波导端口。

        智能推断：waveguide 2 端口，antenna 1 端口。

        :param auto: bool, 是否自动推断端口数
        :param waveguide_name: str, 波导 solid 名称（默认 'wg1'）
        :param params: 额外参数
        :return: list, 端口编号列表
        """
        self._check_path()
        wg = waveguide_name or self._built_parts.get('waveguide', 'wg1')
        if self.model_type == 'waveguide':
            p1, p2 = add_ports_for_straight_waveguide(self.app, waveguide_name=wg)
            self._built_parts['ports'] = [p1, p2]
            return [p1, p2]
        else:
            p1 = add_port_for_antenna(self.app, waveguide_name=wg)
            self._built_parts['ports'] = [p1]
            return [p1]

    def configure_solver(self, freq_range=(300, 380), monitors=None, **kwargs):
        """
        配置求解器。

        :param freq_range: tuple, (fmin, fmax)
        :param monitors: tuple, 监视器类型，默认自动推断
        :param kwargs: 其他参数（steady_state, parallel_threads, gpus 等）
        """
        if monitors is None:
            monitors = self._infer_monitors()
        configure_solver(self.app, freq_range=freq_range, monitors=monitors, **kwargs)
        self._built_parts['solver'] = True

    def integrate(self):
        """
        整合所有部件（布尔加）。

        阶段 2 基础整合：基板 + VPC 区域 + 晶体阵列。
        阶段 3/4 将扩展探针、波导、透镜的整合。
        """
        # 基础整合由各 builder 内部完成（add/subtract/intersect）
        # 这里预留统一整合接口
        pass

    # ================================================================
    # 端到端方法
    # ================================================================

    def build_all(self, freq_range=(300, 380), include_feed=True,
                  include_waveguide=True, include_ports=True, **kwargs):
        """
        按顺序执行全部建模步骤。

        顺序：基板 → VPC区域 → 光子晶体阵列 → 馈源 → 波导 → 端口 → 求解器配置

        :param freq_range: tuple, 频率范围
        :param include_feed: bool, 是否构建馈源
        :param include_waveguide: bool, 是否构建波导
        :param include_ports: bool, 是否添加端口
        :param kwargs: 传递给各 builder 的参数
        :return: self
        """
        self.build_substrate(**kwargs.get('substrate_kw', {}))
        self.build_vpc_regions(**kwargs.get('vpc_kw', {}))
        self.build_crystal(**kwargs.get('crystal_kw', {}))
        if include_feed:
            self.build_feed(**kwargs.get('feed_kw', {}))
        if include_waveguide:
            self.build_waveguide(**kwargs.get('waveguide_kw', {}))
        if include_ports:
            self.add_ports(**kwargs.get('port_kw', {}))
        self.configure_solver(freq_range=freq_range, **kwargs.get('solver_kw', {}))
        self.integrate()
        return self

    def save(self, path):
        """
        保存 CST 工程。

        :param path: str, 保存路径
        :return: self
        """
        if self.app is not None:
            self.app.save(path)
        self._cst_path = path
        return self

    def run(self):
        """
        运行仿真。

        :return: self
        """
        if self.app is not None:
            self.app.run()
        return self

    def preview(self, ax=None, show_grid=True):
        """
        预览路径（matplotlib）。

        :param ax: matplotlib Axes, 默认新建
        :param show_grid: bool, 是否显示晶格背景
        :return: tuple, (fig, ax)
        """
        self._check_path()
        return self.path.preview(ax=ax, show_grid=show_grid)

    def read_results(self):
        """
        读取仿真结果。

        注意：阶段 2 暂未实现，将在阶段 5（工具层）完成。

        :raises NotImplementedError: 阶段 2 未实现
        """
        raise NotImplementedError("read_results 将在阶段 5 实现（ResultReader）")

    def plot_results(self):
        """
        自动绘制结果图。

        注意：阶段 2 暂未实现，将在阶段 5 完成。

        :raises NotImplementedError: 阶段 2 未实现
        """
        raise NotImplementedError("plot_results 将在阶段 5 实现")

    # ================================================================
    # 工具方法
    # ================================================================

    def _check_path(self):
        """检查 path 是否已设置。"""
        if self.path is None:
            raise RuntimeError("请先调用 set_path() 设置拓扑路径")

    def get_built_parts(self):
        """返回已构建的部件名称字典。"""
        return dict(self._built_parts)

    def __repr__(self):
        parts = ', '.join(self._built_parts.keys()) or 'none'
        return (f"TopoModeler(type={self.model_type}, topology={self.topology}, "
                f"path={len(self.path) if self.path else 0}pts, built=[{parts}])")
