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
# 多端口馈源族（lf4 / lf5 / lf6 / wf2）—— 2026-09-17 从参考 notebook 取证
# ============================================================
#
# 取证来源（只读解析 12 个多端口/功分 notebook 的 code cell）：
#   `多端口\Ant6_undiretional\ANT6_undirectional.ipynb` 里有**权威注释**：
#       wf2 = 0.2   # 探针颈部宽度
#       lf4 = 0.2   # 探针颈部长度
#       lf5 = 3.0   # 椭圆过渡段长度
#       lf6 = 0.2   # 铜波导端口段长度
#   同族的 `ANT6_C6_hexring.ipynb` 的 CST_PARAMS 表给出**派生量**：
#       ('wg_out', 'rin-lf4',          '铜波导径向外端 = 探针颈部起点')
#       ('wg_in',  'wg_out-lf5-lf6',   '铜波导径向内端 = 波端口所在半径')
#
# ⚠️ **为什么必须单独登记 `lf6`**：多端口族铜波导的 x 范围写法是
# `x_min='-lf5-lf6-lf4'` —— 它**引用 lf6**，而本库的 `UnitAntenna` /
# `StraightWaveguide` 都**没有**登记 `lf6`。参数未定义时 CST 会弹
# 「请输入变量值」**模态对话框**把脚本挂住（不是抛异常！见 P4/V6 教训），
# 所以这里显式登记，并在缺 `rin` 时提前失败。
MULTIPORT_FAMILY_PARAMS = {
    'wf2': '探针颈部宽度',
    'lf4': '探针颈部长度',
    'lf5': '椭圆过渡段长度',
    'lf6': '铜波导端口段长度（椭圆过渡段之外多出的部分）',
}

#: 多端口族铜波导的默认 x 范围（CST 表达式；与参考 notebook 逐字一致）
MULTIPORT_WG_X_MIN = '-lf5-lf6-lf4'
MULTIPORT_WG_X_MAX = '-lf4'


def register_multiport_params(app, *, wf2=0.2, lf4=0.2, lf5=3.0, lf6=0.2,
                              rin=None, rin_expression=None):
    """
    登记**多端口馈源族**的 CST 参数（`wf2/lf4/lf5/lf6`，可选派生的 `wg_out/wg_in`）。

    ``rin`` 不给（且没给 ``rin_expression``）时**只登记那四个族参数** ——
    直波导/天线这类**不需要径向半径**的器件就是这种用法（它们只用到
    `lf5+lf6+lf4` 这段波导长度，不需要 `wg_out/wg_in`）。

    给了 ``rin`` 时，另按参考 notebook 的 `CST_PARAMS` 表登记**表达式形式**的派生量：
    ``wg_out = rin - lf4``、``wg_in = wg_out - lf5 - lf6``。

    :param app: cst_solver.setup 实例
    :param wf2: 探针颈部宽度 [mm]，默认 0.2（参考取值 12/12 一致）
    :param lf4: 探针颈部长度 [mm]，默认 0.2
    :param lf5: 椭圆过渡段长度 [mm]，默认 3.0（参考里 3.0×9 / 0.2×2 / 0.45×1）
    :param lf6: 铜波导端口段长度 [mm]，默认 0.2
    :param rin: str 可选, **已存在的** CST 参数名（铜波导外端所在的半径基准）
    :param rin_expression: str 可选, 不给就要求 `rin` 已存在；给了就直接 `para(rin, 表达式)`
    :return: dict, ``{'params': [...], 'derived': {...}}``（没给 rin 时 derived 为空）
    :raises ValueError: 给了 `rin`、但它既没有表达式又查不到
    """
    for name, value in (('wf2', wf2), ('lf4', lf4), ('lf5', lf5), ('lf6', lf6)):
        app.para(name, value, expression=MULTIPORT_FAMILY_PARAMS[name])
    result = {'params': list(MULTIPORT_FAMILY_PARAMS), 'derived': {}}
    if rin is None and rin_expression is None:
        return result

    from cst_solver._guards import get_guard_state

    if rin_expression is not None:
        app.para(rin, rin_expression, expression='多端口族铜波导外端基准半径')
    else:
        guard = get_guard_state(app)
        # 与 build_grin_lens 同一套前置检查：真机 app 在第一次 para() 后接上探针；
        # 离线假 app 没有探针 ⇒ 不做拦截（否则单测必然误报）。
        if getattr(guard, '_param_probe', None) is not None \
                and guard.param_existed(rin) is False:
            raise ValueError(
                f"register_multiport_params 需要 CST 参数 {rin!r} 先存在"
                f"（派生量 wg_out = {rin}-lf4 依赖它）。\n"
                f"  请先 `app.para({rin!r}, ...)`，或用 rin_expression=... 让本函数登记。\n"
                f"  ⚠️ 缺参数时 CST 会弹「输入变量值」模态对话框把脚本挂住，"
                f"而不是抛异常 —— 所以这里提前拦下。")

    app.para('wg_out', f'{rin}-lf4',
             expression='铜波导径向外端 = 探针颈部起点')
    app.para('wg_in', 'wg_out-lf5-lf6',
             expression='铜波导径向内端 = 波端口所在半径')
    result['derived'] = {'wg_out': f'{rin}-lf4', 'wg_in': 'wg_out-lf5-lf6'}
    return result


