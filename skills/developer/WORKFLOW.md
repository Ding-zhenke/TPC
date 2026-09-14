# TPC 开发者工作流（WORKFLOW）

> **这是仓库的开发宪法。** 任何人（含 AI 助手）日后修改 TPC，都必须按本文件的流程走。
> 使用者视角（只是用库建模型）请看 [`../user/tpc-usage.md`](../user/tpc-usage.md)。
> 最后更新：见 git log。

---

## 0. 三十秒摘要

```
看清需求 → 判定归属包 → 读该包技能 → 改代码 → 同步存根/文档 → 跑测试 → 逐包提交 → push
```

三条铁律：

1. **一次只改一个包**，并为这个包单独写一条 commit。
2. **改代码必须同步文档**，同步矩阵见 §6，漏了文档视为未完成。
3. **验收靠 `get_messages()`**，CST 不抛异常，跑通不等于对。

---

## 1. 角色与视角分离

| 视角 | 关心什么 | 入口文档 |
|---|---|---|
| **使用者** | 怎么用现成的 API 把模型建出来、报错怎么查、结果怎么验收 | [`../user/`](../user/) |
| **开发者** | 怎么给库加能力、怎么修封装层缺陷、怎么保证不破坏既有约定 | 本文件 + [`cst-solver-dev.md`](./cst-solver-dev.md) |

**判断方法**：如果需求能用现有 API 组合出来 → 使用者任务，**不要**改库；
如果需求要求新增/修改 `cst_solver`、`mesh_grid`、`topo_modeler`、`templates`、`tpc_toolkit` 里的代码 → 开发者任务。

---

## 2. 改动归属：这条需求该进哪个包？

先判定归属，**再**动手。放错包是后面所有麻烦的根源。

| 需求性质 | 归属 | 判定依据 |
|---|---|---|
| CST 原语操作（画体、设端口、跑求解、读结果） | `cst_solver/` | 需要跟 CST 的 VBA 对象一一对应 |
| 与 CST 无关的晶格数学、坐标、可视化、DXF | `mesh_grid/` | 不需要 CST 也能跑 |
| 把部件组装成模型、编排建模顺序 | `topo_modeler/` | 依赖 `cst_solver` + `mesh_grid` |
| 某个具体器件的完整建模流程 | `templates/` | 一个类 = 一个器件 |
| 仿真前后数据处理、优化算法 | `tpc_toolkit/` | 不需要 CST |
| 仓库工具（文档生成、统计脚本） | `scripts/` | 不进入发行包 |
| 文档 / 技能 / 计划 | `docs/`、`skills/` | 不影响运行时 |

**反例（不要这样做）**：
- ❌ 在 `topo_modeler/builders/` 里手写 VBA 字符串 → 应该调 `cst_solver` 的方法。
  唯一例外：`cst_solver` 确实没有对应封装，且该 VBA 只服务这一个部件 —— 此时**先给 `cst_solver` 补封装**，再回来用。
- ❌ 在 `templates/` 里写几何推导 → 应该下沉到 `topo_modeler/builders/` 或 `TopoPath`。
- ❌ 把只服务某个模板的逻辑塞进 `mesh_grid/` → `mesh_grid` 必须保持通用。

---

## 3. 标准工作流

### 步骤 0 — 接需求，先判定阶段

读 [`../../docs/next_plan/`](../../docs/next_plan/)，确认这个需求属于哪个阶段：

- 属于**已完成阶段**（阶段 0–3）→ 发现问题**直接改代码**，并同步修计划文档里的描述。
- 属于**未开始阶段**（阶段 4+）→ **只完善计划**，不写实现代码。

### 步骤 1 — 读对应的技能文档

