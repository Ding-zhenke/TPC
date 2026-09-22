# -*- coding: utf-8 -*-
"""
P4/V10 真机复验：2026-09-23 五处封装层缺陷（**不跑求解**）
========================================================

在**装有 CST Studio Suite 2026 的机器上**跑一次，把
`cst_solver/tests/test_reported_bugfixes.py`（27 条离线回归）里只能离线证明的东西
拿到真 CST 上确认。结论回填 `docs/validation/p4_real_machine_evidence.md`。

本脚本**只建模**：新建空白工程、下发 VBA、`Rebuild()`、保存、读参数、关工程。
**不调用任何求解器**（不 run / 不 scan / 不 optimize）。

复验四点（对应 `docs/next_plan/README.md` 的 P4/V10）
----------------------------------------------------
① `set_background()` 新的 ``Type/Epsilon/Mu`` 写法
   - ``get_messages()`` 为空；
   - 保存后工程 ``Model.mif`` 里背景**确为设定值**；
   - **对照证据**：旧的 ``.Material "<名字>"`` 写法在本版本 CST 上被**静默忽略**
     （不报错、不写消息），背景仍旧 —— 这正是「设了等于没设」的根因。
② ``add_port(..., port_on_bound=False)`` 能在**域内部**建端口
   - 对照：同样的域内范围 + ``port_on_bound=True``（旧代码写死的值）必须**失败**；
   - 修法：``port_on_bound=False`` ⇒ 被接受。
③ 无参 ``app.save()`` 确实落盘（``Model.mif`` 时间戳/大小变化），随后工程完好
   - 工程还没有路径时（刚 ``new_project()``）⇒ ``RuntimeError``（旧行为是静默 no-op）。
④ ``get_parameter()`` 能读回 ``para()`` / ``expression()`` 写下的值
   - 同时记录三个官方读取接口（``RestoreDoubleParameter`` / ``RestoreParameter`` /
     ``RestoreParameterExpression``）的**原始返回值**，以及旧写法
     ``model3d.GetParameter()`` 在真机上的实际表现（取证）。
⑤ （附加）路径入口守卫：不存在 / 是目录 ⇒ 立刻失败且**不新建 DE**。

⚠️ 必须遵守的实测约束
--------------------
1. **每个探针用全新工程**：一条失败命令留在历史里之后 ``get_messages()`` 会
   **反复**报同一条失败（不是"读一次就干净"），会污染后续所有"按消息判定"的结论。
2. **失败有两条通道**：``add_to_history()`` 可能**直接抛 Python 异常**，
   也可能只写消息 —— 两条都看（:func:`verdict` 就是干这个的）。
3. **弹窗会永久阻塞**：每步前后用 `scripts/cst_dialog_guard.py` 检查 CST 对话框
   （未定义参数 ⇒「请输入变量值」；关工程 ⇒「是否保存更改？」）。

用法
----
    python scripts/verify_bugfixes_real.py            # 跑完删掉临时工程
    python scripts/verify_bugfixes_real.py --keep     # 保留临时工程供人工检查
"""

import json
import os
import re
import sys
import tempfile
import time
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))

from topo_modeler.batch import (                    # noqa: E402
    close_extra_design_environments,
    design_environment_query,
)
from cst_dialog_guard import (                      # noqa: E402
    check_dialogs,
    describe_dialogs,
    describe_windows,
    guard,
    list_windows,
    save_prompts,
)

BOX = dict(x1='0', x2='1', y1='0', y2='1', z1='0', z2='1')
BOX_NAME = 'p4v10_box'

#: 旧的 ``set_background()`` 写法（2026-09-23 修复前逐字复制，含 ``.Material`` 行）
OLD_BACKGROUND_VBA = '''With Background
     .Reset
     .Type "Normal"
     .Material "Quartz (Fused) (lossy)"
     .XminSpace "0"
     .XmaxSpace "0"
     .YminSpace "0"
     .YmaxSpace "0"
     .ZminSpace "0"
     .ZmaxSpace "0"
     .ApplyInAllDirections "False"
End With'''

#: 同上，但 ``.Type`` 用小写 ``"normal"``（官方枚举写法）——
#: 用来把「``.Material`` 无效」与「``.Type`` 大小写有问题」两个变量分开
OLD_BACKGROUND_VBA_TYPEFIX = OLD_BACKGROUND_VBA.replace('.Type "Normal"',
                                                        '.Type "normal"')

_results = []
_app = None
_work = None
_baseline = set()
_profile = {}
#: 是否借用了用户已有的 CST 会话（``--attach``）：借用时**绝不**关用户的工程/会话
_attached_mode = False
#: ``--attach`` 给的用户 DE 进程号（attach 模式下复用同一个会话）
_attach_pid = None
#: 当前 ``_app.cst_file`` 指向的是不是「我们自己新建的临时工程」
_own_project_started = False


def _mark_own_closed():
    """记下：当前工程已经关掉，``_app.cst_file`` 不再指向我们的临时工程。"""
    global _own_project_started
    _own_project_started = False


def record(item, status, detail, **extra):
    """记录一条核验结果（OK / FAIL / UNKNOWN），并打印。"""
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    print(f'[{status:^7}] {item}: {detail}', flush=True)
    return entry


def cst_pids():
    """当前活着的 DE 进程号；问不到时返回 ``(None, 原因)``，**绝不**把问不到当「没有」。"""
    query = design_environment_query()
    if not query['ok']:
        return None, query['reason']
    return [int(pid) for pid in query['pids']], ''


