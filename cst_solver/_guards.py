# -*- coding: utf-8 -*-
"""
cst_solver 运行时守卫层
=======================
把「读文档才知道」的约束变成「写错就提示」。

背景
----
本库的覆盖度不低（23 个 Mixin），但**约束全是文档约定**：布尔语义、面编号、
参数重建、save/close 顺序……全都写在 ``docs/ARCHITECTURE.md`` §6 里，靠人记住。
阶段 4 暴露的 8 处缺陷里有 6 处属于这一类（「从未被真实调用过」）。

本模块把这些约定固化成**可执行检查**，每个问题给出错误三件套：

============  ==========================================================
``code``      稳定的机器可读编号（脚本可按它分流）
``message``   人话说明「发生了什么、为什么危险」
``next_action`` 明确告诉使用者「下一步该调哪个函数」
============  ==========================================================

设计边界（**不要照搬第三方 CLI 的那一套**）
------------------------------------------
``cst-runtime-cli`` 的同类模块带 ``session_type`` 状态机、disk marker、
设计环境进程管理 —— 那些是为**CLI 的进程生命周期**设计的。
本库是**长驻 ``setup`` 对象**，因此这里只搬三样东西：

1. 陷阱目录；2. 严重度分级；3. 错误三件套（code / message / next_action）。

状态按**宿主对象**隔离（``get_guard_state(app)``），不设全局单例，
所以不同 ``setup`` 实例互不干扰，也不会在模块 import 时就去碰 CST。

三种模式
--------
========  ================================================================
``off``   完全不检查。**行为与引入本模块之前逐字节一致**（回归基线）
``warn``  **默认**。全部转成 warning，只提示不阻断
``strict`` ``severity='error'`` 的项直接抛 ``CstGuardError``，硬拦截
========  ================================================================

可用 ``cst_solver.set_guard_mode('strict')`` 全局切换，或在 ``config.py`` 里
写 ``CST_GUARD_MODE = 'strict'``；也可对单个实例 ``get_guard_state(app).set_mode(...)``。

陷阱目录
--------
== ====================================== ==============================================
编号 陷阱                                  处置
== ====================================== ==============================================
T2  改参后未重建模型就直接仿真            🔴 硬拦截 + ``next_action``（``check_before_run``）
T3  结果导出后 ``save(include_results=True)`` 有损坏工程的风险  🟡 警告，建议 ``include_results=False``
T8  把 ``Abs(E)``（``'efield'``）当增益证据 🔴 ``require_gain=True`` 时白名单拦截
T10 ``project_path`` 后缀非法              🔴 校验 ``.cst`` / ``.prj``
T13 只改参数表不重建（与 T2 同根因）      🟡 在 ``para()`` 调用点就警告
T15 ``save`` 与 ``close`` 顺序颠倒         🔴 ``close()`` 之后再 ``save()`` 直接报错
T7' ``log_flag=0`` 不重建历史，被误当已生效 🟡 与 T13 同一条检查（本项目特有，对方没有）
== ====================================== ==============================================

@author: PC
"""

import warnings
import weakref

__all__ = [
    'CstGuardError',
    'GuardFinding',
    'GuardState',
    'GUARD_MODES',
    'DEFAULT_GUARD_MODE',
    'SEVERITY_ERROR',
    'SEVERITY_WARNING',
    'SEVERITY_INFO',
    'FARFIELD_GAIN_MODES',
    'FARFIELD_KNOWN_MODES',
    'PROJECT_SUFFIXES',
    'get_guard_state',
    'reset_guard_state',
    'get_guard_mode',
    'set_guard_mode',
    'assert_gain_mode',
]


# ============================================================
# 常量
# ============================================================

GUARD_MODES = ('off', 'warn', 'strict')
DEFAULT_GUARD_MODE = 'warn'

SEVERITY_ERROR = 'error'
SEVERITY_WARNING = 'warning'
SEVERITY_INFO = 'info'

_SEVERITY_ORDER = (SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_ERROR)

#: 可以**当作增益证据**引用的远场显示模式（T8）。
#: ``'efield'`` 明确**不在**其中 —— 那是 ``Abs(E)``，量纲与增益无关。
FARFIELD_GAIN_MODES = ('realized gain', 'gain', 'directivity')

#: ``FarfieldPlot.SetPlotMode()`` 接受的模式（用于拦截拼写错误）。
FARFIELD_KNOWN_MODES = FARFIELD_GAIN_MODES + (
    'efield', 'hfield', 'power', 'power density',
    'e-field', 'h-field', 'abs(e)', 'abs(h)',
)

