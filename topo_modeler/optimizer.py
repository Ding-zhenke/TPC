# -*- coding: utf-8 -*-
r"""
遗传算法优化 —— 与 CST 的桥接（阶段 7 模块 5.5，可选）
=====================================================
把 `tpc_toolkit/ga_optimizer.py` 的算子接到「真实目标函数」上。

⚠️ 计划里的一个前提**不成立**（先说清，免得白做）
------------------------------------------------
计划写：「注意 `tpc_toolkit/ga_optimizer.py` **已存在**独立 GA 实现（不依赖 CST）
—— 本模块应做的是「与 CST 的桥接」，**不是重写 GA**」。

**核对源码后，它和计划的假设不是一回事**：

| 计划假设 | `ga_optimizer` 的实际形态 |
|---|---|
| 输入 `variables={name: (min,max)}` —— **连续变量** | 基因型是 **0/1 二维图案**（`Gen_Length × Gen_Width`），面向**拓扑优化**（每格挖不挖孔） |
| 「传一个 GA 对象」 | `GA` 是 **dict**，键为 `Gen_Length` / `Gen_Width` / `Gen_No` / `max_iter` / `cross_prob` / `mut_prob` |
| `pop_init` 返回种群 | 返回 **4 元组** `(pop, fi, all_pop, all_prob)` |
| `crossover(GA, x)` / `mutation(GA, x)` 对**个体**操作 | 对**整个种群数组** `(r, c, n)` 原地操作（按个体对交换子矩形 / 每位随机翻一位） |
| 随机性可注入 | 用**全局 `np.random`**，要复现必须 `np.random.seed()` |
| `selection` 可直接用 | 它有**硬编码缺陷**（源码自己的 warning）：「保留 2 优 / 替换 3 差」只在 `Gen_No == 4` 时自洽，其它规模行为未定义 ⇒ **本模块不用它** |

所以本模块提供**两条路**，并在代码里写清各自复用了什么、没复用什么：

| 模式 | 基因型 | 复用了 `ga_optimizer` 的什么 |
|---|---|---|
| `mode='continuous'` | 实数向量（每变量一对上下界） | **只借它的思想**（选择/交叉/变异/精英）。实数基因下「交换比特」「翻转比特」没有意义，所以算子自己实现 —— 这不是「重写 GA」，是**换基因型** |
| `mode='binary'` | 0/1 二维图案（**真·桥接**） | **完整复用** `pop_init` / `crossover` / `mutation`（种群级、原地），并用 `np.random.seed()` 对齐随机数 |

两条路的**目标函数都是注入的**（`evaluate(genotype) -> float`），
所以都能**完全离线验收**：给个数学函数就能跑，不需要 CST。

> 📌 这条更正已记入 `docs/next_plan/stages/07` §8。

判据可执行
----------
计划原文：「优化后目标函数值优于初始值」——「优于」在随机算法里**不完全可保证**。
本模块让它在**固定种子下必然成立**：

1. 支持 `seed`；不传也会随机取一个并**写进结果**（复现靠它）；
   二值模式同时 `np.random.seed(seed)`，让 `ga_optimizer` 的随机也受控；
2. **精英保留**：每代把历史最优**原样**带进下一代 ⇒ 末代历史最优 **≥** 初代；
3. `evaluations` 计数 ⇒ 可断言「评估次数 ≤ 种群 × 代数」（有缓存时更少）；
4. 每代最优值曲线记进审计，可事后核对。

用法::

    from topo_modeler.optimizer import GeneticOptimizer, continuous_variables, binary_variables

    # ① 连续参数优化
    opt = GeneticOptimizer(continuous_variables({'length': (10, 30, 'int')}),
                           evaluate=lambda g: -((g[0] - 18) ** 2),
                           population_size=20, generations=30, seed=7)
    res = opt.run()
    res.best_params          # {'length': 18}

    # ② 拓扑图案优化（真正复用 ga_optimizer 的算子）
    opt = GeneticOptimizer(binary_variables(24, shape=(4, 6)),
                           evaluate=lambda bits: sum(bits),      # 换成 CST 适应度即可
                           population_size=8, generations=10, seed=1)
    res = opt.run()
    res.best_params          # {'pattern': [...], 'shape': (4, 6)}

@author: PC
"""

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

__all__ = [
    'GeneticOptimizer',
    'OptResult',
    'OptError',
    'ContinuousVar',
    'BinarySpec',
    'continuous_variables',
    'binary_variables',
]


