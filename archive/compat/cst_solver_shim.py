# -*- coding: utf-8 -*-
"""
⚠ 注意：cst_solver 已重构为 cst_solver/ 包
============================================
从 v2.0 开始，cst_solver 已从单文件重构为 Python 包（cst_solver/ 目录），
采用 Mixin 多继承模式组织代码。

此文件作为兼容性入口，自动导入新包中的 setup 和 result。
新代码推荐直接导入:
    from cst_solver import setup, result

@author: PC
"""

import warnings
warnings.warn(
    "cst_solver.py 已重构为 cst_solver/ 包，"
    "推荐改用 'from cst_solver import setup, result'",
    FutureWarning, stacklevel=2
)

from cst_solver import setup
from cst_solver.result import result
