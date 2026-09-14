# -*- coding: utf-8 -*-
"""
PortBuilder — 端口构建器
========================
在指定 solid 的指定面自动添加波导端口。

复现旧代码 cell 14 的端口设置：
  pick_face('wg1', '10') + add_port(1)
  pick_face('wg1', '22') + add_port(2)

注意：pick_face 的面编号（如 '10', '22'）是 CST 内部编号，
与实体几何相关。阶段 3 先硬编码（从旧 notebook 提取），
后续优化为按法向量自动查找。

用法:
    >>> from topo_modeler.builders import add_waveguide_port
    >>> add_waveguide_port(app, solid_name='wg1', port_number=1, face_id='10')

@author: PC
"""

from typing import Optional


def add_waveguide_port(app, solid_name, port_number, face_id,
                       full_deembedding=False, consider_material_inside=False):
    """
    在指定 solid 的指定面添加波导端口。

    复现旧代码：pick_face(solid_name, face_id) + add_port(port_number)

    :param app: cst_solver.setup 实例
    :param solid_name: str, 目标 solid 名称（如 'wg1'）
    :param port_number: int, 端口编号（1, 2, ...）
    :param face_id: str, CST 面编号（如 '10', '22'）
    :param full_deembedding: bool, 是否完全去嵌入
    :param consider_material_inside: bool, 是否考虑内部材料
    :return: int, 端口编号
    """
    app.pick_face(solid_name, face_id)
    app.add_port(port_number)
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
