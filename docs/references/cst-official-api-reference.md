# CST 官方 Python API 参考手册

> CST Studio Suite 2026 — `cst.interface` / `cst.results` / `cst.units`

## 目录

1. [架构总览](#1-架构总览)
2. [cst.interface — 运行时连接](#2-cstinterface--运行时连接)
   - [DesignEnvironment](#21-designenvironment)
   - [Project](#22-project)
   - [Model3D vs Modeler](#23-model3d-vs-modeler)
   - [辅助函数](#24-辅助函数)
3. [cst.results — 离线结果读取](#3-cstresults--离线结果读取)
   - [ProjectFile](#31-projectfile)
   - [ResultModule](#32-resultmodule)
   - [ResultItem (1D)](#33-resultitem-1d)
   - [Result2DItem (Colormap)](#34-result2ditem-colormap)
   - [Quantity / ComplexQuantity / Unit](#35-quantity--complexquantity--unit)
4. [cst.units — 单位系统](#4-cstunits--单位系统)
5. [C 扩展层全景](#5-c-扩展层全景)
   - [_cst_interface](#51-_cst_interface--核心运行时)
   - [cst_project_info_reader](#52-_cst_interfacecst_project_info_reader--工程属性读取无-de)
   - [_cst_results](#53-_cst_results--离线结果读取)
   - [_cst_circuits](#54-_cst_circuits--电路与-touchstone)
   - [_cst_eda_interface](#55-_cst_eda_interface--pceda后端)
   - [_cst_radar](#56-_cst_radar--雷达信号处理)
   - [_cst_eda_multiphysics](#57-_cst_eda_multiphysics--eda-多物理场)
   - [_cst_chip_interface](#58-_cst_chip_interface--芯片级-eda)
6. [其他子包](#6-其他子包)
7. [cst_runtime 对照表](#7-cst_runtime-对照表)
8. [二次开发方向](#8-二次开发方向--api-差距分析)
9. [源码挖掘的隐藏能力](#9-源码挖掘--官方-api-不提供的隐藏能力)
   - [modeler=Model3D=RemoteObject 动态 COM 代理](#91-modeler--model3d--remoteobject--动态-com-代理)
   - [model3d 私有方法](#92-model3d-的私有方法和属性)
   - [BeginHide/EndHide 批量操作](#93-beginhide--endhide--批量操作无-ui-刷新)
   - [_get_all_result_items 批量结果](#94-resultmodule_get_all_result_items--批量结果读取)
   - [CLI 解析器](#95-_commandlineparse--内置-cst-cli-解析器)
   - [内部日志](#96-_enablelogging--c-扩展内部日志)
   - [ProjectFile 离线混合架构](#97-projectfile-混合架构--结果读取完全离线)
   - [命令构建器](#98-cspcbscommand--通用命令构建器模式)
   - [隐藏能力汇总](#910-隐藏能力汇总)
10. [CST VBA 参考](#10-cst-vba-参考--add_to_history-的完整-api)

---

## 1. 架构总览

```
                             ┌─────────────────────────┐
                             │      cst.__init__.py      │
                             │  版本检测 + sys.path 注入  │
                             └─────────────────────────┘
                                          │
          ┌───────────────────────────────┼───────────────────────────────┐
          ▼                               ▼                               ▼
┌───────────────────┐  ┌─────────────────────┐  ┌─────────────────────────┐
│  cst.interface/    │  │   cst.results.py    │  │  其他 Python 子包        │
│  运行时 API        │  │   离线结果读取       │  │  gui / eda / radar /     │
│  (需 DE 进程)      │  │   (无需 CST GUI)     │  │  post_processing        │
└───────────────────┘  └─────────────────────┘  └─────────────────────────┘
          │                      │                         │
          ▼                      ▼                         ▼
┌───────────────────┐  ┌─────────────────────┐  ┌─────────────────────────┐
│ _cst_interface    │  │ _cst_results        │  │ _cst_eda_interface      │
│ + cst_project_    │  │ ProjectFile         │  │ + gds/geometry2d/       │
│   info_reader     │  │ ResultModule        │  │   part_library/pcb_api  │
│ + install_paths   │  │ ResultItem (1D)     │  ├─────────────────────────┤
│ + units           │  │ Result2DItem (2D)   │  │ _cst_circuits           │
└───────────────────┘  └─────────────────────┘  │ + touchstone reader    │
          │                                      │ + CircuitCreator       │
          ▼                                      ├─────────────────────────┤
┌───────────────────┐                            │ _cst_radar             │
│ Model3D → 历史开关│                            │ + FarfSource           │
│ Modeler → VBA/COM │                            ├─────────────────────────┤
│ PCBSApi → PCB 接口│                            │ _cst_chip_interface    │
└───────────────────┘                            │ (DLL 条件依赖)         │
                                                 └─────────────────────────┘
```

**三层结构：**

| 层 | 实现 | 说明 |
|----|------|------|
| **C 扩展** | `_cst_interface.pyd`, `_cst_results.pyd`, `_cst_eda_interface.pyd`, `_cst_circuits.pyd`, `_cst_radar.pyd`, `_cst_chip_interface.pyd` | 直接调用 CST 底层二进制 |
| **Python 封装** | `cst/interface/studio.py`, `cst/results.py`, `cst/eda/`, `cst/gui/` | 薄封装层 + 类型标注 + 上下文管理器 |
| **导出入口** | `cst/__init__.py` | 版本检查 + sys.path 注入，子包按需加载 |

---

## 2. cst.interface — 运行时连接

### 2.1 DesignEnvironment

DE 代表一个 CST Studio Suite 进程实例。所有操作从连接或创建 DE 开始。

#### 创建与连接

```python
from cst.interface import DesignEnvironment

# 方式 1: 启动新的 CST 实例（无 GUI）
de = DesignEnvironment.new(options=["-nogui"])

# 方式 2: 按 PID 连接已运行的 CST
de = DesignEnvironment.connect(pid=12345)

# 方式 3: 连接到任意一个已运行的 CST
de = DesignEnvironment.connect_to_any()

# 方式 4: 连接到已有实例，若没有则启动新的
de = DesignEnvironment.connect_to_any_or_new()

# 方式 5: 直接用构造函数（等价于 new）
de = DesignEnvironment(mode=DesignEnvironment.StartMode.New)
```

#### constructor 参数

```python
DesignEnvironment.__init__(
    mode: StartMode = New,          # New / Existing / ExistingOrNew
    pid: Union[int, str] = None,    # PID 或管道地址
    options: List[str] = None,      # 命令行参数，如 ["-nogui"]
    gui_linux: bool = None,         # Linux 下是否启动 GUI
    process_info: ProcessInfo = None,  # 进程信息（用于 stdout/stderr 重定向）
    env: Dict = None,               # 环境变量
)
```

#### ProcessInfo

```python
ProcessInfo(
    pid,              # 进程 ID
    returncode,       # 退出码
    stderr,           # stderr 输出
    stdout,           # stdout 输出
    stderr_to_stdout, # 是否将 stderr 合并到 stdout
)
```

#### 项目管理

```python
# 新建项目（按求解器类型）
de.new_mws()        # Microwave Studio (时域/频域)
de.new_cs()         # Cable Studio
de.new_ems()        # EM Studio (静场/低频)
de.new_fd3d()       # Frequency Domain Solver
de.new_mps()        # Multiphysics Studio
de.new_pcbs()       # PCB Studio
de.new_ps()         # Particle Studio
de.new_ds()         # Design Studio
de.new_project()    # 通用新建（需指定 ProjectType）

# 打开已有项目
de.open_project("path/to/project.cst")

# 获取已打开的项目
de.active_project()         # 当前激活的项目 → Project
de.get_open_project(name)   # 按名称获取 → Project
de.get_open_projects()      # 所有打开项目 → list
de.list_open_projects()     # 所有打开项目路径 → list[str]
```

#### 工具方法

```python
de.pid                  # → int: 进程 ID
de.version              # → str: 版本号
de.library_paths        # → list: 库路径
de.is_connected()       # → bool
de.close()              # 关闭 DE 进程
de.set_quiet_mode(bool) # 静默模式（抑制对话框）
de.in_quiet_mode()      # → bool

# 上下文管理器（自动恢复）
with de.quiet_mode_enabled():   # 临时开启静默
    ...
with de.quiet_mode_disabled():  # 临时关闭静默
    ...

de.add_library_path(path)
de.remove_library_path(path)
de.archive(path)        # 归档（打包 .cst）
de.print_version()      # 打印版本
de.print_command_line_options()
```

---

### 2.2 Project

Project 代表一个打开的 .cst 工程。

#### 获取 Project

```python
# 通过 DE
prj = de.active_project()
prj = de.open_project(path)
prj = de.get_open_project(name)

# 直接打开（不通过 DE）
prj = Project.open("path/to/project.cst")

# 智能连接或打开
prj = Project.connect_or_open("path/to/project.cst")
prj = Project.connect("project_name")  # 只连接（项目已在 DE 中打开）
```

#### 属性

```python
prj.project_type        # → ProjectType: 项目类型
prj.design_environment  # → DesignEnvironment: 父 DE
prj.modeler             # → COM Modeler 接口
prj.model3d             # → Model3D（历史记录开关）
prj.schematic           # → CS/DS 原理图接口
prj.pcbs                # → PCBSApi
```

#### 方法

> **注意：** C 扩展层中 `filename`、`folder` 是方法（非属性），调用时需带括号。

```python
prj.filename()          # → str: 完整文件路径
prj.folder()            # → str: 所在文件夹路径
prj.activate()          # 激活为当前项目
prj.save()              # 保存
prj.close()             # 关闭项目（不关 DE）
prj.open(path)          # 打开 .cst 文件到当前项目对象
prj.get_messages()      # 求解器消息
```

#### ProjectType

```python
ProjectType.MWS   # Microwave Studio
ProjectType.CS    # Cable Studio
ProjectType.EMS   # EM Studio
ProjectType.FD3D  # Frequency Domain 3D
ProjectType.MPS   # Multiphysics Studio
ProjectType.PCBS  # PCB Studio
ProjectType.PS    # Particle Studio
ProjectType.DS    # Design Studio

prj_typ.name      # → str: 名称（如 "MWS"）
prj_typ.value     # → int: 枚举值
```

---

### 2.3 Model3D vs Modeler

这是最常见的误解点。**Model3D 不是 Modeler 的替代品。**

| | `modeler` | `model3d` |
|---|---|---|
| **角色** | VBA/COM 自动化接口 | 历史命令记录开关 |
| **能力** | 建模、求解、端口、网格等一切操作 | 仅开关历史记录 |
| **关键方法** | `add_to_history(name, vba)`, `run_solver()` 等 | `allow_history_commands()`, `disallow_history_commands()` |
| **上下文管理器** | ❌ | ✅ `with prj.model3d: ...` |
| **2026 状态** | 正常工作 | 新增，**不是**替代关系 |

```python
# 正确：2026 年仍然如此
prj.modeler.add_to_history("CreateBrick", "Brick ...")
prj.modeler.run_solver()

# model3d 的用途：批处理时控制历史记录
with prj.model3d:           # disallow + allow 自动包裹
    prj.modeler.add_to_history("Op1", "...")
    prj.modeler.add_to_history("Op2", "...")
    prj.modeler.run_solver()

# 等价于手动：
prj.model3d.disallow_history_commands()
prj.modeler.add_to_history("Op1", "...")
prj.modeler.add_to_history("Op2", "...")
prj.model3d.allow_history_commands()
```

> **注意：** `project.modeler.add_to_history("name", "VBA")` 是执行所有建模、端口、网格、仿真控制操作的**唯一统一入口**。`execute_vba_code()` 在 CST 2026 已移除。

Model3D 的 C 扩展类 `_cst_interface.Model3D` 只定义了 4 个方法：

```python
allow_history_commands()     # 开启历史记录
disallow_history_commands()  # 关闭历史记录
__enter__()                  # 上下文管理器入口
__exit__()                   # 自动恢复之前状态
```

---

### 2.4 辅助函数

```python
from cst.interface import running_design_environments

# 获取所有运行中的 DE 进程 PID
pids = running_design_environments()  # → List[int]

# 获取当前项目（自动检测）
from cst.interface import get_current_project
prj = get_current_project()  # 需要恰好一个 DE 在运行

# 获取调用源
from cst.interface import get_calling_app, get_calling_app_name
app = get_calling_app()      # → prj.model3d / prj.schematic / prj.pcbs
name = get_calling_app_name()# → "model3d" / "schematic" / "pcbs"
```

#### install_paths

```python
from cst.interface import install_paths

install_paths.root       # → str: CST 安装根目录
install_paths.bin64      # → str: bin64 目录
install_paths.acis_bin64 # → str: ACIS bin64 目录
```

---

## 3. cst.results — 离线结果读取

`cst.results` 是单文件模块（`cst/results.py`），核心功能由 C 扩展 `_cst_results` 提供。**无需 CST GUI 进程**即可读取结果。

### 3.1 ProjectFile

```python
from cst.results import ProjectFile

pf = ProjectFile("path/to/project.cst")
# 或
pf = ProjectFile()
pf.init("path/to/project.cst")

pf.filename      # → str

# 获取结果模块
rm_3d = pf.get_3d()            # → ResultModule（3D EM 结果）
rm_schematic = pf.get_schematic()  # → ResultModule（电路/原理图结果）

# 子项目
pf.list_subprojects()          # → list[str]
sub = pf.load_subproject("name")  # → ProjectFile
```

**支持：** 2025/2026 版本，未打包（unpacked）且未加密的 `.cst` 文件。

---

### 3.2 ResultModule

ResultModule 是结果树的入口。

```python
rm = pf.get_3d()

# 导航结果树
items = rm.get_tree_items()                    # → list[str]: 所有结果路径
items = rm.get_tree_items("0D/1D")             # → list[str]: 1D 曲线
items = rm.get_tree_items("colormap")          # → list[str]: 2D 云图

# 获取结果项
item = rm.get_result_item("2D/1D/S-Parameters/S11", run_id=1)
item_2d = rm.get_result2d_item("2D/3D Results/Farfields/...")

# 运行 ID
all_runs = rm.get_all_run_ids()               # → list[int]
runs_for_item = rm.get_run_ids(item)          # → list[int]

# 参数组合
params = rm.get_parameter_combination(run_id) # → dict {name: value}
```

> **重要：** `run_id=0` 是别名，永远指向当前（最新）结果，不是真正的历史数据。

---

### 3.3 ResultItem (1D)

```python
# 属性
item.treepath   # → str: 结果树路径
item.run_id     # → int: 运行 ID
item.length     # → int: 数据点数量
item.title      # → str
item.xlabel     # → str
item.ylabel     # → str

# 获取数据
xdata = item.get_xdata()         # → Quantity / ComplexQuantity
ydata = item.get_ydata()         # → Quantity / ComplexQuantity
data = item.get_data()           # → tuple(tuple): (x_values, y_values)

# 辅助信息
params = item.get_parameter_combination()  # → dict
ref_imp = item.get_ref_imp_data()          # → Quantity
```

#### S11 数据处理注意事项

`ydata` 是复数字典结构（不是 dB）：

```python
ydata.value  # → {"real": [...], "imag": [...]} 或 {"real": ..., "imag": ...}

# 转 dB：
import math
s11_db = [20 * math.log10(math.hypot(r, i)) for r, i in zip(ydata.value["real"], ydata.value["imag"])]
```

---

### 3.4 Result2DItem (Colormap)

```python
item_2d = rm.get_result2d_item("2D/3D Results/Farfields/farfield (f=10)")

# 属性
item_2d.title      # → str
item_2d.xlabel     # → str
item_2d.ylabel     # → str
item_2d.dataunit   # → Unit
item_2d.nx         # → int: X 方向网格数
item_2d.ny         # → int: Y 方向网格数
item_2d.xmin, item_2d.xmax  # → float
item_2d.ymin, item_2d.ymax  # → float

# 获取数据
x = item_2d.get_xpositions()      # → list[float]
y = item_2d.get_ypositions()      # → list[float]
data = item_2d.get_data()         # → 2D array
```

---

### 3.5 Quantity / ComplexQuantity / Unit

```python
# Quantity（实数）
q = item.get_ydata()
q.value       # → float 或 list[float]
q.unit        # → Unit
q.convert_to(new_unit)  # → Quantity
q.pow(n)      # → Quantity
q.sqrt()      # → Quantity

# ComplexQuantity（复数）
cq = item.get_ydata()  # S11 等复数结果
cq.value      # → {"real": ..., "imag": ...}
cq.unit       # → Unit
cq.convert_to(new_unit)
cq.pow(n)
cq.sqrt()

# Unit
u = cq.unit
u.get_symbol()      # → str: 如 "dB", "V", "W"
u.inSI()            # → Unit: SI 等效单位
u.simplify()        # → Unit: 化简
u.encode(value)     # → Quantity
u.decode(quantity)  # → float
u.pow(n)            # → Unit
```

**预定义单位常量**（`cst.units` / `cst.results`）：

```python
# SI 基本及衍生
m, kg, s, A, K, mol, cd, Hz, N, Pa, J, W, V, Ohm, S, F, H, T, Wb, Gy, Sv, kat, lm, lx

# 常用工程单位
GHz, MHz, kHz, THz, PHz
mm, cm, km, um, nm, pm, mil, inch, ft
ms, us, ns, ps, fs, min, hour, day, deg, rad, sr
mA, mV, mW, uA, uV, nF, pF, mF, nH, uH, mH
degC, degF, hPa, MPa, GPa, kPa
byte, g, mg, ug, mol, mmol

# 前缀
yocto, zepto, atto, femto, pico, nano, micro, milli, centi, deci
deca, hecto, kilo, mega, giga, tera, peta, exa, zetta, yotta
```

---

## 4. cst.units — 单位系统

`cst.units` 从 `_cst_interface.units` 重新导出，所有单位常量和 `Unit`、`Quantity`、`ComplexQuantity` 类与此处一致。

额外函数：

```python
from cst.units import scaling_factor_to_SI

factor = scaling_factor_to_SI(GHz)  # → 1e9
factor = scaling_factor_to_SI(mm)   # → 0.001
```

---

## 5. C 扩展层全景

CST 2026 提供 6 个 C 扩展 `.pyd`。下面逐一拆包列出所有类和函数。

### 5.1 `_cst_interface` — 核心运行时

```python
import _cst_interface as ci

# ── 类 ──
ci.DesignEnvironment    # DE 连接/管理（运行时基类）
ci.Project              # 单个 .cst 工程
ci.ProjectType          # MWS/CS/DS/EMS/FD3D/MPS/PCBS/PS
ci.Model3D              # 历史命令记录开关（上下文管理器）
ci.Dim                  # 维度值包装
ci.PCBSApi              # PCB Studio API（new_command/send_command）
ci.CSTException         # 所有 CST 异常的基类

# ── 内部远程调用类 ──
ci.RemoteObject         # COM 远程对象代理
ci.RemoteObjectMethod   # COM 远程方法代理
ci.RemoteCommandMethod  # COM 远程命令代理
ci.CS_PCBSCommand       # PCB 命令构建器（AddArgument/Execute）

# ── 函数 ──
ci.running_design_environments()  # → list[int]: 所有运行中的 DE 进程 PID

# ── 子模块 ──
ci.install_paths                # root/bin64/acis_bin64
ci.units                        # Unit/Quantity/ComplexQuantity + 所有单位常量
```

### 5.2 `_cst_interface.cst_project_info_reader` — 工程属性读取（无 DE）

**无需打开 DE 即可读取 .cst 文件属性！** 可直接替代 VBA 的项目信息查询。

```python
from _cst_interface import cst_project_info_reader as pir

# 读取任意 .cst 文件的元数据
data = pir.get_document_uri_for_file("path/to/project.cst")

# 工程属性数据
d = pir.CSTProjectPropertiesData()

d.full_version_string        # → str: 完整版本号
d.cst_release                # → str: 发行号
d.cst_patch                  # → str: 补丁号
d.min_frequency              # → float: 最小频率
d.max_frequency              # → float: 最大频率
d.frequency_unit             # → Unit: 频率单位
d.active_solver_name         # → str: 当前求解器
d.active_solver_features     # → CSTProjectSolverFeatures
d.block_names                # → list[str]: VBA 块名称
d.block_types                # → list[str]: 块类型
d.all_subproject_directories # → list[str]
d.simulation_project_names   # → list[str]
d.task_names                 # → list[str]
d.has_modeler_data           # → bool: 是否有 3D 建模数据
d.has_pcb_studio_data        # → bool: 是否有 PCB 数据
d.is_pcb_studio_active       # → bool

# 求解器特性（HPC/许可）
sfe = d.active_solver_features
sfe.n_threads_or_cores       # → int
sfe.n_gpu_devices            # → int
sfe.n_cpu_devices            # → int
sfe.n_dc_nodes               # → int
sfe.supports_hpc_gpu         # → bool
sfe.supports_hpc_mpi         # → bool
sfe.supports_hpc_multi_gpu   # → bool
sfe.is_price_model_basic     # → bool
sfe.is_price_model_premium   # → bool

# 工程属性浏览器（遍历文件系统）
exp = pir.CSTProjectPropertiesExplorer()
exp.is_opened                # → bool
exp.can_contain_subproject_info
exp.get_project_data("path/to/project.cst")    # → CSTProjectPropertiesData
exp.get_subproject_data("path/to/project.cst") # 子项目数据
exp.get_subproject_locations("path/to/project.cst")

# 提取
ext = pir.CSTProjectPropertiesExtraction()
ext.get_document_uri("path/to/project.cst")

# 运行模式
run_mode = pir.ModelerRunMode  # 枚举
run_mode.SINGLE_RUN           # 单次运行
run_mode.OPTIMIZER            # 优化
run_mode.PARAMETER_SWEEP      # 参数扫描
```

### 5.3 `_cst_results` — 离线结果读取

```python
from _cst_results import *

# 类
ProjectFile     # 打开 .cst（文件系统）
ResultModule    # 结果树（get_3d / get_schematic）
ResultItem      # 1D 曲线（S参数等）
Result2DItem    # 2D 云图（远场等）
CSTException    # 异常

# 函数
__version_info__()  # → str: 如 "2026.1 Release from 2025-10-22"
```

详见[第 3 节](#3-cstresults--离线结果读取)。

### 5.4 `_cst_circuits` — 电路与 Touchstone

**CircuitCreator** — SPICE 网表操作：

```python
from _cst_circuits import CircuitCreator as cc

cc.compare_netlists(netlist1, netlist2, format=NetlistFormat.CST_SPICE)
# 支持的格式: BERKLEY, CCS, CST_SPICE, HSPICE, LTSPICE, PSPICE
```

**Touchstone 文件读取器** — 纯离线，无 CST GUI：

```python
from _cst_circuits.touchstone import read, Touchstone, Format, Type, Version

# 读取 .s2p / .s4p 等文件
ts: Touchstone = read("path/to/example.s2p")

ts.version           # → Version: TS_1_0 / TS_2_0 / HSPICE
ts.format            # → Format: RI / DB / MA
ts.type              # → Type: S / Y / Z
ts.n_ports           # → int: 端口数
ts.frequencies       # → list[float]: 频率点
ts.port_impedances   # → list[float]: 各端口阻抗
ts.pin_naming        # → str: 引脚命名方案
ts.message           # → str: 注释/选项行

# 提取指定频率的 S 矩阵
S = ts.matrix_at(frequency=10e9)  # → 复数矩阵
```

> **注意：** 这是**纯 Python 可调用**的官方 Touchstone 读取器，不依赖任何 COM/GUI。可直接用于封装 `cst_runtime` 的 Touchstone 导出结果读取。

### 5.5 `_cst_eda_interface` — PCB/EDA 后端

```python
from _cst_eda_interface import (
    pcb_api,       # PCB 编辑 API（全量层/网络/元件/焊盘）
    gds,           # GDSII 文件格式读取器
    geometry2d,    # 2D 几何库
    part_library,  # 元件库管理
)
```

**gds — GDSII 文件读取：**

```python
from _cst_eda_interface.gds import GDSLibrary, GDSCell, ElementType

lib = GDSLibrary("path/to/layout.gds")
lib.unit         # → float: 数据库单位（μm）
lib.precision()  # → float
lib.top_level    # → list[str]: 顶层单元名
lib.cells        # → dict[str, GDSCell]

cell = lib.get_cell("cell_name")
cell.name       # → str
cell.elements   # → list[GDSElement]

elem = cell.elements[0]
elem.type       # → ElementType: BOUNDARY / PATH / SREF / ...
elem.layer      # → int: 层号
elem.datatype   # → int: 数据类型
elem.xy         # → list[tuple[float, float]]: 坐标点
elem.sname      # → str: 引用单元名（SREF）
```

**geometry2d — 2D 几何库：**

```python
from _cst_eda_interface.geometry2d import (
    Shape, Curve, SegmentString, Arc, Line, Circle,
    R2, Transformation,
    translation, rotation, scaling, reflection,
    heal_shapes,
)

# 创建形状
shape = Shape.create_rectangle(width=1e-3, height=2e-3)
crv = Curve.create_polyline([R2(0,0), R2(1,0), R2(1,1), R2(0,1)])
crv.is_closed   # → bool
crv.length      # → float
crv.make_closed()

# 线段串
ss = SegmentString([R2(0,0), R2(1,0)])
ss.append_line(R2(1, 1))
ss.append_arc(center=R2(0.5, 0.5), radius=0.5, angle_deg=90)

# 变换
t = translation(dx=1, dy=2)
shape.transform(t)
t_inv = t.inverse()

# 几何修复
healed = heal_shapes([shape1, shape2])
```

**pcb_api — PCB 完整编辑 API（100+ 类）：**

关键类：`PCB`, `Layer`, `Net`, `Component`, `PadstackGI`, `TraceGI`, `ShapeGI`, `Pin`, `Material`, `SimulationSettings`, `Stackup`, `StackupRegion`

```python
from _cst_eda_interface.pcb_api import PCB

# PCB 编辑（需 DE 内打开 PCB 项目）
p = PCB()
p.load_stackup("path/to/stackup.xml")
p.set_length_unit("mm")
layer = p.layer("TOP")
net = p.create_net("GND")
# ... 完整 PCB 布局编辑
```

> **PCB API 完整类表（63 个类型）见：** `_cst_eda_interface.pcb_api` 的 docstring。

**part_library — 元件库：**

```python
from _cst_eda_interface.part_library import PartLibrary

lib = PartLibrary()
lib.add_RLC("RES_001", resistance=100, package="0402")
lib.add_RLC_SPICE("CAP_001", spice_model="...")
lib.add_RLC_Touchstone("FILTER_001", s2p_path="filter.s2p")
lib.save("path/to/library.bin")
lib.clear()
```

### 5.6 `_cst_radar` — 雷达信号处理

```python
from _cst_radar import FarfSource

# 远场源处理（从 .cst 或文件加载远场数据）
fs = FarfSource()
fs.fromfile("path/to/farfield.ffs")

fs.frequencies()                    # → list[float]: 可用频率
fs.coordinate_system_origin()       # → tuple[float,float,float]
fs.coordinate_system_U() / V() / W() # → 坐标系基向量

# 方向图计算
E = fs.compute_E(theta_deg, phi_deg, frequency)
H = fs.compute_H(theta_deg, phi_deg, frequency)
EH = fs.compute_EH(theta_deg, phi_deg, frequency)

# 方向角计算
angles = fs.compute_pattern_angles_E(frequency)      # → dict
directions = fs.compute_pattern_dirs_E(frequency)     # → dict

# 功率
P_acc = fs.get_accepted_powers()      # → 接受功率
P_rad = fs.get_radiated_powers()      # → 辐射功率
P_stim = fs.get_stimulated_powers()   # → 激励功率

# 变换
fs.rotate_pattern(angle_deg, axis)
fs.scale(factor)
fs.translate_origin(x, y, z)
```

> `FarfSource` 是 C 级高性能实现，可直接替代 `cst_runtime` 中基于远场数值提取 + 纯数学计算的路径。

### 5.7 `_cst_eda_multiphysics` — EDA 多物理场

```python
from _cst_eda_multiphysics import *
# 当前版本仅提供 CSTException 异常类型
# 功能由 `cst/eda/pcbs/pi_solver_settings.py` 等 Python 模块补充
```

### 5.8 `_cst_chip_interface` — 芯片级 EDA

```python
# 提供 cp310 ~ cp313 的 .pyd 文件
# 当前环境依赖缺失（DLL not found），可能是选择性安装
# 功能涵盖 chip CDF、layermapping、SPECTRE 网表
# Python 侧: cst/eda/chip/  含 cdf.py, layermapping.py, spectre.py
```

---

## 6. 其他子包

| 子包 | 内容 | 底层 C 扩展 | 状态 |
|------|------|------------|------|
| `cst.interface` | DE/Project 运行时 API | `_cst_interface` | ✅ 核心 |
| `cst.results` | 离线结果读取 | `_cst_results` | ✅ 核心 |
| `cst.units` | 单位系统（重导出） | `_cst_interface.units` | ✅ 核心 |
| `cst.eda` | PCB EDA 工作流 — 转换脚本/过孔设置/GDSII/2D 几何/元件库/全量 PCB 编辑 API | `_cst_eda_interface` (gds/geometry2d/part_library/pcb_api) | ✅ 完整实现 |
| `cst.radar` | 汽车雷达算法 — FMCW/MIMO/测距测角/RCS 远场处理 | `_cst_radar` (FarfSource) + Python 算法模块 | ✅ 需 numpy/scipy/matplotlib |
| `cst.post_processing` | 后处理 — `s_parameters` 提供 `export_touchstone()`（走 model3d._execute_vba_code） | — | ⚠️ 无 `__init__.py`，子模块可导入 |
| `cst.circuits` | **无 Python 封装层**，直接走 `_cst_circuits` — Touchstone 文件读取 + SPICE 网表对比 | `_cst_circuits` (touchstone/CircuitCreator) | ✅ 直接 import 可用 |
| `cst.gui` | CSTRootDialog / CSTChildDialog | — | ✅ 可用 |
| `cst.tools` | 工具 | — | ⚠️ 空模块 |
| `cst.tbpp` | — | — | ⚠️ 空模块 |
| `cst.asymptotic` | 渐近求解器 | — | ⚠️ 空模块 |
| `cst.idem` | IDEM | — | ⚠️ 空模块 |

> 空模块可能在后续版本或特定授权下填充功能，也可能是内部使用。

---

## 7. cst_runtime 对照表

> **关于路径约定：** 以下 `core/` 指向 `scripts/cst_runtime/core/`，`tools/` 指向 `scripts/cst_runtime/tools/`，`cli/` 指向 `scripts/cst_runtime/cli/`。

| 功能 | 官方 API | cst_runtime | 备注 |
|------|---------|-------------|------|
| 发现 DE | `running_design_environments()` | `core/identity.py` | ✓ 已同步 |
| 连接到 DE | `DesignEnvironment.connect(pid)` | `core/session.py` | |
| 新建 MWS | `de.new_mws()` | `core/session.py:create_blank_project()` | |
| 开工程 | `de.open_project(path)` | `core/session.py:open_project()` | 含 attach 复用逻辑 |
| 关工程 | `prj.close()` | `core/session.py:close_project(kill_processes=True)` | 额外杀 DE + 孤儿进程 |
| 执行 VBA | `prj.modeler.add_to_history("name","VBA")` | 各工具内部调用 | 统一入口 |
| 运行求解器 | `prj.modeler.run_solver()` | `core/simulation.py` | 6 个方法全覆盖 |
| 改参数 | `modeler.StoreDoubleParameter(...)` | `core/project.py:change_parameter()` | 支持直接 COM + VBA 两种 |
| 读 S11 | `rm.get_result_item(...).get_ydata()` | `core/results.py:get_1d_result()` → JSON | 使用 `ProjectFile`（离线） |
| 读远场 | `rm.get_result2d_item(...).get_data()` | `core/results.py:get_2d_result()` + `core/farfield.py` | 混合离线+在线 |
| 批量结果列举 | `rm._get_all_result_items()` | `core/results.py:list_result_items(all)` | 隐藏 API 已封装 |
| 读参数组合 | `rm.get_parameter_combination(run_id)` | `core/results.py` | |
| 工程元数据 | `cst_project_info_reader.CSTProjectPropertiesData` | 未封装 | **新增机会**：替代 VBA 查询 |
| Touchstone 文件读取 | `_cst_circuits.touchstone.read("file.s2p")` | 未封装 | **新增机会**：纯离线读取 |
| Touchstone 导出写 | `cst.post_processing.s_parameters.export_touchstone(prj, filename)` | 未封装 | 走 model3d._execute_vba_code |
| 远场方向图计算 | `_cst_radar.FarfSource.compute_E/H/EH()` | `analysis/farfield/` | C 级高性能替代 |
| 单位转换 | `q.convert_to(target_unit)` | 未封装 | 可用 `cst.units` |
| 工程类型 | `ProjectType.MWS` | `core/session.py` | 注释记录 |
| GDSII 读取 | `_cst_eda_interface.gds.GDSLibrary` | 无 | 建模/EDA 场景可能用到 |
| PCB 编辑 | `_cst_eda_interface.pcb_api.PCB` | 无 | 仅 MWS 场景无关 |
| 陷阱保护 | 无官方对应 | `core/gateway.py` — 7 个 Guard | T2/T3/T5/T8/T10/T12/T13/T14 |
| 进程清理 | 无官方对应 | `core/process.py` | 白名单 + 孤儿识别 |
| 环境检测 | 无官方对应 | `core/environment.py` | 注册表扫描 + 自动注册 |

---

### 7.1 集成建议

> **P0 — 高价值低风险：**
> - `cst_project_info_reader` → 替代 `inspect-project` 中的 VBA 查询，实现真正的离线工程侦查
> - `_cst_circuits.touchstone.read()` → 封装成 `read-touchstone` 工具，支持 `.s2p/.s4p` 文件读取
>
> **P1 — 按需使用：**
> - `_cst_radar.FarfSource` → 替代 `farfield_analysis/` 纯数学计算，精度更高、速度更快
> - `cst.post_processing.s_parameters.export_touchstone()` → 替代 VBA touchstone 导出脚本
>
> **不建议：**
> - `_cst_eda_interface` 系列（PCB/GDS/2D几何）→ MWS 场景不需要，保持零依赖

### 7.2 cst_runtime 内部架构

cst_runtime 的源码按四层职责分离，不混在单目录：

| 层 | 目录 | 职责 | 关键文件 |
|----|------|------|---------|
| **核心逻辑** | `core/` | 纯 CST COM 操作，不注册 CLI 工具 | `session.py`, `project.py`, `results.py`, `simulation.py`, `farfield.py`, `gateway.py`, `process.py`, `environment.py` |
| **工具定义** | `tools/` | JSON Schema + Handler，通过 `_register_tool_defs()` 注册 | `project.py`, `modeling.py`, `simulation.py`, `results.py` 等 |
| **CLI 分发** | `cli/` | 工具分派中心 + 管道注册 | `dispatch.py`, `pipelines/registry.py`, `pipelines/impl.py` |
| **分析/渲染** | `analysis/`, `render/` | 纯数学计算 + HTML/SVG 页面 | `farfield/parser.py`, `farfield/flatness.py`, `render/*.py` |

### 7.3 关键差异

| 场景 | 官方 API | cst_runtime |
|------|---------|-------------|
| DE 发现 | `running_design_environments()` → `list[int]` | 同（原 PowerShell fallback） |
| 进程管理 | `DesignEnvironment.close()` | 同 + `kill_processes=True` 额外杀孤儿进程 |
| 项目打开 | `de.open_project()` / `Project.open()` | `DesignEnvironmentSession:open_project()` 统一入口 |
| 结果读取 | `cst.results.ProjectFile`（离线） | `cst.results.ProjectFile`（离线）— `core/results.py` | 与官方 API 一致，非 COM 路径 |
| 远场导出 | 无纯 API（需 VBA） | VBA 脚本导出到文件 |

---

## 8. 二次开发方向 — API 差距分析

> 本节来自对 112 个原子工具 + 5 个管道工具的全面盘点，以及 C 扩展拆包发现的未利用 API。

### 8.1 覆盖度概览

| 领域 | 官方 API 功能数 | cst_runtime 已覆盖 | 覆盖率 | 备注 |
|------|---------------|-------------------|--------|------|
| Session/DE 管理 | 22 | 8 | 36% | 含 connection/attach/close/cleanup |
| 项目管理 | 12 | 5 | 42% | open/close/save/define-params |
| 建模操作 | 全部走 VBA | VBA 全覆盖 | N/A | 通过 add_to_history 间接调用 |
| 仿真控制 | 6 | 6 | 100% | run/start/abort/pause/resume/is_running |
| 结果读取（在线 COM） | 6 | 5 | 83% | get_tree_items/get_result_item/get_data |
| 结果读取（离线） | 6 | 4 | 67% | ProjectFile + get_3d + 树导航 + 批量读取 |
| 单位系统 | 130+ 常量 + 3 类 | 0 | 0% | 可用 `cst.units` 导入 |
| 离线工程侦查 | 3 类 + 5 函数 | 0 | 0% | **新增机会** cst_project_info_reader |
| Touchstone 处理 | 读写两方向 | 0 | 0% | **新增机会** _cst_circuits.touchstone |
| 远场计算 | C 级 FarfSource | 纯 Python | 部分 | core/farfield.py + analysis/farfield/ |
| 陷阱保护层 | 无官方对应 | 7 Guard | N/A | core/gateway.py — 运行时安全 |
| 进程清理 | 无官方对应 | 完整实现 | N/A | core/process.py — 白名单+孤儿识别 |
| 环境检测 | 无官方对应 | 完整实现 | N/A | core/environment.py — 注册表+自动注册 |

### 8.2 高价值立即实现（P0）

> **已实现（后续补充）：** `define-parameters`（`tools/project.py`）已在本文档撰写后完成。

| 新工具名 | 底层 API | 价值 | 难度 | 说明 |
|---------|---------|------|------|------|
| `archive-project` | `de.archive(path)` | 高 | 低 | 基线工程归档，CST 原生格式可离线打开 |
| `get-solver-messages` | `prj.get_messages()` | 高 | 低 | 仿真失败诊断——当前仅靠进程码和超时推断 |
| `read-project-info` | `cst_project_info_reader` | 高 | 中 | **零 DE 启动成本**读取工程元数据，适合预检查 |
| `export-touchstone` | `cst.post_processing.s_parameters.export_touchstone()` | 高 | 中 | 行业标准格式，与 ADS/Matlab 互通 |

### 8.3 中价值可规划（P1-P2）

| 新工具名 | 底层 API | 价值 | 难度 | 说明 |
|---------|---------|------|------|------|
| `read-touchstone` | `_cst_circuits.touchstone.read()` | 中 | 中 | 离线读 .sNp 做 S11 分析 |
| `get-project-type` | `prj.project_type` | 中 | 低 | 增强 `inspect-project`，区分 MWS/PCB/EMC |
| `get-cst-version` | `de.version` | 中 | 低 | 增强 `get-version-info`，增加在线版本 |
| `set-quiet-mode` | `de.quiet_mode_enabled/disabled` | 中 | 低 | 批量操作压制 GUI 弹窗 |
| `connect-or-open-project` | `Project.connect_or_open()` | 中 | 低 | 智能打开——已有则 attach，无则新建 |
| `manage-library-path` | `de.add/remove_library_path()` | 中 | 低 | 材料库/宏库路径管理 |
| `check-license-features` | `cst_project_info_reader` (solver features) | 中 | 中 | 仿真前检查 HPC/许可容量 |
| `scan-parameters` | DOE 编排 + 仿真循环 | 高 | 中 | 全自动参数扫描循环 |

### 8.4 低优先级暂不实现

| 功能 | 原因 |
|------|------|
| PCB/GDSII/2D 几何 | MWS 场景不需要 |
| `_cst_radar.FarfSource` 集成 | 纯 Python 远场分析已满足当前需求 |
| `cst.asymptotic` 渐近求解器 | 电大场景非当前目标 |
| SPICE 网表对比 | 场景太窄 |
| `connect-remote-cst` TCP 连接 | 场景少，协议理解成本高 |
| `de.new_cs/ems/fd3d/mps/pcbs/ps/ds` | 当前仅 MWS，扩展只需加参数 |

### 8.5 实施原则

```
P0 工具 → 独立原子工具，走新的 tools/ 文件
增强已有工具 → 加参数（如 inspect-project 加 --project-type）
暂缓功能 → 记录在案，需要时再实现
```

---

## 9. 源码挖掘 — 官方 API 不提供的隐藏能力

> 本节来自对 C 扩展 `.pyd` 的 `dir()` 拆包、私有方法扫描、动态类型分析、以及 DE 在线实测。这些能力**不是**官方接口文档的一部分，但存在于底层实现中，可以在防卫式编程（先 `hasattr` 再调用）的前提下安全使用。

### 9.1 `modeler` = `Model3D` = `RemoteObject` — 动态 COM 代理

**运行时类型链实测确认：**

```python
type(prj.modeler).__name__      # → 'Model3D'
type(prj.modeler).__mro__       # → [Model3D, RemoteObject, pybind11_object, object]
type(prj.model3d).__name__      # → 'Model3D' （和 modeler 是同一类型！）
```

`modeler` 和 `model3d` 返回的是**同一类**（`Model3D`），都继承 `RemoteObject`，通过 C 扩展的 `__getattr__` 实现 COM IDispatch 动态分发。**任何 VBA 方法都可以直接调用。**

**cst_runtime 实际使用模式：**
- **参数操作**：直接 COM 调用 `modeler.StoreDoubleParameter()`（`core/project.py`）
- **仿真控制**：直接 COM 调用 `modeler.run_solver()` / `start_solver()` / `abort_solver()`（`core/simulation.py`）
- **结果读取**：**不走 COM**，统一走 `cst.results.ProjectFile` 离线路径（`core/results.py`）
- **建模/VBA 流程**：走 `add_to_history("name","VBA")` 确保历史记录（`core/modeling.py` 等）
- **私有 fallback**：`model3d._execute_vba_code()` 用于 VBA 树遍历（`core/farfield.py`）

#### 138 个可直接调用的 VBA 方法

| 分类 | 数量 | 示例 |
|------|------|------|
| 参数操作 | 10+ | `StoreDoubleParameter()`, `StoreParameter()`, `DoesParameterExist()`, `RenameParameter()` |
| 仿真控制 | 5+ | `RunSolver()`, `DeleteResults()`, `StartSolver()` |
| 求解器查询 | 8+ | `GetSolverType()`, `GetNumberOfFinishedDesigns()`, `IsBuildingModel()` |
| 结果读取 | 8+ | `GetLast1DResult()`, `GetLast0DResult()`, `Result1D()`, `Result1DComplex()`, `Result2D()`, `EvaluateResultTemplates()` |
| 项目元数据 | 10+ | `GetApplicationName()`, `GetApplicationVersion()`, `GetProjectPathName()`, `GetNumberOfParameters()` |
| 查询/诊断 | 6+ | `GetInstallPath()`, `GetLicenseCustomerNumber()`, `GetLicenseHostId()`, `GetMPIClusterSize()` |
| 报告/日志 | 6+ | `ReportError()`, `ReportWarning()`, `ReportInformation()`, `ReportWarningToWindow()` |
| 文件操作 | 4+ | `ImportSubProject()`, `ImportXYCurveFromASCIIFile()`, `StoreCurvesInASCIIFile()` |
| 批处理 | 4 | `BeginHide()`, `EndHide()`, `ScreenUpdating()` |
| PCB 辅助 | 2 | `ExportArrayPortInformation()`, `Field3DCalculator()` |
| 模板迭代 | 3+ | `ResetTemplateIterator()`, `SetTemplateFilter()`, `GetTemplateAborted()` |
| 数据管理 | 5+ | `SetGlobalData()`, `GetGlobalData()`, `ClearGlobalDataValues()` |
| 集群/HPC | 5+ | `AddMPIClusterNodeConfig()`, `UseDistributedComputingForParameters()` |
| **Python 扩展** | 19 | `add_to_history()`, `abort_solver()`, `allow/disallow_history_commands()`, `get_active_solver_name()`, `get_solver_run_info()`, `get_tree_items()`, `dist2d()`, `dist3d()`, `full_history_rebuild()` |

#### 6 个 COM 子对象（链式访问）

```python
m = prj.modeler

# 每个子对象都返回 RemoteObject，可无限链式调用
m.Monitor.Create("Farfield", 0, "ff (f=10)", 10.0)     # 创建远场监视器
m.Mesh.AdaptionLimit(0.01)                               # 网格自适应限制
m.Boundary.DefinitionType("Open (add space)")             # 边界条件
m.Units.Frequency("GHz")                                  # 设置频率单位
m.Port.AddModeLine(...)                                   # 添加端口模式线
m.Solver.AKSAccuracy(-40)                                 # 求解器精度
```

#### `add_to_history` vs 直接调用的选择

```python
# 【老方式】拼 VBA 字符串 → 写入历史树 → 解析执行
prj.modeler.add_to_history("CreateBrick", "Brick ...")

# 【新方式】直接 COM 调用 → 立刻执行
prj.modeler.StoreDoubleParameter("width", 10.0)

# 什么时候用 add_to_history：
# - 需要历史记录支持撤销/回放时
# - VBA 语法本身有复杂流程控制（if/for/while）时
# - 需要确保操作序列原子化时

# 什么时候用直接 COM 调用：
# - 简单操作（改参、设置、查询）
# - 性能敏感场景
# - 不需要记录到历史树
```

> **关于 `execute_vba_code`：** `modeler.execute_vba_code()` 在 CST 2026 已移除。但 `model3d._execute_vba_code()`（注意是 `model3d` 的私有方法）仍存在于 2026 的官方代码中，被 CST 自己的 `s_parameters.py` 使用。

### 9.2 `model3d` 的私有方法和属性

实测确认 `model3d`（= `modeler`）上有 9 个私有成员：

```python
m3d = prj.model3d

# VBA 执行（被官方代码使用）
m3d._execute_vba_code("Sub main\n...\nEnd Sub")

# 历史树操作
m3d._GetHistory()                      # → str: 历史树内容
m3d._ResizeHistory(n)                  # 调整历史树大小
m3d._TryToUndoNTimes(n)               # → bool: 撤销 n 步

# 连接信息
m3d._address                           # → str: COM 连接地址
m3d._connection                        # → str: 连接标识

# PCB/TBPP（仅 PCB 场景）
m3d._get_PCB_from_selected()           # → PCB 对象
m3d._get_tbpp_startup_info()
m3d._set_tbpp_result_info(...)
```

> **风险提示：** `_execute_vba_code` 虽然被官方代码使用，但以下划线开头意味着可能在后续版本无预警移除。建议仅作为临时 workaround，首选 `add_to_history` 或直接 COM 调用。

**cst_runtime 使用状态：** `core/farfield.py:173-186` 中的 `_gui_execute_vba()` 使用 `model3d._execute_vba_code()` 作为 VBA 树遍历的 fallback 路径（当 `add_to_history` 无法返回结果时）。这是整个代码库中唯一使用此私有方法的地方。

### 9.3 `BeginHide` / `EndHide` — 批量操作无 UI 刷新

```python
m = prj.modeler
m.BeginHide()      # 挂起 GUI 更新
# ... 执行多个建模操作 ...
m.EndHide()        # 恢复 GUI 更新（一次刷新）

# 屏幕更新控制
m.ScreenUpdating(False)
# ... 批处理 ...
m.ScreenUpdating(True)
```

**价值：** 连续执行大量建模/改参操作时，性能可提升 10-100 倍（避免了每次操作都刷新 GUI 树）。

**cst_runtime 使用状态：** 当前代码未使用 `BeginHide/EndHide`。建议在未来的管道工具（如批量参数扫描）中增加此优化。

### 9.4 `ResultModule._get_all_result_items()` — 批量结果读取

**实测确认：** 返回 `list[ResultItem]`，与 `get_tree_items + get_result_item` 结果一致。

```python
# 单次调用获取全部结果项（70 个项目/2.3s）
items = rm._get_all_result_items()  # → list[ResultItem]
for item in items:
    print(item.title, item.treepath, item.run_id)
```

**注意：** `ProjectFile.get_3d()` 每次返回新的 `ResultModule` 实例（不是单例），但多次调用结果一致。

**已集成到 cst_runtime：** `core/results.py:list_result_items()` 在 `filter_type="all"` 时调用此隐藏 API，封装为 `list-tree-items --all` 工具。

### 9.5 `_commandline.parse()` — 内置 CST CLI 解析器

```python
from _cst_interface import _commandline

_commandline.parse("--cst-pid 12345")
# → {'project-file': ['12345']}     ← 把 PID 解释成 project-file

_commandline.parse("-nogui")
# → {}                              ← 无 GUI 参数

_commandline.parse("--prj myproject.cst")
# → ???                             ← 依赖实际 CST 格式
```

**价值：** 内置的 CST CLI 参数解析器，可替代手写 argpase。注意它使用 `shlex.split` 所以参数必须是完整的命令行字符串。

### 9.6 `_enable_logging()` — C 扩展内部日志

```python
from _cst_interface import _enable_logging
_enable_logging(True)    # 开启底层 C 扩展日志
# ... 执行操作 ...
_enable_logging(False)   # 关闭
```

**价值：** 调试 DE 连接/COM 调用失败时，比 strace/COM trace 更快定位。

### 9.7 `ProjectFile` 混合架构 — 结果读取完全离线

`cst.results.ProjectFile` 和 `cst.interface.DesignEnvironment` 是两个**完全独立的 C 扩展**。`ProjectFile` 读结果不需要任何 DE 进程。

```python
from cst.results import ProjectFile

# 完全离线读取（已被实测验证）
pf = ProjectFile("project.cst")
rm = pf.get_3d()              # → ResultModule
rm_sch = pf.get_schematic()   # → ResultModule（DS 工程有值，MWS 为空）
pf.list_subprojects()         # → list[str]（无子项目时返回 []）

# 结果项
items = rm._get_all_result_items()  # 或标准 get_tree_items
item = items[0]
item.title, item.treepath, item.xlabel, item.ylabel, item.run_id, item.length

# 读取数据
xdata = item.get_xdata()      # → Quantity（有 .value .unit）
ydata = item.get_ydata()      # → Quantity 或 ComplexQuantity
# 注意：get_ydata 有时直接返回 list（当单位信息缺失时）
```

**离线和在线对比：**

| 维度 | 在线（DE + modeler） | 离线（ProjectFile） |
|------|---------------------|-------------------|
| 启动时间 | 5-30s | 0s |
| 许可证占用 | 是 | 否 |
| 结果一致性 | 实时 | 磁盘快照（需文件同步） |
| 并行读取 | 受 DE 限制 | 无限制 |

**理想工作流：**
```
阶段 1（在线）：建模 → 仿真 → 关闭 DE（释放许可证）
阶段 2（离线）：ProjectFile 读取结果 → 分析 → 报告
```

### 9.8 `CS_PCBSCommand` — 通用命令构建器模式

```python
from _cst_interface import CS_PCBSCommand

cmd = CS_PCBSCommand()
cmd.AddStringArgument("key", "value")
cmd.AddJsonArgument('{"complex": "data"}')
cmd.Execute()  # → RemoteObject
```

命令构建器 + JSON 参数模式可作为通用远程调用模板。

### 9.9 其他内部发现

| 符号 | 类型 | 说明 |
|------|------|------|
| `_cst_interface._cleanup` | PyCapsule | 进程退出时自动调用 |
| `_cst_interface._enable_logging(bool)` | 函数 | C 扩展日志开关 |
| `_cst_interface._commandline` | 模块 | CLI 解析 |
| `DesignEnvironment._extract()` | 方法 | 初始化参数提取 |
| `DesignEnvironment._post_init()` | 方法 | Python 侧 __init__ 后调用 |
| `DesignEnvironment._connection_address` | 属性 | COM 连接地址 |
| `_cst_eda_multiphysics._internal` | 模块 | 多物理场内部 |
| `Project.project_type` | **方法**（不是属性） | 调用 `prj.project_type()` |
| `Project.filename` | 方法 | `prj.filename()` 返回路径字符串 |
| `Project.folder` | 方法 | `prj.folder()` 返回文件夹 |

### 9.10 隐藏能力汇总

| # | 能力 | 路径 | 价值 | 风险 | 实测确认 |
|---|------|------|------|------|---------|
| 1 | **直接 COM 调用（138 方法）** | `prj.modeler.VBAMethod()` | **高** — 去掉 VBA 字符串层 | 低 — COM 接口稳定 | ✅ MRO 确认 |
| 2 | **COM 子对象链式调用** | `modeler.Monitor.Create()`, `modeler.Mesh.AdaptionLimit()` | **高** — 6 个子对象全功能访问 | 低 | ✅ 实测 |
| 3 | **model3d 私有方法** | `_execute_vba_code()`, `_GetHistory()`, `_TryToUndoNTimes()` | 中 — 历史树操作/VBA fallback | 中 — 私有 API 可能移除 | ✅ 实测 |
| 4 | **BeginHide/EndHide 批处理** | `modeler.BeginHide()` → 批量操作 → `EndHide()` | **高** — 批量性能提升 10-100x | 低 | ✅ 实测 |
| 5 | **批量结果读取** | `rm._get_all_result_items()` | 中 — 省去一次遍历 | 低 | ✅ 实测 70 项 |
| 6 | **CLI 解析器** | `_commandline.parse(str)` | 中 — 替代 argpase | 低 | ✅ 实测 |
| 7 | **内部日志** | `_enable_logging(bool)` | 中 — 调试利器 | 低 | ✅ |
| 8 | **离线结果读取** | `ProjectFile.get_3d()` → 关 DE | **高** — 释放许可证 / 并行 | 无 — 纯官方 API | ✅ 实测 |
| 9 | **命令构建器** | `CS_PCBSCommand` | 低 — MWS 用不到 | 低 | ✅ |
| 10 | **modeler 直接结果读取** | `modeler.GetLast1DResult()`, `modeler.Result1DComplex()` | 中 — 不走 cst.results | 中 — 需验证返回类型 | ✅ 列表确认 |

---

## 10. CST VBA 参考 — add_to_history 的完整 API

> cst_runtime 60+ 个建模/改参/仿真工具统一通过 `prj.modeler.add_to_history("name", "VBA code")` 调用 CST 的 VBA API。本节提供 VBA 文档的查找方式，以及常见操作的 VBA 模板。

### 10.1 VBA 文档位置

| 文档 | 路径 | 说明 |
|------|------|------|
| **VBA 语言教程** | `C:\Program Files\CST Studio Suite 2026\Online Help\vba\vba_macro_language_overview.htm` | VBA 语法基础（变量/流程控制/文件操作），非 CST 特有 |
| **VBA_3D 对象参考** | `C:\Program Files\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D\index.htm` | Brick/Solver/Monitor/Port 等 CST 专有对象的属性和方法，150+ HTML |
| **VBA_DES 对象参考** | `C:\Program Files\CST Studio Suite 2026\Online Help\mergedProjects\VBA_DES\index.htm` | Design Studio 原理图/电路对象 |
| **Python API 文档** | `C:\Program Files\CST Studio Suite 2026\Online Help\Python\source\` |
| **PDF 用户手册** | `C:\Program Files\CST Studio Suite 2026\Documentation\` |

`VBA_3D\` 目录包含约 **200+ 个 HTML 文件**，按功能分组：

| 子目录 | 内容 |
|--------|------|
| `common_vbabasicsolids\` | 基本实体：Brick, Cone, Cylinder, Sphere, Torus, Wire |
| `common_vbacurves\` | 曲线：Analytical, Arc, Circle, Line, Polygon, Rectangle, Spline, LoftCurve, SweepCurve, ExtrudeCurve, TrimCurve |
| `common_vbaimpexp\` | **导入/导出**：STEP, SAT, IGES, DXF, STL, OBJ, GDSII, CATIA, Nastran, Gerber, HFSS, ProE |
| `common_vbafaces\` | 面操作 |
| `common_vbaextrude\` | 拉伸 |
| `common_vbaloft\` | 放样 |
| `common_vbarotateo\` | 旋转 |
| `common_vbatransformo\` | 变换 |
| `common_vbawcso\` | 工作坐标系 (WCS) |
| `special_vbamonitors\` | 监视器：EField, HField, Farfield, SAR, CurrentDensity, Power, SurfaceCurrent |
| `special_vbaports\` | 端口：Discrete, Waveguide, PlaneWave, FieldSource |
| `special_vbamesh\` | 网格控制 |
| `special_vbasolver\` | 求解器：Transient, Frequency, Eigenmode, Asymp, EMS, Thermal |
| `special_vbapostproc\` | 后处理：Farfield, Nearfield, Calc1D/2D/3D, Network |
| `special_vbaobjects\` | VBA 对象模型总览 |

### 10.2 导入导出格式大全（VBA_3D/common_vbaimpexp/）

| 格式 | 文档 | 导入 | 导出 | 典型场景 |
|------|------|------|------|---------|
| **STEP** | `common_vbaimp_exp_step.htm` | ✅ | ✅ Write/WriteAll | 通用 3D CAD 交换 |
| **SAT** | `common_vbaie_sat.htm` | ✅ | ✅ | ACIS 原生 |
| **IGES** | `common_vbaie_iges.htm` | ✅ | ✅ | 旧式 CAD 交换 |
| **STL** | `common_vbaie_stl.htm` | ✅ | ✅ | 3D 打印/网格 |
| **DXF** | `common_vbaie_dxf.htm` | ✅ | ✅ | AutoCAD 交换 |
| **OBJ** | `common_vbaie_obj.htm` | ✅ | ✅ | Wavefront |
| **GDSII** | `common_vbaie_gdsii.htm` | ✅ | ✅ | 半导体版图 |
| **Parasolid** | `parasolid_object.htm` | ✅ | ✅ | 西门子原生 |
| **CATIA** | `common_vbaimp_exp_catia_object.htm` | ✅ | ✅ | CATIA V4/V5 |
| **ProE/Creo** | `common_vbaimp_exp_proe_object.htm` | ✅ | ✅ | PTC Creo |
| **SolidWorks** | `solidworks_object.htm` | ✅ | ✅ | SolidWorks |
| **SolidEdge** | `solidedge_object.htm` | ✅ | ✅ | SolidEdge |
| **Inventor** | `autodeskinventor_object.htm` | ✅ | ✅ | Inventor |
| **NX** | `siemensnx_object.htm` | ✅ | ✅ | Siemens NX |
| **HFSS** | `common_vbaimp_exp_hfss_object.htm` | ✅ | ❌ | Ansys HFSS 模型 |
| **Nastran** | `common_vbaimpexp_nastran_object.htm` | ✅ | ✅ | NASTRAN 网格 |
| **NFS** | `common_vbaimpexp_nfs.htm` | ✅ | ✅ | CST NFS 格式 |
| **Gerber** | `common_vbaimp_exp_gerber.htm` | ✅ | ❌ | PCB 制造 |
| **MecadTronik** | `common_vbaimp_exp_mecadtron_object.htm` | ✅ | ❌ | EDA 机械 |
| **HumanModel** | `common_vbaimp_exp_humanmodel.htm` | ✅ | ❌ | 人体模型 |
| **ASCII 导出** | `asciiexport_object.htm` | ❌ | ✅ | 通用 ASCII |
| **Mesh 导入** | `meshimport_object.htm` | ✅ | ❌ | 外部网格 |
| **VDaFS** | `vdafs_object.htm` | ✅ | ✅ | VDaFS |
| **Converter** | `common_vbaimp_exp_conventorware_object.htm` | ✅ | ✅ | 格式转换器 |

### 10.3 VBA → Python 转换范式

所有 VBA 操作通过 `add_to_history` 在 Python 中执行：

```python
# VBA:
#   With STEP
#       .Reset
#       .FileName (".\example.stp")
#       .Id ("1")
#       .ImportToActiveCoordinateSystem (True)
#       .Read
#   End With

# Python:
prj.modeler.add_to_history("ImportSTEP", """
With STEP
    .Reset
    .FileName (".\\example.stp")
    .Id ("1")
    .ImportToActiveCoordinateSystem (True)
    .Read
End With
""")
```

**注意点：**
- VBA 字符串中的反斜杠需要双写（`"\\"`）
- `add_to_history` 的第一个参数是历史树中显示的名称
- 多段 VBA 可以写在同一个 `add_to_history` 调用中
- 复杂 VBA 可以先用 `BeginHide()`/`EndHide()` 包装以防止中间 UI 刷新

### 10.4 常用 VBA 模式速查

```python
# STEP 导入
prj.modeler.add_to_history("ImportSTEP", """
With STEP
    .Reset
    .FileName ("C:\\path\\to\\model.stp")
    .Healing (True)
    .ScaleToUnit (True)
    .Read
End With
""")

# SAT 导入
prj.modeler.add_to_history("ImportSAT", """
With SAT
    .Reset  
    .FileName ("C:\\path\\to\\model.sat")
    .Read
End With
""")

# IGES 导入
prj.modeler.add_to_history("ImportIGES", """
With IGES
    .Reset
    .FileName ("C:\\path\\to\\model.igs")
    .Read
End With
""")

# 创建 Brick（直接 VBA）
prj.modeler.add_to_history("CreateBrick", """
With Brick
    .Reset
    .Name "brick1"
    .Component "component1"
    .Material "PEC"
    .Xrange "-5", "5"
    .Yrange "-5", "5"
    .Zrange "0", "10"
    .Create
End With
""")

# 参数改值（也可以直接 COM 调用）
prj.modeler.add_to_history("ChangeParam", """
StoreDoubleParameter("width", 10.0)
""")
```

### 10.5 Python API 文档

Python API 的官方文档位于 `Online Help\Python\`，以 Sphinx HTML 格式组织：

```
C:\Program Files\CST Studio Suite 2026\Online Help\Python\
├── main.html              # 主入口
├── genindex.html          # 总索引（按字母）
├── py-modindex.html       # 模块索引
├── source/
│   ├── cst.html           # cst 包总览
│   ├── cst.interface.html # 运行时 API (102KB)
│   ├── cst.results.html   # 结果读取 API (63KB)
│   ├── cst.units.html     # 单位 API (40KB)
│   ├── cst.eda.html       # EDA 接口 API (920KB, 最大的)
│   ├── cst.radar.html     # 雷达 API (175KB)
│   └── cst.asymptotic.html# 渐近求解器 API (49KB)
```

> **建议：** 在浏览器中打开 `main.html` 浏览 Python API 文档，比读源码更高效。
