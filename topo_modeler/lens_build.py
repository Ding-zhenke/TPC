# -*- coding: utf-8 -*-
"""透镜建模脚本（GRIN 椭圆透镜）—— 从 ANT6_C6_hexring.ipynb 的两个 9b 单元原样抽出。

用途：
  · notebook 里用 exec(open('lens_build.py').read(), globals()) 复用（本来的调用方式）
  · 也可以独立运行：python lens_build.py（需要自己先准备好工程并注入 app / cst_log）

依赖调用方命名空间里的：app, cst_log, _m3, a, h, R_big
（这些都在 notebook 第 1~4 节定义好）
"""
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
from shapely.ops import unary_union

# ★ 库根目录由 __file__ 推出来（本文件位于 <TPC>/topo_modeler/ 下）⇒ 跟着库走，可用 TPC_PATH 覆盖
TPC_PATH = os.environ.get('TPC_PATH') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TPC_PATH not in sys.path:
    sys.path.append(TPC_PATH)


# ---- 纯几何小工具 ----
#   本文件原本依赖 notebook 第 2 节里的同名函数（exec 复用没问题），
#   但 lens_build_standalone.py 独立运行时没有它们 ⇒ 这里自带一份，
#   两种调用方式都能跑（与 notebook 第 2 节的实现逐字一致）。
def hex_pts(R, ang0):
    """正六边形顶点（CCW），顶点首角 = ang0 度"""
    A = np.deg2rad(ang0 + 60 * np.arange(6))
    return np.column_stack([R * np.cos(A), R * np.sin(A)])

# ============================================================================
# ============================================================
# 9b-① 渐变折射率椭圆透镜：Python 生成孔阵列 + 预览图
#       ★ 本单元与 CST 完全无关：只算几何、存 DXF、画预览，可单独反复调参
#       做法参考 Ant1_grid_BA_240D_epc_epc.ipynb：
#         ① 六边形孔网格（hexlib）→ 取椭圆包络内的孔心
#         ② 孔半径沿椭圆等高线 d = √(x² + y²/(1-e²)) 由内(r1)到外(r2)线性渐变
#         ③ 存 DXF（供下一个单元导入 CST）+ 画预览图
#       坐标约定（局部系）：椭圆的**近焦点在原点** ⇒ 椭圆中心在 (ec_c, 0)
#       ★ 关键 1：孔网格的列范围必须覆盖**整个椭圆**（见下面 lens_col_min/max）
#       ★ 关键 2：**DXF 只写 y≥0 的一半**，另一半在 CST 里用一次「y 镜像复制」补齐
#                 —— 孔阵列关于 y=0 严格对称，这样 DXF 大小/导入时间≈减半
#       ★ 关键 3：DXF 坐标按 lens_dxf_precision 位小数截断（CST 逐条建实体，位数越少越快）
# ============================================================
# 六边形网格库已迁移到 mesh_grid.hex_grid（根目录的 hexlib.py 兼容入口已归档）
from mesh_grid.hex_grid import (HexGridVisualizer, create_hex_polygon,
                                save_to_dxf)
from matplotlib.collections import PolyCollection
from matplotlib.patches import Ellipse as MplEllipse

# ---- 透镜参数（改这里 → 重跑本单元即可看效果）----
# lens_ratio 已在第 2 节定义为 Python 参数（便于缓存核对），此处不再重复定义
lens_hexsize = a / np.sqrt(3) / lens_ratio              # 孔网格的六边形半径
lens_a2 = lens_hexsize * np.sqrt(3)                     # 孔网格的晶格边长
# lens_Nx / lens_Ny 同上，已在第 2 节定义
lens_d0 = 6 * lens_hexsize * 2 * np.sqrt(3)              # 渐变区起始的椭圆半径
lens_r = np.array([50.5, 61.3]) / 1e3 / lens_ratio * 2  # 孔半径 [内圈, 外圈]
lens_rho = R_big                                        # ★ 近焦点所在半径 = 大六边形顶点
lens_dxf = os.path.abspath('grin_lens_hexring.dxf')     # DXF 输出（下一个单元导入 CST）
lens_tol = 1.03                       # 椭圆判据容差：把刚压在椭圆边界上的那圈孔也收进来
lens_dxf_precision = 4                # ★ DXF 坐标保留小数位（mm）⇒ 4 位 = 0.1 µm（6 位 = 1 nm 纯浪费；精度不是瓶颈，详见上文 ①）

