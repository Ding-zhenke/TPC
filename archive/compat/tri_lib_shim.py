# -*- coding: utf-8 -*-
"""
⚠ 注意：此文件已迁移至 mesh_grid.tri_grid 包
=============================================
从 v2.0 开始，tri_lib 已迁移为 mesh_grid.tri_grid 子包。

为兼容旧代码，此文件作为兼容性入口，自动导入新包中的全部符号。
新代码推荐直接导入:
    from mesh_grid.tri_grid import build_triangle_lattice, plot_triangle_grid, ...

@author: PC
"""

import numpy as np
import matplotlib.pyplot as plt

import warnings
warnings.warn(
    "tri_lib 已迁移至 mesh_grid.tri_grid，"
    "推荐改用 'from mesh_grid.tri_grid import ...'",
    FutureWarning, stacklevel=2
)

# 从新包导入全部符号
from mesh_grid.tri_grid import *