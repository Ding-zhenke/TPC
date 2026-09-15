# topo_modeler —— 建模引擎层

`topo_modeler` 是 TPC 的**建模引擎**：它把「一条三角晶格路径（`TopoPath`）+ 一组物理参数」翻译成一个完整的 CST 模型。
向上，它为 `templates/` 提供 `TopoModeler`（智能推断 + 流水线编排）与一组可直接调用的部件构建器；
向下，它只通过 `cst_solver` 的 `setup` 对象下发命令，几何数据全部来自 `mesh_grid.tri_grid.TopoPath`。
包内**不含手写 VBA**（唯一例外见第 8 节 `builders/solver.py` 的高级求解器参数），
它自己不发明坐标、不发明 CST 语法，只负责「顺序、参数、归属」。

| 项 | 内容 |
|---|---|
| **职责** | 把路径 + 参数编排成完整 CST 模型：智能推断模型类型/拓扑相/端口数，按固定顺序调用各部件构建器 |
| **需要 CST** | ✅ 必须（仅真实建模时）。无 CST 环境下 `TopoModeler.app = None` 并给出 warning，路径/参数/推断/预览仍可用 |
| **入口** | `TopoModeler`、`NameManager`（包级导出）；底层入口 `topo_modeler.builders.*` |
| **依赖** | `cst_solver`（CST 会话：`setup`）、`mesh_grid.tri_grid.TopoPath`（几何与坐标） |
| **被谁依赖** | `templates/`（`StraightWaveguide`、`UnitAntenna`） |
| **源码位置** | `topo_modeler/`：`modeler.py`、`name_manager.py`、`builders/`（8 个构建器）、`lens_build.py`、`lens_build_standalone.py`、`tests/` |
| **当前阶段** | 阶段 0–3 已完成（坐标层 / 基础引擎 / 模板层）；**阶段 5（库加固）离线部分完成**；**阶段 6 的透镜几何层已完成并离线验收通过**（`builders/lens.py` + `TopoModeler.build_lens()`）；`GRINLensAntenna` 模板与端到端真机验证未做 |

**公开 API 规模**（AST 统计，2026-09-15）：`TopoModeler` 21 个公开方法，`NameManager` 8 个公开方法，
另有 `builders/` 与两个透镜脚本中的模块级函数（`builders/` 见第 3 节的表）。
`tests/test_lens.py`（36 项）是透镜构建器的**等价性护栏**：把原脚本
`lens_build.py` 原样跑一遍，与库函数逐点/逐条比对。

---

## 1. 它解决什么问题

旧 notebook（`AB_feed.ipynb`、`BA_feed.ipynb`、`Ant3_epc.ipynb`、`Ant1_D_BA_120D.ipynb` …）里，
**每建一个模型都要从头手写一遍同样的东西**：

1. 手写 `px1, py1, px2, py2, …, px6, py6` 的坐标推导（10+ 行），
   并且 `path_points` 与 `(px, py)` 两套坐标要同步维护，改一处漏一处；
2. 手写 `xmax / ymax_up / ymax_dn / xup / yup / ydn` 阵列范围；
3. 手写基板与 VPC 区域的 polyline 顶点列表（各 8+ / 20+ 行）；
4. 手写光子晶体超元胞的 `triangle → add → subtract → rotation → translate` 布尔序列（40+ 行）；
5. 手写馈源（25+ 行）、波导（8 行）、`pick_face` + `add_port`（4 行）；
6. 手写约 40 行求解器 VBA。

一个直波导 notebook 因此长达 **200+ 行**，而且这些代码在**每个** notebook 里重复出现、逐份漂移，
一旦 CST 里报错还找不到是哪个几何步骤错了。

分层之后，同一件事变成：

```python
from templates import StraightWaveguide

StraightWaveguide(topology='AB', length=18, output_path=r'D:\out\wg.cst').build_all().save()
```

**分层买到了什么**：

| 收益 | 说明 |
|---|---|
| 单一数据源 | 路径只写一次（`TopoPath`），直角坐标、CST 表达式、边界框、基板多边形、阵列范围全部自动推导 |
| 可参数化 | 生成的 CST 参数是**表达式**（`p1x='x1*a'`），在 CST 里改 `x1` 路径就变，不必回 Python 重算 |
| 可复现 | 建模步骤是代码而不是鼠标操作，`Rebuild()` 能无错重放历史树 |
| 可组合 | 三种用法（模板 / Modeler / Builder）共用同一套构建器，低层不会被高层绑架 |
| 可测试 | 推断逻辑、参数处理可在**没有 CST** 的环境里跑（`app=None`） |
| 归属清晰 | 「几何在 `TopoPath`、CST 原语在 `cst_solver`、顺序在 `topo_modeler`、器件在 `templates`」，改错地方一眼可辨 |

---

## 2. 架构

### 2.1 模块地图

```
topo_modeler/                    建模引擎层（本包）
├── __init__.py                  导出 TopoModeler / NameManager（__all__ 仅这两项）
├── modeler.py                   TopoModeler —— 智能推断 + 流水线编排（所有模板的基类）
├── name_manager.py              NameManager —— CST 实体命名唯一化
├── builders/                    部件构建器：无状态纯函数 + 显式参数
│   ├── __init__.py              统一导出 14 个符号（含 2 个 intersect_* 辅助函数）
│   ├── substrate.py             基板：带状多边形 → extrude → z 居中
│   ├── vpc_region.py            VPC-A / VPC-B 区域 + 与基板求交
│   ├── crystal.py               光子晶体三角孔阵列（超元胞，核心）
│   ├── feed.py                  馈源 3 型：ab_elliptical / ba_tapered / cylinder
│   ├── waveguide.py             空心矩形波导：外方体 − 内方体
│   ├── lens.py                  GRIN 椭圆透镜：纯几何 + DXF + CST 步骤（阶段 6）
│   ├── port.py                  波导端口：面编号 / 直波导 2 端口 / 天线 1 端口
│   └── solver.py                时域求解器 + 监视器 + 高级参数
├── tests/test_lens.py           透镜构建器回归：与原脚本 lens_build.py 逐点/逐条等价
├── lens_build.py                GRIN 透镜建模**脚本**（notebook 用 exec 复用；库侧已收编为 builders/lens.py）
└── lens_build_standalone.py     GRIN 透镜工程的独立驱动脚本（实验沙盒，供 subprocess 启动）
```

### 2.2 三个使用层次

| 层次 | 入口 | 谁在用 | 控制粒度 |
|---|---|---|---|
| **模板层** | `templates.StraightWaveguide` / `UnitAntenna` | 日常建模型（一个类 = 一个器件） | 只填参数：`topology`、`length`、`output_path` … |
| **Modeler 层** | `TopoModeler` | 新器件、非标准路径、需要分步调试 | 逐步骤调用（`build_substrate()` → `build_crystal()` → …），或 `build_all()` 一键 |
| **Builder 层** | `topo_modeler.builders.*` | 需要完全自定义几何顺序、或只想复用某一个部件 | 直接给 `app` + 显式参数，**不需要** `TopoModeler` 实例 |

### 2.3 依赖方向（严格单向）

```
templates/ ──────────▶ topo_modeler/ ──┬──▶ cst_solver/ ──▶ cst（CST 自带）
   （应用层）             （引擎层）      │      （基础层）
                                      └──▶ mesh_grid.tri_grid（TopoPath，晶格/坐标）

tpc_toolkit/  独立工具层：不依赖 CST，也不被本包依赖
```

- 本包**只依赖** `cst_solver` 与 `mesh_grid.tri_grid`，**不依赖** `templates`；
- 同层之间 `cst_solver` 与 `mesh_grid` 互不依赖；
- 本包**不写手写 VBA**：所有 CST 操作都通过 `app.*` 方法下发，唯一的例外是
  `builders/solver.py` 里 `cst_solver` 未封装的求解器高级参数（`SteadyStateLimit` / `ParallelizationThreads` / `GPUAcceleration` / Farfield 监视器）。

---

## 3. 模块地图

