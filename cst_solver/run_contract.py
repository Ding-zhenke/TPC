# -*- coding: utf-8 -*-
r"""
求解运行契约（P1）
==================

问题：四件事在既有代码里区分不开
--------------------------------
求解入口 :meth:`cst_solver.simulation.solver.SolverMixin.run` 只做一件事 ——
把 ``model3d.run_solver()`` 交下去，然后 **返回 None**。而 CST 不抛异常
（``skills/developer/WORKFLOW.md`` 硬约定 §3），于是：

1. ``run()`` 正常返回 —— 只说明 VBA 提交没炸，**不说明求解做完**；
2. 求解真的完成；
3. 工程里存在结果；
4. **这些结果属于本次运行** —— ``run_id=0`` 永远指向「当前最新结果」，
   拿它读数据就可能把上一轮的结果当成本轮结果。

本模块把四者分开，给出**可判定的结论**（``status``）与**判定依据**（``evidence``），
并把「读消息」这件事落盘（JSONL），避免 CST 消息「读取即清空」之后无据可查。

判定口径（引用时必须完整）
--------------------------
=========================  ====================================================
``submitted``              提交调用返回且未抛异常
``messages_clean``         求解后读到的 CST 消息为空（``get_messages()`` 读取即清空）
``results_exist``          结果指纹里能看到结果文件或 run id
``results_changed``        结果指纹在提交**前后**发生变化
``status='succeeded'``     三者同时成立
``status='failed'``        提交抛异常，或消息非空
``status='unverified'``    没有异常、也没有消息，但结果缺失/未变化/查不到 ——
                           **不得**当作成功
=========================  ====================================================

⚠️ **``results_changed`` 是必要条件，不是充分条件**：它只证明「结果区在提交之后
发生了变化」，**不证明**这份结果就是本次提交算出来的（例如另一个会话也在写同一
工程）。真正的判据要在真机上做小范围串行闭环（``docs/next_plan/README.md`` P4/V7）。
本模块的价值在于：**把「返回了」和「算完了、结果是本次的」分开报告**，
而不是替真机验收下结论。

状态词表与 P2 的衔接
--------------------
本模块产出 ``succeeded`` / ``failed`` / ``unverified`` / ``interrupted``；
P2 的任务层在此基础上加 ``queued`` / ``running``。映射规则：
``unverified`` **不得**被报告为成功（``cst_mcp.md`` §5「不得把失败或缺失结果
变成空数据后声称成功」）；``interrupted`` 用于「进程重启后无法确认」的情形
（``cst_mcp.md`` §4），且**不自动重跑**。

@author: PC
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

__all__ = [
    'RUN_STATUSES',
    'RUN_ERROR_CODES',
    'RunContract',
    'JsonlSink',
    'result_conventions',
    'disk_result_probe',
    'cst_result_probe',
    'result_fingerprint',
    'run_log_path',
    'project_path_of',
]

#: 运行结论状态（P2 任务层在此基础上增加 ``queued`` / ``running``）
RUN_STATUSES = ('succeeded', 'failed', 'unverified', 'interrupted')

#: 本模块可能产出的错误码
RUN_ERROR_CODES = (
    'run_exception',            # 提交调用抛了异常
    'run_messages',             # 提交后 CST 消息非空（CST 不抛异常，这是唯一线索）
    'messages_unreadable',      # 读消息本身失败
    'results_missing',          # 工程里找不到任何结果
    'results_unchanged',        # 结果指纹没变 —— 很可能是上一轮的结果
    'results_not_verified',     # 指纹不可用（探测失败/没有工程路径）
    'audit_write_failed',       # 运行记录没能落盘
)


def _error(code: str, message: str, *, retryable: bool = False, **details) -> Dict:
    """统一错误结构（唯一实现在 ``cst_solver.failures.structured_error``）。"""
    from cst_solver.failures import structured_error
    return structured_error(code, message, retryable=retryable, **details)


def _utcnow() -> str:
    """ISO-8601 UTC 时间戳（秒精度，不依赖本地时区）。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ============================================================
