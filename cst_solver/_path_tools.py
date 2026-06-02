import os

def get_paths(cst_install_path):
    """
    从 CST_INSTALL_PATH 自动推导所有从属路径
    
    :param cst_install_path: str, CST 安装路径
    :return: dict, 包含以下键:
        - CST_PYTHON_LIB:   CST Python 库路径
        - CST_MATERIAL_LIB: CST 材料库路径
    """
    return {
        "CST_PYTHON_LIB": os.path.join(cst_install_path, "AMD64", "python_cst_libraries"),
        "CST_MATERIAL_LIB": os.path.join(cst_install_path, "Library", "Materials"),
    }
