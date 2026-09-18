---
description: TPC 库总入口 —— 读 TPC 源码前先读本文件。拓扑光子晶体 CST 自动化建模与排错：cst_solver 封装、mesh_grid.tri_grid（TopoPath 路径 DSL / 晶格）、topo_modeler 构建器。含「按需查阅地图」「报错定位表」「z 平面 / 布尔语义 / 阵列范围 三条硬约定」「已知库缺陷」「验收清单」，用于快速定位错误来源并按需只读 1~2 个文件，避免通读整包。
applyTo: "**/*.py"
---

# TPC 库使用与排错手册

> **AI 助手：读 TPC 库源码前先读本文件。** 第 0~2 节是省 token 的索引与硬约定：先把问题定位到 1~2 个文件，再只读那几个文件的相关函数。

## 0. 省 token 铁律

1. **禁止通读整包**（`os.walk` + 全读）。先在第 2 节查到目标文件，只读那个文件的相关函数。
2. **要接口签名时优先读 `cst_solver/setup.pyi`** —— 类型存根含全部方法签名，一屏读完。
3. 用 `grep`/`Select-String` 定位函数名，只读函数定义行 + docstring，不要整文件读。
4. 需要低成本总览时用 AST 只取名字（不读实现）：打印每个 `.py` 的文档首行 + `FunctionDef/ClassDef` 名。
5. 子包细节读使用者技能文档：`./tri-grid.md`、`./hex-grid.md`、`./topo-modeler.md`。

## 1. 包结构（6 层）

```
TPC/                              ← 已 pip install -e .，无需 sys.path.append
├── cst_solver/       CST VBA 封装（Mixin 聚合，入口 setup；库开发见 ../developer/cst-solver-dev.md）
├── mesh_grid/        纯算法：tri_grid（三角晶格/路径 DSL）、hex_grid（六边形/DXF）
├── topo_modeler/     建模引擎：TopoModeler + builders/ 各部件构建器
├── topo_templates/        端到端模板（StraightWaveguide / UnitAntenna）
├── tpc_service/      运行服务层（P2）：工程注册 + 任务服务 + 单 worker；不依赖 MCP
├── integrations/cst-mcp/  MCP 服务（P3）：发行名 tpc-cst-mcp，11 个工具，stdio 入口
└── tpc_toolkit/      独立工具（s2p 解析 / 遗传算法 / 等效介质），不依赖 CST
```

**安装一次即可**（在仓库根目录执行）：

```bash
pip install -e .
```

```python
from cst_solver import setup                                  # CST 工程控制
from mesh_grid.tri_grid import TopoPath                       # 路径 DSL + 晶格
from topo_modeler.builders import (build_vpc_regions, build_feed,
                                   build_waveguide, add_port_for_antenna)
```

> ⚠️ **不要再写 `sys.path.append(r'D:\...\TPC')`。** 那是 pip 安装方式引入前的
> 临时做法，换机器/换目录就会失效（旧 notebook 里 84 处都是这么写的）。
> 推荐通过环境变量 `CST_INSTALL_PATH` 或 `CST_CONFIG_FILE` 指向用户 JSON 配置；旧 `config.py` 仍兼容。运行 `python -m cst_solver doctor --probe` 检查接口导入，不会启动 CST。普通 `import cst_solver` 不要求 CST；实际建模和读 .cst 结果才需要官方接口。见 [环境配置](../../docs/guides/cst_environment.md)。

### 中文图与负号（所有 Matplotlib 图通用）

在创建 Figure **之前**使用共用字体配置；正式导出把标题/坐标/图例中的中文传入 `text` 并用 `strict=True`：

```python
from mesh_grid.plotting import chinese_plot_style
import matplotlib.pyplot as plt

with chinese_plot_style(text='频率透射系数', strict=True):
    fig, ax = plt.subplots()
    ax.plot([300, 320, 340], [-2, -3, -1])
    ax.set_xlabel('频率 (GHz)')
    ax.set_ylabel('透射系数 (dB)')
    fig.savefig('s21.png', dpi=180, bbox_inches='tight')
    plt.close(fig)
```

不要直接写 `font.sans-serif=['SimHei']` 或 `family='Microsoft YaHei'`：字体可能不存在。工具会检查真实字形；无中文字体时配置 `TPC_CJK_FONT` 或改为英文标签，不要屏蔽 Glyph missing 警告。负号和 PDF/SVG 字体已统一处理。保存后查看一次图，确认中文、图例、负刻度完整。[完整指南](../../docs/guides/chinese_plotting.md)

### Python 与 AI 两种入口的当前状态

Python 包可直接使用；**MCP 服务首版已实现**（P3，独立发行项目 `integrations/cst-mcp/`，发行名 `tpc-cst-mcp`，包名 `cst_mcp`），安装与配置见 [`integrations/cst-mcp/README.md`](../../integrations/cst-mcp/README.md)。证据是**离线 46 项测试**（假后端 + 内存传输 + 真 stdio 杂讯检查）；**真实 CST 上的端到端闭环属计划 P4/V9，尚未进行**。用 AI 编排时仍要读取实际结果、保留参数/单位与消息，不能把 doctor 的 `importable` 当作仿真已通过（P4/V8 真机已确认：`doctor --probe` **不创建设计环境**，`importable` 仅表示**接口能加载**，与许可/仿真无关；见 [`docs/validation/p4_real_machine_evidence.md`](../../docs/validation/p4_real_machine_evidence.md) §1）。

### MCP 入口怎么用（P3 首版，离线验证）

给支持 MCP 的 AI 客户端（Claude Desktop / VS Code / 自研客户端…）接上 CST 能力，只需要两步安装 + 一段客户端配置：

```bash
# 1) 核心包（几何 / 执行 / 数值能力）
pip install -e .
# 2) MCP 服务（依赖 tpc-cst>=2.0.0,<3 与 mcp==1.29.1；要求 Python ≥ 3.10）
pip install -e integrations/cst-mcp
```

> ⚠️ 改完核心包**要重装**：新增顶层包（如 P2 的 `tpc_service`）之后必须重新 `pip install -e .`，
> 否则旧的可编辑安装映射里没有它，在 `integrations/cst-mcp/` 目录里 `import tpc_service` 会 `ModuleNotFoundError`。

自检（不启动服务、不启 CST）：

```bash
python -m cst_mcp --check     # 打印能力报告 JSON：CST 可用性、后端、模板、工具清单与限制
```

客户端配置（任何支持 MCP 的客户端都是「启动一条 stdio 命令」）：

```json
{
  "mcpServers": {
    "tpc-cst": {
      "command": "python",
      "args": ["-m", "cst_mcp"],
      "env": {
        "TPC_MCP_WORKDIR": "D:\\tpc_mcp_work",
        "CST_INSTALL_PATH": "C:\\SOFTWARE\\CST Studio Suite 2026"
      }
    }
  }
}
```

| 阶段 | 工具 |
|---|---|
| 先看能力（离线，不启 CST） | `get_capabilities` → `list_templates` → `validate_model_spec` |
| 建模（异步任务） | `build_model` → `get_project_state` |
| 求解（异步长任务） | `run_simulation` → `get_job_status` |
| 取结果 / 分析 / 报告 | `get_results` → `analyze_s_parameters` → `export_report` |
| 收尾 | `close_project`（只关本服务创建的会话） |

四条最容易踩的边界（详细口径见 [包说明](../../docs/packages/cst_mcp.md) 与
[`integrations/cst-mcp/README.md`](../../integrations/cst-mcp/README.md)）：

- **`interrupted` 不是成功**，且**不会自动重跑**；判断状态要认全 `queued/running/succeeded/failed/interrupted`。
- **多段连续合格区间按段列出，绝不合并**；`total_bandwidth_ghz` 是各段之和（dB 口径 `20·log10|S|`、零值 −300 dB）。
- **失败是结构化错误**（`{code, message, details, retryable}`），不会变成空数据；`get_results` 在任务未成功时返回错误而不是空结果。
- **缺关键物理条件要问用户**：模板默认值会显式回显（`effective` / `field_sources`），**不得**用默认值静默代替用户意图。

## 2. 按需查阅地图（**照此表读文件，别通读**）