| 文件 | 主要符号 | 职责 | 公开方法/函数数 |
|---|---|---|---|
| `__init__.py` | `TopoModeler`、`NameManager` | 包级导出（`__all__` 仅两项） | 0（纯 re-export） |
| `modeler.py` | `TopoModeler` | 智能推断（模型类型 / 拓扑相 / 监视器 / 端口数）+ 流水线编排 + 端到端 / 保存 / 运行 / 关闭 / 预览 / 验收 | 21 |
| `name_manager.py` | `NameManager` | CST 实体命名唯一化、别名、按部件取名 | 8 |
| `builders/__init__.py` | 21 个导出符号 | 统一导出全部构建器，供 `from topo_modeler.builders import …` | 0（纯 re-export） |
| `builders/substrate.py` | `build_substrate` | 沿路径生成带状基板并 z 居中 | 1 |
| `builders/vpc_region.py` | `build_vpc_regions`、`intersect_vpc_with_substrate` | 生成 VPC-A（上半区）/ VPC-B（下半区）并可与基板求交 | 2 |
| `builders/crystal.py` | `build_topological_crystal`、`intersect_crystal_with_vpc` | 三角孔超元胞阵列（最核心的重复代码：25 行 → 1 个函数），并可与 VPC 求交 | 2 |
| `builders/feed.py` | `build_feed`、`build_ab_elliptical_feed`、`build_ba_tapered_feed`、`build_cylinder_feed` | 3 种馈源几何（统一入口 + 3 个具体实现） | 4 |
| `builders/waveguide.py` | `build_waveguide` | 空心矩形波导（外方体 − 内方体） | 1 |
| `builders/lens.py` | `GrinLensSpec`、`GrinLensHoles`、`LensGeometryError`、`grin_lens_spec_from_cst_params`、`build_grin_lens_holes`、`build_grin_lens` | **GRIN 椭圆透镜**（阶段 6）：纯几何层（孔心 / 孔半径 / 孔多边形 / DXF / 三道自查，**不依赖 CST**）+ CST 建模层（导入 → 镜像 → 椭圆减孔 → 楔形裁剪 → 平移 → 旋转×6） | 6 |
| `builders/port.py` | `add_waveguide_port`、`add_ports_for_straight_waveguide`、`add_port_for_antenna` | 在指定面上添加波导端口（当前面编号硬编码，见第 8 节） | 3 |
| `builders/solver.py` | `configure_solver`（另有私有 `_configure_solver_advanced`、`_get_monitor_frequencies`） | 频率范围 + 时域求解器 + 监视器 + 高级参数 | 1 |
| `tests/test_lens.py` | 36 项用例 | 透镜构建器回归：把 `lens_build.py` **原样跑一遍**，与库函数逐点（孔心/孔半径/椭圆参数）+ 逐条（CST 调用序列）比对 | — |
| `lens_build.py` | `hex_pts`（另有私有 `_poly_xy`） | GRIN 椭圆透镜的**原始脚本**：孔阵列生成 → DXF → 导入 CST → 镜像 → 椭圆−孔 → 楔形裁剪 → 旋转×6。**逻辑已收编进 `builders/lens.py`**，本文件保留供 notebook `exec` 复用 | 1 |
| `lens_build_standalone.py` | `log`、`cst_log` | 独立驱动脚本：复制模板 → 登参数 → `exec lens_build.py` → 导出 `.sab` → 保存（实验沙盒，**不可 `import`**） | 2 |

> 两个透镜文件的「函数」是**脚本级辅助函数**，不是库 API：`lens_build.py` 依赖调用方命名空间里的
> `app / cst_log / _m3 / a / h / R_big`，`lens_build_standalone.py` 是一段脚本（import 即执行整条建模流程）。

---

## 4. TopoModeler —— 智能推断与流水线

`TopoModeler` 是本包的门面：它持有 `TopoPath`、拓扑相、参数字典与 `NameManager`，
并根据**路径形状**自动推断出整条流水线需要的关键选择项。

### 4.1 智能推断规则

推断的输入只有一个：`TopoPath` 的点数（`len(path)`）。

| 路径特征 | `model_type` | `topology` | `monitors` | 端口数 | `feed_type` |
|---|---|---|---|---|---|
| 直线（≤ 2 个晶格点，`path.is_straight()`） | `waveguide` | `AB` | `('E',)` | 2 | `ab_elliptical` |
| 有拐弯（> 2 个晶格点，`path.has_bend()`） | `antenna` | `BA` | `('E','Farfield')` | 1 | `ba_tapered` |

实现位置与覆盖方式：

| 推断项 | 推断方法 | 何时生效 | 如何覆盖 |
|---|---|---|---|
| `model_type` | `_infer_model_type()` | `set_path()` 时 | 不可直接覆盖（重新 `set_path` 另一条路径） |
| `topology` | `_infer_topology()` | `set_path()` 时**仅当 `self.topology is None`** | `set_topology('AB'/'BA')`，或 `build_crystal(topology=…)` |
| `monitors` | `_infer_monitors()` | `configure_solver(monitors=None)` 时 | `configure_solver(monitors=('E','Farfield'))` |
| 端口数 | `_infer_ports()` | 仅供文档/约定使用，`add_ports()` 内部按 `model_type` 分支 | 由 `model_type` 决定（当前无参数可覆盖） |
| `feed_type` | `build_feed()` 内部 | `feed_type is None` 时 | `build_feed(feed_type='cylinder')` |

> 注意：`set_topology()` 只接受 `'AB'` / `'BA'`，其它值抛 `ValueError`。
> 由于拓扑相只在「尚未设置」时自动推断，**先 `set_topology` 再 `set_path`** 或**先 `set_path` 再 `set_topology`** 都可以，
> 后者会覆盖推断值。

### 4.2 方法表（21 个公开方法）

配置类：

| 方法 | 签名 | 说明 | 返回 |
|---|---|---|---|
| `set_path` | `set_path(path)` | 设置 `TopoPath`，自动推断 `model_type`（并按需推断 `topology`） | `self` |
| `set_topology` | `set_topology(topology)` | 设置拓扑相，仅 `'AB'` / `'BA'`，其它抛 `ValueError` | `self` |
| `set_parameters` | `set_parameters(params)` | 批量：写入 `self.params` 并调用 `app.set_parameters(params)` | `self` |
| `set_parameter` | `set_parameter(name, value)` | 单个：写入 `self.params` 并调用 `app.para(name, value)` | `self` |

流水线类（按顺序调用 builders；除 `configure_solver` 外都需要先 `set_path`，否则抛 `RuntimeError`）：

| 方法 | 签名（默认值照抄源码） | 说明 | 返回 |
|---|---|---|---|
| `build_substrate` | `build_substrate(name='substrate', height='h', material='Silicon (lossy)', y_margin='e2')` | 基板，记入 `_built_parts['substrate']` | `str`（CST 名） |
| `build_vpc_regions` | `build_vpc_regions(name_prefix='vpc', height='h', material='Silicon (lossy)', y_margin='e2')` | VPC-A / VPC-B 区域，记入 `vpca` / `vpcb` | `(str, str)` |
| `build_crystal` | `build_crystal(topology=None, lattice='a', height='h', large_hole='l1', small_hole='l2', y_margin='e2')` | 光子晶体阵列；`topology=None` 时用 `self.topology`（再退到 `'AB'`） | `(str, str)` |
| `build_feed` | `build_feed(feed_type=None, name=None, **params)` | 馈源；`feed_type=None` 时按 `model_type` 推断 | `str` |
| `build_waveguide` | `build_waveguide(name='wg1', material='Copper (annealed)', **params)` | 空心矩形波导 | `str` |
| `build_lens` | `build_lens(spec=None, dxf_path=None, name='lens_epc', component='gridlens', material='Silicon (lossy)', height='h', **lens_kwargs)` | **GRIN 椭圆透镜**（阶段 6）：算几何 → 落 DXF → 调 CST 步骤；记入 `_built_parts['lens']`。`spec=None` 时用 `lens_kwargs` 现拼（接受 `lens_ratio` / `lens_Nx` / `R_big` 等旧名） | `dict` |
| `add_ports` | `add_ports(auto=True, waveguide_name=None, **params)` | 端口；`waveguide_name=None` 时取 `_built_parts['waveguide']`，再退到 `'wg1'` | `list`（端口号） |
| `configure_solver` | `configure_solver(freq_range=(300, 380), monitors=None, **kwargs)` | 求解器；`monitors=None` 时自动推断 | `None` |
| `integrate` | `integrate()` | **保留接口**：基础整合已由各 builder 内部完成，当前函数体为 `pass` | `None` |

端到端与运行类：

