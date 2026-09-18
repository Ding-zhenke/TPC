# -*- coding: utf-8 -*-
r"""
模板的**参数登记完整性**（P5/P0 迁移取证发现的一类真缺陷）
=======================================================

背景（2026-09-17，做 P0 notebook 迁移验收时发现）
-------------------------------------------------
旧 notebook 的馈源有**两个族**，各自引用不同的 CST 参数：

| 族 | 探针 | 引用的参数 | 铜波导 x 范围 |
|---|---|---|---|
| AB 型椭圆探针（`feed1`） | `build_ab_elliptical_feed` | `x0 / wf1 / lf1 / lf2 / lf3` | `[-lf1-lf2-lf3, -lf1]` |
| BA 型渐变探针（`feed2`） | `build_ba_tapered_feed` | `x01 / wf2 / lf4 / lf5` | `[-lf5-lf6-lf4, -lf4]`（**还要 `lf6`**） |

而两个模板此前**只登记自己默认族**的参数：

* `StraightWaveguide(feed_type='ba_tapered')` ⇒ BA 探针引用未定义的 `wf2/lf4/lf5`；
* `UnitAntenna()` 的波导用 AB 范围 `[-lf1-lf2-lf3, -lf1]` ⇒ 引用未登记的 `lf1/lf2/lf3`。

**为什么这很危险**：CST 遇到未定义参数会弹「请输入变量值」**模态对话框把脚本永久挂住**
（不是抛异常，见 P4/V6 的 Rbig/Ls 教训）。而这两个洞当时**被模板 `tmp.cst` 自带的
遗留参数掩盖了**（该模板其实不干净，里面有 lf1..lf6/wf1/wf2 等旧工程参数，见 P4 §8.7）
—— 一旦换用干净模板就会炸。

本文件把"引用的标识符必须都已登记"变成机器可查的一条规矩。

运行方式::

    pytest tests/test_template_param_registration.py -v
"""

import os
import re
import sys
import warnings

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _Recorder:
    """记录 `para` 等调用的假 app。"""

    def __init__(self):
        self.calls = []

    def __getattr__(self, item):
        def _f(*a, **k):
            self.calls.append((item, a, k))
            return None
        return _f

    def registered(self):
        return {c[1][0] for c in self.calls if c[0] == 'para'}

    def identifiers(self):
        """**表达式**里出现的标识符（含运算符的字符串才算表达式）。

        ⚠️ 不能把所有字符串都算进来：实体名（`feed2`、`wg1`、`feed2_epc`…）也是
        字符串，会把它们误判成"未登记参数"。表达式（`e2/2+wf1/2`、`-lf5-lf6-lf4`）
        一定含运算符，实体名不会 —— 用这一条区分。
        """
        found = set()
        for _op, args, kwargs in self.calls:
            for value in list(args) + list(kwargs.values()):
                for text in _strings(value):
                    if not re.search(r'[-+*/()^]', text):
                        continue
                    found.update(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', text))
        return found


def _strings(value):
    """把实参里所有字符串抠出来（列表/元组/字典都递归）。"""
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_strings(item))
        return out
    if isinstance(value, dict):
        out = []
        for item in value.values():
            out.extend(_strings(item))
        return out
    return []


#: 每次下发**本来就该在**的 CST 内建/全局名字（不算"遗漏登记"）
BUILTIN = {
    'h', 'a', 'e1', 'e2', 'component1', 'component2', 'curve1', 'Vacuum',
    'Silicon', 'lossy', 'Copper', 'annealed', 'PEC', 'and', 'or', 'not',
    'pi', 'sqr', 'sind', 'cosd', 'tand', 'int', 'abs', 'min', 'max',
    'Lin', 'LinInterpolate', 'True', 'False', 'None',
}

#: 各馈源族**必须**被登记的参数（取自两个 builder 的 docstring 与几何表达式）
FEED_PARAMS = {
    'ab_elliptical': {'x0', 'wf1', 'lf1', 'lf2', 'lf3'},
    'ba_tapered': {'x01', 'wf2', 'lf4', 'lf5'},
}
#: BA 族铜波导的 x 范围引用（`MULTIPORT_WG_X_MIN/MAX`）
BA_WAVEGUIDE_PARAMS = {'lf4', 'lf5', 'lf6'}


