# 待实现功能清单

> 记录 `cst_solver` 包中尚未实现的功能与改进计划。
> 最后更新: 2026-05-26

---

## 一、尚未覆盖的 CST VBA 对象

以下 CST VBA 对象尚未建立 Python 接口，根据需求优先级排列：

### 🟡 中等优先级

| VBA 对象 | 说明 | 建议位置 | 难度 |
|----------|------|----------|------|
| `Background` | 完整背景材料设置接口 | `simulation/boundary.py` | 低 |
| `MeshAdaption3D` | 完整的网格自适应配置 | `mesh/mesh.py` | 低 |
| `PostProcess1D` | 1D 后处理操作（S参数计算等） | `postprocessing/proc.py` | 中 |
| `Optimizer` | CST 内置优化器配置 | `simulation/solver.py` | 中 |
| `ParameterSweep` | CST 参数扫描设置 | `simulation/solver.py` | 中 |

### 🔴 低优先级

| VBA 对象 | 说明 | 建议位置 | 难度 |
|----------|------|----------|------|
| `Line` | 完整三维直线接口（已有基础版） | `modeling/curves.py` | 低 |
| `Spline` | 完整样条曲线接口（已有基础版） | `modeling/curves.py` | 低 |
| `Bending` | 弯曲操作 | `modeling/booleans.py` | 中 |
| `LocalModification` | 局部修改操作 | `modeling/booleans.py` | 中 |
| `WCS` | 工作坐标系操作 | `modeling/transforms.py` | 中 |
| `Align` | 对齐操作 | `modeling/transforms.py` | 中 |
| `FloquetPort` | Floquet 端口（周期结构） | `simulation/ports.py` | 中 |
| `CablePort` | 线缆端口 | `simulation/ports.py` | 低 |
| `FieldSource` | 场源定义 | `simulation/sources.py` | 中 |
| `Probe` | 完整探针接口（已有基础版） | `simulation/monitors.py` | 低 |
| `TimeMonitor` | 时域监视器 | `simulation/monitors.py` | 中 |
| `LayerStacking` | 层叠设置 | `simulation/boundary.py` | 中 |
| `ResultTree` | 结果树操作 | `postprocessing/proc.py` | 低 |
| `ResultMap` | 结果映射 | `postprocessing/proc.py` | 中 |
| `SAR` | SAR 计算 | `postprocessing/proc.py` | 高 |

### ⚪ 暂不计划

| VBA 对象 | 原因 |
|----------|------|
| `Cable Studio` 相关 | 当前工作流不涉及线缆仿真 |
| `PIC Solver` 相关 | 当前工作流不涉及粒子仿真 |
| `Thermal Solver` 相关 | 当前工作流不涉及热仿真 |
| `3DEXPERIENCE` 接口 | 不使用该平台 |
| `CoventorWare`/`Mecadtron` 导入 | 不使用这些工具 |

---

## 二、功能完善项

### 🔧 代码修复

| 问题 | 位置 | 说明 | 状态 |
|------|------|------|------|
| `T_solver()` 为空方法 | `simulation/solver.py` | 时域求解器配置未实现 | ⏳ 待实现 |
| 历史标签拼写 `" roation "` | `modeling/transforms.py` | 不影响功能，仅 VBA 历史记录 | 🐞 小问题 |
| 历史标签 `"Freq_range "` 误用 | `material/materials.py` | 复制粘贴导致，不影响功能 | 🐞 小问题 |

### ⚡ 功能增强

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 时域求解器配置 `configure_time_solver()` | 实现完整的 T-Solver 参数设置 | 🟡 中 |
| 频域求解器配置完善 | 增加更多 FDSolver 参数 | 🟡 中 |
| 本征模求解器完善 | 增加 mode tracking 等高级功能 | 🟢 低 |
| 网格自适应完善 | 增加更多自适应参数 | 🟢 低 |
| 结果导出功能增强 | 支持更多导出格式和选项 | 🟢 低 |
| CST 批处理模式支持 | 支持无 GUI 的 Batch 运行模式 | 🟡 中 |
| CST 远程/集群支持 | 支持远程提交仿真任务 | 🔴 低 |

### 🧪 测试与验证

| 任务 | 说明 | 优先级 |
|------|------|--------|
| `test.ipynb` 回归测试 | 确保旧版代码在重构后输出一致 | 🟡 中 |
| 新增 VBA 接口单元测试 | 编写测试用例验证新增接口 | 🟢 低 |
| 跨版本 CST 兼容性测试 | 验证在不同 CST 版本下的兼容性 | 🔴 低 |

---

## 三、文档与工具

| 任务 | 说明 | 优先级 |
|------|------|--------|
| `gen_docs.py` 优化 | 增加更好的搜索、分类过滤等功能 | 🟢 低 |
| 中英文双语文档 | 为每个方法增加英文 docstring | 🔴 低 |
| 使用示例文档 | 编写常见场景的使用示例（如滤波器建模） | 🟡 中 |
| PyPI 发布准备 | 打包为可 pip install 的库 | 🔴 低 |

---

## 四、已知问题

1. **`from cst_solver import result`** — 由于 Python 模块优先级，从包级别导入 `result` 时会得到子模块而非类。
   - **方案**: 使用 `from cst_solver.result import result` 或通过兼容 shim `from cst_solver import setup, result`
   
2. **CST 版本依赖** — 当前接口基于 CST 2026 的 Python 库，旧版本可能不完全兼容。

3. **CST 未安装时导入会报错** — `cst_solver/__init__.py` 在导入时尝试加载 `cst` 模块，若 CST 未安装将抛出 ImportError。

---

## 五、近期计划（按优先级排序）

1. 🔴 实现 `configure_time_solver()` 时域求解器配置
2. 🔴 完善 `test.ipynb` 回归测试
3. 🟡 实现 `ParameterSweep` 参数扫描接口
4. 🟡 实现 `Optimizer` 优化器接口
5. 🟡 实现 CST 批处理模式支持
6. 🟢 完善文档和使用示例
