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
                              orientation=None, shield='electric',
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
    :param orientation: str 可选, 端口激励方向，必须是 CST 位置枚举
        `'xmin'/'xmax'/'ymin'/'ymax'/'zmin'/'zmax'`（多端口族的铜波导外端在 x_min 侧 ⇒ 一般给 `'xmin'`）；
        不传 = 不下发 `.Orientation` 行（CST 默认值）+ 一条 `UserWarning`；
        `'positive'/'negative'` 会抛 `ValueError`（见 `cst_solver.simulation.ports.check_port_orientation`）
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
# BA 微锥条 + 椭圆孔阵列探针（P′ 系列）—— 2026-09-24 从下游工作区下沉
# ============================================================
#
# 来源与取证（只读引用，不改下游工作区）
# ------------------------------------
# 几何与参数口径来自下游真实器件工程 `拓扑光子晶体模型\硅基\探针问题`：
#   * 建模脚本 `_work\probe_build.py`：`_probe_outline()` + `build_custom_probe()`
#   * 优化报告 `分析报告\REPORT_Pp4.md`（CST 原生 Trust Region，48 次评估）
#   * 最优工程 `_work\opt\Pp4_L0.60\opt_Pp4_L0.60.cst`（见 `PROBE_PRESETS`）
#
# 它解决什么问题
# --------------
# 参考 BA 探针（`build_ba_tapered_feed`）靠 **lf5 = 3.0 mm 的长椭圆过渡**做匹配，
# 所以插入管腔的长度压不下去（管内截面长宽比 ~15:1、尖端趋于刀口）。本变体把过渡段
# 换成 **~0.6 mm 的微锥条 + 一排椭圆孔**：用孔阵列的等效电抗代替长渐变，把插入长度
# 缩短到 0.6 mm 量级，且**末端只变细、不加宽**（不挤压铜波导的装配间隙）。
#
# 与工作区逐字一致的硬口径（改之前先读工作区的 `探针缩短方案.md`）
# --------------------------------------------------------------
# 1. **不加宽**：要求 `pb_w_tip <= wf2`，匹配只能靠孔 / 槽（不许「加粗块」）；
# 2. 孔的**位置从探针末端量起**（`pb_x_h0` = 首孔孔心到末端的距离），
#    与结构图（工作区 `probe_dim.py`）的标注口径一致；
# 3. 孔心偏移写成**累加 CST 表达式**（`pb_x_h0+pb_p_e1+…`）、每个孔的长短轴
#    各自独立 ⇒ 几何完全由 CST 参数驱动，优化器扫的是参数而不是烘好的小数
#    （同「阵列次数必须是参数引用」的纪律）。
#
# ⚠️ 依赖 `register_multiport_params()` **先**登记 `wf2 / lf4 / lf5 / lf6`
#    （外形引用 `wf2`（颈部宽）与 `lf4`（颈部长度））；缺参数时 CST 会弹
#    「请输入变量值」**模态对话框把脚本挂住**，所以真机上由本模块提前拦截。

#: `pb_*` 参数 -> 中文含义（**与孔数无关**的那三个；逐孔的名字见
#: :func:`probe_param_names`）
PROBE_HOLE_ARRAY_PARAMS = {
    'pb_L_in': '插入管腔长度（管口 -> 探针末端）',
    'pb_w_tip': '探针末端宽度（只变细、不加宽）',
    'pb_x_h0': '首孔孔心距探针末端的距离',
}

#: `pb_*` 参数写进 CST 参数表时统一用的说明文本
PROBE_PARAM_NOTE = 'probe geometry param (to optimize)'


