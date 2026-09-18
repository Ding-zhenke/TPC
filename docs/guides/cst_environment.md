# CST 环境配置与会话生命周期

Python 包的导入不再加载 CST 接口，不修改 `sys.path`，也不向 stdout 输出安装提示。`setup()` 才加载 `cst.interface`；`Result(path)` / 兼容旧名 `result(path)` 才加载 `cst.results`。CST 接口仍由 CST 安装提供，不能用 `pip install cst` 代替。

## 配置方式

推荐在启动 Python 前设置环境变量，无需修改安装后的包：

```powershell
$env:CST_INSTALL_PATH = 'C:\SOFTWARE\CST Studio Suite 2026'
python -m cst_solver doctor
python -m cst_solver doctor --probe
```

也可将以下 JSON 保存到自己的目录，再将 `CST_CONFIG_FILE` 设为该文件路径：

```json
{
  "CST_INSTALL_PATH": "C:/SOFTWARE/CST Studio Suite 2026",
  "CST_GUARD_MODE": "warn"
}
```

配置内相对路径相对于 JSON 所在目录。`CST_PYTHON_LIB`、`CST_MATERIAL_LIB` 可独立覆盖；未指定时从安装目录推导。兼容旧 `cst_solver/config.py`，但新安装不需要复制配置到 site-packages。`config_template.py` 只作为示例，不再当作本机配置加载。

安装路径优先级：`get_cst_paths(install_path=...)` 显式参数 → `CST_INSTALL_PATH` 环境变量 → 用户 JSON（优先于旧 config.py）→ 常见安装目录自动发现。显式根目录覆盖时，旧配置中的子路径不再生效；显式环境子路径仍优先。

自动发现仅检查 Windows 的 Program Files、Program Files (x86)、`C:\SOFTWARE`；只接受有 `AMD64/python_cst_libraries` 的安装，选择最高年份。其他目录请显式配置。已加载接口后改变版本需要重启解释器，不在同一进程混用版本。

## 诊断与 Python 接口

```python
from cst_solver import discover_cst_installations, get_cst_paths, diagnose_environment

print(discover_cst_installations())
print(get_cst_paths())
report = diagnose_environment()              # 检查配置与发现状态，不导入 CST
report = diagnose_environment(probe=True)    # 仅尝试导入接口，不启动 DE/求解
```

doctor 输出 JSON；配置错误及 probe 导入失败返回退出码 1。`not_probed` 不代表不可用或可用；`importable` 只代表接口能加载，不证明许可有效、模型正确或求解成功。底层 ImportError/DLL 错误作为 `CSTUnavailableError` 的异常链保留。

### 解释器 ↔ 接口 ABI（离线可查）

CST 的 Python 接口是 **pybind11 扩展** `<安装目录>\AMD64\_cst_interface.cpNN-win_amd64.pyd`，
**只有 ABI 与解释器一致的那一个才能被 import**（Python 3.11 需要 `cp311`）。
这一条**不需要启动 CST 就能查**，也常是「装了 CST 却导不进 `cst.interface`」的真正原因：

```python
from cst_solver import describe_interface_abi, diagnose_environment

print(describe_interface_abi())      # 不启动 CST、不导入接口
# {'install_path': ..., 'interpreter_abi': 'cp311',
#  'interfaces': ['cp38', 'cp39', 'cp310', 'cp311', 'cp312', 'cp313'],
#  'matching_abi': 'cp311', 'abi_match': True, 'note': ...}

diagnose_environment()['interface_abi']   # doctor / 诊断里也带这一段
```

⚠️ **`abi_match=True` 不等于「已验证组合」**：有同 ABI 的 `.pyd` 只说明**有可能导入**，
真正导入还依赖 DLL 依赖与许可。计划 P1 要求的「已验证 CST/Python 组合公布」
仍以真机结果为准，本项只是把它变成**可机器核对**的一条判据。

`get_cst_paths(install_path=...)` 只是查询/推导，不持久改变全局配置。供其他代码兼容的 `CST_INSTALL_PATH/CST_PYTHON_LIB/CST_MATERIAL_LIB` 常量是导入时快照，未发现时为 None；运行入口使用当前配置。

## 会话清理

```python
from cst_solver import setup

with setup(r'D:\out\working-copy.cst') as app:
    # 建模后检查 app.get_messages() / app.validate_model()
    app.save()
```

不存在的工程路径在创建 CST 设计环境前报错。打开失败会尝试关闭本次创建的环境；`with setup(): ...` 即使没有打开工程也会关闭环境。项目关闭报错时仍尝试关闭环境；上下文中已有异常时，清理失败写日志而不覆盖原始异常。

先 `close_project()` 后 `close()` 可以释放剩余环境；重复 `close()` 不重复调用底层对象，但原有 warn/strict 的重复关闭诊断保持。`close()` 不自动保存，仍应先显式 `save()`。

`cst_solver` 的项目和材料运行消息使用 logging，默认不往 stdout 写。用户若将日志配置到 stdout，或上层模板/CST 原生输出写 stdout，仍会影响 MCP；MCP 接入层必须单独验证和隔离。

离线测试已覆盖路径、配置、异常链、无 CST 导入与会话清理；真实 CST 生命周期验证保留在 [计划 P4/V8](../next_plan/README.md)。
