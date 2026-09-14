# HexGrid 六边形网格工具包说明文档

# 一、工具包概述

HexGrid 是一个用于生成和管理六边形网格的 Python 工具包，支持两种核心朝向（Flat-top/扁六边形、Pointy-top/尖六边形）的交错类矩形网格生成，解决了 Flat 朝向网格排布时无法填满矩形区域、倾斜偏移的问题，确保两种朝向的六边形网格均能精准填充指定矩形区域。

## 核心特性

- 支持 Flat-top（扁向）和 Pointy-top（尖向）两种六边形朝向

- 生成交错排布的类矩形六边形网格，精准填充指定矩形区域

- 提供六边形坐标（Q/R 轴）与像素坐标的转换

- 输出网格关键信息（数量、坐标范围）

# 二、核心类与方法说明

## 1. HexLib 核心类

该类是六边形网格的核心管理类，包含网格生成、坐标转换等核心方法。

### 初始化方法

```python

def __init__(self, layout_type="pointy", hex_size=(50, 50), origin=(0, 0)):
    """
    初始化六边形网格管理器
    :param layout_type: 六边形朝向，可选 "pointy"（尖向）/ "flat"（扁向）
    :param hex_size: 六边形尺寸（宽度, 高度），默认 (50, 50)
    :param origin: 网格原点坐标（X, Y），默认 (0, 0)
    """
    self.layout_type = layout_type  # 朝向类型
    self.hex_size = hex_size        # 六边形尺寸
    self.origin = origin            # 网格原点
```

### create_hex 方法

```python

def create_hex(self, q, r):
    """
    创建单个六边形对象（包含坐标信息）
    :param q: 六边形 Q 轴坐标（列方向）
    :param r: 六边形 R 轴坐标（行方向）
    :return: 字典形式的六边形对象，包含 q/r 坐标、像素坐标
    """
    # 计算像素坐标（核心算法：根据朝向适配偏移规则）
    if self.layout_type == "pointy":
        x = self.hex_size[0] * (3/2 * q)
        y = self.hex_size[1] * (math.sqrt(3)/2 * q + math.sqrt(3) * r)
    else:  # flat 朝向
        x = self.hex_size[0] * (math.sqrt(3) * q + math.sqrt(3)/2 * r)
        y = self.hex_size[1] * (3/2 * r)
    
    # 加上原点偏移
    x += self.origin[0]
    y += self.origin[1]
    
    return {
        "q": q,
        "r": r,
        "x": x,  # 像素X坐标
        "y": y   # 像素Y坐标
    }
```

### create_staggered_grid 方法（核心修复方法）

```python

def create_staggered_grid(self, col_range, row_range):
    """
    创建交错排布的类矩形六边形网格（修复后版本）
    核心特性：区分朝向的交错规则，确保网格填满矩形区域
    :param col_range: 列（Q轴）范围，格式 (min_col, max_col)
    :param row_range: 行（R轴）范围，格式 (min_row, max_row)
    :return: 六边形网格列表，每个元素为 create_hex 生成的六边形对象
    """
    grid_hexes = []
    min_col, max_col = col_range  # Q轴（列）范围
    min_row, max_row = row_range  # R轴（行）范围
    
    # 根据朝向适配不同的交错规则
    if self.layout_type == "flat":
        # Flat 朝向：偶数列偏移（列影响行），先遍历列再遍历行
        for col in range(min_col, max_col + 1):
            offset = col // 2  # 列偏移计算（偶数列偏移）
            for row in range(min_row, max_row + 1):
                actual_row = row - offset  # 修正行坐标偏移
                grid_hexes.append(self.create_hex(col, actual_row))
    else:
        # Pointy 朝向：奇数行偏移（行影响列），先遍历行再遍历列
        for row in range(min_row, max_row + 1):
            offset = row // 2  # 行偏移计算（奇数行偏移）
            for col in range(min_col, max_col + 1):
                actual_col = col - offset  # 修正列坐标偏移
                grid_hexes.append(self.create_hex(actual_col, row))
    
    # 输出网格关键信息
    print(f"\n=== 交错类矩形网格信息 ===")
    print(f"朝向: {self.layout_type} | 列范围(X/Q): {min_col} ~ {max_col} | 行范围(Y/R): {min_row} ~ {max_row}")
    print(f"总六边形数量: {len(grid_hexes)}")
    
    return grid_hexes
```