#: CST 工程文件合法后缀（T10）。
PROJECT_SUFFIXES = ('.cst', '.prj')


# ============================================================
# 错误三件套
# ============================================================

class GuardFinding:
    """
    一条守卫发现（错误三件套）。

    :param code: str, 稳定机器编号，如 ``'PARAM_NOT_REBUILT'``
    :param severity: str, ``'error'`` / ``'warning'`` / ``'info'``
    :param message: str, 人话说明「发生了什么、为什么危险」
    :param next_action: str, 明确告诉使用者下一步该调哪个函数
    :param plan_id: str, 对应实施计划里的编号（T2 / T3 / …），便于溯源
    """

    __slots__ = ('code', 'severity', 'message', 'next_action', 'plan_id', 'context')

    def __init__(self, code, severity, message, next_action, plan_id='', context=None):
        if severity not in _SEVERITY_ORDER:
            raise ValueError(
                f"severity 必须是 {_SEVERITY_ORDER} 之一，收到 '{severity}'")
        self.code = code
        self.severity = severity
        self.message = message
        self.next_action = next_action
        self.plan_id = plan_id
        self.context = dict(context or {})

    def as_dict(self):
        """转成纯数据字典（便于落盘/进报告）。"""
        return {
            'code': self.code,
            'severity': self.severity,
            'message': self.message,
            'next_action': self.next_action,
            'plan_id': self.plan_id,
            'context': dict(self.context),
        }

    def format(self):
        """人类可读的一行式说明。"""
        head = f"[{self.code}]"
        if self.plan_id:
            head += f"（计划 {self.plan_id}）"
        return (f"{head} {self.message}\n"
                f"    → 下一步：{self.next_action}")

    def downgraded(self):
        """把 ``error`` 降级为 ``warning``（``mode='warn'`` 时用）。"""
        if self.severity != SEVERITY_ERROR:
            return self
        out = GuardFinding(self.code, SEVERITY_WARNING, self.message,
                           self.next_action, self.plan_id, self.context)
        return out

    def __repr__(self):
        return f"GuardFinding({self.code!r}, {self.severity!r}, plan={self.plan_id!r})"


class CstGuardError(RuntimeError):
    """
    守卫在 ``mode='strict'`` 下拦截时抛出的异常。

    带错误三件套，便于调用方分流处理：

    ::

        try:
            app.run()
        except CstGuardError as e:
            print(e.finding.code, '->', e.finding.next_action)
    """

    def __init__(self, finding):
        self.finding = finding
        super().__init__(finding.format())


# ============================================================
# 陷阱目录（工厂函数）
# ============================================================

def _f_param_not_rebuilt(names):
    return GuardFinding(
        'PARAM_NOT_REBUILT', SEVERITY_ERROR,
        f"参数 {names} 在几何已存在后被修改，但工程历史没有重建 —— "
        f"此时 run() 会仿真**旧几何**，结果看起来正常却是错的。",
        "先调用 app.update()（等价于 full_history_rebuild() 重放历史），"
        "或改写 app.para(..., log_flag=1) 让参数立即生效，然后再 run()。",
        plan_id='T2', context={'parameters': list(names)})


def _f_log_flag_no_rebuild(names):
    return GuardFinding(
        'LOG_FLAG_NO_REBUILD', SEVERITY_WARNING,
        f"app.para({names}, ..., log_flag=0) 只把参数写进参数表，"
        f"**不会**重建工程历史 —— 已建好的几何不会随参数变化。",
        "若希望几何立即更新：传 log_flag=1，或随后调用 app.update()。"
        "只是登记参数（几何尚未建）时 log_flag=0 是正常用法，本提示可忽略。",
        plan_id="T7'/T13", context={'parameters': list(names)})


def _f_save_after_close():
    return GuardFinding(
        'SAVE_AFTER_CLOSE', SEVERITY_ERROR,
        "工程（或设计环境）已经 close()，此时 save() 什么都不会写出。",
        "把顺序改成「先 save() 再 close()」；如果工程已关闭，需要重新打开再保存。",
        plan_id='T15')


def _f_double_close():
    return GuardFinding(
        'DOUBLE_CLOSE', SEVERITY_WARNING,
        "该工程/设计环境已经关闭过，重复 close() 不会再有作用。",
        "检查是否在 with 语句块内又手动调了一次 close()。",
        plan_id='T15')


