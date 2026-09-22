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

import os
import logging

from cst_solver.vba_specs import MonitorSpec, PortSpec, validate_vba_specs

from cst_solver.environment import (
    CSTPaths, CSTConfigurationError, CSTUnavailableError,
    discover_cst_installations, get_cst_paths, diagnose_environment,
    describe_interface_abi, interpreter_abi_tag,
    _load_cst_module, _read_config,
)

# ============================================================
# 加载配置快照；实际操作使用 environment 的统一解析与按需加载。
# ============================================================
# 保留历史常量；无配置时不再假定某个开发者的安装目录。
# 配置错误延迟到实际操作，确保诊断入口仍然可导入。
try:
    _cfg, _, _ = _read_config(os.environ)
    _paths = get_cst_paths()
except CSTConfigurationError:
    _cfg = {}
    _paths = CSTPaths(None, None, None, 'configuration_error')
CST_INSTALL_PATH = _paths.install_path
CST_PYTHON_LIB = _paths.python_lib
CST_MATERIAL_LIB = _paths.material_lib

# ============================================================
# 运行时守卫层：模式可在 config.py 里用 CST_GUARD_MODE 覆盖
# （'off' 完全不检查 = 引入守卫层之前的行为；'warn' 默认；'strict' 硬拦截）
# ============================================================
from cst_solver._guards import (  # noqa: E402
    CstGuardError,
    GuardFinding,
    GuardState,
    GUARD_MODES,
    DEFAULT_GUARD_MODE,
    FARFIELD_GAIN_MODES,
    FARFIELD_KNOWN_MODES,
    PROJECT_SUFFIXES,
    assert_gain_mode,
    get_guard_mode,
    get_guard_state,
    reset_guard_state,
    require_project_file,
    set_guard_mode,
)

_guard_mode_cfg = os.environ.get('CST_GUARD_MODE') or _cfg.get("CST_GUARD_MODE")
if _guard_mode_cfg:
    if _guard_mode_cfg in GUARD_MODES:
        set_guard_mode(_guard_mode_cfg)
    else:
        logging.getLogger(__name__).warning(
            "CST_GUARD_MODE=%r 非法，可选 %s；已回退到 %s",
            _guard_mode_cfg, GUARD_MODES, DEFAULT_GUARD_MODE)

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
from cst_solver.modeling.wcs import WCSMixin
from cst_solver.postprocessing.proc import PostProcMixin
from cst_solver.postprocessing.farfield import FarfieldMixin
from cst_solver.postprocessing.plot import PlotMixin
from cst_solver.postprocessing.result_export import ExportMixin
from cst_solver.validation import ValidationMixin

