# -*- coding: utf-8 -*-
"""
初始化脚本 — 将项目根目录和 CST Python 库路径添加到 sys.path
==============================================================
在导入其他模块前先运行此脚本，或将其添加到 Python 启动脚本中。
用户只需在 cst_solver/config.py 中配置 CST_INSTALL_PATH，
Python 库路径和材料库路径会自动推导。

@author: PC
"""

import sys
import os

# ============================================================
# 添加当前工作目录到系统路径（确保 cst_solver 包可导入）
# ============================================================
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

# ============================================================
# CST Python 库路径 — 自动从 cst_solver 配置读取
# 配置优先顺序: config.py > config_template.py > 默认推导
# ============================================================
_DEFAULT_CST = r"C:\SOFTWARE\CST Studio Suite 2026"

try:
    from cst_solver.config import CST_INSTALL_PATH
except ImportError:
    try:
        from cst_solver.config_template import CST_INSTALL_PATH
    except ImportError:
        CST_INSTALL_PATH = _DEFAULT_CST
        print("⚠ 未找到 cst_solver/config.py，使用默认 CST 路径")
        print("   请复制 cst_solver/config_template.py 为 config.py 并修改 CST_INSTALL_PATH")

# 自动推导 Python 库路径
CST_PYTHON_LIB = os.path.join(CST_INSTALL_PATH, "AMD64", "python_cst_libraries")

if CST_PYTHON_LIB not in sys.path:
    sys.path.append(CST_PYTHON_LIB)
    print(f"✅ CST Python 库路径: {CST_PYTHON_LIB}")