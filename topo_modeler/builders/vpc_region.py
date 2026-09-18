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

    VPC-A = 路径**下半区**，VPC-B = 路径**上半区**。
    两个区域通过 polyline + extrude 生成。

    ⚠️ **命名语义以参考工程 `AB_feed.cst` 为准（2026-09-15 修正）**

    本函数原先定义为「VPC-A = 上半区」，与参考工程**相反**。参考工程的历史树
    给出两条独立证据，都指向 **VPC-A = 下半区**：

    1. `vpc_a_area1` 的多边形是 ``(px1,py1) → (0,ymax_dn) → (px2,ymax_dn) → (px2,py2)``，
       即 ``y ∈ [ymax_dn, 0]``（下半平面）；
    2. 参考执行 ``vpca intersect vpc_a_area1``（`Intersect` 结果留第一个操作数），
       于是最终的 `vpca` 就是下半区；随后 ``vpca intersect g1A`` 把**晶体 A 配到下半区**。

    同时注意：参考的 ``vpcb Insert vpc_a_area1`` 中的 **`Insert` 是「差集」不是「并集」**
    —— CST 官方帮助原文为 *"Performs an subtraction between the solids solid1 and
    solid2 (solid1 - solid2) but does not delete solid2"*，故 `vpcb` 得到「上半区」。
    （先前从第三方整理的 VBA 参考里把它记成 `s1 ∪ s2`，是错的。）

    因此本库的 VPC-A 必须是**下半区**、VPC-B 是**上半区**，才能与参考的
    「A↔g1A、B↔g1B」配对一致；否则整个器件在 y 方向**镜像**（哪种拓扑相在上半区反了）。

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

    # ⚠️ 弯折路径上「恒定宽度的整条半带」会自覆盖，单个多边形表达不了（见
    #    TopoPath.build_segment_band_polygons 的说明）；因此按**每段一个四边形 + 布尔并**
    #    来建。直线路径只有一段 ⇒ 四边形与原来的多边形逐字节相同，行为不变。
    def _build_half(side, target_name):
        rings = path.build_segment_band_polygons(y_margin=y_margin, prefix='p',
                                                 side=side)
        solids = []
        for index, ring in enumerate(rings):
            curve = (f"{target_name}_curve" if index == 0
                     else f"{target_name}_curve{index + 1}")
            solid = target_name if index == 0 else f"{target_name}_seg{index + 1}"
            app.polyline(ring, name=curve, curve='curve1')
            app.extrude(f"curve1:{curve}", name=solid, thickness=height,
                        component=component, material=material)
            app.translate(solid, ['0', '0', f'-{height}/2'],
                          component=component, log_flag=1)
            solids.append(solid)
        for extra in solids[1:]:
            app.add(target_name, extra, component1=component,
                    component2=component)
        return target_name

    # ---- VPC-A（下半区，对齐参考工程）----
    _build_half('lower', vpca_name)

    # ---- VPC-B（上半区，对齐参考工程）----
    _build_half('upper', vpcb_name)

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


def build_vpc_regions_multi(app, paths, name_prefix='vpc', height='h',
                            material='Silicon (lossy)', y_margin='e2',
                            component='component1', prefix='p', unite=True):
    """
    多路径 VPC 区域：**每条路径各做上/下半区带，再按侧布尔并**。

    为什么需要它（与 `build_substrate_multi` 同源，阶段 8 模块 6.1）：
    功分器 / MZI / 多端口器件的 VPC 区域必须覆盖**所有分支**；只按主干路径
    生成的 VPC 区域盖不住分支，分支上的光子晶体就会被裁掉（或整块露在区域外）。

    与 `build_vpc_regions`（单路径）的关系
    --------------------------------------
    * **实体名**：第一条路径的第一段沿用规范名（`vpc_A` / `vpc_B`），
      单条路径 ⇒ 与单路径版本**实体名与调用顺序逐条相同**；
      多条路径 ⇒ 后续各段/各路径命名 ``{vpc_A}_p{i}_seg{j}``（`i` 从 1 起，
      因为第 0 条路径的第 0 段已经用了规范名），最后 `Add` 进规范名里
      （CST 的 `Add` 结果留在**第一个操作数**，见 `docs/ARCHITECTURE.md` §6 硬约定 2）。
    * **CST 参数前缀**：**多条路径**时必须各用各的，否则 `p1x/p1y…` 互相覆盖 ⇒
      按顺序生成 ``{prefix}0`` / ``{prefix}1`` / …（与 `build_substrate_multi` 一致）；
      **单条路径**时直接用 `prefix`（= `p`），于是与单路径版本**连参数名都相同**。

    :param app: cst_solver.setup 实例
    :param paths: dict, ``{名字: TopoPath}``（单条也可，等价于单路径版本）
    :param name_prefix: str, 名称前缀，默认 'vpc'
    :param height: str/float, 区域厚度
    :param material: str, 材料
    :param y_margin: str, 半宽参数名
    :param component: str, 归属组件
    :param prefix: str, CST 参数前缀基名（多路径时每条路径加序号）
    :param unite: bool, 是否把各条带并成一个实体（False 保留多个，便于排错）
    :return: tuple, (vpca_name, vpcb_name) —— 规范名，承载布尔并的结果
    :raises ValueError: paths 为空
    """
    if not paths:
        raise ValueError('paths 不能为空')

    vpca_name = f"{name_prefix}_A"
    vpcb_name = f"{name_prefix}_B"
    multi = len(paths) > 1

    parts = {'lower': [], 'upper': []}
    for i, (_path_name, path) in enumerate(paths.items()):
        pfx = f'{prefix}{i}' if multi else prefix
        path.auto_define_cst_params(app, prefix=pfx)
        for side, target in (('lower', vpca_name), ('upper', vpcb_name)):
            rings = path.build_segment_band_polygons(y_margin=y_margin,
                                                     prefix=pfx, side=side)
            for index, ring in enumerate(rings):
                first = (i == 0 and index == 0)
                # 第一条路径的第一段用规范名（单路径时与旧实现逐字节相同）
                solid = target if first else f'{target}_p{i}_seg{index + 1}'
                curve = (f'{target}_curve' if first
                         else f'{target}_p{i}_curve{index + 1}')
                app.polyline(ring, name=curve, curve='curve1')
                app.extrude(f'curve1:{curve}', name=solid, thickness=height,
                            component=component, material=material)
                app.translate(solid, ['0', '0', f'-{height}/2'],
                              component=component, log_flag=1)
                parts[side].append(solid)

    if unite:
        for side, target in (('lower', vpca_name), ('upper', vpcb_name)):
            for extra in parts[side][1:]:
                app.add(target, extra, component1=component,
                        component2=component)

    return vpca_name, vpcb_name