| 你要做什么 | 读这个文件 |
|---|---|
| **提交任务 / 查状态 / 取产物（幂等、重启恢复）** | `tpc_service/service.py`、`tpc_service/state.py`（用法见 §「共用运行服务 tpc_service」） |
| **MCP 工具表 / 参数 Schema / 返回结构** | `integrations/cst-mcp/src/cst_mcp/tools.py`（`TOOL_SPECS` + `HANDLERS`）、`server.py` |
| MCP 协议通道保护（stdout 隔离） | `integrations/cst-mcp/src/cst_mcp/isolation.py` |
| MCP 工作目录 / 后端 / 运行服务单例 | `integrations/cst-mcp/src/cst_mcp/runtime.py` |
| MCP 的 S 参数分析口径（dB / 多段带宽 / 谐振） | `integrations/cst-mcp/src/cst_mcp/analysis.py` |
| 工程注册与会话归属（副本 / 覆盖策略） | `tpc_service/registry.py` |
| 任务记录落盘与工作目录约束 | `tpc_service/store.py` |
| 后端契约 / 假后端 / 真实 CST 接线 | `tpc_service/backends/{base,fake,cst_backend}.py` |
| 任何 `app.xxx()` 的签名 | `cst_solver/setup.pyi`（最快） |
| 开/关/保存工程、`app.cst_file` | `cst_solver/project.py`、`cst_solver/__init__.py` |
| 参数 `para/freq_limit` | `cst_solver/parameters.py` |
| 基础体 `square/cylinder/triangle/hexagon` | `cst_solver/modeling/primitives.py` |
| 曲线 `polyline/ellipse` | `cst_solver/modeling/curves.py` |
| **拉伸 `extrude`（z 平面问题见 §3.1）** | `cst_solver/modeling/curves_ops.py` |
| **布尔 `add/subtract/intersect/insert`（旧拼写 `substract` 仍作别名保留）（语义见 §3.2）** | `cst_solver/modeling/booleans.py` |
| 变换 `translate/rotation/mirror` | `cst_solver/modeling/transforms.py` |
| `pick_face/pick_edge` | `cst_solver/modeling/picks.py` |
| 材料/组件 | `cst_solver/material/materials.py` |
| 端口 `add_port` | `cst_solver/simulation/ports.py` |
| 监视器 `define_monitor/monitor2d` | `cst_solver/simulation/monitors.py` |
| 求解器 `T_solver/run` | `cst_solver/simulation/solver.py` |
| 边界/背景 | `cst_solver/simulation/boundary.py` |
| 导入导出 DXF/STEP | `cst_solver/import_export/io.py` |
| 结果读取（S 参数/远场） | `cst_solver/_result_core.py`、`cst_solver/postprocessing/`、`tpc_toolkit/s2p.py` |
| 路径 DSL、CST 表达式生成、阵列范围 | `mesh_grid/tri_grid/topo_path.py` |
| 晶格/坐标/可视化函数 | `mesh_grid/tri_grid/core.py` |
| 六边形透镜 / DXF | `mesh_grid/hex_grid/core.py` |
| 整体编排、智能推断 | `topo_modeler/modeler.py` |
| 光晶阵列生成（核心 25 行） | `topo_modeler/builders/crystal.py` |
| 探针几何（AB/BA/圆柱） | `topo_modeler/builders/feed.py` |
| 空心铜波导 | `topo_modeler/builders/waveguide.py` |
| 端口添加 | `topo_modeler/builders/port.py` |
| 求解器/监视器配置 | `topo_modeler/builders/solver.py` |
| VPC 区域 / 基板 | `topo_modeler/builders/vpc_region.py`、`substrate.py`（⚠ §6） |

## 3. 三条硬约定（不遵守必出错）

### 3.1 z 平面：拉伸方向由多边形绕向决定 ✅实测

CST `ExtrudeCurve` 沿多边形**法向**拉伸，法向由顶点绕向决定：

| 顶点绕向 | 拉伸方向 | 居中到 z=0 |
|---|---|---|
| 逆时针 CCW（有向面积 > 0） | +z（0 → h） | `translate -h/2` |
| 顺时针 CW（有向面积 < 0） | −z（0 → −h） | `translate +h/2` |

绕向不一致 ⇒ 两实体在 z 上差一个 `h` ⇒ **布尔相交得空集、实体"莫名消失"，且库不报错**。

```python
def signed_area(p):                    # >0 = CCW
    import numpy as np; p = np.asarray(p, float)
    return 0.5 * np.sum(p[:-1, 0] * p[1:, 1] - p[1:, 0] * p[:-1, 1])
assert signed_area(my_poly) > 0        # 手写多边形拉伸前先自检
```

- 库的 `triangle()`、AB/BA 探针都是 **CCW + 内部 -h/2**（放心用）
- 想彻底避开绕向问题：**用 `app.square()`（Brick）直接给 zmin/zmax** ← 裁剪框首选
- `translate` 的 z 参数写成字符串表达式，如 `'-h/2'`

### 3.2 布尔语义 ✅实测

| 调用 | 结果 |
|---|---|
| `Solid.Intersect "A","B"` | 交集**保留在 A**，B 被消耗 |
| `Solid.Add / Subtract "A","B"` | 结果在 A，**B 被删除** |
| `Solid.Insert "A","B"` | 把 B 嵌入 A，**B 仍可被其它布尔继续引用**（旧代码用它复制"裁剪工具"） |

即 `app.intersect('g1A', 'clip_A')` 之后 `g1A` 就是结果，`clip_A` 已不存在。

### 3.3 阵列范围：`get_array_range()` 只够细长直波导 ✅实测

`TopoPath.get_array_range()` 返回 `(xup, yup, ydn)`；**直线路径的 `yup/ydn` 只有 1~2**，
做菱形/宽板时阵列覆盖不到全宽 ⇒ 必须显式给范围。
注意 `build_topological_crystal()` **不接受** `xup/yup/ydn` 参数（内部自己调 `get_array_range()`）。

## 4. 报错定位表（症状 → 病因 → 动作）

| 症状 | 病因 | 动作 |
|---|---|---|
| `RuntimeError: Shape does not exist: component1:xxx` | 该实体此刻不存在：① 上一步布尔把它消耗了（§3.2）② 上一步相交得**空集**（§3.1 z 不共面）③ 命令在 CST 重建中被排队 | 查 §3.1；重操作**分单元**；下一条命令前 `model3d.Rebuild()` 同步 |
| 实体凭空消失、后续 `add` 报缺实体 | 同上②，最常见是 **CW 多边形 + `-h/2`** | 统一 CCW，或改用 Brick |
| `NameError: name 'x' is not defined` | ① 定义它的单元没跑 ② **旧 kernel 残留变量掩盖了 bug** | 重启 kernel → 全量顺序重跑；别信"上次跑通了" |
| `TypeError: build_vpc_regions() got an unexpected keyword argument 'topology'` | `topo_templates/*.py` 传了函数不接受的参数（§6） | 不用 topo_templates，直接调 builders |
| 改参数不生效 | `para()` 只 `StoreParameter`，需刷新 | `app.para(name, val, log_flag=1)` 或 `full_history_rebuild()` |
| 端口选到错误的面 | `pick_face` 面编号依赖具体几何 | 试 `'10'` / `'22'`，或先在 CST 里看面号 |
| 求解器 VBA 报错 | `builders/solver.py` 的 `configure_solver` 含存疑 VBA（`.ParallelizationThreads`、`.GPUAcceleration`） | 优先用旧 notebook 实测过的 `With Solver … End With` 整块 |
| `FileNotFoundError: CST project file not found` | 相对路径按**工作目录**解析 | 模板 `tmp.cst` 放 notebook 同目录 |
| `ImportError: cst` | CST python 库路径没配 | 改 `cst_solver/config.py` 的 `CST_INSTALL_PATH` |
| `AttributeError: … no attribute 'GetBoundingBox'` | `cst_file.modeler` 已废弃 | 改用 `cst_file.model3d` |
| `CstOperationError: cst_unavailable`（`code='cst_unavailable'`） | 没有 CST 环境（CST 初始化失败 ⇒ `app is None`）；**P1 起 `TopoModeler.run()/save()` 不再静默 no-op 返回成功**（见文末「离线预检 / 运行契约 / 结构化失败」§4） | 无 CST 时不要当成「跑完了」，如实上报；只做流程编排用 `m.validate()`（返回 error 结果、不抛） |
| 保存后模型里有垃圾实体 | 实验性命令写进了历史 | 关工程 → 从干净模板重开 → 重跑 → 重新保存（§5） |
| `RuntimeError: An error occurred while trying to execute add_to_history: (&H8000ffff) …` | 下发的 VBA 被 CST 拒绝 —— 走的是**异常**通道，不是消息通道 | 按 CST 原文改 VBA；例：`.Coordinates` 的合法值只有 `"Free"` / `"Full"` / `"Picks"`（§4.1） |
| 拾取明明成功，`pick_face_auto()` 却返回 `None` | 脏工程：历史里的失败命令被 `get_messages()` **反复**报出，「消息为空」判据失效 | 改用正向判据 `get_picked_count('face') == 1`；库侧已修（§4.1 + 文末「面拾取」） |
| 建模时刷 `[LOG_FLAG_NO_REBUILD]` 警告（守卫 T7'/T13） | ① **先判断是不是重复登记**：同一条路径的参数被**多个构建器重复登记**曾导致**误报**（2026-09 已修，`TopoPath.auto_define_cst_params()` 现已幂等），此时参数值根本没变；② 真的是「改了**已有**参数但没重建历史」 | ① 误报：升到修好的版本即可，**不用改建模代码**；② 真报警：`app.para(name, val, log_flag=1)` 或 `full_history_rebuild()`（§7） |

