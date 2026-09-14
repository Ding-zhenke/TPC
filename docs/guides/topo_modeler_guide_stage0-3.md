# topo\_modeler 包规划与使用指南（阶段 0-3）

> 本文档整理自 
>
> `06_整合实施计划_分阶段分模块.md`
>
> ，聚焦已完成的阶段 0-3，
> 包含包结构、模块功能、API 速查、快速上手示例，以及与旧代码的对应关系。



***

## 一、包结构总览



```
TPC/

├── mesh\_grid/tri\_grid/

│   └── topo\_path.py              # 阶段1：坐标统一层（唯一新增到 mesh\_grid 的文件）

├── topo\_modeler/                  # 阶段2-3：核心建模包

│   ├── \_\_init\_\_.py                # 导出 TopoModeler, NameManager

│   ├── modeler.py                 # 阶段2：TopoModeler 核心类（智能推断+流水线）

│   ├── name\_manager.py            # 阶段2：命名管理器

│   └── builders/

│       ├── \_\_init\_\_.py            # 导出全部 builders

│       ├── substrate.py           # 阶段2：基板构建器

│       ├── vpc\_region.py          # 阶段2：VPC-A/B 区域构建器

│       ├── crystal.py             # 阶段2：光子晶体阵列构建器（核心）

│       ├── solver.py              # 阶段2：求解器配置构建器

│       ├── feed.py                # 阶段3：馈源构建器（3种类型）

│       ├── waveguide.py           # 阶段3：空心矩形波导构建器

│       └── port.py                # 阶段3：波导端口构建器

└── templates/                      # 阶段3：端到端模板

&#x20;   ├── \_\_init\_\_.py                # 导出 StraightWaveguide, UnitAntenna

&#x20;   ├── straight\_waveguide.py      # 阶段3：直波导模板

&#x20;   └── unit\_antenna.py            # 阶段3：单元天线模板
```

**设计原则**：



* 新功能全部写在 `topo_modeler/` 和 `templates/`，**不修改** `cst_solver` 和 `mesh_grid` 核心源码

* `topo_path.py` 是唯一新增到 `mesh_grid/tri_grid/` 的文件

* 代码风格与 TPC 库一致：Google 风格 docstring、f-string 拼接 VBA、4 空格缩进



***

## 二、阶段 1：坐标统一层 — TopoPath

### 2.1 核心思想

**唯一数据源是三角晶格坐标&#x20;**`(r, c)`，所有直角坐标（matplotlib 预览 + CST 表达式）全部自动推导，消除旧代码中 `path_points` 和 `(px, py)` 两套坐标的重复维护。

### 2.2 坐标转换公式

与 `mesh_grid/tri_grid/core.py` 的 `path_loc_to_xy` 完全一致：



```
x = c \* a + r \* (a/2)

y = r \* (a/2 \* sqrt(3))
```

### 2.3 6 个晶格方向（逆时针从 0° 开始）



| 角度   | 方向向量 (dr, dc) | 名称   | 物理增量 (dx, dy)  |
| ---- | ------------- | ---- | -------------- |
| 0°   | (0, +1)       | +c   | (+a, 0)        |
| 60°  | (+1, 0)       | +r   | (+a/2, +a√3/2) |
| 120° | (+1, -1)      | +r-c | (-a/2, +a√3/2) |
| 180° | (0, -1)       | -c   | (-a, 0)        |
| 240° | (-1, 0)       | -r   | (-a/2, -a√3/2) |
| 300° | (-1, +1)      | -r+c | (+a/2, -a√3/2) |

### 2.4 声明式 DSL（链式构建）



```
from mesh\_grid.tri\_grid import TopoPath

\# 直波导

path = (TopoPath.builder(a=0.2425)

&#x20;       .start(0, -1)

&#x20;       .move(19, 'c')

&#x20;       .build())

\# → \[(0,-1), (0,18)]

\# 120° 天线

path = (TopoPath.builder(a=0.2425)

&#x20;       .start(0, -1)

&#x20;       .move(19, 'c')

&#x20;       .turn(120)

&#x20;       .move(14, 'along')

&#x20;       .build())

\# → \[(0,-1), (0,18), (14,4)]
```