def make_cst_importable():
    """
    先把 CST 的 ``python_cst_libraries`` 放进 ``sys.path``。

    ⚠️ 血泪点（2026-09-23 实测）：``cst_solver`` 是**惰性**把 CST 库加进 ``sys.path`` 的，
    所以在这个动作**之前**调 :func:`design_environment_baseline` 会拿到空集合
    （``cst.interface`` 还没导入得进来 ⇒ ``running_design_environments()`` 返回 ``[]``）。
    而 ``close_extra_design_environments(baseline=set())`` 会把**用户自己开着的
    CST 会话**（实测 pid 36472，里面有未保存工程）当成「本次新建的 DE」去
    ``connect(pid).close()`` —— 差点造成数据丢失。
    """
    try:
        from cst_solver import _load_cst_module
        _load_cst_module('cst.interface')
        return True
    except Exception:                                   # noqa: BLE001
        return False


def busy_de_hint(pid=None):
    """
    目标 DE 是不是正忙（里面有求解在跑）？忙则返回原因字符串，空闲返回 ``''``。

    ⚠️ 血泪点（2026-09-23 实测）：求解进行中时 CST 主窗口标题带进度前缀
    ``[7% ] <工程名> - CST Studio Suite 2026``。这种状态下在**借来的** DE 里
    `new_project()` 会先报
    ``RuntimeError: An error occurred while trying to create a new project.``，
    重试时甚至把 COM 调用**挂死**（客户端 120s 超时被杀，而 DE 侧其实已经建出了
    一个空白工程）。所以必须在动手前就看出来，别把环境问题记成四条 FAIL。
    """
    try:
        windows = list_windows()
    except Exception:                                   # noqa: BLE001
        return ''
    hits = []
    for window in windows:
        title = window.get('title') or ''
        if pid is not None and window.get('pid') not in (None, pid):
            continue
        if re.search(r'\[\s*\d+\s*%\s*\]', title):
            hits.append(f'{window.get("pid")}: {title!r}')
    if not hits:
        return ''
    return ('目标 DE 里有求解在跑（' + '；'.join(hits[:2]) +
            '）⇒ 在忙碌的 DE 里 new_project() 会失败甚至挂死，本轮不取证。'
            '等它跑完（标题里不再有 [nn% ]）再重跑本脚本。')


def messages():
    """读 CST 消息（历史失败会**反复**出现，见模块 docstring）。"""
    try:
        raw = _app.cst_file.get_messages() or []
    except Exception as exc:                        # noqa: BLE001
        return [f'<get_messages 失败: {exc}>']
    out = []
    for item in raw:
        text = item.get('text', str(item)) if isinstance(item, dict) else str(item)
        out.append(text.replace('\n', ' ')[:300])
    return out


def send(caption, vba):
    """下发 VBA，返回 ``(messages, exception_text)``。"""
    try:
        _app.cst_file.model3d.add_to_history(caption, vba)
    except Exception as exc:                        # noqa: BLE001
        return messages(), f'{type(exc).__name__}: {exc}'
    return messages(), None


def verdict(msgs, exc):
    """把两条失败通道合成 ``(是否被接受, 说明)``。"""
    if exc:
        tail = [line for line in exc.splitlines() if line.strip()]
        return False, '抛异常：' + (tail[-1][:240] if tail else exc[:240])
    if msgs:
        return False, '有消息：' + msgs[0][:240]
    return True, '无异常、无消息 ⇒ 被接受'


def fresh_project(with_box=True, electric_walls=False):
    """
    准备一个干净的空白工程（**每个探针都要调**），返回准备阶段的消息。

    ⚠️ attach 模式（借用用户的 CST 会话）下**绝不能**关掉用户原本打开的工程：
    只关「上一轮我们自己新建的那个空白工程」，而且关之前先存盘，
    免得弹「是否保存更改？」。

    :param with_box: bool, 是否建一个 1×1×1 的实体盒
    :param electric_walls: bool, 是否把六面设成电壁（把计算域钉在盒子表面上）
    """
    global _own_project_started
    if _attached_mode:
        _close_own_project()
    else:
        try:
            if getattr(_app, 'cst_file', None) is not None:
                _app.cst_file.close()
        except Exception:                               # noqa: BLE001
            pass
    _app.new_project()
    _own_project_started = True
    prep = messages()
    if electric_walls:
        # 把计算域钉在实体盒子上：电壁 + 0 扩展空间 ⇒ 域边界 = 盒子表面。
        # 这样「z=0 在边界平面上」与「z=0.5 在域内部」才有确定含义。
        _app.set_background()                        # 六向 space 全 0
        _app.boundary(xmin='electric', xmax='electric', ymin='electric',
                      ymax='electric', zmin='electric', zmax='electric')
    if with_box:
        _app.square(BOX['x1'], BOX['x2'], BOX['y1'], BOX['y2'],
                    BOX['z1'], BOX['z2'], BOX_NAME, 'component1', 'Vacuum')
    return prep + messages() if prep else messages()


def _close_own_project(save_first=True):
    """
    关掉**我们自己新建的**那个临时空白工程（attach 模式下保护用户工程的关键）。

    - 先存盘到临时目录：工程「干净」了再关，就不会弹「是否保存更改？」；
    - ``handle`` 直接取 CST 的 ``Project`` 原始对象（``_app.cst_file``）——
      走 :meth:`cst_solver.setup.close` 在 attach 模式下只是解除引用、并不真关，
      那样临时工程会在用户窗口里越堆越多直到撑爆内存。
    """
    if not _own_project_started:
        return
    handle = getattr(_app, 'cst_file', None)
    if handle is None:
        return
    if save_first:
        try:
            _app.save(str(_work / '_probe_last.cst'), include_results=False,
                      allow_overwrite=True)
        except Exception:                           # noqa: BLE001
            pass
    try:
        handle.close()
        _mark_own_closed()
    except Exception as exc:                        # noqa: BLE001
        record('收尾：关掉临时空白工程', 'UNKNOWN',
               f'关不掉（请手动关掉那个空白工程窗口）：{type(exc).__name__}: {exc}',
               exception=f'{type(exc).__name__}: {exc}')


