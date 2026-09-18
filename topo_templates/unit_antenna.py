# -*- coding: utf-8 -*-
r"""
UnitAntenna — 单元天线端到端模板
================================
复现旧代码 Ant1_D_BA_120D / Ant3_epc 等单元天线的完整建模流程。

内部流程：
  1. 构建 TopoPath（直段 + 拐弯 + 臂）
  2. 定义 CST 参数
  3. build_substrate → build_vpc_regions → build_topological_crystal
  4. build_feed(ba_tapered) → build_waveguide
  5. 可选：圆柱辐射体
  6. add_port(1 个端口)
  7. integrate
  8. configure_solver（含 Farfield）

用户使用：
    >>> from topo_templates import UnitAntenna
    >>> ant = UnitAntenna(bend_angle=120, straight_length=18, arm_length=14,
    ...                   output_path=r'D:\out\ant.cst')
    >>> ant.preview()
    >>> ant.build_all()
    >>> ant.save()

@author: PC
"""

import numpy as np

from mesh_grid.tri_grid import TopoPath
from topo_modeler import TopoModeler, NameManager
from topo_modeler.builders import (
    build_materials,
    build_substrate,
    build_vpc_regions,
    build_topological_crystal,
    build_feed,
    build_cylinder_feed,
    build_waveguide,
    add_port_for_antenna,
    configure_solver,
)


