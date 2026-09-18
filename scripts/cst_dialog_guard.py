# -*- coding: utf-8 -*-
"""
CST 窗口/弹窗守卫（真机脚本用）
===============================

为什么需要（P4/V6 教训，2026-09-17）
------------------------------------
CST 在**交互模式**下遇到未定义的参数（例如表达式里出现没登记的 `Ls`）**不会抛异常**，
而是弹出一个「请输入变量值」的**模态对话框** —— 于是 Python 侧的下一次 CST 调用
**永久阻塞**，而纯文本运行的调用方完全看不到发生了什么。

同理，**关闭项目 / 关闭 DesignEnvironment 时** CST 会弹「是否保存更改？」对话框，
没人点它就会一直挂着（2026-09-17 用户实际遇到过）。

所以真机脚本要能：
1. 在跑之前/之后**列出 CST 的顶层窗口**（含对话框），把标题打出来；
2. 用**窗口类名**识别真正的对话框（标准 Win32 对话框类 ``#32770``），
   并枚举它上面的按钮文字（是/否/取消/Yes/No/...），而不是只看进程有没有卡住；
3. 给每个重步骤加**超时看门狗**：超时就抓一次窗口快照并报「疑似模态弹窗」，
   而不是一直等下去；
4. 需要时**显式**关闭已知对话框（默认不点，避免误点掉用户正在操作的窗口）。

实现要点
--------
* ``EnumWindows`` 枚举**所有**顶层窗口（``Get-Process.MainWindowTitle`` 只给主窗口，
  看不到对话框）；
* 用 ``QueryFullProcessImageNameW`` 取进程名（**快**，且带进程名缓存；
  旧实现每个窗口起一次 ``tasklist``，几百个窗口会跑几十秒 —— V6 实测超时）；
* 可选的 ``dismiss()`` 只按**按钮文字白名单**点，且只点 CST 进程的 ``#32770``。

用法::

    from cst_dialog_guard import describe_windows, describe_dialogs, guard

    print(describe_windows())            # 跑之前先看一眼有没有残留弹窗
    print(describe_dialogs())            # 只列对话框 + 按钮
    with guard('build_grin_lens', timeout=300):
        build_grin_lens(app, ...)        # 卡住会在这里抛 TimeoutError 并带上窗口快照

命令行::

    python scripts/cst_dialog_guard.py            # CST 相关窗口快照
    python scripts/cst_dialog_guard.py --all      # 所有顶层窗口
    python scripts/cst_dialog_guard.py --dialogs  # 只列对话框（含按钮文字）
"""

import ctypes
import ctypes.wintypes as wintypes
import threading
from contextlib import contextmanager

__all__ = ['list_windows', 'describe_windows', 'list_dialogs', 'describe_dialogs',
           'save_prompts', 'dismiss_dialogs', 'check_dialogs', 'guard',
           'CstDialogTimeout']

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_DIALOG_CLASS = '#32770'                  # 标准 Win32 对话框 / 消息框类名

# Win32 常量
_GW_OWNER = 4
_WM_COMMAND = 0x0111
_BM_CLICK = 0x00F5
_IDOK, _IDCANCEL, _IDABORT, _IDRETRY, _IDIGNORE, _IDYES, _IDNO = 1, 2, 3, 4, 5, 6, 7

# 英文按钮 → 对话框控件 ID（中文 CST 用的是同一个 ID，只是文字本地化了）
_BUTTON_LABEL_IDS = {
    'ok': _IDOK, '确定': _IDOK, '是': _IDYES, 'yes': _IDYES,
    '否': _IDNO, 'no': _IDNO, '取消': _IDCANCEL, 'cancel': _IDCANCEL,
    '中止': _IDABORT, 'abort': _IDABORT, '重试': _IDRETRY, 'retry': _IDRETRY,
    '忽略': _IDIGNORE, 'ignore': _IDIGNORE,
}

_pid_name_cache = {}

