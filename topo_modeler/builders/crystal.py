# -*- coding: utf-8 -*-
"""
光子晶体阵列构建器
==================
构建拓扑光子晶体三角孔阵列（最核心的重复代码，25 行 → 1 个函数）。

精确复现旧 notebook 中的超元胞生成逻辑：
  1. 2 个三角孔（朝上+朝下）组成基础单元
  2. 旋转 120° 复制 2 次 → 6 个孔的超元胞
  3. X/Y 方向阵列复制 → 整个 VPC 区域
  4. VPC-A 和 VPC-B 的大/小孔位置互换

.. important::
    **大孔/小孔的 AB·BA 分配方向（已对照参考工程核实）**

    旧的 AB/BA notebook 里 ``l1`` / ``l2`` 的数值随拓扑相互换，容易看反：

    ===========  =========  =========
    拓扑相        l1          l2
    ===========  =========  =========
    AB           ``0.35*a``  ``0.65*a``
    BA           ``0.65*a``  ``0.35*a``
    ===========  =========  =========

    参考工程 ``AB_feed/Model/3D/ModelHistory.json`` 的历史树逐条记录了每个孔的
    实际尺寸参数（用于核实本模块是否与参考几何一致）::

        Triangle: tri_up_A -> l1      Triangle: tri_dn_A -> l2
        Triangle: tri_up_B -> l2      Triangle: tri_dn_B -> l1

    即 **VPC-A 朝上孔使用 ``l1``、VPC-B 朝上孔使用 ``l2``**。

    本库把 ``l1`` / ``l2`` 固定为「大孔 / 小孔」语义（``large_hole='l1'``），
    因此 ``hole_sizes`` 的 AB·BA 分支必须与上表**相反**才能得到同样的几何 ——
    这是历史遗留的命名错位，不要在未对照参考工程的情况下「顺手改正」。

@author: PC
"""


def repeat_expression(value, divisor=1):
    """把阵列次数写成 CST 表达式，**区分「参数名」与「数值」**。

    参考工程 `Ant1_D_{AB,BA}_120_Feed_antenna-DF` 的历史里写的是
    ``"int(xup)"`` / ``"int(yup/2)"`` / ``"int(ydn/2)"`` —— 即**引用 CST 参数**，
    在 CST 里改 `xup/yup/ydn` 阵列就跟着变。本库 2026-09-17 前一律用 f-string
    把 Python 值烘成数字（``int(25)``），后果是：参数表里的 `xup/yup/ydn`
    **一个都不被历史引用**（真机实测 `ModelHistory.json` 里 `xup|yup|ydn` 出现 0 次），
    改参数不动几何 —— 与参考工程的行为不一致。

    于是这里按入参类型分流：

    * ``str``：当作 **CST 参数名**原样引用 ⇒ ``int(xup)``、``int(yup/2)``
    * 数字：烘成数值 ⇒ ``int(25)``、``int(14/2)``（**旧行为**，调用方没在参数表里
      声明该名字时用；字节级与改动前一致，避免影响既有产物）

    :param value: int/float/str，阵列次数或参数名
    :param divisor: int，写成分母（Y/X 方向的复制次数是 `yup/2`，故传 2）
    """
    if isinstance(value, str):
        body = value if divisor == 1 else f'{value}/{divisor}'
        return f'int({body})'
    return f'int({value}/{divisor})' if divisor != 1 else f'int({value})'


