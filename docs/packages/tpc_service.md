# tpc_service —— 共用运行服务层（工程注册 + 任务服务）

> ⚠️ **证据等级**：**离线**证据 —— `tpc_service/tests/`（65 项，全部离线，用假后端 `FakeBackend`）
> 覆盖失败、请求去重、冲突、串行、重启中断、旧结果、清理与会话归属、工作目录逃逸、坏记录、
> 取消语义，以及假后端与真实后端的离线导入。
> **真机（真实 CST 后端）**：`build` 已真机验收（2026-09-17，真 CST + 真 stdio MCP，
> 20 OK / 0 FAIL：真建模 `succeeded`、只关自己开的会话、重启后 `queued → interrupted` 且不重跑），
> 见 [P2 记录](../validation/p2_service_evidence.md) §5.1；
> **`solve` / `study` 的真机闭环仍未验证**（需要求解，属计划 P4/V7）—— 本文不声称它们已通过真机。

`tpc_service` 是 TPC 的**运行服务层**：它把「一个工程怎么被注册、一次任务怎么被提交、执行到哪了、产物在哪」
收敛成一套可复用、可记录、可恢复的接口，让 **Python 用户**和（P3 的）**MCP 服务**共用同一套执行与记录能力。

它补的是中间那一层：`cst_solver` 管**一次 CST 操作**，`topo_modeler` 管**一个器件怎么建**，
`tpc_service` 管**一个工程 + 一串任务**。**不依赖 MCP**，也不重写几何 / VBA / 数值逻辑 —— 那些仍然分别属于
`topo_modeler` 与 `cst_solver`。

| 项 | 内容 |
|---|---|
| **职责** | 工程注册（复制 / 会话归属）+ 任务服务（提交 / 排队 / 串行执行 / 等待 / 取消 / 恢复）+ 状态与产物的持久化与约束 |
| **需要 CST** | ⚠️ **看后端**。默认真后端 `CstBackend` 需要 CST；传 `backend=FakeBackend()` 则**完全离线可用**，本包的测试全部跑在这条路径上 |
| **入口** | `RunService`（包级导出）；配套 `SingleWorker` / `ProjectRegistry` / `ProjectRecord` / `JobRecord` / `ServiceError` / `error_dict` / `JOB_KINDS` / `JOB_STATUSES` / `TERMINAL_STATUSES` / `params_digest` |
| **依赖** | `cst_solver`（会话、失败结构、运行契约）、`topo_modeler`（`preflight` / `config` / `result_reader` / `scanner` / `batch` / `optimizer`）、`topo_templates`（模板工程） |
| **被谁依赖** | 已由 CST MCP 适配层复用；`cst_solver` **不**反向依赖本包 |
| **源码位置** | `tpc_service/`：`__init__.py`、`errors.py`、`state.py`、`store.py`、`registry.py`、`worker.py`、`service.py`、`backends/`（`base.py` / `fake.py` / `cst_backend.py`）、`tests/` |
| **当前阶段** | **P2 共用运行服务已完成**（离线验收 + 真机 `build` 验收，2026-09-17）。`solve`/`study` 的真机闭环属计划 P4/V7，尚未进行 |

---

## 1. 它解决什么问题

在 P2 之前，「跑一次仿真」这件事在每个脚本里都要重来一遍：

1. 手工把模板工程复制到工作目录，起个不重名的文件名；
2. 手工记下「这次是谁提交的、参数是什么」——否则结果出来对不上号；
3. 手工串行：CST 的设计环境（DE）与许可不能并发，只能靠人记得别同时跑；
4. 手工判「这次的结果是不是本次的」——不先保存就交给读取器，读到的是**上一轮**的结果；
5. 进程崩了 / 手滑关了窗口之后，磁盘上留下几条「像是还在跑」的记录，没人知道它们其实已经死了；
6. 产物落在哪儿没有约束，写飞了也没人拦。

这套编排逻辑与具体器件无关，与具体软件也关系不大 —— 它属于**服务层**，而不是任何一次建模。

分层之后，同一件事变成：

```python
from tpc_service import RunService
from tpc_service.backends.fake import FakeBackend

service = RunService(r'D:\work', backend=FakeBackend())
job = service.submit('build', project_path=r'D:\work\tmp.cst', params={'spec': {...}})
service.wait(job['job_id'])['status']        # 'succeeded'
```

