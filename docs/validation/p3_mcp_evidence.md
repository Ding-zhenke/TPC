# P3 CST MCP：离线实测记录

更新：2026-09-17。**性质：离线证据**（假后端 + 内存传输 + 真 stdio 子进程；未启动 CST、未做真实仿真）。真机端到端闭环属计划 P4/V9，本文件不得被当成真机结论引用。

环境：Windows / Anaconda Python **3.11.7**；锁定 **mcp 1.29.1**、pydantic 2.13.4、anyio 4.14.2。
核心包 `tpc-cst` 支持 Python ≥3.9，但 MCP SDK 要求 **≥3.10**，因此 `tpc-cst-mcp` 的 `requires-python = ">=3.10"`。

## 1. 交付内容

新增独立发行项目 `integrations/cst-mcp/`（发行名 `tpc-cst-mcp`，导入名 `cst_mcp`）：

| 模块 | 职责 |
|---|---|
| `server.py` | MCP 装配：`list_tools` / `call_tool`（结构化结果 + stdout 隔离） |
| `tools.py` | 11 个工具的 JSON Schema 与实现（纯函数，可离线单测） |
| `errors.py` | `ToolError` + `error_payload`/`tool_payload`（复用 `cst_solver.failures.structured_error`） |
| `runtime.py` | 进程内单例：工作目录、后端选择、`RunService` 延迟创建 |
| `isolation.py` | `protocol_stdout()`：工具期间 stdout → stderr |
| `analysis.py` | dB 口径、连续带宽、谐振、CSV 读取 |
| `reporting.py` | HTML/CSV 报告产物（复用 `topo_modeler.report.HtmlReport`） |

测试：`integrations/cst-mcp/tests/`（**71 项，全部离线**）—— `test_tools.py` / `test_analysis.py` / `test_protocol.py` / `test_client_stdio.py`（真 stdio + SDK 官方客户端，见 §5.1）/ `test_write_guard.py` / `test_backend_passthrough.py`（真 `CstBackend` 的错误码透传，见 §5.2）/ `test_reporting.py`（报告产物唯一性与工作目录约束，见 §5.3）。

## 2. 逐条对照 P3 待办

| 计划条目 | 结论 | 证据 |
|---|---|---|
| 在 `integrations/cst-mcp/` 建独立发行项目，依赖兼容版本 `tpc-cst`；锁定 MCP SDK 与 Python 版本 | 满足 | `pyproject.toml`：`tpc-cst>=2.0.0,<3` + `mcp==1.29.1` + `requires-python=">=3.10"`；已 `pip install -e integrations/cst-mcp` 成功并可从任意目录导入 |
| 首版工具（能力发现/模板列表/配置校验/建模/工程状态/启动求解/任务状态/结果获取/S 参数分析/报告导出/关闭工程） | 满足（11 个） | `tools.TOOL_SPECS`；`test_tool_table_matches_the_plan` |
| 本地 stdio；协议 stdout 与 Python/CST 输出隔离；统一结构化错误；大结果用产物引用 | 满足（含边界说明） | stdio 服务 + `protocol_stdout()`；真 stdio 子进程测试断言 stdout 每行都是 JSON；`get_results` 返回摘要 + 产物路径；错误统一 `{code,message,details,retryable}` |
| S 参数分析复用已有数值层；明确 dB、零值、多段连续带宽与谐振定义，**不能把离散区间并成一个带宽** | 满足 | `analysis.py` 复用 `result_conventions()`（与 `_to_db` 同源）；`test_disjoint_passbands_are_never_merged`（两段 300–318 / 342–380）；`total_bandwidth_ghz` 明确为各段之和；谐振为相邻三点极值并写明「不做插值」 |
| 客户端配置与直波导完整示例；缺关键物理条件让 AI 补问；模板默认值必须可见 | 满足 | `integrations/cst-mcp/README.md`（配置 jsonc + 八步闭环示例 + 「必须先问用户的条件」清单）；`list_templates`/`validate_model_spec` 回显 `effective`/`field_sources`；缺模板路径返回 `missing_requirement` |
| 协议集成测试：握手、工具发现、无 CST 能力报告、非法参数、长任务状态、失败结果、stdout 无杂讯 | 满足（7 项全覆盖） | `test_protocol.py` 9 项（其中 `test_stdout_stays_protocol_only` 起真 stdio 子进程发 initialize/tools-list/tools-call） |

