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
                 component='component1', copy=False, unite=False, log_flag=1,
                 object='Shape', auto_destination='True'):
        """
        对三维实体 / **端口** 执行旋转变换
        保留原函数名以兼容旧代码

        ★ 端口必须显式给 object='Port'：
          · `.Transform "Shape", "Rotate"` 只作用于实体，端口不会跟着走；
          · 端口名不带组件前缀（写 `Name "Port 2"`，不是 `"component1:Port 2"`）；
          · 转端口时 .AutoDestination 一般要给 'False'。
          （与 mirror() 的 object='Shape'|'Port' 用法对称）

        :param object: str, 'Shape' 旋转实体（默认）| 'Port' 旋转端口对象本身
        :param auto_destination: str, 'True'（默认，与旧行为一致）| 'False'（端口用）

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
        if object == 'Port':
            # 端口：去掉组件前缀 + 把目标换成 "Port" + 覆盖 AutoDestination
            f1 = (f1.replace(f'{component}:{name}', name)
                    .replace('"Shape", "Rotate"', '"Port", "Rotate"')
                    .replace('.AutoDestination "True"',
                             f'.AutoDestination "{auto_destination}"'))
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

    def rotate_port(self, name, angle, center=None, copy=False,
                    component='component1', log_flag=1):
        """
        **旋转『端口』对象本身**（等价于 `rotation(name, angle, object='Port',
        auto_destination='False')`）。

        为什么必须单独转：`rotation()` 下发的是 `.Transform "Shape", "Rotate"`，
        只作用于实体 —— 实体转了，端口还留在原地（曾出现 6 个端口全堆在 0° 的情况）。

        `copy=True` 时是**复制并旋转**：原端口保留、副本落到对称位置
        —— 一次操作就能把对称臂上的端口补齐（例如转 180° 补齐对径臂的 2 个端口）。

        用法：
            >>> app.rotate_port(4, [0, 0, 180])                 # 端口 4 转 180°
            >>> app.rotate_port('Port 2', [0, 0, 180], copy=True)  # 端口 2 复制并转 180° ⇒ 新增一个端口

        :param name: str/int, 端口名（'Port 2'）或端口号（2）
        :param angle: list, 旋转角度 [X°, Y°, Z°]
        :param center: list, 旋转中心 [X, Y, Z]，默认原点 [0,0,0]
        :param copy: bool, True-复制（原端口保留） False-只旋转
        :param component: str, 归属组件（仅用于拼 name，端口实际不带组件前缀）
        :param log_flag: int, 0-仅返回 1-写入历史
        :return: str, CST 指令文本
        """
        _port = f'Port {name}' if isinstance(name, (int, float)) else str(name)
        return self.rotation(_port, angle, center=center, copy=copy,
                             component=component, log_flag=log_flag,
                             object='Port', auto_destination='False')

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
