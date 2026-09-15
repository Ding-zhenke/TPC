# CST Studio Suite 2026 VBA 官方对象参考

> 来源：`C:\Program Files\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D\` 官方 HTML 文档（150+ 页），逐对象提取属性签名、类型、枚举值、官方示例。
>
> 与 `vba-reference.md` 的关系：本文档提供**完整的官方 API 签名**，`vba-reference.md` 提供**生产验证的组合模板和使用模式**。

## 目录

1. [入口与全局对象](#1-入口与全局对象)
2. [参数管理（核心）](#2-参数管理核心)
3. [Units — 单位系统](#3-units--单位系统)
4. [基本实体建模](#4-基本实体建模)
5. [曲线建模](#5-曲线建模)
6. [2D→3D 造型](#6-2d3d-造型)
7. [Solid 实体操作与布尔运算](#7-solid-实体操作与布尔运算)
8. [Transform 变换](#8-transform-变换)
9. [Pick 选取](#9-pick-选取)
10. [WCS 工作坐标系](#10-wcs-工作坐标系)
11. [Background & Boundary](#11-background--boundary)
12. [Solver — 时域求解器（HF）](#12-solver--时域求解器hf)
13. [FDSolver — 频域求解器](#13-fdsolver--频域求解器)
14. [Eigenmode / IE / Asymptotic 求解器](#14-eigenmode--ie--asymptotic-求解器)
15. [Mesh — 网格](#15-mesh--网格)
16. [Port — 端口](#16-port--端口)
17. [Monitor — 监视器](#17-monitor--监视器)
18. [导入导出格式](#18-导入导出格式)
19. [FarfieldPlot & FarfieldCalculator](#19-farfieldplot--farfieldcalculator)
20. [ResultTree & 结果读取](#20-resulttree--结果读取)
21. [Result1D / Result1DComplex / Result0D](#21-result1d--result1dcomplex--result0d)
22. [Plot1D — 1D 绘图](#22-plot1d--1d-绘图)
23. [附录：关键枚举速查](#23-附录关键枚举速查)

---

## 1. 入口与全局对象

### Application 对象

CST 作为 OLE Automation Server 注册，ProgID = `"CSTStudio.Application"`。

**内置 VBA 解释器**（在 CST 中 `Home → Macros → Open VBA Macro Editor`）内所有全局方法可直接调用。

**外部应用启动：**
```vba
Dim app As Object
Set app = CreateObject("CSTStudio.Application")
Dim mws As Object
Set mws = app.NewMWS()           ' 新建 MWS 工程
' 或
Set mws = app.OpenFile("C:\project.cst")  ' 打开已有工程
```

### Project 对象 — 全局方法总表

**文件：** `common_vbaapp\common_vbaappapplication_object.htm`

#### 历史与 UI 控制

| 方法签名 | 说明 |
|----------|------|
| `AddToHistory(string caption, string contents) → bool` | 写入历史树（会标记模型变更） |
| `AddToHistoryNoModelChange(string caption, string contents) → bool` | 写入历史树（不删结果） |
| `BeginHide()` | 挂起 UI 更新（批量操作性能提升 10-100x） |
| `EndHide()` | 恢复 UI 更新 |
| `ScreenUpdating(bool switch)` | 主视图刷新开关 |
| `SetLock(bool switch)` | 禁止用户交互 |
| `Rebuild() → bool` | 强制重建几何模型 |
| `RebuildOnParametricChange(bool bfullRebuild, bool bShowErrorMsgBox) → bool` | 参数变更后重建 |

#### 文件操作

| 方法签名 | 说明 |
|----------|------|
| `Save()` | 保存 |
| `SaveAs(filename filename, bool include_results)` | 另存为 |
| `Backup(filename filename)` | 创建副本 |
| `StoreInArchive(filename, bool keepAllResults, bool keep1DResults, bool keepFarfieldData, bool deleteProjFolder)` | 归档为 ZIP |
| `ImportSubProject(string filename, string do_wcs_alignment) → string` | 导入子项目 |

#### 求解器控制

| 方法签名 | 说明 |
|----------|------|
| `RunSolver() → bool` | 启动当前求解器 |
| `ChangeSolverType(string type)` | 切换求解器类型 |
| `GetSolverType() → string` | 返回当前求解器类型 |
| `DeleteResults()` | 删除所有结果 |
| `AskForDeleteResults() → bool` | 弹确认框删除结果 |

#### 查询

| 方法签名 | 返回 | 说明 |
|----------|------|------|
| `GetApplicationName()` | `string` | 应用名称 |
| `GetApplicationVersion()` | `string` | 版本号 |
| `GetInstallPath()` | `string` | 安装路径 |
| `GetProjectPathName(string type)` | `string` | type ∈ `{"Root","Project","Model3D","Result","Temp","Library",...}` |
| `GetOwnProject()` | `object` | 当前 Project 的 COM 接口 |
| `GetLicenseHostId()` | `string` | 许可证 HostID |
| `IsBuildingModel()` | `bool` | 是否正在构建模型 |
| `UseDistributedComputingForParameters(bool flag)` | — | 参数扫描使用 DC |
| `MaxNumberOfDistributedComputingParameters(int num)` | — | DC 参数上限 |

#### 结果树导航

| 方法签名 | 说明 |
|----------|------|
| `SelectTreeItem(string itemname) → bool` | 选中树节点（路径分隔符 `\`） |
| `SelectAdditionalTreeItem(string itemname) → bool` | 追加选中 |
| `GetNumberOfSelectedTreeItems() → long` | 已选树节点数 |
| `GetSelectedTreeItem() → string` | 当前选中节点路径 |
| `GetNextSelectedTreeItem() → string` | 下一个选中节点 |

---

## 2. 参数管理（核心）

所有参数方法直接可调用，无需前缀。

### 写入参数

| 方法签名 | 说明 |
|----------|------|
| `StoreParameter(string name, string value)` | 创建/修改字符串参数 |
| `StoreDoubleParameter(string name, double value)` | 创建/修改双精度参数 |
| `StoreParameters(string_array names, string_array values)` | 批量创建/修改 |
| `StoreParameterWithDescription(string name, string value, string description)` | 带描述的字符串参数 |
| `MakeSureParameterExists(string name, string value)` | 不存在则创建，已存在保持不变 |
| `SetParameterDescription(string name, string description)` | 设置参数描述 |

### 读取参数

| 方法签名 | 返回 | 说明 |
|----------|------|------|
| `RestoreParameter(string name)` | `string` | 读取字符串参数值 |
| `RestoreDoubleParameter(string name)` | `double` | 读取双精度参数值 |
| `RestoreParameterExpression(string name)` | `string` | 读取参数的表达式 |
| `GetParameterDescription(string name)` | `string` | 读取参数描述 |

### 查询参数

| 方法签名 | 返回 | 说明 |
|----------|------|------|
| `DoesParameterExist(string name)` | `bool` | 是否存在 |
| `GetNumberOfParameters()` | `long` | 参数总数 |
| `GetParameterName(long index)` | `string` | 索引从 0 开始 |
| `GetParameterNValue(long index)` | `double` | 按索引获取数值 |
| `GetParameterSValue(long index)` | `string` | 按索引获取表达式 |

### 参数管理

| 方法签名 | 说明 |
|----------|------|
| `RenameParameter(string oldName, string newName)` | 重命名 |
| `DeleteParameter(string name)` | 删除 |

### 离线参数读取（无需 DE）

| 方法签名 | 返回 | 说明 |
|----------|------|------|
| `GetParameterCombination(string resultID, variant names, variant values)` | `bool` | 获取指定 RunID 的参数组合 |
| `GetProjectParameters(string filename, variant names, variant expressions, variant values, variant descriptions)` | `long` | 从磁盘直接读取关闭项目的参数 |

### 参数 VBA 示例

```vba
' 单参数写入
StoreDoubleParameter "width", 12.5

' 批量参数（使用 VBA 数组）
Dim names(1 To 3) As String, values(1 To 3) As String
names(1) = "width"
values(1) = "10.0"
names(2) = "length"
values(2) = "25.0"
names(3) = "height"
values(3) = "5.0"
StoreParameters names, values

' 读取参数
Dim w As Double
w = RestoreDoubleParameter("width")

' 参数检查
If Not DoesParameterExist("width") Then
    StoreDoubleParameter "width", 10.0
End If
```

---

## 3. Units — 单位系统

**文件：** `common_vbaunitso\common_vbaunitso_units_object.htm`

### 方法

| 方法签名 | 说明 |
|----------|------|
| `SetUnit(enum dimension, enum unit)` | 设置单位 |
| `GetUnit(enum dimension) → enum` | 读取单位 |
| `GetGeometryUnitToSI() → double` | 几何单位 → SI 换算因子 |
| `GetGeometrySIToUnit() → double` | SI → 几何单位因子 |
| `GetTimeUnitToSI() → double` | 时间单位 → SI |
| `GetFrequencyUnitToSI() → double` | 频率单位 → SI |

### 完整单位枚举

| dimension | 可用值 |
|-----------|--------|
| `"Length"` | `"nm"`, `"um"`, `"mm"`, `"cm"`, `"m"`, `"mil"`, `"in"`, `"ft"` |
| `"Time"` | `"fs"`, `"ps"`, `"ns"`, `"us"`, `"ms"`, `"s"` |
| `"Frequency"` | `"Hz"`, `"kHz"`, `"MHz"`, `"GHz"`, `"THz"`, `"PHz"` |
| `"Temperature"` | `"degC"`, `"K"`, `"degF"` |
| `"Voltage"` | `"V"`, `"mV"`, `"uV"` |
| `"Resistance"` | `"Ohm"` |
| `"Inductance"` | `"H"`, `"nH"`, `"uH"`, `"mH"` |
| `"Capacitance"` | `"F"`, `"pF"`, `"nF"`, `"mF"` |
| `"Conductance"` | `"S"` |
| `"Current"` | `"A"`, `"mA"`, `"uA"` |

### 示例

```vba
With Units
    .SetUnit "Length", "mm"
    .SetUnit "Frequency", "GHz"
    .SetUnit "Time", "ns"
    .SetUnit "Temperature", "K"
End With
```

---

## 4. 基本实体建模

所有实体遵循统一模式：`With Obj .Reset .Property1 "v" ... .Create End With`

### 4.1 Brick（六面体）

**文件：** `common_vbabasicsolids\common_vbabasicsolids_brick_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Name` | string | 实体名称（唯一） |
| `Component` | string | 所属组件 |
| `Material` | string | 材质名 |
| `Xrange` | `string, string` | X 方向范围 `"min","max"` |
| `Yrange` | `string, string` | Y 方向范围 |
| `Zrange` | `string, string` | Z 方向范围 |
| `Xwidth` | double | X 方向宽度（替代 Xrange） |
| `Ywidth` | double | Y 方向宽度 |
| `Zwidth` | double | Z 方向宽度 |
| `Useindividualcolor` | bool | 启用单独颜色 |

```vba
With Brick
    .Reset
    .Name "brick1"
    .Component "component1"
    .Material "PEC"
    .Xrange "-10", "10"
    .Yrange "-5", "5"
    .Zrange "-2", "2"
    .Create
