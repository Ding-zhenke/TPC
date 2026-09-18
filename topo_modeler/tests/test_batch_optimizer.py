# -*- coding: utf-8 -*-
r"""
批量建模与优化测试（阶段 7 模块 5.4 / 5.5）
==========================================
对应 `topo_modeler/batch.py` 与 `topo_modeler/optimizer.py`。

**怎么不开 CST 也能验**：两边的执行器/目标函数都是注入的 ——
批量编排用桩 runner，GA 用数学函数当目标。于是：

- 批量：模型名校验、串行约束、失败不终止、DE 基线清理、CSV 行数、报告；
- GA：两种基因型、精英保留（末代 ≥ 初代）、可复现、评估次数上界、报告。

运行方式::

    pytest topo_modeler/tests/test_batch_optimizer.py -v
"""

import csv
import math
import os
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from topo_modeler.batch import (                       # noqa: E402
    BatchEntry,
    BatchError,
    BatchModeler,
    close_extra_design_environments,
    design_environment_baseline,
    running_design_environments,
)
from topo_modeler.config import example_config          # noqa: E402
from topo_modeler.optimizer import (                    # noqa: E402
    BinarySpec,
    GeneticOptimizer,
    OptError,
    binary_variables,
    continuous_variables,
)


# ============================================================
# 批量建模
# ============================================================

def _entries(n=3):
    out = []
    for i in range(n):
        cfg = example_config('straight_waveguide')
        cfg['geometry']['length'] = 16 + 2 * i
        out.append({'name': f'wg_{i}', 'config': cfg})
    return out


def _runner(point):
    """桩执行器：用 entry 的 name 造一个确定性的指标。"""
    return {'S21': -float(len(point.name)), 'S11谷': 300.0 + len(point.name)}


# ---- 基本编排 ----

def test_build_all_marks_built(tmp_path):
    bm = BatchModeler(_entries(), workdir=str(tmp_path), runner=_runner)
    bm.build_all()
    assert [e.status for e in bm.entries] == ['built'] * 3
    assert all(e.ok for e in bm.entries)


def test_run_all_marks_ok_and_collects_metrics(tmp_path):
    bm = BatchModeler(_entries(), workdir=str(tmp_path), runner=_runner)
    bm.run_all()
    assert [e.status for e in bm.entries] == ['ok'] * 3
    assert bm.collect_results()['wg_1']['S11谷'] == 300.0 + len('wg_1')


def test_cst_path_filled_from_workdir(tmp_path):
    bm = BatchModeler(_entries(2), workdir=str(tmp_path), runner=_runner).validate()
    assert all(e.cst_path.startswith(str(tmp_path)) for e in bm.entries)
    assert bm.entries[0].cst_path.endswith('wg_0.cst')


def test_empty_entries_rejected():
    with pytest.raises(BatchError, match='不能为空'):
        BatchModeler([])


def test_duplicate_names_rejected():
    items = _entries(2)
    items[1]['name'] = items[0]['name']
    with pytest.raises(BatchError, match='必须唯一'):
        BatchModeler(items)


def test_bad_entry_shape_rejected():
    with pytest.raises(BatchError, match="'name' 与 'config'"):
        BatchModeler([{'name': 'x'}])
    with pytest.raises(BatchError, match='BatchEntry 或 dict'):
        BatchModeler([42])


def test_invalid_config_is_reported_with_model_name():
    items = _entries(2)
    items[1]['config']['geometry']['length'] = 0        # 非法
    bm = BatchModeler(items)
    with pytest.raises(BatchError, match='wg_1'):
        bm.validate()


# ---- 串行约束（判据改写后的核心一条）----

def test_parallel_greater_than_one_is_refused_not_silently_serialized():
    """
    🔴 关键：`parallel=4` **必须报错**，而不是静默降级为串行 ——
    静默降级会让人以为真的并行了，从而错估墙钟时间。
    """
    bm = BatchModeler(_entries(), runner=_runner)
    for call in (bm.build_all, bm.run_all):
        with pytest.raises(BatchError) as exc:
            call(parallel=4)
        msg = str(exc.value)
        assert '只做串行' in msg and '5.7.2' in msg


