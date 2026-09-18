# -*- coding: utf-8 -*-
"""
P4 补充核验：建成工程的「参数表 ↔ 表达式 ↔ 建模历史」闭合性
============================================================

为什么要查（2026-09-17 V1 真机复验里挖出来的）
----------------------------------------------
`ant_AB_120` 落盘的 `xmax = 8.85125` 与旧 notebook 的 `a*x1+y1*e1+e1 = 6.18375`
对不上，而且 AB/BA 两个拓扑的 `xmax` **完全相同**（参考工程里两者是不同的）。
逐层查下来：`xmax` 根本不是库算出来的，而是模板 `tmp.cst` **自带的遗留参数**
（模板里就是 8.85125，`expr` 为空）。同一张表里 `x1=8 / y1=8` 也是模板遗留值
（本次直段 18、臂长 14）。

也就是说 `scripts/verify_antenna_mapping.py` 里那句注释
「干净模板（只含单位/边界/网格设置）」**是错的**：它带着一整套旧天线工程的参数
（本次实测 85 项里只有约 30 项是库下发的）。

「模板带垃圾参数」本身不一定有害——只有当**某个表达式引用了它**时，几何才会
静默地跟着模板跑。本脚本就是把这件事查清楚，全部离线（不连 CST、不需要求解）：

  A. **表达式闭合**：每个参数的 `expr` 里引用的名字是否都在参数表里定义
     （引用到未定义的名字 ⇒ 由 CST 在建模时报错，属于 FAIL）
  B. **引用统计**：参数表里每个名字是否真的被「建模历史 + 其它表达式」引用
  C. **未引用分类**：未引用的名字是「模板本来就有的遗留」（无害，INFO）还是
     「库下发却没人用」（死写入，FAIL）
  D. **模板遗留却被引用**：值相同 ⇒ 几何可能依赖模板值（WARN，需人看）；
     值不同 ⇒ 本次已被库重写过（INFO）

⚠️ 已知保守处：`a`/`h`/`N` 这类单字母参数名用词边界匹配仍可能被历史里的
无关字符串命中，从而把「未引用」漏报成「已引用」。漏报方向是保守的，
不会把坏的说成好的。

用法
----
    python scripts/verify_model_parameter_usage.py <工程目录> [更多工程目录...]
    python scripts/verify_model_parameter_usage.py --template D:\\TPC_out\\tmp <工程>
    python scripts/verify_model_parameter_usage.py --json <工程>

工程目录既可以是 CST 的**文件夹形式**工程（含 `Model/Parameters.json`），
也可以是单文件 `.cst` 所在目录的父目录（自动找同名文件夹）。
"""

import argparse
import json
import os
import re
import sys

DEFAULT_TEMPLATE = r'D:\TPC_out\tmp'          # 干净模板（文件夹形式）

#: CST 表达式内置函数/常量 —— 出现在 `expr` 里不算「未定义参数」引用。
#  不加这个集合，`sqr(3)`、`int(xup)`、`sind(60)` 里的 `sqr/int/sind`
#  会被当成未定义名字，把 A 检查刷成一片假 FAIL。
CST_FUNCTIONS = frozenset({
    'sqr', 'sqrt', 'int', 'abs', 'min', 'max', 'mod', 'pow', 'round',
    'floor', 'ceil', 'sign', 'exp', 'log', 'log10', 'ln',
    'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'atan2',
    'sind', 'cosd', 'tand', 'asind', 'acosd', 'atand',
    'sinh', 'cosh', 'tanh', 'deg', 'rad', 'pi',
})

_results = []


def record(item, status, detail, **extra):
    """记录一条核验结论。status ∈ {OK, INFO, WARN, FAIL, UNKNOWN}。"""
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    extra_text = ''
    if extra:
        extra_text = '  ' + json.dumps(extra, ensure_ascii=False, default=str)
    print(f'[{status:^7}] {item}: {detail}{extra_text}', flush=True)
    return entry