# 显式声明签名：不声明时 HANDLE 会被当成 c_int，64 位下句柄被截断 → 一律失败
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                 wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD)]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def _query_image_name(pid):
    """
    用 ``QueryFullProcessImageNameW`` 取进程名（快）。

    ⚠️ 对**高完整性级别**进程（实测 CST 的 ``cstd.exe``）OpenProcess 会被拒，
    此时返回 ``None``，由 :func:`_refresh_pid_names` 用 ``tasklist`` 兜底。

    :param pid: int
    :return: str|None
    """
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(260)
        buffer = ctypes.create_unicode_buffer(size.value)
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buffer,
                                                ctypes.byref(size)):
            return buffer.value.rsplit('\\', 1)[-1]
    finally:
        _kernel32.CloseHandle(handle)
    return None


def _refresh_pid_names():
    """
    一次 ``tasklist`` 取回**全部** pid→进程名（兜底，避免每窗口一次子进程）。

    :return: None
    """
    import subprocess
    try:
        out = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'],
                             capture_output=True, text=True, timeout=20)
    except Exception:                                     # noqa: BLE001
        return
    for line in out.stdout.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2:
            try:
                _pid_name_cache[int(parts[1])] = parts[0]
            except ValueError:
                continue


def _pid_name(pid):
    """
    进程名（缓存 + ``QueryFullProcessImageNameW`` + ``tasklist`` 兜底）。

    :param pid: int
    :return: str
    """
    if pid in _pid_name_cache:
        return _pid_name_cache[pid]
    name = _query_image_name(pid)
    if name is None:
        _refresh_pid_names()
        name = _pid_name_cache.get(pid)
    if not name:
        name = f'pid{pid}'
    _pid_name_cache[pid] = name
    return name


def _window_text(hwnd):
    """窗口标题。"""
    length = _user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _class_name(hwnd):
    """窗口类名（对话框为 ``#32770``）。"""
    buffer = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def _pid_of(hwnd):
    """窗口所属进程 pid。"""
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _is_cst_process(name):
    """进程名是否是 CST 系（cstd.exe / CSTDCMainController...）。"""
    return 'cst' in name.lower()


def _child_buttons(hwnd):
    """
    枚举对话框上的按钮（类名 ``Button``）。

    :return: list[dict], ``{'text', 'ctrl_id'}``
    """
    buttons = []
    EnumChildProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _callback(child, _lparam):
        if _class_name(child) == 'Button':
            buttons.append({
                'text': _window_text(child),
                'ctrl_id': _user32.GetDlgCtrlID(child),
                'hwnd': child,
            })
        return True

    _user32.EnumChildWindows(hwnd, EnumChildProc(_callback), 0)
    return buttons


def list_windows(only_cst=True):
    """
    枚举顶层窗口（含对话框与消息框）。

    :param only_cst: bool, 只返回进程名里带 ``CST``/``cstd`` 的窗口
    :return: list[dict], ``{'hwnd', 'pid', 'process', 'title', 'class', 'visible',
        'responding', 'is_dialog', 'owner'}``
    """
    windows = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                         wintypes.LPARAM)

    def _callback(hwnd, _lparam):
        pid = _pid_of(hwnd)
        name = _pid_name(pid)
        if only_cst and not _is_cst_process(name):
            return True
        klass = _class_name(hwnd)
        windows.append({
            'hwnd': hwnd,
            'pid': pid,
            'process': name,
            'title': _window_text(hwnd),
            'class': klass,
            'visible': bool(_user32.IsWindowVisible(hwnd)),
            'responding': bool(_user32.IsHungAppWindow(hwnd)) is False,
            'is_dialog': klass == _DIALOG_CLASS,
            'owner': _user32.GetWindow(hwnd, _GW_OWNER),
        })
        return True

    _user32.EnumWindows(EnumWindowsProc(_callback), 0)
    return windows


