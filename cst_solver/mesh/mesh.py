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
