# 静默失败审计

- 扫描范围：`cst_solver` / `mesh_grid` / `topo_modeler` / `topo_templates` / `tpc_toolkit` / `tpc_service`（不含 tests）
- 规则：`except` 块里只有 `pass`/`continue`/返回 `None·False·[]·''`/只写日志 ⇒ 算「吞掉异常」，必须有登记理由
- 生成：`python scripts/audit_silent_failures.py`

命中站点 **31** 处，涉及函数 **29** 个；未处理的写/判定路径 **0** 处。

## 1. 逐站点

| 位置 | 函数 | 异常 | handler 动作 | 登记理由 |
|---|---|---|---|---|
| `cst_solver/__init__.py:371` | `setup.__exit__` | `Exception` | `logging.getLogger(__name__).exception('CST 清理失败，保留原始操作异常')` | 同上：`with` 收尾清理失败时只记录，不覆盖上下文里已有的原始异常。 |
| `cst_solver/__init__.py:317` | `setup.__init__` | `Exception` | `logging.getLogger(__name__).exception('打开工程失败后的 CST 会话清理失败')` | 打开工程失败后清理本次创建的会话，清理再失败只用 `logging.exception` 记录 —— 必须**保留原始异常**，不能再抛（代码里有注释）。 |
| `cst_solver/_guards.py:393` | `GuardState.geometry_exists` | `Exception` | `return False` | 守卫探针失败（fail-safe 方向，与 `param_existed` 一致）。 |
| `cst_solver/_guards.py:356` | `GuardState.param_existed` | `Exception` | `return False` | 守卫探针失败（fail-safe：按「新参数」处理，由 Rebuild 兜底）。 |
| `cst_solver/_guards.py:668` | `get_guard_state` | `Exception` | `pass` | 读全局守卫状态，取不到就用默认值；状态是**诊断信息**，不影响下发内容。 |
| `cst_solver/_guards.py:696` | `reset_guard_state` | `Exception` | `pass` | 重置内部状态时逐项清理，某项已经不存在就跳过（幂等重置）。 |
| `cst_solver/_guards.py:701` | `reset_guard_state` | `TypeError` | `pass` | 重置内部状态时逐项清理，某项已经不存在就跳过（幂等重置）。 |
| `cst_solver/_result_core.py:316` | `Result.read_3d` | `Exception` | `continue` | 遍历 3D 结果项，读不动的单项跳过；整体成功与否由返回的集合决定。 |
| `cst_solver/environment.py:52` | `discover_cst_installations` | `OSError` | `continue` | 枚举安装目录时某个子目录读不动（权限/正在卸载）就跳过 —— 这是探测，「跳过」本身就是结果，调用方拿到的是**能用的候选列表**。 |
| `cst_solver/failures.py:164` | `collect_failures` | `ValueError` | `pass` | 上下文管理器收尾时移除自己的收集器；此时移除失败意味着收集器栈已乱，再抛异常只会掩盖用户的原始异常。 |
| `cst_solver/modeling/picks.py:234` | `PickMixin._pick_succeeded` | `(TypeError, ValueError)` | `pass` | 已选数不是整数时退回消息判定（脏工程里消息会反复报历史失败，所以只作兜底）。 |
| `cst_solver/modeling/picks.py:190` | `PickMixin.get_edge_id_from_point` | `Exception` | `return None` | 同 `get_face_id_from_point`（棱边版）。 |
| `cst_solver/modeling/picks.py:174` | `PickMixin.get_face_id_from_point` | `Exception` | `return None` | 按坐标反查面号，CST 查询失败返回 None；调用方据此走「没查到」分支（不是「查到 0 号面」）。 |
| `cst_solver/modeling/picks.py:213` | `PickMixin.get_picked_count` | `Exception` | `return None` | 已选数查不到返回 None（**不是 0**），调用方区分处理，方向安全。 |
| `cst_solver/parameters.py:38` | `ParametersMixin._guard_param_probe` | `Exception` | `return False` | 探测守卫层是否挂上了 `_param_probe`；没有守卫（离线/裸用）就返回 None，调用方据此跳过守卫逻辑，属于能力探测。 |
| `cst_solver/parameters.py:131` | `ParametersMixin._set_parameter_description` | `Exception` | `pass` | 版本回退路径：失败是预期内的分支，真正的结果由后面的 VBA 路径决定。 |
| `cst_solver/run_contract.py:226` | `_fingerprint_key` | `(TypeError, ValueError)` | `return None` | 指纹取不到时返回 None，**契约本身**把「指纹不可用」当成一等结果（`results_not_verified` / `results_missing`），不是静默。 |
| `cst_solver/run_contract.py:162` | `disk_result_probe` | `OSError` | `continue` | 逐个结果目录探测可读性，读不动的跳过；最终由「有没有可用指纹」决定判定。 |
| `cst_solver/run_contract.py:321` | `project_path_of` | `Exception` | `continue` | 从历史/属性里推断工程路径，候选来源逐个尝试，全部失败返回 None。 |
| `cst_solver/simulation/monitors.py:60` | `MonitorMixin._get_model_bbox` | `AttributeError` | `return None` | `GetBoundingBox` 在部分接口版本不存在（AttributeError）⇒ 返回 None 表示「不限制子体积」，docstring 已写明。 |
| `mesh_grid/plotting.py:25` | `_covers` | `(OSError, RuntimeError)` | `return False` | 字体是否覆盖某字符的探测，探测失败按「不覆盖」处理（保守方向：会退回默认字体而不是画出豆腐块）。 |
| `mesh_grid/plotting.py:63` | `configure_chinese_font` | `ValueError` | `continue` | 逐个候选字体尝试配置，某个设不上就试下一个；全部失败会走后面的警告分支，不是静默。 |
| `mesh_grid/tri_grid/topo_path.py:917` | `TopoPath.preview` | `ImportError` | `pass` | matplotlib 版本差异导致某些绘图参数不被接受时回退到基本调用；预览不是建模结果，失败不影响下发内容。 |
| `topo_modeler/audit.py:319` | `AuditLog.read` | `json.JSONDecodeError` | `continue                           # 半行（进程被杀）跳过` | 逐行读事件流，进程被杀导致的半行跳过（代码里有内联注释）。 |
| `topo_modeler/audit.py:126` | `_jsonable` | `Exception` | `pass` | 把任意对象转成可 JSON 化的值，转不动就退化成 `repr` —— 审计日志要尽量记下来，不能因为一个字段不可序列化就丢整条记录。 |
| `topo_modeler/batch.py:601` | `_is_number` | `(TypeError, ValueError)` | `return False` | 数值判定辅助函数：不是数就返回 False（判定本身，不是失败）。 |
| `topo_modeler/lens_build_standalone.py:167` | `<module>` | `Exception` | `pass` | 独立运行脚本（不是库 API）：① 枚举 CST 参数名时某个名字取不到就跳过；② 结束时 `app.close()` 失败只记录 —— 不能让清理失败盖掉前面的结果。 |
| `topo_modeler/lens_build_standalone.py:104` | `<module>` | `Exception` | `continue` | 独立运行脚本（不是库 API）：① 枚举 CST 参数名时某个名字取不到就跳过；② 结束时 `app.close()` 失败只记录 —— 不能让清理失败盖掉前面的结果。 |
| `topo_modeler/scanner.py:632` | `_is_number` | `(TypeError, ValueError)` | `return False` | 同 `batch._is_number`（数值判定辅助）。 |
| `tpc_service/backends/fake.py:145` | `FakeBackend._write_synthetic_csv` | `OSError` | `return ''` | 假后端的合成曲线写盘失败：返回空串表示「没有 CSV 产物」。 |
| `tpc_toolkit/s2p.py:27` | `read_s2p_groups` | `(TypeError, ValueError)` | `pass` | **已知缺陷已修**（2026-09-17，本审计发现）：原来是裸 `except:`，现在收窄为 `(TypeError, ValueError)` —— 解析不出数字就保留原文；裸 except 会连 KeyboardInterrupt/SystemExit 一起吞掉。保留 `pass` 是因为「非数字参数值按字符串留着」本身就是期望行为。 |

## 2. 未处理的问题

（无）

> 这张表的作用：**新增的静默失败必须先在这里写明理由**。探测类查询、尽力而为的清理、解析兜底都是合理理由；写/判定路径上的静默失败则要求 `record_failure(...)` 或显式 `risk_ok`。
