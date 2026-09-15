# -*- coding: utf-8 -*-
"""
cst_solver 守卫层与结构化验收单元测试
=====================================
对应实施计划 `docs/next_plan/stages/05_阶段5_库加固与借鉴落地.md` 的 5.1 / 5.2。

运行方式::

    pytest cst_solver/tests/test_guards.py -v
    或直接  python cst_solver/tests/test_guards.py

为什么用「假 CST 对象」而不是真 CST
-----------------------------------
这些用例要验证的是**守卫有没有接对线、判断得对不对**，与 CST 本身无关。
用假对象可以让每条陷阱都能被**确定性地**构造出来（真 CST 里造一次
「参数改了但历史没重建」要开工程、跑历史，慢且不可重复）。

⚠️ 因此本文件**不能**替代「拿真 CST 跑一遍」：真 CST 的 `Solid.GetNumberOfShapes()`、
`Rebuild()`、`get_messages()` 行为仍需实测确认（已登记在 stages/05 的未验证风险里）。

@author: PC
"""

import os
import sys
import warnings

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

# cst_solver 的 __init__ 会把 CST 的 python_cst_libraries 加进 sys.path 并 import cst。
# 没有装 CST 的机器上这套用例无法运行 —— 明确跳过并说明原因，不伪装成通过。
try:
    from cst_solver._guards import (
        CstGuardError,
        GuardFinding,
        GuardState,
        DEFAULT_GUARD_MODE,
        FARFIELD_GAIN_MODES,
        assert_gain_mode,
        get_guard_mode,
        get_guard_state,
        reset_guard_state,
        set_guard_mode,
    )
    from cst_solver.parameters import ParametersMixin
    from cst_solver.project import ProjectMixin
    from cst_solver.simulation.solver import SolverMixin
    from cst_solver.postprocessing.plot import PlotMixin
    from cst_solver.postprocessing.result_export import ExportMixin
    from cst_solver.validation import ValidationMixin
except Exception as _exc:                      # pragma: no cover - 环境相关
    pytest.skip(f"需要可导入的 cst_solver（含 CST python 库）：{_exc!r}",
                allow_module_level=True)


# ============================================================
# 假 CST 对象
# ============================================================

class _FakeSolid:
    """假的 ``model3d.Solid``，只实现守卫用到的 GetNumberOfShapes()。"""

    def __init__(self, model):
        self._model = model

    def GetNumberOfShapes(self):
        self._model.calls.append(('GetNumberOfShapes',))
        return len(self._model.solids)


class _FakeModel3D:
    """假的 ``model3d``：记录所有下发过的调用，供断言检查。"""

    def __init__(self):
        self.params = {}
        self.calls = []
        self.rebuilds = 0
        self.runs = 0
        self.messages = []
        self.solids = []
        self.farfield_modes = []
        self.Solid = _FakeSolid(self)

    # --- 参数 ---
    def StoreParameter(self, name, value):
        self.calls.append(('StoreParameter', name))
        self.params[name] = value

    def GetParameter(self, name):
        # 与真 CST 保持一致的语义：不存在的参数读不到（这里返回空串）
        return self.params.get(name, '')

    def StoreParameters(self, names, values):
        self.calls.append(('StoreParameters', tuple(names)))
        self.params.update(dict(zip(names, values)))

    def SetParameterDescription(self, name, description):
        self.calls.append(('SetParameterDescription', name))

    def add_to_history(self, label, vba):
        self.calls.append(('add_to_history', label))

    def SelectTreeItem(self, path):
        self.calls.append(('SelectTreeItem', path))

    def full_history_rebuild(self):
        self.rebuilds += 1
        self.calls.append(('full_history_rebuild',))

    def Rebuild(self):
        self.rebuilds += 1
        self.calls.append(('Rebuild',))

    # --- 求解 ---
    def run_solver(self):
        self.runs += 1
        self.calls.append(('run_solver',))

    # --- 后处理 ---
    @property
    def FarfieldPlot(self):
        return _FakeFarfieldPlot(self)

    @property
    def ASCIIExport(self):
        return _FakeAsciiExport(self)


