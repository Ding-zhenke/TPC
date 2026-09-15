# -*- coding: utf-8 -*-
"""
求解器配置构建器
================
配置 CST 求解器，调用 TPC 库已有方法，替代旧代码中 40 行手写 VBA。

@author: PC
"""

# calculation_type → (cst_solver 方法名, 说明)
# 这些方法都定义在 cst_solver/simulation/solver.py 的 SolverMixin 上。
_SOLVER_DISPATCH = {
    'TD-S': ('configure_time_solver', '时域求解器'),
    'FD-S': ('configure_fd_solver', '频域求解器'),
    'EIGENMODE': ('configure_eigenmode_solver', '本征模求解器'),
    'IE-S': ('configure_ie_solver', '积分方程求解器'),
    'ASYMPTOTIC': ('configure_asymptotic_solver', '渐近求解器'),
}


def configure_solver(app, freq_range=(300, 380), monitors=('E',),
                     calculation_type='TD-S', steady_state=-30,
                     parallel_threads=1024, gpus=1, component='component1',
                     monitor_frequencies=None):
    """
    配置 CST 求解器。

    调用 TPC 库已有方法，不手写 VBA：
      - app.set_frequency_range(fmin, fmax)
      - app.configure_<calculation_type>_solver()
      - app.create_field_monitor(monitor_type, frequencies)

    :param app: cst_solver.setup 实例
    :param freq_range: tuple, (fmin, fmax) 频率范围（GHz），默认 (300, 380)
    :param monitors: tuple, 监视器类型列表，默认 ('E',)。可选 'E', 'H', 'Farfield', 'Powerflow'
    :param calculation_type: str, 求解器类型，默认 'TD-S'（时域）。
        可选 'TD-S' / 'FD-S' / 'EIGENMODE' / 'IE-S' / 'ASYMPTOTIC'
    :param steady_state: int, 稳态精度（dB），默认 -30
    :param parallel_threads: int, 并行线程数，默认 1024
    :param gpus: int, GPU 数量；**0 表示关闭 GPU 加速**（CST 不接受
        ``MaximumNumberOfGPUs 0``，故 0 会走 `HardwareAcceleration "False"`）
    :param component: str, 归属组件
    :param monitor_frequencies: list 可选, **显式的监视器频点列表**（GHz）。
        不传则按 freq_range 取 5 个等分点（起点/1-4/中心/3-4/终点）。
        与参考工程对比 S 参数时**必须显式给出**，否则两边的监视器频点不同、
        曲线不可比（参考 AB_feed 用的是 310/312/314/316/318/320 GHz）。
    :return: None
    :raises ValueError: calculation_type 不是受支持的求解器类型
    """
    key = str(calculation_type).upper()
    if key not in _SOLVER_DISPATCH:
        supported = ', '.join(sorted(_SOLVER_DISPATCH))
        raise ValueError(
            f"不支持的 calculation_type='{calculation_type}'，可选: {supported}")

    fmin, fmax = freq_range

    # 1. 设置频率范围
    app.set_frequency_range(fmin, fmax)

    # 2. 按 calculation_type 分派到 cst_solver 对应求解器配置方法
    method_name, _desc = _SOLVER_DISPATCH[key]
    getattr(app, method_name)()

    # 3. 高级参数配置（稳态精度、并行、GPU）
    #    通过 VBA 历史命令设置，与旧代码保持一致
    _configure_solver_advanced(app, steady_state, parallel_threads, gpus)

    # 4. 创建场监视器
    #    显式频点优先；未给出时按频率范围取 5 个等分点
    if monitor_frequencies is not None:
        freq_points = [float(f) for f in monitor_frequencies]
    else:
        freq_points = _get_monitor_frequencies(fmin, fmax, monitors)
    for mon_type in monitors:
        if mon_type.upper() == 'FARFIELD':
            # Farfield 监视器需要特殊处理
            _create_farfield_monitor(app, freq_points)
        else:
            # E/H/Powerflow 场监视器
            app.create_field_monitor(mon_type, freq_points)


def _configure_solver_advanced(app, steady_state, parallel_threads, gpus):
    """
    配置求解器高级参数（稳态精度、并行、GPU）。

    全部通过 ``cst_solver`` 的封装下发，不在本文件手写 VBA
    （见 WORKFLOW 第 2 节：builder 里手写 VBA 是明确的反例）。

    历史实现曾直接拼 ``.ParallelizationThreads`` / ``.GPUAcceleration``，
    这两个属性在真实 CST 2026 上并不存在
    （``no such property or method``），正确的属性是
    ``Solver.MaximumNumberOfThreads`` / ``Solver.HardwareAcceleration``。

    :param app: cst_solver.setup 实例
    :param steady_state: int, 稳态精度（dB）
    :param parallel_threads: int, 并行线程数
    :param gpus: int, GPU 数量
    """
    app.set_steady_state_limit(steady_state)
    app.set_parallel_threads(parallel_threads)
    app.set_gpu_acceleration(gpus, enable=bool(gpus))


def _get_monitor_frequencies(fmin, fmax, monitors):
    """
    获取监视器频率点列表。

    取频率范围的起点、终点、中心点，以及 1/4 和 3/4 点。
    """
    fmin = float(fmin)
    fmax = float(fmax)
    freqs = [
        fmin,
        fmin + (fmax - fmin) * 0.25,
        (fmin + fmax) / 2,
        fmin + (fmax - fmin) * 0.75,
        fmax,
    ]
    return freqs


def _create_farfield_monitor(app, frequencies):
    """
    创建 Farfield 远场监视器。

    Farfield 监视器与普通场监视器不同，需要单独配置。
    """
    for freq in frequencies:
        vba = f"""With Farfield
    .Reset
    .Frequency "{freq}"
    .Type "Broadband"
    .Create
End With"""
        app.cst_file.model3d.add_to_history(f"Farfield Monitor {freq}GHz", vba)