def _load_parameters(project_dir):
    """读工程参数表，返回 ``{name: {...}}``；读不到返回 (None, 路径)。

    CST 的 `Parameters.json` 每条只有 `name` / `value` / `expr` 三个字段，其中
    **`expr` 是表达式原文**（不是描述文字）：

    * 常量参数的 `expr` 就是它自己的数字文本（``xup`` → ``'25'``）；
    * 公式参数是公式（``p1x`` → ``'-a'``、``N`` → ``'(y0+4)*2'``）；
    * **公式引用不到名字时 `value` 为空串** —— 这是「CST 自己都没算出来」的指纹
      （模板自带一个死参数 `N = (y0+4)*2`，`y0` 从未定义）。

    因此这里派生出 ``is_formula``（expr 与 value 文本不同 ⇒ 公式）和
    ``value_missing``（value 为空 ⇒ 求值失败），供后面的判据使用。
    """
    path = os.path.join(project_dir, 'Model', 'Parameters.json')
    if not os.path.isfile(path):
        return None, path
    with open(path, encoding='utf-8-sig') as handle:
        data = json.load(handle)
    table = {}
    for item in data.get('parameters', ()):
        value = item.get('value')
        expr = (item.get('expr') or '').strip()
        table[item['name']] = {
            'value': value,
            'expr': expr,
            'is_formula': bool(expr) and expr != str(value),
            'value_missing': value in (None, ''),
        }
    return table, path


def _history_strings(project_dir):
    """把建模历史里所有字符串抠出来（CST 把 VBA 命令逐条存进 ModelHistory.json）。"""
    texts = []
    roots = [os.path.join(project_dir, 'Model', '3D', 'ModelHistory.json'),
             os.path.join(project_dir, 'Model', 'ModelHistory.json')]
    found = None
    for path in roots:
        if os.path.isfile(path):
            found = path
            break
    if found is None:
        return None, roots[0]
    with open(found, encoding='utf-8-sig') as handle:
        data = json.load(handle)

    def walk(node):
        if isinstance(node, str):
            texts.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)

    walk(data)
    return texts, found


def _references(name, texts):
    """名字是否在给定文本里被当作独立标识符引用（**大小写敏感**）。

    大小写必须敏感：历史里的 `.Xmax "expanded open"` 是边界设置，
    不是参数 `xmax`；不敏感匹配会把它误判成「xmax 被引用了」。
    """
    pattern = re.compile(r'(?<![A-Za-z0-9_])' + re.escape(name) + r'(?![A-Za-z0-9_])')
    for text in texts:
        if pattern.search(text):
            return True
    return False


def _expr_names(expr):
    """从表达式里抠出标识符（CST 表达式允许的字符集之外的一律当分隔符）。"""
    return set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', expr or ''))


def _same_value(first, second):
    """两个参数值是否相同 —— 文本相等**或**数值相等。

    必须带数值这一条：CST 把 `lf2=3` 存成 `'3'`、本次写成 `3.0` 存成 `'3.0'`，
    纯文本比较会把「值其实没变」误判成「被重写过」。
    """
    if str(first) == str(second):
        return True
    try:
        return float(first) == float(second)
    except (TypeError, ValueError):
        return False