### 4.1 主要反馈通道之一：CST 自己的消息日志 ✅实测

CST 的失败有**两条**通道，都要看：

1. **`add_to_history()` 可能直接抛 Python 异常** —— 异常文本里带 CST 原文，例如
   `RuntimeError: An error occurred while trying to execute add_to_history:
   (&H8000ffff) Invalid coordinate type. Please specify either "Free", "Full" or "Picks".`
   这条是**显式失败**，代码里不接就会中断；
2. **有的失败只写消息**，完全不抛异常。所以每个重操作后还要**读 CST 日志**
   （只读、不污染历史）：

```python
def cst_log(tag=''):
    msgs = app.cst_file.get_messages()      # 读一次清一次；但历史失败会反复报出（见下方 ⚠）
    print(f'[{tag}]', '无消息' if not msgs else msgs)

app.intersect(g1A, clip_A); cst_log('g1A ∩ clip_A')
app.cst_file.model3d.Rebuild()              # 阻塞式强制重放历史（大模型约数秒）← 最佳同步点
cst_log('完整重建后')
```

> ⚠️ **脏工程里消息会一直报历史失败，别拿它当唯一判据。**
> 实测（2026-09-17，CST Studio Suite 2026 真机）：工程历史里只要留下**一条失败命令**，
> 之后**每次** `get_messages()` 都会**再次**报出那条历史失败，并不是「读一次就干净」。
> 于是「消息为空 = 成功」在脏工程里会**一直判失败** —— 实测 `pick_face_auto()` 因此一直返回
> `None`，而 `GetNumberOfPickedFaces()` 明确是 `1`（拾取其实成功了）。
> 正确做法：**有正向信号就用正向信号**（拾取用 `get_picked_count('face') == 1`），
> 取不到计数时才退回「消息为空」判定 —— 库侧已按此修好 `_pick_succeeded()`（见文末「面拾取」）。
> 证据见 [`docs/validation/p4_real_machine_evidence.md`](../../docs/validation/p4_real_machine_evidence.md) §3。

其它探测手段：
- `app.cst_file.model3d` 有 387 个方法，可 `dir()` 找（`Rebuild`、`StoreParameter`、`add_to_history` 等）
- 判断实体是否存在（`add_to_history` 会真校验）：`app.add(name, 'ZZZ_GHOST')`；
  报错里出现 `ZZZ_GHOST` ⇒ `name` 存在，出现 `name` ⇒ 它不存在
- 已保存的工程可直接读磁盘（§5 第 4 条）

## 5. 验收清单（每次交付建模 notebook 必做）

1. 每个重操作后 `cst_log()` 无消息；`model3d.Rebuild()` 后无消息
   （⚠️ 结论**须在干净工程里**得出：脏工程里消息会反复报历史失败，见 §4.1）
2. **重启 kernel → 从第一个代码单元顺序全量重跑**（唯一可信的验证）
3. notebook 无 error 输出（用 json 扫 `output_type == 'error'`）
4. 保存后核验磁盘产物（**不用连 CST**）：
   - `<工程名>/Model/3D/ModelHistory.json` → 只应出现本项目实体名，grep 模板残留（`vpca`/`feed1`/`epc1`…）
   - `<工程名>/Model/Parameters.json` → 参数是否按预期写入，**连表达式一起看**：CST 几何用到的
     每个尺寸都应在这里查到 `name`/`expr`/`descr`，而不是散落在 notebook 里的浮点数
5. 编辑 notebook 后**回读文件核对**：工具报"编辑成功" ≠ 文件已更新（编辑器缓冲区可能覆盖）；
   改 notebook **优先整格重写**（`edit_notebook_file`），多段替换容易把单元改乱
6. **CST 建模调用里不得出现硬编码数值**：`app.ellipse(2.0612, 1.5751, [1.3296,'0'])` ✗
   → `app.ellipse('ec_a', 'ec_b', ['ec_c','0'])` ✓（详见文末「挖孔板 / 椭圆透镜」一节）

## 6. 已知库缺陷（可直接改库）

| 位置 | 缺陷 | 影响 | 建议 |
|---|---|---|---|
| `builders/vpc_region.py` `build_vpc_regions(side='lower')` | 生成**顺时针**多边形，却用内部 `translate -h/2` | 下半区与晶体差一个 h → 相交空集 | 多边形统一 CCW，或按绕向取 `±h/2`，或改 Brick |
| `builders/substrate.py` `build_substrate` | 同上（带状多边形为 CW） | 基板错一个 h 的平面 | 同上 |
| `topo_templates/straight_waveguide.py` | 调 `build_vpc_regions(..., topology=...)`、`build_topological_crystal(..., xup/yup/ydn=...)`，两函数都不接受 | 模板直接 TypeError | 去掉多余参数，或给构建器加形参 |
| `topo_templates/unit_antenna.py` | 同 `topology=` 问题 | 同 | 同 |
| `builders/crystal.py` | 阵列范围只能从 `path.get_array_range()` 推断 | 宽板覆盖不全 | 加 `xup/yup/ydn` 形参 |

## 7. 最小可用配方（实测写法）

```python
import numpy as np                               # 前提：已 pip install -e .
from cst_solver import setup
from mesh_grid.tri_grid import TopoPath
from topo_modeler.builders import build_feed, build_waveguide, add_port_for_antenna

a, h, lx1 = 0.2425, 0.25, 9                  # 晶格常数 / 板厚 / 路径周期数
e1, e2 = a / 2, a * np.sqrt(3) / 2           # x = c*a + r*a/2, y = r*a*√3/2, +c 即 +X
d_xmax, d_ymax = lx1 * a, lx1 * e2           # 菱形板：长对角线 / 半宽

path = TopoPath.builder(a, name='p').start(0, 0).move(lx1, 'c').build()
path.preview()                                # 预览不需要 CST

try: app.close()                              # 重复运行先关旧环境
except Exception: pass
app = setup('tmp.cst')                        # 相对工作目录，模板必须存在

app.para('a', a); app.para('h', h)
app.para('e1', 'a/2'); app.para('e2', 'a/2*sqr(3)')
app.para('l1', '0.65*a'); app.para('l2', '0.35*a')      # BA：l1 大孔 / l2 小孔
app.para('lx1', lx1)
path.auto_define_cst_params(app, prefix='p')            # 生成 p1x,p1y,p2x,p2y
app.new_material('Copper (annealed)'); app.new_material('Silicon (lossy)')
app.para('fmin', '300'); app.para('fmax', '380'); app.freq_limit('fmin', 'fmax')

# 裁剪框用 Brick（显式 z，最稳）；菱形板用 CCW 顶点 + extrude 'h' + translate '-h/2'
app.square('0', 'd_xmax', '0', 'd_ymax', '-h/2', 'h/2',
           'clip_A', 'component1', 'Silicon (lossy)')

# 光晶阵列：triangle() 造超元胞 → rotation 120°×2 → translate 阵列（见 crystal.py），
# 手动版必须显式给 xup/yup/ydn
feed = build_feed(app, feed_type='ba_tapered', name='feed2')
wg = build_waveguide(app, name='wg1', x_min='-lf5-lf6-lf4', x_max='-lf4', y_center='0')
add_port_for_antenna(app, waveguide_name=wg, port_face='10')

app.add('g1A', feed)
app.define_monitor('E', np.arange(300, 322, 2))
app.cst_file.model3d.Rebuild()                          # 同步 + 自检
app.cst_file.save(r'<绝对路径>\out.cst', include_results=False, allow_overwrite=True)
```

> **导出结果后保存要用 `include_results=False`**（P4/V4 真机验收，2026-09-17）：
> 先在**已求解工程的副本**上 `export_result_1d('S-Parameters\\S1,1', path)` 真的产出文件后，
> 再用 `save(include_results=True)` 会**如期**触发守卫告警 `SAVE_AFTER_RESULT_EXPORT`
> （plan_id=T3，severity=warning）；改成 `include_results=False` **就不再告警**，与守卫建议一致。
> 证据见 [`docs/validation/p4_real_machine_evidence.md`](../../docs/validation/p4_real_machine_evidence.md) §5。

## 8. 坐标与方向速查

