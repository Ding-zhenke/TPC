# 第三方参考资料声明 / Third-Party Notices

本目录（`docs/references/`）下的 4 个 Markdown 文档是**第三方参考资料**，逐字节原样复制自外部开源项目 **cst-runtime-cli**（上游地址见下方），**不属于本仓库（TPC）自身的代码或文档资产**。它们仅供离线查阅之用；本仓库的任何代码都不会 import、读取或依赖这些文件。上游项目的版权与许可条款如下，转载时请一并保留本文档。

---

## 1. 收录文件清单

| 文件 | 字节数 | 用途简述 |
|------|--------|----------|
| `vba-official-reference.md` | 73,155 | CST Studio Suite 2026 的 VBA 官方对象参考：从官方在线帮助 `VBA_3D`（150+ 页 HTML）逐对象提取的属性/方法签名、参数类型、枚举值与官方示例，共 23 节，覆盖入口对象、参数管理、单位、实体建模、曲线、布尔运算、Transform、Pick、WCS、Boundary、时域/频域/本征模求解器、Mesh、Port、Monitor、导入导出、远场与结果读取。用于核对写入 `add_to_history` 的 VBA 片段的确切拼写与参数。 |
| `cst-official-api-reference.md` | 57,636 | CST 官方 **Python** API 参考手册（`cst.interface` / `cst.results` / `cst.units`，CST 2026）：共 10 节，覆盖 DesignEnvironment/Project/Model3D 运行时连接、ProjectFile 离线结果读取、单位系统、C 扩展层全景、其他子包、与 `cst_runtime` 的对照表，以及源码挖掘出的隐藏能力（动态 COM 代理、BeginHide/EndHide、CLI 解析器等）。用于不写 VBA、直接用 Python 驱动 CST 的场合。 |
| `tool-development-guide.md` | 15,444 | 上游项目的「工具开发集成包」：面向 agent/开发者的完整开发流程说明，含两个入口点（直接 COM vs. `add_to_history` VBA 字符串）、三个文档来源、6 步开发流程（查阅 VBA 文档 → 编写 TOML 定义 → 运行代码生成器 → 真实 CST 实测 → 注册到 CLI → 上线归档）、TOML 格式参考、测试脚本模板与常见问题。用作「新增一个 CST 工具」的方法论模板。 |
| `Test_kit_README.md` | 4,798 | 上游项目的测试体系说明：两层测试结构 —— 209 个无需 CST 的 pytest 单元测试（工具/管道元数据、错误路径、治理标签、结果解析等），以及 10 个需要真实 CST COM 环境的管道合约测试（`manual_pipeline_contracts.py`），并给出测试矩阵与各项验证内容。用作本仓库规划 CST 相关测试时的参照。 |

> 说明：以上「用途简述」由人工阅读各文件开头（约前 60 行）后撰写，非推测。

---

## 2. 上游项目与来源

- **上游项目**：cst-runtime-cli
- **上游源码地址**：<https://github.com/bbl21/cst-runtime-cli>
  - 该 URL 由 `git -C <repo> remote -v` 得到：`origin  https://github.com/bbl21/cst-runtime-cli.git (fetch)`
  - 并可由上游 `skills/cst-runtime-cli/scripts/pyproject.toml` 的 `[project.urls] Homepage = "https://github.com/bbl21/cst-runtime-cli"` 相互印证。
- **来源路径**：`<upstream>/devkit/references/`
- **上游版本**：HEAD = `7eac82190845083396889a7ae96ed22c2118a892`（`Wed Jun 24 11:10:20 2026 +0800`，提交信息「更新README」）
- **复制时间**：2026-09-15
- **复制方式**：逐字节复制（`Copy-Item`），未重排格式、未改写行尾、未翻译。每个文件的源/目标字节数与 SHA-256 均已校验一致。

> 注意：本目录中的文件是**为离线查阅而 vendored 的副本（vendored copies）**，不是上游的实时版本；上游后续更新不会自动同步到本仓库，需要时请重新从上述地址获取。

---

## 3. 上游许可证（verbatim）

上游仓库根目录存在 `LICENSE` 文件（1,083 字节），内容为 **MIT License**，版权行为 `Copyright (c) 2026 bbl21`。
该许可信息同时可在上游 `skills/cst-runtime-cli/scripts/pyproject.toml` 中得到印证：`license = {text = "MIT"}`。

以下为该许可的**逐字全文**：

```text
MIT License

Copyright (c) 2026 bbl21

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

说明：

- MIT 许可要求「上述版权声明和本许可声明应包含在本软件的所有副本或实质性部分中」，因此本文档保留完整许可全文；本目录下 4 个文件即为该软件的实质性部分副本。
- 上述许可文本与上游 `LICENSE` 文件**逐字符一致**（含 `Copyright (c) 2026 bbl21` 一行）；仅行尾被规范化为 LF —— 上游 `LICENSE` 使用 CRLF（共 21 个 CR + 21 个 LF，1,083 字节，以 CRLF 结尾）。本仓库 `.gitattributes` 为 `* text=auto`，提交时本就会做 LF 规范化，故此处统一使用 LF。已用程序校验「LF 规范化后的上游 LICENSE 全文（1,062 字符）逐字包含于本文档中」，结果为真。
