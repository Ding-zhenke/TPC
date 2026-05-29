# -*- coding: utf-8 -*-
"""
CST Studio Suite 自动化 Python 接口包
======================================
封装 CST 的 VBA 操作 API，提供 Pythonic 的调用方式。

主要类:
    setup — CST 建模/仿真/后处理全流程控制类（Mixin 聚合）
    result — CST 仿真结果读取类

快速开始:
    >>> from cst_solver import setup, result
    >>> app = setup("project.cst")
    >>> app.create_brick(0, 10, 0, 10, 0, 2, "substrate", material="Quartz (lossy)")
    >>> app.set_frequency_range(1, 10)
    >>> app.run()
    >>> res = result("project.cst")
    >>> s11 = res.read_s_parameter("S1,1")

@author: PC
"""

import sys
import os

# ============================================================
# 加载配置：用户只需配置 CST_INSTALL_PATH，其余路径自动推导
# 配置优先顺序: config.py > config_template.py > 默认值
# ============================================================
try:
    from cst_solver.config import CST_INSTALL_PATH, CST_PYTHON_LIB, CST_MATERIAL_LIB
except ImportError:
    try:
        from cst_solver.config_template import CST_INSTALL_PATH, CST_PYTHON_LIB, CST_MATERIAL_LIB
        print("⚠ 未找到 config.py，使用 config_template.py 中的默认配置")
        print("   请复制 config_template.py 为 config.py 并修改 CST_INSTALL_PATH")
    except ImportError:
        CST_INSTALL_PATH = r"C:\SOFTWARE\CST Studio Suite 2026"
        CST_PYTHON_LIB = os.path.join(CST_INSTALL_PATH, "AMD64", "python_cst_libraries")
        CST_MATERIAL_LIB = os.path.join(CST_INSTALL_PATH, "Library", "Materials")
        print("⚠ 未找到配置文件，使用默认 CST 路径")
        print("   请创建 cst_solver/config.py 并设置 CST_INSTALL_PATH")

# 将 CST Python 库路径添加到系统路径
if CST_PYTHON_LIB and CST_PYTHON_LIB not in sys.path:
    sys.path.append(CST_PYTHON_LIB)

# 导入 CST 库
import cst
import cst.interface
import cst.results

# ============================================================
# 导入所有 Mixin 模块
# ============================================================
from cst_solver.project import ProjectMixin
from cst_solver.units import UnitsMixin
from cst_solver.parameters import ParametersMixin
from cst_solver.modeling.primitives import ModelingPrimitivesMixin
from cst_solver.modeling.curves import CurvesMixin
from cst_solver.modeling.curves_ops import CurveOpsMixin
from cst_solver.modeling.booleans import SolidOpsMixin
from cst_solver.modeling.transforms import TransformMixin
from cst_solver.modeling.picks import PickMixin
from cst_solver.material.materials import MaterialMixin
from cst_solver.simulation.ports import PortMixin
from cst_solver.simulation.sources import SourceMixin
from cst_solver.simulation.monitors import MonitorMixin
from cst_solver.simulation.boundary import BoundaryMixin
from cst_solver.simulation.solver import SolverMixin
from cst_solver.mesh.mesh import MeshMixin
from cst_solver.import_export.io import IOMixin
from cst_solver.postprocessing.proc import PostProcMixin
from cst_solver.postprocessing.farfield import FarfieldMixin
from cst_solver.postprocessing.result_export import ExportMixin

# ============================================================
# 导入结果类
# 注意：Python 导入机制优先返回子模块，因此 `from cst_solver import result`
# 得到的是模块而非类。如需类，请用:
#   from cst_solver.result import result
# 或使用旧兼容层:
#   from cst_solver import setup, result   # 通过 cst_solver.py 兼容层
# ============================================================
from cst_solver.result import result as _result_class
# 注意: 直接使用 result 变量名会被子模块覆盖，故这里不做赋值

# ============================================================
# 额外建模功能 — 面操作（依赖 pick）
# ============================================================