End With
```

### 4.2 Cylinder（圆柱）

**文件：** `common_vbabasicsolids\common_vbabasicsolids_cylinder_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Name` / `Component` / `Material` | — | 同 Brick |
| `Xradius` / `Yradius` | double | X/Y 方向半径 |
| `Xcenter` / `Ycenter` / `Zcenter` | double | 中心坐标 |
| `Xrange` / `Yrange` / `Zrange` | `string, string` | 范围 |
| `Axis` | string | 轴线 `"x"` / `"y"` / `"z"` |
| `Segments` | int | 分段数（`0` = 自动） |
| `Useindividualcolor` | bool | 单独颜色 |

```vba
With Cylinder
    .Reset
    .Name "cylinder1"
    .Component "component1"
    .Material "PEC"
    .Xradius "1" : .Yradius "1"
    .Zrange "-5", "5"
    .Axis "z"
    .Create
End With
```

### 4.3 Cone（锥体）

**文件：** `common_vbabasicsolids\common_vbabasicsolids_cone_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Name` / `Component` / `Material` | — | 同 Brick |
| `Xradius` / `Yradius` | double | 底部 X/Y 半径 |
| `XradiusTop` / `YradiusTop` | double | 顶部 X/Y 半径 |
| `Xcenter` / `Ycenter` / `Zcenter` | double | 中心 |
| `Axis` | string | `"x"` / `"y"` / `"z"` |
| `Segments` | int | 分段数 |

```vba
With Cone
    .Reset
    .Name "cone1"
    .Component "component1"
    .Material "PEC"
    .Xradius "2" : .Yradius "2"
    .XradiusTop "0" : .YradiusTop "0"
    .Zrange "0", "4"
    .Axis "z"
    .Create
End With
```

### 4.4 Sphere（球体）

**文件：** `common_vbabasicsolids\common_vbabasicsolids_sphere_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Xradius` / `Yradius` / `Zradius` | double | 各向半径 |
| `Xcenter` / `Ycenter` / `Zcenter` | double | 中心 |
| `Segments` | int | 分段数 |

```vba
With Sphere
    .Reset
    .Name "sphere1"
    .Component "component1"
    .Material "PEC"
    .Xradius "3" : .Yradius "3" : .Zradius "3"
    .Xcenter "0" : .Ycenter "0" : .Zcenter "0"
    .Create
End With
```

### 4.5 Torus（环）

**文件：** `common_vbabasicsolids\common_vbabasicsolids_torus_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Outerradius` | double | 环形中心到环管中心的距离 |
| `Innerradius` | double | 环管半径 |
| `Xcenter` / `Ycenter` / `Zcenter` | double | 中心 |
| `Axis` | string | `"x"` / `"y"` / `"z"` |
| `Segments` | int | 分段数 |

```vba
With Torus
    .Reset
    .Name "torus1"
    .Component "component1"
    .Material "PEC"
    .Outerradius "5"
    .Innerradius "1"
    .Axis "z"
    .Create
End With
```

### 4.6 ECylinder（椭圆锥台/椭圆圆柱）

**文件：** `common_vbabasicsolids\common_vbabasicsolids_ecylinder_object.htm`

Cylinder 的椭圆变体。`Xradius`/`Yradius` 可不同值，且顶部和底部分别设置。

| 属性 | 类型 | 说明 |
|------|------|------|
| `Xradius` / `Yradius` | double | 底部 X/Y 半轴 |
| `XradiusTop` / `YradiusTop` | double | 顶部 X/Y 半轴 |
| 其余 | — | 同 Cylinder |

```vba
With ECylinder
    .Reset
    .Name "ecylinder1"
    .Component "component1"
    .Material "PEC"
    .Xradius "1" : .Yradius "1"
    .XradiusTop "2" : .YradiusTop "3"
    .Zrange "0", "5"
    .Axis "z"
    .Create
End With
```

### 4.7 Wire（导线）

**文件：** `common_vbabasicsolids\common_vbabasicsolids_wire_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Xcoordinate` / `Ycoordinate` / `Zcoordinate` | `string, string` | 逗号分隔的坐标序列 |
| `Segments` | int | 分段数 |
| `Type` | string | `"Wire"` / `"Polygon"` |
| `ArcFactor` | double | 弧因子（>0 时平滑弧线） |
| `Closed` | bool | 是否封闭 |
| `Radius` | double | 导线半径（2026 版） |

### 4.8 AnalyticalFace（解析曲面）

**文件：** `common_vbabasicsolids\common_vbabasicsolids_analytical_face_object.htm`

直接通过数学表达式定义曲面。

| 属性 | 类型 | 说明 |
|------|------|------|
| `Zposition` | double | Z 位置 |
| `Value` | string | 表达式（如 `"(x^2 + y^2) < 6"`） |

---

## 5. 曲线建模

### 5.1 Arc

**文件：** `common_vbacurves\common_vbacurves_arc_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Type` | string | `"Angle"` / `"View"` |
| `Radius` | double | 弧半径 |
| `ArcAngle` | double | 弧张角（度） |
| `StartAngle` | double | 起始角（度） |
| `Segments` | int | 分段数 |
| `Xcenter` / `Ycenter` / `Zcenter` | double | 中心 |

### 5.2 Circle

**文件：** `common_vbacurves\common_vbacurves_circle_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Type` | string | `"Center"` / `"Edge"` / `"View"` |
| `Radius` | double | 半径 |
| `Xcenter` / `Ycenter` / `Zcenter` | double | 中心 |
| `Segments` | int | 分段数 |

### 5.3 Ellipse

**文件：** `common_vbacurves\common_vbacurves_ellipse_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Type` | string | `"Center"` / `"Edge"` / `"View"` |
| `Xradius` / `Yradius` | double | X/Y 半径 |
| `Xcenter` / `Ycenter` / `Zcenter` | double | 中心 |
| `Segments` | int | 分段数 |

### 5.4 Rectangle（矩形曲线）

**文件：** `common_vbacurves\common_vbacurves_rectangle_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Type` | string | `"Center"` / `"Corner"` / `"View"` |
| `Xrange` / `Yrange` / `Zrange` | `string, string` | 范围 |
| `Xwidth` / `Ywidth` | double | 宽度（替代写法） |
| `Segments` | int | 分段数 |

### 5.5 Line

**文件：** `common_vbacurves\common_vbacurves_line_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Type` | string | `"Point"` / `"View"` |
| `Xpoint1` / `Ypoint1` / `Zpoint1` | double | 起点 |
| `Xpoint2` / `Ypoint2` / `Zpoint2` | double | 终点 |
| `Xrange` / `Yrange` / `Zrange` | `string, string` | 范围 |

### 5.6 Polygon（多边形曲线）

**文件：** `common_vbacurves\common_vbacurves_polygon_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Type` | string | `"View"` |
| `Segments` | int | 线段数 |
| `Closed` | bool | 是否闭合 |

### 5.7 Spline（样条曲线）

**文件：** `common_vbacurves\common_vbacurves_spline_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Type` | string | `"Interpolate"` / `"View"` |
| `Xpoint` / `Ypoint` / `Zpoint` | `string, string` | 逗号分隔的坐标序列 |
| `SplineType` | string | `"Bezier"` / `"B-Spline"` / `"Interpolated"` |
| `Closed` | bool | 是否闭合 |

### 5.8 AnalyticalCurve（解析曲线）

**文件：** `common_vbacurves\common_vbacurves_analytical_curve_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `CurveExpression` | `string, string` | 曲线表达式对 |
| `ParameterName` | string | 参数名（默认 `"t"`） |
| `Minvalue` / `Maxvalue` | double | 参数范围 |

```vba
With AnalyticalCurve
    .Reset
    .Name "helix"
    .CurveExpression "cos(t)", "sin(t)"
    .ParameterName "t"
    .Minvalue "0" : .Maxvalue "2*pi"
    .Segments "32"
    .Create
End With
```

### 5.9 Polygon3D（三维多边形曲线）

**文件：** `common_vbacurves\common_vbacurves_polygon3d_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Point` | `string, string` | 点定义 `"x:y:z"` 格式 |
| `Closed` | bool | 是否闭合 |

```vba
With Polygon3D
    .Reset
    .Name "poly3d1"
    .Point "0:0:0", "1:2:0", "2:0:0", "1:1:0"
    .Closed "true"
    .Create
End With
```

### 所有曲线共有的可选属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `Curve` | bool | 曲线面标识（`"curve_name"`） |
| `CurvePlaneNormal` | string | 曲线法线 `"x"` / `"y"` / `"z"` |
| `CurvePlanePosition` | string | 曲线所在平面位置 |

---

## 6. 2D→3D 造型

### 6.1 Extrude（拉伸）

**文件：** `common_vbaextrude\common_vbaextrudeextrude_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Name` / `Component` / `Material` | — | 标准 |
| `Mode` | string | `"Picks"` / `"Face"` |
| `Height` | double | 拉伸高度 |
| `Twist` | double | 扭转角度（度） |
| `Taper` | double | 锥度角度（度） |
| `Drafttype` | string | `"Round"` / `"Sharp"` / `"Apex"` |

### 6.2 Loft（放样）

**文件：** `common_vbaloft\common_vbaloftloft_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Mode` | string | `"Picks"` / `"Face"` / `"SolidInSpace"` |
| `SmoothTransition` | bool | 平滑过渡 |
| `TaperStyle` | string | `"Apex"` / `"Cone"` |
| `Scale` | bool | 是否缩放 |

### 6.3 Rotate（旋转）

**文件：** `common_vbarotateo\common_vbarotateo_rotate_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Mode` | string | `"Picks"` / `"Face"` |
| `Angle` | double | 旋转角度（度） |

---

## 7. Solid 实体操作与布尔运算

**文件：** `common_vbasolido\common_vbasolido_solid_object.htm`

### 7.1 布尔运算

| 方法签名 | 说明 |
|----------|------|
| `Solid.Add(solidname s1, solidname s2)` | 并集，结果在 s1，s2 被删除 |
| `Solid.Subtract(solidname s1, solidname s2)` | s1 − s2 |
| `Solid.Intersect(solidname s1, solidname s2)` | 交集 |
| `Solid.Insert(solidname s1, solidname s2)` | s1 − s2，保留 s2 |

### 7.2 实体管理

| 方法签名 | 说明 |
|----------|------|
| `Solid.Delete(solidname s)` | 删除 |
| `Solid.Rename(solidname old, name new)` | 重命名 |
| `Solid.ChangeComponent(solidname s, name comp)` | 改组件 |
| `Solid.ChangeMaterial(solidname s, name mat)` | 改材质 |
| `Solid.SetUseIndividualColor(solidname s, bool flag)` | 启用单独颜色 |
| `Solid.ChangeIndividualColor(solidname s, int r, int g, int b)` | 改 RGB 颜色 |

### 7.3 网格属性