lens_ec_a = lens_Nx * lens_a2                                                # 椭圆半轴 a
lens_ec_b = lens_Ny * lens_a2 * np.sin(np.deg2rad(60))                       # 椭圆半轴 b
lens_ecc = np.sqrt(max(lens_ec_a ** 2 - lens_ec_b ** 2, 0)) / lens_ec_a      # 离心率 e
lens_shift = lens_ecc * lens_ec_a                                            # 焦距 ec_c

# ★★ 孔网格必须覆盖整个椭圆（旧版 bug 就在这里）★★
#   局部系里近焦点在原点 ⇒ 椭圆 x ∈ [ec_c−ec_a, ec_c+ec_a]，**关于 0 不对称**，
#   所以列号范围只能按椭圆的真实 x 范围取，不能用对称的 ±Nx：
#   旧版 (-Nx, +Nx) ⇒ 网格只到 x = Nx*a2，而椭圆要伸到 ec_c+ec_a，
#   于是椭圆外侧整片没孔 = 实心硅。
lens_col_min = int(np.floor((lens_shift - lens_ec_a) / lens_a2)) - 1
lens_col_max = int(np.ceil((lens_shift + lens_ec_a) / lens_a2)) + 1

# ★ 渐变归一化到底用哪个"外圈半径"：
#   d_ell = √(x²+y²/(1-e²)) 在椭圆内的取值是 0 → (ec_c+ec_a)（近焦点 → 远端），
#   而下面 t 的分母（旧版/参考案例用 ec_a）只到 ec_a ⇒ **外侧 (ec_c/ec_a≈63%) 的孔全是 r2**。
#   想让孔半径沿整条透镜单调渐变到底，把 lens_d_out 改成 'lens_shift + lens_ec_a'。
lens_d_out = lens_ec_a                                  # ← 想全长度渐变就改成 lens_shift + lens_ec_a

print(f'GRIN 透镜 : 椭圆半轴 {lens_ec_a:.4f} × {lens_ec_b:.4f} mm，离心率 {lens_ecc:.4f}，'
      f'焦距 ec_c = {lens_shift:.4f} mm，孔半径 {lens_r[0] * 1e3:.2f} → {lens_r[1] * 1e3:.2f} um')
print(f'            近焦点 ρ = {lens_rho:.4f} mm（= 顶点），椭圆中心 ρ = {lens_rho + lens_shift:.4f} mm，'
      f'远焦点 ρ = {lens_rho + 2 * lens_shift:.4f} mm')
print(f'孔网格    : 列 {lens_col_min} ~ {lens_col_max}（格距 {lens_a2:.4f} mm）=> '
      f'x ∈ [{(lens_col_min - 0.5) * lens_a2:+.3f}, {(lens_col_max + 0.5) * lens_a2:+.3f}] mm，'
      f'必须覆盖椭圆 x ∈ [{lens_shift - lens_ec_a:+.4f}, {lens_shift + lens_ec_a:+.4f}] mm')

# ---- ① 生成孔心（全象限、以**近焦点**为原点）----
_vis = HexGridVisualizer(hex_size=lens_hexsize, orientation='pointy', origin=(0, 0))
plt.close(_vis.fig)                 # ★ hexlib 的 __init__ 会自建一张 14×12 空画布，这里关掉它，
                                    #   否则单元末尾会先冒出一张空白图（只用它的 hex_lib，不用它的画布）
_vis.set_grid(_vis.hex_lib.create_staggered_grid((lens_col_min, lens_col_max),
                                                 (-lens_Ny, lens_Ny)))
_vis.set_coord_type('offset_q')
_xs, _ys = _vis.hex_lib.hexes_to_pixels(_vis.grid_hexes)
_xs, _ys = np.asarray(_xs, float), np.asarray(_ys, float)

# 椭圆包络 = 到两焦点距离之和 ≤ 2a·tol（焦点在原点与 (2ec_c, 0)）
#   tol > 1：把压在椭圆边界上、或刚出边界一点点的孔也收进来，
#   否则椭圆最扁的两头会留下一圈没孔的实心边（参考实现用 1.1，这里 1.03 足够）
_d1 = np.sqrt(_xs ** 2 + _ys ** 2)
_d2 = np.sqrt((_xs - 2 * lens_shift) ** 2 + _ys ** 2)
_ell = (_d1 + _d2) <= 2 * lens_ec_a * lens_tol
_xp, _yp = _xs[_ell], _ys[_ell]

