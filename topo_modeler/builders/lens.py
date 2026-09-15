# -*- coding: utf-8 -*-
"""
GRIN 椭圆透镜构建器（几何部分 + CST 建模步骤）
=============================================
把原先的**脚本** `topo_modeler/lens_build.py` 收编成**库函数**。

为什么值得收编
--------------
`lens_build.py` 是从 notebook 抽出的顶层脚本：它靠调用方注入 `app / cst_log / _m3 /
a / h / R_big / lens_ratio / lens_Nx / lens_Ny / lens_r1_0 / lens_r2_0` 才能跑，
**无法被 import**（import 会当场执行整段建模流程并把调用进程占住），
参数也没有类型/默认值/单位，几何公式更是只存在于代码里、任何文档都查不到。

本模块把它拆成两层，**两层的等价性都有回归测试钉住**（见
`topo_modeler/builders/tests/test_lens.py`）：

1. **纯几何层**（`GrinLensSpec` / `GrinLensHoles`）—— 只算孔心、孔半径、孔多边形、
   写 DXF、跑三道自查。**完全不依赖 CST**，可单独反复调参；
2. **CST 建模层**（`build_grin_lens()`）—— 只负责把几何变成 VBA 步骤。

几何约定（务必先读）
--------------------
坐标系是**局部系**，原点 = 椭圆**近焦点**（也就是大六边形顶点）：

- 椭圆中心在 ``(ec_c, 0)``，远焦点在 ``(2·ec_c, 0)``；
- 长半轴 ``ec_a = Nx·a2``（沿臂方向），短半轴 ``ec_b = Ny·a2·sind(60)``，
  焦距 ``ec_c = sqr(ec_a² − ec_b²)``；
- 孔网格格距 ``a2 = a / ratio``（``ratio`` 是细化倍率，越大孔越密）；
- 孔半径沿椭圆**等高线** ``d = √(x² + y²/(1−e²))`` 由内圈 ``r1`` 到外圈 ``r2`` 线性渐变。

三条硬约定（照抄原脚本，改动前先想清楚）：

1. 🔴 **孔网格的列范围必须覆盖整个椭圆。** 局部系里近焦点在原点，椭圆
   ``x ∈ [ec_c − ec_a, ec_c + ec_a]`` **关于 0 不对称**，所以列号只能按椭圆的真实
   x 范围取。原脚本注释里明确记着：旧版写 ``(-Nx, +Nx)``，网格只到 ``x = Nx·a2``，
   而椭圆要伸到 ``ec_c + ec_a`` ⇒ **椭圆外侧整片没孔 = 实心硅**。
2. 🔴 **DXF 只写上半平面（y ≥ 0）**，另一半在 CST 里用一次「y 镜像复制」补齐。
   依据：椭圆、孔网格行、孔半径（只依赖 y²）在 ``y → −y`` 下都不变。
   ⚠️ **不能再绕 ``x = ec_c`` 镜像** —— GRIN 的孔半径沿轴向单调变化，
   镜像过去的孔半径是错的。
3. 🟡 **DXF 坐标按 `dxf_precision` 位小数截断。** CST 的 DXF 导入是
   ``.AsCurves "False"``（每条多段线建一个实体），耗时随多段线数**超线性**增长；
   实测 precision 6→2 只让文件小 21%、几乎不影响耗时 ⇒ **精度不是瓶颈，孔数才是**。

@author: PC
"""

import math
import os
from dataclasses import dataclass, field, replace
from typing import List, Optional, Sequence, Tuple

import numpy as np

__all__ = [
    'GrinLensSpec',
    'GrinLensHoles',
    'LensGeometryError',
    'build_grin_lens_holes',
    'build_grin_lens',
    'grin_lens_spec_from_cst_params',
    'DFT_D_OUT_MODE',
    'D_OUT_MODES',
]


def _hex_grid_api():
    """
    惰性导入 ``mesh_grid.hex_grid`` 的三个符号。

    ⚠️ **为什么不在模块顶层 import**：`mesh_grid/hex_grid/core.py` 顶层就
    ``import ezdxf`` / ``from shapely.geometry import Polygon``，而这两个是
    `pyproject.toml` 里的**可选依赖**（extra ``geometry``）。
    若本模块顶层拉它们，``import topo_modeler.builders`` 就会连带要求安装
    shapely + ezdxf —— 那是**回归**（收编之前不需要）。
    所以只在真正要算几何 / 写 DXF 时才导入。
    """
    from mesh_grid.hex_grid import (HexGridVisualizer, create_hex_polygon,
                                    save_to_dxf)
    return HexGridVisualizer, create_hex_polygon, save_to_dxf


#: ``d_out`` 的两种取值方式
#: - ``'ec_a'``：外圈半径取 ``ec_a``（**原脚本的取值**，参考案例也这么用）。
#:   注意 ``d_ell`` 在椭圆内的实际范围是 ``0 → (ec_c + ec_a)``，所以取 ``ec_a`` 时
#:   **外侧约 63%（``ec_c/ec_a``）的孔全是 r2**，孔半径只在前 37% 单调渐变。
#: - ``'shift_plus_ec_a'``：取 ``ec_c + ec_a``，孔半径沿**整条**透镜单调渐变到底。
D_OUT_MODES = ('ec_a', 'shift_plus_ec_a')

#: 与原脚本一致的默认值
DFT_D_OUT_MODE = 'ec_a'


class LensGeometryError(ValueError):
    """透镜参数非法（几何上无解或显然写错）。"""


# ============================================================
# 参数
# ============================================================

