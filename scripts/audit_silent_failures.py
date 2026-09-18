# -*- coding: utf-8 -*-
r"""
静默失败审计（P1 第 4 条「静默失败审计」）
==========================================

问题
----
封装层里最容易出事的一类代码是**吞掉异常还不登记**：

```python
try:
    value = cst_something()
except Exception:
    return None          # ← 调用方以为「查到了，就是空」
```

`cst_solver/failures.py` 已经提供了结构化失败通道（`record_failure` /
`collect_failures`），但**「还有哪些地方在吞异常」此前没人盘过** ——
本脚本把它变成可复现的检查：

1. 用 `ast` 扫 6 个库包（不含 tests），找出**「handler 里只有 pass / continue /
   返回 None·False·[] / 只写日志」**的 `except` 块；
2. 每个站点必须有**登记理由**（`REGISTRY`）—— 探测类查询、尽力而为的清理、
   数值解析兜底…都是合理理由，但必须写下来；
3. 落在**写/判定类函数**（名字含 save/write/apply/set_/add_/create/export…
   或 guard 的存在性查询）里的吞异常会被标成 **`risky`**：
   要么 handler 里调用了 `record_failure(...)`，要么在登记表里显式写明
   `risky_ok` 的理由 —— **不允许悄悄新增**。

输出：`docs/guides/silent_failure_audit.md`；有未登记/理由不符的站点时退出码 1。

用法::

    python scripts/audit_silent_failures.py            # 扫描 + 写报告
    python scripts/audit_silent_failures.py --quiet    # 只打印汇总
"""

import argparse
import ast
import os
import sys
from collections import OrderedDict

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

#: 被审计的库包（tests 不审：测试里为了构造场景吞异常是正常的）
PACKAGES = ('cst_solver', 'mesh_grid', 'topo_modeler', 'topo_templates',
            'tpc_toolkit', 'tpc_service')

OUT_DEFAULT = os.path.join('docs', 'guides', 'silent_failure_audit.md')

#: handler 里这些调用算「已处理/已登记」，不算静默
_HANDLED_CALLS = ('record_failure', 'raise', 'structured_error', 'error_dict',
                  'fail_result', 'ToolError', 'CstOperationError')

#: 函数名的**分词**命中这些词 ⇒ 属于「写或判定路径」，吞异常风险更高。
#: ⚠️ 必须按 token 比对（第一版用子串，`reset_guard_state` 里的 "set_" 被误判成写路径）。
_RISKY_TOKENS = ('save', 'write', 'apply', 'commit', 'set', 'add', 'create',
                 'export', 'delete', 'remove', 'build', 'existed', 'exists',
                 'count', 'verify', 'validate', 'check')

#: 日志类调用（只写日志而没有结构化登记，仍算静默失败，但比纯 pass 好一点）
_LOG_CALLS = ('warning', 'warn', 'info', 'debug', 'error', 'exception')


# ============================================================
# 登记表：每个站点必须有理由（键 = 相对路径::qualname，max = 允许的条数）
# ============================================================

