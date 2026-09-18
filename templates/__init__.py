# -*- coding: utf-8 -*-
"""
templates — **已弃用的旧包名**（转发到 `topo_templates`）
=======================================================

本模块只是**一个版本的兼容 shim**：包名 `templates` 过于通用，装进 site-packages
后有与第三方包重名的风险（`import templates` 命中谁取决于 `sys.path` 顺序），
已于 2026-09-15 更名为 [`topo_templates`](../topo_templates/__init__.py)。

请改用::

    from topo_templates import StraightWaveguide, UnitAntenna, GRINLensAntenna   # ✅ 新名

旧写法仍然可用，但会发 `DeprecationWarning`::

    from templates import StraightWaveguide                    # ⚠️ 已弃用

**移除计划**：下一个版本周期内删除本 shim（见
`docs/next_plan/stages/08_阶段8_复杂结构与旧代码迁移.md` 的「包名风险到期」条目）。

@author: PC
"""

import warnings

warnings.warn(
    "包名 'templates' 已弃用，请改用 'topo_templates'：\n"
    "    from topo_templates import StraightWaveguide, UnitAntenna\n"
    "本 shim 只保留一个版本周期，之后会被删除。",
    DeprecationWarning,
    stacklevel=2,
)

from topo_templates.straight_waveguide import StraightWaveguide  # noqa: E402
from topo_templates.unit_antenna import UnitAntenna              # noqa: E402
from topo_templates.grin_lens_antenna import GRINLensAntenna      # noqa: E402
from topo_templates.multiport_antenna import MultiPortAntenna     # noqa: E402
from topo_templates.mzi_switch import MZISwitch                   # noqa: E402
from topo_templates.power_divider import PowerDivider             # noqa: E402

__all__ = [
    "StraightWaveguide",
    "UnitAntenna",
    "GRINLensAntenna",
    "MultiPortAntenna",
    "MZISwitch",
    "PowerDivider",
]
