# -*- coding: utf-8 -*-
"""重新生成波导端口 VBA 基线 `cst_solver/tests/data/expected_port_vba.json`。

用法::

    python scripts/gen_expected_port_vba.py            # dry-run：只打印用例与长度
    python scripts/gen_expected_port_vba.py --write     # 真的写文件

为什么要有这个脚本
------------------
`cst_solver/tests/test_ports_vba.py` 用 `expected_port_vba.json` 做**逐字节**回归，
但这份基线原先只有一句"由一次性脚本对 git HEAD 实测生成"，没人能复现。
本脚本把"怎么生成基线"变成可执行的事实。

⚠️ 基线变更**必须人工复核**：任何一行变化都意味着"同一组调用参数下输出变了"，
得能说清原因。已知的两次变化：

1. 阶段 5.8：把 `NumberOfModes / AdjustPolarization / PolarizationAngle /
   ReferencePlaneDistance` 四行写死项开放为关键字参数 —— 不传时**必须**与旧版逐字节相同。
2. 2026-09-20 端口朝向加固：`orientation` 默认值由非法的 `'positive'` 改为 `None`
   ⇒ 不再下发 `.Orientation` 行（等价于改动前 CST 的实际行为：该行被静默忽略、
   取默认朝向），并改为打 `UserWarning`。用例里的朝向一律改成 CST 合法的位置枚举。

@author: PC
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cst_solver.simulation.ports import PortMixin  # noqa: E402

FIXTURE = os.path.join(ROOT, 'cst_solver', 'tests', 'data',
                       'expected_port_vba.json')

#: 用例表：(名字, 方法, 位置参数, 关键字参数)
CASES = (
    # --- Picks（面拾取）链路 ---
    ('picks_no_orientation', 'add_port', (1,), {}),
    ('picks_xmax', 'add_port', (2, 'xmax'), {}),
    ('picks_xmin_electric', 'add_port', (3, 'xmin', 'electric'), {}),
    ('picks_ymax_magnetic', 'add_port', (4, 'ymax', 'magnetic'), {}),
    # --- Free（坐标范围）链路 ---
    ('free_xrange_yrange', 'create_waveguide_port_free', (1,),
     {'xrange': ('0', 'a'), 'yrange': ('-b', 'b')}),
    ('free_zrange', 'create_waveguide_port_free', (2,), {'zrange': ('0', 'h')}),
    ('free_xrange_zrange_electric', 'create_waveguide_port_free', (3,),
     {'xrange': ('0', 'a'), 'zrange': ('0', 'h'), 'shield': 'electric'}),
    ('free_orientation_given', 'create_waveguide_port_free', (4,),
     {'xrange': ('0', 'a'), 'yrange': ('-b', 'b'), 'orientation': 'xmin',
      'shield': 'electric'}),
)


def capture(method, args, kwargs):
    """调用 PortMixin 的方法，返回 (历史标签, VBA 字符串)。"""
    calls = []

    class _Model3D:
        def add_to_history(self, label, vba):
            calls.append((label, vba))

    class _CstFile:
        model3d = _Model3D()

    import warnings
    inst = PortMixin()
    inst.cst_file = _CstFile()
    with warnings.catch_warnings():
        # 未给朝向的用例会告警（那正是被测行为之一），生成基线时不刷屏
        warnings.simplefilter('ignore')
        getattr(inst, method)(*args, **kwargs)
    assert len(calls) == 1, f'{method} 应只下发一条历史，实际 {len(calls)} 条'
    return calls[0]


def build():
    cases = {}
    for name, method, args, kwargs in CASES:
        label, vba = capture(method, args, kwargs)
        cases[name] = {
            'method': method,
            'args': list(args),
            'kwargs': {k: (list(v) if isinstance(v, tuple) else v)
                       for k, v in kwargs.items()},
            'label': label,
            'vba': vba,
        }
    return {
        '_source': 'cst_solver/simulation/ports.py（由 scripts/gen_expected_port_vba.py 生成）',
        '_note': ('波导端口 VBA 字符串基线：**不传阶段 5.8 新增的关键字参数**时，'
                  '输出必须与历史版本逐字节相同（阶段 5.8 的硬要求）。'
                  '2026-09-20 端口朝向加固后重生成：orientation 默认由非法的 '
                  "'positive' 改为 None（不下发 .Orientation 行、改打 UserWarning）；"
                  '用例里的朝向一律用 CST 合法位置枚举。人工复核后再提交。'),
        '_tuple_keys': ['xrange', 'yrange', 'zrange'],
        'cases': cases,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--write', action='store_true',
                    help='写入基线文件（不加则只 dry-run 打印）')
    args = ap.parse_args()

    data = build()
    text = json.dumps(data, ensure_ascii=False, indent=1) + '\n'

    for name, case in data['cases'].items():
        has = '.Orientation' in case['vba']
        print(f"{name:32s} {case['method']:28s} "
              f"Orientation={'有' if has else '无'}  {len(case['vba'])} 字节")

    if args.write:
        with open(FIXTURE, 'w', encoding='utf-8') as fh:
            fh.write(text)
        print(f'\n已写入 {FIXTURE}（{len(text)} 字节）—— 请 git diff 复核')
    else:
        print(f'\ndry-run：未写文件（加 --write 才写）。目标 {FIXTURE}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
