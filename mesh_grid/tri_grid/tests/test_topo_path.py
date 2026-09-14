# -*- coding: utf-8 -*-
"""
TopoPath 单元测试
=================
验证拓扑路径统一管理与声明式 DSL 的正确性。

运行方式:
    pytest test_topo_path.py -v
    或直接: python test_topo_path.py

@author: PC
"""

import sys
import os
import numpy as np

# 确保能导入 TPC 库
_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from mesh_grid.tri_grid import TopoPath, TopoPathBuilder, path_loc_to_xy


A = 0.2425  # 晶格常数 mm


# ============================================================
# 测试 1：6 个方向的物理角度映射
# ============================================================
def test_directions_mapping():
    """6 个晶格方向 (dr,dc) 对应的物理角度正确。"""
    cases = [
        ((0, 1), 0.0),     # +c  → 0°
        ((1, 0), 60.0),    # +r  → 60°
        ((1, -1), 120.0),  # +r-c → 120°
        ((0, -1), 180.0),  # -c  → 180°
        ((-1, 0), 240.0),  # -r  → 240°
        ((-1, 1), 300.0),  # -r+c → 300°
    ]
    for (dr, dc), expected_angle in cases:
        # 用 TopoPath 计算单段角度
        path = TopoPath.from_lattice([(0, 0), (dr, dc)], a=A)
        angles = path.segment_angles()
        assert len(angles) == 1, f"方向 ({dr},{dc}) 应只有1段，实际 {len(angles)}"
        actual = angles[0]
        # 处理 180° 和 -180° 的等价性
        diff = abs(actual - expected_angle)
        if diff > 180:
            diff = 360 - diff
        assert diff < 0.01, f"方向 ({dr},{dc}) 角度错误: 期望 {expected_angle}°, 实际 {actual}°"
    print("[OK] 测试1: 6个方向物理角度映射正确")


# ============================================================
# 测试 2：turn 方向旋转
# ============================================================
def test_turn_rotation():
    """turn(60/120/180/240/300) 方向旋转正确。"""
    # 从 0° 方向 (+c) 开始，旋转各种角度
    cases = [
        (60, (1, 0)),     # 0° + 60° = 60° → +r
        (120, (1, -1)),   # 0° + 120° = 120° → +r-c
        (180, (0, -1)),   # 0° + 180° = 180° → -c
        (240, (-1, 0)),   # 0° + 240° = 240° → -r
        (300, (-1, 1)),   # 0° + 300° = 300° → -r+c
        (-60, (-1, 1)),   # 0° - 60° = 300° → -r+c
        (-120, (-1, 0)),  # 0° - 120° = 240° → -r
    ]
    for turn_angle, expected_dir in cases:
        b = TopoPathBuilder(A).start(0, 0, direction=(0, 1))
        b.turn(turn_angle)
        b.move(1, 'along')
        path = b.build()
        actual_dir = (path[1][0] - path[0][0], path[1][1] - path[0][1])
        assert actual_dir == expected_dir, \
            f"turn({turn_angle}) 方向错误: 期望 {expected_dir}, 实际 {actual_dir}"
    print("[OK] 测试2: turn 方向旋转正确")


# ============================================================
# 测试 3：直波导 path
# ============================================================
def test_straight_waveguide_path():
    """直波导 path: .start(0,-1).move(19,'c') → [(0,-1),(0,18)]"""
    path = TopoPath.builder(A).start(0, -1).move(19, 'c').build()
    assert len(path) == 2, f"直波导应有2个点，实际 {len(path)}"
    assert path[0] == (0, -1), f"起点错误: {path[0]}"
    assert path[1] == (0, 18), f"终点错误: {path[1]}"
    assert path.is_straight(), "直波导应为直线"
    assert not path.has_bend(), "直波导不应有拐弯"
    print(f"[OK] 测试3: 直波导 path 正确: {path}")


