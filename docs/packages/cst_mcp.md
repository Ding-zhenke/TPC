# cst_mcp —— CST MCP 集成层（发行名 `tpc-cst-mcp`）

> ⚠️ **证据等级**：以**离线证据**为主 —— `integrations/cst-mcp/tests/` 共 **71 项**，全部离线
> （假后端 `FakeBackend` + 内存传输；其中 `test_client_stdio.py` 用**真 stdio 子进程 + SDK 真客户端**）。
> **真机部分（2026-09-17，`scripts/verify_service_mcp_real.py`，只建模不求解）**：真 CST 后端 +
> 真 stdio 通道跑通「预检 → 建模 → 任务记录」（`succeeded`，84.2 s；20 OK / 0 FAIL），
> 并实测 **CST 进程的原生 stdout 不污染协议通道**（见 [P3 记录](../validation/p3_mcp_evidence.md) §5.4）。
> **仍未真机验证的是「求解 → S 参数 → 报告」那一段**（需要求解，属计划 P4/V9）；
> 用假后端跑出来的是**合成曲线**，不得当作仿真结论。

日期：2026-09-17。位置：`integrations/cst-mcp/` —— 它是 TPC 仓库里的**独立发行项目**（有自己的
`pyproject.toml` 与 `src/` 布局），**不在核心包 `tpc-cst` 的打包白名单里**。

`cst_mcp` 是 TPC 的 **MCP 集成层**：它把同一套 Python 能力（预检 → 建模 → 求解 → 结果 → 分析 → 报告）
暴露成 11 个 **MCP 工具**，供支持 MCP 的 AI 客户端按用户描述驱动 CST。
它**不重写**几何 / VBA / 数值逻辑 —— 那些仍然分别属于 `topo_modeler` / `cst_solver` / `tpc_service`。

| 项 | 内容 |
|---|---|
| **职责** | 协议服务端（stdio）+ 工具注册（JSON Schema）+ 输入输出转换 + 进程内运行时（工作目录 / 后端 / 运行服务单例）+ S 参数分析与报告产物的适配 |
| **需要 CST** | ⚠️ **看后端**。默认真实 CST 后端；`TPC_MCP_BACKEND=fake` 时用假后端，**完全离线可用**（本项目的测试全部跑在这条路径上）。能力发现 / 模板列表 / 预检 / CSV 分析 / 报告这些工具本身**不需要 CST** |
| **发行名 / 包名** | `tpc-cst-mcp` / `cst_mcp`（版本 `0.1.0`，`requires-python >= 3.10`，`mcp==1.29.1` **锁定**） |
| **入口** | `python -m cst_mcp`（stdio 服务）/ `python -m cst_mcp --check`（打印能力报告后退出）/ `tpc-cst-mcp`（console script，同一个 `main`） |
| **依赖** | `tpc-cst>=2.0.0,<3`（→ `topo_modeler.preflight` / `topo_modeler.report` / `tpc_service.RunService` / `cst_solver.run_contract` / `cst_solver.failures`）、`mcp==1.29.1` |
| **被谁依赖** | 无。**核心包不反向依赖 MCP**（依赖方向严格单向：`cst_mcp` → `tpc-cst`） |
| **源码位置** | `integrations/cst-mcp/`：`pyproject.toml`、`README.md`、`src/cst_mcp/`（11 个模块）、`tests/`（3 个文件 / 46 项） |
| **当前阶段** | **P3 首版已完成**（离线验收）。真实 CST 上的端到端闭环属计划 **P4/V9**，尚未进行 |

---

## 1. 它解决什么问题

在 P3 之前，「让 AI 驱动 CST」这件事没有落点：`tpc-cst` 是一套**给 Python 用户**的库
（模板 / `TopoModeler` / `RunService`），而 AI 客户端需要的是另一形态的东西 ——
**有明确名字、明确参数 Schema、明确返回结构的工具**，以及一条**不被日志污染**的协议通道。

