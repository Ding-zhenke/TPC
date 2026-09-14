# cst_solver 待实现功能清单

> 最后更新: 2026-07-02
> 当前覆盖: **209 个方法** / **22 个 Mixin 类别**

---

## ✅ 已实现功能总览

### 包结构与模块 (208 方法 / 23 类别)

```
cst_solver/
├── __init__.py              # setup 主类（208 方法，23 Mixin）
├── config / config_template # 配置系统（.gitignore）
├── project.py / parameters  # 项目管理 + 参数（20 方法）
├── units.py                 # 单位设置（2 方法）
├── _result_core.py          # 结果读取（Result + result 别名，9 方法）
│
├── modeling/                # ★ 几何建模（7 模块，67 方法）
│   ├── primitives.py        # Brick, Cylinder, Sphere, Cone, Torus, Wire
│   ├── curves.py            # Polygon, Arc, Circle, Ellipse, Line, Spline
│   ├── curves_ops.py        # ExtrudeCurve, Loft, SweepCurve, Blend/Chamfer/Cover/Trim
│   ├── booleans.py          # Solid.Add/Subtract/Insert/Intersect/Imprint/Blend
│   ├── transforms.py        # Translate, Rotate, Mirror, Scale
│   ├── picks.py             # PickEdge/Face/Vertex/Endpoint
│   └── wcs.py               # WCS 旋转/平移/对齐/保存/恢复/缩放
│
├── material/
│   └── materials.py         # 材料预设 + 自定义 + **.mtd 库加载**（10 方法）
│
├── simulation/              # ★ 仿真设置（5 模块，49 方法）
│   ├── ports.py             # Port, DiscretePort/DiscreteFacePort, FloquetPort, CablePort
│   ├── sources.py           # PlaneWave, Coil, FieldSource, FarfieldSource, TimeSignal
│   ├── monitors.py          # Monitor, Probe
│   ├── boundary.py          # Boundary, Background, LayerStacking
│   └── solver.py            # T/FD/Eigenmode/IE/Asymptotic + ParamSweep + Optimizer
│
├── mesh/
│   └── mesh.py              # Mesh/MeshAdaption3D/MeshSettings/MeshShapes（6 方法）
│
├── import_export/
│   └── io.py                # SAT/DXF/STEP/IGES/STL 导入
│
└── postprocessing/          # ★ 后处理（4 模块，32 方法）
    ├── proc.py              # QFactor/SAR/CombineResults/PostProcess1D
    ├── farfield.py          # FarfieldPlot/FarfieldArray
    ├── plot.py              # Plot1D/Plot2D3D/标量/矢量/远场极坐标/动画
    └── result_export.py     # ASCIIExport

mesh_grid/                   # 网格算法包（2026-06-02 重构）
├── __init__.py              # 统一入口
├── hex_grid/                # hexlib → mesh_grid.hex_grid
│   ├── core.py / io.py / viz.py
│   └── README.md / SKILL.md
└── tri_grid/                # tri_lib → mesh_grid.tri_grid
    ├── core.py
    └── README.md / SKILL.md

scripts/
└── gen_docs.py              # API 文档生成器
- [x] **优化器** — **Optimizer (`add_optimizer_goal`, `add_optimizer_parameter`, `start_optimizer`)**
- [x] **求解器参数** — SolverParameter (`set_solver_parameter`)
- [x] **排除仿真** — exclude_from_simulation

### 📐 网格

- [x] **网格属性** — Mesh (`set_mesh_properties`, `set_mesh_auto`)
- [x] **网格自适应** — MeshAdaption3D
- [x] **网格设置** — **MeshSettings** (增强)
- [x] **网格形状** — **MeshShapes** (含区域控制 `set_mesh_region`)

### 📂 导入导出

- [x] **CAD 导入** — SAT / DXF / STEP / IGES / STL / 子项目导入 (`io.py`)

### 📊 后处理

- [x] **Q 因子** — QFactor 计算
- [x] **SAR 计算** — SAR (比吸收率)
- [x] **结果组合** — CombineResults
- [x] **1D 后处理** — **PostProcess1D (操作链模式: `post_process_apply_to`, `post_process_add_operation`, `post_process_run`)**
- [x] **远场分析** — FarfieldPlot / FarfieldArray (`farfield.py`)

### 📈 绘图与导出

- [x] **绘图控制** — Plot / Plot1D / Plot2D3D / ScalarPlot2D/3D / VectorPlot2D/3D / 远场极坐标/动画 (`plot.py`)
- [x] **结果导出** — ASCIIExport (1D/2D/3D 场数据导出)

### 📝 工具

- [x] **文档生成** — `scripts/gen_docs.py` (自动扫描 docstring → HTML)
- [x] **配置系统** — `config_template.py` / `config.py` (`.gitignore`)
- [x] **HTML API 文档** — `docs/cst_solver_api.html` (208 方法, 23 类别)
- [x] **项目概览** — `docs/PROJECT_OVERVIEW.md`
- [x] **SKILL 文件** — `.github/copilot-instructions/SKILL.md`
- [x] **向后兼容** — `cst_solver.py` 兼容入口 + 旧函数名别名

---

## 🎯 尚未覆盖的 CST VBA 对象

### 🔴 优先级 1 — 常用

| VBA 对象 | 说明 | 难度 | 理由 |
|----------|------|------|------|
| `WaveguidePort` 增强 | 波导端口模式配置、极化角、参考面 | ⭐ | 现有 `add_port` 太简单 |
| `EStaticSolver` | 静电场求解器 | ⭐⭐ | 低频/静电应用 |
| `MStaticSolver` | 静磁场求解器 | ⭐⭐ | 静磁分析 |
| `StationaryCurrentSolver` | 稳恒电流求解器 | ⭐⭐ | 电流分布分析 |
| `LFSolver` | 低频求解器 | ⭐⭐ | 低频电磁场 |

### 🟡 优先级 2 — 进阶求解器

| VBA 对象 | 说明 | 难度 |
|----------|------|------|
| `ThermalSolver` | 稳态热求解器 | ⭐⭐ |
| `ThermalTDSolver` | 时域热求解器 | ⭐⭐ |
| `CHTSolver` | 共轭传热求解器 | ⭐⭐⭐ |
| `StructuralMechanicsSolver` | 结构力学求解器 | ⭐⭐⭐ |
| `DomainDecomposition` | 区域分解求解器 | ⭐⭐⭐ |
| `PICSolver` | 粒子追踪求解器 | ⭐⭐⭐ |
| `WakefieldSolver` | 尾场求解器 | ⭐⭐⭐ |

### 🟢 优先级 3 — 导入导出格式

| 格式 | VBA 对象 | 难度 |
|------|----------|------|
| OBJ | `OBJ` | ⭐ |
| GDSII | `GDSII` | ⭐⭐ |
| GERBER | `GERBER` | ⭐⭐ |
| CATIA | `CATIA` | ⭐⭐ |
| IGES 导出 / STEP 导出 | `IGES`, `STEP` | ⭐ |
| Touchstone | `TouchstoneExport` | ⭐ |
| HFSS | `HFSS` | ⭐⭐ |

### 🔵 优先级 4 — 高级功能

| VBA 对象 | 说明 | 难度 |
|----------|------|------|
| `EvaluateFieldAlongCurve` | 沿曲线评估场 | ⭐⭐ |
| `EvaluateFieldOnFace` | 在表面评估场 | ⭐⭐ |
| `Force` | 力的计算 | ⭐⭐ |
| `Displacement` | 位移计算 | ⭐⭐ |
| `Potential` | 电势计算 | ⭐ |
| `MaterialLibrary` | 从 CST 库加载材料 (已有 .mtd 加载) | ⭐⭐ |
| 色散材料 | Drude/Lorentz 模型 | ⭐⭐⭐ |
| 各向异性材料 | 各向异性材料设置 | ⭐⭐⭐ |
| `FarfieldCalculator` 增强 | 阵列因子、方向性系数计算 | ⭐⭐ |

---

## ⚙️ 代码质量改进

### 🔧 已知问题

| 问题 | 位置 | 说明 | 状态 |
|------|------|------|------|
| 历史标签拼写 `" roation "` | `modeling/transforms.py` | 不影响功能，仅 VBA 历史记录 | 🐞 小问题 |
| 函数名拼写 `new_componet` | `material/materials.py` | 已保留兼容，建议改为 `new_component` | 🐞 小问题 |
| 函数名拼写 `patten_export` | `import_export/io.py` | 已保留兼容，建议改为 `pattern_export` | 🐞 小问题 |
| 历史标签 `"Freq_range "` 误用 | `material/materials.py` | `new_componet()` 中历史标签错误 | 🐞 小问题 |
| 缺少类型注解 | 全书 | 逐步增加 type hints | 📝 待完善 |

### ⚡ 可增强的功能

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 频域求解器配置完善 | 增加更多 FDSolver 参数 (OBCType, MeshType 等) | 🟡 中 |
| 本征模求解器完善 | 增加 mode tracking 等高级功能 | 🟢 低 |
| 网格自适应完善 | 增加更多自适应参数 | 🟢 低 |
| 结果导出增强 | 支持更多导出格式和选项 | 🟢 低 |
| CST 批处理模式 | 支持无 GUI 的 Batch 运行 | 🟡 中 |
| Probe 增强 | 更多探针类型 (E/H/Both, 时域) | 🟢 低 |
| TimeMonitor 系列 | 时域监视器 (0D/1D/2D/3D) | 🟢 低 |

### 🧪 测试

| 任务 | 说明 | 优先级 |
|------|------|--------|
| `test.ipynb` 回归测试 | 确保旧版代码在重构后输出一致 | 🟡 中 |
| 单元测试框架 | pytest + mock (无需 CST 环境) | 🟢 低 |
| 跨版本 CST 兼容性 | 验证在不同 CST 版本下的兼容性 | 🔴 低 |

---

## 📊 覆盖总览

```
已覆盖 (23 类 / 208 方法):  ████████████████░░░░   ~60%
部分覆盖:                    █████░░░░░░░░░░░░░░░   ~25%
未覆盖:                      ░░░░░░░░░░░░░░░░░░░░   ~15%
```

### ⚪ 暂不计划实现

| VBA 对象 | 原因 |
|----------|------|
| `PIC Solver` 系列 | 当前工作流不涉及粒子仿真 |
| `Thermal Solver` 系列 | 当前工作流不涉及热仿真 |
| `Structural Mechanics` | 当前工作流不涉及结构力学 |
| `3DEXPERIENCE` 接口 | 不使用该平台 |
| `CoventorWare`/`Mecadtron` | 不使用这些工具 |
| `Cable Studio` | 当前工作流不涉及线束仿真 |
| `HumanModel` | 人体模型导入 (特定场景) |
| `ColourMapPlot`/`ColorRamp` | 颜色映射 (极少使用) |
| `Dimension` | 尺寸标注 (极少使用) |
| `LayoutDB` | 版图数据库 (特定场景) |

---

## 📝 文档生成

```bash
python scripts/gen_docs.py
# 输出: docs/cst_solver_api.html (208 方法, 23 类别)
```