- 三角晶格：`x = c*a + r*(a/2)`，`y = r*(a/2)*√3`；`e1 = a/2`，`e2 = a*√3/2`
- 6 个主方向（逆时针）：0°`(0,+1)`、60°`(+1,0)`、120°`(+1,-1)`、180°`(0,-1)`、240°`(-1,0)`、300°`(-1,+1)`
- `+c` = +X；`TopoPath.move(n, 'c')` 即沿 +X 走 n 个周期
- `triangle(a, h, center, theta, name, curve)`：`theta=[0,0,0]` 朝上、`[0,0,180]` 朝下
- 晶格菱形（斜边严格 ±60°，长对角线 = `lx1*a`）顶点（**此顺序即 CCW**）：
  `(0,0) → (lx1*a/2, -lx1*e2) → (lx1*a, 0) → (lx1*a/2, lx1*e2) → 闭合`

---

## 9. 读结果 / 后处理（API 索引）

`result` 类独立于 `setup`，用于读取已算完的工程：

| 方法 | 用途 |
|---|---|
| `result(工程路径)` | 打开结果 |
| `get_available_results()` | 列出可用结果树（**先看它**，再按 `tree_path` 读具体项） |
| `get_tree_items()` | 结果树条目 |
| `read_s_parameter(s_param, run_id)` | 读 S 参数，如 `'S1,1'` |
| `read_1D / read_2d / read_3d(tree_path, run_id)` | 读 1D/2D/3D 结果 |
| `get_run_ids(treepath, skip_nonparametric)`、`get_all_run_ids(max_mesh_passes_only)` | 取 run id |

```python
from cst_solver import result
res = result(r'<工程绝对路径>')
print(res.get_available_results()[:5])       # 先看树，再读具体项
s11 = res.read_s_parameter('S1,1')
```

配套模块：`tpc_toolkit/s2p.py`（`read_s2p_groups` 批量读 s2p；原根目录 `read.py` 已迁入该包）、`postprocessing/proc.py`、`farfield.py`、`plot.py`、`result_export.py`。

> 以上为**签名索引**（取自 `cst_solver/_result_core.py`），返回结构待首次实测后补成完整配方。

---

## 离线预检 / 运行契约 / 结构化失败（P1，2026-09 新增）

> ⚠️ 本节所有结论目前**只有离线测试证据**（`cst_solver/tests/`、`topo_modeler/tests/`、`tests/`）；
> **真机验收属计划 P4**（[统一计划](../../docs/next_plan/README.md)），不要当成「已通过真机验证」。

### 1. 先离线预检，再动手建模（`topo_modeler/preflight.py`）

预检**不导入 CST、不建 DE**（CST 只做路径级诊断），所以可以在没有 CST 的机器上先把规格过一遍。

| 入口 | 作用 |
|---|---|
| `list_templates()` | 默认只列**可构建**的模板；`include_planned=True` 才把未实现类型也列出来（带 `buildable=False` 与 `reason`） |
| `describe_template(model_type)` | 字段/类型/单位/取值范围/默认值/是否必填 |
| `validate_model_spec(spec, …)` | 完整预检，返回 `ok/buildable/normalized/effective/field_sources/ctor_kwargs/errors/warnings/assumptions/checks/cst` |

```python
from topo_modeler.preflight import list_templates, describe_template, validate_model_spec

print([t['model_type'] for t in list_templates()])                       # 只列能建的
print([t['model_type'] for t in list_templates(include_planned=True)])   # 未实现的也在（buildable=False）
print(describe_template('straight_waveguide')['required'])               # 该模板的必填字段

report = validate_model_spec('spec.yaml')          # 不启动 CST
if report['errors'] or not report['buildable']:
    for e in report['errors']:
        print(e['code'], e['message'])             # 按 code 分流（见下）
else:
    print(report['effective'])                     # 用户输入 + 模板默认值（默认值可见）
    print(report['field_sources'])                 # 每个字段来自 'user' 还是 'default'
    print(report['ctor_kwargs'])                   # 真正会传给模板构造的参数
```

- **使用建议**：先 `validate_model_spec` 预检、再建模；**`errors` 为空且 `buildable` 为真**才建档。
- 无效输入会在 `errors` 里给出 `code`；**未实现的类型报 `model_type_not_implemented`**
  （`reason` 会写清「当前可构建的类型」）。
- `assumptions` 是预检**替你做的假设**（例如 `require_output=False` 时「缺 `output.path`」只记假设），
  **必须回显**给用户，不能吞掉。
- `errors` 里放的是**错误码清单**，常见的有：`config_unknown_field`、`config_type_error`、
  `config_value_out_of_range`、`config_enum_invalid`、`config_model_type_invalid`、
  `model_type_not_implemented`（未实现类型）、`template_not_found`（模板工程不存在）、
  `output_not_writable`。
- 直接调配置层时，`topo_modeler.config.ConfigError` 现在带 `code` 与 `details`，可**按码分流**：

```python
from topo_modeler.config import ConfigError, modeler_from_config

try:
    modeler = modeler_from_config(spec)
except ConfigError as exc:
    print(exc.code, exc.details)      # 例如 config_unknown_field / config_value_out_of_range
```

### 2. 运行契约：`run_checked()` 和 `run()` 的区别（`cst_solver/run_contract.py`）

| | `app.run()` | `app.run_checked(...)` |
|---|---|---|
| 返回 | `None`（**行为一字未改**） | `dict`：`status` / `errors` / `evidence` / `fingerprint_before` / `fingerprint_after` … |
| 说明什么 | 只说明 VBA **提交**没炸 | 说明**算完了、且结果是本次的**（或如实说明不是） |
| 记录 | 无 | 默认落盘工程目录的 `run_contract.jsonl` |

`succeeded` 要**四件事同时成立**：提交未抛异常 + `get_messages()` 为空 + 结果存在 +
结果指纹在提交前后发生变化；否则给 `failed`（提交异常 / 消息非空）或 `unverified`
（没异常也没消息，但结果缺失 / 未变化 / 指纹查不到）。**`unverified` 不得当成成功。**
> ⚠️ 其中「`get_messages()` 为空」这一条在**脏工程**里会一直不成立（历史失败反复报出，见 §4.1），
> 所以别把消息判据当成唯一依据，正向信号（结果指纹、几何量、已选面数）优先。

```python
outcome = app.run_checked(note='wg1 首次求解')
print(outcome['status'])                 # succeeded / failed / unverified
if outcome['status'] != 'succeeded':
    for e in outcome['errors']:
        print(e['code'], e['message'])   # run_messages / results_missing / results_unchanged …
    raise SystemExit('本次运行没有可确认的结果')   # 别把它写成「跑完了」
```

| 错误码 | 含义 |
|---|---|
| `run_exception` | 提交求解时抛了异常 |
| `run_messages` | 提交后 CST 消息非空（有的失败不抛异常，消息是主要线索；脏工程里消息会反复报历史失败，见 §4.1） |
| `messages_unreadable` | 读消息本身失败 |
| `results_missing` | 工程里找不到任何结果 |
| `results_unchanged` | 结果指纹没变 —— 很可能还是上一轮的结果 |
| `results_not_verified` | 指纹不可用（探测失败 / 拿不到工程路径），**「有没有结果」其实是不知道** |
| `audit_write_failed` | 运行记录没能落盘（结论仍有效，但事后无法追溯消息） |

- **务必落盘**：CST `get_messages()` **读一次清一次**（但历史失败会反复报出，见 §4.1），
  `JsonlSink` 把读到的消息写进
  `run_contract.jsonl`（路径取 `run_log_path(project_path)`），否则事后无据可查。
- **局限**：`results_changed` 是**必要条件不是充分条件** —— 它只证明结果区变了，
  不证明这份结果就是本次算的（例如另一个会话也在写同一工程）。真正的判据要在真机上做
  小范围串行闭环，属计划 **P4/V7**。
- **`run_id=0` 不是历史编号**，它是「当前最新结果」的别名；要固定某次运行必须显式给具体 `run_id`。
  单位与口径直接取 `result_conventions()`（GHz、`s_db = 20*log10(abs(S))`、幅度 0 记 −300 dB），
  **不要另抄一份**。

### 3. 材料旧接口的失败怎么查（「空列表 / `None`」不再等于没事）

`new_material` / `list_library_materials` / `load_material_from_file` / `get_material_filepath`
这四个旧兼容接口的**返回值和日志文案一字未改**（旧 notebook 照跑），但失败现在会登记一条
结构化记录（`{code, message, details, retryable}`），所以「静默失败」能被看见：