REGISTRY = OrderedDict([
    ('cst_solver/environment.py::discover_cst_installations', {
        'max': 1,
        'reason': '枚举安装目录时某个子目录读不动（权限/正在卸载）就跳过 —— 这是探测，'
                  '「跳过」本身就是结果，调用方拿到的是**能用的候选列表**。',
    }),
    ('cst_solver/failures.py::collect_failures', {
        'max': 1,
        'reason': '上下文管理器收尾时移除自己的收集器；此时移除失败意味着收集器栈已乱，'
                  '再抛异常只会掩盖用户的原始异常。',
    }),
    ('cst_solver/parameters.py::ParametersMixin._guard_param_probe', {
        'max': 1,
        'reason': '探测守卫层是否挂上了 `_param_probe`；没有守卫（离线/裸用）就返回 None，'
                  '调用方据此跳过守卫逻辑，属于能力探测。',
    }),
    ('cst_solver/parameters.py::ParametersMixin._set_parameter_description', {
        'max': 1,
        'risk_ok': '直接 API `SetParameterDescription` 在部分 CST 接口版本不暴露；'
                   '失败后**必须**回退到 VBA 历史命令（紧接着的那段代码），'
                   '回退成功即整体成功，因此这里不能登记成失败。',
        'reason': '版本回退路径：失败是预期内的分支，真正的结果由后面的 VBA 路径决定。',
    }),
    ('cst_solver/run_contract.py::_fingerprint_key', {
        'max': 1,
        'reason': '指纹取不到时返回 None，**契约本身**把「指纹不可用」当成一等结果'
                  '（`results_not_verified` / `results_missing`），不是静默。',
    }),
    ('cst_solver/run_contract.py::disk_result_probe', {
        'max': 1,
        'reason': '逐个结果目录探测可读性，读不动的跳过；最终由「有没有可用指纹」决定判定。',
    }),
    ('cst_solver/run_contract.py::project_path_of', {
        'max': 1,
        'reason': '从历史/属性里推断工程路径，候选来源逐个尝试，全部失败返回 None。',
    }),
    ('cst_solver/_guards.py::GuardState.param_existed', {
        'max': 1,
        'risk_ok': '这是**故意的 fail-safe 方向**：探针查不出来时按「新参数」处理，'
                   '宁可漏报脏状态也不要在建模流水线里误报；漏掉的那一半由 `run()` 前'
                   '的检查与 `validate_model()` 的 Rebuild 兜住（代码里有注释）。',
        'reason': '守卫探针失败（fail-safe：按「新参数」处理，由 Rebuild 兜底）。',
    }),
    ('cst_solver/_guards.py::GuardState.geometry_exists', {
        'max': 1,
        'risk_ok': '与 `param_existed` 同一口径（fail-safe 方向）：探针报错时按「还没有几何」'
                   '处理，同样由 Rebuild 兜底。',
        'reason': '守卫探针失败（fail-safe 方向，与 `param_existed` 一致）。',
    }),
    ('cst_solver/_guards.py::get_guard_state', {
        'max': 1,
        'reason': '读全局守卫状态，取不到就用默认值；状态是**诊断信息**，不影响下发内容。',
    }),
    ('cst_solver/_guards.py::reset_guard_state', {
        'max': 2,
        'reason': '重置内部状态时逐项清理，某项已经不存在就跳过（幂等重置）。',
    }),
    ('cst_solver/_result_core.py::Result.read_3d', {
        'max': 1,
        'reason': '遍历 3D 结果项，读不动的单项跳过；整体成功与否由返回的集合决定。',
    }),
    ('cst_solver/__init__.py::setup.__init__', {
        'max': 1,
        'reason': '打开工程失败后清理本次创建的会话，清理再失败只用 `logging.exception` '
                  '记录 —— 必须**保留原始异常**，不能再抛（代码里有注释）。',
    }),
    ('cst_solver/__init__.py::setup.__exit__', {
        'max': 1,
        'reason': '同上：`with` 收尾清理失败时只记录，不覆盖上下文里已有的原始异常。',
    }),
    ('cst_solver/modeling/picks.py::PickMixin.get_face_id_from_point', {
        'max': 1,
        'reason': '按坐标反查面号，CST 查询失败返回 None；调用方据此走「没查到」分支'
                  '（不是「查到 0 号面」）。',
    }),
    ('cst_solver/modeling/picks.py::PickMixin.get_edge_id_from_point', {
        'max': 1,
        'reason': '同 `get_face_id_from_point`（棱边版）。',
    }),
    ('cst_solver/modeling/picks.py::PickMixin.get_picked_count', {
        'max': 1,
        'risk_ok': '这是**故意区分 None 与 0**：查不到返回 None，`_pick_succeeded()` 明确'
                   '把 None 当成「退回消息判定」、把 0 当成「没选中」；方向安全，'
                   '而且这条在脏工程里是唯一可靠的正向信号（见 ARCHITECTURE §6 第 10 条）。',
        'reason': '已选数查不到返回 None（**不是 0**），调用方区分处理，方向安全。',
    }),
    ('cst_solver/modeling/picks.py::PickMixin._pick_succeeded', {
        'max': 1,
        'reason': '已选数不是整数时退回消息判定（脏工程里消息会反复报历史失败，'
                  '所以只作兜底）。',
    }),
    ('cst_solver/simulation/monitors.py::MonitorMixin._get_model_bbox', {
        'max': 1,
        'reason': '`GetBoundingBox` 在部分接口版本不存在（AttributeError）⇒ 返回 None '
                  '表示「不限制子体积」，docstring 已写明。',
    }),
    ('mesh_grid/plotting.py::_covers', {
        'max': 1,
        'reason': '字体是否覆盖某字符的探测，探测失败按「不覆盖」处理（保守方向：'
                  '会退回默认字体而不是画出豆腐块）。',
    }),
    ('mesh_grid/plotting.py::configure_chinese_font', {
        'max': 1,
        'reason': '逐个候选字体尝试配置，某个设不上就试下一个；全部失败会走后面的'
                  '警告分支，不是静默。',
    }),
    ('mesh_grid/tri_grid/topo_path.py::TopoPath.preview', {
        'max': 1,
        'reason': 'matplotlib 版本差异导致某些绘图参数不被接受时回退到基本调用；'
                  '预览不是建模结果，失败不影响下发内容。',
    }),
    ('topo_modeler/audit.py::_jsonable', {
        'max': 1,
        'reason': '把任意对象转成可 JSON 化的值，转不动就退化成 `repr` —— 审计日志'
                  '要尽量记下来，不能因为一个字段不可序列化就丢整条记录。',
    }),
    ('topo_modeler/audit.py::AuditLog.read', {
        'max': 1,
        'reason': '逐行读事件流，进程被杀导致的半行跳过（代码里有内联注释）。',
    }),
    ('topo_modeler/batch.py::_is_number', {
        'max': 1,
        'reason': '数值判定辅助函数：不是数就返回 False（判定本身，不是失败）。',
    }),
    ('topo_modeler/scanner.py::_is_number', {
        'max': 1,
        'reason': '同 `batch._is_number`（数值判定辅助）。',
    }),
    ('topo_modeler/lens_build_standalone.py::<module>', {
        'max': 2,
        'reason': '独立运行脚本（不是库 API）：① 枚举 CST 参数名时某个名字取不到就跳过；'
                  '② 结束时 `app.close()` 失败只记录 —— 不能让清理失败盖掉前面的结果。',
    }),
    ('tpc_toolkit/s2p.py::read_s2p_groups', {
        'max': 1,
        'reason': '**已知缺陷已修**（2026-09-17，本审计发现）：原来是裸 `except:`，'
                  '现在收窄为 `(TypeError, ValueError)` —— 解析不出数字就保留原文；'
                  '裸 except 会连 KeyboardInterrupt/SystemExit 一起吞掉。'
                  '保留 `pass` 是因为「非数字参数值按字符串留着」本身就是期望行为。',
    }),
    ('tpc_service/backends/fake.py::FakeBackend._write_synthetic_csv', {
        'max': 1,
        'risk_ok': '**假后端**（只在离线测试里用）没有其它产出通道，写不出合成 CSV 时'
                   '返回空串、调用方据此不加 CSV 产物；真后端（`CstBackend`）不走这条路。',
        'reason': '假后端的合成曲线写盘失败：返回空串表示「没有 CSV 产物」。',
    }),
])