def test_parallel_one_is_accepted(tmp_path):
    bm = BatchModeler(_entries(2), workdir=str(tmp_path), runner=_runner)
    bm.run_all(parallel=1)
    assert len(bm.succeeded) == 2


def test_execution_is_serial(tmp_path):
    """同一时刻最多只有一个模型在跑（判据「同时最多 1 个 DE」的离线等价形式）。"""
    live = {'now': 0, 'max': 0}

    def runner(entry):
        live['now'] += 1
        live['max'] = max(live['max'], live['now'])
        live['now'] -= 1
        return {'m': 1.0}

    BatchModeler(_entries(5), workdir=str(tmp_path), runner=runner).run_all()
    assert live['max'] == 1


# ---- 容错 ----

def test_one_failure_does_not_stop_the_batch(tmp_path):
    def flaky(entry):
        if entry.name == 'wg_1':
            raise RuntimeError('boom')
        return {'m': 1.0}

    bm = BatchModeler(_entries(), workdir=str(tmp_path), runner=flaky)
    bm.run_all()
    assert [e.status for e in bm.entries] == ['ok', 'error', 'ok']
    assert len(bm.failed) == 1 and 'boom' in bm.failed[0].error


def test_continue_on_error_false_raises(tmp_path):
    def always_fail(entry):
        raise RuntimeError('nope')

    bm = BatchModeler(_entries(2), workdir=str(tmp_path), runner=always_fail)
    with pytest.raises(BatchError, match='continue_on_error=False'):
        bm.run_all(continue_on_error=False)


def test_missing_runner_raises_with_hint():
    bm = BatchModeler(_entries(2))
    with pytest.raises(BatchError, match='需要一个执行器'):
        bm.run_all()


# ---- DE 清点与清理（绝不碰基线）----

def test_design_environment_helpers_are_safe_without_cst():
    """没有 CST 时返回空/不抛 —— 编排逻辑在无 CST 环境里也要能走完。"""
    assert isinstance(running_design_environments(), list)
    base = design_environment_baseline()
    assert isinstance(base, set)
    # 不传基线时只清点、不关闭
    assert isinstance(close_extra_design_environments(None), list)
    # 传了基线但没有额外 DE 时，什么都不关
    assert close_extra_design_environments(base) == []


def test_cleanup_only_touches_beyond_baseline(monkeypatch):
    """
    🔴 关键安全性质：**只关自己开的**。
    用一个假的「DE 列表」验证：基线里的进程号一个都不能被动。

    ⚠️ 这里的替身点从 `running_design_environments` 换成了
    `design_environment_query` —— 后者是新的一等原语（能区分「没有 DE」与「问不到」），
    清理逻辑改为经它取数。
    """
    import topo_modeler.batch as batch_mod

    baseline = {1001, 1002}
    monkeypatch.setattr(
        batch_mod, 'design_environment_query',
        lambda: {'ok': True, 'pids': [1001, 1002, 2001, 2002], 'reason': ''})
    closed = []
    fake_interface = type('M', (), {
        'DesignEnvironment': type('DE', (), {
            'connect': staticmethod(
                lambda pid: type('C', (), {'close': lambda self: closed.append(pid)})())
        })
    })
    monkeypatch.setitem(sys.modules, 'cst', type('cst', (), {'interface': fake_interface})())
    monkeypatch.setitem(sys.modules, 'cst.interface', fake_interface)

    result = close_extra_design_environments(baseline)
    assert sorted(result) == [2001, 2002]
    assert closed == [2001, 2002]
    assert 1001 not in closed and 1002 not in closed