| 方法签名 | 说明 |
|----------|------|
| `Solid.SetMeshStepWidth(solidname s, double dx, double dy, double dz)` | 最大网格步长 |
| `Solid.SetMeshExtendwidth(solidname s, double dx, double dy, double dz)` | 网格扩展 |
| `Solid.SetAutomeshFixpoints(solidname s, bool flag)` | 影响自动网格 |
| `Solid.SetMaterialBasedRefinement(solidname s, bool flag)` | 材料基础细化 |
| `Solid.SetMeshProperties(solidname s, enum {"PBA","Staircase"} type, bool defaultType)` | 逼近类型 |
| `Solid.SetUseForSimulation(solidname s, bool flag)` | 包含/排除于仿真 |
| `Solid.SetUseThinSheetMeshForShape(solidname s, bool flag)` | 薄片网格 (TST) |

### 7.4 高级建模

| 方法签名 | 说明 |
|----------|------|
| `Solid.BlendEdge(double rad)` | 倒圆角（需先 Pick 边） |
| `Solid.ChamferEdge(double depth, double angle, bool switch, int faceID)` | 倒角 |
| `Solid.SliceShape(name s, name comp)` | 用当前工作平面切割 |
| `Solid.SplitShape(name s, name comp)` | 拆分不连通部分 |
| `Solid.ThickenSheetAdvanced(solidname s, enum {"Inside","Outside","Centered"} key, double thickness, bool clearpicks)` | 片体增厚 |
| `Solid.ShellAdvanced(solidname s, enum {"Inside","Outside","Centered"} key, double thickness, bool clearpicks)` | 抽壳 |
| `Solid.FillUpSpaceAdvanced(name s, name comp, name mat)` | 填充计算域 |
| `Solid.FastModelUpdate(bool flag)` | True=快速更新 / False=完全重建 |

### 7.5 查询

| 方法签名 | 返回 | 说明 |
|----------|------|------|
| `Solid.DoesExist(name s)` | `bool` | 是否存在 |
| `Solid.GetVolume(solidname s)` | `double` | 体积 |
| `Solid.GetMass(solidname s)` | `double` | 质量 |
| `Solid.GetArea(solidname s)` | `double` | 表面积 |
| `Solid.GetNumberOfShapes()` | `int` | 形状总数 |
| `Solid.GetNameOfShapeFromIndex(int i)` | `name` | 按索引获取名称 |
| `Solid.GetMaterialNameForShape(solidname s)` | `name` | 材质名 |
| `Solid.IsSolidShape(solidname s)` | `bool` | 是否为实体 |
| `Solid.IsPointInsideShape(double x, double y, double z, solidname s)` | `bool` | 点是否在形状内 |
| `Solid.DoTheseGeometricallyIntersect(solidname s1, solidname s2)` | `bool` | 几何交叉检查 |
| `Solid.CheckIntersectionFor(solidname s)` | `bool` | 检查与所有其他形状的交叉 |
| `Solid.GetNextEncounteredIntersection()` | `name` | 顺序获取交叉形状名 |

### 7.6 修复

| 方法签名 | 说明 |
|----------|------|
| `Solid.HealAllShapesAdvanced()` | 修复所有导入形状 |
| `Solid.HealShapeAdvanced(solidname s)` | 修复指定形状 |
| `Solid.HealSelfIntersectingShape(solidname s)` | 修复自相交 |
| `Solid.CleanShape(solidname s)` | 清理形状 |
| `Solid.CheckSolid(solidname s, int level)` | 检查问题（level 20/30/40/50） |

---

## 8. Transform 变换

**文件：** `special_vbatransformo\special_vbatransformo_transform_object.htm`

### 静态方法（直接调用，不经过 With/Reset）

| 方法签名 | 说明 |
|----------|------|
| `Transform.Translate(solidname s, double dx, double dy, double dz)` | 平移 |
| `Transform.Scale(solidname s, double fx, double fy, double fz)` | 缩放 |
| `Transform.Rotate(solidname s, string axis, double angle, double cx, double cy, double cz)` | 旋转，axis ∈ `{"x","y","z"}` |
| `Transform.Mirror(solidname s, string plane, double cx, double cy, double cz)` | 镜像，plane ∈ `{"x","y","z"}` |

### With/Reset 模式（支持更多选项）

| 属性 | 类型 | 说明 |
|------|------|------|
| `Name` | string | 结果名称 |
| `Component` | string | 所属组件 |
| `Material` | string | 材质 |
| `MultipleObjects` | string | `"ObeyConstraints"` / `"IgnoreConstraints"` / `"Individual"` |
| `MultipleObjectsMode` | int | 0=保留, 1=忽略约束, 2=单独创建 |
| `Destination` | string | `"Shape"` / `"Component"` / `"Copy"` |
| `GroupName` | string | 组名 |
| `Repetitions` | int | 重复次数 |
| `CreateShapesOfCopies` | bool | 为副本创建形状 |

---

## 9. Pick 选取

**文件：** `common_vbapicko\common_vbapicko_pick_object.htm`

### 通用选取

| 方法签名 | 说明 |
|----------|------|
| `Pick.ClearAllPicks()` | 清除所有已选 |
| `Pick.PickPointFromCoordinates(double x, double y, double z)` | 按坐标选点 |
| `Pick.PickFaceFromId(string shapeName, int id)` | 按面 ID 选面 |
| `Pick.PickEdgeFromId(string shapeName, int edge_id, int vertex_id)` | 按边 ID 选边 |
| `Pick.PickFaceFromPoint(string shapeName, double x, double y, double z)` | 按坐标附近选面 |
| `Pick.PickEdgeFromPoint(string shapeName, double x, double y, double z)` | 按坐标附近选边 |

### 查询

| 方法签名 | 返回 | 说明 |
|----------|------|------|
| `Pick.GetNumberOfPickedPoints()` | `int` | 已选点数 |
| `Pick.GetNumberOfPickedEdges()` | `int` | 已选边数 |
| `Pick.GetNumberOfPickedFaces()` | `int` | 已选面数 |
| `Pick.GetPickpointCoordinatesCompByIndex(int index, int icomp)` | `double` | icomp: 0=x, 1=y, 2=z |
| `Pick.GetFaceIdFromPoint(string shape, double x, double y, double z)` | `long` | 面 ID |
| `Pick.GetEdgeIdFromPoint(string shape, double x, double y, double z)` | `long` | 边 ID |

### 从曲线选取

| 方法签名 | 说明 |
|----------|------|
| `Pick.PickCurveEndpointFromId(string curve, int id)` | 按 ID 选曲线端点 |
| `Pick.PickCurveMidpointFromId(string curve, int id)` | 按 ID 选曲线中点 |
| `Pick.PickCurveCirclecenterFromId(string curve, int id)` | 按 ID 选圆心 |

---

## 10. WCS 工作坐标系

**文件：** `common_vbawcso\common_vbawcso_wcs_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Mode` | string | `"point"` / `"local"` / `"global"` |
| `OriginX` / `OriginY` / `OriginZ` | double | 原点 |
| `UPX` / `UPY` / `UPZ` | double | U 方向分量 |
| `VPX` / `VPY` / `VPZ` | double | V 方向分量 |
| `WPX` / `WPY` / `WPZ` | double | W 方向分量 |
| `Name` | string | WCS 名称 |
| `Id` | int | WCS ID |

```vba
With WCS
    .Reset
    .Mode "point"
    .OriginX "5" : .OriginY "5" : .OriginZ "5"
    .Name "wcs1"
    .Create
End With
WCS.Activate "wcs1"
WCS.AlignWCSWithGlobalCoordinates
```

---

## 11. Background & Boundary

### 11.1 Background

**文件：** `special_vbasolver\special_vbasolver_background_object.htm`

| 方法签名 | 说明 |
|----------|------|
| `Background.Reset()` | 重置 |
| `Background.Type(enum type)` | 背景材料类型 |
| `Background.Epsilon(double val)` | 介电常数 |
| `Background.Mu(double val)` | 磁导率 |
| `Background.ElConductivity(double val)` | 电导率 |
| `Background.XminSpace(double val)` | X−空间 |
| `Background.XmaxSpace(double val)` | X+ 空间 |
| `Background.YminSpace(double val)` | Y−空间 |
| `Background.YmaxSpace(double val)` | Y+ 空间 |
| `Background.ZminSpace(double val)` | Z−空间 |
| `Background.ZmaxSpace(double val)` | Z+ 空间 |
| `Background.ApplyInAllDirections(bool flag)` | 全方向统一 |
| `Background.ThermalType(enum type)` | 热类型 |
| `Background.ThermalConductivity(double val)` | 导热系数 |

### 11.2 Boundary

**文件：** `special_vbasolver\special_vbasolver_boundary_object.htm`（91 个方法）

| 方法签名 | 说明 |
|----------|------|
| `Boundary.Xmin(enum type)` | X−边界 |
| `Boundary.Xmax(enum type)` | X+ 边界 |
| `Boundary.Ymin(enum type)` | ... |
| `Boundary.Ymax(enum type)` | ... |
| `Boundary.Zmin(enum type)` | ... |
| `Boundary.Zmax(enum type)` | ... |
| `Boundary.Xsymmetry(enum type)` | X 对称 |
| `Boundary.Ysymmetry(enum type)` | Y 对称 |
| `Boundary.Zsymmetry(enum type)` | Z 对称 |
| `Boundary.ApplyInAllDirections(bool switch)` | 全方向统一 |
| `Boundary.XPeriodicShift(double val)` | X 周期偏移 |
| `Boundary.YPeriodicShift(double val)` | Y 周期偏移 |
| `Boundary.ZPeriodicShift(double val)` | Z 周期偏移 |
| `Boundary.SetPeriodicBoundaryAngles(double theta, double phi)` | 周期边界角度 |
| `Boundary.MinimumLinesDistance(double val)` | 最小线距 |
| `Boundary.MinimumDistanceType(enum {"Fraction","Absolute"} type)` | 距离类型 |
| `Boundary.Layer(int numLayers)` | 层数 |
| `Boundary.XminPotential(double val)` | X−电位（静电场） |
| `Boundary.XmaxPotential(double val)` | ... |
| `Boundary.XminThermal(enum type)` | X−热边界 |
| `Boundary.UnitCellDs1(double val)` | 单元 Ds1 |
| `Boundary.UnitCellDs2(double val)` | 单元 Ds2 |
| `Boundary.UnitCellAngle(double val)` | 单元角度 |
| `Boundary.UnitCellOrigin(double x, double y)` | 单元原点 |

**边界类型枚举值：**
```
"expanded open", "open", "open (add space)", "electric", "magnetic",
"periodic", "conducting wall", "tangential magnetic", "tangential electric",
"normal electric", "normal magnetic"
```

**对称类型枚举值：**
```
"none", "electric", "magnetic"
```

---

## 12. Solver — 时域求解器（HF）

**文件：** `special_vbasolver\special_vbasolver_solver_object.htm`（140+ 方法）

### 核心配置