def build_topological_crystal(app, path, topology='AB', lattice='a', height='h',
                               large_hole='l1', small_hole='l2', y_margin='e2',
                               component='component1', name_prefix='g',
                               xup=None, yup=None, ydn=None, index=None):
    """
    构建拓扑光子晶体三角孔阵列。

    阵列复制范围默认从 ``path.get_array_range()`` 自动推导；但该推导只按路径长度
    计算，窄路径 + 宽基板时会覆盖不全，因此允许用 ``xup/yup/ydn`` 显式覆盖。

    ``topology='AB'``: VPC-A 朝上小孔 / 朝下大孔，VPC-B 朝上大孔 / 朝下小孔
    ``topology='BA'``: 互换

    :param app: cst_solver.setup 实例
    :param path: TopoPath 实例
    :param topology: str, 'AB' 或 'BA'，默认 'AB'
    :param lattice: str, 晶格常数参数名，默认 'a'
    :param height: str, 硅片厚度参数名，默认 'h'
    :param large_hole: str, 大孔边长参数名，默认 'l1'
    :param small_hole: str, 小孔边长参数名，默认 'l2'
    :param y_margin: str, Y方向阵列步长参数（步长 = y_margin*2），默认 'e2'
    :param component: str, 归属组件
    :param name_prefix: str, 名称前缀，默认 'g'
    :param xup: int/str/None, X 方向阵列次数；**str 视为 CST 参数名**（推荐，几何随参数变）；
        None 时用 path.get_array_range()
    :param yup: int/str/None, Y+ 方向阵列次数；**str 视为 CST 参数名**；None 时同上
    :param ydn: int/str/None, Y- 方向阵列次数；**str 视为 CST 参数名**；None 时同上
    :param index: int/None, **分支号**（多路径用）：`None`/`1` 用规范名
        （`g1A`/`g1B`/`tri_up_A`，与单路径逐名相同）；`k≥2` 时名字里插入分支号
        （`g{k}1A` / `g{k}2A` / `tri_up_A{k}`），避免分支之间实体重名
    :return: tuple, (crystal_a_name, crystal_b_name)
    """
    # 拓扑相决定大孔小孔的分配。
    #
    # 注意：这里 AB / BA 的分支顺序与「直觉」相反，是刻意的 ——
    # 参考 notebook 用 l1 表示 VPC-A 的朝上孔（AB 时 l1=0.35a 是小孔，
    # BA 时 l1=0.65a 是大孔），本库把 l1 固定为大孔，所以列表必须反过来填。
    # 详见模块 docstring 的对照表与 AB_feed 工程历史树核对结果。
    if topology == 'AB':
        # VPC-A 朝上孔 = 小孔, 朝下孔 = 大孔
        hole_sizes = [small_hole, large_hole]
    elif topology == 'BA':
        # VPC-A 朝上孔 = 大孔, 朝下孔 = 小孔
        hole_sizes = [large_hole, small_hole]
    else:
        raise ValueError(f"topology 必须是 'AB' 或 'BA'，收到 '{topology}'")

    # 阵列范围：显式参数优先，否则按路径自动推导
    auto_xup, auto_yup, auto_ydn = path.get_array_range()
    if xup is None:
        xup = auto_xup
    if yup is None:
        yup = auto_yup
    if ydn is None:
        ydn = auto_ydn

    # 超元胞中心位置（与旧代码完全一致）
    center_up = ['-a/2', 'sqr(3)/2*a-a/sqr(3)', '-h/2']   # 朝上三角形中心
    center_dn = ['0', 'a/sqr(3)', '-h/2']                    # 朝下三角形中心

    crystal_names = []

    for i, tick in enumerate(['A', 'B']):
        # VPC-A (i=0): 朝上孔=hole_sizes[0], 朝下孔=hole_sizes[1]
        # VPC-B (i=1): 朝上孔=hole_sizes[1], 朝下孔=hole_sizes[0]
        # 该索引结构与参考 notebook 的 `tri_up_X = l[i]` / `tri_dn_X = l[1-i]` 一一对应
        up_hole = hole_sizes[i]
        dn_hole = hole_sizes[1 - i]

        # 多路径时给名字带上**分支号**（`index`），否则两条分支的实体名会撞车
        # （`tri_up_A` 这种跨分支同名，CST 里会重名/复用）。规则：
        #   index=None 或 1（= 第 1 条分支）⇒ 用规范名，**与单路径逐名相同**；
        #   index=k≥2 ⇒ 名字里插入分支号（`g{k}1A` / `tri_up_A{k}`）。
        mid = '' if index in (None, 1) else str(index)

        g_name = f"{name_prefix}{mid}1{tick}"    # 大三角形合并后名称
        g2_name = f"{name_prefix}{mid}2{tick}"   # 第二个大三角形
        tri_up_name = f"tri_up_{tick}{mid}"      # 朝上小孔
        tri_dn_name = f"tri_dn_{tick}{mid}"      # 朝下小孔

        # 1. 大三角形朝上（边长 a）
        app.triangle(lattice, height, center=center_up, theta=[0, 0, 0],
                     name=g_name, curve='curve1')
        # 2. 大三角形朝下（边长 a，旋转180°）
        app.triangle(lattice, height, center=center_dn, theta=[0, 0, 180],
                     name=g2_name, curve='curve1')
        # 3. 小三角形朝上（边长 up_hole）
        app.triangle(up_hole, height, center=center_up, theta=[0, 0, 0],
                     name=tri_up_name, curve='curve1')
        # 4. 小三角形朝下（边长 dn_hole，旋转180°）
        app.triangle(dn_hole, height, center=center_dn, theta=[0, 0, 180],
                     name=tri_dn_name, curve='curve1')

        # 5. 合并两个大三角形
        app.add(g_name, g2_name, component1=component, component2=component)
        # 6. 合并两个小三角形
        app.add(tri_up_name, tri_dn_name, component1=component, component2=component)
        # 7. 从大三角形中减去小三角形（得到三角孔）
        app.subtract(g_name, tri_up_name, component1=component, component2=component)
        # 8. 旋转 120° 复制 2 次 → 6 个孔的超元胞
        app.rotation(g_name, angle=[0, 0, 120], repetition=2,
                     component=component, copy=True, unite=True, log_flag=1)
        # 9. X 方向阵列复制（步长 a，次数 xup）
        app.translate(g_name, [lattice, '0', '0'],
                      repetitions=repeat_expression(xup),
                      component=component, copy=True, unite=True, log_flag=1)
        # 10. Y+ 方向阵列复制（步长 e2*2，次数 yup/2）
        app.translate(g_name, ['0', f'{y_margin}*2', '0'],
                      repetitions=repeat_expression(yup, 2),
                      component=component, copy=True, unite=True, log_flag=1)
        # 11. Y- 方向阵列复制（步长 -e2*2，次数 ydn/2）
        app.translate(g_name, ['0', f'-{y_margin}*2', '0'],
                      repetitions=repeat_expression(ydn, 2),
                      component=component, copy=True, unite=True, log_flag=1)

        crystal_names.append(g_name)

    return tuple(crystal_names)  # (crystal_a_name, crystal_b_name)


