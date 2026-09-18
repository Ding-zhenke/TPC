# P1 契约收口：离线实测记录

更新：2026-09-17。**性质：离线证据**（全程未启动 CST，未创建设计环境）。真机验收属计划 P4（V7/V8），本文件不得被当成真机结论引用。

环境：Windows / Anaconda Python 3.11.7 / 本机装有 CST Studio Suite 2026（`C:\SOFTWARE\CST Studio Suite 2026`），但本记录中的任何结论都**没有**依赖它。

## 1. 交付内容与证据

| # | 能力 | 落点 | 证据（测试文件:用例数） |
|---|---|---|---|
| 1 | 配置/建模预检（结构化字段描述 + 离线预检结论） | `topo_modeler/preflight.py` | `topo_modeler/tests/test_preflight.py`:21 |
| 2 | 表达式与名称校验（参数引用、几何名、材料名、CST 表达式） | `cst_solver/expressions.py` | `cst_solver/tests/test_expressions.py`:99 |
| 3 | 运行/结果契约（返回 ≠ 完成 ≠ 结果存在 ≠ 结果属于本次） | `cst_solver/run_contract.py`、`simulation/solver.py::run_checked` | `cst_solver/tests/test_run_contract.py`:20 |
| 4 | 静默失败审计（结构化失败通道 + 全仓审计） | `cst_solver/failures.py`、`material/materials.py`、`parameters.py`、`topo_modeler/modeler.py`、`scripts/audit_silent_failures.py` | `cst_solver/tests/test_failures.py`:19、`tests/test_silent_failure_audit.py`（见 §6.3） |
| 5 | API 与发行一致性 | `scripts/check_api_consistency.py` | `tests/test_api_consistency.py`（**8 项**检查 + 反向用例，含 §6.4 的错误码一致性、§6.5 的文档命令一致性） |
| 6 | 旧 notebook 导入兼容审计 | `scripts/check_notebook_imports.py` | `tests/test_notebook_import_audit.py`（见 §2.1） |

复现命令与结果：

```text
python -m pytest -q                          # 646 项，全部通过
python scripts/check_api_consistency.py      # 7/7 项通过
python scripts/audit_silent_failures.py      # 静默失败审计：31 处站点，0 问题
python scripts/check_notebook_imports.py     # 旧 notebook 导入审计：unknown 0 / 符号缺口 0
```

## 2. 逐条对照 P1 的验收判据

| 验收判据（`docs/next_plan/README.md` P1） | 结论 | 证据 |
|---|---|---|
| **离线预检不创建 DE** | 满足 | 在一个用 `sys.meta_path` 钩子**禁止 `import cst`** 的子进程里跑完整预检仍返回 `ok=True`（`test_preflight_runs_without_cst_import`）。DE 必须经 `cst.interface` 才能创建，禁掉导入即证明不可能创建。 |
| **无效输入明确失败** | 满足 | 预检对越界/枚举/类型/未知字段给出结构化错误码（实测：`config_value_out_of_range`、`config_enum_invalid`、`config_type_error`、`config_unknown_field`、`config_field_not_accepted`、`template_not_found`、`output_required`、`model_type_not_implemented`、`config_invalid_character`）；非法表达式给出 `expression_syntax_error` / `expression_forbidden_character` / `expression_unknown_parameter`。 |
| **旧 notebook 导入兼容** | 满足（**API 级**原有测试 + **导入级**新增审计，见 §2.1） | ① `new_material` 等 4 个旧兼容接口的返回值与日志文案**未改**，只多登记一条结构化失败；② `setup.run()` 仍返回 `None`（`test_run_still_returns_none`）；③ `TopoModeler(config)` 在无 CST 时仍可构造、路径/参数/推断功能照旧；④ 计划中类型在 `validate_config` 里仍是「语法放行 + warning」，既有 `test_config.py` 用例继续通过。**⑤ 新增：87 个旧 notebook 的导入语句逐条审计（§2.1）** |
| **Python 单独安装不要求 MCP 依赖** | 满足 | 核心包未引入任何 MCP 依赖；一致性检查的 `installed` 项通过（发行 `tpc-cst` 2.0.0，可编辑安装，仓库外可导入）。 |

