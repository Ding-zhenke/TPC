# -*- coding: utf-8 -*-
"""
P4/V5 事实核验：存疑 VBA（``Port.Coordinates`` 与 ``Solid.Imprint``）
====================================================================

用途：在**装有 CST 的机器上**跑一次，用**最小工程 + CST 错误通道**判定这几个存疑命令，
而不是照第三方文档改名。结论回填 `docs/validation/p4_real_machine_evidence.md`。

为什么要单独核验
----------------
`scripts/verify_port_face_api.py` 的 docstring 里写着：

    明确不在本脚本范围内 —— V1 ``Port.Coordinates`` 的取值究竟认
    ``"Picks"`` 还是 ``"Picked"``（按要求暂不核验）

本脚本就是补上这一条。库当前下发 ``.Coordinates "Picks"``（`ports.py:82`）。

⚠️ 两个必须遵守的实测约束（第一版脚本踩过）
-------------------------------------------
1. **每个探针用全新工程**：一条非法命令留在历史里之后，``get_messages()`` 会**反复**
   报同一条历史失败（不是"读一次就干净"），于是后续所有"按消息判定"的结论都被污染
   （``pick_face_auto`` 就是这么被带偏的）。
2. **失败有两条通道**：有的非法 VBA 会让 ``add_to_history`` **直接抛 Python 异常**
   （消息里带 CST 原文），有的只写消息。两条都要看。

探针清单（每个都带对照）
------------------------
C1  坏值 ``.Coordinates "BogusXYZ"`` → 必须失败（证明判定通道有效）
C2  ``.Coordinates "Picks"``（库当前用法）+ 已拾取的面 → 期望被接受
C3  ``.Coordinates "Picked"``（另一种拼写）→ 记录是否被接受
C4  ``.Coordinates "Full"``（CST 报错信息里列出的第三种）→ 记录是否被接受
C5  ``.Coordinates "Free"`` + ``Xrange/Yrange/Zrange``（已知可用）→ 期望被接受
C6  ``Solid.Imprint "component1:b1", "component1:b2"``（两个相交方块）→ 记录
C7  坏实体名的 ``Solid.Imprint`` → 必须失败

用法
----
    python scripts/verify_dubious_vba.py

注意
----
只新建**空白工程**，不打开、不修改任何既有工程；收尾关闭 DE（只关本次新建的）。
"""

import json
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from topo_modeler.batch import (                    # noqa: E402
    close_extra_design_environments,
    design_environment_baseline,
)

BOX = dict(x1='0', x2='1', y1='0', y2='1', z1='0', z2='1')
BOX_NAME = 'probe_box'
TOP_CENTER = (0.5, 0.5, 1.0)

_results = []
_app = None
_baseline = set()


def record(item, status, detail, **extra):
    """记录一条核验结果（OK / FAIL / UNKNOWN）。"""
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    print(f'[{status:^7}] {item}: {detail}', flush=True)


def messages():
    """读 CST 消息（注意：历史失败会**反复**出现，见模块 docstring）。"""
    return [str(m) for m in (_app.cst_file.get_messages() or [])]


def send(caption, vba):
    """下发 VBA，返回 ``(messages, exception_text)``。"""
    try:
        _app.cst_file.model3d.add_to_history(caption, vba)
    except Exception as exc:                          # noqa: BLE001
        return messages(), f'{type(exc).__name__}: {exc}'
    return messages(), None


def verdict(messages_, exception_text):
    """把两条失败通道合成 ``(是否被接受, 说明)``。"""
    if exception_text:
        tail = [line for line in exception_text.splitlines() if line.strip()]
        return False, '抛异常：' + (tail[-1][:220] if tail else exception_text[:220])
    if messages_:
        first = messages_[0]
        text = first.get('text', str(first)) if isinstance(first, dict) else str(first)
        return False, '有消息：' + text[:220].replace('\n', ' ')
    return True, '无异常、无消息 ⇒ 被接受'


def new_blank_project(with_box=True):
    """关掉当前工程、新建空白工程（**每个探针都要调**），返回准备阶段的消息。"""
    try:
        if _app.cst_file is not None:
            _app.cst_file.close()
    except Exception:                                 # noqa: BLE001
        pass
    _app.new_project()
    if with_box:
        _app.square(BOX['x1'], BOX['x2'], BOX['y1'], BOX['y2'],
                    BOX['z1'], BOX['z2'], BOX_NAME, 'component1', 'Vacuum')
    return messages()


def pick_top_face():
    """按坐标点拾取顶面，返回 ``(结果, 已拾取面数)``。"""
    _app.pick_clear()
    try:
        result = _app.pick_face_auto(BOX_NAME, points=[TOP_CENTER],
                                     candidates=('10', '1', '2', '3'))
    except Exception as exc:                          # noqa: BLE001
        result = f'ERROR: {type(exc).__name__}: {exc}'
    try:
        count = _app.get_picked_count('face')
    except Exception as exc:                          # noqa: BLE001
        count = f'ERROR: {exc}'
    return result, count


