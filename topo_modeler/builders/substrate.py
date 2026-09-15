# -*- coding: utf-8 -*-
"""
基板构建器
==========
基于 TopoPath 自动生成基板（路径上下各扩展的带状区域）。

单路径用 :func:`build_substrate`；
**多路径**（阶段 8 模块 6.1：功分器 / MZI / 多端口）用
:func:`build_substrate_multi` —— 各路径各做一条带，再布尔并成一个实体。

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


def build_substrate_multi(app, paths, name='substrate', height='h',
                          material='Silicon (lossy)', y_margin='e2',
                          component='component1', prefix='p', unite=True):
    """
    多路径基板：**各路径各做一条带，再布尔并成一个实体**（阶段 8 模块 6.1）。

    为什么要这么做：功分器 / MZI / 多端口器件的基板要覆盖**所有分支**。
    旧写法只按主干路径推范围，分支一长就露在基板之外
    （与阶段 4 T2/T5 同源的那类问题）。

    ⚠️ **每条路径必须用自己的 CST 参数前缀**：两条路径都用 `p1x/p1y…` 会互相覆盖。
    这里按顺序生成 ``{prefix}0`` / ``{prefix}1`` / …（例如 `p0`、`p1`）。

    ⚠️ **返回的名字是第一条带的实体名**（``{name}_part0``）—— CST 的 ``Add``
    结果留在**第一个操作数**里（见 `docs/ARCHITECTURE.md` §6 硬约定 2）。
    想统一改名，请调用方自己接一次 `app.rename(...)`（本函数不擅自改别人的名字）。

    :param app: cst_solver.setup 实例
    :param paths: dict, ``{名字: TopoPath}``；单条也可以（等价于 `build_substrate`，
        只是多了个前缀）
    :param name: str, 实体基名（最终实体是 ``{name}_part0``）
    :param height: str/float, 基板厚度
    :param material: str, 材料
    :param y_margin: str, 路径上下扩展量
    :param component: str, 归属组件
    :param prefix: str, CST 参数前缀的基名（每条路径会加序号）
    :param unite: bool, 是否把各条带并成一个实体（False 则保留多个实体，便于排错）
    :return: str, 结果实体名（``{name}_part0``）
    :raises ValueError: paths 为空
    """
    if not paths:
        raise ValueError('paths 不能为空')

    parts = []
    for i, (path_name, path) in enumerate(paths.items()):
        pfx = f'{prefix}{i}'
        path.auto_define_cst_params(app, prefix=pfx)
        pts = path.build_substrate_polygon(y_margin=y_margin, prefix=pfx)
        curve = f'{name}_{i}_curve'
        app.polyline(pts, name=curve, curve='curve1')
        solid = f'{name}_part{i}'
        app.extrude(f'curve1:{curve}', solid, thickness=height,
                    component=component, material=material)
        parts.append(solid)

    if unite and len(parts) > 1:
        # `Add` 结果留在第一个操作数里，且第二个会被删除
        for extra in parts[1:]:
            app.add(parts[0], extra)

    app.translate(parts[0], ['0', '0', f'-{height}/2'],
                  component=component, log_flag=1)
    return parts[0]
