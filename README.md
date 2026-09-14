# TPC —— 拓扑光子晶体 CST 自动化建模库

```text
D:\成电博士生涯\自动建模算法尝试\TPC\
├── cst_solver/      CST VBA → Python 封装（Mixin 聚合，入口 setup）
├── mesh_grid/       纯算法：tri_grid（三角晶格/路径 DSL）、hex_grid（六边形/DXF）
├── topo_modeler/    建模引擎：TopoModeler + builders/ 各部件构建器
└── templates/       端到端模板（⚠ 当前有签名 bug，见 SKILL.md §6）
```

## 📖 先读哪个（AI 助手：读源码前先读对应的 SKILL.md，不要通读整包）

| 你的目的 | 读哪份 |
| --- | --- |
| **用库建模型**（写 notebook、排错、验收） | [`SKILL.md`](./SKILL.md) —— 使用与排错手册：按需查阅地图、报错定位表、三条硬约定（z 平面/布尔语义/阵列范围）、已知库缺陷、验收清单 |
| **维护库本身**（新增 VBA 封装、修库内部缺陷、改存根与文档） | [`.github/skills/cst-solver-dev/SKILL.md`](./.github/skills/cst-solver-dev/SKILL.md) —— 开发技能；把 TPC 作为工作区打开时自动加载，也可 `/cst-solver-dev` 调用 |
| 栅格/透镜算法细节 | [`mesh_grid/tri_grid/SKILL.md`](./mesh_grid/tri_grid/SKILL.md)、[`mesh_grid/hex_grid/SKILL.md`](./mesh_grid/hex_grid/SKILL.md) |

## 快速开始

```python
import sys; sys.path.append(r'D:\成电博士生涯\自动建模算法尝试\TPC')
from cst_solver import setup                       # CST 工程控制
from mesh_grid.tri_grid import TopoPath            # 路径 DSL
from topo_modeler.builders import build_feed       # 部件构建器

path = TopoPath.builder(a=0.2425, name='p').start(0, 0).move(9, 'c').build()
app = setup('tmp.cst')                             # 模板需在当前工作目录
```

## 环境配置

`cst_solver/config.py` 里设置 `CST_INSTALL_PATH`（该文件 gitignored，逐机配置）；
DLL/库路径自动从安装路径推导。
