# -*- coding: utf-8 -*-
"""
CST 曲线操作 Mixin 模块
=======================
封装 ExtrudeCurve、LoftCurves、SweepCurve、BlendCurve 等曲线到实体的操作

@author: PC
"""


class CurveOpsMixin:
    """
    CST 曲线操作 Mixin
    提供曲线拉伸、放样、扫掠、混合、覆盖等操作
    """

    def extrude(self, curve, name, thickness, component='component1',
                material='PEC', log_flag=1):
        """
        将二维曲线拉伸为三维实体（挤出成型）
        保留原函数名以兼容旧代码

        :param curve: str, 待拉伸的曲线全名（格式: curve组名:曲线名）
        :param name: str, 拉伸后实体名称
        :param thickness: float/str, 拉伸高度（Z轴方向）
        :param component: str, 归属组件
        :param material: str, 材料名称
        :param log_flag: int, 0-仅返回 1-写入历史
        :return: str, CST 指令文本
        """
        f1 = f"""
        With ExtrudeCurve
             .Reset 
             .Name "{name} "
             .Component "{component}"
             .Material "{material}"
             .Thickness "{thickness}" 
             .Twistangle "0.0" 
             .Taperangle "0.0" 
             .DeleteProfile "True" 
             .Curve "{curve}" 
             .Create
        End With
        """
        if log_flag == 1:
            self.cst_file.model3d.add_to_history(name + "  extrude  ", f1)
        return f1

    def extrude_curve(self, curve, name, thickness, component='component1',
                      material='PEC', log_flag=1):
        """
        曲线拉伸为实体（蛇形命名）
        等同于 extrude()
        """
        return self.extrude(curve, name, thickness, component, material, log_flag)

    def loft_curves(self, curves, name, component='component1', material='PEC'):
        """
        将多条曲线放样为三维实体

        :param curves: list[str], 曲线名称列表
                      （格式: ["curve组:曲线1", "curve组:曲线2", ...]）
        :param name: str, 放样后实体名称
        :param component: str, 归属组件
        :param material: str, 材料名称
        """
        curve_section = ""
        for i, c in enumerate(curves):
            curve_section += f'            .Curve("{i + 1}", "{c}")\n'
        f1 = f"""With Loft
            .Reset
            .Name "{name}"
            .Component "{component}"
            .Material "{material}"
            .RuledSurface "False"
{curve_section}            .Create
        End With
        """
        self.cst_file.model3d.add_to_history(f"Loft: {name}", f1)

    def sweep_curve(self, path_curve, profile_curve, name,
                    component='component1', material='PEC'):
        """
        沿路径曲线扫掠轮廓曲线生成三维实体

        :param path_curve: str, 路径曲线（格式: "curve组:曲线名"）
        :param profile_curve: str, 轮廓曲线
        :param name: str, 扫掠后实体名称
        :param component: str, 归属组件
        :param material: str, 材料名称
        """
        f1 = f"""With SweepCurve
            .Reset
            .Name "{name}"
            .Component "{component}"
            .Material "{material}"
            .PathCurve "{path_curve}"
            .ProfileCurve "{profile_curve}"
            .Create
        End With
        """
        self.cst_file.model3d.add_to_history(f"SweepCurve: {name}", f1)

    def blend_curve(self, curves, name, curve='curve1'):
        """
        创建曲线之间的混合曲线（倒圆角过渡）

        :param curves: list[str], 要混合的曲线名称列表
        :param name: str, 混合后曲线名称
        :param curve: str, 归属曲线组
        """
        picks = ""
        for c in curves:
            picks += f'            .Curve "{c}"\n'
        f1 = f"""With BlendCurve
            .Reset
            .Name "{name}"
            .Curve "{curve}"
{picks}            .Create
        End With
        """
        self.cst_file.model3d.add_to_history(f"BlendCurve: {name}", f1)

    def chamfer_curve(self, curves, name, curve='curve1'):
        """
        创建曲线之间的倒角过渡

        :param curves: list[str], 要倒角的曲线名称列表
        :param name: str, 倒角后曲线名称
        :param curve: str, 归属曲线组
        """
        picks = ""
        for c in curves:
            picks += f'            .Curve "{c}"\n'
        f1 = f"""With ChamferCurve
            .Reset
            .Name "{name}"
            .Curve "{curve}"
{picks}            .Create
        End With
        """
        self.cst_file.model3d.add_to_history(f"ChamferCurve: {name}", f1)

    def cover_curve(self, closed_curve, name, component='component1',
                    material='PEC'):
        """
        用面覆盖闭合曲线（将闭合曲线转换为面）

        :param closed_curve: str, 闭合曲线（格式: "curve组:曲线名"）
        :param name: str, 生成的面名称
        :param component: str, 归属组件
        :param material: str, 材料名称
        """
        f1 = f"""With CoverCurve
            .Reset
            .Name "{name}"
            .Component "{component}"
            .Material "{material}"
            .Curve "{closed_curve}"
            .Create
        End With
        """
        self.cst_file.model3d.add_to_history(f"CoverCurve: {name}", f1)

    def trim_curves(self, curves_to_trim, trimming_curves, name, curve='curve1'):
        """
        修剪曲线

        :param curves_to_trim: list[str], 被修剪的曲线
        :param trimming_curves: list[str], 用于修剪的曲线
        :param name: str, 结果曲线名称
        :param curve: str, 归属曲线组
        """
        trim_list = ""
        for c in curves_to_trim:
            trim_list += f'            .TrimCurve "{c}"\n'
        for c in trimming_curves:
            trim_list += f'            .TrimmingCurve "{c}"\n'
        f1 = f"""With TrimCurves
            .Reset
            .Name "{name}"
            .Curve "{curve}"
{trim_list}            .Create
        End With
        """
        self.cst_file.model3d.add_to_history(f"TrimCurves: {name}", f1)