def describe_windows(only_cst=True):
    """
    人类可读的窗口快照（给日志/证据用）。

    :param only_cst: bool, 只看 CST 相关窗口
    :return: str
    """
    windows = list_windows(only_cst=only_cst)
    if not windows:
        return '（没有 CST 顶层窗口）'
    lines = []
    for window in windows:
        flag = '可见' if window['visible'] else '隐藏'
        state = '响应中' if window['responding'] else '!! 无响应（疑似模态弹窗）!!'
        kind = ' 对话框' if window['is_dialog'] else ''
        title = window['title'] or '（无标题）'
        lines.append(f"  pid={window['pid']} {window['process']}{kind} "
                     f"[{flag}/{state}] {title!r}")
    return '\n'.join(lines)


def list_dialogs(only_cst=True):
    """
    只列**对话框**（类名 ``#32770``），附按钮文字。

    :param only_cst: bool, 只看 CST 进程的对话框
    :return: list[dict], 在 :func:`list_windows` 字段之外多 ``'buttons'``
    """
    dialogs = []
    for window in list_windows(only_cst=only_cst):
        if not window['is_dialog']:
            continue
        window['buttons'] = _child_buttons(window['hwnd']) if window['visible'] else []
        dialogs.append(window)
    return dialogs


_SAVE_KEYWORDS = ('保存', 'save', '未保存', 'unsaved', '更改', 'changes')


def save_prompts(only_cst=True):
    """
    找出「是否保存更改 / 退出前保存」类弹窗（2026-09-17 实测出现过）。

    判定：对话框标题或按钮文字里出现 保存/save/更改/changes 等关键词。
    这类弹窗是**关闭项目或退出 CST 时**出现的，不点就会一直挂着。

    :param only_cst: bool, 只看 CST 进程
    :return: list[dict], 同 :func:`list_dialogs`
    """
    found = []
    for dialog in list_dialogs(only_cst=only_cst):
        haystack = dialog['title'].lower() + ' ' + ' '.join(
            (b['text'] or '').lower() for b in dialog['buttons'])
        if any(word in haystack for word in _SAVE_KEYWORDS):
            found.append(dialog)
    return found


def describe_dialogs(only_cst=True):
    """
    对话框快照（含按钮文字），没有则返回「没有」。

    :param only_cst: bool, 只看 CST 进程
    :return: str
    """
    dialogs = list_dialogs(only_cst=only_cst)
    if not dialogs:
        return '（没有可见的 CST 对话框）'
    lines = []
    for dialog in dialogs:
        state = '响应中' if dialog['responding'] else '无响应'
        lines.append(f"  pid={dialog['pid']} {dialog['process']} [{state}] "
                     f"标题={dialog['title']!r}")
        for button in dialog['buttons']:
            lines.append(f"      按钮: {button['text']!r} (id={button['ctrl_id']})")
        if not dialog['buttons']:
            lines.append('      （没有枚举到按钮 —— 可能是自绘/CST 私有对话框）')
    return '\n'.join(lines)


def dismiss_dialogs(prefer=('否', 'no', '取消', 'cancel'), only_cst=True,
                    require_title=None):
    """
    显式关闭对话框（默认**不调用**，只有脚本明确要求时才点）。

    安全策略：只点 **CST 进程** 的 ``#32770`` 对话框，且只点 ``prefer`` 里
    出现的按钮文字；找不到匹配按钮则**不点**（返回 ``'no_match'``），
    绝不按位置盲点，以免误毁用户正在编辑的东西。

    默认 ``prefer`` 是「否 / No / 取消 / Cancel」 —— 即「不保存」，
    与用户 2026-09-17 手工点掉「是否保存」对话框的选择一致。

    :param prefer: tuple[str], 优先点击的按钮文字（不区分大小写，子串匹配）
    :param only_cst: bool, 只处理 CST 进程的对话框
    :param require_title: str|None, 若给出则只处理标题含该子串的对话框
    :return: list[dict], ``{'title', 'action', 'button'}``
    """
    results = []
    for dialog in list_dialogs(only_cst=only_cst):
        if require_title and require_title not in dialog['title']:
            continue
        choice = None
        for wanted in prefer:
            for button in dialog['buttons']:
                if wanted.lower() in (button['text'] or '').lower():
                    choice = button
                    break
            if choice:
                break
        if choice is None:
            results.append({'title': dialog['title'], 'action': 'no_match',
                            'button': None,
                            'buttons': [b['text'] for b in dialog['buttons']]})
            continue
        # 优先用 WM_COMMAND + 控件 ID（对话框的标准关闭路径）
        if choice['ctrl_id'] in (_IDOK, _IDCANCEL, _IDYES, _IDNO, _IDABORT,
                                 _IDRETRY, _IDIGNORE):
            _user32.SendMessageW(dialog['hwnd'], _WM_COMMAND, choice['ctrl_id'], 0)
        else:
            _user32.SendMessageW(choice['hwnd'], _BM_CLICK, 0, 0)
        results.append({'title': dialog['title'], 'action': 'clicked',
                        'button': choice['text']})
    return results


