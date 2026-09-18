# -*- coding: utf-8 -*-
"""
面向拓扑优化的遗传算法算子与种群可视化
========================================
本模块是 MATLAB 版本 ``遗传算法/{MAIN,F_SIMULATE,Slover,Export}.m`` 的 Python 移植，
**不依赖 CST**：只包含种群算子、种群落盘、拓扑结构可视化与基于 S 参数的适应度计算。

``GA`` 是一个 dict，约定键如下（由调用方提供，模块内不再依赖全局变量）::

    GA = {
        "StartFlag":  0,     # 是否从断点继续：1=是，0=否（当前算子未读取）
        "Gen_No":     4,     # 种群个体数
        "Gen_Length": 3,     # 个体长度（行数）
        "Gen_Width":  5,     # 个体宽度（列数）
        "mut_prob":   0.3,   # 变异概率
        "cross_prob": 0.8,   # 交叉概率
        "tol":        1e-6,  # 收敛阈值（当前算子未读取）
        "max_iter":   20,    # 最大迭代次数
    }

.. warning::
    ``StartFlag`` 与 ``tol`` 目前不被任何算子读取；``selection()`` 的
    「保留 2 优 / 替换 3 差」是硬编码的，仅在 ``Gen_No == 4`` 时成立。
    这些是本模块尚未清理的移植遗留，改参数前请先看对应函数说明。

@author: PC
"""

import os

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import AutoMinorLocator

from mesh_grid.hex_grid import HexGridVisualizer, HexLib
from mesh_grid.tri_grid import *  # noqa: F401,F403 - 保持与旧脚本一致的通配导入

# ====================== 1. 参数初始化 ======================

# 默认 GA 参数字典（调用方可直接改字段）
GA = {
    "StartFlag": 0,          # 是否从断点继续：1=是，0=否
    "Gen_No": 4,             # 种群数量
    "Gen_Length": 3,         # 种群长度（X方向像素数）
    "Gen_Width": 5,          # 种群宽度（Y方向像素数）
    "mut_prob": 0.3,         # 变异概率
    "cross_prob": 0.8,       # 交叉概率
    "tol": 1e-6,             # 收敛阈值
    "max_iter": 20           # 最大迭代次数
}


# ====================== 2. 种群初始化 ======================
# 随机生成初始种群（0-1矩阵，阈值0.2）
def pop_init(GA, per=0.2):
    """
    随机初始化种群。

    :param GA: dict, GA 参数字典（需含 Gen_Length/Gen_Width/Gen_No/max_iter）
    :param per: float, 二值化阈值，默认 0.2（大于等于该值取 1）
    :return: (pop, fi, all_pop, all_prob)
        pop — (Gen_Length, Gen_Width, Gen_No) 的 0/1 种群
        fi — (Gen_No, max_iter) 每代适应度
        all_pop — (Gen_Length, Gen_Width, Gen_No, max_iter) 全部历史种群
        all_prob — (Gen_No, max_iter) 选择概率
    """
    pop = np.random.rand(GA["Gen_Length"], GA["Gen_Width"], GA["Gen_No"])
    pop[pop >= per] = 1
    pop[pop < per] = 0
    fi = np.zeros((GA["Gen_No"], GA["max_iter"]))  # 保存每代适应度
    all_pop = np.zeros((GA["Gen_Length"], GA["Gen_Width"], GA["Gen_No"], GA["max_iter"]))  # 保存所有种群
    all_prob = np.zeros((GA["Gen_No"], GA["max_iter"]))  # 保存选择概率
    return pop, fi, all_pop, all_prob


