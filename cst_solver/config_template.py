# -*- coding: utf-8 -*-
"""
CST Studio Suite 配置模板文件
==============================
使用方法：
    推荐通过环境变量 CST_INSTALL_PATH 或 CST_CONFIG_FILE（JSON）配置，
    无需修改已安装的 Python 包。以下复制方式保留兼容。
    1. 将本文件复制为 config.py
    2. 修改 CST_INSTALL_PATH 为本机 CST 安装路径
    3. config.py 已加入 .gitignore，不会同步到 GitHub
    本模板不再自动作为本机配置加载；未配置时自动发现常见安装目录。

所有从属路径（Python库、材料库）均自动从 CST_INSTALL_PATH 推导。
    例如 CST_INSTALL_PATH = r"C:\SOFTWARE\CST Studio Suite 2026"
    → CST_PYTHON_LIB   = {CST_INSTALL_PATH}\AMD64\python_cst_libraries
    → CST_MATERIAL_LIB = {CST_INSTALL_PATH}\Library\Materials

如需在其他文件中获取路径，推荐使用 _path_tools 模块：
    from cst_solver._path_tools import get_paths
    paths = get_paths(CST_INSTALL_PATH)

@author: PC
"""

import os

# ============================================================
# ★ 唯一需要配置的项 —— 请修改为本机 CST 安装路径
# ============================================================

CST_INSTALL_PATH = r"C:\SOFTWARE\CST Studio Suite 2026"

# ============================================================
# 以下为自动推导（从 CST_INSTALL_PATH），无需手动修改
# ============================================================

CST_PYTHON_LIB = os.path.join(CST_INSTALL_PATH, "AMD64", "python_cst_libraries")
CST_MATERIAL_LIB = os.path.join(CST_INSTALL_PATH, "Library", "Materials")

# 可选配置
DEFAULT_WORK_DIR = ""
CST_START_MODE = "Interactive"
