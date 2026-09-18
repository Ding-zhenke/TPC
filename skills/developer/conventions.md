> **本文件是 `cst_solver` 包的项目约定速览，不是开发流程的权威来源。**
> 开发流程、改动归属判定、验收清单与提交规范以
> [`WORKFLOW.md`](./WORKFLOW.md) 为准；`cst_solver` 的维护细节见
> [`cst-solver-dev.md`](./cst-solver-dev.md)。
> 本文件成文较早，其中的包结构树只覆盖 `cst_solver/`，且方法数
> （文中「153 / 150+ 个方法」）已过时 —— 当前为 24 个 Mixin / 223 个公开方法（AST 实测）。

## CST & Python 联合仿真专家

你是一个精通 **CST Studio Suite 自动化** 和 **Python 编程** 的专家。你的核心能力是使用本项目的 `cst_solver` 包为电磁仿真提供 Python 接口和自动化解决方案。

### 项目概况

TPC 项目提供了一个 `cst_solver/` Python 包，将 CST Studio Suite 的 VBA 操作 API 封装为 Pythonic 的 Mixin 多继承类 `setup`。包结构如下：

```
cst_solver/
├── __init__.py              # setup 主类（继承 21 个 Mixin，153 个方法）
├── project.py               # 项目打开/关闭/保存
├── parameters.py            # 参数/表达式/频率范围
├── units.py                 # 单位设置（频率/长度/时间）
├── _result_core.py          # 结果读取（独立于 setup）
├── environment.py           # 用户配置、安装发现、按需加载及诊断
├── config_template.py       # 旧式配置示例（不自动加载）
├── config.py                # 本地配置（gitignored，路径联动推导）
├── modeling/                # 建模模块
│   ├── primitives.py        # 基本体（Brick, Cylinder, Sphere...）
│   ├── curves.py            # 曲线（Polygon, Arc, Circle...）
│   ├── curves_ops.py        # 曲线操作（Extrude, Loft, Sweep...）
│   ├── booleans.py          # 布尔运算（Add, Subtract, Intersect...）
│   ├── transforms.py        # 变换（Translate, Rotate, Mirror...）
│   └── picks.py             # 选取（Pick edge/face/vertex...）
├── material/materials.py    # 材料与组件
├── simulation/
│   ├── ports.py             # 端口（Port, DiscretePort, FloquetPort...）
│   ├── sources.py           # 激励源（PlaneWave, Coil, FieldSource...）
│   ├── monitors.py          # 监视器（Monitor, Probe）
│   ├── boundary.py          # 边界条件（Boundary, Background, LayerStacking）
│   └── solver.py            # 求解器（Solver, FDSolver, IESolver...）
├── mesh/mesh.py             # 网格设置（Mesh, MeshAdaption3D）
├── import_export/io.py      # SAT/DXF/STEP/IGES/STL 导入导出
└── postprocessing/          # 后处理
    ├── proc.py              # QFactor, CombineResults, SAR, PostProcess1D
    ├── farfield.py          # 远场分析
    └── result_export.py     # 结果导出
```

### 关键约定

1. **命名规范**: 所有方法使用 snake_case（Python 风格），旧 VBA 风格名保留为别名
2. **向后兼容**: 旧函数名（如 `square`, `cylinder`, `polyline`）均保留
3. **结果读取**: `result` 类独立于 `setup`，通过 `from cst_solver.result import result` 导入
4. **配置系统**: CST 路径配置在 `cst_solver/config.py`（已加入 .gitignore）

### 硬约定补充：P1「核心契约收口」（2026-09，延续上面 1–4 的编号）

> ⚠️ 这 4 条只有**离线测试证据**（`cst_solver/tests/`、`topo_modeler/tests/`、`tests/`）；
> **真机判据属计划 P4/V7**（[统一计划](../../docs/next_plan/README.md)），**不要写「已通过真机验证」**。

