# CST Python 开源库调研与采纳

核对日期：2026-09-18。既有来源使用固定 commit；新增候选以本次访问的项目源码/README 为线索。只参考功能思想，不复制第三方源码，也不增加运行时依赖。

## 核实的来源

| 项目 | 固定版本及直接证据 | 适用性 |
|---|---|---|
| `renanmav/pycst` | commit `3060b91b519711057b18213c91db8c016d218440`；[server.py](https://github.com/renanmav/pycst/blob/3060b91b519711057b18213c91db8c016d218440/src/pycst/com/server.py)、[许可](https://github.com/renanmav/pycst/blob/3060b91b519711057b18213c91db8c016d218440/LICENSE) | Apache-2.0；核心是 COM 创建与接口成员查找。能力发现的思想有参考意义，但本项目已使用 CST 官方 Python 接口，无须另加 COM 后端 |
| `SuperiorArri/py4cst`（原 Arri0） | commit `585a8dfc3aae32d15679a77aa6dcd9b0feb3cec7`；[安装工具](https://github.com/SuperiorArri/py4cst/blob/585a8dfc3aae32d15679a77aa6dcd9b0feb3cec7/src/py4cst/installation_util.py)、[Interface](https://github.com/SuperiorArri/py4cst/blob/585a8dfc3aae32d15679a77aa6dcd9b0feb3cec7/src/py4cst/cst/interface.py)、[许可](https://github.com/SuperiorArri/py4cst/blob/585a8dfc3aae32d15679a77aa6dcd9b0feb3cec7/LICENSE) | MIT；已核实安装目录发现、选择最新版本及接口内部导入 CST 的实现；其项目启动模式不直接照搬，避免关闭用户已有会话 |
| HERMES CST Python API | [CheckParam 官方项目说明](https://gitlab.insa-rennes.fr/hermes/cst-python-api/-/wikis/cst_python_api/diff?version_id=260bc8112feacea5e4e0c99b19afcdabb7f0c326) | 借鉴“执行前检查参数引用”的思路；尚未引入实现，若复制源码须另行核实代码版本与许可 |
| `bbl21/cst-runtime-cli` | 已有快照及许可见 [references](../references/README.md) | 继续复用已有参考资料，不重复引入 CLI 部署链；已有守卫与报告不重复开发 |

## 本轮落地

1. **安装发现**：借鉴 py4cst 的按版本发现安装目录思路，新增 `discover_cst_installations()`；仅接受含 Python 库的目录，多个版本按年份排序，跳过不可读目录。
2. **延迟加载**：借鉴其在接口内部导入 CST 的边界，`setup()` 与 `Result()` 才加载对应接口；纯导入、离线守卫测试与参数准备无需 CST。
3. **项目自身补强**：统一环境变量、JSON 用户配置、旧 `config.py` 的优先级；新增 doctor JSON 诊断；项目/材料日志离开 stdout；创建失败和无工程会话均可清理。

用法见 [CST 环境与生命周期](../guides/cst_environment.md)。这些能力是本项目独立实现，行为与上游并非逐项相同。

## 差距核对

| 外部线索 | 本库现状 | 结论 |
|---|---|---|
[`py4cst` 结果模块](https://github.com/SuperiorArri/py4cst/tree/main/src/py4cst/results)的 S 矩阵/矩阵转换组织 | 已有单条 S 参数读取、谐振分析、CSV/HTML 报告；未见公开的复数多端口矩阵与 Touchstone `sNp` 读写 | 规划独立的网络数据模型和标准文件互通；Touchstone 是本项目拟增功能，不声称 `py4cst` 已实现 |
[`py4cst` history generator](https://github.com/SuperiorArri/py4cst/blob/main/src/py4cst/cst/history_list_generator.py)的缓存和确定性命名 | 本库已有 `log_flag=0` 组合历史、守卫与 VBA 基线 | 只评估可复现录制/回放缺口，不重复造批量提交 |
[`py4cst` 源码树](https://github.com/SuperiorArri/py4cst)的单位封装与安装发现 | 安装发现已吸收；配置字段目前缺统一的显式量纲契约 | 候选为配置层单位校验和转换，保留 CST 表达式 |
[`chaoshu1201/pycst`](https://github.com/chaoshu1201/pycst) README 的仿真、后处理与优化方向 | 本库已有 `ParameterScan`、`BatchModeler`、`GeneticOptimizer`、`RunService` | 无明确新功能可直接采纳；优先完成本库真实求解验收 |
[`renanmav/pycst`](https://github.com/renanmav/pycst) 的 COM 接口发现 | 本库使用 CST 官方 Python 接口并已有环境诊断 | 不增加第二套 COM 后端 |

这些差距已归入[统一未完成计划](../next_plan/README.md)，此处仅保留调研依据。外部库有功能，不证明其兼容当前 CST 版本；涉及 CST 交互仍需官方帮助核验及真机测试。
