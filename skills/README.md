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
└─ 不能，要动 cst_solver / mesh_grid / topo_modeler / templates / tpc_toolkit 的源码
        → developer/    （先读 WORKFLOW.md）
```

---

## AI 助手的自动加载入口

真正被 IDE / Copilot **自动加载**的是 `.github/` 下的两个薄壳文件，它们只做转指：

| 自动加载入口 | 指向 |
|---|---|
| [`../.github/copilot-instructions.md`](../.github/copilot-instructions.md) | 本目录索引 + 硬约定摘要 |
| [`../.github/skills/cst-solver-dev/SKILL.md`](../.github/skills/cst-solver-dev/SKILL.md) | [`developer/cst-solver-dev.md`](./developer/cst-solver-dev.md) |
| [`../.github/skills/tpc-user/SKILL.md`](../.github/skills/tpc-user/SKILL.md) | [`user/tpc-usage.md`](./user/tpc-usage.md) |

**唯一事实来源是本目录**。改技能内容改这里，`.github/` 下的薄壳不用动。
