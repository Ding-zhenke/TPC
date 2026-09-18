# Python 包与 CST MCP 双入口方案

MCP 服务**首版已实现**（离线验证；真机闭环待 P4/V9），实现落点 `integrations/cst-mcp/`；Python 安装发现、延迟加载与诊断基础更早已实现。进度只在 [统一计划](../next_plan/README.md) 维护。日期：2026-09-17。

## 1. 产品边界

目标是同一套 CST 能力、两个使用入口：Python 用户写代码；AI 根据用户描述，通过 MCP 调用 Python 包完成建模、仿真、结果分析。

```text
Python 用户 ───────────────────────────┐
                                     ▼
用户自然语言 → AI 客户端 → CST MCP → Python 能力层 → CST
                                     │
                                     └→ 数值分析、图表、报告
```

AI 客户端负责理解描述、补齐必要信息、规划工具调用和解释结果。MCP 服务负责提供有明确参数和返回值的工具，不要求 Python 包内置大模型或模型 API 密钥。

通用 CST 原语与拓扑光子晶体应用保持分层。第一版面向现有已支持器件；“任意自然语言、任意器件都能可靠建模”不作为首版承诺。

## 2. 现有资产与新增归属

| 模块 | 定位 | 处理方式 |
|---|---|---|
| `cst_solver` | CST 工程、几何、材料、端口、求解、底层结果 | 保留公开接口，逐步补齐统一错误与会话能力 |
| `mesh_grid` | 网格、路径、坐标 | 保留纯算法职责 |
| `topo_modeler` | 器件构建、扫描、结果读取、报告 | 复用；用真实工程验证后对外开放相应工具 |
| `topo_templates` | `StraightWaveguide`、`UnitAntenna` 等模板 | 首版建模入口 |
| `tpc_toolkit` | 独立数值处理 | 分析逻辑留在 Python 层 |
| `cst_mcp`（新增） | 协议、工具注册、输入输出转换 | 依赖 Python 包；不直接生成 VBA，不复制建模公式 |
| Python 运行服务层（已落地为顶层包 `tpc_service`，P2） | 会话、任务、执行记录 | 不依赖 MCP；Python 用户也能调用 |

现有发行名为 `tpc-cst`，先保留，避免破坏 notebook 导入。建议同一仓库内增加独立发行项目 `integrations/cst-mcp/`，包含自己的 `pyproject.toml` 和 `src/cst_mcp/`，发行名暂定 `tpc-cst-mcp`。MCP 项目依赖兼容版本的 `tpc-cst`；核心包不反向依赖 MCP。

> **实现落点（2026-09）**：`integrations/cst-mcp/`（发行名 **`tpc-cst-mcp`**，包名 **`cst_mcp`**，
> 版本 0.1.0，`requires-python >= 3.10`，依赖 `tpc-cst>=2.0.0,<3` 与 `mcp==1.29.1`）。
> 目录、发行名与依赖方向与上面的取齐，均已落地；说明见 [包说明](../packages/cst_mcp.md)
> 与该项目自己的 [`integrations/cst-mcp/README.md`](../../integrations/cst-mcp/README.md)。
> 上层 Python 运行服务层也已落地为顶层包 `tpc_service/`（P2），MCP 层只在它之上做协议与输入输出转换。

## 3. 第一版工具契约（首版 11 个已实现）

| 工具 | 主要输入 | 主要输出 |
|---|---|---|
| `get_capabilities` | 无 | CST 可用性、支持模板、工具限制 |
| `list_templates` | 无 | 模板参数、单位、必填字段、默认值 |
| `validate_model_spec` | 模板与结构化参数 | 规范化配置、缺失项、错误、假设；不启动 CST |
| `build_model` | 通过校验的配置、输出路径 | 建模任务 ID |
| `get_project_state` | 工程 ID | 文件、参数、单位、建模与求解状态、消息 |
| `run_simulation` | 工程 ID、求解配置、请求 ID | 仿真任务 ID |
| `get_job_status` | 任务 ID | 状态、可获取的进度、错误、产物 |
| `get_results` | 工程 ID、运行 ID、结果名称、频段 | 带单位的有限长度数据与完整数据文件 |
| `analyze_s_parameters` | 结果引用、频段、阈值 | S11/S21 指标、连续合格区间、判据 |
| `export_report` | 结果引用、指标配置 | HTML、CSV 等产物引用 |
| `close_project` | 工程 ID、保存策略 | 关闭结果及文件位置 |

几何原语、材料、布尔运算、端口和边界工具作为后续通用建模扩展，按任务分组开放。第一版不将所有底层方法自动映射成工具，也不以任意 Python/VBA 执行作为唯一入口。