# ============================================================
# 扫描
# ============================================================

def _is_empty_return(value) -> bool:
    """
    返回值是不是「假装成功」的空数据：``None`` / ``False`` / ``''`` / ``0`` /
    空 ``[]`` ``{}`` ``()``。

    ⚠️ 空容器在 AST 里是 `ast.List`/`ast.Dict`/`ast.Tuple`（**不是** `Constant`）——
    第一版漏了它们，`return []` 这种最典型的「把失败变成空数据」反而没被认出来。
    """
    if value is None:
        return True
    if isinstance(value, ast.Constant):
        return value.value is None or value.value is False or value.value == '' \
            or value.value == 0
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return not value.elts
    if isinstance(value, ast.Dict):
        return not value.keys
    return False


def _is_swallowing(body):
    """
    判断一个 handler 的 body 是否「吞掉异常」。

    只写日志、只 `pass`/`continue`/`break`、或返回空数据（`None`/`False`/`[]`/…）都算吞掉；
    只要出现 `record_failure(...)`、`raise`、返回结构化错误、或返回别的值，就不算。

    :param body: list[ast.stmt]
    :return: bool
    """
    for stmt in body:
        if isinstance(stmt, (ast.Pass, ast.Continue, ast.Break)):
            continue
        if isinstance(stmt, ast.Raise):
            return False
        if isinstance(stmt, ast.Return):
            if _is_empty_return(stmt.value):
                continue
            return False
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            name = getattr(stmt.value.func, 'attr',
                           getattr(stmt.value.func, 'id', ''))
            if name in _HANDLED_CALLS:
                return False                       # 已登记，不算静默
            if name in _LOG_CALLS:
                continue                           # 只写日志：算「静默但至少留痕」
            return False
        return False
    return True


