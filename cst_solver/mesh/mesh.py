# -*- coding: utf-8 -*-
"""
CST 网格设置 Mixin 模块
=======================
封装 Mesh、MeshAdaption3D 等网格参数设置

@author: PC
"""


class MeshMixin:
    """
    CST 网格设置 Mixin
    提供网格属性设置和网格自适应配置功能
    """

    def set_mesh_properties(self, max_cell=None, min_cell=None,
                            lines_per_wavelength=10, mesh_type='PBA'):
        """
        设置网格基本属性

        :param max_cell: float 可选, 最大网格尺寸
        :param min_cell: float 可选, 最小网格尺寸
        :param lines_per_wavelength: int, 每波长网格线数，默认 10
        :param mesh_type: str, 网格类型 'PBA'/'Tetrahedral'/...
        """
        f1 = f"""With Mesh
     .Reset
     .LinesPerWavelength "{lines_per_wavelength}"
     .MeshType "{mesh_type}"
"""
        if max_cell:
            f1 += f'     .MaxCell "{max_cell}"\n'
        if min_cell:
            f1 += f'     .MinCell "{min_cell}"\n'
        f1 += """End With"""
        self.cst_file.model3d.add_to_history("Mesh Properties", f1)

    def configure_mesh_adaption(self, max_passes=6, max_refinement=1e-6,
                                adaptive_tolerance=0.01):
        """
        配置网格自适应

        :param max_passes: int, 最大网格自适应次数，默认 6
        :param max_refinement: float, 最大细化步长
        :param adaptive_tolerance: float, 自适应容差
        """
        f1 = f"""With MeshAdaption3D
     .Reset
     .MaxPasses "{max_passes}"
     .MaxRefinement "{max_refinement}"
     .AdaptiveTolerance "{adaptive_tolerance}"
End With"""
        self.cst_file.model3d.add_to_history("Mesh Adaption Config", f1)

    # ================================================================
    # 补充: 增强网格设置
    # ================================================================

    def set_mesh_auto(self, lines_per_wavelength=10, lower_mesh_limit=10,
                       mesh_type='PBA', ratio_limit=10,
                       smallest_mesh_step='1e-6'):
        """
        配置自动网格参数（增强版）

        :param lines_per_wavelength: int, 每波长网格线数，默认 10
        :param lower_mesh_limit: int, 最低网格线数，默认 10
        :param mesh_type: str, 网格类型 'PBA'/'Tetrahedral'/'Hexahedral'
        :param ratio_limit: int, 网格比例限制，默认 10
        :param smallest_mesh_step: str, 最小网格步长，默认 '1e-6'
        """
        f1 = f"""With Mesh
     .Reset
     .LinesPerWavelength "{lines_per_wavelength}"
     .LowerMeshLimit "{lower_mesh_limit}"
     .MeshType "{mesh_type}"
     .RatioLimit "{ratio_limit}"
     .SmallestMeshStep "{smallest_mesh_step}"
     .Automesh "True"
End With"""
        self.cst_file.model3d.add_to_history("Mesh Auto Config", f1)

    # ================================================================
    # MeshSettings — 网格设置增强
    # ================================================================

    def set_mesh_settings(self, **kwargs):
        """
        设置网格高级参数（通过 MeshSettings 对象）
        支持的关键字参数:
            - Properties: dict, 网格属性键值对

        示例:
            >>> app.set_mesh_settings(StepsPerWavelength=12,
            ...                       MeshType="Tetrahedral")
        """
        settings_code = ""
        for key, value in kwargs.items():
            settings_code += f'     .{key} "{value}"\n'
        f1 = f"""With MeshSettings
     .Reset
{settings_code}End With"""
        self.cst_file.model3d.add_to_history("MeshSettings Config", f1)

    # ================================================================
    # MeshShapes — 网格形状控制
    # ================================================================

    def set_mesh_shape(self, shape='hexahedral'):
        """
        设置网格形状类型

        :param shape: str, 网格形状
            'hexahedral' - 六面体网格
            'tetrahedral' - 四面体网格
            'surface' - 表面网格
        """
        f1 = f"""With MeshShapes
     .Reset
     .ShapeType "{shape}"
End With"""
        self.cst_file.model3d.add_to_history(f"MeshShape: {shape}", f1)

    def set_mesh_region(self, name, priority=0, xmin=None, xmax=None,
                        ymin=None, ymax=None, zmin=None, zmax=None,
                        mesh_type=None, step=None):
        """
        设置网格加密区域

        :param name: str, 区域名称
        :param priority: int, 优先级，默认 0
        :param xmin/xmax/ymin/ymax/zmin/zmax: float 可选, 区域边界
        :param mesh_type: str 可选, 区域网格类型
        :param step: float 可选, 区域网格步长
        """
        f1 = f"""With MeshShapes
     .Reset
     .Name "{name}"
     .Priority "{priority}"
"""
        bounds = [
            ('Xmin', xmin), ('Xmax', xmax),
            ('Ymin', ymin), ('Ymax', ymax),
            ('Zmin', zmin), ('Zmax', zmax),
        ]
        for attr, val in bounds:
            if val is not None:
                f1 += f'     .{attr} "{val}"\n'
        if mesh_type:
            f1 += f'     .ShapeType "{mesh_type}"\n'
        if step:
            f1 += f'     .Step "{step}"\n'
        f1 += """     .Create
End With"""
        self.cst_file.model3d.add_to_history(f"MeshRegion: {name}", f1)
