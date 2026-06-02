# -*- coding: utf-8 -*-
"""
CST 端口设置 Mixin 模块
=======================
封装 Port、DiscretePort、DiscreteFacePort、FloquetPort 等端口创建

@author: PC
"""


class PortMixin:
    """
    CST 端口设置 Mixin
    提供波导端口、离散端口、集总端口、Floquet 端口等创建功能
    """

    def add_port(self, id_val, orientation='positive', shield=''):
        """
        创建标准波导端口（波端口），用于激励和采集 S 参数
        保留原函数名以兼容旧代码

        :param id_val: int/str, 端口编号
        :param orientation: str, 'positive' 或 'negative'
        :param shield: str, 端口屏蔽类型 'electric'/'magnetic'/''，默认 ''
        """
        if shield == 'electric':
            f2 = '.Shield "PEC"'
        elif shield == 'magnetic':
            f2 = '.Shield "PMC"'
        else:
            f2 = ''
        f1 = f"""With Port 
            .Reset 
            .PortNumber "{id_val}" 
            .Label ""
            .Folder ""
            .NumberOfModes "1"
            .AdjustPolarization "False"
            .PolarizationAngle "0.0"
            .ReferencePlaneDistance "0"
            .TextSize "50"
            .TextMaxLimit "0"
            .Coordinates "Picks"
            .Orientation "{orientation}"
            .PortOnBound "True"
            .ClipPickedPortToBound "False"
            .SingleEnded "False"
            .WaveguideMonitor "False"
            {f2}
            .Create 
        End With
        """
        self.cst_file.model3d.add_to_history("Define Port: " + str(id_val), f1)

    def create_waveguide_port(self, id_val, orientation='positive', shield=''):
        """
        创建波导端口（蛇形命名）
        等同于 add_port()
        """
        self.add_port(id_val, orientation, shield)

    def discrete_port(self, r0, id_val, fold='', invertdrection=False):
        """
        创建离散端口（集总端口），用于射频器件的端接激励
        保留原函数名以兼容旧代码

        :param r0: float/str, 端口特征阻抗（如 50 欧姆）
        :param id_val: int/str, 端口编号
        :param fold: str, 端口归属文件夹
        :param invertdrection: bool, 是否反转激励方向
        """
        f1 = f"""With DiscreteFacePort 
     .Reset 
     .PortNumber "{id_val}" 
     .Type "SParameter"
     .Label ""
     .Folder "{fold}"
     .Impedance "{r0}"
     .VoltageAmplitude "1.0"
     .CurrentAmplitude "1.0"
     .Monitor "True"
     .CenterEdge "True"
     .LocalCoordinates "False"
     .InvertDirection "{invertdrection}"
     .UseProjection "False"
     .ReverseProjection "False"
     .FaceType "Linear"
     .Create 
End With"""
        self.cst_file.model3d.add_to_history(
            "Define Discrete Port: " + str(id_val), f1)

    def create_discrete_face_port(self, r0, id_val, fold='', invertdrection=False):
        """
        创建离散面端口（蛇形命名）
        等同于 discrete_port()
        """
        self.discrete_port(r0, id_val, fold, invertdrection)

    def create_discrete_port(self, id_val, p1, p2, impedance=50,
                             label='', folder=''):
        """
        创建离散端口（两针脚之间）

        :param id_val: int/str, 端口编号
        :param p1: list, 针脚1坐标 [X, Y, Z]
        :param p2: list, 针脚2坐标 [X, Y, Z]
        :param impedance: float/str, 端口阻抗，默认 50 欧姆
        :param label: str, 端口标签
        :param folder: str, 归属文件夹
        """
        f1 = f"""With DiscretePort
     .Reset
     .PortNumber "{id_val}"
     .Type "SParameter"
     .Label "{label}"
     .Folder "{folder}"
     .Impedance "{impedance}"
     .VoltageAmplitude "1.0"
     .CurrentAmplitude "1.0"
     .Monitor "True"
     .SetP1 "True", "{p1[0]}", "{p1[1]}", "{p1[2]}"
     .SetP2 "True", "{p2[0]}", "{p2[1]}", "{p2[2]}"
     .LocalCoordinates "False"
     .InvertDirection "False"
     .Create
End With"""
        self.cst_file.model3d.add_to_history(
            "Define DiscretePort: " + str(id_val), f1)

    def lumped_element(self, id_val, r):
        """
        在指定位置添加集总 RLC 元件
        保留原函数名以兼容旧代码

        :param id_val: int/str, 元件编号
        :param r: float/str, 电阻值
        """
        f1 = f"""With LumpedFaceElement
     .Reset 
     .SetName "element{id_val}" 
     .Folder "Folder1" 
     .SetType "RLCSerial"
     .SetR "{r}"
     .SetL "0"
     .SetC "0"
     .SetGs "0"
     .SetI0 "1e-14"
     .SetT "300"
     .SetMonitor "True"
     .CircuitFileName ""
     .CircuitId "1"
     .UseCopyOnly "True"
     .UseRelativePath "False"
     .SetInvert "False" 
     .UseProjection "False" 
     .ReverseProjection "False" 
     .Create
End With
"""
        self.cst_file.model3d.add_to_history(
            f"Define lumped_element: {id_val}", f1)

    def create_lumped_element(self, id_val, r=0, l=0, c=0,
                              p1=None, p2=None, element_type='RLCSerial'):
        """
        创建集总 RLC 元件

        :param id_val: int/str, 元件编号
        :param r: float/str, 电阻 (Ohm)
        :param l: float/str, 电感 (H)
        :param c: float/str, 电容 (F)
        :param p1: list, 端点1坐标 [X, Y, Z]
        :param p2: list, 端点2坐标 [X, Y, Z]
        :param element_type: str, 'RLCSerial'/'RLCParallel'/'Diode' 等
        """
        if p1 is None:
            p1 = ["0", "0", "0"]
        if p2 is None:
            p2 = ["0", "0", "0.1"]
        f1 = f"""With LumpedFaceElement
     .Reset 
     .SetName "element{id_val}" 
     .Folder "Folder1" 
     .SetType "{element_type}"
     .SetR "{r}"
     .SetL "{l}"
     .SetC "{c}"
     .SetGs "0"
     .SetI0 "1e-14"
     .SetT "300"
     .SetMonitor "True"
     .SetP1 "True", "{p1[0]}", "{p1[1]}", "{p1[2]}"
     .SetP2 "True", "{p2[0]}", "{p2[1]}", "{p2[2]}"
     .SetInvert "False" 
     .UseProjection "False" 
     .ReverseProjection "False" 
     .Create
End With
"""
        self.cst_file.model3d.add_to_history(
            f"Create lumped element: {id_val}", f1)

    # ================================================================
    # Floquet 端口（用于周期结构/频率选择表面）
    # ================================================================

    def create_floquet_port(self, id_val, number_of_modes=2,
                            label='', folder=''):
        """
        创建 Floquet 端口（周期性端口）
        适用于周期结构、频率选择表面 (FSS)、超表面等场景

        :param id_val: int/str, 端口编号
        :param number_of_modes: int, 模式数量，默认 2（TE0,0 + TM0,0）
        :param label: str, 端口标签
        :param folder: str, 端口归属文件夹
        """
        f1 = f"""With FloquetPort
     .Reset
     .PortNumber "{id_val}"
     .Label "{label}"
     .Folder "{folder}"
     .NumberOfModes "{number_of_modes}"
     .Distance "0"
     .Create
End With"""
        self.cst_file.model3d.add_to_history(
            f"FloquetPort: {id_val}", f1)

    def create_cable_port(self, id_val, label='', impedance=50):
        """
        创建电缆端口

        :param id_val: int/str, 端口编号
        :param label: str, 端口标签
        :param impedance: float, 端口阻抗，默认 50 欧姆
        """
        f1 = f"""With CablePort
     .Reset
     .PortNumber "{id_val}"
     .Label "{label}"
     .Impedance "{impedance}"
     .Create
End With"""
        self.cst_file.model3d.add_to_history(
            f"CablePort: {id_val}", f1)