| 方法 | 签名 | 说明 | 返回 |
|---|---|---|---|
| `build_all` | `build_all(freq_range=(300, 380), include_feed=True, include_waveguide=True, include_ports=True, **kwargs)` | 顺序执行：基板 → VPC → 晶体 → 馈源 → 波导 → 端口 → 求解器 → `integrate()` | `self` |
| `save` | `save(path)` | `app.save(path)` 并记录 `self._cst_path` | `self` |
| `run` | `run()` | `app.run()`；守卫层会在提交前拦「参数改过但历史没重建」（陷阱 T2） | `self` |
| `validate` | `validate()` | 转发 `app.validate_model()`（读 `get_messages()` + `Rebuild()`）；无 CST 时返回说明性的 error 字典 | `dict` |
| `close` | `close()` | `app.close()`（**先 save 再 close**，陷阱 T15）；支持 `with TopoModeler(...) as m:` | `self` |
| `preview` | `preview(ax=None, show_grid=True)` | 委托 `path.preview(...)`（matplotlib，不需要 CST） | `(fig, ax)` |
| `read_results` | `read_results()` | **未实现**：抛 `NotImplementedError`（阶段 7，`ResultReader`） | — |
| `plot_results` | `plot_results()` | **未实现**：抛 `NotImplementedError`（阶段 7） | — |
| `get_built_parts` | `get_built_parts()` | 返回已构建部件名典的**副本** | `dict` |

非公开成员（仅供理解内部行为）：`__init__(template_cst='tmp.cst')`、`_init_cst()`、
`_infer_model_type()`、`_infer_topology()`、`_infer_monitors()`、`_infer_ports()`、
`_check_path()`、`_mark_geometry()`、`__repr__()`。

**`build_all()` 的关键字透传分组**（每个都对应一个 builder 的参数）：

| 关键字 | 传给 |
|---|---|
| `substrate_kw` | `build_substrate` |
| `vpc_kw` | `build_vpc_regions` |
| `crystal_kw` | `build_crystal`（可传 `topology=`） |
| `feed_kw` | `build_feed` |
| `waveguide_kw` | `build_waveguide` |
| `port_kw` | `add_ports` |
| `solver_kw` | `configure_solver` |

> ⚠ `modeler.build_vpc_regions()` **没有** `topology` 参数，`modeler.build_crystal()` **没有** `xup/yup/ydn` 参数
> （见第 8 节缺陷 (c)(d)）。要指定阵列范围或拓扑相，请走 Builder 层。

**`_built_parts` 的键**（`get_built_parts()` 返回它）：

`substrate`、`vpca`、`vpcb`、`crystal_a`、`crystal_b`、`feed`、`waveguide`、`ports`、`solver = True`。

### 4.3 端到端示例

```python
from topo_modeler import TopoModeler
from mesh_grid.tri_grid import TopoPath

# 1. 直线路径（2 个晶格点）→ 自动推断为 waveguide + AB + ('E',) + 2 端口 + ab_elliptical
path = TopoPath.builder(a=0.2425, name='p').start(0, -1).move(19, 'c').build()

modeler = TopoModeler(template_cst=r'D:\work\tmp.cst')
modeler.set_path(path)
print(modeler)                      # TopoModeler(type=waveguide, topology=AB, path=2pts, built=[none])

# 2. 物理参数（会同时写入 CST 参数表）
modeler.set_parameters({
    'a': 0.2425, 'h': 0.25,
    'l1': 0.65 * 0.2425, 'l2': 0.35 * 0.2425,
    'e1': 0.2425 / 2, 'e2': 0.2425 * (3 ** 0.5) / 2,
})

# 3. 分步构建（想调试就一步一步来；也可以用 modeler.build_all() 一次到底）
modeler.build_substrate()                       # → 'substrate'
modeler.build_vpc_regions()                     # → ('vpc_A', 'vpc_B')
modeler.build_crystal()                         # → ('g1A', 'g1B')：由 topology 推断决定大小孔分配
modeler.build_feed()                            # → 'feed1'（waveguide → ab_elliptical）
modeler.build_waveguide()                       # → 'wg1'
modeler.add_ports()                             # → [1, 2]
modeler.configure_solver(freq_range=(300, 380)) # monitors 自动推断为 ('E',)

modeler.save(r'D:\out\waveguide.cst')
# modeler.run()                                 # 运行仿真
```

拐弯路径会自动变成天线：

```python
path = (TopoPath.builder(a=0.2425, name='p')
        .start(0, -1).move(19, 'c')     # 直段
        .turn(120).move(15, 'along')    # 臂
        .build())

modeler = TopoModeler(template_cst=r'D:\work\tmp.cst').set_path(path)
# → model_type='antenna'，topology='BA'，monitors=('E','Farfield')，1 端口，feed_type='ba_tapered'
```

---

## 5. NameManager —— 命名管理

### 5.1 为什么 CST 里的实体名必须唯一且有意义

- **布尔运算按名字引用实体**：`app.subtract('wg1', 'wg1_1')` 靠名字定位，重名会让第二步操作的对象错位，
  而 CST **不一定**报错 —— 错误会以「几何不对」的形式延迟暴露。
- **历史树可读性**：`feed_1 / crystal_A / wg_2` 一眼能对上几何；`Solid1 / Solid2 / Solid17` 在几百个三角孔面前完全不可读。
- **多端口/多馈源结构**：直波导要镜像出第二组馈源与波导，天线可能带辐射体；序号必须稳定可预期。
- **结果读取与后处理**：端口号、实体名是后续读取 S 参数、远场的寻址键（阶段 5 会依赖它）。

`NameManager` 把「唯一化」这件事集中到一个对象上：计数器按前缀独立累加，别名表用于「同一个实体的多个称呼」。

### 5.2 API（8 个公开方法）

| 方法 | 签名 | 说明 | 示例返回 |
|---|---|---|---|
| `get` | `get(prefix)` | 生成唯一名 `prefix_N`（同前缀从 1 递增） | `get('feed')` → `'feed_1'`；再次 → `'feed_2'` |
| `alias` | `alias(name, alias_name)` | 给已有名字注册别名 | `alias('substrate_1', 'sub')` |
| `resolve` | `resolve(name)` | 别名 → 原名；不是别名则原样返回 | `resolve('sub')` → `'substrate_1'` |
| `get_feed` | `get_feed(idx=1)` | 探针名（多端口用） | `'feed_1'` |
| `get_waveguide` | `get_waveguide(idx=1)` | 波导名 | `'wg_1'` |
| `get_port` | `get_port(idx=1)` | 端口名 | `'port_1'` |
| `get_crystal` | `get_crystal(side='A')` | 光子晶体阵列名 | `'crystal_A'` / `'crystal_B'` |
| `reset` | `reset()` | 清空计数器与别名表 | — |

另有 `__init__()` 与 `__repr__()`（`NameManager(generated=N, aliases=M)`）。

```python
from topo_modeler import NameManager

nm = NameManager()
nm.get('feed')            # 'feed_1'
nm.get('feed')            # 'feed_2'  ← 同前缀自动递增，绝不复用
nm.get_waveguide(1)       # 'wg_1'
nm.get_port(2)            # 'port_2'
nm.get_crystal('A')       # 'crystal_A'

nm.alias('substrate_1', 'sub')
nm.resolve('sub')         # 'substrate_1'
nm.resolve('wg_1')        # 'wg_1'（非别名，原样返回）

nm.reset()                # 计数器与别名表清空
print(nm)                 # NameManager(generated=0, aliases=0)
```

> 现状说明：`TopoModeler` 会创建一个 `self.nm = NameManager()`，但当前流水线里各 builder 均使用**显式名字**
> （`'substrate'`、`'vpc_A'`、`'feed1'`、`'wg1'` …）。`NameManager` 目前主要供模板（`templates/` 里同样
> `self.nm = NameManager()`）与后续多端口场景使用。

---

## 6. builders/ —— 部件构建器

### 6.0 设计约定

- **无状态纯函数**：所有 `builders/*` 都是模块级函数，第一个参数是 CST 会话对象 `app`（`cst_solver.setup` 实例），
  其余参数**全部显式**给出（几何尺寸是 CST 表达式字符串，如 `'e2/2+wg_b/2+wg_t'`）。
