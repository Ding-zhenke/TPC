# TPC 项目概览

> 用于 AI 快速理解本项目结构和功能的导读文档。
> 最后更新: 2026-05-26

---

## 一、项目目标

本项目的核心目标是通过 **Python 脚本自动控制 CST Studio Suite** 进行电磁仿真，包括：

1. **自动化建模** — 在 CST 中创建几何结构（长方体、圆柱、多边形等）
2. **自动化仿真** — 设置材料、端口、边界、求解器、运行仿真
3. **结果后处理** — 读取 S 参数、场数据、远场方向图
4. **优化循环** — 结合遗传算法（GA）自动调优结构参数

---

## 二、项目结构

```
TPC/
├── cst_solver/                    # 📦 CST 自动化 Python 包（核心）
│   ├── __init__.py                # setup 主类（Mixin 聚合）
│   ├── config_template.py         # 配置模板（提交 git）
│   ├── config.py                  # 本地配置（gitignored）
│   ├── project.py                 # 项目操作：打开/关闭/保存
│   ├── parameters.py              # 参数管理：参数/表达式/频率
│   ├── result.py                  # 结果读取类（独立）
│   ├── modeling/
│   │   ├── primitives.py          # 基本体：Brick, Cylinder, Sphere...
│   │   ├── curves.py              # 曲线：Polygon, Arc, Circle...
│   │   ├── curves_ops.py          # 曲线操作：Extrude, Loft, Sweep...
│   │   ├── booleans.py            # 布尔运算：Add, Subtract...
│   │   ├── transforms.py          # 变换：Translate, Rotate, Mirror...
│   │   └── picks.py               # 选取：Pick edge/face/vertex...
│   ├── material/
│   │   └── materials.py           # 材料与组件
│   ├── simulation/
│   │   ├── ports.py               # 端口：Port, DiscretePort...
│   │   ├── sources.py             # 激励源：PlaneWave, Coil...
│   │   ├── monitors.py            # 监视器：Monitor, Probe
│   │   ├── boundary.py            # 边界条件：Boundary, Background
│   │   └── solver.py              # 求解器：Solver, FDSolver...
│   ├── mesh/
│   │   └── mesh.py                # 网格设置
│   ├── import_export/
│   │   └── io.py                  # 导入导出：SAT, DXF, STEP...
│   └── postprocessing/
│       ├── proc.py                # 后处理：QFactor, CombineResults
│       ├── farfield.py            # 远场分析
│       └── result_export.py       # 结果导出
├── scripts/
│   └── gen_docs.py               # HTML 文档自动生成脚本
├── docs/
│   ├── cst_solver_api.html        # API 文档（生成）
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
├── optimizer.py                   # GA 优化辅助
├── read.py                        # S2P 数据解析
├── setup.py                       # 路径配置（启动时导入）
├── test.ipynb                     # 测试/示例笔记本
├── old_cst_solver.py              # 旧版单文件（已废弃）
├── .gitignore                     # Git 忽略规则
└── README.md                      # 项目说明
```

---

## 三、核心架构：Mixin 多继承

所有功能通过 `setup` 类统一暴露，底层使用 Python Mixin 多继承：

```python
class setup(ProjectMixin, ParametersMixin, ModelingPrimitivesMixin,
             CurvesMixin, CurveOpsMixin, SolidOpsMixin, ...):
    """全部 138 个方法通过一个 setup 对象调用"""
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

## 五、方法分类速查

| 类别 | 方法数 | 主要函数 |
|------|--------|----------|
| 项目操作 | 10 | `open_project`, `close`, `save`, `activate` |
| 参数管理 | 10 | `para`, `expression`, `set_frequency_range` |
| 基本体建模 | 12 | `create_brick`, `create_cylinder`, `create_sphere` |
| 曲线绘制 | 14 | `polyline`, `arc`, `create_circle`, `create_spline` |
| 曲线操作 | 8 | `extrude`, `loft_curves`, `sweep_curve` |
| 布尔运算 | 12 | `add`, `substract`, `intersect`, `boolean_imprint` |
| 变换操作 | 7 | `rotation`, `translate`, `mirror`, `scale` |
| 选取操作 | 7 | `pick_edge`, `pick_face`, `pick_vertex` |
| 面操作 | 3 | `rotation_face`, `extrude_face`, `trace_curve` |
| 材料与组件 | 10 | `new_material`, `create_component`, `change_material` |
| 端口设置 | 10 | `add_port`, `discrete_port`, `create_discrete_port` |
| 激励源 | 8 | `create_plane_wave`, `create_coil`, `create_voltage_wire` |
| 监视器 | 5 | `define_monitor`, `create_probe` |
| 边界条件 | 3 | `boundary`, `set_background` |
| 求解器 | 9 | `run`, `configure_fd_solver`, `exclude_simulation` |
| 网格设置 | 2 | `set_mesh_properties`, `configure_mesh_adaption` |
| 导入导出 | 10 | `sat_import`, `import_step`, `export_data` |
| 后处理 | 2 | `calculate_q_factor`, `combine_results` |
| 远场分析 | 2 | `set_farfield_plot`, `compute_farfield_array` |
| 结果导出 | 3 | `export_result_1d`, `export_result_2d3d` |

---

## 六、使用示例

```python
from cst_solver import setup, result

# 打开工程
app = setup("example.cst")
app.set_frequency_range(1, 10)

# 建模
app.create_brick(0, 10, 0, 10, 0, 2, "substrate", material="Quartz (lossy)")
app.create_cylinder([5, 5], [2, 0], [0, 2], "via", material="Copper (annealed)")

# 设置端口和边界
app.add_port(1)
app.boundary(xmax="expanded open", ymax="expanded open")

# 求解
app.run()

# 读取结果
res = result("example.cst")
s11 = res.read_s_parameter("S1,1")

# 关闭
app.close()
```

---

## 七、关键文件说明

| 文件 | 用途 |
|------|------|
| `cst_solver/result.py` | CST 结果读取类（独立于 setup） |
| `docs/cst_solver_api.html` | 完整 API 文档（脚本生成） |
| `scripts/gen_docs.py` | 文档生成脚本 |
| `setup.py` | 启动时配置路径 |
| `cst_solver/config.py` | 本地 CST 路径配置 |
| `test.ipynb` | 测试/示例笔记本 |

---

## 八、注意事项

1. **CST 必须已安装** — `cst_solver` 需要 CST 的 Python 库
2. **首次使用配置** — 复制 `config_template.py` 为 `config.py`，修改 CST 路径
3. **`from cst_solver import result`** — 得到的是 `result` 类（不是模块）
4. **旧函数名可用** — 但推荐使用 snake_case 新名
5. **CST VBA 文档** — 位于 `C:\SOFTWARE\CST Studio Suite 2026\Online Help\`