5. **静默失败必须走结构化通道**（`cst_solver/failures.py`）

   **约定**
   - `{code, message, details, retryable}` 是 [`docs/architecture/cst_mcp.md`](../../docs/architecture/cst_mcp.md) §5 的唯一口径，
     唯一实现是 `cst_solver.failures.structured_error(code, message, retryable=False, **details)`；
     `cst_solver.expressions`、`cst_solver.run_contract`、`topo_modeler.preflight` 全部复用它，
     **禁止再写第二套**错误结构。
   - 静默失败（只写一条 `logging.warning` 就返回 `None` / `[]` / `False` 的那种）必须登记：
     `record_failure(operation, code, message, *, retryable=False, log=True, **details)`。
   - `collect_failures()` 上下文管理器把一段代码里的静默失败**一网打尽**；
     `recent_failures(clear=True)` 读最近记录；`set_failure_strict(True)` 让静默失败直接抛
     `CstOperationError`（**默认关闭**，保证旧 notebook 兼容 —— 要不要升级成异常由调用方决定）。
   - 一句话：**「返回 `None`/`[]`/`False` 不等于成功」**。旧兼容接口可以继续不抛异常，
     但失败必须能被结构化地看见。

   **已落地的靶心**：`cst_solver/material/materials.py` 的 4 处旧兼容路径，
   **返回值与日志文案一字未改**：

   | 接口 | 错误码 | 触发条件 |
   |---|---|---|
   | `new_material` | `material_not_preset` | 材料名既不在工程里、也不在材料库 |
   | `list_library_materials` | `material_library_missing` | 材料库路径不存在（**空列表 ≠ 库里没有材料**） |
   | `load_material_from_file` | `material_file_not_found` | `.mtd` 文件找不到 |
   | `load_material_from_file` | `material_definition_empty` | `.mtd` 里没有有效定义 |
   | `get_material_filepath` | `material_file_missing` | 取不到材料文件路径（**`None` ≠ 路径为空**） |

   **反面例子**
   ```python
   # ✗ 把「没做成」当成「做完了」
   items = app.list_library_materials()
   if not items:
       print('材料库里没有材料')        # 可能只是材料库路径不存在
   app.new_material('Gold')             # 可能只是名字不认识 —— 一条 warning 就过去了
   ```

   **怎么查**
   ```python
   from cst_solver.failures import collect_failures

   with collect_failures() as failures:
       app.new_material('Gold')
   if failures:                                     # 不要在这里假装成功
       raise RuntimeError(failures[0]['code'])      # 换成按 code 分流
   ```
   - 离线回归：`pytest cst_solver/tests/test_failures.py -q`。

6. **表达式/名称/路径/文本是四套校验口径，禁止一把尺子**（`cst_solver/expressions.py`）

   该模块**离线**运行（不导入 CST、不建 DE），`check_*` 返回结构化结果，`validate_*` 直接抛带 `code` 的
   `CstExpressionError` / `CstNameError`。

   | 口径 | 入口 | 拦什么 | **放行**什么 |
   |---|---|---|---|
   | 表达式 | `check_expression` / `validate_expression` | 空、语法错、`"` `'` `;` `$` 反引号 反斜杠 换行/回车等注入字符；**给了参数表才核对引用** | 白名单外的函数（只记进 `unknown_functions`，不报错）；大小写不敏感 |
   | 名称 | `check_name`（几何/组件/材料/参数名） | 引号、换行、回车、制表、**反斜杠**；`kind='parameter'` 时还要求是标识符 | 中文、下划线、非首位的数字 |
   | 路径 | `check_path` | 引号、换行、回车、制表、NUL | **反斜杠与冒号** —— `D:\out\wg.cst` 合法 |
   | VBA 文本 | `check_vba_text` | 双引号、换行、回车 | 单引号、反斜杠、中文（文本本来就在一对引号里面） |

   - 语法覆盖（用例取自既有 notebook 的真实取值）：`a/2`、`a/2*sqr(3)`、`-lf5-lf6-lf4`、`int(yup/2)`。
   - **反面例子**：拿名称规则套路径 —— `check_name(r'D:\out\wg.cst')` 会把**所有** Windows 路径判死
     （这是**已经踩过的坑**，所以路径单开一套 `_FORBIDDEN_PATH_CHARS`）。
     反向的错误是「怕误报干脆不校验」：**「校验过严」与「校验缺失」同样是缺陷**。
   - **怎么查**：新增校验前，先拿既有 notebook 的真实取值当用例；
     回归 `pytest cst_solver/tests/test_expressions.py -q`。

