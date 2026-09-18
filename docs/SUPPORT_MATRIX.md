# 支持矩阵 —— 已验证的 CST / Python 组合（2026-09-17）

> **这份文件的规矩**：只写**有真机证据**的组合与能力；没验证过的一律写「未验证」，
> 并且**不许**用「应该可以」「理论上支持」顶替。
> 计划里 P1 的原话是「按版本记录**实际验证过**的 CST 与 Python 组合，随 P4 真机结果发布；
> 在此之前文档只能写『开发环境』，不能声称支持矩阵」——本文件就是那份矩阵。
> 机器核对：`python scripts/check_api_consistency.py` 的 `support-matrix` 项会检查
> **本机实际检测到的 CST 版本与解释器 ABI 是否出现在下表**（本机没装 CST 时自动跳过）。

## 1. 已验证组合

| 维度 | 实测值 | 怎么来的 |
|---|---|---|
| 操作系统 | Windows（x64） | 本机实测 |
| CST Studio Suite | **2026**（AMD64），`C:\SOFTWARE\CST Studio Suite 2026` | `python -m cst_solver doctor` / `describe_interface_abi()` |
| Python | **3.11.7**（CPython `cp311`），`D:\Anaconda\python.exe` | 同上 |
| `cst.interface` ABI | 安装提供 `cp38 / cp39 / cp310 / **cp311** / cp312 / cp313` ⇒ `abi_match=True` | `describe_interface_abi()` |
| MCP 侧 | Python 3.11.7 + **`mcp==1.29.1`**（锁定，`requires-python>=3.10`） | `integrations/cst-mcp/pyproject.toml` |
| 服务层依赖 | 无第三方重依赖（标准库 + `cst_solver`） | `tpc_service` |

⚠️ `abi_match=True` **只说明「有可能导入」**（DLL、许可仍可能挡路），不等于「这个组合已验证」；
下表才是「验证过什么」。

## 2. 能力矩阵（本组合下）

| 能力 | 状态 | 证据 |
|---|---|---|
| 环境与会话生命周期（开/关、只关自建会话、弹窗检测） | ✅ **已验证** | [P4 §1/§7](validation/p4_real_machine_evidence.md)、[P2 §5.1](validation/p2_service_evidence.md)（真机 20 OK / 0 FAIL） |
| 建模：单路径模板（直波导 / 单元天线） | ✅ **已验证** | [P4 §4/§5](validation/p4_real_machine_evidence.md)（V1 AB 14 OK / 0 FAIL、V4 10/10） |
| 建模：弯折多路径 + GRIN 透镜 | ✅ **已验证** | P4 §6（17 OK / 0 FAIL）；**本组合新增**：多路径 VPC 并集与晶体裁剪 → [P5 证据](validation/p5_vpc_multi_evidence.md)；`GRINLensAntenna`（DXF 两条入口 + **透镜自转 `dphi`**）→ [P5 GRIN 证据](validation/p5_grin_lens_evidence.md)；`GRINLensAntenna(lens_method='insitu')`（**不落 DXF**，CST 内逐 `hexagon` 建环）→ [P5 就地环透镜证据](validation/p5_grin_lens_insitu_evidence.md)；`MultiPortAntenna`（3 端口，含透镜三条路线、单枚放原点）→ [P5 多端口证据](validation/p5_multiport_evidence.md)；`MZISwitch`（含透镜三条路线，单枚放原点）→ [P5 MZI 证据](validation/p5_mzi_evidence.md)；`PowerDivider`（1分2/3/4/6，含透镜三条路线 `generate`/`dxf`/`insitu` + 相位副本 + **开关/泵浦区**）→ [P5 功分器证据](validation/p5_power_divider_evidence.md) |
| 建模：把模型交给**服务层**（`CstBackend.build`） | ✅ **已验证** | [P2 §5.1](validation/p2_service_evidence.md)：真 CST 建模 `succeeded`，日志含 `Rebuild 验收：success` |
| MCP 通道（本地 stdio + 真 CST 建模） | ✅ **已验证** | [P3 §5.4](validation/p3_mcp_evidence.md)（20 OK / 0 FAIL；CST 原生 stdout 不污染协议） |
| 结果读取（**读别人已求解的工程**） | ✅ **已验证** | P4 §8.1–§8.6（5 个族 30 个真实工程 42 OK / 0 FAIL）—— 这条**不需要本机求解**就跑通了 |
| 谐振判据 / S 参数分析 / HTML+CSV 报告 | ✅ **已验证**（真实曲线） | P4 §8.2（24 OK）、P3 §5.3（18 OK） |
| **求解 `solve`** | ❌ **未验证** | 需要一次真实求解；单次时域求解约 **5300 s CPU / 2.4 GB 峰值**，启动前须确认算例与开销 |
| **扫描 / 批量 / 优化（`study` 三路）** | ❌ **未验证** | 编排逻辑已离线钉住（`tpc_service/tests/test_cst_backend_offline.py` 18 项），真机闭环需要多次求解 |
| 远场监视器与主瓣、`export_farfield_csv` | ⚠️ **部分未验证** | 本机参考工程没有可读的远场结果项（P4 §8.3）；远场 1D 条目在 1 个样本上不可读，须用真机输出复测 |
| MCP 端到端「求解 → S 参数 → 报告」 | ❌ **未验证** | 需要求解（P4/V9）；建模段已真机验证 |
| 运行中任务的取消 | ❌ **不支持**（有意） | CST 侧 `abort_solver` 等接口已确认真机存在，但「调用后真的停下」必须在运行中的求解里观测 |
| 第三方图形化 MCP 客户端 | ❌ **未验证**（人工步骤） | 官方 SDK 客户端路径已离线验证（`tests/test_client_stdio.py`） |

## 3. 这条矩阵怎么维护

1. **新增一行「✅ 已验证」的前提**：有可复跑的命令 + 落到 `docs/validation/` 的记录
   （脚本名、实测数字、失败项都要写清），不接受「我记得跑过」。
2. **换机器/换版本**：`check_api_consistency.py` 的 `support-matrix` 会在本机检测到的
   CST 版本或解释器 ABI 与上表不一致时报错，逼着文档更新（顺便提醒「新组合未验证」）。
3. **求解级能力**：未验证期间，文档、能力报告（`get_capabilities`）与任务记录都**不得**写成已支持；
   `tpc_service` 对运行中任务的取消继续返回 `cancel_not_supported`（不撒谎）。

## 4. 相关文档

- 计划与验收口径：[`next_plan/README.md`](next_plan/README.md)
- 真机验收记录：[`validation/p4_real_machine_evidence.md`](validation/p4_real_machine_evidence.md)
- 环境与安装：[`ARCHITECTURE.md`](ARCHITECTURE.md) §5、[`packages/cst_solver.md`](packages/cst_solver.md)
