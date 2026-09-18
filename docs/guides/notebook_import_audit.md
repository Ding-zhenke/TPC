# 旧 notebook 导入兼容审计

- 源目录：`D:\成电博士生涯\拓扑光子晶体模型\硅基`
- `.ipynb` 总数：**90**
- 方式：只解析 `.ipynb` 的 code cell 源码（去 IPython 魔法后 `ast` 解析），**不执行**任何单元格；对 `current`/`legacy` 的导入逐个符号核对。
- 生成：`python scripts/check_notebook_imports.py`

## 1. 分类汇总

| 类别 | 顶层模块数 |
|---|---|
| `current` | 3 |
| `legacy` | 2 |
| `migrated` | 1 |
| `cst` | 0 |
| `stdlib` | 8 |
| `third-party` | 6 |
| `unknown` | 0 |

## 2. 逐个模块

| 模块 | 类别 | 用到的 notebook 数 | 取用的名字 |
|---|---|---|---|
| `cst_solver` | `current` | 65 | `result`, `setup` |
| `mesh_grid.plotting` | `current` | 1 | `chinese_plot_style` |
| `mesh_grid.tri_grid` | `current` | 6 | `TopoPath`, `build_triangle_lattice`, `color_triangles`, `find_different_points`, `plot_tri_color`, `plot_triangle_grid` … |
| `topo_modeler.builders` | `current` | 4 | `add_port_for_antenna`, `add_waveguide_port`, `build_feed`, `build_materials`, `build_topological_crystal`, `build_waveguide` |
| `hexlib` | `legacy` | 41 | `*`, `HexGridVisualizer`, `HexLib`, `create_hex_polygon`, `read_and_display_dxf_matplotlib`, `save_to_dxf` |
| `tri_lib` | `legacy` | 58 | `*` |
| `cst_solver.result` | `migrated` | 1 | `result` |
| `metalen` | `migrated` | 1 | （`import X`） |
| `importlib` | `stdlib` | 1 | （`import X`） |
| `json` | `stdlib` | 2 | （`import X`） |
| `os` | `stdlib` | 6 | （`import X`） |
| `re` | `stdlib` | 3 | （`import X`） |
| `shutil` | `stdlib` | 3 | （`import X`） |
| `subprocess` | `stdlib` | 1 | （`import X`） |
| `sys` | `stdlib` | 66 | （`import X`） |
| `time` | `stdlib` | 7 | （`import X`） |
| `matplotlib` | `third-party` | 1 | `font_manager` |
| `matplotlib.collections` | `third-party` | 16 | `PolyCollection` |
| `matplotlib.lines` | `third-party` | 1 | `Line2D` |
| `matplotlib.patches` | `third-party` | 2 | `PathPatch`, `Polygon`, `Rectangle` |
| `matplotlib.path` | `third-party` | 3 | `Path` |
| `matplotlib.pyplot` | `third-party` | 18 | （`import X`） |
| `numpy` | `third-party` | 70 | （`import X`） |
| `scipy` | `third-party` | 1 | `signal` |
| `scipy.optimize` | `third-party` | 3 | `curve_fit`, `minimize` |
| `shapely.geometry` | `third-party` | 1 | `Polygon` |
| `shapely.geometry.polygon` | `third-party` | 1 | `orient` |
| `shapely.ops` | `third-party` | 1 | `unary_union` |
| `sympy` | `third-party` | 1 | `I`, `Matrix`, `simplify`, `sqrt`, `symbols` |
| `tqdm` | `third-party` | 24 | `tqdm` |

## 3. 缺口与等价实现

### 3.1 旧名已迁移（改一行导入即可，不必找回模块）

| 旧写法 | 等价实现 | 改成 |
|---|---|---|
| `from cst_solver.result import result` | `cst_solver` | `from cst_solver import result` |
| `import metalen as mt` | `tpc_toolkit.effective_medium` | `from tpc_toolkit import effective_medium as mt` |

> `cst_solver.result`：v2.0 起 `cst_solver.result` **不再是子模块**：`result` 是顶层别名（`from cst_solver import result`），旧写法 `from cst_solver.result import result` 会 `ModuleNotFoundError`。⚠️ 这里**刻意不补** `cst_solver/result.py`：一旦存在同名子模块，导入它之后包的 `result` 属性会被**模块对象遮蔽**，反而破坏 `from cst_solver import result`（现有测试断言 `result` 是类）。所以只能改导入行。
> 用到的 notebook：`Leaky/ANT_LEAKY_MK_GRID_opt.ipynb`

> `metalen`：旧的自定义材料计算模块；四个函数在 `tpc_toolkit.effective_medium` 里**同名存在**（含 `ep_cal_air` 的比值公式），只需把导入行换成`from tpc_toolkit import effective_medium as mt`，其余代码不用动。
> 用到的 notebook：`椭圆透镜单元天线/BA/D120/ep_cal.ipynb`

### 3.2 仍未定位的模块

（没有未交代的模块）

## 4. 怎么让旧 notebook 继续跑

旧名（`tri_lib` / `hexlib`）由 `archive/compat/` 下的兼容入口转发到新包。在 notebook 开头加一行即可（**不必改 notebook 正文里的其它代码**）：

```python
import sys
sys.path.append(r'D:\成电博士生涯\自动建模算法尝试\TPC\archive\compat')
import tri_lib   # 旧名仍可用，会发 FutureWarning
```

已迁移到新包、又不想改调用代码的旧名（如 `metalen`），把导入行换成等价模块的别名即可（见 §3.1）。