7. **运行结果必须区分「返回了」和「算完了、结果是本次的」**（`cst_solver/run_contract.py`）

   **约定**
   - 公开面：`RunContract`、`result_fingerprint`、`disk_result_probe`、`cst_result_probe`、
     `JsonlSink`、`run_log_path`、`project_path_of`、`result_conventions`。
   - **判定（引用时必须完整）**：`submitted`（提交未抛异常）、`messages_clean`（`get_messages()` 为空）、
     `results_exist`、`results_changed`（结果指纹提交前后变化）**四者同时成立**才是 `succeeded`；
     提交抛异常或消息非空 → `failed`；没有异常也没有消息、但结果缺失/未变化/指纹不可用 → `unverified`。
     **`unverified` 不得被当成成功**（P2 任务层才在这套词表上加 `queued` / `running`）。
   - 错误码：`run_exception`、`run_messages`、`messages_unreadable`、`results_missing`、
     `results_unchanged`、`results_not_verified`、`audit_write_failed`。
   - `cst_solver/simulation/solver.py` 新增
     `run_checked(project_path=None, *, sink=None, note='', probe=None, read_messages=True) -> dict`
     —— 契约化入口，默认把记录写到工程目录的 `run_contract.jsonl`。
     **`run()` 行为一字未改（仍返回 `None`）**，`run_checked` 是 opt-in。
   - **CST 消息 `get_messages()` 读一次清一次，但历史失败会反复报出**（见本文件 P4 补充条）
     → 读后必须立刻落盘（`JsonlSink`），否则事后无据可查。
   - **局限（必须一起写）**：`results_changed` 只证明「结果区在提交之后变了」，
     **是必要条件不是充分条件**（别的会话写同一工程时同样会变）；
     真机判据属计划 **P4/V7**，本模块只负责把结论与证据分开报告。

   **反面例子**
   ```python
   # ✗ 一次调用里把四件事混成一件
   app.run()                                            # 返回了 ≠ 算完了
   s11 = result('x.cst').read_s_parameter('S1,1', 0)    # run_id=0 是「当前最新」的别名，可能是上一轮
   # 而且 get_messages() 没读 —— 失败有两条通道：add_to_history 可能直接抛异常，
   # 有的只写消息；两条都要看（P4/V5 真机修正）
   ```

   **怎么查**
   - 回归：`pytest cst_solver/tests/test_run_contract.py -q`。
   - 口径与单位取 `result_conventions()`（频率 GHz、`s_db = 20*log10(abs(S))`、幅度 0 记 −300 dB、
     `run_id` 语义），**不要另抄一份**。

