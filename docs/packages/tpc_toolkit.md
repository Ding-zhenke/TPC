# tpc_toolkit —— 独立工具层（不依赖 CST）

`tpc_toolkit/` 是 TPC 分层架构里的**旁路工具层**：收纳一切与「具体电磁仿真软件」无关的
通用算法与数据处理工具——S 参数文本解析、遗传算法算子、等效介质公式。

它的定位只有一句话：**可以在任意 Python 环境里导入，不需要安装 CST Studio Suite**。
因此它是**纯函数库**，不是面向对象的框架：AST 统计结果是
**0 个类、18 个模块级函数**（分布在 3 个子模块中），没有状态、没有会话、没有全局配置。

这也决定了它的使用方式：像用 `numpy` / `scipy` 那样，直接 `from tpc_toolkit.s2p import ...`，
把它接在「仿真前（参数/介质设计）」和「仿真后（结果筛选/优化决策）」两端，
而不是夹在建模流水线中间。

| 项 | 内容 |
|---|---|
| **职责** | S 参数解析与筛选、遗传算法算子与种群落盘、六边形/等效介质公式 |
| **需要 CST** | ❌ 不需要（**并且禁止**引入 CST 依赖，见 §7） |
| **入口** | `from tpc_toolkit import s2p, ga_optimizer, effective_medium`；或直接 `from tpc_toolkit.s2p import read_s2p_groups` |
| **依赖** | numpy、matplotlib（必需）；scipy、shapely、ezdxf（声明为可选，但当前实际是硬依赖，见 §7）；另在模块级导入 `mesh_grid.hex_grid` |
| **被谁依赖** | 库内无其它包依赖它；只有用户脚本 / notebook 使用 |
| **源码位置** | `tpc_toolkit/__init__.py`、`tpc_toolkit/s2p.py`、`tpc_toolkit/ga_optimizer.py`、`tpc_toolkit/effective_medium.py` |
| **公开 API** | AST 统计：0 个类、**18 个模块级函数**：`s2p` 4 个 + `ga_optimizer` 8 个 + `effective_medium` 6 个 |
| **原文件** | 由根目录散落的 `read.py` / `optimizer.py` / `metalen.py` 提升而来（见 §1） |
| **当前阶段** | 阶段 5（工具层）成型中：函数已集中成包，但内部仍有若干未修缺陷（见 §6） |

---

## 1. 为什么单独成包

这三个模块原先以**根目录散落脚本**的形式存在于仓库顶层：

| 旧位置 | 现位置 | 内容 |
|---|---|---|
| `read.py` | `tpc_toolkit/s2p.py` | CST 导出的 s2p 分组文本解析与筛选 |
| `optimizer.py` | `tpc_toolkit/ga_optimizer.py` | 遗传算法算子、种群落盘、拓扑可视化、S 参数适应度 |
| `metalen.py` | `tpc_toolkit/effective_medium.py` | 六边形面积、等效介电常数、折射率换算 |

把它们提升为独立子包，解决的是三类问题：

1. **依赖污染**：这些代码只是拿 numpy 做数值、拿 matplotlib 画图，
   却被放在与 `cst_solver` 同级的根目录里，读者很容易误以为「用它们就得有 CST」。
   独立成包后，`pyproject.toml` 里它是唯一一个**不需要 CST** 的旁路包，
   可以在服务器/纯数据环境里单独使用。
2. **打包边界**：根目录散落的 `.py` 不会被 `setuptools` 收进发行版；
   变成子包后由 `pyproject.toml` 的 `packages.find` 统一纳管（`tpc_toolkit*`）。