class OptError(RuntimeError):
    """优化配置非法（变量定义错、目标函数缺失、种群/代数非法…）。"""


# ============================================================
# 变量定义
# ============================================================

@dataclass(frozen=True)
class ContinuousVar:
    """连续变量：``(min, max)``，可选整数约束。"""

    name: str
    lo: float
    hi: float
    integer: bool = False

    def clip(self, value: float) -> float:
        """夹到界内（整数约束时取整）。"""
        v = max(self.lo, min(self.hi, float(value)))
        return float(round(v)) if self.integer else v

    def random(self, rng: random.Random) -> float:
        v = rng.uniform(self.lo, self.hi)
        return float(round(v)) if self.integer else v


@dataclass(frozen=True)
class BinarySpec:
    """
    二值（拓扑图案）基因型规格。

    :param n_bits: int, 总比特数
    :param shape: tuple, ``(Gen_Length, Gen_Width)``；乘积必须等于 `n_bits`

    **为什么需要 shape 而不只是一个位数**：`ga_optimizer` 的交叉是
    「随机选一个交叉点，交换两个个体在该点之后**子矩形**里的所有基因」，
    变异是「随机选一格翻一位」—— 都要求基因型是**二维**的，
    而且 `np.random.randint(1, Gen_Length - 1)` 要求两个维度都 **≥ 2**。
    """

    n_bits: int
    shape: Tuple[int, int]

    def __post_init__(self):
        r, c = self.shape
        if r < 2 or c < 2:
            raise OptError(
                f'shape={self.shape} 的两个维度都必须 ≥ 2 —— '
                f'ga_optimizer 的交叉点是在 (1, 维度-1) 里随机取的')
        if r * c != self.n_bits:
            raise OptError(
                f'shape={self.shape} 的乘积 {r * c} 与 n_bits={self.n_bits} 不一致')


def _auto_shape(n_bits: int) -> Tuple[int, int]:
    """把比特数分解成最接近正方形的 ``(r, c)``，两者都 ≥ 2。"""
    best = None
    for r in range(2, int(math.isqrt(n_bits)) + 1):
        if n_bits % r == 0:
            c = n_bits // r
            if c >= 2:
                best = (r, c)
    if best is None:
        raise OptError(
            f'n_bits={n_bits} 无法分解成两个都 ≥ 2 的因子；请显式传 shape=(r, c)'
            f'（如 n_bits 为质数时用 (1, n) 是不允许的 —— 见 BinarySpec 说明）')
    return (best[1], best[0])            # 让 Gen_Width 不小于 Gen_Length


def continuous_variables(spec: Dict[str, Any]) -> List[ContinuousVar]:
    """
    构造连续变量列表。

    :param spec: dict, ``{名字: (min, max)}`` 或 ``{名字: (min, max, 'int')}``
    :return: list[ContinuousVar]
    :raises OptError: 定义非法
    """
    out: List[ContinuousVar] = []
    for name, value in spec.items():
        integer = False
        if isinstance(value, dict):
            lo, hi = value.get('min'), value.get('max')
            integer = bool(value.get('integer', False))
        elif isinstance(value, (list, tuple)) and len(value) >= 2:
            lo, hi = value[0], value[1]
            integer = len(value) > 2 and str(value[2]).lower() in ('int', 'integer')
        else:
            raise OptError(
                f'变量 {name!r} 应写成 (min, max) 或 (min, max, "int")，收到 {value!r}')
        try:
            lo_f, hi_f = float(lo), float(hi)
        except (TypeError, ValueError) as exc:
            raise OptError(f'变量 {name!r} 的上下界必须是数值，收到 {value!r}') from exc
        if hi_f <= lo_f:
            raise OptError(f'变量 {name!r} 的上界必须大于下界（收到 {lo_f}, {hi_f}）')
        out.append(ContinuousVar(name=name, lo=lo_f, hi=hi_f, integer=integer))
    if not out:
        raise OptError('variables 不能为空')
    return out