- **可脱离 `TopoModeler` 单独调用**：这是**有意的设计属性**（不是巧合）——
  `TopoModeler` 只是这些函数的编排器，Builder 层不反向依赖它。
- **几何只来自 `TopoPath` 与参数表达式**：不硬编码 mm 数值，参数在 CST 里仍可调。
- **依赖 `TopoPath` 的三个函数**：`build_substrate`、`build_vpc_regions`、`build_topological_crystal`
  需要 `path` 参数；其余（feed / waveguide / port / solver）与路径无关。

### 6.1 `builders/substrate.py` —— 基板

**作用**：沿路径生成一条「上下一各扩 `y_margin`」的带状多边形，拉伸成体并沿 z 居中，得到基板。

```python
def build_substrate(app, path, name='substrate', height='h',
                    material='Silicon (lossy)', y_margin='e2', component='component1')
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `app` | `setup` | — | `cst_solver.setup` 实例 |
| `path` | `TopoPath` | — | 路径的唯一数据源 |
| `name` | `str` | `'substrate'` | 基板实体名（拉伸体用它，曲线用 `f'{name}_curve'`） |
| `height` | `str \| float` | `'h'` | 基板厚度（z 方向），CST 参数表达式 |
| `material` | `str` | `'Silicon (lossy)'` | 材料 |
| `y_margin` | `str` | `'e2'` | 路径上下扩展量（基板半宽） |
| `component` | `str` | `'component1'` | 归属组件 |

**内部调用链**：
`path.auto_define_cst_params(app, prefix='p')`（在 CST 里定义 `p1x,p1y,…`）
→ `path.build_substrate_polygon(y_margin='e2', prefix='p')`（生成带状多边形顶点）
→ `app.polyline(pts, name='substrate_curve', curve='curve1')`
→ `app.extrude('curve1:substrate_curve', name='substrate', thickness='h', component=…, material=…)`
→ `app.translate('substrate', ['0','0','-h/2'], component=…, log_flag=1)`（把 z 中心挪到 0）

**返回值**：`str` —— 基板实体名（= `name`）。

```python
from topo_modeler.builders import build_substrate

build_substrate(app, path, name='my_sub', y_margin='e2')   # → 'my_sub'
```

> ✅ 已修：`build_substrate_polygon` 现在保证**逆时针（CCW）**绕向，实体与晶体在 z 上对齐（见第 8 节 (a)(b)）。

### 6.2 `builders/vpc_region.py` —— VPC 区域

**作用**：沿路径生成两个区域 —— VPC-A 为路径**上半区**（含路径），VPC-B 为路径**下半区**（含路径），
各自拉伸成体并 z 居中；另提供一个可选的「与基板求交」辅助函数。

```python
def build_vpc_regions(app, path, name_prefix='vpc', height='h',
                      material='Silicon (lossy)', y_margin='e2', component='component1')

def intersect_vpc_with_substrate(app, substrate_name, vpca_name, vpcb_name,
                                 component='component1')
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `app` | `setup` | — | CST 会话 |
| `path` | `TopoPath` | — | 路径 |
| `name_prefix` | `str` | `'vpc'` | 名称前缀 → `vpc_A` / `vpc_B` |
| `height` | `str \| float` | `'h'` | 区域厚度 |
| `material` | `str` | `'Silicon (lossy)'` | 材料 |
| `y_margin` | `str` | `'e2'` | 上下区域的扩展量 |
| `component` | `str` | `'component1'` | 归属组件 |

| `intersect_*` 参数 | 说明 |
|---|---|
| `substrate_name` | 基板实体名 |
| `vpca_name` / `vpcb_name` | 待裁剪的 VPC 区域名 |
| `component` | 两侧实体所属组件 |

**内部调用链**（A、B 各一遍）：
`path.auto_define_cst_params(app, prefix='p')` → `path.build_vpc_area_polygon(side='upper'|'lower', y_margin=…, prefix='p')`
→ `app.polyline(...)` → `app.extrude(f'curve1:{name}_curve', name, thickness=height, …)`
→ `app.translate(name, ['0','0','-h/2'], …)`。

`intersect_vpc_with_substrate` 则是两次 `app.intersect(substrate, vpc_x, component1=…, component2=…)`。

**返回值**：`build_vpc_regions` → `(vpca_name, vpcb_name)`；`intersect_vpc_with_substrate` → `(vpca_name, vpcb_name)`（相交后名字不变）。

```python
from topo_modeler.builders import build_vpc_regions, intersect_vpc_with_substrate

vpca, vpcb = build_vpc_regions(app, path)          # → ('vpc_A', 'vpc_B')
intersect_vpc_with_substrate(app, 'substrate', vpca, vpcb)
```

> 注意 `app.intersect("A","B")` 的语义：结果留在 **A**，B 被消耗（见 `docs/ARCHITECTURE.md` §6）。
> 缺陷：`side='lower'` 的多边形为**顺时针**，与晶体在 z 上差一个 `h`（见第 8 节 (a)）。

### 6.3 `builders/crystal.py` —— 光子晶体三角孔阵列（核心）

**作用**：构建拓扑光子晶体三角孔阵列并生成 VPC-A / VPC-B 两套实体 —— 这是旧代码里最核心、
重复最多的一块（25 行 → 1 个函数）。拓扑相决定「大孔 / 小孔」在上下朝向之间如何分配。

```python
def build_topological_crystal(app, path, topology='AB', lattice='a', height='h',
                              large_hole='l1', small_hole='l2', y_margin='e2',
                              component='component1', name_prefix='g')

def intersect_crystal_with_vpc(app, crystal_a_name, crystal_b_name,
                               vpca_name, vpcb_name, component='component1')
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `app` | `setup` | — | CST 会话 |
| `path` | `TopoPath` | — | 用于推断阵列范围 `xup, yup, ydn` |
| `topology` | `str` | `'AB'` | `'AB'` / `'BA'`，其它值抛 `ValueError` |
| `lattice` | `str` | `'a'` | 晶格常数参数名 |
| `height` | `str` | `'h'` | 硅片厚度参数名 |
| `large_hole` | `str` | `'l1'` | 大孔边长参数名 |
| `small_hole` | `str` | `'l2'` | 小孔边长参数名 |
| `y_margin` | `str` | `'e2'` | Y 方向阵列步长参数（步长 = `y_margin*2`） |
| `component` | `str` | `'component1'` | 归属组件 |
| `name_prefix` | `str` | `'g'` | 名称前缀 → `g1A` / `g1B` |

**拓扑相 → 孔尺寸分配**：

| `topology` | `hole_sizes` | VPC-A（朝上 / 朝下） | VPC-B（朝上 / 朝下） |
|---|---|---|---|
| `'AB'` | `['l1','l2']` | 大孔 / 小孔 | 小孔 / 大孔 |
| `'BA'` | `['l2','l1']` | 小孔 / 大孔 | 大孔 / 小孔 |

**超元胞逻辑**（与旧 notebook 逐行一致）：

1. `triangle × 8`（VPC-A×4 + VPC-B×4，朝上 / 朝下各 2）
2. `add × 4`（合并同区域的三角孔：两个大三角形、两个小三角形）
3. `subtract × 2`（从大三角形中减去小三角形 → 得到三角孔）
4. `rotation × 2`（120° 旋转复制 2 次 → 6 个孔的超元胞）
5. `translate × 6`（X 方向 `a` + Y+ 方向 `e2*2` 共 `yup/2` 次 + Y− 方向 `-e2*2` 共 `ydn/2` 次）

**超元胞中心位置**（与旧代码完全一致，注意 z 已含 `-h/2`）：

| 朝向 | `center` | `theta` |
|---|---|---|
| 朝上（边长 `a` 的大三角形 / `up_hole` 的小三角形） | `['-a/2', 'sqr(3)/2*a-a/sqr(3)', '-h/2']` | `[0, 0, 0]` |
| 朝下（旋转 180°） | `['0', 'a/sqr(3)', '-h/2']` | `[0, 0, 180]` |

**每个区域的实际调用顺序**（`A`、`B` 各一遍）：

```
app.triangle(lattice, height, center=center_up, theta=[0,0,0],   name='g1A',      curve='curve1')
app.triangle(lattice, height, center=center_dn, theta=[0,0,180], name='g2A',      curve='curve1')
app.triangle(up_hole, height, center=center_up, theta=[0,0,0],   name='tri_up_A', curve='curve1')
app.triangle(dn_hole, height, center=center_dn, theta=[0,0,180], name='tri_dn_A', curve='curve1')
app.add('g1A', 'g2A')                       # 合并两个大三角形
app.add('tri_up_A', 'tri_dn_A')             # 合并两个小三角形
app.subtract('g1A', 'tri_up_A')            # 大 − 小 = 三角孔
app.rotation('g1A', angle=[0,0,120], repetition=2, copy=True, unite=True, log_flag=1)
app.translate('g1A', [lattice, '0', '0'],  repetitions='int({xup})',   copy=True, unite=True, log_flag=1)
app.translate('g1A', ['0', '{y_margin}*2', '0'],  repetitions='int({yup}/2)', copy=True, unite=True, log_flag=1)
app.translate('g1A', ['0', '-{y_margin}*2', '0'], repetitions='int({ydn}/2)', copy=True, unite=True, log_flag=1)
```

**返回值**：`build_topological_crystal` → `(crystal_a_name, crystal_b_name)`（`'g1A'`, `'g1B'`）；
`intersect_crystal_with_vpc` → `(crystal_a_name, crystal_b_name)`（相交后名字不变）。

```python
from topo_modeler.builders import build_topological_crystal, intersect_crystal_with_vpc

