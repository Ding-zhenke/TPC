# -*- coding: utf-8 -*-
"""
CST 绘图控制 Mixin 模块
=======================
封装 Plot、Plot1D、Plot2D3D、ScalarPlot2D/3D、VectorPlot2D/3D 等绘图控制功能

@author: PC
"""

import os

from cst_solver._guards import get_guard_state

# Plot.ExportImage 官方支持的图片格式（bmp / jpeg / png；jpg 等价于 jpeg）
_CAPTURE_IMAGE_EXTS = {'.bmp', '.jpeg', '.jpg', '.png'}


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
                            theta_start=0, theta_stop=360, theta_step=1,
                            require_gain=False):
        """
        绘制极坐标远场方向图

        ⚠️ 守卫层（陷阱 T8）：``'efield'`` 这类模式画出来的是 **Abs(E)**，
        量纲与增益无关，**不能**当作增益证据引用。要写进增益结论请用
        ``'directivity'`` / ``'gain'`` / ``'realized gain'``（见
        ``cst_solver.FARFIELD_GAIN_MODES``）；
        传 ``require_gain=True`` 会让守卫强制校验这一点。

        :param frequency: float 可选, 频率
        :param mode: str, 显示模式 'directivity'/'gain'/'realized gain'/'efield'
        :param theta_start: float, 起始角度
        :param theta_stop: float, 终止角度
        :param theta_step: float, 角度步长
        :param require_gain: bool, True 表示这次绘图要当增益证据用，强制白名单校验
        """
        get_guard_state(self).check_farfield_mode(
            mode, require_gain=require_gain, where='farfield_plot_polar()')
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

    def farfield_plot_cartesian(self, frequency=None, mode='directivity',
                                require_gain=False):
        """
        绘制直角坐标远场方向图

        :param frequency: float 可选, 频率
        :param mode: str, 显示模式
        :param require_gain: bool, True 表示这次绘图要当增益证据用（见 T8 说明）
        """
        get_guard_state(self).check_farfield_mode(
            mode, require_gain=require_gain, where='farfield_plot_cartesian()')
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

        ⚠️ ``PlotMode`` 会过守卫层（陷阱 T8）：未知模式会报警；
        ``'efield'`` 等非增益模式本身合法，但**不能**当增益证据引用。
        """
        fp = self.cst_file.model3d.FarfieldPlot
        fp.Reset()
        for key, value in properties.items():
            if key == 'PlotMode':
                get_guard_state(self).check_farfield_mode(
                    value, where='plot_set_properties()')
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

    # ================================================================
    # 3D 视图控制（相机 / Reset View）
    # ================================================================
    #
    # ⚠️ 本节方法都是**即时执行的 GUI 相机命令**，对应官方 ``Plot`` 对象的
    # ``ZoomToStructure`` / ``ResetZoom`` 等成员。它们：
    #   * 只改变当前 3D 视图的相机位置，**不改动几何、不进入建模历史树**；
    #   * 因此**不走** ``add_to_history``（否则会被录进历史、随 Rebuild 重放），
    #     而是像远场绘图一样直接调用动态 COM 对象 ``model3d.Plot``。
    #
    # 官方依据（CST 2026 VBA 帮助，Plot 对象 "Views and Zoom" 一节）：
    #   Plot.ZoomToStructure          —— 等同于菜单 View→Change View→Reset View（快捷键 Space）
    #   Plot.ZoomToSelectedStructure  —— Reset View to Selection（Shift+Space）
    #   Plot.ResetZoom                —— 复位缩放（结构+包围盒+工作平面全部可见）
    #   Plot.ZoomToRegion(6 个坐标)   —— 缩放到指定立方区域
    #
    # 注意与 :meth:`plot_reset` 区分：后者下发 ``Plot.Reset``，是把 **Plot 对象的
    # 绘图属性**恢复默认，**不是**相机意义上的 Reset View。

    def reset_view(self):
        """
        重置 3D 视图（相机），让整个结构充满屏幕

        对应 CST 菜单 **View → Change View → Reset View**（快捷键 **Space**），
        底层为官方 ``Plot.ZoomToStructure``。只调整当前 3D 视图的相机，
        **不改动几何、不写入建模历史树**。

        :说明:
            与 :meth:`plot_reset` 不同：``plot_reset()`` 重置的是 Plot 对象的
            绘图属性；本方法重置的是观察相机。
        """
        self.cst_file.model3d.Plot.ZoomToStructure()

    def zoom_to_structure(self):
        """
        缩放到整个结构（VBA 原名 ``Plot.ZoomToStructure`` 的蛇形别名）

        等同于 :meth:`reset_view`（即 Reset View / Space）。
        """
        self.reset_view()

    def reset_view_to_selection(self):
        """
        把 3D 视图缩放到当前选中的形体

        对应 CST 菜单 **View → Change View → Reset View to Selection**
        （快捷键 **Shift+Space**），底层为 ``Plot.ZoomToSelectedStructure``。
        不写入建模历史树。
        """
        self.cst_file.model3d.Plot.ZoomToSelectedStructure()

    def reset_zoom(self):
        """
        复位相机缩放，使结构、包围盒与整个工作平面均可见

        底层为官方 ``Plot.ResetZoom``。与 :meth:`reset_view` 的区别：
        Reset View（ZoomToStructure）只让结构紧凑充满屏幕，而本方法还会
        把包围盒和完整工作平面（若已开启）一并显示出来。不写入建模历史树。
        """
        self.cst_file.model3d.Plot.ResetZoom()

    def zoom_to_region(self, xmin, ymin, zmin, xmax, ymax, zmax):
        """
        把 3D 视图缩放到指定的立方区域

        底层为官方 ``Plot.ZoomToRegion(xmin, ymin, zmin, xmax, ymax, zmax)``。
        不写入建模历史树。

        :param xmin: float | str, 区域最小 x（CST 表达式字符串也可）
        :param ymin: float | str, 区域最小 y
        :param zmin: float | str, 区域最小 z
        :param xmax: float | str, 区域最大 x
        :param ymax: float | str, 区域最大 y
        :param zmax: float | str, 区域最大 z
        """
        self.cst_file.model3d.Plot.ZoomToRegion(
            xmin, ymin, zmin, xmax, ymax, zmax)

    # ================================================================
    # 3D 视图截图
    # ================================================================
    #
    # 官方依据（CST 2026 VBA 帮助，Plot 对象 "Export image" 一节）：
    #   Plot.ExportImage(name, width, height)
    #     截取当前 plot（3D sheet）为位图；name 必须是**绝对路径**；
    #     支持 bmp / jpeg / png；width、height 给 0 表示用当前窗口尺寸。
    #
    # 与 reset view 同理，截图是即时 GUI 命令，不走 add_to_history。

    def capture_3d_view(self, save_path, width=0, height=0):
        """
        截取当前 3D 模型视图并保存为图片文件

        封装官方 VBA ``Plot.ExportImage(name, width, height)``，截取当前 3D
        视图（3D sheet）。属于**即时 GUI 命令**，不写入建模历史树，因此不会在
        Rebuild 时重复截图。

        :param save_path: str, 图片保存路径。CST 要求为**绝对路径**；
            支持扩展名 ``.bmp`` / ``.jpeg``/``.jpg`` / ``.png``，格式由扩展名决定。
            父目录不存在时会自动创建。
        :param width: int, 图片宽度（像素）；``0`` 表示使用当前 3D 窗口宽度。
        :param height: int, 图片高度（像素）；``0`` 表示使用当前 3D 窗口高度。
        :return: str, 实际传给 CST 的绝对图片路径。
        :raises ValueError: 扩展名不支持、宽高为负，或只给了宽/高中的一个非零值时。
        :raises TypeError: ``save_path`` 不是字符串、宽高不是整数时。

        :说明:
            若想让结构在截图前以标准视角充满画面，先调用
            :meth:`reset_view`（Reset View / Space）。
        """
        # --- 参数校验：早失败，避免下发非法 VBA 后只在 get_messages 里留脏消息 ---
        if not isinstance(save_path, str) or not save_path.strip():
            raise TypeError('save_path 必须是非空字符串（图片的绝对路径）')
        name = save_path.strip()
        ext = os.path.splitext(name)[1].lower()
        if ext not in _CAPTURE_IMAGE_EXTS:
            raise ValueError(
                f'不支持的图片扩展名 {ext or "（无扩展名）"}；'
                f'CST Plot.ExportImage 仅支持 {sorted(_CAPTURE_IMAGE_EXTS)}')
        for dim_name, dim in (('width', width), ('height', height)):
            if isinstance(dim, bool) or not isinstance(dim, int):
                raise TypeError(f'{dim_name} 必须是 int（0 表示当前窗口尺寸）')
            if dim < 0:
                raise ValueError(f'{dim_name} 不能为负；0 表示当前窗口尺寸')
        if (width == 0) != (height == 0):
            raise ValueError(
                'width 与 height 必须同时为 0（都用当前窗口尺寸），'
                '或同时为正整数；不允许只指定其中一个')

        abs_path = os.path.abspath(name)
        parent = os.path.dirname(abs_path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)

        self.cst_file.model3d.Plot.ExportImage(abs_path, width, height)
        return abs_path

    def export_3d_image(self, save_path, width=0, height=0):
        """
        截取当前 3D 模型视图（保留旧 VBA 语义的别名）

        等同于 :meth:`capture_3d_view`。
        """
        return self.capture_3d_view(save_path, width, height)