def _build_antenna(feed_type, **kwargs):
    from topo_templates import UnitAntenna
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return UnitAntenna(feed_type=feed_type, **kwargs)


def _build_waveguide_template(feed_type, **kwargs):
    from topo_templates import StraightWaveguide
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return StraightWaveguide(feed_type=feed_type, **kwargs)


# ============================================================
# 1. 直波导模板：两个馈源族都要能选中并登记齐全
# ============================================================

@pytest.mark.parametrize('feed_type', ('ab_elliptical', 'ba_tapered'))
def test_straight_waveguide_registers_the_selected_feed_family(feed_type):
    template = _build_waveguide_template(feed_type)
    app = _Recorder()
    template.app = app
    template._define_all_params()

    registered = app.registered()
    need = set(FEED_PARAMS[feed_type])
    if feed_type == 'ba_tapered':
        need |= BA_WAVEGUIDE_PARAMS          # 波导 x 范围引用 lf5/lf6/lf4
    missing = sorted(n for n in need if n not in registered)
    assert not missing, f'{feed_type} 缺登记：{missing}（CST 会弹模态框挂住）'


def test_straight_waveguide_ba_feed_uses_the_ba_waveguide_range():
    """BA 族的波导范围必须是 `[-lf5-lf6-lf4, -lf4]`（不是 AB 的 lf1/lf2/lf3）。"""
    template = _build_waveguide_template('ba_tapered')
    app = _Recorder()
    template.app = app
    template._define_all_params()          # 登记参数（含 lf6）
    from topo_modeler.builders import build_multiport_waveguide
    info = build_multiport_waveguide(app, name='wg1')
    assert (info['x_min'], info['x_max']) == ('-lf5-lf6-lf4', '-lf4')
    assert 'lf6' in app.registered(), '波导范围引用 lf6 ⇒ 必须登记'


# ============================================================
# 2. 天线模板：波导用 AB 范围 ⇒ 必须登记 lf1/lf2/lf3
# ============================================================

def test_unit_antenna_registers_the_ba_feed_family():
    template = _build_antenna('ba_tapered')
    app = _Recorder()
    template.app = app
    template._define_all_params()
    missing = sorted(FEED_PARAMS['ba_tapered'] - app.registered())
    assert not missing, f'BA 探针引用未登记参数：{missing}'


def test_unit_antenna_registers_the_waveguide_range_params():
    """
    `UnitAntenna` 的波导是 `build_waveguide(name='wg1')`，默认 x 范围
    `[-lf1-lf2-lf3, -lf1]` ⇒ **lf1/lf2/lf3 必须登记**。

    这条是 2026-09-17 的真缺陷回归：此前它们没登记，只是靠模板 `tmp.cst`
    自带的遗留参数才没报错（换干净模板就会弹模态框挂住）。
    """
    template = _build_antenna('ba_tapered')
    app = _Recorder()
    template.app = app
    template._define_all_params()
    registered = app.registered()
    missing = sorted({'lf1', 'lf2', 'lf3'} - registered)
    assert not missing, f'波导范围引用未登记参数：{missing}'


# ============================================================
# 4. 馈源族覆盖入口 `feed_params`（2026-09-17 新增）
# ============================================================

def test_antenna_feed_params_override_the_hardcoded_values():
    """
    参考里 `lf2` = 3 / 0.2、`lf5` = 3.0 / 0.2 / 0.45 都不统一，
    而这些值此前在模板里是**写死**的 ⇒ 那些模型复现不了。
    `feed_params` 就是覆盖入口（P0 迁移表里 2 个 notebook 靠它才等价）。
    """
    template = _build_antenna('ba_tapered', feed_params={'lf5': 0.2})
    app = _Recorder()
    template.app = app
    template._define_all_params()
    assert app.registered()  # 有登记
    values = {c[1][0]: c[1][1] for c in app.calls if c[0] == 'para'}
    assert values['lf5'] == 0.2, values.get('lf5')