ca, cb = build_topological_crystal(app, path, topology='AB')
# → ('g1A', 'g1B')
intersect_crystal_with_vpc(app, ca, cb, 'vpc_A', 'vpc_B')
```

> 缺陷：阵列范围只能由 `path.get_array_range()` 推断，宽基板覆盖不全；当前**不能**传 `xup/yup/ydn`（见第 8 节 (c)）。

### 6.4 `builders/feed.py` —— 馈源（3 种类型）

**作用**：提供 3 种馈源几何，统一由 `build_feed` 按 `feed_type` 分发。
所有几何尺寸都写成 CST 参数表达式，可在 CST 里参数化调整。

统一入口：

```python
def build_feed(app, feed_type='ab_elliptical', name=None, **kwargs)
```

| `feed_type` | 实际调用 | `name` 默认 |
|---|---|---|
| `'ab_elliptical'` | `build_ab_elliptical_feed(app, name=…)` | `'feed1'` |
| `'ba_tapered'` | `build_ba_tapered_feed(app, name=…)` | `'feed2'` |
| `'cylinder'` | `build_cylinder_feed(app, name=…)` | `'cylinder_feed'` |

其它取值抛 `ValueError("未知馈源类型 …")`。

#### 6.4.1 `build_ab_elliptical_feed` —— AB 型椭圆探针

```python
def build_ab_elliptical_feed(app, name='feed1', material='Silicon (lossy)')
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `app` | `setup` | — | CST 会话 |
| `name` | `str` | `'feed1'` | 馈源实体名（附属实体为 `{name}_epc`、`{name}_cut1`） |
| `material` | `str` | `'Silicon (lossy)'` | 材料 |

**依赖的 CST 参数**（需提前定义）：`x0, e1, e2, wf1, lf1, lf2, h`。

**几何要点**：9 顶点 polyline（含闭合），上半部分为**不对称**渐变；椭圆过渡圆柱切掉右半、保留**左半椭圆**；
**无**优化块。

**内部调用链**：
`app.polyline(9顶点, name=name)` → `app.extrude('curve1', name, 'h', material=…)`
→ `app.create_elliptical_cylinder(name=f'{name}_epc', x_radius='lf2', y_radius='wf1/2', height='h', axis='z')`
→ `app.square(0, 'lf2', '-wf1/2', 'wf1/2', 0, 'h', name=f'{name}_cut1')`（矩形切割）
→ `app.subtract(f'{name}_epc', f'{name}_cut1')`
→ `app.translate(f'{name}_epc', ['-(lf1)', 'e2/2', '0'])`
→ `app.add(name, f'{name}_epc')`
→ `app.translate(name, ['0','0','-h/2'])`（z 居中）

**返回值**：`str`（= `name`）。

#### 6.4.2 `build_ba_tapered_feed` —— BA 型对称渐变探针

```python
def build_ba_tapered_feed(app, name='feed2', material='Silicon (lossy)', add_optimizer=True)
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `app` | `setup` | — | CST 会话 |
| `name` | `str` | `'feed2'` | 馈源实体名（附属：`{name}_epc`、`{name}_cut1`、`{name}_opt1`） |
| `material` | `str` | `'Silicon (lossy)'` | 材料 |
| `add_optimizer` | `bool` | `True` | 是否追加 `tx1×ty1` 优化块 |

**依赖的 CST 参数**：`x01, e1, e2, wf2, lf4, lf5, h, tx1, ty1`。

**几何要点**：10 顶点 polyline（含闭合），上下**对称**渐变；左半椭圆过渡；可选 `tx1×ty1` 优化块。

**内部调用链**：与 AB 型同构（`polyline(10顶点)` → `extrude` → `create_elliptical_cylinder` →
`square` 切割 → `subtract` → `translate(椭圆定位 ['-(lf4)','0','0'])` → `add` → `translate(-h/2)`），
末尾按需追加：`app.para('tx1', 0.2)`、`app.para('ty1', 0.6)` →
`app.square('-tx1/2','tx1/2','-ty1/2','ty1/2','-h/2','h/2', name=f'{name}_opt1', material=…)` → `app.add(name, f'{name}_opt1')`。

**返回值**：`str`（= `name`）。

#### 6.4.3 `build_cylinder_feed` —— 圆柱辐射体

```python
def build_cylinder_feed(app, name='cylinder_feed', radius='r_cyl', height='h',
                        material='Silicon (lossy)', position=None)
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `app` | `setup` | — | CST 会话 |
| `name` | `str` | `'cylinder_feed'` | 实体名 |
| `radius` | `str \| float` | `'r_cyl'` | 圆柱半径（`x_radius = y_radius = radius`，等半径） |
| `height` | `str \| float` | `'h'` | 圆柱高度 |
| `material` | `str` | `'Silicon (lossy)'` | 材料 |
| `position` | `list \| None` | `None` | 平移向量 `[dx, dy, dz]`，`None` 则不平移 |

**内部调用链**：`app.create_elliptical_cylinder(name=name, x_radius=radius, y_radius=radius, height=height, axis='z', material=…)`
→（可选）`app.translate(name, position, copy=False, unite=False, log_flag=1)`。**无 polyline、无椭圆过渡、无优化块。**

**返回值**：`str`（= `name`）。

#### 6.4.4 三种馈源对比

| 类型 | 对应旧代码 | polyline 顶点 | 椭圆过渡 | 优化块 | 适用场景 |
|---|---|---|---|---|---|
| `ab_elliptical` | `feed1` | 9（上半不对称） | 有（左半椭圆） | 无 | 直波导 |
| `ba_tapered` | `feed2` | 10（上下对称） | 有（左半椭圆） | 有（`tx1×ty1`） | 天线 |
| `cylinder` | `cylinder_antenna` | 无 | 无（等半径圆柱） | 无 | 辐射体 |

```python
from topo_modeler.builders import build_feed

build_feed(app, feed_type='ab_elliptical', name='feed1')                       # → 'feed1'
build_feed(app, feed_type='ba_tapered', name='feed2', add_optimizer=True)      # → 'feed2'
build_feed(app, feed_type='cylinder', name='rad1', radius=0.3,
           position=['1.0', '2.0', '-h/2'])                                    # → 'rad1'
```

### 6.5 `builders/waveguide.py` —— 空心矩形波导

**作用**：外方体 − 内方体 = 空心矩形波导（默认铜材质），复现旧代码 `AB_feed` cell 13 的几何。