def _f_unsaved_before_close():
    return GuardFinding(
        'UNSAVED_BEFORE_CLOSE', SEVERITY_WARNING,
        "close() 前有未保存的改动（几何已构建/参数已修改，但之后没有 save()）。",
        "如需保留这次建模结果，请先 save()（远场/结果导出过的话建议 "
        "include_results=False），再 close()。",
        plan_id='T15')


def _f_save_after_result_export():
    return GuardFinding(
        'SAVE_AFTER_RESULT_EXPORT', SEVERITY_WARNING,
        "刚刚导出过远场/2D-3D 结果，随后 save(include_results=True) 有把工程写坏的风险。",
        "建议 save(include_results=False) 只存模型；需要结果就先另存副本再导出。",
        plan_id='T3')


def _f_project_path_bad_suffix(path, suffix):
    return GuardFinding(
        'PROJECT_PATH_BAD_SUFFIX', SEVERITY_ERROR,
        f"工程路径后缀 '{suffix}' 不是 CST 工程文件（收到 {path!r}）。",
        f"请传入以 {PROJECT_SUFFIXES} 结尾的路径；"
        f"三维电磁工程用 '.cst'，Basis/PS 类工程用 '.prj'。",
        plan_id='T10', context={'path': str(path), 'suffix': str(suffix)})


def _f_project_path_invalid(path):
    return GuardFinding(
        'PROJECT_PATH_INVALID', SEVERITY_ERROR,
        f"工程路径为空或类型非法（收到 {path!r}）。",
        "请传入非空字符串路径，例如 r'D:\\work\\wg_AB.cst'。",
        plan_id='T10', context={'path': repr(path)})


def _f_farfield_mode_unknown(mode, where):
    return GuardFinding(
        'FARFIELD_MODE_UNKNOWN', SEVERITY_ERROR,
        f"{where} 收到未知的远场显示模式 {mode!r}；"
        f"CST 的 SetPlotMode 不会给出清晰报错，容易静默画出一张看起来正常的图。",
        f"改用已知模式之一：{FARFIELD_KNOWN_MODES}。"
        f"若要用作增益证据，只能用 {FARFIELD_GAIN_MODES}。",
        plan_id='T8', context={'mode': str(mode), 'where': where})


def _f_farfield_mode_not_gain(mode, where):
    return GuardFinding(
        'FARFIELD_MODE_NOT_GAIN', SEVERITY_ERROR,
        f"{where} 被要求提供增益证据，但 mode={mode!r} 是场量/功率量（如 'efield' "
        f"就是 Abs(E)），**不能**当作增益使用。",
        f"把 mode 改成 {FARFIELD_GAIN_MODES} 之一；"
        f"确实只想看场分布时，不要传 require_gain=True。",
        plan_id='T8', context={'mode': str(mode), 'where': where})


# ============================================================
# 状态
# ============================================================