**分层买到了什么**：

| 收益 | 说明 |
|---|---|
| 单一执行通道 | Python 脚本与（P3 的）MCP 客户端走**同一个** `RunService`，不存在两套行为漂移 |
| 全局串行 | 一个后台线程 + 一个队列，任何时刻最多一条任务在执行（比「同工程串行」更强） |
| 可去重 | 同 `request_id` + 同参数摘要 ⇒ 返回既有任务，**不会再执行一次** |
| 可恢复 | 进程重启后把磁盘上「像是还在跑」的任务如实标成 `interrupted`，**不自动重跑** |
| 账目清楚 | 每条任务一个 JSON（原子写）+ 一份事件流；谁提交、参数是什么、产物在哪都可查 |
| 产物可控 | 所有产物必须落在服务工作目录内，逃逸即报 `workdir_escape` |
| 不依赖 MCP | 服务层是纯 Python，MCP 只是它的一个调用方 |

---

## 2. 架构

### 2.1 模块地图

```
tpc_service/                    共用运行服务层（本包）
├── __init__.py                 包级导出 RunService / SingleWorker / ProjectRegistry /
│                               ProjectRecord / JobRecord / ServiceError / error_dict /
│                               JOB_KINDS / JOB_STATUSES / TERMINAL_STATUSES / params_digest
├── errors.py                   ServiceError（code / retryable / details + to_dict）、
│                               error_dict()、ERROR_CODES；结构复用 cst_solver.failures.structured_error
├── state.py                    任务状态机 + 记录：JOB_STATUSES / TERMINAL_STATUSES / JOB_KINDS、
│                               params_digest()、can_transition()、JobRecord
├── store.py                    JobStore：<workdir>/jobs/<job_id>.json（原子写）+ <workdir>/events.jsonl；
│                               ensure_within() / is_within()：唯一的产物路径约束入口
├── registry.py                 ProjectRecord、ProjectRegistry、copy_project()：工程注册与工作副本
├── worker.py                   SingleWorker：一个后台线程 + 一个队列（全局串行）
├── service.py                  RunService：门面（提交 / 等待 / 查询 / 会话 / 取消 / 恢复 / 关闭）
├── backends/
│   ├── base.py                 Backend 契约 + ok_result() / fail_result() / artifact() 构造器
│   ├── fake.py                 FakeBackend：离线假后端（开关齐全，记录调用与并发度）
│   └── cst_backend.py          CstBackend：真实 CST 接线（**惰性导入**，不 import 不碰 CST）
└── tests/                      47 项离线测试（state / store+registry / worker 串行 / service 端到端）
```

### 2.2 依赖方向

```
tpc_service ──┬──▶ cst_solver       （会话、失败结构、运行契约）
              ├──▶ topo_modeler     （preflight / config / result_reader / scanner / batch / optimizer）
              └──▶ topo_templates   （模板工程）

cst_solver  ──▶ cst（CST 自带）         ✗ 不依赖 tpc_service
topo_modeler ─▶ cst_solver / mesh_grid  ✗ 不依赖 tpc_service
```

- 本包**不被** `cst_solver` / `topo_modeler` / `topo_templates` 反向依赖 —— 服务层是最上面的一层，
  下层包脱离它仍然可以单独使用；
- 本包**不依赖 MCP**：MCP 适配层（P3）是本包的一个调用方，不是本包的前置条件；
- `backends/cst_backend.py` 里所有 CST 相关导入都是**惰性的**（在方法体内 import），
  因此在没有 CST 的机器上 `import tpc_service` 与 `import tpc_service.backends.cst_backend` 都能成功。

---

## 3. 模块地图（符号表）

