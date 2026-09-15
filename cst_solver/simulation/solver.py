# -*- coding: utf-8 -*-
"""
CST 求解器 Mixin 模块
=====================
封装 Solver(HF/LF)、FDSolver、EigenmodeSolver 等求解器配置

@author: PC
"""

from cst_solver._guards import get_guard_state


class SolverMixin:
    """
    CST 求解器 Mixin
    提供时域/频域/本征模/积分方程等求解器的配置与执行
    """

    def T_solver(self):
        """
        时域求解器配置接口
        保留原函数名以兼容旧代码

        只设置求解方法。``Solver`` 对象的属性经真实 CST 2026 会话逐项实测
        （见下表），历史实现里的 ``.Accuracy`` / ``.CalculateAllModes`` /
        ``.DetermineFreq`` / ``.DetermineFreqFromN`` **都不是真实属性**，
        一律报 ``(10091) ActiveX Automation: no such property or method``。

        ``Solver`` 实测可用的属性（本项目常用的部分）：

        ==============================  ==================================
        属性                             用途
        ==============================  ==================================
        ``Method``                      ``"Hexahedral"`` / ``"Hexahedral TLM"``
        ``SteadyStateLimit``            稳态限制（dB），收敛判据
        ``UseParallelization``          并行开关
        ``MaximumNumberOfThreads``      并行线程数
        ``HardwareAcceleration``        GPU 加速开关
        ``MaximumNumberOfGPUs``         GPU 数量
        ``MeshAdaption``                网格自适应
        ``FrequencySamples``            频点数
        ``FrequencySampleRuleLin``      ``"Samples"`` / ``"Steps"`` / ``"Auto"``
        ``CalculateModesOnly``          仅计算模式
        ``SParaSymmetry``               S 参数对称
        ``FullDeembedding``             全去嵌
        ``StimulationPort``             ``"All"`` / 端口号
        ``PBAFillLimit``                PBA 填充限制
        ==============================  ==================================

        精度/稳态限制请用 :meth:`set_steady_state_limit`，
        并行与 GPU 请用 :meth:`set_parallel_threads` / :meth:`set_gpu_acceleration`。
        """
        f1 = """With Solver
     .Reset
     .Method "Hexahedral"
End With"""
        self.cst_file.model3d.add_to_history("T-Solver Config", f1)

    def set_steady_state_limit(self, db='-30'):
        """
        设置时域求解器的稳态限制（收敛判据，dB）。

        :param db: float/str, 稳态限制，如 -30 或 -60；越负越严格，默认 '-30'
        """
        f1 = f"""With Solver
     .SteadyStateLimit "{db}"
End With"""
        self.cst_file.model3d.add_to_history(f"Steady State Limit: {db}", f1)

    def set_parallel_threads(self, threads=8, enable=True):
        """
        设置并行计算线程数。

        :param threads: int/str, 最大线程数
        :param enable: bool, 是否启用并行，默认 True
        """
        f1 = f"""With Solver
     .UseParallelization "{enable}"
     .MaximumNumberOfThreads "{threads}"
End With"""
        self.cst_file.model3d.add_to_history(f"Parallel Threads: {threads}", f1)

    def set_mesh_adaption(self, enable=False):
        """
        开关网格自适应（``Solver.MeshAdaption``）。

        关闭自适应可显著缩短求解时间（省去多轮网格细化），
        适用于**对比验证**场景 —— 只要两个模型用同样的设置，比较仍然公平。

        :param enable: bool, 是否启用网格自适应，默认 False（关闭，求快）
        """
        f1 = f"""With Solver
     .MeshAdaption "{enable}"
End With"""
        self.cst_file.model3d.add_to_history(
            f"Mesh Adaption: {enable}", f1)

    def set_gpu_acceleration(self, gpus=1, enable=True):
        """
        设置 GPU 硬件加速。

        :param gpus: int/str, 最大 GPU 数。**必须 ≥ 1** —— CST 对
            ``MaximumNumberOfGPUs 0`` 会报
            ``Invalid number of hardware devices``，关闭 GPU 要用 ``enable=False``
        :param enable: bool, 是否启用 GPU 加速，默认 True
        """
        if enable:
            f1 = f"""With Solver
     .HardwareAcceleration "True"
     .MaximumNumberOfGPUs "{gpus}"
End With"""
        else:
            f1 = """With Solver
     .HardwareAcceleration "False"
End With"""
        self.cst_file.model3d.add_to_history(f"GPU Acceleration: {enable}", f1)

    def configure_time_solver(self):
        """
        时域求解器配置（蛇形命名）
        等同于 T_solver()
        """
        self.T_solver()

    def run(self):
        """
        执行当前 CST 工程的求解器计算，提交仿真任务

        ⚠️ 提交前会过一遍守卫层（``cst_solver._guards`` 的 T2）：
        参数改过但工程历史没重建时，仿真算的是**旧几何**，结果看着正常却是错的。
        ``mode='strict'`` 下直接抛 ``CstGuardError``；``mode='warn'`` 下只警告。
        修复方式：先 ``app.update()`` 或把 ``para(..., log_flag=1)``。
        """
        get_guard_state(self).check_before_run()
        self.cst_file.model3d.run_solver()

    def update(self):
        """
        刷新当前 CST 工程的模型历史，使参数修改生效

        这也是守卫层认可的「重建」动作 —— 调用后参数脏标记清除。
        """
        self.cst_file.model3d.full_history_rebuild()
        get_guard_state(self).mark_rebuilt()

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
        配置参数扫描（简单版）

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

    # ================================================================
    # ParameterSweep 增强版（参考 py4cst-ccly）
    # ================================================================

    def add_parameter_sweep_sequence(self, sequence_name='sweep1'):
        """
        添加参数扫描序列

        :param sequence_name: str, 序列名称
        """
        f1 = f"""With ParameterSweep
     .Reset
     .AddSequence "{sequence_name}"
End With"""
        self.cst_file.model3d.add_to_history(f"ParamSweep Seq: {sequence_name}", f1)

    def add_sweep_parameter_samples(self, seq_name, param_name,
                                     lower_bound, upper_bound, num_steps):
        """
        为参数扫描序列添加参数（线性采样）

        :param seq_name: str, 序列名称
        :param param_name: str, 参数名
        :param lower_bound: float, 下界
        :param upper_bound: float, 上界
        :param num_steps: int, 步数
        """
        f1 = f"""With ParameterSweep
     .Reset
     .AddParameter_Samples "{seq_name}", "{param_name}", "{lower_bound}", "{upper_bound}", "{num_steps}", "False"
End With"""
        self.cst_file.model3d.add_to_history(
            f"ParamSweep: {param_name} [{lower_bound}:{upper_bound}]/{num_steps}", f1)

    def start_parameter_sweep(self):
        """启动参数扫描"""
        f1 = """ParameterSweep.Start
"""
        self.cst_file.model3d.add_to_history("ParamSweep Start", f1)

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

    # ================================================================
    # Optimizer 增强版（参考 py4cst-ccly）
    # ================================================================

    def add_optimizer_goal(self, name, goal_type, operator, target, weight=1.0):
        """
        添加优化目标

        :param name: str, 目标名称
        :param goal_type: str, 目标类型
            '1D Primary Result' / '0D Result' / '1D Result' / '1DC Result'
        :param operator: str, 运算符 '<' / '>' / '=' / 'min' / 'max'
        :param target: float, 目标值
        :param weight: float, 权重，默认 1.0
        """
        f1 = f"""With Optimizer
     .Reset
     .Goal "{name}", "{goal_type}", "{operator}", "{target}", "{weight}"
End With"""
        self.cst_file.model3d.add_to_history(f"Optimizer Goal: {name}", f1)

    def add_optimizer_parameter(self, param_name, min_val, max_val):
        """
        添加优化参数

        :param param_name: str, 参数名
        :param min_val: float, 最小值
        :param max_val: float, 最大值
        """
        f1 = f"""With Optimizer
     .Reset
     .AddParameter "{param_name}", "{min_val}", "{max_val}"
End With"""
        self.cst_file.model3d.add_to_history(
            f"Optimizer Param: {param_name} [{min_val}, {max_val}]", f1)

    def start_optimizer(self):
        """启动优化器"""
        f1 = """Optimizer.Start
"""
        self.cst_file.model3d.add_to_history("Optimizer Start", f1)

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

    # ================================================================
    # IESolver 增强（参考 py4cst-ccly）
    # ================================================================

    def configure_ie_solver_ext(self, accuracy='-30',
                                 use_fast_frequency_sweep=True,
                                 mesh_type='Tetrahedral',
                                 max_frequency_samples=100):
        """
        配置积分方程求解器（增强版）

        :param accuracy: str, 精度 (dB)
        :param use_fast_frequency_sweep: bool, 快速频率扫描
        :param mesh_type: str, 网格类型
        :param max_frequency_samples: int, 最大频率采样数
        """
        sweep = 'True' if use_fast_frequency_sweep else 'False'
        f1 = f"""With IESolver
     .Reset
     .Accuracy "{accuracy}"
     .UseFastFrequencySweep "{sweep}"
     .MeshType "{mesh_type}"
     .MaxFreqSamples "{max_frequency_samples}"
End With"""
        self.cst_file.model3d.add_to_history("IESolver Config (ext)", f1)

    # ================================================================
    # SolverParameter — 求解器通用参数微调
    # ================================================================

    def set_solver_parameter(self, **kwargs):
        """
        设置求解器通用参数（通过 SolverParameter 对象）
        支持任意键值对参数:

        常用参数:
            - MaxNumberOfIterations: int
            - RelativeResidual: float
            - FrequencySamples: int
            - AccuracyHex: float (六面体精度)
            - AccuracyTet: float (四面体精度)

        示例:
            >>> app.set_solver_parameter(MaxNumberOfIterations=50,
            ...                          RelativeResidual=1e-6)
        """
        params = ""
        for key, value in kwargs.items():
            params += f'     .{key} "{value}"\n'
        f1 = f"""With SolverParameter
     .Reset
{params}End With"""
        self.cst_file.model3d.add_to_history("SolverParameter Config", f1)

    def set_max_iterations(self, max_iter):
        """
        设置求解器最大迭代次数

        :param max_iter: int, 最大迭代次数
        """
        self.set_solver_parameter(MaxNumberOfIterations=max_iter)

    def set_residual(self, residual):
        """
        设置求解器相对残差

        :param residual: float, 相对残差
        """
        self.set_solver_parameter(RelativeResidual=residual)
