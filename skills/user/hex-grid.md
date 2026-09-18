---
description: 六边形网格核心算法库 — HexLib, HexGridVisualizer, DXF 导出
applyTo: "**/*.py"
---

# mesh_grid.hex_grid — 六边形网格算法库

## 概述
提供六边形网格的完整算法支持，包括立方体坐标系、网格生成、像素坐标转换、matplotlib 可视化和 DXF 导出。

## 核心类

### `HexLib`
六边形网格数学核心。支持 Pointy-top 和 Flat-top 两种朝向。
- 坐标系：立方体 `(q, r, s)` 满足 `q+r+s=0`
- 网格生成：`create_staggered_grid(col_range, row_range)` 交错矩形网格、`create_hex_grid_hexagonal(N)` 正六边形排布
- 坐标转换：`hex_to_pixel()` 和 `pixel_to_hex()`
- 偏移坐标：支持 `qoffset` 和 `roffset` 两种偏移类型（EVEN/ODD）

### `HexGridVisualizer`
matplotlib 可视化器，支持分层着色、坐标标签显示、边界框绘制。

## 工具函数
- `create_hex_polygon(center, cell_width, theta)` — Shapely 六边形
- `save_to_dxf(hex_all, filename, layer_name)` — 合并导出 DXF
- `save_multi_dxf(hex_groups, filename, layer_name)` — 分组导出 DXF
- `read_and_display_dxf_matplotlib(filename)` — 读取显示 DXF

## 示例
```python
from mesh_grid.hex_grid import HexLib
lib = HexLib(hex_size=20, orientation="pointy")
grid = lib.create_staggered_grid((0, 5), (0, 4))
```

## 中文绘图约定

预览已接入自动字体检测。自定义 Matplotlib 图在创建 Figure 前使用 `mesh_grid.plotting.chinese_plot_style(text=实际中文标签, strict=True)`，在上下文内保存。无字体时设置 TPC_CJK_FONT 或用英文标签，不忽略缺字警告。见 [中文绘图指南](../../docs/guides/chinese_plotting.md)。