class UnitAntenna:
    """
    单元天线端到端模板（直段 + 拐弯 + 臂 + 辐射体）。

    :param bend_angle: int, 拐弯**张角**（两侧臂的夹角，120 的整数倍；0 表示直波导型天线）。
        单臂相对直段的偏角 = `bend_angle/2`（60° 的整数倍），AB 朝 +y、BA 朝 −y（互为镜像）。
        参考 notebook/工程文件名里的数字就是这个张角：`120D` ⇔ `bend_angle=120`
        （= 单臂 ±60°，臂端 (6.0625, ±2.9402)），`240D` ⇔ `bend_angle=240`
    :param straight_length: int, 直段长度（晶格数）
    :param arm_length: int, 臂长（拐弯后长度，晶格数）
    :param topology: str, 'AB' 或 'BA'（默认 'BA'，天线常用）
    :param lattice_constant: float, 晶格常数 a (mm)
    :param height: float, 硅片厚度 h (mm)
    :param large_hole_ratio: float, 大孔比例
    :param small_hole_ratio: float, 小孔比例
    :param feed_type: str, 馈源类型（默认 'ba_tapered'）
    :param radiator: str, 辐射体类型（None / 'cylinder'）
    :param radiator_radius: float, 圆柱辐射体半径 (mm)
    :param freq_range: tuple, 频率范围
    :param monitors: tuple, 监视器（默认含 Farfield）
    :param template_cst: str, CST 模板文件
    :param output_path: str, 输出路径
    """

    def __init__(self, bend_angle=120, straight_length=18, arm_length=14,
                 topology='BA', lattice_constant=0.2425, height=0.25,
                 large_hole_ratio=0.65, small_hole_ratio=0.35,
                 feed_type='ba_tapered',
                 radiator=None, radiator_radius=0.3,
                 wg_a=0.7312, wg_b=0.3756, wg_t=0.2,
                 freq_range=(300, 380), monitors=('E', 'Farfield'),
                 template_cst='tmp.cst', output_path=None,
                 feed_params=None):
        """
        :param radiator: str/None, 辐射体类型（None 或 'cylinder'）
        :param radiator_radius: float, 圆柱辐射体半径（mm）
        :param wg_a: float, 空心波导内腔 z 向高度（mm），参考模型为 0.7312
        :param wg_b: float, 空心波导内腔 y 向宽度（mm），参考模型为 0.3756
        :param wg_t: float, 波导壁厚（mm），参考模型为 0.2
        :param feed_params: dict 可选, **馈源族参数的覆盖入口**。
            参考 notebook 里这些值并不统一（实测 `lf2` = 3 / 0.2，`lf5` = 3.0 / 0.2 / 0.45），
            而它们此前在模板里是**写死**的 ⇒ 那些模型复现不了。
            可覆盖：`x0 / wf1 / lf1 / lf2 / lf3`（AB 族）与
            `x01 / wf2 / lf4 / lf5`（BA 族）。
            例：`feed_params={'lf5': 0.2}`（对应参考 `Ant1_D_BA_120D_circle_DF`）。
        """
        if topology not in ('AB', 'BA'):
            raise ValueError(f"topology 必须是 'AB' 或 'BA'，收到 '{topology}'")
        # 🔵 `bend_angle` 是**张角**（两侧臂的夹角）= 单臂相对直段偏角的 2 倍。
        #    单臂偏角必须是 60° 的整数倍（三角晶格只有 6 个方向），
        #    所以张角必须是 **120 的整数倍**；60/180/300 会得到 30°/90°/150° 的臂，
        #    那不是晶格方向，必须在这里挡住。
        if bend_angle != 0 and bend_angle % 120 != 0:
            raise ValueError(
                f"bend_angle 是张角（两侧臂夹角），单臂偏角 = bend_angle/2 必须是 "
                f"60° 的整数倍，因此 bend_angle 必须是 120 的整数倍（0/120/240/…），"
                f"收到 {bend_angle}")

        self.bend_angle = bend_angle
        self.straight_length = straight_length
        self.arm_length = arm_length
        self.topology = topology
        self.a = lattice_constant
        self.h = height
        self.l1 = large_hole_ratio * self.a
        self.l2 = small_hole_ratio * self.a
        self.feed_type = feed_type
        self.radiator = radiator
        self.radiator_radius = radiator_radius
        self.freq_range = freq_range
        self.monitors = monitors
        self.template_cst = template_cst
        self.output_path = output_path
        #: 馈源族参数覆盖（见 ctor docstring）；`_define_all_params` 里逐项取值
        self.feed_params = self._check_feed_params(feed_params)

        # 空心波导参数（默认值取自参考模型，保证默认参数下几何一致）
        self.wg_a = wg_a
        self.wg_b = wg_b
        self.wg_t = wg_t

        # 三角晶格几何参数
        self.e1 = self.a / 2
        self.e2 = self.a * np.sqrt(3) / 2

        # 构建路径：起点 (0,-1) → 直段 → 拐弯 → 臂
        #
        # 🔵 `bend_angle` 是**张角**（两侧臂夹角）；单臂相对直段的偏角是它的一半。
        #    依据（2026-09-17 离线逐位比对，见 docs/validation/p4_real_machine_evidence.md §4.5）：
        #      参考工程 AB 120 的臂端 = (6.0625, +2.9402) = turn(+60) ✅
        #      参考工程 BA 120 的臂端 = (6.0625, -2.9402) = turn(-60) ✅（两者严格镜像）
        #      参考 240D notebook 的臂方向 120° = turn(120)
        #    即文件名里的数字是「两侧臂张角」= 2 × 单臂偏角；符号按拓扑取
        #    （AB 臂朝 +y、BA 臂朝 -y），否则两种拓扑不是镜像。
        sign = 1 if topology == 'AB' else -1
        b = (TopoPath.builder(self.a, name='p')
             .start(0, -1)
             .move(straight_length + 1, 'c'))
        if bend_angle != 0:
            b.turn(sign * (bend_angle // 2)).move(arm_length, 'along')
        self.path = b.build()

        # 阵列范围：**不能**直接用 path.get_array_range()
        #
        # 实测（P4/V1，CST 2026 真机）：get_array_range() 给出 (26, 16, 1) ——
        # yup=16 / ydn=1 既不对称、也覆盖不到臂；更致命的是 ydn=1 会让
        # crystal.py 下发 `int(ydn/2)` = 0 次复制，CST 直接报
        # "Invalid number of repetitions"。
        #
        # 参考工程（`普通单元天线\Ant1_D_{AB,BA}_120_Feed_antenna-DF` 的
        # Parameters.json 与对应 ipynb）的权威取值：
        #     xup = x1 + int(y1/2)        （AB，= 25）
        #     xup = x1 + int(y1/2) + 1    （BA，= 26）
        #     yup = ydn = y1 = 14         （= 臂长；阵列步长 e2*2，重复 int(yup/2)=7）
        # 其中 x1 = 直段周期数 ≈ straight_length、y1 = 臂长 = arm_length。
        self.xup = (self.straight_length + int(self.arm_length / 2)
                    + (1 if topology == 'BA' else 0))
        self.yup = self.arm_length
        self.ydn = self.arm_length

        # TopoModeler
        self.modeler = TopoModeler(template_cst=template_cst)
        self.modeler.set_path(self.path)
        self.modeler.set_parameters({
            'a': self.a, 'h': self.h,
            'l1': self.l1, 'l2': self.l2,
            'e1': self.e1, 'e2': self.e2,
        })
        self.app = self.modeler.app
        self.nm = NameManager()

        self._built = False

    # ---- CST 参数定义 ----

    #: `feed_params` 允许覆盖的参数名（按馈源族分）
    _FEED_PARAM_NAMES = {
        'ba_tapered': ('x01', 'wf2', 'lf4', 'lf5'),
        'ab_elliptical': ('x0', 'wf1', 'lf1', 'lf2', 'lf3'),
    }

    def _check_feed_params(self, feed_params):
        """校验 `feed_params` 的键名 —— **写错的键必须报错**，不能静默忽略。

        （静默忽略等于"改了个不存在的参数"，几何一点没变而调用方以为改了。
        本仓库对这类"看起来成功其实没生效"一律零容忍。）
        """
        params = dict(feed_params or {})
        if not params:
            return params
        allowed = set(self._FEED_PARAM_NAMES.get(self.feed_type, ()))
        allowed |= {'lf1', 'lf2', 'lf3'}          # 波导范围引用的三个，始终可覆盖
        unknown = sorted(set(params) - allowed)
        if unknown:
            raise ValueError(
                f'feed_params 里有未知参数名 {unknown}；'
                f'feed_type={self.feed_type!r} 时可覆盖：{sorted(allowed)}')
        return params

    def _define_all_params(self):
        """定义所有 CST 参数。"""
        app = self.app

        # 基础参数
        app.para('a', self.a)
        app.para('h', self.h)
        app.para('l1', self.l1)
        app.para('l2', self.l2)
        app.para('e1', self.e1)
        app.para('e2', self.e2)

        # 路径参数
        self.path.auto_define_cst_params(app, prefix='p')

        # 阵列范围
        app.para('xup', self.xup)
        app.para('yup', self.yup)
        app.para('ydn', self.ydn)

        # feed 参数：**按 `feed_type` 登记对应的馈源族**
        #
        #   BA 型渐变探针（feed2，本模板默认）：x01 / wf2 / lf4 / lf5
        #   AB 型椭圆探针（feed1）：x0 / wf1（lf1/lf2/lf3 下面无条件登记，
        #     因为本模板的波导 `build_waveguide(name='wg1')` 默认范围是
        #     `[-lf1-lf2-lf3, -lf1]`，**引用它们**）
        #
        # ⚠️ 2026-09-17（P0 迁移取证）：此前无条件只登记 BA 族，于是
        #    `UnitAntenna(feed_type='ab_elliptical')` 会引用未定义的 x0/wf1；
        #    而 lf1/lf2/lf3 当时也**没人登记**，只是靠模板 `tmp.cst` 的遗留参数
        #    才没报错（该模板并不干净，见 P4 §8.7）—— 换干净模板就会弹
        #    「请输入变量值」模态对话框把脚本挂住。
        if self.feed_type == 'ba_tapered':
            fp = self.feed_params
            app.para('x01', fp.get('x01', 0))
            app.para('wf2', fp.get('wf2', 0.2))
            app.para('lf4', fp.get('lf4', 0.2))
            app.para('lf5', fp.get('lf5', 3.0))
        else:
            fp = self.feed_params
            app.para('x0', fp.get('x0', 4))
            app.para('wf1', fp.get('wf1', 0.2))

        # 波导范围 `[-lf1-lf2-lf3, -lf1]` 引用的三个参数：**必须登记**
        fp = self.feed_params
        app.para('lf1', fp.get('lf1', 0.2))
        app.para('lf2', fp.get('lf2', 3.0))
        app.para('lf3', fp.get('lf3', 0.2))

        # waveguide 参数
        app.para('wg_a', self.wg_a)
        app.para('wg_b', self.wg_b)
        app.para('wg_t', self.wg_t)

    # ---- 预览 ----

    def preview(self, ax=None, show_grid=True):
        """matplotlib 预览。"""
        return self.path.preview(ax=ax, show_grid=show_grid,
                                  label=f'UnitAntenna ({self.topology}, {self.bend_angle}°, '
                                        f'L={self.straight_length}, arm={self.arm_length})')

    # ---- 端到端建模 ----

    def build_all(self):
        """端到端建模。"""
        if self.app is None:
            raise RuntimeError("CST 初始化失败，无法建模。")

        app = self.app

        # 1. 定义所有 CST 参数
        self._define_all_params()

        # 2. 材料（模板 tmp.cst 不带材料，缺了这一步第一条 extrude
        #    就会报 The specified material does not exist）
        build_materials(app)

        # 3. 基板
        build_substrate(app, self.path, name='substrate')

        # 4. VPC 区域
        #    注意：AB/BA 的大孔小孔分配由 build_topological_crystal 负责，
        #    build_vpc_regions 只按路径上/下半区生成区域，不接受 topology 参数。
        vpca_name, vpcb_name = build_vpc_regions(app, self.path)

        # 5. 光子晶体阵列
        #    阵列次数传**参数名**而不是数值：几何历史里写 `int(xup)` / `int(yup/2)`，
        #    与参考工程一致 ⇒ 在 CST 里改 xup/yup/ydn 阵列会跟着重排。
        #    （2026-09-17 前传数值，历史里是 `int(25)`，参数表里的 xup/yup/ydn
        #     一个都没被引用，改参数不动几何；真机实测见 P4 证据 §8.7）
        build_topological_crystal(app, self.path, topology=self.topology,
                                   xup='xup', yup='yup', ydn='ydn')

        # 6. 馈源（BA 型对称渐变）
        feed_name = build_feed(app, feed_type=self.feed_type, name='feed2')

        # 7. 空心矩形波导
        wg_name = build_waveguide(app, name='wg1')

        # 8. 可选辐射体（圆柱）
        if self.radiator == 'cylinder':
            # 辐射体位于路径末端
            end_xy = self.path.xy[-1]
            cyl_name = build_cylinder_feed(
                app, name='radiator', radius=self.radiator_radius,
                position=[str(end_xy[0]), str(end_xy[1]), '-h/2'],
            )
            app.add(vpca_name, cyl_name)

        # 9. 端口（仅 1 个入口）
        add_port_for_antenna(app, waveguide_name=wg_name)

        # 10. 整合
        app.add(vpca_name, feed_name)
        app.add(vpca_name, vpcb_name)

        # 11. 求解器（含 Farfield）
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
        # 库的求解入口是 setup.run()；旧写法 self.app.start_solver() 在全库中不存在。
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
        守卫层（``cst_solver._guards`` 陷阱 T15）会直接报错。

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
        return (f"UnitAntenna(topology='{self.topology}', bend={self.bend_angle}°, "
                f"L={self.straight_length}, arm={self.arm_length}, built={self._built})")