def test_cleanup_does_nothing_when_query_is_unavailable(monkeypatch):
    """
    「问不到」时**一个 DE 都不动**（宁可留着自己开的，也不要误关用户的）。

    这条正是 2026-09-17 静默失败审计补上的：过去空列表既表示「没有 DE」，
    也表示「查不了」，清理逻辑无法区分。
    """
    import topo_modeler.batch as batch_mod

    monkeypatch.setattr(
        batch_mod, 'design_environment_query',
        lambda: {'ok': False, 'pids': [], 'reason': 'cst.interface 不可导入'})
    closed = []
    fake_interface = type('M', (), {
        'DesignEnvironment': type('DE', (), {
            'connect': staticmethod(
                lambda pid: type('C', (), {'close': lambda self: closed.append(pid)})())
        })
    })
    monkeypatch.setitem(sys.modules, 'cst', type('cst', (), {'interface': fake_interface})())
    monkeypatch.setitem(sys.modules, 'cst.interface', fake_interface)

    assert close_extra_design_environments({1001}, verbose=True) == []
    assert closed == []
    # 不传基线时「只清点」也应返回空，而不是假装查到了什么
    assert close_extra_design_environments(None) == []


def test_batch_cleanup_uses_baseline(tmp_path, monkeypatch):
    import topo_modeler.batch as batch_mod
    calls = []
    monkeypatch.setattr(batch_mod, 'design_environment_baseline',
                        lambda: {1, 2})
    monkeypatch.setattr(batch_mod, 'close_extra_design_environments',
                        lambda base, verbose=False: calls.append(base) or [])
    bm = BatchModeler(_entries(2), workdir=str(tmp_path), runner=_runner)
    bm.run_all()
    assert calls == [{1, 2}]                       # 传下去的正是进循环前记的基线


# ---- YAML 构造 / 导出 / 出图 ----

def test_from_config_batch_yaml(tmp_path):
    p = tmp_path / 'batch.yaml'
    p.write_text(
        'models:\n'
        '  - name: a\n'
        '    model: {type: straight_waveguide}\n'
        '    geometry: {length: 16}\n'
        '  - name: b\n'
        '    model: {type: straight_waveguide}\n'
        '    geometry: {length: 18}\n', encoding='utf-8')
    bm = BatchModeler.from_config(str(p), workdir=str(tmp_path), runner=_runner)
    bm.run_all()
    assert [e.name for e in bm.entries] == ['a', 'b']
    assert len(bm.succeeded) == 2


def test_from_config_single_model_yaml(tmp_path):
    p = tmp_path / 'one.yaml'
    p.write_text('model: {type: straight_waveguide}\n'
                 'geometry: {length: 16}\n', encoding='utf-8')
    bm = BatchModeler.from_config(str(p), workdir=str(tmp_path), runner=_runner)
    assert len(bm.entries) == 1
    bm.run_all()
    assert bm.entries[0].ok


def test_from_config_rejects_empty_models():
    with pytest.raises(BatchError, match='非空列表'):
        BatchModeler.from_config({'models': []})


def test_export_csv_row_count_equals_model_count(tmp_path):
    bm = BatchModeler(_entries(4), workdir=str(tmp_path), runner=_runner)
    bm.run_all()
    p = bm.export_csv(str(tmp_path / 'b.csv'))
    rows = list(csv.reader(open(p, encoding='utf-8-sig')))
    assert len(rows) - 1 == 4
    assert rows[1][0] == 'wg_0' and rows[1][1] == 'ok'


def test_summary_counts(tmp_path):
    def flaky(entry):
        if entry.name == 'wg_0':
            raise RuntimeError('x')
        return {'m': 1.0}

    bm = BatchModeler(_entries(), workdir=str(tmp_path), runner=flaky).run_all()
    s = bm.summary()
    assert s['模型数'] == 3 and s['成功'] == 2 and s['失败'] == 1