def rebuild():
    """阻塞式重放历史，返回 ``(messages, exception_text)``。"""
    try:
        _app.cst_file.model3d.Rebuild()
    except Exception as exc:                        # noqa: BLE001
        return messages(), f'{type(exc).__name__}: {exc}'
    return messages(), None


def save_project(path):
    """带路径保存（复验里的辅助动作，不是被测对象）。"""
    return _app.save(str(path), include_results=False, allow_overwrite=True)


# ------------------------------------------------------------------
# mif 取证：背景是否真的写进去了
# ------------------------------------------------------------------

def find_mif(project_path):
    """CST 工程的 ``Model.mif``（工程是**目录**形式的 .cst）。"""
    path = Path(project_path)
    if path.is_dir():
        hits = sorted(path.rglob('Model.mif'))
        return hits[0] if hits else None
    return None


def project_fingerprint(project_path):
    """
    工程文件的 (mtime_ns, size, 说明) —— 用来判定「无参 save 是否真的落盘」。

    优先用 ``Model.mif``；找不到就退回工程路径本身（单个文件形式），
    再不行就取目录下所有文件里最大的 mtime。
    """
    path = Path(project_path)
    mif = find_mif(path)
    if mif is not None:
        stat = mif.stat()
        return stat.st_mtime_ns, stat.st_size, str(mif)
    if path.is_file():
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size, str(path)
    latest = None
    for child in path.rglob('*'):
        if not child.is_file():
            continue
        stat = child.stat()
        if latest is None or stat.st_mtime_ns > latest[0]:
            latest = (stat.st_mtime_ns, stat.st_size, str(child))
    return latest if latest else (None, None, '<取不到指纹>')


def mif_text(mif_path):
    """读 mif 文本（失败返回 ``('<读失败: ...>', '')``）。"""
    try:
        return mif_path.read_text(encoding='utf-8', errors='replace')
    except Exception as exc:                        # noqa: BLE001
        return f'<读 mif 失败: {exc}>'


def background_windows(text, span=900, limit=4):
    """mif 里所有 ``Background`` 附近的窗口（历史副本 + 模型段都抓回来）。"""
    windows = []
    start = 0
    while len(windows) < limit:
        idx = text.find('Background', start)
        if idx < 0:
            break
        windows.append(text[idx:idx + span])
        start = idx + 10
    return windows


def parse_background(window):
    """
    从窗口里取 ``Type`` / ``Epsilon`` / ``Mu``。

    ⚠️ 只认**不带点**的写法（``Type "normal"``）—— 历史副本里是 ``.Type "normal"``，
    两者不能混着判读。
    """
    fields = {}
    for key in ('Type', 'Epsilon', 'Mu'):
        match = re.search(rf'(?<!\.)\b{key}\s+"([^"]*)"', window)
        if match:
            fields[key] = match.group(1)
    return fields


def _as_float(value):
    """把 mif 里的值转 float（``'1'``/``'1.0'``/``'1.19e+01'`` 都认）；转不了返回 None。"""
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def background_evidence(project_path, label):
    """保存后的背景取证：mif 路径 + 窗口 + 解析值 + 是否出现 ``.Material``。"""
    mif = find_mif(project_path)
    if mif is None:
        return {'mif': None, 'note': '没找到 Model.mif（工程可能不是目录形式）'}
    text = mif_text(mif)
    # 原文另存一份：正则万一不匹配真机格式，可以离线改解析、不必再跑真机
    dump = _work / f'bg_{label}.mif.txt'
    try:
        dump.write_text(text, encoding='utf-8')
    except Exception:                                   # noqa: BLE001
        dump = None
    windows = background_windows(text)
    parsed = [parse_background(w) for w in windows]
    # 只挑「看起来像模型段」的那一条：同时有 Type 与 Epsilon/Mu
    model_like = [p for p in parsed if 'Type' in p and ('Epsilon' in p or 'Mu' in p)]
    return {
        'mif': str(mif),
        'mif_dump': str(dump) if dump else None,
        'mif_size': mif.stat().st_size,
        'mif_mtime': mif.stat().st_mtime,
        'parsed': parsed,
        'model_like': model_like[0] if model_like else None,
        'has_dot_material': '.Material' in text,
        'windows': [w[:600] for w in windows],
        'label': label,
    }


# ------------------------------------------------------------------
# ① 背景
# ------------------------------------------------------------------