def build_multiport_waveguide(app, name='wg2', material='Copper (annealed)',
                              x_min=None, x_max=None, y_center='0',
                              port_number=None, port_face='10',
                              orientation='positive', shield='electric',
                              wg_b='wg_b', wg_a='wg_a', wg_t='wg_t'):
    """
    多端口族的**铜波导**（+ 可选波端口），x 范围默认 ``[-lf5-lf6-lf4, -lf4]``。

    与 `build_waveguide` 的区别只有默认值：多端口族的波导长在**椭圆过渡段之外**
    （`lf5`+`lf6` 那段），不是直波导族的 `lf1`+`lf2`+`lf3` 那段。
    ⚠️ 因此**依赖 `lf4/lf5/lf6` 三个参数已登记**（先用
    :func:`register_multiport_params`，或用登记过它们的模板）。

    :param app: cst_solver.setup 实例
    :param name: str, 波导实体名
    :param material: str, 材料
    :param x_min: str 可选, 默认 `'-lf5-lf6-lf4'`
    :param x_max: str 可选, 默认 `'-lf4'`
    :param y_center: str, 波导 y 中心（多端口族在轴线上 ⇒ `'0'`）
    :param port_number: int 可选, 给了就在 `port_face` 上加波导端口
    :param port_face: str, 端面编号（默认 `'10'`：轴向口径端面，12/12 notebook 一致）
    :param orientation: str, 端口法向
    :param shield: str, 端口屏蔽（多端口族用 `'electric'`）
    :param wg_b/wg_a/wg_t: str, 波导内宽/内高/壁厚参数名
    :return: dict, ``{'name': ..., 'x_min': ..., 'x_max': ..., 'port': ...}``
    """
    from topo_modeler.builders.waveguide import build_waveguide
    from topo_modeler.builders.port import add_waveguide_port

    x_min = x_min or MULTIPORT_WG_X_MIN
    x_max = x_max or MULTIPORT_WG_X_MAX
    build_waveguide(app, name=name, material=material, x_min=x_min, x_max=x_max,
                    y_center=y_center, wg_b=wg_b, wg_a=wg_a, wg_t=wg_t)

    port = None
    if port_number is not None:
        port = add_waveguide_port(app, solid_name=name, port_number=port_number,
                                  face_id=port_face, orientation=orientation,
                                  shield=shield)
    return {'name': name, 'x_min': x_min, 'x_max': x_max, 'port': port}


# ============================================================
# AB 型椭圆探针（对应旧代码 feed1）
# ============================================================
def build_ab_elliptical_feed(app, name='feed1', material='Silicon (lossy)'):
    """
    AB 型三角渐变 + 椭圆过渡探针（上半部分不对称渐变）。

    复现旧代码 cell 12 的几何：
      polyline(9顶点) -> extrude(h) -> 椭圆圆柱 -> 矩形切割 -> subtract
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
    app.subtract(epc_name, cut_name, 'component1')

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
      polyline(10顶点) -> extrude(h) -> 椭圆圆柱 -> 矩形切割 -> subtract
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
    app.subtract(epc_name, cut_name, 'component1')

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
