# -*- coding: utf-8 -*-
"""
CST 边界条件 Mixin 模块
=======================
封装 Boundary、Background、LayerStacking 等边界与背景设置

@author: PC
"""


class BoundaryMixin:
    """
    CST 边界条件 Mixin
    提供边界条件、背景材料、层叠设置等功能
    """

    def boundary(self, xmax='expanded open', xmin='expanded open',
                 ymax='expanded open', ymin='expanded open',
                 zmax='expanded open', zmin='expanded open',
                 Xsymmetry='none', Ysymmetry='none', Zsymmetry='none',
                 ApplyInAllDirections=False, OpenAddSpaceFactor=0.5):
        """
        配置仿真区域的边界条件
        保留原函数名以兼容旧代码

        :param xmax/xmin: str, X轴边界类型
        :param ymax/ymin: str, Y轴边界类型
        :param zmax/zmin: str, Z轴边界类型
          常见取值: 'expanded open', 'open', 'electric', 'magnetic', 'periodic', 'unit cell'
        :param Xsymmetry/Ysymmetry/Zsymmetry: str, 对称面
          'magnetic'-磁对称 'electric'-电对称 'none'-无对称
        :param ApplyInAllDirections: bool, 是否全局应用
        :param OpenAddSpaceFactor: float, 开放边界扩展空间系数
        """
        f1 = f"""
            With Boundary
        .Xmin "{xmax}"
        .Xmax "{xmin}"
        .Ymin "{ymax}"
        .Ymax "{ymin}"
        .Zmin "{zmax}"
        .Zmax "{zmin}"
        .Xsymmetry "{Xsymmetry}"
        .Ysymmetry "{Ysymmetry}"
        .Zsymmetry "{Zsymmetry}"
        .ApplyInAllDirections "{ApplyInAllDirections}"
        .OpenAddSpaceFactor "{OpenAddSpaceFactor}"
    End With
    """
        self.cst_file.model3d.add_to_history('Define boundary', f1)

    def set_boundary(self, **kwargs):
        """
        设置边界条件（蛇形命名）
        等同于 boundary(**kwargs)

        支持的关键字参数:
            xmin, xmax, ymin, ymax, zmin, zmax: 边界类型
            Xsymmetry, Ysymmetry, Zsymmetry: 对称面
            ApplyInAllDirections: 全局应用
            OpenAddSpaceFactor: 扩展空间系数
        """
        self.boundary(**kwargs)

    def set_background(self, material='Vacuum', xmin_space=0, xmax_space=0,
                       ymin_space=0, ymax_space=0, zmin_space=0, zmax_space=0,
                       background_type='Normal', apply_in_all_directions=False):
        """
        设置背景材料与扩展空间

        :param material: str, 背景材料名称，默认 'Vacuum'
        :param xmin_space/xmax_space: float, X方向扩展空间
        :param ymin_space/ymax_space: float, Y方向扩展空间
        :param zmin_space/zmax_space: float, Z方向扩展空间
        :param background_type: str, 背景类型 'Normal'/'PEC'/'PMC'/'Open'
        :param apply_in_all_directions: bool, 是否全局应用
        """
        apply_str = 'True' if apply_in_all_directions else 'False'
        f1 = f"""With Background
     .Reset
     .Type "{background_type}"
     .Material "{material}"
     .XminSpace "{xmin_space}"
     .XmaxSpace "{xmax_space}"
     .YminSpace "{ymin_space}"
     .YmaxSpace "{ymax_space}"
     .ZminSpace "{zmin_space}"
     .ZmaxSpace "{zmax_space}"
     .ApplyInAllDirections "{apply_str}"
End With"""
        self.cst_file.model3d.add_to_history("Set Background", f1)

    # ================================================================
    # 补充: LayerStacking 层叠设置
    # ================================================================

    def set_layer_stacking(self, direction='z', stack_type='Default',
                            periodicity=None):
        """
        设置层叠参数（用于多层板结构仿真）

        :param direction: str, 层叠方向 'x'/'y'/'z'，默认 'z'
        :param stack_type: str, 层叠类型 'Default'/'Periodic'，默认 'Default'
        :param periodicity: list 可选, 周期 [nx, ny]（仅 stack_type='Periodic' 时生效）
        """
        f1 = f"""With LayerStacking
     .Reset
     .Direction "{direction}"
     .StackingType "{stack_type}"
"""
        if periodicity:
            f1 += f'     .Periodicity "{periodicity[0]}", "{periodicity[1]}"\n'
        f1 += """End With"""
        self.cst_file.model3d.add_to_history("LayerStacking Config", f1)