class GuardState:
    """
    单个宿主对象（通常是 ``cst_solver.setup`` 实例）的守卫状态。

    状态**始终**被记录（即使 mode='off'），因为记录本身不产生任何 CST 调用、
    不产生任何输出；只有 ``_emit()`` 才受 mode 影响。
    这样「先 mode='off' 跑再切 'warn'」得到的判断才是准的。
    """

    def __init__(self, mode=None):
        self._mode = None
        if mode is not None:
            self.set_mode(mode)

        # --- 参数/几何 ---
        self.has_geometry = False     # 是否已经建过几何
        self.param_dirty = False      # 参数改过但历史未重建（T2/T13/T7'）
        self.param_names = ()         # 最近一次改动的参数名

        # --- 生命周期 ---
        self.saved = True             # 是否已保存
        self.closed = False           # 是否已经 close()

        # --- 结果导出 ---
        self.result_exported = False  # 是否导出过远场/2D-3D 结果（T3）
        self.export_kinds = ()

        # --- 证据 ---
        self.findings = []

        # --- 几何存在性探针（由宿主注入，见 attach_geometry_probe） ---
        self._geometry_probe = None
        # --- 参数是否已存在探针（由宿主注入，见 attach_param_probe） ---
        self._param_probe = None
        #: 本守卫见过被写入过的参数名。用于区分「**首次定义**」与「**改已存在的值**」——
        #: 只有后者才可能让**已建好的几何**变旧（见 mark_params_changed 的说明）。
        self.known_params = set()

    # ---------------- 参数存在性 ----------------

    def attach_param_probe(self, probe):
        """
        注入「这个参数在工程里已经存在吗」的探针。

        为什么需要它：``geometry_exists()`` 只能说明**有几何**，不能说明
        **这些几何引用了这个参数**。CST 没有公开 API 能查「某参数被哪些历史条目引用」，
        所以只能用一个更弱但足够准的判据 —— **首次写入的参数名不可能被已有几何引用**
        （库的约定就是「先定义参数，再用它建几何」）。

        对**打开已有工程**的情况，首次写入也可能是改一个早已存在的参数
        （比如改参考工程的 ``x1``），所以这里再问 CST 一句
        ``GetParameter(name)`` 兜底。

        :param probe: callable, 收一个参数名，返回 bool（该参数当前是否已存在）
        :return: self
        """
        self._param_probe = probe
        return self

    def param_existed(self, name):
        """
        判断某个参数在**本次写入之前**是否已经存在于工程里。

        :param name: str, 参数名
        :return: bool, True 表示改它可能让已有几何变旧
        """
        if name in self.known_params:
            return True
        if self._param_probe is None or self.effective_mode() == 'off':
            return False
        try:
            return bool(self._param_probe(name))
        except Exception:
            # 查不出来时按「新参数」处理：宁可漏报，也不要在建模流水线里误报
            # （漏报的那一半由 run() 前的检查和 validate_model() 的 Rebuild 兜住）
            return False

    # ---------------- 几何存在性 ----------------

    def attach_geometry_probe(self, probe):
        """
        注入「工程里现在有没有几何」的探针。

        ``cst_solver`` 里几何是通过 ``add_to_history()`` 建的，调用点分散在十几个
        Mixin 中，逐个埋点既侵入又容易漏。改为让守卫在**需要时**主动问 CST 一句
        ``Solid.GetNumberOfShapes()``（官方公开 API，见 VBA 参考「Solid.GetNumberOfShapes」）。

        注意：探针**只在非 off 模式且尚未确定**时才会被调用，
        因此 ``mode='off'`` 不会因此产生任何额外 CST 调用。

        :param probe: callable, 无参，返回 bool（工程里是否有几何）
        :return: self
        """
        self._geometry_probe = probe
        return self

    def geometry_exists(self):
        """
        工程里是否已经有几何。

        先看显式标记（``mark_geometry_built()``），没有标记时才走探针。
        探针抛异常时按「未知」处理（返回 False），绝不因为守卫本身把主流程打断。
        """
        if self.has_geometry:
            return True
        if self._geometry_probe is None or self.effective_mode() == 'off':
            return False
        try:
            exists = bool(self._geometry_probe())
        except Exception:
            return False
        if exists:
            self.has_geometry = True
        return exists

    # ---------------- 模式 ----------------

    def effective_mode(self):
        """本状态实际生效的模式（未单独设置时取全局）。"""
        return self._mode if self._mode is not None else _global_mode()

    @property
    def mode(self):
        """本状态实际生效的模式。"""
        return self.effective_mode()

    def set_mode(self, mode):
        """
        设置本对象的守卫模式。

        :param mode: str, 'off' / 'warn' / 'strict'
        :return: self
        :raises ValueError: mode 不在 GUARD_MODES 中
        """
        if mode is not None and mode not in GUARD_MODES:
            raise ValueError(f"守卫模式必须是 {GUARD_MODES} 之一，收到 '{mode}'")
        self._mode = mode
        return self

    # ---------------- 记录与汇报 ----------------

    def record(self, finding):
        """登记一条发现（不阻断）。"""
        self.findings.append(finding)
        return finding

    def get_findings(self, min_severity=None):
        """
        取出已登记的发现。

        :param min_severity: str 可选, 只返回不低于该严重度的项
        :return: list[GuardFinding]
        """
        if min_severity is None:
            return list(self.findings)
        floor = _SEVERITY_ORDER.index(min_severity)
        return [f for f in self.findings
                if _SEVERITY_ORDER.index(f.severity) >= floor]

    def clear_findings(self):
        """清空已登记的发现。"""
        self.findings = []

    def summary(self):
        """按严重度统计的摘要字典。"""
        out = {s: 0 for s in _SEVERITY_ORDER}
        for f in self.findings:
            out[f.severity] += 1
        return out

    # ---------------- 陷阱检查（供宿主调用） ----------------

    def mark_params_changed(self, names=None, rebuilt=False, preexisting=None):
        """
        参数被修改（T13 / T7'）。

        只把「**改一个已存在的参数**」判成脏：首次写入的参数名不可能被已有几何引用
        （库的约定是「先定义参数，再用它建几何」，例如 ``build_feed()`` 会在
        几何已存在时才补写 ``tx1``/``ty1``，但它们只被**之后**建的矩形使用，
        并不会让任何已有几何变旧）。这条判据是阶段 5 实测模板时补上的，
        原计划「几何已存在就判脏」会误报。

        :param names: 参数名列表
        :param rebuilt: True 表示这次修改**已经**重建了历史（``log_flag=1``）
        :param preexisting: list[bool] 可选, 每个名字在写入前是否已存在；
            不传则用 ``param_existed()`` 逐个判断
        :return: 登记的 GuardFinding，未触发返回 None
        """
        names = list(names or ())
        if preexisting is None:
            preexisting = [n in self.known_params for n in names]
        preexisting = list(preexisting)

        self.known_params.update(names)
        self.param_names = tuple(names)

        if rebuilt:
            self.param_dirty = False
            return None

        touched = [n for n, pre in zip(names, preexisting) if pre]
        if not touched:
            return None                 # 全是首次定义 → 现有几何不可能引用它
        if not self.geometry_exists():
            return None                 # 还没有几何 → 无所谓脏不脏

        self.param_dirty = True
        self.saved = False
        return _emit(self, _f_log_flag_no_rebuild(touched))

    def mark_geometry_built(self):
        """几何已构建（history 已写入）—— 参数与几何此刻是一致的。"""
        self.has_geometry = True
        self.param_dirty = False
        self.saved = False

    def mark_rebuilt(self):
        """工程历史已重建（``update()`` / ``log_flag=1``）—— 脏标记清除。"""
        self.param_dirty = False

    def mark_saved(self):
        """工程已保存。"""
        self.saved = True

    def mark_opened(self):
        """
        工程（重新）打开或新建 —— 生命周期重新开始。

        关掉一个工程再打开/新建另一个时，旧的「已关闭」「未保存」状态不该继续生效。
        """
        self.closed = False
        self.saved = True
        self.result_exported = False
        self.export_kinds = ()

    def mark_closed(self):
        """工程/设计环境已关闭。"""
        self.closed = True

    def mark_result_exported(self, kind='result'):
        """导出过远场/2D-3D 结果（T3）。"""
        self.result_exported = True
        self.export_kinds = tuple(set(self.export_kinds) | {str(kind)})

    # ---------------- 检查点 ----------------

    def check_before_run(self):
        """
        T2：仿真前的硬检查。

        :return: None
        :raises CstGuardError: ``mode='strict'`` 且参数改了但历史未重建
        """
        if self.param_dirty:
            return _emit(self, _f_param_not_rebuilt(self.param_names))
        return None

    def check_before_save(self, include_results=True):
        """
        T15 / T3：保存前检查。

        :param include_results: 本次 save 是否连结果一起存
        :raises CstGuardError: ``mode='strict'`` 且工程已关闭（保存不会生效）
        """
        if self.closed:
            return _emit(self, _f_save_after_close())
        if self.result_exported and include_results:
            return _emit(self, _f_save_after_result_export())
        return None

    def check_before_close(self):
        """
        T15：关闭前检查。

        :raises CstGuardError: ``mode='strict'`` 且重复关闭
        """
        if self.closed:
            return _emit(self, _f_double_close())
        if not self.saved:
            return _emit(self, _f_unsaved_before_close())
        return None

    def check_project_path(self, path):
        """
        T10：工程路径后缀校验。

        :param path: str, 待检查路径
        :raises CstGuardError: ``mode='strict'`` 且后缀非法
        """
        import os
        if not path or not isinstance(path, str):
            return _emit(self, _f_project_path_invalid(path))
        suffix = os.path.splitext(path)[1].lower()
        if suffix not in PROJECT_SUFFIXES:
            return _emit(self, _f_project_path_bad_suffix(path, suffix))
        return None

    def check_farfield_mode(self, mode, require_gain=False, where='远场绘图'):
        """
        T8：远场显示模式校验。

        :param mode: str, ``SetPlotMode`` 的模式名
        :param require_gain: True 表示这个数值要**当增益证据**用
        :param where: str, 报错时标注的调用位置
        :return: bool, 通过返回 True
        :raises CstGuardError: ``mode='strict'`` 且模式未知 / 不是增益量
        """
        text = str(mode).strip().lower()
        if text not in FARFIELD_KNOWN_MODES:
            _emit(self, _f_farfield_mode_unknown(mode, where))
            return False
        if require_gain and text not in FARFIELD_GAIN_MODES:
            _emit(self, _f_farfield_mode_not_gain(mode, where))
            return False
        return True

    def __repr__(self):
        return (f"GuardState(mode={self.effective_mode()!r}, "
                f"geometry={self.has_geometry}, param_dirty={self.param_dirty}, "
                f"saved={self.saved}, closed={self.closed}, "
                f"findings={len(self.findings)})")


