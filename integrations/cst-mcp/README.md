# tpc-cst-mcp —— TPC 的 CST MCP 服务

把 `tpc-cst` 的 Python 能力（预检 → 建模 → 求解 → 结果 → 分析 → 报告）暴露成 **MCP 工具**，
供 AI 客户端按用户描述驱动 CST。它**不重写**几何、VBA 或数值逻辑：
工具层只是把 `topo_modeler.preflight`（P1）、`tpc_service.RunService`（P2）、
`cst_solver.run_contract` 与 `topo_modeler.report` 串起来。

> ⚠️ **证据等级**：本服务目前只有**离线证据** —— 46 项测试全部用假后端与内存传输，
> 覆盖协议握手、工具发现、非法参数、长任务状态、失败结果、stdout 无杂讯。
> 真实 CST 上的端到端闭环属计划 **P4/V9**，本文档不给「已验证」的说法。

## 安装

```bash
# 1) 核心包（提供几何/执行/数值能力）
pip install -e .
# 2) 本服务（依赖 tpc-cst>=2.0.0,<3 与 mcp==1.29.1）
pip install -e integrations/cst-mcp
```

已验证组合（2026-09-17）：**Python 3.11.7 + mcp 1.29.1 + pydantic 2.13.4 + anyio 4.14.2**。
核心包支持 Python ≥3.9，但 MCP SDK 要求 **≥3.10**，所以本发行项目的下限是 3.10。

## 自检（不启动服务）

```bash
python -m cst_mcp --check     # 打印能力报告 JSON：CST 可用性、后端、工具、限制
```

## 客户端配置

任何支持 MCP 的客户端都按「启动一条 stdio 命令」来配：

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

| 环境变量 | 作用 |
|---|---|
| `TPC_MCP_WORKDIR` | 服务工作目录（任务记录、工程副本、报告都写这里；默认 `./tpc_mcp_work`） |
| `CST_INSTALL_PATH` / `CST_CONFIG_FILE` | CST 安装路径 / 用户 JSON 配置（见 `docs/guides/cst_environment.md`） |
| `TPC_MCP_BACKEND=fake` | 用**假后端**：离线演示/自测用。能力报告会写明后端是 `fake`，产物标注「合成曲线」，**不得当作仿真结论** |
| `CST_GUARD_MODE` | 守卫层模式（`off` / `warn` / `strict`） |

调试时看 **stderr**：协议走 stdout，业务日志（含上层库的 `print`）全部被重定向到 stderr。

## 工具清单（首版 11 个）

| 工具 | 什么时候用 | 关键点 |
|---|---|---|
| `get_capabilities` | **总是先调**：确认 CST 是否可用、后端是谁、有哪些限制 | 不启动 CST；假后端会明说 |
| `list_templates` | 看模板的字段/单位/取值域/默认值 | 未实现类型带 `buildable=false`；默认值必须回显给用户 |
| `validate_model_spec` | 建模前预检（可反复调） | **不建设计环境**；无效输入给结构化错误码 |
| `build_model` | 建模（异步任务） | 需要模板路径：`project_path` 或 `spec.output.template_cst` |
| `get_project_state` | 看工程工作副本、任务历史 | 工程默认**复制**到工作目录，不动原文件 |
| `run_simulation` | 启动求解（异步长任务） | 带 `request_id` 可幂等重发 |
| `get_job_status` | 轮询任务状态 | `interrupted` ≠ 成功；不会自动重跑 |
| `get_results` | 取结果摘要 + 产物路径 | 失败时返回结构化错误，不回空数据 |
| `analyze_s_parameters` | 找连续合格区间、谐振 | dB=20·log10\|S\|；**多段带宽分段列出，绝不合并** |
| `export_report` | 出 HTML/CSV 报告 | 返回产物路径，不把整份 HTML 塞回对话 |
| `close_project` | 释放工程 | 只关本服务创建的会话；外部会话只解除注册 |

## 完整示例：BA 直波导

用户说：**「建一个长度 18a 的 BA 直波导，看看 300–380 GHz 的传输，阈值 −3 dB」**

> AI 在动手前必须先补齐这些关键物理条件（缺哪条就问用户，**不要**拿默认值静默代替）：
> 模板工程路径、`output.path`、晶格常数 `a`、片厚 `h`、拓扑相 `AB`/`BA`、
> 长度（晶格数）、频段与阈值、是否需要报告。
> `list_templates` 里给出的默认值是**模板默认**，要与用户确认后才生效。