```python
def build_waveguide(app, name='wg1', material='Copper (annealed)',
                    x_min='-lf1-lf2-lf3', x_max='-lf1',
                    y_center='e2/2', wg_b='wg_b', wg_a='wg_a', wg_t='wg_t')
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `app` | `setup` | — | CST 会话 |
| `name` | `str` | `'wg1'` | 外方体名（内方体自动为 `f'{name}_1'`） |
| `material` | `str` | `'Copper (annealed)'` | 波导材料 |
| `x_min` | `str` | `'-lf1-lf2-lf3'` | 波导 x 起点（CST 表达式） |
| `x_max` | `str` | `'-lf1'` | 波导 x 终点 |
| `y_center` | `str` | `'e2/2'` | 波导 y 中心 |
| `wg_b` | `str` | `'wg_b'` | 波导窄边尺寸（y 方向**内宽**） |
| `wg_a` | `str` | `'wg_a'` | 波导宽边尺寸（z 方向**内高**） |
| `wg_t` | `str` | `'wg_t'` | 壁厚 |

**依赖的 CST 参数**：`lf1, lf2, lf3, e2, wg_a, wg_b, wg_t`。

**几何**：

- 内方体 `{name}_1`：`y ∈ [e2/2 - wg_b/2, e2/2 + wg_b/2]`，`z ∈ [-wg_a/2, +wg_a/2]`；
- 外方体 `{name}`：在内外两侧各加一个壁厚 `wg_t` ——
  `y ∈ [e2/2 - wg_b/2 - wg_t, e2/2 + wg_b/2 + wg_t]`，`z ∈ [-wg_a/2 - wg_t, +wg_a/2 + wg_t]`；
- 两者 x 范围相同（`x_min … x_max`）。

**内部调用链**：
`app.square(x_min, x_max, 'y_center-wg_b/2', 'y_center+wg_b/2', '-wg_a/2', '+wg_a/2', f'{name}_1', 'component1', material)`
→ `app.square(x_min, x_max, 'y_center-wg_b/2-wg_t', 'y_center+wg_b/2+wg_t', '-wg_a/2-wg_t', '+wg_a/2+wg_t', name, 'component1', material)`
→ `app.subtract(name, f'{name}_1', 'component1')`。

**返回值**：`str`（= `name`）。

```python
from topo_modeler.builders import build_waveguide

build_waveguide(app, name='wg1')                       # → 'wg1'（内方体 'wg1_1' 已被减掉）
build_waveguide(app, name='wg2', x_min='0', x_max='lf3')  # 自定义 x 范围
```

### 6.6 `builders/port.py` —— 波导端口

**作用**：在指定 solid 的指定面上 `pick_face` + `add_port`，并提供「直波导 2 端口」与「天线 1 端口」两个便捷入口。

```python
def add_waveguide_port(app, solid_name, port_number, face_id,
                       full_deembedding=False, consider_material_inside=False)

def add_ports_for_straight_waveguide(app, waveguide_name='wg1',
                                     port1_face='10', port2_face='22')

def add_port_for_antenna(app, waveguide_name='wg1', port_face='10')
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `app` | `setup` | — | CST 会话 |
| `solid_name` / `waveguide_name` | `str` | — / `'wg1'` | 目标 solid 名 |
| `port_number` | `int` | — | 端口号（1, 2, …） |
| `face_id` / `port1_face` / `port2_face` / `port_face` | `str` | `'10'` / `'22'` / `'10'` | CST 面编号 |
| `full_deembedding` | `bool` | `False` | 是否完全去嵌入 |
| `consider_material_inside` | `bool` | `False` | 是否考虑内部材料 |

> ⚠ 注意：`full_deembedding` 与 `consider_material_inside` 当前**只出现在签名与 docstring 中**，
> 函数体内并未使用它们（函数体只有 `app.pick_face(...)` + `app.add_port(...)`）。

**内部调用链**：`app.pick_face(solid_name, face_id)` → `app.add_port(port_number)`。

**返回值**：`add_waveguide_port` → `int`（端口号）；`add_ports_for_straight_waveguide` → `(port1_number, port2_number)`；
`add_port_for_antenna` → `int`（1）。

```python
from topo_modeler.builders import add_waveguide_port, add_ports_for_straight_waveguide, add_port_for_antenna

add_waveguide_port(app, solid_name='wg1', port_number=1, face_id='10')   # 单端口 → 1
add_ports_for_straight_waveguide(app, waveguide_name='wg1')              # → (1, 2)
add_port_for_antenna(app, waveguide_name='wg1')                          # → 1
```

> 缺陷：面编号 `'10'` / `'22'` 是从旧 notebook 提取的 **CST 内部编号**，与实体几何强相关，
> 当前为**硬编码**（见第 8 节）。

### 6.7 `builders/solver.py` —— 求解器配置

**作用**：配置时域求解器 —— 频率范围、时域求解器基本设置、高级参数（稳态精度 / 并行 / GPU）、场监视器与远场监视器。
**尽量调用 `cst_solver` 已有方法**（替代旧代码约 40 行手写 VBA）。

```python
def configure_solver(app, freq_range=(300, 380), monitors=('E',),
                     calculation_type='TD-S', steady_state=-30,
                     parallel_threads=1024, gpus=1, component='component1')
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `app` | `setup` | — | CST 会话 |
| `freq_range` | `tuple` | `(300, 380)` | `(fmin, fmax)`，单位 GHz |
| `monitors` | `tuple` | `('E',)` | 监视器类型：`'E'` / `'H'` / `'Farfield'` / `'Powerflow'` |
| `calculation_type` | `str` | `'TD-S'` | 求解器类型（当前仅记录语义，函数体未使用该参数） |
| `steady_state` | `int` | `-30` | 稳态精度（dB） |
| `parallel_threads` | `int` | `1024` | 并行线程数 |
| `gpus` | `int` | `1` | GPU 数量 |
| `component` | `str` | `'component1'` | 归属组件（当前函数体未使用） |

**内部调用链**：

1. `app.set_frequency_range(fmin, fmax)`（`cst_solver` 封装）；
2. `app.configure_time_solver()`（时域求解器基本配置：Method / Accuracy / CalculateAllModes / DetermineFreq）；
3. `_configure_solver_advanced(app, steady_state, parallel_threads, gpus)` ——
   通过 `app.cst_file.model3d.add_to_history(...)` 下发两段 VBA
   （`Solver.SteadyStateLimit "<steady_state>"`；`Solver.ParallelizationThreads "<n>"` + `Solver.GPUAcceleration "<gpus>"`）；
4. `_get_monitor_frequencies(fmin, fmax, monitors)` 取 5 个频率点（起点 / 1/4 / 中点 / 3/4 / 终点），
   逐个建监视器：`'FARFIELD'` → `_create_farfield_monitor(app, freqs)`（逐频率下发 `Farfield.Reset/Frequency/Type "Broadband"/Create`），
   其余 → `app.create_field_monitor(mon_type, freqs)`。

**返回值**：`None`。

```python
from topo_modeler.builders import configure_solver

configure_solver(app, freq_range=(300, 380), monitors=('E',))                # 直波导
configure_solver(app, freq_range=(300, 380), monitors=('E', 'Farfield'))     # 天线
```

> 这是包内**唯一**直接写 VBA 的地方：`SteadyStateLimit` / `ParallelizationThreads` / `GPUAcceleration`
> 与 Farfield 监视器在 `cst_solver` 中尚无可直接调用的封装。

---

## 7. 三种用法

### 7.1 模板层（推荐：日常建模型）

一个类 = 一个器件，内部组装 `TopoModeler` + 参数定义 + 镜像 + 端口 + 求解器。

```python
from templates import StraightWaveguide, UnitAntenna

# 直波导（AB 型，2 端口）
wg = StraightWaveguide(
    topology='AB',
    length=18,                      # 波导长度（晶格数）
    lattice_constant=0.2425,
    height=0.25,
    large_hole_ratio=0.65,
    small_hole_ratio=0.35,
    feed_type='ab_elliptical',
    freq_range=(300, 380),
    monitors=('E',),
    template_cst=r'D:\work\tmp.cst',
    output_path=r'D:\out\wg.cst',
)
wg.preview()        # matplotlib 预览路径 + 晶格背景（不需要 CST）
print(wg)           # StraightWaveguide(topology='AB', length=18, a=0.2425, h=0.25, built=False)
wg.build_all()      # 参数 → 基板 → VPC → 晶体 → feed → 波导 → 镜像 → 端口 → 整合 → 求解器
wg.save()           # → 写到 output_path
# wg.run()          # 运行仿真

