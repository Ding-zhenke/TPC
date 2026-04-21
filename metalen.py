import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from tqdm import tqdm
# === 在这里设置中文字体 ===
plt.rcParams['font.sans-serif'] = ['SimHei'] # macOS 用 'Heiti TC'，Linux 可以尝试 'WenQuanYi Micro Hei'
plt.rcParams['axes.unicode_minus'] = False     # 解决负号 '-' 显示为方块的问题

from hexlib import HexLib, HexGridVisualizer,create_hex_polygon,save_to_dxf,read_and_display_dxf_matplotlib


def cal_phi(r,fp,lambda1):
    #该点的相位
    phi = (2*np.pi/lambda1)*(np.sqrt(r**2+fp**2)-fp)
    phi = np.mod(phi, 2*np.pi)  # 将相位限制在0到2π之间
    phi= np.rad2deg(phi)  # 转换为角度
    return phi