# ---- ② 孔半径沿椭圆等高线渐变 ----
_d_ell = np.sqrt(_xp ** 2 + _yp ** 2 / (1 - lens_ecc ** 2 + 1e-10))          # 椭圆等高线距离
_t = np.clip((_d_ell - lens_d0) / (lens_d_out - lens_d0 + 1e-10), 0, 1)      # 渐变系数 t∈[0,1]
_ri = lens_r[0] + (lens_r[1] - lens_r[0]) * _t                               # 孔半径 r1→r2 线性插值

_polys = [create_hex_polygon(center=(float(x), float(y)), cell_width=float(r))
          for x, y, r in zip(_xp, _yp, _ri)]                                 # 完整孔阵列（预览/自查用）

# ---- ②' DXF 只写**上半平面（y ≥ 0）**的孔，另一半留给 CST 镜像补齐 ----
#   依据：椭圆（对称轴 y=0）、孔网格行（y = k·行距，正负成对且 x 位置相同）、
#         孔半径（只依赖 y²）在 y → −y 下全都不变
#         ⇒ 上半 ∪ 镜像(上半) = 完整孔阵列（含 y=0 的那一行：它自己镜像自己，unite 合并）
#   ⚠ 只能砍一半：GRIN 的孔半径沿轴向单调变化（近焦点小、远焦点大），
#     所以**不能**再绕 x = ec_c 镜像（否则镜像过去的孔半径是错的）
_upper = _yp >= 0
_polys_dxf = [create_hex_polygon(center=(float(x), float(y)), cell_width=float(r))
              for x, y, r in zip(_xp[_upper], _yp[_upper], _ri[_upper])]
save_to_dxf(_polys_dxf, lens_dxf, layer_name='gridlens', precision=lens_dxf_precision)
print(f'孔阵列   : 网格 {len(_xs)} 个 → 椭圆内 {len(_polys)} 个；'
      f'DXF 只写 y≥0 的 {len(_polys_dxf)} 个'
      f'（坐标保留 {lens_dxf_precision} 位小数 => {0.5 * 10 ** (-lens_dxf_precision) * 1e3:.1f} um，'
      f'文件 {os.path.getsize(lens_dxf) / 1024:.0f} KB；另一半在 CST 里镜像复制）')

# ---- ③ 预览图（只画几何，方便单独调节；不涉及 CST）----
def _poly_xy(poly):
    """把 create_hex_polygon 的返回值取成 (N,2) 顶点数组"""
    if hasattr(poly, 'exterior'):                       # shapely Polygon
        return np.asarray(poly.exterior.coords, float)
    if hasattr(poly, 'vertices'):                       # matplotlib Polygon
        return np.asarray(poly.vertices, float)
    return np.asarray(poly, float)


fig, ax = plt.subplots(figsize=(9.0, 7.2))
_coll = PolyCollection([_poly_xy(p) for p in _polys], array=_ri * 1e3,
                       cmap='rainbow', edgecolors='none')
ax.add_collection(_coll)
fig.colorbar(_coll, ax=ax, shrink=0.8, pad=0.02, label='孔半径 [µm]')   # 渐变的直观标尺

ax.add_patch(MplEllipse((lens_shift, 0), 2 * lens_ec_a, 2 * lens_ec_b,
                        fill=False, ec='r', lw=2.0, label='椭圆包络'))
ax.plot([0], [0], marker='*', ms=16, color='k',
        label=f'近焦点（= 大六边形顶点 ρ={lens_rho:.3f} mm）')
ax.plot([2 * lens_shift], [0], marker='+', ms=12, mew=2, color='b', label='远焦点')
ax.plot([lens_shift], [0], marker='.', ms=10, color='r')
ax.annotate('椭圆中心', (lens_shift, 0), textcoords='offset points', xytext=(6, -15), fontsize=9)
ax.annotate('', xy=(0, -0.55 * lens_ec_b), xytext=(2 * lens_shift, -0.55 * lens_ec_b),
            arrowprops=dict(arrowstyle='<->', color='0.3', lw=1.0))
