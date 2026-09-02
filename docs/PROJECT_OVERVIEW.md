# cst_solver 项目概览

> 用于 AI 快速理解本项目结构和功能的导读文档。
最后更新: 2026-07-02
---

## 一、项目目标

本项目的核心目标是通过 **Python 脚本自动控制 CST Studio Suite** 进行电磁仿真，包括：
│   ├── __init__.py                # setup 主类（208 方法，23 Mixin）
1. **自动化建模** — 在 CST 中创建几何结构（长方体、圆柱、多边形等）
2. **自动化仿真** — 设置材料、端口、边界、求解器、运行仿真
3. **结果后处理** — 读取 S 参数、场数据、远场方向图
4. **优化循环** — 结合遗传算法（GA）自动调优结构参数

---

## 二、项目结构

```
TPC/
├── cst_solver/                    # 📦 CST 自动化 Python 包（核心）
│   ├── __init__.py                # setup 主类（196 方法，22 Mixin）
│   ├── config_template.py         # 配置模板（提交 git）
│   ├── config.py                  # 本地配置（gitignored）
│   ├── project.py                 # 项目操作：打开/关闭/保存
│   ├── parameters.py              # 参数管理：参数/表达式/频率
│   ├── units.py                   # 单位设置
│   ├── result.py                  # 结果读取类（Result/result）
│   ├── modeling/
│   │   ├── primitives.py          # 基本体：Brick, Cylinder, Sphere, Wire...
│   │   ├── curves.py              # 曲线：Polygon, Arc, Circle, Spline...
│   │   ├── curves_ops.py          # 曲线操作：Extrude, Loft, Sweep...
│   │   ├── booleans.py            # 布尔运算：Add, Subtract, Intersect...
│   │   ├── transforms.py          # 变换：Translate, Rotate, Mirror...
│   │   └── io.py                  # 导入导出：SAT, DXF, STEP, IGES, STL, 子项目导入
│   │   └── wcs.py                 # 工作坐标系（★ 新增）
│   ├── material/
│   │   └── materials.py           # 材料与组件
│   ├── simulation/
│   │   ├── ports.py               # 端口：Port, DiscretePort, FloquetPort...
│   │   ├── sources.py             # 激励源：PlaneWave, Coil, FarfieldSource...
│   │   ├── monitors.py            # 监视器：Monitor, Probe
│   │   ├── boundary.py            # 边界条件：Boundary, Background
│   │   └── solver.py              # 求解器：Solver, FDSolver, SolverParameter...
│   ├── mesh/
│   │   └── mesh.py                # 网格：Mesh, MeshAdaption3D, MeshSettings...
│   │   └── io.py                  # 导入导出：SAT, DXF, STEP, IGES, STL
│   └── postprocessing/
│       ├── proc.py                # 后处理：QFactor, CombineResults, SAR
│       ├── farfield.py            # 远场分析
│       ├── plot.py                # 绘图控制（★ 新增）
│       └── result_export.py       # 结果导出
├── scripts/
│   └── gen_docs.py               # HTML 文档自动生成脚本
├── docs/
│   ├── cst_solver_api.html        # API 文档（208 方法，23 类别）
│   ├── PROJECT_OVERVIEW.md        # ← 本文件
│   └── TODO_LIST.md               # 待实现功能清单
├── 遗传算法/
│   ├── MAIN.m                     # GA 主程序（MATLAB）
│   ├── F_SIMULATE.m               # 适应度评估
│   ├── Slover.m                   # CST 接口引擎
│   └── Export.m                   # 结果导出
├── c/                             # SAT 几何文件
├── hexlib.py                      # 六边形网格库
├── tri_lib.py                     # 三角形网格库
├── metalen.py                     # 材料公式工具
| 导入导出 | 9 | `import_sat`, `import_step`, `import_dxf`, `import_subproject` |
├── read.py                        # S2P 数据解析
├── setup.py                       # 路径配置（启动时导入）
├── test.ipynb                     # 测试/示例笔记本
├── cst_solver.py                  # 旧版兼容入口（推荐用 from cst_solver import setup）
└── README.md                      # 项目说明
| `docs/cst_solver_api.html` | 完整 API 文档（208 方法，脚本生成） |

# 输出: docs/cst_solver_api.html (208 方法, 23 类别)

## 三、核心架构：Mixin 多继承

所有功能通过 `setup` 类统一暴露，底层使用 Python Mixin 多继承：

```python
class setup(ProjectMixin, UnitsMixin, ParametersMixin,
             ModelingPrimitivesMixin, CurvesMixin, CurveOpsMixin,
             WCSMixin, SolidOpsMixin, TransformMixin, PickMixin,
             FaceOpsMixin, MaterialMixin, PortMixin, SourceMixin,
             MonitorMixin, BoundaryMixin, SolverMixin, MeshMixin,
             IOMixin, PostProcMixin, FarfieldMixin,
             PlotMixin, ExportMixin):
    """全部 196 个方法通过一个 setup 对象调用"""