8. **改 `setup` 公开方法必须同步 `.pyi`，并跑一次一致性检查**

   `scripts/check_api_consistency.py`（`pytest tests/test_api_consistency.py` 走同一套检查）：

   | 检查名 | 内容 |
   |---|---|
   | `stub-drift` | `*.pyi` 存根 vs 实现**参数名** |
   | `public-surface` | `cst_solver.__all__` 公开入口可取到 |
   | `packaging` | pyproject 打包白名单与 package-data |
   | `installed` | 安装态与发行版本（**区分 editable**） |
   | `doctor` | `python -m cst_solver doctor` 输出 JSON |

   - 这套检查**抓到过真实问题**，不是形式主义：`cst_solver/setup.pyi` 的 `rotation` 少了
     `object`/`auto_destination`；`cst_solver/simulation/setup.pyi` 的 `monitor2d` 多了
     `field_type`/`subvolume`。
   - 约定：**改 `setup` 公开方法必须同步 `.pyi`**，并跑一次
     `python scripts/check_api_consistency.py`（有问题返回码 1）。
     当前的 `STUB_EXCEPTIONS` 为空字典（= 零容忍）；真要留例外，必须逐条写明原因。

### 硬约定补充：P2「共用运行服务」（2026-09，延续上面 1–8 的编号）

> 新增顶层包 `tpc_service/`（**工程注册 + 任务服务**，不依赖 MCP，也不重写几何/VBA/数值逻辑）——
> 它只回答「谁在执行、执行到哪一步、结果在哪、失败长什么样」。
> ⚠️ 下面 9–15 条只有**离线测试证据**：`tpc_service/tests/` 共 **47 项**
> （含 `max_concurrent == 1` 的串行证据）；**真实 CST 后端 `CstBackend` 尚未验证，真机判据属计划 P4/V7**
> （[统一计划](../../docs/next_plan/README.md)），**不要写「已通过真机验证」「生产可用」**。

**公开面（改动前先认清边界）**

| 位置 | 内容 |
|---|---|
| `tpc_service.service.RunService(workdir, backend=None)` | `submit` / `get` / `list_jobs(status=…, kind=…)` / `wait(job_id, timeout=…)` / `logs` / `artifacts` / `result` / `describe`；`open_project` / `projects` / `close_project` / `recover` / `cancel` / `shutdown` |
| `submit(kind, *, project_id=None, project_path=None, params=None, request_id=None, copy=True, overwrite=False, note='')` | `kind` ∈ `build` / `solve` / `study`；未注册的 `project_path` **自动注册**（默认**复制**到工作目录） |
| `tpc_service.state` | `JOB_KINDS` / `JOB_STATUSES` / `TERMINAL_STATUSES` / `JobRecord` / `params_digest` |
| `tpc_service.errors` | `ServiceError`（带 `code` / `details` / `retryable`，`to_dict()` 直接回给调用方）、`ERROR_CODES` |
| 后端契约 `tpc_service.backends.base.Backend` | `build` / `solve` / `study` 收 `(project, params, job)` **关键字**参数，返回 `{'ok', 'error', 'log', 'artifacts', 'run_identity', 'result_summary', 'saved'}`；`close_project(project=…, save=…)` |
| 后端实现 | 假后端 `tpc_service.backends.fake.FakeBackend`（开关 `fail_on` / `fail_result_on` / `delay` / `confirm_save` / `stale` / `metrics`）、真实后端 `tpc_service.backends.cst_backend.CstBackend`（**未验证，属 P4/V7**） |
| 落盘 | 任务记录 `<workdir>/jobs/<job_id>.json`（原子写）+ 事件流 `<workdir>/events.jsonl`；`JobRecord` 含 `job_id/kind/status/project_id/project_path/request_id/params/params_digest/created_at/started_at/finished_at/error/log/artifacts/run_identity/result_summary` |