### 2.5 符号坐标（参数化，CST 中可调整路径长度）



```
\# 参数化直波导：x1 是 CST 参数，可在 CST 中修改调整波导长度

path = (TopoPath.builder(a=0.2425)

&#x20;       .start(0, 0)

&#x20;       .move('x1', 'c')                    # 符号步数

&#x20;       .build(param\_values={'x1': 18}))    # 预览用数值

path.auto\_define\_cst\_params(app)

\# 生成: px2='x1\*a', py2='0'  ← 参数化！

\# 参数化 120° 天线

path = (TopoPath.builder(a=0.2425)

&#x20;       .start(0, 0)

&#x20;       .move('x1', 'c')

&#x20;       .turn(120)

&#x20;       .move('y1', 'along')

&#x20;       .build(param\_values={'x1': 18, 'y1': 14}))

\# 生成: px2='x1\*a'

\#       px3='(x1-y1)\*a+y1\*a/2'

\#       py3='y1\*a/2\*sqr(3)'
```

### 2.6 核心 API



| 方法 / 属性                                     | 说明                        |
| ------------------------------------------- | ------------------------- |
| `TopoPath.builder(a, name)`                 | 创建构建器                     |
| `.start(r, c, direction)`                   | 设置起点（r/c 支持 int 或 str 符号） |
| `.move(steps, direction)`                   | 沿方向移动（steps 支持 int 或 str） |
| `.turn(angle)`                              | 旋转方向（60° 的倍数）             |
| `.line_to(r, c)`                            | 直接移动到指定坐标                 |
| `.close()`                                  | 闭合路径                      |
| `.build(param_values=None)`                 | 构建 TopoPath 实例            |
| `path.xy`                                   | 直角坐标 (N,2) numpy array    |
| `path.lattice`                              | 数值化晶格坐标                   |
| `path.lattice_symbolic`                     | 原始符号坐标（可能含 str）           |
| `path.has_symbols`                          | 是否包含符号坐标                  |
| `path.auto_define_cst_params(app, prefix)`  | 自动在 CST 中定义 p1x,p1y,...   |
| `path.lattice_to_cst_expr(r, c)`            | (r,c) → CST 表达式 (px, py)  |
| `path.get_bounding_box(margin_c, margin_r)` | 自动推导边界范围                  |
| `path.get_array_range()`                    | 自动推导阵列范围 (xup, yup, ydn)  |
| `path.build_substrate_polygon(y_margin)`    | 自动生成基板多边形顶点               |
| `path.build_vpc_area_polygon(side)`         | 自动生成 VPC 区域多边形            |
| `path.segment_angles()`                     | 每段路径的物理角度                 |
| `path.is_straight()` / `path.has_bend()`    | 判断波导 / 天线                 |
| `path.preview(ax, show_grid)`               | matplotlib 预览             |

### 2.7 被优化掉的旧代码



* 每个 notebook 中手写的 `px1,py1,...,px6,py6` 计算（10+ 行）

* 手写的 `xmax, ymax_up, ymax_dn, xup, yup, ydn` 推导

* 手写的基板 / VPC 区域 polyline 顶点列表



***

## 三、阶段 2：基础建模引擎

### 3.1 NameManager — 命名管理器

自动管理 CST 中 solid 名称，保证唯一、有意义、不冲突。



```
from topo\_modeler import NameManager

nm = NameManager()

nm.get('feed')           # → 'feed\_1'

nm.get\_feed(1)           # → 'feed\_1'

nm.get\_waveguide(1)      # → 'wg\_1'

nm.get\_port(2)           # → 'port\_2'

nm.get\_crystal('A')      # → 'crystal\_A'

nm.alias('substrate\_1', 'sub')  # 起别名

nm.resolve('sub')        # → 'substrate\_1'
```

