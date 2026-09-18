# -*- coding: utf-8 -*-
r"""
批量建模（阶段 7 模块 5.4）
==========================
从一批配置建多个模型、跑起来、汇总对比。

并发模型：**串行，一次一个设计环境**
------------------------------------
计划原本写的是 `build_all(parallel=True)` / `run_all(parallel=4)`。**这条路不走**：

- 阶段 5 §5.7.2 已把「CST 并发模型」按证据强度分档写清 —— 本库**实测过**的事实只有
  三条（一次 `DesignEnvironment()` 起一个新进程、同一工程不能被两个 DE 打开、
  `cst.results.ProjectFile` 可离线读结果），而**同时开 N 个 DE 的许可是什么上限、
  同时提交 N 个求解任务会排队还是报错**都**没验证过**；
- 阶段 4 反复强调过「不要开几十个工程窗口留着」。

所以本模块：

1. **只做串行**。传 `parallel > 1` 会**明确报错**并说明原因，不做「静默降级为串行」
   —— 静默降级会让人以为真的并行了；
2 每次执行都配一次 `close()`；
3. 提供 `design_environment_baseline()` / `close_extra_design_environments()`：
   **进循环前记基线，结束后只关自己开的那些**，绝不碰用户自己开着的会话。

可注入
------
和 `scanner.py` 一样，执行器是注入的：

.. code-block:: python

    def runner(entry) -> .cst 路径 | ResultReader | dict

于是「批量编排 + 汇总 + 对比图」的逻辑**完全可离线验收**，
只有真跑 CST 时才需要一个会开工程的 runner。

用法::

    from topo_modeler.batch import BatchModeler

    bm = BatchModeler.from_config('batch.yaml', workdir='out', runner=my_runner)
    bm.build_all().run_all()
    bm.collect_results()
    bm.export_csv('batch.csv')
    bm.plot_comparison('compare.html')

@author: PC
"""

import csv
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from cst_solver.failures import record_failure        # 只依赖失败通道，不拉 CST

__all__ = [
    'BatchModeler',
    'BatchEntry',
    'BatchError',
    'design_environment_baseline',
    'design_environment_query',
    'close_extra_design_environments',
    'running_design_environments',
]


class BatchError(RuntimeError):
    """批量配置或执行出错。"""


# ============================================================
# 设计环境（DE）清点 —— 只关自己开的
# ============================================================

_de_query_failure_seen = None


def design_environment_query() -> Dict:
    """
    查询当前活着的 CST 设计环境 —— **区分「没有 DE」与「问不到」**。

    为什么单独有这个函数（P4/V8 教训 + 静默失败审计）：
    :func:`running_design_environments` 在 `cst.interface` 导不进来时**返回空列表**
    （为了无 CST 环境也能跑编排逻辑），于是「一个 DE 都没有」与
    「根本查不了」在返回值上**长得一模一样**。实测踩过：本机 Anaconda 解释器
    默认没把 CST 的 `python_cst_libraries` 放进 `sys.path`，`running_design_environments()`
    **必然**返回 `[]`，与是否真有 DE 无关 —— 当时差点把「空列表」当成否定证据。

    :return: dict, ``{'ok': bool, 'pids': list[int], 'reason': str}``；
        ``ok=False`` 时 ``pids`` 恒为空、``reason`` 说明为什么查不到
    """
    global _de_query_failure_seen

    def _note(reason: str, code: str) -> None:
        """登记结构化失败；**同样的原因连续出现只记一次**（探针会被反复调用）。"""
        global _de_query_failure_seen
        if _de_query_failure_seen != reason:
            _de_query_failure_seen = reason
            record_failure('running_design_environments', code, reason,
                           log=False, reason=reason)

    try:
        from cst.interface import running_design_environments as _query
    except Exception as exc:                            # pragma: no cover - 环境相关
        reason = f'cst.interface 不可导入（{type(exc).__name__}: {exc}）'
        _note(f'{reason}：「没有 DE」与「问不到」无法区分',
              'cst_interface_unavailable')
        return {'ok': False, 'pids': [], 'reason': reason}
    try:
        pids = [int(pid) for pid in _query()]
    except Exception as exc:                            # pragma: no cover
        reason = f'查询 DE 列表失败（{type(exc).__name__}: {exc}）'
        _note(reason, 'cst_query_failed')
        return {'ok': False, 'pids': [], 'reason': reason}
    _de_query_failure_seen = None                       # 查到了就复位
    return {'ok': True, 'pids': pids, 'reason': ''}


