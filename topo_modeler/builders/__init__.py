# -*- coding: utf-8 -*-
"""
topo_modeler.builders — 各部件构建器
====================================
基板、VPC区域、光子晶体阵列、探针、波导、透镜、端口、求解器等构建器。

@author: PC
"""

from topo_modeler.builders.substrate import build_substrate
from topo_modeler.builders.vpc_region import build_vpc_regions, intersect_vpc_with_substrate
from topo_modeler.builders.crystal import build_topological_crystal, intersect_crystal_with_vpc
from topo_modeler.builders.solver import configure_solver
from topo_modeler.builders.feed import (
    build_feed,
    build_ab_elliptical_feed,
    build_ba_tapered_feed,
    build_cylinder_feed,
)
from topo_modeler.builders.waveguide import build_waveguide
from topo_modeler.builders.port import (
    add_waveguide_port,
    add_ports_for_straight_waveguide,
    add_port_for_antenna,
)

__all__ = [
    # 基础 builders（阶段2）
    "build_substrate",
    "build_vpc_regions",
    "intersect_vpc_with_substrate",
    "build_topological_crystal",
    "intersect_crystal_with_vpc",
    "configure_solver",
    # 馈源 builders（阶段3）
    "build_feed",
    "build_ab_elliptical_feed",
    "build_ba_tapered_feed",
    "build_cylinder_feed",
    # 波导 builder（阶段3）
    "build_waveguide",
    # 端口 builders（阶段3）
    "add_waveguide_port",
    "add_ports_for_straight_waveguide",
    "add_port_for_antenna",
]