def probe_param_names(n_holes):
    """
    某个孔数下**逐孔**的 CST 参数名（顺序 = 从探针末端往管口）。

    :param n_holes: int, 椭圆孔个数（>= 1）
    :return: list[str], ``n_holes=4`` 时给出
        ``['pb_x_h0', 'pb_p_e1', 'pb_p_e2', 'pb_p_e3',
        'pb_d_ex1'...'pb_d_ex4', 'pb_d_ey1'...'pb_d_ey4']``
    :raises ValueError: `n_holes < 1`
    """
    n = int(n_holes)
    if n < 1:
        raise ValueError(f'n_holes 必须 >= 1，收到 {n_holes!r}')
    return (['pb_x_h0'] + [f'pb_p_e{i + 1}' for i in range(n - 1)]
            + [f'pb_d_ex{i + 1}' for i in range(n)]
            + [f'pb_d_ey{i + 1}' for i in range(n)])


def probe_param_note(name):
    """
    单个 `pb_*` 参数的中文说明（写进 CST 参数表的 description）。

    :param name: str, 参数名（`probe_param_names` 的成员，或那三个公共名）
    :return: str, 人类可读说明；认不出的名字退回 `PROBE_PARAM_NOTE`
    """
    if name in PROBE_HOLE_ARRAY_PARAMS:
        return PROBE_HOLE_ARRAY_PARAMS[name]
    if name.startswith('pb_p_e'):
        return f'第 {name[len("pb_p_e"):]} 个孔心距（与前一个孔的孔心距离）'
    if name.startswith('pb_d_ex'):
        return f'第 {name[len("pb_d_ex"):]} 个椭圆孔沿 x 的长轴'
    if name.startswith('pb_d_ey'):
        return f'第 {name[len("pb_d_ey"):]} 个椭圆孔沿 y 的短轴'
    return PROBE_PARAM_NOTE


#: 探针参数**预设**：`preset -> {...}`。**每一套 = 一次完整优化的最优解**，
#: 供下游「照着建同一个器件」时一键取用，不必再抄一遍数字。
PROBE_PRESETS = {
    # ------------------------------------------------------------------
    # P′4：BA 微锥条 + **4 个椭圆孔**（孔位 / 3 个孔距 / 4 组长短轴**全独立**，
    #      且**允许相邻椭圆重叠** ⇒ 近似「扇贝边开槽」）
    # ------------------------------------------------------------------
    'Pp4': {
        'n_holes': 4,
        'label': 'P′4（BA 微锥条 + 4 椭圆孔阵列）',
        'band_GHz': (300.0, 320.0),
        # ⚠ 数值一律取 **4 位小数**（0.1 µm 分辨率）—— 比工艺下限（8 µm）
        #   与网格分辨率（~30 µm，见工作区 `probe_opt_cfg.MIN_FEATURE`）都小几个
        #   量级，取整无损；好处是与工作区 `REPORT_Pp4.md` 的表格逐位对得上。
        #   工程里的原值（14~15 位）见 `project` 指向的 `Model/Parameters.json`。
        'values': {
            'pb_L_in': 0.5988,
            'pb_w_tip': 0.1610,
            'pb_x_h0': 0.0646,
            'pb_p_e1': 0.1192,
            'pb_p_e2': 0.1187,
            'pb_p_e3': 0.1394,
            'pb_d_ex1': 0.1105,
            'pb_d_ex2': 0.1295,
            'pb_d_ex3': 0.1270,
            'pb_d_ex4': 0.1108,
            'pb_d_ey1': 0.0486,
            'pb_d_ey2': 0.0539,
            'pb_d_ey3': 0.0539,
            'pb_d_ey4': 0.0458,
        },
        'metrics': {
            'RL_dB': 10.02,           # 回波损耗（带内最差 |S11| 的相反数）
            'IL_dB': 2.62,            # 插入损耗（带内最差 |S21|）
            'VSWR': 1.92,
            'bw_minus10dB_GHz': 20.00,   # = 整个工作带 300–320 GHz
            'baseline_A_RL_dB': 6.82,    # 对照：库自带 BA 长锥基线
            'baseline_A_IL_dB': 3.51,
        },
        'provenance': ('CST 原生 Optimizer / Trust Region Framework，48 次评估'
                       '（13:21:14 求解机时），**目标达成**（goal = 0：'
                       'S11 带内 < -10 dB 且 S21 带内 > -3 dB）'),
        'project': r'_work\opt\Pp4_L0.60\opt_Pp4_L0.60.cst',
        'report': r'分析报告\REPORT_Pp4.md',
    },
}


