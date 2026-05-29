# -*- coding: utf-8 -*-
"""
mesh_grid.hex_grid — 六边形网格算法库
======================================
六边形网格的核心算法、可视化与 DXF 导出功能。

导出符号:
    HexLib — 六边形网格核心算法类
    HexGridVisualizer — 六边形网格可视化类
    create_hex_polygon — 创建 Shapely 六边形多边形
    save_to_dxf — 合并导出 DXF
    save_multi_dxf — 分组导出 DXF（多图层）
    read_and_display_dxf_matplotlib — 读取并显示 DXF

快速开始:
    >>> from mesh_grid.hex_grid import HexLib, HexGridVisualizer
    >>> lib = HexLib(hex_size=20, orientation="pointy")
    >>> grid = lib.create_staggered_grid((0, 5), (0, 4))
    >>> viz = HexGridVisualizer()
    >>> viz.set_grid(grid)
    >>> viz.draw()

@author: PC
"""

from mesh_grid.hex_grid.core import (
    HexLib,
    HexGridVisualizer,
    create_hex_polygon,
    save_to_dxf,
    save_multi_dxf,
    read_and_display_dxf_matplotlib,
)

__all__ = [
    "HexLib",
    "HexGridVisualizer",
    "create_hex_polygon",
    "save_to_dxf",
    "save_multi_dxf",
    "read_and_display_dxf_matplotlib",
]
