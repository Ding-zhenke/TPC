# -*- coding: utf-8 -*-
"""
CST 结果导出 Mixin 模块
========================
封装 ASCIIExport 结果导出功能

@author: PC
"""


class ExportMixin:
    """
    CST 结果导出 Mixin
    提供 1D/2D/3D 结果的 ASCII 导出功能
    """

    def export_result_1d(self, tree_path, save_path):
        """
        导出 1D 结果到 ASCII 文件

        :param tree_path: str, 导航树路径
        :param save_path: str, 保存路径
        """
        ascii_export = self.cst_file.model3d.ASCIIExport
        self.cst_file.model3d.SelectTreeItem("1D Results\\" + tree_path)
        ascii_export.Reset()
        ascii_export.FileName(save_path)
        ascii_export.Execute()

    def export_result_2d3d(self, tree_path, save_path, mode='FixedWidth',
                           step=-1,usesubvolume=False,setsubvolume=None):
        """
        导出 2D/3D 结果到 ASCII 文件

        :param tree_path: str, 导航树路径
        :param save_path: str, 保存路径
        :param mode: str, 'FixedWidth'/'FixedNumber'
        :param step: float/int, 步长/采样数
        """
        ascii_export = self.cst_file.model3d.ASCIIExport
        self.cst_file.model3d.SelectTreeItem(tree_path)
        ascii_export.Reset()
        ascii_export.FileName(save_path)
        ascii_export.Mode(mode)
        if usesubvolume is True:
            xmin,xmax,ymin, ymax,zmin,zmax = setsubvolume
            ascii_export.SetSubvolume(xmin, xmax, ymin, ymax, zmin, zmax)
        if step != -1:
            ascii_export.Step(step)
        ascii_export.Execute()
