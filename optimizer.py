import numpy as np
import matplotlib.pyplot as plt 
import matplotlib.patches as patches
from tri_lib import *
# from cst_solver import setup, result
from hexlib import HexLib, HexGridVisualizer
import os

# ====================== 1. 参数初始化 ======================

# 遗传算法参数
# GA = {
#     "StartFlag": 0,          # 是否从断点继续：1=是，0=否
#     "Gen_No": 4,             # 种群数量
#     "Gen_Length": 3,        # 种群长度（X方向像素数）
#     "Gen_Width": 5,         # 种群宽度（Y方向像素数）
#     "mut_prob": 0.3,         # 变异概率
#     "cross_prob": 0.8,       # 交叉概率
#     "tol": 1e-6,             # 收敛阈值
#     "max_iter": 20           # 最大迭代次数
# }
# ====================== 2. 种群初始化 ======================
# 随机生成初始种群（0-1矩阵，阈值0.2）
def pop_init(GA,per=0.2):
    pop = np.random.rand(GA["Gen_Length"], GA["Gen_Width"], GA["Gen_No"])
    pop[pop >= per] = 1
    pop[pop < per] = 0
    fi = np.zeros((GA["Gen_No"], GA["max_iter"]))  # 保存每代适应度
    all_pop = np.zeros((GA["Gen_Length"], GA["Gen_Width"], GA["Gen_No"], GA["max_iter"]))  # 保存所有种群
    all_prob = np.zeros((GA["Gen_No"], GA["max_iter"]))  # 保存选择概率
    return pop,fi,all_pop,all_prob

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
    选择操作：替换适应度差的个体（原MATLAB逻辑：保留前N优，替换后N差）
    :param pop: 当前种群 (Gen_Length, Gen_Width, Gen_No)
    :param fitness: 当前适应度 (Gen_No, 1)
    :return: 选择后的种群
    """
    pop=x.copy()  # 避免修改原种群
    # 计算选择概率（适应度归一化）
    prob = fitness / np.sum(fitness)
    # 排序：从小到大（适应度越小越优）
    sorted_idx = np.argsort(prob)
    # 原MATLAB逻辑：取前2优、后3差，用优的替换差的（需匹配Gen_No=4）
    far_idx = sorted_idx[-3:]  # 适应度差的3个个体索引
    bet_idx = sorted_idx[:2]   # 适应度优的2个个体索引

    # 替换操作（原MATLAB中for up=1:3）
    for up in range(3):
        if up < len(bet_idx):
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
    pop=x.copy()  # 避免修改原种群
    """保存当前迭代的种群到文件"""
    for n in range(1, ga["Gen_No"] + 1):
        pop_file = f'Iter_{iter_count}_POP.txt'
        pop_dir = os.path.join(base_path, str(iter_count), str(n))
        os.makedirs(pop_dir, exist_ok=True)
        pop_path = os.path.join(pop_dir, pop_file)
        np.savetxt(pop_path, pop[:, :, n-1], delimiter='\t')
    # 保存当前迭代数（断点）
    np.savetxt(os.path.join(base_path, 'Break.txt'), [iter_count], delimiter='\t')
    
# ===================== 5. 计算适应度 =====================

def calculate_fitness_single(s11_data, s21_data,s11_target,s21_target, freq_min=200, freq_max=1000):
    """
    单个个体的适应度计算（直接接收S11、S21数据，返回适应度值）
    :param s11_data: S11参数数据，二维数组（行数≥freq_max，列数=2，格式[频率, S11值]）
    :param s21_data: S21参数数据，二维数组（行数≥freq_max，列数=2，格式[频率, S21值]）
    :param s11_target: S11目标数据
    :param s21_target: S21目标数据
    :param freq_min: 计算起始频率点（默认200，与原逻辑一致）
    :param freq_max: 计算结束频率点（默认1000，与原逻辑一致）
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
        freq = s11_row[0]  # 取出当前行的频率值（可用于日志/调试）
        s11_value = s11_row[1]
        s21_value = s21_row[1]
        
        # 原逻辑：(S11-4)^2/2 + (S21-2)^2/2
        s11_error = (s11_value - (s11_target)) ** 2
        s21_error = (s21_value - (s21_target)) ** 2
        fit_sum += 0.5 * s11_error + 0.5 * s21_error
    
    # 返回单个个体的适应度值
    return fit_sum



from matplotlib.patches import RegularPolygon
import ezdxf
from ezdxf.addons.drawing import matplotlib as drawing
from ezdxf.addons.drawing.config import Configuration
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

def create_hexagon_polygon(center, cell_width):
    """创建一个六边形多边形"""
    xc, yc = center
    angles = np.linspace(0, 2*np.pi, 7)[:-1] + np.pi/6  # 旋转30度使六边形平顶
    points = [(xc + cell_width * np.cos(angle), 
                yc + cell_width * np.sin(angle)) for angle in angles]
    return Polygon(points)

def save_to_dxf(intersected_hexagons, filename="hex_grid.dxf"):
    """将六边形网格保存为DXF文件"""
    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()
    # 添加图层
    doc.layers.new(name="HexGrid", dxfattribs={"color": 1})  # 红色
    for polygon in intersected_hexagons:
        if polygon.geom_type == 'Polygon':
            # 获取多边形边界点
            coords = list(polygon.exterior.coords)
            # 创建闭合的多段线
            points = [(x, y, 0) for x, y in coords[:-1]]  # 忽略重复的最后一个点
            if len(points) >= 3:
                msp.add_lwpolyline(points, dxfattribs={"layer": "HexGrid"})
        elif polygon.geom_type == 'MultiPolygon':
            # 处理多个多边形的情况
            for poly in polygon.geoms:
                coords = list(poly.exterior.coords)
                points = [(x, y, 0) for x, y in coords[:-1]]
                if len(points) >= 3:
                    msp.add_lwpolyline(points, dxfattribs={"layer": "HexGrid"})
    doc.saveas(filename)
    print(f"DXF文件已保存: {filename}")
    
def read_and_display_dxf_matplotlib(filename="hex_grid.dxf"):
    """使用matplotlib读取并显示DXF文件"""
    try:
        doc = ezdxf.readfile(filename)
        msp = doc.modelspace()
        fig, ax = plt.subplots(figsize=(12, 10))
        # 提取所有线条
        for entity in msp.query("LWPOLYLINE"):
            points = list(entity.get_points())
            x_coords = [p[0] for p in points]
            y_coords = [p[1] for p in points]
            # 闭合多边形
            x_coords.append(x_coords[0])
            y_coords.append(y_coords[0])
            ax.plot(x_coords, y_coords, 'b-', linewidth=1.5)
        # 设置图形属性
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
        ax.set_xlabel('X (mm)', fontsize=12)
        ax.set_ylabel('Y (mm)', fontsize=12)
        ax.set_title(f'DXF文件: {filename}\n六边形网格', fontsize=14)
        plt.tight_layout()
        plt.show()
    except Exception as e:
        print(f"读取DXF文件时出错: {e}")