def probe_background(label, expect, *, setup_call=None, vba=None, note=''):
    """
    在一个全新工程里做一次背景设置，保存后取证。

    :param label: str, 探针名
    :param expect: str, 'eps'（期望 mif 里 ε 等于某个值）/ 'pec' / 'silent'
    :param setup_call: callable|None, 调用 ``app.set_background(...)``
    :param vba: str|None, 直接下发原始 VBA（对照用）
    :param note: str, 说明
    """
    check_dialogs(f'① {label}')
    prep = fresh_project(with_box=False)
    if vba is not None:
        msgs, exc = send(f'old background {label}', vba)
    else:
        try:
            setup_call()
            exc = None
        except Exception as err:                    # noqa: BLE001
            msgs, exc = messages(), f'{type(err).__name__}: {err}'
        else:
            msgs = messages()
    accepted, detail = verdict(msgs, exc)

    rebuild_msgs, rebuild_exc = rebuild()
    accepted_after, detail_after = verdict(rebuild_msgs, rebuild_exc)

    out = _work / f'bg_{label}.cst'
    try:
        save_project(out)
        saved = True
    except Exception as err:                        # noqa: BLE001
        saved, detail_save = False, f'{type(err).__name__}: {err}'
    else:
        detail_save = str(out)

    evidence = background_evidence(out, label) if saved else {}
    model_like = evidence.get('model_like')

    if expect == 'silent':
        # 对照组的判据只看 mif：旧写法里的 .Type "Normal" 大小写可能本来就报错，
        # 那不是我们要证的事（.Material 是否生效才是）
        status = 'OK' if (_as_float((model_like or {}).get('Epsilon')) == 1.0
                          and saved) else 'FAIL'
    elif not accepted or not accepted_after or not saved:
        status = 'FAIL'
    elif expect == 'eps' and _as_float((model_like or {}).get('Epsilon')) != _as_float(_profile[label]):
        status = 'FAIL'
    elif expect == 'pec' and str((model_like or {}).get('Type', '')).lower() != 'pec':
        status = 'FAIL'
    else:
        status = 'OK'

    record(f'① {label}', status,
           f'{detail}；Rebuild：{detail_after}；mif 背景={model_like}'
           + (f'；{note}' if note else ''),
           prepare_messages=len(prep), accepted=accepted,
           accepted_after_rebuild=accepted_after,
           messages=msgs[:2], exception=exc,
           rebuild_messages=rebuild_msgs[:2], rebuild_exception=rebuild_exc,
           save=detail_save, evidence=evidence)


def run_background_probes():
    """① 的三组探针：对照（什么都不设）/ 旧写法 / 新写法（默认、自定义、PEC）。"""
    # 对照：全新工程什么都不设 ⇒ 背景就是 CST 默认（真空 ε=1）
    _profile['control_unset'] = '1.0'
    probe_background('control_unset', 'eps', setup_call=lambda: None,
                     note='对照：不设背景 ⇒ CST 默认 ε=1')

    # 旧写法：.Material 在本版本 CST 上是否被静默忽略？
    _profile['old_material'] = '1.0'
    probe_background('old_material', 'silent', vba=OLD_BACKGROUND_VBA,
                     note='对照：旧 .Material "Quartz (Fused) (lossy)"（.Type "Normal"）'
                          '是否生效 ⇒ 期望 mif 里 ε 仍是 1.0')

    # 旧写法（.Type 用官方小写枚举）：单独把 .Material 这个变量隔离出来
    _profile['old_material_lc'] = '1.0'
    probe_background('old_material_lc', 'silent', vba=OLD_BACKGROUND_VBA_TYPEFIX,
                     note='对照：同一段但 .Type "normal"（官方枚举写法）⇒ '
                          '若仍 ε=1.0，则 .Material 确实无效（与 .Type 大小写无关）')

    # 新写法（默认 Vacuum）
    _profile['new_default'] = '1.0'
    probe_background('new_default', 'eps', setup_call=lambda: _app.set_background(),
                     note='新写法：默认 Vacuum ⇒ Type normal + ε/μ 1.0')

    # 新写法（显式 ε/μ：11.9 硅背景）
    _profile['new_eps11'] = '11.9'
    probe_background('new_eps11', 'eps',
                     setup_call=lambda: _app.set_background(
                         'Silicon', epsilon=11.9, mu=1.0),
                     note='新写法：ε=11.9（旧写法无法表达）')

    # 新写法（PEC 背景）
    probe_background('new_pec', 'pec',
                     setup_call=lambda: _app.set_background(material='PEC'),
                     note='新写法：PEC ⇒ Type pec，不下发 ε/μ')


# ------------------------------------------------------------------
# ② 端口
# ------------------------------------------------------------------

PORT_FREE_TEMPLATE = '''With Port 
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
            .Coordinates "Free" 
            .Orientation "{orientation}" 
            .PortOnBound "{on_bound}" 
            .ClipPickedPortToBound "False" 
            .Xrange {x1}, {x2}
            .Yrange {y1}, {y2}
            .Zrange {z1}, {z2}
            .SingleEnded "False" 
            .WaveguideMonitor "False" 
            
            .Create 
        End With
'''


def probe_port(label, *, zplane, on_bound, expect, use_library_call=True,
               orientation='zmin'):
    """
    建一个 ``Coordinates "Free"`` 波导端口，看 CST 接不接受。

    :param zplane: str, 端口面所在的 z（'0' = 计算域边界平面，'0.5' = 域内部）
    :param on_bound: bool, ``.PortOnBound``
    :param expect: str, 'accepted' / 'rejected'
    :param use_library_call: bool, True = 走 ``create_waveguide_port_free()``；
        False = 直接下发等价 VBA（脚本自带，用于确认脚本模板与库一致）
    """
    check_dialogs(f'② {label}')
    fresh_project(with_box=True, electric_walls=True)
    if use_library_call:
        try:
            _app.create_waveguide_port_free(
                1, xrange=(BOX['x1'], BOX['x2']), yrange=(BOX['y1'], BOX['y2']),
                zrange=(zplane, zplane), orientation=orientation,
                port_on_bound=on_bound)
            exc = None
        except Exception as err:                    # noqa: BLE001
            exc = f'{type(err).__name__}: {err}'
        msgs = messages()
    else:
        msgs, exc = send(f'probe port {label}', PORT_FREE_TEMPLATE.format(
            number=1, orientation=orientation,
            on_bound='True' if on_bound else 'False',
            x1=BOX['x1'], x2=BOX['x2'], y1=BOX['y1'], y2=BOX['y2'],
            z1=zplane, z2=zplane))
    accepted, detail = verdict(msgs, exc)
    rebuild_msgs, rebuild_exc = rebuild()
    accepted_after, detail_after = verdict(rebuild_msgs, rebuild_exc)

    count = port_count()
    status = 'OK' if (accepted == (expect == 'accepted')) else 'FAIL'
    record(f'② {label}', status,
           f'zplane={zplane} PortOnBound={on_bound} ⇒ {detail}；'
           f'Rebuild：{detail_after}；端口数={count}',
           accepted=accepted, accepted_after_rebuild=accepted_after,
           messages=msgs[:2], exception=exc,
           rebuild_messages=rebuild_msgs[:2], rebuild_exception=rebuild_exc,
           port_count=count, expected=expect)


