# -*- coding: utf-8 -*-
"""
CST 仿真结果读取类
====================
封装 cst.results.ProjectFile，提供导航树结果查询和数据读取接口

@author: PC
"""

import numpy as np
import cst.results


class result:
    """
    CST 仿真结果读取类
    用于从已完成的 CST 仿真工程中读取 S 参数、场数据等结果

    用法示例:
        >>> app_result = result("path/to/project.cst")
        >>> s21 = app_result.read_1D("S-Parameters\\S2,1")
        >>> s11 = app_result.read_1D("S-Parameters\\S1,1", run_id=0)
    """

    def __init__(self, cst_file):
        """
        初始化结果读取器

        :param cst_file: str, CST 工程文件路径（.cst）
        """
        self.app_result = cst.results.ProjectFile(cst_file, allow_interactive=True)
        self.result_module = self.app_result.get_3d()

    # ================================================================
    # 导航树浏览
    # ================================================================

    def get_tree_items(self):
        """
        列出导航树中的所有结果项

        :return: 导航树项目列表
        """
        return self.result_module.get_tree_items()

    def get_available_results(self):
        """
        获取所有可用的结果项（中文别名）
        等同于 get_tree_items()
        """
        return self.get_tree_items()

    # ================================================================
    # Run ID 查询
    # ================================================================

    def get_all_run_ids(self, max_mesh_passes_only: bool = True):
        """
        获取所有已存在的仿真运行 ID

        :param max_mesh_passes_only: bool
            True-仅返回最高网格自适应次数的结果（最终结果）
            False-包含所有网格自适应中间结果
        :return: list[int], 运行 ID 列表
        """
        return self.result_module.get_all_run_ids(max_mesh_passes_only)

    def get_run_ids(self, treepath: str, skip_nonparametric: bool = False):
        """
        获取指定导航树项目的所有运行 ID

        :param treepath: str, 导航树项目路径
        :param skip_nonparametric: bool
            True-排除 run_id=0 的非参数结果
        :return: list[int], 运行 ID 列表
        """
        return self.result_module.get_run_ids(treepath, skip_nonparametric)

    # ================================================================
    # 结果项获取
    # ================================================================

    def get_result_item(self, treepath: str, run_id=0, load_impedances: bool = True):
        """
        获取指定导航树路径的结果项对象

        :param treepath: str, 导航树路径
            例如 "1D Results\\S-Parameters\\S1,1"
        :param run_id: int, 运行 ID，默认 0（最终结果）
        :param load_impedances: bool
            False-跳过自动加载参考阻抗（提升速度）
        :return: cst.results.ResultItem
        """
        return self.result_module.get_result_item(treepath, run_id, load_impedances)

    # ================================================================
    # 数据读取
    # ================================================================

    def read_1D(self, tree_path, run_id: int = 0):
        """
        读取 1D 结果数据（如 S 参数）

        :param tree_path: str, 导航树路径（相对于 "1D Results\\"）
            例如 "S-Parameters\\S2,1"
        :param run_id: int, 运行 ID，默认 0
        :return: ndarray, 形状为 (n, 2) 的二维数组 [xdata, ydata]
        """
        data = self.result_module.get_result_item(
            "1D Results\\" + tree_path, run_id)
        ss = np.asarray([data.get_xdata(), data.get_ydata()]).T
        return ss

    def read_2d(self, tree_path, run_id: int = 0):
        """
        读取 2D 结果数据

        :param tree_path: str, 导航树路径（相对于 "2D Results\\"）
        :param run_id: int, 运行 ID，默认 0
        :return: dict, 包含 xdata, ydata, zdata 等字段
        """
        data = self.result_module.get_result_item(
            "2D Results\\" + tree_path, run_id)
        return {
            'x': data.get_xdata(),
            'y': data.get_ydata(),
            'z': data.get_zdata() if hasattr(data, 'get_zdata') else None,
            'values': data.get_data()
        }

    def read_s_parameter(self, s_param: str, run_id: int = 0):
        """
        便捷方法：直接读取 S 参数

        :param s_param: str, S 参数标识，如 'S1,1', 'S2,1'
        :param run_id: int, 运行 ID，默认 0
        :return: ndarray, 形状 (n, 2) 的 [频率, S参数值]

        用法示例:
            >>> res = result("project.cst")
            >>> s11 = res.read_s_parameter("S1,1")
        """
        return self.read_1D(f"S-Parameters\\{s_param}", run_id)

    def read_3d(self, tree_path, run_id: int = 0):
        """
        读取 3D 结果数据（电场/磁场/功率损耗等）

        :param tree_path: str, 导航树路径（相对于 "2D/3D Results\\" 或 "3D Results\\"）
        :param run_id: int, 运行 ID，默认 0
        :return: dict, 包含 xdata, ydata, zdata, values 等字段

        用法示例:
            >>> res = result("project.cst")
            >>> e_field = res.read_3d("E-Field\\e-field (f=310)")
        """
        # 尝试多种路径前缀
        for prefix in ["2D/3D Results\\"]:
            try:
                full_path = prefix + tree_path
                data = self.result_module.get_result_item(full_path, run_id)
                return {
                    'x': data.get_xdata(),
                    'y': data.get_ydata(),
                    'z': data.get_zdata() if hasattr(data, 'get_zdata') else None,
                    'values': data.get_data()
                }
            except Exception:
                continue
        raise ValueError(f"无法读取 3D 结果: {tree_path}")