| 文件 | 主要符号 | 职责 |
|---|---|---|
| `__init__.py` | `RunService`、`SingleWorker`、`ProjectRegistry`、`ProjectRecord`、`JobRecord`、`ServiceError`、`error_dict`、`JOB_KINDS`、`JOB_STATUSES`、`TERMINAL_STATUSES`、`params_digest` | 包级导出（`__all__` 共 11 项） |
| `errors.py` | `ServiceError`、`error_dict`、`ERROR_CODES` | 结构化错误：`ServiceError` 带 `code` / `retryable` / `details` 与 `to_dict()`；四件套结构**复用** `cst_solver.failures.structured_error`（全仓唯一实现，不另起一套） |
| `state.py` | `JOB_STATUSES`、`TERMINAL_STATUSES`、`JOB_KINDS`、`params_digest`、`can_transition`、`JobRecord` | 状态机与任务记录；`JobRecord` 含 `to_dict` / `from_dict` / `note` / `add_artifact` / `transition` |
| `store.py` | `JobStore`、`ensure_within`、`is_within` | 持久化：每条任务一个 JSON（**原子写**）+ `events.jsonl` 事件流；路径约束的**唯一**入口 |
| `registry.py` | `ProjectRecord`、`ProjectRegistry`、`copy_project` | 工程注册：默认复制工程到工作目录；`ProjectRegistry` 提供 `register` / `get` / `find_by_path` / `find_by_source` / `list` / `release` / `release_all` / `artifact_path` / `describe` |
| `worker.py` | `SingleWorker` | **一个后台线程 + 一个队列**：任何时刻最多一条任务在执行；`submit` / `shutdown` / `current` / `pending` / `errors` / `is_stopped` |
| `service.py` | `RunService` | 门面：提交、查询、等待、日志、产物、结果、会话、恢复、取消、关闭、自描述 |
| `backends/base.py` | `Backend`、`ok_result`、`fail_result`、`artifact` | 后端契约与结果构造器 |
| `backends/fake.py` | `FakeBackend` | 离线假后端：开关 `fail_on` / `fail_result_on` / `delay` / `confirm_save` / `stale` / `metrics`；记录 `calls` / `max_concurrent` / `closed` |
| `backends/cst_backend.py` | `CstBackend` | 真实 CST 接线（惰性导入）：`build` 走 `topo_modeler.preflight` 预检 + `template_from_config`；`solve` 走 `cst_solver.setup` + `run_checked` + **保存** + `ResultReader` 读指标；`study` 走 `topo_modeler.scanner.ParameterScan` / `batch.BatchModeler` / `optimizer.GeneticOptimizer` |

---

## 4. 关键语义

这一节是本包**行为契约**的部分 —— 每一条都有对应的离线测试守着。

### 4.1 后端契约

三种任务类型 `build` / `solve` / `study` 都收同样的三个关键字参数，并返回同样的字典：

```python
backend.build(project=dict, params=dict, job=dict)   # 同理 solve / study
# → {'ok', 'error', 'log', 'artifacts', 'run_identity', 'result_summary', 'saved'}
```

| 键 | 含义 |
|---|---|
| `ok` | 本次操作是否成功（构造器：`ok_result()` / `fail_result()`） |
| `error` | 失败时的结构化错误（`{code, message, details, retryable}`），成功时为 `None` |
| `log` | 人类可读的日志行（会进 `logs(job_id)`） |
| `artifacts` | 产物列表（用 `artifact()` 构造，路径受工作目录约束） |
| `run_identity` | 本次运行的标识（用于判断「结果是不是本次的」） |
| `result_summary` | **小**结果摘要（大结果请给 `artifacts` 路径，见 4.9） |
| `saved` | 结果是否已**落盘保存**（见 4.2） |

后端**不写状态、不改记录**：它只负责「做一次操作并如实汇报」，任务状态由服务层决定。

### 4.2 先保存再读

`solve` / `study` 返回的 `saved` **不是 `True`** 时，服务层**直接判定 `failed`**，不进入读取环节。

原因：CST 的 `ResultReader` 是从**磁盘上的工程**读结果的 —— 求解跑完但没保存，读到的就是**上一轮**的结果。
「没保存却读了个数出来」是最难发现的一类错误：它有值、不报错、看起来完全正常。

因此计划要求「**保存求解后的结果再交给读取器**」，本包把这条做成硬判据；错误消息里含「已保存」字样，
便于调用方与测试直接核对。

### 4.3 请求去重

| 情形 | 行为 |
|---|---|
| 同 `request_id` + **参数摘要相同** | 返回**既有任务**（返回字典里 `duplicate=True`），**不会再执行一次** |
| 同 `request_id` + **参数摘要不同** | 抛 `request_id_conflict` |

参数摘要是 `params_digest()`：对**稳定 JSON**（键排序）取 sha256 —— 因此**字典键顺序不同不算冲突**，
只有真正的取值差异才会被判定为冲突。

### 4.4 重启恢复

构造 `RunService` 时 `recover=True`（**默认**）：磁盘上处于 `queued` / `running` 的任务会被标成
`interrupted`，错误码 `service_restarted`，**不自动重跑**。

