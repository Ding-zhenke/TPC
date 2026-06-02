# -*- coding: utf-8 -*-
"""
CST 激励源 Mixin 模块
=====================
封装 PlaneWave、CurrentPort、Coil、VoltageWire 等激励源创建

@author: PC
"""


class SourceMixin:
    """
    CST 激励源 Mixin
    提供平面波、电流源、线圈、电压线、电荷、电流路径等激励源创建
    """

    def create_plane_wave(self, name, direction, polarization,
                          frequency=None, phase=0):
        """
        创建平面波激励

        :param name: str, 平面波名称
        :param direction: list, 传播方向向量 [X, Y, Z]
        :param polarization: list, 极化方向向量 [X, Y, Z]
        :param frequency: float 可选, 平面波频率
        :param phase: float, 相位（度），默认 0
        """
        freq_line = ""
        if frequency:
            freq_line = f'\n            .Frequency "{frequency}"'
        f1 = f"""With PlaneWave
     .Reset
     .Name "{name}"
     .PropagationDirection "{direction[0]}", "{direction[1]}", "{direction[2]}"
     .Polarization "{polarization[0]}", "{polarization[1]}", "{polarization[2]}"
     .Phase "{phase}"
     {freq_line}
     .Create
End With"""
        self.cst_file.model3d.add_to_history(f"PlaneWave: {name}", f1)

    def create_current_port(self, id_val, p1, p2, current=1.0, label=''):
        """
        创建电流端口激励

        :param id_val: int/str, 端口编号
        :param p1: list, 端点1坐标 [X, Y, Z]
        :param p2: list, 端点2坐标 [X, Y, Z]
        :param current: float, 电流值 (A)，默认 1.0
        :param label: str, 端口标签
        """
        f1 = f"""With CurrentPort
     .Reset
     .PortNumber "{id_val}"
     .Label "{label}"
     .Current "{current}"
     .SetP1 "True", "{p1[0]}", "{p1[1]}", "{p1[2]}"
     .SetP2 "True", "{p2[0]}", "{p2[1]}", "{p2[2]}"
     .Create
End With"""
        self.cst_file.model3d.add_to_history(f"CurrentPort: {id_val}", f1)

    def create_coil(self, name, turns, radius, current=1.0,
                    center=None, axis='z'):
        """
        创建线圈激励

        :param name: str, 线圈名称
        :param turns: int, 匝数
        :param radius: float, 线圈半径
        :param current: float, 电流 (A)，默认 1.0
        :param center: list, 线圈中心 [X, Y, Z]，默认原点
        :param axis: str, 线圈轴向 'x'/'y'/'z'
        """
        if center is None:
            center = [0, 0, 0]
        f1 = f"""With Coil
     .Reset
     .Name "{name}"
     .Turns "{turns}"
     .Radius "{radius}"
     .Current "{current}"
     .Xcenter "{center[0]}"
     .Ycenter "{center[1]}"
     .Zcenter "{center[2]}"
     .Axis "{axis}"
     .Create
End With"""
        self.cst_file.model3d.add_to_history(f"Coil: {name}", f1)

    def create_voltage_wire(self, id_val, p1, p2, voltage=1.0):
        """
        创建电压线激励

        :param id_val: int/str, 编号
        :param p1: list, 端点1坐标 [X, Y, Z]
        :param p2: list, 端点2坐标 [X, Y, Z]
        :param voltage: float, 电压值 (V)，默认 1.0
        """
        f1 = f"""With VoltageWire
     .Reset
     .PortNumber "{id_val}"
     .Voltage "{voltage}"
     .SetP1 "True", "{p1[0]}", "{p1[1]}", "{p1[2]}"
     .SetP2 "True", "{p2[0]}", "{p2[1]}", "{p2[2]}"
     .Create
End With"""
        self.cst_file.model3d.add_to_history(f"VoltageWire: {id_val}", f1)

    def create_charge(self, name, charge_value, center=None):
        """
        创建电荷激励

        :param name: str, 电荷名称
        :param charge_value: float, 电荷量
        :param center: list, 位置 [X, Y, Z]，默认原点
        """
        if center is None:
            center = [0, 0, 0]
        f1 = f"""With Charge
     .Reset
     .Name "{name}"
     .Charge "{charge_value}"
     .Xcenter "{center[0]}"
     .Ycenter "{center[1]}"
     .Zcenter "{center[2]}"
     .Create
End With"""
        self.cst_file.model3d.add_to_history(f"Charge: {name}", f1)

    def create_current_path(self, name, current=1.0, component='component1'):
        """
        创建电流路径激励

        :param name: str, 电流路径名称
        :param current: float, 电流值 (A)
        :param component: str, 归属组件
        """
        f1 = f"""With CurrentPath
     .Reset
     .Name "{name}"
     .Current "{current}"
     .Create
End With"""
        self.cst_file.model3d.add_to_history(f"CurrentPath: {name}", f1)

    def create_magnet(self, name, coercivity, remanence, axis='z'):
        """
        创建永磁体

        :param name: str, 永磁体名称
        :param coercivity: float, 矫顽力 (A/m)
        :param remanence: float, 剩磁 (T)
        :param axis: str, 磁化方向 'x'/'y'/'z'
        """
        f1 = f"""With Magnet
     .Reset
     .Name "{name}"
     .Coercivity "{coercivity}"
     .Remanence "{remanence}"
     .Axis "{axis}"
     .Create
End With"""
        self.cst_file.model3d.add_to_history(f"Magnet: {name}", f1)

    # ================================================================
    # 补充场源: FieldSource, PredefinedField
    # ================================================================

    def create_field_source(self, name, filename):
        """
        从文件创建场源激励

        :param name: str, 场源名称
        :param filename: str, 场数据文件路径
        """
        f1 = f"""With FieldSource
     .Reset
     .Name "{name}"
     .FileName "{filename}"
     .Create
End With"""
        self.cst_file.model3d.add_to_history(f"FieldSource: {name}", f1)

    def create_predefined_field(self, name, field_type='E', amplitude='1.0'):
        """
        创建预定义场激励

        :param name: str, 场名称
        :param field_type: str, 场类型 'E'-电场 'H'-磁场，默认 'E'
        :param amplitude: str, 场幅度，默认 '1.0'
        """
        f1 = f"""With PredefinedField
     .Reset
     .Name "{name}"
     .FieldType "{field_type}"
     .Amplitude "{amplitude}"
     .Create
End With"""
        self.cst_file.model3d.add_to_history(f"PredefinedField: {name}", f1)

    # ================================================================
    # FarfieldSource — 远场源激励
    # ================================================================

    def create_farfield_source(self, name, source_file, polarization='Theta',
                               distance=1.0):
        """
        创建远场源激励（用于天线耦合仿真等）

        :param name: str, 远场源名称
        :param source_file: str, 远场源文件路径 (*.farfield 或 *.txt)
        :param polarization: str, 极化类型 'Theta'/'Phi'/'Both'
        :param distance: float, 源到目标距离（波长）
        """
        f1 = f"""With FarfieldSource
     .Reset
     .Name "{name}"
     .SourceFile "{source_file}"
     .Polarization "{polarization}"
     .Distance "{distance}"
     .Create
End With"""
        self.cst_file.model3d.add_to_history(
            f"FarfieldSource: {name}", f1)

    # ================================================================
    # TimeSignal — 时域信号定义
    # ================================================================

    def create_time_signal(self, name, signal_type='Gaussian',
                           amplitude=1.0, center_time=0.0,
                           width=1.0, frequency=1.0):
        """
        创建时域信号定义（用于时域求解器激励）

        :param name: str, 信号名称
        :param signal_type: str, 信号类型
            'Gaussian' / 'GaussianSingleCycle' / 'Ramp' / 'Step' / 'Custom'
        :param amplitude: float, 信号幅度
        :param center_time: float, 中心时间
        :param width: float, 信号宽度
        :param frequency: float, 调制频率（仅 GaussianSingleCycle）
        """
        f1 = f"""With TimeSignal
     .Reset
     .Name "{name}"
     .Type "{signal_type}"
     .Amplitude "{amplitude}"
     .CenterTime "{center_time}"
     .Width "{width}"
"""
        if signal_type == 'GaussianSingleCycle':
            f1 += f'     .Frequency "{frequency}"\n'
        f1 += """     .Create
End With"""
        self.cst_file.model3d.add_to_history(f"TimeSignal: {name}", f1)
