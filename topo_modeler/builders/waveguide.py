# -*- coding: utf-8 -*-
"""
WaveguideBuilder — 空心矩形波导构建器
====================================
外方体 - 内方体 = 空心矩形波导（铜波导）。

复现旧代码 cell 13 的几何：
  square(外方体) + square(内方体) + substract(外, 内)

依赖的 CST 参数（需提前定义）：
  lf1, lf2, lf3, e2, wg_a, wg_b, wg_t

用法:
    >>> from topo_modeler.builders import build_waveguide
    >>> build_waveguide(app, name='wg1')

@author: PC
"""


def build_waveguide(app, name='wg1', material='Copper (annealed)',
                    x_min='-lf1-lf2-lf3', x_max='-lf1',
                    y_center='e2/2', wg_b='wg_b', wg_a='wg_a', wg_t='wg_t'):
    """
    构建空心矩形波导（外方体 - 内方体）。

    复现旧代码 AB_feed cell 13：
      外方体: x[-lf1-lf2-lf3, -lf1], y[e2/2-wg_b/2-wg_t, e2/2+wg_b/2+wg_t],
              z[-wg_a/2-wg_t, +wg_a/2+wg_t]
      内方体: x[-lf1-lf2-lf3, -lf1], y[e2/2-wg_b/2, e2/2+wg_b/2],
              z[-wg_a/2, +wg_a/2]
      substract(外方体, 内方体) = 空心波导

    :param app: cst_solver.setup 实例
    :param name: str, 波导实体名称
    :param material: str, 波导材料（默认铜）
    :param x_min: str, 波导 x 方向起点（CST 表达式）
    :param x_max: str, 波导 x 方向终点
    :param y_center: str, 波导 y 中心位置
    :param wg_b: str, 波导窄边尺寸（y 方向内宽）
    :param wg_a: str, 波导宽边尺寸（z 方向内高）
    :param wg_t: str, 波导壁厚
    :return: str, 波导实体名称
    """
    inner_name = f'{name}_1'

    # 1. 内方体（空心部分，后续被减去）
    app.square(
        x_min, x_max,
        f'{y_center}-{wg_b}/2', f'{y_center}+{wg_b}/2',
        f'-{wg_a}/2', f'+{wg_a}/2',
        inner_name, 'component1', material,
    )

    # 2. 外方体（含壁厚）
    app.square(
        x_min, x_max,
        f'{y_center}-{wg_b}/2-{wg_t}', f'{y_center}+{wg_b}/2+{wg_t}',
        f'-{wg_a}/2-{wg_t}', f'+{wg_a}/2+{wg_t}',
        name, 'component1', material,
    )

    # 3. 外方体 - 内方体 = 空心波导
    app.substract(name, inner_name, 'component1')

    return name
