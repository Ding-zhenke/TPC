# -*- coding: utf-8 -*-
r"""
StraightWaveguide — 直波导端到端模板
====================================
第一个端到端模板，复现旧代码 AB_feed.ipynb / BA_feed.ipynb 的完整建模流程。

内部流程：
  1. 构建 TopoPath（直线路径）
  2. 定义 CST 参数（基础 + 路径 + 阵列 + feed + waveguide）
  3. build_substrate → build_vpc_regions → build_topological_crystal
  4. build_feed(ab_elliptical) → build_waveguide
  5. mirror(feed + waveguide 到右端)
  6. add_ports(2 个端口)
  7. integrate（合并 vpca + feed + vpcb）
  8. configure_solver

用户使用（约 10 行）：
    >>> from topo_templates import StraightWaveguide
    >>> wg = StraightWaveguide(topology='AB', length=18, output_path=r'D:\out\wg.cst')
    >>> wg.preview()
    >>> wg.build_all()
    >>> wg.save()

@author: PC
"""

import os
import numpy as np
from typing import Optional, Tuple

from mesh_grid.tri_grid import TopoPath
from topo_modeler import TopoModeler, NameManager
from topo_modeler.builders import (
    build_materials,
    build_vpc_regions,
    build_topological_crystal,
    intersect_crystal_with_vpc,
    build_feed,
    build_waveguide,
    add_ports_for_straight_waveguide,
    configure_solver,
)