class _FakeFarfieldPlot:
    def __init__(self, model):
        self._model = model

    def Reset(self):
        pass

    def Plottype(self, t):
        pass

    def SetPlotMode(self, mode):
        self._model.farfield_modes.append(mode)

    def Frequency(self, f):
        pass

    def ThetaStart(self, v):
        pass

    def ThetaStop(self, v):
        pass

    def ThetaStep(self, v):
        pass

    def Plot(self):
        pass


class _FakeAsciiExport:
    def __init__(self, model):
        self._model = model

    def Reset(self):
        pass

    def FileName(self, p):
        pass

    def Mode(self, m):
        pass

    def Step(self, s):
        pass

    def Execute(self):
        self._model.calls.append(('ASCIIExport.Execute',))


class _FakeProject:
    def __init__(self):
        self.closed = False

    def open_project(self, filename):
        return None

    def close(self):
        self.closed = True


class _FakeCstFile:
    def __init__(self):
        self.model3d = _FakeModel3D()
        self.saved = []
        self.closed = False

    def get_messages(self):
        out = list(self.model3d.messages)
        self.model3d.messages = []
        return out

    def save(self, *args, **kwargs):
        self.saved.append((args, kwargs))

    def close(self):
        self.closed = True

    def activate(self):
        pass


class FakeApp(ProjectMixin, ParametersMixin, SolverMixin, PlotMixin,
              ExportMixin, ValidationMixin):
    """按真实 ``setup`` 相同的 Mixin 组合拼出来的假宿主。"""

    def __init__(self, mode=None):
        self.cst_file = _FakeCstFile()
        self.project = _FakeProject()
        if mode is not None:
            get_guard_state(self).set_mode(mode)


@pytest.fixture(autouse=True)
def _restore_global_mode():
    """用例若改了全局模式，结束后恢复，避免互相污染。"""
    old = get_guard_mode()
    yield
    set_guard_mode(old)


@pytest.fixture
def app():
    """默认模式的假宿主。"""
    return FakeApp()


def _catch(fn, *args, **kwargs):
    """执行并返回 (结果, 捕获到的 warning 列表, 异常对象或 None)。"""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        try:
            result = fn(*args, **kwargs)
            exc = None
        except Exception as e:      # noqa: BLE001 - 测试就是要抓它
            result, exc = None, e
    return result, [str(w.message) for w in caught], exc


def _quiet(fn, *args, **kwargs):
    """执行但丢弃 warning（用于只关心中间状态、不关心提示的用例）。"""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return fn(*args, **kwargs)


# ============================================================
# 1. 回归基线：mode='off' 必须与改动前一致
# ============================================================

def test_default_mode_is_warn():
    assert DEFAULT_GUARD_MODE == 'warn'


def test_off_mode_is_inert(app):
    """mode='off' 下：不报警、不拦截、不登记，CST 调用序列与改动前一致。"""
    app.cst_file.model3d.solids.append('wg1')          # 已有几何
    get_guard_state(app).set_mode('off')

    _, warns, exc = _catch(app.para, 'w', 14)          # 改参不重建
    assert warns == [] and exc is None

    _, warns, exc = _catch(app.run)                    # 直接仿真
    assert warns == [] and exc is None
    assert app.cst_file.model3d.runs == 1

    _, warns, exc = _catch(app.close)
    assert warns == [] and exc is None

    _, warns, exc = _catch(app.save)                   # close 之后再 save
    assert warns == [] and exc is None

    assert get_guard_state(app).get_findings() == []


