# -*- coding: utf-8 -*-
"""
TopoModeler — 拓扑光子晶体核心建模器
====================================
智能推断 + 流水线编排，是所有模板的基类。

统一管理：路径(TopoPath)、拓扑相(AB/BA)、参数、建模流水线、仿真、结果读取。

@author: PC
"""

import os
import numpy as np

#: 本模块经结构化失败通道产出的错误码。
#: 一致性检查（`scripts/check_api_consistency.py` 的 `error-codes` 项）要求
#: 代码里用到的码必须出现在某个 `*_ERROR_CODES` 表里。
MODELER_ERROR_CODES = (
    'cst_unavailable',      # CST 初始化失败（无 CST 环境）：app=None，建模/求解不可用
)

from topo_modeler.name_manager import NameManager
from topo_modeler.builders import (
    build_substrate,
    build_substrate_multi,
    build_vpc_regions,
    build_vpc_regions_multi,
    build_topological_crystal,
    build_crystals_multi,
    clip_crystals_with_vpc,
    build_feed as _build_feed_func,
    build_waveguide as _build_waveguide_func,
    build_grin_lens as _build_grin_lens_func,
    build_grin_lens_holes,
    grin_lens_spec_from_cst_params,
    add_ports_for_straight_waveguide,
    add_port_for_antenna,
    configure_solver,
)


def _guard_state(app):
    """
    取 ``cst_solver`` 守卫状态（方案 A：零侵入 ``cst_solver`` 的接线）。

    ``app`` 为 None（无 CST 环境）时返回一个一次性状态，调用方无需分支判断。

    :param app: cst_solver.setup 实例或 None
    :return: cst_solver._guards.GuardState
    """
    from cst_solver._guards import get_guard_state
    return get_guard_state(app)