```python
from cst_solver.failures import collect_failures, recent_failures, set_failure_strict

with collect_failures() as failures:
    app.new_material('Copper (annealed)')     # 名字不认识：返回值照旧，但会登记
    mats = app.list_library_materials()       # 空列表：先确认是不是材料库路径不存在
if failures:
    for f in failures:
        print(f['operation'], f['code'], f['message'], f['details'])
```

| 错误码 | 出现处 | 含义 |
|---|---|---|
| `material_not_preset` | `new_material` | 材料名既不在工程里、也不在材料库 |
| `material_library_missing` | `list_library_materials` | 材料库路径不存在（**空列表 ≠ 库里没有材料**） |
| `material_file_not_found` | `load_material_from_file` | `.mtd` 文件找不到 |
| `material_definition_empty` | `load_material_from_file` | `.mtd` 里没有有效定义 |
| `material_file_missing` | `get_material_filepath` | 取不到材料文件路径（**`None` ≠ 路径为空**） |

- 批处理 / CI 里想「失败就停」：`set_failure_strict(True)` —— 之后静默失败直接抛
  `CstOperationError`（带 `code` / `retryable` / `details`）；**用完记得关回去**，
  默认关闭就是为了兼容旧 notebook。
- `recent_failures(clear=True)` 读最近的记录（**包括**没放进 `collect_failures()` 的那些）。
- 离线回归：`pytest cst_solver/tests/test_failures.py -q`。

### 4. ⚠ 行为变更：`TopoModeler.run()` / `save()` 无 CST 环境时改为抛异常

- **旧行为**：`app is None`（CST 初始化失败）时**静默 no-op 却返回成功** ——
  把「没跑」「没保存」当成成功，是本库最危险的一类谎报。
- **新行为（P1）**：直接抛 `CstOperationError('cst_unavailable')`
  （`operation='TopoModeler.run'` / `'TopoModeler.save'`）。初始化失败时
  `TopoModeler._init_cst` 也会 `record_failure(..., 'cst_unavailable', ...)`，
  可用 `collect_failures()` 看到。
- **影响**：在无 CST 机器上做流程编排的代码要分开处理 —— `m.validate()` 仍**返回**
  error 结果（不抛），`m.run()` / `m.save()` 会**抛**。

```python
from cst_solver.failures import CstOperationError

try:
    modeler.run()
except CstOperationError as exc:
    print(exc.code, exc.retryable)      # 'cst_unavailable'
    # 没有 CST 环境：记成「未运行」，不要记成「跑完了」，也不要吞掉
```

---

## 共用运行服务 tpc_service（P2，2026-09 新增）

> 新增顶层包 `tpc_service/`：**工程注册 + 任务服务**（`RunService`），让 Python 用户和（P3 的）MCP 服务
> 共用同一套「提交 → 查状态 → 取产物」能力。它**不依赖 MCP**，也不重写几何/VBA/数值逻辑。
> ⚠️ 本节全部结论只有**离线测试证据**：`tpc_service/tests/` 共 **47 项**（含 `max_concurrent == 1` 的串行证据）。
> **真实 CST 后端 `CstBackend` 尚未验证，真机判据属计划 P4/V7**
> （[统一计划](../../docs/next_plan/README.md)）—— 不要当成「已通过真机验证」「生产可用」。
> （下文 `§P1-n` 指上一节「离线预检 / 运行契约 / 结构化失败（P1）」的第 n 小节。）

### 1. 什么时候用它

需要下面任何一件事，就用 `RunService`；都不是的话，单次建模**仍直接用模板或 `TopoModeler` 即可**
（见 §7 最小可用配方），不必套一层服务：

- **提交任务 → 查状态 → 取产物**：不想自己管「跑到哪一步了」；
- **幂等重发**：脚本重跑时用**同一个 `request_id`**，同参数的重复提交不会重跑第二遍；
- **重启后不丢历史**：任务记录落在 `<workdir>/jobs/<job_id>.json`（原子写）、事件流落在
  `<workdir>/events.jsonl`，服务重启后未完成的任务会被如实标成 `interrupted`；
- **多人/多入口共用一台 CST**：所有后端调用在**一个**专用线程里串行，天然不打架。

### 2. 最小例子（离线，假后端）

假后端不碰 CST，可在无 CST 的机器上把流程先跑一遍：

```python
import os
from tpc_service import RunService
from tpc_service.backends.fake import FakeBackend

work = r'D:\tpc_work'
os.makedirs(work, exist_ok=True)
template = os.path.join(work, 'tmp.cst')
open(template, 'w').close()          # 占位工程（假后端不解析文件内容）

service = RunService(work, backend=FakeBackend())      # 不传 backend 就是真实 CST（第 4 段）
job = service.submit('build', project_path=template,
                     params={'spec': {'model': {'type': 'straight_waveguide'}}})
print(job['status'], job['job_id'])                    # queued job-xxxxxxxxxxxx

done = service.wait(job['job_id'], timeout=10)
print(done['status'])                                  # succeeded
print(done['artifacts'])                               # [{'kind': 'project', 'path': ..., 'note': ...}]
print(service.logs(job['job_id']))                     # 后端日志
service.shutdown()
```

- `kind` 只有三种：`build` / `solve` / `study`。
- **未注册的 `project_path` 会自动注册**，默认**复制**到 `<workdir>/projects/` 再执行
  （`copy=False` 就地执行、`overwrite=True` 才刷新已有副本）。
- 状态词表就五个：`queued` / `running` / `succeeded` / `failed` / `interrupted`；
  **`interrupted` 不是成功**（重启后未完成的任务一律 `interrupted`，`error.code='service_restarted'`，**不自动重跑**）。
- 状态判断要**认全词表**：`if done['status'] != 'failed'` 这种写法会把 `interrupted` 当成跑通了。
- `wait(job_id, timeout=…)` **超时不抛异常**，只是返回**当前**状态（可能还是 `running`）——
  看到 `running` 就继续等，别当成功。服务快照：`service.describe()`
  （含 `worker` / `backend` / 各状态任务数 / `recovery`）。

### 3. 幂等与错误处理

**`request_id` 去重**：同一个 `request_id` + 同一种 `kind` + 同一份参数 ⇒ 返回既有任务并带
`duplicate=True`，**不会再执行一次**；同 ID 但参数/种类不同 ⇒ 抛 `request_id_conflict`。

```python
from tpc_service.errors import ServiceError

job = service.submit('solve', project_id=pid, request_id='wg1-solve-01')
again = service.submit('solve', project_id=pid, request_id='wg1-solve-01')
print(again['job_id'] == job['job_id'], again['duplicate'])   # True True —— 没有重跑

try:
    service.submit('solve', project_id=pid, request_id='wg1-solve-01',
                   params={'run_id': 3})                       # 同 ID 不同参数
except ServiceError as exc:
    print(exc.code)                                            # request_id_conflict
```

所有失败都是 `tpc_service.errors.ServiceError`，带 `code` / `message` / `details` / `retryable`，
`exc.to_dict()` 直接是 `{code, message, details, retryable}`（与 P1 的结构化失败**同一套口径**）：

| `code` | 含义 | 你该做什么 |
|---|---|---|
| `workdir_escape` | 产物路径逃出工作目录 | 检查自己拼的路径，写文件的路径必须走 `ensure_within()` |
| `project_not_found` | 工程文件不存在 | 先确认路径；用 `validate_model_spec` / 预检（§P1-1）挡住更早的错 |
| `project_exists` | 目标工作副本已存在且未允许覆盖 | 复用已有 `project_id`，或确认后 `overwrite=True` |
| `project_not_registered` | 工程 ID 没注册 | `service.projects()` 看现有 ID |
| `request_id_conflict` | 同一 `request_id` 提交了不同参数 | 换一个 `request_id`（别改参数硬塞进旧 ID） |
| `unknown_job_kind` | `kind` 不是 `build`/`solve`/`study` | 改 `kind` |
| `unknown_job` | 任务 ID 不存在 | 用 `service.list_jobs()` 列一遍 |
| `invalid_transition` | 任务状态迁移非法（内部一致性错误） | 不要自己改记录文件；报 bug |
| `cancel_not_supported` | 运行中的任务无法取消（CST 停止接口未核实） | 等它跑完；只有 `queued` 才 `cancel()` 得掉 |
| `backend_failed` | 后端执行失败（含「求解没确认保存」） | 看 `job['error']['message']` 与 `job['log']` |
| `service_shutdown` | worker 已关闭，不再接受任务 | 重新 `RunService(...)` |

- `cancel(job_id)` 只对 `queued` 生效（→ `interrupted` + `cancelled_before_start`）；
  `running` 会抛 `cancel_not_supported` —— 本库**不提供虚假的「已取消」**。