进程已经不在了，那些「还在跑」的记录就是**假的**；如实标成中断、把是否重跑的判断交回调用方，
比自动重启一条来路不明的任务安全得多。想跳过这一步用 `recover=False`。

### 4.5 取消

| 任务状态 | 行为 |
|---|---|
| `queued` | **真的取消**：置为 `interrupted`，错误码 `cancelled_before_start`，任务从未开始，**不涉及 CST** |
| `running` | 抛 / 返回 `cancel_not_supported` |

`running` 的任务**不提供虚假的「已取消」**：CST 的停止接口尚未核实，本包不会假装停下了一个正在跑的 CST 求解 ——
那会让调用方以为资源已经释放，实际上没有。

### 4.6 会话归属

`close_project(project_id, save)` **只关闭 `session_owned=True` 的会话**；外部会话（不是本服务打开的）
只做**解除注册**，不会去关别人的设计环境。

`ProjectRecord` 的 `session` 字段**不落盘**、**不出 worker 线程** —— CST 句柄不对外暴露：

| 字段 | 含义 | 是否持久化 |
|---|---|---|
| `path` | 执行用的工程路径（工作副本） | ✅ |
| `source_path` | 源工程路径 | ✅ |
| `owned_copy` | 是否为服务复制出来的工作副本 | ✅ |
| `session_owned` | 会话是否由本服务打开（决定 `close_project` 关不关） | ✅ |
| `session` | CST 会话对象 | ❌ **不落盘、不出 worker 线程** |

### 4.7 工作目录约束

**所有产物必须落在服务工作目录内**。`store.ensure_within()` / `is_within()` 是**唯一**的路径约束入口：
越界即抛 `workdir_escape`。不让每个后端各写一遍检查，是因为「有一处忘了检查」等于没有约束。

### 4.8 同一源工程重复提交只注册一次

注册时会先按**执行路径**查、再按**源路径**查：同一个源工程重复提交**只会注册一次**，
不会每提交一次就复制一份工作副本。只有 `overwrite=True` 才会刷新工作副本
（`copy_project()` 默认 `overwrite=False`，目标已存在时报 `project_exists`，**不静默覆盖**）。

### 4.9 状态与记录的持久化

- 每条任务一个 JSON 文件（`<workdir>/jobs/<job_id>.json`），**原子写**；
- 另有 `<workdir>/events.jsonl` 事件流（追加式，供审计与排错）；
- `result_summary` 只放**小结果**，大结果给 `artifacts` 路径 —— 任务 JSON 是账本，不是数据仓库；
- 读不出来的坏记录**不会被静默丢掉**：它会被如实转成一条 `failed` 记录，带 `backend_failed` 错误。
  「静静地少了一条任务」比「多一条失败的记录」危险得多。

### 4.10 状态机

```
JOB_STATUSES      = ('queued', 'running', 'succeeded', 'failed', 'interrupted')
TERMINAL_STATUSES = ('succeeded', 'failed', 'interrupted')
JOB_KINDS         = ('build', 'solve', 'study')
```

| 从 | 可到 |
|---|---|
| `queued` | `running` / `interrupted` |
| `running` | `succeeded` / `failed` / `interrupted` |
| 终态（`succeeded` / `failed` / `interrupted`） | **不可再迁移** |

非法迁移抛 `invalid_transition`（判断入口 `can_transition()`）。终态不可逆这一点是刻意的：
一条已完成的任务被改成别的状态，账本就再也对不上了。

---

## 5. `RunService` API

```python
service = RunService(workdir, backend=None, *, recover=True)
```