@dataclass(frozen=True)
class GrinLensSpec:
    """
    GRIN 椭圆透镜的输入参数（**全部带单位，长度一律 mm**）。

    :param a: float, 晶格常数 a [mm]（与基板工程同一个 ``a``）
    :param ratio: float, 孔网格细化倍率 [无量纲]；格距 ``a2 = a / ratio``，
        抬高它 ⇒ 格距变小 ⇒ 孔数按 ``ratio²`` 增长（耗时也随孔数增长）
    :param nx: int, 椭圆长半轴 = ``nx`` 个格距，即 ``ec_a = nx · a2``
    :param ny: int, 椭圆短半轴 = ``ny`` 个格距（还要乘 ``sind(60°)``），
        即 ``ec_b = ny · a2 · sind(60)``
    :param r1_0: float, 内圈孔半径 [mm]（**未除 ratio 的基准值**，
        CST 参数表里登记的是 ``r1 = r1_0 / ratio``）
    :param r2_0: float, 外圈孔半径 [mm]（同上，``r2 = r2_0 / ratio``）
    :param r_big: float, 大六边形外接圆半径 [mm] = ``a·(3·n_small/4 + lx1)``；
        透镜近焦点要落在它的 0° 顶点上
    :param d_out_mode: str, ``d_out`` 取值方式，见 :data:`D_OUT_MODES`
    :param tol: float, 椭圆包络判据的容差（把刚压在边界上的孔也收进来）。
        原脚本用 1.03，参考实现用 1.1
    :param dxf_precision: int, DXF 坐标保留小数位 [位]（4 位 = 0.1 µm）
    """

    a: float
    ratio: float
    nx: int
    ny: int
    r1_0: float
    r2_0: float
    r_big: float
    d_out_mode: str = DFT_D_OUT_MODE
    tol: float = 1.03
    dxf_precision: int = 4

    # ---- 派生量（全部只读）----

    @property
    def hex_size(self) -> float:
        """孔网格的六边形半径 [mm]：``a / √3 / ratio``。"""
        return self.a / math.sqrt(3.0) / self.ratio

    @property
    def a2(self) -> float:
        """孔网格的晶格边长（格距）[mm]：``hex_size · √3``，等价于 ``a / ratio``。"""
        return self.hex_size * math.sqrt(3.0)

    @property
    def d0(self) -> float:
        """孔半径渐变区的起始椭圆半径 [mm]：``12 · a2``（= 原脚本的 ``6·hex·2·√3``）。"""
        return 6.0 * self.hex_size * 2.0 * math.sqrt(3.0)

    @property
    def r_in(self) -> float:
        """内圈孔半径 [mm]：``r1_0 / ratio``。"""
        return self.r1_0 / self.ratio

    @property
    def r_out(self) -> float:
        """外圈孔半径 [mm]：``r2_0 / ratio``。"""
        return self.r2_0 / self.ratio

    @property
    def r_pair(self) -> np.ndarray:
        """``np.array([r_in, r_out])``（线性插值的两个端点）。"""
        return np.array([self.r_in, self.r_out])

    @property
    def ec_a(self) -> float:
        """椭圆长半轴 [mm]：``nx · a2``。"""
        return self.nx * self.a2

    @property
    def ec_b(self) -> float:
        """椭圆短半轴 [mm]：``ny · a2 · sind(60)``。"""
        return self.ny * self.a2 * math.sin(math.radians(60.0))

    @property
    def ecc(self) -> float:
        """离心率 e [无量纲]：``√(ec_a² − ec_b²) / ec_a``（负根号下截断为 0）。"""
        return math.sqrt(max(self.ec_a ** 2 - self.ec_b ** 2, 0.0)) / self.ec_a

    @property
    def shift(self) -> float:
        """焦距 ``ec_c`` [mm]（椭圆中心相对近焦点的偏移）。"""
        return self.ecc * self.ec_a

    @property
    def d_out(self) -> float:
        """孔半径渐变归一化的「外圈半径」[mm]，由 :attr:`d_out_mode` 决定。"""
        if self.d_out_mode == 'ec_a':
            return self.ec_a
        if self.d_out_mode == 'shift_plus_ec_a':
            return self.shift + self.ec_a
        raise LensGeometryError(
            f"d_out_mode 必须是 {D_OUT_MODES} 之一，收到 {self.d_out_mode!r}")

    @property
    def col_min(self) -> int:
        """孔网格列号下限（按椭圆真实 x 范围取，**不能**用 ``-nx``）。"""
        return int(math.floor((self.shift - self.ec_a) / self.a2)) - 1

    @property
    def col_max(self) -> int:
        """孔网格列号上限。"""
        return int(math.ceil((self.shift + self.ec_a) / self.a2)) + 1

    @property
    def row_range(self) -> Tuple[int, int]:
        """孔网格行号范围 ``(-ny, ny)``（关于 y=0 对称）。"""
        return (-self.ny, self.ny)

    def validate(self) -> 'GrinLensSpec':
        """
        开工前的基本校验。

        :return: self
        :raises LensGeometryError: 参数在几何上无解或明显写错
        """
        if self.a <= 0:
            raise LensGeometryError(f"a 必须为正（收到 {self.a}）")
        if self.ratio <= 0:
            raise LensGeometryError(f"ratio 必须为正（收到 {self.ratio}）")
        if int(self.nx) <= 0 or int(self.ny) <= 0:
            raise LensGeometryError(f"nx / ny 必须为正整数（收到 {self.nx}/{self.ny}）")
        if self.r1_0 <= 0 or self.r2_0 <= 0:
            raise LensGeometryError(f"r1_0 / r2_0 必须为正（收到 {self.r1_0}/{self.r2_0}）")
        if self.r_out < self.r_in:
            raise LensGeometryError(
                f"外圈孔半径应不小于内圈：r_in={self.r_in} > r_out={self.r_out}；"
                "若确实要反向渐变（外圈更小），请显式改 r1_0 / r2_0 的顺序")
        if self.ec_b > self.ec_a:
            raise LensGeometryError(
                f"短半轴 ec_b={self.ec_b} 大于长半轴 ec_a={self.ec_a}；"
                f"请满足 ny·sind(60) ≤ nx（当前 nx={self.nx}, ny={self.ny}）")
        if self.r_big <= 0:
            raise LensGeometryError(f"r_big 必须为正（收到 {self.r_big}）")
        if self.d_out <= self.d0:
            raise LensGeometryError(
                f"渐变区间为空：d_out={self.d_out:.4f} ≤ d0={self.d0:.4f}；"
                "请抬高 nx / ny，或换 d_out_mode")
        return self

    @property
    def hole_overlap_ratio(self) -> float:
        """
        ``2·r_out / a2`` —— 相邻孔「直径 / 格距」之比，> 1 表示最外圈孔互相叠一点。

        ⚠️ **实测参考配置下这个值是 1.011**（``a=0.2425, ratio=8, Nx/Ny=38/34``），
        即最外圈孔**本来就轻微相叠**。所以它**不是**错误条件，只是随参数变化的观测量；
        真正决定「孔阵列是否可用」的是覆盖自查（``check_coverage``），不是这一条。
        """
        return 2.0 * self.r_out / self.a2

    def notes(self) -> List[str]:
        """
        参数的非阻断性提示（**不抛异常**，供日志/报告使用）。

        :return: list[str]
        """
        out = []
        ratio = self.hole_overlap_ratio
        if ratio > 1.0:
            out.append(
                f"最外圈孔轻微相叠：2·r_out/a2 = {ratio:.3f} > 1（参考配置为 1.011，属正常）；"
                f"若不想相叠请降低 r2_0 或抬高 ratio")
        if self.d_out_mode == 'ec_a':
            frac = (self.ec_b and (self.shift / self.ec_a)) or 0.0
            out.append(
                f"d_out_mode='ec_a'：d_ell 的实际范围是 0 → {self.shift + self.ec_a:.4f}，"
                f"而分母只到 {self.ec_a:.4f} ⇒ 外侧约 {frac * 100:.0f}% 的孔全是 r2，"
                f"孔半径只在前 {100 - frac * 100:.0f}% 单调渐变。"
                f"想要全长度渐变请用 d_out_mode='shift_plus_ec_a'")
        return out

    def with_overrides(self, **kwargs) -> 'GrinLensSpec':
        """返回一份替换了若干字段的新 spec（frozen dataclass 的便捷写法）。"""
        return replace(self, **kwargs)


