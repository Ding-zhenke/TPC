---
name: tpc-user
description: '**用 TPC 库建拓扑光子晶体模型** —— 写 notebook、调用模板/建模引擎、排查 CST 报错、验收模型。USE FOR: 用 cst_solver / topo_modeler / topo_templates 建模型；CST 历史树报错定位；S 参数与远场结果读取。DO NOT USE FOR: 修改库源码 —— 那属于开发者视角，读 ../developer/WORKFLOW.md。'
argument-hint: 描述要建的器件与目标频段（如「300-380 GHz 的 120° 拐弯单元天线」）
---

# TPC 使用视角

> **本文件是薄壳。完整手册在 [`../../skills/user/tpc-usage.md`](../../../skills/user/tpc-usage.md)。**

**请现在就去读完整手册**，本薄壳只保留最关键的几条：

## 三种用法，按需选择

```python
# ① 模板层（推荐起点）：一个类 = 一个器件
from topo_templates import StraightWaveguide, UnitAntenna
wg = StraightWaveguide(topology='AB', length=18, output_path=r'D:\out\wg.cst')
wg.preview(); wg.build_all(); wg.save()

# ② Modeler 层：自定义路径 + 分步构建
from topo_modeler import TopoModeler
from mesh_grid.tri_grid import TopoPath
path = TopoPath.builder(a=0.2425).start(0, -1).move(19, 'c').turn(120).move(15, 'along').build()
modeler = TopoModeler(template_cst='tmp.cst')
modeler.set_path(path)
modeler.build_all(freq_range=(300, 380))

# ③ Builder 层：完全控制
from topo_modeler.builders import build_substrate, build_topological_crystal, configure_solver
```

## 三条硬约定（违反必出问题）

1. **z 平面**：多边形必须 **CCW**，配合内部 `translate -h/2`。
   绕向错了 → 实体在 z 上差一个 `h` → 布尔求交得**空集且不报错**。
2. **布尔语义**：`Intersect "A","B"` 结果留 **A**、B 被消耗；
   `Add/Subtract "A","B"` 结果在 A、**B 被删除**；`Insert` 保留 B。
3. **阵列范围**：`xup / yup / ydn` 必须覆盖**整个基板**，不能只按路径推断。

## 验收必做

```python
print(app.cst_file.get_messages())     # 必须为空
app.cst_file.model3d.Rebuild()         # 阻塞式重放历史，最能暴露问题
print(app.cst_file.get_messages())     # 必须为空
```

CST **不抛异常**，跑通 ≠ 建模正确。

## 相关

- 三角晶格 / 路径 DSL → [`../../skills/user/tri-grid.md`](../../../skills/user/tri-grid.md)
- 六边形晶格 / DXF → [`../../skills/user/hex-grid.md`](../../../skills/user/hex-grid.md)
- 建模引擎详解 → [`../../skills/user/topo-modeler.md`](../../../skills/user/topo-modeler.md)
- 报错定位表 / 已知库缺陷 → [`../../skills/user/tpc-usage.md`](../../../skills/user/tpc-usage.md)
