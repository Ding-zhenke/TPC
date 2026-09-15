# -*- coding: utf-8 -*-
"""
PortBuilder — 端口构建器
========================
在指定 solid 的指定面自动添加波导端口。

复现旧代码 cell 14 的端口设置：
  pick_face('wg1', '10') + add_port(1)
  pick_face('wg1', '22') + add_port(2)

面编号（'10' / '22'）是 CST 内部编号，与实体几何和构建顺序强相关。
**经与参考工程 `AB_feed.cst` 逐条核对（2026-09-15）：参考工程用的正是
同样的 '10' / '22'，且端口定义块与本库逐字相同** —— 原因是 `wg1` 这个
brick 两边几何一致，面编号自然一致。所以保留编号做法是**与参考一致**的
选择，不是遗留缺陷。

但编号做法有一个真实风险：**几何或构建顺序一变，编号会静默指错面**
（CST 不保证把这种错误抛出来）。故 `add_waveguide_port()` 在建端口前用
`get_picked_count('face')` 校验「确实选中了 1 个面」，选不中时抛
`RuntimeError`，而不是让端口悄悄建错位置。

用法:
    >>> from topo_modeler.builders import add_waveguide_port
    >>> add_waveguide_port(app, solid_name='wg1', port_number=1, face_id='10')

@author: PC
"""

from typing import Optional


def add_waveguide_port(app, solid_name, port_number, face_id,
                       orientation='positive', shield=''):
    """
    在指定 solid 的指定面添加波导端口。

    复现旧代码：pick_face(solid_name, face_id) + add_port(port_number)

    :param app: cst_solver.setup 实例
    :param solid_name: str, 目标 solid 名称（如 'wg1'）
    :param port_number: int, 端口编号（1, 2, ...）
    :param face_id: str, CST 面编号（如 '10', '22'）
    :param orientation: str, 'positive' 或 'negative'，端口法向朝向
    :param shield: str, 端口屏蔽类型 'electric'/'magnetic'/''，默认 ''
    :return: int, 端口编号
    :raises RuntimeError: 该面编号没选中任何面（几何或构建顺序已变，编号失效）
    """
    app.pick_face(solid_name, face_id)

    # 校验：面编号失效时 CST 不一定报错，端口会静默建在错误位置。
    # get_picked_count() 已在真实 CST 会话实测可用（见 stages/04 §2.4）。
    # 返回 None 表示该查询接口不可用，此时跳过校验（不误报）。
    picked = app.get_picked_count('face')
    if picked is not None and picked != 1:
        raise RuntimeError(
            f"pick_face('{solid_name}', '{face_id}') 之后已选面数为 {picked}"
            f"（期望 1）—— 面编号已失效，端口会建在错误位置。"
            f"请核对该实体在当前几何下的面编号；"
            f"轴对齐的矩形端面可改用 create_waveguide_port_free() 直接给范围。")

    app.add_port(port_number, orientation=orientation, shield=shield)
    return port_number


def add_ports_for_straight_waveguide(app, waveguide_name='wg1',
                                      port1_face='10', port2_face='22'):
    """
    为直波导添加 2 个端口（入口 + 出口）。

    复现旧代码 cell 14：
      pick_face('wg1', '10') + add_port(1)
      pick_face('wg1', '22') + add_port(2)

    :param app: cst_solver.setup 实例
    :param waveguide_name: str, 波导 solid 名称
    :param port1_face: str, 端口 1 的面编号
    :param port2_face: str, 端口 2 的面编号
    :return: tuple, (port1_number, port2_number)
    """
    p1 = add_waveguide_port(app, waveguide_name, 1, port1_face)
    p2 = add_waveguide_port(app, waveguide_name, 2, port2_face)
    return (p1, p2)


def add_port_for_antenna(app, waveguide_name='wg1', port_face='10'):
    """
    为天线添加 1 个端口（仅入口）。

    :param app: cst_solver.setup 实例
    :param waveguide_name: str, 波导 solid 名称
    :param port_face: str, 端口面编号
    :return: int, 端口编号
    """
    return add_waveguide_port(app, waveguide_name, 1, port_face)