| 方法 | 签名（要点） | 说明 |
|---|---|---|
| `submit` | `submit(kind, *, project_id=None, project_path=None, params=None, request_id=None, copy=True, overwrite=False, note='')` | 提交一条任务；`kind` ∈ `JOB_KINDS`，非法值报 `unknown_job_kind`；去重语义见 4.3 |
| `get` | `get(job_id)` | 取单条任务记录（未知 `job_id` 报 `unknown_job`） |
| `list_jobs` | `list_jobs(status=None, kind=None)` | 按状态 / 类型筛选 |
| `wait` | `wait(job_id, timeout=None)` | 阻塞等待到终态（或超时），返回任务字典 |
| `logs` | `logs(job_id)` | 任务日志行 |
| `artifacts` | `artifacts(job_id)` | 产物列表（路径均在工作目录内） |
| `result` | `result(job_id)` | 结果摘要 |
| `open_project` | `open_project(path, *, copy=True, overwrite=False, project_id=None, session=None, session_owned=False, note='')` | 注册工程（`copy=True` 时复制工作副本）；`session_owned` 决定 `close_project` 关不关它（见 4.6） |
| `projects` | `projects()` | 已注册工程列表 |
| `close_project` | `close_project(project_id, *, save=True)` | 关闭**本服务打开**的会话；外部会话只解除注册（见 4.6） |
| `recover` | `recover()` | 执行重启恢复（把 `queued` / `running` 标成 `interrupted`） |
| `cancel` | `cancel(job_id)` | 取消任务（语义见 4.5） |
| `shutdown` | `shutdown(wait=True, timeout=None)` | 停止服务；再提交报 `service_shutdown` |
| `describe` | `describe()` | 自描述字典（工作目录、后端、任务计数等） |

### 5.1 错误码（`ERROR_CODES`）

| 错误码 | 含义 |
|---|---|
| `workdir_escape` | 产物路径逃出服务工作目录 |
| `project_not_found` | 工程路径不存在 |
| `project_exists` | 复制目标已存在（未给 `overwrite=True`） |
| `project_copy_failed` | 复制工程失败 |
| `project_not_registered` | 引用了未注册的工程 |
| `request_id_conflict` | 同 `request_id` 但参数摘要不同 |
| `unknown_job_kind` | 未知任务类型 |
| `unknown_job` | 未知任务 id |
| `invalid_transition` | 非法状态迁移 |
| `cancelled_before_start` | 排队中的任务被取消（尚未开始，不涉及 CST） |
| `cancel_not_supported` | 正在运行的任务不支持取消 |
| `service_restarted` | 服务重启后发现无法确认的任务，标记为中断 |
| `backend_failed` | 后端失败 / 记录不可读 |
| `service_shutdown` | 服务已关闭 |

`ServiceError` 带 `code` / `retryable` / `details`，`to_dict()` 产出与 `cst_solver.failures.structured_error()`
**同一种**四件套结构（`{code, message, details, retryable}`），因此错误在 `cst_solver`、
`topo_modeler`、`tpc_service` 之间是**同一种**，不需要任何转换层。

> 2026-09-17 一致性检查（`scripts/check_api_consistency.py` 的 `error-codes` 项）发现
> 本表漏了两个**实际在用**的码 —— `cancelled_before_start`（`cancel()` 取消排队任务）
> 与 `service_restarted`（`recover()` 标记中断任务），已补进 `ERROR_CODES` 与本表。
> 现在「代码里用到的每个码都必须在某个 `*_ERROR_CODES` 表里」由检查强制。

---

## 6. 后端

### 6.1 `FakeBackend`（离线假后端）

不碰 CST，用于在没有 CST 的机器上验收整条服务链路。开关：

| 开关 | 作用 |
|---|---|
| `fail_on` | 指定哪种任务类型直接失败 |
| `fail_result_on` | 返回一条**失败结果**（而不是抛异常） |
| `delay` | 每次调用的人为延迟（用来观察 `running` 状态与串行性） |
| `confirm_save` | `saved` 是否返回 `True`（置 `False` 可复现「未保存即读取」这条陷阱，见 4.2） |
| `stale` | 模拟**上一轮**结果（复现 4.2 的旧结果判据） |
| `metrics` | 是否采集指标 |

采集量：`calls`（调用记录）、`max_concurrent`（**实测最大并发度** —— 串行性就靠断言它 `== 1` 来钉）、`closed`。

### 6.2 `CstBackend`（真实后端）

`RunService(workdir)` **不传 `backend`** 时使用它。全部 CST 相关导入都是**惰性**的：

| 任务 | 走什么 |
|---|---|
| `build` | `topo_modeler.preflight` 预检 + `topo_modeler.config.template_from_config` |
| `solve` | `cst_solver.setup` + `run_checked` + **保存** + `topo_modeler.result_reader.ResultReader` 读指标 |
| `study` | `topo_modeler.scanner.ParameterScan` / `batch.BatchModeler` / `optimizer.GeneticOptimizer` |

