# -*- coding: utf-8 -*-
"""
mesh_grid — 网格算法库
======================
提供六边形网格和三角形网格的生成、计算、可视化与导出功能。

子包:
    hex_grid — 六边形网格核心算法 (HexLib, HexGridVisualizer, DXF 导出等)
    tri_grid — 三角形网格核心算法 (网格生成、坐标转换、空间分析等)

子包按需加载；导入时不修改 matplotlib 字体，也不要求 DXF 可选依赖。

@author: PC
"""

import importlib

__all__ = ['hex_grid', 'tri_grid', 'plotting']


def __getattr__(name):
    if name in __all__:
        module = importlib.import_module(f'{__name__}.{name}')
        globals()[name] = module
        return module
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
