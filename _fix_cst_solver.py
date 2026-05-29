# -*- coding: utf-8 -*-
"""修复 cst_solver.py — 清除残留的旧 VBA 代码"""
content = '''# -*- coding: utf-8 -*-
"""
\u26a0 注意：此文件已重构为 cst_solver/ 包
========================================
从 v2.0 开始，cst_solver 已重构为 Python 包（cst_solver/ 目录），
采用 Mixin 多继承模式组织代码。

为兼容旧代码，此文件作为兼容性入口，自动导入新包中的 setup 和 result。
新代码推荐直接导入:
    from cst_solver import setup, result

@author: PC
"""

import warnings
warnings.warn(
    "cst_solver.py \u5df2\u91cd\u6784\u4e3a cst_solver/ \u5305\uff0c"
    "\u63a8\u8350\u6539\u7528 'from cst_solver import setup, result'",
    FutureWarning, stacklevel=2
)

from cst_solver import setup
from cst_solver.result import result
'''
with open(r'd:\成电博士生涯\自动建模算法尝试\TPC\cst_solver.py', 'w', encoding='utf-8') as f:
    f.write(content.strip())
print('cst_solver.py has been rewritten successfully')