> ✅ **真实 CST 后端的 `build` 已真机验证**（2026-09-17，真 CST + 真 stdio MCP，`succeeded`
> 且任务日志含 `Rebuild 验收：success`）；`solve` / `study` 仍属计划 P4/V7。离线测试另外验证了它**能被导入**
> （惰性导入不炸），不构成任何真机行为结论。

---

## 7. 安装与使用

```bash
pip install -e .
```

```python
from tpc_service import RunService
from tpc_service.backends.fake import FakeBackend

# 离线：假后端，不需要 CST
service = RunService(r'D:\work', backend=FakeBackend())
job = service.submit('build', project_path=r'D:\work\tmp.cst', params={'spec': {...}})
service.wait(job['job_id'])['status']     # 'succeeded'
```

```python
# 真实后端：不传 backend 即使用 CstBackend
service = RunService(r'D:\work')
job = service.submit('solve',
                     project_path=r'D:\out\wg.cst',
                     params={'freq_range': (300, 380)},
                     request_id='wg-r1')      # 同 request_id + 同参数 ⇒ 去重，不会跑第二遍

if service.wait(job['job_id'], timeout=1800)['status'] == 'succeeded':
    print(service.result(job['job_id']))      # 小结果摘要
    for a in service.artifacts(job['job_id']):  # 大结果在产物路径里
        print(a['path'])

service.close_project(project_id, save=True)  # 只关本服务打开的会话
service.shutdown()
```

---

## 8. 已知限制与证据等级

| 项 | 状态 |
|---|---|
| 服务层离线行为（去重、串行、恢复、取消、路径约束、坏记录、会话归属） | ✅ 已验收：`tpc_service/tests/` 47 项，**全部离线**、全部走 `FakeBackend` |
| `running` 任务取消 | ⏳ **不支持**（`cancel_not_supported`）：CST 停止接口未核实，**不提供虚假的「已取消」** |
| 重启后的自动重跑 | ⏳ **不做**：恢复只把记录如实标成 `interrupted`，重跑由调用方决定 |
| 并发执行 | ⏳ **不做**：`SingleWorker` 是**一个**后台线程 + **一个**队列，全局串行。CST 的 DE 与许可不支持无脑并发 |
| 真实 CST 后端真机行为 | ⚠️ **`build` 已真机验证**（P2 §5.1：真 CST + 真 stdio，20 OK / 0 FAIL，含会话归属与重启状态语义）；**`solve` / `study` 尚未验证**（计划 **P4/V7**，需要求解）。本文不声称 `solve`/`study` 已通过真机 |
| MCP 适配层 | ✅ 首版已实现；本包**不依赖 MCP**，为适配层提供执行能力。真实求解闭环仍待验收 |

**测试覆盖口径**（`tpc_service/tests/`，47 项，全部离线，用假后端）：
失败、重复请求、冲突、串行（断言 `max_concurrent == 1`）、重启中断、旧结果、清理 / 会话归属、
工作目录逃逸、坏记录、取消语义、假后端与**真实后端的离线导入**。

---

## 9. 相关文档

| 想知道什么 | 读哪份 |
|---|---|
| 全仓库分层、各包职责、跨包硬约定 | [`../ARCHITECTURE.md`](../ARCHITECTURE.md) |
| CST 会话封装层（「一次 CST 操作」管到哪） | [`cst_solver.md`](./cst_solver.md) |
| 建模引擎层（「一个器件怎么建」） | [`topo_modeler.md`](./topo_modeler.md) |
| 端到端器件模板 | [`topo_templates.md`](./topo_templates.md) |
| 后续阶段计划、P2 的上下文与 P3/P4 的位置 | [`../next_plan/README.md`](../next_plan/README.md) |
| Python 包与 MCP 的双入口设计（P3 的上游依据） | [`../architecture/cst_mcp.md`](../architecture/cst_mcp.md) |
| 开发者工作流（归属判定 / 验收 / 同步矩阵） | [`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md) |
| 使用者视角总规程 | [`../../skills/user/tpc-usage.md`](../../skills/user/tpc-usage.md) |

---

*文档基于当前源码编写（`tpc_service/` 共 7 个模块 + `backends/` 3 个模块 + `tests/` 47 项离线用例）。
证据等级：服务层**离线**已验收，且真实 CST 后端的 `build` 与「会话归属 / 重启状态语义」**已真机验收**（P2 §5.1）；`solve`/`study` 属计划 P4/V7，**尚未验证**。*
