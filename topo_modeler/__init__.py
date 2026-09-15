# -*- coding: utf-8 -*-
"""
topo_modeler — 拓扑光子晶体建模引擎
====================================
智能推断 + 流水线编排，统一坐标管理，自动化建模；
外加阶段 7 的工具层（配置 / 结果读取 / 报告 / 审计）。

快速开始:
    >>> from topo_modeler import TopoModeler, NameManager
    >>> from mesh_grid.tri_grid import TopoPath
    >>>
    >>> path = TopoPath.builder(a=0.2425).start(0, 0).move(18, 'c').build()
    >>> modeler = TopoModeler(template_cst='tmp.cst')
    >>> modeler.set_path(path)
    >>> modeler.set_topology('AB')
    >>> modeler.build_all()
    >>> modeler.save('waveguide.cst')

阶段 7 工具层（都放在**子模块**里，不进包顶层的 `__all__`）:

    topo_modeler.config          YAML 配置驱动（load_config / validate_config / 工厂）
    topo_modeler.result_reader   结果读取与自动出图（ResultReader）
    topo_modeler.report          自包含 HTML 报告引擎（HtmlReport）
    topo_modeler.audit           审计落盘（AuditLog）

这些子模块**都不需要 CST 才能 import**：只有真的去读 .cst / 建实例时才用得上。

@author: PC
"""

from topo_modeler.name_manager import NameManager
from topo_modeler.modeler import TopoModeler

__all__ = [
    "NameManager",
    "TopoModeler",
]
