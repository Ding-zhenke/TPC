# -*- coding: utf-8 -*-
r"""
S 参数曲线判据：连续合格区间、谐振提取与**谐振峰频差**（V3 判据）
=================================================================

为什么有这个模块
----------------
这些规则原本**有两份实现**：`cst_mcp/analysis.py`（MCP 层，prominence 多极值）
与 `topo_modeler/result_reader.py::peak_position`（库层，全局单极值）。
同一仓库里两套「怎么算谐振」的规则正是 `skills/developer/conventions.md` 明令禁止的
漂移源 —— MCP 层应当**复用**库能力，而不是自己实现数值逻辑。

现在这里是**唯一实现**：

* `contiguous_bands()` —— 连续合格区间（相邻采样点才合并，绝不跨越不合格点）；
* `find_resonances()` —— 局部极值（相邻三点比较）+ **prominence 过滤**；
* `match_resonances()` —— 把两条曲线的极值**按频率就近配对**（V3 要求「可比曲线」）；
* `resonance_criterion()` —— 直接回答计划 P4/V3 的判据「谐振峰偏差 < 1 GHz」。

* `cst_mcp/analysis.py` 改为从这里导入（保留同名公开入口，只把 `ValueError` 翻成
  MCP 的 `invalid_arguments`）；
* `topo_modeler/result_reader.py` 的 `resonances()` / `resonance_shift()` 也走这里。

本模块**不依赖 CST**（纯数值），可以离线单测，也可直接拿来分析任意曲线。

@author: PC
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    'contiguous_bands',
    'find_resonances',
    'match_resonances',
    'resonance_criterion',
]

#: 极值幅度比较的容差（浮点噪声）：低于它不算「有突出」
_PROMINENCE_EPS = 1e-12


def _sorted_points(freqs: Sequence[float], values: Sequence[float]
                   ) -> List[Tuple[float, float]]:
    """按频率排序的 ``(f, v)``，丢掉 NaN。"""
    return sorted(((float(f), float(v)) for f, v in zip(freqs, values) if v == v),
                  key=lambda item: item[0])


def contiguous_bands(freqs: Sequence[float], values: Sequence[float], *,
                     threshold_db: float, criterion: str = 'below',
                     max_gap_ghz: Optional[float] = None) -> List[Dict[str, Any]]:
    """
    找**连续合格区间**（只按相邻采样点合并，绝不跨越不合格点）。

    :param freqs: 频率序列（GHz）
    :param values: 对应的 dB 序列
    :param threshold_db: 阈值（dB）
    :param criterion: ``'below'``（≤ 阈值合格，如回波损耗）或 ``'above'``
        （≥ 阈值合格，如插损）
    :param max_gap_ghz: float 可选, 相邻两点频差超过它就断开（默认只用采样相邻性）
    :return: list[dict], 每段含 ``fmin_ghz/fmax_ghz/bandwidth_ghz/n_points/
        best_db/best_freq_ghz/worst_db/worst_freq_ghz/margin_db/index``
    :raises ValueError: 判据非法或频率/数值长度不一致
    """
    if criterion not in ('below', 'above'):
        raise ValueError(
            f"criterion 只能是 'below' 或 'above'，收到 {criterion!r}")
    if len(freqs) != len(values):
        raise ValueError(f'频率与数值长度不一致：{len(freqs)} vs {len(values)}')
    points = _sorted_points(freqs, values)
    if not points:
        return []

    def passes(value: float) -> bool:
        return value <= threshold_db if criterion == 'below' else value >= threshold_db

    bands: List[Dict[str, Any]] = []
    run: List[Tuple[float, float]] = []

    def flush() -> None:
        if not run:
            return
        band_freqs = [p[0] for p in run]
        band_values = [p[1] for p in run]
        best_index = (min if criterion == 'below' else max)(
            range(len(band_values)), key=band_values.__getitem__)
        worst_index = (max if criterion == 'below' else min)(
            range(len(band_values)), key=band_values.__getitem__)
        best_db = band_values[best_index]
        worst_db = band_values[worst_index]
        margin = (threshold_db - worst_db) if criterion == 'below' \
            else (worst_db - threshold_db)
        bands.append({
            'fmin_ghz': band_freqs[0],
            'fmax_ghz': band_freqs[-1],
            'bandwidth_ghz': band_freqs[-1] - band_freqs[0],
            'n_points': len(run),
            'best_db': best_db,
            'best_freq_ghz': band_freqs[best_index],
            'worst_db': worst_db,
            'worst_freq_ghz': band_freqs[worst_index],
            'margin_db': margin,
        })
        run.clear()

    for frequency, value in points:
        if passes(value):
            if run and max_gap_ghz is not None and \
                    (frequency - run[-1][0]) > max_gap_ghz:
                flush()                                   # 频差过大：断开，不合并
            run.append((frequency, value))
        else:
            flush()
    flush()
    for index, band in enumerate(bands):
        band['index'] = index
    return bands


def find_resonances(freqs: Sequence[float], values: Sequence[float], *,
                    kind: str = 'min', min_prominence_db: float = 0.0,
                    band: Optional[Tuple[float, float]] = None
                    ) -> List[Dict[str, Any]]:
    """
    找局部极值（谷/峰），**相邻三点比较**。

    这是全仓**唯一**的谐振提取规则：`prominence_db` 取「相对两侧较不利一方的幅度」，
    低于 ``min_prominence_db`` 的极值被过滤掉（用来滤数值毛刺）。

    :param freqs: 频率序列（GHz）
    :param values: dB 序列
    :param kind: ``'min'``（谷，如 S11 谐振）或 ``'max'``
    :param min_prominence_db: float, 幅度低于此值的不算
    :param band: tuple 可选, ``(fmin, fmax)`` 只在带内找
    :return: list[dict], ``{'freq_ghz','db','kind','prominence_db'}``（按频率升序）
    :raises ValueError: ``kind`` 非法
    """
    if kind not in ('min', 'max'):
        raise ValueError(f"kind 只能是 'min' 或 'max'，收到 {kind!r}")
    points = _sorted_points(freqs, values)
    if band is not None:
        lo, hi = band
        points = [p for p in points if lo <= p[0] <= hi]
    found: List[Dict[str, Any]] = []
    for index in range(1, len(points) - 1):
        prev_value, value, next_value = (points[index - 1][1], points[index][1],
                                         points[index + 1][1])
        if kind == 'min':
            if value < prev_value and value < next_value:
                prominence = min(prev_value, next_value) - value
            else:
                continue
        else:
            if value > prev_value and value > next_value:
                prominence = value - max(prev_value, next_value)
            else:
                continue
        if prominence + _PROMINENCE_EPS < min_prominence_db:
            continue
        found.append({'freq_ghz': points[index][0], 'db': value, 'kind': kind,
                      'prominence_db': prominence})
    return found


def match_resonances(first: Sequence[Dict[str, Any]],
                     second: Sequence[Dict[str, Any]], *,
                     tolerance_ghz: Optional[float] = None,
                     name: str = '') -> Dict[str, Any]:
    """
    把两条曲线的极值**按频率就近配对**（V3 要求的「可比曲线」）。

    规则：对 ``first`` 的每个极值，在 ``second`` 里找**最近的**、且**尚未被用过**的极值；
    频差超过 ``tolerance_ghz`` 就不算配对（默认不限）。

    :param first: list[dict], `find_resonances` 的结果（参考曲线）
    :param second: list[dict], 同上（对比曲线）
    :param tolerance_ghz: float 可选, 配对的最大允许频差
    :param name: str, 曲线名（写进结果，便于报告）
    :return: dict, ``{'name','pairs','n_matched','n_unmatched_first',
        'n_unmatched_second','max_delta_ghz','mean_delta_ghz'}``
        pairs 每项含 ``freq_first_ghz/freq_second_ghz/delta_ghz/db_first/db_second``
    """
    remaining = list(second)
    pairs: List[Dict[str, Any]] = []
    for item in first:
        if not remaining:
            break
        best = min(remaining, key=lambda other: abs(other['freq_ghz']
                                                    - item['freq_ghz']))
        delta = abs(best['freq_ghz'] - item['freq_ghz'])
        if tolerance_ghz is not None and delta > tolerance_ghz:
            continue
        remaining.remove(best)
        pairs.append({'freq_first_ghz': item['freq_ghz'],
                      'freq_second_ghz': best['freq_ghz'],
                      'delta_ghz': delta,
                      'db_first': item['db'],
                      'db_second': best['db']})
    deltas = [p['delta_ghz'] for p in pairs]
    return {'name': name, 'pairs': pairs, 'n_matched': len(pairs),
            'n_unmatched_first': len(first) - len(pairs),
            'n_unmatched_second': len(second) - len(pairs),
            'max_delta_ghz': max(deltas) if deltas else None,
            'mean_delta_ghz': (sum(deltas) / len(deltas)) if deltas else None}


def resonance_criterion(first: Sequence[Dict[str, Any]],
                        second: Sequence[Dict[str, Any]], *,
                        limit_ghz: float = 1.0,
                        tolerance_ghz: Optional[float] = None,
                        name: str = '') -> Dict[str, Any]:
    """
    **计划 P4/V3 的判据**：谐振峰偏差是否 < ``limit_ghz``（默认 1 GHz）。

    在此之前这条判据只是文档里的一句话（旧做法是拿四个频点的 dB 差当代理）。
    这里给出可执行版本：配对 → 算频差 → 与限值比较，并把中间量全部返回。

    :param first: list[dict], 参考曲线的极值
    :param second: list[dict], 对比曲线的极值
    :param limit_ghz: float, 判据限值（默认 1 GHz）
    :param tolerance_ghz: float 可选, 配对容差
    :param name: str, 曲线名
    :return: dict, 匹配结果 + ``{'limit_ghz','ok','reason'}``；
        没有任何配对时 ``ok=False`` 且 ``reason='no_matched_resonance'``
        （**不把「没配上」当成通过**）
    """
    matched = match_resonances(first, second, tolerance_ghz=tolerance_ghz, name=name)
    if not matched['n_matched']:
        return dict(matched, limit_ghz=float(limit_ghz), ok=False,
                    reason='no_matched_resonance')
    worst = matched['max_delta_ghz']
    return dict(matched, limit_ghz=float(limit_ghz), ok=bool(worst < limit_ghz),
                reason='within_limit' if worst < limit_ghz else 'exceeds_limit')