class FaceOpsMixin:
    """
    CST 面操作 Mixin
    提供表面拉伸、表面旋转等基于面的建模功能
    """

    def rotation_face(self, name, angle, component='component1', material='Vacuum'):
        """
        对拾取的实体表面执行旋转拉伸，生成旋转曲面特征
        保留原函数名以兼容旧代码

        :param name: str, 目标实体名称
        :param angle: float/str, 旋转角度
        :param component: str, 归属组件
        :param material: str, 拉伸材料
        """
        f1 = f"""With Rotate 
        .Reset 
        .Name "{name}" 
        .Component "{component}" 
        .NumberOfPickedFaces "1" 
        .Material "{material}" 
        .Mode "Picks" 
        .Angle "{angle}" 
        .Height "0.0" 
        .RadiusRatio "1.0" 
        .TaperAngle "0.0" 
        .NSteps "0" 
        .SplitClosedEdges "True" 
        .SegmentedProfile "False" 
        .DeleteBaseFaceSolid "False" 
        .ClearPickedFace "True" 
        .SimplifySolid "True" 
        .UseAdvancedSegmentedRotation "True" 
        .CutEndOff "False" 
        .Create 
        End With
        """
        self.cst_file.model3d.add_to_history("Rotation Face: " + name, f1)

    def rotate_face(self, name, angle, component='component1', material='Vacuum'):
        """
        旋转拉伸表面（蛇形命名）
        等同于 rotation_face()
        """
        self.rotation_face(name, angle, component, material)

    def extrude_face(self, name, height, material='PEC', component='component1'):
        """
        对拾取的实体表面执行拉伸操作，生成凸起/凹陷特征
        保留原函数名以兼容旧代码

        :param name: str, 目标实体名称
        :param height: float/str, 拉伸高度（正数凸起，负数凹陷）
        :param material: str, 拉伸特征材料
        :param component: str, 归属组件
        """
        f1 = f"""With Extrude 
     .Reset 
     .Name "{name}" 
     .Component "{component}" 
     .Material "{material}" 
     .Mode "Picks" 
     .Height "{height}" 
     .Twist "0.0" 
     .Taper "0.0" 
     .UsePicksForHeight "False" 
     .DeleteBaseFaceSolid "False" 
     .KeepMaterials "False" 
     .ClearPickedFace "True" 
     .Create 
End With"""
        self.cst_file.model3d.add_to_history("Extrude Face: " + name, f1)

    def trace_curve(self, name, height, weight, material='PEC',
                    curve='curve1', component='component1'):
        """
        沿指定曲线绘制带状实体（走线/传输线）
        保留原函数名以兼容旧代码

        :param name: str, 带状实体名称
        :param height: float/str, 厚度
        :param weight: float/str, 宽度
        :param material: str, 材料名称
        :param curve: str, 走线中心曲线名称
        :param component: str, 归属组件
        """
        f1 = f"""With TraceFromCurve 
     .Reset 
     .Name "{name}" 
     .Component "{component}" 
     .Material "{material}" 
     .Curve "{curve}:{name}" 
     .Thickness "{height}" 
     .Width "{weight}" 
     .RoundStart "False" 
     .RoundEnd "False" 
     .DeleteCurve "True" 
     .GapType "2" 
     .Create 
End With"""
        self.cst_file.model3d.add_to_history("Trace on curve: " + str(name), f1)


# ============================================================
# setup 主类 — 通过多继承聚合所有功能
# ============================================================


class setup(
    ProjectMixin,
    UnitsMixin,
    ParametersMixin,
    ModelingPrimitivesMixin,
    CurvesMixin,
    CurveOpsMixin,
    SolidOpsMixin,
    TransformMixin,
    PickMixin,
    FaceOpsMixin,
    MaterialMixin,
    PortMixin,
    SourceMixin,
    MonitorMixin,
    BoundaryMixin,
    SolverMixin,
    MeshMixin,
    IOMixin,
    PostProcMixin,
    FarfieldMixin,
    ExportMixin,
):
    """
    CST 电磁仿真自动化操作核心类
    ==============================
    通过多继承聚合所有功能模块，包括:
        - 项目操作: 打开/关闭/保存
        - 参数管理: 参数/表达式/频率范围
        - 基本体建模: 长方体/圆柱/球/圆锥/圆环/椭圆柱/三角形/六边形
        - 曲线绘制: 多边形/圆弧/圆/椭圆/直线/样条
        - 曲线操作: 拉伸/放样/扫掠/混合/修剪
        - 布尔运算: 相加/相减/相交/插入/压印/倒角
        - 变换: 平移/旋转/镜像/缩放
        - 选取: 棱边/端点/表面/顶点
        - 面操作: 表面拉伸/旋转/走线
        - 材料与组件: 材料创建/组件管理
        - 端口: 波导端口/离散端口/集总元件
        - 激励源: 平面波/电流源/线圈/磁体
        - 监视器: 场监视器/探针
        - 边界条件: 边界/背景/对称面
        - 求解器: 时域/频域/本征模
        - 网格: 网格属性/自适应
        - 导入导出: SAT/DXF/STEP/IGES/STL
        - 后处理: 远场/Q因子/结果导出

    用法:
        >>> app = setup("example.cst")
        >>> app.create_brick(0, 10, 0, 10, 0, 2, "substrate")
        >>> app.set_frequency_range(1, 10)
        >>> app.create_waveguide_port(1)
        >>> app.run()
        >>> app.close()

    也支持使用旧版函数名:
        >>> app.square(0, 10, 0, 10, 0, 2, "substrate")  # 同 create_brick
    """

    def __init__(self, filename=None):
        """
        初始化 CST 交互环境并打开指定 CST 工程文件

        :param filename: str 可选, CST 工程文件路径
            如果为 None，则仅初始化设计环境但不打开具体工程
        :raises FileNotFoundError: 指定的工程文件不存在
        :raises RuntimeError: 打开工程失败
        """
        self.t = 0
        # 初始化 CST 交互式设计环境
        self.project = cst.interface.DesignEnvironment()

        if filename is not None:
            self._open_and_activate(filename)

    def _open_and_activate(self, filename):
        """
        打开并激活 CST 工程文件的内部方法

        :param filename: str, 工程文件路径
        """
        try:
            filename_abs = os.path.abspath(filename)
        except Exception:
            filename_abs = filename

        if not os.path.exists(filename_abs):
            raise FileNotFoundError(
                f"CST project file not found: {filename_abs}")

        try:
            self.cst_file = self.project.open_project(filename_abs)
            self.cst_file.activate()
        except Exception as e:
            raise RuntimeError(
                f"Failed to open the CST project '{filename_abs}'. "
                f"Underlying error: {e!s}.\n"
                f"Possible causes: file is not a valid .cst project, "
                f"CST automation not available, or permissions/encoding issues."
            )

    def open(self, filename):
        """
        打开 CST 工程文件（便捷方法）

        :param filename: str, 工程文件路径
        """
        self._open_and_activate(filename)

    def __enter__(self):
        """支持 with 语句上下文管理"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出时自动关闭工程"""
        self.close()
