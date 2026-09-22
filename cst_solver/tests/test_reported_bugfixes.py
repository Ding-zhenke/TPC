# -*- coding: utf-8 -*-
"""
用户报告缺陷的回归测试（2026-10）
=================================
一个文件守住**用户真机报上来的 5 个缺陷**，每个缺陷一条（或几条）用例。
这些用例的价值在于：它们会在**离线**环境下失败于旧实现 —— 不依赖真机 CST。

被守住的 5 个缺陷
-----------------
1. ``get_parameter()`` 是坏的
   旧实现调 ``model3d.GetParameter(name)`` —— **CST 没有这个方法**。
   ``Model3D`` 的动态派发（``__getattr__``）让写错的名字既不报 AttributeError、
   也过不了静态检查，直到真机才炸。官方 API 是
   ``DoesParameterExist`` / ``RestoreDoubleParameter`` / ``RestoreParameter``
   （见 ``docs/references/vba-official-reference.md`` 的 Parameter 一节）。
2. ``set_background()`` 下发 ``.Material``
   CST 的 Background **没有材料属性**（只有 ``Type`` / ``Epsilon`` / ``Mu``），
   该行在真机上是**被静默忽略**的 —— 调用方以为设好了背景材料，其实没有。
3. ``add_port()`` 写死 ``.PortOnBound "True"``
   该行声明「端口面落在计算域边界平面上」；端口在域**内部**时它是错的。
4. ``save()`` 不传路径是**静默 no-op**
   真机 ``Project.save()`` 无参什么都不会写出，没有任何报错与 warning，
   紧接着 ``close()`` 会把整场建模丢掉。
5. 路径校验三处入口三种写法（``exists`` / ``isfile`` / 完全不检查）
   现在统一走 :func:`cst_solver._guards.require_project_file`，并且
   「不是文件」与「不存在」给**不同**的异常与能指明原因的信息。

运行方式::

    pytest cst_solver/tests/test_reported_bugfixes.py -v
"""

import os
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from cst_solver._guards import (get_guard_mode, require_project_file,
                                set_guard_mode)
from cst_solver.parameters import ParametersMixin
from cst_solver.project import ProjectMixin
from cst_solver.simulation.boundary import BoundaryMixin
from cst_solver.simulation.ports import PortMixin


# ============================================================
# 假 CST 对象（只实现真实存在的官方 API）
# ============================================================

class _FakeModel3D:
    """只提供**官方存在**的参数接口；``GetParameter`` 故意不提供。"""

    def __init__(self):
        self.calls = []
        self.params = {}

    def add_to_history(self, label, vba):
        self.calls.append((label, vba))

    def DoesParameterExist(self, name):
        return name in self.params

    def RestoreParameter(self, name):
        if name not in self.params:
            raise RuntimeError(f"Parameter '{name}' does not exist")
        return str(self.params[name])

    def RestoreDoubleParameter(self, name):
        if name not in self.params:
            raise RuntimeError(f"Parameter '{name}' does not exist")
        return float(self.params[name])


class _FakeProject:
    def __init__(self, cst_file):
        self._cst_file = cst_file
        self.opened = []

    def open_project(self, filename):
        self.opened.append(filename)
        return self._cst_file

    def close(self):
        pass


class _FakeCstFile:
    def __init__(self, path='D:/fake/project.cst'):
        self.model3d = _FakeModel3D()
        self.saved = []
        self.closed = False
        self._path = path

    def filename(self):
        return self._path

    def save(self, *args, **kwargs):
        self.saved.append((args, kwargs))

    def close(self):
        self.closed = True

    def activate(self):
        pass


class _Host(BoundaryMixin, PortMixin, ParametersMixin, ProjectMixin):
    """按真实 ``setup`` 的 Mixin 方式拼出来的假宿主。"""

    def __init__(self, path='D:/fake/project.cst'):
        self.cst_file = _FakeCstFile(path)
        self.project = _FakeProject(self.cst_file)


@pytest.fixture
def host():
    """守卫层静音（本文件只验证缺陷本身，不验证守卫），结束后恢复全局模式。"""
    old = get_guard_mode()
    set_guard_mode('off')
    try:
        yield _Host()
    finally:
        set_guard_mode(old)


