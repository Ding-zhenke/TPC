# -*- coding: utf-8 -*-
"""仅用注入对象验证会话清理，不启动 CST。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import cst_solver
from cst_solver._guards import get_guard_state


@pytest.fixture
def backend(monkeypatch):
    project = Mock()
    design_env = Mock(return_value=project)
    monkeypatch.setattr(cst_solver, '_load_cst_module',
                        lambda name: SimpleNamespace(DesignEnvironment=design_env))
    return project, design_env


def test_invalid_path_does_not_start_cst(backend, tmp_path):
    _, create = backend
    with pytest.raises(FileNotFoundError):
        cst_solver.setup(tmp_path / 'missing.cst')
    create.assert_not_called()


def test_directory_path_does_not_start_cst(backend, tmp_path):
    """给目录要报 IsADirectoryError（不是含糊的「路径非法」），且同样不启动 CST。"""
    _, create = backend
    with pytest.raises(IsADirectoryError, match='是一个目录'):
        cst_solver.setup(tmp_path)
    create.assert_not_called()


def test_non_pathlike_filename_is_rejected(backend):
    _, create = backend
    with pytest.raises(TypeError):
        cst_solver.setup(123)
    create.assert_not_called()


def test_open_failure_closes_owned_environment(backend, tmp_path):
    project, _ = backend
    path = tmp_path / 'test.cst'
    path.touch()
    project.open_project.side_effect = RuntimeError('bad project')
    with pytest.raises(RuntimeError, match='bad project'):
        cst_solver.setup(path)
    project.close.assert_called_once()


def test_empty_environment_closes_without_project(backend):
    project, _ = backend
    with cst_solver.setup():
        pass
    project.close.assert_called_once()


def test_environment_closed_even_if_project_close_fails(backend):
    project, _ = backend
    app = cst_solver.setup()
    app.cst_file = Mock()
    app.cst_file.close.side_effect = RuntimeError('project close failure')
    with pytest.raises(RuntimeError, match='project close failure'):
        app.close()
    project.close.assert_called_once()


def test_project_close_then_environment_close_in_strict_mode(backend):
    project, _ = backend
    app = cst_solver.setup()
    app.cst_file = Mock()
    get_guard_state(app).set_mode('strict')
    app.close_project()
    app.close()
    app.cst_file.close.assert_called_once()
    project.close.assert_called_once()


def test_repeat_close_does_not_repeat_cst_calls(backend):
    project, _ = backend
    app = cst_solver.setup()
    get_guard_state(app).set_mode('off')
    app.close()
    app.close()
    project.close.assert_called_once()


def test_context_cleanup_keeps_original_error(backend):
    project, _ = backend
    project.close.side_effect = RuntimeError('cleanup failed')
    with pytest.raises(ValueError, match='original'):
        with cst_solver.setup():
            raise ValueError('original')


# ---------------------------------------------------------------
# attach：借用现有 DE，close() 绝不关闭用户的会话
# ---------------------------------------------------------------

@pytest.fixture
def attached(monkeypatch):
    project = Mock()          # 活动工程（用户自己的）
    de = Mock()               # 用户的 DesignEnvironment
    de.active_project.return_value = project
    design_env = SimpleNamespace(
        connect_to_any=Mock(return_value=de),
        connect=Mock(return_value=de))
    monkeypatch.setattr(cst_solver, '_load_cst_module',
                        lambda name: SimpleNamespace(DesignEnvironment=design_env))
    return project, de, design_env


def test_attach_connect_to_any_does_not_create(attached):
    project, de, design_env = attached
    app = cst_solver.setup.attach()
    design_env.connect_to_any.assert_called_once()
    assert app._attached is True
    assert app.cst_file is project


def test_attach_close_does_not_shut_down_user_session(attached):
    project, de, _ = attached
    app = cst_solver.setup.attach()
    app.close()                       # 经 __exit__ 同路径
    de.close.assert_not_called()      # 用户 DE 必须保留
    project.close.assert_not_called()


def test_attach_close_project_does_not_close_user_project(attached):
    project, de, _ = attached
    app = cst_solver.setup.attach()
    app.close_project()
    project.close.assert_not_called()
    de.close.assert_not_called()


def test_attach_with_specific_pid_calls_connect(attached):
    _, _, design_env = attached
    cst_solver.setup.attach(pid=36472)
    design_env.connect.assert_called_once_with(36472)


def test_attach_no_running_de_raises_runtime_error(monkeypatch):
    design_env = SimpleNamespace(
        connect_to_any=Mock(side_effect=RuntimeError('none')))
    monkeypatch.setattr(cst_solver, '_load_cst_module',
                        lambda name: SimpleNamespace(DesignEnvironment=design_env))
    with pytest.raises(RuntimeError, match='无法 attach'):
        cst_solver.setup.attach()
