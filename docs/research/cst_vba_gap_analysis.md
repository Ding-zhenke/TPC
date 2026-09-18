# CST 2026 VBA 封装差距清单

核对日期：2026-09-18。依据本机 CST 2026 帮助目录：
`C:\SOFTWARE\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D`。
本文件是帮助文档与当前 Python 源码的差集调查，不代表每个 CST 对象都应直接暴露为 Python 方法；实施前仍需确认对象在 CST Studio Suite MWS 工程中的适用范围、参数语义和许可证条件。本轮不运行求解。由 [`scripts/build_cst_vba_catalog.py`](../../scripts/build_cst_vba_catalog.py) 生成的 647 页索引见 [`cst_vba_catalog.json`](./cst_vba_catalog.json)；按对象族的离线覆盖报告见 [`cst_vba_coverage.json`](./cst_vba_coverage.json)，可用 [`scripts/check_vba_coverage.py`](../../scripts/check_vba_coverage.py) 重建。

## 当前已经覆盖的主要范围

当前库已有参数、项目生命周期、材料基础定义、基本实体与布尔、曲线的一部分、变换、坐标系、边界/背景、基础端口、场监视器、频率范围、常用求解器入口、结果树/1D 读取、远场绘图与 CSV 导出。对应代码主要在 `cst_solver/modeling/`、`cst_solver/simulation/`、`cst_solver/postprocessing/` 和 `cst_solver/_result_core.py`。

## 帮助中明确存在、当前尚未形成完整封装的对象族

| 优先级 | VBA 帮助对象/目录 | 当前差距 | 计划 |
|---|---|---|---|
| P1 | `special_vbapostproc`：`Result0D`、复数 1D、2D/3D、矩阵、`ResultTree`、`FarfieldCalculator`、`NearfieldScan`、`NetworkParameterExtraction`、`QFactor`、SAR、结果映射/跟踪 | 当前主要是结果树和 1D 读取；没有统一的 0D/2D/3D/矩阵对象模型、场值查询、近场扫描、Q 因子和网络参数提取 API | 设计 `ResultDataset`/`ResultMatrix`/`FieldResult` 的统一读取接口，保留 CST 原始 tree path，并先做离线 fixture；真实结果验证另列，不在本轮运行 |
| P1 | `special_vbaports`：Floquet、Cable、Discrete Face、Field Source、Plane Wave、Farfield Source | 已有普通波导/离散/电缆端口的部分接口，但 Floquet、面离散端口、场源、平面波和远场源未形成完整 API | 补齐端口对象与参数校验；端口方向、模式、极化、参考面和边界条件使用结构化配置，不再要求用户手写 VBA |
| P1 | `special_vbamonitors`：Time/0D/1D/2D/3D、Voltage、Current、Particle、PIC monitors | 当前有频域场监视器、2D monitor、probe；时间域、0D/1D/3D、Voltage/Current 以及粒子/PIC 监视器不完整 | 统一 `MonitorSpec`，按监视器类型生成/查询/删除/复制，并把结果路径登记到运行记录 |
| P1 | `special_vbasolver`：FD、Eigenmode、IE、Asymptotic、PIC、ADS/Cosimulation、Solver/Parameter、Sensitivity、Optimizer | 当前 solver 分派覆盖有限；缺少各 solver 的专用配置对象、网格/本征模跟踪、灵敏度和 CST 内置优化对象 | 先定义 solver capability matrix 和纯配置模型，再为 FD/Eigenmode/IE/Asymptotic 补 VBA 适配；Sensitivity/Optimizer 与现有 Python scan/GA 明确边界 |
| P1 | `special_vbaparametersweep`：ParameterSweep | Python 有扫描/批处理编排，但没有 CST 原生参数扫描对象的完整封装 | 支持 CST sweep 的参数、采样、恢复、结果关联；与 `ParameterScan` 做同一任务记录，不重复两套分析规则 |
| P2 | `common_vbacurves`、`common_vbaextrude`、`common_vbaloft`、`common_vbabasicsolids` | 当前有 polyline/arc/ellipse/circle/line/spline/rectangle/polygon3D 及 brick/cylinder/sphere/torus 等常用实体；帮助还包括 analytical curve、blend/chamfer/cover/edge/trace/projection/trim/sweep、extrude、loft、face 操作等 | 先补高复用曲线和实体：cover/trim/sweep/loft、面提取/封闭、变截面挤出；每个操作加入 component/name/历史记录和几何守卫 |
| P2 | `common_vbaimpexp`：DXF/GDSII/IGES/OBJ/SAT/STL/STEP/HFSS/CATIA/GERBER/Nastran 等 | 当前已有 DXF/部分导入导出路径，但没有统一 CAD interchange API，格式能力不完整 | 建立 `ImportSpec`/`ExportSpec` 与能力探测；优先 STEP/IGES/OBJ/GDSII/HFSS，明确“只导入几何”与“保留材料/端口/结果”的差异 |
| P2 | `common_vbapostproc`：evaluate field along curve/on face、result database、plot/colour ramp | 当前有基本绘图和 CSV/HTML 报告，但没有沿曲线/面求值、结果数据库和 CST 图层/色标控制 | 增加场后处理数据 API，输出 NumPy/CSV/报告；绘图只做数据适配，不在核心层复制 CST GUI |
| P2 | `common_vbaunitso`、`common_vbawcso`、`common_vbapicko` | 当前有部分单位、WCS、pick/face 辅助；没有完整单位对象、WCS 保存/恢复/对齐和 pick 状态生命周期 | 收口上下文管理器与恢复语义，补齐单位、WCS、pick 的查询/撤销/清理 |
| P3 | `special_vbathermalsolver`、`special_vbastaticsolver`、`special_vbatransientsolvers`、`special_vbawakefieldsolver`、粒子/机械/热对象 | 当前项目目标主要是 TPC 电磁建模；热、静态、瞬态、粒子、尾场和结构对象基本未封装 | 只有出现对应算例时再立项；先做能力发现和清晰的 `unsupported_solver` 错误，不引入空壳接口 |

## 先做的收口任务

1. ✅ 已从帮助 HTML 的对象页生成机器可读的 CST 2026 VBA capability catalog（当前安装目录共 647 个 VBA 页面）；后续继续从具体对象页补充 method/property/signature，不只依据文件名猜参数。
2. 将 catalog 与 `cst_solver` 公开 API 生成差异报告，区分“完全缺失”“已有但参数不全”“已有且仅缺测试”。
3. 对 P1 结果、端口、监视器、solver 四组先补离线 VBA golden tests 和参数校验；真实 CST 只做建模/对象创建验证，求解结果验证按用户后续授权单独执行。
4. 每新增一个封装，同时更新 `docs/packages/`、`skills/developer/WORKFLOW.md`、相关 `skills/user/` 和 `docs/next_plan/README.md`；没有实测依据时不得写成已支持。

## 参考页

- `mergedProjects/3D/common_overview/common_overview_vba.htm`：VBA 宏和 History List 总览。
- `mergedProjects/VBA_3D/special_vbapostproc/`：结果与后处理对象。
- `mergedProjects/VBA_3D/special_vbaports/`：端口与场源对象。
- `mergedProjects/VBA_3D/special_vbamonitors/`：监视器对象。
- `mergedProjects/VBA_3D/special_vbasolver/`：专用求解器对象。
- `mergedProjects/VBA_3D/common_vbacurves/`、`common_vbaimpexp/`：几何曲线和格式导入导出对象。