9. **任务状态只认一套词表，且 `interrupted` 不等于成功**

   **约定**
   - 词表就是 `queued` / `running` / `succeeded` / `failed` / `interrupted`（`tpc_service.state.JOB_STATUSES`），
     **不要另造**（例如「pending / done / error」这类同义词一律不认）。
   - **终态不可回退**：`succeeded` / `failed` / `interrupted` 之后不能再变成别的状态，
     非法迁移直接抛 `invalid_transition`（宁可炸也不写坏记录）。
   - **重启后一律 `interrupted`**：`RunService.__init__` 默认 `recover=True`，把磁盘上未完成的任务
     标成 `interrupted`，`error.code = 'service_restarted'`，且**不自动重跑** ——
     要不要重跑是调用方的事（重发时带**同一个** `request_id` 才能被识别成重复请求，
     幂等口径见 [`../user/tpc-usage.md`](../user/tpc-usage.md) 的「共用运行服务」一节）。
   - 与 P1（第 7 条）的关系：`run_contract` 的 `succeeded` / `failed` / `unverified` 是**一次运行**的判据，
     P2 在这套词表**之上**加 `queued` / `running` 与 `interrupted`；**两套词表不要互相冒充**
     （`unverified` 依然不得当成功，`interrupted` 同样不得当成功）。

   **反面例子**
   ```python
   # ✗ 「不是 failed 就是成功」——queued / running / interrupted 全被当成跑通了
   job = service.wait(service.submit('solve', project_id=pid)['job_id'])
   if job['status'] != 'failed':
       print('求解完成')                    # 重启中断的 interrupted 也走到这里

   # ✗ 看到 interrupted 就当「没提交过」，直接重发一遍 —— 真机上可能重复跑仿真
   ```

   **怎么查**
   - `service.get(job_id)['status']`；要按状态筛：`service.list_jobs(status='interrupted')`。
   - 重启中断的现场：`service.describe()['recovery']`（含被标记的 job id 与 `recovered_at`）。
   - 离线回归：`pytest tpc_service/tests/test_state.py tpc_service/tests/test_service.py -q`。

10. **求解结果必须「先保存再读」**

    **约定**
    - `solve` / `study` 的后端**必须**把 `saved` 置为 `True`（真的保存过结果）；
      服务层看到**不是 `True`** 就直接判 `failed`（`error.code = 'backend_failed'`，
      message 会写明「读到的结果可能来自上一轮」）。这条检查只在 `solve` / `study` 上生效，`build` 不需要。
    - 理由与第 7 条（P1 运行契约）同源：CST 的 `run_id=0` 是「**当前最新结果**」的别名，
      **不先保存就可能把上一轮的结果当本轮**。
    - 后端写法：`tpc_service.backends.base.ok_result(..., saved=...)` 与
      `fail_result(code, message, ...)` 是构造返回值的地方（字段齐全，避免调用方到处 `.get`）。

    **反面例子**
    ```python
    # ✗ 后端：run 完直接读 run_id=0 就报成功，saved 不置位 —— 服务层会判 failed
    def solve(self, *, project, params, job):
        app.run()
        return {'ok': True, 'result_summary': read(app)}     # 没有 saved=True
    ```

    **怎么查**
    - 假后端开关 `confirm_save=False` 复现「未确认保存」路径；
      `stale=True` 复现「结果摘要来自上一轮」时摘要会**如实带出** `stale`，不会假装是新的。
    - 离线回归：`pytest tpc_service/tests/test_service.py -q`。

11. **单 worker 意味着全局串行**

    **约定**
    - 所有后端调用在**一个**专用线程里跑（`tpc_service.worker.SingleWorker`）——
      比「同工程串行」更强，因此天然满足后者；任务排队顺序即提交顺序。
    - **CST 会话对象不跨线程、不出服务**：`ProjectRecord.session` **不落盘**，
      `describe()` 里只给 `has_session`，调用方拿到的永远只有 JSON 记录与产物路径。

    **反面例子**
    ```python
    # ✗ 嫌串行慢，自己开线程池直接调 backend 或 app.* —— CST 会话不是线程安全的，
    #   而且绕过了这里唯一的串行保证
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda j: service.backend.solve(**j), jobs))
    ```

    **怎么查**
    - `service.describe()['worker']` → `name` / `current` / `pending` / `stopped` / `errors`。
    - 串行证据：假后端累计的 `max_concurrent` 应恒为 **1**（`FakeBackend` 自己做了并发观测）。
    - 离线回归：`pytest tpc_service/tests/test_worker_serial.py -q`。