本项目只补这两件事：

1. **协议与工具面**：11 个工具的 JSON Schema、参数校验、返回结构；
2. **通道与运行时**：stdio 上的 JSON-RPC、stdout 隔离、进程内的单例运行服务与工作目录。

它**不产生第二套能力**。每一次「建模 / 求解 / 分析 / 出报告」的动作，最终都落到上层库里已有的那一个实现上；
工具层只负责「参数怎么进来、结果怎么出去」。

---

## 2. 架构与依赖

### 2.1 依赖方向（严格单向）

```text
AI 客户端 ──stdio/JSON-RPC──▶ cst_mcp（协议 + 工具 + 输入输出转换）
                                  │  （不重写几何 / VBA / 数值）
                                  ▼
        ┌──────────────────────────────────────────────────┐
        │ topo_modeler.preflight     预检（离线，不建 DE）      │
        │ tpc_service.RunService     执行 / 任务 / 串行 / 去重  │
        │ cst_solver.run_contract    判定与单位口径            │
        │ topo_modeler.report        报告产物                 │
        │ cst_solver.failures        唯一的错误结构            │
        └──────────────────────────────────────────────────┘
                                  ▼
                              CST（真机时）
```

### 2.2 所有动作调用共用同一套 Python 能力

| MCP 工具侧的需求 | 实际落点（**唯一实现**） |
|---|---|
| 预检「这个规格能不能建」 | `topo_modeler.preflight.validate_model_spec()` |
| 模板字段 / 单位 / 取值域 / 默认值 | `topo_modeler.preflight.list_templates()`、`describe_template()` |
| 提交建模 / 求解 / 参数研究，排队、串行、去重、恢复 | `tpc_service.RunService.submit()` / `get()` / `wait()` / `logs()` / `artifacts()` |
| 「这次到底算成功吗」与频率 / dB / `run_id` 口径 | `cst_solver.run_contract`（含 `result_conventions()`） |
| HTML / CSV 报告 | `topo_modeler.report.HtmlReport`（自包含、零 CDN、零 JS） |
| 错误结构 `{code, message, details, retryable}` | `cst_solver.failures.structured_error()` |

**MCP 层不写几何、不写 VBA、不做数值推导**：`cst_mcp` 里没有任何一处生成 CST 表达式或调用 `app.*`。

---

## 3. 模块地图

```
integrations/cst-mcp/
├── pyproject.toml           发行项目定义：name=tpc-cst-mcp, version=0.1.0,
│                            requires-python>=3.10, deps: tpc-cst>=2.0.0,<3 与 mcp==1.29.1
├── README.md                客户端配置 + BA 直波导完整示例（**权威用法文档**）
└── src/cst_mcp/
    ├── __init__.py          __version__ = '0.1.0'（包级导出仅这一项）
    ├── __main__.py          CLI：python -m cst_mcp / --check / --workdir / --version
    ├── server.py            build_server()：把 list_tools + call_tool 装配成 MCP Server
    ├── tools.py             TOOL_SPECS（11 个工具的 JSON Schema）+ HANDLERS + dispatch()
    ├── errors.py            ToolError + error_payload / tool_payload（复用 cst_solver.failures.structured_error）
    ├── isolation.py         protocol_stdout()：工具期间把 stdout 重定向到 stderr；stdout_is_protocol_only()
    ├── runtime.py           进程内单例：TPC_MCP_WORKDIR / TPC_MCP_BACKEND / get_service() 延迟创建
    ├── analysis.py          dB 口径、连续带宽、谐振、CSV 读取
    └── reporting.py         HTML / CSV 报告产物（复用 topo_modeler.report.HtmlReport）
```