def test_antenna_ab_family_feed_params_are_overridable():
    template = _build_antenna('ab_elliptical',
                              feed_params={'x0': 5, 'wf1': 0.3, 'lf2': 0.2})
    app = _Recorder()
    template.app = app
    template._define_all_params()
    values = {c[1][0]: c[1][1] for c in app.calls if c[0] == 'para'}
    assert (values['x0'], values['wf1'], values['lf2']) == (5, 0.3, 0.2)


def test_waveguide_ba_family_feed_params_are_overridable():
    template = _build_waveguide_template('ba_tapered',
                                         feed_params={'lf6': 0.5, 'wf2': 0.3})
    app = _Recorder()
    template.app = app
    template._define_all_params()
    values = {c[1][0]: c[1][1] for c in app.calls if c[0] == 'para'}
    assert (values['lf6'], values['wf2']) == (0.5, 0.3)


def test_unknown_feed_param_name_is_rejected():
    """写错的键名必须**报错**：静默忽略等于"改了参数但没生效"。"""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with pytest.raises(ValueError, match='未知参数名'):
            _build_antenna('ba_tapered', feed_params={'lf55': 0.2})
        with pytest.raises(ValueError, match='未知参数名'):
            _build_waveguide_template('ba_tapered', feed_params={'nope': 1})


def test_feed_params_are_not_accepted_for_the_ab_family_on_waveguide():
    """直波导的 AB 族参数请用同名构造参数（`feed_params` 对 AB 族没有可覆盖项）。"""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with pytest.raises(ValueError, match='未知参数名'):
            _build_waveguide_template('ab_elliptical', feed_params={'lf5': 0.2})

@pytest.mark.parametrize('builder', ('antenna', 'waveguide_ab', 'waveguide_ba',
                                     'multiport'))
def test_no_unregistered_identifier_leaks_into_geometry(builder):
    """
    把 `_define_all_params()` + 馈源/波导构建器跑一遍（假 app），
    检查表达式里出现的标识符**要么已登记、要么是内建/全局**。

    这是本文件的主护栏：新加几何时若引用了没登记的参数，这里会红。
    """
    from topo_modeler.builders import build_feed, build_multiport_waveguide, build_waveguide

    if builder == 'antenna':
        template = _build_antenna('ba_tapered')
    elif builder == 'waveguide_ab':
        template = _build_waveguide_template('ab_elliptical')
    elif builder == 'waveguide_ba':
        template = _build_waveguide_template('ba_tapered')
    else:
        from topo_templates import MultiPortAntenna
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            template = MultiPortAntenna(straight_length=4, arm_length=3)

    app = _Recorder()
    template.app = app
    template._define_all_params()

    # 只跑探针/波导这两段（几何主体已经在别的测试里真机验过）
    if builder == 'antenna':
        build_feed(app, feed_type='ba_tapered', name='feed2')
        build_waveguide(app, name='wg1')
    elif builder == 'waveguide_ab':
        build_feed(app, feed_type='ab_elliptical', name='feed1')
        build_waveguide(app, name='wg1')
    elif builder == 'waveguide_ba':
        build_feed(app, feed_type='ba_tapered', name='feed2')
        build_multiport_waveguide(app, name='wg1')
    else:
        # 多端口天线是**双馈源**：两族都要建
        build_feed(app, feed_type='ab_elliptical', name='feed1')
        build_feed(app, feed_type='ba_tapered', name='feed2')
        build_waveguide(app, name='wg1')
        build_multiport_waveguide(app, name='wg2')

    # ⚠️ 已登记集合必须在**跑完 builder 之后**取：有些参数是 builder 内部登记的
    #    （例如 BA 探针的 `tx1/ty1`）。只按模板那一份快照会误报。
    registered = app.registered()
    used = app.identifiers()
    suspects = {n for n in used
                if re.fullmatch(r'[a-z][a-z0-9_]{1,}', n)
                and n not in registered and n not in BUILTIN}
    assert not suspects, (
        f'{builder}：表达式里引用了未登记的标识符 {sorted(suspects)} '
        f'—— CST 会弹「请输入变量值」模态框挂住；请先在 _define_all_params() 里登记')
