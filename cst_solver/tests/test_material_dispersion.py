# -*- coding: utf-8 -*-
"""自定义材料色散模型的离线单元测试。"""

import pytest

from cst_solver.material.materials import MaterialMixin


class _FakeModel3D:
    def __init__(self):
        self.history = []

    def add_to_history(self, label, vba):
        self.history.append((str(label), str(vba)))


class _FakeCstFile:
    def __init__(self):
        self.model3d = _FakeModel3D()


class _App(MaterialMixin):
    def __init__(self):
        self.cst_file = _FakeCstFile()


def _create(**kwargs):
    app = _App()
    app.create_material_custom('dispersive', 1, 1, 0, **kwargs)
    return app.cst_file.model3d.history[-1][1]


def test_drude_electric_dispersion_emits_official_cst_coefficients():
    """防止 Drude 参数被漏写、错序或错误映射到磁性色散。"""
    vba = _create(
        dispersion_model_eps='Drude',
        eps_infinity=3.7,
        dispersion_coeffs_eps=('1.37e16', '4.05e13'),
    )

    assert '.DispModelEps "Drude"' in vba
    assert '.EpsInfinity "3.7"' in vba
    assert '.DispCoeff1Eps "1.37e16"' in vba
    assert '.DispCoeff2Eps "4.05e13"' in vba
    assert '.DispCoeff3Eps' not in vba
    assert vba.index('.DispModelEps') < vba.index('.Create')


def test_lorentz_magnetic_dispersion_uses_mu_commands():
    """防止磁性色散误用 Eps 命令或丢失 Lorentz 第三个系数。"""
    vba = _create(
        dispersion_model_mu='Lorentz',
        mu_infinity='mu_inf',
        dispersion_coeffs_mu=(2.5, 'f0', 'gamma'),
    )

    assert '.DispModelMu "Lorentz"' in vba
    assert '.MuInfinity "mu_inf"' in vba
    assert '.DispCoeff1Mu "2.5"' in vba
    assert '.DispCoeff2Mu "f0"' in vba
    assert '.DispCoeff3Mu "gamma"' in vba
    assert '.DispModelEps' not in vba


@pytest.mark.parametrize(
    ('model', 'coefficients'),
    [
        ('Debye1st', (2, 'tau')),
        ('Debye2nd', (2, 3, 'tau1', 'tau2')),
        ('General1st', ('alpha0', 'beta0')),
        ('General2nd', ('alpha0', 'alpha1', 'beta0', 'beta1')),
    ],
)
def test_supported_electric_models_accept_official_coefficient_counts(
        model, coefficients):
    """防止受支持的 CST 线性色散模型被错误拒绝。"""
    vba = _create(
        dispersion_model_eps=model,
        eps_infinity=1,
        dispersion_coeffs_eps=coefficients,
    )
    assert f'.DispModelEps "{model}"' in vba
    assert vba.count('DispCoeff') == len(coefficients)


@pytest.mark.parametrize(
    ('kwargs', 'message'),
    [
        ({'dispersion_model_eps': 'Unknown', 'eps_infinity': 1,
          'dispersion_coeffs_eps': (1, 2)}, '不支持'),
        ({'dispersion_model_eps': 'Drude',
          'dispersion_coeffs_eps': (1, 2)}, 'eps_infinity'),
        ({'dispersion_model_eps': 'Drude', 'eps_infinity': 1,
          'dispersion_coeffs_eps': (1,)}, '需要 2 个'),
        ({'eps_infinity': 1}, 'dispersion_model_eps'),
    ],
)
def test_invalid_dispersion_configuration_fails_before_history_write(
        kwargs, message):
    """防止不完整配置进入 CST 后才以消息或弹窗形式失败。"""
    app = _App()
    with pytest.raises(ValueError, match=message):
        app.create_material_custom('bad', 1, 1, 0, **kwargs)
    assert app.cst_file.model3d.history == []


def test_legacy_custom_material_does_not_emit_dispersion_commands():
    """防止新增可选参数改变既有非色散材料的 VBA。"""
    vba = _create()
    assert '.DispModel' not in vba
    assert '.EpsInfinity' not in vba
    assert '.MuInfinity' not in vba
    assert '.DispCoeff' not in vba
