# -*- coding: utf-8 -*-
"""
求解器配置构建器
================
配置 CST 求解器，调用 TPC 库已有方法，替代旧代码中 40 行手写 VBA。

@author: PC
"""


def configure_solver(app, freq_range=(300, 380), monitors=('E',),
                     calculation_type='TD-S', steady_state=-30,
                     parallel_threads=1024, gpus=1, component='component1'):
    """
    配置 CST 求解器。

    调用 TPC 库已有方法，不手写 VBA：
      - app.set_frequency_range(fmin, fmax)
      - app.configure_time_solver()
      - app.create_field_monitor(monitor_type, frequencies)

    :param app: cst_solver.setup 实例
    :param freq_range: tuple, (fmin, fmax) 频率范围（GHz），默认 (300, 380)
    :param monitors: tuple, 监视器类型列表，默认 ('E',)。可选 'E', 'H', 'Farfield', 'Powerflow'
    :param calculation_type: str, 求解器类型，默认 'TD-S'（时域求解器）
    :param steady_state: int, 稳态精度（dB），默认 -30
    :param parallel_threads: int, 并行线程数，默认 1024
    :param gpus: int, GPU 数量，默认 1
    :param component: str, 归属组件
    :return: None
    """
    fmin, fmax = freq_range

    # 1. 设置频率范围
    app.set_frequency_range(fmin, fmax)

    # 2. 配置时域求解器（基本配置：Method, Accuracy, CalculateAllModes, DetermineFreq）
    app.configure_time_solver()

    # 3. 高级参数配置（稳态精度、并行、GPU）
    #    通过 VBA 历史命令设置，与旧代码保持一致
    _configure_solver_advanced(app, steady_state, parallel_threads, gpus)

    # 4. 创建场监视器
    #    频率点取频率范围的中心和几个关键点
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

    通过 VBA 历史命令设置，与旧 notebook 中的手写 VBA 保持一致。
    """
    # 稳态精度
    vba = f"""With Solver
    .SteadyStateLimit "{steady_state}"
End With"""
    app.cst_file.model3d.add_to_history("Solver Steady State", vba)

    # 并行计算配置
    vba_parallel = f"""With Solver
    .ParallelizationThreads "{parallel_threads}"
    .GPUAcceleration "{gpus}"
End With"""
    app.cst_file.model3d.add_to_history("Solver Parallel", vba_parallel)


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