| 文件 | 主要符号 | 职责 | 是否需要 CST |
|---|---|---|---|
| `__main__.py` | `main` | 命令行入口：服务模式 / `--check` 自检 / `--workdir` / `--version`。服务模式下**不向 stdout 打印任何东西** | ❌（`--check` 也不启 CST） |
| `server.py` | `build_server`、`SERVER_NAME` | MCP Server 装配：`list_tools` 取自 `TOOL_SPECS`，`call_tool` 走 `dispatch()` | ❌ |
| `tools.py` | `TOOL_SPECS`、`HANDLERS`、`dispatch`、`tool_names` | **工具契约的唯一来源**：11 个 Schema + 11 个 handler + 总入口 | ⚠️ 看工具 |
| `errors.py` | `ToolError`、`error_payload`、`tool_payload`、`TOOL_ERROR_CODES` | 工具层错误码与成功/失败返回结构（错误结构**复用** `cst_solver.failures`） | ❌ |
| `isolation.py` | `protocol_stdout`、`stdout_is_protocol_only` | 每次工具调用期间把 `sys.stdout` 重定向到 `sys.stderr` | ❌ |
| `runtime.py` | `configure`、`reset`、`get_service`、`describe_runtime`、`default_workdir`、`backend_name`、`service_ready` | 工作目录、后端选择、`RunService` **延迟创建**的进程内单例 | ⚠️ 创建服务时不启 CST；执行才启 |
| `analysis.py` | `to_db`、`read_series_csv`、`contiguous_bands`、`find_resonances`、`analyze_series`、`conventions` | S 参数分析：dB 口径、多段连续区间、局部极值、CSV 读取 | ❌ |
| `reporting.py` | `export_report`、`analysis_csv_rows` | 报告产物落盘（HTML 复用 `topo_modeler.report.HtmlReport`） | ❌ |

---

## 4. 工具表（首版 11 个）

| 工具 | 主要输入 | 主要输出 | 关键点 |
|---|---|---|---|
| `get_capabilities` | `probe=false` | CST 可用性、后端名、工作目录、可构建 / 计划中模板、工具清单、`limits` | **总是先调**；不启动 CST；假后端会明说「合成结果，不能当结论」 |
| `list_templates` | `model_type`、`include_planned=false` | 模板的结构化字段描述（单位 / 取值域 / 默认值 / 必填项） | 未实现类型带 `buildable=false`；**默认值必须显式回显**，不得静默代替用户意图 |
| `validate_model_spec` | `spec`（必填）、`model_type`、`require_output`、`spec_base_dir` | `effective` / `field_sources` / `ctor_kwargs` / `assumptions` / `checks` | **离线**：不启 CST、不建设计环境，可反复调 |
| `build_model` | `spec`（必填）、`project_path` 或 `project_id`、`request_id`、`note` | `job_id` + 状态 | **异步**；缺模板路径返回 `missing_requirement`（应去问用户） |
| `get_project_state` | `project_id`（省略列全部） | 工作副本路径、`session_owned`、最近任务与产物 | 工程默认**复制**到工作目录，不动原文件 |
| `run_simulation` | `project_id` / `project_path`、`request_id`、`run_id`、`note` | `job_id` + 状态 | **异步长任务**，必须轮询；先保存再读（见 §5.3） |
| `get_job_status` | `job_id`（必填） | 状态、日志、错误、产物 | `interrupted` **不是成功**，且**不自动重跑** |
| `get_results` | `job_id`（必填） | 结果**摘要** + 产物路径 + `run_identity` | 任务未成功时返回**结构化错误**，不是空结果 |
| `analyze_s_parameters` | `threshold_db`（必填）、`csv_path` / `job_id` / `project_path`、`metric`、`criterion`、`band`、`max_gap_ghz`、`resonance_kind` | 各段合格区间、`total_bandwidth_ghz`、谐振列表、口径 `conventions` | **多段连续区间按段列出，绝不合并**（§5.7） |
| `export_report` | `analysis` 或 `csv_path` / `job_id`、`title`、`formats`、`out_dir` | 产物引用 `[{kind, path}]` | 只回路径，**不把整份 HTML 塞回对话** |
| `close_project` | `project_id`（必填）、`save=true` | 关闭结果与文件位置 | **只关本服务创建的会话**；外部会话只解除注册 |