### 3.2 SubstrateBuilder — 基板构建器

基于 TopoPath 自动生成基板（路径上下各扩展的带状区域）。



```
from topo\_modeler.builders import build\_substrate

build\_substrate(app, path, name='substrate', height='h',

&#x20;               material='Silicon (lossy)', y\_margin='e2')
```

**内部调用链**：`path.build_substrate_polygon()` → `app.polyline()` → `app.extrude()` → `app.translate(Z居中)`

### 3.3 VPCRegionBuilder — VPC 区域构建器

基于 TopoPath 自动生成 VPC-A 和 VPC-B 两个区域并裁剪。



```
from topo\_modeler.builders import build\_vpc\_regions

vpca, vpcb = build\_vpc\_regions(app, path, topology='AB',

&#x20;                                 height='h', material='Silicon (lossy)')
```

**拓扑相分配**：



* AB 型：VPC-A 朝上大孔 / 朝下小孔，VPC-B 朝上小孔 / 朝下大孔

* BA 型：互换

### 3.4 CrystalBuilder — 光子晶体阵列构建器（核心）

构建拓扑光子晶体三角孔阵列，精确复现旧代码超元胞逻辑。



```
from topo\_modeler.builders import build\_topological\_crystal

ca, cb = build\_topological\_crystal(app, path, topology='AB',

&#x20;                                    xup=26, yup=15, ydn=1)
```

**超元胞逻辑**（与旧代码完全一致）：



1. `triangle × 8`（VPC-A×4 + VPC-B×4，朝上 / 朝下各 2）

2. `add × 4`（合并同区域的三角孔）

3. `subtract × 2`（从基板中扣除孔）

4. `rotation × 2`（120° 旋转复制 2 次 → 6 个孔）

5. `translate × 6`（X 方向 + Y± 方向阵列复制）

**超元胞中心位置**：



* 朝上三角形：`center=['-a/2', 'sqr(3)/2*a-a/sqr(3)', '-h/2']`

* 朝下三角形：`center=['0', 'a/sqr(3)', '-h/2']`

### 3.5 SolverBuilder — 求解器配置构建器

配置求解器，调用 TPC 库已有方法，不手写 VBA。



```
from topo\_modeler.builders import configure\_solver

configure\_solver(app, freq\_range=(300, 380), monitors=('E', 'Farfield'))
```

**调用的 TPC 库已有方法**（替代 40 行手写 VBA）：



* `app.set_frequency_range(fmin, fmax)`

* `app.configure_time_solver(...)`

* `app.create_field_monitor(...)`

* 高级参数 VBA（稳态限制 -30dB、并行 1024 线程、GPU 加速）

### 3.6 TopoModeler — 核心建模类（智能推断 + 流水线）

所有模板的基类，智能推断模型类型并编排建模流水线。



```
from topo\_modeler import TopoModeler

from mesh\_grid.tri\_grid import TopoPath

path = TopoPath.builder(a=0.2425).start(0, -1).move(19, 'c').build()

modeler = TopoModeler(template\_cst='tmp.cst')

modeler.set\_path(path)              # 自动推断为 waveguide + AB

modeler.set\_parameters({'a': 0.2425, 'h': 0.25, 'l1': 0.1576})

modeler.build\_all(freq\_range=(300, 380))

modeler.save('waveguide.cst')
```

**智能推断规则**：



| 路径特征       | model\_type | topology | monitors         | 端口数 | feed\_type     |
| ---------- | ----------- | -------- | ---------------- | --- | -------------- |
| 直线 (≤2 点)  | waveguide   | AB       | ('E',)           | 2   | ab\_elliptical |
| 有拐弯 (>2 点) | antenna     | BA       | ('E','Farfield') | 1   | ba\_tapered    |

**流水线方法**（可单独调用）：



