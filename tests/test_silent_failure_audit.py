# -*- coding: utf-8 -*-
r"""
静默失败审计的回归测试（P1 第 4 条）
====================================

守住三件事：

1. **扫描规则本身是对的**：`except` 块里只有 `pass`/`continue`/返回 `None·False·[]·''`/
   只写日志 ⇒ 算「吞掉异常」；一旦 handler 里 `raise`、调 `record_failure(...)`、
   或返回非空值 ⇒ 不算。
2. **登记表与代码同步**：`REGISTRY` 里每一行都必须命中真实站点（防止代码删了、
   登记还留着变成假记录）；未登记的站点会让审计失败。
3. **写/判定路径零容忍**：名字落在写/判定词表里的函数（`get_picked_count`、
   `param_existed`、`_write_synthetic_csv`…）若静默吞异常，必须 `record_failure(...)`
   或在登记表里写明 `risk_ok` 的理由。

运行方式::

    pytest tests/test_silent_failure_audit.py -v
"""

import importlib.util
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_SCRIPT = os.path.join(ROOT, 'scripts', 'audit_silent_failures.py')
_spec = importlib.util.spec_from_file_location('audit_silent_failures', _SCRIPT)
auditor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(auditor)


# ============================================================
# 1. 扫描规则
# ============================================================

def _handlers(source):
    import ast
    tree = ast.parse(source)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            out.extend(node.handlers)
    return out


@pytest.mark.parametrize('body', [
    'pass',
    'continue',
    'return None',
    'return False',
    'return []',
    "return ''",
    "logging.warning('x')",
    "return None",
])
def test_swallowing_bodies_are_detected(body):
    source = f'def f():\n    for _ in range(1):\n        try:\n            x = 1\n        except Exception:\n            {body}\n'
    handlers = _handlers(source)
    assert handlers and auditor._is_swallowing(handlers[0].body)


def test_registered_and_raising_handlers_are_not_swallowing():
    """handler 里 `record_failure(...)` / `raise` / 返回结构化错误 ⇒ 不算吞异常。"""
    good = [
        "def f():\n    try:\n        x = 1\n    except Exception:\n        record_failure('op', 'code', 'msg')\n        return None\n",
        "def f():\n    try:\n        x = 1\n    except Exception:\n        raise\n",
        "def f():\n    try:\n        x = 1\n    except Exception as exc:\n        return fail_result('code', str(exc))\n",
        "def f():\n    try:\n        x = 1\n    except Exception:\n        return {'ok': False}\n",
    ]
    for source in good:
        handler = _handlers(source)[0]
        assert not auditor._is_swallowing(handler.body), source


def test_risky_detection_is_token_based():
    """写/判定路径按**词**判定：`reset_guard_state` 不该因为含 "set_" 被误判。"""
    assert auditor._is_risky('PickMixin.get_picked_count')
    assert auditor._is_risky('GuardState.param_existed')
    assert auditor._is_risky('FakeBackend._write_synthetic_csv')
    assert auditor._is_risky('ParametersMixin._set_parameter_description')
    assert not auditor._is_risky('GuardState.reset_guard_state')
    assert not auditor._is_risky('read_3d')


# ============================================================
# 2. 登记表与真代码同步
# ============================================================

def test_every_registry_row_matches_a_real_site():
    """登记了但代码里找不到 ⇒ 说明代码变了、登记变假记录，必须删。"""
    result = auditor.evaluate(auditor.scan())
    stale = [problem for problem in result['problems'] if '登记已失效' in problem]
    assert stale == [], '\n'.join(stale)


def test_audit_passes_on_the_current_codebase():
    """当前代码库必须**零问题**：所有吞异常站点都登记过，写路径没有漏网的。"""
    result = auditor.evaluate(auditor.scan())
    assert result['problems'] == [], '\n'.join(result['problems'])
    assert result['counts']['sites'] > 0, '扫描没找到任何站点，说明规则失效了'
    assert result['counts']['risky'] == 0, '写/判定路径上出现了未处理的静默失败'


def test_unregistered_site_is_reported(tmp_path, monkeypatch):
    """反向验证：新增一个未登记的吞异常站点，审计必须报出来。"""
    package = tmp_path / 'fakepkg'
    package.mkdir()
    (package / 'mod.py').write_text(
        'def do_something():\n'
        '    try:\n'
        '        value = compute()\n'
        '    except Exception:\n'
        '        return None\n', encoding='utf-8')
    sites = auditor.scan(packages=('fakepkg',), root=str(tmp_path))
    assert len(sites) == 1
    result = auditor.evaluate(sites, registry={})
    assert any('未登记' in problem for problem in result['problems'])
    # 名字里有 is/do… 不在写路径词表里 ⇒ 不算 risky，但仍然要有登记理由
    assert result['counts']['risky'] == 0


def test_risky_site_without_record_failure_is_reported(tmp_path):
    """反向验证：写路径里的静默失败即使登记了，没有 risk_ok 也要报。"""
    package = tmp_path / 'fakepkg'
    package.mkdir()
    (package / 'mod.py').write_text(
        'def save_thing():\n'
        '    try:\n'
        '        write_it()\n'
        '    except Exception:\n'
        '        pass\n', encoding='utf-8')
    sites = auditor.scan(packages=('fakepkg',), root=str(tmp_path))
    assert sites[0]['risky'] is True
    registry = {'fakepkg/mod.py::save_thing': {'max': 1, 'reason': '随便写的理由'}}
    result = auditor.evaluate(sites, registry=registry)
    assert any('写/判定路径' in problem for problem in result['problems'])
    # 补上 risk_ok 之后必须放行（说明这条规则是可满足的，不是死锁）
    registry['fakepkg/mod.py::save_thing']['risk_ok'] = '这里失败是设计内的分支'
    assert auditor.evaluate(sites, registry=registry)['problems'] == []
