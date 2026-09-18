import pytest

from cst_solver.vba_specs import MonitorSpec, PortSpec, validate_vba_specs


def test_offline_specs_validate_without_solver():
    result = validate_vba_specs(
        ports=[PortSpec("floquet", number=1, orientation="positive")],
        monitors=[MonitorSpec("time1d", frequencies=[10.0])],
    )
    assert result == {"ok": True, "ports": 1, "monitors": 1,
                     "solver_started": False}


def test_unknown_kinds_and_duplicate_ports_are_rejected():
    with pytest.raises(ValueError, match="unsupported port kind"):
        PortSpec("unknown", number=1).validate()
    with pytest.raises(ValueError, match="unique"):
        validate_vba_specs(ports=[
            PortSpec("waveguide", number=1, orientation="positive"),
            PortSpec("waveguide", number=1, orientation="negative"),
        ])


def test_probe_requires_three_coordinates():
    with pytest.raises(ValueError, match="three coordinates"):
        MonitorSpec("probe", position=(0, 1)).validate()