3. **归属判定**：按
   [`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md) §2 的改动归属表，
   「仿真前后数据处理、优化算法」明确归 `tpc_toolkit/`，不再需要每次讨论「这个函数放哪」。

**放在这里 vs 不放在这里**：

| 内容 | 归属 | 判定依据 |
|---|---|---|
| S 参数文本解析、GA 算子、等效介质公式 | `tpc_toolkit/` | 不需要 CST 也能跑 |
| 晶格坐标、路径 DSL、六边形网格与 DXF | `mesh_grid/` | 通用晶格数学，必须保持纯计算 |
| 从 CST 工程里读结果（`result` / `read_1D`…） | `cst_solver/` | 必须与 CST 的结果对象对话 |

> 旧名仍有残留引用：`../../skills/user/tpc-usage.md` 里还写着「配套模块：`read.py`（`read_s2p_groups` 批量读 s2p）」，
> 按 WORKFLOW §9 的交叉引用检查，应把这处旧路径一并更新为 `tpc_toolkit/s2p.py`。

---

## 2. 三个模块总览

| 模块 | 原文件名 | 职责 | 依赖 | 公开函数数 |
|---|---|---|---|---|
| `tpc_toolkit.s2p` | `read.py` | 解析 CST 导出的 s2p「参数分组」文本；按频率范围 / 阈值条件筛选参数组；把筛选结果映射回原始列号 | `numpy`、`re`（标准库） | **4** |
| `tpc_toolkit.ga_optimizer` | `optimizer.py` | 遗传算法算子（种群初始化 / 选择 / 交叉 / 变异）、种群分代落盘、0-1 拓扑结构可视化（矩形与六边形两种）、S 参数适应度计算 | `numpy`、`matplotlib`（`pyplot` + `patches` + `AutoMinorLocator`）、`mesh_grid.tri_grid`（未使用）、`mesh_grid.hex_grid`（用 `HexGridVisualizer`） | **8** |
| `tpc_toolkit.effective_medium` | `metalen.py` | 六边形面积（由边长 / 由晶格常数）、两种等效介电常数公式、介电常数→折射率、透镜上某点的补偿相位 | `numpy`、`matplotlib`（设中文字体 rcParams）、`scipy.signal`（未使用）、`tqdm`（未使用）、`mesh_grid.hex_grid`（5 个符号全部未使用） | **6** |
| **合计** | — | — | — | **18** |

`tpc_toolkit/__init__.py` 会**一次性导入全部三个子模块**：

```python
from tpc_toolkit import effective_medium, ga_optimizer, s2p
```

所以 `import tpc_toolkit` 就等于把 numpy / matplotlib / scipy / tqdm 以及
`mesh_grid.hex_grid`（连带 ezdxf、shapely）全部拉起来——想省掉这些开销时，
应直接导入子模块（`from tpc_toolkit.s2p import read_s2p_groups`），
不过注意 **Python 仍会先执行包的 `__init__.py`**，因此在当前实现下
「只导入 s2p 就能避开 matplotlib/scipy」是做不到的（见 §6、§7）。

---

## 3. `tpc_toolkit.s2p` —— S 参数解析

源码：`tpc_toolkit/s2p.py`（143 行），4 个函数。

### 3.1 它解析的是什么格式

CST 在**参数扫描导出**时，可以把多个参数组合的曲线写进同一个文本文件，
每一组曲线前面带一行「参数标记」，后面紧跟该组的数值数据：

```
#Parameters = {l1=0.157625;l2=0.084875}
300.0    -12.31
300.5    -12.55
...
#Parameters = {l1=0.120000;l2=0.084875}
300.0     -9.87
300.5    -10.02
...
```

`read_s2p_groups()` 对这层结构的解析方式是：

1. `re.split(r'#Parameters = \{.+?\}\n', content)[1:]` —— 按标记行切分，
   丢掉切分产生的首个空串，得到**每个参数组的数据块**；
2. `re.findall(r'#Parameters = \{(.+?)\}', content)` —— 再单独把 `{}` 里的参数串抓出来；
3. 两者用 `zip()` 一一配对（数量天然一致）；
4. 每个数据块交给 `np.loadtxt(block.splitlines(), dtype=float)` 读成二维数组。

由于 `open(filepath, 'r')` 是文本模式、默认启用通用换行，CRLF 会被归一成 `\n`，
所以上面那两个「以 `}\n` 结尾」的正则对 Windows 行尾的文件同样成立。

**隐含约定（用之前先确认）**：

| 约定 | 后果 |
|---|---|
| 只会取每个数据块的**第 2 列**（索引 1）作为「S21」 | 导出时必须恰好是「频率 + 幅值」两列；若是 `(freq, S11, S21)` 之类的多列格式，取到的是 S11，不会报错 |
| 频率列只从**第一个块**取，然后复用到所有块 | 各组必须频率采样完全一致；否则列会静默错位（MATLAB 旧注释里也记过「CST 相同采样点数仍可能出现 1~2 点差异」的坑） |
| 每个块必须能整体 `np.loadtxt` 成浮点数组 | 块里混入表头/非数值行会直接抛异常 |
| 数值转换启发式：含 `.` 或小写 `e` 才走 `float()`，否则走 `int()`，异常被 `except: pass` 吞掉 | `1E-3` 这类**大写 E** 的科学计数法不会被转成数值，会原样留成字符串 |
| 「变化参数」标签的键来自 `set` 迭代 | 同一个键集合在不同进程里顺序可能不同（字符串哈希随机化），标签字符串的**键顺序不稳定** |

### 3.2 函数速查

#### `read_s2p_groups(filepath)`

读取文件，返回 `(data, param_strings)`。

| 项 | 内容 |
|---|---|
| 参数 | `filepath`：s2p 分组文本路径 |
| 返回 `data` | `numpy.ndarray`，形状 **`(n_freq, 1 + n_blocks)`**：第 0 列是频率，其后每列是一个参数组的 S21 |
| 返回 `param_strings` | `numpy.ndarray`（字符串数组），长度 `n_blocks`；每个元素是**该组与其它组不同的参数**拼成的标签（如 `'l1=0.157625, l2=0.084875'`）；若该组参数与所有组都相同，则写死为 `'all_params_same'` |

#### `filter_by_frequency(data, freq_range, atol=1e-6)`

按频率筛选**行**，所有参数组一起保留。

| 项 | 内容 |
|---|---|
| `freq_range` | `tuple (fmin, fmax)` → 返回落在闭区间内的所有行；或单个 `int/float` → 取**最接近**的频率点 |
| `atol` | 单点模式下允许的偏差；`abs(freq[idx] - freq_range) > atol` 时抛 `ValueError` |
| 返回 | `(filtered_data, None)` |

> ⚠ **docstring 与实现不一致**：docstring 写第二个返回值是「原始参数标签数组（不变）」，
> 但两条分支都 `return ..., None`。也就是说这个函数**不会**把标签带出来，
> 调用方必须自己保留 `param_strings`。

#### `filter_parameters_by_condition(data, param_strings, freq_range, threshold, comparison='less', mode='any')`

按阈值条件筛选**列**（参数组）。

| 参数 | 说明 |
|---|---|
| `data` | `(n_freq, 1 + n_blocks)`，同上 |
| `param_strings` | `(n_blocks,)` 标签数组 |
| `freq_range` | `(fmin, fmax)` 闭区间，先按频率切出行 |
| `threshold` | 阈值（dB） |
| `comparison` | `'less'` → `s < threshold`；`'greater'` → `s > threshold`；其它值抛 `ValueError` |
| `mode` | `'any'` → 区间内**任意**一个频点满足即保留该组；`'all'` → **所有**频点都满足才保留；其它值抛 `ValueError` |

| 返回 | 内容 |
|---|---|
| `filtered_data` | `(n_freq, 1 + n_kept)`，**频率列保持完整**（不裁剪），后续列只留被选中的组 |
| `filtered_params` | `(n_kept,)`，对应的标签 |

#### `find_param_indices(original_params, selected_params)`

把「筛选后的标签」映射回「原始数组里的列号」。

| 项 | 内容 |
|---|---|
| 参数 | `original_params` `(n_blocks,)`；`selected_params` `(n_selected,)` |
| 返回 | `numpy.ndarray`（整数），长度 `n_selected`，元素是 `selected_params` 每一项在 `original_params` 中的**首次**匹配下标 |
| 异常 | 任一项在原始数组里找不到 → `ValueError` |

> 注意返回的是**列号（从 0 开始，对应 `data[:, 1:]` 的列）**，不是 `data` 的整体列号；
> 取回原始数据时要补偿频率列：`data[:, 1:][:, idx]`。

### 3.3 完整示例

```python
import numpy as np
from tpc_toolkit.s2p import (
    read_s2p_groups,
    filter_by_frequency,
    filter_parameters_by_condition,
    find_param_indices,
)

# ① 读入 CST 扫描导出的分组文本
data, labels = read_s2p_groups(r'D:\sim\AB-s21.txt')
print(data.shape)        # (n_freq, 1 + n_blocks)
print(labels[:3])        # ['l1=0.157625, l2=0.084875' ... 'all_params_same' ...]

