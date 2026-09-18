---
name: topo-quickstart
description: '用 topo_templates / TopoModeler / builders 建 AB/BA 域壁器件及已实现的直波导、单元天线、GRIN 透镜天线、多端口天线、MZI 开关、功分器；核对参考 notebook 的几何口径、装配顺序与离线拓扑正确性。修改库源码应读开发者工作流；泄漏波、C6 环和未实现变体须先查看统一计划。'
argument-hint: 描述要建的器件（直波导 / 单元天线 / 多域壁器件 / 自定义域壁路径）、拓扑（AB/BA）、频段与自定义尺寸
---

# 拓扑光子晶体建模（TOPO 模块）

> **本文件是薄壳。完整手册在 [`../../../skills/user/topo-quickstart.md`](../../../skills/user/topo-quickstart.md)。**
>
> **请现在就去读完整手册** —— §3 是结构解剖（超元胞/相/域壁/相区怎么建出来）、
> §5 是参数口径表、§8 是**离线拓扑自检**、§9 是语义错位清单、§11 是报错表。
> 本薄壳只保留最关键的几条，不足以独立完成一次交付。

## 30 秒上手

```python
from topo_templates import StraightWaveguide, UnitAntenna

wg = StraightWaveguide(topology='AB', length=18, width=14,
                       lattice_constant=0.2425, height=0.25,
                       large_hole_ratio=0.65, small_hole_ratio=0.35,
                       feed_type='ab_elliptical',
                       freq_range=(300, 380), monitors=('E',),
                       template_cst='tmp.cst', output_path=r'D:\out\wg.cst')
wg.preview(); wg.build_all(); wg.save()
```

前提：仓库根已 `pip install -e .`；`CST_INSTALL_PATH` 已配；模板 `tmp.cst` 在**当前工作目录**。
BA 直波导必须显式 `feed_type='ba_tapered'`（默认值不随 `topology` 变）。

## 器件由什么组成（一句话版）

**域壁 = 你给的 `TopoPath` 路径**；路径上方是 B 相、下方是 A 相；两相是同一套三角孔阵列的两种排布
（只差"朝上孔/朝下孔"谁大谁小）；成品 = `vpc_A ∩ 晶体A` ∪ 探针 ∪ `vpc_B ∩ 晶体B`，
**刻意没有一块额外的整块基板**（多一块会把孔洞填平）。详见完整手册 §3。

## 四条不能违反的规则

1. **CCW + 内部 `translate -h/2`**。`ExtrudeCurve` 沿多边形法向拉伸（CCW→+z、CW→−z）；
   绕向错了 → 布尔求交得**空集且 CST 不报错**。
2. **布尔语义**：`add/subtract` 结果留 A、B 删；`intersect` 结果留 A、**B 被消耗**；
   **`insert` 是差集 `A−B`（不是并集）**，B 保留。相区就是靠这两条求出来的 —— 记反 ⇒ **域壁消失且不报错**。
3. **阵列范围**：`xup/yup/ydn` 必须覆盖整个基板，且必须写成 **CST 参数引用**（`int(xup)`）；
   `ydn=1` ⇒ `int(ydn/2)=0` ⇒ `Invalid number of repetitions`。别用 `path.get_array_range()` 推。
4. **CST 不抛异常**。未定义参数会弹「请输入变量值」**把脚本挂住**。跑通 ≠ 建对。

## 三个最高危陷阱

* 🔴 **`l1`/`l2` 同名不同义**：参考工程里 `l1` = 「A 相朝上孔」（大小随拓扑换），
  TPC 里 `l1` **恒为大孔**。复用参考工程口径**必须**写 `large_hole='l2', small_hole='l1'`；
  用 TPC 口径则**不要**传这两个参数 —— **两者混用会把相再翻回去**。
* 🔴 **不要按文件名猜 `topology`**：参考工程的 AB/BA 是「目录名 + `l1/l2` 数值」，
  `MZI-BA.ipynb` 注册的其实是 AB 形状。判定拓扑要看 CST 参数表与区域/路径侧，**预览图也算不出来**
  （预览函数把 `l1` 硬编码成 `0.65a`，永远画 BA）。
* 🔴 **多域壁器件（MZI/功分器）的相区不是"路径下侧"**：A 相是**两个多边形之并**（参考写法见完整手册 §3.6）。
  把单域壁直觉套上去 ⇒ 相区错、域壁数量与位置都错。

**AB/BA 不变式**：AB ⇔ 大孔（朝上那组）在域壁 **+y** 侧；BA ⇔ 在 **−y** 侧。
`bend_angle` 是**张角**（`120D` ⇔ 120，单臂 ±60），必须是 120 的整数倍。

## ⭐ 离线拓扑自检（不用 CST、秒级，建完必跑）

```python
from mesh_grid.tri_grid import TopoPath
from topo_modeler.builders.crystal import build_topological_crystal

class _Recorder:
    def __init__(self): self.calls = []
    def __getattr__(self, label):
        def f(*a, **k): self.calls.append((label, a, k))
        return f

app = _Recorder()
path = TopoPath.builder(0.2425, name='p').start(0, 0).move(18, 'c').build()
build_topological_crystal(app, path, topology='AB',
                          large_hole='l2', small_hole='l1',     # ← 参考工程口径
                          xup='xup', yup='yup', ydn='ydn')

binding = {k['name']: a[0] for label, a, k in app.calls
           if label == 'triangle' and str(k.get('name', '')).startswith('tri_')}
assert binding == {'tri_up_A': 'l1', 'tri_dn_A': 'l2',
                   'tri_up_B': 'l2', 'tri_dn_B': 'l1'}, binding   # 参考工程的权威绑定
print('相绑定 OK')
```

**这是唯一能在建模前证明"相没搞反"的低成本手段。** 更多（阵列引用断言、几何不变式清单、
相区覆盖自算）见完整手册 §8。

## CST 侧验收

```python
app = wg.app                           # 模板把 cst_solver.setup 实例挂在 .app 上
print(app.cst_file.get_messages())     # 必须为空
app.cst_file.model3d.Rebuild()         # 阻塞式重放历史
print(app.cst_file.get_messages())     # 必须为空
print(wg.validate())                   # 结构化校验
```

## 相关

- ⭐ **完整手册（先读这个）** → [`../../../skills/user/topo-quickstart.md`](../../../skills/user/topo-quickstart.md)
- 库总入口 / 报错定位 / 大几何子工程 → [`../../../skills/user/tpc-usage.md`](../../../skills/user/tpc-usage.md)
- 三角晶格 / 路径 DSL → [`../../../skills/user/tri-grid.md`](../../../skills/user/tri-grid.md)
- 建模引擎三种用法 → [`../../../skills/user/topo-modeler.md`](../../../skills/user/topo-modeler.md)
- 要改库源码 → [`../../../skills/developer/WORKFLOW.md`](../../../skills/developer/WORKFLOW.md)