# ============================================================
# 测试 4：120° 拐弯天线 path
# ============================================================
def test_120degree_antenna_path():
    """120° 天线: .start(0,-1).move(19,'c').turn(120).move(14,'along')
       → [(0,-1),(0,18),(14,4)]"""
    path = (TopoPath.builder(A)
            .start(0, -1).move(19, 'c').turn(120).move(14, 'along').build())
    assert len(path) == 3, f"120°天线应有3个点，实际 {len(path)}"
    assert path[0] == (0, -1), f"起点错误: {path[0]}"
    assert path[1] == (0, 18), f"拐点错误: {path[1]}"
    assert path[2] == (14, 4), f"终点错误: {path[2]}, 期望 (14,4)"
    assert path.has_bend(), "天线应有拐弯"
    assert not path.is_straight(), "天线不应为直线"
    # 段角度验证
    angles = path.segment_angles()
    assert abs(angles[0] - 0.0) < 0.01, f"第一段角度错误: {angles[0]}"
    assert abs(angles[1] - 120.0) < 0.01, f"第二段角度错误: {angles[1]}"
    print(f"[OK] 测试4: 120°天线 path 正确: {path}")
    print(f"       段角度: {angles}")


# ============================================================
# 测试 5：CST 表达式 (0,18)
# ============================================================
def test_cst_expr_0_18():
    """lattice_to_cst_expr(0,18) → ('18*a', '0')"""
    px, py = TopoPath.lattice_to_cst_expr(0, 18)
    assert px == '18*a', f"px 错误: {px}, 期望 '18*a'"
    assert py == '0', f"py 错误: {py}, 期望 '0'"
    print(f"[OK] 测试5: CST表达式(0,18) → ({px},{py})")


# ============================================================
# 测试 6：CST 表达式 (14,4)
# ============================================================
def test_cst_expr_14_4():
    """lattice_to_cst_expr(14,4) → ('4*a+14*a/2', '14*a/2*sqr(3)')"""
    px, py = TopoPath.lattice_to_cst_expr(14, 4)
    assert px == '4*a+14*a/2', f"px 错误: {px}, 期望 '4*a+14*a/2'"
    assert py == '14*a/2*sqr(3)', f"py 错误: {py}, 期望 '14*a/2*sqr(3)'"
    print(f"[OK] 测试6: CST表达式(14,4) → ({px},{py})")


# ============================================================
# 测试 7：与 path_loc_to_xy 一致性
# ============================================================
def test_consistency_with_path_loc_to_xy():
    """TopoPath.xy 与 mesh_grid.tri_grid.path_loc_to_xy 输出完全一致。"""
    # 直波导
    p1 = TopoPath.builder(A).start(0, -1).move(19, 'c').build()
    ref1 = path_loc_to_xy(p1.lattice, A)
    assert np.allclose(p1.xy, ref1), f"直波导与 path_loc_to_xy 不一致:\n{p1.xy}\n{ref1}"

    # 120° 天线
    p2 = (TopoPath.builder(A)
          .start(0, -1).move(19, 'c').turn(120).move(14, 'along').build())
    ref2 = path_loc_to_xy(p2.lattice, A)
    assert np.allclose(p2.xy, ref2), f"120°天线与 path_loc_to_xy 不一致:\n{p2.xy}\n{ref2}"

    # 240° 天线
    p3 = (TopoPath.builder(A)
          .start(0, -1).move(19, 'c').turn(240).move(10, 'along').build())
    ref3 = path_loc_to_xy(p3.lattice, A)
    assert np.allclose(p3.xy, ref3), f"240°天线与 path_loc_to_xy 不一致:\n{p3.xy}\n{ref3}"

    print("[OK] 测试7: 与 path_loc_to_xy 完全一致（直波导+120°+240°）")


