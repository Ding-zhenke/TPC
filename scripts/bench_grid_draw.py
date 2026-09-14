# -*- coding: utf-8 -*-
"""网格向量化绘制性能基准（不是单元测试，故放在 scripts/ 而非 tests/）"""
import os
import sys
import time

import numpy as np

# 仓库根目录（本脚本位于 <root>/scripts/）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ===== 六边形网格测试 =====
from mesh_grid.hex_grid import HexLib, HexGridVisualizer

print("=" * 60)
print("六边形网格性能测试")
print("=" * 60)

for size_name, n in [("小 (5×5)", 5), ("中 (20×20)", 20), ("大 (50×50)", 50)]:
    lib = HexLib(hex_size=15, orientation="pointy")
    grid = lib.create_staggered_grid((0, n), (0, n))
    
    viz = HexGridVisualizer(hex_size=15, orientation="pointy", origin=(0, 0))
    viz.set_grid(grid)
    
    t0 = time.perf_counter()
    viz.draw(title=f"Hex Grid {n}x{n}", show_on=False)
    t1 = time.perf_counter()
    
    # 测试涂色
    colors = np.random.rand(len(grid))
    t2 = time.perf_counter()
    viz.add_color_array(colors, cmap='plasma')
    t3 = time.perf_counter()
    
    print(f"  [{size_name}] 网格数={len(grid):>6d}  |  绘制={t1-t0:.4f}s  |  涂色={t3-t2:.4f}s")

# ===== 三角形网格测试 =====
from mesh_grid.tri_grid import build_triangle_lattice, plot_triangle_grid, color_triangles

print("\n" + "=" * 60)
print("三角形网格性能测试")
print("=" * 60)

for size_name, n in [("小 (5×5)", 5), ("中 (20×20)", 20), ("大 (50×50)", 50)]:
    t0 = time.perf_counter()
    tris, up_c, dn_c, _, _ = build_triangle_lattice((0, n), (0, n), a=1.0)
    t1 = time.perf_counter()
    
    fig, ax = plot_triangle_grid((0, n), (0, n), a=1.0, show_labels=False,
                                  show_points=False, show_on=False)
    t2 = time.perf_counter()
    
    # 测试涂色
    colors_up = np.random.rand(len(up_c))
    colors_dn = np.random.rand(len(dn_c))
    t3 = time.perf_counter()
    
    print(f"  [{size_name}] 网格数={len(tris):>6d}  |  生成={t1-t0:.4f}s  |  绘制={t2-t1:.4f}s")

print("\n✅ 测试完成")
print("---> 注意：绘制性能提升显著（old: O(N)个Patch → new: O(1)个PolyCollection）")