def running_design_environments() -> List[int]:
    """
    当前活着的 CST 设计环境进程号。

    **需要 CST**（惰性导入 `cst.interface`）。没有 CST 时返回空列表并**不抛异常** ——
    调用方在无 CST 环境里也应该能走完编排逻辑。

    ⚠️ **返回值区分不了「没有 DE」与「问不到」**（两者都是 `[]`）。
    需要区分时用 :func:`design_environment_query`（它同时会走结构化失败通道）；
    判「有没有 DE 活着」这类**结论性**用途，不要拿空列表当否定证据。

    :return: list[int]
    """
    return list(design_environment_query()['pids'])


def design_environment_baseline() -> set:
    """
    记下**进批量循环之前**就已经存在的 DE 集合。

    :return: set[int]
    """
    return set(running_design_environments())


def close_extra_design_environments(baseline: Optional[set] = None,
                                    verbose: bool = False) -> List[int]:
    """
    关掉**不在基线里**的 DE（即本次批量自己开出来的），返回被关掉的进程号。

    🔴 **绝不能反过来**（关掉用户自己开着的会话）—— 所以必须传基线。

    :param baseline: set 可选, `design_environment_baseline()` 的结果；
        不传则只清点不关闭（返回当前所有 DE，供调用方判断）
    :param verbose: bool, 是否打印
    :return: list[int], 实际关闭（或清点到）的 DE 列表
    """
    query = design_environment_query()
    current = list(query['pids'])
    if not query['ok'] and verbose:
        print(f'  ⚠️ DE 清点不可用（{query["reason"]}）：'
              f'本次无法区分「没有 DE」与「问不到」，不做任何关闭动作')
    if baseline is None:
        return current
    if not query['ok']:
        return []                                      # 清点不可用 ⇒ 一个都不动
    extra = [pid for pid in current if pid not in baseline]
    if not extra:
        return []
    try:
        from cst.interface import DesignEnvironment
    except Exception:                                  # pragma: no cover
        return extra
    closed = []
    for pid in extra:
        try:
            DesignEnvironment.connect(pid).close()
            closed.append(pid)
            if verbose:
                print(f'  已关闭本次新建的 DE：{pid}')
        except Exception as exc:                        # noqa: BLE001
            if verbose:
                print(f'  兜底关闭 DE {pid} 失败，请手动关掉该窗口：{exc!r}')
    return closed


# ============================================================
# 批量条目
# ============================================================

@dataclass
class BatchEntry:
    """
    一个待建模型。

    :param name: str, 唯一名字（同时作为输出 .cst 的基名）
    :param config: dict, 该模型的配置（会被 `validate_config()` 校验）
    :param cst_path: str, 输出 .cst 路径
    :param note: str, 备注（会进 CSV 与报告）
    """

    name: str
    config: Dict[str, Any]
    cst_path: str = ''
    note: str = ''
    status: str = 'pending'             # pending / built / ok / error / skipped
    error: str = ''
    duration_s: float = 0.0
    metrics: Dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in ('built', 'ok')


# ============================================================
# 批量执行器
# ============================================================

