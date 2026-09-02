# -*- coding: utf-8 -*-
"""
CST 变换操作 Mixin 模块
=======================
封装 Transform、Mirror、Align、WCS 等变换功能

@author: PC
"""


class TransformMixin:
    """
    CST 变换操作 Mixin
    提供平移、旋转、镜像、对齐、工作坐标系等变换功能
    """

    def rotation(self, name, angle, center=None, repetition=1,
                 component='component1', copy=False, unite=False, log_flag=1):
        """
        对三维实体执行旋转变换
        保留原函数名以兼容旧代码

        :param name: str, 待旋转实体名称
        :param angle: list, 旋转角度 [X°, Y°, Z°]
        :param center: list, 旋转中心 [X, Y, Z]，默认原点 [0,0,0]
        :param repetition: int, 旋转复制份数，默认1（仅旋转不复制）
        :param component: str, 归属组件
        :param copy: bool, True-复制旋转 False-直接旋转
        :param unite: bool, True-合并 False-独立
        :param log_flag: int, 0-仅返回 1-写入历史
        :return: str, CST 指令文本
        """
        if center is None:
            center = ['0', '0', '0']
        f1 = f"""With Transform 
     .Reset 
     .Name "{component}:{name}" 
     .Origin "Free" 
     .Center "{center[0]}", "{center[1]}", "{center[2]}" 
     .Angle "{angle[0]}", "{angle[1]}", "{angle[2]}" 
     .MultipleObjects "{copy}" 
     .GroupObjects "{unite}" 
     .Repetitions "{repetition}" 
     .MultipleSelection "False" 
     .AutoDestination "True" 
     .Transform "Shape", "Rotate" 
End With
"""
        if log_flag == 1:
            self.cst_file.model3d.add_to_history(" roation " + name, f1)
        return f1

    def rotate(self, name, angle, center=None, repetition=1,
               component='component1', copy=False, unite=False, log_flag=1):
        """
        旋转变换（蛇形命名）
        等同于 rotation()
        """
        return self.rotation(name, angle, center, repetition, component,
                             copy, unite, log_flag)

    def translate(self, name, vector, component='component1',
                  repetitions=1, copy=False, unite=False, log_flag=1):
        """
        对三维实体执行平移变换
        保留原函数名以兼容旧代码

        :param name: str, 待平移实体名称
        :param vector: list, 平移矢量 [X, Y, Z]
        :param component: str, 归属组件
        :param repetitions: int, 平移复制份数
        :param copy: bool, True-复制平移 False-直接平移
        :param unite: bool, True-合并 False-独立
        :param log_flag: int, 0-仅返回 1-写入历史
        :return: str, CST 指令文本
        """
        if component =='':
            f1 = f"""With Transform 
        .Reset 
        .Name "{name}" 
        .Vector "{vector[0]}", "{vector[1]}", "{vector[2]}" 
        .UsePickedPoints "False" 
        .InvertPickedPoints "False" 
        .MultipleObjects "{copy}" 
        .GroupObjects "{unite}" 
        .Repetitions "{repetitions}" 
        .MultipleSelection "False" 
        .AutoDestination "True" 
        .Transform "Shape", "Translate" 
    End With
    """
        else:    
            f1 = f"""With Transform 
        .Reset 
        .Name "{component}:{name}" 
        .Vector "{vector[0]}", "{vector[1]}", "{vector[2]}" 
        .UsePickedPoints "False" 
        .InvertPickedPoints "False" 
        .MultipleObjects "{copy}" 
        .GroupObjects "{unite}" 
        .Repetitions "{repetitions}" 
        .MultipleSelection "False" 
        .AutoDestination "True" 
        .Transform "Shape", "Translate" 
    End With
    """
        if log_flag == 1:
            self.cst_file.model3d.add_to_history(
                " translate " + name + f'{vector} {repetitions}', f1)
        return f1

    def mirror(self, name, center, plane, component='component1',
               object='Shape', copy=False, unite=False):
        """
        对实体/端口执行镜像变换
        保留原函数名以兼容旧代码

        :param name: str, 待镜像对象名称
        :param center: list, 镜像平面中心 [X, Y, Z]
        :param plane: list, 镜像平面法向量 [X, Y, Z]
        :param component: str, 归属组件
        :param object: str, 'Shape' 或 'Port'
        :param copy: bool, True-复制镜像 False-直接镜像
        :param unite: bool, True-合并 False-独立
        """
        f1 = f"""With Transform 
     .Reset 
     .Name "{component}:{name}" 
     .Origin "Free" 
     .Center "{center[0]}", "{center[1]}", "{center[2]}" 
     .PlaneNormal "{plane[0]}", "{plane[1]}", "{plane[2]}" 
     .MultipleObjects "{copy}" 
     .GroupObjects "{unite}" 
     .Repetitions "1" 
     .MultipleSelection "False" 
     .AutoDestination "True" 
     .Transform "{object}", "Mirror" 
End With
"""
        self.cst_file.model3d.add_to_history(
            name + "  mirror " + str(plane) + 'on' + str(center), f1)

    def scale(self, name, factor, center=None, component='component1'):
        """
        对三维实体执行缩放变换

        :param name: str, 实体名称
        :param factor: float/str 或 list, 缩放因子
                       单个值: [factor, factor, factor]
                       三个值: [fx, fy, fz]
        :param center: list, 缩放中心 [X, Y, Z]，默认原点
        :param component: str, 归属组件
        """
        if center is None:
            center = ['0', '0', '0']
        if isinstance(factor, (int, float)):
            factor_str = f'"{factor}"'
        else:
            factor_str = f'"{factor[0]}", "{factor[1]}", "{factor[2]}"'
        f1 = f"""With Transform
     .Reset
     .Name "{component}:{name}"
     .Origin "Free"
     .Center "{center[0]}", "{center[1]}", "{center[2]}"
     .MultipleObjects "False"
     .GroupObjects "False"
     .Repetitions "1"
     .MultipleSelection "False"
     .Destination ""
     .Material ""
     .AutoDestination "True"
     .Transform "Shape", "Scale"
End With
"""
        self.cst_file.model3d.add_to_history(f"Scale: {name}", f1)