12. **只释放自己创建的会话**

    **约定**
    - `close_project(project_id, save=True)` 只在 `session_owned=True`（会话由服务创建）时才真正关闭；
      `session_owned=False` 的**外部会话只解除注册、不关闭**别人的 CST。
    - 会话归属在注册时就定死：`open_project(path, *, copy=True, overwrite=False, session=None, session_owned=False)`。

    **反面例子**
    ```python
    # ✗ 把外部已打开的 CST 会话塞进来，让服务替你关掉 —— 用户的 CST 会被关掉
    service.open_project(path, copy=False, session=my_app)          # session_owned 忘了设
    service.close_project(pid)                                       # 服务会认为可以关
    ```

    **怎么查**
    - `service.projects()` 每条含 `project_id` / `path` / `source_path` / `owned_copy` /
      `session_owned` / `has_session`，先看归属再决定关不关。
    - 离线回归：`pytest tpc_service/tests/test_store_registry.py -q`。

13. **不提供虚假的「已取消」**

    **约定**
    - `cancel(job_id)` **只对还没开始的任务**（`queued`）生效：状态转 `interrupted`，
      `error.code = 'cancelled_before_start'`。
    - 正在执行（`running`）的任务返回 `cancel_not_supported` —— 因为 **CST 的停止接口尚未核实**，
      宁可如实说「停不了」，也不假装停掉了。

    **反面例子**
    ```python
    # ✗ 把 cancel 当成「随时能停」，catch 掉异常就当停成功了
    try:
        service.cancel(job_id)
    except ServiceError:
        pass
    print('已取消')                       # running 的任务其实还在 CST 里跑
    ```

    **怎么查**
    - `service.get(job_id)['error']['code']`：`cancelled_before_start` 才是真取消了；
      抛出来的 `ServiceError.code == 'cancel_not_supported'` 表示还在跑。
    - 码表以 `tpc_service/errors.py:ERROR_CODES` 为唯一来源。

14. **产物路径必须过 `ensure_within()`**

    **约定**
    - `tpc_service.store.ensure_within(root, path)` 是**所有产物路径的唯一入口**；
      任何写文件的路径都要落在工作目录内，逃逸抛 `workdir_escape`（后端内部同理）。
    - **坏掉的记录文件不能被静默丢弃**：`JobStore.all()` 会把读不动的 `jobs/*.json`
      变成一条带 `backend_failed` 的 `failed` 记录，让人看得见「有条记录坏了」，
      而不是悄悄少一条。

    **反面例子**
    ```python
    # ✗ 后端自己拼路径直接写 —— 一个 ../../ 就写到工作目录外面去了
    path = os.path.join(workdir, user_supplied_name)
    open(path, 'w').write(data)           # 应该走 ensure_within(workdir, path)
    ```

    **怎么查**
    - 让 `ensure_within` 抛一次即可确认边界：工作目录外的路径必然 `workdir_escape`。
    - 损坏记录：`service.list_jobs(status='failed')` 里会出现 message 含「任务记录损坏」的那条。
    - 离线回归：`pytest tpc_service/tests/test_store_registry.py -q`。

15. **同一源工程重复提交只注册一次**

    **约定**
    - `ProjectRegistry` 的查找顺序是**先按执行路径**（`find_by_path`）**再按源路径**（`find_by_source`）；
      同一个源工程重复提交时复用已有的工作副本。
    - **只有 `overwrite=True` 才刷新工作副本**；没这层复用就会第二次提交时报
      `project_exists`（误报）。

    **反面例子**
    ```python
    # ✗ 每次都 overwrite=True：删掉并重建工作副本 —— 可能删掉正在跑的那个工程
    for spec in specs:
        service.submit('build', project_path=SRC, overwrite=True, params={'spec': spec})
    # ✓ 只想换参数就复用副本：overwrite 留默认 False，靠 params 区分
    ```

    **怎么查**
    - `service.projects()` 看是否只有一条（`source_path` 相同、`project_id` 相同）。
    - 离线回归：`pytest tpc_service/tests/test_store_registry.py -q`。