**验收闭环**（描述直波导参数 → 预检 → 建模 → 求解 → S 参数 → HTML/CSV 报告；所有动作调用共用 Python 能力）：
`test_build_run_analyze_report_closed_loop` 端到端跑通，分析结果为**两段不相连通带**（300–317 / 343–380 GHz，各段带宽之和 54 GHz），谐振 330 GHz / −21.5 dB，报告产出 HTML + CSV 两个产物文件。

## 3. 与 P1/P2 的衔接（不重复实现）

| 能力 | 唯一实现 |
|---|---|
| 字段/取值域/预检、未实现类型不可构建 | `topo_modeler.preflight`（P1） |
| 任务状态机、去重、重启中断、单 worker、落盘、工程副本与会话归属 | `tpc_service`（P2） |
| 求解判定（返回 ≠ 算完 ≠ 结果是本次的）、单位口径 | `cst_solver.run_contract`（P1） |
| 错误结构 | `cst_solver.failures.structured_error`（P1） |
| 报告渲染 | `topo_modeler.report`（阶段 7） |

MCP 层只做**协议装配 + 输入输出转换**：`tools.py` 不生成 VBA、不复制建模公式、不做数值推导。

## 4. 开发过程中发现并修掉的问题

| 现象 | 根因 | 处理 |
|---|---|---|
| 包外（`integrations/cst-mcp` 目录）`import tpc_service` 失败 | P2 新增的顶层包不在**旧的可编辑安装映射**里 | 重新 `pip install -e .`；并把「新增顶层包后必须重装」写进开发约定 |
| 重装后一致性检查的 `installed` 项反而报「非可编辑安装下仓库外拿到源码目录」 | 第二次安装落成了**老式开发安装**（源码树里的 `tpc_cst.egg-info`，没有 `direct_url.json`），而检查脚本当时只认「PEP 660 editable / 常规」两种模式 | 检查脚本改为识别三种模式（`pep660-editable` / `legacy-develop` / `regular`），并**顺带加强**：仓库外必须能导入全部 6 个顶层包 —— 这条正好能提前抓住上面那类「忘记重装」的问题 |
| 手写 CSV 的 `S1,1` 表头被读成两列 | S 参数名**自身含逗号**；标准 CSV 会加引号，手写文件通常不加 | 读取器增加「`S<数字>` + 纯数字」的窄模式回拼；并补两条用例（引号 / 未引号） |
| `get_capabilities` 只在 `runtime.backend` 里给后端名，客户端要钻两层 | 契约不便 | 顶层补 `backend` 与 `workdir` |

## 5. 仍未覆盖 / 待 P4

| 项 | 说明 |
|---|---|
| 真实 CST 端到端闭环（P4/V9） | 真机上跑「预检 → 建模 → 求解 → S 参数 → 报告」，记录日志、工程、原始数据与报告；本文件不覆盖 |
| CST 原生 stdout | `protocol_stdout()` 是**进程内**重定向，管得住 Python 的 `print`，**管不住 CST 进程自己的输出** —— 真机验收必须实测协议通道无杂讯 |
| 运行中任务的取消 | 仍为 `cancel_not_supported`。**离线核实已完成**（见 [P2 记录](./p2_service_evidence.md) §4.1：接口静态成员只有 `close()`；动态代理需真机 `hasattr`）；真机一步：`python scripts/probe_solver_control_api.py --live` |
| 长时间求解的进度粒度 | 目前只有任务状态与日志尾部；CST 的进度回调未核实 |
| MCP 客户端的真实接入 | **SDK 官方客户端路径已离线验证**（§4.1 below / `test_client_stdio.py`）；**第三方图形化客户端**里的人工走查仍属 V9 |
| 真实 CST 后端被使用过 | `real_cst_backend_verified: False`（能力报告里如实标注）；真机闭环属 V9 |

### 5.1 真 stdio + SDK 官方客户端（2026-09-17 新增）

`test_protocol.py` 原本只有「内存会话」与「手写 JSON-RPC 行」两条通道，
**没有走过真实客户端代码路径**。新增 `tests/test_client_stdio.py`（6 项）：
用 `mcp.client.stdio.stdio_client` + `ClientSession` 连**真 stdio 子进程**
（`python -m cst_mcp`，假后端），覆盖：