# ============================================================
# 导入结果类
# 注意：Python 导入机制优先返回子模块，因此 `from cst_solver import result`
# 得到的是模块而非类。如需类，请用:
#   from cst_solver.result import result
# 或使用旧兼容层:
#   from cst_solver import setup, result   # 通过 cst_solver.py 兼容层
# ============================================================
from cst_solver._result_core import result as _result_class
from cst_solver._result_core import Result
# 导出 result 类到包顶层（子模块重命名为 _result_core 避免冲突）
result = _result_class  # 现在 from cst_solver import result 得到的是类

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
    WCSMixin,
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
    PlotMixin,
    ExportMixin,
    ValidationMixin,
):
    """
    CST 电磁仿真自动化操作核心类
    ==============================
    通过多继承聚合所有功能模块，包括:
        - 项目操作: 打开/关闭/保存
        - 参数管理: 参数/表达式/频率范围
        - 基本体建模: 长方体/圆柱/球/圆锥/圆环/椭圆柱/三角形/六边形/导线
        - 曲线绘制: 多边形/圆弧/圆/椭圆/直线/样条/矩形
        - 曲线操作: 拉伸/放样/扫掠/混合/倒角/覆盖/修剪
        - 布尔运算: 相加/相减/相交/插入/压印/倒角
        - 变换: 平移/旋转/镜像/缩放/对齐
        - 工作坐标系: 旋转/平移/对齐/保存/恢复/缩放
        - 选取: 棱边/端点/表面/顶点
        - 面操作: 表面拉伸/旋转/走线
        - 材料与组件: 材料创建/组件管理
        - 端口: 波导端口/离散端口/集总元件/Floquet端口/电缆端口
        - 激励源: 平面波/电流源/线圈/磁体/远场源/时域信号
        - 监视器: 场监视器/探针
        - 边界条件: 边界/背景/对称面/层叠
        - 求解器: 时域/频域/本征模/积分方程/渐近/参数扫描/优化
        - 网格: 网格属性/自适应/区域控制
        - 导入导出: SAT/DXF/STEP/IGES/STL
        - 绘图控制: 1D/2D/3D/标量/矢量/远场极坐标/动画
        - 后处理: 远场/Q因子/SAR/结果组合/结果导出

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

        :param filename: str 或 os.PathLike 可选, CST 工程文件路径
            如果为 None，则仅初始化设计环境但不打开具体工程
        :raises FileNotFoundError: 指定的工程文件不存在
        :raises IsADirectoryError: 给的是目录（CST 工程是单个 .cst/.prj 文件）
        :raises TypeError: 路径既不是 str 也不是 os.PathLike
        :raises RuntimeError: 打开工程失败
        """
        self.t = 0
        self.cst_file = None
        self._environment_closed = False
        # 本实例自己创建了 DE（非 attach），close() 时负责释放它。
        self._attached = False
        # 路径错误在创建 DE 之前暴露，避免打开工程失败留下空窗口。
        # 校验统一走 _guards.require_project_file（与 open()/project_open() 同一入口），
        # 报错会分清「不存在」与「是目录不是文件」。
        if filename is not None:
            filename = require_project_file(filename)
            get_guard_state(self).check_project_path(filename)
        self.project = _load_cst_module('cst.interface').DesignEnvironment()
        try:
            if filename is not None:
                self._open_and_activate(filename)
        except BaseException:
            try:
                self.project.close()
                self._environment_closed = True
            except Exception:
                logging.getLogger(__name__).exception('打开工程失败后的 CST 会话清理失败')
            raise

    @classmethod
    def attach(cls, pid=None, filename=None):
        """Attach 到一个**已在运行**的 CST DE 会话（不新建实例）。

        背景：许可证不足时 ``setup()`` 新建 DE 会报 ``EXITCODE_NOLICENSE``；
        attach 到已持有许可证的现有会话即可复用其许可证（2026-09 真机验证）。

        :param pid: int 或 'host:port' 可选，指定 DE；缺省用 ``connect_to_any()``
            连到任意一个正在运行的 DE。
        :param filename: str 或 os.PathLike 可选，attach 后打开指定工程；
            缺省则绑定当前活动工程（若 DE 未打开任何工程，``cst_file`` 为 None，
            之后可调用 ``.open(path)``）。
        :return: setup 实例
        :raises RuntimeError: 没有可 attach 的 DE

        .. note::
            attach 实例**不拥有**该会话：之后调用 :meth:`close`/
            :meth:`close_project` 只会解除 Python 侧引用，
            **不会**关闭借用的工程或 DE（保护用户自己开着的 CST）。
        """
        obj = cls.__new__(cls)
        obj.t = 0
        obj.cst_file = None
        obj._environment_closed = False
        # 标记本实例只借用（attach）了用户的 DE：close() 时**绝不**
        # 关闭该设计环境，只解除引用（见 project.py close() 的防护）。
        obj._attached = True
        interface = _load_cst_module('cst.interface')
        try:
            if pid is None:
                obj.project = interface.DesignEnvironment.connect_to_any()
            else:
                obj.project = interface.DesignEnvironment.connect(pid)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"无法 attach 到运行中的 CST DE（pid={pid!r}）：{e!s}。"
                f"请确认 CST DESIGN ENVIRONMENT 已启动。") from e
        # 绑定当前活动工程（可能没有，None 时交给后续 .open()）
        try:
            obj.cst_file = obj.project.active_project()
            get_guard_state(obj).mark_opened()
        except Exception:  # noqa: BLE001
            obj.cst_file = None
        if filename is not None:
            obj._open_and_activate(filename)
        return obj

    def _open_and_activate(self, filename):
        """
        打开并激活 CST 工程文件的内部方法

        2026-09-23：路径校验统一到 :func:`cst_solver._guards.require_project_file`
        —— 原先这里用的是 ``os.path.exists``（目录也能过），而 ``setup.__init__``
        用的是 ``os.path.isfile``、``project_open`` 干脆不检查，同一个错误写法
        在三条入口上表现不同。现在三处一致：不存在 ⇒ ``FileNotFoundError``，
        是目录 ⇒ ``IsADirectoryError``。

        :param filename: str 或 os.PathLike, 工程文件路径
        """
        filename_abs = require_project_file(filename)

        # 陷阱 T10：后缀校验（strict 模式下后缀非法直接抛 CstGuardError）
        get_guard_state(self).check_project_path(filename_abs)

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
        get_guard_state(self).mark_opened()

    def open(self, filename):
        """
        打开 CST 工程文件（便捷方法）

        :param filename: str 或 os.PathLike, 工程文件路径（必须已存在且是文件）
        :raises FileNotFoundError: 路径不存在
        :raises IsADirectoryError: 路径是目录，不是 .cst/.prj 文件
        :raises TypeError: 路径既不是 str 也不是 os.PathLike
        """
        self._open_and_activate(filename)

    def __enter__(self):
        """支持 with 语句上下文管理"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出时自动关闭工程"""
        if exc_type is None:
            self.close()
        else:
            try:
                self.close()
            except Exception:
                logging.getLogger(__name__).exception('CST 清理失败，保留原始操作异常')