# ============================================================
# 测试 8：边界框与阵列范围
# ============================================================
def test_bounding_box_and_array_range():
    """get_bounding_box() 和 get_array_range() 返回值合理。"""
    path = (TopoPath.builder(A)
            .start(0, -1).move(19, 'c').turn(120).move(14, 'along').build())

    # 边界框
    xmin, xmax, ymin, ymax = path.get_bounding_box()
    assert xmin < xmax, f"xmin({xmin}) 应小于 xmax({xmax})"
    assert ymin < ymax, f"ymin({ymin}) 应小于 ymax({ymax})"
    # 路径点应在边界框内
    for x, y in path.xy:
        assert xmin <= x <= xmax, f"x={x} 不在边界框 [{xmin},{xmax}] 内"
        assert ymin <= y <= ymax, f"y={y} 不在边界框 [{ymin},{ymax}] 内"

    # 阵列范围
    xup, yup, ydn = path.get_array_range()
    assert xup > 0, f"xup 应大于0，实际 {xup}"
    assert yup > 0, f"yup 应大于0，实际 {yup}"
    assert ydn > 0, f"ydn 应大于0，实际 {ydn}"
    # 120°天线的 r 范围是 [0,14]，所以 yup=15, ydn=1
    assert yup == 15, f"yup 应为15，实际 {yup}"
    assert ydn == 1, f"ydn 应为1，实际 {ydn}"
    # c 范围是 [-1,18]，xup = 18 + 14//2 + 1 = 26
    assert xup == 26, f"xup 应为26，实际 {xup}"

    print(f"[OK] 测试8: 边界框 x=[{xmin:.3f},{xmax:.3f}], y=[{ymin:.3f},{ymax:.3f}]")
    print(f"       阵列范围 xup={xup}, yup={yup}, ydn={ydn}")


# ============================================================
# 测试 9：基板多边形顶点数
# ============================================================
def test_substrate_polygon_vertices():
    """build_substrate_polygon() 顶点数 = 2*N + 1（N 为路径点数）。"""
    # 直波导（2个点）
    p1 = TopoPath.builder(A).start(0, -1).move(19, 'c').build()
    sub1 = p1.build_substrate_polygon()
    expected1 = 2 * len(p1) + 1
    assert len(sub1) == expected1, \
        f"直波导基板顶点数错误: 期望 {expected1}, 实际 {len(sub1)}"

    # 120°天线（3个点）
    p2 = (TopoPath.builder(A)
          .start(0, -1).move(19, 'c').turn(120).move(14, 'along').build())
    sub2 = p2.build_substrate_polygon()
    expected2 = 2 * len(p2) + 1
    assert len(sub2) == expected2, \
        f"120°天线基板顶点数错误: 期望 {expected2}, 实际 {len(sub2)}"

    # VPC 区域多边形：两条边界链各含全部路径点，故顶点数 = 2*N + 1
    vpc_upper = p2.build_vpc_area_polygon(side='upper')
    vpc_lower = p2.build_vpc_area_polygon(side='lower')
    expected_vpc = 2 * len(p2) + 1
    assert len(vpc_upper) == expected_vpc, \
        f"VPC上半区顶点数错误: 期望 {expected_vpc}, 实际 {len(vpc_upper)}"
    assert len(vpc_lower) == expected_vpc, \
        f"VPC下半区顶点数错误: 期望 {expected_vpc}, 实际 {len(vpc_lower)}"

    # side 取值非法应报错
    try:
        p2.build_vpc_area_polygon(side='middle')
        assert False, "side='middle' 应报错"
    except ValueError as e:
        assert 'upper' in str(e), f"错误信息应提示合法取值: {e}"

    print(f"[OK] 测试9: 基板多边形顶点数正确（直波导{len(sub1)}, 天线{len(sub2)}）")
    print(f"       VPC区域顶点数: upper={len(vpc_upper)}, lower={len(vpc_lower)}")


# ============================================================
# 测试 10：非法输入报错
# ============================================================
def test_invalid_inputs():
    """非法输入应抛出明确异常。"""
    # 非 60° 倍数的 turn
    try:
        TopoPath.builder(A).start(0, 0).turn(90)
        assert False, "turn(90) 应报错"
    except ValueError as e:
        assert '60' in str(e), f"错误信息应包含'60': {e}"

    # 空路径 build
    try:
        TopoPath.builder(A).build()
        assert False, "空路径 build 应报错"
    except RuntimeError as e:
        assert '空' in str(e) or 'start' in str(e), f"错误信息应提示起点: {e}"

    # 未 start 就 move
    try:
        TopoPath.builder(A).move(5, 'c')
        assert False, "未 start 就 move 应报错"
    except RuntimeError as e:
        assert 'start' in str(e), f"错误信息应提示 start: {e}"

    # 未知方向名
    try:
        TopoPath.builder(A).start(0, 0).move(5, 'unknown_dir')
        assert False, "未知方向应报错"
    except ValueError as e:
        assert '未知方向' in str(e), f"错误信息应包含'未知方向': {e}"

    # 错误形状的 path_lattice
    try:
        TopoPath.from_lattice([(0, 0, 0)], a=A)
        assert False, "错误形状应报错"
    except ValueError as e:
        assert '(N,2)' in str(e), f"错误信息应包含'(N,2)': {e}"

    print("[OK] 测试10: 非法输入报错正确（turn非60倍数/空路径/未start/未知方向/错误形状）")