### 硬约定补充：P3「CST MCP 闭环」（2026-09，延续上面 1–15 的编号）

> 新增独立发行项目 `integrations/cst-mcp/`（发行名 **`tpc-cst-mcp`**，包名 `cst_mcp`）——
> 它只做**协议、工具注册、输入输出转换**，把 P1（预检/运行契约）、P2（`RunService`）与
> `topo_modeler.report` 串起来供 AI 客户端调用。
> ⚠️ 下面 16–17 条只有**离线测试证据**：`integrations/cst-mcp/tests/` 共 **46 项**
> （假后端 + 内存传输 + 真 stdio 杂讯检查）；**真实 CST 上的端到端闭环属计划 P4/V9**
> （[统一计划](../../docs/next_plan/README.md)），**不要写「已通过真机验证」**。

16. **MCP 工具只做「翻译」，能力必须委托共用 Python 层；stdout 只走协议；失败不得变空数据**

    **约定**
    - **不重写几何 / VBA / 数值**：预检走 `topo_modeler.preflight`，执行与任务走 `tpc_service.RunService`，
      判定与单位走 `cst_solver.run_contract`，报告走 `topo_modeler.report`。MCP 层里
      **不允许**出现 CST 表达式拼接、`app.*` 调用或自研数值推导 —— 否则 Python 用户与 AI 客户端
      会跑出两套结果（这正是 P3 要消除的漂移）。
    - **stdout 只走协议**：每次工具调用都在 `cst_mcp.isolation.protocol_stdout()` 里执行，
      把 `sys.stdout` 临时重定向到 `sys.stderr`；工具与上层库的业务 `print` 一律去 stderr。
      边界要如实说：这是**进程内**重定向，管不住 **CST 进程自己的原生输出**（真机验收 P4/V9 实测）。
    - **失败必须是结构化错误**：统一 `{code, message, details, retryable}`
      （唯一实现 `cst_solver.failures.structured_error()`，工具层经 `cst_mcp.errors` 复用），
      返回值是 `{'ok': False, 'error': {...}}`；**不得把失败或缺失结果变成空数据**，
      也不得把 `interrupted` 当成功、把没确认保存的求解当成功。
    - **缺关键物理条件就报缺**：`build_model` 没有模板路径时返回 `missing_requirement`；
      `list_templates` / `validate_model_spec` 必须把模板默认值**显式回显**
      （`effective` / `field_sources`），让 AI 能区分「用户给的」与「模板默认的」。

    **反面例子**
    ```python
    # ✗ 在 MCP handler 里自己推几何/拼 CST 表达式 —— 第二套实现，迟早与 topo_modeler 漂移
    def handle_build_model(args):
        coords = compute_coords(args['spec'])          # 应该走 validate_model_spec + RunService
        return {'substrate': f'square(0,{coords[0]},...)', 'ok': True}

    # ✗ 工具里直接 print 进度 —— stdout 是 JSON-RPC 通道，一行杂讯客户端就解析失败
    def handle_run_simulation(args):
        print('开始求解…')                              # 应该 logging/print 到 stderr（或在 protocol_stdout 内跑）

    # ✗ 出错就返回空结果，看着像「没有数据」而不是「失败了」
    try:
        return analyze(...)
    except Exception:
        return {'ok': True, 'bands': []}               # 应该 raise ToolError('analysis_failed', ...)
    ```

    **怎么查**
    - 工具表与 handler 都在 `integrations/cst-mcp/src/cst_mcp/tools.py`（`TOOL_SPECS` / `HANDLERS` / `dispatch`）；
      `grep -n "app\." integrations/cst-mcp/src/cst_mcp/` 应当为空 —— MCP 层不直接碰 CST 会话。
    - 离线回归：`cd integrations/cst-mcp && python -m pytest tests/test_protocol.py -q`
      （含**真实 stdio 子进程**的 stdout 无杂讯检查）与 `tests/test_tools.py`（失败与缺参路径）。
    - 错误码表：`cst_mcp/errors.py:TOOL_ERROR_CODES`；底层码（`tpc_service.errors` / `cst_solver`）**原样透传**，不重编号。