def plot_single_pop(pop, iter_count, n_count, ga=None,
                    save_flag=0, save_path="", dpi=300, show=True):
    """
    绘制单个个体的矩形拓扑（1=蓝色，0=红色）。

    旧版本直接读取模块级全局 ``GA``，一旦该全局不存在就抛 ``NameError``；
    现改为显式 ``ga`` 参数，``None`` 时按 ``pop`` 的形状推断行列数。

    :param pop: ndarray, (Gen_Length, Gen_Width) 的 0/1 拓扑
    :param iter_count: int, 代数（仅用于标题与文件名）
    :param n_count: int, 个体编号（仅用于标题与文件名）
    :param ga: dict/None, GA 参数字典；None 时用 pop.shape 推断
    :param save_flag: int, 1 时保存 PNG
    :param save_path: str, PNG 保存目录（save_flag=1 时必填）
    :param dpi: int, 保存分辨率
    :param show: bool, 是否 plt.show()（批量绘图时应设 False）
    :return: matplotlib Figure 对象
    """
    from mesh_grid.plotting import configure_chinese_font
    configure_chinese_font()
    if ga is None:
        ga = {"Gen_Length": pop.shape[0], "Gen_Width": pop.shape[1]}
    n_row = ga["Gen_Length"]
    n_col = ga["Gen_Width"]

    fig, ax = plt.subplots(1, 1, figsize=(n_col * 0.8, n_row * 0.8))
    for i in range(n_row):
        for j in range(n_col):
            # 矩形左下角坐标（j,i），宽度和高度均为1（网格状）
            # 注意：matplotlib坐标j是横轴（列），i是纵轴（行），与矩阵索引一致
            rect = patches.Rectangle(
                (j, i), 1, 1,  # 坐标(x,y)，宽w，高h
                linewidth=0.5,  # 矩形边框宽度（细边框区分网格）
                edgecolor='black',  # 边框颜色
                facecolor='blue' if pop[i, j] == 1 else 'red'  # 填充色：1=蓝，0=红
            )
            ax.add_patch(rect)
    # 设置坐标轴
    ax.set_xlim(0, n_col)  # 横轴范围：0到列数
    ax.set_ylim(0, n_row)  # 纵轴范围：0到行数
    ax.set_xticks(np.arange(0, n_col + 1, 1))  # 横轴刻度间隔1
    ax.set_yticks(np.arange(0, n_row + 1, 1))  # 纵轴刻度间隔1
    ax.grid(True, linewidth=0.3, color='gray', linestyle='-')  # 网格线（辅助查看）
    ax.invert_yaxis()  # 反转y轴，使矩阵第0行显示在顶部（符合视觉习惯）
    # 设置标题和标签
    ax.set_title(f'第{iter_count}代 第{n_count}个个体拓扑结构', fontsize=14, pad=20)
    ax.set_xlabel('Gen_Width（列）', fontsize=12)
    ax.set_ylabel('Gen_Length（行）', fontsize=12)
    # 调整布局，避免标签被裁剪
    plt.tight_layout()
    if show:
        plt.show()
    if save_flag == 1:
        # 构造保存文件名
        img_name = f"Iter_{iter_count}_No_{n_count}_pop.png"
        full_img_path = os.path.join(save_path, img_name)
        # 保存图片，关闭画布（避免内存占用）
        plt.savefig(full_img_path, dpi=dpi, bbox_inches='tight')
        plt.close(fig)
        print(f"单个个体拓扑图已保存：{full_img_path}")
    return fig


def single_hex_visualization(HEX_SIZE, col_range, row_range, pop):
    """
    用六边形网格可视化单个个体（1=蓝色，0=白色）。

    :param HEX_SIZE: float, 六边形尺寸
    :param col_range: tuple, 列范围 (start, end)
    :param row_range: tuple, 行范围 (start, end)
    :param pop: ndarray, (行, 列) 的 0/1 拓扑
    :return: None
    """
    visualizer = HexGridVisualizer(
            hex_size=HEX_SIZE,
            orientation="pointy",
            origin=(0, 0)
        )
    # 生成正六边形网格
    grid_hexes = visualizer.hex_lib.create_staggered_grid(col_range, row_range)
    visualizer.set_grid(grid_hexes)
    #六边形网格
    grid=visualizer.grid_hexes
    visualizer.set_coord_type('offset_q')
    pop_flattern=pop.flatten()
    for i in range(len(grid)):
        hex_coord=grid[i]
        visualizer.set_hex_color(hex_coord, 'blue' if pop_flattern[i] == 1 else 'white')
    visualizer.draw()