### 2.1 「旧 notebook 导入兼容」的**导入级**审计（2026-09-17 新增）

此前这条判据只有 **API 级**证据（旧接口返回值没变），**从没验证过旧 notebook 的导入语句**
到底还能不能解析 —— 而「能不能 import」才是使用者第一时间撞上的问题。
新增 `scripts/check_notebook_imports.py`：只读 87 个 `.ipynb` 的 code cell（**不执行**），
去 IPython 魔法后 `ast` 解析导入语句，逐个判定类别并**逐符号核对**。

审计结果（`docs/guides/notebook_import_audit.md`）：

| 类别 | 顶层模块数 | 说明 |
|---|---|---|
| `current` | 3 | `cst_solver`(64 个 notebook) / `mesh_grid.tri_grid`(4) / `topo_modeler.builders`(3) |
| `legacy` | 2 | `tri_lib`(58) / `hexlib`(41) —— 由 `archive/compat/` 转发 |
| `stdlib` | 8 | `sys` / `os` / `time` / `re` / `json` / `shutil` / `subprocess` / `importlib` |
| `third-party` | 6 | `numpy` / `matplotlib` / `tqdm` / `sympy` / `scipy` / `shapely` |
| `unknown` | 0 | —— |
| `migrated` | 2 | `metalen`、`cst_solver.result`：旧名不在仓库里，但**等价实现已存在且逐名核对通过**（改一行导入即可，见下） |

**审计抓到的真实缺口（已修）**：`archive/compat/` 下原本只有 `tri_lib_shim.py` /
`hexlib_shim.py`，**文件名带 `_shim`**，所以旧 notebook 里的 `import tri_lib` 依旧
`ModuleNotFoundError`（实测确认）—— 58 + 41 个 notebook 会当场失败。
修复：新增**以旧名命名**的转发模块 `archive/compat/tri_lib.py`、`hexlib.py`
（`*_shim.py` 改为转发到它们，避免两份实现），使用者只需按文档把 `archive/compat`
加进 `sys.path`。符号级核对同时通过：`hexlib` 上旧 notebook 实际用到的
`HexLib` / `HexGridVisualizer` / `create_hex_polygon` / `save_to_dxf` /
`read_and_display_dxf_matplotlib` 在新包里都还在。

**`metalen` 的定论（同轮查清，不是缺口）**：它只在
`椭圆透镜单元天线/BA/D120/ep_cal.ipynb` 里出现（`import metalen as mt`，
该 notebook 把 TPC 仓库根加进 `sys.path` 后导入），仓库里确实**没有**这个模块，
也没有历史副本（全盘搜索确认）。但它用到的 4 个函数 ——
`hex_area_from_lattice` / `hex_area_from_side` / `ep_cal_air` /
`permittivity_to_refractive_index` —— 在 **`tpc_toolkit.effective_medium` 里同名存在**
（含 `ep_cal_air` 的比值公式），实测可调用。所以这不是缺口，而是**改名**：
该 notebook 只需把导入行换成
`from tpc_toolkit import effective_medium as mt`，其余代码一行都不用动。

脚本用 `MIGRATED_MODULES` 表记录这种「旧名 → 等价实现」的映射，并**逐名核对目标模块
真的提供同样的 API**（目标改名/删函数会导致检查失败，所以这张表不会悄悄失效）。
当前审计结果：`unknown 0`、`symbol_gaps 0`、`migrated 2`，退出码 0。

**第二个缺口（同样已定论）**：`from cst_solver.result import result`
（1 个 notebook：`Leaky/ANT_LEAKY_MK_GRID_opt.ipynb`）。v2.0 起 `cst_solver.result`
**不再是子模块**，`result` 是顶层别名，旧写法直接 `ModuleNotFoundError`。
⚠️ 这里**刻意不补** `cst_solver/result.py`：一旦存在同名子模块，
`import cst_solver.result` 之后包的 `result` 属性会被**模块对象遮蔽**，
反而破坏 `from cst_solver import result`（既有用例断言 `result` 是类）。
正确做法是改导入行为 `from cst_solver import result` —— 两条都写进了迁移表与报告。

