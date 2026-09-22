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

端口**朝向**（2026-09-20 加固）：`orientation` 只接受 CST 的**位置枚举**
`'xmin'/'xmax'/'ymin'/'ymax'/'zmin'/'zmax'`，含义是「激励波传入器件的方向」。
库底层 `add_port()` 会拦截非法值；本封装把默认值从旧版的 `'positive'`
改成 `None`（= 不下发 `.Orientation` 行、由 CST 取默认值，**行为与旧版一致**
但会打一条 `UserWarning` 提醒你没说朝向）。

用法:
    >>> from topo_modeler.builders import add_waveguide_port
    >>> add_waveguide_port(app, solid_name='wg1', port_number=1, face_id='10',
    ...                    orientation='xmin')   # 端口在 x_min 端 ⇒ 激励朝 +x

@author: PC
"""

from typing import Optional


def add_waveguide_port(app, solid_name, port_number, face_id,
                       orientation=None, shield=''):
    """
    在指定 solid 的指定面添加波导端口。

    复现旧代码：pick_face(solid_name, face_id) + add_port(port_number)

    :param app: cst_solver.setup 实例
    :param solid_name: str, 目标 solid 名称（如 'wg1'）
    :param port_number: int, 端口编号（1, 2, ...）
    :param face_id: str, CST 面编号（如 '10', '22'）
    :param orientation: str 可选, **端口激励方向**，必须给位置枚举
        `'xmin'/'xmax'/'ymin'/'ymax'/'zmin'/'zmax'`（= 激励波传入器件的方向）：
        端口面在 x_min 端给 `'xmin'`、在 x_max 端给 `'xmax'`，否则 S21 会反。
        不传 = 不下发 `.Orientation` 行（CST 默认值）+ 一条 `UserWarning`；
        `'positive'/'negative'` 会抛 `ValueError`（旧默认值就是它，会被 CST 静默忽略）
    :param shield: str, 端口屏蔽类型 'electric'/'magnetic'/''，默认 ''
    :return: int, 端口编号
    :raises RuntimeError: 该面编号没选中任何面（几何或构建顺序已变，编号失效）
    :raises ValueError: orientation 不是合法位置枚举
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
                                      port1_face='10', port2_face='22',
                                      port1_orientation='xmin',
                                      port2_orientation='xmax'):
    """
    为直波导添加 2 个端口（入口 + 出口）。

    复现旧代码 cell 14：
      pick_face('wg1', '10') + add_port(1)
      pick_face('wg1', '22') + add_port(2)

    朝向默认值按 `build_waveguide` 造出的实体给（`'10'` 在 x_min 端、`'22'` 在 x_max 端，
    见 `anchorpoints.json` 里的 pin）——両端口都朝**器件内部**，这样 S21 不会被反向定义。
    若你换用别的面号，必须把对应朝向一起换掉（或显式传 `port1_orientation` /
    `port2_orientation`），否则 CST 会静默接受一个方向不对的端口。

    :param app: cst_solver.setup 实例
    :param waveguide_name: str, 波导 solid 名称
    :param port1_face: str, 端口 1 的面编号
    :param port2_face: str, 端口 2 的面编号
    :param port1_orientation: str, 端口 1 朝向（默认 `'xmin'`：面在 x_min 端）
    :param port2_orientation: str, 端口 2 朝向（默认 `'xmax'`：面在 x_max 端）
    :return: tuple, (port1_number, port2_number)
    """
    p1 = add_waveguide_port(app, waveguide_name, 1, port1_face,
                            orientation=port1_orientation)
    p2 = add_waveguide_port(app, waveguide_name, 2, port2_face,
                            orientation=port2_orientation)
    return (p1, p2)


def add_multiport_port_set(app, entries, component='component1'):
    """
    **多端口器件**的端口组（α1 族：双馈源 ⇒ 3 端口）—— 2026-09-17 取证落地。

    参考 notebook 的写法（`多端口\\Ant3_1W2N`、`MPMBA\\Ant3_*` 4 个 notebook 同构）：

    ```python
    app1.pick_face('wg2','10'); app1.add_port(1)      # BA 馈源的铜波导
    app1.pick_face('wg1','10'); app1.add_port(3)      # AB 馈源经 mirror 后的两条
    app1.pick_face('wg1','22'); app1.add_port(2)
    ```

    ⚠️ **端口编号在各 notebook 之间有对调**（A 是 `wg2→P1 / wg1:10→P3 / wg1:22→P2`，
    B/K 是 `wg2→P1 / wg1:10→P2 / wg1:22→P3`）—— 所以**编号必须由调用方给**，
    不能在本函数里猜（猜错会让激励端口与预期相反，而 CST 不会报错）。

    ⚠️ 面号 `'10'`（轴向口径端面）在多端口族里最稳；`'22'` 等跨模型不可复用，
    所以每个端口都用 :func:`add_waveguide_port` 的「选不中就抛」校验。

    ⚠️ **上面那段参考写法里的 `app1.add_port(1)` 不要再照抄**（缺朝向参数，
    2026-09-20 起会打 `UserWarning`；且当年那个默认值 `'positive'` 是**非法值**，
    CST 会静默忽略 ⇒ 端口朝向错）。落库时给 5 元组显式带上朝向，例如
    `('wg1', 2, '22', 'electric', 'xmax')`。

    :param app: cst_solver.setup 实例
    :param entries: 序列, 每项 ``(solid_name, port_number, face_id)``；
        也可给 4 元组 ``(solid_name, port_number, face_id, shield)``，
        或 5 元组 ``(solid_name, port_number, face_id, shield, orientation)``
        （多端口族各端口朝向往往不同 ⇒ **推荐逐条给 orientation**，
        不给会走 `add_waveguide_port` 的默认（None + 告警））
    :param component: str, 归属组件（仅记录用，端口挂在 solid 上）
    :return: list[dict], 每项 ``{'solid':…, 'port':…, 'face':…, 'shield':…, 'orientation':…}``
    :raises ValueError: entries 为空或形状不对
    """
    items = list(entries or ())
    if not items:
        raise ValueError('add_multiport_port_set 需要至少一个 (solid, port, face) 条目')

    created = []
    for entry in items:
        orientation = None
        if len(entry) == 5:
            solid, port, face, shield, orientation = entry
        elif len(entry) == 4:
            solid, port, face, shield = entry
        elif len(entry) == 3:
            (solid, port, face), shield = entry, 'electric'
        else:
            raise ValueError(
                f'端口条目必须是 (solid, port, face) 或 (solid, port, face, shield) 或 '
                f'(solid, port, face, shield, orientation)，收到 {entry!r}')
        add_waveguide_port(app, solid_name=solid, port_number=int(port),
                           face_id=str(face), shield=shield,
                           orientation=orientation)
        created.append({'solid': solid, 'port': int(port), 'face': str(face),
                        'shield': shield, 'orientation': orientation})
    return created


def add_port_for_antenna(app, waveguide_name='wg1', port_face='10',
                         orientation='xmin'):
    """
    为天线添加 1 个端口（仅入口）。

    :param app: cst_solver.setup 实例
    :param waveguide_name: str, 波导 solid 名称
    :param port_face: str, 端口面编号
    :param orientation: str, 端口激励方向（默认 `'xmin'`：`build_waveguide` 造出的
        `'10'` 面在 x_min 端）；若换用别的面号，必须同步换朝向
    :return: int, 端口编号
    """
    return add_waveguide_port(app, waveguide_name, 1, port_face,
                              orientation=orientation)
