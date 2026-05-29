# -*- coding: utf-8 -*-
"""
CST 求解器 Mixin 模块
=====================
封装 Solver(HF/LF)、FDSolver、EigenmodeSolver 等求解器配置

@author: PC
"""


class SolverMixin:
    """
    CST 求解器 Mixin
    提供时域/频域/本征模/积分方程等求解器的配置与执行
    """

    def T_solver(self):
        """
        时域求解器配置接口
        保留原函数名以兼容旧代码
        注意：当前为简易配置，完整参数请参考 CST VBA Solver 对象文档
        """
        f1 = """With Solver
     .Reset
     .Method "T-Solver"
     .Accuracy "-60"
End With"""
        self.cst_file.model3d.add_to_history("T-Solver Config", f1)

    def configure_time_solver(self):
        """
        时域求解器配置（蛇形命名）
        等同于 T_solver()
        """
        self.T_solver()

    def run(self):
        """执行当前 CST 工程的求解器计算，提交仿真任务"""
        self.cst_file.model3d.run_solver()

    def update(self):
        """刷新当前 CST 工程的模型历史，使参数修改生效"""
        self.cst_file.model3d.full_history_rebuild()

    def configure_fd_solver(self, accuracy='-60'):
        """
        配置频域求解器

        :param accuracy: str, 求解精度（dB），默认 '-60'
        """
        f1 = f"""With FDSolver
     .Reset
     .Accuracy "{accuracy}"
     .CalculateAllModes "True"
     .DetermineFreq "False"
End With"""
        self.cst_file.model3d.add_to_history("FDSolver Config", f1)

    def configure_eigenmode_solver(self, n_modes=3, frequency='1.0'):
        """
        配置本征模求解器

        :param n_modes: int, 求解模式数
        :param frequency: str/float, 搜索频率中心
        """
        f1 = f"""With EigenmodeSolver
     .Reset
     .NumberModes "{n_modes}"
     .Frequency "{frequency}"
End With"""
        self.cst_file.model3d.add_to_history("EigenmodeSolver Config", f1)

    def exclude_simulation(self, name, component='component1'):
        """
        将指定实体排除出仿真计算
        保留原函数名以兼容旧代码

        :param name: str, 需排除的实体名称
        :param component: str, 归属组件
        """
        f1 = f"""Group.AddItem "solid${component}:{name}", "Excluded from Simulation\""""
        self.cst_file.model3d.add_to_history(
            'Excluded from Simulation ' + name, f1)

    def exclude_from_simulation(self, name, component='component1'):
        """
        排除实体（蛇形命名）
        等同于 exclude_simulation()
        """
        self.exclude_simulation(name, component)

    # ================================================================
    # 补充求解器: IESolver, AsymptoticSolver, ParameterSweep, Optimizer
    # ================================================================

    def configure_ie_solver(self, accuracy='-30',
                            use_fast_frequency_sweep=True):
        """
        配置积分方程求解器 (IESolver)

        :param accuracy: str, 求解精度（dB），默认 '-30'
        :param use_fast_frequency_sweep: bool, 是否使用快速频率扫描
        """
        sweep = "True" if use_fast_frequency_sweep else "False"
        f1 = f"""With IESolver
     .Reset
     .Accuracy "{accuracy}"
     .UseFastFrequencySweep "{sweep}"
End With"""
        self.cst_file.model3d.add_to_history("IESolver Config", f1)

    def configure_asymptotic_solver(self, accuracy='-30'):
        """
        配置渐近求解器 (AsymptoticSolver)
        适用于电大尺寸问题的高频近似求解

        :param accuracy: str, 求解精度（dB），默认 '-30'
        """
        f1 = f"""With AsymptoticSolver
     .Reset
     .Accuracy "{accuracy}"
End With"""
        self.cst_file.model3d.add_to_history("AsymptoticSolver Config", f1)

    def configure_parameter_sweep(self, sequence='', start=True):
        """
        配置参数扫描

        :param sequence: str, 扫描序列定义
        :param start: bool, 是否立即启动扫描
        """
        start_cmd = '.Start' if start else ''
        f1 = f"""With ParameterSweep
     .Reset
     .SetSequence "{sequence}"
     {start_cmd}
End With"""
        self.cst_file.model3d.add_to_history("ParameterSweep", f1)

    def configure_optimizer(self, goal='', max_iterations='100'):
        """
        配置优化器

        :param goal: str, 优化目标定义
        :param max_iterations: str, 最大迭代次数，默认 '100'
        """
        f1 = f"""With Optimizer
     .Reset
     .Goal "{goal}"
     .MaxIterations "{max_iterations}"
     .Start
End With"""
        self.cst_file.model3d.add_to_history("Optimizer Config", f1)

    def configure_eigenmode_solver_ext(self, n_modes=3, frequency='1.0',
                                        method='AKS', mesh_type='Tetrahedral'):
        """
        配置本征模求解器（扩展版，支持更多参数）

        :param n_modes: int, 求解模式数
        :param frequency: str/float, 搜索频率中心
        :param method: str, 求解方法 'AKS'/'JDM'/'Subspace'
        :param mesh_type: str, 网格类型 'Tetrahedral'/'Hexahedral'
        """
        f1 = f"""With EigenmodeSolver
     .Reset
     .NumberModes "{n_modes}"
     .Frequency "{frequency}"
     .MethodType "{method}"
     .MeshType "{mesh_type}"
End With"""
        self.cst_file.model3d.add_to_history("EigenmodeSolver Config", f1)