# ============================================================
# 测试 11：符号运算辅助函数
# ============================================================
def test_symbolic_operations():
    """验证 _symbolic_add 和 _symbolic_mul 辅助函数。"""
    from mesh_grid.tri_grid.topo_path import _symbolic_add, _symbolic_mul

    # 符号加法
    assert _symbolic_add(-1, 'x1') == 'x1-1', f"_symbolic_add(-1,'x1') 错误: {_symbolic_add(-1,'x1')}"
    assert _symbolic_add('x1', 'y1') == 'x1+y1', f"_symbolic_add('x1','y1') 错误"
    assert _symbolic_add(0, 'x1') == 'x1', f"_symbolic_add(0,'x1') 错误"
    assert _symbolic_add('x1', 0) == 'x1', f"_symbolic_add('x1',0) 错误"
    assert _symbolic_add(3, 4) == 7, f"_symbolic_add(3,4) 错误"
    assert _symbolic_add('x1', -2) == 'x1-2', f"_symbolic_add('x1',-2) 错误"
    print(f"[OK] 测试11: 符号加法正确")

    # 符号乘法
    assert _symbolic_mul('x1', 0) == 0, f"_symbolic_mul('x1',0) 错误"
    assert _symbolic_mul('x1', 1) == 'x1', f"_symbolic_mul('x1',1) 错误"
    assert _symbolic_mul('x1', -1) == '-x1', f"_symbolic_mul('x1',-1) 错误"
    assert _symbolic_mul(2, 3) == 6, f"_symbolic_mul(2,3) 错误"
    assert _symbolic_mul(0, 'y1') == 0, f"_symbolic_mul(0,'y1') 错误"
    print(f"[OK] 测试11: 符号乘法正确")


# ============================================================
# 测试 12：符号直波导（参数化 CST 表达式）
# ============================================================
def test_symbolic_straight_waveguide():
    """符号直波导：.start(0,0).move('x1','c')，生成参数化 CST 表达式。"""
    path = (TopoPath.builder(A)
            .start(0, 0)
            .move('x1', 'c')
            .build(param_values={'x1': 18}))

    # 符号坐标
    assert path.has_symbols, "应包含符号坐标"
    assert path[0] == (0, 0), f"起点错误: {path[0]}"
    assert path[1] == (0, 'x1'), f"终点符号坐标错误: {path[1]}"
    print(f"  符号坐标: {path.lattice_symbolic}")

    # CST 表达式（参数化！）
    px1, py1 = TopoPath.lattice_to_cst_expr(0, 0)
    px2, py2 = TopoPath.lattice_to_cst_expr(0, 'x1')
    assert px1 == '0*a' or px1 == '0', f"p1x 错误: {px1}"
    assert py1 == '0', f"p1y 错误: {py1}"
    assert px2 == 'x1*a', f"p2x 应为参数化 'x1*a'，实际: {px2}"
    assert py2 == '0', f"p2y 错误: {py2}"
    print(f"  CST表达式: p1=({px1},{py1}), p2=({px2},{py2})")
    print(f"  ★ p2x='x1*a' 是参数化的！在 CST 中修改 x1 即可调整波导长度")

    # 数值化（用于预览）
    assert path.lattice.tolist() == [[0, 0], [0, 18]], f"数值化错误: {path.lattice.tolist()}"
    assert np.allclose(path.xy[1], [18 * A, 0]), f"数值化直角坐标错误: {path.xy[1]}"
    print(f"  数值化: {path.lattice.tolist()}, 终点直角坐标={path.xy[1].tolist()}")

    print("[OK] 测试12: 符号直波导参数化 CST 表达式正确")


