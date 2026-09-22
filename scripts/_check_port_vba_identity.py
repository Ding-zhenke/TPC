# -*- coding: utf-8 -*-
"""
波导端口 VBA 逐字节一致性校验（一次性工具，保留作方法与证据记录）
=================================================================

阶段 5.8 把 `add_port()` / `create_waveguide_port_free()` 的四个写死属性
（`NumberOfModes` / `AdjustPolarization` / `PolarizationAngle` /
`ReferencePlaneDistance`）开放成了关键字参数。做法：把
`git HEAD:cst_solver/simulation/ports.py` 的源码 `exec` 进一个临时模块，
用它和当前模块分别生成同样的端口，逐字节比对。

实测结果（2026-09-15，HEAD = 98fd0ca）：7/7 用例逐字节相同。
该实测的输出已经**固化成回归测试**：`cst_solver/tests/test_ports_vba.py`
+ 基线数据 `cst_solver/tests/data/expected_port_vba.json`。

⚠️ 本脚本只在**提交改动之前**有意义：一旦 ports.py 的改动提交进 HEAD，
两侧就变成了同一个版本，比对恒为真。

⚠️ 2026-09-20 端口朝向加固后：用例里的朝向一律改成 CST 合法的位置枚举
（`xmin/xmax/ymin/ymax/zmin/zmax`）—— 旧用例里的 `'positive'/'negative'` 已被
`check_port_orientation()` 挡下（会抛 `ValueError`，代表它就是那个静默错朝向的寕头）。
基线文件的重生成现在由 `scripts/gen_expected_port_vba.py` 负责（本脚本只做
HEAD 差异比对，不再用于生成）。

用法: python scripts/_check_port_vba_identity.py
退出码: 0 = 全部逐字节相同；1 = 有差异（差异会写到 _port_diff_old.txt / _port_diff_new.txt）
"""

import io
import subprocess
import sys
import types

ROOT = r'D:\成电博士生涯\自动建模算法尝试\TPC'
sys.path.insert(0, ROOT)


class _FakeModel:
    def __init__(self):
        self.last = None

    def add_to_history(self, label, vba):
        self.last = (label, vba)


class _FakeApp:
    def __init__(self):
        class _CF:
            model3d = _FakeModel()
        self.cst_file = _CF()


def _capture(mixin_cls, method, *args, **kwargs):
    app = _FakeApp()
    inst = mixin_cls()
    inst.cst_file = app.cst_file
    getattr(inst, method)(*args, **kwargs)
    return app.cst_file.model3d.last


def _head_mixin():
    src = subprocess.run(
        ['git', 'show', 'HEAD:cst_solver/simulation/ports.py'],
        cwd=ROOT, capture_output=True)
    text = src.stdout.decode('utf-8')
    mod = types.ModuleType('head_ports')
    exec(compile(text, 'head_ports.py', 'exec'), mod.__dict__)
    return mod.PortMixin


def main():
    from cst_solver.simulation.ports import PortMixin as NewPorts
    OldPorts = _head_mixin()

    cases = [
        ('add_port', (1, 'xmin'), {}),
        ('add_port', (2, 'xmax'), {}),
        ('add_port', (3, 'xmin', 'electric'), {}),
        ('add_port', (4, 'ymax', 'magnetic'), {}),
        ('create_waveguide_port_free', (1, 'xmin'), dict(xrange=('0', 'a'), yrange=('-b', 'b'))),
        ('create_waveguide_port_free', (2, 'zmin'), dict(zrange=('0', 'h'))),
        ('create_waveguide_port_free', (3, 'xmax'), dict(xrange=('0', 'a'), zrange=('0', 'h'), shield='electric')),
    ]

    bad = 0
    for method, args, kwargs in cases:
        old = _capture(OldPorts, method, *args, **kwargs)
        new = _capture(NewPorts, method, *args, **kwargs)
        same = (old == new)
        if not same:
            bad += 1
            print(f'[DIFF] {method}{args}{kwargs}')
            io.open('_port_diff_old.txt', 'w', encoding='utf-8').write(old[1])
            io.open('_port_diff_new.txt', 'w', encoding='utf-8').write(new[1])
        else:
            print(f'[SAME] {method}{args} {kwargs}  ({len(old[1])} 字节, label={old[0]!r})')

    print('----')
    print('全部逐字节相同' if bad == 0 else f'{bad} 个用例不同（已写 _port_diff_*.txt）')
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
