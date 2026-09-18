# -*- coding: utf-8 -*-
"""
`scripts/cst_dialog_guard.py` 的**离线**测试。
=============================================

不打开 CST、不点任何真实窗口：只把 :func:`cst_dialog_guard.list_dialogs`
换成假的对话框数据，验证

* 保存类弹窗（「是否保存更改？」）能被 :func:`save_prompts` 认出来；
* :func:`dismiss_dialogs` 在**按钮不匹配**时**绝不盲点**（返回 ``no_match``）；
* ``prefer`` 默认是「否 / 取消」（= 不保存，与用户手工选择一致）。
"""

import importlib.util
import pathlib

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location('cst_dialog_guard',
                                              _REPO / 'scripts' / 'cst_dialog_guard.py')
guard = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(guard)


def _dialog(title, buttons, pid=1234, process='cstd.exe'):
    """伪造一个对话框 dict（字段与 list_dialogs 一致）。"""
    return {
        'hwnd': 0x1000,
        'pid': pid,
        'process': process,
        'title': title,
        'class': '#32770',
        'visible': True,
        'responding': True,
        'is_dialog': True,
        'owner': 0,
        'buttons': [{'text': text, 'ctrl_id': ctrl_id, 'hwnd': 0x2000 + index}
                    for index, (text, ctrl_id) in enumerate(buttons)],
    }


@pytest.fixture
def fake_dialogs(monkeypatch):
    """把 list_dialogs 换成可注入的假实现。"""
    state = {'dialogs': []}
    monkeypatch.setattr(guard, 'list_dialogs',
                        lambda only_cst=True: list(state['dialogs']))
    return state


def test_save_prompt_recognized_by_title(fake_dialogs):
    """标题含「保存」的弹窗要被认出来。"""
    fake_dialogs['dialogs'] = [_dialog('CST Studio Suite - 保存更改？',
                                       [('是', 6), ('否', 7), ('取消', 2)])]
    prompts = guard.save_prompts()
    assert len(prompts) == 1
    assert prompts[0]['title'].endswith('保存更改？')


def test_save_prompt_recognized_english(fake_dialogs):
    """英文弹窗（unsaved changes）也要认出来。"""
    fake_dialogs['dialogs'] = [_dialog('Save changes to project?',
                                       [('&Yes', 6), ('&No', 7)])]
    assert len(guard.save_prompts()) == 1


def test_ordinary_dialog_is_not_a_save_prompt(fake_dialogs):
    """普通对话框（例如「请输入变量值」）不应被误判成保存弹窗。"""
    fake_dialogs['dialogs'] = [_dialog('请输入变量值', [('确定', 1)])]
    assert guard.save_prompts() == []


def test_describe_dialogs_lists_buttons(fake_dialogs):
    """快照里要有按钮文字（人工排查靠它）。"""
    fake_dialogs['dialogs'] = [_dialog('是否保存更改？', [('是', 6), ('否', 7)])]
    text = guard.describe_dialogs()
    assert '是否保存更改？' in text
    assert "'否'" in text


def test_dismiss_prefers_no(fake_dialogs, monkeypatch):
    """默认 prefer 命中「否」→ 点「否」（不保存），且走 WM_COMMAND。"""
    clicked = []
    monkeypatch.setattr(guard._user32, 'SendMessageW',
                        lambda hwnd, msg, wparam, lparam: clicked.append(
                            (msg, wparam, lparam)))
    fake_dialogs['dialogs'] = [_dialog('是否保存更改？',
                                       [('是', 6), ('否', 7), ('取消', 2)])]
    result = guard.dismiss_dialogs()
    assert result == [{'title': '是否保存更改？', 'action': 'clicked', 'button': '否'}]
    assert clicked == [(guard._WM_COMMAND, guard._IDNO, 0)]


def test_dismiss_never_clicks_unknown_buttons(fake_dialogs, monkeypatch):
    """按钮不匹配时**不点**（避免误毁用户正在编辑的东西）。"""
    clicked = []
    monkeypatch.setattr(guard._user32, 'SendMessageW',
                        lambda *args: clicked.append(args))
    fake_dialogs['dialogs'] = [_dialog('某私有对话框', [('了解更多', 9)])]
    result = guard.dismiss_dialogs()
    assert result[0]['action'] == 'no_match'
    assert clicked == []


def test_check_dialogs_raises_on_visible_dialog(fake_dialogs):
    """有对话框时 check_dialogs 必须抛 CstDialogTimeout（而不是继续跑 CST）。"""
    fake_dialogs['dialogs'] = [_dialog('是否保存更改？', [('否', 7)])]
    with pytest.raises(guard.CstDialogTimeout):
        guard.check_dialogs('build_x')


def test_check_dialogs_silent_when_clean(fake_dialogs):
    """没有对话框时不抛异常，返回空列表。"""
    assert guard.check_dialogs('build_x') == []