def check_dialogs(label='', only_cst=True):
    """
    断言式检查：有可见对话框就 ``raise CstDialogTimeout``（脚本前置/后置调用）。

    :param label: str, 步骤名（进错误信息）
    :param only_cst: bool, 只看 CST 进程
    :return: list[dict], 为空表示干净
    """
    dialogs = list_dialogs(only_cst=only_cst)
    if dialogs:
        raise CstDialogTimeout(
            f'步骤「{label}」发现 CST 弹窗 —— 脚本若继续调用 CST 会永久阻塞。\n'
            f'  当前对话框：\n{describe_dialogs(only_cst=only_cst)}\n'
            f'  处理：人工点掉对话框，或确认后用 dismiss_dialogs() 关闭。')
    return dialogs


class CstDialogTimeout(TimeoutError):
    """重步骤超时：多半是 CST 弹了模态对话框（附窗口快照）。"""


@contextmanager
def guard(label, timeout=300.0, poll=1.0):
    """
    给一个重步骤加超时看门狗；超时则抓窗口快照并抛 :class:`CstDialogTimeout`。

    ⚠️ 看门狗**不能中断**已经卡在 CST 里的调用（线程无法强杀），
    它的作用是让脚本**尽快报出**「哪一步卡了、当时 CST 有哪些窗口」，
    而不是无声等待。看到这个异常时，请人工检查 CST 窗口并关掉对话框。

    :param label: str, 步骤名（进错误信息）
    :param timeout: float, 超时秒数
    :param poll: float, 轮询间隔（保留参数，兼容旧调用）
    """
    done = threading.Event()
    timed_out = threading.Event()

    def _watchdog():
        if not done.wait(timeout):
            timed_out.set()

    watcher = threading.Thread(target=_watchdog, daemon=True)
    watcher.start()
    try:
        yield
    except BaseException:
        raise
    finally:
        done.set()
    if timed_out.is_set():
        raise CstDialogTimeout(
            f'步骤「{label}」超过 {timeout:.0f}s 未返回 —— 很可能是 CST 弹了'
            f'模态对话框（例如未定义参数时询问「请输入变量值」、关闭时询问「是否保存」）。\n'
            f'  当前 CST 对话框：\n{describe_dialogs()}\n'
            f'  当前 CST 窗口：\n{describe_windows()}\n'
            f'  处理：关掉 CST 里的对话框，并补齐缺失的 CST 参数后重跑。')


def _main(argv):
    """命令行快照（给人工排查/证据用）。"""
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print('=== CST 对话框 ===')
    print(describe_dialogs())
    prompts = save_prompts()
    if prompts:
        print('  !! 检测到「保存更改」类弹窗，不点会阻塞后续 CST 调用：')
        for prompt in prompts:
            print(f"     {prompt['title']!r} 按钮={[b['text'] for b in prompt['buttons']]}")
    print()
    if '--dialogs' in argv:
        return 0
    print('=== CST 顶层窗口 ===')
    print(describe_windows(only_cst='--all' not in argv))
    if '--dismiss' in argv:
        print()
        print('=== 关闭对话框（prefer=否/取消）===')
        for result in dismiss_dialogs():
            print(f"  {result}")
    return 0


if __name__ == '__main__':
    import sys
    raise SystemExit(_main(sys.argv[1:]))