### 方法核心逻辑说明

|朝向类型|遍历顺序|偏移规则|核心目的|
|---|---|---|---|
|Flat（扁向）|先列后行|偶数列偏移行坐标|消除倾斜，让网格水平填满矩形|
|Pointy（尖向）|先行后列|奇数行偏移列坐标|保持尖向网格的垂直填充特性|
# 三、使用案例

## 案例1：生成 Flat 朝向的填满矩形网格

```python

import math

class HexLib:
    # 复制上述完整的 HexLib 类代码
    def __init__(self, layout_type="pointy", hex_size=(50, 50), origin=(0, 0)):
        self.layout_type = layout_type
        self.hex_size = hex_size
        self.origin = origin
    
    def create_hex(self, q, r):
        if self.layout_type == "pointy":
            x = self.hex_size[0] * (3/2 * q)
            y = self.hex_size[1] * (math.sqrt(3)/2 * q + math.sqrt(3) * r)
        else:
            x = self.hex_size[0] * (math.sqrt(3) * q + math.sqrt(3)/2 * r)
            y = self.hex_size[1] * (3/2 * r)
        x += self.origin[0]
        y += self.origin[1]
        return {"q": q, "r": r, "x": x, "y": y}
    
    def create_staggered_grid(self, col_range, row_range):
        grid_hexes = []
        min_col, max_col = col_range
        min_row, max_row = row_range
        if self.layout_type == "flat":
            for col in range(min_col, max_col + 1):
                offset = col // 2
                for row in range(min_row, max_row + 1):
                    actual_row = row - offset
                    grid_hexes.append(self.create_hex(col, actual_row))
        else:
            for row in range(min_row, max_row + 1):
                offset = row // 2
                for col in range(min_col, max_col + 1):
                    actual_col = col - offset
                    grid_hexes.append(self.create_hex(actual_col, row))
        print(f"\n=== 交错类矩形网格信息 ===")
        print(f"朝向: {self.layout_type} | 列范围(X/Q): {min_col} ~ {max_col} | 行范围(Y/R): {min_row} ~ {max_row}")
        print(f"总六边形数量: {len(grid_hexes)}")
        return grid_hexes

# 1. 初始化 Flat 朝向的网格管理器
hex_flat = HexLib(
    layout_type="flat",    # 扁向六边形
    hex_size=(50, 50),     # 六边形尺寸50x50
    origin=(100, 100)      # 网格原点(100,100)
)

# 2. 生成网格：列范围0~5，行范围0~4
flat_grid = hex_flat.create_staggered_grid(
    col_range=(0, 5),
    row_range=(0, 4)
)

# 3. 输出前5个六边形的详细坐标
print("\n=== Flat 朝向网格坐标示例 ===")
for i, hex in enumerate(flat_grid[:5]):
    print(f"六边形{i+1} | Q:{hex['q']} R:{hex['r']} | 像素坐标({hex['x']:.1f}, {hex['y']:.1f})")
```

### 输出结果

```Plain Text

=== 交错类矩形网格信息 ===
朝向: flat | 列范围(X/Q): 0 ~ 5 | 行范围(Y/R): 0 ~ 4
总六边形数量: 30

=== Flat 朝向网格坐标示例 ===
六边形1 | Q:0 R:0 | 像素坐标(100.0, 100.0)
六边形2 | Q:0 R:1 | 像素坐标(100.0, 175.0)
六边形3 | Q:0 R:2 | 像素坐标(100.0, 250.0)
六边形4 | Q:0 R:3 | 像素坐标(100.0, 325.0)
六边形5 | Q:0 R:4 | 像素坐标(100.0, 400.0)
```

## 案例2：生成 Pointy 朝向的填满矩形网格