# 单元天线（BA 型，120° 拐弯，1 端口，含远场）
ant = UnitAntenna(
    bend_angle=120, straight_length=18, arm_length=14,
    topology='BA', feed_type='ba_tapered',
    radiator='cylinder', radiator_radius=0.3,
    freq_range=(300, 380), monitors=('E', 'Farfield'),
    template_cst=r'D:\work\tmp.cst',
    output_path=r'D:\out\ant.cst',
)
ant.preview()
ant.build_all()
ant.save()
```

> ⚠ **当前不可直接运行**：`templates/straight_waveguide.py` 与 `templates/unit_antenna.py` 的 `build_all()`
> 会给 `build_vpc_regions` 传 `topology=`、给 `build_topological_crystal` 传 `xup/yup/ydn=`，
> ✅ 已修：`build_topological_crystal` 现在接受 `xup/yup/ydn`，`build_vpc_regions` 不再接收 `topology`（见第 8 节 (d)(e)）。
> 修好这两处（或先按 7.2 / 7.3 的方式绕开）之后，上面的代码才是可用路径。

### 7.2 Modeler 层（新器件、非标准路径、需要分步调试）

```python
from topo_modeler import TopoModeler
from mesh_grid.tri_grid import TopoPath

# 自定义路径：直段 + 60° 拐弯
path = (TopoPath.builder(a=0.2425, name='p')
        .start(0, -1)
        .move(19, 'c')
        .turn(60)
        .move(10, 'along')
        .build())

modeler = TopoModeler(template_cst=r'D:\work\tmp.cst')
modeler.set_path(path)                  # 自动推断 antenna + BA + ('E','Farfield') + 1 端口 + ba_tapered
modeler.set_topology('BA')              # 手动确认/覆盖拓扑相

modeler.set_parameter('a', 0.2425)
modeler.set_parameters({
    'h': 0.25,
    'l1': 0.65 * 0.2425, 'l2': 0.35 * 0.2425,
    'e1': 0.2425 / 2, 'e2': 0.2425 * 3 ** 0.5 / 2,
})

# 分步构建：每一步都能单独检查、单独重跑
modeler.build_substrate(name='substrate')
modeler.build_vpc_regions(name_prefix='vpc')
modeler.build_crystal(topology='BA')
modeler.build_feed(feed_type='ba_tapered', name='feed2')
modeler.build_waveguide(name='wg1')
modeler.add_ports()

modeler.configure_solver(freq_range=(300, 380), monitors=('E', 'Farfield'),
                         steady_state=-30, parallel_threads=1024, gpus=1)

print(modeler.get_built_parts())
# {'substrate': 'substrate', 'vpca': 'vpc_A', 'vpcb': 'vpc_B',
#  'crystal_a': 'g1A', 'crystal_b': 'g1B',
#  'feed': 'feed2', 'waveguide': 'wg1', 'ports': [1], 'solver': True}

modeler.preview()                       # matplotlib 预览路径
modeler.save(r'D:\out\custom.cst')
```

想一键到底时，用 `build_all()` 并按下表传参：

```python
modeler.build_all(
    freq_range=(300, 380),
    include_feed=True, include_waveguide=True, include_ports=True,
    crystal_kw={'topology': 'BA', 'lattice': 'a'},
    feed_kw={'feed_type': 'ba_tapered', 'name': 'feed2'},
    waveguide_kw={'name': 'wg1'},
    solver_kw={'monitors': ('E', 'Farfield')},
)
```

### 7.3 Builder 层（完全控制：只要某一个部件，或要自定义顺序）

```python
from cst_solver import setup
from mesh_grid.tri_grid import TopoPath
from topo_modeler.builders import (
    build_substrate, build_vpc_regions, build_topological_crystal,
    build_feed, build_waveguide, add_ports_for_straight_waveguide,
    configure_solver,
)

# 1. 自己开工程、自己定参数（builder 不替你定义任何参数）
app = setup(r'D:\work\tmp.cst')

a, h = 0.2425, 0.25
app.para('a', a)
app.para('h', h)
app.para('l1', 0.65 * a)
app.para('l2', 0.35 * a)
app.para('e1', a / 2)
app.para('e2', a * 3 ** 0.5 / 2)
app.para('x0', 1)
app.para('wf1', 0.5)
app.para('lf1', 0.5)
app.para('lf2', 0.3)
app.para('lf3', 5.0)
app.para('wg_a', 0.5)
app.para('wg_b', 0.25)
app.para('wg_t', 0.02)

# 2. 路径（唯一数据源）
path = TopoPath.builder(a, name='p').start(0, -1).move(19, 'c').build()

# 3. 逐部件构建 —— 完全自己控制顺序与参数
build_substrate(app, path, name='my_sub', y_margin='e2')
vpca, vpcb = build_vpc_regions(app, path, name_prefix='my_vpc')
ca, cb = build_topological_crystal(app, path, topology='AB')      # 阵列范围由 path 推断
build_feed(app, feed_type='ab_elliptical', name='my_feed')
build_waveguide(app, name='my_wg')
add_ports_for_straight_waveguide(app, waveguide_name='my_wg')
configure_solver(app, freq_range=(300, 380), monitors=('E',))

# 4. 验收：CST 不保证把错误抛成异常，必须读消息
print(app.cst_file.get_messages())        # 应为空（读后即清空）
app.cst_file.model3d.Rebuild()            # 阻塞式重放历史，最能暴露问题
print(app.cst_file.get_messages())        # 仍应为空

