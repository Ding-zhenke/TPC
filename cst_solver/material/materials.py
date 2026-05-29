# -*- coding: utf-8 -*-
"""
CST 材料与组件 Mixin 模块
=========================
封装 Material、MaterialLibrary、Component 等材料与组件的创建管理

@author: PC
"""

import os


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

        :param name: str, 材料名称
        """
        if name == 'Copper (annealed)':
            f1 = self._material_copper()
        elif name == 'Silicon (lossy)':
            f1 = self._material_silicon()
        elif name == "Quartz (Fused) (lossy)":
            f1 = self._material_quartz()
        else:
            print("没有该材料，请手动添加")
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

    def create_material_custom(self, name, epsilon, mu, kappa, tand=None,
                               material_type='Normal'):
        """
        创建自定义材料（简化版）

        :param name: str, 材料名称
        :param epsilon: float/str, 介电常数
        :param mu: float/str, 磁导率
        :param kappa: float/str, 电导率
        :param tand: float 可选, 损耗角正切
        :param material_type: str, 材料类型 'Normal' 或 'Lossy metal'
        """
        tand_block = ""
        if tand is not None:
            tand_block = f'''
            .TanD "{tand}"
            .TanDGiven "True"
            .TanDModel "ConstTanD"
            '''
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
            {tand_block}
            .Create
        End With
        """
        self.cst_file.model3d.add_to_history(f"Material: {name}", f1)

    def new_componet(self, name):
        """
        在 CST 工程中创建新的组件分组
        保留原函数名以兼容旧代码

        :param name: str, 新建组件名称
        """
        f1 = """
        '  new component: %s
        Component.New "%s" 
        """ % (name, name)
        self.cst_file.model3d.add_to_history("Freq_range ", f1)

    def create_component(self, name):
        """
        创建新组件（蛇形命名）
        等同于 new_componet()
        """
        self.new_componet(name)

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
        try:
            from cst_solver.config import CST_MATERIAL_LIB
            return CST_MATERIAL_LIB
        except ImportError:
            pass
        try:
            from cst_solver.config_template import CST_MATERIAL_LIB
            return CST_MATERIAL_LIB
        except ImportError:
            pass
        # 最终 fallback: 从默认安装路径推导
        _default = r"C:\SOFTWARE\CST Studio Suite 2026"
        return os.path.join(_default, 'Library', 'Materials')

    def list_library_materials(self):
        """
        列出 CST 材料库中所有可用材料名称

        :return: list[str], 材料名称列表（不含 .mtd 后缀）

        用法:
            >>> app = setup("project.cst")
            >>> materials = app.list_library_materials()
            >>> print(materials)
            ['Copper (annealed)', 'Silicon (lossy)', ...]
        """
        lib_path = self._get_material_library_path()
        if not os.path.exists(lib_path):
            print(f"⚠ 材料库路径不存在: {lib_path}")
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
                print(f"⚠ 未找到材料文件: {filepath}")
                return False

        if not os.path.exists(filepath):
            print(f"⚠ 材料文件不存在: {filepath}")
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
            print(f"⚠ 材料文件 {filepath} 中未找到有效定义")
            return False

        # 生成 VBA 命令并写入 CST 历史
        cmd = 'With Material\n.Reset\n'
        cmd += f'.Name "{material_name}"\n'
        cmd += '\n'.join(commands)
        cmd += '\nEnd With'

        self.cst_file.model3d.add_to_history(
            f'Define material: {material_name}', cmd)
        print(f"✅ 已加载材料: {material_name}")
        return True

    def get_material_filepath(self, material_name):
        """
        获取 CST 材料库中指定材料的完整文件路径

        :param material_name: str, 材料名称（如 'Copper (annealed)'）
        :return: str 或 None, 完整路径或 None（未找到时）
        """
        lib_path = self._get_material_library_path()
        filepath = os.path.join(lib_path, material_name + '.mtd')
        if os.path.exists(filepath):
            return filepath
        print(f"⚠ 材料库中未找到: {material_name}")
        return None