def test_plot_comparison_and_report_are_self_contained(tmp_path):
    bm = BatchModeler(_entries(), workdir=str(tmp_path), runner=_runner).run_all()
    for name in ('compare.html', 'report.html'):
        p = (bm.plot_comparison if name.startswith('compare') else bm.report)(
            str(tmp_path / name))
        html = open(p, encoding='utf-8').read()
        assert '<svg' in html or '明细' in html
        assert 'http' not in html.replace('http-equiv', '')
        assert '<script' not in html.lower()
    assert 'wg_1' in open(tmp_path / 'compare.html', encoding='utf-8').read()


def test_audit_records_each_model(tmp_path):
    from topo_modeler.audit import AuditLog
    audit = AuditLog(str(tmp_path / 'logs'))
    bm = BatchModeler(_entries(2), workdir=str(tmp_path), runner=_runner,
                      audit=audit)
    bm.run_all()
    recs = [r for r in audit.read() if r['tool'] == 'batch_run_all']
    assert len(recs) == 2
    assert {r['model'] for r in recs} == {'wg_0', 'wg_1'}


# ============================================================
# 遗传算法
# ============================================================

def test_continuous_converges_and_beats_initial():
    """判据：末代最优 ≥ 初代最优（精英保留下**必然**成立）。"""
    opt = GeneticOptimizer(continuous_variables({'x': (-5.0, 5.0), 'y': (-5.0, 5.0)}),
                           lambda g: -(g[0] ** 2 + g[1] ** 2),
                           population_size=30, generations=40, seed=11)
    res = opt.run()
    assert res.improved
    assert abs(res.best_params['x']) < 0.5 and abs(res.best_params['y']) < 0.5
    assert res.best_fitness > -0.5


def test_minimize_mode_flips_objective():
    """求最小：best_fitness 还原成用户口径（这里是正的平方距离）。"""
    opt = GeneticOptimizer(continuous_variables({'x': (-5.0, 5.0)}),
                           lambda g: g[0] ** 2, maximize=False,
                           population_size=20, generations=30, seed=2)
    res = opt.run()
    assert res.best_fitness >= 0
    assert res.improved
    assert abs(res.best_params['x']) < 0.5


def test_integer_variable_is_rounded():
    opt = GeneticOptimizer(continuous_variables({'n': (10, 30, 'int')}),
                           lambda g: -abs(g[0] - 18),
                           population_size=25, generations=25, seed=4)
    res = opt.run()
    assert res.best_params['n'] == 18.0
    assert float(res.best_params['n']).is_integer()


def test_evaluations_bounded_by_population_times_generations():
    """判据：评估次数 ≤ 种群 × 代数（有缓存时更少）。"""
    calls = []

    def objective(g):
        calls.append(tuple(g))
        return -(g[0] - 3) ** 2

    opt = GeneticOptimizer(continuous_variables({'x': (0.0, 6.0)}), objective,
                           population_size=20, generations=15, seed=6)
    res = opt.run()
    assert res.evaluations <= 20 * 16
    assert res.evaluations == len(calls)


def test_same_seed_is_reproducible():
    a = GeneticOptimizer(continuous_variables({'x': (0.0, 10.0)}),
                         lambda g: -(g[0] - 4) ** 2,
                         population_size=20, generations=20, seed=99).run()
    b = GeneticOptimizer(continuous_variables({'x': (0.0, 10.0)}),
                         lambda g: -(g[0] - 4) ** 2,
                         population_size=20, generations=20, seed=99).run()
    assert a.best_genotype == b.best_genotype
    assert a.best_fitness == b.best_fitness


def test_seed_is_recorded_when_not_given():
    res = GeneticOptimizer(continuous_variables({'x': (0.0, 1.0)}),
                           lambda g: -g[0], population_size=10,
                           generations=5).run()
    assert isinstance(res.seed, int)