def _qualname(tree):
    """给每个节点算出「外层→内层」的限定名映射（用于站点键）。"""
    mapping = {}

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                name = f'{prefix}.{child.name}' if prefix else child.name
                mapping[id(child)] = name
                walk(child, name)
            else:
                walk(child, prefix)

    mapping[id(tree)] = '<module>'
    walk(tree, '')
    for node in ast.walk(tree):
        if id(node) not in mapping:
            mapping[id(node)] = None
    return mapping


def _owner_name(tree, name_of, node):
    """包含给定节点的最内层函数/类限定名（取不到就用 ``<module>``）。"""
    best = '<module>'
    for candidate in ast.walk(tree):
        if candidate is node:
            continue
        name = name_of.get(id(candidate))
        if not name:
            continue
        start = getattr(candidate, 'lineno', -1)
        end = getattr(candidate, 'end_lineno', 10 ** 9)
        if start <= node.lineno <= end:
            if name.count('.') >= best.count('.') and name != '<module>':
                best = name
    return best


def _is_risky(owner: str) -> bool:
    """
    函数限定名是否落在「写或判定路径」上（按词判定，见 :data:`_RISKY_TOKENS`）。

    :param owner: str, 形如 ``PickMixin.get_picked_count``
    :return: bool
    """
    leaf = owner.rsplit('.', 1)[-1].strip('_').lower()
    tokens = [token for token in leaf.split('_') if token]
    return any(token in _RISKY_TOKENS for token in tokens)


def scan(packages=PACKAGES, root=_REPO):
    """
    扫描库包，返回所有「吞掉异常」的站点。

    :param packages: 序列, 包名
    :param root: str, 仓库根
    :return: list[dict], ``{'key', 'file', 'line', 'owner', 'exc', 'action', 'risky'}``
    """
    sites = []
    for package in packages:
        base = os.path.join(root, package)
        for dirpath, _dirnames, filenames in os.walk(base):
            parts = os.path.relpath(dirpath, root).split(os.sep)
            if 'tests' in parts:
                continue
            for filename in sorted(filenames):
                if not filename.endswith('.py'):
                    continue
                path = os.path.join(dirpath, filename)
                try:
                    with open(path, encoding='utf-8') as handle:
                        source = handle.read()
                    tree = ast.parse(source)
                except (OSError, SyntaxError):
                    continue
                rel = os.path.relpath(path, root).replace('\\', '/')
                lines = source.splitlines()
                name_of = _qualname(tree)
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Try):
                        continue
                    for handler in node.handlers:
                        if not _is_swallowing(handler.body):
                            continue
                        owner = _owner_name(tree, name_of, node)
                        action = ' | '.join(
                            lines[stmt.lineno - 1].strip()
                            for stmt in handler.body if stmt.lineno <= len(lines))
                        exc = ast.unparse(handler.type) if handler.type else 'bare'
                        risky = _is_risky(owner)
                        sites.append({
                            'key': f'{rel}::{owner}',
                            'file': rel, 'line': node.lineno, 'owner': owner,
                            'exc': exc, 'action': action[:80], 'risky': risky,
                            'registered': _has_record_failure(handler),
                        })
    return sites


def _has_record_failure(handler) -> bool:
    """handler 里是否调用了 `record_failure(...)`。"""
    for stmt in ast.walk(handler):
        if isinstance(stmt, ast.Call):
            name = getattr(stmt.func, 'attr', getattr(stmt.func, 'id', ''))
            if name == 'record_failure':
                return True
    return False


