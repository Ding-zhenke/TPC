# -*- coding: utf-8 -*-
r"""
审计落盘（阶段 7 §3.3）
=======================
让「这次模型是怎么建出来的」可以被回答。

为什么需要
----------
阶段 4 反复踩同一类坑：**跑了很久的模型，事后说不清用了哪些参数、哪一步改过什么**
（「几何建了 200~300 s，别因为后面任何一步失败白费」；「参考工程没有可复用的结果」）。
审计落盘解决的是**可追溯性**，不是正确性 —— 它回答三个问题：

1. 这次跑用了**哪些参数**？（参数文件自动存档副本）
2. 中间**调用了哪些工具、花了多久、成没成**？（`logs/tool_calls.jsonl`）
3. 整个流程**按什么顺序**走的？（`logs/production_chain.md`）

产物
----
::

    logs/
    ├── tool_calls.jsonl          # 一行一个 JSON 事件（机器读）
    ├── production_chain.md       # 人读的流程链
    └── params/
        └── <name>-<时间戳>.json  # 参数文件的历史副本（不覆盖）

设计原则
--------
- **审计失败不能拖垮主流程。** 默认 `strict=False`：写盘出错只记在
  `AuditLog.last_error` 里并继续；`strict=True` 时才抛。这符合本库一贯的做法
  （守卫层探针、几何自查都是这个态度）。
- **只用标准库**，不 import numpy / CST —— 审计要能在任何环节被调用。
- **追加写，不覆盖**：`tool_calls.jsonl` 是 append，参数存档按时间戳命名。

用法::

    from topo_modeler.audit import AuditLog

    audit = AuditLog('logs')                     # 也可用环境变量 TPC_AUDIT_DIR
    audit.archive_parameters(cfg, name='wg_AB')

    with audit.stage('build_all', model='straight_waveguide'):
        template.build_all()

    audit.write_production_chain()               # 生成人读的流程链

@author: PC
"""

import json
import os
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

__all__ = [
    'AuditLog',
    'default_audit_dir',
    'record_call',
]


#: 环境变量：覆盖默认审计目录（便于把不同实验分开放）
ENV_AUDIT_DIR = 'TPC_AUDIT_DIR'

#: 默认目录名（相对当前工作目录）
DEFAULT_AUDIT_DIR = 'logs'


def default_audit_dir() -> str:
    """
    默认审计目录：环境变量 ``TPC_AUDIT_DIR`` 优先，否则当前工作目录下的 ``logs/``。

    :return: str, 绝对路径
    """
    return os.path.abspath(os.environ.get(ENV_AUDIT_DIR) or DEFAULT_AUDIT_DIR)


def _now_iso() -> str:
    """本地时间（带时区偏移），便于与 CST 日志对时。"""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def _stamp() -> str:
    """
    文件名用时间戳：``20260915-233901``。

    ⚠️ **必须带微秒**：只用秒的话，同一秒内两次 `archive_parameters()` 会撞名，
    而「存档绝不覆盖旧档」是本模块的对外承诺（`_unique_path` 再兜一层）。
    """
    return datetime.now().strftime('%Y%m%d-%H%M%S-%f')


def _unique_path(path: str) -> str:
    """
    若 `path` 已存在，依次尝试 ``-2`` / ``-3`` … 后缀，直到找到不存在的路径。

    保证「参数存档不覆盖」这条承诺**在任何情况下**成立（含同微秒的极端情况）。
    """
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    for i in range(2, 1000):
        candidate = f'{stem}-{i}{ext}'
        if not os.path.exists(candidate):
            return candidate
    raise RuntimeError(f'无法为 {path} 找到不冲突的文件名（已尝试 1000 次）')