| 用例 | 验的是什么 |
|---|---|
| `test_real_client_handshake` | 初始化协商：`serverInfo.name/version`、`capabilities.tools`、`protocolVersion` |
| `test_real_client_discovers_all_tools` | 工具发现：11 个工具与 `tools.tool_names()` 一致，且都有描述与对象型入参 schema |
| `test_real_client_calls_offline_tools` | 离线工具：能力报告（`backend=fake`）、模板字段、预检通过/非法输入的**结构化错误**；并断言 CST 相关检查**不是 failed**（预检不连 CST） |
| `test_real_client_long_task_polling` | 长任务：提交 → 轮询到终态（含 `finished_at`） |
| `test_real_client_result_analysis_report_loop` | **闭环**：建模 → 求解 → `get_results` 产物 → `analyze_s_parameters`（阈值 −10 dB ⇒ 1 段合格带，最优 330 GHz）→ `export_report` 产出 **HTML + CSV 文件**；并核对报告里写明数据来自假后端合成曲线 |
| `test_real_client_unknown_tool_is_structured_error` | 未知工具在真客户端里是结构化错误（连接不断） |

⚠️ 假后端写的是**合成曲线**（`fake_sparams_*.csv`，S11 在 330 GHz 下探约 −17 dB），
只证明**闭环能力**，不是物理结论。

### 5.2 P2↔P3 衔接：真实 `CstBackend` 的错误码原样到达客户端（2026-09-17 新增）

上面两节走的都是**假后端**（`FakeBackend`）—— 它们验证协议与工具语义，但**绕过了真实后端**。
而「底层错误码原样透传、不重编号」是 P2↔P3 的硬要求，链路上有三层：
`cst_solver`（运行契约）→ `tpc_service`（任务/结构化错误）→ `cst_mcp`（客户端）。

新增 `tests/test_backend_passthrough.py`（6 项）：用**真 `CstBackend` + 真 `RunService` +
真工具 + 真协议会话**，只在 **CST 边界**打桩（`cst_solver.setup` / 预检），
验证每个失败场景的码**逐字**到达客户端：

| 场景 | 期望码 | 附加断言 |
|---|---|---|
| 预检未过（配置越界） | `config_value_out_of_range` | `get_results` 也返回同一个码的**结构化错误**，不是空数据 |
| 产物逃出服务工作目录 | `workdir_escape` | 码属于 `tpc_service.ERROR_CODES` |
| 运行契约判失败 | `run_messages` | `run_identity.run_token` 一并透传；**调用序列只有 `run_checked → close`**（没保存、没读结果） |
| 工作副本被删 | `project_not_found` | 连 `setup()` 都没被调用 |
| 后端抛异常 | `backend_failed` + `retryable=True` | 消息里保留 `RuntimeError` 原因 |
| 能力报告（真后端） | —— | `limits.real_cst_backend_verified` 仍为 `False`（**不假装已验证**） |

⚠️ 这里验证的是**错误传播与契约**，不是物理解算（真机闭环属 P4/V9）。

### 5.3 真实曲线上的分析与报告（不是假后端合成曲线，2026-09-17 新增）

前面几节的离线证据用的都是**假后端产出的合成曲线**（本文件一开始就写明「不能代替真机」）。
但分析/报告这一段**不需要跑求解** —— 只要有**真实的 S 参数曲线**（从已求解工程离线读出）
就能验。新增 `python scripts/verify_mcp_real_curves.py`（离线、只读）
→ **OK 18 / FAIL 0 / UNKNOWN 0**

| 工程 | 形态 | 结果 |
|---|---|---|
| `普通单元天线\Ant1_D_BA_120_Feed_antenna-DF.cst` | 1 端口 | 分析 + 报告 ✅ |
| `Leaky\ANT_LEAKY_EPC_GRID.cst` | 2 端口（含收敛监控陷阱） | 分析 + 报告 ✅ |
| `MPMBA\Ant3_epc.cst` | **3 端口 6 条 S 参数** | 分析 + 报告 ✅ |

验的东西：

* 真实工程导出 CSV → MCP `analyze_s_parameters`（阈值 −10 dB、`resonance_kind='min'`、
  `min_prominence_db=0.5`）给出 `n_points=1001`、区间数与谐振数；
* **跨层一致**：同一曲线用库层规则（`tpc_toolkit.curves.find_resonances`）算出来的谐振
  与 MCP 给的**条数一致、最大频率差 ≤ 1.4e-8 GHz**（阈值 1e-3 GHz）；
  这点差异只来自 CSV 往返的浮点末位舍入，**不是两套规则**（规则本身在 §5.1/§5.2 已合并为一份）；