def audit_project(project_dir, template_table=None, label=None):
    """核验一个建成工程，返回结论字典。"""
    label = label or project_dir
    table, param_path = _load_parameters(project_dir)
    if table is None:
        record(f'{label} 参数表', 'FAIL', f'没有参数表：{param_path}')
        return None
    record(f'{label} 参数表', 'OK', f'{len(table)} 项参数', path=param_path)

    texts, history_path = _history_strings(project_dir)
    if texts is None:
        record(f'{label} 建模历史', 'FAIL', f'没有建模历史：{history_path}')
        return None
    # 引用来源 = 建模历史字符串 ∪ 所有参数的表达式
    corpus = list(texts) + [item['expr'] for item in table.values()]
    record(f'{label} 建模历史', 'OK', f'{len(texts)} 条字符串', path=history_path)

    # --- B. 引用统计（先算，A 的严重度依赖它） -----------------------------
    used = {name for name in table if _references(name, corpus)}
    unused = sorted(set(table) - used)

    # --- A. 表达式闭合：公式里引用的名字是否都有定义 -----------------------
    #     只查**公式**参数（常量参数的 expr 就是数字文本，查它没有意义）。
    #     区分严重度：在用的公式引用未定义名字 ⇒ FAIL（CST 会按弹窗/报错处理）；
    #     死参数里的坏公式 ⇒ WARN（模板自带 `N=(y0+4)*2`，实测被容忍）。
    undefined = {}
    dead_undefined = {}
    for name, item in table.items():
        if not item['is_formula']:
            continue
        missing = sorted(_expr_names(item['expr']) - set(table) - CST_FUNCTIONS)
        if missing:
            (undefined if name in used else dead_undefined)[name] = missing
    unresolved = sorted(n for n, i in table.items() if i['value_missing'])
    if undefined:
        record(f'{label} A 表达式闭合', 'FAIL',
               f'{len(undefined)} 个**在用**公式引用了未定义的名字',
               undefined_refs=undefined)
    elif dead_undefined:
        record(f'{label} A 表达式闭合', 'WARN',
               f'未被引用的死参数里有坏公式 {len(dead_undefined)} 项'
               f'（CST 实测容忍，不影响几何）',
               dead_param_bad_expr=dead_undefined)
    else:
        record(f'{label} A 表达式闭合', 'OK',
               f'{sum(1 for i in table.values() if i["is_formula"])} 个公式参数，'
               f'引用名字全部有定义')
    if unresolved:
        record(f'{label} A2 参数求值', 'WARN',
               f'{len(unresolved)} 个参数在 CST 里**求值为空**（通常是引用了未定义名字）：'
               f'{unresolved}',
               unresolved=unresolved,
               expressions={n: table[n]['expr'] for n in unresolved})

    # --- C. 未引用分类 -----------------------------------------------------
    #     判据不能只看「名字在不在模板里」：模板自己也带 `xup=37/yup=24/ydn=24`，
    #     和库下发同名。真正的证据是**值**——
    #       · 模板里没有该名字                      ⇒ 本次新增，却没人引用 ⇒ 死写入
    #       · 有表达式（expr 非空）                 ⇒ 派生参数，值随输入变，不判
    #       · expr 为空且值 ≠ 模板值                ⇒ 被本次重写过，却没人引用 ⇒ 死写入
    #       · expr 为空且值 = 模板值                ⇒ 模板遗留，无害
    if template_table is None:
        record(f'{label} B 引用统计', 'OK',
               f'已引用 {len(used)} / 未引用 {len(unused)}（样例）',
               unused_sample=unused[:12], unused_total=len(unused))
        record(f'{label} C 未引用分类', 'UNKNOWN',
               '未给出 --template，无法区分「模板遗留」与「库下发死写入」')
        dead_writes = []
    else:
        record(f'{label} B 引用统计', 'OK',
               f'已引用 {len(used)} / 未引用 {len(unused)}',
               unused=unused)
        legacy, dead_writes, derived = [], [], []
        for name in unused:
            tpl = template_table.get(name)
            ours = table[name]
            if tpl is None:
                dead_writes.append(name)              # 本次新增却没人引用
            elif ours['is_formula']:
                derived.append(name)                  # 公式参数：值随输入变，不判定
            elif not _same_value(tpl['value'], ours['value']):
                dead_writes.append(name)              # 常量被重写过却没人引用
            else:
                legacy.append(name)                   # 与模板逐字一致 ⇒ 模板遗留
        record(f'{label} C 未引用分类', 'FAIL' if dead_writes else 'INFO',
               f'模板遗留未引用 {len(legacy)} 项（无害）；'
               f'本次写过却未引用 {len(dead_writes)} 项；'
               f'派生参数未引用 {len(derived)} 项',
               legacy_unused=legacy, library_dead_writes=dead_writes,
               derived_unused=derived,
               dead_write_values={n: table[n]['value'] for n in dead_writes},
               dead_write_template_values={n: template_table[n]['value']
                                           for n in dead_writes if n in template_table})

    # --- D. 模板遗留却被引用：几何是否可能跟着模板值跑 ----------------------
    if template_table is not None:
        risky, rewritten = [], []
        for name in sorted(used):
            if name not in template_table:
                continue
            same = _same_value(template_table[name]['value'], table[name]['value'])
            (risky if same else rewritten).append(name)
        record(f'{label} D 模板遗留项被引用', 'WARN' if risky else 'OK',
               f'值未变（无法区分谁写的，几何可能依赖模板值）{len(risky)} 项；'
               f'本次已重写 {len(rewritten)} 项',
               unchanged_and_used=risky, rewritten=rewritten)

    return {'label': label, 'defined': len(table), 'used': len(used),
            'unused': unused, 'undefined_refs': undefined,
            'dead_undefined_exprs': dead_undefined,
            'classified': template_table is not None,
            'dead_writes': dead_writes}