def grin_lens_spec_from_cst_params(a, h=None, ratio=None, nx=None, ny=None,
                                   r1_0=None, r2_0=None, n_small=None, lx1=None,
                                   r_big=None, **kwargs) -> GrinLensSpec:
    """
    从「CST 参数表里那几个量」拼出 :class:`GrinLensSpec`。

    对应 `lens_build_standalone.py` 读 ``lens_params.json`` 的那几行：

    .. code-block:: python

        a = P['a']; lens_ratio = P['ratio']; lens_Nx, lens_Ny = P['Nx'], P['Ny']
        lens_r1_0, lens_r2_0 = P['r1_0'], P['r2_0']
        R_big = a * (3 * n_small / 4 + lx1)

    也接受**旧脚本/notebook 的变量名**（``lens_ratio`` / ``lens_Nx`` / ``lens_Ny`` /
    ``lens_r1_0`` / ``lens_r2_0`` / ``nsm``），免得调用方还要自己改名。

    :param a: float, 晶格常数 [mm]
    :param h: float 可选, 硅片厚度 [mm]（几何不需要，收下只为签名完整）
    :param ratio: float, 孔网格细化倍率（别名 ``lens_ratio``）
    :param nx: int, 椭圆长半轴格数（别名 ``lens_Nx``）
    :param ny: int, 椭圆短半轴格数（别名 ``lens_Ny``）
    :param r1_0: float, 内圈孔半径基准 [mm]（别名 ``lens_r1_0``）
    :param r2_0: float, 外圈孔半径基准 [mm]（别名 ``lens_r2_0``）
    :param n_small: int, 六边形环数（别名 ``nsm``），用于推 ``r_big``
    :param lx1: float, 大六边形额外边长系数，用于推 ``r_big``
    :param r_big: float 可选, 直接给大六边形半径；不给则按 ``a·(3·n_small/4 + lx1)`` 算
    :param kwargs: 透传给 :class:`GrinLensSpec` 的其余字段（``d_out_mode`` / ``tol`` …）
    :return: GrinLensSpec
    :raises LensGeometryError: 关键参数缺失、别名冲突或 r_big 推不出来
    """
    aliases = {'lens_ratio': 'ratio', 'lens_Nx': 'nx', 'lens_Ny': 'ny',
               'lens_r1_0': 'r1_0', 'lens_r2_0': 'r2_0', 'nsm': 'n_small'}
    # 旧脚本里大六边形半径叫 R_big（大写），本模块按 PEP8 叫 r_big
    if 'R_big' in kwargs:
        cap = kwargs.pop('R_big')
        if cap is not None:
            if r_big is not None and r_big != cap:
                raise LensGeometryError(
                    f"别名冲突：r_big={r_big!r} 与 R_big={cap!r} 同时给出且不一致")
            r_big = cap
    given = {'ratio': ratio, 'nx': nx, 'ny': ny, 'r1_0': r1_0, 'r2_0': r2_0,
             'n_small': n_small}
    for old, new in aliases.items():
        if old not in kwargs:
            continue
        val = kwargs.pop(old)
        if val is None:
            continue
        if given.get(new) is not None and given[new] != val:
            raise LensGeometryError(
                f"别名冲突：{new}={given[new]!r} 与 {old}={val!r} 同时给出且不一致")
        given[new] = val
    if kwargs:
        raise LensGeometryError(f"收到未知参数：{sorted(kwargs)}")

    ratio, nx, ny = given['ratio'], given['nx'], given['ny']
    r1_0, r2_0, n_small = given['r1_0'], given['r2_0'], given['n_small']

    missing = [n for n, v in (('ratio', ratio), ('nx', nx), ('ny', ny),
                              ('r1_0', r1_0), ('r2_0', r2_0)) if v is None]
    if missing:
        raise LensGeometryError(f"缺少参数：{missing}")
    if r_big is None:
        if n_small is None or lx1 is None:
            raise LensGeometryError(
                "r_big 未给出时必须同时给出 n_small 与 lx1（R_big = a·(3·n_small/4 + lx1)）")
        r_big = a * (3.0 * n_small / 4.0 + lx1)
    return GrinLensSpec(a=a, ratio=ratio, nx=int(nx), ny=int(ny),
                        r1_0=r1_0, r2_0=r2_0, r_big=r_big).validate()