def evaluate(sites, registry=REGISTRY):
    """
    对照登记表评估扫描结果。

    :return: dict, ``{'problems': [...], 'counts': {...}, 'sites': sites}``
    """
    problems = []
    per_key = OrderedDict()
    for site in sites:
        per_key.setdefault(site['key'], []).append(site)

    for key, entries in per_key.items():
        entry = registry.get(key)
        if entry is None:
            problems.append(
                f'未登记：{key}（{len(entries)} 处，首个在 L{entries[0]["line"]}）'
                f' —— 请在 scripts/audit_silent_failures.py 的 REGISTRY 里写明理由，'
                f'或改成 record_failure(...)/抛异常')
            continue
        if len(entries) > entry.get('max', 1):
            problems.append(
                f'条数超出登记：{key} 实测 {len(entries)} 处 > 登记 {entry.get("max", 1)} 处')
        if not entry.get('reason'):
            problems.append(f'登记缺少理由：{key}')
    for key, entry in registry.items():
        if key not in per_key:
            problems.append(f'登记已失效（代码里找不到该站点，请删掉这行）：{key}')

    risky = [site for site in sites
             if site['risky'] and not site['registered']
             and not (registry.get(site['key']) or {}).get('risk_ok')]
    for site in risky:
        problems.append(
            f'**写/判定路径**里的静默失败未处理：{site["key"]} L{site["line"]} '
            f'（{site["action"]}）—— 请调用 record_failure(...) 或在登记表里写明 '
            f'risk_ok 的理由')
    counts = {'sites': len(sites), 'keys': len(per_key), 'risky': len(risky)}
    return {'problems': problems, 'counts': counts, 'sites': sites,
            'by_key': per_key}


def render_markdown(result, registry=REGISTRY) -> str:
    """生成报告。"""
    lines = ['# 静默失败审计', '',
             f'- 扫描范围：{" / ".join(f"`{p}`" for p in PACKAGES)}（不含 tests）',
             f'- 规则：`except` 块里只有 `pass`/`continue`/返回 `None·False·[]·\'\'`/'
             f'只写日志 ⇒ 算「吞掉异常」，必须有登记理由',
             f'- 生成：`python scripts/audit_silent_failures.py`', '',
             f"命中站点 **{result['counts']['sites']}** 处，"
             f"涉及函数 **{result['counts']['keys']}** 个；"
             f"未处理的写/判定路径 **{result['counts']['risky']}** 处。", '',
             '## 1. 逐站点', '',
             '| 位置 | 函数 | 异常 | handler 动作 | 登记理由 |', '|---|---|---|---|---|']
    for key, entries in sorted(result['by_key'].items()):
        entry = registry.get(key, {})
        reason = entry.get('reason', '**未登记**')
        for site in entries:
            lines.append(f"| `{site['file']}:{site['line']}` | `{site['owner']}` | "
                         f"`{site['exc']}` | `{site['action']}` | {reason} |")
    lines += ['', '## 2. 未处理的问题', '']
    if result['problems']:
        lines += [f'- {problem}' for problem in result['problems']]
    else:
        lines.append('（无）')
    lines += ['', '> 这张表的作用：**新增的静默失败必须先在这里写明理由**。'
                  '探测类查询、尽力而为的清理、解析兜底都是合理理由；'
                  '写/判定路径上的静默失败则要求 `record_failure(...)` 或显式 `risk_ok`。', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description='静默失败审计')
    parser.add_argument('--out', default=OUT_DEFAULT, help='报告输出路径')
    parser.add_argument('--quiet', action='store_true', help='只打印汇总')
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    result = evaluate(scan())
    print(f"命中 {result['counts']['sites']} 处，涉及 "
          f"{result['counts']['keys']} 个函数；"
          f"未处理的写/判定路径 {result['counts']['risky']} 处")
    for problem in result['problems']:
        print('  [问题]', problem)

    if not args.quiet:
        out = args.out if os.path.isabs(args.out) else os.path.join(_REPO, args.out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w', encoding='utf-8') as handle:
            handle.write(render_markdown(result))
        print(f'报告已写出：{out}')
    return 1 if result['problems'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
