# cst-runtime-cli 测试体系

## 分层总览

| 层 | 文件 | 依赖 | 速度 | 触发时机 |
|----|------|------|------|---------|
| 单元测试 | `tests/cli/`, `tests/core/`, `test_*.py` | 无 | <30s | 每次改代码后 |
| 管道合约测试 | `manual_pipeline_contracts.py` | CST + 工作区 | 2s–5min | push 前 |

### 单元测试（209 passed，无需 CST）

由 pytest 自动发现，在仓库内直接运行：

```powershell
uv run pytest skills/cst-runtime-cli/tests -v
```

覆盖范围：

| 文件 | 测试内容 |
|------|---------|
| `cli/test_tools_metadata.py` | 工具注册、JSON Schema 完整性、args-template |
| `cli/test_pipelines_metadata.py` | 管道注册、步骤定义、错误路径 |
| `cli/test_cli_functional.py` | CLI 功能：health-check、材料列表、报告生成 |
| `cli/test_cli_errors.py` | 错误路径：缺少 workspace、缺少参数 |
| `cli/test_governance.py` | 权限标签：读/写/会话 |
| `core/test_results.py` | 结果工具的错误路径（文件缺失、格式不符） |
| `core/test_session.py` | 会话工具的空安全 |
| `core/test_simulation.py` | gateway 守卫：改参脏检测 |
| `core/test_farfield.py` | 远场导出守卫：quantity 合法性 |
| `core/test_project.py` | 改参标注、脏标记 |
| `test_gateway.py` | gateway registry、T2/T3/T4/T5/T8/T10/T12/T13/T14 |
| `test_render.py` | SVG 图表渲染、HTML 页面、dashboard |
| `test_farfield_analysis.py` | 远场数据解析、平坦度计算 |
| `test_objective.py` | 目标函数计算 |
| `test_pipelines.py` | 管道辅助函数（parse_s11_json 等） |
| `test_arch_invariants.py` | 架构不变式：Schema 规范、Handler 注册、Import 合规 |
| `test_project_identity.py` | 跨 DE 工程附加、身份验证 |

### 管道合约测试（10 tests，需 CST COM）

文件 `manual_pipeline_contracts.py`（pytest 不自动发现，需显式指定路径）。

在**真实 CST 环境**下验证 CLI 工具的完整调用链，包括 gateway 守卫、结果读取、参数持久化。

---

## 管道合约测试详解

### 环境要求

- CST Studio Suite 已安装
- 已部署 cst_runtime（`health-check --auto-fix`）
- 工作区已初始化

### 测试矩阵

| 测试 | 工具 | 验证内容 | 仿真次数 |
|------|------|---------|---------|
| `test_health_check` | `health-check` | 运行时部署完整性 | 0 |
| `test_t8_abs_e_rejected_realized_gain_allowed` | `export-farfield-grid` | RED: Abs(E) 被 gateway 拒绝，GREEN: Realized Gain 通过 | 0 |
| `test_t13_change_parameter_warns` | `change-parameter` | 改参后返回 warning + next_action + cst_raw | 0 |
| `test_t2_change_blocks_simulation` | `start-simulation-async` | 改参后仿真被 gateway 拒绝（params_not_rebuilt） | 0 |
| `test_pipeline_inspect_project` | `inspect-project` | 管道：参数列表、实体列表、远场监视器完整 | 0 |
| `test_pipeline_prepare_experiment` | `prepare-experiment` | 管道：改参 + 保存 + 关闭成功 | 0 |
| `test_s11_export_structure` | `get-1d-result` | S11 JSON 导出结构：xdata/ydata/real/imag → dB 转换 | 0–1 |
| `test_list_run_ids` | `list-run-ids` | 历史 run_id 发现 | 0–1 |
| `test_get_parameter_combination` | `get-parameter-combination` | 指定 run_id 的参数组合回读 | 0–1 |
| `test_workflow_prepare_sim_param_roundtrip` | `prepare-experiment` + `run-experiment` | 完整工作流：改参 → 仿真 → 导出 → 参数持久化验证 | 1 |

### 缓存机制

- 首次运行：复制仓库 `refs/ref_0/ref_0.cst` 裸工程，结果缓存缺失时自动仿真
- 后续运行：工作区 `refs/ref_0/ref_0/` 结果缓存命中，跳过仿真（~2s）
- 强制刷新：删除工作区 `refs/ref_0/ref_0/` 目录，回退到自动仿真

### 运行方式

```powershell
# 从工作区目录（CWD 必须有 .cst_runtime/）
cd <workspace>

# 首次运行（无缓存，自动仿真，~5min）
uv run pytest <repo>\\skills\\cst-runtime-cli\\tests\\manual_pipeline_contracts.py -v

# 后续运行（缓存命中，~2s）
uv run pytest <repo>\\skills\\cst-runtime-cli\\tests\\manual_pipeline_contracts.py -v

# 指定工作区（env var 覆盖 CWD）
$env:CST_TEST_WORKSPACE = "C:\\path\\to\\workspace"
uv run pytest <repo>\\skills\\cst-runtime-cli\\tests\\manual_pipeline_contracts.py -v

# 单测
uv run pytest <repo>\\skills\\cst-runtime-cli\\tests\\manual_pipeline_contracts.py::test_s11_export_structure -v
```

### 结果缓存位置

```
<workspace>/refs/ref_0/
├── ref_0.cst          ← 复制自仓库
└── ref_0/             ← 仿真结果缓存（~38 MB，不入仓）
    ├── Result/
    ├── Export/
    └── ...
```