```
modeler.build\_substrate()       # 基板

modeler.build\_vpc\_regions()     # VPC 区域

modeler.build\_crystal()         # 光子晶体阵列

modeler.build\_feed()            # 馈源（阶段3）

modeler.build\_waveguide()       # 空心波导（阶段3）

modeler.add\_ports()             # 端口（阶段3）

modeler.configure\_solver()      # 求解器

modeler.integrate()             # 整合

modeler.build\_all()             # 端到端一键执行
```



***

## 四、阶段 3：基础模板层

### 4.1 FeedBuilder — 馈源构建器（3 种类型）



```
from topo\_modeler.builders import build\_feed

\# AB 型椭圆探针（直波导用，对应旧 feed1）

build\_feed(app, feed\_type='ab\_elliptical', name='feed1')

\# BA 型对称渐变探针（天线用，对应旧 feed2）

build\_feed(app, feed\_type='ba\_tapered', name='feed2', add\_optimizer=True)

\# 圆柱辐射体（单元天线用）

build\_feed(app, feed\_type='cylinder', name='rad1', radius=0.3,

&#x20;          position=\['1.0', '2.0', '-h/2'])
```

**3 种类型对比**：



| 类型              | 对应旧代码             | polyline 顶点 | 椭圆过渡     | 优化块        | 适用场景 |
| --------------- | ----------------- | ----------- | -------- | ---------- | ---- |
| `ab_elliptical` | feed1             | 9（上半不对称）    | 有（左半椭圆）  | 无          | 直波导  |
| `ba_tapered`    | feed2             | 10（上下对称）    | 有（左半椭圆）  | 有（tx1×ty1） | 天线   |
| `cylinder`      | cylinder\_antenna | 无           | 无（等半径圆柱） | 无          | 辐射体  |

**AB 型内部调用序列**：

`polyline(9顶点)` → `extrude(h)` → `create_elliptical_cylinder` → `square(切割右半)` → `subtract` → `translate(椭圆定位)` → `add(主体+椭圆)` → `translate(Z居中)`

### 4.2 WaveguideBuilder — 空心矩形波导构建器



```
from topo\_modeler.builders import build\_waveguide

build\_waveguide(app, name='wg1', material='Copper (annealed)')
```

**几何**：外方体 (wg1) - 内方体 (wg1\_1) = 空心波导



* 内方体：y ∈ \[e2/2-wg\_b/2, e2/2+wg\_b/2], z ∈ \[-wg\_a/2, +wg\_a/2]

* 外方体：y ∈ \[e2/2-wg\_b/2-wg\_t, e2/2+wg\_b/2+wg\_t], z ∈ \[-wg\_a/2-wg\_t, +wg\_a/2+wg\_t]

* 壁厚 = wg\_t

### 4.3 PortBuilder — 波导端口构建器



```
from topo\_modeler.builders import (

&#x20;   add\_waveguide\_port,

&#x20;   add\_ports\_for\_straight\_waveguide,

&#x20;   add\_port\_for\_antenna,

)

\# 单端口

add\_waveguide\_port(app, solid\_name='wg1', port\_number=1, face\_id='10')

\# 直波导 2 端口（面 '10' + '22'）

add\_ports\_for\_straight\_waveguide(app, waveguide\_name='wg1')

\# 天线 1 端口

add\_port\_for\_antenna(app, waveguide\_name='wg1')
```

> **注意**
>
> ：
>
> `pick_face`
>
>  面编号（如 
>
> `'10'`
>
> , 
>
> `'22'`
>
> ）是 CST 内部编号，当前硬编码从旧 notebook 提取，后续优化为按法向量自动查找。

### 4.4 StraightWaveguide — 直波导模板（端到端）