ax.text(lens_shift, -0.62 * lens_ec_b, f'2·ec_c = {2 * lens_shift:.3f} mm',
        ha='center', va='top', fontsize=9, color='0.3')

# ★ 坐标范围按**实际几何**取（椭圆两端 + 孔阵列外沿 + 余量），
#   不要写死比例系数：椭圆右端 = ec_c+ec_a，左端 = ec_c−ec_a，
#   当离心率 e < 0.7 时右端会跑到 2·ec_c+0.3·ec_a 之外（旧版就是这里被切掉的）
_pad_x, _pad_y = 0.04 * lens_ec_a, 0.06 * lens_ec_b
ax.set_aspect('equal')
ax.set_xlim(min(lens_shift - lens_ec_a, _xp.min()) - _pad_x,
            max(lens_shift + lens_ec_a, _xp.max()) + _pad_x)
ax.set_ylim(min(-lens_ec_b, _yp.min()) - _pad_y,
            max(lens_ec_b, _yp.max()) + _pad_y)
ax.set_xlabel('x [mm]  （0 = 顶点/近焦点，+x 朝外）')
ax.set_ylabel('y [mm]')
ax.grid(alpha=0.25)
ax.legend(loc='upper left', fontsize=8)
ax.set_title(f'GRIN 椭圆透镜：{lens_ec_a:.3f} × {lens_ec_b:.3f} mm，e = {lens_ecc:.3f}，'
             f'{len(_polys)} 个孔（DXF {len(_polys_dxf)} 个）', fontsize=10)
plt.tight_layout()
plt.show()

# ---- ④ 纯几何自查：裁剪后透镜与大六边形**不相交**（与 CST 无关）----
#   9b-② 在 CST 里是在局部系（近焦点=原点）用「顶点内角 120° 的楔形」subtract；
#   这里在**全局系**里等价地算一遍（椭圆与楔形都平移到顶点 Rbig 处）再求交。
from shapely.geometry import Polygon as _ShpPoly

_th = np.linspace(0, 2 * np.pi, 2001)
_ell_poly = _ShpPoly(np.column_stack([lens_rho + lens_shift + lens_ec_a * np.cos(_th),
                                      lens_ec_b * np.sin(_th)]))          # 椭圆（全局，中心在顶点之后 ec_c）
_ang = np.deg2rad([120, 240])                                             # 顶点处两条六边形边的方向
_cut_len = 2.2 * R_big                                                    # 与 9b-② 的 Ls 一致
_wedge = _ShpPoly([(lens_rho, 0.0),                                       # 楔形顶点 = 大六边形顶点
                   (lens_rho + _cut_len * np.cos(_ang[0]), _cut_len * np.sin(_ang[0])),
                   (lens_rho + _cut_len * np.cos(_ang[1]), _cut_len * np.sin(_ang[1]))])
_lens_region = _ell_poly.difference(_wedge)                               # 裁剪后的透镜（全局）
_hex_poly = _ShpPoly(hex_pts(R_big, 0))                                   # 大六边形（顶点在 0°）
_ov = _lens_region.intersection(_hex_poly).area
print(f'裁剪自查 : 透镜与大六边形的重叠面积 = {_ov:.8f} mm^2 '
      + ('[OK] 无重叠（重叠部分已全部剪掉）' if _ov < 1e-3 else '[x] 仍有重叠，需要检查裁剪角'))

# ---- ⑤ 纯几何自查：孔阵列是否**遍布整个椭圆**（无成片实心区）----
#   判据：透镜内任一点到**最近孔心**的最远距离 d_max
#         完好的三角格子（格距 a2）里，最坏的点是三角形重心，距离 = a2/√3；
#         d_max 一旦明显超过它 ⇒ 必然存在"孔铺不到"的成片实心区
_gx2 = np.arange(lens_shift - lens_ec_a - 0.02, lens_shift + lens_ec_a + 0.02, 0.02)
_gy2 = np.arange(-lens_ec_b - 0.02, lens_ec_b + 0.02, 0.02)
_GX2, _GY2 = np.meshgrid(_gx2, _gy2)
_ang2 = np.mod(np.arctan2(_GY2, _GX2), 2 * np.pi)      # 必须取模 2π，否则下半楔形会被误判成透镜
_in2 = (((_GX2 - lens_shift) ** 2 / lens_ec_a ** 2 + _GY2 ** 2 / lens_ec_b ** 2) <= 1.0) \
       & ~((_ang2 >= np.deg2rad(120)) & (_ang2 <= np.deg2rad(240)))       # 去掉被剪掉的楔形