def port_count():
    """尝试用官方查询取端口数（取不到返回字符串说明，不作为判定依据）。"""
    model3d = _app.cst_file.model3d
    solver = getattr(model3d, 'Solver', None)
    if solver is not None:
        try:
            return int(solver.GetNumberOfPorts())
        except Exception as exc:                    # noqa: BLE001
            return f'Solver.GetNumberOfPorts 失败: {type(exc).__name__}: {exc}'
    try:
        return int(model3d.GetNumberOfPorts())
    except Exception as exc:                        # noqa: BLE001
        return f'model3d.GetNumberOfPorts 失败: {type(exc).__name__}: {exc}'


def run_port_probes():
    """② 的四组探针：边界平面（对照）/ 域内部 + True（对照）/ 域内部 + False（修复）/ 拾取端口。"""
    probe_port('P0 边界平面 + PortOnBound=True（对照）', zplane='0',
               on_bound=True, expect='accepted')
    probe_port('P1 域内部 + PortOnBound=True（旧写法）', zplane='0.5',
               on_bound=True, expect='rejected')
    probe_port('P2 域内部 + PortOnBound=False（2026-09-23 修复）', zplane='0.5',
               on_bound=False, expect='accepted')
    probe_port('P3 边界平面 + PortOnBound=False（对照）', zplane='0',
               on_bound=False, expect='accepted')
    # 拾取端口：库当前用法（add_port）在真机上仍应被接受
    check_dialogs('② P4 拾取端口')
    fresh_project(with_box=True, electric_walls=True)
    try:
        _app.pick_clear()
        picked = _app.pick_face_auto(BOX_NAME, points=[(0.5, 0.5, 0.0)],
                                     candidates=('10', '1', '2', '3'))
        picked_count = _app.get_picked_count('face')
    except Exception as err:                        # noqa: BLE001
        picked, picked_count = f'{type(err).__name__}: {err}', None
    try:
        _app.add_port(2, orientation='zmin', port_on_bound=True,
                      clip_picked_port_to_bound=False)
        exc = None
    except Exception as err:                        # noqa: BLE001
        exc = f'{type(err).__name__}: {err}'
    msgs = messages()
    accepted, detail = verdict(msgs, exc)
    record('② P4 拾取端口 + PortOnBound=True（库既有用法）',
           'OK' if accepted else 'FAIL',
           f'{detail}；拾取={picked}，已选面数={picked_count}',
           accepted=accepted, messages=msgs[:2], exception=exc,
           picked=str(picked), picked_faces=picked_count)


# ------------------------------------------------------------------
# ③ 无参 save
# ------------------------------------------------------------------