- **求解结果先保存再读**：`solve` / `study` 没确认保存（`saved` 不为 `True`）时服务层直接判 `failed`，
  因为 `run_id=0` 指向「当前最新结果」，不先保存就可能把**上一轮**的结果当本轮（同 §P1-2 的契约）。

### 4. 真实 CST 用法与边界

不传 `backend` 时用 `tpc_service.backends.cst_backend.CstBackend`：

```python
from tpc_service import RunService

service = RunService(r'D:\tpc_work')          # backend=None → CstBackend

# 建模：params['spec'] 就是 §P1-1 的模型规格（先预检、再建模、最后保存）
job = service.submit('build', project_path=r'D:\src\ant6.cst', params={'spec': spec})
built = service.wait(job['job_id'], timeout=3600)
pid = built['project_id']                     # 后续用 project_id 引用同一工作副本

# 求解：run_checked 判定成功 → 先保存 → 再读指标（saved=True 才可能成功）
job = service.submit('solve', project_id=pid, params={'note': 'wg1 首次求解'})
solved = service.wait(job['job_id'], timeout=7200)
print(solved['result_summary'])               # 指标摘要；run_identity 里有 run_token / run_id

# 参数研究：scan / batch / optimize（各自走 topo_modeler 的扫描/批量/优化器）
job = service.submit('study', project_id=pid, params={'study': {
    'kind': 'scan',
    'base_config': spec,                    # 模型规格
    'params': {'a': [0.9, 1.0, 1.1]},       # 要扫的参数 → 取值列表
}})
```

- `study` 的三种 `kind` 分别走 `topo_modeler.scanner.ParameterScan`（扫描）、
  `topo_modeler.batch.BatchModeler`（批量）、`topo_modeler.optimizer.GeneticOptimizer`（优化），内部串行。
- `build` 会先跑 `validate_model_spec` 预检（§P1-1），预检不过就不会启动 CST。
- ⚠️ **真机行为尚未验证（计划 P4/V7）**：本轮只有离线假后端证据，
  `CstBackend` 的建模/求解/参数研究**都还没在真机上跑过**，不要据此承诺结果可用。

---

## 库开发 / 维护视角 → 已拆成独立 skill

给 `cst_solver` **新增封装、修库内部缺陷、改 API 存根与文档**：
**`./.github/skills/cst-solver-dev/SKILL.md`**
（把 TPC 作为 VS Code 工作区打开时会自动加载，也可用 `/cst-solver-dev` 调用。）

本文件只负责「用库建模型 + 排错」。

---

## 面拾取：不要再硬编码面号（2026-09 新增）

CST 的面编号（`'10'` / `'22'` / `'9'` …）随几何与生成顺序变化，**布尔/扭转/阵列之后不可复用**。
库已提供按**坐标点**拾取的接口（`cst_solver/modeling/picks.py`）：

| 方法 | 说明 |
|---|---|
| `pick_face_at(name, x, y, z)` | 按坐标点拾取面（下发 `Pick.PickFaceFromPoint`），点需落在目标面上 |
| `pick_face_auto(name, points=[…], candidates=[…])` | 先按点逐个试、失败再按编号试；**优先以已选面数 `GetNumberOfPickedFaces() == 1` 判定成功**，取不到计数时才退回 `get_messages()` 判定（2026-09 真机修正：脏工程里消息会反复报历史失败，只看消息会一直判失败），返回 `('point',(x,y,z))` / `('id',fid)` / `None`，失败的点会自动 `pick_clear()` |

用法（扭波导 / 加端口这类面号会变的场景）：

```python
app.pick_clear()
app.pick_face_auto('wg1', points=[(1.13, 0.2878, 0)], candidates=('10',))   # 径向内端面（环壁中点）
app.set_edge('x_fold', '0', '1', 'x_fold', '0', '-1')                      # 定扭转轴
app.rotation_face('wg1_bend', 30, material='Copper (annealed)')            # 扭转该面
app.pick_clear()
app.pick_face_auto('wg1_bend', points=[(0.9861, 0.2493, 0)], candidates=('9',))   # 扭转后的面
app.extrude_face('wg1_sec', 'Ls', material='Copper (annealed)')            # 延长一段
```

> ⚠ `rotation_face` / `extrude_face` 的默认材料是 `Vacuum` / `PEC`，**必须显式传**目标材料（如铜）。
> ⚠ 每次拾取前先 `pick_clear()`，避免上一次的选取被后续操作带上。

---

## 挖孔板 / 椭圆透镜（GRIN 孔阵列）：2026-09 新增

用 `mesh_grid.hex_grid`（`HexGridVisualizer` + `create_staggered_grid` + `create_hex_polygon` + `save_to_dxf`）
做"六边形孔阵列 + 椭圆包络 − 孔阵列"这类渐变折射率（GRIN）透镜时，按下面六条做。

### 1. 孔网格的列范围必须**覆盖整个图形**（最容易翻车）
`create_staggered_grid(col_range, row_range)` 的 `(col, row)` 是**索引不是坐标**：
pointy 时 `x = a2*(col + (row%2)/2)`、`y = 1.5*hex_size*row`（`a2 = hex_size*sqr(3)`）。

图形关于原点不对称时（典型：椭圆**近焦点放在原点** ⇒ 椭圆跨 `x ∈ [ec_c-ec_a, ec_c+ec_a]`），
列范围**必须按图形的真实 x 范围算**，不能用对称的 `(-Nx, +Nx)`：

```python
col_min = int(np.floor((ec_c - ec_a) / a2)) - 1     # ← 不是 -Nx
col_max = int(np.ceil((ec_c + ec_a) / a2)) + 1      # ← 不是 +Nx
```

> 实测：`ec_a = 2.061、ec_c = 1.330` 时用 `±Nx = ±17` ⇒ 网格只到 `x = 2.06`，而椭圆要伸到 `3.39`
> ⇒ **外侧 1.33 mm（26% 面积）整片无孔 = 实心硅**（用户一眼就看出"有一块没挖空"）。

### 2. 边界那一圈孔要用"容差"收进来
只用标准椭圆判据 `((x-ec_c)/ec_a)^2 + (y/ec_b)^2 <= 1` 时，图形最扁的两头会留一圈没孔的实心边
（椭圆短半轴恰好落在某行孔心上时，那一行孔心全在界外 ⇒ 整行被丢掉）。
改用**到两焦点距离之和 ≤ 2a·tol**，`tol` 取 1.03~1.1：

```python
d1 = np.sqrt(x**2 + y**2); d2 = np.sqrt((x - 2*ec_c)**2 + y**2)
keep = (d1 + d2) <= 2*ec_a*tol          # 参考案例 Ant1_grid_BA_240D_epc_epc 用 1.1
```

界外的孔在 CST 里只会把图形边缘啃掉很小的缺口；**不这样做就一定留实心边**。

### 3. 验收：孔阵覆盖率（一条硬指标）
图形内任一点到**最近孔心**的最远距离 `d_max`；完好三角格子里最坏点（三角形重心）距离 = `格距/√3`。
`d_max ≈ 1.00×` 才算铺满。

```python
dmax = max( 图形内采样点到最近孔心的距离 )        # 与 格距/sqr(3) 比
# 实测：修复前 1.269 mm（18.1×，椭圆末端整片无孔）；修复后 0.0699 mm（1.00×）
```

> 采样图形内点时，楔形/被剪区域的角度判据要写 `np.mod(np.arctan2(y, x), 2*np.pi)`；
> 直接用 `atan2` 的原始负角区间会把"下半楔形"误判成图形内部（会让剪枝后的指标虚高）。

### 4. 尺寸参数一律用晶格常数 a 表出（含椭圆）
参数表里把"个数"单列出来，改 `a` 就能整体缩放，也便于核对：

```python
app.para('nrin',  '3*nsm/4',  expression='挖孔内切半径 = nrin 个晶格常数')
app.para('nRbig', 'nrin+lx1', expression='大六边形边长 = nRbig 个晶格常数（=17）')
app.para('rin',   'nrin*a');  app.para('Rbig', 'nRbig*a');  app.para('Ls', '2.2*nRbig*a')
```

实测（`a = 0.2425、nsm = 12、lx1 = 8`）：`nrin = 9`、`nRbig = 17`、`rin = 9a = 2.1825`、
**大六边形边长 = 17a = 4.1225**。改成表达式后 CST 求值结果与写死数值完全一致。

### 5. ★ 椭圆的建模：长短轴与中心**必须用 CST 变量**
`app.ellipse()` 的半径与中心都接受**参数名/表达式字符串**。照参考案例
`Ant1_grid_BA_240D_epc_epc.ipynb`（其 cell 8 / cell 10）的写法：