# ====================== 3. 可视化单个种群 ======================
# iter_count=1
# n_count=1
# #控制示那个
# hex1=1
# if hex1==0:
#     for i in range(len(pop[0,0,:])):
#         plot_single_pop(pop[:,:,i], iter_count, i+1, save_flag=0)
# else:
#     HEX_SIZE=1
#     col_range=(0, 6)
#     row_range=(0, 5)
#     for i in range(len(pop[0,0,:])):
#         single_hex_visualization(HEX_SIZE,col_range,row_range,pop[:,:,i])
# ===================== 4. 遗传操作（选择+交叉+变异） =====================
def selection(x, fitness):
    """
    选择操作：用适应度优的个体替换适应度差的个体。

    :param x: ndarray, 当前种群 (Gen_Length, Gen_Width, Gen_No)
    :param fitness: ndarray, 当前适应度 (Gen_No,)
    :return: (pop, prob) — 替换后的种群副本与归一化选择概率

    .. warning::
        「保留 2 优 / 替换 3 差」是从 MATLAB 原逻辑直接搬来的**硬编码**，
        只有在 ``Gen_No == 4`` 时才自洽。其它种群规模下行为未定义，请先改成
        按比例（如前 50% 优个体）再使用。
    """
    pop = x.copy()  # 避免修改原种群
    # 计算选择概率（适应度归一化）
    prob = fitness / np.sum(fitness)
    # 排序：从小到大（适应度越小越优）
    sorted_idx = np.argsort(prob)
    # 原MATLAB逻辑：取前2优、后3差，用优的替换差的（需匹配Gen_No=4）
    far_idx = sorted_idx[-3:]  # 适应度差的3个个体索引
    bet_idx = sorted_idx[:2]   # 适应度优的2个个体索引

    # 替换操作（原MATLAB中for up=1:3）
    for up in range(min(3, len(far_idx), len(bet_idx))):
        pop[:, :, far_idx[up]] = pop[:, :, bet_idx[up]]
    return pop, prob

def crossover(GA, x):
    """
    交叉操作：随机交叉点交换两个个体的基因
    :param pop: 当前种群 (Gen_Length, Gen_Width, Gen_No)
    :param cross_prob: 交叉概率
    :return: 交叉后的种群
    """
    pop=x.copy()  # 避免修改原种群
    # 遍历偶数索引（m=1,3,... 对应MATLAB中1:2:Gen_No）
    for m in range(0, GA["Gen_No"]-1, 2):
        if np.random.rand() < GA["cross_prob"]:
            # 随机选交叉点（X/Y方向）
            cross_i = np.random.randint(1, GA["Gen_Length"]-1)
            cross_j = np.random.randint(1, GA["Gen_Width"]-1)
            # 交换交叉点后的基因
            temp = pop[cross_i:, cross_j:, m].copy()
            pop[cross_i:, cross_j:, m] = pop[cross_i:, cross_j:, m+1]
            pop[cross_i:, cross_j:, m+1] = temp
    return pop

def mutation(GA,x):
    """
    变异操作：随机翻转基因位（0→1 或 1→0）
    :param pop: 当前种群 (Gen_Length, Gen_Width, Gen_No)
    :param mut_prob: 变异概率
    :return: 变异后的种群
    """
    pop=x.copy()  # 避免修改原种群
    for m in range(GA["Gen_No"]):
        if np.random.rand() < GA["mut_prob"]:
            # 随机选变异点
            mut_i = np.random.randint(0, GA["Gen_Length"]-1)
            mut_j = np.random.randint(0, GA["Gen_Width"]-1)
            # 翻转基因
            pop[mut_i, mut_j, m] = 1 - pop[mut_i, mut_j, m]
    return pop

def save_population(base_path, x, ga, iter_count):
    """
    保存当前迭代的种群到 ``<base_path>/<iter>/<n>/Iter_<iter>_POP.txt``。

    同时在 ``<base_path>/Break.txt`` 写入当前迭代数，供 ``StartFlag`` 断点续算使用。

    :param base_path: str, 根目录
    :param x: ndarray, 种群 (Gen_Length, Gen_Width, Gen_No)
    :param ga: dict, GA 参数字典（需含 Gen_No）
    :param iter_count: int, 当前迭代数
    :return: None
    """
    pop = x.copy()  # 避免修改原种群
    # 文件名不依赖循环变量，循环外算一次即可（旧版在循环内重复计算）
    pop_file = f'Iter_{iter_count}_POP.txt'
    for n in range(1, ga["Gen_No"] + 1):
        pop_dir = os.path.join(base_path, str(iter_count), str(n))
        os.makedirs(pop_dir, exist_ok=True)
        pop_path = os.path.join(pop_dir, pop_file)
        np.savetxt(pop_path, pop[:, :, n - 1], delimiter='\t')
    # 保存当前迭代数（断点）
    np.savetxt(os.path.join(base_path, 'Break.txt'), [iter_count], delimiter='\t')