| 方法签名 | 说明 |
|----------|------|
| `Solver.FrequencyRange(double fmin, double fmax)` | 频率范围 |
| `Solver.Method(enum method)` | 方法（通常 `"Hexahedral"`） |
| `Solver.MeshType(enum type)` | 网格类型 |
| `Solver.StimulationPort(enum port)` | 激励端口 `"All"` / 端口号 |
| `Solver.StimulationMode(enum mode)` | 激励模式 `"All"` / 模式号 |
| `Solver.SteadyStateLimit(double dB)` | 稳态限制（如 `-30`） |
| `Solver.AutoNormImpedance(bool flag)` | 自动归一化阻抗 |
| `Solver.NormingImpedance(double imped)` | 归一化阻抗值（如 `50`） |
| `Solver.MeshAdaption(bool flag)` | 网格自适应 |
| `Solver.CalculateZandYMatrices()` | 计算 Z/Y 矩阵 |
| `Solver.CalculateVSWR()` | 计算 VSWR |

### 加速/并行

| 方法签名 | 说明 |
|----------|------|
| `Solver.UseParallelization(bool flag)` | 并行化 |
| `Solver.MaximumNumberOfThreads(int n)` | 最大线程数 |
| `Solver.MaximumNumberOfCPUDevices(int n)` | CPU 设备数 |
| `Solver.RemoteCalculation(bool flag)` | 远程计算 |
| `Solver.UseDistributedComputing(bool flag)` | 分布式计算 |
| `Solver.MPIParallelization(bool flag)` | MPI |
| `Solver.AutomaticMPI(bool flag)` | 自动 MPI |
| `Solver.HardwareAcceleration(bool flag)` | GPU 加速 |
| `Solver.MaximumNumberOfGPUs(int n)` | 最大 GPU 数 |
| `Solver.MaxNumberOfDistributedComputingPorts(int n)` | DC 端口上限 |
| `Solver.DistributeMatrixCalculation(bool flag)` | 分布式矩阵计算 |

### 高级设置

| 方法签名 | 说明 |
|----------|------|
| `Solver.StoreTDResultsInCache(bool flag)` | 缓存 TD 结果 |
| `Solver.FrequencySampleRuleLin(enum {"Samples","Steps","Auto"})` | 线性采样规则 |
| `Solver.FrequencySampleRuleLog(enum {"Samples","Auto"})` | 对数采样 |
| `Solver.FrequencySamples(int n)` | 频点数 |
| `Solver.FrequencyStep(double step)` | 频率步长 |
| `Solver.TimeStepStabilityFactor(double val)` | 时间步稳定因子 |
| `Solver.SParaSymmetry(bool flag)` | S 参数对称 |
| `Solver.CalculateModesOnly(bool flag)` | 仅计算模式 |
| `Solver.FullDeembedding(bool flag)` | 全去嵌 |
| `Solver.SuperimposePLWExcitation(bool flag)` | 叠加平面波 |
| `Solver.UseSensitivityAnalysis(bool flag)` | 灵敏度分析 |
| `Solver.PBAFillLimit(double pct)` | PBA 填充限制 |
| `Solver.UseSplitComponents(bool flag)` | 拆分组件 |
| `Solver.AlwaysExcludePec(bool flag)` | 排除 PEC |
| `Solver.PrepareFarfields(bool flag)` | 准备远场 |
| `Solver.MonitorFarFieldsNearToModel(bool flag)` | 近场远场 |
| `Solver.SetPMLType(enum {"ConvPML","GTPML","SIBC"} key)` | PML 类型 |
| `Solver.SuppressTimeSignalStorage(enum key)` | 抑制时域信号存储 |
| `Solver.UseArfilter(bool flag)` | AR 滤波器 |
| `Solver.ArMaxEnergyDeviation(double limit)` | AR 最大能量偏差 |
| `Solver.AdaptivePortMeshing(bool flag)` | 自适应端口网格 |
| `Solver.AccuracyAdaptivePortMeshing(int pct)` | 自适应网格精度 |
| `Solver.PassesAdaptivePortMeshing(int n)` | 自适应网格轮次 |
| `Solver.UseTSTAtPort(bool flag)` | 端口 TST |
| `Solver.SimplifiedPBAMethod(bool flag)` | 简化 PBA |
| `Solver.SetHFTDDispUpdateScheme(enum {"Standard","Generalized","Automatic"} key)` | 色散更新方案 |

### 激励管理

| 方法签名 | 说明 |
|----------|------|
| `Solver.ResetExcitationList()` | 重置激励列表 |
| `Solver.ActivateExcitation(enum key, int name, int mode, bool flag)` | 激活激励 |
| `Solver.SetExcitation(enum key, int name, int mode, double accuracy, double fmin, double fmax, bool flag)` | 设置激励 |
| `Solver.AddToExcitationList(enum key, int name, int mode)` | 添加到激励列表 |

### 停止准则

| 方法签名 | 说明 |
|----------|------|
| `Solver.AddStopCriterion(name group, double threshold, int checks, bool active)` | 添加停止准则 |
| `Solver.AddStopCriterionWithTargetFrequency(name, double, int, bool, string ranges)` | 带目标频率的停止准则 |

### 仿真控制

| 方法签名 | 返回 | 说明 |
|----------|------|------|
| `Solver.Start()` | `int` | 启动求解（0=成功） |
| `Solver.GetNumberOfPorts()` | `int` | 端口数 |
| `Solver.GetFmin()` | `double` | Fmin |
| `Solver.GetFmax()` | `double` | Fmax |
| `Solver.GetNFsamples()` | `int` | 频点数 |

---

## 13. FDSolver — 频域求解器

**文件：** `special_vbasolver\special_vbasolver_fdsolver_object.htm`（96 个方法）

### 核心配置

| 方法签名 | 说明 |
|----------|------|
| `FDSolver.Reset()` | 重置默认值 |
| `FDSolver.Start() → int` | 启动 |
| `FDSolver.SetMethod(enum {"Hexahedral","Tetrahedral","Surface"} mesh, enum sweep)` | 求解方法 |
| `FDSolver.Type(enum {"Auto","Iterative","Direct"} key)` | 求解器类型 |
| `FDSolver.FrequencySamples(int n)` | 频点数 |
| `FDSolver.AddSampleInterval(double min, double max, int samples, enum key, bool adaptation)` | 添加采样区间 |
| `FDSolver.MaxIterations(int n)` | 最大迭代数 |
| `FDSolver.ModesOnly(bool flag)` | 仅计算模式 |

### 精度与加速

| 方法签名 | 说明 |
|----------|------|
| `FDSolver.AccuracyTet(double val)` | 四面体精度 |
| `FDSolver.AccuracySrf(double val)` | 表面精度 |
| `FDSolver.AccuracyHex(double val)` | 六面体精度 |
| `FDSolver.AccuracyROM(double val)` | ROM 精度 |
| `FDSolver.AcceleratedRestart(bool flag)` | 加速重启 |
| `FDSolver.UseParallelization(bool flag)` | 并行化 |
| `FDSolver.MaxCPUs(int n)` | 最大 CPU 数 |
| `FDSolver.OrderTet(enum order)` | 四面体阶数 |
| `FDSolver.OrderSrf(enum order)` | 表面阶数 |
| `FDSolver.UseDoublePrecision(bool flag)` | 双精度 |

### 高级设置

| 方法签名 | 说明 |
|----------|------|
| `FDSolver.SetOpenBCTypeHex(enum {"Default","PML","FreespaceSIBC"} type)` | 六面体开放边界 |
| `FDSolver.SetOpenBCTypeTet(enum {"Default","PML","SIBC"} type)` | 四面体开放边界 |
| `FDSolver.MeshAdaptionHex(bool flag)` | 六面体网格自适应 |
| `FDSolver.MeshAdaptionTet(bool flag)` | 四面体网格自适应 |
| `FDSolver.StoreAllResults(bool flag)` | 存储所有结果 |
| `FDSolver.StoreResultsInCache(bool flag)` | 缓存结果 |
| `FDSolver.UseSensitivityAnalysis(bool flag)` | 灵敏度分析 |
| `FDSolver.UseDistributedComputing(bool flag)` | 分布式计算 |
| `FDSolver.ExtrudeOpenBC(bool flag)` | 拉伸开放边界 |
| `FDSolver.SetWrite3DFieldsForFarfieldCalc(bool flag)` | 远场 3D 场写入 |

---

## 14. Eigenmode / IE / Asymptotic 求解器

### 14.1 EigenmodeSolver（本征模求解器）

**文件：** `special_vbasolver\special_vbasolver_eigenmodesolver_object.htm`（42 个方法）

| 方法签名 | 说明 |
|----------|------|
| `EigenmodeSolver.Reset()` / `.Start() → int` | 重置/启动 |
| `EigenmodeSolver.SetNumberOfModes(int n)` | 模式数 |
| `EigenmodeSolver.SetModesInFrequencyRange(bool flag)` | 按频率范围搜模 |
| `EigenmodeSolver.SetMethodType(enum {"AKS","JDM","JDM (low memory)","Automatic","Classical (Lossless)","General (Lossy)"} key, enum {"Hex","Tet"} mesh)` | 方法 |
| `EigenmodeSolver.SetMeshType(enum {"Hex","Tet"} key)` | 网格类型 |
| `EigenmodeSolver.SetFrequencyTarget(bool flag, double freq)` | 目标频率 |
| `EigenmodeSolver.SetAccuracy(double acc)` | 精度 |
| `EigenmodeSolver.SetMaxNumberOfThreads(int n)` | 线程数 |
| `EigenmodeSolver.GetNumberOfModesCalculated() → int` | 计算得到的模式数 |
| `EigenmodeSolver.GetModeFrequencyInHz(int n) → double` | 第 n 模频率 |
| `EigenmodeSolver.GetModeQFactor(int n) → double` | 第 n 模 Q 值 |
| `EigenmodeSolver.GetModeExternalQFactor(int n) → double` | 第 n 模外部 Q 值 |

### 14.2 IESolver（积分方程求解器）

**文件：** `special_vbasolver\special_vbasolver_iesolver_object.htm`（23 个方法）

| 方法签名 | 说明 |
|----------|------|
| `IESolver.SetAccuracySetting(enum {"Custom","Low","Medium","High"} key)` | 精度 |
| `IESolver.UseFastFrequencySweep(bool flag)` | 快速扫频 |
| `IESolver.UseIEGroundPlane(bool flag)` | 地平面 |
| `IESolver.SetRealGroundMaterialName(string name)` | 真实地面材质 |
| `IESolver.CalcFarFieldInRealGround(bool flag)` | 真实地面远场 |
| `IESolver.PreconditionerType(enum {"Auto","Type 1","Type 2","Type 3"} key)` | 预处理器 |
| `IESolver.LowFrequencyStabilization(bool flag)` | 低频稳定 |
| `IESolver.Multilayer(bool flag)` | 多层 |
| `IESolver.DeembedExternalPorts(bool flag)` | 去嵌外部端口 |
| `IESolver.ModeTrackingCMA(bool flag)` | CMA 模式追踪 |
| `IESolver.NumberOfModesCMA(int n)` | CMA 模式数 |

### 14.3 AsymptoticSolver（渐进求解器 / SBR）

**文件：** `special_vbasolver\special_vbasolver_asymptoticsolver_object.htm`（77 个方法）