# ============================================================
# 测试 13：符号 120° 天线（参数化 CST 表达式）
# ============================================================
def test_symbolic_120_antenna():
    """符号 120° 天线：直段 x1 + 拐弯 y1，生成参数化 CST 表达式。"""
    path = (TopoPath.builder(A)
            .start(0, 0)
            .move('x1', 'c')
            .turn(120)
            .move('y1', 'along')
            .build(param_values={'x1': 18, 'y1': 14}))

    # 符号坐标
    assert path.has_symbols
    assert path[0] == (0, 0)
    assert path[1] == (0, 'x1'), f"第2点符号坐标错误: {path[1]}"
    # 120°方向 (+1,-1)，走 y1 步：r = 0+y1 = 'y1', c = x1-y1 = 'x1-y1'
    assert path[2] == ('y1', 'x1-y1'), f"第3点符号坐标错误: {path[2]}"
    print(f"  符号坐标: {path.lattice_symbolic}")

    # CST 表达式（参数化！）
    px2, py2 = TopoPath.lattice_to_cst_expr(0, 'x1')
    px3, py3 = TopoPath.lattice_to_cst_expr('y1', 'x1-y1')
    assert px2 == 'x1*a', f"p2x 应为 'x1*a'，实际: {px2}"
    assert py2 == '0', f"p2y 错误: {py2}"
    # px3 = (x1-y1)*a + y1*a/2 = x1*a - y1*a + y1*a/2 = x1*a - y1*a/2
    assert px3 == '(x1-y1)*a+y1*a/2', f"p3x 参数化表达式错误: {px3}"
    assert py3 == 'y1*a/2*sqr(3)', f"p3y 参数化表达式错误: {py3}"
    print(f"  CST表达式: p2=({px2},{py2})")
    print(f"             p3=({px3},{py3})")
    print(f"  ★ p2x='x1*a', p3x='(x1-y1)*a+y1*a/2' 都是参数化的！")

    # 数值化验证：x1=18, y1=14 → 第3点 (14, 4)，与旧代码一致
    assert path.lattice.tolist() == [[0, 0], [0, 18], [14, 4]], \
        f"数值化错误: {path.lattice.tolist()}"
    # 数值验证 p3 = (14,4): x = 4*a + 14*a/2 = 11a, y = 14*a/2*√3 = 7a√3
    expected_x3 = 4 * A + 14 * A / 2
    expected_y3 = 14 * A / 2 * np.sqrt(3)
    assert abs(path.xy[2, 0] - expected_x3) < 1e-10, f"p3x 数值错误: {path.xy[2,0]}"
    assert abs(path.xy[2, 1] - expected_y3) < 1e-10, f"p3y 数值错误: {path.xy[2,1]}"
    print(f"  数值化: {path.lattice.tolist()}, p3直角坐标=({path.xy[2,0]:.4f},{path.xy[2,1]:.4f})")

    print("[OK] 测试13: 符号 120° 天线参数化 CST 表达式正确")