```python
app.para('ec_a', 'Nx*a2',              expression='椭圆长半轴')
app.para('ec_b', 'Ny*a2*sind(60)',     expression='椭圆短半轴')
app.para('ec_c', 'sqr(ec_a^2-ec_b^2)', expression='焦距：椭圆中心在 (ec_c,0)，近焦点在原点')
app.ellipse('ec_a', 'ec_b', ['ec_c', '0'], 'epc1')      # ← 不要写 2.0612 / 1.5751 / 1.3296
# 等价写法（参考案例用的）：app.ellipse('ec_a','ec_b',[0,0],'epc1') → translate('epc1',['ec_c','0','0'])
```

> ⚠ 把 Python 里算好的浮点数传给 `ellipse()`/`translate()` ⇒ 模型里就固化成数值了，
> 参数表里既看不到来源、也没法靠改 `a` 缩放。

### 6. GRIN 透镜建模配方（DXF → CST）
```python
app.dxf_import(dxf, add='True', component='gridlens', height='h')      # 孔阵列（实体名固定 import_1）
app.ellipse('ec_a', 'ec_b', ['ec_c', '0'], 'lens_epc')                 # 椭圆包络（变量！）
app.extrude('curve1:lens_epc', 'lens_epc', 'h', material='Silicon (lossy)', log_flag=1)
app.subtract('lens_epc', 'import_1', component2='gridlens')           # 椭圆 − 孔阵列 = GRIN 透镜
```

---

## 10. 大几何「建一次 + 子工程引用」架构（2026-09 实测，ANT6_C6_hexring）

**问题**：GRIN 透镜的孔阵列（DXF 里 2215 条多段线）每次 run 都要重建 ⇒ 单次 ≈ 300 s。

**实测数据（每次都在 CST 里真跑出来的）**

| 步骤 | 耗时 | 说明 |
|---|---|---|
| `dxf_import` 2215 条多段线 | **165–185 s** | ≈75 ms/条；与模型里已有多少实体无关 |
| y 镜像复制（2215 → 4351 孔） | 3 s | |
| 椭圆 − 孔阵列（布尔减） | **73–95 s** | |
| 楔形裁剪 / 平移 / 旋转 ×6 | 7.7 / 1.8 / 15.0 s | `rotation(..., unite=False)`：**不要**做布尔并（6×4351 壳做 union 会卡 >19 min） |
| 铜基板全流程（板+晶体+6 探针+6 铜管+6 端口） | **≈33 s** | 与透镜并行跑 |

⇒ 透镜 ≈ 300 s、基板 ≈ 33 s ⇒ **并行后可重叠**；透镜不变时整个 run ≈ 60 s。

**落地做法（子工程引用，CST 原生机制）**

```
ANT6_C6_tmpl.cst        干净模板（参考模型清空全部变量后的副本，只清一次，之后每轮 2 s 复制）
ANT6_C6_base.cst        基板工作工程（每轮复制；透镜稍后用子工程引进来）
ANT6_C6_lens.cst        透镜工程（只含透镜）
ANT6_C6_lens_export.sab 子工程几何（SAT.WriteAll 导出）
lens_build_standalone.py + lens_build.py   透镜构建（可独立 / 并行运行）
lens_params.json        notebook → 子进程的“本次意图参数 + CST 参数表”
```

单元顺序（关键）：`准备(判缓存+复制模板)` → `打开基板工程` → **`并行 subprocess.Popen(透镜脚本)`**
→ 基板建模（板/晶体/探针/铜管/端口） → **`import_subproject(.sab, .cst, scale_factor=…)`** → 监视器/求解器 → 保存。

**库接口**：`app.import_subproject(filename, subproject_name, scale_factor=...)`
= CST VBA 的 `StartSubProject … EndSubProject`（**链接式**子工程，会连带子工程的参数/材料）。
导出侧用 `SAT.Reset/FileName/SaveVersion/WriteAll`（`Write` 需要参数：`.Write("comp:shape")`）。

### ⚠ 四条踩过的坑（都是实测报错）

1. **两个工程的参数表必须完全一致**。透镜脚本里会出现 `translate(..., 'Rbig')` 这类
   基板工程才有的变量；子工程只登自己的 17 个参数时，CST 直接报
   `RuntimeError: Unable to evaluate expression: "Rbig"`。
   ⇒ **一张表、一个来源**：notebook 第 2.5 节定义 `CST_PARAMS`（40 项，= 原来单工程版的集合），
   notebook 第 4 节登记它，`lens_params.json` 里带 `ctsparams` 交给 `lens_build_standalone.py` 也登记它。
2. **`exec(open(...).read(), globals())` 共享命名空间**：被 exec 的透镜代码里有 `_t`（numpy 数组）、
   `_t0`、`_dt_*` ⇒ 驱动脚本里同名的计时变量会被覆盖，日志 `f'{t:.1f}'` 报
   `TypeError: unsupported format string passed to numpy.ndarray.__format__`，
   **后续的导出与保存全部被跳过**（白跑 300 s）。⇒ 驱动脚本变量加前缀，并且**几何建完先 `save()` 一次**。
3. **未裁剪的原始孔阵列不能早于端口拾取存在**（CST 报 `The picked port area is empty`）；
   成品透镜在六边形板之外，安全 ⇒ 缓存/引用进来的必须是成品透镜。
4. **子进程崩溃后 CST 会话不退出**，会一直占着 `.cst`，导致下一轮复制/删除工程失败
   ⇒ 重跑前 `Get-Process 'CST DESIGN ENVIRONMENT*' | Stop-Process`（只杀本次的）。

### 缓存有效性判定（毫秒级，不启动 CST）

读 `<透镜工程>/Model/Parameters.json`（字段 `name`/`expr`/`value`/`descr`），比对
`a, h, nsm, lx1, ratio, Nx, Ny, r1, r2`（含 `nsm/lx1`：透镜裁剪板 `Ls = 2.2*(nrin+lx1)*a` 由它们决定）
+ 检查 `.sab` 是否存在；一致就**跳过重建**，只 `import_subproject`。
app.subtract('lens_epc', 'lens_hex_cut')                              # 只剪掉与其它实体重叠的部分
# ↑ 该裁剪体 = 目标实体的**内角楔形**（六边形顶点内角 120° ⇒ 张开 120°~240° 的楔形）
app.translate('lens_epc', ['0', '0', '-h/2'])                          # z 居中（与板共面）
app.translate('lens_epc', ['Rbig', '0', '0'])                          # 局部原点（近焦点）→ 目标位置
app.rotation('lens_epc', [0, 0, 60], repetition=5, copy=True, unite=True)   # 6 重对称复制
```

> - 要求"**只剪重叠、不重叠的全留**"时，必须用目标实体的内角楔形去 `subtract`，
>   不能用"切掉内半边"的做法。
> - 孔阵列 DXF 用 `save_to_dxf()` 生成（内部 `unary_union`，孔不重叠时输出 MultiPolygon）。
> - 本模型实测：`ec_a = 2.0613、ec_b = 1.5751、ec_c = 1.3296`，871 个孔，覆盖率 1.00×。

### 7. DXF 只写一半，另一半在 CST 里镜像复制（导入提速）
**CST 的 DXF 导入耗时基本正比于多边形数量** —— 直接用阵列的对称性砍一半最省事。
本模型的孔阵列在 **y → −y** 下严格不变（椭圆中心在 `(ec_c,0)` 故对称轴是 y=0；
网格行 `y = k·行距` 正负成对、同一对行的 x 位置相同；孔半径只依赖 `y²`）：

```python
# 9b-①：只把上半平面写进 DXF
_upper = _yp >= 0
save_to_dxf([create_hex_polygon(center=(float(x), float(y)), cell_width=float(r))
             for x, y, r in zip(_xp[_upper], _yp[_upper], _ri[_upper])],
            lens_dxf, layer_name='gridlens')