def run_save_probes():
    """③ 无参 ``app.save()``：无路径报错、有路径真落盘、关掉后工程完好。"""
    check_dialogs('③ save')

    # 3a 刚 new_project() ⇒ 没有路径 ⇒ 必须响亮地失败（旧行为是静默 no-op）
    fresh_project(with_box=True)
    try:
        result = _app.save()
        status, detail = 'FAIL', f'竟然返回 {result!r}（期望 RuntimeError）'
        exc_text = None
    except RuntimeError as err:
        status, detail = 'OK', f'RuntimeError: {err}'
        exc_text = f'RuntimeError: {err}'
    except Exception as err:                        # noqa: BLE001
        status, detail = 'FAIL', f'抛了 {type(err).__name__}（期望 RuntimeError）: {err}'
        exc_text = f'{type(err).__name__}: {err}'
    record('③a 新建工程后无参 save() ⇒ RuntimeError', status, detail,
           exception=exc_text)

    # 3b 先带路径保存（给出工程路径），改一个参数，再无参 save() ⇒ 必须落盘
    project = _work / 'save_probe.cst'
    try:
        first = save_project(project)
    except Exception as err:                        # noqa: BLE001
        record('③b 无参 save() 落盘', 'FAIL',
               f'准备阶段（带路径保存）就失败了：{type(err).__name__}: {err}')
        return None
    mif = find_mif(project)
    before_ns, size_before, fingerprint_source = project_fingerprint(project)

    _app.para('p4v10_marker', 42)                   # 让工程变脏（默认 log_flag=0）
    time.sleep(1.5)                                 # 拉开时间戳，便于比对

    try:
        returned = _app.save()
        exc_text = None
    except Exception as err:                        # noqa: BLE001
        record('③b 无参 save() 落盘', 'FAIL',
               f'无参 save() 抛异常：{type(err).__name__}: {err}')
        return None

    after_ns, size_after, _ = project_fingerprint(project)
    ok = (returned == os.path.abspath(str(project))
          and after_ns is not None and before_ns is not None and after_ns > before_ns)
    record('③b 无参 save() 落盘', 'OK' if ok else 'FAIL',
           f'返回 {returned!r}；{Path(fingerprint_source).name} 时间戳 '
           f'{before_ns} → {after_ns}，大小 {size_before} → {size_after}',
           returned=returned, first_save=first, mif=str(mif),
           fingerprint_source=fingerprint_source,
           mtime_before=before_ns, mtime_after=after_ns,
           size_before=size_before, size_after=size_after)

    # 3c 关掉工程与 DE，再开一次：工程完好（参数读得回来）
    if _attached_mode:
        # attach 模式：**不能**关用户的 DE，也不能关用户的工程。
        # 改为「关掉我们自己的临时工程 → 重新 attach → 打开刚保存的工程 → 读参数」，
        # 取证强度不降（验证的是「保存出来的文件能不能被重新读回」）。
        _close_own_project(save_first=False)
        time.sleep(1.5)
        prompts = save_prompts()
        if prompts:
            record('③c 保存后重开工程完好', 'UNKNOWN',
                   f'关临时工程时出现「保存更改」类弹窗（不点会阻塞）：'
                   f'{[p["title"] for p in prompts]}')
            return project
        try:
            reopened = setup_attach(_attach_pid, str(project))
            value = reopened.get_parameter('p4v10_marker')
            ok = float(value) == 42.0
            record('③c 保存后重开工程完好', 'OK' if ok else 'FAIL',
                   f'attach 重开后打开 {project}，读到 p4v10_marker={value!r}'
                   f'（期望 42）；用户的工程未被关闭', reopened_value=value)
        except Exception as err:                    # noqa: BLE001
            record('③c 保存后重开工程完好', 'FAIL',
                   f'重新 attach/打开失败：{type(err).__name__}: {err}')
            return None
        # ④ 继续借用同一个会话
        _reattach_for_phase4()
        return project

    try:
        _app.close()
    except Exception as err:                        # noqa: BLE001
        record('③c 保存后 close() 工程完好', 'FAIL',
               f'close() 抛异常：{type(err).__name__}: {err}')
        return None
    prompts = save_prompts()
    if prompts:
        record('③c 保存后 close() 工程完好', 'FAIL',
               f'close() 之后出现「保存更改」类弹窗（不该有）：'
               f'{[p["title"] for p in prompts]}')
        return None
    time.sleep(2.0)
    try:
        reopened = setup_plain(str(project))
        value = reopened.get_parameter('p4v10_marker')
        ok = float(value) == 42.0
        record('③c 保存后 close() 工程完好', 'OK' if ok else 'FAIL',
               f'重新打开 {project} 读到 p4v10_marker={value!r}（期望 42）',
               reopened_value=value)
        try:
            reopened.close()
        except Exception:                           # noqa: BLE001
            pass
    except Exception as err:                        # noqa: BLE001
        record('③c 保存后 close() 工程完好', 'FAIL',
               f'重新打开失败：{type(err).__name__}: {err}')
        return None
    return project


def setup_plain(path):
    """新建一个独立的 ``setup(path)`` 实例（用于「重开工程」取证）。"""
    from cst_solver import setup
    return setup(path)


def setup_attach(pid, path=None):
    """attach 到用户已在运行的 DE（借用许可证，**不**新建会话）。"""
    from cst_solver import setup
    return setup.attach(pid=pid, filename=path)


def _reattach_for_phase4():
    """③c 之后重新 attach 到同一个 DE，供第 ④ 项继续用（attach 模式专用）。"""
    global _app, _own_project_started
    _app = setup_attach(_attach_pid)
    _own_project_started = False                    # 刚 attach 绑定的是用户的工程


# ------------------------------------------------------------------
# ④ get_parameter
# ------------------------------------------------------------------

READERS = ('RestoreDoubleParameter', 'RestoreParameter',
           'RestoreParameterExpression')


def raw_read(model3d, reader, name):
    """调用一个官方读取接口，返回 ``'值'`` 或 ``'<异常 ...>'``。"""
    method = getattr(model3d, reader, None)
    if method is None:
        return '<该接口不存在>'
    try:
        return repr(method(f'{name}'))
    except Exception as exc:                        # noqa: BLE001
        return f'<异常 {type(exc).__name__}: {exc}>'


