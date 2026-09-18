# P2 共用运行服务：离线实测记录

更新：2026-09-17。**性质：离线证据**（全程用假后端，未启动 CST）。真机判据属计划 P4（V7/V8），本文件不得被当成真机结论引用。

环境：Windows / Anaconda Python 3.11.7；测试全部用 `tpc_service.backends.fake.FakeBackend`，不导入 CST。

## 1. 交付内容

| 模块 | 职责 |
|---|---|
| `tpc_service/service.py` | `RunService`：提交、查询、等待、恢复、取消、工程管理 |
| `tpc_service/worker.py` | `SingleWorker`：一个线程 + 一个队列，全局串行 |
| `tpc_service/state.py` | 状态词表、迁移规则、`JobRecord`、`params_digest` |
| `tpc_service/store.py` | 任务记录原子落盘 + 事件流 + 工作目录约束 |
| `tpc_service/registry.py` | 工程注册、副本/覆盖策略、会话归属 |
| `tpc_service/backends/{base,fake,cst_backend}.py` | 后端契约、假后端、真实 CST 接线 |

测试：`tpc_service/tests/`（**65 项，全部离线**）—— `test_state.py`:7、`test_store_registry.py`:13、`test_service.py`:16、`test_worker_serial.py`:11、`test_cst_backend_offline.py`:**18**（CstBackend 编排，见 §4.2）。

> 补充（2026-09-17，P3 期间）：`FakeBackend` 增加了 `write_csv` 开关，`solve` 会额外产出一条 300–380 GHz 的**合成** S 参数 CSV 产物（备注写明「假后端生成的合成曲线，不是真实仿真」）。用途只有一个：让 P3 的「建模 → 求解 → 分析 → 报告」闭环在没有 CST 的机器上端到端可测；它**不能**当作仿真结论。P2 的 47 项测试在该改动后仍全绿。

## 2. 逐条对照 P2 待办与验收

| 计划条目 | 结论 | 证据 |
|---|---|---|
| 不依赖 MCP 的工程注册与任务服务；单 CST worker；同工程写操作串行 | 满足（串行更强：**全局**串行） | `SingleWorker` 单线程单队列；`test_service_runs_jobs_strictly_serialized` 观测 `backend.max_concurrent == 1`，且调用顺序严格为提交顺序 |
| 建模/求解采用任务 ID 与五种状态；持久化参数、配置摘要、日志、输出路径、运行标识 | 满足 | `JobRecord` 落 `<workdir>/jobs/<job_id>.json`（原子写）+ `events.jsonl`；记录含 `params`/`params_digest`/`log`/`artifacts`/`run_identity`/`result_summary`；`test_store_roundtrip_and_events` |
| 请求 ID 去重；同 ID 不同参数报冲突 | 满足 | 同 ID 同摘要 ⇒ `duplicate=True` 且**不再执行一次**（`test_duplicate_request_returns_existing_job_without_rerunning` 断言后端调用数不变）；同 ID 不同参 ⇒ `request_id_conflict`；键顺序不同不算冲突（`test_equivalent_params_do_not_conflict`） |
| 重启后无法确认的任务标记中断，不自动重跑 | 满足 | 构造 `RunService(recover=True)` 时把 `queued`/`running` 标为 `interrupted` + `service_restarted`；`test_recover_marks_unfinished_jobs_interrupted_without_rerunning` 断言 `backend.calls == []`（真的一次都没跑） |
| 工程副本/覆盖策略、工作目录约束、保存与资源清理；只释放自己创建的会话 | 满足 | 默认复制（`.cst` + 同名目录）；已存在默认 `project_exists`，仅 `overwrite=True` 重建；`ensure_within()` 逃逸报 `workdir_escape`；`release()` 只关闭 `session_owned=True` 的会话（`test_release_closes_only_owned_sessions`） |
| 真实 CST runner 接入 ParameterScan / BatchModeler / 优化器；保存求解后的结果再交给读取器 | **编排已离线钉住、真机未验证** | `CstBackend.study` 分派 `scan`/`batch`/`optimize`（分别用 `topo_modeler` 的 `ParameterScan` / `BatchModeler` / `GeneticOptimizer`）；`solve` 在 `run_checked` 判定成功后 `app.save()` 才返回 `saved=True`。服务层对 `solve`/`study` 强制校验 `saved is True`，否则判 `failed`（`test_solve_without_confirmed_save_fails`）。**新增 `tpc_service/tests/test_cst_backend_offline.py`（18 项，见 §4.2）**：三路编排与纪律全部离线覆盖 |
| CST 取消/停止能力先核实；未验证前不提供虚假的「已取消」 | 满足（按「不假装」实现）；**离线核实部分已完成**（见 §4.1） | `cancel()` 对 `queued` 任务真的取消（`cancelled_before_start`，不涉及 CST）；对 `running` 任务返回 `cancel_not_supported`（`test_cancel_running_job_is_refused_not_faked`） |