```
from templates import StraightWaveguide

wg = StraightWaveguide(

&#x20;   topology='AB',           # 'AB' 或 'BA'

&#x20;   length=18,               # 波导长度（晶格数）

&#x20;   lattice\_constant=0.2425, # 晶格常数 a (mm)

&#x20;   height=0.25,             # 硅片厚度 h (mm)

&#x20;   large\_hole\_ratio=0.65,   # 大孔比例

&#x20;   small\_hole\_ratio=0.35,   # 小孔比例

&#x20;   feed\_type='ab\_elliptical', # 馈源类型

&#x20;   freq\_range=(300, 380),   # 频率范围 GHz

&#x20;   monitors=('E',),         # 监视器

&#x20;   output\_path=r'D:\out\wg.cst',

)

wg.preview()          # matplotlib 预览路径

wg.build\_all()        # 端到端建模（参数→基板→VPC→晶体→feed→波导→端口→求解器）

wg.save()             # 保存 .cst

\# wg.run()            # 运行仿真
```

**内部流程**：



1. 构建 path：`.start(0,-1).move(length+1, 'c')` → \[(0,-1), (0,length)]

2. 定义 CST 参数（a/h/l1/l2/e1/e2 + 路径点 + 阵列范围 + feed + waveguide）

3. `build_substrate` → `build_vpc_regions` → `build_topological_crystal`

4. `build_feed(ab_elliptical)` → `build_waveguide`

5. `mirror`（feed + waveguide 到右端，中心点 p2x/2）

6. `add_ports_for_straight_waveguide`（2 端口）

7. `integrate`（vpca + feed + vpcb）

8. `configure_solver`

**被优化掉的旧代码**：约 200 行 → 约 10 行。

### 4.5 UnitAntenna — 单元天线模板（端到端）



```
from templates import UnitAntenna

ant = UnitAntenna(

&#x20;   bend\_angle=120,              # 拐弯角度（60°倍数，0=直波导型）

&#x20;   straight\_length=18,           # 直段长度（晶格数）

&#x20;   arm\_length=14,                # 臂长（拐弯后长度，晶格数）

&#x20;   topology='BA',                # 默认 BA

&#x20;   lattice\_constant=0.2425,

&#x20;   height=0.25,

&#x20;   feed\_type='ba\_tapered',       # 默认 BA 型馈源

&#x20;   radiator=None,                 # 辐射体类型（None/'cylinder'）

&#x20;   radiator\_radius=0.3,           # 圆柱辐射体半径

&#x20;   freq\_range=(300, 380),

&#x20;   monitors=('E', 'Farfield'),    # 默认含远场

&#x20;   output\_path=r'D:\out\ant.cst',

)

ant.preview()

ant.build\_all()

ant.save()
```

**内部 path 构建**：



```
b = TopoPath.builder(a).start(0, -1).move(straight\_length + 1, 'c')

if bend\_angle != 0:

&#x20;   b.turn(bend\_angle).move(arm\_length + 1, 'along')

self.path = b.build()
```

**自动推断**：`topology='BA'`, `monitors=('E','Farfield')`, 1 端口



***

## 五、快速上手指南

### 5.1 环境准备



```
import sys

sys.path.append(r'D:\成电博士生涯\自动建模算法尝试\TPC')
```

Python 环境：使用 Anaconda Python（`D:\Anaconda\python.exe`），需有 numpy/matplotlib。

### 5.2 最简用法（模板层，推荐）



```
import sys

sys.path.append(r'D:\成电博士生涯\自动建模算法尝试\TPC')

from templates import StraightWaveguide, UnitAntenna

\# 直波导

wg = StraightWaveguide(topology='AB', length=18, output\_path=r'D:\out\wg.cst')

wg.preview()

wg.build\_all()

wg.save()

\# 单元天线

ant = UnitAntenna(bend\_angle=120, straight\_length=18, arm\_length=14,

&#x20;                  output\_path=r'D:\out\ant.cst')

ant.preview()

ant.build\_all()

ant.save()
```

### 5.3 进阶用法（Modeler 层，灵活控制）