# ② 只看 300~380 GHz 这一段（第二项恒为 None，标签要自己留着）
band, _ = filter_by_frequency(data, (300, 380))

# ③ 找出「整个频段内 S21 都低于 -15 dB」的参数组
kept, kept_labels = filter_parameters_by_condition(
    data, labels, (300, 380), threshold=-15,
    comparison='less', mode='all',
)
print(kept.shape, kept_labels.shape)

# ④ 回到原始矩阵的列号，做后续对比
idx = find_param_indices(labels, kept_labels)
kept_from_original = data[:, 1:][:, idx]
np.testing.assert_allclose(kept_from_original, kept[:, 1:])

# ⑤ 单频点取值（最接近 350 GHz 的那一行，容差 1e-6）
one, _ = filter_by_frequency(data, 350.0)
```

---

## 4. `tpc_toolkit.ga_optimizer` —— 遗传算法

源码：`tpc_toolkit/ga_optimizer.py`（228 行），8 个函数。
它是 `archive/matlab/MAIN.m` 等四个 MATLAB 文件的 **Python 移植版**（provenance 见 §4.3）。

### 4.1 `GA` 字典（当前被注释掉，必须由调用方提供）

`ga_optimizer.py:12-21` 有一整块**被注释掉**的 `GA = {...}` 定义。
它不是一个可用的默认值，而是一份「字段说明 + 示例取值」：所有算子都要求调用方
自己在 notebook / 脚本里造出这个 dict 再传进来。

| 键 | 被代码读取的位置 | 注释块里的值 | `MAIN.m` 里的对应 | 说明 |
|---|---|---|---|---|
| `StartFlag` | **无人读取** | `0` | `GA.StartFlag=0` | MATLAB 里是「断点续算」总开关；Python 版**未移植**该逻辑（`save_population()` 仍在写 `Break.txt`，但没有任何代码读它） |
| `Gen_No` | `pop_init` / `crossover` / `mutation` / `save_population` | `4` | `4` | 种群数量。`selection()` 内部**硬编码依赖 `Gen_No == 4`** |
| `Gen_Length` | `pop_init` / `plot_single_pop` / `crossover` / `mutation` | `3` | `10` | 基因「行」数（优化区域 X 向像素数） |
| `Gen_Width` | 同上 | `5` | `14` | 基因「列」数（优化区域 Y 向像素数） |
| `mut_prob` | `mutation` | `0.3` | `0.3` | 变异概率（逐个体判定一次） |
| `cross_prob` | `crossover` | `0.8` | `0.8` | 交叉概率（逐对判定一次） |
| `tol` | **无人读取** | `1e-6` | `tol = 1e-6`（**独立变量，不在 `GA` 里**） | 收敛阈值；Python 版没有实现停止判据 |
| `max_iter` | `pop_init` | `20` | `max_iter = 100`（独立变量） | 最大迭代次数，只用于预分配 `fi / all_pop / all_prob` 的形状 |

> 注释块里的 `Gen_Length=3 / Gen_Width=5 / max_iter=20` 是演示值；
> 真正的旧代码 `MAIN.m` 用的是 `10 / 14 / 100`。移植时把 MATLAB 的独立变量
> `tol`、`max_iter` 一并塞进了 `GA` 字典，这个「字典化」是 Python 版的新设计。

### 4.2 函数速查

#### `pop_init(GA, per=0.2)`

随机生成初始种群并预分配记录数组。

| 项 | 内容 |
|---|---|
| 返回 | `(pop, fi, all_pop, all_prob)` 四元组 |
| `pop` | `(Gen_Length, Gen_Width, Gen_No)` 浮点数组，元素为 `0.0/1.0`：`np.random.rand(...) >= per` 置 1，否则置 0 |
| `fi` | `(Gen_No, max_iter)` 全零，用于保存每代适应度 |
| `all_pop` | `(Gen_Length, Gen_Width, Gen_No, max_iter)` 全零，用于保存所有种群 |
| `all_prob` | `(Gen_No, max_iter)` 全零，用于保存选择概率 |

#### `plot_single_pop(pop, iter_count, n_count, save_flag=0, save_path="", dpi=300)`

把**单个个体**的 0-1 拓扑画成矩形网格图（`1` 蓝、`0` 红），y 轴反转以符合矩阵视觉习惯。

| 项 | 内容 |
|---|---|
| 返回 | `None` |
| `save_flag` | `1` 时才 `plt.savefig(save_path/Iter_{iter_count}_No_{n_count}_pop.png)` 并 `plt.close(fig)` |
| ⚠ 缺陷 | 函数体直接读**模块级全局 `GA`**（`GA["Gen_Width"]` / `GA["Gen_Length"]`），而模块里那份 `GA` 已被注释掉 → 按现状调用会 `NameError`；且 `plt.show()` 在 `save_flag` 判据**之前**被无条件调用（见 §6） |

#### `single_hex_visualization(HEX_SIZE, col_range, row_range, pop)`

同一份 0-1 基因的**六边形**版本可视化。

| 项 | 内容 |
|---|---|
| 返回 | `None`（直接 `visualizer.draw()`） |
| 实现 | 建 `HexGridVisualizer(hex_size=HEX_SIZE, orientation="pointy", origin=(0, 0))` → `create_staggered_grid(col_range, row_range)` 生成错位六边形网格 → `set_grid()` → `set_coord_type('offset_q')` → 把 `pop.flatten()` 的第 `i` 个元素映射成第 `i` 个六边形的颜色（`1` → `'blue'`，否则 `'white'`） |
| 隐含耦合 | 依赖 `len(grid) >= pop.size` 且**展平顺序与网格顺序一致**；`pop` 形状与 `col_range/row_range` 不匹配时不会报错，只会画错 |

#### `selection(x, fitness)`

选择：把适应度**最差**的几个个体替换成**最好**的几个（原 MATLAB 逻辑：保留前 N 优、替换后 N 差）。

| 项 | 内容 |
|---|---|
| 参数 | `x` `(Gen_Length, Gen_Width, Gen_No)`；`fitness` `(Gen_No,)`，**越小越优**（误差平方和） |
| 返回 | `(pop, prob)` —— 注意返回的是**元组**，与 `crossover` / `mutation` 只返回种群不同 |
| 算法 | `prob = fitness / fitness.sum()` → `np.argsort(prob)` 升序 → 最差 3 个 `sorted_idx[-3:]`、最优 2 个 `sorted_idx[:2]` → 循环 3 次，把优的**复制覆盖**到差的个体上 |
| ⚠ 缺陷 | 3 / 2 这两个数字是照抄 MATLAB 的 `for up=1:3`，**只在 `Gen_No == 4` 时成立**；换种群规模会静默给出错误选择（见 §6） |

#### `crossover(GA, x)`

交叉：按相邻成对（`m` 与 `m+1`）随机交换一个子块。

| 项 | 内容 |
|---|---|
| 返回 | `pop`（新数组，`x` 不被修改） |
| 循环 | `for m in range(0, GA["Gen_No"] - 1, 2)` —— 对应 MATLAB 的 `1:2:Gen_No` |
| 判定 | `np.random.rand() < GA["cross_prob"]` 才交叉 |
| 交叉点 | `cross_i ∈ [1, Gen_Length-2]`、`cross_j ∈ [1, Gen_Width-2]`（`np.random.randint` 上界不含） |
| 操作 | 交换 `pop[cross_i:, cross_j:, m]` 与 `pop[cross_i:, cross_j:, m+1]` |

#### `mutation(GA, x)`

变异：逐个个体判定，命中则**翻转一个基因位**。

| 项 | 内容 |
|---|---|
| 返回 | `pop`（新数组） |
| 判定 | 对每个 `m in range(Gen_No)`：`np.random.rand() < GA["mut_prob"]` |
| 变异点 | `mut_i ∈ [0, Gen_Length-2]`、`mut_j ∈ [0, Gen_Width-2]` |
| 操作 | `pop[mut_i, mut_j, m] = 1 - pop[mut_i, mut_j, m]` |

#### `save_population(base_path, x, ga, iter_count)`

把当前代种群落盘，保持与 MATLAB 完全一致的目录结构（**断点续算的约定格式**）。

| 项 | 内容 |
|---|---|
| 每个个体 | 写入 `<base_path>/<iter_count>/<n>/Iter_<iter_count>_POP.txt`（`n` 从 1 到 `ga["Gen_No"]`），制表符分隔 |
| 断点文件 | 写入 `<base_path>/Break.txt`，内容为当前 `iter_count` |
| 返回 | `None` |

#### `calculate_fitness_single(s11_data, s21_data, s11_target, s21_target, freq_min=200, freq_max=1000)`

单个体适应度：在频率区间内累加 S11 / S21 与目标值的加权平方误差。

| 项 | 内容 |
|---|---|
| `s11_data` / `s21_data` | 二维数组，**第 0 列是频率**，第 1 列是 S 参数值 |
| `freq_min` / `freq_max` | 频率筛选条件（`>= freq_min` 且 `<= freq_max`） |
| 返回 | `float`：`Σ [0.5·(S11 - s11_target)² + 0.5·(S21 - s21_target)²]`，**越小越优** |
| 对应旧代码 | `F_SIMULATE.m` 里的 `0.5*(S11-4)^2 + 0.5*(S12-2)^2` → 把硬编码的 `4`、`2` 提成 `s11_target` / `s21_target` 形参 |
| ⚠ 缺陷 | 函数体内**无条件** `plt.figure()` + 绘图 + `plt.show()`；放进 GA 主循环等于**每个个体开一次图**，会把优化速度拖垮（见 §6） |

### 4.3 MATLAB 移植来源（provenance）

Python GA 模块是 `archive/matlab/` 下四个脚本的移植。
`archive/matlab/` 保留的是原始 MATLAB 代码（GBK 编码），**不要**把它当成可运行入口：

| MATLAB 文件 | 内容 | Python 对应 | 移植状态 |
|---|---|---|---|
| `MAIN.m` | 参数初始化（`GA.*`、`BrickSet.*`、`MirrorSet.*`、`TranslateSet.*`）、初始种群生成、主循环（适应度 → 选择 → 交叉 → 变异 → 落盘）、`Break.txt` 断点 | 注释掉的 `GA = {...}`、`pop_init`、`selection`、`crossover`、`mutation`、`save_population` | ✅ 已移植算子与落盘；❌ 断点续算（`StartFlag`）、收敛停止（`tol`）、主循环本身未移植（由调用方自己写） |
| `F_SIMULATE.m` | 逐个体查缓存 `S11_n.txt` / `S12_n.txt`，缺则调 `Slover` 仿真；目标函数 `0.5*(S11-4)^2 + 0.5*(S12-2)^2`；结果写 `Iter_i_F.txt` | `calculate_fitness_single` | 🟡 只移植了目标函数；缓存复用、批量遍历、结果落盘未移植 |
| `Slover.m` | 通过 `actxserver('CSTStudio.application')` 打开 `.cst`、删旧结果、按基因位逐个画 `Brick`、可选 `Translate` / `Mirror` 变换、`SaveAs`、启动求解器 | 无（Python 侧这是 `cst_solver` + `topo_modeler/builders` 的职责） | ❌ 未移植（COM 自动化被库的 CST 封装取代） |
| `Export.m` | 选中 `1D Results\S-Parameters\S1,1`（S11 用 `PlotView 'magnituded'`）与 `S2,1`（S12 用 `'magnitudedB'`），`ASCIIExport` 导出文本，再 `readmatrix` 读回；异常时用 1024×1 的零矩阵兜底 | 无（由 `cst_solver` 的结果导出承担）；读回后的文本正是 `s2p.py` 处理的格式 | ❌ 未移植 |

**仍然残留的 MATLAB 习惯（移植时要留意）**：

1. **`Gen_No=4` 硬编码**：`selection()` 的 `[-3:]` / `[:2]` 直接对应 MATLAB 的 `FAR=probs(nn-2)`、`BET=probs(2)` 与 `for up=1:3`。
2. **按采样点序号 vs 按频率值筛选**：`F_SIMULATE.m` 用**行下标** `Sample_MIN=200 : Sample_MAX=1000`（并预留 1002 行）；
   Python 的 `calculate_fitness_single` 却是拿 `data[:, 0]` 的**频率值**做 `>= freq_min & <= freq_max`。
   形参名与默认值都沿用旧的 200 / 1000，**物理含义已经不同**，换数据前务必确认单位（GHz）。
3. **量纲混用**：`Export.m` 里 S11 导的是 `magnituded`（线性幅度）、S12 导的是 `magnitudedB`（dB），
   两者量纲本就不同；`F_SIMULATE.m` 又直接拿原始值算 `(x-4)^2`。
   Python 版照搬了「原始值算误差」，同时在 `calculate_fitness_single` 里用 `20*log10(abs(...))` 绘图，
   **同一份数据在误差与绘图两处被当作不同量纲使用**。
4. **S-参数命名**：旧代码导出的是 `S1,2`，Python 形参叫 `s21_data`（同一物理量的两种叫法）。
5. **随机点边界差一格**：MATLAB `randi(Gen_Length-1)` → `1..Gen_Length-1`；
   Python 交叉用 `np.random.randint(1, Gen_Length-1)` → `1..Gen_Length-2`；
   变异用 `np.random.randint(0, Gen_Length-1)` → `0..Gen_Length-2`（比 MATLAB 多出第 0 行）。
6. **`break` 只跳出内层循环**：`MAIN.m` 的停止判据写在 `for nn` 内层，即使满足 `tol` 也只跳出内层；
   Python 侧索性没有实现停止判据。
7. **可视化是逐个体弹窗**（`plot_single_pop` / `calculate_fitness_single` 都无条件 `plt.show()`），
   在 MATLAB 交互式桌面里尚可忍受，搬到批处理式的 Python 优化循环里就是性能杀手。

---

## 5. `tpc_toolkit.effective_medium` —— 等效介质

源码：`tpc_toolkit/effective_medium.py`（139 行），6 个函数。
本模块顶部把 matplotlib 的中文字体设成 `SimHei`、并关掉负号方块问题
（`plt.rcParams` 两行），属于**导入即生效的全局副作用**，调用方需知悉。

### 5.1 公式与推导

#### 六边形面积（由边长）—— `hex_area_from_side(a)`

正六边形可剖成 6 个边长为 `a` 的等边三角形，每个面积 `(√3/4)a²`：

```
Area = 6 · (√3/4) a²  =  (3√3/2) a²
```

返回 `(3 * sqrt(3) / 2) * a**2`。

#### 六边形面积（由晶格常数）—— `hex_area_from_lattice(L)`

蜂窝晶格中「相邻六边形中心距 `L`」与「六边形边长 `a`」满足 `L = √3·a`，即 `a = L/√3`，代入上式：

```
Area = (3√3/2) · (L/√3)²  =  (3√3/2) · (L²/3)  =  (√3/2) L²
```

返回 `(sqrt(3) / 2) * L**2`。

> 两个函数在 `L = √3·a` 时给出**完全相同**的结果——这正是六边形恰好铺满平面的极限
> （此时孔面积 = 元胞面积，填充因子 `f = 1`）。实际用 `hex_area_from_lattice(L)`
> 算的是**三角晶格的元胞面积**：`L` 取相邻孔中心距，`(√3/2)L²` 就是每个孔平均占据的面积。

#### 体积/面积加权平均 —— `effective_permittivity(ep1, s1, ep2, s2)`

```
ε_eff = (ε1·s1 + ε2·s2) / (s1 + s2)
```

最简单的线性（面积或体积占比）加权：`s1`、`s2` 是**两种材料各自的面积**，
两者之和即总面积（注意：`s1` 与 `s2` 是**互不包含**的两块面积）。

#### 空气孔的等效介电常数 —— `ep_cal_air(ep1, s1, ep2, s2)`

实现形式是一个比值型（Maxwell-Garnett 风格）公式：

```
ratio   = s1 / s2
delta   = ep1 - ep2
sigma   = ep2 + ep1
ε_eff   = ep2 · (sigma + delta·ratio) / (sigma - delta·ratio)
```

代入本项目的用材（`ep1 = 1` 空气、`ep2 = 11.9` 硅），`sigma = 12.9`、`delta = -10.9`，
令填充因子 `f = s1/s2`：

```
ε_eff = 11.9 · (12.9 - 10.9·f) / (12.9 + 10.9·f)
```

**两个极限都对**：`f = 0`（无孔）→ `11.9`；`f = 1`（全空气）→ `11.9 · 2.0/23.8 = 1.0`。
`f = 1/3` 时约为 `11.9 · 9.267/16.533 ≈ 6.67`。

> ⚠ **参数约定与 docstring 不符**：docstring 直接复述了线性加权公式
> `ε_eff = (ε1·s1 + ε2·s2)/(s1+s2)`，但实现是上面的比值式。
> 且按 docstring 的说明，`s1` 是**空气孔面积**、`s2` 是**整个晶格面积**（`s2` 已经包含 `s1`），
> 这与 `effective_permittivity()` 里「`s1`、`s2` 是两块互不包含的面积」的约定**不同**，两函数不要混用参数。

#### 介电常数 → 折射率 —— `permittivity_to_refractive_index(ep)`

非磁性材料（`μ = 1`）有 `n = √ε`，返回 `np.sqrt(ep)`；支持标量与 `array_like`。
传入负值时 numpy 会给出 `nan` 并伴随 RuntimeWarning（docstring 已注明必须非负）。

#### 透镜上某点的补偿相位 —— `cal_phi(r, fp, lambda1)`

```python
phi = (2*np.pi/lambda1) * (np.sqrt(r**2 + fp**2) - fp)   # 弧度
phi = np.mod(phi, 2*np.pi)                               # 折回 [0, 2π)
phi = np.rad2deg(phi)                                    # 转成「度」
```

物理含义：把焦点设在轴上距离 `fp` 处，透镜上距轴心 `r` 的点到焦点的斜距为
`√(r² + fp²)`，减去中心点的 `fp` 就是**多走的路径**，乘以 `2π/λ` 即该点相对中心点的相位超前量
——补偿这一相位（把 `2π` 的整数倍折掉）就得到超表面/透镜每个单元该提供的相位。
返回值单位是**度**（`0~360`），不是弧度。

### 5.2 函数速查

| 函数 | 签名 | 返回 |
|---|---|---|
| `cal_phi` | `cal_phi(r, fp, lambda1)` | 相位（**度**，`[0, 360)`） |
| `hex_area_from_side` | `hex_area_from_side(a: float) -> float` | 正六边形面积，`a` 为边长 |
| `hex_area_from_lattice` | `hex_area_from_lattice(L: float) -> float` | 正六边形/元胞面积，`L` 为晶格常数（相邻中心距） |
| `effective_permittivity` | `effective_permittivity(ep1: float, s1: float, ep2: float, s2: float) -> float` | 线性加权的等效介电常数 |
| `ep_cal_air` | `ep_cal_air(ep1, s1, ep2, s2)` | 空气孔型比值公式的等效介电常数（`s2` 为整个晶格面积） |
| `permittivity_to_refractive_index` | `permittivity_to_refractive_index(ep)` | `sqrt(ep)`，标量或数组 |

### 5.3 典型用例：硅上的空气孔

```python
import numpy as np
from tpc_toolkit.effective_medium import (
    hex_area_from_side,
    hex_area_from_lattice,
    ep_cal_air,
    effective_permittivity,
    permittivity_to_refractive_index,
    cal_phi,
)