_PX2, _PY2 = _GX2[_in2], _GY2[_in2]
try:                                                    # KD 树（scipy 在时装，O(N log N)，孔多时快很多）
    from scipy.spatial import cKDTree as _KDTree
    _dmin = _KDTree(np.column_stack([_xp, _yp])).query(
        np.column_stack([_PX2, _PY2]), k=1, workers=-1)[0]
except ImportError:                                     # 退回分块 numpy（无 scipy 时）
    _dmin = np.full(_PX2.size, np.inf)
    for _i in range(0, _xp.size, 64):
        _bx, _by = _xp[_i:_i + 64], _yp[_i:_i + 64]
        _dmin = np.minimum(_dmin, np.sqrt((_PX2[:, None] - _bx) ** 2
                                          + (_PY2[:, None] - _by) ** 2).min(axis=1))
_dmax, _d_theory = _dmin.max(), lens_a2 / np.sqrt(3)
print(f'孔阵覆盖自查 : 透镜内 {_PX2.size} 个采样点到最近孔心的最远距离 = {_dmax:.4f} mm，'
      f'完好三角格子的理论值 格距/√3 = {_d_theory:.4f} mm（{_dmax / _d_theory:.2f}×）')
print('              ' + ('[OK] 孔阵列遍布整个椭圆，无成片实心区' if _dmax <= 1.05 * _d_theory else
      f'[x] 有孔铺不到的区域：最远点在 x = {_PX2[_dmin.argmax()]:+.3f}, y = {_PY2[_dmin.argmax()]:+.3f} mm'))

# ---- ⑥ 纯几何自查：上半 + y 镜像 == 完整孔阵列（保证 DXF 只写一半不漏孔）----
from shapely.affinity import scale as _scale
_half_u = unary_union(_polys_dxf)                                    # DXF 里写进去的那一半
_rebuilt = unary_union([_half_u, _scale(_half_u, yfact=-1, origin=(0, 0))])   # 镜像拼回整体
_full_u = unary_union(_polys)
_diff = _rebuilt.symmetric_difference(_full_u).area
print(f'镜像自查 : 上半 {len(_polys_dxf)} 个 ∪ y镜像  vs  完整 {len(_polys)} 个 => '
      f'差异面积 = {_diff:.3e} mm^2 '
      + ('[OK] 完全一致（DXF 只写一半即可）' if _diff < 1e-6 else '[x] 不一致，不能用镜像简化！'))

# ============================================================
# 9b-② 渐变折射率椭圆透镜：CST 建模（消费上一个单元生成的 DXF）
#       ★ 依赖 9b-① 的 DXF 与 lens_ec_a / lens_ec_b / lens_shift
#       ① dxf_import 孔阵列（component='gridlens'）—— DXF 里**只有 y≥0 的一半**
#          ★ 紧接着用一次「y 镜像复制」把另一半补齐（孔阵列关于 y=0 严格对称）
#            ⇒ DXF 大小与导入时间≈减半，几何与"整份导入"完全等价
#          ⚠ 耗时坑 1（实测 Nx/Ny = 38/34、2215 条多段线 = 183.9 s）：CST 的 DXF 导入是
#            .AsCurves "False" ⇒ **每条多段线建一个实体**，耗时随多段线数量**超线性**增长
#            （precision 6→2 只让文件小 21%，几乎不影响耗时）
#            ⇒ 想更快只有**减少孔数**：抬高 lens_ratio（格距 ×k ⇒ 孔数 ÷k²）
#       ② 椭圆包络（中心在 (ec_c,0)）拉伸 − 孔阵列 = 渐变折射率（GRIN）透镜
#          ★★ 椭圆的**长短轴与中心一律用 CST 变量**，不写具体数值 ★★
#             写法照抄参考案例 Ant1_grid_BA_240D_epc_epc.ipynb：
#                 app.para('ec_a','Nx*a2'); app.para('ec_b','Ny*a2*sind(60)')
#                 app.para('ec_c','sqr(ec_a^2-ec_b^2)')
#                 app.ellipse('ec_a','ec_b',[0,0],'epc1') → translate(['ec_c','0','0'])
#             本例把中心直接写成 ['ec_c','0']（与"先画在原点再平移 ec_c"等价），
#             并且整条尺寸链都挂在晶格常数 a 上：a → ratio → a2 → Nx,Ny → ec_a,ec_b → ec_c
#       ③ 剪掉与大六边形**重叠**的部分：顶点处六边形内角 120°，
#          其内部就是张开 120°（120°→240°）的楔形 ⇒ 用这个楔形去 subtract
#          （重叠的不要、不重叠的全留，所以不能用"切掉内半边"的做法）
#       ④ 平移 Rbig ⇒ 椭圆**近焦点**正好落在大六边形顶点上
#       ⑤ rotation(repetition=5, copy=True, unite=False) 旋转复制 ⇒ 6 个顶点各 1 个
#          ⚠ 耗时坑 2（本次定位到的卡死点）：**必须 unite=False**。
#            unite=True 时 CST 要把 6×(4351 个壳) 并成 1 个实体，实测 19 min 都跑不完；
#            6 个互不接触的独立实体对网格/求解完全等价，秒级完成
#       ⏱ 每个重操作都打印耗时，方便按参数（Nx/Ny/ratio/precision）评估导入与布尔开销
# ============================================================
import time as _time