# ============================================================
# 孔阵列
# ============================================================

@dataclass
class GrinLensHoles:
    """
    孔阵列的计算结果（纯数据，可反复自查 / 导出 / 画图）。

    - ``grid_x / grid_y``：整个孔网格的孔心（未筛椭圆）
    - ``x / y``：落在椭圆包络内的孔心
    - ``radius``：每个孔对应的半径（沿椭圆等高线 r1→r2 线性渐变）

    另有两个只看不动的便利量：``upper_mask``（``y ≥ 0``）与 ``n_upper``。
    """

    spec: GrinLensSpec
    grid_x: np.ndarray
    grid_y: np.ndarray
    x: np.ndarray
    y: np.ndarray
    radius: np.ndarray
    _poly_cache: dict = field(default_factory=dict, repr=False, compare=False)

    # ---- 规模 ----
    def __len__(self) -> int:
        """椭圆内的孔数（**完整**阵列，含下半）。"""
        return int(self.x.size)

    @property
    def n_grid(self) -> int:
        """孔网格的孔心总数（未筛椭圆）。"""
        return int(self.grid_x.size)

    @property
    def upper_mask(self) -> np.ndarray:
        """``y ≥ 0`` 的布尔掩码（DXF 只写这一半）。"""
        return self.y >= 0

    @property
    def n_upper(self) -> int:
        """上半平面的孔数（= DXF 里写进去的多段线数）。"""
        return int(self.upper_mask.sum())

    # ---- 多边形 ----
    def polygons(self, upper_only: bool = False) -> list:
        """
        六边形孔多边形（shapely Polygon）。

        :param upper_only: True 只返回 ``y ≥ 0`` 的那一半（DXF 用）；False 返回完整阵列
        :return: list[shapely.geometry.Polygon]
        """
        key = 'upper' if upper_only else 'full'
        if key not in self._poly_cache:
            _, create_hex_polygon, _ = _hex_grid_api()
            mask = self.upper_mask if upper_only else np.ones(self.x.size, bool)
            self._poly_cache[key] = [
                create_hex_polygon(center=(float(px), float(py)), cell_width=float(r))
                for px, py, r in zip(self.x[mask], self.y[mask], self.radius[mask])]
        return self._poly_cache[key]

    # ---- 导出 ----
    def export_dxf(self, dxf_path, layer_name: str = 'gridlens',
                   upper_only: bool = True) -> str:
        """
        导出孔阵列 DXF（CST 的 ``DXF`` 导入消费它）。

        :param dxf_path: str, 输出路径
        :param layer_name: str, DXF 图层名（CST 侧用 ``component`` 与之对应）
        :param upper_only: bool, 只写 ``y ≥ 0`` 的一半（**默认，且与 CST 的镜像步骤配对**）
        :return: str, 写出的绝对路径
        """
        dxf_path = os.path.abspath(dxf_path)
        _, _, save_to_dxf = _hex_grid_api()
        save_to_dxf(self.polygons(upper_only=upper_only), dxf_path,
                    layer_name=layer_name, precision=self.spec.dxf_precision)
        return dxf_path

    # ---- 预览 ----
    def preview(self, ax=None, show_ellipse: bool = True,
                show_foci: bool = True, annotate: bool = True):
        """
        画几何预览（孔按半径着色 + 椭圆包络 + 两个焦点）。

        **不调用 ``plt.show()``** —— 库函数不该阻塞调用方。

        :param ax: matplotlib Axes 可选, 不传则新建
        :param show_ellipse: bool, 是否画椭圆包络
        :param show_foci: bool, 是否标注近焦点 / 远焦点
        :param annotate: bool, 是否写标题与 ``2·ec_c`` 标注
        :return: tuple, (fig, ax)
        """
        import matplotlib.pyplot as plt
        from matplotlib.collections import PolyCollection
        from matplotlib.patches import Ellipse as MplEllipse

        spec = self.spec
        if ax is None:
            fig, ax = plt.subplots(figsize=(9.0, 7.2))
        else:
            fig = ax.figure

        coll = PolyCollection([_poly_xy(p) for p in self.polygons()],
                              array=self.radius * 1e3, cmap='rainbow',
                              edgecolors='none')
        ax.add_collection(coll)
        fig.colorbar(coll, ax=ax, shrink=0.8, pad=0.02, label='孔半径 [µm]')

        if show_ellipse:
            ax.add_patch(MplEllipse((spec.shift, 0), 2 * spec.ec_a, 2 * spec.ec_b,
                                    fill=False, ec='r', lw=2.0, label='椭圆包络'))
        if show_foci:
            ax.plot([0], [0], marker='*', ms=16, color='k',
                    label=f'近焦点（= 大六边形顶点 ρ={spec.r_big:.3f} mm）')
            ax.plot([2 * spec.shift], [0], marker='+', ms=12, mew=2, color='b',
                    label='远焦点')
            ax.plot([spec.shift], [0], marker='.', ms=10, color='r')
        if annotate:
            ax.annotate('椭圆中心', (spec.shift, 0), textcoords='offset points',
                        xytext=(6, -15), fontsize=9)
            ax.annotate('', xy=(0, -0.55 * spec.ec_b),
                        xytext=(2 * spec.shift, -0.55 * spec.ec_b),
                        arrowprops=dict(arrowstyle='<->', color='0.3', lw=1.0))
            ax.text(spec.shift, -0.62 * spec.ec_b,
                    f'2·ec_c = {2 * spec.shift:.3f} mm',
                    ha='center', va='top', fontsize=9, color='0.3')
            ax.set_title(f'GRIN 椭圆透镜：{spec.ec_a:.3f} × {spec.ec_b:.3f} mm，'
                         f'e = {spec.ecc:.3f}，{len(self)} 个孔（DXF {self.n_upper} 个）',
                         fontsize=10)

        pad_x, pad_y = 0.04 * spec.ec_a, 0.06 * spec.ec_b
        ax.set_aspect('equal')
        ax.set_xlim(min(spec.shift - spec.ec_a, float(self.x.min())) - pad_x,
                    max(spec.shift + spec.ec_a, float(self.x.max())) + pad_x)
        ax.set_ylim(min(-spec.ec_b, float(self.y.min())) - pad_y,
                    max(spec.ec_b, float(self.y.max())) + pad_y)
        ax.set_xlabel('x [mm]  （0 = 顶点/近焦点，+x 朝外）')
        ax.set_ylabel('y [mm]')
        ax.grid(alpha=0.25)
        ax.legend(loc='upper left', fontsize=8)
        if ax is not None:
            fig.tight_layout()
        return fig, ax

    # ---- 三道自查（全部与 CST 无关）----

    def check_cut_overlap(self, tol_area: float = 1e-3,
                          cut_len_factor: float = 2.2, n_pts: int = 2001) -> dict:
        """
        自查 ①：按「顶点内角 120° 的楔形」裁剪后，透镜与大六边形**不相交**。

        在**全局系**里等价地算一遍（椭圆与楔形都平移到顶点 ``r_big`` 处）再求交 ——
        与 CST 里在局部系做 ``subtract`` 的结果应当一致。

        :param tol_area: float, 允许的残余重叠面积 [mm²]，默认 1e-3
        :param cut_len_factor: float, 楔形边长 = ``factor · r_big``（原脚本取 2.2，与 CST 的 ``Ls`` 一致）
        :param n_pts: int, 椭圆离散点数
        :return: dict, ``{'ok', 'name', 'overlap_area', 'tol_area', 'detail'}``
        """
        from shapely.geometry import Polygon as ShpPoly

        spec = self.spec
        th = np.linspace(0.0, 2 * np.pi, n_pts)
        ell = ShpPoly(np.column_stack([
            spec.r_big + spec.shift + spec.ec_a * np.cos(th),
            spec.ec_b * np.sin(th)]))
        ang = np.deg2rad([120.0, 240.0])
        cut_len = cut_len_factor * spec.r_big
        wedge = ShpPoly([(spec.r_big, 0.0),
                         (spec.r_big + cut_len * np.cos(ang[0]), cut_len * np.sin(ang[0])),
                         (spec.r_big + cut_len * np.cos(ang[1]), cut_len * np.sin(ang[1]))])
        overlap = ell.difference(wedge).intersection(ShpPoly(_hex_pts(spec.r_big, 0.0))).area
        return {'ok': bool(overlap < tol_area), 'name': '裁剪不重叠',
                'overlap_area': float(overlap), 'tol_area': float(tol_area),
                'detail': (f'楔形裁剪后与大六边形的重叠面积 = {overlap:.8f} mm²' if overlap < tol_area
                           else f'仍有重叠 {overlap:.8f} mm² —— 检查裁剪角（应为 120°/240°）')}

    def check_coverage(self, step: float = 0.02, tol_ratio: float = 1.05) -> dict:
        """
        自查 ②：孔阵列**遍布整个椭圆**（无成片实心区）。

        判据：透镜区域内任一点到**最近孔心**的最远距离 ``d_max``。
        完好的三角格子（格距 ``a2``）里最坏的点是三角形重心，距离 = ``a2/√3``；
        ``d_max`` 明显超过它 ⇒ 必然存在「孔铺不到」的成片实心区。

        :param step: float, 采样步长 [mm]
        :param tol_ratio: float, 允许 ``d_max`` 不超过理论值的多少倍，默认 1.05
        :return: dict, 含 ``d_max`` / ``d_theory`` / ``ratio`` / 最远点坐标
        """
        spec = self.spec
        gx = np.arange(spec.shift - spec.ec_a - step, spec.shift + spec.ec_a + step, step)
        gy = np.arange(-spec.ec_b - step, spec.ec_b + step, step)
        gx2, gy2 = np.meshgrid(gx, gy)
        # 必须取模 2π，否则下半楔形会被误判成透镜
        ang2 = np.mod(np.arctan2(gy2, gx2), 2 * np.pi)
        inside = (((gx2 - spec.shift) ** 2 / spec.ec_a ** 2 + gy2 ** 2 / spec.ec_b ** 2) <= 1.0) \
            & ~((ang2 >= np.deg2rad(120.0)) & (ang2 <= np.deg2rad(240.0)))
        px, py = gx2[inside], gy2[inside]

        try:
            from scipy.spatial import cKDTree
            dmin = cKDTree(np.column_stack([self.x, self.y])).query(
                np.column_stack([px, py]), k=1, workers=-1)[0]
        except ImportError:                       # 退回分块 numpy
            dmin = np.full(px.size, np.inf)
            for i in range(0, self.x.size, 64):
                bx, by = self.x[i:i + 64], self.y[i:i + 64]
                dmin = np.minimum(dmin, np.sqrt((px[:, None] - bx) ** 2
                                                + (py[:, None] - by) ** 2).min(axis=1))
        dmax = float(dmin.max())
        d_theory = spec.a2 / math.sqrt(3.0)
        worst = int(dmin.argmax())
        return {'ok': bool(dmax <= tol_ratio * d_theory), 'name': '孔阵覆盖',
                'd_max': dmax, 'd_theory': float(d_theory),
                'ratio': float(dmax / d_theory), 'tol_ratio': float(tol_ratio),
                'n_samples': int(px.size),
                'worst_point': (float(px[worst]), float(py[worst])),
                'detail': (f'透镜内 {px.size} 个采样点到最近孔心的最远距离 = {dmax:.4f} mm，'
                           f'理论值 a2/√3 = {d_theory:.4f} mm（{dmax / d_theory:.2f}×）')}

    def check_mirror_equivalence(self, tol_area: float = 1e-6) -> dict:
        """
        自查 ③：**上半 ∪ y 镜像(上半) == 完整孔阵列**（保证 DXF 只写一半不漏孔）。

        :param tol_area: float, 允许的对称差面积 [mm²]，默认 1e-6
        :return: dict, 含 ``diff_area`` 与两侧孔数
        """
        from shapely.affinity import scale as shp_scale
        from shapely.ops import unary_union

        half = unary_union(self.polygons(upper_only=True))
        rebuilt = unary_union([half, shp_scale(half, yfact=-1, origin=(0, 0))])
        full = unary_union(self.polygons(upper_only=False))
        diff = float(rebuilt.symmetric_difference(full).area)
        return {'ok': bool(diff < tol_area), 'name': '镜像等价',
                'diff_area': diff, 'tol_area': float(tol_area),
                'n_upper': self.n_upper, 'n_full': len(self),
                'detail': (f'上半 {self.n_upper} 个 ∪ y镜像 vs 完整 {len(self)} 个，'
                           f'差异面积 = {diff:.3e} mm²')}

    def run_self_checks(self, **kwargs) -> dict:
        """
        一次跑完三道自查。

        :param kwargs: 分别透传（``cut_overlap`` / ``coverage`` / ``mirror`` 各一个 dict）
        :return: dict, ``{'all_ok': bool, 'checks': [check1, check2, check3], 'summary': str}``
        """
        checks = [
            self.check_cut_overlap(**kwargs.get('cut_overlap', {})),
            self.check_coverage(**kwargs.get('coverage', {})),
            self.check_mirror_equivalence(**kwargs.get('mirror', {})),
        ]
        return {'all_ok': all(c['ok'] for c in checks), 'checks': checks,
                'summary': '；'.join(f"[{'OK' if c['ok'] else 'x'}] {c['detail']}"
                                    for c in checks)}

    def describe(self) -> str:
        """一段可复制的几何摘要（日志/报告用，不含 CST）。"""
        spec = self.spec
        return (
            f"GRIN 透镜 : 椭圆半轴 {spec.ec_a:.4f} × {spec.ec_b:.4f} mm，"
            f"离心率 {spec.ecc:.4f}，焦距 ec_c = {spec.shift:.4f} mm，"
            f"孔半径 {spec.r_in * 1e3:.2f} → {spec.r_out * 1e3:.2f} um\n"
            f"            近焦点 rho = {spec.r_big:.4f} mm（= 顶点），"
            f"椭圆中心 rho = {spec.r_big + spec.shift:.4f} mm，"
            f"远焦点 rho = {spec.r_big + 2 * spec.shift:.4f} mm\n"
            f"孔网格    : 列 {spec.col_min} ~ {spec.col_max}（格距 {spec.a2:.4f} mm）=> "
            f"x ∈ [{(spec.col_min - 0.5) * spec.a2:+.3f}, "
            f"{(spec.col_max + 0.5) * spec.a2:+.3f}] mm，"
            f"必须覆盖椭圆 x ∈ [{spec.shift - spec.ec_a:+.4f}, "
            f"{spec.shift + spec.ec_a:+.4f}] mm")


