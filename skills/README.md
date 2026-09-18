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
| [`../.github/skills/cst-solver-dev/SKILL.md`](../.github/skills/cst-solver-dev/SKILL.md) | [`developer/cst-solver-dev.md`](./developer/cst-solver-dev.md) |
| [`../.github/skills/tpc-user/SKILL.md`](../.github/skills/tpc-user/SKILL.md) | [`user/tpc-usage.md`](./user/tpc-usage.md) |
| [`../.github/skills/topo-quickstart/SKILL.md`](../.github/skills/topo-quickstart/SKILL.md) | [`user/topo-quickstart.md`](./user/topo-quickstart.md) |
| [`../.dsh/skills/topo-quickstart/SKILL.md`](../.dsh/skills/topo-quickstart/SKILL.md) | [`user/topo-quickstart.md`](./user/topo-quickstart.md)（DSH 自动发现入口） |

**唯一事实来源是本目录**。改技能内容改这里，`.github/` 与 `.dsh/` 下的薄壳不用动
（但**新增 skill 时要同时补这两个薄壳**，否则 IDE / DSH 发现不到）。

## 共用约定入口

- 环境配置、诊断、Python/MCP 当前能力与中文绘图：见 [使用者主手册](./user/tpc-usage.md)。
- 统一未完成计划维护、两类 skill 同步与字体实现约定：见 [开发者工作流](./developer/WORKFLOW.md)。
- Matplotlib 中文图必须使用 `mesh_grid.plotting` 的字体检测入口；不能靠硬编码字体名或屏蔽警告。