# ── 几何：三角晶格上的六边形空气孔 ──
L = 0.2425                      # 相邻孔中心距 (mm)，与 TPC 的晶格常数同量级
A_cell = hex_area_from_lattice(L)              # 元胞面积 = (√3/2)L²
A_hole = hex_area_from_side(0.06)              # 边长 0.06 mm 的六边形孔
f = A_hole / A_cell                            # 填充因子
print(f'A_cell={A_cell:.5f} mm², A_hole={A_hole:.5f} mm², f={f:.3f}')

# ── 等效介电常数：注意两个函数的 s1/s2 约定不同 ──
ep_mg = ep_cal_air(1.0, A_hole, 11.9, A_cell)                       # s2 = 整个晶格面积
ep_lin = effective_permittivity(1.0, A_hole, 11.9, A_cell - A_hole)  # s2 = 只含硅的面积
print(f'比值公式 ε={ep_mg:.4f} → n={permittivity_to_refractive_index(ep_mg):.4f}')
print(f'线性加权 ε={ep_lin:.4f} → n={permittivity_to_refractive_index(ep_lin):.4f}')

# ── 极限检查：f=0 应为纯硅 11.9，f=1 应为纯空气 1.0 ──
assert np.isclose(ep_cal_air(1.0, 0.0, 11.9, A_cell), 11.9)
assert np.isclose(ep_cal_air(1.0, A_cell, 11.9, A_cell), 1.0)

