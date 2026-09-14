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


def build_topological_crystal(app, path, topology='AB', lattice='a', height='h',
                               large_hole='l1', small_hole='l2', y_margin='e2',
                               component='component1', name_prefix='g',
                               xup=None, yup=None, ydn=None):
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
    :param xup: int/str/None, X 方向阵列次数；None 时用 path.get_array_range()
    :param yup: int/str/None, Y+ 方向阵列次数；None 时用 path.get_array_range()
    :param ydn: int/str/None, Y- 方向阵列次数；None 时用 path.get_array_range()
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

        g_name = f"{name_prefix}1{tick}"       # 大三角形合并后名称
        g2_name = f"{name_prefix}2{tick}"      # 第二个大三角形
        tri_up_name = f"tri_up_{tick}"          # 朝上小孔
        tri_dn_name = f"tri_dn_{tick}"          # 朝下小孔

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
                      repetitions=f'int({xup})',
                      component=component, copy=True, unite=True, log_flag=1)
        # 10. Y+ 方向阵列复制（步长 e2*2，次数 yup/2）
        app.translate(g_name, ['0', f'{y_margin}*2', '0'],
                      repetitions=f'int({yup}/2)',
                      component=component, copy=True, unite=True, log_flag=1)
        # 11. Y- 方向阵列复制（步长 -e2*2，次数 ydn/2）
        app.translate(g_name, ['0', f'-{y_margin}*2', '0'],
                      repetitions=f'int({ydn}/2)',
                      component=component, copy=True, unite=True, log_flag=1)

        crystal_names.append(g_name)

    return tuple(crystal_names)  # (crystal_a_name, crystal_b_name)


def intersect_crystal_with_vpc(app, crystal_a_name, crystal_b_name,
                                 vpca_name, vpcb_name, component='component1'):
    """
    将光子晶体阵列与 VPC 区域相交裁剪。

    :param app: cst_solver.setup 实例
    :param crystal_a_name: str, VPC-A 晶体阵列名称
    :param crystal_b_name: str, VPC-B 晶体阵列名称
    :param vpca_name: str, VPC-A 区域名称
    :param vpcb_name: str, VPC-B 区域名称
    :param component: str, 归属组件
    :return: tuple, (crystal_a_name, crystal_b_name)（相交后名称不变）
    """
    app.intersect(crystal_a_name, vpca_name,
                  component1=component, component2=component)
    app.intersect(crystal_b_name, vpcb_name,
                  component1=component, component2=component)
    return crystal_a_name, crystal_b_name