# ============================================================
# 纯几何小工具
# ============================================================

def _hex_pts(r: float, ang0: float) -> np.ndarray:
    """正六边形顶点（CCW），顶点首角 = ``ang0`` 度。"""
    ang = np.deg2rad(ang0 + 60.0 * np.arange(6))
    return np.column_stack([r * np.cos(ang), r * np.sin(ang)])


def _poly_xy(poly) -> np.ndarray:
    """把 ``create_hex_polygon`` 的返回值取成 ``(N,2)`` 顶点数组。"""
    if hasattr(poly, 'exterior'):            # shapely Polygon
        return np.asarray(poly.exterior.coords, float)
    if hasattr(poly, 'vertices'):            # matplotlib Polygon
        return np.asarray(poly.vertices, float)
    return np.asarray(poly, float)


def _hole_grid(spec: GrinLensSpec) -> Tuple[np.ndarray, np.ndarray]:
    """
    用 ``HexGridVisualizer`` 生成孔网格的孔心（点型六边形 + offset_q 编号）。

    注意：``HexGridVisualizer.__init__`` 会自建一张 14×12 的空画布，
    这里**只用它的 hex_lib**、用完立刻关掉，否则调用方会莫名多出一张空白图。
    """
    import matplotlib.pyplot as plt

    HexGridVisualizer, _, _ = _hex_grid_api()
    vis = HexGridVisualizer(hex_size=spec.hex_size, orientation='pointy',
                            origin=(0, 0))
    try:
        vis.set_grid(vis.hex_lib.create_staggered_grid(
            (spec.col_min, spec.col_max), spec.row_range))
        vis.set_coord_type('offset_q')
        xs, ys = vis.hex_lib.hexes_to_pixels(vis.grid_hexes)
    finally:
        plt.close(vis.fig)
    return np.asarray(xs, float), np.asarray(ys, float)