def register_probe_params(app, preset='Pp4', overrides=None):
    """
    把某个**探针预设**的 `pb_*` 参数登记进 CST 工程。

    ⚠️ 本函数**只登记 `pb_*`**；外形还用到的 `wf2 / lf4 / lf5 / lf6` 由
    :func:`register_multiport_params` 负责（下游的 12 步流水线里它在更早的位置）。

    :param app: cst_solver.setup 实例
    :param preset: str, `PROBE_PRESETS` 的键，默认 `'Pp4'`
    :param overrides: dict 可选, 覆盖预设里的个别参数（例如只改 `pb_L_in`）
    :return: dict, ``{'preset': ..., 'n_holes': ..., 'params': {名: 值}}``
    :raises ValueError: 预设不存在
    """
    spec = PROBE_PRESETS.get(preset)
    if spec is None:
        raise ValueError(f'未知探针预设 {preset!r}，可选: '
                         f'{sorted(PROBE_PRESETS)}')
    values = dict(spec['values'])
    values.update(overrides or {})
    for pname, value in values.items():
        app.para(pname, value, expression=probe_param_note(pname))
    return {'preset': preset, 'n_holes': spec['n_holes'], 'params': values}


def _require_existing_params(app, names, who):
    """
    真机上**提前拦下「缺参数」**（防挂死）。

    CST 遇到未定义参数会弹「请输入变量值」**模态对话框把脚本挂住**，而不是抛异常
    —— 所以不能等 CST 自己报错。离线假 app 没有 `_param_probe` ⇒ 不拦截
    （否则单测必然误报），与 :func:`register_multiport_params` 同一套前置检查。

    :param app: cst_solver.setup 实例
    :param names: 序列, 必须有值的 CST 参数名
    :param who: str, 调用者名字（写进错误消息）
    :raises ValueError: 缺参数（仅真机）
    """
    from cst_solver._guards import get_guard_state

    guard = get_guard_state(app)
    if getattr(guard, '_param_probe', None) is None:
        return
    missing = [n for n in names if guard.param_existed(n) is False]
    if missing:
        raise ValueError(
            f'{who} 需要这些 CST 参数先存在：{missing}。\n'
            f'  探针参数用 register_probe_params(app, preset=...) 登记；'
            f'wf2/lf4/lf5/lf6 用 register_multiport_params(app, ...) 登记。\n'
            f'  ⚠️ 缺参数时 CST 会弹「输入变量值」模态对话框把脚本挂住，'
            f'而不是抛异常 —— 所以这里提前拦下。')


