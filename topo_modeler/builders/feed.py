# -*- coding: utf-8 -*-
"""
FeedBuilder — 馈源/探针构建器
============================
支持 3 种馈源类型，精确复现旧代码几何：
  1. 'ab_elliptical' : AB 型三角渐变 + 椭圆过渡（直波导用，对应旧 feed1）
  2. 'ba_tapered'    : BA 型对称渐变 + 椭圆过渡（天线用，对应旧 feed2）
  3. 'cylinder'      : 圆柱辐射体（单元天线用）

所有几何参数通过 CST 参数表达式传入，可在 CST 中参数化调整。

用法:
    >>> from topo_modeler.builders import build_feed
    >>> build_feed(app, feed_type='ab_elliptical', name='feed1')

@author: PC
"""

from typing import Optional


# ============================================================
# AB 型椭圆探针（对应旧代码 feed1）
# ============================================================
def build_ab_elliptical_feed(app, name='feed1', material='Silicon (lossy)'):
    """
    AB 型三角渐变 + 椭圆过渡探针（上半部分不对称渐变）。

    复现旧代码 cell 12 的几何：
      polyline(9顶点) -> extrude(h) -> 椭圆圆柱 -> 矩形切割 -> substract
      -> translate -> add -> translate(Z居中)

    依赖的 CST 参数（需提前定义）：
      x0, e1, e2, wf1, lf1, lf2, h

    :param app: cst_solver.setup 实例
    :param name: str, 馈源实体名称
    :param material: str, 材料
    :return: str, 馈源实体名称
    """
    epc_name = f'{name}_epc'
    cut_name = f'{name}_cut1'

    # 1. polyline 渐变主体（9 个顶点，含闭合）
    data = [
        ["x0*a", "0"],
        ["x0*a-e1", "e2"],
        ["0", "e2"],
        ["0", "e2/2+wf1/2"],
        ["-lf1", "e2/2+wf1/2"],
        ["-lf1", "e2/2-wf1/2"],
        ["0", "e2/2-wf1/2"],
        ["0", "0"],
        ["x0*a", "0"],
    ]
    app.polyline(data, name=name, curve='curve1')
    app.extrude('curve1', name, 'h', material=material)

    # 2. 椭圆过渡圆柱
    app.create_elliptical_cylinder(
        name=epc_name, x_radius='lf2', y_radius='wf1/2', height='h',
        axis='z', material=material,
    )

    # 3. 矩形切割（切掉椭圆右半，保留左半）
    app.square('0', 'lf2', '-wf1/2', 'wf1/2', '0', 'h',
                name=cut_name, material=material)
    app.substract(epc_name, cut_name, 'component1')

    # 4. 椭圆平移到波导接口位置
    app.translate(epc_name, ['-(lf1)', 'e2/2', '0'], copy=False, unite=False, log_flag=1)

    # 5. 合并渐变主体 + 椭圆过渡
    app.add(name, epc_name)

    # 6. Z 方向居中
    app.translate(name, ['0', '0', '-h/2'], copy=False, unite=False, log_flag=1)

    return name