# ── 透镜单元相位：λ 用介质中的有效波长 ──
lam0 = 3e8 / 300e9 * 1e3        # 300 GHz 在空气中的波长 = 1.0 mm
lam_eff = lam0 / np.sqrt(ep_mg)
for r in (0.0, 1.5, 3.0):
    print(f'r={r} mm → 补偿相位 {cal_phi(r, 3.0, lam_eff):.1f}°')
```

---

## 6. 已知缺陷

> 表中带 **（本次核查新增）** 的行是本次核对源码时发现、此前未登记的条目；
> 其余为已登记或已明确的问题。修完请按 WORKFLOW §6 同步本文件与
> `docs/next_plan/` 的对应条目。

### 6.1 `ga_optimizer.py`

| 位置 | 问题 | 影响 | 建议修法 |
|---|---|---|---|
| `plot_single_pop()`（`ga_optimizer.py:35-51`） | 函数体读**模块级全局 `GA`**（`GA["Gen_Width"]` / `GA["Gen_Length"]`），但模块里的 `GA` 定义已被注释掉（`:12-21`） | 按现状调用 → `NameError: name 'GA' is not defined` | 把尺寸变成显式形参（如 `plot_single_pop(pop, iter_count, n_count, save_flag=0, save_path="", dpi=300)` 里由 `pop.shape` 推 `Gen_Length/Gen_Width`），或加 `GA=None` 形参并在 `None` 时从 `pop.shape` 推断 |
| `plot_single_pop()`（`:60-61`） | `plt.show()` 在 `if save_flag == 1` **之前**被无条件调用 | 只想存图（`save_flag=1`）的批处理场景会被弹窗阻塞 | 把 `plt.show()` 移入「交互模式」分支或加 `show=True/False` 开关 |
| `calculate_fitness_single()`（`:209-222`） | **每次**适应度评估都 `plt.figure()` → 绘图 → `plt.show()` | 放进 GA 主循环 = 每个个体开一张图：优化速度崩塌、内存堆积，批量跑必然卡死 | 加 `plot=False`（默认关）形参；绘图挪出评估函数，只在需要时对最优个体单独画 |
| `selection()` docstring（`:103-108`） | docstring 写 `:param pop:`、`:param fitness:`、`:return: 选择后的种群`；真实签名是 `selection(x, fitness)`，且实际返回**元组** `(pop, prob)` | 使用者按 docstring 传参/取返回值就会出错（`crossover` / `mutation` 的 docstring 同样写 `pop`，还写了并非形参的 `cross_prob` / `mut_prob`） | 三个算子的 docstring 统一改为真实签名与真实返回类型 |
| `selection()`（`:111-122`） | 「替换 3 个 / 保留 2 个」硬编码，只在 `Gen_No == 4` 时语义正确 **（本次核查新增）** | 换种群规模（如 `Gen_No=8`）时静默按错误比例选择，结果不可信 | 改成由 `Gen_No` 推导的比例（如「最差 ⌈N/2⌉ 个被最优 ⌊N/2⌋ 个按序覆盖」），或至少 `assert GA["Gen_No"] == 4` |
| 全模块 | `GA` 字典被注释掉，**没有任何默认值**；`StartFlag`、`tol` 从未被任何函数读取 **（本次核查新增）** | 每个调用方都要自己重造一份 dict；「断点续算」「收敛停止」两个开关看似存在、实际不生效 | 把 `GA` 提为模块级 `DEFAULT_GA` dict + `make_ga(**overrides)` 工厂；或者要么实现 `StartFlag`/`tol`，要么在 docstring 里明确标注「未实现」 |
| `save_population()`（`:161-171`） | `pop_file = f'Iter_{iter_count}_POP.txt'` 写在循环体内，而它**不依赖** `n`；于是同一个文件名被写进 `base/iter/1/`、`base/iter/2/` … 各个按序号分出的目录 | 磁盘上出现一批同名文件（目录名是唯一区分），排查/搬运时极易混淆；循环内重复计算文件名也是无意义开销 | 把文件名提到循环外；若沿用旧约定必须保持目录结构，建议在文件名里带上序号（`Iter_{i}_POP_{n}.txt`）并在文档里写明格式，或至少写清「同名文件靠目录区分」 |
| `from mesh_grid.tri_grid import *`（`:4`）、`HexLib`（`:5`） **（本次核查新增）** | 通配符导入与 `HexLib` 均未被使用（实际只用了 `HexGridVisualizer`） | 通配符导入污染命名空间、静态检查失效；并把 `mesh_grid.hex_grid` 整包依赖（含 ezdxf/shapely）拉进本模块 | 删掉 `import *` 与 `HexLib`，只保留真正使用的最小导入 |

### 6.2 `effective_medium.py`

| 位置 | 问题 | 影响 | 建议修法 |
|---|---|---|---|
| `:3` `from scipy import signal`；`:4` `from tqdm import tqdm` | **两个 import 都没有被使用**（模块里没有 `signal.*`，也没有 `tqdm(...)`）——docstring 称本包「可在任意装有 numpy / matplotlib 的环境导入」，实际却被这两行绑上了 scipy 与 tqdm | **使 `scipy` 从「可选依赖」变成「硬依赖」**：`pyproject.toml` 把 scipy 放在 `science` extra 里，但只装基础依赖的环境 `import tpc_toolkit` 会直接 `ImportError: scipy`（本机实测：屏蔽 scipy 后导入即失败） | **直接删掉这两行**（确认无其它模块依赖它们的副作用；`tqdm` 在 `pyproject.toml` 里是必装依赖，但本模块确实不用） |
| `:9` `from mesh_grid.hex_grid import HexLib, HexGridVisualizer, create_hex_polygon, save_to_dxf, read_and_display_dxf_matplotlib` **（本次核查新增）** | 一行导入 5 个符号，**一个都没在本模块用到**；而 `mesh_grid.hex_grid.core` 在模块级 `import ezdxf` / `from shapely.geometry import ...` | 同样把可选依赖变成硬依赖：`import tpc_toolkit` 会连带要求 **ezdxf + shapely**（本机实测：屏蔽 ezdxf 后导入即失败），与 `pyproject.toml` 的 `geometry` extra 声明不符 | 删掉这行；将来真要画六边形/DXF 时再在函数内部做**延迟导入** |
| `ep_cal_air()` docstring（`:94-116`） | docstring 复述的是线性加权公式与「按面积加权平均」的措辞，实现却是比值型公式；且 `s2` 的含义（整个晶格面积 vs 单种材料面积）与 `effective_permittivity()` 不一致 **（本次核查新增）** | 使用者按 docstring 选参数会算错等效介电常数（例如把 `s2` 传成「只含硅的面积」） | 把 docstring 改成实现里的公式与两个极限（`f=0 → ep2`、`f=1 → ep1`）说明，并注明 `s1`（孔面积）⊂ `s2`（元胞面积） |

### 6.3 `s2p.py`

| 位置 | 问题 | 影响 | 建议修法 |
|---|---|---|---|
| `filter_by_frequency()` docstring（`:55-67`）与实现（`:72, :78`） | docstring 说返回 `param_strings`（原始参数标签数组），实现两条分支都返回 `None` **（本次核查新增）** | 使用者写 `band, labels = filter_by_frequency(...)` 后拿到 `None`，后续按标签取列会崩 | 要么真的把 `param_strings` 作为形参传进来并原样返回，要么把 docstring 改成「第二项恒为 `None`，标签由调用方自行保留」 |
| `read_s2p_groups()`（`:9`、`:18-21`） | 只取每块的**第 2 列**当 S21，且频率只从第一块取；块数/列数不匹配时不校验 **（本次核查新增）** | 换一种 CST 导出格式（多列 / 不同采样点数）就会静默取错列或错行，结果「看起来正常但是错的」 | 增加列选择形参（`value_col=1`）或对 ≥3 列的情况直接报错；补一条「各组频率必须一致」的校验 |
| `read_s2p_groups()`（`:26-31`） | 数值转换启发式只看 `.` 和**小写** `e`，`int('1E-3')` 抛异常后被 `except: pass` 吞掉 **（本次核查新增）** | 大写 `E` 的科学计数法参数（如 `1E-3`）会原样留成字符串，参与比较/排序时行为诡异 | 改成 `float(v)` 优先、失败再 `int(v)`、再失败保留原串；不要用裸 `except` 吞掉 |
| `read_s2p_groups()`（`:37-45`） | 「变化参数」标签的键顺序来自 `set` 迭代 **（本次核查新增）** | 同一份数据在不同进程里生成的标签字符串键顺序可能不同，做成字典键/文件名时会漂移 | 遍历前把 `all_keys` 排序（`sorted(all_keys)`），保证标签稳定 |
| `:48-53` 注释残留 | 注释里的示例函数名是旧名 `read_cst_s2p_groups`，实际函数叫 `read_s2p_groups` **（本次核查新增）** | 复制示例会得到 `NameError` | 注释里的旧名同步改成 `read_s2p_groups`（或直接删掉这段注释，把示例写进本文件 §3.3） |

### 6.4 包级

| 位置 | 问题 | 影响 | 建议修法 |
|---|---|---|---|
| `tpc_toolkit/__init__.py:28` | 一次性导入全部三个子模块（`from tpc_toolkit import effective_medium, ga_optimizer, s2p`） | 想只用 `s2p`（纯文本解析、只需要 numpy）也会被强制拉起 matplotlib/scipy/ezdxf/shapely；`__init__.py` 先于子模块执行，所以「只导入子模块」也躲不掉 | 把 `__init__.py` 改成惰性导入（`__getattr__` 代理），或至少把重依赖模块的导入下沉到函数内部 |

---

## 7. 依赖说明

### 7.1 声明 vs 实际

| 依赖 | `pyproject.toml` 声明 | 本包实际是否需要 | 说明 |
|---|---|---|---|
| `numpy >= 1.21` | `dependencies`（必装） | ✅ 需要 | 三个子模块全用 |
| `matplotlib >= 3.5` | `dependencies`（必装） | ✅ 需要 | `ga_optimizer` 绘图；`effective_medium` 设 `plt.rcParams`（导入即生效） |
| `tqdm >= 4.60` | `dependencies`（必装） | ⚠ 只在死 import 里出现 | `effective_medium.py:4` 导入后未使用（`mesh_grid/hex_grid/core.py` 也导入了它） |
| `scipy >= 1.7` | `optional-dependencies.science` | ❌ 实际是**硬依赖**（应去掉） | `effective_medium.py:3` 的 `from scipy import signal` 未被使用，但导入即执行 |
| `shapely >= 2.0` | `optional-dependencies.geometry` | ❌ 实际是**硬依赖**（应去掉） | `ga_optimizer.py:5`、`effective_medium.py:9` 在模块级导入 `mesh_grid.hex_grid`，而后者无条件 `import ezdxf` / `from shapely...` |
| `ezdxf >= 1.0` | `optional-dependencies.geometry` | ❌ 实际是**硬依赖**（应去掉） | 同上 |
| `shapely` / `ezdxf` / `scipy` | `optional-dependencies.all` | — | `all` 是「全部可选能力」的聚合 extra，本身不改变上面的结论 |

`geometry` extra 的注释写的是「六边形网格 DXF 导出、GRIN 透镜几何运算」，
`science` 写的是「透镜 KD-tree 加速与信号处理」——也就是说 **`tpc_toolkit` 本来不在这些 extra 的服务范围内**，
它被卷进来纯粹是因为模块级的死 import。

### 7.2 实测结论

本机（Python 3.11.7，numpy / matplotlib / tqdm / scipy / ezdxf / shapely 全部已安装）实测：

```python
import tpc_toolkit          # ✅ 成功（会连带加载 ezdxf、shapely、scipy、tqdm、matplotlib）
print(tpc_toolkit.__all__)  # ['s2p', 'ga_optimizer', 'effective_medium']
```

用一个 import 钩子把某个三方包屏蔽掉之后再导入，可以验证「它到底是不是硬依赖」
（下面是 `importlib` 老式钩子写法，Python 3.11 及更早版本可直接跑）：

```python
import sys