class StraightWaveguide:
    """
    直波导端到端模板。

    :param topology: str, 'AB' 或 'BA'
    :param length: int, 波导长度（晶格数，不含起点偏移）
    :param width: int, 波导宽度（预留，当前由 VPC 区域决定）
    :param lattice_constant: float, 晶格常数 a (mm)
    :param height: float, 硅片厚度 h (mm)
    :param large_hole_ratio: float, 大孔比例（l1 = ratio * a）
    :param small_hole_ratio: float, 小孔比例（l2 = ratio * a）
    :param feed_type: str, 馈源类型（默认 'ab_elliptical'）
    :param freq_range: tuple, 频率范围 (fmin, fmax) GHz
    :param monitors: tuple, 监视器类型 ('E',) 或 ('E', 'Farfield')
    :param template_cst: str, CST 模板文件路径
    :param output_path: str, 输出 .cst 文件路径
    """

    def __init__(self, topology='AB', length=18, width=14,
                 lattice_constant=0.2425, height=0.25,
                 large_hole_ratio=0.65, small_hole_ratio=0.35,
                 feed_type='ab_elliptical',
                 x0=4, wf1=0.2, lf1=0.2, lf2=3.0, lf3=0.2,
                 wg_a=0.7312, wg_b=0.3756, wg_t=0.2,
                 freq_range=(300, 380), monitors=('E',),
                 template_cst='tmp.cst', output_path=None,
                 feed_params=None):
        """
        :param x0: float, 探针起点（晶格数），参考模型 AB_feed.ipynb 为 4
        :param wf1: float, 探针宽度（mm），参考为 0.2
        :param lf1: float, 探针长度 1（mm），参考为 0.2
        :param lf2: float, 椭圆过渡半轴（mm），参考为 3.0
        :param lf3: float, 探针长度 3（mm），参考为 0.2
        :param wg_a: float, 空心波导内腔 z 向高度（mm），参考为 0.7312
        :param wg_b: float, 空心波导内腔 y 向宽度（mm），参考为 0.3756
        :param wg_t: float, 波导壁厚（mm），参考为 0.2
        :param feed_params: dict 可选, **BA 族馈源参数的覆盖入口**
            （`feed_type='ba_tapered'` 时用）：`wf2 / lf4 / lf5 / lf6 / x01`。
            AB 族那五个 `x0 / wf1 / lf1 / lf2 / lf3` 本身就是构造参数，不需要走这里。

        注：feed / waveguide 的默认值取自参考模型 ``AB_feed.ipynb`` 的 CST 参数，
        以保证默认参数下几何与参考工程一致（差异 < 0.1%）。
        """
        if topology not in ('AB', 'BA'):
            raise ValueError(f"topology 必须是 'AB' 或 'BA'，收到 '{topology}'")

        self.topology = topology
        self.length = length
        self.width = width
        self.a = lattice_constant
        self.h = height
        self.l1 = large_hole_ratio * self.a
        self.l2 = small_hole_ratio * self.a
        self.feed_type = feed_type
        self.freq_range = freq_range
        self.monitors = monitors
        self.template_cst = template_cst
        self.output_path = output_path

        # feed / waveguide 参数（默认值见 __init__ docstring）
        self.x0 = x0
        self.wf1 = wf1
        self.lf1 = lf1
        self.lf2 = lf2
        self.lf3 = lf3
        self.wg_a = wg_a
        self.wg_b = wg_b
        self.wg_t = wg_t
        #: BA 族馈源参数覆盖（见 ctor docstring；AB 族直接走上面的构造参数）
        self.feed_params = self._check_feed_params(feed_params)

        # 三角晶格几何参数
        self.e1 = self.a / 2
        self.e2 = self.a * np.sqrt(3) / 2

        # 构建路径：起点 (0,0)，沿 +c 走 length 步
        #
        # 与参考工程对齐（阶段 4 T2）：参考的 px1=0、px2=x1*a=18a=4.365，
        # 即 x ∈ [0, 18a] 共 **18 格**（x1=18=length）。
        # 原写法 start(0,-1) + move(length+1,'c') 的终点虽也对（c=18），
        # 但起点落到 c=-1（x=-a），整条路径是 **19 格** ——
        # 基板/VPC/晶体在 x 方向比参考长一个晶格周期。
        self.path = (TopoPath.builder(self.a, name='p')
                     .start(0, 0)
                     .move(length, 'c')
                     .build())

        # 阵列范围：必须覆盖**整个基板**（ARCHITECTURE 第 6 节硬约定 3）
        #
        # 不能只按路径推断：直线路径下 path.get_array_range() 只给出
        # xup=19 / yup=1 / ydn=1，而晶体阵列的 Y 向复制次数是 int(yup/2)，
        # 取整后为 0，CST 会直接报 "Invalid number of repetitions"。
        #
        # 参考工程 AB_feed.cst 的取值为 xup=25 / yup=14 / ydn=14，
        # 即 xup = length + int(width/2)、yup = ydn = width（width 对应旧代码 y1）。
        self.xup = self.length + int(self.width / 2)
        self.yup = self.width
        self.ydn = self.width

        # TopoModeler（智能推断 + 流水线）
        self.modeler = TopoModeler(template_cst=template_cst)
        self.modeler.set_path(self.path)
        self.modeler.set_parameters({
            'a': self.a, 'h': self.h,
            'l1': self.l1, 'l2': self.l2,
            'e1': self.e1, 'e2': self.e2,
        })
        self.app = self.modeler.app
        self.nm = NameManager()

        # 构建状态
        self._built = False

    # ---- CST 参数定义 ----

    #: `feed_params` 允许覆盖的参数名（只用于 BA 族；AB 族本身是构造参数）
    _FEED_PARAM_NAMES = {
        'ba_tapered': ('x01', 'wf2', 'lf4', 'lf5', 'lf6'),
        'ab_elliptical': (),
    }

    def _check_feed_params(self, feed_params):
        """校验 `feed_params` 的键名 —— **写错的键必须报错**（不静默忽略）。"""
        params = dict(feed_params or {})
        if not params:
            return params
        allowed = set(self._FEED_PARAM_NAMES.get(self.feed_type, ()))
        unknown = sorted(set(params) - allowed)
        if unknown:
            raise ValueError(
                f'feed_params 里有未知参数名 {unknown}；'
                f'feed_type={self.feed_type!r} 时可覆盖：{sorted(allowed)}'
                f'（AB 族的 x0/wf1/lf1/lf2/lf3 请直接用同名构造参数）')
        return params

    def _define_all_params(self):
        """定义所有 CST 参数（基础 + 路径 + 阵列 + feed + waveguide）。"""
        app = self.app

        # 基础参数
        app.para('a', self.a)
        app.para('h', self.h)
        app.para('l1', self.l1)
        app.para('l2', self.l2)
        app.para('e1', self.e1)
        app.para('e2', self.e2)

        # 路径参数（p1x, p1y, p2x, p2y, ...）
        self.path.auto_define_cst_params(app, prefix='p')

        # 阵列范围
        app.para('xup', self.xup)
        app.para('yup', self.yup)
        app.para('ydn', self.ydn)

        # feed 参数：**按 `feed_type` 登记对应的馈源族**
        #
        #   AB 型椭圆探针（feed1）：x0 / wf1 / lf1 / lf2 / lf3
        #   BA 型渐变探针（feed2）：x01 / wf2 / lf4 / lf5，**并且必须登记 lf6**
        #     —— 因为 BA 族的铜波导范围是 `[-lf5-lf6-lf4, -lf4]`，引用 lf6。
        #
        # ⚠️ 2026-09-17（P5/P0 迁移取证时发现）：此前本模板**只登记 AB 族**，
        #    于是 `StraightWaveguide(feed_type='ba_tapered')` 会让 BA 探针的多边形
        #    引用未定义的 wf2/lf4/lf5 —— CST 遇到未定义参数会弹「请输入变量值」
        #    **模态对话框把脚本挂住**（不是抛异常，见 P4/V6 的 Rbig/Ls 教训）。
        #    参考工程佐证：`直波导\BA\优化后的\BA_feed_epc.ipynb` 建的正是 `feed2`
        #    + `square('-lf5-lf6-lf4','-lf4',...)` 的 BA 族。
        if self.feed_type == 'ba_tapered':
            from topo_modeler.builders import register_multiport_params
            fp = self.feed_params
            register_multiport_params(
                app, wf2=fp.get('wf2', 0.2), lf4=fp.get('lf4', 0.2),
                lf5=fp.get('lf5', 3.0), lf6=fp.get('lf6', 0.2))
            app.para('x01', fp.get('x01', 0))
        else:
            app.para('x0', self.x0)
            app.para('wf1', self.wf1)
            app.para('lf1', self.lf1)
            app.para('lf2', self.lf2)
            app.para('lf3', self.lf3)

        # waveguide 参数（铜波导尺寸，默认值与参考模型一致）
        app.para('wg_a', self.wg_a)
        app.para('wg_b', self.wg_b)
        app.para('wg_t', self.wg_t)

    # ---- 预览 ----

    def preview(self, ax=None, show_grid=True):
        """matplotlib 预览路径 + 晶格背景。"""
        return self.path.preview(ax=ax, show_grid=show_grid,
                                  label=f'StraightWaveguide ({self.topology}, L={self.length})')

    # ---- 端到端建模 ----

    def build_all(self):
        """
        端到端建模：参数定义 → 材料 → 基板 → VPC → 晶体 → 晶体∩VPC → feed → waveguide → mirror → ports → 整合 → 求解器。
        """
        if self.app is None:
            raise RuntimeError("CST 初始化失败，无法建模。请检查 template_cst 路径。")

        app = self.app

        # 1. 定义所有 CST 参数
        self._define_all_params()

        # 2. 材料（参考工程 AB_feed.cst 的历史里，Silicon (lossy) 与
        #    Copper (annealed) 是两条最早的显式记录；模板 tmp.cst 本身
        #    不带材料，缺了这一步第一条 extrude 就会报材料不存在）
        build_materials(app)

        # 3. VPC 区域的**半宽**必须覆盖整个晶体阵列
        #    参考工程 AB_feed.cst 的 ymax_up = e2*y1 = 14*e2 ≈ 2.94（14 行晶格），
        #    而 y_margin 默认值 'e2' 只有 1 行宽（0.21）—— 会让 14 行的晶体阵列
        #    远远落在基板之外。故按 width（= 旧代码 y1）取值。
        y_margin = f'{self.width}*e2'

        # 4. VPC 区域（A=下半区 / B=上半区，语义对齐参考工程，见 build_vpc_regions）
        #
        #    ⚠️ 这里**不再单独建 substrate**（2026-09-15，对齐参考工程）：
        #    参考工程 `AB_feed.cst` 的实体清单里**没有 substrate**，它的硅就是
        #    `vpca`（= 下半区∩晶体A + feed1 + 上半区∩晶体B）；晶体阵列经
        #    `vpca intersect g1A` / `vpcb intersect g1B` 裁剪成**图形化**的硅。
        #    若本库额外保留一块整幅未图形化的 substrate（同为 Silicon (lossy)），
        #    它与图形化区域求并会**把光子晶体的孔洞全部填平**，器件失去周期性。
        #    build_substrate() 仍保留在库中（unit_antenna 等其它器件可能仍需要），
        #    只是本模板用参考工程的做法：两个 VPC 区域即硅本体。
        vpca_name, vpcb_name = build_vpc_regions(app, self.path, y_margin=y_margin)

        # 5. 光子晶体阵列
        #    阵列次数传**参数名**（历史里写 `int(xup)`/`int(yup/2)`/`int(ydn/2)`，
        #    与参考 AB_feed 工程一致；旧行为是烘成 `int(25)`，参数形同备注）
        crystal_a_name, crystal_b_name = build_topological_crystal(
            app, self.path, topology=self.topology,
            xup='xup', yup='yup', ydn='ydn')

        # 6. 晶体阵列与 VPC 区域求交
        #    参考工程：vpca intersect g1A / vpcb intersect g1B
        #    （Intersect 结果留第一个操作数，故 VPC 区域名被保留，晶体名被消耗）
        intersect_crystal_with_vpc(app, crystal_a_name, crystal_b_name,
                                   vpca_name, vpcb_name)

        # 7. 馈源（默认 AB 型椭圆探针 feed1；BA 族用 feed2 —— 与参考工程同名）
        ba_feed = self.feed_type == 'ba_tapered'
        feed_name = build_feed(app, feed_type=self.feed_type,
                               name='feed2' if ba_feed else 'feed1')

        # 8. 空心矩形波导
        #    AB 族用 `[-lf1-lf2-lf3, -lf1]`；BA 族的波导长在椭圆过渡段之外
        #    ⇒ `[-lf5-lf6-lf4, -lf4]`，且 y 在轴线上（参考 BA_feed_epc 一致）
        if ba_feed:
            wg_name = build_waveguide(app, name='wg1', x_min='-lf5-lf6-lf4',
                                      x_max='-lf4', y_center='0')
        else:
            wg_name = build_waveguide(app, name='wg1')

        # 9. mirror feed + waveguide 到右端（中心点 p2x/2，法向量 x）
        #     注：参考写 x1*a/2，与本库 p2x/2 数值相同（均为 4.365/2 = 2.1825）
        mirror_center = ['p2x/2', '0', '0']
        app.mirror(feed_name, mirror_center, ['1', '0', '0'], copy=True, unite=True)
        app.mirror(wg_name, mirror_center, ['1', '0', '0'], copy=True, unite=True)

        # 10. 端口（2 个：入口 + 出口）
        add_ports_for_straight_waveguide(app, waveguide_name=wg_name)

        # 11. 整合：vpca + feed + vpcb
        app.add(vpca_name, feed_name)
        app.add(vpca_name, vpcb_name)

        # 12. 求解器配置
        configure_solver(app, freq_range=self.freq_range, monitors=self.monitors)

        self._built = True
        return self

    # ---- 保存 / 运行 ----

    def save(self, output_path=None):
        """保存 .cst 文件。"""
        path = output_path or self.output_path
        if path is None:
            raise ValueError("请指定 output_path")
        if not self._built:
            self.build_all()
        self.app.cst_file.save(path, include_results=False, allow_overwrite=True)
        print(f"已保存: {path}")
        return path

    def run(self):
        """运行仿真。"""
        if not self._built:
            self.build_all()
        # 库的求解入口是 setup.run()（下发 Solver 历史并启动仿真）。
        # 旧写法 self.app.start_solver() 在全库中并不存在，会抛 AttributeError。
        self.app.run()
        return self

    def validate(self):
        """
        结构化验收：读 CST 消息 + 跑 ``Rebuild()``。

        :return: dict, 见 ``cst_solver.validation.ValidationMixin.validate_model``
        """
        if not self._built:
            self.build_all()
        return self.app.validate_model()

    def close(self):
        """
        关闭 CST 工程与设计环境，释放资源（阶段 5.7.1）。

        ⚠️ **先 save() 再 close()**。关掉之后 ``save()`` 不会写出任何东西，
        守卫层（``cst_solver._guards`` 陷阱 T15）会直接报错；有未保存改动时
        ``close()`` 会给一条 warning。

        :return: self
        """
        self.modeler.close()
        return self

    def __enter__(self):
        """支持 with 语句，保证工程一定被关闭。"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出时关闭工程。"""
        try:
            self.close()
        except Exception:
            if exc_type is None:
                raise
        return False

    def __repr__(self):
        return (f"StraightWaveguide(topology='{self.topology}', length={self.length}, "
                f"a={self.a}, h={self.h}, built={self._built})")
