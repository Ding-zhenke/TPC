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