class Block:
    def find_module(self, name, path=None):
        if name == 'scipy' or name.startswith('scipy.'):
            return self
        return None
    def load_module(self, name):
        raise ImportError(name)

sys.meta_path.insert(0, Block())
import tpc_toolkit          # → ImportError: scipy
```

| 屏蔽的包 | 结果 |
|---|---|
| `scipy` | `ImportError: scipy`（来自 `effective_medium.py:3`） |
| `ezdxf` | `ImportError: ezdxf`（来自 `mesh_grid.hex_grid.core`，经 `ga_optimizer.py:5` / `effective_medium.py:9` 触发） |

结论：**当前 `import tpc_toolkit` 实际需要 numpy + matplotlib + tqdm + scipy + ezdxf + shapely 六个三方包**；
把 §6.2 里那两行死 import 删掉之后，才能回到「只需要 numpy + matplotlib」的原始设计目标。
（在那之前，想在裸环境里用 `s2p` 的话，暂时只能把 `s2p.py` 独立拷出去，或先补装 `.[all]`。）

### 7.3 一条硬约定：本包永不导入 CST

- [`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md) §10.5 明确禁止：
  **❌ 在 `tpc_toolkit` 里引入 CST 依赖**；§2 的归属表也把「仿真前后数据处理、优化算法」
  划到「不需要 CST」这一列；§4 的 `tpc_toolkit/` 验收清单第一条就是「不引入 CST 依赖」。