# ============================================================
# BA 型对称渐变探针（对应旧代码 feed2）
# ============================================================
def build_ba_tapered_feed(app, name='feed2', material='Silicon (lossy)',
                           add_optimizer=True):
    """
    BA 型对称渐变 + 椭圆过渡探针（上下对称）。

    复现旧代码 Ant3_epc cell 14 的几何：
      polyline(10顶点) -> extrude(h) -> 椭圆圆柱 -> 矩形切割 -> substract
      -> translate -> add -> translate(Z居中) -> 可选优化块

    依赖的 CST 参数（需提前定义）：
      x01, e1, e2, wf2, lf4, lf5, h, tx1, ty1

    :param app: cst_solver.setup 实例
    :param name: str, 馈源实体名称
    :param material: str, 材料
    :param add_optimizer: bool, 是否添加优化块 feed2_opt1
    :return: str, 馈源实体名称
    """
    epc_name = f'{name}_epc'
    cut_name = f'{name}_cut1'
    opt_name = f'{name}_opt1'

    # 1. polyline 对称渐变主体（10 个顶点，含闭合）
    data = [
        ["a", "0"],
        ["e1+x01*a", "e2"],
        ["0", "e2"],
        ["0", "wf2/2"],
        ["-lf4", "wf2/2"],
        ["-lf4", "-wf2/2"],
        ["0", "-wf2/2"],
        ["0", "-e2"],
        ["e1+x01*a", "-e2"],
        ["a", "0"],
    ]
    app.polyline(data, name=name, curve='curve1')
    app.extrude('curve1', name, 'h', material=material)

    # 2. 椭圆过渡圆柱
    app.create_elliptical_cylinder(
        name=epc_name, x_radius='lf5', y_radius='wf2/2', height='h',
        axis='z', material=material,
    )

    # 3. 矩形切割（切掉椭圆右半）
    app.square('0', 'lf5', '-wf2/2', 'wf2/2', '0', 'h',
                name=cut_name, material=material)
    app.substract(epc_name, cut_name, 'component1')

    # 4. 椭圆平移到波导接口位置
    app.translate(epc_name, ['-(lf4)', '0', '0'], copy=False, unite=False, log_flag=1)

    # 5. 合并渐变主体 + 椭圆过渡
    app.add(name, epc_name)

    # 6. Z 方向居中
    app.translate(name, ['0', '0', '-h/2'], copy=False, unite=False, log_flag=1)

    # 7. 可选优化块（小矩形，位于馈源中心）
    if add_optimizer:
        app.para('tx1', 0.2)
        app.para('ty1', 0.6)
        app.square('-tx1/2', 'tx1/2', '-ty1/2', 'ty1/2',
                    '-h/2', 'h/2', name=opt_name, material=material)
        app.add(name, opt_name)

    return name


# ============================================================
# 圆柱辐射体（单元天线用）
# ============================================================
def build_cylinder_feed(app, name='cylinder_feed', radius='r_cyl',
                         height='h', material='Silicon (lossy)',
                         position=None):
    """
    圆柱辐射体（单元天线末端辐射器）。

    :param app: cst_solver.setup 实例
    :param name: str, 圆柱实体名称
    :param radius: str/float, 圆柱半径（CST 参数名或数值）
    :param height: str/float, 圆柱高度
    :param material: str, 材料
    :param position: list, 平移向量 [dx, dy, dz]，None 则不平移
    :return: str, 圆柱实体名称
    """
    app.create_elliptical_cylinder(
        name=name, x_radius=radius, y_radius=radius, height=height,
        axis='z', material=material,
    )
    if position is not None:
        app.translate(name, position, copy=False, unite=False, log_flag=1)
    return name


# ============================================================
# 统一入口
# ============================================================
def build_feed(app, feed_type='ab_elliptical', name=None, **kwargs):
    """
    馈源构建器统一入口。

    :param app: cst_solver.setup 实例
    :param feed_type: str, 馈源类型
        - 'ab_elliptical' : AB 型三角渐变 + 椭圆过渡（直波导）
        - 'ba_tapered'    : BA 型对称渐变 + 椭圆过渡（天线）
        - 'cylinder'      : 圆柱辐射体
    :param name: str, 馈源实体名称（None 则按类型默认命名）
    :param kwargs: 传递给具体构建函数的额外参数
    :return: str, 馈源实体名称
    """
    if feed_type == 'ab_elliptical':
        name = name or 'feed1'
        return build_ab_elliptical_feed(app, name=name, **kwargs)
    elif feed_type == 'ba_tapered':
        name = name or 'feed2'
        return build_ba_tapered_feed(app, name=name, **kwargs)
    elif feed_type == 'cylinder':
        name = name or 'cylinder_feed'
        return build_cylinder_feed(app, name=name, **kwargs)
    else:
        raise ValueError(f"未知馈源类型 '{feed_type}'，支持: ab_elliptical, ba_tapered, cylinder")
