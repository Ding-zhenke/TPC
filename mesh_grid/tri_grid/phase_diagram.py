# -*- coding: utf-8 -*-
r"""
相区结构示意图（建模前必出）
============================

用途：在**动手建 CST 模型之前**，把器件的两种晶相（A/B）、区域大小与边界
一次性画清楚，供人眼核对「相有没有画反、区域够不够大、域壁在不在、端口对不对」。

与库里旧的 :meth:`TopoPath.preview` 的本质区别：

* 旧 preview 只画路径线 + 晶格背景，**不着色、不按真实孔大小**，无法确认拓扑；
* 本模块按 **crystal builder 完全相同的超元胞 + 阵列规则**数值生成每个三角孔的
  中心与边长，再按「孔中心落在路径哪一侧相区」绑定相颜色，因此图上看到的
  相分布 = CST 里实际建出来的相分布（AB/BA 都由 ``topology`` 如实驱动，绝不硬编码）。

相绑定口径（与 :func:`topo_modeler.builders.build_topological_crystal` 一致）：

* 路径**下半区** = 晶体 A，路径**上半区** = 晶体 B（``vpc_A`` / ``vpc_B``）；
* ``topology='AB'``：A 内**朝上小孔 / 朝下大孔**，B 相反；
* ``topology='BA'``：A 内**朝上大孔 / 朝下小孔**，B 相反。

函数入口：:func:`plot_phase_structure`。
"""

from typing import Optional, Sequence, Tuple

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

from mesh_grid.plotting import configure_chinese_font
from mesh_grid.tri_grid.core import (
    equilateral_triangle_vertices,
    point_in_polygon,
)

__all__ = ['generate_crystal_holes', 'plot_phase_structure']


# 超元胞在「未做任何阵列复制」时的 6 个孔中心基准（旋转 120° 生成，见 crystal.py）。
#   朝上 3 个 + 朝下 3 个；单位 = a。
# 这与 build_topological_crystal 里 center_up/center_dn 旋转 120°×2 的结果逐点相同。
def _supercell_base_centers(a):
    """返回超元胞 6 个孔的基准中心（``(centers, is_up)``），未做阵列复制。

    :param a: float, 晶格常数
    :return: tuple[np.ndarray, np.ndarray]，
        ``centers`` 形状 (6,2)；``is_up`` 形状 (6,) 的 bool（True=朝上孔）
    """
    sq3 = np.sqrt(3)
    center_up = np.array([-a / 2, sq3 / 2 * a - a / sq3])
    center_dn = np.array([0.0, a / sq3])

    def rot120(p):
        c, s = -0.5, sq3 / 2
        return np.array([c * p[0] - s * p[1], s * p[0] + c * p[1]])

    up_centers = []
    p = center_up
    for _ in range(3):
        up_centers.append(p)
        p = rot120(p)
    dn_centers = []
    p = center_dn
    for _ in range(3):
        dn_centers.append(p)
        p = rot120(p)
    centers = np.array(up_centers + dn_centers, dtype=float)
    is_up = np.array([True] * 3 + [False] * 3)
    return centers, is_up


