# -*- coding: utf-8 -*-
"""
topo_modeler — 拓扑光子晶体建模引擎
====================================
智能推断 + 流水线编排，统一坐标管理，自动化建模。

快速开始:
    >>> from topo_modeler import TopoModeler, NameManager
    >>> from mesh_grid.tri_grid import TopoPath
    >>>
    >>> path = TopoPath.builder(a=0.2425).start(0, -1).move(19, 'c').build()
    >>> modeler = TopoModeler(template_cst='tmp.cst')
    >>> modeler.set_path(path)
    >>> modeler.set_topology('AB')
    >>> modeler.build_all()
    >>> modeler.save('waveguide.cst')

@author: PC
"""

from topo_modeler.name_manager import NameManager
from topo_modeler.modeler import TopoModeler

__all__ = [
    "NameManager",
    "TopoModeler",
]
