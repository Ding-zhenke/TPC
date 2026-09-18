# -*- coding: utf-8 -*-
"""
cst_solver.simulation — 类型存根文件
=====================================
为 simulation 下所有 Mixin 类提供类型提示，消除 Pylance 红色波浪线。
"""

from typing import Any, List, Dict, Tuple, Optional, Union

# ============================================================
# 监视器 (MonitorMixin)
# ============================================================
class MonitorMixin:
    @property
    def cst_file(self): ...
    @property
    def model3d(self): ...
    @property
    def modeler(self): ...

    def define_monitor(self, name: str, freq: List[float]) -> None: ...
    def create_field_monitor(self, monitor_type: str, frequencies: List[float]) -> None: ...
    def monitor2d(self, name: str, frequencies: Union[float, List[float]],
                  plane_normal: Optional[str] = 'z',
                  plane_position: Optional[float] = 0) -> None: ...
    def create_probe(self, name: str, position: List[float],
                     frequency: Optional[float] = None,
                     field_type: str = 'E') -> None: ...