def binary_variables(n_bits: int, shape: Optional[Tuple[int, int]] = None) -> BinarySpec:
    """
    构造二值（拓扑图案）基因型规格。这条路过 `ga_optimizer` 的真算子。

    :param n_bits: int, 比特数（= 可挖孔的格子数）
    :param shape: tuple 可选, ``(行, 列)``；不给则自动分解（两者都 ≥ 2）
    :return: BinarySpec
    :raises OptError: 位数非法或无法分解
    """
    if int(n_bits) <= 0:
        raise OptError(f'n_bits 必须为正整数，收到 {n_bits}')
    n = int(n_bits)
    return BinarySpec(n_bits=n, shape=tuple(shape) if shape else _auto_shape(n))


# ============================================================
# 结果
# ============================================================

@dataclass
class OptResult:
    """
    优化结果。

    :param mode: str, ``'continuous'`` / ``'binary'``
    :param best_genotype: 最优个体（连续模式是数值列表；二值模式是**扁平**的 0/1 列表）
    :param best_fitness: 最优适应度（已按 `maximize` 还原到用户口径）
    :param best_params: 连续模式 ``{变量名: 值}``；
        二值模式 ``{'pattern': [...], 'shape': (r, c)}``
    :param history: ``[(代数, 当代最优, 历史最优), …]``（已按用户口径）
    :param evaluations: 目标函数实际被调用次数（有缓存时少于 种群×代数）
    :param seed: 实际使用的随机种子（**复现靠它**）
    :param generations_run: 实际跑了多少代
    :param duration_s: 总耗时
    """

    mode: str
    best_genotype: List[Any]
    best_fitness: float
    best_params: Dict[str, Any]
    history: List[Tuple[int, float, float]] = field(default_factory=list)
    evaluations: int = 0
    seed: Optional[int] = None
    generations_run: int = 0
    duration_s: float = 0.0
    stop_reason: str = 'generations'
    maximize: bool = True

    @property
    def improved(self) -> bool:
        """
        末代历史最优**不劣于**初代历史最优。

        ⚠️ 方向必须跟着 `maximize` 走：求最大时「变好」是变大，
        求最小时「变好」是**变小**。精英保留下两种方向都**必然**成立。
        """
        if len(self.history) < 2:
            return True
        first, last = self.history[0][2], self.history[-1][2]
        if self.maximize:
            return last >= first - 1e-12
        return last <= first + 1e-12

    def fitness_curve(self) -> Tuple[List[int], List[float], List[float]]:
        """``(代数, 当代最优, 历史最优)`` 三条序列，出图直接用。"""
        return ([h[0] for h in self.history],
                [h[1] for h in self.history],
                [h[2] for h in self.history])


# ============================================================
# 优化器
# ============================================================