def test_off_mode_does_not_probe_cst(app):
    """mode='off' 时不许多问 CST 一句 —— 这是「逐字节一致」的一部分。"""
    get_guard_state(app).set_mode('off')
    app.para('w', 14)
    probed = [c for c in app.cst_file.model3d.calls
              if c[0] == 'GetNumberOfShapes']
    assert probed == []


# ============================================================
# 2. T2 / T13 / T7'：参数改了但历史没重建
# ============================================================

def test_param_change_after_geometry_warns_then_blocks(app):
    """定义了参数 → 建了几何 → 改这个参数（log_flag=0）→ warn 报警；strict 硬拦截。"""
    _quiet(app.para, 'w', 14)                          # 1) 先定义参数
    app.cst_file.model3d.solids.append('wg1')          # 2) 再建几何

    # --- warn 模式：para() 当场给一条 LOG_FLAG_NO_REBUILD（T13 / T7'）---
    _, warns, exc = _catch(app.para, 'w', 15)          # 3) 改已存在的参数
    assert exc is None
    assert len(warns) == 1 and 'LOG_FLAG_NO_REBUILD' in warns[0]

    # --- warn 模式：run() 给 PARAM_NOT_REBUILT，但**不阻断** ---
    _, warns, exc = _catch(app.run)
    assert exc is None
    assert len(warns) == 1 and 'PARAM_NOT_REBUILT' in warns[0]
    assert app.cst_file.model3d.runs == 1

    # --- strict 模式：run() 直接抛 ---
    get_guard_state(app).set_mode('strict')
    _, warns, exc = _catch(app.run)
    assert isinstance(exc, CstGuardError)
    assert exc.finding.code == 'PARAM_NOT_REBUILT'
    assert exc.finding.plan_id == 'T2'
    assert 'update()' in exc.finding.next_action
    assert app.cst_file.model3d.runs == 1          # 第二次没有真的下发


def test_new_parameter_after_geometry_is_clean(app):
    """
    **阶段 5 实测模板时发现的误报源**：几何已存在，但写入的是一个**全新参数**。

    真实例子是 ``topo_modeler/builders/feed.py`` 的优化块 —— 它在几何已建好之后才
    ``app.para('tx1', 0.2)``，而 ``tx1`` 只被**紧接着**创建的那个矩形引用，
    不会让任何已有几何变旧。守卫必须区分「首次定义」与「改已存在的值」。
    """
    app.cst_file.model3d.solids.append('epc')          # 几何已存在

    _, warns, exc = _catch(app.para, 'tx1', 0.2)       # 却是全新参数
    assert warns == [] and exc is None

    _, warns, exc = _catch(app.run)
    assert warns == [] and exc is None
    assert app.cst_file.model3d.runs == 1


def test_param_before_geometry_is_clean(app):
    """模板的常规用法：参数在建几何之前设置 → 不该报警。"""
    _, warns, exc = _catch(app.para, 'a', 0.2425)
    assert warns == [] and exc is None

    get_guard_state(app).mark_geometry_built()      # 建模流水线走完

    _, warns, exc = _catch(app.run)
    assert warns == [] and exc is None
    assert app.cst_file.model3d.runs == 1


def test_existing_param_in_opened_project_is_dirty(app):
    """
    **打开已有工程**的场景：本次会话里第一次写某个参数，但它早就存在。

    这是 T2 最真实的用法（复制一份参考工程 → 改 ``x1`` → 直接跑）。
    只靠「本会话见过没有」会漏报，所以还要问 CST 一句 ``GetParameter()``。
    """
    app.cst_file.model3d.solids.append('some_solid')   # 工程本来就有几何
    app.cst_file.model3d.params['x1'] = 18             # 而且本来就有 x1

    _, warns, exc = _catch(app.para, 'x1', 20)         # 本会话第一次写它
    assert exc is None
    assert len(warns) == 1 and 'LOG_FLAG_NO_REBUILD' in warns[0]
    assert get_guard_state(app).param_dirty


