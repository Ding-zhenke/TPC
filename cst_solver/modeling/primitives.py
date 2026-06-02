# -*- coding: utf-8 -*-
"""
CST 基本体建模 Mixin 模块
==========================
封装 Brick、Cylinder、Sphere、Cone、Torus 等基本三维体的创建

@author: PC
"""


class ModelingPrimitivesMixin:
    """
    CST 基本体建模 Mixin
    提供长方体、圆柱体、球体、圆锥体、圆环体等基本三维实体的创建
    """

    def square(self, xmin, xmax, ymin, ymax, zmin, zmax, name,
               component='component1', material='PEC'):
        """
        创建长方体(立方体)三维实体模型
        保留原函数名以兼容旧代码

        :param xmin: float/str, X轴最小值
        :param xmax: float/str, X轴最大值
        :param ymin: float/str, Y轴最小值
        :param ymax: float/str, Y轴最大值
        :param zmin: float/str, Z轴最小值
        :param zmax: float/str, Z轴最大值
        :param name: str, 长方体模型名称
        :param component: str, 归属组件名称，默认 component1
        :param material: str, 模型材料名称，默认理想导体 PEC
        """
        f1 = f"""
        With Brick
            .Reset 
            .Name "{name}"
            .Component "{component}"
            .Material "{material}" 
            .Xrange "{xmin}", "{xmax}" 
            .Yrange "{ymin}", "{ymax}"
            .Zrange "{zmin}", "{zmax}"
            .Create
        End With
        """
        self.cst_file.model3d.add_to_history("Square: " + name, f1)

    def create_brick(self, xmin, xmax, ymin, ymax, zmin, zmax, name,
                     component='component1', material='PEC'):
        """
        创建长方体（蛇形命名）
        等同于 square()

        :param xmin: float/str, X轴最小值
        :param xmax: float/str, X轴最大值
        :param ymin: float/str, Y轴最小值
        :param ymax: float/str, Y轴最大值
        :param zmin: float/str, Z轴最小值
        :param zmax: float/str, Z轴最大值
        :param name: str, 模型名称
        :param component: str, 归属组件
        :param material: str, 材料名称
        """
        self.square(xmin, xmax, ymin, ymax, zmin, zmax, name, component, material)

    def cylinder(self, center, r, h, name, axis='z',
                 component='component1', material='PEC'):
        """
        创建圆柱体三维实体模型
        保留原函数名以兼容旧代码

        :param center: list, 中心点坐标 [X, Y]（axis=z时）
                       [X, Z]（axis=y时） [Y, Z]（axis=x时）
        :param r: list, [外半径, 内半径] 内半径为0则是实心圆柱
        :param h: list, 轴方向高度范围 [起始值, 终止值]
        :param name: str, 模型名称
        :param axis: str, 中心轴方向 'x'/'y'/'z'，默认 'z'
        :param component: str, 归属组件
        :param material: str, 材料名称
        """
        axis_map = {
            'z': ('Zrange', 'Xcenter', 'Ycenter'),
            'y': ('Yrange', 'Xcenter', 'Zcenter'),
            'x': ('Xrange', 'Ycenter', 'Zcenter'),
        }
        if axis not in axis_map:
            raise ValueError(f"axis 必须是 'x', 'y' 或 'z'，当前为: {axis}")
        rng_attr, c1_attr, c2_attr = axis_map[axis]

        f1 = f"""
        With Cylinder 
            .Reset 
            .Name "{name}" 
            .Component "{component}" 
            .Material "{material}" 
            .OuterRadius "{r[0]}" 
            .InnerRadius "{r[1]}" 
            .Axis "{axis}" 
            .{rng_attr} "{h[0]}", "{h[1]}" 
            .{c1_attr} "{center[0]}" 
            .{c2_attr} "{center[1]}" 
            .Segments "0" 
            .Create 
        End With
        """
        self.cst_file.model3d.add_to_history(f"Cylinder: {name}", f1)

    def create_cylinder(self, center, r, h, name, axis='z',
                        component='component1', material='PEC'):
        """
        创建圆柱体（蛇形命名）
        等同于 cylinder()
        """
        self.cylinder(center, r, h, name, axis, component, material)

    def create_sphere(self, center, radius, name,
                      component='component1', material='PEC'):
        """
        创建球体三维实体

        :param center: list, 球心坐标 [X, Y, Z]
        :param radius: float/str, 球半径
        :param name: str, 模型名称
        :param component: str, 归属组件，默认 component1
        :param material: str, 材料名称，默认 PEC
        """
        f1 = f"""
        With Sphere
            .Reset
            .Name "{name}"
            .Component "{component}"
            .Material "{material}"
            .Radius "{radius}"
            .Xcenter "{center[0]}"
            .Ycenter "{center[1]}"
            .Zcenter "{center[2]}"
            .Segments "0"
            .Create
        End With
        """
        self.cst_file.model3d.add_to_history(f"Sphere: {name}", f1)

    def create_cone(self, bottom_radius, top_radius, height, name,
                    center=None, axis='z',
                    component='component1', material='PEC'):
        """
        创建圆台/圆锥体三维实体

        :param bottom_radius: float/str, 底部半径
        :param top_radius: float/str, 顶部半径（为0则创建圆锥）
        :param height: float/str, 高度
        :param name: str, 模型名称
        :param center: list, 底部中心坐标 [X, Y]（axis=z时），默认 [0,0]
        :param axis: str, 中心轴方向 'x'/'y'/'z'，默认 'z'
        :param component: str, 归属组件，默认 component1
        :param material: str, 材料名称，默认 PEC
        """
        if center is None:
            center = [0, 0]
        axis_map = {
            'z': ('Zrange', 'Xcenter', 'Ycenter'),
            'y': ('Yrange', 'Xcenter', 'Zcenter'),
            'x': ('Xrange', 'Ycenter', 'Zcenter'),
        }
        if axis not in axis_map:
            raise ValueError(f"axis 必须是 'x', 'y' 或 'z'，当前为: {axis}")
        rng_attr, c1_attr, c2_attr = axis_map[axis]

        f1 = f"""
        With Cone
            .Reset
            .Name "{name}"
            .Component "{component}"
            .Material "{material}"
            .Axis "{axis}"
            .{rng_attr} "0", "{height}"
            .{c1_attr} "{center[0]}"
            .{c2_attr} "{center[1]}"
            .Bottomradius "{bottom_radius}"
            .Topradius "{top_radius}"
            .Segments "0"
            .Create
        End With
        """
        self.cst_file.model3d.add_to_history(f"Cone: {name}", f1)

    def create_torus(self, major_radius, minor_radius, name,
                     center=None, axis='z',
                     component='component1', material='PEC'):
        """
        创建圆环体三维实体

        :param major_radius: float/str, 主半径（环中心到管中心）
        :param minor_radius: float/str, 副半径（管的半径）
        :param name: str, 模型名称
        :param center: list, 环中心坐标 [X, Y, Z]，默认 [0,0,0]
        :param axis: str, 环轴方向 'x'/'y'/'z'，默认 'z'
        :param component: str, 归属组件，默认 component1
        :param material: str, 材料名称，默认 PEC
        """
        if center is None:
            center = [0, 0, 0]
        f1 = f"""
        With Torus
            .Reset
            .Name "{name}"
            .Component "{component}"
            .Material "{material}"
            .Axis "{axis}"
            .OuterRadius "{major_radius}"
            .InnerRadius "{minor_radius}"
            .Xcenter "{center[0]}"
            .Ycenter "{center[1]}"
            .Zcenter "{center[2]}"
            .Segments "0"
            .Create
        End With
        """
        self.cst_file.model3d.add_to_history(f"Torus: {name}", f1)

    def create_elliptical_cylinder(self, name,x_radius, y_radius, height, 
                                   center=None, axis='z',
                                   component='component1', material='PEC'):
        """
        创建椭圆柱体三维实体（ECylinder）

        :param x_radius: float/str, X方向半径
        :param y_radius: float/str, Y方向半径
        :param height: float/str, 高度
        :param name: str, 模型名称
        :param center: list, 底部中心坐标 [X, Y]，默认 [0,0]
        :param axis: str, 轴方向 'x'/'y'/'z'，默认 'z'
        :param component: str, 归属组件
        :param material: str, 材料名称
        """
        if center is None:
            center = [0, 0]
        axis_map = {
            'z': ('Zrange', 'Xcenter', 'Ycenter'),
            'y': ('Yrange', 'Xcenter', 'Zcenter'),
            'x': ('Xrange', 'Ycenter', 'Zcenter'),
        }
        if axis not in axis_map:
            raise ValueError(f"axis 必须是 'x', 'y' 或 'z'，当前为: {axis}")
        rng_attr, c1_attr, c2_attr = axis_map[axis]

        f1 = f"""
        With ECylinder
            .Reset
            .Name "{name}"
            .Component "{component}"
            .Material "{material}"
            .Axis "{axis}"
            .{rng_attr} "0", "{height}"
            .{c1_attr} "{center[0]}"
            .{c2_attr} "{center[1]}"
            .Xradius "{x_radius}"
            .Yradius "{y_radius}"
            .Segments "0"
            .Create
        End With
        """
        self.cst_file.model3d.add_to_history(f"ECylinder: {name}", f1)

    # ============================================================
    # 专用建模：三角形棱柱、六边形棱柱
    # ============================================================

    def triangle(self, a, h, center, theta, name, curve,
                 material='Silicon (lossy)'):
        """
        创建正三角形棱柱三维实体模型，支持旋转+平移
        保留原函数名以兼容旧代码

        :param a: float/str, 正三角形边长
        :param h: float/str, 棱柱 Z 轴拉伸高度
        :param center: list, 最终平移中心 [X, Y, Z]
        :param theta: list, 旋转角度 [X°, Y°, Z°]
        :param name: str, 模型名称
        :param curve: str, 绘制三角形的曲线名称
        :param material: str, 材料名称
        """
        data = [
            ["0", f"{a}/sqr(3)"],
            [f"-{a}/(2)", f"-{a}/2/sqr(3)"],
            [f"{a}/(2)", f"-{a}/2/sqr(3)"],
            ["0", f"{a}/sqr(3)"]
        ]
        f1 = self.polyline(data, name, curve, log_flag=0)
        f2 = self.extrude(f'{curve}:{name}', f'{name}', f'{h}',
                          component='component1', material=material, log_flag=0)
        f1 = f1 + f2
        if theta != [0, 0, 0]:
            f3 = self.rotation(f'{name}', theta, component='component1', log_flag=0)
            f1 = f1 + f3
        f4 = self.translate(f'{name}', center, component='component1', log_flag=0)
        f1 = f1 + f4
        self.cst_file.model3d.add_to_history(" Triangle: " + name, f1)

    def create_triangular_prism(self, a, h, center, theta, name, curve,
                                material='Silicon (lossy)'):
        """
        创建正三角形棱柱（蛇形命名）
        等同于 triangle()
        """
        self.triangle(a, h, center, theta, name, curve, material)

    def hexagon(self, a, h, center, theta, name, curve='curve1',
                component='component1', material='Silicon (lossy)'):
        """
        创建正六边形棱柱三维实体模型，支持旋转+平移
        保留原函数名以兼容旧代码

        :param a: float/str, 正六边形外接圆半径
        :param h: float/str, 棱柱 Z 轴拉伸高度
        :param center: list, 最终平移中心 [X, Y, Z]
        :param theta: list, 旋转角度 [X°, Y°, Z°]
        :param name: str, 模型名称
        :param curve: str, 绘制六边形的曲线名称，默认 curve1
        :param component: str, 归属组件，默认 component1
        :param material: str, 材料名称，默认损耗硅 Silicon (lossy)
        """
        data = []
        for i in range(7):
            tmp = [f'({a})*cosd({i * 60})', f'({a})*sind({i * 60})']
            data.append(tmp)
        f1 = self.polyline(data, name, log_flag=0)
        f2 = self.extrude(f'{curve}:{name}', f'{name}', f'{h}',
                          component=component, material=material, log_flag=0)
        f1 = f1 + f2
        if theta != [0, 0, 0]:
            f3 = self.rotation(f'{name}', theta, component=component, log_flag=0)
            f1 = f1 + f3
        f4 = self.translate(f'{name}', center, component=component, log_flag=0)
        f1 = f1 + f4
        self.cst_file.model3d.add_to_history(" Hexagon: " + name, f1)

    def create_hexagonal_prism(self, a, h, center, theta, name, curve='curve1',
                               component='component1', material='Silicon (lossy)'):
        """
        创建正六边形棱柱（蛇形命名）
        等同于 hexagon()
        """
        self.hexagon(a, h, center, theta, name, curve, component, material)

    # ================================================================
    # Wire — 3D 导线/圆柱体创建
    # ================================================================

    def create_wire(self, name, start_point, end_point, radius,
                    component='component1', material='PEC',
                    segments=0):
        """
        创建 3D 导线（Wire）

        :param name: str, 导线名称
        :param start_point: list, 起点坐标 [X, Y, Z]
        :param end_point: list, 终点坐标 [X, Y, Z]
        :param radius: float/str, 导线半径
        :param component: str, 归属组件
        :param material: str, 材料名称
        :param segments: int, 分段数（0 表示自动）
        """
        f1 = f"""With Wire
     .Reset
     .Name "{name}"
     .Component "{component}"
     .Material "{material}"
     .WireRadius "{radius}"
     .X1 "{start_point[0]}"
     .Y1 "{start_point[1]}"
     .Z1 "{start_point[2]}"
     .X2 "{end_point[0]}"
     .Y2 "{end_point[1]}"
     .Z2 "{end_point[2]}"
     .Segments "{segments}"
     .Create
End With"""
        self.cst_file.model3d.add_to_history(f"Wire: {name}", f1)