def _jsonable(value):
    """
    把任意值压成可 JSON 序列化的形式。

    认不出来的一律转 ``str`` —— 审计**绝不应该**因为某个字段不能序列化就失败。
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, 'tolist'):                      # numpy 数组
        try:
            return _jsonable(value.tolist())
        except Exception:
            pass
    return repr(value)


class AuditLog:
    """
    审计日志（JSONL + 流程链 + 参数存档）。

    :param root: str 可选, 审计根目录；默认 :func:`default_audit_dir`
    :param enabled: bool, 关掉后所有方法变成 no-op（便于「这次不想留痕」）
    :param strict: bool, True 时写盘失败抛异常；默认 False（只记 `last_error`）
    :param echo: bool, True 时把每个事件同时 `print` 一行（便于实时看进度）
    """

    def __init__(self, root: Optional[str] = None, enabled: bool = True,
                 strict: bool = False, echo: bool = False):
        self.root = os.path.abspath(root) if root else default_audit_dir()
        self.enabled = bool(enabled)
        self.strict = bool(strict)
        self.echo = bool(echo)
        #: 最近一次写盘失败（None 表示一切正常）。审计不抛异常，错误留在这里。
        self.last_error: Optional[str] = None
        self._records: List[Dict[str, Any]] = []

    # ------------------------------------------------------------
    # 路径
    # ------------------------------------------------------------

    @property
    def jsonl_path(self) -> str:
        """`logs/tool_calls.jsonl` 的绝对路径。"""
        return os.path.join(self.root, 'tool_calls.jsonl')

    @property
    def chain_path(self) -> str:
        """`logs/production_chain.md` 的绝对路径。"""
        return os.path.join(self.root, 'production_chain.md')

    @property
    def params_dir(self) -> str:
        """`logs/params/` 的绝对路径。"""
        return os.path.join(self.root, 'params')

    def _ensure(self, *dirs):
        for d in dirs:
            if d:
                os.makedirs(d, exist_ok=True)

    def _fail(self, what: str, exc: BaseException):
        """处理写盘失败：记下来；`strict=True` 时抛。"""
        msg = f'{what} 失败：{exc!r}'
        self.last_error = msg
        if self.echo:
            print(f'[AUDIT-WARN] {msg}')
        if self.strict:
            raise RuntimeError(msg) from exc

    # ------------------------------------------------------------
    # 记录事件
    # ------------------------------------------------------------

    def record(self, tool: str, status: str = 'ok', duration_s: Optional[float] = None,
               **fields) -> Dict[str, Any]:
        """
        追加一条事件。

        :param tool: str, 工具/步骤名（如 `'build_all'`、`'configure_solver'`）
        :param status: str, ``'ok'`` / ``'error'`` / ``'running'`` / 自定义
        :param duration_s: float 可选, 耗时（秒）
        :param fields: 任意附加字段（参数、路径、消息…），会原样进 JSON
        :return: dict, 实际写入的记录（`enabled=False` 时也返回，只是不落盘）
        """
        rec: Dict[str, Any] = {
            # `uid` 只用于「内存记录 vs 文件记录」精确去重 —— 见 read()
            'uid': uuid.uuid4().hex,
            'ts': _now_iso(),
            'epoch': time.time(),
            'tool': str(tool),
            'status': str(status),
        }
        if duration_s is not None:
            rec['duration_s'] = round(float(duration_s), 3)
        for key, value in fields.items():
            rec[key] = _jsonable(value)

        self._records.append(rec)
        if not self.enabled:
            return rec

        if self.echo:
            extra = f"（{rec['duration_s']}s）" if 'duration_s' in rec else ''
            print(f"[AUDIT] {rec['tool']} -> {rec['status']}{extra}")
        try:
            self._ensure(self.root)
            with open(self.jsonl_path, 'a', encoding='utf-8') as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
        except Exception as exc:                       # noqa: BLE001 - 审计不该拖垮主流程
            self._fail('写 tool_calls.jsonl', exc)
        return rec

    @contextmanager
    def stage(self, tool: str, **fields):
        """
        上下文管理器：自动记录**开始 / 结束 / 耗时 / 是否异常**。

        ::

            with audit.stage('build_all', model='straight_waveguide'):
                template.build_all()

        异常会照常抛出去（审计不吞异常），但会先落一条 ``status='error'`` 的记录。

        :param tool: str, 步骤名
        :param fields: 附加字段
        """
        t0 = time.perf_counter()
        try:
            yield
        except BaseException as exc:
            self.record(tool, status='error', duration_s=time.perf_counter() - t0,
                        error=repr(exc), **fields)
            raise
        else:
            self.record(tool, status='ok', duration_s=time.perf_counter() - t0, **fields)

    # ------------------------------------------------------------
    # 参数存档
    # ------------------------------------------------------------

    def archive_parameters(self, params: Any, name: str = 'params',
                           note: str = '') -> Optional[str]:
        """
        把参数（通常是配置 dict）存档成**带时间戳的新文件**，绝不覆盖旧档。

        :param params: dict 或任意可 JSON 化的对象（含 YAML 路径字符串时会被读进来）
        :param name: str, 存档名前缀
        :param note: str, 附注（写进存档文件里的 `_note`）
        :return: str 存档文件的绝对路径；`enabled=False` 或写失败时返回 None
        """
        if not self.enabled:
            return None
        data = params
        if isinstance(params, str) and os.path.exists(params):
            try:
                with open(params, encoding='utf-8') as fh:
                    data = json.load(fh)
            except Exception:
                with open(params, encoding='utf-8', errors='replace') as fh:
                    data = {'_raw_text': fh.read()}
        payload = {
            '_note': note or '参数存档（审计落盘，不覆盖）',
            '_ts': _now_iso(),
            'params': _jsonable(data),
        }
        path = _unique_path(os.path.join(self.params_dir, f'{name}-{_stamp()}.json'))
        try:
            self._ensure(self.params_dir)
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
        except Exception as exc:                       # noqa: BLE001
            self._fail('写参数存档', exc)
            return None
        self.record('archive_parameters', status='ok', name=name, path=path)
        return path

    # ------------------------------------------------------------
    # 读回与流程链
    # ------------------------------------------------------------

    def read(self) -> List[Dict[str, Any]]:
        """
        读回全部事件。

        **顺序 = 文件里的追加顺序**（JSONL 是 append-only，所以那就是时间顺序）。
        不用 `epoch` / `ts` 排序：Windows 上 `time.time()` 的粒度约 15 ms，
        同一刻的两条记录 `epoch` 会**完全相同**（实测），拿它排序等于没排。

        内存里还没落盘的记录（写盘失败时）会接在文件记录之后。

        :return: list[dict]
        """
        records: List[Dict[str, Any]] = []
        seen = set()
        if os.path.exists(self.jsonl_path):
            try:
                with open(self.jsonl_path, encoding='utf-8') as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue                           # 半行（进程被杀）跳过
                        seen.add(_dedup_key(rec))
                        records.append(rec)
            except Exception as exc:                   # noqa: BLE001
                self._fail('读 tool_calls.jsonl', exc)

        for rec in self._records:
            key = _dedup_key(rec)
            if key in seen:
                continue
            seen.add(key)
            records.append(rec)
        return records

    def write_production_chain(self, path: Optional[str] = None,
                               title: str = '模型生产链') -> Optional[str]:
        """
        生成人读的流程链 Markdown：**按时间顺序**列出每个步骤、耗时与关键字段。

        :param path: str 可选, 输出路径；默认 `logs/production_chain.md`
        :param title: str, 标题
        :return: str 写出的绝对路径；`enabled=False` 或写失败时返回 None
        """
        if not self.enabled:
            return None
        path = os.path.abspath(path or self.chain_path)
        records = self.read()

        lines = [f'# {title}', '']
        lines.append(f'- 审计目录：`{self.root}`')
        lines.append(f'- 记录条数：**{len(records)}**')
        if records:
            lines.append(f"- 起止：{records[0].get('ts')} → {records[-1].get('ts')}")
            total = sum(r.get('duration_s') or 0 for r in records)
            lines.append(f'- 累计计时（各步骤之和）：**{total:.1f} s**')
        lines.append('')
        lines.append('> 本文件由 `topo_modeler/audit.py` 生成，回答「这次模型是怎么建出来的」。')
        lines.append('> 逐行原始事件见 `tool_calls.jsonl`。')
        lines.append('')

        if not records:
            lines.append('（没有记录）')
        else:
            lines.append('| # | 时间 | 步骤 | 状态 | 耗时 (s) | 关键字段 |')
            lines.append('|---|---|---|---|---|---|')
            skip = {'ts', 'epoch', 'tool', 'status', 'duration_s'}
            for i, rec in enumerate(records, 1):
                extra = '；'.join(
                    f'{k}={_short(v)}' for k, v in rec.items() if k not in skip)
                dur = rec.get('duration_s')
                lines.append(
                    f"| {i} | {rec.get('ts', '')} | `{rec.get('tool', '')}` | "
                    f"{rec.get('status', '')} | "
                    f"{'' if dur is None else f'{dur:.1f}'} | {extra} |")
            lines.append('')

            errors = [r for r in records if r.get('status') == 'error']
            lines.append('## 失败步骤')
            lines.append('')
            if errors:
                for rec in errors:
                    lines.append(f"- `{rec.get('tool')}` @ {rec.get('ts')}："
                                 f"{rec.get('error', '（无 error 字段）')}")
            else:
                lines.append('无。')
            lines.append('')

            slow = sorted((r for r in records if r.get('duration_s')),
                          key=lambda r: r['duration_s'], reverse=True)[:10]
            if slow:
                lines.append('## 最慢的 10 步')
                lines.append('')
                lines.append('| 步骤 | 耗时 (s) |')
                lines.append('|---|---|')
                for rec in slow:
                    lines.append(f"| `{rec['tool']}` | {rec['duration_s']:.1f} |")
                lines.append('')

        try:
            self._ensure(os.path.dirname(path))
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join(lines))
        except Exception as exc:                       # noqa: BLE001
            self._fail('写 production_chain.md', exc)
            return None
        return path

    def reset_memory(self):
        """清空**内存**里的记录（不动磁盘文件），便于分段生成流程链。"""
        self._records = []

    def __repr__(self):
        return (f"AuditLog(root={self.root!r}, enabled={self.enabled}, "
                f"records={len(self._records)}, last_error={self.last_error!r})")


def _dedup_key(rec: Dict[str, Any]):
    """
    去重键：优先用 `uid`（精确）；老记录没有 `uid` 时退回内容三元组。

    ⚠️ 内容三元组里**不能**用 `epoch`：Windows 的 `time.time()` 粒度约 15 ms，
    同一刻的两条记录 `epoch` 完全相同（实测），会互相误判成重复。
    """
    uid = rec.get('uid')
    if uid:
        return ('uid', uid)
    return ('triple', rec.get('ts'), rec.get('tool'), rec.get('status'),
            rec.get('duration_s'))


def _short(value, limit: int = 60) -> str:
    """把字段值压成表格里能看的一小段。"""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = text.replace('|', r'\|').replace('\n', ' ')
    return text if len(text) <= limit else text[:limit - 1] + '…'


#: 进程级默认审计器（惰性创建）—— 便于在库内部随手记一笔而不必到处传对象
_DEFAULT: Optional[AuditLog] = None


def record_call(tool: str, status: str = 'ok', **fields) -> Dict[str, Any]:
    """
    用**进程级默认审计器**记一笔（不存在则按默认目录创建）。

    给「不想改签名把 audit 对象传进来」的场景用。

    :param tool: str, 步骤名
    :param status: str, 状态
    :param fields: 附加字段
    :return: dict
    """
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = AuditLog()
    return _DEFAULT.record(tool, status=status, **fields)