# ============================================================
# 公开入口（P1：API 与发行一致性）
# ============================================================
#
# 在此之前本包**没有 __all__**：`from cst_solver import *` 会把 24 个内部
# Mixin 类也一并导出，公开面与实现细节混在一起，也没有任何地方可以核对。
# 这里显式声明「故意公开」的名字；Mixin 类仍然可以直接 import
# （`from cst_solver import MaterialMixin` 照旧可用），只是不再算公开面。
# 一致性由 `scripts/check_api_consistency.py` 的 public-surface 检查守住：
# __all__ 里的每个名字都必须真的能取到。
__all__ = [
    # 主要类
    'setup',
    'result',
    'Result',
    # 环境发现与诊断（离线可用，不启动 CST）
    'CSTPaths',
    'CSTConfigurationError',
    'CSTUnavailableError',
    'discover_cst_installations',
    'get_cst_paths',
    'diagnose_environment',
    'describe_interface_abi',
    'interpreter_abi_tag',
    'CST_INSTALL_PATH',
    'CST_PYTHON_LIB',
    'CST_MATERIAL_LIB',
    # 运行时守卫层
    'CstGuardError',
    'GuardFinding',
    'GuardState',
    'GUARD_MODES',
    'DEFAULT_GUARD_MODE',
    'FARFIELD_GAIN_MODES',
    'FARFIELD_KNOWN_MODES',
    'PROJECT_SUFFIXES',
    'assert_gain_mode',
    'get_guard_mode',
    'get_guard_state',
    'reset_guard_state',
    'require_project_file',
    'set_guard_mode',
    # 面操作（依赖 pick，与 setup 一起公开）
    'FaceOpsMixin',
    # CST VBA 对象的离线配置契约（不启动 CST）
    'PortSpec',
    'MonitorSpec',
    'validate_vba_specs',
]