* MCP `export_report` 产出 HTML + CSV：文件**真的存在**、HTML **自包含**（无 http/外部脚本）、
  报告里含指标名；
* **负例**：`out_dir` 写到服务工作目录外 → `workdir_escape` 拒绝 ✅；
* 三个参考工程目录前后快照 **0 变化**。

**顺带修掉一个静默数据丢失**（真实数据跑出来的）：报告文件名原本是
`sparams-<时间戳>.csv` / `report-<时间戳>.html`，时间戳**只到秒** —— 同一秒内出两份报告时，
第二份会**静默覆盖**第一份，而两次调用返回的产物路径**完全一样**（调用方以为两份都在）。
现在 `_unique_stamp()` 会给同一份报告的所有产物找一个不冲突的后缀
（`…-2.csv` / `…-2.html`，CSV 与 HTML 仍配对），后缀用尽时退化成随机 token。
回归：`tests/test_reporting.py`（5 项，其中时间戳被**冻结**，冲突可复现而不靠碰运气）。

### 5.4 ✅ CST 原生输出与协议通道（真机，2026-09-17，**只建模不求解**）

**问题**：`cst_mcp.protocol_stdout()` 是**进程内**重定向（把 `sys.stdout` 换成协议流
上的一个 writer），它管得住 Python 的 `print`；但 CST 是**另一个进程**，
它自己往 stdout 写的东西不经过 Python 的解释器 —— 需要真机确认「CST 真正干活时，
协议通道还干净吗」。

**做法**：`python scripts/verify_service_mcp_real.py`（同一次会话也是 P2 §5.1 的证据）。
让真 CST 后端**真的建模**，全程用 SDK 真客户端
（`mcp.client.stdio.stdio_client` + `ClientSession`）收发 JSON-RPC：

| 观测 | 实测 |
|---|---|
| 建模 | `build_model` → `succeeded`，**84.2 s**（另一轮 80.1 s / 40 次轮询） |
| 期间协议交互 | 1 次 `initialize`、`list_tools`、`get_capabilities`、`validate_model_spec`、`build_model` + **42 次 `get_job_status` 轮询**，全部正常解析 |
| CST 原生输出污染 | **无** —— 任何非 JSON-RPC 的行都会让 framing 解析失败，而全部调用都拿到了结构化结果 |
| 产物 | 服务目录里产出真 CST 工程（`Model/Parameters.json` 可读），证明跑的是真 CST |

**结论**：本地 stdio 形态下，CST 进程的原生 stdout **不会**污染 MCP 协议通道
（这条通道是客户端↔服务进程的管道，CST 的输出不在这条管道上）；
`protocol_stdout()` 只需要继续管住 Python 侧的 `print`。

> ⚠️ 边界（不要过度外推）：这只覆盖**本地 stdio + 真 CST 建模**这一种形态。
> 若将来把服务改成**远程/共享传输**（SSE、socket），或让 CST 与 Python 共进程，
> 需要重新实测。

> ⚠️ 脚本里**没有**调用 `run_simulation`（求解工具，虽然 `tools/list` 里它在），
> 并有离线护栏 `tests/test_service_mcp_real_script.py::test_script_never_calls_the_solve_tool`
> 防止以后被人顺手加上 —— 求解闭环仍属 P4/V9。

## 6. 复现命令

```text
pip install -e . && pip install -e integrations/cst-mcp
python -m cst_mcp --check                       # 能力报告（不启动服务）
cd integrations/cst-mcp && python -m pytest tests -q     # 71 项，全部离线
python -m pytest -q                             # 全仓（核心包）
python scripts/verify_mcp_real_curves.py        # 真实曲线上的分析/报告：18 OK / 0 FAIL
python scripts/verify_service_mcp_real.py       # （真机、~3 分钟、不求解）真 CST + 真 stdio 闭环：20 OK / 0 FAIL
python scripts/verify_service_mcp_real.py --no-cst       # 同一脚本离线骨架（假后端：OK 10 / FAIL 0）
```

## 7. 相关文档

- 客户端配置与完整示例：`integrations/cst-mcp/README.md`
- 设计口径：`docs/architecture/cst_mcp.md`；包说明：`docs/packages/cst_mcp.md`
- 计划状态：`docs/next_plan/README.md`（P3 已完成项删除，只留真机验收）