def _last_call(host):
    """返回最近一次下发给 CST 的 (历史标签, VBA)。"""
    return host.cst_file.model3d.calls[-1]


# ============================================================
# 缺陷 5：统一的路径校验入口
# ============================================================

def test_path_not_found_raises_filenotfounderror(tmp_path):
    missing = tmp_path / 'nope.cst'
    with pytest.raises(FileNotFoundError) as ei:
        require_project_file(str(missing))
    msg = str(ei.value)
    assert '不存在' in msg
    assert os.path.abspath(str(missing)) in msg


def test_directory_raises_isadirectoryerror(tmp_path):
    """目录给的是**不一样**的异常 —— 这正是「报错信息要改进」的要求。"""
    with pytest.raises(IsADirectoryError) as ei:
        require_project_file(str(tmp_path))
    assert '是一个目录' in str(ei.value)


def test_empty_path_raises_valueerror():
    with pytest.raises(ValueError):
        require_project_file('   ')


def test_non_pathlike_raises_typeerror():
    with pytest.raises(TypeError) as ei:
        require_project_file(123)
    assert 'int' in str(ei.value)


def test_pathlike_is_accepted_and_absolutised(tmp_path):
    real = tmp_path / 'ok.cst'
    real.write_text('', encoding='utf-8')
    assert require_project_file(real) == os.path.abspath(str(real))


def test_project_open_checks_path_before_touching_cst(host, tmp_path):
    """缺陷 5 的现场：``project_open`` 原先**不检查存在性**。"""
    with pytest.raises(FileNotFoundError):
        host.project_open(str(tmp_path / 'missing.cst'))
    assert host.project.opened == [], "路径不合法就不该去调 CST 的 open_project"


def test_project_open_accepts_pathlike(host, tmp_path):
    real = tmp_path / 'ok.cst'
    real.write_text('', encoding='utf-8')
    host.project_open(real)                      # 不再被后缀守卫误判
    assert host.project.opened == [os.path.abspath(str(real))]


# ============================================================
# 缺陷 1：get_parameter
# ============================================================

def test_get_parameter_uses_official_api(host):
    """数值参数 ⇒ float，且全程不碰 ``GetParameter``（假对象里根本没有它）。"""
    host.cst_file.model3d.params['w'] = 0.44
    value = host.get_parameter('w')
    assert isinstance(value, float)
    assert value == pytest.approx(0.44)


def test_get_parameter_returns_expression_text(host):
    """非数值（表达式）参数 ⇒ 退回 ``RestoreParameter`` 拿字符串。"""
    m3 = host.cst_file.model3d
    m3.params['a'] = '2*w'

    def _not_a_double(name):
        raise RuntimeError('not a double parameter')

    m3.RestoreDoubleParameter = _not_a_double
    assert host.get_parameter('a') == '2*w'


def test_get_parameter_missing_raises_keyerror(host):
    """不存在的参数 ⇒ KeyError，且提示怎么定义它（旧实现会返回空串或炸得莫名其妙）。"""
    with pytest.raises(KeyError) as ei:
        host.get_parameter('not_defined')
    assert 'app.para' in str(ei.value)


def test_get_parameter_is_graceful_when_interface_is_missing(host):
    """CST 会话什么读取接口都没暴露 ⇒ 报 KeyError，而不是 AttributeError。"""

    class _Bare:
        def add_to_history(self, label, vba):
            pass

    host.cst_file.model3d = _Bare()
    with pytest.raises(KeyError):
        host.get_parameter('w')


# ============================================================
# 缺陷 2：set_background
# ============================================================

def test_background_never_emits_material(host):
    """核心断言：**不再**下发 ``.Material``（该命令在本版本 CST 上无效）。"""
    host.set_background()
    label, vba = _last_call(host)
    assert label == 'Set Background'
    assert '.Material' not in vba
    assert '.Type "normal"' in vba
    assert '.Epsilon "1.0"' in vba
    assert '.Mu "1.0"' in vba


def test_pec_background_has_no_epsilon_mu(host):
    host.set_background(material='PEC')
    _, vba = _last_call(host)
    assert '.Type "pec"' in vba
    assert '.Epsilon' not in vba


