# -*- coding: utf-8 -*-
"""
topo_templates — 拓扑光子晶体端到端模板
======================================
一键建模模板：直波导、单元天线、透镜天线等。**一个类 = 一个器件**。

为什么叫 `topo_templates`（而不是 `templates`）
---------------------------------------------
顶层包名 `templates` 过于通用：一旦本库装进 site-packages，很可能与第三方包**重名**，
届时 `import templates` 命中的是谁取决于 `sys.path` 顺序 —— 属于极难排查的隐性故障。
2026-09-15 按 T10 更名为 `topo_templates`；旧名 `templates` 在一个弃用周期内保留为
转发 shim（见仓库根的 `templates/__init__.py`），再择版本移除。

用法::

    from topo_templates import (StraightWaveguide, UnitAntenna,
                                GRINLensAntenna, MultiPortAntenna)

@author: PC
"""

from topo_templates.straight_waveguide import StraightWaveguide
from topo_templates.unit_antenna import UnitAntenna
from topo_templates.grin_lens_antenna import GRINLensAntenna
from topo_templates.multiport_antenna import MultiPortAntenna
from topo_templates.mzi_switch import MZISwitch
from topo_templates.power_divider import PowerDivider

__all__ = [
    "StraightWaveguide",
    "UnitAntenna",
    "GRINLensAntenna",
    "MultiPortAntenna",
    "MZISwitch",
    "PowerDivider",
]
