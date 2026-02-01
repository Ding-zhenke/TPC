import numpy as np
import matplotlib.pyplot as plt 
import matplotlib.patches as patches
from tri_lib import *
from cst_solver import setup, result

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

# 砖块参数（拓扑结构基本单元）
BrickSet = {
    "material": "Gold",      # 材料
    "x_min": 0.09,           # X起始坐标
    "y_min": -0.5,           # Y起始坐标
    "z_min": -0.025,         # Z起始坐标
    "z_max": -0.026,         # Z结束坐标
    "minsize": 0.02,         # 最小单元尺寸（mm）
}

# 镜像变换参数
MirrorSet = {
    "Flag": 1,               # 是否镜像：1=是，0=否
    "X": 1, "Y": 0, "Z": 0,  # 镜像平面法向量
    "CenterX": 0, "CenterY": 0, "CenterZ": 0,  # 镜像中心
}

# 平移变换参数
TranslateSet = {
    "Flag": 1,               # 是否平移：1=是，0=否
    "X": 1, "Y": 0, "Z": 0,  # 平移向量
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
# ====================== 2. 种群初始化 ======================
# 随机生成初始种群（0-1矩阵，阈值0.2）
pop = np.random.rand(GA["Gen_Length"], GA["Gen_Width"], GA["Gen_No"])
pop[pop >= 0.2] = 1
pop[pop < 0.2] = 0

# ====================== 3. 可视化单个种群 ======================
iter_count=1
n_count=1
from hexlib import HexLib, HexGridVisualizer
HEX_SIZE=1
col_range=(0, 6)
row_range=(0, 5)
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
# for n_count in range(GA["Gen_No"]):
#     # plot_single_pop(pop[:, :, n_count], iter_count, n_count)
pop_flattern=pop[:, :, 0].flatten()
for i in range(len(grid)):
    # hex_coord=visualizer.hex_lib.roffset_from_cube(-1,hex_coord)
    # print(hex_coord)
    hex_coord=grid[i]
    visualizer.set_hex_color(hex_coord, 'blue' if pop_flattern[i] == 1 else 'red')

visualizer.draw()