# ===================== 5. 计算适应度 =====================

def calculate_fitness_single(s11_data, s21_data, s11_target, s21_target,
                             freq_min=200, freq_max=1000, plot=False):
    """
    单个个体的适应度计算（直接接收 S11、S21 数据，返回适应度值）。

    FIFO 顺序：先按频率范围筛选，再累加加权误差平方和
    ``0.5*(S11-S11目标)² + 0.5*(S21-S21目标)²``。

    :param s11_data: S11参数数据，二维数组（行数≥freq_max，列数=2，格式[频率, S11值]）
    :param s21_data: S21参数数据，二维数组（行数≥freq_max，列数=2，格式[频率, S21值]）
    :param s11_target: S11目标数据
    :param s21_target: S21目标数据
    :param freq_min: 计算起始频率点（默认200，与原逻辑一致）
    :param freq_max: 计算结束频率点（默认1000，与原逻辑一致）
    :param plot: bool, 是否绘制对比图。**默认 False** ——
        旧版每次评估都无条件 ``plt.figure()/plt.show()``，
        在遗传算法循环里会为每个个体弹一次图并把性能拖垮。
    :return: 该个体的适应度值（误差平方和，值越小越优）
    """
    # 初始化误差平方和
    fit_sum = 0.0

    # 核心逻辑：根据第一列的频率值筛选数据，再计算误差
    # 步骤1：先筛选出S11中频率在范围内的数据行
    valid_s11_mask = (s11_data[:, 0] >= freq_min) & (s11_data[:, 0] <= freq_max)
    valid_s11 = s11_data[valid_s11_mask]

    # 步骤2：同理筛选S21（如果S21和S11频率完全一致，可只筛选一次）
    valid_s21_mask = (s21_data[:, 0] >= freq_min) & (s21_data[:, 0] <= freq_max)
    valid_s21 = s21_data[valid_s21_mask]

    # 步骤3：遍历筛选后的有效数据，计算误差平方和
    # 确保S11和S21的有效数据行数一致（否则需校验）
    for s11_row, s21_row in zip(valid_s11, valid_s21):
        s11_value = s11_row[1]
        s21_value = s21_row[1]

        # 原逻辑：(S11-目标)^2/2 + (S21-目标)^2/2
        s11_error = (s11_value - s11_target) ** 2
        s21_error = (s21_value - s21_target) ** 2
        fit_sum += 0.5 * s11_error + 0.5 * s21_error

    # 绘图仅在显式要求时执行（GA 循环内默认不画图）
    if plot:
        plt.figure(figsize=(8, 6))
        plt.plot(valid_s11[:, 0], 20 * np.log10(np.abs(valid_s11[:, 1])),
                 label='S11 Data', marker='o')
        plt.plot(valid_s21[:, 0], 20 * np.log10(np.abs(valid_s21[:, 1])),
                 label='S21 Data', marker='x')
        plt.axhline(y=20 * np.log10(np.abs(s11_target)), color='blue',
                    linestyle='--', label='S11 Target')
        plt.axhline(y=20 * np.log10(np.abs(s21_target)), color='orange',
                    linestyle='--', label='S21 Target')
        plt.title('S11 and S21 Data with Targets')
        plt.xlabel('Frequency (GHz)')
        plt.ylabel('S-parameter')
        plt.ylim(-20, 0)
        plt.minorticks_on()
        # y轴每2个主刻度之间显示4个小刻度
        plt.gca().yaxis.set_minor_locator(AutoMinorLocator(4))
        plt.legend()
        plt.show()

    # 返回单个个体的适应度值
    return fit_sum

# DXF 导出功能已迁移至 mesh_grid.hex_grid
# 请改用 from mesh_grid.hex_grid import create_hex_polygon, save_to_dxf, read_and_display_dxf_matplotlib