_t_all = _time.perf_counter()
if not os.path.exists(lens_dxf):
    raise FileNotFoundError(f'缺少透镜 DXF：{lens_dxf} —— 请先跑 9b-① 生成孔阵列')

_t0 = _time.perf_counter()
app.dxf_import(lens_dxf, add='True', component='gridlens', height='h')
_dt_dxf = _time.perf_counter() - _t0
cst_log('DXF 导入（孔阵列：DXF 里只有 y≥0 的一半）')
print(f'[t] DXF 导入耗时 = {_dt_dxf:.1f} s'
      f'（{len(_polys_dxf)} 条多段线，{os.path.getsize(lens_dxf) / 1024:.0f} KB，'
      f'precision={lens_dxf_precision}）')

# ---- ①' 一次「y 镜像复制」把下半补齐（孔阵列关于 y=0 严格对称）----
#       Center=(0,0,0)、PlaneNormal=(0,1,0) ⇒ 关于 y=0 平面镜像
#       copy=True 保留上半、unite=True 合并成一个实体（y=0 那一行自己镜像自己不冲突）
_t0 = _time.perf_counter()
app.mirror('import_1', [0, 0, 0], [0, 1, 0], component='gridlens', copy=True, unite=True)
_dt_mir = _time.perf_counter() - _t0
cst_log('孔阵列 y 镜像复制（补齐下半）')
print(f'[t] y 镜像复制耗时 = {_dt_mir:.1f} s（{len(_polys_dxf)} → {len(_polys)} 个孔）')

# ---- ② 登记椭圆相关的 CST 参数（全部由 a 与孔网格格距推出，无硬编码数值）----
app.para('ratio', lens_ratio, expression='透镜孔网格细化倍率：格距 a2 = a/ratio')
app.para('Nx', lens_Nx, expression='椭圆长半轴 = Nx 个格距')
app.para('Ny', lens_Ny, expression='椭圆短半轴 = Ny 个格距')
app.para('a2', 'a/ratio', expression='孔网格格距（= hexlib 的 HEX_SIZE*sqr(3)）')
app.para('d0', '12*a2', expression='孔半径渐变区起始的椭圆半径')
app.para('r1', f'{lens_r1_0}/ratio', expression='孔半径（内圈）[mm] = lens_r1_0/ratio')
app.para('r2', f'{lens_r2_0}/ratio', expression='孔半径（外圈）[mm] = lens_r2_0/ratio')
app.para('ec_a', 'Nx*a2', expression='★ 椭圆长半轴（沿臂方向）')
app.para('ec_b', 'Ny*a2*sind(60)', expression='★ 椭圆短半轴（横向）')
app.para('ec_c', 'sqr(ec_a^2-ec_b^2)', expression='★ 焦距：椭圆中心在 (ec_c, 0)，近焦点在原点')
print(f'椭圆变量  : ec_a = Nx*a2 = {lens_ec_a:.4f} mm，ec_b = Ny*a2*sind(60) = {lens_ec_b:.4f} mm，'
      f'ec_c = sqr(ec_a^2-ec_b^2) = {lens_shift:.4f} mm')