# ============================================================
# 测试 14：符号路径与旧代码对比
# ============================================================
def test_symbolic_vs_old_code():
    """验证符号路径生成的 CST 表达式与旧代码的参数化方式一致。"""
    # 旧代码方式（cell 5）:
    #   px1=0, py1=0
    #   px2 = px1 + x1*a = x1*a
    #   px3 = px2 + y1*e1  (e1 = -a/2 for 120°方向)
    #   py3 = py1 - y1*e2  (e2 = a√3/2)
    # TopoPath 方式:
    #   px2 = x1*a
    #   px3 = (x1-y1)*a + y1*a/2 = x1*a - y1*a/2
    #   py3 = y1*a/2*√3 = y1*a√3/2

    x1_val, y1_val = 18, 14

    # 旧代码计算（e1 = -a/2, e2 = a√3/2）
    old_px2 = x1_val * A
    old_px3 = old_px2 + y1_val * (-A / 2)
    old_py3 = 0 - y1_val * (A * np.sqrt(3) / 2)

    # TopoPath 数值化
    path = (TopoPath.builder(A)
            .start(0, 0).move('x1', 'c').turn(120).move('y1', 'along')
            .build(param_values={'x1': x1_val, 'y1': y1_val}))

    new_px2 = path.xy[1, 0]
    new_px3 = path.xy[2, 0]
    new_py3 = path.xy[2, 1]

    # px 应完全一致
    assert abs(new_px2 - old_px2) < 1e-10, f"px2 不一致: new={new_px2}, old={old_px2}"
    assert abs(new_px3 - old_px3) < 1e-10, f"px3 不一致: new={new_px3}, old={old_px3}"
    print(f"  px2: TopoPath={new_px2:.6f}, 旧代码={old_px2:.6f} ✓")
    print(f"  px3: TopoPath={new_px3:.6f}, 旧代码={old_px3:.6f} ✓")

    # py3 符号相反（旧代码用 -y1*e2，TopoPath 120°方向 dy 为正）
    # 这是拐弯方向定义的差异，用户可用 turn(240) 得到旧代码方向
    print(f"  py3: TopoPath={new_py3:.6f}, 旧代码={old_py3:.6f} (符号相反，拐弯方向定义差异)")
    print(f"  提示：旧代码拐弯方向对应 turn(240)，TopoPath 默认 turn(120)")

    # 验证 turn(240) 与旧代码 py3 一致
    path240 = (TopoPath.builder(A)
               .start(0, 0).move('x1', 'c').turn(240).move('y1', 'along')
               .build(param_values={'x1': x1_val, 'y1': y1_val}))
    assert abs(path240.xy[2, 1] - old_py3) < 1e-10, \
        f"turn(240) 的 py3 应与旧代码一致: {path240.xy[2,1]} vs {old_py3}"
    print(f"  turn(240) py3={path240.xy[2,1]:.6f} 与旧代码完全一致 ✓")

    print("[OK] 测试14: 符号路径与旧代码参数化方式一致")


# ============================================================
# 测试 15：符号路径无 param_values 时的行为
# ============================================================
def test_symbolic_without_param_values():
    """符号路径不提供 param_values 时：CST 表达式正常，数值计算应报错。"""
    path = (TopoPath.builder(A)
            .start(0, 0)
            .move('x1', 'c')
            .build())  # 不提供 param_values

    assert path.has_symbols
    print(f"  符号坐标: {path.lattice_symbolic}")

    # CST 表达式应正常工作（不需要数值）
    px, py = TopoPath.lattice_to_cst_expr(0, 'x1')
    assert px == 'x1*a'
    print(f"  CST表达式正常: p2=({px},{py})")

    # 数值计算应报错
    try:
        _ = path.xy
        assert False, "无 param_values 时访问 xy 应报错"
    except RuntimeError as e:
        assert 'param_values' in str(e), f"错误信息应包含 'param_values': {e}"
        print(f"  访问 xy 正确报错: {e}")

    try:
        _ = path.lattice
        assert False, "无 param_values 时访问 lattice 应报错"
    except RuntimeError as e:
        assert 'param_values' in str(e)
        print(f"  访问 lattice 正确报错: {e}")

    try:
        _ = path.get_bounding_box()
        assert False, "无 param_values 时 get_bounding_box 应报错"
    except RuntimeError as e:
        assert 'param_values' in str(e)
        print(f"  get_bounding_box 正确报错")

    print("[OK] 测试15: 符号路径无 param_values 时行为正确")