上表 11 个工具的首版实现落点在 `integrations/cst-mcp/src/cst_mcp/tools.py`（`TOOL_SPECS` 工具 Schema + `HANDLERS` + `dispatch()`）；
工具语义与逐条边界见 [包说明](../packages/cst_mcp.md)，完整调用示例见
[`integrations/cst-mcp/README.md`](../../integrations/cst-mcp/README.md)。

## 4. 会话与长任务

- 服务使用工程 ID 管理 CST 对象，不把对象或内存地址传给 AI。明确区分服务创建的会话与外部已有会话。
- 建模与求解都可能耗时，采用提交任务、查询状态、获取产物的方式。底层同步操作放入专用执行单元；创建和调用 CST 对象的线程/进程约束需真机确认。
- 同一工程写操作串行；首版单 CST worker，避免同时重建、求解、读取未完成结果。
- 状态至少包含 `queued/running/succeeded/failed/interrupted`。超时或服务重启后不得凭空标记成功；重启后无法确认的任务标记中断，不能自动重复提交仿真。
- 请求 ID 用于重复请求检测。重复调用返回既有任务，不重复建模或求解。
- 取消仿真仅在底层停止接口验证后开放；终止等待不等于停止 CST。

## 5. 输入、验收与结果可信度

- 输入明确长度/频率单位、材料、端口、边界、求解器、输出路径。模板默认值必须在规范化配置中可见；缺少关键物理条件时由 AI 向用户补问。
- 每次写入后读取 CST 消息并分类。求解前检查配置与重建状态；调用返回不抛异常不代表成功。
- `run_solver()` 返回后还需确认运行状态和结果是否存在。保存参数、配置摘要、运行 ID、工程标识，防止将旧结果当成本轮结果。
- 错误结构含 `code/message/details/retryable`。不得把失败或缺失结果变成空数据后声称成功。
- 复数结果用实部/虚部表示；频率带单位，数值必须可 JSON 序列化。大数据输出为文件，小摘要供 AI 阅读。
- S 参数 dB 的幅度口径为 `20*log10(abs(S))`；零值处理明确标注。带宽按用户阈值识别连续频段，禁止把不相连区间并为一个带宽。
- 分析同时返回原始数据引用、频段、阈值、端口/模式与运行信息；AI 区分计算事实和物理解释。
- 工作目录限制、明确覆盖策略及输入校验集中实现；CST 表达式字符串须专门校验，不将原始用户文字直接拼入 VBA。

## 6. 本地运行与依赖

首版服务运行在安装 CST 的 Windows 机器，使用本地 stdio 接入支持 MCP 的 AI 客户端。Python 包独立安装、独立使用。远程部署后续再设计身份认证、文件传输与任务隔离。

stdio 的 stdout 必须留给协议消息。`cst_solver` 的项目与材料运行日志已替换为 logging；接入 MCP 前仍须隔离上层模板、第三方和 CST 原生输出，不能让这些输出进入协议通道。

CST 安装路径应支持环境变量或用户配置，避免要求安装用户修改 site-packages 下的代码。只有真正执行 CST 操作时才加载 CST 依赖；离线参数校验、测试和服务能力发现应能正常运行并报告 CST 不可用。

MCP Python SDK 版本、Python 最低版本与 CST 自带接口兼容性须在实现阶段锁定并测试，不能默认沿用核心包 Python >=3.9 就足够。

> **首版锁定（2026-09）**：已验证组合为 **Python 3.11.7 + mcp 1.29.1 + pydantic 2.13.4 + anyio 4.14.2**；
> `integrations/cst-mcp/pyproject.toml` 把 `mcp==1.29.1` **钉死**，并把本发行项目的下限设为
> **Python ≥ 3.10**（核心包仍是 ≥3.9，两者**不是同一个下限**）。
> stdio 通道的保护由 `cst_mcp.isolation.protocol_stdout()` 在每次工具调用期间把 `sys.stdout`
> 重定向到 `sys.stderr` 实现；**边界**：这是进程内重定向，管得住 Python 的 `print`，
> 管不住 CST 进程自己的原生输出 —— 后者要等真机验收（P4/V9）实测。

## 7. 实施与协议参考

实施顺序、剩余任务与验收要求见 [统一计划](../next_plan/README.md)。



- [MCP 架构](https://modelcontextprotocol.io/specification/2025-06-18/architecture)：客户端/服务端分工。
- [MCP 工具](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)：工具输入、结构化结果与资源引用。

本方案中的会话、任务状态和器件接口为项目设计，不代表 MCP 强制要求。实现时选择并锁定实际支持的协议和 SDK 版本。
