# -*- coding: utf-8 -*-
"""
topo_modeler.builders — 各部件构建器
====================================
基板、VPC区域、光子晶体阵列、探针、波导、透镜、端口、求解器等构建器。

@author: PC
"""

from topo_modeler.builders.substrate import build_substrate, build_substrate_multi
from topo_modeler.builders.materials import build_materials, DEFAULT_MATERIALS
from topo_modeler.builders.vpc_region import (
    build_vpc_regions,
    build_vpc_regions_multi,
    intersect_vpc_with_substrate,
)
from topo_modeler.builders.crystal import (
    build_topological_crystal,
    build_crystals_multi,
    clip_crystals_with_vpc,
    intersect_crystal_with_vpc,
    repeat_expression,
)
from topo_modeler.builders.solver import configure_solver
from topo_modeler.builders.feed import (
    build_feed,
    build_ab_elliptical_feed,
    build_ba_tapered_feed,
    build_cylinder_feed,
    register_multiport_params,
    build_multiport_waveguide,
    MULTIPORT_FAMILY_PARAMS,
    MULTIPORT_WG_X_MIN,
    MULTIPORT_WG_X_MAX,
)
from topo_modeler.builders.waveguide import build_waveguide
from topo_modeler.builders.lens import (
    GrinLensSpec,
    GrinLensHoles,
    LensGeometryError,
    build_grin_lens_holes,
    build_grin_lens,
    build_grin_lens_from_dxf,
    grin_ring_holes,
    build_grin_lens_insitu,
    DEFAULT_RING_LAYERS,
    DEFAULT_D0_LAYERS,
    grin_lens_spec_from_cst_params,
    D_OUT_MODES,
)
from topo_modeler.builders.port import (
    add_waveguide_port,
    add_ports_for_straight_waveguide,
    add_port_for_antenna,
    add_multiport_port_set,
)

__all__ = [
    # 材料（建模前置，阶段3补充）
    "build_materials",
    "DEFAULT_MATERIALS",
    # 基础 builders（阶段2）
    "build_substrate",
    "build_substrate_multi",
    "build_vpc_regions",
    "build_vpc_regions_multi",
    "intersect_vpc_with_substrate",
    "build_topological_crystal",
    "build_crystals_multi",
    "clip_crystals_with_vpc",
    "intersect_crystal_with_vpc",
    "repeat_expression",
    "configure_solver",
    # 馈源 builders（阶段3）
    "build_feed",
    "build_ab_elliptical_feed",
    "build_ba_tapered_feed",
    "build_cylinder_feed",
    # 多端口馈源族（P5，2026-09-17）
    "register_multiport_params",
    "build_multiport_waveguide",
    "MULTIPORT_FAMILY_PARAMS",
    "MULTIPORT_WG_X_MIN",
    "MULTIPORT_WG_X_MAX",
    # 波导 builder（阶段3）
    "build_waveguide",
    # 透镜 builder（阶段6）
    "GrinLensSpec",
    "GrinLensHoles",
    "LensGeometryError",
    "grin_lens_spec_from_cst_params",
    "build_grin_lens_holes",
    "build_grin_lens",
    "build_grin_lens_from_dxf",
    "grin_ring_holes",
    "build_grin_lens_insitu",
    "DEFAULT_RING_LAYERS",
    "DEFAULT_D0_LAYERS",
    "D_OUT_MODES",
    # 端口 builders（阶段3）
    "add_waveguide_port",
    "add_ports_for_straight_waveguide",
    "add_port_for_antenna",
    "add_multiport_port_set",
]