def _resolve_project(path):
    """允许传「文件夹工程」或「单文件 .cst 路径」，统一解析到文件夹工程。"""
    if os.path.isdir(os.path.join(path, 'Model')):
        return path
    if os.path.isfile(path) and path.lower().endswith('.cst'):
        folder = os.path.splitext(path)[0]
        if os.path.isdir(os.path.join(folder, 'Model')):
            return folder
        return path                     # 单文件工程（参数表读不到，交给上层报错）
    return path


#: 公开别名 —— 本模块要被 `verify_antenna_mapping.py` 等真机脚本复用：
#: `load_parameters` 读参数表、`resolve_project` 把 `.cst` 路径解析到文件夹工程、
#: `RESULTS` 是同一份结论列表（便于并入别的脚本汇总）。
load_parameters = _load_parameters
resolve_project = _resolve_project
RESULTS = _results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('projects', nargs='+', help='一个或多个工程目录（文件夹形式）')
    parser.add_argument('--template', default=DEFAULT_TEMPLATE,
                        help=f'干净模板的文件夹形式工程（默认 {DEFAULT_TEMPLATE}）')
    parser.add_argument('--no-template', action='store_true',
                        help='不做模板对比（只做 A/B，不判定死写入）')
    parser.add_argument('--json', action='store_true', help='最后附上完整 JSON')
    args = parser.parse_args(argv)

    template_table = None
    if not args.no_template:
        template_table, template_path = _load_parameters(_resolve_project(args.template))
        if template_table is None:
            record('模板参数表', 'UNKNOWN',
                   f'模板读不到参数表，退化为不做分类：{template_path}')
        else:
            record('模板参数表', 'OK', f'{len(template_table)} 项（模板自带，'
                                      f'其中未被引用的属于遗留）', path=template_path)

    audited = []
    for project in args.projects:
        resolved = _resolve_project(project)
        result = audit_project(resolved, template_table)
        if result is not None:
            audited.append(result)
        print('', flush=True)

    print('=== 汇总 ===')
    for result in audited:
        dead = len(result['dead_writes']) if result['classified'] else '—'
        print(f"{result['label']}: 参数 {result['defined']} / 已引用 {result['used']} "
              f"/ 未引用 {len(result['unused'])} / 库下发死写入 {dead}"
              + ('' if result['classified'] else '（未给 --template，不判死写入）'))
    failed = [r for r in _results if r['status'] == 'FAIL']
    print(f"\nOK {len([r for r in _results if r['status'] == 'OK'])} / "
          f"INFO {len([r for r in _results if r['status'] == 'INFO'])} / "
          f"WARN {len([r for r in _results if r['status'] == 'WARN'])} / "
          f"FAIL {len(failed)}")
    if args.json:
        print(json.dumps({'results': _results, 'audited': audited},
                         ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