def test_off_mode_does_not_probe_params(app):
    """mode='off' 时连参数存在性也不许问 CST。"""
    app.cst_file.model3d.solids.append('s')
    app.cst_file.model3d.params['w'] = 14
    get_guard_state(app).set_mode('off')
    app.para('w', 15)
    assert [c for c in app.cst_file.model3d.calls
            if c[0] in ('GetNumberOfShapes',)] == []
    assert not get_guard_state(app).param_dirty


def test_update_clears_dirty(app):
    """改参 → update() 重建历史 → run() 应放行（这正是守卫教的正确用法）。"""
    _quiet(app.para, 'w', 14)
    app.cst_file.model3d.solids.append('wg1')
    _quiet(app.para, 'w', 15)
    assert get_guard_state(app).param_dirty

    _quiet(app.update)
    assert app.cst_file.model3d.rebuilds == 1
    assert not get_guard_state(app).param_dirty

    _, warns, exc = _catch(app.run)
    assert warns == [] and exc is None


def test_log_flag_1_does_not_dirty(app):
    """log_flag=1 表示立即重建历史 → 不进入脏状态，也不再提示。"""
    _quiet(app.para, 'w', 14)
    app.cst_file.model3d.solids.append('wg1')
    _, warns, exc = _catch(app.para, 'w', 15, 1)
    assert warns == [] and exc is None
    assert app.cst_file.model3d.rebuilds == 1
    assert not get_guard_state(app).param_dirty


def test_paras_batch_marks_dirty(app):
    """批量接口 paras() 走同一套判断。"""
    _quiet(app.paras, {'a': 1, 'w': 14}, None)         # 先定义
    app.cst_file.model3d.solids.append('wg1')          # 再建几何
    _, warns, exc = _catch(app.paras, {'a': 1, 'w': 15}, None)
    assert exc is None
    assert len(warns) == 1 and 'LOG_FLAG_NO_REBUILD' in warns[0]
    assert get_guard_state(app).param_dirty


def test_geometry_probe_uses_solid_getnumbershapes(app):
    """没显式标记时，守卫靠 Solid.GetNumberOfShapes() 判断有没有几何。"""
    get_guard_state(app).set_mode('strict')

    # 工程是空的 → 改参不算脏 → run 放行
    _, _, exc = _catch(app.para, 'w', 14)
    assert exc is None
    _, _, exc = _catch(app.run)
    assert exc is None

    # 建了几何之后**再改同一个参数** → 拦住
    app.cst_file.model3d.solids.append('wg1')
    _, _, exc = _catch(app.para, 'w', 15)
    assert exc is None                                   # para 本身是 warning 级
    _, _, exc = _catch(app.run)
    assert isinstance(exc, CstGuardError)


# ============================================================
# 3. T15：save / close 顺序
# ============================================================

def test_save_after_close_blocks(app):
    app.close()
    get_guard_state(app).set_mode('strict')
    _, _, exc = _catch(app.save)
    assert isinstance(exc, CstGuardError)
    assert exc.finding.code == 'SAVE_AFTER_CLOSE'
    assert '先 save() 再 close()' in exc.finding.next_action


def test_unsaved_before_close_warns(app):
    """建了几何但没保存就 close() → 提醒可能丢结果。"""
    get_guard_state(app).mark_geometry_built()
    _, warns, exc = _catch(app.close)
    assert exc is None
    assert len(warns) == 1 and 'UNSAVED_BEFORE_CLOSE' in warns[0]


def test_save_then_close_is_clean(app):
    get_guard_state(app).mark_geometry_built()
    _, warns, exc = _catch(app.save)
    assert warns == [] and exc is None
    _, warns, exc = _catch(app.close)
    assert warns == [] and exc is None
    assert app.cst_file.closed and app.project.closed


def test_double_close_warns(app):
    app.close()
    _, warns, exc = _catch(app.close)
    assert exc is None
    assert len(warns) == 1 and 'DOUBLE_CLOSE' in warns[0]


