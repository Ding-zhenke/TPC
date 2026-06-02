# -*- coding: utf-8 -*-
"""
CST 后处理 Mixin 模块
=====================
封装 PostProcess1D、CombineResults、QFactor 等后处理功能

@author: PC
"""


class PostProcMixin:
    """
    CST 后处理 Mixin
    提供 1D/2D/3D 后处理、结果组合、Q 因子计算等功能
    """

    def calculate_q_factor(self, s_param_path='S-Parameters\\S1,1',
                           method='3dB'):
        """
        计算 Q 因子

        :param s_param_path: str, S 参数导航树路径
        :param method: str, 计算方法 '3dB'/'10dB'/...
        """
        f1 = f"""With QFactor
     .Reset
     .SParameter "{s_param_path}"
     .Method "{method}"
     .Execute
End With"""
        self.cst_file.model3d.add_to_history("QFactor Calculation", f1)

    def combine_results(self, operation, result_paths, new_name):
        """
        组合多个结果

        :param operation: str, 操作类型 'Add'/'Subtract'/'Multiply'/'Divide'/'Average'
        :param result_paths: list[str], 要组合的结果路径列表
        :param new_name: str, 组合结果名称
        """
        op_line = ""
        for r in result_paths:
            op_line += f'            .Result "{r}"\n'
        f1 = f"""With CombineResults
     .Reset
     .Operation "{operation}"
     .Name "{new_name}"
{op_line}     .Execute
End With"""
        self.cst_file.model3d.add_to_history(f"CombineResults: {new_name}", f1)

    # ================================================================
    # 补充: SAR 计算, PostProcess1D
    # ================================================================

    def calculate_sar(self, mass_density='1000', averaging_method='1g'):
        """
        计算比吸收率 (SAR)

        :param mass_density: str, 质量密度 (kg/m^3)，默认 '1000'
        :param averaging_method: str, 平均方法 '1g'/'10g'/...
        """
        f1 = f"""With SAR
     .Reset
     .MassDensity "{mass_density}"
     .AveragingMethod "{averaging_method}"
     .Calculate
End With"""
        self.cst_file.model3d.add_to_history("SAR Calculation", f1)

    def post_process_1d(self, operation, result_path, new_name=''):
        """
        执行 1D 后处理操作

        :param operation: str, 操作类型
            'calc'/'smooth'/'integrate'/'differentiate'
        :param result_path: str, 结果路径
        :param new_name: str, 新结果名称
        """
        f1 = f"""With PostProcess1D
     .Reset
     .Operation "{operation}"
     .Result "{result_path}"
     .Name "{new_name}"
     .Execute
End With"""
        self.cst_file.model3d.add_to_history(f"PostProcess1D: {operation}", f1)

    # ================================================================
    # PostProcess1D 增强（参考 py4cst-ccly — 操作链模式）
    # ================================================================

    def post_process_apply_to(self, apply_target='S-parameter'):
        """
        设置 1D 后处理的应用目标

        :param apply_target: str, 应用目标
            'S-parameter' / 'Probes' / 'Monitors'
        """
        f1 = f"""With PostProcess1D
     .Reset
     .ApplyTo "{apply_target}"
End With"""
        self.cst_file.model3d.add_to_history(f"PostProcess ApplyTo: {apply_target}", f1)

    def post_process_add_operation(self, operation_type):
        """
        添加后处理操作

        :param operation_type: str, 操作类型
            'Time Window' / 'AR-Filter' / 'Phase Deembedding'
            'Renormalization' / 'VSWR' / 'YZ-matrices' / 'Exclude Port Modes'
        """
        f1 = f"""With PostProcess1D
     .Reset
     .AddOperation "{operation_type}"
End With"""
        self.cst_file.model3d.add_to_history(f"PostProcess Op: {operation_type}", f1)

    def post_process_run(self):
        """运行 1D 后处理"""
        f1 = "PostProcess1D.Run\n"
        self.cst_file.model3d.add_to_history("PostProcess Run", f1)