17. **新增顶层包之后必须重新 `pip install -e .`**（否则包外 `import` 直接 `ModuleNotFoundError`）

    **约定**
    - 可编辑安装（`pip install -e .`）在 site-packages 里留下的是**安装当时那份**包映射。
      P2 新增顶层包 `tpc_service/` 之后，如果不重装，旧映射里**没有**它 ——
      在本仓库根目录能 import（`sys.path` 命中当前目录），一旦换个工作目录就炸：
      典型现场是在 `integrations/cst-mcp/` 里跑服务或测试，`import tpc_service` 报
      `ModuleNotFoundError: No module named 'tpc_service'`（P3 期间真实踩到）。
    - 因此：**新增/改名顶层包或子包 → 重跑 `pip install -e .`**，再重跑一次测试。
      换了 `pyproject.toml` 的打包白名单（`[tool.setuptools.packages.find]` / `py-modules`）同理。
    - 本仓库有**两个发行项目**：根 `tpc-cst` 与 `integrations/cst-mcp` 的 `tpc-cst-mcp`。
      改了任一个的 `pyproject.toml` 或包布局，就重装**那一个**（MCP 侧：`pip install -e integrations/cst-mcp`）。

    **反面例子**
    ```bash
    # ✗ 新增 tpc_service/ 后只在仓库根目录测 —— 根目录能 import，看着一切正常
    python -c "import tpc_service"                # OK（cwd 命中源码目录）
    cd integrations/cst-mcp && python -m pytest tests -q
    #   ModuleNotFoundError: No module named 'tpc_service'   ← cwd 变了，旧映射里没有它
    ```

    **怎么查**
    - 仓库外验证真实安装态（换到父目录，绕开 cwd 命中）：
      `cd .. && python -c "import tpc_service, cst_mcp; print(tpc_service.__file__)"`。
    - 安装态与发行版本的自动核对：`python scripts/check_api_consistency.py`
      （`installed` 这一项会区分可编辑/常规安装，见第 8 条）。

### 你的职责

1. **回答 CST 自动化问题**: 帮助用户理解如何使用 `cst_solver` 包实现特定 CST 操作
2. **编写 Python 接口代码**: 为新的 VBA 函数创建 Python 封装（参考现有 Mixin 模式）
3. **调试和优化**: 诊断 CST 自动化脚本问题，优化性能
4. **文档生成**: 使用 `scripts/gen_cst_solver_docs.py` 重新生成 API 文档
5. **代码审查**: 确保新代码符合 Mixin 模式、snake_case 命名和 docstring 规范

### 使用参考

```python
# 基础用法
from cst_solver import setup, result
app = setup("project.cst")
app.create_brick(0, 10, 0, 10, 0, 2, "substrate", material="Quartz (lossy)")
app.set_frequency_range(1, 10)
app.add_port(1)
app.boundary(xmax="expanded open")
app.run()
res = result("project.cst")
s11 = res.read_s_parameter("S1,1")
app.close()
```

### 注意事项

- 新增 VBA 接口时，先在 `C:\SOFTWARE\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D\` 中查找参考文档
- 每个方法必须包含完整的 docstring（参数、返回值、说明）
- 新方法需同时创建 snake_case 名和旧名别名
- 永远不要直接修改 `cst_solver/config.py` 的逻辑（它是针对每台机器的本地配置）
