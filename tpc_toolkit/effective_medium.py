# -*- coding: utf-8 -*-
"""
等效介质与六边形晶格几何工具
============================
纯解析工具，**不依赖 CST**，可在任意装有 numpy / matplotlib 的环境中导入。

包含：
  - 透镜相位计算
  - 正六边形面积（由边长或晶格常数给出）
  - 两种介电材料的等效介电常数（体积加权平均）
  - 硅基空气孔结构的 Maxwell-Garnett 型等效介电常数
  - 介电常数 → 折射率

.. note::
    原先本模块在顶层 ``from scipy import signal`` / ``from tqdm import tqdm``
    以及从 ``mesh_grid.hex_grid`` 导入一批符号，但这些符号**一个都没被用到**。
    由于 ``tpc_toolkit/__init__.py`` 会导入本模块，这些死导入把 scipy、tqdm、
    ezdxf、shapely 变成了硬依赖（``import tpc_toolkit`` 直接 ImportError），
    与「scipy/geometry 是可选依赖」的打包声明矛盾。现已全部移除。

@author: PC
"""

import matplotlib.pyplot as plt
import numpy as np

# === 在这里设置中文字体 ===
plt.rcParams['font.sans-serif'] = ['SimHei']  # macOS 用 'Heiti TC'，Linux 可尝试 'WenQuanYi Micro Hei'
plt.rcParams['axes.unicode_minus'] = False    # 解决负号 '-' 显示为方块的问题


def cal_phi(r, fp, lambda1):
    """
    计算透镜上某点相对焦点的相位。

    相位按 ``phi = 2π/λ · (√(r²+fp²) − fp)`` 计算，再取模 2π 并转成角度。

    :param r: float or ndarray, 该点到光轴的径向距离（与 lambda1、fp 同单位）
    :param fp: float, 焦距
    :param lambda1: float, 工作波长
    :return: float or ndarray, 相位（度），取值 [0, 360)
    """
    # 该点的相位
    phi = (2 * np.pi / lambda1) * (np.sqrt(r ** 2 + fp ** 2) - fp)
    phi = np.mod(phi, 2 * np.pi)  # 将相位限制在0到2π之间
    phi = np.rad2deg(phi)  # 转换为角度
    return phi


"""
六边形相关的工具函数
"""

def hex_area_from_side(a: float) -> float:
    """
    已知六边形的边长 a，计算正六边形的面积。

    正六边形可分成 6 个边长为 a 的等边三角形，
    每个等边三角形面积 = (√3/4) * a²
    总面积 = 6 * (√3/4) * a² = (3√3/2) * a²

    Parameters
    ----------
    a : float
        正六边形的边长

    Returns
    -------
    float
        正六边形的面积
    """
    return (3 * np.sqrt(3) / 2) * a ** 2


def hex_area_from_lattice(L: float) -> float:
    """
    已知六边形晶格常数 L，计算正六边形的面积。

    在六边形蜂窝晶格中，相邻六边形中心之间的距离（晶格常数 L）与边长 a 的关系：
        L = √3 * a  →  a = L / √3
    代入面积公式：
        Area = (3√3/2) * (L/√3)² = (√3/2) * L²

    Parameters
    ----------
    L : float
        六边形晶格常数（相邻六边形中心之间的距离）

    Returns
    -------
    float
        正六边形的面积
    """
    return (np.sqrt(3) / 2) * L ** 2


def effective_permittivity(ep1: float, s1: float, ep2: float, s2: float) -> float:
    """
    计算两种介电材料的等效介电常数（体积加权平均）。

    对于两种介电材料，按面积（或体积）占比进行加权平均：
        ε_eff = (ε1 * s1 + ε2 * s2) / (s1 + s2)

    这是最简单的等效介质近似。

    Parameters
    ----------
    ep1 : float
        第一种材料的介电常数
    s1 : float
        第一种材料的面积
    ep2 : float
        第二种材料的介电常数
    s2 : float
        第二种材料的面积

    Returns
    -------
    float
        等效介电常数
    """
    return (ep1 * s1 + ep2 * s2) / (s1 + s2)

def ep_cal_air(ep1,s1,ep2,s2):
    """
    计算两种介电材料的等效介电常数（体积加权平均），其中第1种材料为空气（ε1=1）。

    对于两种介电材料，按面积（或体积）占比进行加权平均：
        ε_eff = (ε1 * s1 + ε2 * s2) / (s1 + s2)
    第一种材料为空气，ε1=1，第二种是硅，ε2=11.9，在硅上挖空气孔时，s1是空气孔的面积，s2是整个晶格的面积。 
    Parameters
    ----------     
    ep1 : float
        第一种材料的介电常数（这里为1，表示空气）
    s1 : float
        第一种材料的面积
    ep2 : float
        第二种材料的介电常数
    s2 : float
        第二种晶格的面积

    Returns
    -------
    float
        等效介电常数
    """
    ratio=s1/s2
    delta_ep=ep1-ep2
    sigma_ep=ep2+ep1
    
    return ep2*(sigma_ep+delta_ep*ratio)/(sigma_ep-delta_ep*ratio)

def permittivity_to_refractive_index(ep):
    """
    由介电常数计算折射率。

    对于非磁性材料（μ = 1），折射率 n = √ε。

    Parameters
    ----------
    ep : float or array_like
        介电常数（必须为非负值）

    Returns
    -------
    float or ndarray
        折射率 n
    """
    return np.sqrt(ep)