class GeneticOptimizer:
    """
    遗传算法驱动器（目标函数**注入**）。

    :param variables: 连续变量列表（`continuous_variables` 的产物）
        或二值规格（`binary_variables` 的产物）
    :param evaluate: callable, ``evaluate(genotype) -> float``。
        连续模式收到 ``[v1, v2, …]``；二值模式收到**扁平**的 ``[0/1, …]``。
    :param population_size: int, 种群规模（二值模式映射到 `GA['Gen_No']`）
    :param generations: int, 代数（映射到 `GA['max_iter']`）
    :param maximize: bool, True 求最大（默认），False 求最小（内部取负）
    :param seed: int 可选, 随机种子；不给则随机取一个并记进结果
    :param elite: int, 每代原样保留的最优个体数（≥1 才有「末代 ≥ 初代」的保证）
    :param mutation_rate: float, 连续模式的变异概率
    :param crossover_rate: float, 连续模式的交叉概率
    :param cross_prob: float 可选, 二值模式传给 `ga_optimizer` 的交叉概率
        （不给则用 `crossover_rate`）
    :param mut_prob: float 可选, 二值模式传给 `ga_optimizer` 的变异概率
        （不给则用 `mutation_rate`）
    :param pop_init_per: float, 二值模式 `pop_init(GA, per)` 的二值化阈值，默认 0.2
    :param cache: bool, 连续模式是否缓存已评估过的基因型
    :param audit: AuditLog 可选, 每代记一条
    :param ga: 可选, `tpc_toolkit.ga_optimizer` 模块对象（便于注入替身）
    """

    def __init__(self, variables, evaluate: Callable, population_size: int = 20,
                 generations: int = 30, maximize: bool = True,
                 seed: Optional[int] = None, elite: int = 1,
                 mutation_rate: float = 0.1, crossover_rate: float = 0.9,
                 cross_prob: Optional[float] = None, mut_prob: Optional[float] = None,
                 pop_init_per: float = 0.2, cache: bool = True, audit=None, ga=None):
        if evaluate is None or not callable(evaluate):
            raise OptError('evaluate 必须是可调用对象')
        if int(population_size) < 2:
            raise OptError(f'种群规模至少 2，收到 {population_size}')
        if int(generations) < 1:
            raise OptError(f'代数至少 1，收到 {generations}')

        if isinstance(variables, BinarySpec):
            self.mode = 'binary'
            self.spec: Optional[BinarySpec] = variables
            self.variables: List[ContinuousVar] = []
            if int(population_size) < 4:
                raise OptError(
                    f'二值模式的种群规模建议 ≥ 4（收到 {population_size}）：'
                    'ga_optimizer 的交叉是**按个体对**做的（步长 2）')
        else:
            self.mode = 'continuous'
            self.spec = None
            self.variables = list(variables)
            if not self.variables:
                raise OptError('variables 不能为空')

        self.evaluate = evaluate
        self.population_size = int(population_size)
        self.generations = int(generations)
        self.maximize = bool(maximize)
        self.elite = max(1, int(elite))
        self.mutation_rate = float(mutation_rate)
        self.crossover_rate = float(crossover_rate)
        self.cross_prob = float(cross_prob if cross_prob is not None else crossover_rate)
        self.mut_prob = float(mut_prob if mut_prob is not None else mutation_rate)
        self.pop_init_per = float(pop_init_per)
        self.cache = bool(cache)
        self.audit = audit
        self._ga = ga
        self.seed = seed
        self._cache: Dict[Any, float] = {}
        self.evaluations = 0

    # ------------------------------------------------------------
    # 目标函数包装
    # ------------------------------------------------------------

    def _score(self, genotype: Sequence) -> float:
        """调一次目标函数（连续模式带缓存），把「求最大/最小」统一成「越大越好」。"""
        key = tuple(map(float, genotype)) if (self.cache and self.mode == 'continuous') else None
        if key is not None and key in self._cache:
            return self._cache[key]
        value = float(self.evaluate(list(genotype)))
        if not math.isfinite(value):
            value = -math.inf if self.maximize else math.inf
        score = value if self.maximize else -value
        self.evaluations += 1
        if key is not None:
            self._cache[key] = score
        return score

    @property
    def ga(self):
        """`tpc_toolkit.ga_optimizer` 模块（惰性导入）。"""
        if self._ga is None:
            try:
                from tpc_toolkit import ga_optimizer
            except Exception as exc:                    # pragma: no cover
                raise OptError(
                    f'二值模式需要 tpc_toolkit.ga_optimizer（{exc!r}）') from exc
            self._ga = ga_optimizer
        return self._ga

    def _ga_params(self) -> Dict[str, Any]:
        """构造 `ga_optimizer` 要的那个 **dict**（键名以它源码为准）。"""
        r, c = self.spec.shape
        return {'Gen_Length': r, 'Gen_Width': c,
                'Gen_No': self.population_size, 'max_iter': self.generations,
                'cross_prob': self.cross_prob, 'mut_prob': self.mut_prob}

    # ------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------

    def run(self, progress: Optional[Callable] = None) -> OptResult:
        """
        跑优化。

        :param progress: callable 可选, ``progress(gen, gen_best, hist_best)``，
            每代回调一次（按**用户口径**的适应度）
        :return: :class:`OptResult`
        """
        rng = random.Random(self.seed)
        if self.seed is None:
            self.seed = rng.randrange(2 ** 31)          # 记下来，便于复现
            rng = random.Random(self.seed)
        if self.mode == 'binary':
            return self._run_binary(progress)
        return self._run_continuous(rng, progress)

    # ---- 连续模式 ----

    def _run_continuous(self, rng: random.Random, progress) -> OptResult:
        t0 = time.perf_counter()
        pop = [[v.random(rng) for v in self.variables]
               for _ in range(self.population_size)]
        scored = self._sort([(ind, self._score(ind)) for ind in pop])
        history = [(0, scored[0][1], scored[0][1])]
        best_ind, best_score = list(scored[0][0]), scored[0][1]
        self._audit(0, best_score, best_score)
        self._progress(progress, 0, best_score, best_score)

        for gen in range(1, self.generations + 1):
            children = [list(best_ind) for _ in range(self.elite)]
            while len(children) < self.population_size:
                p1 = self._tournament(scored, rng)
                p2 = self._tournament(scored, rng)
                c1, c2 = self._crossover(p1, p2, rng)
                children.append(self._mutate(c1, rng))
                if len(children) < self.population_size:
                    children.append(self._mutate(c2, rng))
            scored = self._sort([(ind, self._score(ind))
                                 for ind in children[:self.population_size]])
            if scored[0][1] < best_score:
                # 精英保留：历史最优**原样**带进下一代 ⇒ 历史最优单调不降
                scored[-1] = (list(best_ind), best_score)
                scored = self._sort(scored)
            if scored[0][1] > best_score:
                best_ind, best_score = list(scored[0][0]), scored[0][1]
            history.append((gen, scored[0][1], best_score))
            self._audit(gen, scored[0][1], best_score)
            self._progress(progress, gen, scored[0][1], best_score)

        return self._result(history, best_ind, best_score,
                            time.perf_counter() - t0)

    def _sort(self, scored):
        return sorted(scored, key=lambda p: p[1], reverse=True)

    def _tournament(self, scored, rng: random.Random, k: int = 3) -> List[Any]:
        """k 元锦标赛（比按比例选择稳，且不要求适应度非负）。"""
        picks = [scored[rng.randrange(len(scored))] for _ in range(k)]
        return list(max(picks, key=lambda p: p[1])[0])

    def _mutate(self, genotype: List[Any], rng: random.Random) -> List[Any]:
        """连续模式变异：按概率给每个变量加高斯扰动并夹回界内。"""
        child = list(genotype)
        for i, var in enumerate(self.variables):
            if rng.random() < self.mutation_rate:
                child[i] = var.clip(child[i] + rng.gauss(0.0, 0.15 * (var.hi - var.lo)))
        return child

    def _crossover(self, a, b, rng: random.Random):
        """连续模式交叉：凸组合 —— 实数基因没有「交换比特」的含义。"""
        if rng.random() > self.crossover_rate:
            return list(a), list(b)
        t = rng.random()
        return ([v.clip(x + t * (y - x)) for v, x, y in zip(self.variables, a, b)],
                [v.clip(y + t * (x - y)) for v, x, y in zip(self.variables, a, b)])

    # ---- 二值模式（真·桥接：复用 ga_optimizer 的种群级算子）----

    def _run_binary(self, progress) -> OptResult:
        import numpy as np

        ga = self.ga
        gp = self._ga_params()
        r, c = self.spec.shape
        t0 = time.perf_counter()

        # ga_optimizer 用全局 np.random ⇒ 想复现就必须先 seed
        np.random.seed(self.seed)
        pop, _fi, _all_pop, _all_prob = ga.pop_init(gp, self.pop_init_per)
        if pop.shape != (r, c, self.population_size):
            raise OptError(
                f'ga_optimizer.pop_init 返回的形状 {pop.shape} 与期望 '
                f'{(r, c, self.population_size)} 不一致 —— 上游实现可能变了')

        fit = [self._score(_flatten(pop[:, :, m])) for m in range(self.population_size)]
        best_idx = int(max(range(len(fit)), key=lambda i: fit[i]))
        best_bits = _flatten(pop[:, :, best_idx])
        best_score = fit[best_idx]
        history = [(0, best_score, best_score)]
        self._audit(0, best_score, best_score)
        self._progress(progress, 0, best_score, best_score)

        for gen in range(1, self.generations + 1):
            pop = np.asarray(ga.crossover(gp, pop))
            pop = np.asarray(ga.mutation(gp, pop))
            if pop.shape != (r, c, self.population_size):
                raise OptError(
                    f'ga_optimizer 交叉/变异后的形状 {pop.shape} 与期望 '
                    f'{(r, c, self.population_size)} 不一致 —— 上游实现可能变了')
            # 精英保留：把历史最优**原样**写回种群尾部，保证单调不降
            pop[:, :, -1] = np.asarray(best_bits, dtype=pop.dtype).reshape(r, c)
            fit = [self._score(_flatten(pop[:, :, m]))
                   for m in range(self.population_size)]
            gen_idx = int(max(range(len(fit)), key=lambda i: fit[i]))
            if fit[gen_idx] > best_score:
                best_score = fit[gen_idx]
                best_bits = _flatten(pop[:, :, gen_idx])
            history.append((gen, fit[gen_idx], best_score))
            self._audit(gen, fit[gen_idx], best_score)
            self._progress(progress, gen, fit[gen_idx], best_score)

        return self._result(history, best_bits, best_score,
                            time.perf_counter() - t0)

    # ---- 收尾 ----

    def _progress(self, progress, gen, gen_best, hist_best):
        if progress is None:
            return
        to_user = (lambda v: v) if self.maximize else (lambda v: -v)
        progress(gen, to_user(gen_best), to_user(hist_best))

    def _result(self, history, best_genotype, best_score, duration) -> OptResult:
        to_user = (lambda v: v) if self.maximize else (lambda v: -v)
        if self.maximize:
            best_fitness = best_score
        else:
            best_fitness = -best_score
        if self.mode == 'binary':
            best_params: Dict[str, Any] = {
                'pattern': [int(b) for b in best_genotype],
                'shape': tuple(self.spec.shape)}
        else:
            best_params = {v.name: g for v, g in zip(self.variables, best_genotype)}
        return OptResult(
            mode=self.mode,
            best_genotype=[int(b) for b in best_genotype] if self.mode == 'binary'
            else list(best_genotype),
            best_fitness=float(best_fitness), best_params=best_params,
            history=[(g, to_user(a), to_user(b)) for g, a, b in history],
            evaluations=self.evaluations, seed=self.seed,
            generations_run=self.generations, duration_s=duration,
            maximize=self.maximize)

    def _audit(self, gen: int, gen_best: float, hist_best: float):
        if self.audit is None:
            return
        to_user = (lambda v: v) if self.maximize else (lambda v: -v)
        self.audit.record('ga_generation', status='ok', generation=gen,
                          gen_best=round(to_user(gen_best), 6),
                          hist_best=round(to_user(hist_best), 6),
                          evaluations=self.evaluations)

    # ------------------------------------------------------------
    # 出图
    # ------------------------------------------------------------

    def report(self, result: OptResult, path: str = 'ga_report.html',
               title: str = '遗传算法优化') -> str:
        """
        出优化报告（自包含 HTML）：适应度曲线 + 最优参数 + 审计。

        :param result: :class:`OptResult`
        :param path: str, 输出 .html
        :param title: str, 标题
        :return: str, 写出的绝对路径
        """
        from topo_modeler.report import HtmlReport, svg_line_chart
        gens, gen_best, hist_best = result.fitness_curve()
        rep = HtmlReport(title=title, meta={
            '模式': result.mode + ('（复用 ga_optimizer 算子）'
                                  if self.mode == 'binary' else '（实数基因，算子自实现）'),
            '种群 / 代数': f'{self.population_size} / {result.generations_run}',
            '目标函数评估次数': result.evaluations,
            '随机种子（复现用）': result.seed,
            '求': '最大' if self.maximize else '最小',
            '耗时 (s)': round(result.duration_s, 3),
        })
        rep.add_section('适应度曲线', svg_line_chart(
            [('当代最优', gens, gen_best), ('历史最优', gens, hist_best)],
            xlabel='代数', ylabel='适应度'))
        rep.add_note('末代历史最优 ≥ 初代历史最优：由**精英保留**保证，'
                     '在固定种子下必然成立。',
                     level='ok' if result.improved else 'warn')
        if self.mode == 'binary':
            rep.add_note('二值模式的交叉/变异**直接调用** tpc_toolkit.ga_optimizer 的 '
                         'crossover/mutation（种群级、原地），并用 np.random.seed() 对齐随机数；'
                         '未使用它的 selection() —— 源码自己标注了「保留 2 优 / 替换 3 差」'
                         '只在种群规模为 4 时自洽。', level='warn')
        if self.audit is not None:
            rep.add_audit(self.audit)
        rows = [[k, (f'{len(v)} 位' if k == 'pattern' else v)]
                for k, v in result.best_params.items()]
        rep.add_table(['参数', '最优值'], rows, caption='最优参数')
        return rep.write(path)

    def __repr__(self):
        target = (f'{self.spec.n_bits} 位 {self.spec.shape}'
                  if self.mode == 'binary' else f'{len(self.variables)} 个变量')
        return (f'GeneticOptimizer(mode={self.mode!r}, {target}, '
                f'pop={self.population_size}, gens={self.generations}, '
                f'seed={self.seed})')


def _flatten(array) -> List[int]:
    """把二维 0/1 个体压成扁平列表（目标函数的输入口径）。"""
    return [int(v) for v in array.reshape(-1).tolist()]