| 方法签名 | 说明 |
|----------|------|
| `AsymptoticSolver.SetSolverType(enum {"SBR","SBR_RAYTUBES"} type)` | 求解器类型 |
| `AsymptoticSolver.SetSolverMode(enum {"MONOSTATIC_SCATTERING","BISTATIC_SCATTERING","FIELD_SOURCES","RANGE_PROFILES"} type)` | 模式 |
| `AsymptoticSolver.SetAccuracyLevel(enum {"LOW","MEDIUM","HIGH","CUSTOM"} type)` | 精度 |
| `AsymptoticSolver.AddHorizontalPolarization(double angle)` | 水平极化角 |
| `AsymptoticSolver.AddVerticalPolarization(double angle)` | 垂直极化角 |
| `AsymptoticSolver.AddFrequencySweep(double fmin, double fmax, double fstep)` | 扫频 |
| `AsymptoticSolver.AddExcitationAngleSweep(enum type, double tmin, double tmax, double tstep, double pmin, double pmax, double pstep)` | 激励角扫描 |
| `AsymptoticSolver.SetSolverMaximumNumberOfReflections(int n)` | 最大反射次数 |
| `AsymptoticSolver.SetSolverRangeProfilesWindowFunction(enum {"RECTANGULAR","HANNING","HAMMING","BLACKMAN"} type)` | 窗函数 |
| `AsymptoticSolver.Set("CalculateMonitors", bool flag)` | 通用 Set 调用 |
| `AsymptoticSolver.Set("MeshMaxWedgeLengthPerLambda", double val)` | 楔形网格 |
| `AsymptoticSolver.Start() → int` | 启动 |

---

## 15. Mesh — 网格

### 15.1 Mesh 对象

**文件：** `special_vbamesh\special_vbamesho.htm`（109 个方法）

#### 全局设置

| 方法签名 | 说明 | 默认值 |
|----------|------|--------|
| `Mesh.MeshType(enum {"HexahedralFIT","HexahedralTLM","Tetrahedral","Surface","SurfaceML","Planar"} type)` | 网格类型 | `"HexahedralFIT"` |
| `Mesh.LinesPerWavelength(int val)` | 每波长线数 | `10` |
| `Mesh.MinimumLineNumber(int val)` | 最小线数 | — |
| `Mesh.MinimumStepNumber(int val)` | 最小步数 | `10` |
| `Mesh.RatioLimit(double val)` | 比例限制 | `10` |
| `Mesh.UseRatioLimit(bool flag)` | 启用比例限制 | `True` |
| `Mesh.SmallestMeshStep(double val)` | 最小网格步长 | `0.0` |
| `Mesh.Automesh(bool flag)` | 自动网格 | `True` |
| `Mesh.EquilibrateMesh(bool flag)` | 平衡网格 | `False` |
| `Mesh.EquilibrateMeshRatio(double val)` | 平衡比 | `1.19` |
| `Mesh.UseCellAspectRatio(bool flag)` | 单元纵横比 | `False` |
| `Mesh.CellAspectRatio(double val)` | 纵横比值 | `50.0` |
| `Mesh.UsePecEdgeModel(bool flag)` | PEC 边模型 | `True` |
| `Mesh.PointAccEnhancement(double pct)` | 点精度增强 | `0` |
| `Mesh.FastPBAAccuracy(int val)` | 快速 PBA 精度 | `3` |
| `Mesh.FastPBAGapDetection(bool flag)` | PBA 间隙检测 | — |
| `Mesh.FPBAFGapTolerance(double val)` | 间隙容差 | — |
| `Mesh.AreaFillLimit(double val)` | 填充限制 | — |
| `Mesh.ConvertGeometryDataAfterMeshing(bool flag)` | 网格后转换 | `True` |
| `Mesh.ConsiderSpaceForLowerMeshLimit(bool flag)` | 空间下限 | — |
| `Mesh.RatioLimitGovernsLocalRefinement(bool flag)` | 比例限制控制局部细化 | — |
| `Mesh.SmallFeatureSize(double val)` | 小特征尺寸 | `0.0` |

#### 自动固定点

| 方法签名 | 默认值 |
|----------|--------|
| `Mesh.AutomeshStraightLines(bool flag)` | `True` |
| `Mesh.AutomeshEllipticalLines(bool flag)` | `True` |
| `Mesh.AutomeshAtEllipseBounds(bool flag, double factor)` | `True, 10` |
| `Mesh.AutomeshAtWireEndPoints(bool flag)` | `True` |
| `Mesh.AutomeshAtProbePoints(bool flag)` | `True` |
| `Mesh.AutoMeshLimitShapeFaces(bool flag)` | `True` |
| `Mesh.AutoMeshNumberOfShapeFaces(int n)` | `1000` |
| `Mesh.MergeThinPECLayerFixpoints(bool flag)` | `False` |
| `Mesh.AutomeshFixpointsForBackground(bool flag)` | `True` |

#### 细化

| 方法签名 | 说明 |
|----------|------|
| `Mesh.AutomeshRefineAtPecLines(bool flag, int factor)` | PEC 线细化 |
| `Mesh.AutomeshRefinePecAlongAxesOnly(bool flag)` | 仅沿轴 |
| `Mesh.SetAutomeshRefineDielectricsType(enum {"None","Wave","Static"} type)` | 介质细化 |
| `Mesh.MaterialRefinementTet(bool flag)` | 四面体材料细化 |

#### 四面体/表面网格参数

| 方法签名 | 默认值 |
|----------|--------|
| `Mesh.StepsPerWavelengthTet(double val)` | `4` |
| `Mesh.StepsPerWavelengthSrf(double val)` | — |
| `Mesh.StepsPerWavelengthSrfML(double val)` | — |
| `Mesh.MinimumStepNumberTet(double val)` | `10` |
| `Mesh.MinimumStepNumberSrf(double val)` | — |
| `Mesh.SurfaceMeshGeometryAccuracy(double val)` | — |
| `Mesh.SurfaceMeshMethod(enum {"General","Fast"} type)` | `"General"` |
| `Mesh.SurfaceTolerance(double val)` | `1.0` |
| `Mesh.SurfaceToleranceType(enum {"Relative","Absolute"} type)` | `"Relative"` |
| `Mesh.NormalTolerance(double val)` | `15.0` |
| `Mesh.AnisotropicCurvatureRefinementFSM(bool flag)` | — |
| `Mesh.SurfaceMeshEnrichment(int level)` | — |
| `Mesh.SurfaceOptimization(bool flag)` | `True` |
| `Mesh.SurfaceSmoothing(int level)` | `3` |
| `Mesh.CurvatureRefinementFactor(double val)` | `0.05` |
| `Mesh.MinimumCurvatureRefinement(double val)` | `30` |
| `Mesh.AnisotropicCurvatureRefinement(bool flag)` | `False` |
| `Mesh.VolumeOptimization(bool flag)` | `True` |
| `Mesh.VolumeSmoothing(bool flag)` | `True` |
| `Mesh.DensityTransitions(double val)` | `0.5` |
| `Mesh.VolumeMeshMethod(enum {"Delaunay","Advancing Front"} type)` | `"Delaunay"` |
| `Mesh.SelfIntersectionCheck(bool flag)` | `True` |

#### 并行网格

| 方法签名 | 说明 |
|----------|------|
| `Mesh.SetParallelMesherMode(enum {"Hex","Tet"} type, enum {"maximum","user-defined","none"} mode)` | 并行模式 |
| `Mesh.SetMaxParallelMesherThreads(enum {"Hex","Tet"} type, int val)` | 最大线程 |

#### 手动固定点

| 方法签名 | 说明 |
|----------|------|
| `Mesh.AddFixpoint(double x, double y, double z)` | 添加固定点 |
| `Mesh.RelativeAddFixpoint(int id, double dx, double dy, double dz)` | 相对添加 |
| `Mesh.DeleteFixpoint(int id)` | 删除 |
| `Mesh.FindFixpointFromPosition(double x, double y, double z) → int` | 查找 |
| `Mesh.AddAutomeshFixpoint(bool useX, bool useY, bool useZ, double x, double y, double z)` | 添加自动固定点 |
| `Mesh.DeleteAutomeshFixpoint(double x, double y, double z)` | 删除自动固定点 |

#### 查询

| 方法签名 | 返回 | 说明 |
|----------|------|------|
| `Mesh.GetNp()` | `int` | 网格点数 |
| `Mesh.GetXPos(int i)` | `double` | X 坐标 |
| `Mesh.GetYPos(int i)` | `double` | Y 坐标 |
| `Mesh.GetZPos(int i)` | `double` | Z 坐标 |
| `Mesh.GetClosestPtIndex(double x, double y, double z)` | `int` | 最近点索引 |
| `Mesh.GetNumberOfMeshCells()` | `long` | 网格单元数 |
| `Mesh.GetNumberOfMeshCellsMetrics()` | `long` | 质量单元数 |
| `Mesh.GetActiveMeshType()` | `enum` | 当前网格类型 |
| `Mesh.GetMinimumEdgeLength()` | `double` | 最短边 |
| `Mesh.GetMaximumEdgeLength()` | `double` | 最长边 |
| `Mesh.GetSurfaceMeshArea()` | `double` | 表面面积 |

### 15.2 MeshAdaption3D 对象

**文件：** `special_vbamesh\special_vbamesh_meshadaption3d_object.htm`

| 方法签名 | 说明 |
|----------|------|
| `MeshAdaption3D.SetType(enum type)` | 类型 |
| `MeshAdaption3D.SetAdaptionStrategy(enum key)` | 策略 |
| `MeshAdaption3D.AccuracyFactor(double val)` | 精度因子 |
| `MeshAdaption3D.MinPasses(int n)` | 最少轮次 |
| `MeshAdaption3D.MaxPasses(int n)` | 最多轮次 |
| `MeshAdaption3D.MeshIncrement(int val)` | 网格增量（%） |
| `MeshAdaption3D.MaxDeltaS(double val)` | 最大 ΔS |
| `MeshAdaption3D.SetFrequencyRange(bool auto, double min, double max)` | 频率范围 |
| `MeshAdaption3D.ClearStopCriteria()` | 清除停止准则 |
| `MeshAdaption3D.AddSParameterStopCriterion(bool auto, double fmin, double fmax, double maxdelta, int checks, bool active)` | S 参数停止准则 |
| `MeshAdaption3D.Add0DResultStopCriterion(name result, double maxdelta, int checks, bool active)` | 0D 停止准则 |
| `MeshAdaption3D.Add1DResultStopCriterion(name result, double maxdelta, int checks, bool active, bool complex)` | 1D 停止准则 |
| `MeshAdaption3D.RefinementType(enum {"Automatic","Bisection"} type)` | 细化类型 |
| `MeshAdaption3D.CellIncreaseFactor(double factor)` | 单元增长因子 |
| `MeshAdaption3D.WavelengthBasedRefinement(bool flag)` | 基于波长细化 |
| `MeshAdaption3D.SingularEdgeRefinement(int level)` | 奇异边细化 |
| `MeshAdaption3D.SnapToGeometry(bool flag)` | 吸附几何 |
| `MeshAdaption3D.EnableInnerSParameterAdaptation(bool flag)` | 内部 S 参数自适应 |
| `MeshAdaption3D.EnablePortPropagationConstantAdaptation(bool flag)` | 端口传播常数自适应 |