def build_crystals_multi(app, paths, topology='AB', lattice='a', height='h',
                         large_hole='l1', small_hole='l2', y_margin='e2',
                         component='component1', name_prefix='g',
                         xup=None, yup=None, ydn=None):
    """
    多路径光子晶体：**每条路径各建一套 A/B 晶体阵列**，名字互不冲突。

    为什么需要它（阶段 8 模块 6.1，与 `build_vpc_regions_multi` 配套）：
    功分器 / MZI / 多端口器件的每条分支都要有自己的晶体阵列，最后分别与
    （并集后的）VPC 区域求交 —— 裁剪函数见 :func:`clip_crystals_with_vpc`。

    命名：第 ``i`` 条路径（`i` 从 0 起）用 **分支号** ``index=i+1`` ——
    **第 1 条路径与单路径版本逐名相同**（`g1A`/`g1B`），第 ``k≥2`` 条则在名字里
    带上分支号（`g{k}1A`/`g{k}1B`，内部 `tri_up_A{k}`），这样两条分支的实体
    不会重名（`tri_up_A` 这种名字跨分支会撞车）。

    :param app: cst_solver.setup 实例
    :param paths: dict, ``{名字: TopoPath}``（单条也可）
    :param topology: str, 'AB' / 'BA'
    :param lattice: str, 晶格常数参数名
    :param height: str, 厚度参数名
    :param large_hole: str, 大孔参数名
    :param small_hole: str, 小孔参数名
    :param y_margin: str, Y 方向阵列步长参数名
    :param component: str, 归属组件
    :param name_prefix: str, 名称前缀基名（各分支共用，分支号由 `index` 带入）
    :param xup/yup/ydn: int/str/None, 阵列次数或**参数名**；None ⇒ 按路径推断
    :return: dict, ``{路径名: (crystal_a_name, crystal_b_name)}``（保持传入顺序）
    :raises ValueError: paths 为空
    """
    if not paths:
        raise ValueError('paths 不能为空')

    crystals = {}
    for i, (path_name, path) in enumerate(paths.items()):
        crystals[path_name] = build_topological_crystal(
            app, path, topology=topology, lattice=lattice, height=height,
            large_hole=large_hole, small_hole=small_hole, y_margin=y_margin,
            component=component, name_prefix=name_prefix,
            xup=xup, yup=yup, ydn=ydn, index=i + 1)
    return crystals