```
```python
# 9b-②：导入后立刻镜像补齐
app.dxf_import(lens_dxf, add='True', component='gridlens', height='h')
app.mirror('import_1', [0, 0, 0], [0, 1, 0], component='gridlens', copy=True, unite=True)
```

实测：**871 → 453 个多边形，DXF 581 KB → 300 KB，导入时间约减半**，几何完全等价。

> - 参考案例 `Ant1_grid_BA_240D_epc_epc` 用的是**四分之一**（只写 `x≥0 & y≥0`，再先后绕 y、x
>   镜像两次）。那条路只在"网格关于 x=0 也对称"时才严格成立 —— 本例椭圆中心在 `(ec_c,0)`、
>   网格关于 y=0 对称但**不**关于 x=0 对称（列范围不对称），所以只能砍一半。
> - 用镜像前**必须先证明**对称性，并做一次 Python 自查（应 ≈ 0）：
>   ```python
>   d = unary_union([half_u, scale(half_u, yfact=-1, origin=(0, 0))]).symmetric_difference(full_u).area
>   ```
>   （`shapely.affinity.scale(geom, yfact=-1)` 即关于 y=0 镜像）
> - 镜像平面上的孔（`y=0` 那一行）会**自己镜像自己** ⇒ 必须 `copy=True, unite=True`，
>   否则会留下重复实体。
> - 镜像出来的孔若落到图形之外（例如绕 x=0 镜像后跑到椭圆外面）没有危害 —— 没材料可切。

### 8. 导入提速 / 画布 / 坐标范围（2026-09 补，都实测过）
**CST 的 DXF 导入耗时 ∝ 多段线数量**，不是文件大小。库的 `dxf_import`（`cst_solver/import_export/io.py`）
下发的是：

```
.AsCurves "False"  .HealSelfIntersections "False"  .PreserveHoles "True"  .CloseShapes "True"
.SetSimplifyActive "False"   .ModelTolerance "0.0001"
```

`.AsCurves "False"` ⇒ **CST 为每条多段线单独建一个实体**，所以：

| 手段 | 效果 | 备注 |
|---|---|---|
| 对称性减半（上面第 7 条） | **×0.5**（多段线数） | 孔少时很赚；耗时是**超线性**的（见 §9） |
| 加粗孔网格 `ratio`（格距 = a/ratio） | **×4**（ratio 2→1） | 会改变 GRIN 的采样密度/等效折射率，属设计取舍 |
| 坐标位数 `precision` | 文件 −21%（6→2 位） | 实测 2215 条：6/5/4/3/2 位 → 1397/1328/1252/1175/1098 KB，对导入帮助有限 |
| `.SetSimplifyActive "True"` | 只对**圆弧**有效 | 六边形只有 6 个顶点，简化无意义 |

> 结论：**优先砍条数**（对称性 → 网格粗细），`precision` 顺手设 3 位（1 µm）即可，不必纠结。

**画布**：`HexGridVisualizer.__init__` 里有一句 `self.fig, self.ax = plt.subplots(figsize=(14, 12))`
—— 它自己建了一张空画布。只用它的 `hex_lib` 时，**用完立刻 `plt.close(_vis.fig)`**，
否则 notebook 单元末尾会先冒出一张空白图，然后才是自己的示意图。

**预览坐标范围**：不要写死比例系数。椭圆右端是 `ec_c+ec_a`（近焦点在原点、中心在 ec_c），
写死 `2·ec_c + 0.3·ec_a` 在离心率 `e < 0.7` 时会被切掉（Nx/Ny 一大就中招）。
按实际几何取：`xlim = [min(ec_c−ec_a, 孔心 xmin)−余量, max(ec_c+ec_a, 孔心 xmax)+余量]`。

**GRIN 透镜只能做 y 镜像（不能做 1/4 对称）**：孔半径沿轴向单调变化（近焦点 r1 → 远焦点 r2），
绕椭圆中心 x 镜像会把远端的半径搬到近端 ⇒ 几何错了。

### 9. CST 侧「布尔/复制」的两个耗时坑（2026-09 实测：Nx/Ny = 38/34，单透镜孔 4351 个）

同一台机、CST 2026，一次完整建模的分步实测：

| 步骤 | 耗时 | 结论 |
|---|---|---|
| `dxf_import` 2215 条多段线 | **183.9 s** | 随多段线数量**超线性**增长（不是线性、更不是文件大小） |
| `mirror` 孔阵列（`unite=True`） | 3.6 s | 便宜 |
| `subtract(椭圆, 孔阵列)`，4351 个工具体 | 100.1 s | ≈ 23 ms / 工具体 |
| `rotation(repetition=5, copy=True, **unite=True**)` | **> 19 min 卡死** | ✗ 千万别这样写 |
| `rotation(..., unite=False)` | 秒级 | ✓ 6 个独立实体，网格/求解等价 |

**坑 A：`rotation(..., unite=True)` 会卡死。**
把「已挖几千个孔」的实体旋转复制 5 份再 `unite`，CST 要并 6×4351 个壳 ⇒ 实测 19 min 未结束。
6 个互不接触的独立实体对 CST 网格/求解**完全等价** ⇒ **一律 `unite=False`**。
推广：任何「复制 N 份再合并」的写法，N 大时必须先问自己**是否真的需要 unite**。

**坑 B：布尔减的耗时 ∝ 工具体个数，与被减实体的大小关系不大。**
⇒ **壳少的操作放前面、壳多的放最后**：光板只有 1 个壳时先做楔形 / 半空间裁剪（几乎免费），
再把孔阵列用对称性砍半后一次减掉（2215 而不是 4351），镜像合并作为最后一步。
（若要把「半边孔」镜像成整体，注意**不能**镜像已减孔的透镜再 unite ——
`(E−H₁)∪(E−H₂) = E−(H₁∩H₂)`，会把孔**填回来**；必须先把实体沿 y=0 切开成互补两半。）

**排除法结论**：`precision` 6→2 只让文件小 21%，对导入耗时几乎无影响 ⇒ 慢的不是精度，是**实体条数**。
想根治只能减少孔数：固定物理尺寸时应降低 `ratio`（格距 `a/ratio` 增大、孔数下降），并重新检查 GRIN 采样和等效折射率；固定 `nx/ny` 时改 `ratio` 不减少孔数。

---

### 11. 端口三件事：面号拾取 / 端口旋转 / 用「复制旋转」补齐对称端口（2026-09 实测）

**① 拾取端口面用「面号」，且面号要在「轴向状态」下确认。**
`build_waveguide`（外方体 − 内方体）的**径向内端面 = 面号 `'10'`**（用 anchorpoints 里端口位置
正好落在 `wg_in` 反证过）。转 / 扭 / 镜像之后新生成的面，面号要**在 CST 里现查**。
库里有现成封装：`topo_modeler.builders.add_waveguide_port(app, solid, 端口号, 面号)`
= `pick_face` + `add_port`。

**② `rotation()` 原本转不了端口 —— 已补 `object='Shape'|'Port'`（与 `mirror()` 对称）。**
`Transform "Shape","Rotate"` 只作用于实体，端口不会跟着走（曾出现 6 个端口全堆在 0°）。
现在可直接：

```python
app.rotation('Port 2', [0, 0, 180], object='Port', auto_destination='False')
app.rotate_port(2, [0, 0, 180])                 # 端口 2 转 180°
app.rotate_port(2, [0, 0, 180], copy=True)      # 复制并旋转 ⇒ 新增一个端口
```

要点：端口名**不带组件前缀**（写 `Name "Port 2"`，不是 `"component1:Port 2"`）；
`.AutoDestination` 要给 `'False'`；默认参数保持旧行为（实体旋转的 VBA 一字未变，向后兼容）。

**③ 用「复制旋转 180°」一次补齐对称臂的端口 + 控制编号顺序。**
4 条臂由镜像得到、关于原点成对（60↔240、120↔300 相差 180°）⇒
**只需在其中 2 条臂的端面上各加一个端口，再 `rotate_port(..., copy=True)` 转 180°**，
副本自动落到对径两臂上，且法向也正好翻到正确方向（300°→120°、240°→60°）。

**编号顺序**：副本拿的是「下一个空号」⇒ 想让端口号按顺时针
`1=0°, 2=300°, 3=240°, 4=180°, 5=120°, 6=60°`，建端口的顺序就必须是
`0° → 斜臂 300° → 斜臂 240° → 180° → 最后才复制旋转`。

**④ 扭波导（把端口面法向扭到坐标轴）的稳定做法 —— 避开未知面号：**
`pick_face(端口面号)` → `set_edge(外侧壁竖边)` → `rotation_face(β)` 扫出缺角楔形 →
**另建一段长 L 的直管、绕同一条铰边转同一个 β**（它的端面正好是楔形的斜端面，面面贴合）→ `add` 拼合。
比「拉伸楔形的斜端面」省一步：**不需要知道楔形实体的面号**。
铰边坐标必须用**本模型**的参数表达式（沿用别的脚本的变量名会报
`Invalid coordinate setting, please specify a number`）。
只需扭 1 条 + `mirror` 两次即得 4 条对称斜臂；铰边要在「扭转朝向那一侧」的外侧壁上，
否则扭出的段会埋进管腔（反了就把铰边符号与 β 一起取反）。

**⑤ 顺带：`import_subproject(filename, subproject_name)` 两个路径都必须传绝对路径。**
CST 用**它自己的**工作目录解析相对路径 ⇒ 传相对名会报 `Unable to read SAB file`
（文件本身没问题：`.sab` 头 `ACIS BinaryFile … ACIS 35.0`、尾 `End-of-ACIS-data`）。