def build_grin_lens_holes(spec: GrinLensSpec) -> GrinLensHoles:
    """
    **纯几何**：算出 GRIN 透镜的孔阵列（不依赖 CST）。

    步骤（与原脚本 9b-① 一一对应）：

    1. 按 ``HexGridVisualizer`` 生成点型六边形孔网格的孔心；
    2. 用**椭圆包络**筛出透镜内的孔心 —— 判据是「到两焦点距离之和 ≤ 2·ec_a·tol」，
       ``tol > 1`` 把刚压在边界上的孔也收进来，否则椭圆最扁的两头会留下没孔的实心边；
    3. 孔半径沿等高线 ``d = √(x² + y²/(1−e²))`` 由 ``r1`` 到 ``r2`` 线性渐变。

    :param spec: GrinLensSpec
    :return: GrinLensHoles
    """
    spec.validate()

    gx, gy = _hole_grid(spec)

    # 椭圆包络：焦点在原点与 (2·ec_c, 0)
    d1 = np.sqrt(gx ** 2 + gy ** 2)
    d2 = np.sqrt((gx - 2 * spec.shift) ** 2 + gy ** 2)
    inside = (d1 + d2) <= 2 * spec.ec_a * spec.tol
    xp, yp = gx[inside], gy[inside]

    # 孔半径沿椭圆等高线渐变
    d_ell = np.sqrt(xp ** 2 + yp ** 2 / (1 - spec.ecc ** 2 + 1e-10))
    t = np.clip((d_ell - spec.d0) / (spec.d_out - spec.d0 + 1e-10), 0.0, 1.0)
    ri = spec.r_in + (spec.r_out - spec.r_in) * t

    return GrinLensHoles(spec=spec, grid_x=gx, grid_y=gy, x=xp, y=yp, radius=ri)