---

## 16. Port — 端口

**文件：** `special_vbaports\special_vbaports_port_object.htm`

### 16.1 Waveguide Port（波端口）

| 属性 | 类型 | 说明 |
|------|------|------|
| `PortType` | enum | 端口类型 |
| `Label` | string | 标签 |
| `NumberOfModes` | int | 模式数 |
| `Coordinates` | string | `"Free"` / `"Picked"` |
| `Orientation` | string | `"x"` / `"y"` / `"z"` |
| `Xrange` / `Yrange` / `Zrange` | `double, double` | 范围 |
| `XrangeAdd` / `YrangeAdd` / `ZrangeAdd` | `double, double` | 端口扩展 |
| `PortOnBound` | bool | 是否在边界上 |
| `ClipPickedPortToBound` | bool | 裁剪到边界 |
| `SingleEnded` | bool | 单端 |
| `WaveguideMonitor` | bool | 波导监视器 |
| `Impedance` | double | 阻抗 |
| `AdjustPolarization` | bool | 调整极化 |
| `PolarizationAngle` | double | 极化角 |
| `ReferencePlaneDistance` | double | 参考面距离 |
| `TextSize` | int | 文本尺寸 |
| `TextMaxLimit` | int | 文本限制 |
| `DeembedDistance` | double | 去嵌距离 |
| `NumberOfLayers` | int | 层数 |
| `CalculateMeanImpedanceAfterAnalysis` | bool | 分析后计算均值阻抗 |

### 16.2 端口类型枚举

```
"SINGUL", "COAX", "WAVEGUIDE", "WGDIA", "WGQUAD", "WGOVAL",
"WGCRL", "WRECT", "WGMLINE", "CPW", "SLOT", "PIN",
"PLANE WAVE", "FLOQUET", "DISCRETE", "DISCRETE_TML"
```

### 16.3 DiscretePort（离散端口）

**文件：** `special_vbaports\special_vbaports_discrete_port_object.htm`

| 属性 | 类型 | 说明 |
|------|------|------|
| `Type` | string | `"SParameter"` / `"Voltage"` / `"Current"` |
| `Impedance` | double | 阻抗 |
| `Voltage` | double | 电压 |
| `Current` | double | 电流 |
| `Monitor` | bool | 监视器 |
| `Radius` | double | 半径 |
| `SetP1(bool pick, double x, double y, double z)` | — | 起点 |
| `SetP2(bool pick, double x, double y, double z)` | — | 终点 |
| `InvertDirection` | bool | 反转方向 |

---

## 17. Monitor — 监视器

**文件：** `special_vbamonitors\special_vbamonitors_monitor_object.htm`（690 行）

### 完整字段类型枚举

```
"Efield 3D", "Efield 2D", "H-Field 3D", "H-Field 2D",
"Powerflow 3D", "Current 3D", "Loss density 3D",
"E-Energy 3D", "H-Energy 3D", "SAR 3D", "Farfield",
"Fieldsource", "Adaption 3D",
"Space charge density 3D", "Particle current density 3D"
```

### 方法

| 方法签名 | 说明 | 默认值 |
|----------|------|--------|
| `Monitor.Reset()` | 重置 | — |
| `Monitor.Name(string name)` | 名称 | — |
| `Monitor.Domain(enum domain)` | `"frequency"` / `"time"` / `"static"` | `"frequency"` |
| `Monitor.FieldType(string type)` | 场类型 | `"Efield"` |
| `Monitor.Frequency(double freq)` | 频率 | — |
| `Monitor.Create()` | 创建 | — |
| `Monitor.Delete(string name)` | 删除 | — |
| `Monitor.Rename(string old, string new)` | 重命名 | — |
| `Monitor.Coordinates(string coord)` | 坐标系 | — |
| `Monitor.PlaneNormal(string normal)` | 法线方向（2D 监视器） | — |
| `Monitor.PlanePosition(double pos)` | 平面位置（2D 监视器） | — |
| `Monitor.SetSubVolume(double x1, x2, y1, y2, z1, z2)` | 子体积 | — |
| `Monitor.SetSubVolumeOffset(double d1..d6)` | 偏移 | — |
| `Monitor.UseSubvolume(bool flag)` | 启用子体积 | — |
| `Monitor.SamplingStrategy(enum {"Linear","Logarithmic"})` | 采样策略 | `"Linear"` |
| `Monitor.Samples(int n)` | 采样数 | — |
| `Monitor.MaxOrder(int n)` | 最大阶数 | `1` |
| `Monitor.FrequencySamples(int n)` | 频点数 | `1` |
| `Monitor.SampleStep(double step)` | 步长 | — |
| `Monitor.AutomaticOrder(bool flag)` | 自动阶数 | — |
| `Monitor.TransientFarfield(bool flag)` | 瞬态远场 | — |
| `Monitor.ExportFarfieldSource(bool flag)` | 导出远场源 | — |
| `Monitor.EnableNearfieldCalculation(bool flag)` | 近场计算 | — |
| `Monitor.TimeAverage(bool flag)` | 时间平均 | — |
| `Monitor.Tstart(double val)` | 开始时间 | — |
| `Monitor.Tstep(double val)` | 时间步长 | — |
| `Monitor.Tend(double val)` | 结束时间 | — |

### 查询

| 方法签名 | 返回 | 说明 |
|----------|------|------|
| `Monitor.GetMonitorDomainFromIndex(int i)` | `string` | 域 |
| `Monitor.GetMonitorFrequencyFromIndex(int i)` | `double` | 频率 |
| `Monitor.GetMonitorTstartFromIndex(int i)` | `double` | Tstart |
| `Monitor.GetMonitorTstepFromIndex(int i)` | `double` | Tstep |
| `Monitor.GetMonitorTendFromIndex(int i)` | `double` | Tend |

### Monitor VBA 示例（官方）

```vba
' 频域 E-field 3D 监视器
With Monitor
    .Reset
    .Name "e-field (f=10)"
    .FieldType "Efield 3D"     ' 或 "Efield"
    .Domain "frequency"
    .Frequency "10"
    .UseSubvolume "False"
    .Create
End With

' 远场监视器（线性步进）
With Monitor
    .Reset
    .Name "farfield broadband"
    .FieldType "Farfield"
    .Domain "frequency"
    .SamplingStrategy "Linear"
    .FrequencySamples "5"
    .SampleStep "0.5"
    .Create
End With

' 带子体积的监视器
With Monitor
    .Reset
    .Name "e-field subvolume"
    .FieldType "Efield"
    .Domain "frequency"
    .Frequency "10"
    .UseSubvolume "True"
    .SetSubVolume "-50", "50", "-50", "50", "0", "100"
    .SetSubVolumeOffset "5", "5", "5", "5", "5", "5"
    .Create
End With
```

---

## 18. 导入导出格式

### 18.1 标准导入模式（所有格式通用）

```vba
With [ObjectName]
    .Reset
    .FileName (".\example.ext")
    .ImportToActiveCoordinateSystem (False)
    .Read
End With
```

### 18.2 标准导出模式

```vba
With [ObjectName]
    .Reset
    .FileName (".\export.ext")
    .ExportFromActiveCoordinateSystem (True)
    .Write ("component1/solid1")   ' 或 .WriteAll
End With
```

### 18.3 各格式独有属性

| 格式 | 独有属性 |
|------|---------|
| **STEP** | `Healing(bool)`, `ScaleToUnit(bool)`, `ExportAttributes(bool)` |
| **SAT** | `Version`, `SaveVersion`, `Wires`, `SubProjectName2D/3D` |
| **IGES** | `Healing(bool)`, `IncludeTopologyInformation(bool)`, `ExportAsNurbsOnly(bool)` |
| **STL** | `NormalTolerance`, `SurfaceTolerance`, `WriteCAD`, `WriteMesh` |
| **DXF** | `Version`, `ImportFileUnits`, `Height`, `Offset`, `AddLayer(name,color,style)` |
| **GDSII** | `SelectedStructure`，其余类似 DXF |
| **OBJ** | `ScaleFactor`, `ImportFileUnits` |
| **CATIA** | `CatiaVersion`, `ImportAttributes`, `PreserveHierarchicalNameForCurves` |
| **PROE/Creo** | `Healing`, `ImportSheets` |
| **SolidWorks** | `ImportHiddenEntities`, `ImportSketches`, `UseFileNameAsShapeName` |
| **HFSS** | `FilenameHFSS`, `FilenameSAB`, `FilenameSM3` — **仅导入** |
| **NASTRAN** | `ReadPointsOnly`, `SetDecimationActive`, `SetMaximalAngle` |
| **Gerber** | `GerberType`, `ApertureFileName`, `Stackup`, `Dimensions` — **仅导入** |
| **HumanModel** | `Tissue`, `Volume`, `Priority`, `Scale`, `Frequency` — **仅导入** |
| **Parasolid** | `Healing`, `ImportHiddenEntities` |
| **TOUCHSTONE** | `Impedance(double)`, `Write` |
| **ASCIIExport** | `Mode`, `SetFileType`, `SetCsvSeparator`, `Step`, `SetSubvolume`（见 §19.3） |

### 18.4 支持的全部导入导出格式列表

STEP, SAT, IGES, STL, DXF, OBJ, GDSII, CATIA, PRO/E(Creo), SOLIDWORKS, SiemensNX, SolidEdge, Inventor, Parasolid, HFSS, NASTRAN, NFS, Gerber, CoventorWare, HumanModel, Mecadtron, VDAFS, MeshImport, TOUCHSTONE, ADSComponentExport, ASCIIExport, LayoutDB, LiveLink

---

## 19. FarfieldPlot & FarfieldCalculator

### 19.1 FarfieldPlot（远场图配置 — 最大的后处理对象，60+ 方法）

**文件：** `special_vbapostproc\special_vbapostproc_farfieldploto.htm`（1227 行）

#### 绘图控制

| 方法签名 | 说明 |
|----------|------|
| `FarfieldPlot.NewPlot()` | 创建新图 |
| `FarfieldPlot.Delete()` | 删除 |
| `FarfieldPlot.Plot()` | **使所有更改生效（每次修改后必须调用）** |
| `FarfieldPlot.ResetSettings()` | 恢复默认设置 |
| `FarfieldPlot.StoreSettings()` | 保存设置到 .plt 文件 |
| `FarfieldPlot.UseSettings()` | 从 .plt 文件加载设置 |

#### 图类型和模式

| 方法签名 | 说明 |
|----------|------|
| `FarfieldPlot.SetPlotType(enum type)` | `"3D"` / `"Polar"` / `"Radiation Pattern"` / `"Cartesian"` / `"2D"` |
| `FarfieldPlot.SetPlotMode(enum mode)` | `"db"` / `"linear"` / `"abs"` |
| `FarfieldPlot.SetStep(int step)` | 角度步长 |
| `FarfieldPlot.UseAutomaticStep(bool flag)` | 自动步长 |
| `FarfieldPlot.SetScale(bool linear)` | True=线性, False=dB |
| `FarfieldPlot.SetMaxValue(double dB)` | 最大值 |
| `FarfieldPlot.SetLogRange(double dB)` | dB 范围 |
| `FarfieldPlot.SetLogNorm(double norm)` | dB 归一化值 |