# ============================================================
# 4. T10：工程路径后缀
# ============================================================

@pytest.mark.parametrize('bad', ['D:/x/myproject', 'D:/x/a.txt', 'D:/x/a.cst.bak'])
def test_project_path_bad_suffix_is_blocked(app, bad):
    get_guard_state(app).set_mode('strict')
    _, _, exc = _catch(get_guard_state(app).check_project_path, bad)
    assert isinstance(exc, CstGuardError)
    assert exc.finding.code == 'PROJECT_PATH_BAD_SUFFIX'


@pytest.mark.parametrize('good', ['D:/x/a.cst', 'D:/x/a.prj', 'D:/x/A.CST'])
def test_project_path_good_suffix_passes(app, good):
    get_guard_state(app).set_mode('strict')
    _, _, exc = _catch(get_guard_state(app).check_project_path, good)
    assert exc is None


def test_project_path_empty_is_blocked(app):
    get_guard_state(app).set_mode('strict')
    _, _, exc = _catch(get_guard_state(app).check_project_path, '')
    assert isinstance(exc, CstGuardError)
    assert exc.finding.code == 'PROJECT_PATH_INVALID'


# ============================================================
# 5. T8：远场模式白名单
# ============================================================

def test_farfield_unknown_mode_is_blocked(app):
    get_guard_state(app).set_mode('strict')
    _, _, exc = _catch(app.farfield_plot_polar, None, 'gaim')
    assert isinstance(exc, CstGuardError)
    assert exc.finding.code == 'FARFIELD_MODE_UNKNOWN'
    # 没通过校验就不该把非法模式发给 CST
    assert app.cst_file.model3d.farfield_modes == []


def test_farfield_efield_allowed_but_not_as_gain(app):
    """'efield' 合法（画场分布），但 require_gain=True 时必须被拦住。"""
    get_guard_state(app).set_mode('warn')
    _, warns, exc = _catch(app.farfield_plot_polar, None, 'efield')
    assert exc is None and warns == []
    assert app.cst_file.model3d.farfield_modes == ['efield']

    get_guard_state(app).set_mode('strict')
    _, _, exc = _catch(app.farfield_plot_polar, None, 'efield', require_gain=True)
    assert isinstance(exc, CstGuardError)
    assert exc.finding.code == 'FARFIELD_MODE_NOT_GAIN'


@pytest.mark.parametrize('mode', FARFIELD_GAIN_MODES)
def test_farfield_gain_modes_pass(app, mode):
    get_guard_state(app).set_mode('strict')
    _, _, exc = _catch(app.farfield_plot_polar, None, mode, 0, 360, 1, True)
    assert exc is None


def test_assert_gain_mode_helper():
    assert assert_gain_mode('Realized Gain') is True
    with pytest.raises(ValueError):
        assert_gain_mode('efield')


# ============================================================
# 6. T3：结果导出后再 save
# ============================================================

def test_save_after_result_export_warns(app):
    app.export_result_2d3d('2D/3D Results\\Farfields\\farfield (f=310)', 'x.txt')
    _, warns, exc = _catch(app.save, None, True)
    assert exc is None
    assert len(warns) == 1 and 'SAVE_AFTER_RESULT_EXPORT' in warns[0]

    # include_results=False 时不提示
    app2 = FakeApp()
    app2.export_result_2d3d('2D/3D Results\\Farfields\\f', 'x.txt')
    _, warns, exc = _catch(app2.save, None, False)
    assert warns == [] and exc is None


# ============================================================
# 7. 验收 API：validate_model
# ============================================================

def test_validate_model_success(app):
    out = app.validate_model()
    assert out['status'] == 'success'
    assert out['messages'] == []
    assert out['rebuild_ok'] is True