# ============================================================
# 测试 16：多边形顶点绕向必须为逆时针（CCW）
# ============================================================
def _signed_area_numeric(pts, param_values):
    """把 CST 表达式顶点列表数值化并计算有向面积（>0 表示 CCW）。

    仅支持本测试用到的形式：'<num>' 或 '<param><op><num>' 与 '常量*参数'，
    以及 'pNx'/'pNy' 这类直接以参数名出现的项。
    """
    import re

    def ev(token):
        expr = str(token)
        # 纯参数名
        if expr in param_values:
            return float(param_values[expr])
        # 形如 '18+1'、'0-1'、'-1'
        if re.fullmatch(r'-?\d+(\.\d+)?([+-]\d+(\.\d+)?)?', expr):
            return eval(expr)  # noqa: S307 - 仅测试内部使用，输入受控
        # 形如 'p2y+e2' / 'p2y-e2'
        m = re.fullmatch(r'(\w+)([+-])(\w+)', expr)
        if m:
            left = param_values.get(m.group(1), re.fullmatch(r'-?\d+(\.\d+)?', m.group(1)) and float(m.group(1)))
            right = param_values.get(m.group(3), re.fullmatch(r'-?\d+(\.\d+)?', m.group(3)) and float(m.group(3)))
            return left + float(right) if m.group(2) == '+' else left - float(right)
        raise AssertionError(f"测试无法解析的表达式: {expr!r}")

    coords = [(ev(p[0]), ev(p[1])) for p in pts]
    area = 0.0
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def test_polygon_winding_is_ccw():
    """
    基板与 VPC 区域多边形必须都是逆时针（CCW，有向面积 > 0）。

    背景：CST 的 ExtrudeCurve 沿多边形法向拉伸，绕向决定拉伸方向（CCW→+z，CW→−z）。
    若为 CW，实体在 z 上会与其它部件差一个 h，布尔求交得空集且不报错。
    这是一个曾经真实存在的缺陷，故用测试钉住。
    """
    a = A
    p1 = TopoPath.builder(a, name='p').start(0, -1).move(19, 'c').build()
    p2 = (TopoPath.builder(a, name='p')
          .start(0, -1).move(19, 'c').turn(120).move(14, 'along').build())

    for label, path in (('直波导', p1), ('120°天线', p2)):
        # 由 CST 表达式反推数值参数： p<i>x / p<i>y
        pv = {'a': a, 'e2': a * (3 ** 0.5) / 2}
        for i, (r, c) in enumerate(path.lattice):
            px, py = path.lattice_to_cst_expr(r, c)
            pv[f'p{i + 1}x'] = eval(px.replace('sqr(3)', str(3 ** 0.5)).replace('*a', f'*{a}'))  # noqa: S307
            pv[f'p{i + 1}y'] = eval(py.replace('sqr(3)', str(3 ** 0.5)).replace('*a', f'*{a}'))  # noqa: S307

        for name, pts in (
            ('build_substrate_polygon', path.build_substrate_polygon()),
            ("build_vpc_area_polygon('upper')", path.build_vpc_area_polygon(side='upper')),
            ("build_vpc_area_polygon('lower')", path.build_vpc_area_polygon(side='lower')),
        ):
            area = _signed_area_numeric(pts, pv)
            assert area > 0, (
                f"{label} {name} 顶点绕向为顺时针（有向面积 {area:.6g} < 0），"
                "会导致 ExtrudeCurve 沿 −z 拉伸、与其它部件差一个 h"
            )
            print(f"  [OK] {label} {name}: 有向面积 {area:.6g} > 0 (CCW)")

    print("[OK] 测试16: 所有区域多边形顶点绕向均为逆时针（CCW）")


# ============================================================
# 主入口：直接运行时执行所有测试
# ============================================================
if __name__ == '__main__':
    print("=" * 60)
    print("TopoPath 单元测试")
    print("=" * 60)
    test_directions_mapping()
    test_turn_rotation()
    test_straight_waveguide_path()
    test_120degree_antenna_path()
    test_cst_expr_0_18()
    test_cst_expr_14_4()
    test_consistency_with_path_loc_to_xy()
    test_bounding_box_and_array_range()
    test_substrate_polygon_vertices()
    test_invalid_inputs()
    test_symbolic_operations()
    test_symbolic_straight_waveguide()
    test_symbolic_120_antenna()
    test_symbolic_vs_old_code()
    test_symbolic_without_param_values()
    test_polygon_winding_is_ccw()
    print("=" * 60)
    print("全部 16 项测试通过！")
    print("=" * 60)