验收判据「可注入假后端覆盖失败、重复请求、竞争、重启中断、旧结果和清理」：**全部覆盖**

| 判据 | 测试 |
|---|---|
| 失败 | 后端抛异常 / 返回结构化失败 / 求解未确认保存 ⇒ 一律 `failed`（3 个用例） |
| 重复请求 | 见上表去重行 |
| 竞争 | `test_service_runs_jobs_strictly_serialized`（并发提交 5 条，最大并发 1） |
| 重启中断 | 见上表恢复行 |
| 旧结果 | `FakeBackend(stale=True)` ⇒ 摘要如实带 `stale=True`，**不隐藏**（`test_stale_results_are_flagged_not_hidden`） |
| 清理 | 会话归属 2 个用例 + `close_project` 只关自有会话 |

验收判据「用真实临时工程验证对象归属与状态语义」：**未做**，属 P4/V8（需要真机）。

## 3. 与 P1 运行契约的衔接

`tpc_service` **不重复实现**运行判定：`CstBackend.solve` 直接调 `cst_solver` 的 `run_checked()`
（P1 交付的 `cst_solver/run_contract.py`），把 `succeeded` 作为服务层成功的前置条件；
失败时把 `run_contract` 的错误码（`run_exception` / `run_messages` / `results_unchanged` …）
原样透传进任务记录。也就是说：**「算完了、结果是本次的」这件事只有一个判定实现**。

## 4. 开发过程中发现并修掉的真实缺陷

| 现象 | 根因 | 处理 |
|---|---|---|
| 第二次提交同一个源工程时误报 `project_exists` | `_resolve_project` 只按**执行路径**（工作副本）查注册表，源路径相同的重复提交查不到，于是又复制一遍、撞上「工作副本已存在」 | 增加 `ProjectRegistry.find_by_source()`，解析顺序改为「先执行路径、再源路径」；只有显式 `overwrite=True` 才刷新工作副本 |
| 坏掉的任务记录会被静默跳过 | 初版 `JobStore.all()` 直接 `continue` | 改为把它变成一条 `failed` 记录并带 `backend_failed` 错误与说明（`test_store_reports_broken_records_instead_of_dropping_them`） |

### 4.1 CST 取消/停止接口：离线可查的部分已查清（2026-09-17）

计划要求「停止接口与语义核实前不开放取消运行中任务」。本轮把**不需要起 CST 就能查清的部分**查清了，
并把必须真机做的那一步做成一条命令：`scripts/probe_solver_control_api.py`。

**新发现的方法学（可复用）**：CST 的 Python 接口是
`<安装目录>\AMD64\_cst_interface.cpNN-win_amd64.pyd`（pybind11 扩展），
**版本号对得上就能在本机 Python 里离线 import 并内省**，无需启动 DesignEnvironment：

```python
sys.path.insert(0, r'C:\SOFTWARE\CST Studio Suite 2026\AMD64')
sys.path.insert(0, r'C:\SOFTWARE\CST Studio Suite 2026\AMD64\python_cst_libraries')
import _cst_interface            # 实测：Python 3.11.7 + cp311 .pyd → import OK
```

实测结论：

| 类 | 公开静态成员数 | 名字命中 stop/abort/cancel/terminate/interrupt/kill |
|---|---|---|
| `DesignEnvironment` | 33 | **无**（只有 `close()`：关 DE） |
| `Project` | 15 | **无**（只有 `close()`：*closes the project without saving*） |
| `Model3D` | 2 | **无**（静态只有 `allow/disallow_history_commands()`） |