def test_validate_model_reports_messages(app):
    """调用前积压了消息 → status=error；但 Rebuild 本身干净 ⇒ rebuild_ok 仍为 True。"""
    app.cst_file.model3d.messages = ['(&H8000ffff) The specified material does not exist']
    out = app.validate_model()
    assert out['status'] == 'error'
    assert len(out['before']) == 1
    assert out['rebuild_ok'] is True
    assert len(out['messages']) == 1


def test_validate_model_rebuild_messages(app):
    """调用前干净，但 Rebuild() 阶段报错 → 也算 error。"""
    app.cst_file.model3d.messages = []
    original = app.cst_file.model3d.Rebuild

    def noisy_rebuild():
        original()
        app.cst_file.model3d.messages = ['Rebuild 阶段的历史错误']

    app.cst_file.model3d.Rebuild = noisy_rebuild
    out = app.validate_model()
    assert out['status'] == 'error'
    assert out['rebuild_ok'] is False


def test_validate_model_skips_rebuild_when_asked(app):
    out = app.validate_model(rebuild=False)
    assert out['status'] == 'success'
    assert out['rebuild_ok'] is True
    assert app.cst_file.model3d.rebuilds == 0


def test_validate_model_clears_dirty_after_rebuild(app):
    _quiet(app.para, 'w', 14)
    app.cst_file.model3d.solids.append('wg1')
    _quiet(app.para, 'w', 15)
    assert get_guard_state(app).param_dirty
    _quiet(app.validate_model)
    assert not get_guard_state(app).param_dirty


# ============================================================
# 8. 错误三件套与状态隔离
# ============================================================

def test_finding_carries_error_triple(app):
    _quiet(app.para, 'w', 14)
    app.cst_file.model3d.solids.append('wg1')
    _quiet(app.para, 'w', 15)
    get_guard_state(app).set_mode('strict')
    _, _, exc = _catch(app.run)
    d = exc.finding.as_dict()
    for key in ('code', 'message', 'next_action'):
        assert d[key], f'错误三件套缺 {key}'
    assert d['plan_id'] == 'T2'


def test_finding_severity_validation():
    with pytest.raises(ValueError):
        GuardFinding('X', 'fatal', 'm', 'n')


def test_states_are_isolated_per_host():
    a, b = FakeApp(), FakeApp()
    _quiet(a.para, 'w', 14)
    a.cst_file.model3d.solids.append('wg1')
    _quiet(a.para, 'w', 15)
    assert get_guard_state(a).param_dirty
    assert not get_guard_state(b).param_dirty


def test_reset_guard_state():
    a = FakeApp()
    _quiet(a.para, 'w', 14)
    a.cst_file.model3d.solids.append('wg1')
    _quiet(a.para, 'w', 15)
    assert get_guard_state(a).param_dirty
    reset_guard_state(a)
    assert not get_guard_state(a).param_dirty


def test_guard_state_survives_unsettable_host():
    """宿主既不能挂属性、也不能弱引用（__slots__=()）时，守卫不能崩。"""
    class Slotted:
        __slots__ = ()

    obj = Slotted()
    assert isinstance(get_guard_state(obj), GuardState)


def test_guard_state_shared_for_weakrefable_slots_host():
    """支持弱引用时，同一个宿主必须拿到同一个状态对象。"""
    class Slotted:
        __slots__ = ('__weakref__',)

    obj = Slotted()
    st1 = get_guard_state(obj)
    st2 = get_guard_state(obj)
    assert st1 is st2
    st1.mark_geometry_built()
    assert get_guard_state(obj).has_geometry


def test_get_guard_state_none_is_usable():
    st = get_guard_state(None)
    assert isinstance(st, GuardState)
    st.mark_params_changed(['a'])
    assert st.get_findings() == []


def test_set_guard_mode_validates():
    with pytest.raises(ValueError):
        set_guard_mode('loud')


# ============================================================
# 9. 直接跑（不装 pytest 也能用）
# ============================================================

if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