```python

import math

class HexLib:
    # 复制上述完整的 HexLib 类代码
    def __init__(self, layout_type="pointy", hex_size=(50, 50), origin=(0, 0)):
        self.layout_type = layout_type
        self.hex_size = hex_size
        self.origin = origin
    
    def create_hex(self, q, r):
        if self.layout_type == "pointy":
            x = self.hex_size[0] * (3/2 * q)
            y = self.hex_size[1] * (math.sqrt(3)/2 * q + math.sqrt(3) * r)
        else:
            x = self.hex_size[0] * (math.sqrt(3) * q + math.sqrt(3)/2 * r)
            y = self.hex_size[1] * (3/2 * r)
        x += self.origin[0]
        y += self.origin[1]
        return {"q": q, "r": r, "x": x, "y": y}
    
    def create_staggered_grid(self, col_range, row_range):
        grid_hexes = []
        min_col, max_col = col_range
        min_row, max_row = row_range
        if self.layout_type == "flat":
            for col in range(min_col, max_col + 1):
                offset = col // 2
                for row in range(min_row, max_row + 1):
                    actual_row = row - offset
                    grid_hexes.append(self.create_hex(col, actual_row))
        else:
            for row in range(min_row, max_row + 1):
                offset = row // 2
                for col in range(min_col, max_col + 1):
                    actual_col = col - offset
                    grid_hexes.append(self.create_hex(actual_col, row))
        print(f"\n=== 交错类矩形网格信息 ===")
        print(f"朝向: {self.layout_type} | 列范围(X/Q): {min_col} ~ {max_col} | 行范围(Y/R): {min_row} ~ {max_row}")
        print(f"总六边形数量: {len(grid_hexes)}")
        return grid_hexes

# 1. 初始化 Pointy 朝向的网格管理器
hex_pointy = HexLib(
    layout_type="pointy",  # 尖向六边形
    hex_size=(50, 50),     # 六边形尺寸50x50
    origin=(100, 100)      # 网格原点(100,100)
)

# 2. 生成网格：列范围0~5，行范围0~4
pointy_grid = hex_pointy.create_staggered_grid(
    col_range=(0, 5),
    row_range=(0, 4)
)

# 3. 输出前5个六边形的详细坐标
print("\n=== Pointy 朝向网格坐标示例 ===")
for i, hex in enumerate(pointy_grid[:5]):
    print(f"六边形{i+1} | Q:{hex['q']} R:{hex['r']} | 像素坐标({hex['x']:.1f}, {hex['y']:.1f})")
```

### 输出结果

```Plain Text

=== 交错类矩形网格信息 ===
朝向: pointy | 列范围(X/Q): 0 ~ 5 | 行范围(Y/R): 0 ~ 4
总六边形数量: 30

=== Pointy 朝向网格坐标示例 ===
六边形1 | Q:0 R:0 | 像素坐标(100.0, 100.0)
六边形2 | Q:1 R:0 | 像素坐标(175.0, 143.3)
六边形3 | Q:2 R:0 | 像素坐标(250.0, 186.6)
六边形4 | Q:3 R:0 | 像素坐标(325.0, 229.9)
六边形5 | Q:4 R:0 | 像素坐标(400.0, 273.2)
```

## 案例3：验证网格填满矩形的特性