```
from topo\_modeler import TopoModeler

from mesh\_grid.tri\_grid import TopoPath

\# 自定义路径

path = (TopoPath.builder(a=0.2425)

&#x20;       .start(0, -1).move(19, 'c').turn(60).move(10, 'along').build())

modeler = TopoModeler(template\_cst='tmp.cst')

modeler.set\_path(path)

modeler.set\_topology('BA')  # 手动覆盖自动推断

modeler.set\_parameters({'a': 0.2425, 'h': 0.25, 'l1': 0.1576, 'l2': 0.0849})

\# 分步构建，灵活控制

modeler.build\_substrate()

modeler.build\_vpc\_regions()

modeler.build\_crystal()

modeler.build\_feed(feed\_type='ba\_tapered')

modeler.build\_waveguide()

modeler.add\_ports()

modeler.configure\_solver(freq\_range=(300, 380))

modeler.save('custom.cst')
```

### 5.4 底层用法（Builder 层，完全控制）



```
from topo\_modeler.builders import (

&#x20;   build\_substrate, build\_vpc\_regions, build\_topological\_crystal,

&#x20;   build\_feed, build\_waveguide, add\_ports\_for\_straight\_waveguide,

&#x20;   configure\_solver,

)

\# 直接调用各个 builder，完全自定义

build\_substrate(app, path, name='my\_sub')

build\_vpc\_regions(app, path, topology='AB')

build\_topological\_crystal(app, path, topology='AB', xup=26, yup=15, ydn=1)

build\_feed(app, feed\_type='ab\_elliptical', name='my\_feed')

build\_waveguide(app, name='my\_wg')

add\_ports\_for\_straight\_waveguide(app, waveguide\_name='my\_wg')

configure\_solver(app, freq\_range=(300, 380), monitors=('E',))
```

### 5.5 参数化路径（CST 中可调整长度）



```
from mesh\_grid.tri\_grid import TopoPath

\# 符号步数：x1/y1 是 CST 参数，可在 CST 中修改

path = (TopoPath.builder(a=0.2425)

&#x20;       .start(0, 0)

&#x20;       .move('x1', 'c')

&#x20;       .turn(120)

&#x20;       .move('y1', 'along')

&#x20;       .build(param\_values={'x1': 18, 'y1': 14}))

path.auto\_define\_cst\_params(app)

\# 在 CST 中修改 x1/y1 参数，路径长度自动更新！
```



***

## 六、API 速查表

### 6.1 TopoPath（mesh\_grid.tri\_grid）



| 入口                                       | 说明             |
| ---------------------------------------- | -------------- |
| `TopoPath.builder(a, name)`              | 创建构建器          |
| `TopoPath.from_lattice(points, a, name)` | 从 (r,c) 列表直接创建 |

### 6.2 Builders（topo\_modeler.builders）



| 函数                                           | 说明         | 返回值                      |
| -------------------------------------------- | ---------- | ------------------------ |
| `build_substrate(app, path, ...)`            | 基板         | solid 名称                 |
| `build_vpc_regions(app, path, ...)`          | VPC-A/B 区域 | (vpca, vpcb)             |
| `build_topological_crystal(app, path, ...)`  | 光子晶体阵列     | (crystal\_a, crystal\_b) |
| `build_feed(app, feed_type, ...)`            | 馈源（3 种类型）  | feed 名称                  |
| `build_waveguide(app, ...)`                  | 空心矩形波导     | wg 名称                    |
| `add_waveguide_port(app, ...)`               | 单端口        | 端口号                      |
| `add_ports_for_straight_waveguide(app, ...)` | 直波导 2 端口   | (1, 2)                   |
| `add_port_for_antenna(app, ...)`             | 天线 1 端口    | 1                        |
| `configure_solver(app, ...)`                 | 求解器配置      | None                     |

### 6.3 TopoModeler（topo\_modeler）