# 结果单位与口径（作为数据暴露，供 MCP 回给客户端）
# ============================================================

def result_conventions() -> Dict[str, Any]:
    """
    结果的口径与单位，**从实现里取**（不要另抄一份）。

    与 :func:`cst_solver._result_core._to_db`、``topo_modeler/result_reader.py``
    的 ``_to_db`` 保持一致：``20*log10(|S|)``，幅度为 0 记 −300 dB。

    :return: dict, 可直接 JSON 序列化
    """
    return {
        'frequency_unit': 'GHz',
        's_magnitude': 'complex（实部/虚部）',
        's_db': '20*log10(abs(S))',
        'zero_magnitude_db': -300.0,
        'run_id_default': 0,
        'run_id_semantics': ('run_id=0 是「当前最新结果」的别名，不是历史 run 编号；'
                             '要固定某次运行必须显式给出具体 run_id'),
        'port_mode_naming': 'S<i>,<j> 对应 cst_solver 的端口编号 i、j（模式 1 为基模）',
        'length_unit': 'mm（CST 工程单位，见 cst_solver.units.get_units）',
        'source': ('cst_solver/_result_core.py::_to_db 与 '
                   'topo_modeler/result_reader.py::_to_db'),
    }


# ============================================================
# 结果指纹
# ============================================================

def _project_folder(project_path: str) -> Optional[str]:
    """``...\\wg.cst`` → ``...\\wg``（CST 工程目录）；不存在则返回 None。"""
    if not project_path:
        return None
    stem = os.path.splitext(os.path.abspath(project_path))[0]
    return stem if os.path.isdir(stem) else None


def disk_result_probe(project_path: str) -> Dict[str, Any]:
    """
    磁盘结果指纹（**不导入 CST**）。

    记录工程目录下 ``Result/`` 与 ``ModelCache/`` 的文件名、大小、纳秒修改时间。
    这两处一起变化才说明「真跑过」：求解写 ``Result/``，网格/几何重建写
    ``ModelCache/``。

    :param project_path: str, ``.cst`` 工程文件路径
    :return: dict, 可 JSON 序列化（探测失败时带 ``error``）
    """
    report: Dict[str, Any] = {'kind': 'disk', 'project': os.path.abspath(project_path)
                              if project_path else None, 'items': []}
    folder = _project_folder(project_path)
    if folder is None:
        report['error'] = (f'CST 工程目录不存在：'
                           f'{os.path.splitext(os.path.abspath(project_path))[0]}')
        return report
    items: List[Tuple[str, int, int]] = []
    for sub in ('Result', 'ModelCache'):
        base = os.path.join(folder, sub)
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for name in sorted(files):
                path = os.path.join(root, name)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                rel = os.path.relpath(path, folder).replace('\\', '/')
                items.append((rel, int(stat.st_size), int(stat.st_mtime_ns)))
                if len(items) >= 500:                 # 上限：指纹要便宜
                    break
            if len(items) >= 500:
                break
    report['items'] = [list(it) for it in sorted(items)]
    return report


def cst_result_probe(project_path: str) -> Dict[str, Any]:
    """
    「磁盘 + CST 结果接口」指纹（可选）。

    在 :func:`disk_result_probe` 之上，用 ``cst.results.ProjectFile``（**离线读取**，
    不创建设计环境）取 run id 列表与结果项数量。CST 不可用时把错误记进
    ``error`` 并保留磁盘部分 —— 探测失败**不等于**没有结果。

    :param project_path: str, ``.cst`` 工程文件路径
    :return: dict, 可 JSON 序列化
    """
    report: Dict[str, Any] = {'kind': 'cst', 'disk': disk_result_probe(project_path)}
    try:
        from cst_solver._result_core import Result
    except Exception as exc:                          # noqa: BLE001
        report['error'] = f'结果接口不可用：{type(exc).__name__}: {exc}'
        return report
    try:
        reader = Result(project_path)
        report['run_ids'] = sorted(int(r) for r in
                                   (reader.get_all_run_ids(max_mesh_passes_only=False) or []))
        report['available_results'] = len(reader.get_available_results() or [])
    except Exception as exc:                          # noqa: BLE001
        report['error'] = f'{type(exc).__name__}: {exc}'
    return report