def run_parameter_probes():
    """④ ``get_parameter()`` 读回数值/表达式参数 + 旧写法的真机表现。"""
    global _app
    if not _attached_mode:
        from cst_solver import setup
        check_dialogs('④ get_parameter')
        # ③c 把上一个 DE 关掉了（那是「关掉后重开检查工程完好」的一部分），
        # 这里重新开一个干净的 DE 继续第 ④ 项。
        _app = setup()
    fresh_project(with_box=False)
    model3d = _app.cst_file.model3d

    _app.para('p4v10_num', 1.5)
    _app.expression('p4v10_expr', '2*p4v10_num')
    _app.para('p4v10_plain', '3.25')

    exists = {}
    for name in ('p4v10_num', 'p4v10_expr', 'p4v10_plain', 'p4v10_absent'):
        try:
            exists[name] = bool(model3d.DoesParameterExist(name))
        except Exception as exc:                    # noqa: BLE001
            exists[name] = f'<异常 {type(exc).__name__}: {exc}>'
    record('④a DoesParameterExist（修复所依赖的官方查询）',
           'OK' if exists.get('p4v10_num') is True
           and exists.get('p4v10_absent') is False else 'FAIL',
           f'{exists}')

    detail = {}
    for name, expect_kind in (('p4v10_num', '数值 1.5'),
                              ('p4v10_plain', '字符串写的数 3.25'),
                              ('p4v10_expr', '表达式 2*p4v10_num')):
        raw = {r: raw_read(model3d, r, name) for r in READERS}
        try:
            value = _app.get_parameter(name)
            got = f'{value!r} ({type(value).__name__})'
        except Exception as exc:                    # noqa: BLE001
            got = f'<异常 {type(exc).__name__}: {exc}>'
        detail[name] = {'expect': expect_kind, 'raw_readers': raw,
                        'get_parameter': got}
        print(f'    {name}（{expect_kind}）：get_parameter={got}；'
              f'原始接口={raw}', flush=True)

    numeric_ok = detail['p4v10_num']['get_parameter'].startswith('1.5 (float)')
    record('④b get_parameter 读数值参数', 'OK' if numeric_ok else 'FAIL',
           detail['p4v10_num']['get_parameter'], raw=detail['p4v10_num']['raw_readers'])
    record('④c get_parameter 读表达式参数', 'UNKNOWN',
           detail['p4v10_expr']['get_parameter'],
           note='记录真机行为（RestoreDoubleParameter 对表达式是否求值）',
           raw=detail['p4v10_expr']['raw_readers'])
    record('④d get_parameter 读「字符串写的数」', 'UNKNOWN',
           detail['p4v10_plain']['get_parameter'],
           raw=detail['p4v10_plain']['raw_readers'])

    # 不存在的参数 ⇒ KeyError
    try:
        value = _app.get_parameter('p4v10_absent')
        status, text = 'FAIL', f'竟然返回 {value!r}（期望 KeyError）'
    except KeyError as err:
        status, text = 'OK', f'KeyError: {err}'
    except Exception as err:                        # noqa: BLE001
        status, text = 'FAIL', f'抛了 {type(err).__name__}: {err}'
    record('④e get_parameter 读不存在的参数 ⇒ KeyError', status, text)

    # 取证：旧写法 model3d.GetParameter() 在真机上到底怎样
    old = raw_read(model3d, 'GetParameter', 'p4v10_num')
    record('④f 取证：旧写法 model3d.GetParameter() 的真机表现',
           'OK' if old.startswith('<异常') else 'UNKNOWN',
           f'GetParameter("p4v10_num") ⇒ {old}',
           note='若为 <异常> ⇒ 旧写法在真机上必然失败（与离线推断一致）')

    # 读回来之后收摊（attach 模式只关我们自己的临时工程，绝不碰用户的）
    if _attached_mode:
        _close_own_project(save_first=True)
    else:
        try:
            _app.close()
        except Exception:                               # noqa: BLE001
            pass


# ------------------------------------------------------------------
# ⑤ 路径入口守卫（附加）
# ------------------------------------------------------------------

def run_path_guard_probes(project_path):
    """⑤ 不存在 / 是目录 ⇒ 立刻失败且不新建 DE（真机版）。"""
    check_dialogs('⑤ 路径守卫')
    # 本项**不需要**任何 CST 会话（也不该需要）：两个入口都应在**新建 DE 之前**
    # 就抛错。所以即使别的相位因「DE 正忙」没跑，这一项照样能取证。
    del project_path                                  # 仅为保持签名；此处不用
    before = design_environment_query()
    missing = _work / 'no_such_project.cst'
    case = ('setup(不存在的工程)', str(missing), FileNotFoundError)
    for label, target, expected in (case, ('setup(目录)', str(_work), IsADirectoryError)):
        try:
            instance = setup_plain(target)
            record(f'⑤ {label}', 'FAIL',
                   f'竟然成功了（返回 {instance!r}，期望 {expected.__name__}）')
            try:
                instance.close()
            except Exception:                       # noqa: BLE001
                pass
        except expected as err:
            after = design_environment_query()
            unchanged = (after['pids'] == before['pids'])
            record(f'⑤ {label}', 'OK' if unchanged else 'FAIL',
                   f'{type(err).__name__}: {str(err)[:200]}；'
                   f'DE 集合 {before["pids"]} → {after["pids"]}'
                   f'（{"未新建" if unchanged else "!! 被改动了"}）',
                   exception=f'{type(err).__name__}: {err}',
                   de_before=before['pids'], de_after=after['pids'])
        except Exception as err:                    # noqa: BLE001
            record(f'⑤ {label}', 'FAIL',
                   f'抛了 {type(err).__name__}（期望 {expected.__name__}）: {err}')


# ------------------------------------------------------------------
# main
# ------------------------------------------------------------------