#### 方向和原点

| 方法签名 | 说明 |
|----------|------|
| `FarfieldPlot.InvertOrientation()` | 反转 |
| `FarfieldPlot.ResetOrientation()` | 重置 |
| `FarfieldPlot.SetOrientation(double theta, double phi)` | 方向 |
| `FarfieldPlot.SetOrigin(string origin)` | 原点类型 |
| `FarfieldPlot.SetOriginToMaximum()` | 置原点于最大值 |
| `FarfieldPlot.SetUserOrigin(double x, double y, double z)` | 自定义原点 |

#### 坐标系和分量

`FarfieldPlot.SetCoordinateSystem(string cs)` — cs 取值：
- `"polarization"` / `"component"` / `"complex"` / `"power"`

#### 频率和时间

| 方法签名 | 说明 |
|----------|------|
| `FarfieldPlot.SetFrequency(double freq)` | 单频 |
| `FarfieldPlot.SetFrequencies(double f1, double f2)` | 频率范围 |

#### 切面控制

| 方法签名 | 说明 |
|----------|------|
| `FarfieldPlot.ClearCuts()` | 清除所有切面 |
| `FarfieldPlot.AddCut(string type, double angle, bool active)` | 添加切面 |
| `FarfieldPlot.AddCut2(string type, double angle, bool active)` | 添加第二切面 |

#### 远场属性

| 方法签名 | 说明 |
|----------|------|
| `FarfieldPlot.SetFarfieldPlotMode(string mode)` | `"directivity"` / `"gain"` / `"realized gain"` / `"efield"` / `"hfield"` / `"pfield"` / `"rcs"` / `"rcsunits"` / `"rcssw"` |
| `FarfieldPlot.SetPlotAsFunctionOf(string var)` | 作为什么的函数 |
| `FarfieldPlot.SetCoordinateSystemType(string type)` | `"spherical"` / `"ludwig2ae"` / `"ludwig2ea"` / `"ludwig3"` |

#### 轴对称

| 方法签名 | 说明 |
|----------|------|
| `FarfieldPlot.SetSymmetricAzimuthAngle(double angle)` | 对称方位角 |
| `FarfieldPlot.UseAutomaticAzimuthRange(bool flag)` | 自动方位范围 |
| `FarfieldPlot.SetAzimuthRange(double min, double max)` | 方位范围 |

#### 外观

| 方法签名 | 说明 |
|----------|------|
| `FarfieldPlot.SetUnit(string unit)` | 单位 |
| `FarfieldPlot.ShowTransparency(bool flag)` | 透明度 |

#### 统计查询

| 方法签名 | 返回 | 说明 |
|----------|------|------|
| `FarfieldPlot.GetMax()` | `double` | 最大值 |
| `FarfieldPlot.GetMin()` | `double` | 最小值 |
| `FarfieldPlot.GetMean()` | `double` | 均值 |
| `FarfieldPlot.GetTRP()` | `double` | 总辐射功率 |
| `FarfieldPlot.GetRadiationEfficiency()` | `double` | 辐射效率 |
| `FarfieldPlot.GetMainLobeDirection()` | — | 主瓣方向 |
| `FarfieldPlot.GetAngularWidthXdB(double x)` | `double` | x-dB 波束宽度 |
| `FarfieldPlot.GetSideLobeSuppression()` | `double` | 旁瓣抑制 |

#### 导出

| 方法签名 | 说明 |
|----------|------|
| `FarfieldPlot.ASCIIExportVersion(string ver)` | `"2009"` / `"2010"` |
| `FarfieldPlot.ASCIIExportAsSource(string fileName)` | 导出远场源 |
| `FarfieldPlot.CopyFarfieldTo1DResults(string folder, string name)` | 复制到 1D 结果 |

#### FarfieldPlot VBA 示例（官方）

```vba
' 基本极坐标远场图
With FarfieldPlot
    .Reset
    .Plottype "polar"
    .Vary "angle1"
    .Step 1
    .SetPlotMode "gain"
    .Plot
End With

' 3D 远场图
With FarfieldPlot
    .Reset
    .Plottype "3d"
    .SetPlotMode "directivity"
    .Plot
End With

' 自定义用户原点
With FarfieldPlot
    .Reset
    .Plottype "3d"
    .SetUserOrigin "10", "20", "30"
    .Plot
End With
```

### 19.2 FarfieldCalculator（COM 方式，非 VBA With/Reset 模式）

**文件：** `special_vbapostproc\special_vbapostproc_farfieldcalculator_object.htm`

| 方法签名 | 说明 |
|----------|------|
| `FarfieldCalculator.Reset()` | 重置 |
| `FarfieldCalculator.Delete()` | 删除 |
| `FarfieldCalculator.SetResultID(string id)` | 设置结果 ID |
| `FarfieldCalculator.SetResultName(string name)` | 设置结果名 |
| `FarfieldCalculator.SetConstantPhi(double phi)` | 固定 Phi |
| `FarfieldCalculator.SetConstantTheta(double theta)` | 固定 Theta |
| `FarfieldCalculator.UseAutomaticTolerance(bool flag)` | 自动容差 |
| `FarfieldCalculator.SetTolerance(double tol)` | 容差 |
| `FarfieldCalculator.AddCartesianFieldComponent(double x, double y, double z, double freq)` | 添加笛卡尔场分量 |
| `FarfieldCalculator.Calc(string farfieldName)` | 计算 |
| `FarfieldCalculator.Plot()` | 绘图 |
| `FarfieldCalculator.StoreSettings()` | 保存 |
| `FarfieldCalculator.UseSettings()` | 加载 |

**CalcOperation 枚举：**
```
"Add", "Subtract", "Multiply", "Divide", "Energy", "Efficiency",
"RealizedGain", "Directivity", "RCS", "AxialRatio", "AxialRatioFine",
"Phase", "None"
```

**场分量语法：** `"<坐标系统> <极化> <分量> <复数部分>"`

- 坐标系统: `"spherical"` / `"ludwig2ae"` / `"ludwig2ea"` / `"ludwig3"`
- 极化: `"linear"` / `"circular"` / `"slant"` / `"abs"`
- 分量: `"theta"` / `"phi"` / `"left"` / `"right"` / `"horizontal"` / `"vertical"`
- 复数部分: `"real"` / `"imag"` / `"magnitude"` / `"phase"` / `"db"` / `"dbphase"` / `"db10magnitude"` / `"db10phase"`

```vba
' 示例：计算远场 Etheta 分量
With FarfieldCalculator
    .Reset
    .SetResultName "farfield (f=10) [1]"
    .AddCartesianFieldComponent "0", "0", "0", "10"
    .Calc "farfield (f=10) [1]"
End With
```

### 19.3 ASCIIExport（直出文本/CSV）

**文件：** `common_vbaimpexp\asciiexport_object.htm`

| 方法签名 | 说明 |
|----------|------|
| `ASCIIExport.Reset()` | 重置 |
| `ASCIIExport.Mode(string mode)` | `"2D"` / `"3D"` / `"1D"` / `"Farfield"` / `"Eigenmode"` / `"NTFF"` / `"TimeSignal"` |
| `ASCIIExport.FileName(string path)` | 输出文件路径 |
| `ASCIIExport.SetFileType(string type)` | `"ascii"` / `"csv"` / `"hdf5"` |
| `ASCIIExport.SetCsvSeparator(string sep)` | CSV 分隔符 |
| `ASCIIExport.Step(int n)` | 角度步数（所有方向） |
| `ASCIIExport.StepX(int n)` / `.StepY(n)` / `.StepZ(n)` | 单方向步数 |
| `ASCIIExport.Coordinates(string coord)` | 坐标系统 |
| `ASCIIExport.CoordinateSystem(string cs)` | 坐标系 |
| `ASCIIExport.Direct(bool flag)` | 直接模式 |
| `ASCIIExport.Frequency(double freq)` | 频率 |
| `ASCIIExport.ThetaStep(int n)` / `.PhiStep(int n)` | Theta/Phi 步数 |
| `ASCIIExport.UseSubvolume(bool flag)` | 子体积 |
| `ASCIIExport.SetSubvolume(double x1,x2,y1,y2,z1,z2)` | 子体积范围 |
| `ASCIIExport.SetTimeRange(double min, double max)` | 时间范围 |
| `ASCIIExport.SetSampleRange(double min, double max)` | 采样范围 |
| `ASCIIExport.ExportCoordinatesInMeter(bool flag)` | 坐标用米 |
| `ASCIIExport.PhaseCenter(double x, double y, double z)` | 相位中心 |
| `ASCIIExport.UsePhaseCenterAsOrigin(bool flag)` | 相位中心为原点 |
| `ASCIIExport.Execute()` | 执行导出 |

**注意：** ASCIExport 必须在 `SelectTreeItem` 选中结果树节点之后调用。

---

## 20. ResultTree & 结果读取

**文件：** `special_vbapostproc\special_vbapostproc_resulttreeo.htm`

### 方法

| 方法签名 | 返回 | 说明 |
|----------|------|------|
| `ResultTree.GetTreeItem(string path, string filter)` | `variant` | filter ∈ `{"0D/1D","colormap","farfields","schematic","timeSignals","carg","dynamic","s-parameter-CC"}` |
| `ResultTree.GetTreeItemType(string path)` | `string` | 节点类型 |
| `ResultTree.GetTreeItemValue(string path)` | `double` | 节点数值 |
| `ResultTree.GetResultIDFromTreeTab(int tab, string path)` | `string` | 结果 ID |
| `ResultTree.GetResultsFromTreeTab(int tab, string path)` | `variant` | 所有结果 |
| `ResultTree.GetTimeSignalsFromTreeTab(int tab, string path)` | `variant` | 时域信号 |
| `ResultTree.SelectTreeItem(string itemname)` | `bool` | 选中树节点 |
| `ResultTree.WaitForTreeItem(string itemname)` | — | 等待节点出现 |
| `ResultTree.GetBranchName(int tab, string path)` | `string` | 分支名 |
| `ResultTree.GetNumberOfChildren(int tab, string path)` | `int` | 子节点数 |
| `ResultTree.GetResultByID(string id)` | `object` | 按 ID 获取结果对象 |

### VBA 示例

```vba
' 列出 1D 结果
Dim items As Variant
items = ResultTree.GetTreeItem("2D/1D", "0D/1D")

' 获取 S11 结果
Dim resultIDs As Variant
resultIDs = ResultTree.GetResultIDsFromTreeItem("1D Results\S-Parameters\S1,1")
Dim latestID As String
latestID = resultIDs(UBound(resultIDs))

' 获取结果对象
Dim s11 As Object
Set s11 = ResultTree.GetResultFromTreeItem("1D Results\S-Parameters\S1,1", latestID)
```

---

## 21. Result1D / Result1DComplex / Result0D