工具错误码：`unknown_tool`、`invalid_arguments`、`missing_requirement`、`not_found`、
`analysis_failed`、`report_failed`、`tool_failed`（`cst_mcp/errors.py:TOOL_ERROR_CODES`）；
底层（`tpc_service.errors.ERROR_CODES` / `cst_solver` 的码）**原样透传**，不重编号。
另有 `request_id_conflict`、`cancel_not_supported` 等来自服务层的码，属于同一套 `{code, message, details, retryable}`。

> 2026-09-17 一致性检查（`scripts/check_api_consistency.py` 的 `error-codes` 项）
> 在此表上抓到两处漂移并已修：① `dispatch()` 的兜底码 `tool_failed` 原来**不在表里**；
> ② `service_unavailable` 从未被产出过（运行服务不可用时底层会抛
> `tpc_service` 的 `service_shutdown`/`backend_failed`），属于死表项，已删除。

---

## 5. 关键语义（照着判断，别凭印象）

### 5.1 MCP 层不重写能力

几何 / VBA / 数值逻辑一律**委托**给上层库（§2.2 的表）。想在工具里「顺手算一下」是明确的反例 ——
那会造成两套实现漂移：Python 用户跑出来的结果与 AI 客户端跑出来的结果不一致。

**写入口三条约束（`tools.py` 的 `WRITE_TOOLS`，计划 P1「MCP 写入口接入校验层」）**：
会改变工程状态的工具是 `build_model` / `run_simulation` / `close_project`，它们必须
① 经 `runtime.get_service()` 提交任务（MCP 层不直接开 CST）；
② 校验用共用纯函数 —— 配置/字段走 `topo_modeler.preflight.validate_model_spec`，
表达式/名称/VBA 文本走 `cst_solver.expressions`；
③ 成败判定用 `cst_solver.run_contract`。

其余 8 个工具是**只读**（`READ_TOOLS`，含 `export_report` —— 它只往服务工作目录写报告文件）。
新增工具必须显式归类，否则一致性检查会失败。守住这条规则的两处（**不是靠注释**）：

* `python scripts/check_api_consistency.py` 第 6 项 `mcp-write-guard`（静态：写入口必须引用
  `get_service`；`cst_mcp/` 的代码行里不得出现 `add_to_history` / `cst.interface` /
  `cst.results` / `model3d.` 等 CST 原语，也不得自带第二套校验规则）；
* `tests/test_write_guard.py`（运行期替身，证明「先校验、经服务、再执行」真的发生）。

### 5.2 异步长任务

`build_model` / `run_simulation` **立即返回** `job_id`（状态 `queued`），不阻塞；
用 `get_job_status` 轮询：`queued` → `running` → `succeeded` / `failed` / `interrupted`。

* 状态词表与 P2 完全一致（`tpc_service.state.JOB_STATUSES`），**不要另造**；
* **`interrupted` 不是成功**（服务重启或排队中被取消），且**不会自动重跑** ——
  要不要重跑是调用方（AI / 用户）的决定；
* 判断状态**要认全词表**：`if status != 'failed'` 这种写法会把 `interrupted` 当成跑通了。

### 5.3 先保存再读

`solve` / `study` 的任务，后端**必须**确认已保存（`saved=True`），否则服务层直接判 `failed`。
理由与 P1 运行契约同源：`run_id=0` 指向「**当前最新结果**」，不先保存就可能把**上一轮**的结果当本轮。
`run_identity` 会随结果一起返回，用来说明「这批数据属于哪一次运行」。

### 5.4 幂等：`request_id`

