# -*- coding: utf-8 -*-
"""
CST 曲线绘制 Mixin 模块
=======================
封装 Polygon、Arc、Circle、Ellipse、Line、Spline 等二维/三维曲线的创建

@author: PC
"""


class CurvesMixin:
    """
    CST 曲线绘制 Mixin
    提供多边形、圆弧、圆、椭圆、直线、样条曲线等绘制功能
    """

    def polyline(self, data, name='1', curve='curve1', log_flag=1):
        """
        绘制二维多边形折线/闭合轮廓（基础绘图函数）
        保留原函数名以兼容旧代码

        :param data: list[list], 顶点坐标集合 [[x1,y1],[x2,y2],...]
                     最后一点需与第一点重合实现闭合
        :param name: str, 多边形名称，默认 '1'
        :param curve: str, 归属曲线组名称，默认 'curve1'
        :param log_flag: int, 0-仅返回指令不生效 1-写入历史并立即生效
        :return: str, CST 绘图指令文本
        """
        f1 = f"""
        With Polygon 
            .Reset 
            .Name "{name}" 
            .Curve "{curve}" 
            .Point "{data[0][0]}", "{data[0][1]}" 
        """
        f2 = """  """
        for i in range(len(data) - 1):
            f2 = f2 + f""".LineTo "{data[i + 1][0]}", "{data[i + 1][1]}" 
            """
        f3 = """.Create 
        End With
        """
        f1 = f1 + f2 + f3
        if log_flag == 1:
            self.cst_file.model3d.add_to_history(" Polyline " + name, f1)
        return f1

    def create_polygon(self, data, name='1', curve='curve1', log_flag=1):
        """
        绘制二维多边形（蛇形命名）
        等同于 polyline()
        """
        return self.polyline(data, name, curve, log_flag)

    def arc(self, center, p, angle, name="arc1", curve='curve1',
            orientation='Counterclockwise', log_flag=1):
        """
        绘制二维圆弧曲线
        保留原函数名以兼容旧代码

        :param center: list, 圆弧圆心坐标 [X, Y]
        :param p: list, 圆弧起始点坐标 [X, Y]
        :param angle: float/str, 圆弧角度（度）
        :param name: str, 圆弧名称，默认 'arc1'
        :param curve: str, 归属曲线组名称，默认 'curve1'
        :param orientation: str, 绘制方向 Counterclockwise/Clockwise
        :param log_flag: int, 0-仅返回 1-写入历史
        :return: str, CST 指令文本
        """
        f1 = f"""With Arc
        .Reset 
        .Name "{name}" 
        .Curve "{curve}" 
        .Orientation "{orientation}" 
        .XCenter "{center[0]}" 
        .YCenter "{center[1]}" 
        .X1 "{p[0]}" 
        .Y1 "{p[1]}" 
        .X2 "0.15" 
        .Y2 "-0.1" 
        .Angle "{angle}" 
        .UseAngle "True" 
        .Segments "0" 
        .Create
    End With"""
        if log_flag == 1:
            self.cst_file.model3d.add_to_history("Arc " + name, f1)
        return f1

    def create_arc(self, center, p, angle, name="arc1", curve='curve1',
                   orientation='Counterclockwise', log_flag=1):
        """
        绘制圆弧（蛇形命名）
        等同于 arc()
        """
        return self.arc(center, p, angle, name, curve, orientation, log_flag)

    def ellipse(self, a, b, center, name="arc1", curve='curve1'):
        """
        绘制二维椭圆曲线
        保留原函数名以兼容旧代码

        :param a: float/str, X 轴半径
        :param b: float/str, Y 轴半径
        :param center: list, 椭圆中心 [X, Y]
        :param name: str, 椭圆名称，默认 'arc1'
        :param curve: str, 归属曲线组，默认 'curve1'
        :return: str, CST 指令文本
        """
        f1 = f"""With Ellipse
            .Reset 
            .Name "{name}" 
            .Curve "{curve}" 
            .XRadius "{a}" 
            .YRadius "{b}" 
            .Xcenter "{center[0]}" 
            .Ycenter "{center[1]}" 
            .Segments "0" 
            .Create
        End With
        """
        self.cst_file.model3d.add_to_history("ellipse curve " + name, f1)
        return f1

    def create_ellipse(self, a, b, center, name="arc1", curve='curve1'):
        """
        绘制椭圆曲线（蛇形命名）
        等同于 ellipse()
        """
        return self.ellipse(a, b, center, name, curve)

    def create_circle(self, center, radius, name="circle1", curve='curve1'):
        """
        绘制圆形曲线

        :param center: list, 圆心坐标 [X, Y]
        :param radius: float/str, 圆半径
        :param name: str, 圆名称，默认 'circle1'
        :param curve: str, 归属曲线组，默认 'curve1'
        """
        f1 = f"""With Circle
            .Reset
            .Name "{name}"
            .Curve "{curve}"
            .Xcenter "{center[0]}"
            .Ycenter "{center[1]}"
            .Radius "{radius}"
            .Segments "0"
            .Create
        End With
        """
        self.cst_file.model3d.add_to_history(f"Circle: {name}", f1)

    def create_line(self, x1, y1, z1, x2, y2, z2, name="line1", curve='curve1'):
        """
        绘制三维直线

        :param x1,y1,z1: float/str, 起点坐标
        :param x2,y2,z2: float/str, 终点坐标
        :param name: str, 直线名称
        :param curve: str, 归属曲线组
        """
        f1 = f"""With Line
            .Reset
            .Name "{name}"
            .Curve "{curve}"
            .Point1 "{x1}", "{y1}", "{z1}"
            .Point2 "{x2}", "{y2}", "{z2}"
            .Create
        End With
        """
        self.cst_file.model3d.add_to_history(f"Line: {name}", f1)

    def create_spline(self, points, name="spline1", curve='curve1'):
        """
        绘制样条曲线

        :param points: list[list], 控制点坐标集合 [[x1,y1,z1], [x2,y2,z2], ...]
        :param name: str, 样条曲线名称
        :param curve: str, 归属曲线组
        """
        f1 = f"""With Spline
            .Reset
            .Name "{name}"
            .Curve "{curve}"
        """
        for i, pt in enumerate(points):
            if len(pt) == 2:
                f1 += f'            .Point "{pt[0]}", "{pt[1]}", "0"\n'
            else:
                f1 += f'            .Point "{pt[0]}", "{pt[1]}", "{pt[2]}"\n'
        f1 += """            .Create
        End With
        """
        self.cst_file.model3d.add_to_history(f"Spline: {name}", f1)

    def create_rectangle_curve(self, x1, y1, x2, y2, name="rect1", curve='curve1'):
        """
        绘制矩形曲线

        :param x1,y1: float/str, 矩形左下角坐标
        :param x2,y2: float/str, 矩形右上角坐标
        :param name: str, 矩形曲线名称
        :param curve: str, 归属曲线组
        """
        f1 = f"""With Rectangle
            .Reset
            .Name "{name}"
            .Curve "{curve}"
            .Xrange "{x1}", "{x2}"
            .Yrange "{y1}", "{y2}"
            .Create
        End With
        """
        self.cst_file.model3d.add_to_history(f"Rectangle: {name}", f1)

    def create_polygon_3d(self, points, name="poly3d1", curve='curve1'):
        """
        绘制三维多边形

        :param points: list[list], 三维顶点 [[x1,y1,z1], [x2,y2,z2], ...]
                       最后一点应与第一点重合实现闭合
        :param name: str, 三维多边形名称
        :param curve: str, 归属曲线组
        """
        f1 = f"""With Polygon3D
            .Reset
            .Name "{name}"
            .Curve "{curve}"
        """
        for pt in points:
            f1 += f'            .Point "{pt[0]}", "{pt[1]}", "{pt[2]}"\n'
        f1 += """            .Create
        End With
        """
        self.cst_file.model3d.add_to_history(f"Polygon3D: {name}", f1)
