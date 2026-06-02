# -*- coding: utf-8 -*-
"""
CST 绘图控制 Mixin 模块
=======================
封装 Plot、Plot1D、Plot2D3D、ScalarPlot2D/3D、VectorPlot2D/3D 等绘图控制功能

@author: PC
"""


class PlotMixin:
    """
    CST 绘图控制 Mixin
    提供 1D/2D/3D 绘图、标量/矢量场图绘制、绘图属性控制等功能
    """

    # ================================================================
    # 通用绘图
    # ================================================================

    def plot_reset(self):
        """
        重置绘图对象属性到默认值
        """
        f1 = """With Plot
     .Reset
End With"""
        self.cst_file.model3d.add_to_history("Plot Reset", f1)

    def reset_plot(self):
        """
        重置绘图（蛇形命名）
        等同于 plot_reset()
        """
        self.plot_reset()

    def plot_1d(self, tree_path):
        """
        绘制 1D 结果（S 参数等）

        :param tree_path: str, 1D 结果导航树路径
            如 "1D Results\\S-Parameters\\S1,1"
        """
        self.cst_file.model3d.SelectTreeItem(tree_path)
        f1 = """With Plot1D
     .Reset
     .Plot
End With"""
        self.cst_file.model3d.add_to_history("Plot1D", f1)

    def plot_2d3d(self, tree_path):
        """
        绘制 2D/3D 结果（场分布等）

        :param tree_path: str, 2D/3D 结果导航树路径
            如 "2D/3D Results\\E-Field\\e-field (f=310)"
        """
        self.cst_file.model3d.SelectTreeItem(tree_path)
        f1 = """With Plot2D3D
     .Reset
     .Plot
End With"""
        self.cst_file.model3d.add_to_history("Plot2D3D", f1)

    # ================================================================
    # 标量场图
    # ================================================================

    def scalar_plot_2d(self, tree_path, component='', frequency=None):
        """
        绘制 2D 标量场图

        :param tree_path: str, 场结果路径
        :param component: str, 场分量 'Abs'/'X'/'Y'/'Z'/'Phase'
        :param frequency: float 可选, 频率
        """
        self.cst_file.model3d.SelectTreeItem(tree_path)
        f1 = f"""With ScalarPlot2D
     .Reset
     .ScalarFieldComponent "{component}" if component else "Abs"
"""
        if frequency:
            f1 += f'     .Frequency "{frequency}"\n'
        f1 += """     .Plot
End With"""
        self.cst_file.model3d.add_to_history("ScalarPlot2D", f1)

    def scalar_plot_3d(self, tree_path, component='Abs', frequency=None):
        """
        绘制 3D 标量场图

        :param tree_path: str, 场结果路径
        :param component: str, 场分量 'Abs'/'X'/'Y'/'Z'/'Phase'
        :param frequency: float 可选, 频率
        """
        self.cst_file.model3d.SelectTreeItem(tree_path)
        f1 = f"""With ScalarPlot3D
     .Reset
     .ScalarFieldComponent "{component}"
"""
        if frequency:
            f1 += f'     .Frequency "{frequency}"\n'
        f1 += """     .Plot
End With"""
        self.cst_file.model3d.add_to_history("ScalarPlot3D", f1)

    # ================================================================
    # 矢量场图
    # ================================================================

    def vector_plot_2d(self, tree_path, frequency=None):
        """
        绘制 2D 矢量场图

        :param tree_path: str, 场结果路径
        :param frequency: float 可选, 频率
        """
        self.cst_file.model3d.SelectTreeItem(tree_path)
        f1 = """With VectorPlot2D
     .Reset
"""
        if frequency:
            f1 += f'     .Frequency "{frequency}"\n'
        f1 += """     .Plot
End With"""
        self.cst_file.model3d.add_to_history("VectorPlot2D", f1)

    def vector_plot_3d(self, tree_path, frequency=None):
        """
        绘制 3D 矢量场图

        :param tree_path: str, 场结果路径
        :param frequency: float 可选, 频率
        """
        self.cst_file.model3d.SelectTreeItem(tree_path)
        f1 = """With VectorPlot3D
     .Reset
"""
        if frequency:
            f1 += f'     .Frequency "{frequency}"\n'
        f1 += """     .Plot
End With"""
        self.cst_file.model3d.add_to_history("VectorPlot3D", f1)

    # ================================================================
    # 远场绘图（补充 FarfieldMixin）
    # ================================================================

    def farfield_plot_polar(self, frequency=None, mode='directivity',
                            theta_start=0, theta_stop=360, theta_step=1):
        """
        绘制极坐标远场方向图

        :param frequency: float 可选, 频率
        :param mode: str, 显示模式 'directivity'/'gain'/'realized gain'/'efield'
        :param theta_start: float, 起始角度
        :param theta_stop: float, 终止角度
        :param theta_step: float, 角度步长
        """
        fp = self.cst_file.model3d.FarfieldPlot
        fp.Reset()
        fp.Plottype("Polar")
        fp.SetPlotMode(mode)
        if frequency:
            fp.Frequency(frequency)
        fp.ThetaStart(theta_start)
        fp.ThetaStop(theta_stop)
        fp.ThetaStep(theta_step)
        fp.Plot()

    def farfield_plot_cartesian(self, frequency=None, mode='directivity'):
        """
        绘制直角坐标远场方向图

        :param frequency: float 可选, 频率
        :param mode: str, 显示模式
        """
        fp = self.cst_file.model3d.FarfieldPlot
        fp.Reset()
        fp.Plottype("Cartesian")
        fp.SetPlotMode(mode)
        if frequency:
            fp.Frequency(frequency)
        fp.Plot()

    # ================================================================
    # 绘图属性控制
    # ================================================================

    def plot_set_properties(self, properties: dict):
        """
        批量设置绘图属性

        :param properties: dict, 属性键值对
            例如: {'PlotMode': 'directivity', 'Frequency': '3.5'}

        支持的属性:
            - PlotMode: 'directivity'/'gain'/'realized gain'/'efield'
            - Frequency: 频率值
            - ThetaStart/ThetaStop/ThetaStep: 角度范围
            - PhiStart/PhiStop/PhiStep: 方位角范围
            - Trace: 'all'/'max'/'min'
        """
        fp = self.cst_file.model3d.FarfieldPlot
        fp.Reset()
        for key, value in properties.items():
            method = getattr(fp, key, None)
            if method and callable(method):
                method(str(value))
        fp.Plot()

    def plot_animate(self, tree_path, parameter, start, stop, step):
        """
        创建参数动画绘图

        :param tree_path: str, 结果导航树路径
        :param parameter: str, 扫描参数名
        :param start: float, 起始值
        :param stop: float, 终止值
        :param step: float, 步长
        """
        self.cst_file.model3d.SelectTreeItem(tree_path)
        f1 = f"""With Plot1D
     .Reset
     .Animate "{parameter}", "{start}", "{stop}", "{step}"
     .Plot
End With"""
        self.cst_file.model3d.add_to_history(f"Plot Animate {parameter}", f1)

    def plot_delete_all(self):
        """删除所有绘图结果"""
        self.cst_file.model3d.DeleteAllPlots()