app.save(r'D:\out\manual.cst')
```

> Builder 层**不需要** `TopoModeler` 实例：这正是设计意图 —— 想复用「只有光子晶体阵列」这一块时，
> 直接 import 那个函数即可，不必把整条流水线拖进来。

---

## 8. 已知缺陷与限制

> **修复状态（本轮已更新）**：下表 (a)–(e) **全部已修复**，(c) 的形参已补齐，
> `full_deembedding` / `consider_material_inside` 两个空转形参已删除，
> `calculation_type` 已接上 `cst_solver` 的求解器分派，
> `'vpca' / 'vpcb'` 命名错位与模板 `run()` 的 `start_solver()` 也一并修掉了。
> 仍**未修**的是端口面编号硬编码，以及阶段 4/5/6 未实现的功能。
> 详见仓库提交历史与 `skills/developer/cst-solver-dev.md`。

以下缺陷原记录自 [`../../skills/developer/cst-solver-dev.md`](../../skills/developer/cst-solver-dev.md) 的「待修清单」，
另含端口面编号与本包内**尚不可用**的路径。

| 位置 | 问题 | 影响 | 处理结果 |
|---|---|---|---|
| (a) `mesh_grid/tri_grid/topo_path.py::build_vpc_area_polygon(side='lower')` | 多边形顶点曾为**顺时针（CW）** | `ExtrudeCurve` 沿多边形**法向**拉伸（CCW → +z，CW → −z），该实体与晶体在 z 上**差一个 `h`**；布尔求交得到**空集且 CST 不报错** | ✅ 已修：两条边界链改为「每个路径点都参与」的确定绕向写法，`upper`/`lower` **均保证 CCW**；`test_topo_path.py` 新增第 16 项测试用有向面积钉住该约定 |
| (b) `mesh_grid/tri_grid/topo_path.py::build_substrate_polygon` | 同上：带状多边形曾为 CW | 基板与晶体/其它实体在 z 上差一个 `h`，后续布尔运算静默出错 | ✅ 已修：改为「下侧偏移链正向 → 上侧偏移链反向」，保证 CCW（一并更新了单测的顶点数断言：VPC 区域由 `N+3` 变为 `2N+1`） |
| (c) `builders/crystal.py::build_topological_crystal` | 阵列范围只能由 `path.get_array_range()` 推断 | 宽基板上阵列**覆盖不全**（边缘留实心区），且调用方无法纠正 | ✅ 已修：新增可选形参 `xup=None, yup=None, ydn=None`，`None` 时回退自动推导 |
| (d) `templates/straight_waveguide.py` | `build_all()` 曾给 `build_vpc_regions` 传 `topology=`、给 `build_topological_crystal` 传 `xup/yup/ydn=` | 模板一调用就 `TypeError` | ✅ 已修：`topology` 只传给 `build_topological_crystal`；`xup/yup/ydn` 现在被接受 |
| (e) `templates/unit_antenna.py` | 同 (d) | `UnitAntenna.build_all()` 同样 `TypeError` | ✅ 已修 |
| (f) `templates/*.py` 的 `run()` | 调用 `self.app.start_solver()`，而该方法在全库中**不存在** | `run()` 必抛 `AttributeError`（`build_all()` 正常） | ✅ 已修：改用 `self.app.run()` |
| (g) `templates/*.py` 的 `__init__` | 经 `TopoModeler.set_parameters()` 调 `app.set_parameters(params)`，而真实签名是 `set_parameters(name, value, log_flag=0)` | **构造时就抛 `TypeError`**，比 (d)(e) 更早触发 | ✅ 已修：`TopoModeler.set_parameters()` 改用字典式批量接口 `app.paras(params, None)` |
| `builders/port.py::add_ports_for_straight_waveguide` / `add_port_for_antenna` | CST 面编号 `'10'` / `'22'` 从旧 notebook **硬编码**提取 | 面编号与实体几何强相关：一旦波导尺寸/朝向/构建顺序变化，端口可能落在**错误的面上** | ⏳ 未修（阶段 3 已知限制）：应改为按法向量自动查找，把 `face_id` 降级为可选覆盖项 |
| `TopoModeler.build_lens` / `builders/lens.py`（GRIN 透镜） | ~~**阶段 4 未实现**~~ | ~~含 GRIN 透镜的器件暂不能建~~ | ✅ **已修**（2026-09-15）：透镜几何下沉为 `builders/lens.py` 的无状态层（`GrinLensSpec` / `GrinLensHoles` / `build_grin_lens_holes`），`build_lens()` 已接线。**与原脚本 `lens_build.py` 逐点/逐条等价**（`topo_modeler/tests/test_lens.py`，36 项）。⚠️ 仍缺：`method='dxf'` 入口、`GRINLensAntenna` 模板、CST 端到端真机验证 |
| `TopoModeler.read_results` / `plot_results` | **阶段 7 未实现**：两者都抛 `NotImplementedError` | 仿真结果（S 参数 / 远场 / E 场）无法通过本包读取 | ⏳ 待阶段 7 实现独立的 `ResultReader`（阶段 5 已把底层读取/导出 API 做进 `cst_solver.Result`） |
| `add_waveguide_port` 的 `full_deembedding` / `consider_material_inside`；`configure_solver` 的 `calculation_type` | 形参曾存在但函数体**未使用** | 调用方以为开关生效，实际被忽略 | ✅ 已修：两个空转形参已删除（改为 `orientation` / `shield` 并真正转发给 `add_port`）；`calculation_type` 已按 `TD-S`/`FD-S`/`EIGENMODE`/`IE-S`/`ASYMPTOTIC` 分派到对应 `cst_solver` 方法，非法值直接 `ValueError` |

**注意 (a)(b) 的绕向修复引入了两处可见变化**：

1. VPC 区域多边形的顶点数由 `N+3` 变为 `2N+1`（两条边界链各含全部路径点）——
   只取两端偏移点的稀疏写法，其绕向会随路径拐弯方向翻转，无法保证 CCW；
2. 拐弯路径的 VPC 区域现在是**真正沿路径的带状区域**（含中间偏移点），
   因此与旧 notebook 里那个「三角形 + `insert`/`intersect`」的 VPC-A 造法**几何不同**。
   旧 notebook 的 VPC 区域语义与新库并不一致，这一点需要在阶段 4 之前与参考工程对齐（见 `docs/next_plan/`）。

**已一并修掉的命名错位**：
`build_vpc_regions` 默认 `name_prefix='vpc'`，生成 `vpc_A` / `vpc_B`；
模板原先按 `'vpca'` / `'vpcb'` 引用（`app.add('vpca', …)`）。
现已改为接收 `build_vpc_regions()` 的返回值并使用 `vpc_A` / `vpc_B`。

**其它限制**（来自阶段 0–3 指南，尚未开始）：

- **多端口未实现**（阶段 6）：3 端口 / 4 端口天线不在当前能力范围；
- **符号路径的阵列范围**：符号路径的 `get_array_range()` 需要 `param_values` 才能数值化，
  无法直接返回 CST 表达式；
- **无 CST 环境**：`TopoModeler` 会把 `app` 置为 `None` 并给 warning，
  此时 `set_path` / `set_parameters` / `preview` 可用，但任何 `build_*` 会失败（`templates` 里则显式抛 `RuntimeError`）。

---

## 9. 如何扩展这个包

先读 [`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md)（开发宪法：归属判定 → 改代码 → 同步文档 → 验收 → 逐包提交）。
流程、命名、验收清单、提交规范以它为准，本节只是把「加一个部件构建器」这条最常见的路径串起来。

1. **判定归属**。按 WORKFLOW §2 的表格判断需求落在哪个包：
   把部件组装成模型、编排建模顺序 → `topo_modeler/`；某个具体器件的完整流程 → `templates/`；
   CST 原语本身缺失 → 先去 `cst_solver/` 补封装，**再**回来用。
   在 `topo_modeler/builders/` 里手写 VBA 是明确的反例。
2. **写进 `builders/<部件>.py`，作为无状态函数**。签名风格与本包一致：
   第一个参数 `app`，其余参数**全部显式**、带默认值、类型标注 `str | float`（CST 尺寸是表达式字符串）；
   返回创建的实体名（或名字元组）。**不要**依赖 `TopoModeler` 实例或任何全局状态。
3. **在 `builders/__init__.py` 的 `__all__` 里导出**。同时按公私有约定命名
   （新 API 用 `snake_case`；历史 VBA 风格别名如 `substract`（已废弃的旧拼写）必须保留为别名）。
4. **保证多边形 CCW 绕向**（`有向面积 > 0`）+ 内部 `translate -h/2`。
   `ExtrudeCurve` 沿法向拉伸：CW 会得到 −z 方向实体，实体之间在 z 上差一个 `h`，
   布尔求交返回空集**且不报错** —— 这是本仓库最高频的静默事故（ARCHITECTURE §6 硬约定 1）。
5. **用模板端到端验证**：至少用一个 `templates/` 里的模板（或最小脚本）跑通，
   并检查 `app.cst_file.get_messages()` 为空、`model3d.Rebuild()` 后仍为空
   （CST 不保证把错误抛成 Python 异常）。
6. **同步文档**：新增/修改 builder 或模板 → 更新本文件（`docs/packages/topo_modeler.md`）对应小节；
   新增硬约定或踩坑 → `docs/ARCHITECTURE.md` §6 + 相关 skill；
   修掉已知缺陷 → 删掉 `cst-solver-dev.md` 的「待修清单」对应行（见 WORKFLOW §6 同步矩阵）。

验收清单（WORKFLOW §4，`topo_modeler/`）：

- [ ] builder 是**无状态纯函数**，可脱离 `TopoModeler` 单独调用
- [ ] 已在 `builders/__init__.py` 导出并加入 `__all__`
- [ ] 多边形**绕向 CCW**
- [ ] 阵列范围覆盖整个基板
- [ ] 至少用一个模板或最小脚本端到端跑通

---

## 10. 相关文档

| 想知道什么 | 读哪份 |
|---|---|
| 全仓库分层、各包职责、跨包硬约定 | [`../ARCHITECTURE.md`](../ARCHITECTURE.md) |
| 阶段 0–3 的包结构、API 速查、与旧代码的对应关系 | [`../guides/topo_modeler_guide_stage0-3.md`](../guides/topo_modeler_guide_stage0-3.md) |
| 后续阶段计划、阶段状态表 | [`../next_plan/README.md`](../next_plan/README.md) |
| 使用者视角：怎么用本包把模型建出来 | [`../../skills/user/topo-modeler.md`](../../skills/user/topo-modeler.md) |
| 使用者总规程：写 notebook、排错、验收 | [`../../skills/user/tpc-usage.md`](../../skills/user/tpc-usage.md) |
| 开发者工作流（开发宪法：归属判定 / 提交规范 / 同步矩阵） | [`../../skills/developer/WORKFLOW.md`](../../skills/developer/WORKFLOW.md) |
| CST 封装层开发，含本包 builders 的**待修清单** | [`../../skills/developer/cst-solver-dev.md`](../../skills/developer/cst-solver-dev.md) |

> 注：撰写本文时，`../next_plan/README.md` 与 `../../skills/user/topo-modeler.md` 两个目标**尚未创建**
> （`docs/ARCHITECTURE.md`、`docs/README.md` 与 `skills/developer/WORKFLOW.md` 已先行引用这两个位置）；
> 它们创建后上面的链接即自然生效。

---

*文档基于当前源码实测编写（`TopoModeler` 21 个公开方法、`NameManager` 8 个公开方法；
`builders/` 8 个构建器；`tests/test_lens.py` 36 项回归）。*