`Model3D` 继承 `RemoteObject`，是**动态 COM 代理（`__getattr__` 分发）**：
`add_to_history()` 以及本项目参考资料
[`cst-official-api-reference.md`](../references/cst-official-api-reference.md) §9 记录的
`abort_solver()/run_solver()/start_solver()` 这类扩展方法 **`dir()` 看不到**
⇒ **静态内省无法定论「有没有停止接口」**，必须在活的 DE 上 `hasattr`。

⚠️ **同时记一条反面教训**：直接扫 `.pyd` 二进制找符号名（ASCII / UTF-16）**不可靠** ——
连确定存在且天天在用的 `add_to_history`、`StoreDoubleParameter` 都是 **0 命中**
（方法名不在明文里）。这类扫描**不得**作为证据；本脚本也不采用。

**剩余（真机、秒级）**：`python scripts/probe_solver_control_api.py --live`
—— 只开一个空工程，对候选名字逐个 `hasattr` 并打印 docstring，然后**只关自己开的 DE**，
全程带弹窗守卫；不建模、不求解。拿到结果后再决定是否开放在任务取消
（还要顺带回答「终止等待 vs 停止求解」的语义，那需要一次真实运行中的求解）。

### 4.2 `CstBackend` 的离线编排测试（2026-09-17）

计划原本写道：`CstBackend` 的 `build`/`solve`/`study` 只经过「离线导入与失败路径」测试。
新增 `tpc_service/tests/test_cst_backend_offline.py`（**18 项**，不碰 CST）把编排与纪律钉住 ——
替身会话（记录 `run_checked`/`save`/`close` 顺序）、替身模板、替身预检，
但 `ParameterScan`/`BatchModeler`/`GeneticOptimizer` 用的是**真实现**。

| 断言 | 用例 |
|---|---|
| 预检未过 ⇒ **一次都不建模板** | `test_build_stops_before_creating_template_when_preflight_fails` |
| `solve` 顺序必须是 `run_checked → save → 读取器` | `test_solve_saves_before_reading_and_closes` |
| 运行契约未判 `succeeded` ⇒ **绝不 save、也不读结果** | `test_solve_never_saves_when_run_contract_fails` |
| 读结果失败不改变「已保存」，但要写进摘要与日志 | `test_solve_reader_failure_keeps_saved_fact` |
| 关闭会话失败不掩盖求解结果 | `test_solve_close_failure_does_not_mask_result` |
| 建模失败也要 `close()`；产物必须落在工作目录内 | 两个用例（含 `workdir_escape`） |
| 三路分派真的跑到既有实现；单点失败进 `last_errors` 而任务不崩 | `test_study_*`（5 项） |
| 未知 `kind`、缺必填字段 ⇒ 结构化失败 | `test_study_unknown_kind_and_missing_fields_are_structured` |

**过程中修掉两个真实缺陷**（都是这些用例逼出来的）：

| 现象 | 根因 | 处理 |
|---|---|---|
| `build` 的 Rebuild 验收在真机上**必然失败**（且被静默记成 `validation='unknown'`） | 代码**先 `template.close()` 再 `template.validate()`**，而 `validate()` 走的是 `self.app.validate_model()` —— 会话已经关了 | 把验收移进 `try` 内、`finally` 之前：`build_all → save → validate → close`；顺序由用例钉住 |
| 优化路摘要里 `best` 恒为 `None` | 取的是 `OptResult` 上**不存在**的属性 `best`（真名是 `best_params`） | 改为 `best_params`，并补 `generations_run` 与 `seed` |

## 5. 仍未覆盖 / 待 P4

| 项 | 说明 |
|---|---|
| `CstBackend` 真机行为 | **`build` 已真机验收**（2026-09-17，§5.1：真 CST 后端 + 真 stdio MCP，`succeeded`，日志含 `Rebuild 验收：success`）；`solve` / `study`（scan/batch/optimize 三路）仍只有离线编排测试，需要**求解** ⇒ P4/V7 |
| CST 取消/停止接口 | **真机探针已完成**（2026-09-17）：CST 2026 侧**存在** `abort_solver` / `start_solver` / `get_solver_run_info` 等（不存在 `AbortSolver`/`stop_solver`/`IsSolving`）。但「调用后求解**真的**停下」必须**在一次运行中的求解里**观测 ⇒ 运行中任务的取消**继续拒绝**（`cancel_not_supported`），不猜 |
| 取消等待语义 | 「终止等待 ≠ 停止 CST」——`wait(timeout=…)` 超时只返回当前状态，不代表已停止 |
| 多实例/许可行为 | 未实测；服务层按单 worker 设计，不开并行 |
| 真实临时工程验证对象归属 | ✅ **已完成**（2026-09-17，§5.1） |

