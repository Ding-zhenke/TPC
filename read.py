import numpy as np
import re

def read_s2p_groups(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    # 按参数块分割
    blocks = re.split(r'#Parameters = \{.+?\}\n', content)[1:]  # 去掉开头空字符串
    param_matches = re.findall(r'#Parameters = \{(.+?)\}', content)
    
    # 提取每组数据
    data_list = []
    param_strs = []
    freq = None
    for block, param_str in zip(blocks, param_matches):
        # 使用loadtxt读取数据块
        data_block = np.loadtxt(block.splitlines(), dtype=float)
        if freq is None:
            freq = data_block[:, 0]  # 频率列，所有块相同
        data_list.append(data_block[:, 1])  # 只取S21列
        
        # 解析参数
        params = dict(item.split('=') for item in param_str.split(';') if '=' in item)
        # 转换数值
        for k, v in params.items():
            try:
                params[k] = float(v) if '.' in v or 'e' in v else int(v)
            except:
                pass
        param_strs.append(params)
    
    # 转换为numpy数组 (频率点数, 组数)
    data = np.column_stack([freq] + data_list)  # shape: (n_freq, n_blocks)
    
    # 找出变化的参数
    all_keys = set().union(*[p.keys() for p in param_strs])
    param_strings = []
    for p in param_strs:
        changed = []
        for key in all_keys:
            val = p.get(key)
            if val is not None and not all(val == other.get(key) for other in param_strs):
                changed.append(f"{key}={val}")
        param_strings.append(", ".join(changed) if changed else "all_params_same")
    
    return data, np.array(param_strings)
# 使用示例
# data_arr, diff_params = read_cst_s2p_groups('AB-s21.txt')
# print(f"数据形状: {data_arr.shape}")  # (n_freq, n_blocks)
# print("不同的参数组合:")
# for i, params in enumerate(diff_params):
#     print(f"组{i+1}: {params}")

def filter_by_frequency(data, freq_range, atol=1e-6):
    """
    按频率范围筛选数据行（保留所有参数组）。
    
    参数:
        data: (n_freq, 1+n_blocks)
        freq_range: tuple (fmin, fmax) 或 float（单个频率点）
        atol: 单个频率点匹配容差
    
    返回:
        filtered_data: 筛选后的数据
        param_strings: 原始参数标签数组（不变）
    """
    freq = data[:, 0]
    if isinstance(freq_range, (int, float)):
        idx = np.argmin(np.abs(freq - freq_range))
        if np.abs(freq[idx] - freq_range) <= atol:
            return data[idx:idx+1, :], None  # param_strings 不变，由调用者自行保留
        else:
            raise ValueError(f"频率 {freq_range} 未找到，最近值为 {freq[idx]}")
    else:
        fmin, fmax = freq_range
        mask = (freq >= fmin) & (freq <= fmax)
        return data[mask, :], None

def filter_parameters_by_condition(data, param_strings, freq_range, threshold, comparison='less', mode='any'):
    """
    筛选出在指定频率范围内满足阈值条件的参数组（列），并返回对应的数据和参数标签。
    
    参数:
        data: (n_freq, 1+n_blocks)
        param_strings: (n_blocks,)
        freq_range: tuple (fmin, fmax)
        threshold: 阈值(dB)
        comparison: 'less' 或 'greater'
        mode: 'any' - 只要有一个频率点满足条件即保留该参数组
              'all' - 所有频率点都满足条件才保留该参数组
    
    返回:
        filtered_data: 筛选后的数据，第一列频率保持不变，后续列为满足条件的参数组
        filtered_params: 对应的参数标签数组
    """
    freq = data[:, 0]
    s_params = data[:, 1:]  # (n_freq, n_blocks)
    
    fmin, fmax = freq_range
    freq_mask = (freq >= fmin) & (freq <= fmax)
    s_in_range = s_params[freq_mask, :]  # (n_freq_in_range, n_blocks)
    
    if comparison == 'less':
        condition = s_in_range < threshold
    elif comparison == 'greater':
        condition = s_in_range > threshold
    else:
        raise ValueError("comparison 必须是 'less' 或 'greater'")
    
    if mode == 'any':
        keep = np.any(condition, axis=0)
    elif mode == 'all':
        keep = np.all(condition, axis=0)
    else:
        raise ValueError("mode 必须是 'any' 或 'all'")
    
    # 筛选列（保留频率列）
    filtered_data = np.column_stack([data[:, 0], s_params[:, keep]])
    filtered_params = param_strings[keep]
    
    return filtered_data, filtered_params

def find_param_indices(original_params, selected_params):
    """
    找出 selected_params 中的每个元素在 original_params 中的位置索引。
    
    参数:
        original_params: 原始参数标签数组 (n_blocks,)
        selected_params: 筛选后的参数标签数组 (n_selected,)
    
    返回:
        indices: 整数数组，对应 selected_params 在 original_params 中的索引
    """
    # 使用 np.where 和列表推导，保持顺序
    indices = []
    for sel in selected_params:
        # 找到第一个匹配的位置（假设标签唯一）
        idx = np.where(original_params == sel)[0]
        if len(idx) == 0:
            raise ValueError(f"参数标签 '{sel}' 未在原始数组中找到")
        indices.append(idx[0])
    return np.array(indices)