class TopoModeler:
    """
    拓扑光子晶体核心建模器。

    智能推断规则：
      - model_type: path.is_straight() → 'waveguide'，path.has_bend() → 'antenna'
      - topology: 波导默认 'AB'，天线默认 'BA'，可被用户参数覆盖
      - 端口数: 波导 2 端口，天线 1 端口
      - 监视器: 波导 E 场，天线 E 场 + Farfield

    使用示例:
        >>> from topo_modeler import TopoModeler
        >>> from mesh_grid.tri_grid import TopoPath
        >>> path = TopoPath.builder(a=0.2425).start(0, -1).move(19, 'c').build()
        >>> modeler = TopoModeler(template_cst='tmp.cst')
        >>> modeler.set_path(path)
        >>> modeler.set_topology('AB')
        >>> modeler.build_all()
        >>> modeler.save('waveguide.cst')
    """

    def __init__(self, template_cst='tmp.cst'):
        """
        初始化 TopoModeler。

        :param template_cst: str, CST 模板文件路径，默认 'tmp.cst'
        """
        self.template_cst = template_cst
        self.app = None
        self.path = None                 # 向后兼容：等价于 self._paths['main'] 或第一条
        self._paths = {}                 # {名字: TopoPath}（阶段 8 模块 6.1 多路径）
        self.topology = None  # 'AB' / 'BA' / None(自动推断)
        self.model_type = None  # 'waveguide' / 'antenna' / None(自动推断)
        self.params = {}
        self.nm = NameManager()
        self._built_parts = {}  # 已构建的部件名称 {part_name: cst_name}
        self._cst_path = None

        # 延迟导入 cst_solver，避免在无 CST 环境下导入失败
        self._init_cst()

    def _init_cst(self):
        """初始化 CST 工程。"""
        try:
            from cst_solver import setup
            self.app = setup(self.template_cst)
        except Exception as e:
            # 无 CST 环境时（如单元测试），app 为 None
            self.app = None
            import warnings
            warnings.warn(f"CST 初始化失败（无 CST 环境？）: {e}。"
                          f"建模功能不可用，但路径/参数/推断功能可用。")
            # 这条失败必须能被共用服务看见：app=None 之后 run()/save() 会直接
            # 报 cst_unavailable，而不是静默什么都不做却返回成功
            from cst_solver.failures import record_failure
            record_failure('TopoModeler._init_cst', 'cst_unavailable',
                           f'CST 初始化失败，建模/求解不可用：{e}',
                           template_cst=self.template_cst, log=False)

    # ================================================================
    # 配置方法
    # ================================================================

    def set_path(self, path):
        """
        设置拓扑路径，自动推断 model_type。

        :param path: TopoPath 实例
        :return: self（支持链式调用）
        """
        self.set_paths({'main': path})
        return self

    # ---- 多路径（阶段 8 模块 6.1）----
    #
    # 旧 notebook 里「多路径」本来就是既有表达方式：例如
    # `功分器加天线\B5\Ant6_2H4L_epc.ipynb` 的 CST 参数表里同时有
    # `px1..py8` 与 `qx1..qy4` **两套坐标族** —— 一路用前缀 p，另一路用 q。
    # 所以本库的做法是：`TopoPath` 仍然只表示**一条**折线（不改它的语义），
    # 多路径由 `TopoModeler` 用 `{名字: TopoPath}` 管理。

    def set_paths(self, paths):
        """
        设置**多条**路径（阶段 8 模块 6.1）。

        多路径的用途：功分器 / MZI / 多端口天线里，「主干 + 若干分支」或
        「两条干涉臂」需要各自一条折线；基板、VPC 与晶体阵列的范围要按
        **所有路径的并集**取，而不是只看主干 —— 否则分支会露在基板之外
        （这正是阶段 4 T2/T5 那类问题的根因）。

        :param paths: dict, ``{名字: TopoPath}``；必须非空。也接受单个 TopoPath
            （等价于 ``{'main': path}``）
        :return: self
        :raises TypeError: 值不是 TopoPath
        :raises ValueError: 空字典或重名
        """
        if paths is None:
            raise ValueError('paths 不能为空')
        if hasattr(paths, 'path_lattice'):            # 直接给了单个 TopoPath
            paths = {'main': paths}
        if not isinstance(paths, dict) or not paths:
            raise ValueError(
                'set_paths 需要 {名字: TopoPath} 且至少一条；'
                '只有一条路径时可以直接用 set_path()')
        for name, path in paths.items():
            if not hasattr(path, 'path_lattice'):
                raise TypeError(
                    f'paths[{name!r}] 不是 TopoPath（收到 {type(path).__name__}）')
        self._paths = dict(paths)
        # 向后兼容：self.path 始终指向 'main'（没有 main 时取第一条）
        self.path = self._paths.get('main') or next(iter(self._paths.values()))
        self.model_type = self._infer_model_type()
        if self.topology is None:
            self.topology = self._infer_topology()
        return self

    def add_path(self, name, path):
        """
        追加一条路径。

        :param name: str, 路径名（例如 ``'main'`` / ``'arm1'`` / ``'arm2'``）
        :param path: TopoPath 实例
        :return: self
        :raises ValueError: 名字已存在
        :raises TypeError: path 不是 TopoPath
        """
        if not hasattr(path, 'path_lattice'):
            raise TypeError(f'path 不是 TopoPath（收到 {type(path).__name__}）')
        if name in self._paths:
            raise ValueError(
                f"路径名 {name!r} 已存在（现有：{sorted(self._paths)}）；"
                f"要替换请先 remove_path('{name}')")
        self._paths[name] = path
        if self.path is None:
            self.path = path
        self.model_type = self._infer_model_type()
        return self

    def remove_path(self, name):
        """
        删掉一条路径。

        :param name: str, 路径名
        :return: self
        :raises KeyError: 名字不存在
        :raises ValueError: 这是最后一条路径（不允许清空）
        """
        if name not in self._paths:
            raise KeyError(f'没有名为 {name!r} 的路径（现有：{sorted(self._paths)}）')
        if len(self._paths) == 1:
            raise ValueError('至少要保留一条路径')
        del self._paths[name]
        if self.path is not None and not any(p is self.path for p in self._paths.values()):
            self.path = next(iter(self._paths.values()))
        return self

    @property
    def paths(self):
        """路径字典的**副本**（``{名字: TopoPath}``）。"""
        return dict(self._paths)

    @property
    def path_names(self):
        """所有路径名（保持插入顺序）。"""
        return list(self._paths)

    @property
    def is_multi_path(self):
        """是否是多路径（>1 条）。"""
        return len(self._paths) > 1

    def all_lattice_points(self):
        """
        所有路径的晶格点**并集**（排序去重）。

        符号路径（含 `str` 坐标）会原样保留 —— 此时只能做集合运算，不能算数值。

        :return: list[tuple], 排序后的 ``(r, c)`` 列表
        """
        pts = set()
        for path in self._paths.values():
            for r, c in path.path_lattice:
                pts.add((r, c))
        try:
            return sorted(pts, key=lambda p: (float(p[0]), float(p[1])))
        except (TypeError, ValueError):
            return sorted(pts, key=lambda p: (str(p[0]), str(p[1])))

    def bounding_box(self):
        """
        覆盖**所有路径**的数值包围盒。

        :return: tuple, ``(xmin, xmax, ymin, ymax)``
        :raises RuntimeError: 存在符号路径且未给 param_values（无法算数值）
        """
        boxes = []
        for name, path in self._paths.items():
            try:
                boxes.append(path.get_bounding_box())
            except Exception as exc:                   # noqa: BLE001
                raise RuntimeError(
                    f'路径 {name!r} 算不出包围盒（符号路径需要 param_values）：{exc!r}'
                ) from exc
        return (min(b[0] for b in boxes), max(b[1] for b in boxes),
                min(b[2] for b in boxes), max(b[3] for b in boxes))

    def array_range(self, names=None):
        """
        覆盖**所有路径（或指定路径）**的晶体阵列范围 ``(xup, yup, ydn)``。

        这就是「基板 / VPC / 阵列范围要按所有路径并集取」的可执行形式：
        旧写法只按主干路径推，分支一长就会露出基板（阶段 4 T2/T5 的同类问题）。

        :param names: 序列可选, 只统计这些路径；不给则全部
        :return: tuple, ``(xup, yup, ydn)`` —— 取各路径所需范围的**逐项最大值**
        :raises KeyError: 给了不存在的路径名
        """
        selected = list(names) if names else list(self._paths)
        for name in selected:
            if name not in self._paths:
                raise KeyError(f'没有名为 {name!r} 的路径（现有：{sorted(self._paths)}）')
        ranges = [self._paths[n].get_array_range() for n in selected]
        xup = max(r[0] for r in ranges)
        yup = max(r[1] for r in ranges)
        ydn = max(r[2] for r in ranges)
        return (xup, yup, ydn)

    def describe_paths(self) -> str:
        """多路径的一段文字摘要（日志 / 报告用，不碰 CST）。"""
        lines = [f'路径数：{len(self._paths)}'
                 + ('（多路径）' if self.is_multi_path else '（单路径）')]
        for name, path in self._paths.items():
            n = len(path)
            kind = '直' if path.is_straight() else f'{len(path) - 1} 段'
            lines.append(f'  · {name}: {n} 个点 / {kind}'
                         f'{"（符号）" if getattr(path, "has_symbols", False) else ""}')
        if self.is_multi_path:
            try:
                xmin, xmax, ymin, ymax = self.bounding_box()
                lines.append(f'  并集包围盒：x ∈ [{xmin:.4f}, {xmax:.4f}]，'
                             f'y ∈ [{ymin:.4f}, {ymax:.4f}] mm')
                xup, yup, ydn = self.array_range()
                lines.append(f'  并集阵列范围：xup={xup}, yup={yup}, ydn={ydn}')
            except RuntimeError as exc:
                lines.append(f'  （数值量算不出：{exc}）')
        return '\n'.join(lines)

    def set_topology(self, topology):
        """
        设置拓扑相。

        :param topology: str, 'AB' 或 'BA'
        :return: self
        """
        if topology not in ('AB', 'BA'):
            raise ValueError(f"topology 必须是 'AB' 或 'BA'，收到 '{topology}'")
        self.topology = topology
        return self

    def set_parameters(self, params):
        """
        批量设置 CST 参数。

        cst_solver 的批量接口有两套签名，这里用的是**字典式**：
        ``app.paras({名称: 值}, None)`` —— ``paras(name, value, log_flag=0)``
        在 ``name`` 为 dict 时会忽略 ``value``。
        注意不要写成 ``app.set_parameters(params)``：那是
        ``set_parameters(name, value, log_flag=0)``，需要一个 dict 会直接抛 TypeError。

        :param params: dict, {参数名: 参数值, ...}
        :return: self
        """
        self.params.update(params)
        if self.app is not None:
            self.app.paras(params, None)
        return self

    def set_parameter(self, name, value):
        """
        设置单个 CST 参数。

        :param name: str, 参数名
        :param value: float/str, 参数值
        :return: self
        """
        self.params[name] = value
        if self.app is not None:
            self.app.para(name, value)
        return self

    # ================================================================
    # 智能推断
    # ================================================================

    def _infer_model_type(self):
        """从 path 判断模型类型：直线路径 → 波导，有拐弯 → 天线。"""
        if self.path is None:
            return None
        if self.path.is_straight():
            return 'waveguide'
        return 'antenna'

    def _infer_topology(self):
        """推断默认拓扑相：波导默认 AB，天线默认 BA。"""
        if self.model_type == 'waveguide':
            return 'AB'
        return 'BA'

    def _infer_monitors(self):
        """推断监视器类型：波导 E 场，天线 E 场 + Farfield。"""
        if self.model_type == 'waveguide':
            return ('E',)
        return ('E', 'Farfield')

    def _infer_ports(self):
        """推断端口数：波导 2 端口，天线 1 端口。"""
        if self.model_type == 'waveguide':
            return 2
        return 1

    # ================================================================
    # 流水线方法（按顺序调用 builders）
    # ================================================================

    def _mark_geometry(self):
        """
        告诉守卫层「几何刚建过」—— 此后**再改已存在的参数**会被判为需重建。

        这是阶段 5 守卫层的方案 A 接线：``cst_solver`` 源码不做改动，
        由 ``topo_modeler`` 在每个 builder 之后显式标记。
        """
        _guard_state(self.app).mark_geometry_built()

    def build_substrate(self, name='substrate', height='h',
                        material='Silicon (lossy)', y_margin='e2',
                        paths=None, **kwargs):
        """
        构建基板。

        **多路径时自动走并集**（阶段 8 模块 6.1）：`self._paths` 里有多条路径时，
        各路径各做一条带再布尔并成一个实体 —— 否则分支会露在基板之外。

        :param name: str, 基板名称
        :param height: str, 厚度参数名
        :param material: str, 材料
        :param y_margin: str, 半宽参数名
        :param paths: dict 可选, 只针对这些路径建（``{名字: TopoPath}``）；
            不给则用全部已设路径
        :return: str, 基板 CST 名称
        """
        self._check_path()
        target = paths or self._paths
        if len(target) > 1:
            cst_name = build_substrate_multi(
                self.app, target, name=name, height=height,
                material=material, y_margin=y_margin, **kwargs)
        else:
            one = next(iter(target.values()))
            cst_name = build_substrate(self.app, one, name=name, height=height,
                                        material=material, y_margin=y_margin)
        self._built_parts['substrate'] = cst_name
        self._mark_geometry()
        return cst_name

    def build_vpc_regions(self, name_prefix='vpc', height='h',
                           material='Silicon (lossy)', y_margin='e2',
                           paths=None, **kwargs):
        """
        构建 VPC-A 和 VPC-B 区域。

        **多路径时自动走并集**（阶段 8 模块 6.1，与 `build_substrate` 对称）：
        `self._paths` 里有多条路径时，各路径各做上/下半区带再布尔并 ——
        否则分支上的光子晶体落在 VPC 区域之外，会被裁掉。

        :param name_prefix: str, 名称前缀
        :param height: str, 厚度参数名
        :param material: str, 材料
        :param y_margin: str, 扩展量参数名
        :param paths: dict 可选, 只针对这些路径建（``{名字: TopoPath}``）
        :return: tuple, (vpca_name, vpcb_name)
        """
        self._check_path()
        target = paths or self._paths
        if len(target) > 1:
            vpca, vpcb = build_vpc_regions_multi(
                self.app, target, name_prefix=name_prefix, height=height,
                material=material, y_margin=y_margin, **kwargs)
        else:
            one = next(iter(target.values()))
            vpca, vpcb = build_vpc_regions(self.app, one, name_prefix=name_prefix,
                                            height=height, material=material,
                                            y_margin=y_margin)
        self._built_parts['vpca'] = vpca
        self._built_parts['vpcb'] = vpcb
        self._mark_geometry()
        return vpca, vpcb

    def build_crystals_multi(self, paths=None, topology=None, lattice='a',
                             height='h', large_hole='l1', small_hole='l2',
                             y_margin='e2', name_prefix='g', **kwargs):
        """
        多路径光子晶体：**每条路径各建一套 A/B 阵列**（阶段 8 模块 6.1）。

        命名沿用 `topo_modeler.builders.build_crystals_multi`：第 1 条路径是
        `g1A/g1B`（与单路径版本逐名相同），第 2 条是 `g2A/g2B`…

        :param paths: dict 可选, 只针对这些路径建；不给则用全部已设路径
        :param topology: str 可选, 'AB'/'BA'，默认用 `self.topology`
        :param kwargs: 传给 `build_topological_crystal`（如 `xup='xup'` 走参数引用）
        :return: dict, ``{路径名: (crystal_a_name, crystal_b_name)}``
        """
        self._check_path()
        target = paths or self._paths
        topo = topology or self.topology or 'AB'
        crystals = build_crystals_multi(
            self.app, target, topology=topo, lattice=lattice, height=height,
            large_hole=large_hole, small_hole=small_hole, y_margin=y_margin,
            name_prefix=name_prefix, **kwargs)
        self._built_parts['crystals'] = crystals
        self._mark_geometry()
        return crystals

    def clip_crystals_with_vpc(self, paths=None):
        """
        把各条路径的晶体阵列与（并集后的）VPC 区域求交（阶段 8 模块 6.1）。

        需要在 `build_vpc_regions()` 与 `build_crystals_multi()`（或单路径的
        `build_crystal()`）之后调用。操作数顺序与参考工程一致：
        ``vpca intersect g1A`` —— 结果留在 VPC 区域名上，晶体名被消耗。

        :param paths: dict 可选, 只裁这些路径的晶体
        :return: dict, 见 `builders.clip_crystals_with_vpc`（含被消耗的晶体名）
        :raises RuntimeError: 还没建过 VPC 区域或晶体
        """
        crystals = self._built_parts.get('crystals')
        if crystals is None:
            single = (self._built_parts.get('crystal_a'),
                      self._built_parts.get('crystal_b'))
            if None in single:
                raise RuntimeError('还没有晶体可裁剪：请先 build_crystal() 或 '
                                   'build_crystals_multi()')
            crystals = {'main': single}
        if paths:
            crystals = {name: pair for name, pair in crystals.items()
                        if name in paths}
        vpca = self._built_parts.get('vpca')
        vpcb = self._built_parts.get('vpcb')
        if not vpca or not vpcb:
            raise RuntimeError('还没有 VPC 区域可裁剪：请先 build_vpc_regions()')
        info = clip_crystals_with_vpc(self.app, vpca, vpcb, crystals)
        self._built_parts['clipped'] = info
        self._mark_geometry()
        return info

    def build_crystal(self, topology=None, lattice='a', height='h',
                      large_hole='l1', small_hole='l2', y_margin='e2', **kwargs):
        """
        构建光子晶体三角孔阵列。

        :param topology: str, 'AB'/'BA'，默认使用 self.topology
        :param lattice: str, 晶格常数参数名
        :param height: str, 厚度参数名
        :param large_hole: str, 大孔参数名
        :param small_hole: str, 小孔参数名
        :param y_margin: str, Y方向步长参数名
        :param kwargs: 透传给 `build_topological_crystal`，**尤其是
            `xup/yup/ydn`**（参数名 ⇒ 历史里写 `int(xup)`）。
            ⚠️ 不传它们会回退到 `path.get_array_range()` —— 对**单边偏置**的路径
            （例如 MZI）会给出 `ydn=1`，`int(ydn/2)=0`，CST 直接报
            `Invalid number of repetitions`（P4/V1 与 P5 MZI 各踩过一次）。
        :return: tuple, (crystal_a_name, crystal_b_name)
        """
        self._check_path()
        topo = topology or self.topology or 'AB'
        ca, cb = build_topological_crystal(self.app, self.path, topology=topo,
                                            lattice=lattice, height=height,
                                            large_hole=large_hole, small_hole=small_hole,
                                            y_margin=y_margin, **kwargs)
        self._built_parts['crystal_a'] = ca
        self._built_parts['crystal_b'] = cb
        self._mark_geometry()
        return ca, cb

    def build_feed(self, feed_type=None, name=None, **params):
        """
        构建探针/馈电。

        智能推断：waveguide 默认 'ab_elliptical'，antenna 默认 'ba_tapered'。

        :param feed_type: str, 'ab_elliptical' / 'ba_tapered' / 'cylinder'
        :param name: str, 馈源名称（None 则按类型默认）
        :param params: 传递给 build_feed 的额外参数
        :return: str, 馈源 CST 名称
        """
        self._check_path()
        if feed_type is None:
            feed_type = 'ab_elliptical' if self.model_type == 'waveguide' else 'ba_tapered'
        cst_name = _build_feed_func(self.app, feed_type=feed_type, name=name, **params)
        self._built_parts['feed'] = cst_name
        self._mark_geometry()
        return cst_name

    def build_waveguide(self, name='wg1', material='Copper (annealed)', **params):
        """
        构建空心矩形波导（外方体 - 内方体）。

        :param name: str, 波导名称
        :param material: str, 材料
        :param params: 传递给 build_waveguide 的额外参数
        :return: str, 波导 CST 名称
        """
        self._check_path()
        cst_name = _build_waveguide_func(self.app, name=name, material=material, **params)
        self._built_parts['waveguide'] = cst_name
        self._mark_geometry()
        return cst_name

    def build_lens(self, spec=None, dxf_path=None, name='lens_epc',
                   component='gridlens', material='Silicon (lossy)',
                   height='h', **lens_kwargs):
        """
        构建 GRIN 椭圆透镜（阶段 6）。

        几何由 `topo_modeler.builders.lens` 负责（**纯 numpy/shapely，不依赖 CST**），
        本方法只做三件事：算几何 → 落 DXF → 调 CST 步骤。

        🔴 **开工前必须知道**：CST 的 DXF 导入是"每条多段线建一个实体"，
        耗时随孔数**超线性**增长（参考配置 2215 条 ≈ 184 s）。

        ⚠️ **提速方向别记反**（2026-09-17 实测更正，此前这里写的是「抬高 ratio」）：
        固定 `nx/ny` 时孔数与 `ratio` **无关**（ratio 0.5→4 都是 713 个，
        因为 `ec_a = nx·a2` 与格距同比缩放 ⇒ 器件物理尺寸跟着变）；
        **固定器件物理尺寸**（`nx` 随 ratio 同步缩放）时孔数 **∝ ratio²**
        （ratio 0.75/1/1.5/2 ⇒ 449/713/1630/2828）。
        ⇒ 要提速就**降 ratio 并把 nx/ny 同比缩小**，且 `nx > 12` 是硬约束
        （`d_out > d0 = 12·a2`）—— 所以固定尺寸下提速幅度有限，
        要大幅减孔只能整体缩小器件。回归：`test_lens_ratio_does_not_change_hole_count`。

        :param spec: GrinLensSpec 可选, 透镜参数；不给则用 ``lens_kwargs`` 现拼
            （可传 ``a / ratio / nx / ny / r1_0 / r2_0 / r_big``，也接受旧脚本的
            ``lens_ratio / lens_Nx / R_big / nsm`` 等别名）
        :param dxf_path: str 可选, 孔阵列 DXF 的输出路径；不给则放在当前目录的
            ``grin_lens_hexring.dxf``
        :param name: str, 透镜实体名
        :param component: str, 孔阵列归属组件（= DXF 图层名）
        :param material: str, 材料
        :param height: str, 厚度参数名（CST 表达式）
        :param lens_kwargs: 透传给 :func:`grin_lens_spec_from_cst_params` 的参数
        :return: dict，含 ``name`` / ``dxf_path`` / ``spec`` / ``holes`` / 几何摘要
        :raises RuntimeError: 无 CST 环境
        """
        if self.app is None:
            raise RuntimeError(
                "CST 初始化失败，无法建透镜。透镜几何本身不依赖 CST —— "
                "只想算几何 / 出 DXF 时请直接用 "
                "topo_modeler.builders.lens.build_grin_lens_holes()")
        if spec is None:
            if not lens_kwargs:
                raise ValueError(
                    "build_lens 需要 spec，或给出足够拼出 spec 的参数"
                    "（a / ratio / nx / ny / r1_0 / r2_0 / r_big）")
            spec = grin_lens_spec_from_cst_params(**lens_kwargs)

        holes = build_grin_lens_holes(spec)
        if dxf_path is None:
            dxf_path = os.path.abspath('grin_lens_hexring.dxf')
        holes.export_dxf(dxf_path, layer_name=component)

        out = _build_grin_lens_func(self.app, holes, spec, name=name,
                                    component=component, material=material,
                                    height=height, dxf_path=dxf_path)
        self._built_parts['lens'] = name
        self._mark_geometry()
        out['spec'] = spec
        out['holes'] = holes
        out['describe'] = holes.describe()
        return out

    def add_ports(self, auto=True, waveguide_name=None, **params):
        """
        添加波导端口。

        智能推断：waveguide 2 端口，antenna 1 端口。

        :param auto: bool, 是否自动推断端口数
        :param waveguide_name: str, 波导 solid 名称（默认 'wg1'）
        :param params: 额外参数
        :return: list, 端口编号列表
        """
        self._check_path()
        wg = waveguide_name or self._built_parts.get('waveguide', 'wg1')
        if self.model_type == 'waveguide':
            p1, p2 = add_ports_for_straight_waveguide(self.app, waveguide_name=wg)
            self._built_parts['ports'] = [p1, p2]
            return [p1, p2]
        else:
            p1 = add_port_for_antenna(self.app, waveguide_name=wg)
            self._built_parts['ports'] = [p1]
            return [p1]

    def configure_solver(self, freq_range=(300, 380), monitors=None, **kwargs):
        """
        配置求解器。

        :param freq_range: tuple, (fmin, fmax)
        :param monitors: tuple, 监视器类型，默认自动推断
        :param kwargs: 其他参数（steady_state, parallel_threads, gpus 等）
        """
        if monitors is None:
            monitors = self._infer_monitors()
        configure_solver(self.app, freq_range=freq_range, monitors=monitors, **kwargs)
        self._built_parts['solver'] = True

    def integrate(self):
        """
        整合所有部件（布尔加）。

        阶段 2 基础整合：基板 + VPC 区域 + 晶体阵列。
        阶段 3/4 将扩展探针、波导、透镜的整合。
        """
        # 基础整合由各 builder 内部完成（add/subtract/intersect）
        # 这里预留统一整合接口
        pass

    # ================================================================
    # 端到端方法
    # ================================================================

    def build_all(self, freq_range=(300, 380), include_feed=True,
                  include_waveguide=True, include_ports=True, **kwargs):
        """
        按顺序执行全部建模步骤。

        顺序：基板 → VPC区域 → 光子晶体阵列 → 馈源 → 波导 → 端口 → 求解器配置

        :param freq_range: tuple, 频率范围
        :param include_feed: bool, 是否构建馈源
        :param include_waveguide: bool, 是否构建波导
        :param include_ports: bool, 是否添加端口
        :param kwargs: 传递给各 builder 的参数
        :return: self
        """
        self.build_substrate(**kwargs.get('substrate_kw', {}))
        self.build_vpc_regions(**kwargs.get('vpc_kw', {}))
        self.build_crystal(**kwargs.get('crystal_kw', {}))
        if include_feed:
            self.build_feed(**kwargs.get('feed_kw', {}))
        if include_waveguide:
            self.build_waveguide(**kwargs.get('waveguide_kw', {}))
        if include_ports:
            self.add_ports(**kwargs.get('port_kw', {}))
        self.configure_solver(freq_range=freq_range, **kwargs.get('solver_kw', {}))
        self.integrate()
        return self

    def save(self, path):
        """
        保存 CST 工程。

        :param path: str, 保存路径
        :return: self
        :raises CstOperationError: ``app is None``（CST 环境没起来）——
            旧版本在这种情况下**什么都不写却返回成功**，会把「没保存」当成
            「保存成功」，因此改为结构化失败
        """
        if self.app is None:
            from cst_solver.failures import CstOperationError
            raise CstOperationError(
                'cst_unavailable',
                '没有 CST 环境（app is None），save() 无法写出任何东西；'
                '这是结构化失败，不是空结果',
                operation='TopoModeler.save')
        self.app.save(path)
        self._cst_path = path
        return self

    def run(self):
        """
        运行仿真。

        ⚠️ ``cst_solver`` 的守卫层会在这里拦截「参数改过但工程历史没重建」的情况
        （陷阱 T2）：``mode='strict'`` 抛 ``CstGuardError``，``mode='warn'`` 只警告。
        正确的改参姿势是先 ``self.app.update()``（或 ``para(..., log_flag=1)``）。

        :return: self
        :raises CstOperationError: ``app is None``（CST 环境没起来）——
            旧版本在这种情况下**不提交任何仿真却返回成功**
        """
        if self.app is None:
            from cst_solver.failures import CstOperationError
            raise CstOperationError(
                'cst_unavailable',
                '没有 CST 环境（app is None），run() 没有提交任何仿真；'
                '这是结构化失败，不是「跑完了」',
                operation='TopoModeler.run')
        self.app.run()
        return self

    def validate(self):
        """
        结构化验收：读 CST 消息 + 跑 ``Rebuild()``。

        等价于 ``self.app.validate_model()``；无 CST 环境时返回一个
        说明性的 error 结果而不是抛异常，方便在无 CST 的机器上做流程编排。

        :return: dict, 见 ``cst_solver.validation.ValidationMixin.validate_model``
        """
        if self.app is None:
            return {'status': 'error', 'messages': ['无 CST 环境，app 为 None'],
                    'rebuild_ok': False, 'before': [], 'guard': {}}
        return self.app.validate_model()

    def close(self):
        """
        关闭 CST 工程与设计环境，释放资源（阶段 5.7.1）。

        ⚠️ **先 save() 再 close()** —— 关闭之后 ``save()`` 不会写出任何东西，
        守卫层会直接报错。有未保存改动时 ``close()`` 会给一条 warning。

        :return: self
        """
        if self.app is not None:
            self.app.close()
        self._cst_path = None
        return self

    def __enter__(self):
        """支持 with 语句（保证工程一定被关闭）。"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出时关闭工程；关闭本身出错不掩盖原始异常。"""
        try:
            self.close()
        except Exception:
            if exc_type is None:
                raise
        return False

    def preview(self, ax=None, show_grid=True):
        """
        预览路径（matplotlib）。

        :param ax: matplotlib Axes, 默认新建
        :param show_grid: bool, 是否显示晶格背景
        :return: tuple, (fig, ax)
        """
        self._check_path()
        return self.path.preview(ax=ax, show_grid=show_grid)

    def read_results(self, path=None, names=None, run_id=0):
        """
        读取仿真结果（阶段 7 模块 5.1）。

        返回一个 :class:`topo_modeler.result_reader.ResultReader` —— 它**不需要
        设计环境**（走 `cst.results.ProjectFile` 离线读），所以「跑完关掉工程之后再读」
        是最自然的用法，也不会占用求解器许可。

        :param path: str 可选, .cst 路径；不给则用 `save()` / `build_all()` 记下的
            `self._cst_path`
        :param names: 序列可选, 只读这些 S 参数名；不给则自动发现
        :param run_id: int, 运行 ID（0 = 当前/最新结果）
        :return: ResultReader
        :raises RuntimeError: 既没有传 path，也没有已知的工程路径
        """
        from topo_modeler.result_reader import ResultReader

        target = path or self._cst_path
        if target is None:
            raise RuntimeError(
                "read_results 不知道读哪个工程 —— 请传 path=，"
                "或先 save('/path/to/x.cst')，或在 build_all() 时给出 output_path")
        return ResultReader(target, names=names, run_id=run_id)

    def plot_results(self, path='results_report.html', title=None, note='',
                     highlight=None, meta=None, audit=None, **kwargs):
        """
        自动出图并落成**自包含 HTML 报告**（阶段 7 §3.2）。

        报告引擎在 `topo_modeler.report`：**零 CDN、零 JS**，所有图形都是内联 SVG，
        断网/十年后都能打开。同时把审计记录（如果给了 `audit`）一并附上 ——
        这样一份报告既回答了「结果长什么样」，也回答了「这次是怎么跑出来的」。

        :param path: str, 输出 .html 路径
        :param title: str 可选, 报告标题（默认按 model_type / topology 生成）
        :param note: str, 图下附注
        :param highlight: 可选, ``[(频点 GHz, 标注), …]`` 画竖直参考线
        :param meta: dict 可选, 报告顶部额外元信息
        :param audit: AuditLog 可选, 一并附上审计小节
        :param kwargs: 透传给 `read_results()`（如 `run_id=` / `names=`）
        :return: str, 写出的 HTML 绝对路径
        """
        reader = self.read_results(**kwargs)
        auto_title = title or (
            f"{self.model_type or 'model'} · {self.topology or '-'} · 仿真结果")
        base_meta = {
            '模型类型': self.model_type or '（未知）',
            '拓扑相': self.topology or '（未知）',
            '路径点数': len(self.path) if self.path else 0,
            '已建部件': ', '.join(self._built_parts.keys()) or '（无）',
        }
        base_meta.update(meta or {})
        return reader.plot_all(path, title=auto_title, meta=base_meta,
                               note=note, highlight=highlight, include_audit=audit)

    # ================================================================
    # 工具方法
    # ================================================================

    def _check_path(self):
        """检查 path 是否已设置。"""
        if self.path is None:
            raise RuntimeError("请先调用 set_path() 设置拓扑路径")

    def get_built_parts(self):
        """返回已构建的部件名称字典。"""
        return dict(self._built_parts)

    def __repr__(self):
        parts = ', '.join(self._built_parts.keys()) or 'none'
        return (f"TopoModeler(type={self.model_type}, topology={self.topology}, "
                f"path={len(self.path) if self.path else 0}pts, built=[{parts}])")