| 方法                           | 说明                    |
| ---------------------------- | --------------------- |
| `set_path(path)`             | 设置路径，自动推断 model\_type |
| `set_topology(topology)`     | 设置拓扑相（AB/BA）          |
| `set_parameters(params)`     | 批量设置参数                |
| `set_parameter(name, value)` | 设置单个参数                |
| `build_substrate()`          | 构建基板                  |
| `build_vpc_regions()`        | 构建 VPC 区域             |
| `build_crystal()`            | 构建光子晶体                |
| `build_feed()`               | 构建馈源                  |
| `build_waveguide()`          | 构建波导                  |
| `add_ports()`                | 添加端口                  |
| `configure_solver()`         | 配置求解器                 |
| `build_all()`                | 端到端一键建模               |
| `save(path)`                 | 保存 .cst               |
| `run()`                      | 运行仿真                  |
| `preview()`                  | matplotlib 预览         |
| `get_built_parts()`          | 获取已构建部件名称             |

### 6.4 Templates（templates）



| 类                   | 说明      | 关键参数                                                 |
| ------------------- | ------- | ---------------------------------------------------- |
| `StraightWaveguide` | 直波导端到端  | topology, length, freq\_range                        |
| `UnitAntenna`       | 单元天线端到端 | bend\_angle, straight\_length, arm\_length, radiator |



***

## 七、与旧代码的对应关系



| 旧代码（notebook 中手写）                | 新代码（topo\_modeler）                           | 优化效果       |
| -------------------------------- | -------------------------------------------- | ---------- |
| 手写 `px1,py1,...,px6,py6`（10 + 行） | `path.auto_define_cst_params(app)`（1 行）      | 消除重复计算     |
| 手写 `xup,yup,ydn` 推导              | `path.get_array_range()`（1 行）                | 自动推导       |
| 手写基板 polyline 顶点（8 + 行）          | `build_substrate(app, path)`（1 行）            | 自动生成       |
| 手写 VPC 区域（20 + 行）                | `build_vpc_regions(app, path)`（1 行）          | 自动生成 + 裁剪  |
| 手写光子晶体阵列（40 + 行）                 | `build_topological_crystal(app, path)`（1 行）  | 超元胞逻辑封装    |
| 手写 feed1/feed2（25 + 行）           | `build_feed(app, feed_type=...)`（1 行）        | 3 种类型统一    |
| 手写 wg1/wg1\_1+subtract（8 行）     | `build_waveguide(app)`（1 行）                  | 自动计算壁厚     |
| 手写 pick\_face+add\_port（4 行）     | `add_ports_for_straight_waveguide(app)`（1 行） | 自动推断端口数    |
| 手写求解器 VBA（40 + 行）                | `configure_solver(app)`（1 行）                 | 调用 TPC 库方法 |
| 完整 notebook（200 + 行）             | `StraightWaveguide(...).build_all()`（1 行）    | 端到端封装      |



***

## 八、固定物理参数



| 参数   | 值                 | 说明            |
| ---- | ----------------- | ------------- |
| a    | 0.2425 mm         | 晶格常数          |
| h    | 0.25 mm           | 硅片厚度          |
| 大孔比例 | 0.65              | l1 = 0.65 × a |
| 小孔比例 | 0.35              | l2 = 0.35 × a |
| e1   | a/2 = 0.12125 mm  | 三角晶格 x 方向半间距  |
| e2   | a√3/2 ≈ 0.2100 mm | 三角晶格 y 方向半间距  |
| 工作频段 | \~300 GHz         | 太赫兹频段         |



***

## 九、已知限制与后续优化



1. **pick\_face 面编号硬编码**：当前端口面编号（'10','22'）从旧 notebook 提取，后续优化为按法向量自动查找

2. **透镜未实现**：GRIN 透镜（阶段 4）尚未实现，含透镜的 notebook 暂不能用模板

3. **结果读取未实现**：S 参数 / 远场 / E 场结果读取（阶段 5）尚未实现

4. **多端口未实现**：3 端口 / 4 端口天线（阶段 6）尚未实现

5. **符号路径阵列范围**：符号路径的 `get_array_range()` 需要 `param_values` 才能数值化，后续可优化为返回 CST 表达式



***

*文档版本：阶段 0-3 完成版 | 生成时间：2026-09-14*