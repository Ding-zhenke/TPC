# -*- coding: utf-8 -*-
"""
tpc_toolkit — TPC 独立工具层（不依赖 CST）
==========================================
收纳与具体电磁仿真软件无关的通用算法与数据处理工具，
可在任意装有 numpy / matplotlib 的 Python 环境中导入，
**不需要安装 CST Studio Suite**。

子模块:
    s2p               — CST 导出的 S 参数（s2p 分组文本）解析与筛选
    ga_optimizer      — 面向拓扑优化的遗传算法算子与种群可视化
    effective_medium  — 六边形晶格面积、等效介电常数与折射率换算

与其它包的关系:
    cst_solver     → CST 会话封装（需要 CST 安装）
    mesh_grid      → 晶格/网格算法（纯计算）
    topo_modeler   → 建模引擎（依赖 cst_solver + mesh_grid）
    templates      → 端到端模板（依赖 topo_modeler）
    tpc_toolkit    → 数据与优化工具（本包，独立）

快速开始:
    >>> from tpc_toolkit.s2p import read_s2p_groups
    >>> data, labels = read_s2p_groups('AB-s21.txt')

@author: PC
"""

from tpc_toolkit import effective_medium, ga_optimizer, s2p

__all__ = [
    "s2p",
    "ga_optimizer",
    "effective_medium",
]
