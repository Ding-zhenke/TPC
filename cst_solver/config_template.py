# -*- coding: utf-8 -*-
"""
CST Studio Suite 配置模板文件
==============================
使用方法：
    1. 将本文件复制为 config.py
    2. 修改 CST_INSTALL_PATH 为本机 CST 安装路径
    3. config.py 已加入 .gitignore，不会同步到 GitHub

其他路径（Python库、材料库）会自动从 CST_INSTALL_PATH 推导。
    例如 CST_INSTALL_PATH = r"C:\SOFTWARE\CST Studio Suite 2026"
    则 CST_PYTHON_LIB   = CST_INSTALL_PATH + r"\AMD64\python_cst_libraries"
    则 CST_MATERIAL_LIB = CST_INSTALL_PATH + r"\Library\Materials"

@author: PC
"""

import os

# ============================================================
# ★ 唯一需要配置的项 —— 请修改为本机 CST 安装路径
# ============================================================

CST_INSTALL_PATH = r"C:\SOFTWARE\CST Studio Suite 2026"

# ============================================================
# 以下为自动推导，无需手动修改
# ============================================================

# CST Python 库路径
CST_PYTHON_LIB = os.path.join(CST_INSTALL_PATH, "AMD64", "python_cst_libraries")

# CST 材料库路径
CST_MATERIAL_LIB = os.path.join(CST_INSTALL_PATH, "Library", "Materials")

# 可选配置
DEFAULT_WORK_DIR = ""
CST_START_MODE = "Interactive"