def result_fingerprint(project_path: str,
                       probe: Optional[Callable[[str], Dict[str, Any]]] = None
                       ) -> Dict[str, Any]:
    """
    取一次结果指纹。

    :param project_path: str, ``.cst`` 工程文件路径
    :param probe: 可调用 可选, 自定义探测函数（测试或真机扩展用）；默认磁盘指纹
    :return: dict；探测抛异常时返回 ``{'error': ...}`` 而不向上抛
    """
    if not project_path:
        return {'error': 'project_path 为空，无法取结果指纹'}
    fn = probe or disk_result_probe
    try:
        return fn(project_path)
    except Exception as exc:                          # noqa: BLE001
        return {'error': f'{type(exc).__name__}: {exc}'}


def _fingerprint_key(fingerprint: Optional[Dict[str, Any]]) -> Optional[str]:
    """把指纹压成可比较的字符串；不可用时返回 None。"""
    if not fingerprint or 'error' in fingerprint:
        return None
    try:
        return json.dumps(fingerprint, sort_keys=True, ensure_ascii=True)
    except (TypeError, ValueError):
        return None


def _has_results(fingerprint: Optional[Dict[str, Any]]) -> bool:
    """指纹里能否看到结果（磁盘条目或 run id）。"""
    if not fingerprint or 'error' in fingerprint:
        return False
    if fingerprint.get('run_ids'):
        return True
    if fingerprint.get('items'):
        return True
    disk = fingerprint.get('disk') or {}
    return bool(disk.get('items') or disk.get('run_ids'))


# ============================================================
# 运行记录落盘
# ============================================================

def run_log_path(project_path: str) -> str:
    """
    默认的运行记录路径：工程目录下的 ``run_contract.jsonl``。

    放在工程目录里是为了「工程走到哪，记录跟到哪」；工程目录不存在时
    退回 ``<工程文件同级的 .jsonl>``。

    :param project_path: str, ``.cst`` 工程文件路径
    :return: str, 绝对路径
    """
    folder = _project_folder(project_path)
    if folder:
        return os.path.join(folder, 'run_contract.jsonl')
    return os.path.abspath(project_path) + '.run_contract.jsonl'


class JsonlSink:
    """
    运行记录落盘器：每行一条 JSON（JSONL，追加写）。

    CST 的 ``get_messages()`` **读取即清空**，所以消息必须由调用方在
    读取后立刻写进这样的记录里，否则事后无法追溯（``cst_mcp.md`` §5
    「明确读消息后的持久记录策略」）。

    :param path: str, 输出文件路径
    """

    def __init__(self, path: str):
        self.path = os.path.abspath(path)

    def write(self, record: Dict[str, Any]) -> str:
        """
        追加一条记录。

        :param record: dict, JSON 可序列化
        :return: str, 实际写入的路径
        :raises OSError: 目录不可创建或不可写（由调用方决定如何降级）
        """
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with open(self.path, 'a', encoding='utf-8') as handle:
            handle.write(line + '\n')
        return self.path


# ============================================================
# 工程路径
# ============================================================

def project_path_of(app) -> Optional[str]:
    """
    从 :class:`cst_solver.setup` 实例上取工程文件路径（取不到返回 None）。

    兼容多种取法：``cst_file.filename()``（CST 官方接口里 ``filename`` 是**方法**）、
    ``cst_file.filename`` 属性、``project_path``/``_cst_path`` 之类的自定义字段。
    取不到**不抛异常** —— 后续会以 ``results_not_verified`` 如实报告。

    :param app: 任意对象（一般是 setup 实例）
    :return: str | None
    """
    if app is None:
        return None
    for holder_name in ('cst_file', ''):
        holder = getattr(app, holder_name, None) if holder_name else app
        if holder is None:
            continue
        for attr in ('filename', 'project_path', '_cst_path'):
            value = getattr(holder, attr, None)
            if value is None:
                continue
            if callable(value):
                try:
                    value = value()
                except Exception:                     # noqa: BLE001
                    continue
            if isinstance(value, str) and value:
                return value
    return None