def test_unknown_material_raises_instead_of_silently_becoming_vacuum(host):
    with pytest.raises(ValueError) as ei:
        host.set_background(material='Silicon')
    assert 'epsilon' in str(ei.value)


def test_unknown_material_with_explicit_epsilon_warns_but_works(host):
    with pytest.warns(UserWarning):
        host.set_background(material='Silicon', epsilon=11.9, mu=1.0)
    _, vba = _last_call(host)
    assert '.Epsilon "11.9"' in vba


def test_invalid_background_type_raises(host):
    """``PMC`` / ``Open`` 都不是 ``Background.Type`` 的合法取值。"""
    with pytest.raises(ValueError):
        host.set_background(background_type='PMC')


def test_background_spaces_are_emitted(host):
    host.set_background(xmin_space=5, zmax_space=10,
                        apply_in_all_directions=True)
    _, vba = _last_call(host)
    assert '.XminSpace "5"' in vba
    assert '.ZmaxSpace "10"' in vba
    assert '.ApplyInAllDirections "True"' in vba


# ============================================================
# 缺陷 3：端口是否落在计算域边界
# ============================================================

def test_port_on_bound_defaults_to_true(host):
    """默认仍是 ``True``（保持既有模型的 VBA 逐字节不变）。"""
    host.add_port(1, orientation='xmin')
    _, vba = _last_call(host)
    assert '.PortOnBound "True"' in vba
    assert '.ClipPickedPortToBound "False"' in vba


def test_port_on_bound_can_be_disabled(host):
    host.add_port(1, orientation='xmin', port_on_bound=False)
    _, vba = _last_call(host)
    assert '.PortOnBound "False"' in vba


def test_clip_picked_port_to_bound_is_effective(host):
    host.add_port(1, orientation='xmin', clip_picked_port_to_bound=True)
    _, vba = _last_call(host)
    assert '.ClipPickedPortToBound "True"' in vba


def test_free_port_on_bound_can_be_disabled(host):
    """域内部（``Coordinates "Free"``）的端口必须能关掉 ``PortOnBound``。"""
    host.create_waveguide_port_free(1, xrange=('0', 'a'), orientation='xmin',
                                    port_on_bound=False)
    _, vba = _last_call(host)
    assert '.Coordinates "Free"' in vba
    assert '.PortOnBound "False"' in vba


# ============================================================
# 缺陷 4：无参 save 的静默 no-op
# ============================================================

def test_save_without_filename_targets_the_current_project_file(host):
    target = host.save()
    assert target == os.path.abspath('D:/fake/project.cst')
    args, kwargs = host.cst_file.saved[-1]
    assert args == (target,), "必须把显式路径交给 CST，而不能调无参 save()"
    assert kwargs['allow_overwrite'] is True


def test_save_without_filename_forwards_include_results(host):
    host.save(include_results=False)
    args, kwargs = host.cst_file.saved[-1]
    assert kwargs['include_results'] is False


def test_save_without_filename_needs_a_project_path():
    """刚 ``new_project()`` 还没落盘 ⇒ 明确报错，而不是静默丢弃整场建模。"""
    h = _Host(path='')
    with pytest.raises(RuntimeError) as ei:
        h.save()
    assert '文件名' in str(ei.value) or '路径' in str(ei.value)


def test_save_without_filename_reports_broken_filename_api():
    h = _Host()

    def _boom():
        raise RuntimeError('no filename')

    h.cst_file.filename = _boom
    with pytest.raises(RuntimeError) as ei:
        h.save()
    assert 'app.save(path)' in str(ei.value)


def test_save_to_a_directory_raises_isadirectoryerror(host, tmp_path):
    with pytest.raises(IsADirectoryError):
        host.save(str(tmp_path))
    assert host.cst_file.saved == [], "报错时不该已经写过盘"


def test_save_with_explicit_path_returns_that_path(host, tmp_path):
    out = host.save(str(tmp_path / 'wg_AB.cst'))
    assert out == os.path.abspath(str(tmp_path / 'wg_AB.cst'))
    args, kwargs = host.cst_file.saved[-1]
    assert args == (out,)
