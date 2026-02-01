import numpy as np
import matplotlib.pyplot as plt 
import matplotlib.patches as patches
from tri_lib import *
# from cst_solver import setup, result
from hexlib import HexLib, HexGridVisualizer
import os

# ====================== 1. 参数初始化 ======================
# 路径参数
base_path = r"D:\GX\\"  # 根路径（需根据实际修改）
FileName_CST = "FILTER.cst"  # 原始CST文件

# 遗传算法参数
GA = {
    "StartFlag": 0,          # 是否从断点继续：1=是，0=否
    "Gen_No": 4,             # 种群数量
    "Gen_Length": 10,        # 种群长度（X方向像素数）
    "Gen_Width": 14,         # 种群宽度（Y方向像素数）
    "mut_prob": 0.3,         # 变异概率
    "cross_prob": 0.8,       # 交叉概率
}
# 迭代控制参数
tol = 1e-6                  # 收敛阈值
max_iter = 100              # 最大迭代次数
fi = np.zeros((GA["Gen_No"], max_iter))  # 保存每代适应度
all_pop = np.zeros((GA["Gen_Length"], GA["Gen_Width"], GA["Gen_No"], max_iter))  # 保存所有种群
all_prob = np.zeros((GA["Gen_No"], max_iter))  # 保存选择概率

def plot_single_pop(pop, iter_count, n_count, save_flag=0, save_path="", dpi=300):
    #这是矩形的
    fig, ax = plt.subplots(1, 1, figsize=(GA["Gen_Width"]*0.8, GA["Gen_Length"]*0.8))
    for i in range(GA["Gen_Length"]):
        for j in range(GA["Gen_Width"]):
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
    ax.set_xlim(0, GA["Gen_Width"])  # 横轴范围：0到列数
    ax.set_ylim(0, GA["Gen_Length"])  # 纵轴范围：0到行数
    ax.set_xticks(np.arange(0, GA["Gen_Width"]+1, 1))  # 横轴刻度间隔1
    ax.set_yticks(np.arange(0, GA["Gen_Length"]+1, 1))  # 纵轴刻度间隔1
    ax.grid(True, linewidth=0.3, color='gray', linestyle='-')  # 网格线（辅助查看）
    ax.invert_yaxis()  # 反转y轴，使矩阵第0行显示在顶部（符合视觉习惯）
    # 设置标题和标签
    ax.set_title(f'第{iter_count}代 第{n_count}个个体拓扑结构', fontsize=14, pad=20)
    ax.set_xlabel('Gen_Width（列）', fontsize=12)
    ax.set_ylabel('Gen_Length（行）', fontsize=12)
    # 调整布局，避免标签被裁剪
    plt.tight_layout()
    plt.show()
    if save_flag==1:
        # 构造保存文件名
        img_name = f"Iter_{iter_count}_No_{n_count}_pop.png"
        full_img_path = os.path.join(save_path, img_name)
        # 保存图片，关闭画布（避免内存占用）
        plt.savefig(full_img_path, dpi=dpi, bbox_inches='tight')
        plt.close(fig)
        print(f"单个个体拓扑图已保存：{full_img_path}")
def single_hex_visualization(HEX_SIZE,col_range,row_range,pop):
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
        visualizer.set_hex_color(hex_coord, 'blue' if pop_flattern[i] == 1 else 'red')
    visualizer.draw()



# ====================== 2. 种群初始化 ======================
# 随机生成初始种群（0-1矩阵，阈值0.2）
pop = np.random.rand(GA["Gen_Length"], GA["Gen_Width"], GA["Gen_No"])
pop[pop >= 0.2] = 1
pop[pop < 0.2] = 0

# ====================== 3. 可视化单个种群 ======================
iter_count=1
n_count=1


#控制显示那个
hex1=1
if hex1==0:
    for i in range(len(pop[0,0,:])):
        plot_single_pop(pop[:,:,i], iter_count, i+1, save_flag=0)
else:
    HEX_SIZE=1
    col_range=(0, 6)
    row_range=(0, 5)
    for i in range(len(pop[0,0,:])):
        single_hex_visualization(HEX_SIZE,col_range,row_range,pop[:,:,i])
