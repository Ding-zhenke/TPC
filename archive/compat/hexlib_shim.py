# -*- coding: utf-8 -*-
"""
⚠ 注意：此文件已迁移至 mesh_grid.hex_grid 包
=============================================
从 v2.0 开始，hexlib 已迁移为 mesh_grid.hex_grid 子包。

**该用哪个文件**：旧 notebook 写的是 `import hexlib`，所以真正顶用的是同目录下
**以旧名命名**的 [`hexlib.py`](./hexlib.py)（2026-09-17 补上 —— 此前只有本文件，
文件名带 `_shim`，于是 `import hexlib` 仍然报 `ModuleNotFoundError`）。
本文件保留旧文件名，内容改为转发到 `hexlib`，避免出现两份实现。

新代码推荐直接导入:
    from mesh_grid.hex_grid import HexLib, HexGridVisualizer

@author: PC
"""

from hexlib import *            # noqa: F401,F403   （告警由 hexlib.py 发出）
