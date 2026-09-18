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

    # 2. 生成带状区域。**弯折路径**上恒定宽度的整条带会自覆盖（单个多边形表达不了），
    #    所以按「每段一个四边形 + 布尔并」来建（P4/V1 真机实测：
    #    y 向偏移的整条带在 120° 天线路径上自交，CST 报
    #    `The specified curve is not closed and planar.`）。
    #    直线路径只有一段 ⇒ 四边形就是原来的整条带多边形，行为不变。
    quads = path.build_segment_band_polygons(y_margin=y_margin, prefix='p',
                                             side=None)
    solids = []
    for index, ring in enumerate(quads):
        curve_name = f"{name}_curve" if index == 0 else f"{name}_curve{index + 1}"
        solid_name = name if index == 0 else f"{name}_seg{index + 1}"
        app.polyline(ring, name=curve_name, curve='curve1')
        app.extrude(f"curve1:{curve_name}", name=solid_name, thickness=height,
                    component=component, material=material)
        app.translate(solid_name, ['0', '0', f'-{height}/2'],
                      component=component, log_flag=1)
        solids.append(solid_name)

    # 3. 多段时布尔并成一个实体（与 build_substrate_multi 的做法一致）
    extrude_name = solids[0]
    for extra in solids[1:]:
        app.add(extrude_name, extra, component1=component, component2=component)

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
        # ⚠️ 与 build_substrate 同一处理（P4/V6 真机修复，2026-09-17）：
        # **弯折路径**上恒定宽度的整条带会自覆盖，单个多边形会被 CST 拒绝
        # （`The specified curve is not closed and planar.`），所以按
        # 「每段一个四边形 + 拐角补块」建，最后统一布尔并。
        # 直线路径只有一段 ⇒ 与旧实现逐字节相同。
        rings = path.build_segment_band_polygons(y_margin=y_margin, prefix=pfx,
                                                 side=None)
        for index, ring in enumerate(rings):
            curve = (f'{name}_{i}_curve' if index == 0
                     else f'{name}_{i}_curve{index + 1}')
            solid = (f'{name}_part{i}' if index == 0
                     else f'{name}_part{i}_seg{index + 1}')
            app.polyline(ring, name=curve, curve='curve1')
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
