# -*- coding: utf-8 -*-
"""
CST 远场后处理 Mixin 模块
==========================
封装 FarfieldPlot、FarfieldCalculator 等远场分析功能

@author: PC
"""


class FarfieldMixin:
    """
    CST 远场后处理 Mixin
    提供远场方向图绘制、远场计算等功能
    """

    @property
    def farfield_plot(self):
        """获取 FarfieldPlot 对象"""
        return self.cst_file.model3d.FarfieldPlot

    def set_farfield_plot(self, plottype='3d', plotmode='realized gain',
                          frequency=None):
        """
        设置远场方向图绘制参数

        :param plottype: str, 'polar'/'cartesian'/'2d'/'2dortho'/'3d'
        :param plotmode: str, 绘制模式
        :param frequency: float 可选, 频率
        """
        fp = self.farfield_plot
        fp.Reset()
        fp.Plottype(plottype)
        fp.SetPlotMode(plotmode)
        if frequency:
            fp.Frequency(frequency)
        fp.Plot()

    def compute_farfield_array(self, array_type='rectangular',
                               element_count=(2, 2),
                               spacing=(0.5, 0.5)):
        """
        计算阵列天线的远场方向图

        :param array_type: str, 阵列类型 'rectangular'/'circular'
        :param element_count: tuple, 阵元数量 (nx, ny)
        :param spacing: tuple, 阵元间距 (dx, dy)，单位波长
        """
        f1 = f"""With FarfieldArray
     .Reset
     .ArrayType "{array_type}"
     .ElementCountX "{element_count[0]}"
     .ElementCountY "{element_count[1]}"
     .SpacingX "{spacing[0]}"
     .SpacingY "{spacing[1]}"
     .Execute
End With"""
        self.cst_file.model3d.add_to_history("FarfieldArray", f1)
