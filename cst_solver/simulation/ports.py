# -*- coding: utf-8 -*-
"""
CST 端口设置 Mixin 模块
=======================
封装 Port、DiscretePort、DiscreteFacePort、FloquetPort 等端口创建

@author: PC
"""

import warnings

#: ``Port.Orientation`` 的**合法值全集** —— CST 的位置枚举
#: （官方 VBA 帮助：Port Object → Orientation，"the direction of the excitation"）。
#:
#: ⚠️ 它**不是** `'positive'/'negative'`：往这一行写非法值时 CST **不报错**
#: （`get_messages()` 也干净），会静默退回默认朝向 —— 表现是端口箭头朝外、
#: S21 与预期相反（2026-09-20 真机实测确认）。
PORT_ORIENTATIONS = ('xmin', 'xmax', 'ymin', 'ymax', 'zmin', 'zmax')

#: 历史上被误当成合法值的写法（本库旧默认值、旧 notebook 都在用）—— 一律拒绝。
_PORT_ORIENTATION_MISTAKES = ('positive', 'negative', 'pos', 'neg', 'plus', 'minus')

_ORIENTATION_FIX_HINT = (
    "改法（朝向 = 激励波**传入器件**的方向；x 向直波导两端都朝器件内部）：\n"
    "    app.add_port(1, orientation='xmin')   # 端口在 x_min 端面 → 激励朝 +x\n"
    "    app.add_port(2, orientation='xmax')   # 端口在 x_max 端面 → 激励朝 −x\n"
    "  轴对齐矩形端面也可用 create_waveguide_port_free(..., orientation=...) 直接给范围。"
)