```jsonc
// ① 能力与限制（离线，不启 CST）
{"name": "get_capabilities", "arguments": {}}

// ② 预检：字段/单位/取值域 + 模板默认值合并（不创建 DE）
{"name": "validate_model_spec", "arguments": {"spec": {
  "model": {"type": "straight_waveguide"},
  "geometry": {"lattice_constant": 0.2425, "height": 0.25,
               "topology": "BA", "length": 18, "width": 14},
  "solver": {"fmin": 300, "fmax": 380, "monitors": ["E"]},
  "output": {"template_cst": "D:\\tpc_mcp_work\\tmp.cst",
             "path": "D:\\tpc_mcp_work\\BA_waveguide_18a.cst"}
}}}
// → ok=true, buildable=true, effective.* 里能看到生效的默认值,
//   assumptions 里列出「哪些字段用了模板默认值」

// ③ 建模（异步）
{"name": "build_model", "arguments": {
  "spec": { /* 同上 */ },
  "request_id": "ba18-run1"
}}
// → {"job_id": "job-xxxx", "status": "queued"}

// ④ 轮询
{"name": "get_job_status", "arguments": {"job_id": "job-xxxx"}}
// → status: queued → running → succeeded（failed/interrupted 都不是成功）

// ⑤ 求解（异步长任务）
{"name": "run_simulation", "arguments": {
  "project_id": "prj-xxxx", "request_id": "ba18-run1-solve"
}}

// ⑥ 结果摘要（大结果给产物路径）
{"name": "get_results", "arguments": {"job_id": "job-yyyy"}}
// → result_summary 里的指标 + run_identity（标明结果属于哪次运行）

// ⑦ S 参数分析：传输 > −3 dB 的连续合格区间
{"name": "analyze_s_parameters", "arguments": {
  "job_id": "job-yyyy", "metric": "S2,1",
  "threshold_db": -3.0, "criterion": "above", "resonance_kind": "min"
}}
// → n_bands 可能是 2（两段不相连的通带）—— bands 分段列出,
//   total_bandwidth_ghz 明确是「各段之和」，不是一段连续带宽

// ⑧ 报告（产物文件）
{"name": "export_report", "arguments": {
  "analysis": { /* ⑦ 的 analysis */ }, "job_id": "job-yyyy",
  "title": "BA 直波导 S 参数", "formats": ["html", "csv"]
}}
// → artifacts: [{kind: "html", path: ...}, {kind: "csv", path: ...}]
```

## 语义与边界（照着判断，别凭印象）

* **任务状态**：`queued` / `running` / `succeeded` / `failed` / `interrupted`。
  `interrupted`（如服务重启或排队中被取消）**不是成功**，也**不会自动重跑**。
* **结果归属**：`run_identity` 标明本次运行；`run_id=0` 是「当前最新结果」的别名，
  不是历史编号。求解必须**先保存再读**，服务层对没确认保存的任务直接判失败。
* **幂等**：同一 `request_id` 同参数 → 返回既有任务（`duplicate=true`），不会重复执行；
  同 ID 不同参数 → `request_id_conflict`。
* **串行**：所有执行在**单 worker** 里串行（比「同工程串行」更强）。
* **取消**：只对**还没开始**的任务有效；运行中的任务返回 `cancel_not_supported`
  （CST 停止接口未核实，本服务不提供虚假的「已取消」）。
* **错误**：统一 `{code, message, details, retryable}`；失败**不会**变成空数据。
* **stdout**：只承载 JSON-RPC。工具与上层库的 `print` 都被重定向到 stderr。

## 开发与测试

```bash
cd integrations/cst-mcp
python -m pytest tests -q          # 46 项，全部离线（假后端 + 内存传输 + 真 stdio 杂讯检查）
```

| 测试文件 | 覆盖 |
|---|---|
| `tests/test_analysis.py` | dB 口径、零值、**多段连续带宽不合并**、谐振定义、CSV 读取（含引号/未引号两种表头） |
| `tests/test_tools.py` | 11 个工具的离线行为、闭环（预检→建模→求解→分析→报告）、失败与缺参路径 |
| `tests/test_protocol.py` | 握手、工具发现、无 CST 能力报告、非法参数、长任务状态、失败结果、**真 stdio stdout 无杂讯** |