def generate_crystal_holes(path, topology='AB', a=None,
                           large_size=None, small_size=None,
                           xup=None, yup=None, ydn=None, y_step='e2'):
    """按 crystal builder 的阵列规则数值生成**整块晶体阵列**的全部三角孔。

    生成过程与 :func:`topo_modeler.builders.build_topological_crystal` 一一对应：
    超元胞（6 孔）先沿 x 以步长 ``a`` 复制 ``xup`` 次，再沿 ±y 以步长
    ``2·y_step`` 各复制 ``yup/ydn`` 次（此处直接数值展开，不引用 CST 参数）。

    返回的每个孔都带有**真实边长**与朝向，但**尚未判定属于 A 还是 B 相**
    （相归属由孔中心相对路径的位置决定，见 :func:`plot_phase_structure`）。

    :param path: TopoPath, 已数值化的路径（``build()`` 时可无参，默认 a）
    :param topology: str, ``'AB'`` / ``'BA'``
    :param a: float/None, 晶格常数；None 时用 ``path.a``
    :param large_size: float/None, 大孔边长；None 时取 ``0.65·a``
    :param small_size: float/None, 小孔边长；None 时取 ``0.35·a``
    :param xup: int/None, x 方向阵列复制次数（**不含**原始超元胞）；
        None 时用 ``path.get_array_range()``
    :param yup: int/None, y+ 方向复制次数（crystal builder 里实际次数为 ``int(yup/2)``）
    :param ydn: int/None, y− 方向复制次数
    :param y_step: str/float, y 阵列步长基准；默认 ``'e2'`` ⇒ 步长 ``2·(√3/2·a)``
    :return: dict，键：
        ``centers`` (M,2) 孔中心；``is_up`` (M,) 朝向；
        ``sizes`` (M,) 边长（**注意：此处的 size 已含 AB/BA 的相内分配，但还没区分
        该孔落在 A 还是 B**——故调用方仍需按位置二次确认）
    """
    if topology not in ('AB', 'BA'):
        raise ValueError(f"topology 必须是 'AB' 或 'BA'，收到 '{topology}'")
    a = float(path.a if a is None else a)
    if large_size is None:
        large_size = 0.65 * a
    if small_size is None:
        small_size = 0.35 * a
    if y_step == 'e2':
        dy = 2.0 * (np.sqrt(3) / 2.0 * a)
    else:
        dy = float(y_step)

    auto_xup, auto_yup, auto_ydn = path.get_array_range()
    xup = int(auto_xup if xup is None else xup)
    yup = int(auto_yup if yup is None else yup)
    ydn = int(auto_ydn if ydn is None else ydn)
    # crystal builder 的 y 复制次数是 int(yup/2) / int(ydn/2)
    iy_up = int(yup / 2)
    iy_dn = int(ydn / 2)

    base, is_up_base = _supercell_base_centers(a)

    offsets = []
    for ix in range(xup + 1):
        for iy in range(-iy_dn, iy_up + 1):
            offsets.append((ix * a, iy * dy))

    centers = np.concatenate([base + off for off in offsets], axis=0)
    is_up = np.tile(is_up_base, len(offsets))

    # 超元胞内部的「基准大小」：与 crystal.py 的 hole_sizes + tick 索引一致。
    # 基准 6 孔里，前 3 个朝上、后 3 个朝下，且它们在 crystal builder 中分别由
    # A/B 两次 translate 生成。为避免在这里预设相归属，这里只按**朝向**给出
    # AB/BA 下「晶体 A」的尺寸，真正属于 A 还是 B 交给位置判定。
    if topology == 'AB':
        size_up_a, size_dn_a = small_size, large_size
    else:
        size_up_a, size_dn_a = large_size, small_size
    base_sizes = np.where(is_up_base, size_up_a, size_dn_a)
    sizes = np.tile(base_sizes, len(offsets))

    return {'centers': centers, 'is_up': is_up, 'sizes': sizes,
            'a': a, 'large_size': float(large_size),
            'small_size': float(small_size)}


def _resolve_hole_phase_and_size(holes, polys_a, polys_b, topology):
    """按孔中心落在 A / B 相区，判定每个孔的相归属与**真实边长**。

    落在相区之外（未被晶体覆盖）的孔标记为 ``phase=0``，不画。

    :return: tuple[np.ndarray, np.ndarray]，``(phase, sizes)``；
        phase: +1=A（下半）, -1=B（上半）, 0=区外
    """
    centers = holes['centers']
    is_up = holes['is_up']
    a = holes['a']
    large_size, small_size = holes['large_size'], holes['small_size']

    def in_any(point, polys):
        return any(point_in_polygon((float(point[0]), float(point[1])), poly)
                   for poly in polys)

    phase = np.zeros(len(centers), dtype=int)
    sizes = np.zeros(len(centers), dtype=float)
    for i, center in enumerate(centers):
        in_a = in_any(center, polys_a)
        in_b = (not in_a) and in_any(center, polys_b)
        if not (in_a or in_b):
            continue
        # AB：A 朝上小/朝下大；BA：A 朝上大/朝下小。B 与同拓扑的 A 相反。
        if topology == 'AB':
            up_is_small = in_a
        else:
            up_is_small = not in_a
        size = small_size if (is_up[i] == up_is_small) else large_size
        phase[i] = 1 if in_a else -1
        sizes[i] = size
    return phase, sizes


