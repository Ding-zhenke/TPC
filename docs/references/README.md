# docs/references — 第三方参考资料（vendored）

本目录存放**从外部开源项目 vendored（原样收录）的第三方参考文档**，仅供离线查阅，**不是本仓库（TPC）自己的文档资产，也不被任何代码 import / 读取**。

- **来源**：上游项目 **cst-runtime-cli**，仓库内路径 `devkit/references/`
- **上游地址**：<https://github.com/bbl21/cst-runtime-cli>（HEAD `7eac8219`，2026-06-24）
- **Vendored 时间**：2026-09-15，逐字节复制，未重排格式、未改写行尾、未翻译
- **许可**：上游为 MIT License（`Copyright (c) 2026 bbl21`），**许可全文见 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)**；该文档同时列出 4 个文件的字节数与用途
- **收录文件**：`vba-official-reference.md`、`cst-official-api-reference.md`、`tool-development-guide.md`、`Test_kit_README.md`
- **只读原则**：这些文件视为只读参考资料，不要在本目录里做项目化改写；如需修改请改本仓库自己的文档
- ⚠️ 本目录内容是**离线快照**，上游更新不会自动同步；需要最新版本请回到上述上游地址获取

## 已知上游不一致：`devkit/tools/vba_defs/` 并不存在

上游自己的文档声称存在一个 `devkit/tools/vba_defs/` 目录，内含 **10 个 TOML 参考实现**。该说法出现在（已核对原文）：

- 上游 `README.md` L92：「TOML 定义参考：`devkit/tools/vba_defs/`（10 个参考实现）。」、L172 目录树注释「TOML 定义（10 个参考实现）」
- 上游 `devkit/README.md` L81：「`tools/vba_defs/` | TOML 定义模板 — 10 个参考实现」、L184「├── vba_defs/  ← 10 个 TOML 参考实现」
- 本目录的 `tool-development-guide.md` L38 也把 `tools/vba_defs/` 列为文档来源之一（但**没有**提「10 个」这个数字）

**该目录在上游仓库 HEAD 中并不存在** —— 这是**上游文档跑在代码前面**（文档描述了计划中/已移除的内容），**不是我们 clone 不完整**。

2026-09-15 由我本人用只读 git 命令核实，命令与**实际输出**如下：

```powershell
# 精确命令
git -C "D:\成电博士生涯\自动建模算法尝试\cst-runtime-cli" ls-files "devkit/tools/vba_defs/*"
# 实际输出：空 —— 0 行，命中数 = 0
# 退出码：0     ← 注意：0 命中时 git ls-files 仍返回 0，不要用退出码判断有无命中

# 交叉验证 1：全仓库任意路径含 vba_defs 的已跟踪文件
git -C "D:\成电博士生涯\自动建模算法尝试\cst-runtime-cli" ls-files "*vba_defs*"
# 实际输出：空 —— 命中数 = 0

# 交叉验证 2：devkit/tools/ 下实际被跟踪的文件（只有 1 个）
git -C "D:\成电博士生涯\自动建模算法尝试\cst-runtime-cli" ls-files "devkit/tools/*"
# 实际输出：devkit/tools/generate_tools.py

# 交叉验证 3：代码生成器所指向的另一个 vba_defs 位置
git -C "D:\成电博士生涯\自动建模算法尝试\cst-runtime-cli" ls-files "skills/cst-runtime-cli/tools/*"
# 实际输出：skills/cst-runtime-cli/tools/generate_tools.py    ← 同样没有 vba_defs/

# 交叉验证 4：仓库里到底有没有任何被跟踪的 .toml（除 2 个 pyproject.toml 外）
git -C "D:\成电博士生涯\自动建模算法尝试\cst-runtime-cli" ls-files "*.toml"
# 实际输出（仅 2 行）：
#   skills/cst-runtime-cli/references/pyproject.toml
#   skills/cst-runtime-cli/scripts/pyproject.toml

# 交叉验证 5：工作区磁盘上是否存在
Test-Path "D:\成电博士生涯\自动建模算法尝试\cst-runtime-cli\devkit\tools\vba_defs"
# 实际输出：False
Test-Path "D:\成电博士生涯\自动建模算法尝试\cst-runtime-cli\skills\cst-runtime-cli\tools\vba_defs"
# 实际输出：False
```

结论：**6 条独立检查全部为「不存在」**。同时 `git status --porcelain` 输出为空、仓库共 876 个已跟踪文件（`skills/` 867 个、`devkit/` 若干），说明 clone 是**完整且干净**的 —— 上游就是把 `vba_defs/` 写进了文档但没提交任何 `.toml`。因此 `tool-development-guide.md` / 上游 README 中关于 `vba_defs/` 的描述**不能当作可用的现有资产**，只能当作设计意图参考。上游两处 `generate_tools.py` 里确有 `DEFS_DIR = HERE / "vba_defs"` 的常量，即生成器本身在，但它的输入目录缺失。