> **审计脚本自身的一个真缺陷（本轮修掉）**：第一版按**顶层包**合并统计，
> 于是 `cst_solver` 与 `cst_solver.result` 的名字混在一起，子模块整体不存在时
> 因为「有多个子模块」而**跳过了符号核对** —— `cst_solver.result` 这个真缺口被静默放过。
> 现在改为**按完整模块名统计并逐模块核对**，并补了两条针对性用例
> （子模块分开统计、真不存在的子模块必须报 gap）。

回归：`tests/test_notebook_import_audit.py`（17 项）—— 解析/分类纯函数、旧名真的能导入
（含 `FutureWarning`、同一对象、`*_shim` 转发关系）、以及「仓库侧不得有导入缺口 +
未知模块必须已交代」的整体审计。

## 3. 运行契约的判定矩阵（实测）
判定口径：`succeeded` 需**同时**满足「提交未抛异常 + CST 消息为空 + 结果存在 + 结果指纹在提交前后变化」。

| 场景 | status | 错误码 |
|---|---|---|
| 提交成功、消息空、指纹变化 | `succeeded` | — |
| 提交抛异常 | `failed` | `run_exception` |
| 提交后消息非空（失败通道之一；另一条是提交调用本身抛异常，见 P4/V5 修正） | `failed` | `run_messages` |
| 结果指纹不可用（探测失败/取不到工程路径） | `unverified` | `results_not_verified` |
| 工程里看不到任何结果 | `unverified` | `results_missing` |
| 指纹与提交前完全一致（很可能是上一轮的结果） | `unverified` | `results_unchanged` |
| 读消息失败 | 降级为 `unverified` | `messages_unreadable` |
| 运行记录落盘失败 | 结论不变 + 报错 | `audit_write_failed` |

**必须完整引用的局限**：`results_changed` 只是**必要条件**——它证明「结果区在提交之后变了」，**不证明**这份结果就是本次提交算出来的（例如另一个会话也在写同一工程）。真机判据（真实 runner 小范围串行闭环）仍在 P4/V7。

## 4. 校验口径的实测边界

「校验过严」与「校验缺失」被同等对待，两组用例都在测试里：

