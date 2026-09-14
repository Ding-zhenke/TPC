# -*- coding: utf-8 -*-
"""
VPC 区域构建器
==============
基于 TopoPath 自动生成 VPC-A 和 VPC-B 两个区域并裁剪。

@author: PC
"""


def build_vpc_regions(app, path, name_prefix='vpc', height='h',
                       material='Silicon (lossy)', y_margin='e2', component='component1'):
    """
    基于 TopoPath 自动生成 VPC-A 和 VPC-B 两个区域并裁剪。

    VPC-A = 路径上半区（含路径），VPC-B = 路径下半区（含路径）。
    两个区域通过 polyline + extrude 生成，然后用 insert 嵌入基板。

    :param app: cst_solver.setup 实例
    :param path: TopoPath 实例
    :param name_prefix: str, 名称前缀，默认 'vpc'
    :param height: str/float, 区域厚度，默认 'h'
    :param material: str, 材料名称，默认 'Silicon (lossy)'
    :param y_margin: str, 扩展量，默认 'e2'
    :param component: str, 归属组件
    :return: tuple, (vpca_name, vpcb_name)
    """
    # 确保路径点参数已定义（build_substrate 中已定义，这里重复调用无害）
    path.auto_define_cst_params(app, prefix='p')

    vpca_name = f"{name_prefix}_A"
    vpcb_name = f"{name_prefix}_B"

    # ---- VPC-A（上半区）----
    polygon_a = path.build_vpc_area_polygon(side='upper', y_margin=y_margin, prefix='p')
    curve_a = f"{vpca_name}_curve"
    app.polyline(polygon_a, name=curve_a, curve='curve1')
    app.extrude(f"curve1:{curve_a}", name=vpca_name, thickness=height,
                component=component, material=material)
    app.translate(vpca_name, ['0', '0', f'-{height}/2'],
                  component=component, log_flag=1)

    # ---- VPC-B（下半区）----
    polygon_b = path.build_vpc_area_polygon(side='lower', y_margin=y_margin, prefix='p')
    curve_b = f"{vpcb_name}_curve"
    app.polyline(polygon_b, name=curve_b, curve='curve1')
    app.extrude(f"curve1:{curve_b}", name=vpcb_name, thickness=height,
                component=component, material=material)
    app.translate(vpcb_name, ['0', '0', f'-{height}/2'],
                  component=component, log_flag=1)

    return vpca_name, vpcb_name


def intersect_vpc_with_substrate(app, substrate_name, vpca_name, vpcb_name,
                                  component='component1'):
    """
    将 VPC-A 和 VPC-B 区域与基板相交裁剪，得到最终的 VPC 区域。

    :param app: cst_solver.setup 实例
    :param substrate_name: str, 基板名称
    :param vpca_name: str, VPC-A 名称
    :param vpcb_name: str, VPC-B 名称
    :param component: str, 归属组件
    :return: tuple, (vpca_final_name, vpcb_final_name)（相交后名称不变）
    """
    # VPC-A 与基板相交
    app.intersect(substrate_name, vpca_name,
                  component1=component, component2=component)
    # VPC-B 与基板相交
    app.intersect(substrate_name, vpcb_name,
                  component1=component, component2=component)
    return vpca_name, vpcb_name
