# -*- coding: utf-8 -*-
"""
CST 端口设置 Mixin 模块
=======================
封装 Port、DiscretePort、DiscreteFacePort、FloquetPort 等端口创建

@author: PC
"""


def _resolve_legacy_invert_direction(invert_direction, legacy_kwargs, func_name):
    """
    解析 `invert_direction`，并兼容旧拼写关键字 `invertdrection`。

    早期版本把 `invert_direction` 误拼为 `invertdrection`，调用方可能仍在用旧拼写。
    本函数把旧关键字映射到新参数上；若同时传入两者则报错；其余未知关键字同样报错。

    :param invert_direction: bool, 新拼写的参数值
    :param legacy_kwargs: dict, 收集到的多余关键字参数
    :param func_name: str, 调用方函数名（用于错误信息）
    :return: bool, 最终生效的反转方向开关
    :raises TypeError: 同时传入新旧拼写，或传入了未知关键字
    """
    legacy = legacy_kwargs.pop('invertdrection', None)
    if legacy is not None:
        if invert_direction is not False:
            raise TypeError(
                f"{func_name}() 同时收到了 invert_direction 和已废弃的 invertdrection，"
                "请只使用 invert_direction")
        invert_direction = legacy
    if legacy_kwargs:
        unknown = ', '.join(sorted(legacy_kwargs))
        raise TypeError(f"{func_name}() 收到未知关键字参数: {unknown}")
    return invert_direction