# ============================================================
# 全局模式
# ============================================================

_global_mode_value = DEFAULT_GUARD_MODE


def _global_mode():
    """当前全局守卫模式。"""
    return _global_mode_value


def get_guard_mode():
    """返回当前全局守卫模式。"""
    return _global_mode_value


def set_guard_mode(mode):
    """
    设置全局守卫模式。

    :param mode: str, 'off' / 'warn' / 'strict'
    :return: str, 设置前的旧模式
    :raises ValueError: mode 非法
    """
    global _global_mode_value
    if mode not in GUARD_MODES:
        raise ValueError(f"守卫模式必须是 {GUARD_MODES} 之一，收到 '{mode}'")
    old = _global_mode_value
    _global_mode_value = mode
    return old


# ============================================================
# 宿主对象 -> 状态
# ============================================================

_STATE_ATTR = '_cst_guard_state'
_fallback_states = weakref.WeakKeyDictionary()


def get_guard_state(owner):
    """
    取得（必要时创建）某个宿主对象的守卫状态。

    宿主通常是 ``cst_solver.setup`` 实例；传入 ``None`` 时返回一个临时状态
    （无 CST 环境也能正常调用守卫 API，只是不跨调用保留）。

    :param owner: 任意对象，通常是 setup 实例；可为 None
    :return: GuardState
    """
    if owner is None:
        return GuardState()

    existing = getattr(owner, _STATE_ATTR, None)
    if isinstance(existing, GuardState):
        return existing

    state = GuardState()
    try:
        setattr(owner, _STATE_ATTR, state)
        return state
    except Exception:
        pass
    # 宿主用了 __slots__ 之类的限制 —— 退回弱引用表
    try:
        state = _fallback_states.get(owner)
        if state is None:
            state = GuardState()
            _fallback_states[owner] = state
        return state
    except TypeError:
        # 连弱引用都不支持（如内建类型）—— 退化为一次性状态
        return GuardState()