同一个 `request_id` + 同一种 `kind` + 同一份参数 ⇒ 返回**既有任务**并带 `duplicate=true`，
**不会重复建模或求解**；同一个 `request_id` 配**不同**参数 ⇒ `request_id_conflict`（换 ID，别硬塞）。

### 5.5 失败必须是结构化错误

所有失败都是 `{code, message, details, retryable}`（唯一实现 `cst_solver.failures.structured_error()`），
工具返回值形如 `{'ok': False, 'error': {...}}`。

* **失败不会变成空数据**：`get_results` 在任务未成功时返回错误，而不是空结果；
  预检不通过时返回第一条 `errors[0]` 的码与说明，同时把完整报告放进 `details.report`。
* 成功返回值形如 `{'ok': True, ...}`，可选 `notes` 给 AI 补充说明
  （例如「模板默认值已生效」「当前用的是假后端」）。

### 5.6 大结果用产物引用

`get_results` / `analyze_s_parameters` / `export_report` **只回小摘要 + 文件路径**：
曲线数据落 CSV / 报告落 HTML，对话里只出现路径与关键指标。这既是 token 问题，也是可复现问题 ——
AI 读到的数字必须能追溯到论文/报告里的那个文件。

### 5.7 S 参数分析口径（照抄实现，别另立）

| 口径 | 取值 |
|---|---|
| 频率单位 | **GHz** |
| 幅度 dB | **20·log10\|S\|** |
| 幅度为 0 | **−300 dB** |
| 来源 | `cst_solver.run_contract.result_conventions()`（`analysis.conventions()` 转发，不另抄一份） |

**连续合格区间只按相邻采样点合并**：

* 中间只要有一个不合格点，就**断成两段**（`n_bands` 增加）；
* **绝不**把两段不相连的合格区间并成一个「总带宽」；
* `total_bandwidth_ghz` 明确是**各段带宽之和**（字段名写清了，避免被误读成一段连续带宽）；
* 需要按「频率间隔」而不是「采样索引」断开时传 `max_gap_ghz`（拼接多段扫频时用）。

**谐振**：相邻三点比较的局部极值（谷 `v[i] < v[i-1] 且 v[i] < v[i+1]`，峰对称），
幅度用 `prominence_db` 过滤毛刺；⚠️ **这是采样点级定义，不做抛物线插值** ——
给出的频率精度受限于扫频步长，要精确比较两个模型的谐振位置必须用**同一套频点**。

### 5.8 stdout 隔离与它的边界

MCP 的 stdio 传输用 **stdout** 传 JSON-RPC。上层库里有大量 `print`（模板的「已保存: …」、
`lens_build.py` 约 20 处、批量/扫描的进度输出…），一行杂讯就会让客户端解析失败。

`cst_mcp.isolation.protocol_stdout()` 在**每次工具调用期间**把 `sys.stdout` 临时指向 `sys.stderr`，
于是业务 `print` 全部落到 stderr（客户端日志里能看到，不丢），stdout 只由协议层写 JSON-RPC。

⚠️ **两个必须说清的边界（不夸大）**：

1. 这是**进程内重定向**：管得住 Python 的 `print`，**管不住 CST 进程自己的原生 stdout**
   （那是另一个进程的句柄）—— ✅ **已真机实测（2026-09-17）**：真 CST 建模 84.2 s 期间协议
   收发全程正常（`scripts/verify_service_mcp_real.py`，见 [P3 §5.4](../validation/p3_mcp_evidence.md)）。
   CST 的输出不在这条 stdio 管道上，故不污染；**改远程/共享传输或让 CST 与 Python 共进程时需重测**；
2. 它是**进程级全局状态**（并发线程的 `print` 也会被一起重定向）—— 本服务按**单 worker 串行**设计（P2），
   因此可以接受。

### 5.9 单 worker 串行 + 不提供虚假的「已取消」

