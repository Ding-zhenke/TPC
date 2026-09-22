# TPC 技能文档（Skills）

> 本目录存放**给 AI 助手和开发者读的规程文档**，按视角分成两类。
> 与 [`../docs/`](../docs/) 的区别：`docs/` 回答「这是什么」，`skills/` 回答「我该怎么干活」。

---

## 两类视角，不要混用

### `user/` —— 使用者视角

**场景**：我要用 TPC 把某个器件建出来、跑仿真、读结果。
**边界**：**只调用现成 API，不修改库源码**。

| 文件 | 内容 |
|---|---|
| [`user/cst-solver.md`](./user/cst-solver.md) | ⭐ **cst_solver 快速使用手册**：常用 API 速查（照抄即可、不必翻源码）、不常用 API 的查源码地图、三条硬约定、症状速查、CST 侧验收、**结构示意图工程制图规范（Python+Matplotlib、中文入口、变量用 LaTeX）**、**疑似库 bug 的判定与报告流程（只报告，不修库）** |
| [`user/tpc-usage.md`](./user/tpc-usage.md) | **主手册**：按需查阅地图、报错定位表、三条硬约定（z 平面 / 布尔语义 / 阵列范围）、已知库缺陷、验收清单 |
| [`user/topo-quickstart.md`](./user/topo-quickstart.md) | ⭐ **拓扑光子晶体建模专用技能（TOPO 模块）**：器件结构解剖（超元胞六孔 → 两种相 → 域壁 → 相区 → 阵列覆盖 → 馈源/端口）、与参考工程（`硅基` notebook）逐值对齐的参数口径表、AB/BA 不变式、装配顺序、**离线拓扑正确性自检**、语义错位清单（`l1`/`l2` 命名错位等）、验收与排错、器件族可实现性判据 |
| [`user/tri-grid.md`](./user/tri-grid.md) | 三角晶格算法库 API 速查 |
| [`user/hex-grid.md`](./user/hex-grid.md) | 六边形晶格算法库 API 速查 |
| [`user/topo-modeler.md`](./user/topo-modeler.md) | 建模引擎使用者视角（模板层 / Modeler 层 / Builder 层三种用法） |

### `developer/` —— 开发者视角

**场景**：我要给库加能力、修封装层缺陷、改文档。
**边界**：可以改任何包的源码，但必须遵守工作流。

| 文件 | 内容 |
|---|---|
| [`developer/WORKFLOW.md`](./developer/WORKFLOW.md) | ⭐ **开发宪法**：改动归属判定、标准工作流、逐包验收清单、文档同步矩阵、提交规范、禁止事项 |
| [`developer/conventions.md`](./developer/conventions.md) | 项目约定与 cst_solver 结构速览 |
| [`developer/cst-solver-dev.md`](./developer/cst-solver-dev.md) | 维护 / 扩展 `cst_solver` 的专门技能（含**待修清单**与硬约定来源） |
| [`developer/doc-generation.md`](./developer/doc-generation.md) | API 文档生成与维护 |

---

## 先搞清层级：TPC → 子包 → skill

**TPC 是整个库（本仓库），由多个领域范围、大小各不相同的子包组成，自底向上分层：**

| 层级 | 子包 | 领域范围 | 对应 skill |
|---|---|---|---|
| 通用底层 | `cst_solver/` | **最小**：只做 CST VBA → Python 封装，与研究方向无关，任何 CST 模型都能用 | [`user/cst-solver.md`](./user/cst-solver.md) |
| 通用算法 | `mesh_grid/` | 三角 / 六边形晶格、`TopoPath` 路径 DSL（不依赖 CST） | [`user/tri-grid.md`](./user/tri-grid.md)、[`user/hex-grid.md`](./user/hex-grid.md) |
| 通用工具 | `tpc_toolkit/` | S 参数解析、遗传算法、等效介质公式 | 见 [`user/tpc-usage.md`](./user/tpc-usage.md) |
| **研究方向专用** | `topo_modeler/`、`topo_templates/` | **最大、最贴物理**：硅基拓扑光子晶体器件（域壁 / 相 / 阵列 / 馈源） | [`user/topo-quickstart.md`](./user/topo-quickstart.md)、[`user/topo-modeler.md`](./user/topo-modeler.md) |
| 服务 / 集成 | `tpc_service/`、`integrations/`、`cst_mcp` | 把上述能力包成服务 / MCP / 对外接口 | 见 [`user/tpc-usage.md`](./user/tpc-usage.md) |

**要点**：

- 越靠**底层**的包领域越小、口径越稳定 → 常用 API 直接照查对应 skill，不必翻源码；
- 越靠**上层 / 越专用**的包口径与物理约定越多 → 必须读对应专用 skill（topo 系）；
- **各 skill 只覆盖它声明的子包**：`cst-solver` 不管 topo 装配，`topo-quickstart` 也不重复讲 VBA 封装细节。

---

## 我该读哪个？30 秒判断

```
需求能用现有 API 组合出来吗？
├─ 能  → user/         （不要改库）
└─ 不能，要动 cst_solver / mesh_grid / topo_modeler / topo_templates / tpc_toolkit 的源码
        → developer/    （先读 WORKFLOW.md）
```

---

## AI 助手的自动加载入口

真正被 IDE / Copilot **自动加载**的是 `.github/` 下的薄壳文件，它们只做转指；
DSH（DeepSeek Harness）扫描的是 `.dsh/skills/`，两者内容一致、都指向本目录：

| 自动加载入口 | 指向 |
|---|---|
| [`../.github/copilot-instructions.md`](../.github/copilot-instructions.md) | 本目录索引 + 硬约定摘要 |
| [`../.github/skills/cst-solver/SKILL.md`](../.github/skills/cst-solver/SKILL.md) | [`user/cst-solver.md`](./user/cst-solver.md) |
| [`../.github/skills/cst-solver-dev/SKILL.md`](../.github/skills/cst-solver-dev/SKILL.md) | [`developer/cst-solver-dev.md`](./developer/cst-solver-dev.md) |
| [`../.github/skills/tpc-user/SKILL.md`](../.github/skills/tpc-user/SKILL.md) | [`user/tpc-usage.md`](./user/tpc-usage.md) |
| [`../.github/skills/topo-quickstart/SKILL.md`](../.github/skills/topo-quickstart/SKILL.md) | [`user/topo-quickstart.md`](./user/topo-quickstart.md) |
| [`../.dsh/skills/cst-solver/SKILL.md`](../.dsh/skills/cst-solver/SKILL.md) | [`user/cst-solver.md`](./user/cst-solver.md)（DSH 自动发现入口） |
| [`../.dsh/skills/topo-quickstart/SKILL.md`](../.dsh/skills/topo-quickstart/SKILL.md) | [`user/topo-quickstart.md`](./user/topo-quickstart.md)（DSH 自动发现入口） |

**唯一事实来源是本目录**。改技能内容改这里，`.github/` 与 `.dsh/` 下的薄壳不用动
（但**新增 skill 时要同时补这两个薄壳**，否则 IDE / DSH 发现不到）。

## 共用约定入口

- 环境配置、诊断、Python/MCP 当前能力与中文绘图：见 [使用者主手册](./user/tpc-usage.md)。
- 统一未完成计划维护、两类 skill 同步与字体实现约定：见 [开发者工作流](./developer/WORKFLOW.md)。
- Matplotlib 中文图必须使用 `mesh_grid.plotting` 的字体检测入口；不能靠硬编码字体名或屏蔽警告。