| 改动范围 | 必读 |
|---|---|
| `cst_solver/` | [`cst-solver-dev.md`](./cst-solver-dev.md)（含「待修清单」与硬约定） |
| `mesh_grid/` | [`../user/tri-grid.md`](../user/tri-grid.md)、[`../user/hex-grid.md`](../user/hex-grid.md) |
| `topo_modeler/` | [`../user/topo-modeler.md`](../user/topo-modeler.md) + 本文件 §4 |
| 命名/存根/文档 | [`conventions.md`](./conventions.md)、[`doc-generation.md`](./doc-generation.md) |
| 整体架构 | [`../../docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) |

**不要通读整包源码**。按需求定位到具体文件再读。

### 步骤 2 — 查权威来源

- **CST VBA 命令与参数**：CST 安装目录下的帮助文档
  `C:\SOFTWARE\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D\`
  （路径以 `cst_solver/config.py` 里的 `CST_INSTALL_PATH` 为准）。
- **晶格/坐标公式**：以 `mesh_grid/tri_grid/core.py` 的 `path_loc_to_xy` 为唯一基准，
  任何新公式必须与它一致（`topo_path.py` 已有单测覆盖）。
- **物理参数取值**：见 §7。

### 步骤 3 — 设计变更（写代码前）

必须明确回答：

1. **公开 API 的签名**是什么？（参数名、类型、默认值、返回值）
2. **是否需要旧名别名**？（见 §5 命名规则）
3. **是否新增文件/包**？如果是，是否需要更新 `__init__.py` 的 `__all__` 和 `pyproject.toml`？
4. **失败时怎么暴露**？CST 不抛异常，要有 `get_messages()` 检查或显式返回状态。
5. **验收判据**是什么？（能跑通 + `get_messages()` 为空 + 几何量正确）

### 步骤 4 — 写代码

硬性要求：

- **Google/Numpy 风格中文 docstring**，含 `参数 / 返回值 / 说明`。
  CST 里的长度、角度都是**表达式字符串**，类型标注写 `float | str`。
- 4 空格缩进；文件头 `# -*- coding: utf-8 -*-`。
- 复合构件的多条 VBA 必须用 `log_flag=0` 拼接后**一次**下发，保持历史树干净。
- 禁止把 `print` 当错误通道；用异常或返回值。

### 步骤 5 — 同步类型存根

改了 `setup` 的公开方法 → **必须**同步 `cst_solver/setup.pyi`
（`simulation/` 相关还要看 `cst_solver/simulation/setup.pyi`）。
Pylance 的补全完全依赖存根，漏改等于 API 对 IDE 不可见。

### 步骤 6 — 同步文档（§6 的矩阵）

### 步骤 7 — 验证

```bash
# 单元测试（三角路径 DSL 已有完整单测）
python -m pytest -q

# 文档生成器必须还能跑通
python scripts/gen_cst_solver_docs.py
python scripts/gen_mesh_docs.py
```

**涉及 CST 的改动**：跑冒烟测试（不污染正式工程）：

```python
from cst_solver import setup

app = setup(r'<某个 tmp.cst 的绝对路径>')        # 用临时模板
app.square(0, 1, 0, 1, 0, 1, 'smoke', 'component1', 'Silicon (lossy)')
print(app.cst_file.get_messages())                # 必须为空
app.cst_file.model3d.Rebuild()                    # 阻塞式重放历史，最能暴露问题
print(app.cst_file.get_messages())                # 必须为空
app.close()
```

`Rebuild()` 是最关键的验收动作：历史树能否无错重放，决定了模型是否真的可复现。

### 步骤 8 — 提交（一个包一条 commit）

```bash
git add <这个包涉及的文件>
git commit -m "<type>(<scope>): <一句话说清做了什么>" -m "<详细说明：为什么改、改了哪些文件、怎么验证的、有没有破坏兼容>"
git push origin main
```

规范见 §8。

---

## 4. 各包的验收清单

### `cst_solver/`
- [ ] 新方法有 `snake_case` 名 + 旧名别名
- [ ] docstring 完整（参数/返回值/说明），长度角度标注 `float | str`
- [ ] 已同步 `setup.pyi`
- [ ] 冒烟测试 `get_messages()` 为空，`Rebuild()` 后仍为空
- [ ] 已重新生成 `docs/guides/api/cst_solver_api.html`

### `mesh_grid/`
- [ ] 新公式与 `path_loc_to_xy` 一致
- [ ] `__init__.py` 的 `__all__` 已更新
- [ ] `python -m pytest mesh_grid -q` 通过
- [ ] 已重新生成 `docs/guides/api/{hex,tri}_grid_api.html`

### `topo_modeler/`
- [ ] builder 是**无状态纯函数**，可脱离 `TopoModeler` 单独调用
- [ ] 已在 `builders/__init__.py` 导出并加入 `__all__`
- [ ] 多边形**绕向 CCW**（见 §5 硬约定 1）
- [ ] 阵列范围覆盖整个基板
- [ ] 至少用一个模板（`templates/`）或最小脚本端到端跑通

### `templates/`
- [ ] 参数有合理默认值，构造后 `preview()` 能画路径
- [ ] `build_all()` 端到端无 `get_messages()` 报错
- [ ] 与 `TopoModeler` 的自动推断结果一致（或显式覆盖）

### `tpc_toolkit/`
- [ ] 不引入 CST 依赖
- [ ] 输入输出的数组形状/dtype 写进 docstring
- [ ] 有最小可运行示例

---

## 5. 命名与兼容规则

1. **新 API 一律 snake_case**；CST/VBA 风格旧名保留为别名。
   例：`create_brick`（新）/ `square`（旧）、`subtract`（新）/ `substract`（旧，拼写错误的历史名）。
2. **拼写错误必须修**，但**不允许静默破坏兼容**：
   - 加正确名 → 旧名指向正确名（别名）→ 文档标注「旧名，已弃用」→ 计划中登记移除版本。
   - ❌ 不允许直接把 `substract` 删掉改成 `subtract` 而不留别名。
3. **历史标签字符串**（`add_to_history` 的第一个参数）也属于拼写检查范围。
   注意：**已存在于旧工程历史树里的标签不能改**，否则对比历史会失配 —— 改之前先确认是否有存量工程依赖。
4. 删除任何公开符号前，先在 `docs/next_plan/` 登记弃用，并保留至少一个版本周期。

---

## 6. 文档同步矩阵（改完必须逐项对照）

| 你改了什么 | 必须同步 |
|---|---|
| `cst_solver` 公开方法签名 | `cst_solver/setup.pyi`、`docs/guides/api/cst_solver_api.html`（重跑生成器） |
| `mesh_grid` 公开 API | `mesh_grid/*/__init__.py`、`docs/guides/api/*.html` |
| 新增/删除包或模块 | `docs/ARCHITECTURE.md`、`docs/packages/*.md`、`pyproject.toml` 的 `packages.find`、`README.md` 的结构图 |
| 新增 builder / 模板 | `docs/packages/topo_modeler.md` 或 `docs/packages/templates.md` |
| 新增硬约定或踩坑 | `docs/ARCHITECTURE.md` §6 + 相关 skill |
| 阶段进度变化 | `docs/next_plan/README.md` 的阶段状态表 |
| 修掉一个已知缺陷 | 删掉 `cst-solver-dev.md` 的「待修清单」对应行 + `docs/next_plan/` 对应条目 |
| 新增/移动文件 | 全仓库搜一遍旧路径引用（见 §9） |

---

## 7. 固定物理参数（改之前先确认不是笔误）

| 参数 | 值 | 说明 |
|---|---|---|
| `a` | 0.2425 mm | 晶格常数 |
| `h` | 0.25 mm | 硅片厚度 |
| 大孔比例 | 0.65 | `l1 = 0.65 × a` |
| 小孔比例 | 0.35 | `l2 = 0.35 × a` |
| `e1` | `a/2` = 0.12125 mm | 三角晶格 x 方向半间距 |
| `e2` | `a√3/2` ≈ 0.2100 mm | 三角晶格 y 方向半间距 |
| 工作频段 | ~300 GHz | 太赫兹 |

---

## 8. 提交规范

**一个包一条 commit。** 格式：

```
<type>(<scope>): <简短祈使句，中文>

<正文：为什么改（问题现象）>
<正文：改了哪些文件，关键设计决策>
<正文：怎么验证的（命令 + 结果）>
<正文：兼容性影响（旧名是否保留、是否破坏既有调用）>
```

`type`：`feat` / `fix` / `refactor` / `docs` / `chore` / `build` / `test`
`scope`：`cst_solver` / `mesh_grid` / `topo_modeler` / `templates` / `tpc_toolkit` / `docs` / `repo` / `build`

示例：

```
fix(topo_modeler): 修正基板与 VPC 区域多边形绕向，消除与晶体差一个 h 的问题

现象：build_substrate / build_vpc_regions 生成的多边形为顺时针，
      ExtrudeCurve 沿法向拉伸后得到 −z 方向实体，与晶体在 z 上差一个 h，
      布尔求交返回空集且 CST 不报错。

改动：在 builders/substrate.py、builders/vpc_regions.py 拉伸前统一调用
      _ensure_ccw(pts)，不改任何公开签名。

验证：python -m pytest mesh_grid -q 通过；模板 StraightWaveguide.build_all()
      后 app.cst_file.get_messages() 为空，model3d.Rebuild() 后仍为空。

兼容性：无破坏；builders 函数签名未变。
```

**禁止**：`git commit -m "update"`、把多个包的改动塞进一条 commit、跳过 push。

---

## 9. 改完必做的交叉引用检查

移动/重命名文件后，旧路径引用是本仓库最常见的事故来源。至少检查：

```bash
# 旧路径是否还有残留引用
grep -rn "sys.path.append\|scripts/gen_docs.py\|\.github/skills\|cst_solver/docs\|mesh_grid/docs" \
     --include="*.py" --include="*.md" --include="*.toml" .
```

同时确认：

- [ ] 所有 `.md` 里的相对链接仍然有效
- [ ] 所有 Python 示例里的 `import` 路径仍然有效（本仓库已改用 `pip install -e .`，示例里不应再出现 `sys.path.append`）
- [ ] `pyproject.toml` 的包发现规则覆盖了新增的包

---

## 10. 禁止事项

1. ❌ 跨包大改塞进一条 commit。
2. ❌ 改了公开 API 不更新 `setup.pyi` / 文档。
3. ❌ 为了让自己的代码跑通而修改 `cst_solver/config.py` 的逻辑（它是逐机本地配置，已 gitignored）。
4. ❌ 在 `mesh_grid` 里引入 CST 依赖（它必须保持纯计算）。
5. ❌ 在 `tpc_toolkit` 里引入 CST 依赖。
6. ❌ 删除公开符号而不留别名、不登记弃用。
7. ❌ 把实验性代码直接写进 `templates/` 或 `topo_modeler/builders/` 的公开路径 —— 先放 `lens_build_standalone.py` 这类沙盒文件验证。
8. ❌ 用 `print` 代替异常。
9. ❌ 跳过 `docs/next_plan` 的阶段判定就开工。