- 现状核查：`tpc_toolkit/` 全目录内**没有任何** `import cst_solver` / `import cst`，
  只有 docstring 与注释里提到 CST（`__init__.py` 的模块说明、`s2p.py:49` 的示例注释）。
- 推论：**不要**为了「顺手读一下 CST 结果」而在本包里 import `cst_solver` 或 `result`；
  需要 CST 结果时，让调用方先用 `cst_solver` 读出来、再喂给本包的纯函数。
- 同理，`mesh_grid` 也必须保持纯计算（WORKFLOW §10.4），所以本包对 `mesh_grid` 的依赖
  只应限于**纯数学/可视化**部分（而且如 §6.2 所示，当前这两处导入连用都没用上）。

---

## 8. 如何扩展这个包

完整流程以 [`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md) 为准
（§2 改动归属、§3 标准工作流、§4 `tpc_toolkit/` 验收清单、§6 文档同步矩阵、§8 提交规范）。
针对本包的要点：

1. **先判定归属**：确实是「与 CST 无关的数据处理 / 优化算法 / 数学公式」才放这里；
   读 CST 结果 → `cst_solver`；晶格/坐标/DXF → `mesh_grid`；建模顺序 → `topo_modeler`；器件流程 → `topo_templates`。
2. **不要引入 CST，也不要无意引入重依赖**：新代码里任何 `import` 都要问一句「这个包是必需的吗」；
   画图/加速之类的库请在**函数内部**延迟导入，别放在模块顶层（§6.2 就是反面教材）。
3. **函数而非类**：本包是纯函数库（0 个类），保持一致；输入输出数组的**形状与 dtype 写进 docstring**
   （如 `(n_freq, 1 + n_blocks)`），这是 WORKFLOW §4 对该包的硬要求。
4. **公式要写推导**：涉及物理/几何公式的新函数，docstring 里给出推导或至少给出两个极限值，
   便于自查（`ep_cal_air` 之所以容易用错，就是因为 docstring 没有交代 `s1`/`s2` 的包含关系）。
5. **每个函数配一个最小可运行示例**：可直接写进本文件对应小节，例如 §3.3 / §5.3。
6. **新增子模块时同步**：在 `tpc_toolkit/__init__.py` 的导入与 `__all__` 里登记；
   确认 `pyproject.toml` 的 `packages.find`（`tpc_toolkit*`）已覆盖；同步 `docs/ARCHITECTURE.md` §3.5 的模块表与本文件 §2。
7. **顺手清理旧名残留**：移动/改名后按 WORKFLOW §9 全仓库搜旧路径
   （已知待改：`skills/user/tpc-usage.md` 里的 `read.py`、`s2p.py:49` 注释里的 `read_cst_s2p_groups`）。
8. **提交**：一个包一条 commit（`feat(tpc_toolkit): …` / `fix(tpc_toolkit): …`），
   正文里写清「为什么改、改了哪些文件、怎么验证、有没有破坏兼容（签名是否变化）」。

---

## 9. 相关文档

- 总体架构与依赖方向（含「工具层不依赖 CST」的旁路定位）→ [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
- 晶格算法层（本包在模块级导入的 `mesh_grid.hex_grid`）→ [`../packages/mesh_grid.md`](../packages/mesh_grid.md)
- 开发者工作流（归属判定、验收清单、文档同步、禁止事项）→ [`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md)
