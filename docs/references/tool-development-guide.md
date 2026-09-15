# CST Runtime CLI — 工具开发集成包

面向 agent 或开发者。覆盖从查阅 VBA 文档到 CLI 上线的完整流程。

---

## 目录

1. [前置知识](#1-前置知识)
2. [开发流程总览](#2-开发流程总览)
3. [Step 1: 查阅 VBA 对象文档](#3-step-1-查阅-vba-对象文档)
4. [Step 2: 编写 TOML 定义](#4-step-2-编写-toml-定义)
5. [Step 3: 运行代码生成器](#5-step-3-运行代码生成器)
6. [Step 4: 在真实 CST 上测试](#6-step-4-在真实-cst-上测试)
7. [Step 5: 注册到 CLI 工具集](#7-step-5-注册到-cli-工具集)
8. [Step 6: 上线归档](#8-step-6-上线归档)
9. [TOML 格式参考](#9-toml-格式参考)
10. [测试脚本模板](#10-测试脚本模板)
11. [常见问题](#11-常见问题)

---

## 1. 前置知识

### 两个入口点

| 入口 | 方式 | 用途 |
|------|------|------|
| 直接 COM | `project.modeler.StoreDoubleParameter("w", 10)` | 参数读写、查询、仿真控制 |
| VBA 字符串 | `project.modeler.add_to_history("名称", "VBA 代码")` | 建模、端口、监视器、求解器配置 |

### 三个文档来源

| 来源 | 位置 | 内容 |
|------|------|------|
| **VBA_3D HTML**（官方） | `C:\Program Files\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D\` | 150+ 对象的完整方法签名、参数类型、枚举值 |
| **cst_runtime 源码** | `scripts/cst_runtime/core/modeling.py` 等 | 生产环境验证过的 VBA 拼装模式 |
| **TOML 定义** | `tools/vba_defs/` | 已封装为可生成工具的声明式定义 |

### 架构层次

```
VBA_3D HTML 方法签名 → TOML 声明式定义 → 代码生成器 → gen_*.py 工具函数
                                                       ↓
                                           cst_runtime CLI dispatch
                                                       ↓
                                          agent 调用: uv run python -m cst_runtime <tool>
```

---

## 2. 开发流程总览

```
查阅 VBA_3D HTML → 编写 TOML → run generate_tools.py → 部署到测试区 → CST 实测
                                                                          ↓
                                                              PASS? → 注册到 CLI → 提交
                                                                          ↓
                                                              FAIL? → 修 TOML → 重跑
```

**核心原则：**
- 只加优化流程相关方法，不全量照抄官方文档
- 非核心参数加默认值，不暴露给 agent
- 方法名和枚举值必须和 VBA_3D HTML 一致

---

## 3. Step 1: 查阅 VBA 对象文档

### 3.1 离线 HTML（推荐）

用浏览器直接打开，不需启动 CST：

```
# 对象索引（50+ 子目录入口）
C:\Program Files\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D\index.htm

# 对象树总览
C:\Program Files\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D\special_vbaobjects\special_vbaobjects_vbaobjects.htm

# 基本实体
C:\Program Files\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D\common_vbabasicsolids\

# 导入导出
C:\Program Files\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D\common_vbaimpexp\

# 后处理
C:\Program Files\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D\special_vbapostproc\

# 求解器
C:\Program Files\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D\special_vbasolver\
```

### 3.2 核对清单

对每个 VBA 对象逐个核对：
- [ ] 方法名是否与 HTML 文档一致
- [ ] 参数类型是否正确（str / float / int / bool / enum）
- [ ] 枚举值是否完整且值正确
- [ ] 哪些方法是优化流程核心需要的
- [ ] 哪些方法可以加默认值

### 3.3 在线镜像（备用）

CST 2013 版对象树，与 2026 基本兼容：
- `http://www.mweda.com/cst/cst2013/mergedProjects/VBA_Help_MWS/special_vbaobjects/special_vbaobjects_vbaobjects.htm`

---

## 4. Step 2: 编写 TOML 定义

### 4.1 文件位置

```
skills/cst-runtime-cli/tools/vba_defs/<object>.toml
```

### 4.2 结构

```toml
[object]
name = "monitor"           # 生成的函数名 create_monitor
vba_object = "Monitor"     # VBA 对象名（With Monitor ... End With）

[enums.FieldType]          # 枚举定义
values = ["Efield", "Hfield", "Farfield"]
default = "Efield"

# With/End With 块方法（按 VBA 顺序排列）
[[methods]]
name = "Reset"             # → VBA: Monitor.Reset

[[methods]]
name = "Name"             # → VBA: Monitor.Name "xxx"
params = [{ name = "name", type = "str" }]

[[methods]]
name = "FieldType"        # → VBA: Monitor.FieldType "Efield"
params = [{ name = "field_type", type = "FieldType" }]

[[methods]]
name = "Create"           # → VBA: Monitor.Create
block_end = true           # ← 标记 With 块结束

# 独立方法（不在 With 块内）
[[methods]]
name = "Delete"
params = [{ name = "monitor_name", type = "str" }]
standalone = true          # ← 独立函数
vba_raw = 'Monitor.Delete "{monitor_name}"'
```

### 4.3 关键规则

| 规则 | 说明 |
|------|------|
| 方法顺序 | 按 VBA With 块中的实际顺序排列 |
| `block_end` | 标记 With 块的最后一个方法 |
| `standalone` | 不在 With 块内的方法，生成独立函数 |
| `vba_raw` | 手动指定 VBA 模板（用于复杂格式） |
| `hardcoded` | 硬编码值，不暴露到函数签名 |
| 参数名去重 | 同名同类型合并，同名不同类型报错 |
| bool 默认值 | TOML 中写 `"true"` / `"false"`（小写字符串） |
| enum 值 | 必须与 VBA_3D HTML 一致 |

### 4.4 参考实现

```
skills/cst-runtime-cli/tools/vba_defs/
├── monitor.toml      — 场监视器（With 块 + 枚举 + standalone）
├── brick.toml        — 基本实体（简单 With 块）
├── solver.toml       — 求解器（多 bool 参数）
├── port.toml         — 波端口（多默认值参数）
├── units.toml        — 单位系统（hardcoded 参数）
├── transform.toml    — 变换（枚举 + 布尔）
├── cylinder.toml     — 圆柱体（With 块 + 默认值）
├── solid.toml        — 全 standalone 方法（无 With 块）
├── background.toml   — 背景材料
└── boundary.toml     — 边界条件
```

---

## 5. Step 3: 运行代码生成器

```powershell
cd skills/cst-runtime-cli
uv run python tools/generate_tools.py
```

输出到 `scripts/cst_runtime/tools/gen_<object>.py`。

**生成内容：**
- Python Enum 类（从 TOML `[enums]`）
- `create_xxx()` 函数（With/End With 块 → 一条 `add_to_history`）
- 独立函数（standalone 方法）
- `TOOLS_TO_REGISTER` 字典（可直接导入 CLI 注册）

### 验证语法

```powershell
python -c "import py_compile; [py_compile.compile(f'skills/cst-runtime-cli/scripts/cst_runtime/tools/gen_{n}.py', doraise=True) for n in ['monitor','brick']]"
```

---

## 6. Step 4: 在真实 CST 上测试

### 测试体系

本仓库有两层测试，详见 `skills/cst-runtime-cli/tests/Test_kit_README.md`：

| 层 | 触发时机 | 命令 |
|----|---------|------|
| **单元测试** | 每次改代码后 | `uv run pytest skills/cst-runtime-cli/tests -v` |
| **管道合约测试** | 修改 `core/` 后，push 前 | 见 `tests/Test_kit_README.md` |

### 生成工具验证（额外层）

每次运行 `generate_tools.py` 产出新 `gen_*.py` 后，在测试区对真实 CST 逐工具验证。**每个工具一个独立 run**，路径遵循标准结构：

```
C:\Users\Admin\Documents\test\
  refs/ref_0/ref_0.cst                 ← 基准工程（只读）
  tasks/task_test_xxx/
    runs/
      run_001/
        projects/working.cst            ← 测试工程（save=True）
        summary.md                       ← 记录操作和结果
      run_002/...
```

测试脚本模板见 [§10](#10-测试脚本模板)。

### 运行

```powershell
cd C:\Users\Admin\Documents\test
uv run python _test_gen_tools.py
```

```python
"""每个工具一个独立 run，保存供人工查验。"""
import shutil, sys
from pathlib import Path

TEST_DIR = Path(r"C:\Users\Admin\Documents\test")
sys.path.insert(0, str(TEST_DIR / ".cst_runtime"))

from cst_runtime.core.session import open_project, close_project, get_attached_project

REF0 = TEST_DIR / "refs" / "ref_0" / "ref_0.cst"
TASK = TEST_DIR / "tasks" / "task_test_xxx"


def new_run(name: str) -> Path:
    """创建新 run 目录，复制 ref_0 → working.cst。"""
    import shutil
    run_id = len(results) + 1
    run_dir = TASK / "runs" / f"run_{run_id:03d}"
    proj_dir = run_dir / "projects"
    proj_dir.mkdir(parents=True, exist_ok=True)
    dst = proj_dir / "working.cst"
    shutil.copy2(REF0, dst)
    comp_src = REF0.with_suffix("")
    comp_dst = dst.with_suffix("")
    if comp_src.is_dir():
        shutil.copytree(comp_src, comp_dst, dirs_exist_ok=True)
    return dst


def summary(run_dir: Path, content: str):
    (run_dir / "summary.md").write_text(content, encoding="utf-8")


results = []


def do(run_name, desc, import_line, call_fn):
    dst = new_run(run_name)
    run_dir = dst.parent.parent
    proj_path = str(dst)
    try:
        open_project(proj_path)
        prj = get_attached_project(proj_path)
        exec(import_line, globals())
        call_fn(prj)
        close_project(proj_path, save=True, kill_processes=True)
        summary(run_dir, f"# {run_name}\n\n**Status**: PASS\n**Op**: {desc}")
        results.append((True, run_name, ""))
    except Exception as e:
        results.append((False, run_name, str(e)))
        try: close_project(proj_path, save=False, kill_processes=True)
        except: pass
        summary(run_dir, f"# {run_name}\n\n**Status**: FAIL\n**Error**: {e}")


# ── 在此定义要测试的工具 ──
TESTS = [
    (
        "Monitor (farfield)",                           # 测试名
        "create_monitor: farfield (f=12), freq=12.0",   # 操作描述
        "from cst_runtime.tools.gen_monitor import create_monitor, FieldType",  # import
        lambda prj: create_monitor(prj, name="farfield (f=12)", field_type=FieldType.FARFIELD, freq=12.0),  # 调用
    ),
    (
        "Brick",
        "create_brick: 100mm cube PEC",
        "from cst_runtime.tools.gen_brick import create_brick",
        lambda prj: create_brick(prj, "gt_cube", "component1", "PEC", -50.0, 50.0, -50.0, 50.0, -50.0, 50.0),
    ),
]


def main():
    for name, desc, imp, fn in TESTS:
        do(name, desc, imp, fn)
    total = len(results)
    passed = sum(1 for ok, _, _ in results if ok)
    print(f"\nResults: {passed}/{total} passed")
    if passed == total:
        print(f"All passed! See: {TASK / 'runs'}")


if __name__ == "__main__":
    main()
```

---

## 7. Step 5: 注册到 CLI 工具集

在 `cli.py` 的 TOOLS dict 中添加引用：

```python
# cli.py
from cst_runtime.tools.gen_monitor import TOOLS_TO_REGISTER as _MONITOR_TOOLS

TOOLS = {
    # ... 现有工具 ...
    **_MONITOR_TOOLS,  # 自动注册 create-monitor / delete / rename
}
```

生成器产出的 `TOOLS_TO_REGISTER` 字典已含完整的 params schema，直接 merge 即可。

---

## 8. Step 6: 上线归档

```powershell
# 1. 跑合约测试
uv run pytest skills/cst-runtime-cli/tests -v

# 2. 同步到 agent 安装目录
Copy-Item -LiteralPath "skills\cst-runtime-cli\scripts\cst_runtime\" -Destination "$env:USERPROFILE\.config\opencode\skills\cst-runtime-cli\scripts\cst_runtime\" -Recurse -Force
Copy-Item -LiteralPath "skills\cst-runtime-cli\SKILL.md" -Destination "$env:USERPROFILE\.config\opencode\skills\cst-runtime-cli\SKILL.md" -Force
Copy-Item -LiteralPath "skills\cst-runtime-cli\scripts\bootstrap.py" -Destination "$env:USERPROFILE\.config\opencode\skills\cst-runtime-cli\scripts\bootstrap.py" -Force

# 3. 测试目录也会定期部署，确保 gen_*.py 在测试区的 .cst_runtime/ 下
Copy-Item -LiteralPath "skills\cst-runtime-cli\scripts\cst_runtime\tools\gen_*.py" -Destination "C:\Users\Admin\Documents\test\.cst_runtime\cst_runtime\tools\" -Force
```

---

## 9. TOML 格式参考

### 完整字段说明

```toml
[object]
name = "对象名"              # 必填。生成 create_xxx() 函数名
vba_object = "VBA对象名"      # 可选。With 块中使用的 VBA 对象名
categories = ["cat"]          # 可选。函数名前缀

[enums.EnumName]              # 枚举定义
values = ["val1", "val2"]     # 枚举值列表
default = "val1"              # 可选。默认值

[[methods]]                   # 方法定义
name = "MethodName"           # 必填。VBA 方法名
params = [...]                # 可选。参数列表
  name = "param_name"         #   参数名
  type = "str"                #   参数类型: str/float/int/bool/enum名/expr
  default = "value"           #   可选。默认值
  description = "说明"         #   可选。参数描述
  hardcoded = "Literal"       #   可选。硬编码值（不暴露到函数签名）
vba_raw = 'VBA模板'           # 可选。手动指定 VBA 字符串
block_end = true              # 可选。标记 With 块结束
standalone = true             # 可选。独立方法（不在 With 块内）
```

### 参数类型映射

| TOML type | Python 类型 | VBA 格式 | 默认值写法 |
|-----------|------------|---------|-----------|
| `str` | `str` | `"value"` | `"hello"` |
| `float` | `float` | `10.0` | `"0.0"` |
| `int` | `int` | `5` | `"0"` |
| `bool` | `bool` | `True` / `False` | `"true"` / `"false"` |
| `expr` | `str` | `-width/2`（透传） | `"0"` |
| `EnumName` | Python Enum | `"Value"` | 枚举成员引用 |

---

## 10. 测试脚本模板

完整模板见 [§6.4](#64-测试脚本模板)。

---

## 11. 常见问题

**Q: TOML 和 VBA_3D HTML 不一致怎么办？**
以 VBA_3D HTML 为准。如果既有方法名在现有代码中使用但不在 HTML 里（如 `.ResetBackground`），说明是旧版 API，实测通过则保留不走生成器。

**Q: 生成的 VBA 和现有手工 VBA 不一样但都通过测试？**
两者都有效。差异通常是 `With/End With` vs 直接前缀风格，或 bool/数字加不加引号。CST COM 都接受。

**Q: 新增 TOML 方法后生成器报"Duplicate param"？**
两个方法使用了同名参数。改名或检查是否真的应该同名——same name + same type = 自动合并，same name + different type = 错误。

**Q: 测试区能不能直接在 ref_0 上跑？**
不能。必须复制到 `tasks/task_xxx/runs/run_xxx/projects/working.cst`。测试完 `save=True` 保留供人工查验。

**Q: 怎么人工查验测试结果？**
用 CST GUI 打开 `working.cst`，检查 History List 中是否有对应操作记录。

**Q: 管道合约测试什么时候跑？**
修改 `core/` 后累积多次提交，push 前集中跑一次。不是每次改代码都跑。

**Q: 现有的 `core/modeling.py` 函数要不要迁移到生成器？**
不需要。已验证的手工 VBA 保持原样。两个体系并存：手工修补路径维护现有核心工具，生成器路径扩展新对象。