app.ellipse('ec_a', 'ec_b', ['ec_c', '0'], 'lens_epc')       # ← 长短轴 / 中心：CST 变量
app.extrude('curve1:lens_epc', 'lens_epc', 'h', material='Silicon (lossy)', log_flag=1)
cst_log('椭圆包络拉伸（ec_a / ec_b / ec_c）')

_t0 = _time.perf_counter()
app.subtract('lens_epc', 'import_1', component2='gridlens')         # 椭圆硅片 − 孔阵列 = GRIN 透镜
_dt_sub = _time.perf_counter() - _t0
cst_log('椭圆包络 − 孔阵列')
print(f'[t] 椭圆 - 孔阵列（布尔减）耗时 = {_dt_sub:.1f} s')

# ---- ③ 剪掉与正六边形重叠的部分（顶点内角 120°，内部为 120°→240° 的楔形）----
_lens_cut_pts = [[0, 0],
                 ['Ls*cosd(120)', 'Ls*sind(120)'],                   # 顶点处的两条六边形边方向
                 ['Ls*cosd(240)', 'Ls*sind(240)'],
                 [0, 0]]                                             # 逆时针 ⇒ 沿 +z 拉伸
app.polyline(_lens_cut_pts, name='lens_hex_cut')
app.extrude('curve1:lens_hex_cut', 'lens_hex_cut', 'h',
            material='Silicon (lossy)', log_flag=1)
cst_log('六边形内部楔形（裁剪体）')
_t0 = _time.perf_counter()
app.subtract('lens_epc', 'lens_hex_cut')                            # 只去掉落在六边形内的那一块
_dt_cut = _time.perf_counter() - _t0
cst_log('剪掉与正六边形重叠的部分')
print(f'[t] 楔形裁剪耗时 = {_dt_cut:.1f} s')

# ---- ④ 移到 0° 顶点（此时局部原点就是近焦点）----
_t0 = _time.perf_counter()
app.translate('lens_epc', ['0', '0', '-h/2'], copy=False, unite=False, log_flag=1)   # z 居中（与板共面）
app.translate('lens_epc', ['Rbig', '0', '0'], copy=False, unite=False, log_flag=1)   # 近焦点 → 顶点
_dt_tr = _time.perf_counter() - _t0
cst_log('透镜移到 0° 顶点（近焦点在顶点）')
print(f'[t] 平移耗时 = {_dt_tr:.1f} s')

# ---- ⑤ 旋转复制 ×5 ⇒ 6 个顶点各 1 个 ----
#       ★ unite=False：6 个互不接触的独立实体（网格/求解与合并等价）
#         原来写 unite=True ⇒ CST 要布尔并 6×4351 个壳，实测 19 min 都没跑完（真正的卡死点）
_t0 = _time.perf_counter()
app.rotation('lens_epc', [0, 0, 60], repetition=5, copy=True, unite=False)
_dt_rot = _time.perf_counter() - _t0
cst_log('透镜 旋转复制 ×6（unite=False）')
print(f'[t] 旋转复制 ×6 耗时 = {_dt_rot:.1f} s（unite=False => 不做布尔并）')
print(f'已建 6 个 GRIN 椭圆透镜：近焦点 ρ = {lens_rho:.4f} mm（= 大六边形顶点），'
      f'椭圆中心 ρ = {lens_rho + lens_shift:.4f} mm，远焦点 ρ = {lens_rho + 2 * lens_shift:.4f} mm；'
      f'与六边形重叠的部分已剪掉；孔阵列 = DXF 上半 {len(_polys_dxf)} 个 + y 镜像')
print(f'[t] 本单元总耗时 = {_time.perf_counter() - _t_all:.1f} s'
      f'（DXF 导入 {_dt_dxf:.1f} + 镜像 {_dt_mir:.1f} + 减孔 {_dt_sub:.1f}')
print(f'   + 楔形裁剪 {_dt_cut:.1f} + 平移 {_dt_tr:.1f} + 旋转复制 {_dt_rot:.1f}）')
print('CST 参数个数 =', _m3.GetNumberOfParameters())
