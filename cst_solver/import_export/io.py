# -*- coding: utf-8 -*-
"""
CST 导入导出 Mixin 模块
=======================
封装 SAT、DXF、STEP、IGES、STL、GDSII 等导入导出功能

@author: PC
"""


class IOMixin:
    """
    CST 导入导出 Mixin
    提供各类 CAD 格式的导入和结果导出功能
    """

    def import_subproject(self, filename, subproject_name, scale_factor='0.001',
                          version='15.0', portname_map='',
                          import_to_active_coordinate_system='True',
                          curves='True', wires='True',
                          solid_wires_as_solids='False',
                          import_sources='False',
                          import_sensitivity_information='False'):
        """
        导入子 CST 工程到当前工程中

        对应 CST VBA 的 StartSubProject / EndSubProject 工作流。

        :param filename: str, 子项目导入文件名，例如 *.sab
        :param subproject_name: str, 子 CST 工程路径 (.cst)
        :param scale_factor: str, 子项目缩放因子，默认 '0.001'
        :param version: str, CST 导入版本号，默认 '15.0'
        :param portname_map: str, 端口映射表，默认空字符串
        :param import_to_active_coordinate_system: str, 是否导入到当前坐标系
        :param curves: str, 是否导入曲线
        :param wires: str, 是否导入线框
        :param solid_wires_as_solids: str, 是否将实体线框作为实体导入
        :param import_sources: str, 是否导入源
        :param import_sensitivity_information: str, 是否导入灵敏度信息
        """
        f1 = f"""StartSubProject 
        With SAT
     .Reset
     .FileName "{filename}"
     .SubProjectName3D "{subproject_name}"
     .SubProjectScaleFactor "{scale_factor}"
     .Version "{version}"
     .PortnameMap "{portname_map}"
     .ImportToActiveCoordinateSystem "{import_to_active_coordinate_system}"
     .Curves "{curves}"
     .Wires "{wires}"
     .SolidWiresAsSolids "{solid_wires_as_solids}"
     .ImportSources "{import_sources}"
     .Set "ImportSensitivityInformation", "{import_sensitivity_information}"
     .Read
End With
EndSubProject
"""
        self.cst_file.model3d.add_to_history("import external project: " + subproject_name, f1)

    def sat_import(self, filename, tpn='True'):
        """
        导入 SAT 格式文件
        保留原函数名以兼容旧代码

        :param filename: str, SAT 文件路径
        :param tpn: str, 是否将新材料设为 PEC，默认 'True'
        """
        f1 = f"""
            With SAT
            .Reset 
            .FileName "{filename}" 
            .Id "1" 
            .Version "9.0" 
            .ScaleToUnit "0" 
            .ImportToActiveCoordinateSystem "True" 
            .Curves "True" 
            .TypePECForNewMaterials "{tpn}" 
            .Read 
        End With
        """
        self.cst_file.model3d.add_to_history('Import Sat: ' + filename, f1)

    def import_sat(self, filename, tpn='True'):
        """
        导入 SAT 文件（蛇形命名）
        等同于 sat_import()
        """
        self.sat_import(filename, tpn)

    def dxf_import(self, filename, add='True', HealSelfIntersections='False',
                   component='component2', material='Silicon (lossy)',
                   height='0'):
        """
        导入 DXF 格式文件
        保留原函数名以兼容旧代码

        :param filename: str, DXF 文件路径
        :param add: str, 是否添加所有形状
        :param HealSelfIntersections: str, 是否修复自交
        :param component: str/list, 层名称或层名称列表
        :param material: str/list, 层材料或材料列表
        :param height: str/list, 层厚度或厚度列表
        """
        if isinstance(height, (list, tuple)):
            count = len(height)
            f2 = ''
            for i in range(count):
                comp = component[i] if isinstance(component, (list, tuple)) else component
                mat = material[i] if isinstance(material, (list, tuple)) else material
                f2 = f2 + f'.AddLayer "{comp}", "{mat}", "0", "{height[i]}", "0"\n  '
        else:
            f2 = f'  .AddLayer "{component}", "{material}", "0", "{height}", "0"\n  '

        f1 = f'''
        With DXF
            .Reset 
            .FileName "{filename}" 
            .AddAllShapes "{add}" 
            .PreserveHoles "True" 
            .CloseShapes "True" 
            .AsCurves "False" 
            .HealSelfIntersections "{HealSelfIntersections}" 
            .Id "1" 
            .SetSimplifyActive "False" 
            .SetSimplifyAngle "5.0" 
            .SetSimplifyRadiusTol "2.0" 
            .SetSimplifyEdgeLength "0.0" 
            .ScaleToUnit "False" 
            .ImportFileUnits "m" 
            .UseModelTolerance "False" 
            .ModelTolerance "0.0001" 
            .ConsiderPolylineStartAndEndWidth "True" 
            .Version "11.3" 
            .DiscardElevationsReadFromDXFFile "True" 
            {f2}
            .Read
        End With
        '''
        self.cst_file.model3d.add_to_history("Import DXF:" + filename, f1)

    def import_dxf(self, filename, add='True', HealSelfIntersections='False',
                   component='component2', material='Silicon (lossy)',
                   height='0'):
        """
        导入 DXF 文件（蛇形命名）
        等同于 dxf_import()
        """
        self.dxf_import(filename, add, HealSelfIntersections, component,
                        material, height)

    def import_step(self, filename, unit='mm'):
        """
        导入 STEP 格式文件

        :param filename: str, STEP 文件路径
        :param unit: str, 导入单位，默认 'mm'
        """
        f1 = f"""With STEP
     .Reset
     .FileName "{filename}"
     .ScaleToUnit "True"
     .FileUnit "{unit}"
     .Read
End With"""
        self.cst_file.model3d.add_to_history(f"Import STEP: {filename}", f1)

    def import_iges(self, filename, unit='mm'):
        """
        导入 IGES 格式文件

        :param filename: str, IGES 文件路径
        :param unit: str, 导入单位，默认 'mm'
        """
        f1 = f"""With IGES
     .Reset
     .FileName "{filename}"
     .ScaleToUnit "True"
     .FileUnit "{unit}"
     .Read
End With"""
        self.cst_file.model3d.add_to_history(f"Import IGES: {filename}", f1)

    def import_stl(self, filename, unit='mm'):
        """
        导入 STL 格式文件

        :param filename: str, STL 文件路径
        :param unit: str, 导入单位，默认 'mm'
        """
        f1 = f"""With STL
     .Reset
     .FileName "{filename}"
     .ScaleToUnit "True"
     .FileUnit "{unit}"
     .Read
End With"""
        self.cst_file.model3d.add_to_history(f"Import STL: {filename}", f1)

    # ============================================================
    # 结果导出
    # ============================================================

    def field_export(self, tree_item, save_path, mode='FixedWidth', step=-1):
        """
        导出 2D/3D 场数据到 ASCII 文件

        :param tree_item: str, 导航树中的场结果路径
        :param save_path: str, 保存路径
        :param mode: str, 'FixedWidth' 或 'FixedNumber'
        :param step: float/int, 步长或采样点数，默认 -1
        """
        ascii_export = self.cst_file.model3d.ASCIIExport
        self.cst_file.model3d.SelectTreeItem("2D/3D Results\\" + tree_item)

        ascii_export.Reset()
        ascii_export.FileName(save_path)
        if mode == 'FixedWidth':
            ascii_export.Mode(mode)
            ascii_export.Step(step)
        elif mode == 'FixedNumber':
            ascii_export.Mode(mode)
            ascii_export.Step(step)
        ascii_export.Execute()

    def export_field(self, tree_item, save_path, mode='FixedWidth', step=-1):
        """
        导出场数据（蛇形命名）
        等同于 field_export()
        """
        self.field_export(tree_item, save_path, mode, step)

    def pattern_export(self, tree_item, save_path,
                       plottype='3d',
                       plotmode='realized gain',
                       step=-1):
        """
        导出远场方向图数据

        :param tree_item: str, 导航树中远场结果路径
        :param save_path: str, 保存路径
        :param plottype: str, 'polar'/'cartesian'/'2d'/'2dortho'/'3d'
        :param plotmode: str, 'realized gain'/'directivity'/'efield'/'hfield'/'power density'
        :param step: float, 步长
        """
        ascii_export = self.cst_file.model3d.ASCIIExport
        self.cst_file.model3d.SelectTreeItem("Farfields\\" + tree_item)
        ascii_export.FileName(save_path)

        FarfieldPlot = self.cst_file.model3d.FarfieldPlot
        FarfieldPlot.Reset()
        FarfieldPlot.Plottype(plottype)
        FarfieldPlot.SetPlotMode(plotmode)
        FarfieldPlot.Plot()
        ascii_export.Execute()

    def export_pattern(self, tree_item, save_path,
                       plottype='3d', plotmode='realized gain', step=-1):
        """
        导出方向图（蛇形命名）
        等同于 pattern_export()
        """
        self.pattern_export(tree_item, save_path, plottype, plotmode, step)

    # ---------------------------------------------------------------
    # 兼容别名：历史拼写错误（patten_export → pattern_export）
    # 旧脚本使用 patten_export()，保留为等价别名，请勿在新代码中使用。
    # ---------------------------------------------------------------
    patten_export = pattern_export

    def export_data(self, tree_item, save_path):
        """
        导出导航树中指定项的数据到 ASCII 文件

        :param tree_item: str, 导航树项目路径
        :param save_path: str, 保存路径
        """
        ascii_export = self.cst_file.model3d.ASCIIExport
        self.cst_file.model3d.SelectTreeItem(tree_item)

        ascii_export.Reset()
        ascii_export.FileName(save_path)
        ascii_export.Execute()

    def export_to_ascii(self, tree_item, save_path):
        """
        导出到 ASCII（蛇形命名）
        等同于 export_data()
        """
        self.export_data(tree_item, save_path)
