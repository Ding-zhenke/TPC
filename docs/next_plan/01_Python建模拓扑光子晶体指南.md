# Python 建模拓扑光子晶体指南（给 AI 看）

> 本文档面向 AI 助手，说明如何使用 Python + 自定义库自动化控制 CST Studio Suite 建模拓扑光子晶体。所有内容基于现有工程实际代码提炼，非凭空编写。



***

## 一、工程与库概览

### 1.1 源码位置



| 内容                 | 路径                        |
| ------------------ | ------------------------- |
| 拓扑光子晶体 notebook 工程 | `D:\成电博士生涯\拓扑光子晶体模型\硅基\`  |
| 自定义 Python 库（TPC）  | `D:\成电博士生涯\自动建模算法尝试\TPC\` |

### 1.2 核心库

工程依赖三个自定义库（已重构为包，旧兼容入口仍保留）：



| 库         | 包路径                   | 旧兼容入口           | 作用                    |
| --------- | --------------------- | --------------- | --------------------- |
| CST 自动化接口 | `cst_solver/`         | `cst_solver.py` | 控制 CST 建模、仿真、结果读取     |
| 三角形网格     | `mesh_grid/tri_grid/` | `tri_lib.py`    | 三角晶格生成、坐标转换、区域选择、可视化  |
| 六边形网格     | `mesh_grid/hex_grid/` | `hexlib.py`     | 六边形网格生成、GRIN 透镜建模、可视化 |

**推荐导入方式（新代码）：**



```
import sys

sys.path.append(r'D:\成电博士生涯\自动建模算法尝试\TPC')

from cst\_solver import setup, result