class PortMixin:
    """
    CST 端口设置 Mixin
    提供波导端口、离散端口、集总端口、Floquet 端口等创建功能
    """

    def add_port(self, id_val, orientation='positive', shield='',
                 *, number_of_modes=1, adjust_polarization='False',
                 polarization_angle='0.0', reference_plane_distance='0'):
        """
        创建标准波导端口（波端口），用于激励和采集 S 参数
        保留原函数名以兼容旧代码

        阶段 5.8：把原先写死的四项开放为**关键字参数**（默认值与改动前**逐字节相同**，
        不传就等于老行为）：

        - ``number_of_modes`` → ``.NumberOfModes``（多模波导/过模传输时用得到）
        - ``adjust_polarization`` / ``polarization_angle`` → ``.AdjustPolarization`` / ``.PolarizationAngle``
        - ``reference_plane_distance`` → ``.ReferencePlaneDistance``（参考面回退距离，做去嵌入时用）

        :param id_val: int/str, 端口编号
        :param orientation: str, 'positive' 或 'negative'
        :param shield: str, 端口屏蔽类型 'electric'/'magnetic'/''，默认 ''
        :param number_of_modes: int, 端口模式数，默认 1
        :param adjust_polarization: str/bool, 是否自动调整极化，默认 'False'
        :param polarization_angle: float/str, 极化角（度），默认 '0.0'
        :param reference_plane_distance: float/str, 参考面距离，默认 '0'
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
            .NumberOfModes "{number_of_modes}"
            .AdjustPolarization "{adjust_polarization}"
            .PolarizationAngle "{polarization_angle}"
            .ReferencePlaneDistance "{reference_plane_distance}"
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

    def create_waveguide_port(self, id_val, orientation='positive', shield='',
                              **kwargs):
        """
        创建波导端口（蛇形命名）
        等同于 add_port()

        :param kwargs: 透传给 ``add_port()`` 的关键字参数
            （``number_of_modes`` / ``adjust_polarization`` /
            ``polarization_angle`` / ``reference_plane_distance``）
        """
        self.add_port(id_val, orientation, shield, **kwargs)

    def create_waveguide_port_free(self, id_val, xrange=None, yrange=None,
                                   zrange=None, orientation='positive',
                                   shield='', *, number_of_modes=1,
                                   adjust_polarization='False',
                                   polarization_angle='0.0',
                                   reference_plane_distance='0'):
        """
        用**坐标范围**创建波导端口（``Coordinates "Free"``），无需任何面拾取。

        与 ``create_waveguide_port`` 的分工：后者走 ``Coordinates "Picks"``，
        必须先 ``pick_face`` 选到面才生效，而面编号与实体几何、生成顺序强相关，
        扭转/布尔/阵列之后会变；本方法直接给出端口矩形范围，不产生拾取动作，
        因此可复现性更好，也不会因几何微调而指错面。

        适用范围：**轴对齐的矩形端口面**（直波导两端、单元天线入口）。
        非轴对齐面（拐弯/扭转后的波导端面）不适用 —— 仍走
        ``pick_face + add_port``，或先用 ``pick_face_at`` 按坐标拾取。

        三个方向的范围至少给出一个；未给出的方向沿用 ``.Reset`` 后的默认值。
        端口面所处的平面由所给范围决定（例如只给 ``xrange`` + ``yrange``
        时端口法向沿 z）。

        :param id_val: int/str, 端口编号
        :param xrange: tuple, (min, max)，x 方向范围，元素可为 CST 表达式
        :param yrange: tuple, (min, max)，y 方向范围，元素可为 CST 表达式
        :param zrange: tuple, (min, max)，z 方向范围，元素可为 CST 表达式
        :param orientation: str, 端口法向朝向，沿用 ``add_port`` 的约定
        :param shield: str, 端口屏蔽类型 'electric'/'magnetic'/''，默认 ''
        :param number_of_modes: int, 端口模式数，默认 1（阶段 5.8 新增）
        :param adjust_polarization: str/bool, 是否自动调整极化，默认 'False'（阶段 5.8 新增）
        :param polarization_angle: float/str, 极化角（度），默认 '0.0'（阶段 5.8 新增）
        :param reference_plane_distance: float/str, 参考面距离，默认 '0'（阶段 5.8 新增）
        :raises ValueError: 三个方向的范围全部为 None，无法确定端口面
        """
        if xrange is None and yrange is None and zrange is None:
            raise ValueError(
                "create_waveguide_port_free 至少需要给出一个方向的范围"
                "（xrange / yrange / zrange），否则无法确定端口面；"
                "若确实要按面拾取建端口，请用 create_waveguide_port()")

        ranges = ''
        for _line, _val in (('.Xrange', xrange), ('.Yrange', yrange),
                            ('.Zrange', zrange)):
            if _val is not None:
                ranges += f'{_line} {_val[0]}, {_val[1]}\n            '

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
            .NumberOfModes "{number_of_modes}" 
            .AdjustPolarization "{adjust_polarization}" 
            .PolarizationAngle "{polarization_angle}" 
            .ReferencePlaneDistance "{reference_plane_distance}" 
            .TextSize "50" 
            .TextMaxLimit "0" 
            .Coordinates "Free" 
            .Orientation "{orientation}" 
            .PortOnBound "True" 
            .ClipPickedPortToBound "False" 
            {ranges}.SingleEnded "False" 
            .WaveguideMonitor "False" 
            {f2}
            .Create 
        End With
        """
        self.cst_file.model3d.add_to_history(
            "Define Free Port: " + str(id_val), f1)

    def discrete_port(self, r0, id_val, fold='', invert_direction=False,
                      **legacy_kwargs):
        """
        创建离散端口（集总端口），用于射频器件的端接激励
        保留原函数名以兼容旧代码

        :param r0: float/str, 端口特征阻抗（如 50 欧姆）
        :param id_val: int/str, 端口编号
        :param fold: str, 端口归属文件夹
        :param invert_direction: bool, 是否反转激励方向
        :param legacy_kwargs: 仅用于兼容旧拼写关键字 `invertdrection`（已废弃）
        :raises TypeError: 传入了未知关键字参数
        """
        invert_direction = _resolve_legacy_invert_direction(
            invert_direction, legacy_kwargs, 'discrete_port')
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
     .InvertDirection "{invert_direction}"
     .UseProjection "False"
     .ReverseProjection "False"
     .FaceType "Linear"
     .Create 
End With"""
        self.cst_file.model3d.add_to_history(
            "Define Discrete Port: " + str(id_val), f1)

    def create_discrete_face_port(self, r0, id_val, fold='', invert_direction=False,
                                  **legacy_kwargs):
        """
        创建离散面端口（蛇形命名）
        等同于 discrete_port()
        """
        self.discrete_port(r0, id_val, fold, invert_direction, **legacy_kwargs)

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
