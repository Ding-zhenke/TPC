# -*- coding: utf-8 -*-
r"""
tri_lib — **旧包名的兼容入口**（转发到 `mesh_grid.tri_grid`）
============================================================

为什么存在这个**具体文件名**
----------------------------
`archive/compat/` 下原本只有 `tri_lib_shim.py` —— 名字里带 `_shim`，
于是旧 notebook 里的 `import tri_lib` / `from tri_lib import *` **依然报
`ModuleNotFoundError`**（实测：2026-09-17，58 个 notebook 用 `tri_lib`）。

本文件以**旧名**命名，因此这条迁移路径真的成立::

    import sys
    sys.path.append(r'<TPC 仓库根>\archive\compat')
    from tri_lib import *          # ⚠️ 已弃用，会发 FutureWarning

新代码请直接用::

    from mesh_grid.tri_grid import TopoPath, build_triangle_lattice, ...

@author: PC
"""

import warnings

warnings.warn(
    "tri_lib 已迁移至 mesh_grid.tri_grid，请改用 "
    "'from mesh_grid.tri_grid import ...'；本兼容入口只保留一个版本周期。",
    FutureWarning, stacklevel=2)

# 旧代码用 `from tri_lib import *`（实测 58 个 notebook 都是这种写法），
# 因此这里必须星号转发；同时显式列出常用名字，改名时能立刻报错。
from mesh_grid.tri_grid import *                     # noqa: F401,F403,E402
from mesh_grid.tri_grid import (                     # noqa: F401,E402
    TopoPath,
    build_triangle_lattice,
    color_triangles,
    plot_triangle_grid,
)