from mesh\_grid.tri\_grid import (build\_triangle\_lattice, plot\_triangle\_grid,

&#x20;                                 path\_loc\_to\_xy, select\_inside, find\_different\_points,

&#x20;                                 find\_corner\_points, plot\_tri\_color)

from mesh\_grid.hex\_grid import HexLib, HexGridVisualizer

import numpy as np

import matplotlib.pyplot as plt

from tqdm import tqdm
```

**现有 notebook 中的导入方式（旧兼容，仍可运行但有 FutureWarning）：**



```
import sys

sys.path.append(r'D:\成电博士生涯\自动建模算法尝试\TPC')

from tri\_lib import \*          # 旧入口，等价于 from mesh\_grid.tri\_grid import \*

from cst\_solver import setup   # 旧入口，等价于 from cst\_solver import setup
```

### 1.3 第三方依赖



* `numpy` — 数值计算、坐标数组

* `matplotlib` — 拓扑结构预览绘图

* `tqdm` — 进度条

* `cst`（CST 自带 Python 库，由 `cst_solver` 自动加载）— CST 交互接口



***

## 二、核心 API 速查

### 2.1 `cst_solver.setup` 类（CST 控制核心）

`setup` 是通过 20+ Mixin 多继承聚合的类，提供 150+ 方法。以下是建模中最常用的：

#### 参数与频率



```
app.para('h', 0.25)                  # 定义/设置 CST 参数（值可为数字或表达式字符串）

app.para('e1', 'a/2')                # 参数可以是 CST 表达式

app.freq\_limit('fmin', 'fmax')       # 设置频率范围（参数名）
```

#### 材料



```
app.new\_material('Copper (annealed)')   # 添加材料（从 CST 材料库）

app.new\_material('Silicon (lossy)')
```

#### 基本体建模



```
app.triangle('a', 'h', center=\['x','y','z'], theta=\[0,0,0], name='tri', curve='curve1')

app.hexagon('r', 'h', center=\[...], theta=\[0,0,90], name='hex', curve='curve1')

app.square(xmin, xmax, ymin, ymax, zmin, zmax, name, component, material)

app.cylinder(\[p1x,p1y], \[p2x,p2y], \[zmin,zmax], name, axis, component, material)

app.create\_elliptical\_cylinder(name, x\_radius, y\_radius, height, axis, material)
```

#### 曲线与拉伸



```
app.polyline(data, name, curve='curve1')   # data 为 \[\[x,y],...] 列表，元素可为数字或字符串表达式

app.extrude('curve1:name', name, 'h', material='Silicon (lossy)')
```

#### 布尔运算



```
app.add('obj1', 'obj2', component='component1')

app.substract('obj1', 'obj2', 'component1')   # 注意：方法名是 substract（非 subtract）

app.intersect('obj1', 'obj2', 'component1')

app.insert('obj1', 'obj2', 'component1')
```

#### 变换



```
app.translate(name, \[dx,dy,dz], copy=False, unite=False, repetitions='int(n)', log\_flag=1)

app.rotation(name, angle=\[0,0,120], repetition=2, copy=True, unite=True)

app.mirror(name, \[px,py,pz], \[nx,ny,nz], copy=True, unite=True)
```

#### 选取与端口



```
app.pick\_face('obj', '10')       # 拾取面（面编号需在 CST 中确认）

app.add\_port(1)                   # 添加波导端口

app.add\_port(1, shield='electric')
```

#### 监视器与求解器



```
f\_monitor = np.arange(310, 322, 2)

app.define\_monitor('E', f\_monitor)          # E 场监视器

app.define\_monitor('Farfield', f\_monitor)   # 远场监视器

\# 求解器配置（通过 VBA 字符串注入历史树）

solver\_vba = """With Solver ... End With"""

app.cst\_file.model3d.add\_to\_history("Define Solver", solver\_vba)
```

#### 保存与运行



```
app.cst\_file.save(r'path\to\project.cst', include\_results=False, allow\_overwrite=True)

\# app.run()  # 运行仿真（注释掉则只建模不仿真）
```

### 2.2 `mesh_grid.tri_grid` 三角形网格



```
\# 生成三角晶格

\_, centers\_up, centers\_dn, \_, \_ = build\_triangle\_lattice(rows, cols, a, offset=offset)

\# 可视化

fig, ax = plot\_triangle\_grid(rows, cols, a, offset=offset, show\_labels=True, show\_points=False)

tri = plot\_tri\_color((x, y), l, angle, color='#RRGGBB')  # 返回 matplotlib Polygon

ax.add\_patch(tri)

\# 坐标转换

point\_xy = path\_loc\_to\_xy(path\_loc, a)  # 晶格坐标 -> 物理坐标

\# 空间分析

p0 = find\_corner\_points(centers\_up)              # 找网格顶点

inside\_up = select\_inside(centers\_up, polygon)    # 选多边形内的点

diff = find\_different\_points(all\_points, subset)   # 找差集点
```

### 2.3 `mesh_grid.hex_grid` 六边形网格（GRIN 透镜用）



```
visualizer = HexGridVisualizer(hex\_size=HEX\_SIZE, orientation="pointy", origin=(0,0))

grid\_hexes = visualizer.hex\_lib.create\_hex\_grid\_hexagonal(N)  # N 层正六边形网格

visualizer.set\_grid(grid\_hexes)

for hex\_coord in grid:

&#x20;   loc = visualizer.hex\_lib.hex\_to\_pixel(hex\_coord)  # 六边形坐标 -> 像素坐标

&#x20;   distance = np.sqrt(loc\[0]\*\*2 + loc\[1]\*\*2)

&#x20;   # 根据距离设置半径（渐变折射率）

&#x20;   app.hexagon(f'r1+(r2-r1)\*({distance}-d0)/(N\*a2-d0)', 'h',

&#x20;               center=\[loc\[0], loc\[1], '-h/2'], theta=\[0,0,90], name=f'GRIB-{n}')
```



***

## 三、标准建模流程（通用骨架）

所有拓扑光子晶体模型都遵循以下 10 步流程：



```
1\. 导入库

2\. 用 matplotlib 预览拓扑结构（计算 VPC-A/B 区域点集）

3\. 定义几何参数

4\. 打开 CST 工程 (setup)

5\. 传递参数到 CST (para)

6\. 计算区域坐标点 (px/py 等)

7\. 添加材料、设置频率

8\. 建模：基板 → VPC区域 → 光子晶体阵列 → 探针/馈电 → 端口

9\. 设置监视器、求解器配置

10\. 保存 .cst 文件
```



***

## 四、示例一：拓扑波导（直波导）

> 参考文件：
>
> `D:\成电博士生涯\拓扑光子晶体模型\硅基\直波导\AB\AB_feed.ipynb`

### 4.1 结构特点



* **类型**：直波导，两端口（Port 1 / Port 2）

* **拓扑相**：AB 型（VPC-A 在上半区，VPC-B 在下半区）

* **馈电**：硅基探针 + 矩形铜波导（WR 标准波导）

* **仿真**：S 参数（传输 / 反射），E 场监视器

### 4.2 关键参数



```
h = 0.25          # 硅片厚度 (mm)

a = 0.2425        # 晶格常数 (mm)

l1 = 0.35 \* a     # VPC-A 三角孔边长

l2 = 0.65 \* a     # VPC-B 三角孔边长（与 A 互补）

x = np.array(\[18, 5])   # 晶格列数（两段）

y = np.array(\[14, 5])   # 晶格行数（两段）

x0 = 4             # 探针起始列位置

\# 探针尺寸

lf1, lf2, lf3 = 0.2, 3, 0.2     # 探针长度方向分段

lf4, lf5, lf6 = 0.2, 3, 0.2

wf1, wf2 = 0.2, 0.2              # 探针宽度

\# 矩形波导（铜）

wg\_a = 0.7312    # 波导宽边 (mm)

wg\_b = 0.3756    # 波导窄边 (mm)

wg\_t = 0.2        # 波导壁厚
```

### 4.3 拓扑预览（matplotlib）



```
def tp(ax, up, dn, l1, l2, color):

&#x20;   """在 ax 上绘制朝上/朝下三角形"""

&#x20;   for (xi, yi) in up:

&#x20;       tri = plot\_tri\_color((xi, yi), l1, 0, color=color\[0])

&#x20;       ax.add\_patch(tri)

&#x20;   for (xj, yj) in dn:

&#x20;       tri = plot\_tri\_color((xj, yj), l2, 60, color=color\[1])

&#x20;       ax.add\_patch(tri)

def plot\_power\_divider(a, x, y):

&#x20;   """预览拓扑结构，返回 VPC-A/B 的上下三角中心点集"""

&#x20;   color = \['#E6B4C8', '#B4DCBE']

&#x20;   rows = \[-y\[0], y\[0]]

&#x20;   cols = \[-1, x\[0]]

&#x20;   l1 = 0.65 \* a

&#x20;   l2 = 0.35 \* a

&#x20;   h = a \* np.sin(np.deg2rad(60))

&#x20;   r = a / np.sqrt(3)

&#x20;   offset = (a/2, h - r)

&#x20;   \_, centers\_up, centers\_dn, \_, \_ = build\_triangle\_lattice(rows, cols, a, offset=offset)

&#x20;   fig, ax = plot\_triangle\_grid(rows, cols, a, offset=offset, show\_labels=True, show\_points=False)

&#x20;   # 主路径（波导走向）

&#x20;   path1 = np.vstack(((0, -1), (0, x\[0])))

&#x20;   point1 = path\_loc\_to\_xy(path1, a)

&#x20;   ax.plot(point1\[:, 0], point1\[:, 1], color='green', lw=3, marker='o')

&#x20;   p0 = find\_corner\_points(centers\_up)

&#x20;   area1 = np.vstack((p0\[0, :], point1, p0\[1, :], p0\[0, :]))

&#x20;   area1\_up = select\_inside(centers\_up, area1)

&#x20;   area1\_dn = select\_inside(centers\_dn, area1)

&#x20;   vpca\_up, vpca\_dn = area1\_up, area1\_dn

&#x20;   tp(ax, vpca\_up, vpca\_dn, l1, l2, color)

&#x20;   vpcb\_up = find\_different\_points(np.array(centers\_up), vpca\_up)

&#x20;   vpcb\_dn = find\_different\_points(np.array(centers\_dn), vpca\_dn)

&#x20;   tp(ax, vpcb\_up, vpcb\_dn, l2, l1, color\[::-1])

&#x20;   plt.legend()

&#x20;   plt.tight\_layout()

&#x20;   plt.show()

&#x20;   return vpca\_dn, vpca\_up, vpcb\_dn, vpcb\_up
```

### 4.4 CST 建模步骤



```
\# 1. 打开工程

app = setup('tmp.cst')

\# 2. 传递参数

for name, val in \[('h',h), ('a',a), ('e1','a/2'), ('e2','a/2\*sqr(3)'),

&#x20;                  ('l1','0.35\*a'), ('l2','0.65\*a'),

&#x20;                  ('lf1',lf1), ('lf2',lf2), ('lf3',lf3),

&#x20;                  ('lf4',lf4), ('lf5',lf5), ('lf6',lf6),

&#x20;                  ('wf1',wf1), ('wf2',wf2),

&#x20;                  ('wg\_a',wg\_a), ('wg\_b',wg\_b), ('wg\_t',wg\_t),

&#x20;                  ('x0',x0), ('x01',0)]:

&#x20;   app.para(name, val)

for i in range(len(x)): app.para(f'x{i+1}', x\[i])

for i in range(len(y)): app.para(f'y{i+1}', y\[i])

\# 3. 区域坐标点（CST 表达式）

app.para('px1', '0'); app.para('py1', '0')

app.para('px2', 'px1+x1\*a'); app.para('py2', 'py1')

app.para('px3', 'px2+y1\*e1'); app.para('py3', 'py1-y1\*e2')

app.para('px4', 'px3+x2\*a+y1\*e1\*2'); app.para('py4', 'py3')

app.para('xmax', 'a\*(x1)+(y1)\*e1+e1')

app.para('ymax\_up', 'e2\*(y1)'); app.para('ymax\_dn', '-e2\*(y1)')

app.para('xup', 'x1+int((y1)/2)'); app.para('yup', 'y1'); app.para('ydn', 'y1')

\# 4. 材料与频率

app.new\_material('Copper (annealed)')

app.new\_material('Silicon (lossy)')

app.para('fmin', '300'); app.para('fmax', '380')

app.freq\_limit('fmin', 'fmax')

\# 5. 基板（vpca / vpcb 两块，用 polyline + extrude）

for i in \['vpca', 'vpcb']:

&#x20;   data = \[\[0,0], \["0","ymax\_up"], \["px2","py2+y1\*e2"],

&#x20;           \["px2","py2"], \["px2",'ymax\_dn'], \[0,'ymax\_dn'], \[0,0]]

&#x20;   app.polyline(data, i)

&#x20;   app.extrude(f'curve1:{i}', i, 'h', material='Silicon (lossy)', log\_flag=1)

&#x20;   app.translate(i, \['0','0','h/2'], copy=False, unite=False, log\_flag=1)

\# 6. VPC-A 区域裁剪

data = \[\["px1","py1"], \["0","ymax\_dn"], \["px2","ymax\_dn"], \["px2","py2"], \["px1","py1"]]

app.polyline(data, 'vpc\_a\_area1')

app.extrude('curve1:vpc\_a\_area1', 'vpc\_a\_area1', 'h', material='Silicon (lossy)', log\_flag=1)

app.translate('vpc\_a\_area1', \['0','0','-h/2'], copy=False, unite=False, log\_flag=1)

app.insert('vpcb', 'vpc\_a\_area1', 'component1')

app.intersect('vpca', 'vpc\_a\_area1', 'component1')

\# 7. 生成光子晶体三角孔阵列（核心！）

l = \['l1', 'l2']

tick = \['A', 'B']

for i in range(2):

&#x20;   # 一个超元胞：大三角（挖空参考）+ 小三角（实际孔）

&#x20;   app.triangle('a', 'h', center=\['-a/2','sqr(3)/2\*a-a/sqr(3)','-h/2'],

&#x20;                 theta=\[0,0,0], name='g1'+tick\[i], curve='curve1')

&#x20;   app.triangle('a', 'h', center=\['0','a/sqr(3)','-h/2'],

&#x20;                 theta=\[0,0,180], name='g2'+tick\[i], curve='curve1')

&#x20;   app.triangle(l\[i], 'h', center=\['-a/2','sqr(3)/2\*a-a/sqr(3)','-h/2'],

&#x20;                 theta=\[0,0,0], name='tri\_up\_'+tick\[i], curve='curve1')

&#x20;   app.triangle(l\[1-i], 'h', center=\['0','a/sqr(3)','-h/2'],

&#x20;                 theta=\[0,0,180], name='tri\_dn\_'+tick\[i], curve='curve1')

&#x20;   app.add('g1'+tick\[i], 'g2'+tick\[i])

&#x20;   app.add('tri\_up\_'+tick\[i], 'tri\_dn\_'+tick\[i])

&#x20;   app.substract('g1'+tick\[i], 'tri\_up\_'+tick\[i], 'component1')  # 挖出三角孔

&#x20;   # 旋转 120° 复制两次，形成六重对称超元胞

&#x20;   app.rotation('g1'+tick\[i], angle=\[0,0,120], repetition=2, copy=True, unite=True)

&#x20;   # 平移阵列复制

&#x20;   app.translate('g1'+tick\[i], \['a','0','0'], repetitions='int(xup)',

&#x20;                 copy=True, unite=True, log\_flag=1)

&#x20;   app.translate('g1'+tick\[i], \['0','e2\*2','0'], repetitions='int(yup/2)',

&#x20;                 copy=True, unite=True, log\_flag=1)

&#x20;   app.translate('g1'+tick\[i], \['0','-e2\*2','0'], repetitions='int(ydn/2)',

&#x20;                 copy=True, unite=True, log\_flag=1)

\# 8. 相交裁剪到 VPC 区域

app.intersect('vpca', 'g1A', 'component1')

app.intersect('vpcb', 'g1B', 'component1')

\# 9. 探针（硅基渐变馈电）

data = \[\["x0\*a","0"], \["x0\*a-e1","e2"], \["0","e2"],

&#x20;       \["0","e2/2+wf1/2"], \["-lf1","e2/2+wf1/2"], \["-lf1","e2/2-wf1/2"],

&#x20;       \["0","e2/2-wf1/2"], \["0","0"], \["x0\*a","0"]]

app.polyline(data, name='feed1', curve='curve1')

app.extrude('curve1', 'feed1', 'h', material='Silicon (lossy)')

\# 椭圆过渡

app.create\_elliptical\_cylinder(name='feed1\_epc', x\_radius='lf2', y\_radius='wf1/2',

&#x20;                               height='h', axis='z', material='Silicon (lossy)')

app.square('0','lf2', '-wf1/2','wf1/2', '0','h', name='feed1\_cut1', material='Silicon (lossy)')

app.substract('feed1\_epc', 'feed1\_cut1', 'component1')

app.translate('feed1\_epc', \['-(lf1)','e2/2','0'], copy=False, unite=False, log\_flag=1)

app.add('feed1', 'feed1\_epc')

app.translate('feed1', \['0','0','-h/2'], copy=False, unite=False, log\_flag=1)

\# 10. 矩形铜波导（空心波导 = 外方体 - 内方体）

app.square('-lf1-lf2-lf3','-lf1', 'e2/2-wg\_b/2','e2/2+wg\_b/2',

&#x20;           '-wg\_a/2','+wg\_a/2', 'wg1\_1', 'component1', 'Copper (annealed)')

app.square('-lf1-lf2-lf3','-lf1', 'e2/2-wg\_b/2-wg\_t','e2/2+wg\_b/2+wg\_t',

&#x20;           '-wg\_a/2-wg\_t','+wg\_a/2+wg\_t', 'wg1', 'component1', 'Copper (annealed)')

app.substract('wg1', 'wg1\_1')

\# 11. 镜像复制到另一端（直波导两端口）

app.mirror('wg1', \['x1\*a/2',0,0], \['1','0','0'], copy=True, unite=True)

app.mirror('feed1', \['x1\*a/2',0,0], \['1','0','0'], copy=True, unite=True)

\# 12. 端口

app.pick\_face('wg1', '10'); app.add\_port(1)

app.pick\_face('wg1', '22'); app.add\_port(2)

\# 13. 整合

app.add('vpca', 'feed1')

app.add('vpca', 'vpcb')

\# 14. 监视器

f\_monitor = np.arange(310, 322, 2)

app.define\_monitor('E', f\_monitor)

\# 15. 求解器配置（VBA）

solver\_cfg = """With Solver

&#x20;    .UseParallelization "True"

&#x20;    .MaximumNumberOfThreads "1024"

&#x20;    .MaximumNumberOfCPUDevices "8"

&#x20;    .HardwareAcceleration "True"

&#x20;    .MaximumNumberOfGPUs "1"

End With

Mesh.SetCreator "High Frequency"

With Solver

&#x20;    .Method "Hexahedral"

&#x20;    .CalculationType "TD-S"

&#x20;    .StimulationPort "1"

&#x20;    .StimulationMode "1"

&#x20;    .SteadyStateLimit "-30"

&#x20;    .MeshAdaption "False"

End With

"""

app.cst\_file.model3d.add\_to\_history("Define Solver", solver\_cfg)

\# 16. 保存

app.cst\_file.save(r'D:\成电博士生涯\拓扑光子晶体模型\硅基\直波导\AB\AB\_feed.cst',

&#x20;                  include\_results=False, allow\_overwrite=True)
```



***

## 五、示例二：拓扑天线

> 参考文件：
>
> `D:\成电博士生涯\拓扑光子晶体模型\硅基\普通单元天线\Ant1_D_BA_120D_circle_DF.ipynb`
> 进阶参考（GRIN 透镜天线）：
>
> `D:\成电博士生涯\拓扑光子晶体模型\硅基\单元天线GRIB\AB型\180°透镜\Ant1_grid_circle.ipynb`

### 5.1 结构特点



* **类型**：单元天线，单端口（Port 1）

* **拓扑相**：BA 型（VPC-B 在上半区，VPC-A 在下半区，与波导互补）

* **馈电**：硅基探针 + 圆柱 / 椭圆辐射体

* **仿真**：远场方向图（Farfield），S11，E 场监视器

* **与波导的关键区别**：


  * 只有一个端口（不镜像）

  * 有辐射体（圆柱天线 / GRIN 透镜）

  * 必须加 Farfield 监视器

  * 探针形状不同（更宽的渐变过渡）

### 5.2 关键参数



```
h = 0.25

a = 0.2425

l1 = 0.65 \* a     # 注意：BA 型 l1/l2 与 AB 型互换

l2 = 0.35 \* a

x = np.array(\[18, 4])

y = np.array(\[14, 4])

x0 = 4

\# 探针（BA 型更宽）

lf1=lf2=lf3=lf4=lf5=lf6 = 0.2

wf1=wf2 = 0.2

\# 圆柱辐射体

r\_cyl = 0.5       # 圆柱半径

w\_cyl1 = 0.2      # 馈电端宽度

w\_cyl2 = 0.1      # 辐射端宽度

x\_cyl1 = 0.3

x\_cyl2 = 0.15
```

### 5.3 CST 建模（天线特有部分）

基板、VPC 区域、光子晶体阵列的建模与波导完全相同（见第四章 4.4 节步骤 4-8），以下只列天线特有部分：



```
\# === 探针（BA 型，对称渐变）===

data = \[

&#x20; \["a+x01\*a", "0"], \["e1+x01\*a", "e2"], \["0","e2"],

&#x20; \["0","wf2/2"], \["-lf4","wf2/2"], \["-lf4-lf5","wf2/2"],

&#x20; \["-lf4-lf5","-wf2/2"], \["-lf4","-wf2/2"], \["0","-wf2/2"],

&#x20; \["0","-e2"], \["e1+x01\*a", "-e2"], \["a+x01\*a", "0"]

]

app.polyline(data, name='feed2', curve='curve1')

app.extrude('curve1', 'feed2', 'h', material='Silicon (lossy)')

app.translate('feed2', \['0','0','-h/2'], copy=False, unite=False, log\_flag=1)

\# === 圆柱辐射体（渐变宽度 + 半圆头）===

data = \[

&#x20; \["e1", "0"], \["0","e2"], \["0","w\_cyl1/2"],

&#x20; \["-x\_cyl1","w\_cyl2/2"], \["-x\_cyl1-x\_cyl2","w\_cyl2/2"],

&#x20; \["-x\_cyl1-x\_cyl2","-w\_cyl2/2"], \["-x\_cyl1","-w\_cyl2/2"],

&#x20; \["0","-w\_cyl1/2"], \["0","-e2"], \["e1", "0"]

]

app.polyline(data, name='cylinder\_antenna', curve='curve1')

app.extrude('curve1', 'cylinder\_antenna', 'h', material='Silicon (lossy)')

app.translate('cylinder\_antenna', \['0','0','-h/2'], copy=False, unite=False, log\_flag=1)

\# 半圆头

app.cylinder(\['-x\_cyl1-x\_cyl2-(sqr(r\_cyl^2-(w\_cyl2/2)^2))','0'],

&#x20;             \['r\_cyl',0], \['h/2','-h/2'],

&#x20;             name='cylinder\_antenna\_circle', Material='Silicon (lossy)')

app.add('cylinder\_antenna', 'cylinder\_antenna\_circle', 'component1')

app.mirror('cylinder\_antenna', \[0,0,0], \[1,0,0], copy=False, unite=False)

app.translate('cylinder\_antenna', \['px2+e1','py2','0'], copy=False, unite=False, log\_flag=1)

\# === 单端口 ===

app.pick\_face('feed2', '5')

app.add\_port(1, shield='electric')

\# === 整合 ===

app.add('vpca', 'feed2')

app.add('vpca', 'vpcb')

\# === 监视器（必须加 Farfield！）===

f\_monitor = np.arange(310, 322, 2)

app.define\_monitor('E', f\_monitor)

app.define\_monitor('Farfield', f\_monitor)

\# === 求解器配置（同波导）===

\# ...

\# === 保存 ===

app.cst\_file.save(r'D:\成电博士生涯\拓扑光子晶体模型\硅基\普通单元天线\Ant1\_D\_BA\_120\_cylinder-DF.cst',

&#x20;                  include\_results=False, allow\_overwrite=True)
```

### 5.4 GRIN 透镜天线（进阶）

在基础天线上叠加渐变折射率（GRIN）透镜，使用六边形网格：



```
from mesh\_grid.hex\_grid import HexLib, HexGridVisualizer

HEX\_SIZE = a / np.sqrt(3) / 2

app.para('HEX\_SIZE', 'a/sqr(3)/2')

a2 = HEX\_SIZE \* np.sqrt(3)

app.para('a2', 'HEX\_SIZE\*sqr(3)')

N = (y\[0] + 2) \* 2

app.para('N', '(y1+1)\*2')

d0 = 8 \* HEX\_SIZE \* 2 \* np.sqrt(3)

app.para('d0', '8\*HEX\_SIZE\*2\*sqr(3)')

r = np.array(\[50.5, 61.3]) / 1e3   # 内/外半径

for i in range(len(r)): app.para(f'r{i+1}', r\[i])

visualizer = HexGridVisualizer(hex\_size=HEX\_SIZE, orientation="pointy", origin=(0,0))

grid\_hexes = visualizer.hex\_lib.create\_hex\_grid\_hexagonal(N)

visualizer.set\_grid(grid\_hexes)

count = 0

for hex\_coord in grid:

&#x20;   loc = visualizer.hex\_lib.hex\_to\_pixel(hex\_coord)

&#x20;   distance = np.sqrt(loc\[0]\*\*2 + loc\[1]\*\*2)

&#x20;   if loc\[1] >= 0 and loc\[0] >= 0:  # 第一象限，后续镜像

&#x20;       if distance < d0:

&#x20;           app.hexagon('r1', 'h', center=\[loc\[0],loc\[1],'-h/2'],

&#x20;                       theta=\[0,0,90], name=f'GRIB-{count}', curve='curve1')

&#x20;       else:

&#x20;           app.hexagon(f'r1+(r2-r1)\*({distance}-d0)/(N\*a2-d0)', 'h',

&#x20;                       center=\[loc\[0],loc\[1],'-h/2'], theta=\[0,0,90],

&#x20;                       name=f'GRIB-{count}', curve='curve1')

&#x20;       if count > 0:

&#x20;           app.add('GRIB-0', f'GRIB-{count}')

&#x20;       count += 1

app.mirror('GRIB-0', \[0,0,0], \[1,0,0], copy=True, unite=True)  # 镜像到全平面
```



***

## 六、波导 vs 天线 关键差异对照表



| 维度           | 拓扑波导              | 拓扑天线                 |
| ------------ | ----------------- | -------------------- |
| 端口数          | 2（两端）             | 1（馈电端）               |
| 是否镜像探针       | 是（镜像到另一端）         | 否                    |
| 辐射体          | 无                 | 有（圆柱 / 椭圆 / GRIN 透镜） |
| Farfield 监视器 | 不需要               | 必须                   |
| 探针形状         | 窄渐变 + 椭圆过渡 + 矩形波导 | 宽对称渐变                |
| 拓扑相          | AB 型常见            | BA 型常见               |
| 关注结果         | S21/S11（传输 / 反射）  | S11 + 远场方向图 / 增益     |
| 频率范围         | 300-380 GHz       | 280-380 GHz          |



***

## 七、注意事项与坑



1. `substract`**&#x20;拼写**：库中方法名是 `substract`（非标准 `subtract`），不要写错。

2. `extrude`**&#x20;参数名不一致**：部分旧代码用 `materials=`，部分用 `material=`，新代码统一用 `material=`。

3. **CST 表达式字符串**：`app.para()` 的值可以是字符串表达式（如 `'a/2*sqr(3)'`），CST 会自动解析。`sqr()` 是 CST 的平方根函数（非 Python 的 `sqrt`）。

4. **面编号&#x20;**`pick_face`：面编号（如 `'10'`, `'22'`, `'5'`）是 CST 内部编号，不同结构可能不同，需在 CST 界面中确认。

5. **坐标偏移**：所有结构建模后通常需要 `translate(['0','0','-h/2'])` 使中心在 z=0。

6. `setup('tmp.cst')`：需要 `tmp.cst` 模板文件存在于工作目录，或使用绝对路径。

7. **保存路径**：`app.cst_file.save()` 是直接访问内部属性，路径需用原始字符串或正斜杠。

8. **旧兼容入口**：`from tri_lib import *` 会触发 FutureWarning，新代码应迁移到 `from mesh_grid.tri_grid import ...`。

9. **GRIN 透镜只建第一象限**：通过 `mirror` 复制到全平面，减少建模时间。

10. **光子晶体超元胞**：一个超元胞由 6 个三角孔组成（旋转 120° 复制两次），然后通过 `translate` 阵列复制。