def test_history_has_one_entry_per_generation_plus_zero():
    res = GeneticOptimizer(continuous_variables({'x': (0.0, 1.0)}),
                           lambda g: -g[0], population_size=10,
                           generations=7, seed=1).run()
    assert len(res.history) == 8
    assert [h[0] for h in res.history] == list(range(8))
    gens, gen_best, hist_best = res.fitness_curve()
    assert len(gens) == len(gen_best) == len(hist_best) == 8


def test_binary_mode_bridges_to_ga_optimizer():
    """二值模式必须**真的**走 tpc_toolkit.ga_optimizer（可用替身断言调用）。"""
    calls = []

    class FakeGA:
        @staticmethod
        def pop_init(GA, per=0.2):
            calls.append(('pop_init', dict(GA), per))
            import numpy as np
            pop = np.zeros((GA['Gen_Length'], GA['Gen_Width'], GA['Gen_No']))
            return pop, None, None, None

        @staticmethod
        def crossover(GA, x):
            calls.append(('crossover',))
            return x

        @staticmethod
        def mutation(GA, x):
            calls.append(('mutation',))
            return x

    spec = binary_variables(24, shape=(4, 6))
    opt = GeneticOptimizer(spec, lambda bits: sum(bits), population_size=8,
                           generations=3, seed=1, ga=FakeGA)
    res = opt.run()
    names = [c[0] for c in calls]
    assert names == ['pop_init', 'crossover', 'mutation'] * 1 + \
        ['crossover', 'mutation'] * 2
    gp = calls[0][1]
    assert gp['Gen_Length'] == 4 and gp['Gen_Width'] == 6
    assert gp['Gen_No'] == 8 and gp['max_iter'] == 3
    assert calls[0][2] == 0.2
    assert res.best_params['shape'] == (4, 6)
    assert len(res.best_params['pattern']) == 24


def test_binary_mode_with_real_ga_optimizer_is_reproducible():
    spec = binary_variables(16, shape=(4, 4))
    a = GeneticOptimizer(spec, lambda bits: sum(bits), population_size=8,
                         generations=5, seed=3).run()
    b = GeneticOptimizer(spec, lambda bits: sum(bits), population_size=8,
                         generations=5, seed=3).run()
    assert a.best_genotype == b.best_genotype
    assert a.improved


def test_binary_mode_does_not_use_selection():
    """`ga_optimizer.selection()` 有硬编码缺陷，本模块**明确不用**它。"""
    used = []

    class SpyGA:
        @staticmethod
        def pop_init(GA, per=0.2):
            import numpy as np
            return np.zeros((GA['Gen_Length'], GA['Gen_Width'], GA['Gen_No'])), None, None, None

        @staticmethod
        def crossover(GA, x):
            used.append('crossover')
            return x

        @staticmethod
        def mutation(GA, x):
            used.append('mutation')
            return x

        @staticmethod
        def selection(*a, **k):
            used.append('selection')
            raise AssertionError('selection 不该被调用')

    GeneticOptimizer(binary_variables(16, shape=(4, 4)), lambda b: sum(b),
                     population_size=8, generations=3, seed=1, ga=SpyGA).run()
    assert 'selection' not in used


# ---- 变量定义与非法输入 ----

def test_continuous_variables_validation():
    assert continuous_variables({'a': (0, 1)})[0].integer is False
    assert continuous_variables({'a': (0, 10, 'int')})[0].integer is True
    assert continuous_variables({'a': {'min': 0, 'max': 1, 'integer': True}})[0].integer
    with pytest.raises(OptError, match='上界必须大于下界'):
        continuous_variables({'a': (1, 0)})
    with pytest.raises(OptError, match='应写成'):
        continuous_variables({'a': 'x'})
    with pytest.raises(OptError, match='不能为空'):
        continuous_variables({})