def reset_guard_state(owner):
    """
    丢弃某个宿主对象的守卫状态，下次 ``get_guard_state()`` 重新建。

    主要给测试用，让用例之间互不污染。

    :param owner: 宿主对象
    :return: None
    """
    if owner is None:
        return
    try:
        if isinstance(getattr(owner, _STATE_ATTR, None), GuardState):
            delattr(owner, _STATE_ATTR)
    except Exception:
        pass
    try:
        _fallback_states.pop(owner, None)
    except TypeError:
        pass


# ============================================================
# 内部：按模式汇报
# ============================================================

def _emit(state, finding):
    """
    按当前模式汇报一条发现。

    - ``mode='off'``：**什么都不做**（不登记、不 warning、不抛异常）
      —— 这是「与改动前逐字节一致」的实现方式
    - ``mode='warn'``：error 降级为 warning 后 warning 出去
    - ``mode='strict'``：error 抛 ``CstGuardError``，warning 照常 warning

    :return: 实际登记/抛出的那条 GuardFinding（off 模式返回 None）
    """
    if state.effective_mode() == 'off':
        return None

    if state.effective_mode() == 'warn':
        finding = finding.downgraded()

    state.record(finding)

    if finding.severity == SEVERITY_ERROR:
        raise CstGuardError(finding)
    if finding.severity == SEVERITY_WARNING:
        warnings.warn(finding.format(), UserWarning, stacklevel=3)
    return finding


def assert_gain_mode(mode):
    """
    断言某个远场模式可以**当作增益证据**使用（T8）。

    给下游脚本（报告引擎、验收脚本）用：拿到一个模式名就确认它是不是增益量，
    避免把 ``Abs(E)`` 写进增益结论。

    :param mode: str, 远场显示模式
    :return: bool, 合法返回 True
    :raises ValueError: 不是增益量
    """
    if str(mode).strip().lower() not in FARFIELD_GAIN_MODES:
        raise ValueError(
            f"'{mode}' 不是增益量，不能作为增益证据；"
            f"可用的是 {FARFIELD_GAIN_MODES}")
    return True
