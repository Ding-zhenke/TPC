# TPC 文档索引

> 本目录是 TPC 的**全部文档**。先看下面这张「我想干什么 → 读哪份」的表。

---

## 我想干什么 → 读哪份

| 我的目的 | 读哪份 |
|---|---|
| **第一次接触这个项目**，想知道有哪些包、各干什么 | [`ARCHITECTURE.md`](./ARCHITECTURE.md) ← **从这里开始** |
| 深入看某个包的设计与 API | [`packages/`](./packages/) 下对应的一份 |
| **用库建模型**（写 notebook、排错、验收） | [`../skills/user/tpc-usage.md`](../skills/user/tpc-usage.md) |
| 用三角晶格/路径 DSL | [`../skills/user/tri-grid.md`](../skills/user/tri-grid.md)、[`guides/topo_modeler_guide_stage0-3.md`](./guides/topo_modeler_guide_stage0-3.md) |
| 用六边形晶格 / DXF 导出 | [`../skills/user/hex-grid.md`](../skills/user/hex-grid.md)、[`guides/hex_grid_guide.md`](./guides/hex_grid_guide.md) |
| **维护/扩展库本身**（改代码） | [`../skills/developer/WORKFLOW.md`](../skills/developer/WORKFLOW.md) ← 开发宪法 |
| 查方法签名（自动生成的 HTML） | [`guides/api/`](./guides/api/) |
| 知道后面要做什么、做到哪了 | [`next_plan/README.md`](./next_plan/README.md) |

---

## 目录结构

```
docs/
├── README.md                         ← 本文件：文档索引
├── ARCHITECTURE.md                   总体架构：每个包负责什么功能
│
├── packages/                         每个包一份说明（不同用途的包分开写）
│   ├── cst_solver.md                 CST 会话封装层
│   ├── mesh_grid.md                  晶格/网格算法层
│   ├── topo_modeler.md               建模引擎层
│   ├── templates.md                  端到端模板层
│   └── tpc_toolkit.md                独立工具层
│
├── guides/                           面向「怎么用」的指南
│   ├── index.md                      指南索引
│   ├── topo_modeler_guide_stage0-3.md 建模引擎使用指南（阶段 0–3）
│   ├── hex_grid_guide.md             六边形网格算法库使用文档
│   └── api/                          自动生成的 API HTML
│       ├── cst_solver_api.html
│       ├── hex_grid_api.html
│       └── tri_grid_api.html
│
└── next_plan/                        改善计划（阶段实施计划 + TODO 清单）
    └── README.md                     计划索引与阶段状态
```

---

## 三个层次的文档，别混用

| 层次 | 位置 | 回答什么问题 | 读者 |
|---|---|---|---|
| **架构** | `ARCHITECTURE.md` + `packages/` | 「这个包为什么存在、负责什么、跟谁有依赖」 | 想理解全局的人 / AI |
| **指南** | `guides/` | 「这个 API 怎么调、参数怎么填」 | 使用者 |
| **技能** | `../skills/` | 「我该怎么干活」——使用者规程 vs 开发者规程 | 人 + AI 助手 |
| **计划** | `next_plan/` | 「还没做什么、下一步做什么」 | 开发者 |

---

## 文档生成

API HTML 由脚本扫描 docstring 生成，**不要手改 HTML**：

```bash
python scripts/gen_cst_solver_docs.py   # → docs/guides/api/cst_solver_api.html
python scripts/gen_mesh_docs.py         # → docs/guides/api/{hex,tri}_grid_api.html
```

改了公开 API 之后必须重跑，否则 HTML 与代码脱节。详见
[`../skills/developer/doc-generation.md`](../skills/developer/doc-generation.md)。