def plot_phase_structure(path, topology='AB', margin=None, a=None,
                         large_size=None, small_size=None,
                         xup=None, yup=None, ydn=None,
                         color_a='#e8829b', color_b='#5f9e6e',
                         title=None, ax=None, show_domain_wall=True,
                         waveguide=None, ports=True, figsize=(12, 9),
                         strict_chinese=True):
    """绘制建模前的**相区结构示意图**。

    图中如实渲染：

    * 两种晶相颜色（A=下半区，默认粉红；B=上半区，默认绿色）；
    * 每个三角孔按**真实边长**绘制（大孔/小孔随 AB/BA 与相位置自动正确）；
    * 相区边界（宽 ``2·margin``）与域壁路径（点划线）；
    * 可选的铜波导轮廓与两端端口标注。

    :param path: TopoPath, 已数值化路径
    :param topology: str, ``'AB'`` / ``'BA'``
    :param margin: float/None, 相区**半宽**；None 时取 ``7·√3/2·a``（约 7 行）
    :param a: float/None, 晶格常数；None 用 ``path.a``
    :param large_size/small_size: float/None, 大/小孔边长；None 用 0.65a / 0.35a
    :param xup/yup/ydn: int/None, 晶体阵列次数，透传 :func:`generate_crystal_holes`
    :param color_a/color_b: str, A 相（下半）/ B 相（上半）填充色
    :param title: str/None, 图标题
    :param ax: plt.Axes/None, 复用坐标轴；None 时新建
    :param show_domain_wall: bool, 是否叠加域壁路径点划线
    :param waveguide: dict/None, 波导绘制参数；支持键
        ``x_ends=((x1,x2),(x3,x4))``（左右两段的 x 范围）、``half_height``、
        ``color``；None 时不画
    :param ports: bool, 是否在路径两端标注「端口 1（输入）/端口 2（输出）」
    :param figsize: tuple, 新建图时的尺寸
    :param strict_chinese: bool, 中文标签下找不到中文字体是否直接报错（默认 True，
        遵守「不发布缺字图」约定）
    :return: tuple[plt.Figure, plt.Axes]
    """
    a = float(path.a if a is None else a)
    if margin is None:
        margin = 7.0 * (np.sqrt(3) / 2.0 * a)

    configure_chinese_font(text='晶相域壁波导端口输入输出区域大小边界',
                           strict=strict_chinese)

    # 1) 相区多边形（A=下半，B=上半）
    polys_a, polys_b = path.band_polygons_numeric(margin)

    # 2) 整块阵列的孔 → 按位置绑定相与真实尺寸
    holes = generate_crystal_holes(path, topology=topology, a=a,
                                   large_size=large_size, small_size=small_size,
                                   xup=xup, yup=yup, ydn=ydn)
    phase, sizes = _resolve_hole_phase_and_size(holes, polys_a, polys_b, topology)

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    # 3) 相区淡色底（让区域大小/边界一目了然）
    band_a = PolyCollection(polys_a, facecolors=color_a, alpha=0.28,
                            edgecolors=color_a, linewidths=1.2)
    band_b = PolyCollection(polys_b, facecolors=color_b, alpha=0.28,
                            edgecolors=color_b, linewidths=1.2)
    ax.add_collection(band_a)
    ax.add_collection(band_b)

    # 4) 三角孔（按相着色、按真实大小；区外孔 phase==0 不画）
    verts_a, verts_b = [], []
    for i in np.where(phase != 0)[0]:
        center = holes['centers'][i]
        theta = 0.0 if holes['is_up'][i] else 180.0
        tri = equilateral_triangle_vertices((float(center[0]), float(center[1])),
                                            float(sizes[i]), theta)
        (verts_a if phase[i] == 1 else verts_b).append(tri)
    if verts_a:
        ax.add_collection(PolyCollection(verts_a, facecolors=color_a,
                                         edgecolors='#333333', linewidths=0.7))
    if verts_b:
        ax.add_collection(PolyCollection(verts_b, facecolors=color_b,
                                         edgecolors='#333333', linewidths=0.7))

    # 5) 域壁路径
    if show_domain_wall:
        xy = path.xy
        ax.plot(xy[:, 0], xy[:, 1], color='black', linestyle='-.',
                linewidth=1.4, zorder=6)

    # 6) 波导（可选）
    if waveguide is not None:
        wcolor = waveguide.get('color', '#1f77b4')
        hh = float(waveguide.get('half_height', 0.18))
        for (x1, x2) in waveguide.get('x_ends', ()):
            ax.add_patch(plt.Rectangle((x1, -hh), x2 - x1, 2 * hh,
                                       fill=False, edgecolor=wcolor,
                                       linewidth=1.6, zorder=7))

    # 7) 端口标注（放在相区左右外侧，避免压住彩色区）
    if ports:
        xy = path.xy
        p_start, p_end = xy[0], xy[-1]
        ax.annotate('端口 1（输入）', (p_start[0], p_start[1]),
                    xytext=(-14, 0), textcoords='offset points',
                    ha='right', va='center', color='#1f77b4', fontsize=11)
        ax.annotate('端口 2（输出）', (p_end[0], p_end[1]),
                    xytext=(14, 0), textcoords='offset points',
                    ha='left', va='center', color='#1f77b4', fontsize=11)

    # 8) 图例与坐标
    legend_items = [
        Patch(facecolor=color_a, label='A 相：路径下半区'),
        Patch(facecolor=color_b, label='B 相：路径上半区'),
        Line2D([0], [0], color='black', linestyle='-.',
               label='域壁路径（波导中线）'),
    ]
    if waveguide is not None:
        legend_items.append(
            Line2D([0], [0], color=waveguide.get('color', '#1f77b4'),
                   label='铜波导 / 探针轮廓'))
    ax.legend(handles=legend_items, loc='upper center',
              bbox_to_anchor=(0.5, -0.06), ncol=3, frameon=False)

    ax.set_aspect('equal')
    ax.autoscale_view()
    ax.margins(0.08)
    ax.set_xlabel('x (mm)')
    ax.set_ylabel('y (mm)')
    ax.set_title(title or f'相区结构示意图（topology={topology}）')
    fig.tight_layout()
    return fig, ax