* 所有执行在 `tpc_service` 的**单 worker** 里串行（比「同工程串行」更强），排队顺序即提交顺序；
* `close_project` 只关闭**本服务创建**的会话（`session_owned=True`），外部已有会话只解除注册；
* **取消**只对还没开始的任务（`queued`）有效；**运行中的任务返回 `cancel_not_supported`** ——
  CST 的停止接口尚未核实，**宁可如实说「停不了」，也不假装停掉了**。

### 5.10 关键物理条件缺失要问用户

* `build_model` 缺模板路径（既没有 `project_path`，`spec.output.template_cst` 也为空）⇒
  返回 `missing_requirement`，并在 message 里写明「请向用户确认模板工程位置，不要凭空假定」；
* `list_templates` / `validate_model_spec` 把模板默认值**显式回显**（`effective` / `field_sources` /
  `assumptions`）—— AI 必须区分「用户给的」与「模板默认的」，
  **不得用默认值静默代替用户意图**（例如频段、晶格常数、拓扑相、输出路径都必须确认）。

---

## 6. 安装与客户端配置

```bash
# 1) 核心包（提供几何 / 执行 / 数值能力）
pip install -e .
# 2) 本服务（依赖 tpc-cst>=2.0.0,<3 与 mcp==1.29.1）
pip install -e integrations/cst-mcp
```

> ⚠️ **改完核心包要重装**：新增顶层包（如 P2 的 `tpc_service`）之后**必须重新 `pip install -e .`**，
> 否则旧的可编辑安装映射里没有它，在 `integrations/cst-mcp/` 目录里 `import tpc_service` 会
> `ModuleNotFoundError`。见 [`../../skills/developer/conventions.md`](../../skills/developer/conventions.md)。

已验证组合（2026-09-17）：**Python 3.11.7 + mcp 1.29.1 + pydantic 2.13.4 + anyio 4.14.2**。
核心包支持 Python ≥3.9，但 **MCP SDK 要求 ≥3.10**，所以本发行项目的下限是 **3.10**
—— 不能默认沿用核心包的下限。

自检（不启动服务、不启 CST）：

```bash
python -m cst_mcp --check        # 打印能力报告 JSON：CST 可用性、后端、模板、工具、限制
```

**客户端配置与完整示例（BA 直波导全流程：能力 → 预检 → 建模 → 轮询 → 求解 → 结果 → 分析 → 报告）
见 [`integrations/cst-mcp/README.md`](../../integrations/cst-mcp/README.md)** ——
那里是配置片段与环境变量表（`TPC_MCP_WORKDIR` / `TPC_MCP_BACKEND` / `CST_INSTALL_PATH` / `CST_GUARD_MODE`）的权威出处，
本文件不重复抄录。

调试时看 **stderr**：协议走 stdout，业务日志（含上层库的 `print`）全部被重定向到 stderr。

---

## 7. 证据等级与已知限制

### 7.1 离线证据（71 项，全部离线）

| 测试文件 | 项数 | 覆盖 |
|---|---|---|
| `tests/test_analysis.py` | 15 | dB 口径与零值、**多段连续带宽不合并**、谐振定义、CSV 读取（含引号 / 未引号两种表头） |
| `tests/test_tools.py` | 22 | 11 个工具的离线行为、**闭环**（预检 → 建模 → 求解 → 分析 → 报告，用假后端）、失败与缺参路径 |
| `tests/test_protocol.py` | 9 | 握手、工具发现、无 CST 能力报告、非法参数、长任务状态、失败结果、**真实 stdio 子进程的 stdout 无杂讯** |
| `tests/test_client_stdio.py` | 6 | **SDK 官方客户端**连真 stdio 子进程：握手协商、工具发现、离线工具与结构化错误、长任务轮询、产物 → 分析 → 报告闭环（§5.1 的客户端侧） |
| `tests/test_write_guard.py` | 8 | 写入口纪律：清单自洽、经 run service、预检走共用纯函数、**静态不许出现 CST 原语/第二套校验规则** |
| `tests/test_backend_passthrough.py` | 6 | **真 `CstBackend` + 真服务**下的错误码透传（`config_value_out_of_range` / `workdir_escape` / `run_messages` / `project_not_found` / `backend_failed`），以及真后端下 `real_cst_backend_verified` 仍为 `False` |
| `tests/test_reporting.py` | 5 | 报告产物**路径唯一**（同一秒内多份不互相覆盖）、CSV/HTML 后缀配对、后缀用尽退化、`workdir_escape`、HTML 自包含 |

