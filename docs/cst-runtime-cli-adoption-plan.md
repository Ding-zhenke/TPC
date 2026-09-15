# 借鉴 cst-runtime-cli 实施计划清单

> 创建：2026-09-15 · 状态：**计划，未实施**（批次归属见下）
> 来源：[bbl21/cst-runtime-cli](https://github.com/bbl21/cst-runtime-cli)（MIT）
> 依据：`next_plan/README.md`（**唯一计划入口与阶段权威**）+ `gateway.py` 源码实读
> 路线：**C（借设计）+ D（挖资料）**
>
> ## ⚠️ 批次归属已并入现行阶段（2026-09-15 整理）
>
> 本文件的「批次 0–5」**不再是独立计划单元**，已按内容并入
> [`next_plan/README.md`](./next_plan/README.md) 的阶段体系：
>
> | 本文件批次 | 现行归属 |
> |---|---|
> | 批次 0 可行性验证 | **阶段 4**（部分已完成，见 `stages/04_…` §2.4） |
> | 批次 1 守卫层 | **阶段 5** §5.1 |
> | 批次 2 补守卫 | **阶段 5** §5.2 |
> | 批次 3 资料落地 | **阶段 5** §5.3 |
> | 批次 4 阶段 5 计划（审计/报告） | **阶段 7** §3.2 / §3.3 |
> | 批次 5 几何验收 | **阶段 4**（即 `stages/04_…` 全文） |
>
> 本文件保留**设计论证与源码实读结论**（陷阱目录、守卫设计差异、不能照搬的部分），
> 这些内容仍然有效，是阶段 5 的设计输入。

---

## 0. 先说一个必须澄清的差异（决定你的修复方式）

我原本假设「`para()` 后调 `full_history_rebuild()` 就能生效」。**读了它的 `gateway.py` 后，这个假设需要重新验证。**

它的 T2 守卫这样描述：

```python
# gateway.py :: guard_before_simulation
"Parameters changed (...) but model NOT rebuilt from disk. "
"Simulation would use cached old geometry."

next_action = ("cst-session-close --save true, 然后 cst-session-open "
               "to force model rebuild from disk")

_explain: "CST saves parameter table changes immediately but "
          "geometry rebuild only happens on project open"
```

**它的心智模型是：几何重建发生在「工程重新打开」时，而不是 `Rebuild()` 调用时。**

而你的 `parameters.py` 走的是：

```python
def para(self, name, value, log_flag=0, ...):
    self.cst_file.model3d.StoreParameter(f"{name}", value)
    if log_flag == 1:
        self.cst_file.model3d.full_history_rebuild()   # ← 你是这条路
```

你的 `copilot-instructions.md` 硬约定 §3 也写「验收必须…跑 `Rebuild()`」。

### 这两条路是否等价，必须实测

| 若 `StoreParameter + full_history_rebuild()` **有效** | 若**无效** |
|---|---|
| 修复 = `run()` 前自动调 `update()`（轻量，1 行） | 修复 = `run()` 前必须 close+reopen（重，改流程） |
| 守卫只需拦截 | 守卫还需提供"关闭重开"的补救动作 |
| `log_flag=1` 是正确写法 | `log_flag=1` **也是错的** —— 全仓 26 处需重审 |

> ⚠️ **这是整个计划的第 0 步。** 在验证清楚之前，任何守卫设计都可能建在错的前提上。
> 验证方法见 §3 批次 0。

---

## 1. Path D — 可直接拿的资料（见效最快）

### 1.1 `devkit/references/` 四个文件（实测大小）

| 文件 | 大小 | 对你的用途 |
|---|---|---|
| `vba-official-reference.md` | **71 KB** | VBA API 参考 —— 你一直在手工翻 `CST\Online Help\`，这份已整理 |
| `cst-official-api-reference.md` | **56 KB** | CST Python API 参考（`cst.interface` / `cst.results`） |
| `tool-development-guide.md` | 15 KB | 工具开发流程（含新增 VBA 对象的方法论） |
| `Test_kit_README.md` | 4.7 KB | 测试体系设计（分层、合约测试、缓存机制） |

**获取方式**（任选）：

```powershell
# 方式 1：只取这 4 个文件，不用全量 clone
$base = "https://raw.githubusercontent.com/bbl21/cst-runtime-cli/master/devkit/references"
$dst  = "D:\tmp\cst-runtime-refs"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
foreach ($f in @("vba-official-reference.md","cst-official-api-reference.md",
                 "tool-development-guide.md","Test_kit_README.md")) {
    Invoke-WebRequest "$base/$f" -OutFile "$dst\$f"
}
```

### 1.2 顺带可挖的（次要）

| 位置 | 内容 | 价值 |
|---|---|---|
| `devkit/tools/vba_defs/` | 10 个 TOML 参考实现（代码生成器输入） | 你已从 py4cst-ccly 借鉴过 TOML 模式，可对比 |
| `skills/cst-runtime-cli/references/` | `setup_guide.md`、任务卡模板、管道指南、**材料库** | 材料库可能有用 |
| `skills/cst-runtime-cli/tests/test_gateway.py` | T2/T3/T4/T5/T8/T10/T12/T13/T14 的测试用例 | **陷阱的"标准答案"** —— 比读 gateway.py 更直观 |

> 💡 `test_gateway.py` 值得优先看：它用可执行的断言定义了什么算踩坑，可**直接改写成你库的测试**。

### 1.3 落地位置建议

```
TPC/
└── docs/
    └── references/                    # 新建
        ├── vba-official-reference.md       # 原样存放
        ├── cst-official-api-reference.md   # 原样存放
        └── THIRD_PARTY_NOTICES.md          # ★ 必须：MIT 许可 + 来源声明
```

⚠️ **许可合规**：这两份是对方的文档产物，直接纳入仓库需在 `THIRD_PARTY_NOTICES.md` 保留
MIT 许可原文与来源链接。若只想自用，放仓库外也可。

---

## 2. Path C — 设计借鉴

### C1. 完整陷阱目录（源码实读，比 README 多 5 条）

从 `gateway.py` 提取的全部守卫，**标注你的现状**：

| 编号 | 陷阱 | 它的处理 | 你的状态 |
|---|---|---|---|
| **T2** | 改参后未重建就仿真 | 🔴 **硬拦截** + `next_action` | 🔴 **已确认存在**（`modeler.set_parameter().run()`） |
| T3 | 远场导出后 save 损坏工程 | 强制 `save=False` | ❓ 未查 —— 看 `postprocessing/farfield.py` |
| T4 | S11 复数当 dB 用 | `20*log10(max(hypot(re,im),1e-30))` | ⏭️ 你说熟，跳过 |
| T5 | modeler/results session 混用 | 拒绝跨 session | ✅ 你已分离（`setup`/`Result`） |
| T8 | `Abs(E)` 当增益证据 | 白名单 `{Realized Gain, Gain, Directivity}` | 🟡 **可加** —— 你的 `farfield_plot_polar(mode=...)` 无校验 |
| T9 | 重复打开同一 session | 警告 | 🟡 **可加** —— `new_project()` 无检查 |
| T10 | `project_path` 非法 | 校验后缀 `.cst`/`.prj` | 🟡 **可加** —— `open_project()` 无后缀校验 |
| T12 | session 类型跟踪 | 记录 modeler/results | 🟢 低 |
| **T13** | 只改参数表不重建 | **警告**（非拦截） | 🔴 同 T2（根因） |
| **T14** | `get_tree_items` filter 只支持 `0D/1D`、`colormap` | 拒绝非法 filter | 🟡 **可加** —— 你的 `_result_core.get_tree_items()` 无参数，但扩展时须知 |
| T15 | save 与 close 顺序 | 先 `project.save()` 再 close | 🟡 **可加** —— `project.py` 的 `close()` 无此保证 |

**你已有的（靠文档覆盖，非运行时强制）**：T9–T12 的一部分已在
`copilot-instructions.md` 硬约定里（绕向、布尔语义、路径、`modeler` 废弃）。

> 🎯 **核心洞察**：你的覆盖度不低，但全是**文档约定**。守卫层的价值是把
> "读文档才知道" → "写错就提示"。

### C2. 守卫层实现 —— 关键设计差异

它的架构（`gateway.py`，约 300 行）：

```python
_registry: dict[str, ProjectState] = {}     # 模块级状态注册表

@dataclass
class ProjectState:
    path: str
    session_type: str = "unknown"   # modeler | results
    stage: str = "clean"            # clean | params_dirty | farfield_exported | closed
    params_changed: list[str] = None
```

三个值得学的机制：

1. **双层状态持久化** —— 内存 registry **+ 落盘 marker 文件**：

   ```python
   def _dirty_marker_path(project_path):
       cst_path = Path(_normalize(project_path))
       return cst_path.parent / cst_path.stem / ".cst_params_dirty"
   ```

   Disk marker 解决**跨进程**问题（CLI 每次调用是新进程）。
   **你的库是长驻对象，内存状态就够 —— 这个机制可以省略。**

2. **分级严重度** —— T2 **拦截**，T13 **警告**。同根因，不同处置点：
   - T13 在**改参时**警告（提醒"还没重建"）
   - T2 在**仿真前**拦截（阻止用旧几何）

3. **结构化错误** —— 每个 `error_response` 必带三件套：

   ```python
   error_response(
       "params_not_rebuilt",          # code
       "...",                         # message
       trap="T2_params_not_rebuilt",
       cst_raw={...},                 # COM 状态快照
       next_action="cst-session-close --save true, 然后 reopen",
       # _explain: 为什么会踩坑
   )
   ```

#### ⚠️ 你不能照搬的部分

它的状态机围绕 **CLI 的 session 生命周期**（open/close/DE 进程管理）设计。
你的库是**一个长驻 `setup` 对象**，生命周期完全不同。

**能搬**：陷阱目录、严重度分级、错误三件套、`next_action` 理念
**不能搬**：`session_type` 状态机、disk marker、DE 进程管理

#### 你的最小设计草案（待批次 0 验证后定稿）

新增 `cst_solver/_guards.py`（**纯新增，不碰现有 Mixin**）：

```python
# -*- coding: utf-8 -*-
"""
CST 运行时守卫 —— 拦截已知陷阱
===============================
@author: PC
"""

class CstTrapError(RuntimeError):
    def __init__(self, trap, message, next_action=""):
        super().__init__(message)
        self.trap = trap
        self.next_action = next_action


class SolverGuard:
    """
    :param mode: 'off' | 'warn' | 'strict'
    """

    def __init__(self, mode='warn'):
        self.mode = mode
        self._dirty = set()      # 改过但未重建的参数名

    def mark_dirty(self, name):      self._dirty.add(name)
    def mark_clean(self):            self._dirty.clear()

    def check_before_run(self):
        """T2"""
        if not self._dirty:
            return
        msg = (f"[T2] 参数 {sorted(self._dirty)} 已改但模型未重建，"
               f"将用旧几何仿真。")
        action = "app.update() 后重跑；或 para(..., log_flag=1)"
        if self.mode == 'strict':
            raise CstTrapError("T2_params_not_rebuilt", msg, action)
        if self.mode == 'warn':
            print(f"⚠ {msg}\n   → {action}")
```

接线（三处各 1–3 行，**追加不修改**）：

```python
# parameters.py :: para() 末尾
        self._guard.mark_dirty(name)

# solver.py :: update() 末尾
        self._guard.mark_clean()

# solver.py :: run() 开头
        self._guard.check_before_run()
```

惰性初始化，保证单独 import Mixin 不炸：

```python
@property
def _guard(self):
    if not hasattr(self, '_cst_guard'):
        from cst_solver._guards import SolverGuard
        self._cst_guard = SolverGuard(mode='warn')
    return self._cst_guard
```

### C3. 错误契约（`{status, message, ...}`）

**⚠️ 不要全库改造** —— 会破坏 207 个方法的现有签名，违反铁律 §3。

**建议**：只在**新增**的验收方法上用。这也正好补上你 `copilot-instructions.md`
硬约定 §3 的缺口 —— 那句"验收必须读 `get_messages()` 并跑 `Rebuild()`"
目前**只是口头约定，无 API 支撑**：

```python
def validate_model(self):
    """
    验收：读 CST 消息 + 跑 Rebuild，返回结构化结果。

    :return: dict, {"status": "success"|"error",
                    "messages": [...], "rebuild_ok": bool}
    """
```

### C4. 审计落盘

它的做法：`stages/` + `logs/tool_calls.jsonl` + `logs/production_chain.md`，
且 `--args-file` 会自动存档副本到 `stages/`。

**归属：阶段 5**（`next_plan/02` 未覆盖此议题，建议新增）。见 §3 批次 3。

### C5. 报告引擎

内联 HTML/SVG/WebGL，零 JS/CDN 依赖；支持 S11 多迹叠加、3D 远场、2D 热力图、迭代时间线。

**归属：阶段 5**（与 `modeler.plot_results()` 合并 —— 当前抛 `NotImplementedError`）。
见 §3 批次 4。

---

## 3. 实施清单（勾选式 · 按依赖排序）

### 批次 0 — 可行性验证（🔴 先做，决定后续设计）

- [ ] **0.1** 建最小 CST 工程：一个 `Brick`，尺寸引用参数 `a`
- [ ] **0.2** 设 `a=10`，建模，读几何体积 → 记为 `V1`
- [ ] **0.3** `app.para('a', 20, log_flag=0)` → 读体积 → 记为 `V2`（预期仍是 `V1`）
- [ ] **0.4** `app.update()`（即 `full_history_rebuild()`）→ 读体积 → `V3`
- [ ] **0.5** **判定**：
  - 若 `V3 != V1` → ✅ `Rebuild()` **有效** → 守卫走"拦截 + 提示 `update()`"
  - 若 `V3 == V1` → ❌ `Rebuild()` **无效** → 守卫须走"close + reopen"，且 `log_flag=1` 全仓 26 处需重审
- [ ] **0.6** 把结论写进 `docs/next_plan/`（这属于事实发现，须留痕）

> 预估：1–2 h（含建工程）。**这一步的结论决定 C2 的全部设计。**

### 批次 1 — 守卫层（阶段 0–2 ✅ 可实施）

- [ ] **1.1** 新增 `cst_solver/_guards.py`（纯新增，零风险）
- [ ] **1.2** `topo_modeler/modeler.py` 接线（**方案 A：零侵入 cst_solver**）
- [ ] **1.3** 回归：跑 `templates/straight_waveguide.py` + `unit_antenna.py`，确认**不误报**
      （它们的 `para` 在建模前，应判 clean）
- [ ] **1.4** **构造反例**：`modeler.set_parameter('g', 25).run()` → 必须报警
- [ ] **1.5** 若 1.3 通过 → 扩到**方案 B**：`cst_solver` 三处追加（`para`/`update`/`run`）
- [ ] **1.6** `mode='off'` 时行为与改动前**逐字节一致**（回归基线）
- [ ] **1.7** 同步 `setup.pyi` + 重跑 `python scripts/gen_cst_solver_docs.py`（铁律 §2）

> ⚠️ 铁律 §1：改动跨 `cst_solver` 与 `topo_modeler` 两包 → **拆两条 commit**。
> 预估：4–6 h

### 批次 2 — 补守卫（阶段 0–2 ✅ 可实施）

- [ ] **2.1** **T8**：`postprocessing/farfield.py` 的 `farfield_plot_polar(mode=...)`
      加白名单校验 `{Realized Gain, Gain, Directivity}`
- [ ] **2.2** **T3 普查**：读 `postprocessing/farfield.py`，确认远场导出后是否会触发 `save()`
- [ ] **2.3** **T7' 普查**：`log_flag=0` 只返文本不下发 —— 用户误当已执行的风险
      （这是你**特有**的坑，对方没有）
- [ ] **2.4** **T10**：`project.py` 的 `open_project()` 加后缀校验
- [ ] **2.5** **T15**：`project.py` 的 `close()` 保证 save-before-close 顺序
- [ ] **2.6** 新增 `cst_solver.validate_model()` —— 结构化验收 API（契约试点）
- [ ] **2.7** 新增 `cst_solver/tests/test_guards.py` —— **改写自它的 `test_gateway.py`**

> 预估：4–6 h

### 批次 3 — 资料落地（Path D，独立于代码）

- [ ] **3.1** 下载 4 个 reference 文件（见 §1.1 脚本）
- [ ] **3.2** 存放 `docs/references/`
- [ ] **3.3** 写 `docs/references/THIRD_PARTY_NOTICES.md`（MIT 许可 + 来源）
- [ ] **3.4** 在 `.github/copilot-instructions.md` 增一行指向新参考（替代"翻 CST Help"的说明）
- [ ] **3.5** 抽查：用 `vba-official-reference.md` 核对 `cst_solver` 里 3–5 个 VBA 命令拼写

> 预估：1–2 h。**可与批次 1/2 并行，收益立即**

### 批次 4 — 阶段 5 计划（📝 只写计划，不写实现）

- [ ] **4.1** 把 C4 审计落盘写成阶段 5 条目，并入 `06_整合实施计划`
- [ ] **4.2** 把 C5 报告引擎写成阶段 5 条目（与 `modeler.plot_results()` 合并）
- [ ] **4.3** 更新 `next_plan/README.md` 的阶段状态表
- [ ] **4.4** （可选）把 DOE/ask-tell 抽象写成阶段 5 备选条目

> 预估：2–3 h，纯文档

### 批次 5 — 优先级提醒（非借鉴项，但你 README 里的阻塞项）

> `next_plan/stages/04_阶段4_验收与缺陷清账.md`：阶段 2/3 的**几何验收从未完整执行**
> （尺寸偏差 <0.1%、谐振峰 <1GHz、主瓣 <5°）

- [ ] **5.1** 判断：批次 0 若证明"数据可能是脏的"，验收优先级应**高于**所有借鉴项

---

## 4. 关键风险

| 风险 | 等级 | 缓解 |
|---|---|---|
| **批次 0 未做就动手** | 🔴 高 | 结论决定设计，必须先验 |
| 守卫误报打断既有流程 | 🟡 中 | 默认 `warn`；`off` 可完全关闭；1.3 回归 |
| 改动破坏向后兼容 | 🟡 中 | 只追加不修改；`setup.pyi` 同步（铁律 §3） |
| 两库混用导致混乱 | 🟡 中 | 只借思路，不引入依赖 |
| 许可合规 | 🟢 低 | MIT；`THIRD_PARTY_NOTICES.md` |

---

## 5. 明确不做

- ❌ 依赖它（CLI 形态、Python 3.13+、90% 重叠）
- ❌ 抄它的 113 个命令
- ❌ 抄它的 CLI 形态 / `bootstrap.py` 部署链
- ❌ 全库改造返回契约（破坏 207 个签名）
- ❌ 搬它的 disk marker / session 状态机（生命周期不同）
- ❌ 跑 LobeHub 市场页的 `mcp rate/comment`（对外公开发布，未授权）

---

## 6. 一页速览

```text
批次 0  ← 🔴 先做！验证 full_history_rebuild() 是否真生效
   │        └─ 决定批次 1 的设计走"轻量拦截"还是"close+reopen"
   ▼
批次 1  ← 守卫层（阶段 0–2，可实施）      4–6 h
批次 2  ← 补 T3/T7'/T8/T10/T15（可实施）   4–6 h
批次 3  ← Path D 资料落地（可并行）        1–2 h  ★ 见效最快
批次 4  ← 阶段 5 计划（只写文档）          2–3 h
批次 5  ← 几何验收（可能优先级最高）
```