def port_vba(number, coordinates, ranges=False):
    """构造一个 Port 定义块（结构与 `ports.py` 的 add_port 保持一致）。"""
    head = f'''With Port
     .Reset
     .PortNumber "{number}"
     .Label ""
     .Folder ""
     .NumberOfModes "1"
     .AdjustPolarization "False"
     .PolarizationAngle "0.0"
     .ReferencePlaneDistance "0"
     .TextSize "50"
     .TextMaxLimit "0"
     .Coordinates "{coordinates}"
     .Orientation "positive"
     .PortOnBound "True"
     .ClipPickedPortToBound "False"
     .SingleEnded "False"
     .WaveguideMonitor "False"
'''
    if ranges:
        head += (f'     .Xrange "{BOX["x1"]}", "{BOX["x2"]}"\n'
                 f'     .Yrange "{BOX["y1"]}", "{BOX["y2"]}"\n'
                 f'     .Zrange "{BOX["z2"]}", "{BOX["z2"]}"\n')
    return head + '     .Create\nEnd With'


def probe_coordinate(label, value, *, ranges=False, need_pick=True,
                     expected='accepted', port_number=1):
    """在一个干净工程里试一种 ``Coordinates`` 取值。"""
    prep = new_blank_project()
    picked, count = (None, None)
    if need_pick:
        picked, count = pick_top_face()
    msgs, exc = send(f'probe coordinates {value}', port_vba(port_number, value,
                                                            ranges=ranges))
    ok, detail = verdict(msgs, exc)
    if expected == 'accepted':
        status = 'OK' if ok else 'FAIL'
    elif expected == 'rejected':
        status = 'OK' if not ok else 'FAIL'
    else:
        status = 'UNKNOWN'
    record(label, status, detail, picked=str(picked), picked_faces=count,
           prepare_messages=len(prep), messages=msgs[:2], exception=exc)


def probe_imprint(label, name1, name2, expected):
    """在一个干净工程里试 ``Solid.Imprint``。"""
    new_blank_project(with_box=False)
    _app.square('0', '1', '0', '1', '0', '1', 'b1', 'component1', 'Vacuum')
    _app.square('0.5', '1.5', '0.5', '1.5', '0.5', '1.5', 'b2', 'component1', 'Vacuum')
    msgs, exc = send('probe Solid.Imprint',
                     f'Solid.Imprint "component1:{name1}", "component1:{name2}"')
    ok, detail = verdict(msgs, exc)
    status = ('OK' if ok else 'FAIL') if expected == 'accepted' else \
             ('OK' if not ok else 'FAIL')
    record(label, status, detail, messages=msgs[:2], exception=exc)


def main() -> int:
    global _app, _baseline
    from cst_solver import setup

    _baseline = design_environment_baseline()
    print(f'基线 DE：{sorted(_baseline)}', flush=True)
    try:
        _app = setup()                                # 只建 DE，不开工程
        prep = new_blank_project()
        record('准备最小工程', 'OK' if not prep else 'FAIL',
               f'空白工程 + 1×1×1 方块（准备阶段消息 {len(prep)} 条）')

        probe_coordinate('C1 对照（坏值 BogusXYZ）', 'BogusXYZ',
                         expected='rejected')
        probe_coordinate('C2 .Coordinates "Picks"（库当前用法）', 'Picks',
                         expected='accepted', port_number=2)
        probe_coordinate('C3 .Coordinates "Picked"（另一种拼写）', 'Picked',
                         expected='unknown', port_number=3)
        probe_coordinate('C4 .Coordinates "Full"（报错信息里的第三种）', 'Full',
                         expected='unknown', need_pick=False, port_number=4)
        probe_coordinate('C5 对照（Free + 范围，已知可用）', 'Free',
                         ranges=True, need_pick=False, expected='accepted',
                         port_number=5)
        probe_imprint('C6 Solid.Imprint（两个相交方块）', 'b1', 'b2', 'accepted')
        probe_imprint('C7 对照（坏实体名）', 'nope1', 'nope2', 'rejected')
    except Exception:                                 # noqa: BLE001
        record('核验过程异常', 'FAIL', traceback.format_exc(limit=3))
    finally:
        try:
            if _app is not None:
                _app.close()
        except Exception:                             # noqa: BLE001
            pass
        closed = close_extra_design_environments(_baseline, verbose=True)
        record('收尾', 'OK', f'关闭本次新建的 DE：{closed or "无"}')

    print('\n=== 汇总 ===')
    for entry in _results:
        print(f"{entry['status']:^7}  {entry['item']}")
    failed = [r for r in _results if r['status'] == 'FAIL']
    print(f'\nOK {len([r for r in _results if r["status"] == "OK"])} / '
          f'FAIL {len(failed)} / UNKNOWN {len([r for r in _results if r["status"] == "UNKNOWN"])}')
    print(json.dumps(_results, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