```bash
cd integrations/cst-mcp
python -m pytest tests -q          # 71 项
```

> **真实数据上的分析/报告**（不是合成曲线）：`python scripts/verify_mcp_real_curves.py`
> → 18 OK / 0 FAIL（1/2/3 端口三种工程形态）。见
> [P3 记录 §5.3](../validation/p3_mcp_evidence.md)。

> **真机「预检 → 建模 → 任务记录」**（真 CST + 真 stdio，**不求解**）：
> `python scripts/verify_service_mcp_real.py` → 20 OK / 0 FAIL（84.2 s）。
> 见 [P3 记录 §5.4](../validation/p3_mcp_evidence.md)。

### 7.2 已知限制（不要在文档里说成已完成）

| 限制 | 现状 |
|---|---|
| **真实 CST 端到端闭环** | ⚠️ **「预检 → 建模 → 任务记录」已真机验证**（§7.1，真 CST + 真 stdio）；**「求解 → S 参数 → 报告」那段未验证**，属计划 **P4/V9**。假后端（`TPC_MCP_BACKEND=fake`）产出的是**合成曲线**，能力报告与产物备注都会写明 |
| CST 进程原生 stdout 是否会污染协议通道 | ✅ **已实测不污染**（2026-09-17）：真 CST 建模 84.2 s 期间，SDK 真客户端的 JSON-RPC 收发全程正常。边界：只覆盖**本地 stdio + 建模**；改远程/共享传输或共进程需重测 |
| 运行中的任务能否取消 | ❌ 不支持（`cancel_not_supported`）。真机探针已确认 CST 侧**存在** `abort_solver` 等接口，但「调用后真的停下」必须在**运行中的求解**里观测 ⇒ 不提供虚假的「已取消」 |
| 历史 `run_id` 的语义 | ⚠️ `run_id=0` = 当前最新结果；历史任务读取需真机确认 |
| 远程 / 多客户端部署 | ❌ 未设计。当前只有**本地 stdio、单进程、单 worker** |

---

## 8. 相关文档

| 想知道什么 | 读哪份 |
|---|---|
| 产品边界、双入口设计、第一版工具契约的设计口径 | [`../architecture/cst_mcp.md`](../architecture/cst_mcp.md) |
| **客户端配置 + BA 直波导完整示例 + 工具清单** | [`../../integrations/cst-mcp/README.md`](../../integrations/cst-mcp/README.md) |
| 共用运行服务（工程注册、任务、串行、去重、恢复） | [`./tpc_service.md`](./tpc_service.md) |
| 预检 / 模板字段 / 错误码（`cst_mcp` 直接调用它） | [`./topo_modeler.md`](./topo_modeler.md) §12 |
| 运行契约、判定矩阵、频率与 dB 口径 | [`./cst_solver.md`](./cst_solver.md) 的「运行契约」小节 |
| 使用者视角：装好之后 AI 客户端怎么接、怎么用 | [`../../skills/user/tpc-usage.md`](../../skills/user/tpc-usage.md) 的「MCP 入口怎么用」一节 |
| 开发者视角：MCP 层必须遵守的两条硬约定 | [`../../skills/developer/conventions.md`](../../skills/developer/conventions.md) 第 16–17 条 |
| 后续任务与验收要求 | [`../next_plan/README.md`](../next_plan/README.md) |