### 21.1 Result1DComplex（复数 1D — S 参数等）

**文件：** `special_vbapostproc\result_1d_complex_object.htm`

| 方法签名 | 说明 |
|----------|------|
| `Result1DComplex.Load(string file)` | 加载 .sig 文件 |
| `Result1DComplex.Save(string file)` | 保存 .sig |
| `Result1DComplex.GetN() → long` | 数据点数 |
| `Result1DComplex.GetX(long i) → double` | 第 i 个 X 值 |
| `Result1DComplex.GetYRe(long i) → double` | 第 i 个 Y 实部 |
| `Result1DComplex.GetYIm(long i) → double` | 第 i 个 Y 虚部 |
| `Result1DComplex.GetArray(string comp) → variant` | `"x"`, `"yre"`, `"yim"` 批量读取 |
| `Result1DComplex.GetArrayX(string name) → variant` | 获取 X 数组 |
| `Result1DComplex.GetArrayY(string name) → variant` | 获取 Y 数组 |
| `Result1DComplex.GetArrayComplexY(string name) → variant` | 获取复数 Y 数组 |
| `Result1DComplex.GetArrayPhaseY(string name) → variant` | 获取相位数组 |
| `Result1DComplex.GetNumberOfArrays() → int` | 数组数 |
| `Result1DComplex.GetNumberOfDataSets() → int` | 数据集数 |
| `Result1DComplex.GetNumberOfRows() → int` | 行数 |
| `Result1DComplex.GetRowID(long i) → string` | 行 ID |
| `Result1DComplex.GetRowLabel(long i) → string` | 行标签 |

### 21.2 Result1D（标量 1D — 实数曲线）

**文件：** `special_vbapostproc\special_vbapostprocres1do.htm`

| 方法签名 | 说明 |
|----------|------|
| `Result1D.GetArrayX(string name) → variant` | X 数组 |
| `Result1D.GetArrayY(string name) → variant` | Y 数组 |

### 21.3 Result0D（0D — 标量值）

**文件：** `special_vbapostproc\result_0d_object.htm`

| 方法签名 | 返回 | 说明 |
|----------|------|------|
| `Result0D.GetArray(string name) → variant` | | 获取数组 |
| `Result0D.Get1DArray() → variant` | | 1D 数组形式 |
| `Result0D.GetName() → string` | | 名称 |
| `Result0D.GetType() → string` | | 类型 |
| `Result0D.GetUnit() → string` | | 单位 |
| `Result0D.GetID() → string` | | ID |
| `Result0D.GetNumberOfArrays() → int` | | 数组数 |
| `Result0D.GetNumberOfRows() → int` | | 行数 |
| `Result0D.GetRow(int i) → variant` | | 第 i 行 |
| `Result0D.GetRowID(int i) → string` | | 行 ID |
| `Result0D.GetRowLabel(int i) → string` | | 行标签 |

### VBA 示例

```vba
' 读取 S11 的 0D 值（单频）
Dim s11vals As Variant
s11vals = Result0D.Get1DArray()
' → 数组包含每行的名称、值、单位

' 读取远场 RCS
Dim rcsVals As Variant
rcsVals = Result0D.GetArray("RCS")

' 遍历结果 ID
Dim allIDs As Variant
allIDs = ResultTree.GetResultIDsFromTreeItem("1D Results\S-Parameters\S1,1")
Dim id As Variant
For Each id In allIDs
    Dim r As Object
    Set r = ResultTree.GetResultFromTreeItem("1D Results\S-Parameters\S1,1", id)
Next
```

### 21.4 PostProcess1D

**文件：** `special_vbapostproc\special_vbapostproc_postprocess1d_object.htm`

| 方法签名 | 说明 |
|----------|------|
| `PostProcess1D.Reset()` | 重置 |
| `PostProcess1D.Calc()` | 计算 |
| `PostProcess1D.GetArray(string name) → variant` | 获取数组 |
| `PostProcess1D.SetCombine(enum {"Add","Subtract","Multiply","Divide","Convolution","Correlation","Concatenation"})` | 组合方式 |

### 21.5 CombineResults

**文件：** `special_vbapostproc\special_vbapostproc_combineresults_object.htm`

| 方法签名 | 说明 |
|----------|------|
| `CombineResults.Reset()` | 重置 |
| `CombineResults.AddDataset(string id)` | 添加数据集 |
| `CombineResults.Calc()` | 计算 |
| `CombineResults.CalcAll()` | 全计算 |
| `CombineResults.GetResult(string name) → object` | 获取结果 |
| `CombineResults.PlotAll()` | 全绘图 |
| `CombineResults.SetConstraint(enum {"Equality","GreaterThan","LessThan"})` | 约束 |
| `CombineResults.SetParameter(enum param)` | param ∈ `{"Expression","Stime","Etime","T1","T2","Const0","Samples","fmin","fmax","N","CalcSteps"}` |

---

## 22. Plot1D — 1D 绘图

**文件：** `common_vbaplot\common_vbaplot_plot1d_object.htm`（353 行）

### 视图与外观

| 方法签名 | 说明 |
|----------|------|
| `Plot1D.Plot()` | 刷新图 |
| `Plot1D.PlotView(enum view)` | `"real"` / `"imaginary"` / `"magnitude"` / `"magnitudedb"` / `"phase"` / `"polar"` / `"smith"` / `"smithy"` |
| `Plot1D.ResetView()` | 重置视图 |
| `Plot1D.ShowPlotLegend(bool flag)` | 图例 |
| `Plot1D.UseCurveSmoothing(bool flag)` | 平滑 |
| `Plot1D.ShowReferenceCircle(bool flag)` | 参考圆（Smith） |

### 轴控制

| 方法签名 | 说明 |
|----------|------|
| `Plot1D.XAutorange(bool flag)` | 自动范围 |
| `Plot1D.XAutoTick(bool flag)` | 自动刻度 |
| `Plot1D.XLogarithmic(bool flag)` | 对数 |
| `Plot1D.XRange(double min, double max)` | 范围 |
| `Plot1D.XRoundscale(bool flag)` | 圆整 |
| `Plot1D.XTicks(int n)` | 刻度数 |
| `Plot1D.XTicksDistance(double d)` | 刻度间距 |
| （`Y*` 同理） | |

### 标记

| 方法签名 | 说明 |
|----------|------|
| `Plot1D.AddMarker(double x, double y)` | 添加标记 |
| `Plot1D.AddMarkerToCurve(int curveIndex, double x)` | 添加到曲线 |
| `Plot1D.DeleteAllMarker()` | 删除 |
| `Plot1D.DeleteMarker(int id)` | 删除指定 |
| `Plot1D.ShowMarkerAtMin(bool flag)` | 最小值标记 |
| `Plot1D.ShowMarkerAtMax(bool flag)` | 最大值标记 |

### 曲线样式

| 方法签名 | 说明 |
|----------|------|
| `Plot1D.SetLineColor(int curveIndex, int r, int g, int b)` | 线色 |
| `Plot1D.RemoveLineColor(int curveIndex)` | 移除 |
| `Plot1D.SetLineStyle(int curveIndex, enum style)` | `"solid"` / `"dashed"` / `"dotted"` / `"dashdotted"` |
| `Plot1D.SetMarkerStyle(int curveIndex, enum style)` | `"auto"` / `"additionalmarks"` / `"marksonly"` / `"nomarks"` |

### 查询

| 方法签名 | 返回 | 说明 |
|----------|------|------|
| `Plot1D.GetNumberOfCurves()` | `int` | 曲线数 |
| `Plot1D.GetCurveValue(int i, double x)` | `double` | 曲线值 |
| `Plot1D.GetMaximumLocation(int i)` | `double` | 最大值位置 |
| `Plot1D.GetMinimumLocation(int i)` | `double` | 最小值位置 |
| `Plot1D.ExportImage(string name, int w, int h)` | — | 导出图像 |

---

## 23. 附录：关键枚举速查

### 求解器类型

```
"HF Time Domain", "HF Frequency Domain", "HF Eigenmode",
"HF Integral Equation", "Asymptotic", "EM Static", "EM Quasistatic",
"EM Magnetostatic", "EM Electrostatic", "Stationary Current",
"Thermal Steady State", "Thermal Transient", "Particle Tracking",
"PIC", "Wakefield", "CHT", "Structural Mechanics"
```

### 网格类型

```
"HexahedralFIT", "HexahedralTLM", "Tetrahedral", "Surface", "SurfaceML", "Planar"
```

### 边界条件

```
"expanded open", "open", "open (add space)", "electric", "magnetic",
"periodic", "conducting wall"
```

### 对称类型

```
"none", "electric", "magnetic"
```

### Plot1D 视图模式

```
"real", "imaginary", "magnitude", "magnitudedb", "phase", "polar", "smith", "smithy"
```

### FarfieldPlot 图类型

```
"polar", "cartesian", "2d", "2dortho", "3d", "Radiation Pattern"
```

### FarfieldPlot 绘图模式

```
"directivity", "gain", "realized gain", "efield", "hfield", "pfield",
"rcs", "rcsunits", "rcssw"
```

### 坐标系类型

```
"spherical", "ludwig2ae", "ludwig2ea", "ludwig3"
```

### 线型

```
"solid", "dashed", "dotted", "dashdotted"
```

### 采样策略

```
"Linear", "Logarithmic"
```

### 布尔类型限制

在 CST VBA 中布尔值使用字符串 `"True"` / `"False"`（带引号），少数情况可用 `True` / `False`（不带引号）。两种写法均有效，但推荐**带引号**以保证兼容性。

---

## 参考

所有内容提取自 `C:\Program Files\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D\` 官方 HTML 文档。

常用子目录速查：
- `common_vbabasicsolids/` — Brick, Cylinder, Cone, Sphere, Torus, Wire, ECylinder, AnalyticalFace
- `common_vbacurves/` — Arc, Circle, Ellipse, Line, Polygon, Rectangle, Spline, AnalyticalCurve, Polygon3D
- `common_vbasolido/` — Solid（布尔运算/查询/修复）
- `common_vbaextrude/`, `common_vbaloft/`, `common_vbarotateo/` — Extrude, Loft, Rotate
- `common_vbaimpexp/` — 所有导入导出格式
- `special_vbaports/` — Port, DiscretePort, FloquetPort, PlaneWave
- `special_vbamonitors/` — Monitor, Probe
- `special_vbamesh/` — Mesh, MeshAdaption3D
- `special_vbasolver/` — Solver, FDSolver, Eigenmode, IE, Asymptotic, Background, Boundary, Optimizer
- `special_vbapostproc/` — FarfieldPlot, FarfieldCalculator, ResultTree, Result1DComplex, PostProcess1D, CombineResults
- `common_vbaplot/` — Plot1D, Plot, ScalarPlot2D/3D, VectorPlot2D/3D
- `common_vbaunitso/` — Units
- `common_vbaapp/` — Project 全局方法（参数/文件/求解器控制）
- `special_vbaparametersweep/` — ParameterSweep
- `special_vbatransformo/` — Transform
- `common_vbapicko/` — Pick
- `common_vbawcso/` — WCS, AnchorPoint
