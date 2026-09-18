"""Offline contracts for CST VBA-backed ports and monitors.

These dataclasses deliberately stop at validation.  Rendering a particular
CST command remains the responsibility of a version-specific adapter, so an
offline preflight can never imply that a solver or monitor was accepted by
CST.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


PORT_KINDS = frozenset({
    "waveguide", "discrete", "discrete_face", "floquet", "plane_wave",
    "field_source", "farfield_source", "cable",
})
MONITOR_KINDS = frozenset({
    "efield", "hfield", "farfield", "time", "time0d", "time1d",
    "time2d", "time3d", "voltage", "current", "particle", "pic",
    "probe",
})


def _required(value: Any, name: str) -> None:
    if value is None or value == "":
        raise ValueError(f"{name} is required")


@dataclass(frozen=True)
class PortSpec:
    """Version-neutral description of a CST port or excitation."""

    kind: str
    number: int | str | None = None
    orientation: str | None = None
    modes: int = 1
    polarization_angle: float | str | None = None
    reference_plane_distance: float | str | None = None
    shield: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> "PortSpec":
        if self.kind not in PORT_KINDS:
            raise ValueError(f"unsupported port kind: {self.kind}")
        if self.kind not in {"plane_wave", "field_source", "farfield_source"}:
            _required(self.number, "number")
        if self.modes < 1:
            raise ValueError("modes must be >= 1")
        if self.shield not in {None, "", "electric", "magnetic"}:
            raise ValueError("shield must be electric, magnetic, or empty")
        if self.kind in {"waveguide", "discrete", "discrete_face", "floquet", "cable"}:
            _required(self.orientation, "orientation")
        return self


@dataclass(frozen=True)
class MonitorSpec:
    """Version-neutral description of a CST monitor/probe."""

    kind: str
    frequencies: Sequence[float | str] = ()
    name: str | None = None
    position: Sequence[float | str] | None = None
    field_type: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> "MonitorSpec":
        if self.kind not in MONITOR_KINDS:
            raise ValueError(f"unsupported monitor kind: {self.kind}")
        if self.kind == "probe":
            if self.position is None or len(self.position) != 3:
                raise ValueError("probe position must contain three coordinates")
        elif not self.frequencies:
            raise ValueError(f"{self.kind} monitor requires frequencies")
        if self.field_type is not None and not self.field_type.strip():
            raise ValueError("field_type cannot be empty")
        return self


def validate_vba_specs(*, ports: Sequence[PortSpec] = (),
                       monitors: Sequence[MonitorSpec] = ()) -> dict[str, Any]:
    """Validate a complete offline port/monitor specification."""
    for item in ports:
        item.validate()
    for item in monitors:
        item.validate()
    numbers = [str(item.number) for item in ports if item.number is not None]
    if len(numbers) != len(set(numbers)):
        raise ValueError("port numbers must be unique")
    return {"ok": True, "ports": len(ports), "monitors": len(monitors),
            "solver_started": False}


__all__ = ["PORT_KINDS", "MONITOR_KINDS", "PortSpec", "MonitorSpec",
           "validate_vba_specs"]