## 如何查阅

下列均为可直接复制执行的命令（Windows PowerShell），在仓库根目录运行。

| 文件 | 查阅示例 | 说明 |
|------|----------|------|
| `vba-official-reference.md` | `Select-String -Path docs\references\vba-official-reference.md -Pattern 'NumberOfModes' -Context 3,12` | 按 VBA 对象名/属性名检索，然后读命中的语法表格（属性名/类型/枚举值）。本文件中 VBA 对象按 `## N. 对象名` 分节，如 `## 16. Port — 端口`。⚠️ 实测：检索 `WaveguidePort` **0 命中**（该文件里没有这个对象名，波端口对象叫 `Port`，用 `PortType = "WAVEGUIDE"` 区分），所以请检索 `Port` / `PortType` / `NumberOfModes` 这类真实存在的名字。 |
| `cst-official-api-reference.md` | `Select-String -Path docs\references\cst-official-api-reference.md -Pattern 'ProjectFile' -Context 3,15` | 查 Python API；例如查 `cst.results.ProjectFile`，读它的构造参数与离线读取示例，判断能否不启动 CST GUI 就读结果。 |
| `tool-development-guide.md` | `Select-String -Path docs\references\tool-development-guide.md -Pattern 'TOML' -Context 2,20` | 查「怎么新增一个工具」；直接跳到 `## 9. TOML 格式参考` 或 `## 3. Step 1`，照抄其 6 步流程。 |
| `Test_kit_README.md` | `Select-String -Path docs\references\Test_kit_README.md -Pattern '单元测试' -Context 2,15` | 查测试分层；读「分层总览」表判断某类验证需不需要真实 CST，再读对应测试矩阵。 |

## VBA 拼写抽查记录

2026-09-15 对 `cst_solver` 包中已有 VBA 片段与本目录 vendored 的 `vba-official-reference.md` 做了抽查（只读，未修改任何 `cst_solver\` 文件）：

> 注意：抽查时 `cst_solver\` 正被另一进程并发修改（`git status` 显示 `solver.py` 等处于已修改状态），因此表中的**行号仅供参考、可能漂移**；引用的写法本身均为抽查当时读到的原文。

| # | 来源文件 | 仓库写法 | 参考文档说法 | 判定 |
|---|----------|----------|--------------|------|
| 1 | `cst_solver\simulation\ports.py` L63 | `With Port` + `.NumberOfModes "1"` | `## 16.1 Waveguide Port`：`NumberOfModes`（int，模式数）；参考用对象名 `Port`，`"WAVEGUIDE"` 只是 `PortType` 的枚举值之一。**全文检索 `WaveguidePort` = 0 命中**，参考中没有 `With WaveguidePort` 这种写法 | 属性名与对象名**匹配**。仓库写的就是 `With Port`（与参考一致），没有任何问题 |
| 2 | `cst_solver\simulation\ports.py` L69 | `.Coordinates "Picks"` | L1189：`Coordinates` \| string \| `"Free"` / `"Picked"` | **不一致**：仓库写 `"Picks"`，参考在 Port 对象下列的是 `"Picked"`。（参考文档自身在其它对象的 `Mode` 属性处用的是 `"Picks"`，L562/574/585，属文档内部用词不一致；未在真实 CST 上实测，故此项标为**不确定**） |
| 3 | `cst_solver\simulation\solver.py` L53/L65 等（**该文件正被并发修改，行号可能漂移**） | `With Solver` + `.SteadyStateLimit "-30"` | L829 `## 12. Solver — 时域求解器（HF）`；L842 `Solver.SteadyStateLimit(double dB)`（稳态限制，如 `-30`） | **匹配**（属性名与写法一致；注意参考中不存在 `TimeDomainSolver` 对象名，`With Solver` 才是正确入口） |
| 4 | `cst_solver\simulation\boundary.py` L36-38 | `With Boundary` + `.Xmin "{xmax}"` | L790 `Boundary.Xmin(enum type)`（X− 边界），同节还有 `Xmax/Ymin/Ymax/Zmin/Zmax/Xsymmetry/...` | **匹配** |
| 5 | `cst_solver\modeling\booleans.py` L51 | `Solid.Subtract "{c1}:{n1}", "{c2}:{n2}"` | L599 `Solid.Subtract(solidname s1, solidname s2)`（s1 − s2） | **匹配** |

附加发现（不在抽查 5 项内，但同样只读核对过）：`booleans.py` L123 的 `Solid.Imprint` 在参考文档中 **未找到**（`Imprint` 全文 0 命中；参考的 Solid 章节只列了 Add / Subtract / Intersect / Insert / Delete / BlendEdge / ChamferEdge 等）；`ports.py` L72-74 的 `ClipPickedPortToBound` / `SingleEnded` / `WaveguideMonitor` 与 L64 的 `AdjustPolarization` 均在 L1193-1198 **匹配**。以上仅就本参考文档而言，未在真实 CST 2026 上实测。
