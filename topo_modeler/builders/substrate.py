# -*- coding: utf-8 -*-
"""
基板构建器
==========
基于 TopoPath 自动生成基板（路径上下各扩展的带状区域）。

@author: PC
"""


def build_substrate(app, path, name='substrate', height='h',
                    material='Silicon (lossy)', y_margin='e2', component='component1'):
    """
    基于 TopoPath 自动生成基板。

    基板 = 路径上下各扩展 y_margin 的带状区域，通过 polyline + extrude + translate 生成。

    :param app: cst_solver.setup 实例
    :param path: TopoPath 实例，路径的唯一数据源
    :param name: str, 基板实体名称，默认 'substrate'
    :param height: str/float, 基板厚度（Z方向），默认 'h'（CST参数）
    :param material: str, 材料名称，默认 'Silicon (lossy)'
    :param y_margin: str, 路径上下扩展量，默认 'e2'（CST参数，基板半宽）
    :param component: str, 归属组件，默认 'component1'
    :return: str, 基板实体名称
    """
    # 1. 自动在 CST 中定义路径点参数 p1x,p1y,...
    path.auto_define_cst_params(app, prefix='p')

    # 2. 生成基板多边形顶点（路径上下各扩展 y_margin）
    polygon_pts = path.build_substrate_polygon(y_margin=y_margin, prefix='p')

    # 3. 绘制 polyline 曲线
    curve_name = f"{name}_curve"
    app.polyline(polygon_pts, name=curve_name, curve='curve1')

    # 4. 拉伸为三维实体（从 -h/2 到 +h/2，先拉伸 h 再平移 -h/2）
    extrude_name = name
    app.extrude(f"curve1:{curve_name}", name=extrude_name, thickness=height,
                component=component, material=material)

    # 5. Z方向居中平移（extrude 默认从 0 开始，平移 -h/2 使中心在 z=0）
    app.translate(extrude_name, ['0', '0', f'-{height}/2'],
                  component=component, log_flag=1)

    return extrude_name