- **必须放行**：33 条来自本仓库与参考 notebook 的真实表达式（`a/2`、`a/2*sqr(3)`、`0.65*a`、`-lf5-lf6-lf4`、`e1+x01*a`、`int(yup/2)`、`sqr(ec_a^2-ec_b^2)`、`2*2.2*(nrin+lx1)*a`、`pi`、`1e-3`、`.5` …）与 22 条真实名称（`vpc_A`、`feed2_opt1`、`Port 2`、`Copper (annealed)`、`直波导BA-18a` …）。
- **必须拦下**：引号/换行/分号/`$`/反引号等注入字符、`0.65*aa` 这类未知参数引用、`a+`／`(a`／`sqr(3` 等语法不完整、`1a`／`a-1` 这类非法参数名。
- **踩过并修掉的坑**：路径最初被名称规则校验，反斜杠导致**所有 Windows 路径被判死**；修正后路径与名称使用不同的禁止字符集（`check_path` 允许 `\` 与 `:`）。VBA 字面量内的自由文本（参数说明）另有一套更宽松的规则（只禁双引号/换行/回车）。

## 5. 一致性检查发现的真实问题（均已修）

脚本第一版把存根里的 `self` 也拿去和运行时对比，导致满屏假报警；修正后暴露的是真问题：

| 问题 | 位置 | 处理 |
|---|---|---|
| 存根缺参数（`rotation` 转端口的 `object`/`auto_destination` 早已实现，存根没跟上） | `cst_solver/setup.pyi` | 补齐 |
| 存根多参数（`monitor2d` 声明了实现里不存在的 `field_type`/`subvolume`） | `cst_solver/simulation/setup.pyi` | 按实现改正 |
| 包顶层没有 `__all__`，公开面与 24 个内部 Mixin 混在一起、无处核对 | `cst_solver/__init__.py` | 新增 `__all__`（Mixin 仍可直接 import，只是不再算公开面） |

## 6. 仍未覆盖 / 待 P4

| 项 | 说明 |
|---|---|
| 运行契约的真机判据 | `run_checked` 的 `results_changed`、`cst_result_probe`（`cst.results.ProjectFile` 离线读）、`JsonlSink` 写进真实工程目录，都还没在真机上走一遍（P4/V7）。 |
| stdout 隔离 | `topo_templates`、`topo_modeler/lens_build.py`、`batch/scanner/audit` 里仍有 `print`；MCP 的 stdio 通道要求 stdout 只走协议，必须在 P3 接入前隔离。 |
| 已验证 CST/Python 组合的公布 | **判据已可机器核对**（见 §6.1），但「按版本公布支持矩阵」仍需真机结果（P4）。 |
| `validate_model()` 真机证据 | 既有测试用的是假宿主，仍属未验证（P4/V8）。 |

### 6.1 解释器 ↔ CST 接口 ABI：离线判据（2026-09-17 新增）

「装了 CST 却导不进 `cst.interface`」最常见的原因是**解释器 ABI 与接口不一致** ——
而这**不需要启动 CST 就能判定**：接口是 pybind11 扩展
`<安装目录>\AMD64\_cst_interface.cpNN-win_amd64.pyd`，文件名里的 `cpNN` 就是要求的 ABI。

新增公开入口（均已导出并进 `doctor` 的 JSON）：

| 入口 | 作用 |
|---|---|
| `interpreter_abi_tag()` | 当前解释器 ABI（`cp311` 形式；**注意 `sys.implementation.cache_tag` 是 `cpython-311`，不能直接用**） |
| `describe_interface_abi(install_path=None)` | `interfaces`（安装里有哪些 cpNN）/`interpreter_abi`/`matching_abi`/`abi_match`/`note` |
| `diagnose_environment()['interface_abi']` | 同上，随 doctor 一起输出 |

实测（本机 CST 2026 + Python 3.11.7）：安装提供 `cp38/cp39/cp310/cp311/cp312/cp313`，
`abi_match=True`。⚠️ 有同 ABI 的 `.pyd` **只说明「有可能导入」**，真正导入还依赖 DLL 与许可，
因此本项**不**声称「已验证组合」——支持矩阵仍以真机结果为准。

离线回归：`cst_solver/tests/test_environment.py`（5 项：标签来源、匹配/不匹配/无 .pyd/无安装、
doctor 输出；全部用假安装目录，不碰真 CST）。开发过程中这三个用例抓到两个真实缺陷
（`CSTPaths` 字段名写错、ABI 标签取成 `cpython`），已修。

> 另外，`doctor` 的 JSON 现在含中文说明，两个 doctor 测试因此改为**显式 UTF-8** 收发 ——
> 原先依赖 Windows locale（GBK）解码，在设置 `PYTHONIOENCODING=utf-8` 的环境里会随机失败。

### 6.2 MCP 写入口纪律：从「注释要求」变成「机器检查」（2026-09-17）

P1 原话是「P3 的写入口必须**先调用**这些校验纯函数再下发 VBA，**不得另写一套规则**」。
现在这条不再只是文档约定：

* `integrations/cst-mcp/src/cst_mcp/tools.py` 显式声明 `WRITE_TOOLS`
  （`build_model` / `run_simulation` / `close_project`）与 `READ_TOOLS`，
  未归类的工具会让检查失败（新增工具必须显式归类）；
* **静态检查**：`scripts/check_api_consistency.py` 的第 6 项 `mcp-write-guard` ——
  每个写入口的源码必须引用 `runtime.get_service()`（即经共用运行服务提交），
  且 `cst_mcp/` 的**代码行**里不得出现 CST 原语
  （`add_to_history` / `cst.interface` / `cst.results` / `model3d.` / `full_history_rebuild`
  / `StoreParameter`）或第二套校验规则（`invalid_char` 之类）；
* **运行期检查**：`integrations/cst-mcp/tests/test_write_guard.py`（8 项）用替身服务与
  替身预检证明「先校验、经服务、再执行」这条路**真的被走到**
  （`build_model` 提交 `kind='build'`、`run_simulation` 提交 `kind='solve'`、
  `close_project` 真的调用服务的 `close_project`、预检工具调用的是
  `topo_modeler.preflight.validate_model_spec` 本体）；
* 反向用例：`tests/test_api_consistency.py::test_mcp_write_guard_detects_violations`
  在临时包里故意塞一个直接 `add_to_history` 的写入口，检查必须报出来。

> 顺带修掉检查器自身一个跨盘符崩溃：`_rel()` 用 `os.path.relpath` 在「仓库在 D:、
> 临时目录在 C:」时会抛 `ValueError` —— 现在退回绝对路径，不再因为报告一条问题而崩。

### 6.3 静默失败审计：把「还有哪些地方在吞异常」盘成清单（2026-09-17）

结构化失败通道（`cst_solver/failures.py`）此前只有**零散**的使用点，
「仓库里还有多少地方在吞异常」没人盘过。新增 `scripts/audit_silent_failures.py`：
用 `ast` 扫 6 个库包（不含 tests），把「`except` 块里只有 `pass`/`continue`/
返回 `None·False·[]·''`/只写一条日志」全部列出来，并要求**每个站点在登记表里写明理由**
（探测查询 / 尽力而为的清理 / 解析兜底…都可以，但必须写下来）。

| 结果 | 数值 |
|---|---|
| 命中站点 | **31** 处，涉及 **29** 个函数 |
| 未登记的站点 | 0（每个都有理由） |
| 写/判定路径上未处理的静默失败 | 0（要么 `record_failure(...)`，要么在登记表里显式 `risk_ok` + 理由） |

报告：[静默失败审计](../guides/silent_failure_audit.md)；回归：
`tests/test_silent_failure_audit.py`（15 项：扫描规则正/反例、风险词表按词判定、
登记表与代码同步、写路径零容忍、反向构造未登记站点必须报错）。

**审计过程中修掉的两个真实缺陷**（都是「空结果冒充成功」这一类）：

| 现象 | 根因 | 处理 |
|---|---|---|
| `topo_modeler.batch.running_design_environments()` 在 `cst.interface` 导不进来时返回 `[]`，与「真的没有 DE」**无法区分**（P4/V8 实测差点拿它当否定证据） | 惰性导入失败被静默吞掉，为了「无 CST 也能跑编排」而返回空列表 | 新增一等原语 `design_environment_query() → {ok, pids, reason}`：查不到时走 `record_failure(..., 'cst_interface_unavailable')`，`reason` 说明原因；`running_design_environments()` 保留旧签名（内部转调）。`close_extra_design_environments()` 改为**问不到就一个 DE 都不动**（宁可留着自己开的，也不误关用户的） |
| `tpc_toolkit/s2p.py` 用裸 `except:` 解析参数值 | 裸 except 会连 `KeyboardInterrupt` / `SystemExit` 一起吞掉（用户按 Ctrl-C 都停不下来） | 收窄为 `(TypeError, ValueError)` —— 对「非数字参数值保留原文」的行为完全一致 |

> 审计脚本自身也踩了一个坑：第一版把「返回空数据」只当成 `ast.Constant`，
> 而 `return []` / `{}` / `()` 在 AST 里是 `List`/`Dict`/`Tuple` ——
> 结果**最典型的「把失败变成空数据」反而没被认出来**（由反向用例发现并修）。
> 修好后规则变严，立刻多扫出上面 `running_design_environments` 那两处。

### 6.4 错误码一致性：跨层契约的机器检查（2026-09-17）

`check_api_consistency.py` 新增第 7 项 `error-codes`：扫出**代码里实际用到的**每个错误码
（五种产码写法：`structured_error/error_dict/fail_result/error_payload/ServiceError/ToolError/_error`
的首参、`record_failure` 的次参、任意调用的 `code=` 关键字、
`getattr(exc, 'code', '<literal>')` 的兜底、`code = '<literal>'` 赋值），
要求它必须出现在某个 `*_ERROR_CODES` 表里。错误码是**跨层契约**
（`cst_solver` → `tpc_service` → `cst_mcp` 原样透传、不重编号），手写字符串最容易
「拼错一个字母」或「加了新码忘了登记」，而调用方按码分支时完全看不出来。

**首次运行抓到三处真实漂移（均已修）**：

| 漂移 | 影响 | 处理 |
|---|---|---|
| `tpc_service.ERROR_CODES` 缺 `cancelled_before_start`、`service_restarted` | 这两个码**确实在用**（`cancel()` 取消排队任务、`recover()` 标记中断任务），却不在「唯一来源」表里 | 补进 `ERROR_CODES` + docstring 表 + [tpc_service 包说明](../packages/tpc_service.md) §5.1 |
| `cst_mcp.TOOL_ERROR_CODES` 缺 `tool_failed` | `dispatch()` 在异常没有自带 `code` 时产这个码，客户端按表判断会漏 | 补进 `TOOL_ERROR_CODES` + [cst_mcp 包说明](../packages/cst_mcp.md) |
| `TOOL_ERROR_CODES` 里的 `service_unavailable` **从未被产出** | 死表项（运行服务不可用时底层抛的是 `service_shutdown`/`backend_failed`） | 删除该码并同步文档 |

顺带补齐了此前**没有码表**的模块（检查要求「用到就要登记」）：
`cst_solver/expressions.py:EXPRESSION_ERROR_CODES`、
`cst_solver/material/materials.py:MATERIAL_ERROR_CODES`、
`topo_modeler/config.py:CONFIG_ERROR_CODES`、
`topo_modeler/preflight.py:PREFLIGHT_ERROR_CODES`、
`topo_modeler/modeler.py:MODELER_ERROR_CODES`。

> 检查器自身也被反向用例逼着改了两处：① 码表命名 `ERROR_CODES` **不以** `_ERROR_CODES` 结尾，
> 第一版按后缀匹配把它整个漏掉；② `ConfigError(message, code=...)` 是**消息在前**，
> 第一版把首参当码，于是把一堆错误消息当成了错误码。

### 6.5 文档命令一致性：第 8 项检查（2026-09-17）

`check_api_consistency.py` 新增第 8 项 `doc-commands`：文档里写的
`python scripts/*.py`、`pytest <路径>`、`pip install -e <路径>` 必须指向**真实存在**的文件。
这类引用**不是 markdown 链接**（`check_md_links.py` 只管链接），脚本改名/移动后文档会
静默烂掉 —— 而文档正是使用者照着敲的地方（本仓库的 `scripts/` 在最近若干轮里频繁增删）。

本轮实测：**没有发现坏引用**（本项因此作为**防回归**门存在）。检查器自己被反向用例逼着
改了两处，都是**误报**：

| 误报 | 原因 | 处理 |
|---|---|---|
| `skills/developer/conventions.md` 的 `tests/test_protocol.py` | 那条命令是 `cd integrations/cst-mcp && python -m pytest tests/test_protocol.py -q` —— 路径**相对 `cd` 的目录**，按仓库根判就错了 | 识别同行 `cd X &&` 前缀，用它作基准目录 |
| 正文里的「pytest 入口」「pytest 自动发现」 | 正则把正文当成了路径 | 只认**带路径分隔符或 `.py`** 的 token |

**顺带修掉一处文档陈旧**：`docs/packages/cst_solver.md` 的文件表里，
`_result.py` 被写成「正在按死代码归档」—— 实际它**早已归档**到
`archive/legacy/_result_dead_duplicate.py`（`cst_solver/_result.py` 不存在，全仓零引用）。
现已改成明确的「已归档」说明并给出归档路径；AST 统计那行的措辞也一并更正。

回归：`tests/test_api_consistency.py`（18 项，新增 5 项覆盖脚本缺失、pytest 路径缺失、
`cd` 基准目录、正文误报、`pip install -e` 路径缺失）。

## 7. 与其它文档的分工
- 使用方法与 API 细节：`docs/packages/cst_solver.md`、`docs/packages/topo_modeler.md`；
- 使用者姿势与开发硬约定：`skills/user/tpc-usage.md`、`skills/developer/conventions.md`；
- 计划状态：`docs/next_plan/README.md`（已完成项已从待办删除）。