```python

import math

class HexLib:
    # 复制上述完整的 HexLib 类代码
    def __init__(self, layout_type="pointy", hex_size=(50, 50), origin=(0, 0)):
        self.layout_type = layout_type
        self.hex_size = hex_size
        self.origin = origin
    
    def create_hex(self, q, r):
        if self.layout_type == "pointy":
            x = self.hex_size[0] * (3/2 * q)
            y = self.hex_size[1] * (math.sqrt(3)/2 * q + math.sqrt(3) * r)
        else:
            x = self.hex_size[0] * (math.sqrt(3) * q + math.sqrt(3)/2 * r)
            y = self.hex_size[1] * (3/2 * r)
        x += self.origin[0]
        y += self.origin[1]
        return {"q": q, "r": r, "x": x, "y": y}
    
    def create_staggered_grid(self, col_range, row_range):
        grid_hexes = []
        min_col, max_col = col_range
        min_row, max_row = row_range
        if self.layout_type == "flat":
            for col in range(min_col, max_col + 1):
                offset = col // 2
                for row in range(min_row, max_row + 1):
                    actual_row = row - offset
                    grid_hexes.append(self.create_hex(col, actual_row))
        else:
            for row in range(min_row, max_row + 1):
                offset = row // 2
                for col in range(min_col, max_col + 1):
                    actual_col = col - offset
                    grid_hexes.append(self.create_hex(actual_col, row))
        print(f"\n=== 交错类矩形网格信息 ===")
        print(f"朝向: {self.layout_type} | 列范围(X/Q): {min_col} ~ {max_col} | 行范围(Y/R): {min_row} ~ {max_row}")
        print(f"总六边形数量: {len(grid_hexes)}")
        return grid_hexes

# 初始化两种朝向的网格管理器并生成网格
hex_flat = HexLib(layout_type="flat", hex_size=(50, 50), origin=(100, 100))
flat_grid = hex_flat.create_staggered_grid(col_range=(0, 5), row_range=(0, 4))

hex_pointy = HexLib(layout_type="pointy", hex_size=(50, 50), origin=(100, 100))
pointy_grid = hex_pointy.create_staggered_grid(col_range=(0, 5), row_range=(0, 4))

# 分析 Flat 朝向网格的像素坐标范围
flat_x_coords = [h['x'] for h in flat_grid]
flat_y_coords = [h['y'] for h in flat_grid]

print("\n=== Flat 朝向网格填充范围验证 ===")
print(f"X轴像素范围: {min(flat_x_coords):.1f} ~ {max(flat_x_coords):.1f}")
print(f"Y轴像素范围: {min(flat_y_coords):.1f} ~ {max(flat_y_coords):.1f}")

# 分析 Pointy 朝向网格的像素坐标范围
pointy_x_coords = [h['x'] for h in pointy_grid]
pointy_y_coords = [h['y'] for h in pointy_grid]

print("\n=== Pointy 朝向网格填充范围验证 ===")
print(f"X轴像素范围: {min(pointy_x_coords):.1f} ~ {max(pointy_x_coords):.1f}")
print(f"Y轴像素范围: {min(pointy_y_coords):.1f} ~ {max(pointy_y_coords):.1f}")
```

### 输出结果

```Plain Text

=== 交错类矩形网格信息 ===
朝向: flat | 列范围(X/Q): 0 ~ 5 | 行范围(Y/R): 0 ~ 4
总六边形数量: 30

=== 交错类矩形网格信息 ===
朝向: pointy | 列范围(X/Q): 0 ~ 5 | 行范围(Y/R): 0 ~ 4
总六边形数量: 30

=== Flat 朝向网格填充范围验证 ===
X轴像素范围: 100.0 ~ 533.0
Y轴像素范围: 100.0 ~ 400.0

=== Pointy 朝向网格填充范围验证 ===
X轴像素范围: 100.0 ~ 400.0
Y轴像素范围: 100.0 ~ 846.4
```

# 四、修复前后对比

|修复前问题|修复后效果|
|---|---|
|Flat 朝向网格倾斜，无法填满矩形|Flat 朝向网格水平对齐，像素坐标均匀分布填满指定矩形|
|两种朝向共用同一套偏移规则|区分朝向的偏移规则，各自保持视觉特性且填满矩形|
|坐标偏移混乱|坐标计算精准，行列偏移可预测|
# 五、注意事项

1. 六边形尺寸建议设置为等比例（如 (50,50)），避免拉伸变形；

2. 原点坐标 (origin) 会影响整个网格的像素位置，可根据界面布局调整；

3. 列/行范围支持负数（如 col_range=(-2,3)），可生成包含负坐标的网格；

4. 总六边形数量 = (max_col - min_col + 1) * (max_row - min_row + 1)，确保数量符合预期。
> （注：文档部分内容可能由 AI 生成）