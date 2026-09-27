# -*- coding: utf-8 -*-
"""
CST 材料与组件 Mixin 模块
=========================
封装 Material、MaterialLibrary、Component 等材料与组件的创建管理

@author: PC
"""

import logging
import math
import os

from cst_solver.failures import record_failure

#: 本模块可能产出的错误码（材料名/材料库/材料文件三类）。
#: 一致性检查（`scripts/check_api_consistency.py` 的 `error-codes` 项）要求
#: 代码里用到的码必须出现在某个 `*_ERROR_CODES` 表里。
MATERIAL_ERROR_CODES = (
    'material_not_preset',        # 材料名不在预设表里（旧兼容接口，只提示不抛）
    'material_library_missing',   # 材料库目录不存在
    'material_file_not_found',    # 指定的 .mtd 不存在
    'material_file_missing',      # 材料在库里找不到对应文件
    'material_definition_empty',  # .mtd 里没有有效定义
)

_logger = logging.getLogger(__name__)


# CST 2026 Material Object 的线性色散模型参数个数。
# 系数按官方帮助的 Coeff1..Coeff4 顺序传入。
_LINEAR_DISPERSION_COEFFICIENT_COUNTS = {
    'Debye1st': 2,
    'Debye2nd': 4,
    'Drude': 2,
    'Lorentz': 3,
    'General1st': 2,
    'General2nd': 4,
}