def main(argv):
    global _app, _work, _baseline, _attached_mode, _attach_pid
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    keep = '--keep' in argv
    attach_pid = None
    if '--attach' in argv:
        attach_pid = int(argv[argv.index('--attach') + 1])
    _attached_mode = attach_pid is not None
    _attach_pid = attach_pid

    from cst_solver import setup

    _work = Path(tempfile.mkdtemp(prefix='p4v10_'))
    print(f'临时工作目录：{_work}', flush=True)
    print(f'=== 跑之前的 CST 窗口 ===\n{describe_windows()}', flush=True)

    # ⚠️ 必须在拿基线**之前**把 CST 库塞进 sys.path，否则基线是空集合，
    # 收尾时会拿「用户自己开着的会话」当本次新建的 DE 去关（实测差点关掉 pid 36472）
    importable = make_cst_importable()
    baseline_pids, baseline_reason = cst_pids()
    if baseline_pids is None:
        _baseline = set()
        print(f'⚠️ DE 清点不可用（{baseline_reason}）：收尾时**不做任何关闭动作**',
              flush=True)
    else:
        _baseline = set(baseline_pids)
    print(f'基线 DE：{sorted(_baseline)}（cst.interface 是否可用：{importable}）',
          flush=True)

    project_path = None
    if attach_pid is None and _baseline:
        print(f'⚠️ 检测到已有 CST 会话 {sorted(_baseline)} 正开着。\n'
              f'   本机许可证（CST registry: 27075@localhost）是**单份**的，'
              f'新建 DE 极可能报 EXITCODE_NOLICENSE / DesignEnvironmentStartupError。\n'
              f'   • 若那个会话是你自己在用/在跑求解 ⇒ 请等它结束、或关掉它再跑本脚本；\n'
              f'   • 若你确实要借用它 ⇒ 加 --attach <pid>（探针会在该会话里新建空白工程，'
              f'脚本绝不关闭它）。', flush=True)
    try:
        with guard('新建 DesignEnvironment', timeout=240):
            if attach_pid is not None:
                _app = setup.attach(pid=attach_pid)
            else:
                _app = setup()
        record('准备：建立 CST 会话', 'OK',
               f'attach pid={attach_pid}' if attach_pid is not None
               else f'新建 DE；基线 {sorted(_baseline)}')
    except Exception:                                   # noqa: BLE001
        record('准备：建立 CST 会话', 'FAIL', traceback.format_exc(limit=4))
        _app = None
        if attach_pid is None:
            print(f'\n💡 若报的是 `EXITCODE_NOLICENSE` / '
                  f'`DesignEnvironmentStartupError ... is gone`：\n'
                  f'   那是许可证被 {sorted(_baseline) or "其它会话"} 占用了，'
                  f'不是这些缺陷本身的问题。\n'
                  f'   关掉那个会话后重跑，或用 --attach <pid> 借用它。', flush=True)

    # 预检：借来的 DE 里若还有求解在跑，`new_project()` 会失败甚至挂死
    # （2026-09-23 实测）⇒ 不取证，也别把环境问题记成四条 FAIL。
    if _app is not None:
        hint = busy_de_hint(attach_pid)
        if hint:
            print(f'!! {hint}', flush=True)
            record('预检：目标 DE 是否空闲', 'UNKNOWN', hint)
            _app = None

    phases = [('① 背景探针', run_background_probes, 900),
              ('② 端口探针', run_port_probes, 900),
              ('③ save 探针', None, 600),
              ('④ 参数探针', run_parameter_probes, 600)]
    for label, function, timeout in phases:
        if _app is None:
            record(label, 'UNKNOWN',
                   '没有可用且空闲的 CST 会话（许可证被占用，或借来的 DE 正在跑求解）'
                   '⇒ 这一项**未取证**，不代表缺陷仍在')
            continue
        try:
            with guard(label, timeout=timeout):
                if label == '③ save 探针':
                    project_path = run_save_probes()
                else:
                    function()
        except Exception:                               # noqa: BLE001
            record(label, 'FAIL', traceback.format_exc(limit=4))

    try:
        # 收尾：先把当前工程落盘（避免关闭时弹「是否保存更改」），再收摊
        if _app is not None:
            if _attached_mode:
                # attach 模式：只关**我们自己新建的**那个临时空白工程。
                # 绝不调用 _app.close()（那只是解除引用，会让临时工程留在用户窗口里），
                # 更不会去碰用户原本打开的工程。
                _close_own_project(save_first=True)
            elif getattr(_app, 'cst_file', None) is not None:
                try:
                    _app.save(str(_work / 'cleanup.cst'),
                              include_results=False, allow_overwrite=True)
                except Exception:                       # noqa: BLE001
                    pass
                if not getattr(_app, '_environment_closed', False):
                    _app.close()
        prompts = save_prompts()
        if prompts:
            print(f'!! 检测到「保存更改」类弹窗（不点会阻塞下一次 CST 调用）：'
                  f'{[p["title"] for p in prompts]}', flush=True)
        if attach_pid is not None:
            print('本次是 attach 到用户的 DE：用户工程与 DE **一个都没关**'
                  '（只关掉了我们自己新建的临时空白工程）', flush=True)
        elif baseline_pids is None:
            print('DE 清点不可用 ⇒ 不做任何关闭动作（保护用户会话）', flush=True)
        elif not _baseline:
            print('!! 基线上一个 DE 都没有 —— 拒绝执行「关掉非基线 DE」'
                  '（否则会把用户自己开着的 CST 关掉）', flush=True)
        else:
            closed = close_extra_design_environments(_baseline, verbose=True)
            record('收尾', 'OK', f'关闭本次新建的 DE：{closed or "无"}')
    except Exception:                                   # noqa: BLE001
        record('收尾', 'FAIL', traceback.format_exc(limit=3))

    try:
        run_path_guard_probes(project_path)
    except Exception:                                   # noqa: BLE001
        record('⑤ 路径入口守卫', 'FAIL', traceback.format_exc(limit=3))
    print(f'=== 跑之后的 CST 窗口 ===\n{describe_windows()}', flush=True)
    print(f'=== 对话框 ===\n{describe_dialogs()}', flush=True)

    evidence = {
        'when': time.strftime('%Y-%m-%d %H:%M:%S'),
        'workdir': str(_work),
        'baseline_de': sorted(_baseline),
        'results': _results,
    }
    out = _work / 'evidence.json'
    try:
        out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2),
                       encoding='utf-8')
        print(f'\n证据 JSON：{out}', flush=True)
    except Exception as exc:                            # noqa: BLE001
        print(f'写证据 JSON 失败：{exc}', flush=True)

    print('\n=== 汇总 ===')
    for entry in _results:
        print(f"{entry['status']:^7}  {entry['item']}")
    counts = {key: len([r for r in _results if r['status'] == key])
              for key in ('OK', 'FAIL', 'UNKNOWN')}
    print(f"\nOK {counts['OK']} / FAIL {counts['FAIL']} / UNKNOWN {counts['UNKNOWN']}")

    if not keep:
        import shutil
        shutil.rmtree(_work, ignore_errors=True)
        print('临时工程已删除（加 --keep 可保留）', flush=True)
    return 1 if counts['FAIL'] else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
