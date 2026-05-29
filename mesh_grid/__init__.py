# -*- coding: utf-8 -*-
"""
mesh_grid — 网格算法库
======================
提供六边形网格和三角形网格的生成、计算、可视化与导出功能。

子包:
    hex_grid — 六边形网格核心算法 (HexLib, HexGridVisualizer, DXF 导出等)
    tri_grid — 三角形网格核心算法 (网格生成、坐标转换、空间分析等)

导入本包时会自动加载子包，触发 matplotlib 中文字体等初始化。

@author: PC
"""

# 自动导入子包，确保 matplotlib 中文字体配置等初始化代码被执行
from mesh_grid import hex_grid, tri_grid
