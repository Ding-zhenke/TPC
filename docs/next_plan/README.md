# TPC 后续计划（唯一待办）

更新：2026-09-18。这里只列尚未实现或尚未验收的工作。已完成的 Python 包、`tpc_service`、CST MCP 首版、六类器件模板和建模级真机记录，见[支持矩阵](../SUPPORT_MATRIX.md)、[真机验证记录](../validation/p4_real_machine_evidence.md)及[包说明](../README.md)。**本轮按用户要求不运行 CST 求解**；以下求解项只是计划，不表示已验收。

## 优先级 1：双入口真实求解闭环

- [ ] **P4/V7：Python 服务真实 runner**。用独立临时工程、有限频段、串行验证 `build → run_checked → save → read → report`；分别核对 `solve`、小范围 `scan`、`batch`、`optimize` 的任务状态、原始数据归属、审计记录和会话清理。现有离线替身及真机建模测试不能代替求解。运行前确定算例与资源上限。[P2 证据](../validation/p2_service_evidence.md)、[P4 证据](../validation/p4_real_machine_evidence.md)。
- [ ] **P4/V9：MCP 真实端到端交付**。两个发行包独立安装，以真实 CST 完成预检、建模、求解、S 参数读取、分析和 HTML/CSV 报告；保存工程、日志、原始曲线与报告。真实 stdio 建模及真实历史曲线分析已验证，求解段尚未验证。另用第三方图形客户端人工核对工具发现、长任务轮询与产物获取。[P3 证据](../validation/p3_mcp_evidence.md)。
- [ ] **P4/V2：远场物理验收**。用真实求解结果核对 Farfield 监视器、`export_farfield_csv()` 路径/模式/单位，并与参考主瓣方向比较（目标偏差 <5°）。已有样本的部分 `1D Results\farfield` 条目读取报 `UnicodeDecodeError`，须复核实际结果树及替代导出路径。[调查记录](../validation/p4_real_machine_evidence.md)。
- [ ] **P4/V3：参考谐振对比**。本库工程与参考工程分别求解，使用现有 `resonance_criterion` 匹配峰/谷并计算频率差（目标 <1 GHz），解释 350 GHz 处 S11 既有 1.83 dB 差异。真实历史曲线上的规则验证已完成；缺的是本库新求解与同条件参考对照。[判据证据](../validation/p4_real_machine_evidence.md)。
- [ ] **运行中控制语义**。先核实 CST 停止/暂停能力，再决定是否支持运行中取消与进度；当前 `cancel_not_supported` 是准确行为。补充超时、中断、重启及无孤儿会话的真实求解验收。

## 优先级 2：未覆盖的器件变体

依据 [87 个 notebook 清点](../guides/notebook_migration_inventory.md)和[迁移分类](../guides/notebook_migration_p1p2.md)，先做离线几何与只建模验收，仿真验收并入 P4。P0 另列 5 个；P1/P2/P3 共 82 个，分类为 65 `COVERED`、7 `PARTIAL`、5 `NO_TEMPLATE`、5 `NOT_MIGRATED`。模板覆盖不等于求解一致。

- [ ] 为 `MZISwitch` 增加 `parallel` 十点路径与 `anti` 不对称泵浦变体；保留 `basic`/`cascade` 同几何的已核实口径。
- [ ] 为 `PowerDivider` 增加 `2H4L` 双透镜组及每条输出臂的透镜定位；现有 1 分 6 是 2×3 级联。
- [ ] 为 `ANT6_C6_hexring` 评估 `.sab` 子工程透镜、扭波导、C6 环与端口随旋转；为 5 个 `Leaky` notebook 单独设计泄漏波天线模板。
- [ ] 为 P0 `short.ipynb` 的短探针加槽结构确定变体入口；按登记表逐项补齐其余 `PARTIAL` 的几何差异。完成后重新分类，做离线测试与只建模真机验收，同步模板配置、预检和技能。

## 优先级 3：外部库提示的可选增强

来源、现有能力和采纳边界见[开源库调研](../research/cst_python_libraries.md)。以下是经差距核对的候选，不是首版承诺；不复制第三方源码。

- [ ] **多端口网络结果**：在已有单条 S 参数曲线和 CSV/HTML 基础上，增加复数 S 矩阵、端口/频率维度校验、参考阻抗、Touchstone `sNp` 读写及可选 Z/Y/VSWR 派生。先用保存的多端口结果离线对账。参考 `py4cst` 结果模块，不重复已有读取器和谐振规则。
- [ ] **量纲与参数单位**：为公开配置定义频率、长度、角度单位、转换及混用时报错；保留底层 CST 表达式透传，避免静默猜单位。参考 `py4cst` 单位封装。
- [ ] **可复现历史批处理**：评估命令缓存、确定性命名和一次提交的边界；与现有 `log_flag=0` 组合历史、守卫及 VBA 基线比对，只有实际缺口才实施。参考 `py4cst` history generator。
- [ ] **版本固定与环境诊断**：现可自动发现或显式指定 CST 路径；若多版本共存需要，再提供配置级固定选择及隔离验证。
- [ ] **单文件 `.cst` 只读取证**：当前历史解析依赖已展开工程目录。若只有单文件参考工程，先研究容器格式，再提供只读解析、损坏文件错误与跨版本回归。

其余扩展（增量建模、FDSolver/本征模、其他 CAD 格式、各向异性/色散材料、无 GUI 批处理、跨版本矩阵、3D 远场交互报告）仅在有明确算例和可验证环境后立项。

## 优先级 4：CST 2026 VBA 覆盖差距

依据本机安装的 [VBA 差距清单](../research/cst_vba_gap_analysis.md)，先补 P1 的结果对象、端口/场源、监视器、专用 solver 配置和 CST 原生参数扫描；再按需求补曲线/放样、CAD 格式、场后处理、WCS/单位/pick。帮助中存在的热、静态、瞬态、粒子、尾场和结构对象暂不做空壳封装。帮助目录索引和对象族覆盖报告已经可以离线生成；下一步只做离线 VBA golden tests、参数校验和建模级对象验证，不启动 CST 求解。

## 维护与同步

- [ ] 兼容周期结束后复评 `templates`、`tri_lib`、`hexlib` shim；先审计旧 notebook 调用者，再决定移除版本。
- 完成一项后从本计划删去；API 用法放入 `docs/packages/` 或 `docs/guides/`，证据放入 `docs/validation/`，同步 `skills/developer/`、`skills/user/`、`.github/skills/` 与[支持矩阵](../SUPPORT_MATRIX.md)。
- 真实求解验收应记录 CST/Python 版本、算例、频段、耗时、结果路径；离线测试、只建模真机测试与物理结果分开标记。