def check_port_orientation(orientation, where='add_port'):
    """
    校验并归一化 ``Port.Orientation``（防呆入口）。

    设计取舍（为什么非法值抛错、``None`` 只警告）：

    - **非法值抛 ``ValueError``**：`'positive'/'negative'` 这类写法曾被 CST 静默忽略，
      是"端口朝向反了但一切看起来都正常"的根因，必须让调用方当场看见。
    - **``None`` 只警告 + 不下发该行**：这等价于改动前 CST 的实际行为
      （`.Reset` 后的默认朝向，实测等价于 `zmin`），所以既有代码不会因为本次加固而改变
      建模结果；但会打一条 ``UserWarning``，提示"你没说朝向"。

    :param orientation: str 可选, 调用方给的朝向
    :param where: str, 调用方名字（用于错误/警告信息）
    :return: str 或 None。合法枚举返回**小写**字符串；``None`` 表示不下发
        ``.Orientation`` 行（交给 CST 默认值）
    :raises ValueError: 给了非法值（尤其 `'positive'/'negative'`）
    """
    if orientation is None:
        warnings.warn(
            f"{where}() 没有指定端口朝向（orientation=None）⇒ 不下发 .Orientation 行，"
            f"CST 会用它自己的默认值（实测等价于 'zmin'），端口激励方向很可能不是你要的。"
            f"合法值（位置枚举）：{' / '.join(PORT_ORIENTATIONS)}。\n"
            f"{_ORIENTATION_FIX_HINT}",
            UserWarning, stacklevel=3)
        return None

    value = orientation.strip().lower() if isinstance(orientation, str) else orientation
    if value in PORT_ORIENTATIONS:
        return value

    if value in _PORT_ORIENTATION_MISTAKES:
        raise ValueError(
            f"orientation={orientation!r} 不是 CST 的合法值：`Port.Orientation` **只接受位置枚举** "
            f"{' / '.join(PORT_ORIENTATIONS)}。\n"
            f"  写 'positive'/'negative' 时 CST **不报错、不告警**（get_messages() 也是干净的），"
            f"它把这一行静默忽略、退回默认朝向 ⇒ 端口箭头朝外、S21 与预期相反。\n"
            f"{_ORIENTATION_FIX_HINT}")
    raise ValueError(
        f"orientation={orientation!r} 不认识：`Port.Orientation` 的合法值是位置枚举 "
        f"{' / '.join(PORT_ORIENTATIONS)}。\n{_ORIENTATION_FIX_HINT}")


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

    def add_port(self, id_val, orientation=None, shield='',
                 *, number_of_modes=1, adjust_polarization='False',
                 polarization_angle='0.0', reference_plane_distance='0',
                 port_on_bound=True, clip_picked_port_to_bound=False):
        """
        创建标准波导端口（波端口），用于激励和采集 S 参数
        保留原函数名以兼容旧代码

        阶段 5.8：把原先写死的四项开放为**关键字参数**（默认值与改动前**逐字节相同**，
        不传就等于老行为）：

        - ``number_of_modes`` → ``.NumberOfModes``（多模波导/过模传输时用得到）
        - ``adjust_polarization`` / ``polarization_angle`` → ``.AdjustPolarization`` / ``.PolarizationAngle``
        - ``reference_plane_distance`` → ``.ReferencePlaneDistance``（参考面回退距离，做去嵌入时用）

        端口朝向（2026-09-20 加固）：见 :func:`check_port_orientation`。一句话 ——
        **朝向必须给位置枚举**（`xmin/xmax/ymin/ymax/zmin/zmax`），取"激励波传入器件"的方向；
        `'positive'/'negative'` 会抛 ``ValueError``，``None`` 会打 ``UserWarning``。

        端口与计算域边界（2026-09-23 修复）：原先 ``.PortOnBound`` 被写死成 ``"True"``，
        于是**域内部**的端口只能靠手改 VBA 才能建。现在开放为 ``port_on_bound``：

        - ``port_on_bound=True``（默认）⇒ ``.PortOnBound "True"``：
          **端口面必须落在计算域边界平面上**（直波导两端、天线入口的常规做法）；
        - ``port_on_bound=False`` ⇒ ``.PortOnBound "False"``：
          允许端口位于计算域**内部**，此时端口位置由 ``.Xrange/.Yrange/.Zrange``
          决定（本方法的 picked 端口由拾取面决定 —— 官方原文：
          ``PortOnBound`` *is not relevant for picked ports*）。

        拾取端口还有一个专用开关 ``clip_picked_port_to_bound``
        （官方 ``ClipPickedPortToBound``：**只对 picked 端口有效**）：
        置 True 会把拾取到的端口面**吸附到计算域边界平面**，
        正好用来修「拾取面比边界略靠里 ⇒ 端口不在边界平面上」的情形。

        :param id_val: int/str, 端口编号
        :param orientation: str 可选, 端口激励方向，取 ``PORT_ORIENTATIONS``
            里的位置枚举；不传 = 不下发 ``.Orientation`` 行（CST 默认值）+ 告警
        :param shield: str, 端口屏蔽类型 'electric'/'magnetic'/''，默认 ''
        :param number_of_modes: int, 端口模式数，默认 1
        :param adjust_polarization: str/bool, 是否自动调整极化，默认 'False'
        :param polarization_angle: float/str, 极化角（度），默认 '0.0'
        :param reference_plane_distance: float/str, 参考面距离，默认 '0'
        :param port_on_bound: bool, 端口是否位于计算域**边界平面**上，默认 True
            （改 False ⇒ 端口可在域内部，位置由范围/拾取决定）
        :param clip_picked_port_to_bound: bool, 是否把**拾取**到的端口面吸附到
            计算域边界，默认 False（CST 默认值，保持既有 VBA 一字不变）
        :raises ValueError: ``orientation`` 不是合法位置枚举
        """
        ori = check_port_orientation(orientation, where='add_port')
        ori_line = f'            .Orientation "{ori}"\n' if ori else ''
        on_bound_str = 'True' if port_on_bound else 'False'
        clip_str = 'True' if clip_picked_port_to_bound else 'False'
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
{ori_line}            .PortOnBound "{on_bound_str}"
            .ClipPickedPortToBound "{clip_str}"
            .SingleEnded "False"
            .WaveguideMonitor "False"
            {f2}
            .Create 
        End With
        """
        self.cst_file.model3d.add_to_history("Define Port: " + str(id_val), f1)

    def create_waveguide_port(self, id_val, orientation=None, shield='',
                              **kwargs):
        """
        创建波导端口（蛇形命名）
        等同于 add_port()

        :param orientation: str 可选, 同 ``add_port``：位置枚举（``xmin``…``zmax``），
            不传 = 不下发 ``.Orientation`` 行 + 告警；非法值抛 ``ValueError``
        :param kwargs: 透传给 ``add_port()`` 的关键字参数
            （``number_of_modes`` / ``adjust_polarization`` /
            ``polarization_angle`` / ``reference_plane_distance`` /
            ``port_on_bound`` / ``clip_picked_port_to_bound``）
        """
        self.add_port(id_val, orientation, shield, **kwargs)

    def create_waveguide_port_free(self, id_val, xrange=None, yrange=None,
                                   zrange=None, orientation=None,
                                   shield='', *, number_of_modes=1,
                                   adjust_polarization='False',
                                   polarization_angle='0.0',
                                   reference_plane_distance='0',
                                   port_on_bound=True):
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

        端口与计算域边界（2026-09-23 修复）：``.PortOnBound`` 原先写死 ``"True"``，
        对**域内部**的端口是错的。现在由 ``port_on_bound`` 控制：

        - ``port_on_bound=True``（默认）⇒ 端口面必须落在计算域**边界平面**上；
        - ``port_on_bound=False`` ⇒ 端口可在计算域**内部**，位置完全由
          ``xrange`` / ``yrange`` / ``zrange`` 决定
          （官方 Free 端口示例正是 ``.PortOnBound (False)``）。

        不确定时怎么选：端口矩形贴着计算域的一个端面 ⇒ True；
        端口被 ``Boundary`` 的 ``XminSpace`` 等扩展空间推到了域**内部**、
        或者你希望端口面浮在器件入口处 ⇒ False。CST 对「端口面不在边界平面上
        却声明 True」通常不会给出清晰报错，所以这里不做静默猜测 —— 由调用方明示。

        :param id_val: int/str, 端口编号
        :param xrange: tuple, (min, max)，x 方向范围，元素可为 CST 表达式
        :param yrange: tuple, (min, max)，y 方向范围，元素可为 CST 表达式
        :param zrange: tuple, (min, max)，z 方向范围，元素可为 CST 表达式
        :param orientation: str 可选, 端口激励方向，取 ``PORT_ORIENTATIONS`` 里的位置枚举
            （`xmin/xmax/ymin/ymax/zmin/zmax`）；不传 = 不下发 ``.Orientation`` 行
            （CST 默认值，实测等价于 `zmin`）+ 告警；`'positive'/'negative'` 抛 ``ValueError``
        :param shield: str, 端口屏蔽类型 'electric'/'magnetic'/''，默认 ''
        :param number_of_modes: int, 端口模式数，默认 1（阶段 5.8 新增）
        :param adjust_polarization: str/bool, 是否自动调整极化，默认 'False'（阶段 5.8 新增）
        :param polarization_angle: float/str, 极化角（度），默认 '0.0'（阶段 5.8 新增）
        :param reference_plane_distance: float/str, 参考面距离，默认 '0'（阶段 5.8 新增）
        :param port_on_bound: bool, 端口是否位于计算域**边界平面**上，默认 True（2026-09-23 新增）
        :raises ValueError: 三个方向的范围全部为 None，无法确定端口面；或 orientation 非法
        """
        if xrange is None and yrange is None and zrange is None:
            raise ValueError(
                "create_waveguide_port_free 至少需要给出一个方向的范围"
                "（xrange / yrange / zrange），否则无法确定端口面；"
                "若确实要按面拾取建端口，请用 create_waveguide_port()")

        ori = check_port_orientation(orientation,
                                     where='create_waveguide_port_free')
        ori_line = f'            .Orientation "{ori}" \n' if ori else ''
        on_bound_str = 'True' if port_on_bound else 'False'

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
{ori_line}            .PortOnBound "{on_bound_str}" 
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