# ============================================================
# CST 建模步骤
# ============================================================

def build_grin_lens(app, holes: GrinLensHoles, spec: Optional[GrinLensSpec] = None,
                    name: str = 'lens_epc', holes_name: str = 'import_1',
                    cut_name: str = 'lens_hex_cut', component: str = 'gridlens',
                    material: str = 'Silicon (lossy)', height: str = 'h',
                    dxf_path: Optional[str] = None, dxf_layer: str = 'gridlens',
                    unite_mirror: bool = True, rotation_repetition: int = 5,
                    rotation_axis=None, log=None) -> dict:
    """
    把孔阵列与椭圆包络做成 CST 里的 GRIN 透镜（**只下发 VBA，不做几何计算**）。

    步骤顺序与原脚本 9b-② 完全一致：

    1. ``dxf_import`` 导入孔阵列（DXF 里**只有 y ≥ 0 的一半**）；
    2. 一次 **y 镜像复制** 补齐下半（``copy=True``；``unite`` 默认 True，
       ``y=0`` 那一行自己镜像自己不会冲突）；
    3. 登记椭圆相关的 CST 参数，**全部由 ``a`` 与格距推出、不写死数值**：
       ``ratio / Nx / Ny / a2 / d0 / r1 / r2 / ec_a / ec_b / ec_c``；
    4. ``ellipse`` + ``extrude`` 出椭圆包络，再 ``subtract`` 掉孔阵列 = GRIN 透镜；
    5. ``polyline`` + ``extrude`` 出「顶点内角 120° 的楔形」，``subtract`` 掉与
       大六边形重叠的那一块（重叠的不要、不重叠的全留，所以**不能**用「切掉内半边」）；
    6. ``translate`` 到 0° 顶点（此时局部原点就是近焦点），z 先居中与板共面；
    7. ``rotation`` 旋转复制 ⇒ 6 个顶点各 1 个透镜。

    ⚠️ **耗时坑（实测，原脚本注释里有记录）**：

    - DXF 导入是 ``.AsCurves "False"`` ⇒ **每条多段线建一个实体**，耗时随多段线数
      **超线性**增长（实测 2215 条 = 183.9 s）。想更快只有**减少孔数**（抬高 ``ratio``）；
      ``dxf_precision`` 不是瓶颈。
    - ``rotation`` **必须 ``unite=False``**（本函数默认如此）：``unite=True`` 时
      CST 要把 6×(4351 个壳) 并成 1 个实体，实测 19 min 都跑不完；6 个互不接触的
      独立实体对网格/求解完全等价。

    :param app: cst_solver.setup 实例
    :param holes: GrinLensHoles（来自 :func:`build_grin_lens_holes`）
    :param spec: GrinLensSpec 可选, 不给则用 ``holes.spec``
    :param name: str, 椭圆包络（= 透镜本体）的实体名
    :param holes_name: str, DXF 导入产生的实体名（CST 的 ``Id "1"`` ⇒ ``import_1``）
    :param cut_name: str, 楔形裁剪体的名称
    :param component: str, 孔阵列归属组件（= DXF 图层名）
    :param material: str, 椭圆包络与楔形的材料
    :param height: str, 厚度参数名（CST 表达式）
    :param dxf_path: str 可选, 直接用这个 DXF；不给则由 ``holes`` 现导一份
    :param dxf_layer: str, 现导 DXF 时的图层名
    :param unite_mirror: bool, y 镜像复制时是否合并成一个实体（默认 True）
    :param rotation_repetition: int, 旋转复制的次数（5 ⇒ 连本体共 6 个）
    :param rotation_axis: list 可选, 旋转轴 ``[x, y, z]``，默认 ``[0, 0, 60]``
    :param log: callable 可选, ``log(tag)`` —— 每步之后读一次 ``get_messages()`` 做验收
    :return: dict，含各实体名、DXF 路径与几何参数
    :raises FileNotFoundError: DXF 不存在
    :raises ValueError: app 为 None
    """
    if app is None:
        raise ValueError("build_grin_lens 需要 cst_solver.setup 实例（app 为 None）")
    spec = spec or holes.spec
    if rotation_axis is None:
        rotation_axis = [0, 0, 60]
    if log is None:
        log = lambda tag='': None                       # noqa: E731

    if dxf_path is None:
        raise ValueError(
            "build_grin_lens 需要 dxf_path —— 请先调用 "
            "holes.export_dxf('xxx.dxf') 把孔阵列落到磁盘（DXF 只写 y≥0 的一半）")
    dxf_path = os.path.abspath(dxf_path)
    if not os.path.exists(dxf_path):
        raise FileNotFoundError(f"缺少透镜 DXF：{dxf_path}")

    # ① DXF 导入（孔阵列，DXF 里只有 y≥0 的一半）
    app.dxf_import(dxf_path, add='True', component=component, height=height)
    log('DXF 导入（孔阵列：DXF 里只有 y≥0 的一半）')

    # ①' 一次 y 镜像复制补齐下半（关于 y=0 平面镜像）
    app.mirror(holes_name, [0, 0, 0], [0, 1, 0], component=component,
               copy=True, unite=unite_mirror)
    log('孔阵列 y 镜像复制（补齐下半）')

    # ② 登记椭圆相关的 CST 参数（全部由 a 与格距推出，无硬编码数值）
    app.para('ratio', spec.ratio, expression='透镜孔网格细化倍率：格距 a2 = a/ratio')
    app.para('Nx', spec.nx, expression='椭圆长半轴 = Nx 个格距')
    app.para('Ny', spec.ny, expression='椭圆短半轴 = Ny 个格距')
    app.para('a2', 'a/ratio', expression='孔网格格距（= hexlib 的 HEX_SIZE*sqr(3)）')
    app.para('d0', '12*a2', expression='孔半径渐变区起始的椭圆半径')
    app.para('r1', f'{spec.r1_0}/ratio', expression='孔半径（内圈）[mm] = r1_0/ratio')
    app.para('r2', f'{spec.r2_0}/ratio', expression='孔半径（外圈）[mm] = r2_0/ratio')
    app.para('ec_a', 'Nx*a2', expression='★ 椭圆长半轴（沿臂方向）')
    app.para('ec_b', 'Ny*a2*sind(60)', expression='★ 椭圆短半轴（横向）')
    app.para('ec_c', 'sqr(ec_a^2-ec_b^2)',
             expression='★ 焦距：椭圆中心在 (ec_c, 0)，近焦点在原点')

    # 椭圆包络拉伸 → 减去孔阵列 = GRIN 透镜（长短轴/中心一律用 CST 变量）
    app.ellipse('ec_a', 'ec_b', ['ec_c', '0'], name)
    app.extrude(f'curve1:{name}', name, height, material=material, log_flag=1)
    log('椭圆包络拉伸（ec_a / ec_b / ec_c）')
    app.subtract(name, holes_name, component2=component)
    log('椭圆包络 − 孔阵列')

    # ③ 剪掉与大六边形重叠的部分（顶点内角 120° ⇒ 内部是 120°→240° 的楔形）
    cut_pts = [[0, 0],
               ['Ls*cosd(120)', 'Ls*sind(120)'],
               ['Ls*cosd(240)', 'Ls*sind(240)'],
               [0, 0]]                                   # 逆时针 ⇒ 沿 +z 拉伸
    app.polyline(cut_pts, name=cut_name)
    app.extrude(f'curve1:{cut_name}', cut_name, height,
                material=material, log_flag=1)
    log('六边形内部楔形（裁剪体）')
    app.subtract(name, cut_name)
    log('剪掉与正六边形重叠的部分')

    # ④ 移到 0° 顶点（此时局部原点就是近焦点）
    app.translate(name, ['0', '0', f'-{height}/2'], copy=False, unite=False, log_flag=1)
    app.translate(name, ['Rbig', '0', '0'], copy=False, unite=False, log_flag=1)
    log('透镜移到 0° 顶点（近焦点在顶点）')

    # ⑤ 旋转复制 ⇒ 6 个顶点各 1 个（unite=False，理由见 docstring）
    app.rotation(name, rotation_axis, repetition=rotation_repetition,
                 copy=True, unite=False)
    log('透镜 旋转复制 ×6（unite=False）')

    return {'name': name, 'holes_name': holes_name, 'cut_name': cut_name,
            'component': component, 'dxf_path': dxf_path,
            'n_holes_total': len(holes), 'n_holes_dxf': holes.n_upper,
            'ec_a': spec.ec_a, 'ec_b': spec.ec_b, 'ec_c': spec.shift,
            'r1': spec.r_in, 'r2': spec.r_out, 'r_big': spec.r_big}