def build_ba_hole_array_feed(app, name='feed2', material='Silicon (lossy)',
                             n_holes=4, register_preset=None):
    """
    BA 型**微锥条 + 椭圆孔阵列**探针（`feed_type='ba_hole_array'`）。

    几何 = `build_ba_tapered_feed` 的楔形+颈部外形，但把 **3.0 mm 长椭圆过渡**
    换成 **`pb_L_in` 长的微锥条**（半宽 `wf2/2` → `pb_w_tip/2`），再沿轴**逐孔**
    减去 `n_holes` 个椭圆孔（孔心 `= 末端 + pb_x_h0 + Σpb_p_e…`）。

    依赖的 CST 参数（需提前定义）：
      `a, h, e1, e2, x01, wf2, lf4`（外形）+
      `pb_L_in, pb_w_tip, pb_x_h0, pb_p_e1..n-1, pb_d_ex1..n, pb_d_ey1..n`（探针）

    :param app: cst_solver.setup 实例
    :param name: str, 馈源实体名称，默认 `'feed2'`（BA 直波导/天线族的口径）
    :param material: str, 材料（与硅探针一致）
    :param n_holes: int, 椭圆孔个数（**离散量**：改个数要重建模型，不放进优化器）
    :param register_preset: str 可选, 给 `PROBE_PRESETS` 的键（如 `'Pp4'`）时
        先调 :func:`register_probe_params` 把预设写进工程；不给则要求调用方
        已经登记好参数（纯函数风格，与其余 builder 一致）
    :return: str, 馈源实体名称
    :raises ValueError: `n_holes < 1`；或真机上缺必需参数
    """
    n = int(n_holes)
    if n < 1:
        raise ValueError(f'n_holes 必须 >= 1，收到 {n_holes!r}')

    if register_preset is not None:
        register_probe_params(app, preset=register_preset)

    _require_existing_params(
        app,
        ['a', 'h', 'e1', 'e2', 'x01', 'wf2', 'lf4',
         'pb_L_in', 'pb_w_tip'] + probe_param_names(n),
        'build_ba_hole_array_feed')

    tip = '-lf4-pb_L_in'                 # 探针末端 x（CST 表达式）

    # 1. 外形多边形（12 顶点，**CCW**，含闭合）—— 前 5 / 后 5 个顶点与
    #    `build_ba_tapered_feed` 逐字一致，只把中间「椭圆过渡」换成微锥条。
    data = [
        ['a', '0'],
        ['e1+x01*a', 'e2'],
        ['0', 'e2'],
        ['0', 'wf2/2'],
        ['-lf4', 'wf2/2'],
        [tip, 'pb_w_tip/2'],
        [tip, '-pb_w_tip/2'],
        ['-lf4', '-wf2/2'],
        ['0', '-wf2/2'],
        ['0', '-e2'],
        ['e1+x01*a', '-e2'],
        ['a', '0'],
    ]
    assert list(data[0]) == list(data[-1]), '多边形未闭合：最后一点必须回到首点'
    app.polyline(data, name=name, curve='curve1')
    app.extrude('curve1', name, 'h', material=material)

    # 2. 逐孔：椭圆通刻 → 平移到孔心 → 从探针里减掉
    for i in range(n):
        # 孔心偏移 = pb_x_h0 + pb_p_e1 + … + pb_p_e(i)（累加表达式，非烘好的数）
        off = 'pb_x_h0' + ''.join(f'+pb_p_e{k + 1}' for k in range(i))
        hname = f'pb_hole{i + 1}'
        app.create_elliptical_cylinder(
            name=hname, x_radius=f'pb_d_ex{i + 1}/2',
            y_radius=f'pb_d_ey{i + 1}/2', height='h', axis='z',
            material=material)
        app.translate(hname, [f'{tip}+{off}', '0', '0'],
                      copy=False, unite=False, log_flag=1)
        app.subtract(name, hname, 'component1')

    # 3. Z 方向居中（CCW + extrude h ⇒ 实体在 +z，平移到 −h/2）
    app.translate(name, ['0', '0', '-h/2'], copy=False, unite=False, log_flag=1)

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
        - 'ba_hole_array' : BA 型**微锥条 + 椭圆孔阵列**（短探针，见
          `build_ba_hole_array_feed` 与 `PROBE_PRESETS['Pp4']`）
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
    elif feed_type == 'ba_hole_array':
        name = name or 'feed2'
        return build_ba_hole_array_feed(app, name=name, **kwargs)
    elif feed_type == 'cylinder':
        name = name or 'cylinder_feed'
        return build_cylinder_feed(app, name=name, **kwargs)
    else:
        raise ValueError(f"未知馈源类型 '{feed_type}'，支持: ab_elliptical, "
                         f"ba_tapered, ba_hole_array, cylinder")