def _parse_colour(color):
    """把颜色输入归一成 CST ``Material.Colour`` 需要的三个 0~1 字符串。

    接受的写法（其它一律抛 ``ValueError``，不做静默兑底）：

    * ``'#RRGGBB'`` / ``'RRGGBB'`` / ``'#RGB'`` —— 十六进制字符串
    * ``(r, g, b)`` / ``[r, g, b]``，三个分量都在 ``0~1`` —— 直接使用
    * ``(r, g, b)`` / ``[r, g, b]``，有分量 > 1（即 0~255 整数色）—— 自动除以 255

    :param color: 颜色输入
    :return: ``(r, g, b)`` 三个字符串（CST 的 VBA 取字符串形式的数值）
    :raises ValueError: 格式不认识，或分量超出可解释范围（如 >255、负数、NaN）
    """
    if isinstance(color, str):
        hexstr = color.strip().lstrip('#')
        if len(hexstr) == 3:
            hexstr = ''.join(ch * 2 for ch in hexstr)
        if len(hexstr) != 6:
            raise ValueError(
                f'颜色字符串 {color!r} 无法解析：支持 \'#RRGGBB\' / \'#RGB\'')
        try:
            rgb = [int(hexstr[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
        except ValueError as exc:
            raise ValueError(
                f'颜色字符串 {color!r} 含非法十六进制字符'
                f'（支持 \'#RRGGBB\' / \'#RGB\'）：{exc}') from exc
        return tuple(_fmt_colour(v) for v in rgb)

    if isinstance(color, (tuple, list)):
        if len(color) != 3:
            raise ValueError(
                f'颜色序列必须正好 3 个分量（r, g, b），收到 {len(color)} 个：{color!r}')
        try:
            vals = [float(v) for v in color]
        except (TypeError, ValueError) as exc:
            raise ValueError(f'颜色分量必须是数值：{color!r}') from exc
        if any(math.isnan(v) or math.isinf(v) for v in vals):
            raise ValueError(f'颜色分量不能是 NaN/Inf：{color!r}')
        if all(0.0 <= v <= 1.0 for v in vals):
            return tuple(_fmt_colour(v) for v in vals)
        if all(0.0 <= v <= 255.0 for v in vals):
            return tuple(_fmt_colour(v / 255.0) for v in vals)
        raise ValueError(
            f'颜色分量超范围：{color!r}；要么全部 0~1，要么全部 0~255')

    raise ValueError(
        f'颜色 {color!r} 格式不支持：用 \'(r, g, b)\'(0~1 或 0~255) 或 \'#RRGGBB\'')


def _fmt_colour(value):
    """0~1 的分量 → 紧凑字符串（去掉浮点尾巴，如 0.3058823529411765 → 0.305882）。"""
    return '%.6g' % value


def _material_dispersion_block(model, infinity, coefficients, quantity):
    """校验并生成 CST 线性材料色散 VBA 片段。

    :param model: str 或 None，CST 色散模型名
    :param infinity: float/str 或 None，高频极限值
    :param coefficients: list/tuple 或 None，Coeff1..Coeff4
    :param quantity: str，``'eps'`` 或 ``'mu'``
    :return: str，可插入 ``With Material`` 的 VBA 片段
    :raises ValueError: 模型、高频极限或系数配置不完整
    """
    suffix = 'Eps' if quantity == 'eps' else 'Mu'
    infinity_name = 'eps_infinity' if quantity == 'eps' else 'mu_infinity'
    model_name = ('dispersion_model_eps' if quantity == 'eps'
                  else 'dispersion_model_mu')
    coefficients_name = ('dispersion_coeffs_eps' if quantity == 'eps'
                         else 'dispersion_coeffs_mu')

    if model is None:
        if infinity is not None or coefficients is not None:
            raise ValueError(
                f'设置 {infinity_name} 或 {coefficients_name} 时必须同时设置 '
                f'{model_name}')
        return ''

    if model not in _LINEAR_DISPERSION_COEFFICIENT_COUNTS:
        supported = ', '.join(_LINEAR_DISPERSION_COEFFICIENT_COUNTS)
        raise ValueError(
            f'{model_name}={model!r} 不支持；可选：{supported}')
    if infinity is None:
        raise ValueError(f'{model_name}={model!r} 时必须设置 {infinity_name}')
    if not isinstance(coefficients, (list, tuple)):
        raise ValueError(f'{coefficients_name} 必须是 list 或 tuple')

    expected = _LINEAR_DISPERSION_COEFFICIENT_COUNTS[model]
    if len(coefficients) != expected:
        raise ValueError(
            f'{model_name}={model!r} 需要 {expected} 个系数，'
            f'{coefficients_name} 收到 {len(coefficients)} 个')

    lines = [
        f'            .DispModel{suffix} "{model}"',
        f'            .{suffix}Infinity "{infinity}"',
    ]
    lines.extend(
        f'            .DispCoeff{index}{suffix} "{value}"'
        for index, value in enumerate(coefficients, start=1)
    )
    return '\n'.join(lines) + '\n'


class MaterialMixin:
    """
    CST 材料与组件 Mixin
    提供材料创建、材料库调用、组件创建与管理等功能
    """

    def new_material(self, name):
        """
        在 CST 工程中创建指定的预设材料，材料属性为固定最优仿真参数
        保留原函数名以兼容旧代码

        支持的预设材料:
          - 'Copper (annealed)' — 退火铜（损耗金属）
          - 'Silicon (lossy)' — 损耗硅
          - 'Quartz (Fused) (lossy)' — 损耗熔融石英

        ⚠️ 名字不在预设表里时**行为与旧版一致**：写一条日志后返回 ``None``，
        什么也不建；同时这条失败会进入**结构化失败通道**
        （``cst_solver.failures``），因此共用服务不会把它当成功。
        需要「直接抛异常」时可开 ``cst_solver.failures.set_failure_strict(True)``；
        上层 ``topo_modeler.builders.build_materials`` 就是提前校验后抛 ``ValueError``。

        :param name: str, 材料名称
        """
        if name == 'Copper (annealed)':
            f1 = self._material_copper()
        elif name == 'Silicon (lossy)':
            f1 = self._material_silicon()
        elif name == "Quartz (Fused) (lossy)":
            f1 = self._material_quartz()
        else:
            record_failure(
                'new_material', 'material_not_preset',
                f'没有该材料，请手动添加：{name!r}',
                material=name,
                preset=['Copper (annealed)', 'Silicon (lossy)',
                        'Quartz (Fused) (lossy)'])
            return
        self.cst_file.model3d.add_to_history(name, f1)

    def create_material(self, name):
        """
        创建预设材料（蛇形命名）
        等同于 new_material()
        """
        self.new_material(name)

    def _material_copper(self):
        """退火铜材料 VBA 脚本"""
        return """
            With Material
            .Reset
            .Name "Copper (annealed)"
            .Folder ""
            .FrqType "static"
            .Type "Normal"
            .SetMaterialUnit "Hz", "mm"
            .Epsilon "1"
            .Mu "1.0"
            .Kappa "5.8e+007"
            .TanD "0.0"
            .TanDFreq "0.0"
            .TanDGiven "False"
            .TanDModel "ConstTanD"
            .KappaM "0"
            .TanDM "0.0"
            .TanDMFreq "0.0"
            .TanDMGiven "False"
            .TanDMModel "ConstTanD"
            .DispModelEps "None"
            .DispModelMu "None"
            .DispersiveFittingSchemeEps "Nth Order"
            .DispersiveFittingSchemeMu "Nth Order"
            .UseGeneralDispersionEps "False"
            .UseGeneralDispersionMu "False"
            .FrqType "all"
            .Type "Lossy metal"
            .SetMaterialUnit "GHz", "mm"
            .Mu "1.0"
            .Kappa "5.8e+007"
            .Rho "8930.0"
            .ThermalType "Normal"
            .ThermalConductivity "401.0"
            .SpecificHeat "390", "J/K/kg"
            .MetabolicRate "0"
            .BloodFlow "0"
            .VoxelConvection "0"
            .MechanicsType "Isotropic"
            .YoungsModulus "120"
            .PoissonsRatio "0.33"
            .ThermalExpansionRate "17"
            .Colour "1", "1", "0"
            .Wireframe "False"
            .Reflection "False"
            .Allowoutline "True"
            .Transparentoutline "False"
            .Transparency "0"
            .Create
            End With"""

    def _material_silicon(self):
        """损耗硅材料 VBA 脚本"""
        return """
            With Material
            .Reset
            .Name "Silicon (lossy)"
            .Folder ""
            .FrqType "all"
            .Type "Normal"
            .SetMaterialUnit "GHz", "mm"
            .Epsilon "11.9"
            .Mu "1.0"
            .Kappa "2.5e-004"
            .TanD "0.00"
            .TanDFreq "0.0"
            .TanDGiven "False"
            .TanDModel "ConstTanD"
            .KappaM "0.0"
            .TanDM "0.0"
            .TanDMFreq "0.0"
            .TanDMGiven "False"
            .TanDMModel "ConstKappa"
            .DispModelEps "None"
            .DispModelMu "None"
            .DispersiveFittingSchemeEps "General 1st"
            .DispersiveFittingSchemeMu "General 1st"
            .UseGeneralDispersionEps "False"
            .UseGeneralDispersionMu "False"
            .Rho "2330.0"
            .ThermalType "Normal"
            .ThermalConductivity "148"
            .SpecificHeat "700", "J/K/kg"
            .SetActiveMaterial "all"
            .MechanicsType "Isotropic"
            .YoungsModulus "112"
            .PoissonsRatio "0.28"
            .ThermalExpansionRate "5.1"
            .Colour "0.94", "0.82", "0.76"
            .Wireframe "False"
            .Transparency "0"
            .Create
            End With"""

    def _material_quartz(self):
        """损耗熔融石英材料 VBA 脚本"""
        return """With Material
     .Reset
     .Name "Quartz (Fused) (lossy)"
     .Folder ""
     .FrqType "all"
     .Type "Normal"
     .SetMaterialUnit "MHz", "mm"
     .Epsilon "3.75"
     .Mu "1.0"
     .Kappa "0.0"
     .TanD "0.0004"
     .TanDFreq "1.0"
     .TanDGiven "True"
     .TanDModel "ConstTanD"
     .KappaM "0.0"
     .TanDM "0.0"
     .TanDMFreq "0.0"
     .TanDMGiven "False"
     .TanDMModel "ConstKappa"
     .DispModelEps "None"
     .DispModelMu "None"
     .DispersiveFittingSchemeEps "General 1st"
     .DispersiveFittingSchemeMu "General 1st"
     .UseGeneralDispersionEps "False"
     .UseGeneralDispersionMu "False"
     .Rho "2200.0"
     .ThermalType "Normal"
     .ThermalConductivity "5"
     .SpecificHeat "700", "J/K/kg"
     .SetActiveMaterial "all"
     .MechanicsType "Isotropic"
     .YoungsModulus "75"
     .PoissonsRatio "0.17"
     .ThermalExpansionRate "0.5"
     .Colour "0.94", "0.82", "0.76"
     .Wireframe "False"
     .Transparency "0"
     .Create
End With
"""

    def create_material_custom(
            self, name, epsilon, mu, kappa, tand=None,
            material_type='Normal', color=None, colour=None,
            dispersion_model_eps=None, eps_infinity=None,
            dispersion_coeffs_eps=None, dispersion_model_mu=None,
            mu_infinity=None, dispersion_coeffs_mu=None):
        """
        创建自定义材料（简化版）

        :param name: str, 材料名称
        :param epsilon: float/str, 介电常数
        :param mu: float/str, 磁导率
        :param kappa: float/str, 电导率
        :param tand: float 可选, 损耗角正切
        :param material_type: str, 材料类型 'Normal' 或 'Lossy metal'
        :param color: 可选, 材料**显示颜色**（CST 的 ``Material.Colour``）。
            支持三种写法：``'#RRGGBB'`` / ``'#RGB'`` 十六进制字符串、
            ``(r, g, b)`` 且三分量在 0~1、``(r, g, b)`` 且三分量在 0~255
            （自动归一化）。**不传时与旧版行为完全一致**（用 CST 默认色）。
            例：``color='#4ec9b0'``、``color=(78, 201, 176)``、``color=(0.31, 0.79, 0.69)``
        :param colour: ``color`` 的英式拼写别名（两者同时给会报 ``ValueError``）
        :param dispersion_model_eps: str 可选，电色散模型。支持
            ``Debye1st`` / ``Debye2nd`` / ``Drude`` / ``Lorentz`` /
            ``General1st`` / ``General2nd``
        :param eps_infinity: float/str 可选，介电常数高频极限
        :param dispersion_coeffs_eps: list/tuple 可选，电色散 Coeff1..Coeff4。
            Drude 按 ``(等离子体频率, 碰撞频率)`` 传入，频率单位
            遵循本方法的 ``SetMaterialUnit "GHz", "mm"``
        :param dispersion_model_mu: str 可选，磁色散模型，支持集合同上
        :param mu_infinity: float/str 可选，磁导率高频极限
        :param dispersion_coeffs_mu: list/tuple 可选，磁色散 Coeff1..Coeff4
        :raises ValueError: 颜色或色散模型配置非法
        """
        if colour is not None:
            if color is not None:
                raise ValueError(
                    'color 与 colour 只能给一个（colour 是 color 的拼写别名）')
            color = colour

        tand_block = ""
        if tand is not None:
            tand_block = f'''
            .TanD "{tand}"
            .TanDGiven "True"
            .TanDModel "ConstTanD"
            '''
        colour_block = ""
        if color is not None:
            r, g, b = _parse_colour(color)
            colour_block = f'            .Colour "{r}", "{g}", "{b}"\n'
        dispersion_block = _material_dispersion_block(
            dispersion_model_eps, eps_infinity, dispersion_coeffs_eps, 'eps')
        dispersion_block += _material_dispersion_block(
            dispersion_model_mu, mu_infinity, dispersion_coeffs_mu, 'mu')
        f1 = f"""
        With Material
            .Reset
            .Name "{name}"
            .Folder ""
            .FrqType "all"
            .Type "{material_type}"
            .SetMaterialUnit "GHz", "mm"
            .Epsilon "{epsilon}"
            .Mu "{mu}"
            .Kappa "{kappa}"
            {tand_block}{colour_block}{dispersion_block}
            .Create
        End With
        """
        # 注意：历史标签保持 "Material: <name>" 不变 —— 旧工程历史里有同名条目,
        # 改了会让“对比历史”失配（开发宪法 §5.3）。
        self.cst_file.model3d.add_to_history(f"Material: {name}", f1)

    def new_component(self, name):
        """
        在 CST 工程中创建新的组件分组

        :param name: str, 新建组件名称
        """
        f1 = """
        '  new component: %s
        Component.New "%s" 
        """ % (name, name)
        self.cst_file.model3d.add_to_history("New Component: " + name, f1)

    def create_component(self, name):
        """
        创建新组件（蛇形命名）
        等同于 new_component()
        """
        self.new_component(name)

    # ---------------------------------------------------------------
    # 兼容别名：历史拼写错误（new_componet → new_component）
    # 旧脚本使用 new_componet()，保留为等价别名，请勿在新代码中使用。
    # ---------------------------------------------------------------
    new_componet = new_component

    def rename(self, old, new, type='Solid'):
        """
        更改实体或组件的名称
        保留原函数名以兼容旧代码

        :param old: str, 原名称
        :param new: str, 新名称
        :param type: str, 'Solid' 或 'Component'，默认 'Solid'
        """
        f1 = f"""
        {type}.Rename "{old}", "{new}"
        """
        self.cst_file.model3d.add_to_history('Rename: ' + old + ' to ' + new, f1)

    def rename_solid(self, old, new):
        """重命名实体（蛇形命名）"""
        self.rename(old, new, 'Solid')

    def rename_component(self, old, new):
        """重命名组件"""
        self.rename(old, new, 'Component')

    def change_component(self, model, component):
        """
        将模型移动到指定组件
        保留原函数名以兼容旧代码

        :param model: str, 模型名称
        :param component: str, 目标组件名称
        """
        f1 = f"""
        Solid.ChangeComponent "{model}", "{component}"
        """
        self.cst_file.model3d.add_to_history(
            'ChangeComponent:' + model + ' to ' + component, f1)

    def change_material(self, model, material):
        """
        更改模型的材料属性
        保留原函数名以兼容旧代码

        :param model: str, 模型名称
        :param material: str, 目标材料名称
        """
        f1 = f"""
        Solid.ChangeMaterial "{model}", "{material}"
        """
        self.cst_file.model3d.add_to_history(
            'Change_material:' + model + ' to ' + material, f1)

    def change_material_color(self, name, r, g, b, folder="",
                              wireframe=False, reflection=False,
                              allow_outline=True, transparent_outline=False,
                              transparency=0):
        """
        修改已有材料的显示颜色

        参考 CST VBA:
            With Material
                .Name "Polycarbonate (lossy)"
                .Folder ""
                .Color "0.694118", "0.694118", "0.694118"
                ...
                .ChangeColor
            End With

        :param name: str, 材料名称
        :param r: float/str, 红色通道 (0~1)
        :param g: float/str, 绿色通道 (0~1)
        :param b: float/str, 蓝色通道 (0~1)
        :param folder: str, 材料所在目录，默认根目录
        :param wireframe: bool, 是否线框显示
        :param reflection: bool, 是否反射显示
        :param allow_outline: bool, 是否允许轮廓
        :param transparent_outline: bool, 是否透明轮廓
        :param transparency: int/float/str, 透明度
        """
        f1 = f"""
        With Material
            .Name "{name}"
            .Folder "{folder}"
            .Color "{r}", "{g}", "{b}"
            .Wireframe "{str(bool(wireframe))}"
            .Reflection "{str(bool(reflection))}"
            .Allowoutline "{str(bool(allow_outline))}"
            .Transparentoutline "{str(bool(transparent_outline))}"
            .Transparency "{transparency}"
            .ChangeColor
        End With
        """
        self.cst_file.model3d.add_to_history(
            f"Change material color: {name}", f1)

    def change_material_colour(self, *args, **kwargs):
        """change_material_color() 的英式拼写别名。"""
        self.change_material_color(*args, **kwargs)

    # ================================================================
    # 材料库管理: 从 CST 材料库 .mtd 文件加载材料
    # ================================================================

    def _get_material_library_path(self):
        """
        获取 CST 材料库路径

        CST 材料库位于 CST 安装目录下的 Library\\Materials 文件夹中,
        所有材料以 .mtd 格式存储。
        路径自动从 config.py 的 CST_INSTALL_PATH 推导。

        :return: str, 材料库路径
        """
        from cst_solver.environment import get_cst_paths, CSTUnavailableError
        path = get_cst_paths().material_lib
        if path is None:
            raise CSTUnavailableError('未配置 CST 材料库，请设置 CST_INSTALL_PATH 或 CST_MATERIAL_LIB')
        return path

    def list_library_materials(self):
        """
        列出 CST 材料库中所有可用材料名称

        :return: list[str], 材料名称列表（不含 .mtd 后缀）

        用法:
            >>> app = setup("project.cst")
            >>> materials = app.list_library_materials()
            >>> print(materials)
            ['Copper (annealed)', 'Silicon (lossy)', ...]

        ⚠️ 材料库路径不存在时返回 ``[]``（与旧版一致），但会记录一条结构化失败
        （``material_library_missing``）—— 空列表不等于「库里没有材料」。
        """
        lib_path = self._get_material_library_path()
        if not os.path.exists(lib_path):
            record_failure('list_library_materials', 'material_library_missing',
                           f'材料库路径不存在: {lib_path}', path=lib_path)
            return []
        materials = []
        for f in os.listdir(lib_path):
            if f.endswith('.mtd'):
                materials.append(f[:-4])
        return sorted(materials)

    def load_material_from_file(self, filepath, name=None):
        """
        从 CST 材料库文件 (.mtd) 加载材料并导入到当前工程

        .mtd 文件是 CST 的材料定义文件，包含材料的电磁属性参数。
        可以通过 list_library_materials() 获取所有可用的材料名称,
        然后使用 get_material_filepath() 获取完整路径。

        :param filepath: str, .mtd 文件路径
            可以是绝对路径，也可以是材料库中的材料名（自动补全路径）
        :param name: str 可选, 自定义材料名称（不传则使用 .mtd 文件名）
        :return: bool, 是否成功加载

        用法:
            >>> app = setup("project.cst")
            # 方式1: 直接传文件路径
            >>> app.load_material_from_file(
            ...     r"C:\\CST\\Library\\Materials\\Copper (annealed).mtd")
            # 方式2: 传材料名自动补全路径
            >>> app.load_material_from_file("Copper (annealed)")

        注意:
            - 如果 filepath 不以 .mtd 结尾，会自动补全路径到材料库
            - 已存在的材料会被覆盖
        """
        # 自动补全路径: 如果只是材料名而非完整路径
        if not filepath.lower().endswith('.mtd'):
            lib_path = self._get_material_library_path()
            candidate = os.path.join(lib_path, filepath + '.mtd')
            if os.path.exists(candidate):
                filepath = candidate
            else:
                record_failure('load_material_from_file', 'material_file_not_found',
                               f'未找到材料文件: {filepath}', path=filepath)
                return False

        if not os.path.exists(filepath):
            record_failure('load_material_from_file', 'material_file_not_found',
                           f'材料文件不存在: {filepath}', path=filepath)
            return False

        # 解析 .mtd 文件
        material_name = name or os.path.basename(filepath).removesuffix('.mtd')
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            # 有些 mtd 文件可能使用其他编码
            with open(filepath, 'r', encoding='latin-1') as f:
                lines = f.readlines()

        # 提取 [Definition] 部分的 VBA 命令
        commands = []
        in_definition = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('['):
                in_definition = stripped == '[Definition]'
                continue
            if in_definition and stripped:
                commands.append(stripped)

        if not commands:
            record_failure('load_material_from_file', 'material_definition_empty',
                           f'材料文件 {filepath} 中未找到有效定义', path=filepath)
            return False

        # 生成 VBA 命令并写入 CST 历史
        cmd = 'With Material\n.Reset\n'
        cmd += f'.Name "{material_name}"\n'
        cmd += '\n'.join(commands)
        cmd += '\nEnd With'

        self.cst_file.model3d.add_to_history(
            f'Define material: {material_name}', cmd)
        _logger.info('已加载材料: %s', material_name)
        return True

    def get_material_filepath(self, material_name):
        """
        获取 CST 材料库中指定材料的完整文件路径

        :param material_name: str, 材料名称（如 'Copper (annealed)'）
        :return: str 或 None, 完整路径或 None（未找到时）

        ⚠️ 未找到时返回 ``None``（与旧版一致），同时记录一条结构化失败
        （``material_file_missing``）—— ``None`` 不等于「路径为空」。
        """
        lib_path = self._get_material_library_path()
        filepath = os.path.join(lib_path, material_name + '.mtd')
        if os.path.exists(filepath):
            return filepath
        record_failure('get_material_filepath', 'material_file_missing',
                       f'材料库中未找到: {material_name}',
                       material=material_name, path=filepath)
        return None
