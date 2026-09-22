---
name: cst-solver
description: '**cst_solver 快速使用手册（使用者视角）** —— 常用 API 速查（开工程 / 参数 / 实体 / 布尔 / 变换 / 材料 / 端口 / 监视器 / 边界 / 求解 / 读结果），照抄即可，不必翻源码；不常用或不确定的 API 才按地图查源码。含三条硬约定、CST 侧验收、**结构示意图的工程制图规范（Python+Matplotlib、中文显示入口、变量用 LaTeX）**、以及**疑似库 bug 的判定与报告流程（只报告，不修库）**。USE FOR: 直接用 cst_solver.setup / result 建模型、配仿真、读结果；确认常用 API 怎么调；**绘制结构示意图**；模型异常时区分「我用错了」还是「库有 bug」。DO NOT USE FOR: 拓扑光子晶体器件装配 → topo-quickstart；topo_modeler/topo_templates 用法 → tpc-user；修改库源码 / 新增封装 / 修 bug → cst-solver-dev。'
whenToUse: 用户要直接用 cst_solver 建模/配仿真/读结果、想快速确认常用 API 用法、或需要判定并报告疑似库 bug 时。
argument-hint: 描述要用 cst_solver 做什么（建什么结构、配什么端口/求解、读什么结果）
---

# cst_solver 快速使用手册

> **层级**：TPC 是整个库，`cst_solver` 只是其中领域最小的通用子包（CST VBA → Python）。
> topo 器件（`topo_modeler`/`topo_templates`）是研究方向专用大包 → 读 `topo-quickstart`，不在本 skill。
>
> **本文件是薄壳。完整手册在 [`../../../skills/user/cst-solver.md`](../../../skills/user/cst-solver.md)。**
>
> **请现在就去读完整手册** —— §3 是常用 API 速查（照抄即可）、§4 是三条硬约定、
> §5 是症状速查、§6 是 CST 侧验收、§8 是 bug 报告流程。
> 本薄壳只保留最关键的几条，不足以独立完成一次交付。

## 30 秒上手

```python
from cst_solver import setup, result

app = setup('tmp.cst')                       # 相对路径按当前工作目录解析
app.para('a', 0.2425)
app.freq_limit(300, 380)
app.square(-5, 5, -2, 2, -0.1, 0.1, 'box', material='PEC')
app.pick_face_at('box', -5, 0, 0)     # add_port 用 Picks 坐标：必须先拾取端口面
app.add_port(1, orientation='xmin')
app.T_solver()
report = app.run_checked()                  # unverified 不能当成功
app.save(r'D:\out\device.cst', include_results=False)
app.close()

res = result(r'D:\out\device.cst')          # 离线读结果，不需许可证
s21 = res.read_s_parameter('S2,1')
```

前提：仓库根已 `pip install -e .`；`CST_INSTALL_PATH` 已配。环境自检：`python -m cst_solver doctor --probe`。

## 查不查源码？

- 常用 API（完整手册 §3）→ **直接照抄，不翻源码**。
- 不常用 / 拿不准签名 → 先读 `cst_solver/setup.pyi`；仍不确定按 §2 地图读对应模块。
- 源码显示封装本身有错（拼错 VBA / 调了不存在的方法 / 参数收下却不下发）→ **库 bug，按 §8 报告**。

## 三条硬约定

1. **z 平面**：自写多边形必须 CCW + 内部 `translate -h/2`；绕向错 → 求交空集且不报错。
   （`triangle()`/`hexagon()` 底层是 CCW，但只平移到给定 center、不做 `-h/2`。）
2. **布尔**：add/subtract 结果在 A、B 删除；intersect 结果留 A、B 消耗；
   **insert = A−B 且保留 B**（不是并集）。
3. **阵列范围**：必须覆盖真实基板且用 CST 参数表达式，不能只按路径推。

## 最高危陷阱

* 🔴 **CST 不抛异常**：每步读 `app.get_messages()` + `model3d.Rebuild()`；跑通 ≠ 建对。
* 🔴 **端口 orientation**：只接受 `xmin/xmax/ymin/ymax/zmin/zmax`，
  `positive/negative` 当场 ValueError；不要依赖默认值。
* 🔴 **`para()` 默认 `log_flag=0`**：改参数后不重建是常见「没生效」原因。
* 🔴 **发现库 bug 只报告，不修库**：结构化报告（环境/最小复现/逐字报错/源码行号/绕过方案）
  交给用户，并追加登记到 `skills/developer/cst-solver-dev.md` 待修清单。

## 绘制结构示意图（被要求时）

- 用 **Python + Matplotlib** 程序化画，按**工程制图标准**：实线=可见轮廓、虚线=遮挡、点划线=中心；
  尺寸线+箭头+尺寸界线齐全；`set_aspect('equal')`；材料区用剖面线/淡色填充+图例；出 PNG(dpi≥180)+PDF/SVG。
- 中文必须走 `mesh_grid.plotting.chinese_plot_style(strict=True)`；禁写死字体、禁屏蔽缺字警告。
- 变量标注一律 **LaTeX mathtext `$...$`**：`r'$a$'`、`r'$l_1$'`、`r'$\theta$'`；中文留在 `$...$` 外。

## CST 侧验收

```python
print(app.get_messages())            # 必须 []
app.cst_file.model3d.Rebuild()
print(app.get_messages())            # 必须 []
```

## 相关

- ⭐ **完整手册（先读这个）** → [`../../../skills/user/cst-solver.md`](../../../skills/user/cst-solver.md)
- 拓扑光子晶体器件装配 → [`../../../skills/user/topo-quickstart.md`](../../../skills/user/topo-quickstart.md)
- 建模引擎 / 模板层完整手册 → [`../../../skills/user/tpc-usage.md`](../../../skills/user/tpc-usage.md)
- 要改库源码 → [`../../../skills/developer/cst-solver-dev.md`](../../../skills/developer/cst-solver-dev.md)