# ===================== 4. 遗传操作（选择+交叉+变异） =====================
def selection(pop, fitness):
    """
    选择操作：替换适应度差的个体（原MATLAB逻辑：保留前N优，替换后N差）
    :param pop: 当前种群 (Gen_Length, Gen_Width, Gen_No)
    :param fitness: 当前适应度 (Gen_No, 1)
    :return: 选择后的种群
    """
    # 计算选择概率（适应度归一化）
    prob = fitness / np.sum(fitness)
    # 排序：从小到大（适应度越小越优）
    sorted_idx = np.argsort(prob[:, 0])
    # 原MATLAB逻辑：取前2优、后3差，用优的替换差的（需匹配Gen_No=4）
    far_idx = sorted_idx[-3:]  # 适应度差的3个个体索引
    bet_idx = sorted_idx[:2]   # 适应度优的2个个体索引

    # 替换操作（原MATLAB中for up=1:3）
    for up in range(3):
        if up < len(bet_idx):
            pop[:, :, far_idx[up]] = pop[:, :, bet_idx[up]]
    return pop, prob

def crossover(pop, cross_prob):
    """
    交叉操作：随机交叉点交换两个个体的基因
    :param pop: 当前种群 (Gen_Length, Gen_Width, Gen_No)
    :param cross_prob: 交叉概率
    :return: 交叉后的种群
    """

    # 遍历偶数索引（m=1,3,... 对应MATLAB中1:2:Gen_No）
    for m in range(0, GA["Gen_No"]-1, 2):
        if np.random.rand() < cross_prob:
            # 随机选交叉点（X/Y方向）
            cross_i = np.random.randint(1, GA["Gen_Length"]-1)
            cross_j = np.random.randint(1, GA["Gen_Width"]-1)
            # 交换交叉点后的基因
            temp = pop[cross_i:, cross_j:, m].copy()
            pop[cross_i:, cross_j:, m] = pop[cross_i:, cross_j:, m+1]
            pop[cross_i:, cross_j:, m+1] = temp
    return pop

def mutation(pop, mut_prob):
    """
    变异操作：随机翻转基因位（0→1 或 1→0）
    :param pop: 当前种群 (Gen_Length, Gen_Width, Gen_No)
    :param mut_prob: 变异概率
    :return: 变异后的种群
    """
    ga = GAConfig()
    for m in range(GA["Gen_No"]):
        if np.random.rand() < mut_prob:
            # 随机选变异点
            mut_i = np.random.randint(0, GA["Gen_Length"]-1)
            mut_j = np.random.randint(0, GA["Gen_Width"]-1)
            # 翻转基因
            pop[mut_i, mut_j, m] = 1 - pop[mut_i, mut_j, m]
    return pop

def save_population(base_path, pop, ga, iter_count):
    """保存当前迭代的种群到文件"""
    for n in range(1, ga.Gen_No + 1):
        pop_file = f'Iter_{iter_count}_POP.txt'
        pop_dir = os.path.join(base_path, str(iter_count), str(n))
        os.makedirs(pop_dir, exist_ok=True)
        pop_path = os.path.join(pop_dir, pop_file)
        np.savetxt(pop_path, pop[:, :, n-1], delimiter='\t')
    # 保存当前迭代数（断点）
    np.savetxt(os.path.join(base_path, 'Break.txt'), [iter_count], delimiter='\t')
    

# ===================== 5. 计算适应度 =====================

def calculate_fitness_single(s11_data, s12_data, freq_min=200, freq_max=1000):
    """
    单个个体的适应度计算（直接接收S11、S12数据，返回适应度值）
    :param s11_data: S11参数数据，二维数组（行数≥freq_max，列数=2，格式[频率点, S11值]）
    :param s12_data: S12参数数据，二维数组（行数≥freq_max，列数=2，格式[频率点, S12值]）
    :param freq_min: 计算起始频率点（默认200，与原逻辑一致）
    :param freq_max: 计算结束频率点（默认1000，与原逻辑一致）
    :return: 该个体的适应度值（误差平方和，值越小越优）
    """
    # 校验输入数据的有效性（避免频率点不足导致报错）
    if s11_data.shape[0] < freq_max or s12_data.shape[0] < freq_max:
        raise ValueError(f"输入的S11/S12数据行数不足，至少需要{freq_max}行（对应频率点）")
    if s11_data.shape[1] != 2 or s12_data.shape[1] != 2:
        raise ValueError("输入的S11/S12数据必须是二维数组，格式为[频率点, 对应参数值]")
    
    # 初始化适应度总和（误差平方和）
    fit_sum = 0.0
    
    # 遍历指定频率范围，计算误差平方和（与原MATLAB逻辑完全一致）
    for freq in range(freq_min, freq_max + 1):
        # 原逻辑：(S11-4)^2/2 + (S12-2)^2/2
        s11_error = (s11_data[freq, 1] - 4) ** 2
        s12_error = (s12_data[freq, 1] - 2) ** 2
        fit_sum += 0.5 * s11_error + 0.5 * s12_error
    
    # 返回单个个体的适应度值
    return fit_sum