### 5.1 ✅ 真机验收：真实 CST 后端 + 真 stdio MCP（2026-09-17，**只建模不求解**）

命令：`python scripts/verify_service_mcp_real.py`（真 CST + 真 stdio；
`--no-cst` 用假后端只验接线，离线 **OK 10 / FAIL 0**）。

| 计划要求 | 实测 | 结论 |
|---|---|---|
| 真后端建模（`build`） | `build_model` → `succeeded`，**84.2 s**、轮询 42 次（另一轮 80.1 s / 40 次）；任务日志：`提交 → 开始执行 → 建模：straight_waveguide → Rebuild 验收：success → 执行完成` | ✅ 真 CST 建模闭环；**`build_all → save → validate → close` 的顺序修正在真机上被证实**（此前「先关会话再验收」在真机上必然失败并静默记成 `unknown`） |
| 产物真的是 CST 工程 | 服务工作目录下找到 2 个真工程（`projects/straight_waveguide_18`、`projects/tmp`），均有 `Model/Parameters.json` | ✅ 不是替身产物 |
| 只释放**自己**创建的会话 | 脚本先自己开一个「别人的」DE（实测 pid `7104`），再让服务跑任务：任务后 `running_design_environments()` = **[7104]**（服务自己的会话已关，没有多余 DE），「别人的」DE 仍在 | ✅ 对象归属成立（收尾时脚本自己 `close()` 掉那个 DE，最终 DE 列表回到基线 `[]`） |
| 重启后未完成任务标记中断 | 磁盘上留一条 `queued` 记录（`autostart=False`，不执行）⇒ 换新服务进程后 `get_job_status` 返回 `interrupted`，`error.code=service_restarted`、`previous_status=queued`，note 明确「**不自动重跑**」 | ✅ 与离线结论一致，且是在**真实服务进程 + 真 stdio 通道**上得到的 |
| 重启不丢已完成任务 | 上一条 `succeeded` 的真任务在重启后仍查询到 `succeeded`（记录含 `artifacts` 指向真工程） | ✅ 记录往返不丢状态 |
| 重启不偷偷重跑 | 重启前后 DE 列表完全一致（`[7104] → [7104]`） | ✅ 没有因为恢复而新开 CST |

> ⚠️ **这一轮同时就是 P3「CST 原生输出与协议通道」的真机证据**（见
> [P3 记录](./p3_mcp_evidence.md) §5.4）：CST 真的建模了 84 s，而客户端与服务的
> JSON-RPC 收发全程正常 —— CST 进程自己的 stdout 没有污染协议通道。

> ⚠️ **一个自己的坑（已修）**：脚本第一次跑时 `design_environment_query()` 报
> 「`cst.interface` 不可导入 ⇒ 查不到 DE」，于是**会话归属那两条断言根本没验到**
> （`UNKNOWN`）。根因是没把 `cst_solver.CST_PYTHON_LIB` 放进 `sys.path`。
> 这正是 §4.1 那条教训的翻版：**「问不到」不能当「没有」**。修好后基线/快照/收尾
> 三处 DE 清点才真的生效。

## 6. 复现命令

```text
python -m pytest tpc_service/tests -q                        # 65 项，全部离线（含 CstBackend 编排 18 项）
python scripts/probe_solver_control_api.py                   # 离线内省 CST 接口（6 OK，不起 CST）
python scripts/probe_solver_control_api.py --live            # （真机、秒级）候选名字 hasattr 探针
python scripts/verify_service_mcp_real.py                    # （真机、~2 分钟、不求解）服务+真 stdio MCP 闭环
python scripts/verify_service_mcp_real.py --no-cst           # 同一脚本的离线骨架（假后端，OK 10 / FAIL 0）
python -m pytest -q                                          # 全仓
python scripts/check_api_consistency.py                       # 8/8（含 tpc_service 打包白名单、MCP 写入口纪律、文档命令）
```

## 7. 相关文档

- 用法与 API：`docs/packages/tpc_service.md`；
- 使用者与开发约定：`skills/user/tpc-usage.md`、`skills/developer/conventions.md`；
- 计划状态：`docs/next_plan/README.md`（已完成项已从待办删除）。