```

### 命名规范

| 规范 | 示例 | 说明 |
|------|------|------|
| 新方法 | `create_brick()` | snake_case，Python 风格 |
| 旧别名 | `square()` | 保留以兼容旧代码 |
| 新旧映射 | `square = create_brick` | 同一功能，两个名字 |

---

## 四、配置系统

每台机器的 CST 安装路径不同，通过配置文件管理：

```
cst_solver/config_template.py   →  提交 git（模板）
cst_solver/config.py            →  加入 .gitignore（本地）
```

配置内容：
```python
CST_INSTALL_PATH = r"C:\SOFTWARE\CST Studio Suite 2026"
CST_PYTHON_LIB = r"C:\SOFTWARE\CST Studio Suite 2026\AMD64\python_cst_libraries"
```

导入时自动加载顺序：`config.py` → `config_template.py` → 默认路径

---

## 五、方法分类速查（208 方法，23 类别）

| 类别 | 方法数 | 主要函数 |
|------|--------|----------|
| 项目操作 | 9 | `open_project`, `close`, `save`, `activate` |
| 单位设置 | 1 | `set_units` |
| 参数管理 | 11 | `para`, `expression`, `set_frequency_range` |
| 基本体建模 | 13 | `create_brick`, `create_cylinder`, `create_sphere`, `create_wire` |
| 曲线绘制 | 10 | `polyline`, `arc`, `create_circle`, `create_spline` |
| 曲线操作 | 9 | `extrude`, `loft_curves`, `sweep_curve`, `blend_curve` |
| 工作坐标系 | 17 | `reset_wcs`, `rotate_wcs`, `translate_wcs`, `align_wcs` |
| 布尔运算 | 11 | `add`, `substract`, `intersect`, `boolean_imprint`, `blend_edge` |
| 变换操作 | 5 | `rotate`, `translate`, `mirror`, `scale` |
| 选取操作 | 6 | `pick_edge`, `pick_face`, `pick_vertex` |
| 面操作 | 4 | `rotation_face`, `extrude_face`, `trace_curve` |
| 材料与组件 | 8 | `create_material`, `create_component`, `change_material` |
| 端口设置 | 9 | `add_port`, `discrete_port`, `create_floquet_port` |
| 激励源 | 11 | `create_plane_wave`, `create_coil`, `create_farfield_source` |
| 监视器 | 3 | `define_monitor`, `create_probe` |
| 边界条件 | 3 | `boundary`, `set_background`, `set_layer_stacking` |
| 求解器 | 16 | `run`, `configure_fd_solver`, `set_solver_parameter` |
| 网格设置 | 6 | `set_mesh_properties`, `configure_mesh_adaption`, `set_mesh_region` |
| 导入导出 | 7 | `import_sat`, `import_step`, `import_dxf` |
| 后处理 | 4 | `calculate_q_factor`, `combine_results`, `calculate_sar` |
| 远场分析 | 5 | `set_farfield_plot`, `compute_farfield_array`, `farfield_plot_polar` |
| 绘图控制 | 13 | `plot_1d`, `plot_2d3d`, `scalar_plot_3d`, `vector_plot_3d` |
| 结果导出 | 7 | `export_result_1d`, `export_result_2d3d` |

---

## 六、使用示例

```python
from cst_solver import setup
from cst_solver.result import Result

# 打开工程
app = setup("example.cst")
app.set_units(frequency='GHz', length='mm')
app.set_frequency_range(1, 10)

# 建模
app.create_brick(0, 10, 0, 10, 0, 2, "substrate", material="Quartz (lossy)")
app.create_cylinder([5, 5], [2, 0], [0, 2], "via", material="Copper (annealed)")

# 端口和边界
app.add_port(1)
app.boundary(xmax="expanded open", ymax="expanded open")

# 求解
app.run()

# 读取结果
res = Result("example.cst")
s11 = res.read_s_parameter("S1,1")

# 关闭
app.close()
```

---

## 七、关键文件说明

| 文件 | 用途 |
|------|------|
| `cst_solver/result.py` | CST 结果读取类（Result + result 别名） |
| `docs/cst_solver_api.html` | 完整 API 文档（196 方法，脚本生成） |
| `scripts/gen_docs.py` | 文档生成脚本（扫描 docstring） |
| `cst_solver.py` | 旧版兼容入口（`from cst_solver import setup, result`） |
| `cst_solver/config.py` | 本地 CST 路径配置 |
| `test.ipynb` | 测试/示例笔记本 |

---

## 八、注意事项

1. **CST 必须已安装** — `cst_solver` 需要 CST 的 Python 库
2. **首次使用配置** — 复制 `config_template.py` 为 `config.py`，修改 CST 路径
3. **`from cst_solver import setup`** — 推荐（通过包直接导入）
4. **旧函数名可用** — 但推荐使用 snake_case 新名
5. **CST VBA 文档** — 位于 `C:\SOFTWARE\CST Studio Suite 2026\Online Help\`
6. **文档生成** — 运行 `python scripts/gen_docs.py` 重新生成 HTML 文档
