# -*- coding: utf-8 -*-
r"""
hexlib — **旧包名的兼容入口**（转发到 `mesh_grid.hex_grid`）
============================================================

与 `tri_lib.py` 同理：`archive/compat/` 下原本只有 `hexlib_shim.py`，
旧 notebook 里的 `import hexlib` 会报 `ModuleNotFoundError`
（实测：2026-09-17，41 个 notebook 用 `hexlib`）。

用法（不改 notebook 正文）::

    import sys
    sys.path.append(r'<TPC 仓库根>\archive\compat')
    from hexlib import HexLib, HexGridVisualizer, create_hex_polygon

新代码请直接用 `mesh_grid.hex_grid`。

@author: PC
"""

import warnings

warnings.warn(
    "hexlib 已迁移至 mesh_grid.hex_grid，请改用 "
    "'from mesh_grid.hex_grid import ...'；本兼容入口只保留一个版本周期。",
    FutureWarning, stacklevel=2)

# 旧 notebook 实际用到的名字（由 scripts/check_notebook_imports.py 扫出来）：
#   HexLib / HexGridVisualizer / create_hex_polygon / save_to_dxf /
#   read_and_display_dxf_matplotlib（另有 `import *`）
from mesh_grid.hex_grid import *                     # noqa: F401,F403,E402
from mesh_grid.hex_grid import (                     # noqa: F401,E402
    HexLib,
    HexGridVisualizer,
    create_hex_polygon,
    read_and_display_dxf_matplotlib,
    save_to_dxf,
)