def clip_crystals_with_vpc(app, vpca_name, vpcb_name, crystals,
                           component='component1'):
    """
    把**各条路径的晶体阵列**分别与（并集后的）VPC 区域求交。

    ⚠️ **操作数顺序与参考工程一致**（见 :func:`intersect_crystal_with_vpc`）：
    ``vpca intersect g1A`` —— 结果留在**第一个操作数**（VPC 区域），晶体名被消耗。
    因此这里对每个晶体各调一次，**VPC 区域名在整个过程中保持不变**，
    多条路径的晶体会被依次"吸收"进同一个 VPC 区域。

    :param app: cst_solver.setup 实例
    :param vpca_name: str, VPC-A 区域名（保留，承载所有交集结果）
    :param vpcb_name: str, VPC-B 区域名（保留）
    :param crystals: dict/可迭代, ``{路径名: (crystal_a, crystal_b)}``
        或可迭代的 ``(crystal_a, crystal_b)`` 对
    :param component: str, 归属组件
    :return: dict, ``{'vpc_a':…, 'vpc_b':…, 'pairs': n, 'consumed': [...]}``
        —— `consumed` 列出被消耗掉的晶体名，便于核对"确实裁到了每一条分支"
    :raises ValueError: crystals 为空
    """
    pairs = list(crystals.values()) if isinstance(crystals, dict) else list(crystals)
    if not pairs:
        raise ValueError('crystals 不能为空')

    consumed = []
    for crystal_a_name, crystal_b_name in pairs:
        app.intersect(vpca_name, crystal_a_name,
                      component1=component, component2=component)
        app.intersect(vpcb_name, crystal_b_name,
                      component1=component, component2=component)
        consumed.extend([crystal_a_name, crystal_b_name])
    return {'vpc_a': vpca_name, 'vpc_b': vpcb_name,
            'pairs': len(pairs), 'consumed': consumed}


def intersect_crystal_with_vpc(app, crystal_a_name, crystal_b_name,
                                 vpca_name, vpcb_name, component='component1'):
    """
    将光子晶体阵列与 VPC 区域相交裁剪（**单条路径**版）。

    ⚠️ **操作数顺序以参考工程 `AB_feed.cst` 为准（2026-09-15 修正）**

    参考工程执行的是 ``vpca intersect g1A`` / ``vpcb intersect g1B``；
    而 CST 的 ``Intersect`` **结果留在第一个操作数**、第二个被消耗，
    因此参考中**保留下来的是 VPC 区域名**，晶体阵列名被消耗。

    本函数原先写成 ``intersect(crystal_a, vpca)``，几何相同但**保留的是晶体名**，
    与参考不符，且会使后续 ``vpc_A add feed1`` 落到一个已被消耗的名字上。
    现改为与参考一致：结果留在 VPC 区域名上。

    多路径用 :func:`clip_crystals_with_vpc`（对每个晶体各调一次同一顺序）。

    :param app: cst_solver.setup 实例
    :param crystal_a_name: str, VPC-A 晶体阵列名称（会被消耗）
    :param crystal_b_name: str, VPC-B 晶体阵列名称（会被消耗）
    :param vpca_name: str, VPC-A 区域名称（保留，承载交集结果）
    :param vpcb_name: str, VPC-B 区域名称（保留，承载交集结果）
    :param component: str, 归属组件
    :return: tuple, (vpca_name, vpcb_name)（相交后由 VPC 区域承载结果）
    """
    app.intersect(vpca_name, crystal_a_name,
                  component1=component, component2=component)
    app.intersect(vpcb_name, crystal_b_name,
                  component1=component, component2=component)
    return vpca_name, vpcb_name