class BatchModeler:
    """
    批量建模 + 批量仿真 + 汇总对比。

    :param entries: 序列, :class:`BatchEntry` 或 ``{'name':…, 'config':…}`` 字典
    :param workdir: str, .cst 输出目录
    :param runner: callable 可选, ``runner(entry) -> 路径 | reader | dict``
    :param metric_specs: dict, ``{指标名: callable(reader) -> float}``
    :param audit: AuditLog 可选
    :param cleanup: bool, 结束时是否关闭自己开的 DE（默认 True）
    """

    def __init__(self, entries: Sequence[Any], workdir: str = '.',
                 runner: Optional[Callable] = None,
                 metric_specs: Optional[Dict[str, Callable]] = None,
                 audit=None, cleanup: bool = True,
                 model_type: Optional[str] = None):
        self.entries: List[BatchEntry] = [_as_entry(e) for e in entries]
        if not self.entries:
            raise BatchError('entries 不能为空')
        names = [e.name for e in self.entries]
        if len(names) != len(set(names)):
            dup = sorted({n for n in names if names.count(n) > 1})
            raise BatchError(f'模型名必须唯一，重复的有：{dup}')
        self.workdir = os.path.abspath(workdir)
        self.runner = runner
        self.metric_specs: Dict[str, Callable] = dict(metric_specs or {})
        self.audit = audit
        self.cleanup = bool(cleanup)
        self.model_type = model_type
        self.last_errors: Dict[str, str] = {}
        self._baseline: Optional[set] = None
        self._validated: List[Dict[str, Any]] = []

    # ------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------

    @classmethod
    def from_config(cls, source, model_type: Optional[str] = None, **kwargs):
        """
        从「批量配置」构造。

        支持两种形态：

        1. **批量 YAML**：顶层是 ``models:`` 列表::

               models:
                 - name: wg_AB_l1_060
                   model: {type: straight_waveguide}
                   geometry: {large_hole_ratio: 0.60}
                 - name: wg_AB_l1_065
                   model: {type: straight_waveguide}
                   geometry: {large_hole_ratio: 0.65}

        2. **单配置 YAML**：直接给一个模型（等价于一个条目的批量）。

        :param source: str（YAML 路径）或 dict
        :param model_type: str 可选, 覆盖所有条目的 `model.type`
        :param kwargs: 透传给 :class:`BatchModeler`
        :return: BatchModeler
        """
        from topo_modeler import config as _config

        raw = _config.load_config(source)
        if 'models' in raw:
            items = raw['models']
            if not isinstance(items, list) or not items:
                raise BatchError('批量配置的 `models` 必须是非空列表')
        else:
            items = [raw]
        entries = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                raise BatchError(f'models[{i}] 应为映射，收到 {type(item).__name__}')
            name = item.get('name') or f'model_{i:03d}'
            cfg = {k: v for k, v in item.items() if k not in ('name', 'note')}
            entries.append(BatchEntry(name=str(name), config=cfg,
                                      note=str(item.get('note', ''))))
        return cls(entries, model_type=model_type, **kwargs)

    # ------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------

    def validate(self) -> 'BatchModeler':
        """
        逐个校验配置（**不碰 CST**）。

        :return: self
        :raises BatchError: 任一配置非法（消息里带模型名，便于定位）
        """
        from topo_modeler import config as _config

        self._validated = []
        for entry in self.entries:
            try:
                self._validated.append(
                    _config.validate_config(entry.config, model_type=self.model_type))
            except _config.ConfigError as exc:
                raise BatchError(f'模型 {entry.name!r} 的配置非法：{exc}') from exc
            if not entry.cst_path:
                entry.cst_path = os.path.join(self.workdir, entry.name + '.cst')
        return self

    # ------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------

    def _guard_parallel(self, parallel):
        if parallel is not None and int(parallel) != 1:
            raise BatchError(
                f'本模块**只做串行**，parallel={parallel} 不支持。\n'
                '  原因（阶段 5 §5.7.2）：CST 同时开多个设计环境/同时提交多个求解任务的'
                '许可与排队行为**尚未验证**，而阶段 4 已吃过「开一堆工程窗口」的亏。\n'
                '  要做并行，请自己在 runner 里排队并承担后果；本模块不替你静默降级。')

    def build_all(self, runner: Optional[Callable] = None,
                  parallel: Optional[int] = None,
                  continue_on_error: bool = True, echo: bool = False) -> 'BatchModeler':
        """
        逐个建模（串行）。

        :param runner: callable 可选, 覆盖构造时的 runner
        :param parallel: int 可选, **只接受 1**；其它值报错（见 :meth:`_guard_parallel`）
        :param continue_on_error: bool, 单个失败是否继续
        :param echo: bool, 是否打印进度
        :return: self
        """
        return self._execute(runner, parallel, continue_on_error, echo,
                             stage='build_all', ok_status='built')

    def run_all(self, runner: Optional[Callable] = None,
                parallel: Optional[int] = None,
                continue_on_error: bool = True, echo: bool = False) -> 'BatchModeler':
        """
        逐个仿真 + 读结果（串行）。

        与 :meth:`build_all` 是同一套编排 —— 区别只在记录的状态名。
        真跑 CST 时 runner 内部通常一次做完「建 + 跑 + 存」，
        那就只调 `run_all()` 即可。

        :return: self
        """
        return self._execute(runner, parallel, continue_on_error, echo,
                             stage='run_all', ok_status='ok')

    def _execute(self, runner, parallel, continue_on_error, echo,
                 stage: str, ok_status: str):
        self._guard_parallel(parallel)
        runner = runner or self.runner
        if runner is None:
            raise BatchError(
                f'{stage}() 需要一个执行器：BatchModeler(..., runner=…) 或 '
                f'{stage}(runner=…)。\n'
                f'  runner(entry) 应返回三者之一：.cst 路径 / ResultReader / 指标字典。')
        if not self._validated:
            self.validate()
        os.makedirs(self.workdir, exist_ok=True)

        # 🔴 进循环前记基线：结束后只关自己开的 DE
        self._baseline = design_environment_baseline()
        try:
            for i, entry in enumerate(self.entries):
                entry.status = 'running'
                t0 = time.perf_counter()
                try:
                    payload = runner(entry)
                    self._absorb(entry, payload)
                    entry.status = ok_status
                except BaseException as exc:             # noqa: BLE001
                    entry.status = 'error'
                    entry.error = repr(exc)
                    self.last_errors[entry.name] = repr(exc)
                    if not continue_on_error:
                        entry.duration_s = time.perf_counter() - t0
                        self._audit(entry, stage)
                        raise BatchError(
                            f'模型 {entry.name} 失败'
                            f'（continue_on_error=False）：{exc!r}') from exc
                finally:
                    entry.duration_s = time.perf_counter() - t0
                self._audit(entry, stage)
                if echo:
                    flag = 'OK ' if entry.ok else 'x  '
                    metrics = ', '.join(f'{k}={v:.4g}' for k, v in entry.metrics.items())
                    print(f'[{i + 1}/{len(self.entries)}] {flag} {entry.name}  '
                          f'{entry.duration_s:.2f}s  {metrics}')
        finally:
            if self.cleanup:
                self.cleanup_environments(verbose=echo)
        return self

    def cleanup_environments(self, verbose: bool = False) -> List[int]:
        """
        关掉本次批量自己开出来的设计环境（**不碰基线里的**）。

        :param verbose: bool, 是否打印
        :return: list[int], 被关掉的进程号
        """
        return close_extra_design_environments(self._baseline, verbose=verbose)

    def _absorb(self, entry: BatchEntry, payload):
        if payload is None:
            return
        if isinstance(payload, dict) and not hasattr(payload, 'read_s_parameters'):
            entry.metrics.update({k: float(v) for k, v in payload.items()
                                  if _is_number(v)})
            return
        reader = payload
        if isinstance(payload, str):
            entry.cst_path = os.path.abspath(payload)
            from topo_modeler.result_reader import ResultReader
            reader = ResultReader(payload)
        for name, spec in self.metric_specs.items():
            try:
                entry.metrics[name] = float(spec(reader))
            except Exception as exc:                     # noqa: BLE001
                self.last_errors[f'{entry.name}:{name}'] = repr(exc)

    def _audit(self, entry: BatchEntry, stage: str):
        if self.audit is None:
            return
        self.audit.record(f'batch_{stage}', status=entry.status,
                          duration_s=entry.duration_s, model=entry.name,
                          cst_path=entry.cst_path, error=entry.error,
                          metrics=entry.metrics)

    # ------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------

    @property
    def failed(self) -> List[BatchEntry]:
        """失败的条目。"""
        return [e for e in self.entries if e.status == 'error']

    @property
    def succeeded(self) -> List[BatchEntry]:
        """成功的条目。"""
        return [e for e in self.entries if e.ok]

    @property
    def metric_names(self) -> List[str]:
        """出现过的指标名（保持首次出现顺序）。"""
        names: List[str] = list(self.metric_specs)
        for entry in self.entries:
            for key in entry.metrics:
                if key not in names:
                    names.append(key)
        return names

    def collect_results(self) -> Dict[str, Dict[str, float]]:
        """
        汇总：``{模型名: {指标: 值}}``（只含成功的条目）。

        :return: dict
        """
        return {e.name: dict(e.metrics) for e in self.succeeded}

    def summary(self) -> Dict[str, Any]:
        """一句话能说清的整体状态（进报告 / 打印用）。"""
        return {'模型数': len(self.entries),
                '成功': len(self.succeeded),
                '失败': len(self.failed),
                '总耗时 (s)': round(sum(e.duration_s for e in self.entries), 3)}

    # ------------------------------------------------------------
    # 导出与出图
    # ------------------------------------------------------------

    def export_csv(self, path: str) -> str:
        """
        导出汇总 CSV（**行数 == 模型数**）。

        :param path: str, 输出路径
        :return: str, 写出的绝对路径
        """
        path = os.path.abspath(path)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        header = (['name', 'status', 'model_type', 'cst_path', 'note']
                  + self.metric_names + ['duration_s', 'error'])
        with open(path, 'w', encoding='utf-8-sig', newline='') as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            for e in self.entries:
                writer.writerow([e.name, e.status,
                                 e.config.get('model', {}).get('type', ''),
                                 e.cst_path, e.note]
                                + [e.metrics.get(m, '') for m in self.metric_names]
                                + [round(e.duration_s, 3), e.error])
        return path

    def plot_comparison(self, path: str = 'batch_compare.html',
                        metric: Optional[str] = None,
                        title: str = '批量对比') -> str:
        """
        对比图（自包含 HTML）：按指标出柱状/条形对比 + 明细表。

        :param path: str, 输出 .html
        :param metric: str 可选, 指标名；不给则全部指标各出一张
        :param title: str, 标题
        :return: str, 写出的绝对路径
        """
        from topo_modeler.report import HtmlReport, svg_line_chart
        metrics = [metric] if metric else self.metric_names
        rep = HtmlReport(title=title, meta={
            '模型数': len(self.entries),
            '成功 / 失败': f'{len(self.succeeded)} / {len(self.failed)}',
            '工作目录': self.workdir,
        })
        if self.audit is not None:
            rep.add_audit(self.audit, title='批量耗时')
        for m in metrics:
            names = [e.name for e in self.succeeded if m in e.metrics]
            vals = [e.metrics[m] for e in self.succeeded if m in e.metrics]
            if not names:
                continue
            # 每个模型一个点、图例即模型名：量级与离群一眼能看出来。
            # 精确读数看下面的「明细」表 —— 图不承担读数职责。
            series = [(n, [i + 1], [v]) for i, (n, v) in enumerate(zip(names, vals))]
            rep.add_section(f'{m} 对比',
                            svg_line_chart(series, xlabel='模型序号', ylabel=m)
                            + '<p class="sub">每个模型一个点（图例即模型名）；'
                              '具体数值见下表。</p>')
        header = ['模型', '状态'] + metrics
        rows = [[e.name, e.status] + [e.metrics.get(m) for m in metrics]
                for e in self.entries]
        rep.add_table(header, rows, caption='明细')
        if self.failed:
            for e in self.failed:
                rep.add_note(f'失败：{e.name} — {e.error}', level='error')
        return rep.write(path)

    def report(self, path: str = 'batch_report.html',
               title: str = '批量建模报告') -> str:
        """
        完整报告：状态汇总 + 审计时间线 + 对比 + 明细。

        :param path: str, 输出 .html
        :param title: str, 标题
        :return: str, 写出的绝对路径
        """
        from topo_modeler.report import HtmlReport
        rep = HtmlReport(title=title, meta=self.summary())
        if self.audit is not None:
            rep.add_audit(self.audit)
        header = ['模型', '状态'] + self.metric_names
        rows = [[e.name, e.status] + [e.metrics.get(m) for m in self.metric_names]
                for e in self.entries]
        rep.add_table(header, rows, caption='明细')
        if self.failed:
            for e in self.failed:
                rep.add_note(f'失败：{e.name} — {e.error}', level='error')
        return rep.write(path)

    def __repr__(self):
        return (f'BatchModeler({len(self.entries)} 个模型, workdir={self.workdir!r}, '
                f'成功={len(self.succeeded)}, 失败={len(self.failed)})')


# ============================================================
# 小工具
# ============================================================

def _as_entry(item) -> BatchEntry:
    """把 dict / BatchEntry 统一成 BatchEntry。"""
    if isinstance(item, BatchEntry):
        return item
    if isinstance(item, dict):
        if 'name' not in item or 'config' not in item:
            raise BatchError("条目字典必须含 'name' 与 'config' 两个键")
        return BatchEntry(name=str(item['name']), config=item['config'],
                          note=str(item.get('note', '')))
    raise BatchError(f'条目应为 BatchEntry 或 dict，收到 {type(item).__name__}')


def _is_number(value) -> bool:
    if isinstance(value, bool):
        return False
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True