# ============================================================
# 运行契约
# ============================================================

class RunContract:
    """
    把「提交求解 → 判定完成 → 结果归属 → 消息落盘」串成一次可追溯的运行。

    :param project_path: str | None, ``.cst`` 工程文件路径（取不到时结论会落到
        ``unverified``，不会假装成功）
    :param probe: 可调用 可选, 结果指纹探测函数，默认 :func:`disk_result_probe`
    :param sink: 对象 可选, 有 ``write(record) -> path`` 方法；默认不落盘
    :param clock: 可调用 可选, 返回时间字符串，便于测试注入
    :param tag: str, 本次运行的备注（写进记录）

    用法::

        contract = RunContract(project_path, sink=JsonlSink(run_log_path(project_path)))
        outcome = contract.run_and_record(app.run, read_messages=app.get_messages)
        if outcome['status'] != 'succeeded':
            ...  # 按 outcome['errors'] 分流
    """

    def __init__(self, project_path: Optional[str] = None, *,
                 probe: Optional[Callable[[str], Dict[str, Any]]] = None,
                 sink=None, clock: Optional[Callable[[], str]] = None,
                 tag: str = ''):
        self.project_path = project_path
        self.probe = probe or disk_result_probe
        self.sink = sink
        self.clock = clock or _utcnow
        self.tag = tag

    # ---- 内部 ----

    def _fingerprint(self) -> Dict[str, Any]:
        return result_fingerprint(self.project_path, self.probe)

    def _persist(self, outcome: Dict[str, Any]) -> Tuple[bool, Optional[str], List[Dict]]:
        """落盘；失败降级成 warning + 错误码，不抛异常。"""
        if self.sink is None:
            return False, None, []
        try:
            path = self.sink.write(outcome)
        except Exception as exc:                      # noqa: BLE001
            return False, None, [_error(
                'audit_write_failed',
                f'运行记录落盘失败（{type(exc).__name__}: {exc}）；'
                f'结论本身仍然有效，但事后无法追溯消息', retryable=True)]
        return True, path, []

    # ---- 公开 ----

    def before_submit(self, note: str = '') -> Dict[str, Any]:
        """
        提交前拍照：生成运行标识 + 结果指纹。

        :param note: str, 备注
        :return: dict, 传给 :meth:`after_submit` 的运行记录
        """
        return {
            'run_token': f'{self.clock()}-{uuid.uuid4().hex[:8]}',
            'project': self.project_path,
            'tag': self.tag,
            'note': note,
            'started_at': self.clock(),
            'status': 'running',
            'fingerprint_before': self._fingerprint(),
        }

    def after_submit(self, record: Dict[str, Any], *,
                     messages: Optional[Sequence[Any]] = None,
                     error: Optional[str] = None) -> Dict[str, Any]:
        """
        提交后判定：结果是否变化、消息是否干净、本次运行是否成立。

        :param record: dict, :meth:`before_submit` 的返回值
        :param messages: 序列 可选, 读到的 CST 消息
        :param error: str 可选, 提交阶段捕获到的异常字符串
        :return: dict, 运行结论（``status`` / ``errors`` / ``evidence`` …）
        """
        fingerprint_before = record.get('fingerprint_before')
        fingerprint_after = self._fingerprint()
        key_before = _fingerprint_key(fingerprint_before)
        key_after = _fingerprint_key(fingerprint_after)
        if key_before is None or key_after is None:
            results_changed: Optional[bool] = None
        else:
            results_changed = key_before != key_after
        results_exist = _has_results(fingerprint_after)

        message_list = [str(m) for m in (messages or [])]
        errors: List[Dict] = []
        warnings: List[str] = []

        if error:
            status = 'failed'
            errors.append(_error('run_exception',
                                 f'提交求解时抛出异常：{error}', retryable=True,
                                 error=error))
        elif message_list:
            status = 'failed'
            errors.append(_error(
                'run_messages',
                f'提交后 CST 消息非空（{len(message_list)} 条）：'
                f'CST 不抛异常，消息是唯一线索',
                messages=message_list))
        elif results_changed is None:
            # 指纹不可用时先报这一条：此时「有没有结果」其实是**不知道**，
            # 报 results_missing 会误导（把探测失败说成没有结果）
            status = 'unverified'
            errors.append(_error(
                'results_not_verified',
                '结果指纹不可用（探测失败或工程路径取不到），无法判断结果归属',
                fingerprint_error=(fingerprint_after or {}).get('error')))
        elif not results_exist:
            status = 'unverified'
            errors.append(_error(
                'results_missing',
                '工程里看不到任何结果；求解可能没跑完，或结果没有保存',
                fingerprint=fingerprint_after))
        elif results_changed is False:
            status = 'unverified'
            errors.append(_error(
                'results_unchanged',
                '结果指纹在提交前后完全一致：这次很可能没有产生新结果，'
                '拿现有结果读数据会把上一轮当成本轮',
                fingerprint=fingerprint_after))
        else:
            status = 'succeeded'

        if self.sink is None:
            warnings.append('未配置 sink：本次运行消息**没有落盘**，事后无法追溯')
        if record.get('messages_read_error'):
            errors.append(_error('messages_unreadable',
                                 f'读取 CST 消息失败：{record["messages_read_error"]}'))
            if status == 'succeeded':
                status = 'unverified'

        outcome: Dict[str, Any] = {
            'run_token': record.get('run_token'),
            'project': self.project_path,
            'tag': self.tag,
            'note': record.get('note', ''),
            'started_at': record.get('started_at'),
            'finished_at': self.clock(),
            'status': status,
            'submitted': bool(record.get('submitted')),
            'messages': message_list,
            'messages_clean': not message_list,
            'results_exist': results_exist,
            'results_changed': results_changed,
            'errors': errors,
            'warnings': warnings,
            'conventions': result_conventions(),
            'evidence': {
                'fingerprint_before': fingerprint_before,
                'fingerprint_after': fingerprint_after,
                'probe': getattr(self.probe, '__name__', str(self.probe)),
                'status_rule': ('succeeded 需同时满足：提交未抛异常、消息为空、'
                                '结果存在且指纹变化；results_changed 是必要条件'
                                '而非充分条件（真机判据见 P4/V7）'),
            },
        }
        persisted, path, persist_errors = self._persist(outcome)
        outcome['persisted'] = persisted
        outcome['record_path'] = path
        if persist_errors:
            outcome['errors'].extend(persist_errors)
            outcome['warnings'].append('运行记录未能落盘')
        return outcome

    def run_and_record(self, submit: Callable[[], Any], *,
                       read_messages: Optional[Callable[[], Sequence[Any]]] = None,
                       note: str = '') -> Dict[str, Any]:
        """
        组合入口：拍照 → 调用 ``submit()`` → 读消息 → 判定 → 落盘。

        :param submit: 可调用, 真正的求解提交（如 ``app.run``）
        :param read_messages: 可调用 可选, 读 CST 消息（如 ``app.get_messages``）；
            读取即清空，所以必须在判定前读、并立刻落盘
        :param note: str, 备注
        :return: dict, 同 :meth:`after_submit`
        """
        record = self.before_submit(note=note)
        error: Optional[str] = None
        try:
            submit()
            record['submitted'] = True
        except Exception as exc:                      # noqa: BLE001
            record['submitted'] = False
            error = f'{type(exc).__name__}: {exc}'
        messages: List[Any] = []
        if read_messages is not None:
            try:
                messages = list(read_messages() or [])
            except Exception as exc:                  # noqa: BLE001
                record['messages_read_error'] = f'{type(exc).__name__}: {exc}'
        return self.after_submit(record, messages=messages, error=error)