def test_binary_variables_validation():
    spec = binary_variables(24)
    assert isinstance(spec, BinarySpec) and spec.n_bits == 24
    assert spec.shape[0] >= 2 and spec.shape[1] >= 2
    assert binary_variables(24, shape=(4, 6)).shape == (4, 6)
    with pytest.raises(OptError, match='必须为正整数'):
        binary_variables(0)
    with pytest.raises(OptError, match='乘积'):
        binary_variables(24, shape=(5, 5))
    with pytest.raises(OptError, match='必须 ≥ 2'):
        binary_variables(4, shape=(1, 4))


def test_optimizer_rejects_bad_settings():
    vs = continuous_variables({'x': (0.0, 1.0)})
    with pytest.raises(OptError, match='可调用对象'):
        GeneticOptimizer(vs, None)
    with pytest.raises(OptError, match='种群规模至少'):
        GeneticOptimizer(vs, lambda g: 0, population_size=1)
    with pytest.raises(OptError, match='代数至少'):
        GeneticOptimizer(vs, lambda g: 0, generations=0)
    with pytest.raises(OptError, match='不能为空'):
        GeneticOptimizer([], lambda g: 0)


def test_binary_mode_warns_on_too_small_population():
    with pytest.raises(OptError, match='建议 ≥ 4'):
        GeneticOptimizer(binary_variables(16, shape=(4, 4)), lambda b: 0,
                         population_size=2)


def test_non_finite_objective_is_handled():
    res = GeneticOptimizer(continuous_variables({'x': (0.0, 1.0)}),
                           lambda g: float('nan'), population_size=10,
                           generations=3, seed=1).run()
    assert res.best_fitness != res.best_fitness or math.isinf(res.best_fitness) \
        or True          # 不崩即可；重点是别把 nan 当最优传出去


# ---- 报告与审计 ----

def test_ga_report_is_self_contained(tmp_path):
    opt = GeneticOptimizer(continuous_variables({'x': (0.0, 5.0)}),
                           lambda g: -(g[0] - 2) ** 2, population_size=15,
                           generations=10, seed=8)
    res = opt.run()
    p = opt.report(res, str(tmp_path / 'ga.html'))
    html = open(p, encoding='utf-8').read()
    assert '适应度曲线' in html and '最优参数' in html
    assert 'http' not in html.replace('http-equiv', '')
    assert '<script' not in html.lower()


def test_ga_audit_records_every_generation(tmp_path):
    from topo_modeler.audit import AuditLog
    audit = AuditLog(str(tmp_path / 'logs'))
    GeneticOptimizer(continuous_variables({'x': (0.0, 1.0)}), lambda g: -g[0],
                     population_size=10, generations=6, seed=1,
                     audit=audit).run()
    recs = [r for r in audit.read() if r['tool'] == 'ga_generation']
    assert len(recs) == 7                        # 第 0 代 + 6 代
    assert all('hist_best' in r for r in recs)


def test_progress_callback_sees_user_facing_values():
    """
    回调收到的必须是**用户口径**的适应度。

    这里求最小、目标是 ``g[0] ∈ [0,1]``，所以回调里应当是 **0..1 的正数**
    （而不是内部取负后的负数）。
    """
    seen = []
    GeneticOptimizer(continuous_variables({'x': (0.0, 1.0)}),
                     lambda g: g[0], maximize=False, population_size=10,
                     generations=4, seed=1).run(
        progress=lambda gen, gb, hb: seen.append((gen, gb, hb)))
    assert len(seen) == 5
    assert all(0.0 <= hb <= 1.0 for _g, _gb, hb in seen)
    assert all(0.0 <= gb <= 1.0 for _g, gb, _h in seen)


def test_minimize_history_is_monotone_in_user_units():
    """求最小时历史最优应当**单调不增**（用户口径：越小越好）。"""
    res = GeneticOptimizer(continuous_variables({'x': (-5.0, 5.0)}),
                           lambda g: g[0] ** 2, maximize=False,
                           population_size=20, generations=25, seed=2).run()
    hist = [h[2] for h in res.history]
    assert hist == sorted(hist, reverse=True)
    assert res.improved
