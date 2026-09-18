# -*- coding: utf-8 -*-
r"""
P2 ③ + P3 ④ 真机验收：真实 CST 后端 + 真 stdio MCP 通道（**只建模，不求解**）
==============================================================================

一次 CST 会话同时收掉两条计划待办（[next_plan/README.md](../docs/next_plan/README.md)）：

P2「对象归属与状态语义的真机验证」
----------------------------------
1. **只释放自己创建的会话**：先由本脚本自己开一个「别人的」DE（模拟第三方客户端
   已经开着 CST），再让服务跑完一条真实任务 —— 服务自己的会话必须已关闭
   （DE 数量回到 基线 + 1），而**那个别人的 DE 必须还活着**。
2. **重启后未完成任务标记中断**：磁盘上留一条 `queued` 记录，换一个新服务起来后
   必须变成 `interrupted` 且**不自动重跑**（DE 数量不变 ⇒ 没有偷偷开 CST）。
   同时上一条**已完成**的真任务在重启后必须仍是 `succeeded`（真记录往返不丢状态）。

P3「CST 原生输出与协议通道」
---------------------------
`cst_mcp.protocol_stdout()` 是**进程内**重定向，管得住 Python 的 `print`；
CST 进程自己往 stdout 写的东西它管不着。本脚本让 CST 在**真 stdio 协议通道开着**的
时候真的建模（CST 启动/建模全程），全部收发都走 SDK 真客户端
（`mcp.client.stdio.stdio_client` + `ClientSession`）——
协议通道一旦被 CST 的原生输出污染，JSON-RPC 解析立刻失败。
另加一道直接证据：任务**真的产出了 CST 工程目录**（`Model/Parameters.json`），
证明跑的是真 CST 而不是替身。

用法
----
    python scripts/verify_service_mcp_real.py                 # 真 CST + 真 stdio
    python scripts/verify_service_mcp_real.py --topology AB
    python scripts/verify_service_mcp_real.py --no-cst        # 只验协议通道骨架（假后端）

注意
----
* **不求解**：只调 `build_model`（服务侧 kind=`build`）；脚本不碰 `solve`/`study`。
* 只新建临时工程；收尾关闭本脚本自己开的 DE（那个「别人的」DE 由脚本自己关）。
"""

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MCP_SRC = PROJECT_ROOT / 'integrations' / 'cst-mcp' / 'src'
for _extra in (PROJECT_ROOT, MCP_SRC, Path(__file__).resolve().parent):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from topo_modeler.batch import (                        # noqa: E402
    close_extra_design_environments,
    design_environment_baseline,
    design_environment_query,
)

CLEAN_TEMPLATE = r'D:\TPC_out\tmp.cst'                  # 干净模板（文件夹形式见 tmp\）
POLL_DEADLINE = 900.0                                   # 建模级任务：秒级~分钟级
POLL_INTERVAL = 2.0

_results = []
_baseline = set()


def record(item, status, detail, **extra):
    """记录一条结论。status ∈ {OK, INFO, WARN, FAIL, UNKNOWN}。"""
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    extra_text = ''
    if extra:
        extra_text = '  ' + json.dumps(extra, ensure_ascii=False, default=str)
    print(f'[{status:^7}] {item}: {detail}{extra_text}', flush=True)
    return entry


# ================================================================
# CST 设计环境（DE）查询：只信 design_environment_query（区分「没有」与「问不到」）
# ================================================================

def de_snapshot(tag):
    """取一次 DE 快照并登记。返回 (ok, pids)。"""
    query = design_environment_query()
    if not query['ok']:
        record(f'DE 快照（{tag}）', 'UNKNOWN',
               f'查不到 DE，不能当否定证据：{query["reason"]}')
        return False, set()
    record(f'DE 快照（{tag}）', 'OK', f'{len(query["pids"])} 个：{query["pids"]}',
           pids=query['pids'])
    return True, set(query['pids'])


def ensure_cst_importable():
    """让 `cst.interface` 可导入：把 CST 的 python 库目录放进 `sys.path`。

    ⚠️ **不做这一步，`design_environment_query()` 只会返回「cst.interface 不可导入」
    ——那是「问不到」，绝不能当「一个 DE 都没有」用**（P4/V8 的教训）。
    `cst_solver.CST_PYTHON_LIB` 是公开常量，不需要碰私有函数。

    :return: str, 加进 `sys.path` 的库目录
    """
    import cst_solver

    lib = cst_solver.CST_PYTHON_LIB
    if lib and lib not in sys.path:
        sys.path.append(lib)
    import cst.interface                                # noqa: F401
    return lib or ''


def open_foreign_de():
    """开一个「别人的」DE（不属于 MCP 服务）。"""
    from cst.interface import DesignEnvironment
    return DesignEnvironment()


# ================================================================
# MCP 客户端接线
# ================================================================

def server_params(workdir, cwd, backend=None):
    """真 stdio 服务进程参数；`backend='fake'` 时用假后端（只验协议骨架）。"""
    from mcp import StdioServerParameters

    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join(
        [str(MCP_SRC), str(PROJECT_ROOT), env.get('PYTHONPATH', '')]).rstrip(os.pathsep)
    env['TPC_MCP_WORKDIR'] = str(workdir)
    env['PYTHONIOENCODING'] = 'utf-8'
    env.pop('TPC_MCP_BACKEND', None)                    # 默认真 CST 后端
    if backend:
        env['TPC_MCP_BACKEND'] = backend
    return StdioServerParameters(command=sys.executable, args=['-m', 'cst_mcp'],
                                 env=env, cwd=str(cwd))


def with_client(params, scenario):
    """用 SDK 真客户端连真 stdio 子进程跑一个场景。"""
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async def runner():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await scenario(session)

    return asyncio.run(runner())


async def _payload(result):
    """把 CallToolResult 归一成 dict。"""
    if result.structuredContent is not None:
        return result.structuredContent
    if result.content:
        return json.loads(result.content[0].text)
    return {}


def spec_for(tmpdir, workdir, topology, length=18):
    """直波导建模规格（与 README/P3 离线测试同构，但模板是真 .cst）。"""
    template = os.path.join(tmpdir, 'tmp.cst')
    if not os.path.exists(template):
        shutil.copy2(CLEAN_TEMPLATE, template)
    return {'model': {'type': 'straight_waveguide'},
            'geometry': {'length': length, 'topology': topology},
            'output': {'template_cst': template,
                       'path': os.path.join(workdir, f'{topology}{length}.cst')}}


def job_record(workdir, job_id):
    """读磁盘上的任务记录（服务写的是 `jobs/<job_id>.json`）。"""
    path = os.path.join(workdir, 'jobs', f'{job_id}.json')
    if not os.path.isfile(path):
        return None, path
    try:
        with open(path, encoding='utf-8-sig') as handle:
            return json.load(handle), path
    except Exception as exc:                            # noqa: BLE001
        return {'_read_error': f'{type(exc).__name__}: {exc}'}, path


def find_cst_projects(root):
    """找出工作目录下**真 CST 工程**（有 `Model/Parameters.json` 的目录）。"""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        if 'Parameters.json' in filenames and os.path.basename(dirpath) == 'Model':
            found.append(os.path.dirname(dirpath))
    return found


# ================================================================
# 场景 1：真建模（同一次会话里核对会话归属 + 协议通道）
# ================================================================

async def _scenario_build(session, spec, request_id):
    caps = await _payload(await session.call_tool('get_capabilities', {}))
    tools = await session.list_tools()
    preflight = await _payload(await session.call_tool(
        'validate_model_spec', {'spec': spec}))
    build = await _payload(await session.call_tool(
        'build_model', {'spec': spec, 'request_id': request_id}))
    job_id = build.get('job_id')
    status = None
    polls = 0
    deadline = time.time() + POLL_DEADLINE
    while job_id and time.time() < deadline:
        status = await _payload(await session.call_tool(
            'get_job_status', {'job_id': job_id}))
        polls += 1
        if status.get('status') in ('succeeded', 'failed', 'interrupted'):
            break
        await asyncio.sleep(POLL_INTERVAL)
    return {'capabilities': caps, 'tool_names': [t.name for t in tools.tools],
            'preflight': preflight, 'build': build, 'status': status,
            'polls': polls}


# ================================================================
# 场景 2：重启后状态语义（同一工作目录，新服务进程）
# ================================================================

async def _scenario_restart(session, job_ids):
    out = {}
    for label, job_id in job_ids.items():
        if not job_id:
            out[label] = {'_skipped': f'{label} 没有 job_id'}
            continue
        result = await session.call_tool('get_job_status', {'job_id': job_id})
        out[label] = {'is_error': bool(result.isError),
                      'payload': await _payload(result)}
    return {'statuses': out,
            'capabilities': await _payload(await session.call_tool(
                'get_capabilities', {}))}


def craft_queued_record(workdir, spec, request_id):
    """在磁盘上留一条 `queued` 记录（不启动 worker，于是它「未完成」）。

    用**另一份**模板副本（`crafted_<request_id>.cst`）：服务注册工程时会复制到工作目录，
    拿已被前面任务注册过的那个路径会撞 `project_exists`。
    """
    from tpc_service import RunService
    from tpc_service.backends.cst_backend import CstBackend

    template = spec['output']['template_cst']
    safe_id = re.sub(r'[^0-9A-Za-z_-]+', '_', str(request_id or 'crafted'))
    crafted_template = os.path.join(os.path.dirname(template),
                                    f'crafted_{safe_id}.cst')
    shutil.copy2(template, crafted_template)
    service = RunService(workdir, backend=CstBackend(), autostart=False,
                         recover=False)
    job = service.submit('build', project_path=crafted_template,
                         params={'spec': spec}, request_id=request_id,
                         copy=True)
    return job['job_id'], job


def main(argv=None):
    global _baseline
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('--topology', default='BA', choices=('AB', 'BA'))
    parser.add_argument('--length', type=int, default=18)
    parser.add_argument('--no-cst', action='store_true',
                        help='用假后端只验协议通道与接线（不启动 CST）')
    args = parser.parse_args(argv)

    from cst_dialog_guard import check_dialogs, describe_dialogs, save_prompts

    # DE 清点要能真的查到：先把 CST 的 python 库目录放进 sys.path，否则
    # `design_environment_query()` 只会返回「cst.interface 不可导入」——那是
    # 「问不到」，不能当「没有 DE」用。基线必须在**这之后**取。
    if not args.no_cst:
        try:
            lib = ensure_cst_importable()
            record('cst.interface 准备', 'OK', f'已把 CST python 库加入 sys.path：{lib}')
        except Exception as exc:                        # noqa: BLE001
            record('cst.interface 准备', 'WARN',
                   f'{type(exc).__name__}: {exc}（DE 清点将不可用）')

    _baseline = design_environment_baseline()
    print(f'基线 DE：{sorted(_baseline)}', flush=True)
    check_dialogs('开工前')
    print(f'开工前 CST 对话框：\n{describe_dialogs()}', flush=True)

    tmpdir = tempfile.mkdtemp(prefix='tpc_svc_mcp_')
    workdir = os.path.join(tmpdir, 'svc')
    os.makedirs(workdir, exist_ok=True)
    print(f'临时目录：{tmpdir}\n服务工作目录：{workdir}', flush=True)

    spec = spec_for(tmpdir, workdir, args.topology, args.length)
    backend = 'fake' if args.no_cst else None

    foreign = None
    foreign_pids = set()
    try:
        # ---- 「别人的」会话：服务不许关它 ------------------------------
        if not args.no_cst:
            try:
                foreign = open_foreign_de()
                time.sleep(3.0)                         # 等 DE 进程起来
                ok, pids = de_snapshot('开好「别人的」DE 之后')
                foreign_pids = pids - _baseline
                record('「别人的」DE', 'OK' if foreign_pids else 'WARN',
                       f'{type(foreign).__name__} 已开；本次新增 DE '
                       f'{sorted(foreign_pids)}（基线 {sorted(_baseline)}）',
                       foreign_pids=sorted(foreign_pids))
            except Exception as exc:                    # noqa: BLE001
                foreign = None
                record('「别人的」DE', 'FAIL',
                       f'开不出来，无法验证「只关自己的会话」：'
                       f'{type(exc).__name__}: {exc}')

        # ---- 场景 1：真建模 -------------------------------------------
        before = set(design_environment_query()['pids'])
        started = time.time()
        try:
            first = with_client(server_params(workdir, tmpdir, backend),
                                lambda s: _scenario_build(s, spec, 'svc-mcp-1'))
        except Exception as exc:                        # noqa: BLE001
            record('MCP 真建模（真 stdio）', 'FAIL',
                   f'{type(exc).__name__}: {exc}',
                   traceback=traceback.format_exc(limit=4))
            first = None
        elapsed = time.time() - started

        if first:
            caps = first['capabilities']
            record('能力发现', 'OK' if caps.get('ok') else 'FAIL',
                   f"backend={caps.get('backend')!r}，"
                   f"工具 {len(first['tool_names'])} 个",
                   backend=caps.get('backend'), tools=first['tool_names'])
            if args.no_cst:
                record('真 CST 后端', 'INFO', '本轮用假后端（--no-cst），不验真机')
            else:
                record('真 CST 后端', 'OK' if caps.get('backend') == 'cst' else 'FAIL',
                       f"capabilities.backend={caps.get('backend')!r}（应为 'cst'）")
            record('离线预检', 'OK' if first['preflight'].get('valid') else 'FAIL',
                   f"valid={first['preflight'].get('valid')}")
            job_id = (first['build'] or {}).get('job_id')
            status = (first['status'] or {}).get('status')
            record('建模任务终态', 'OK' if status in ('succeeded', 'failed')
                   else 'FAIL',
                   f'job_id={job_id}，status={status}，轮询 {first["polls"]} 次，'
                   f'耗时 {elapsed:.1f}s',
                   job_id=job_id, job_status=status, elapsed=round(elapsed, 1))
            record('任务种类是 build（不是求解）',
                   'OK' if (first['build'] or {}).get('kind') in (None, 'build')
                   else 'FAIL',
                   f"kind={(first['build'] or {}).get('kind')!r}")
            if not args.no_cst:
                record('建模结果', 'OK' if status == 'succeeded' else 'FAIL',
                       f'真 CST 建模 {status}')

            rec, rec_path = job_record(workdir, job_id or '')
            if rec:
                messages = rec.get('messages')
                record('任务记录（磁盘）', 'OK',
                       f'status={rec.get("status")}，字段 {sorted(rec.keys())[:12]}',
                       path=rec_path, job_status=rec.get('status'),
                       messages=messages if isinstance(messages, list) else None)
            else:
                record('任务记录（磁盘）', 'FAIL', f'找不到记录：{rec_path}')

            projects = find_cst_projects(workdir)
            if args.no_cst:
                record('真 CST 工程产物', 'INFO', '假后端不产出真工程')
            else:
                record('真 CST 工程产物', 'OK' if projects else 'FAIL',
                       f'工作目录下找到 {len(projects)} 个真工程：'
                       f'{[os.path.basename(p) for p in projects]}',
                       projects=projects)

        # ---- 会话归属：服务自己的会话必须已关，别人的必须还在 ----------
        if not args.no_cst:
            after = design_environment_query()
            if not after['ok']:
                record('服务收尾后的 DE', 'UNKNOWN',
                       f'查不到（{after["reason"]}），无法定论')
            else:
                pids = set(after['pids'])
                extra = pids - before
                record('服务只关自己的会话', 'OK' if not extra else 'FAIL',
                       f'任务后 DE={sorted(pids)}，本次任务期间新增且仍活着={sorted(extra)}',
                       pids=sorted(pids), leftover=sorted(extra))
                if foreign_pids:
                    missing = foreign_pids - pids
                    record('「别人的」DE 没被服务关掉', 'OK' if not missing else 'FAIL',
                           f'「别人的」DE {sorted(foreign_pids)} '
                           f'{"仍在" if not missing else f"被关掉了 {sorted(missing)}"}'
                           f'；当前 DE {sorted(pids)}',
                           foreign_pids=sorted(foreign_pids))

        # ---- 场景 2：重启后的状态语义 ---------------------------------
        try:
            crafted_id, crafted = craft_queued_record(workdir, spec, 'crafted-queued')
            rec, _ = job_record(workdir, crafted_id)
            record('伪造的未完成任务（queued）',
                   'OK' if (rec or {}).get('status') in ('queued', 'running') else 'FAIL',
                   f'job_id={crafted_id}，磁盘状态={(rec or {}).get("status")!r}')
        except Exception as exc:                        # noqa: BLE001
            crafted_id = None
            record('伪造的未完成任务（queued）', 'FAIL',
                   f'{type(exc).__name__}: {exc}')

        before_restart = set(design_environment_query()['pids'])
        try:
            second = with_client(
                server_params(workdir, tmpdir, backend),
                lambda s: _scenario_restart(
                    s, {'已完成任务': ((first or {}).get('build') or {}).get('job_id'),
                        '未完成任务': crafted_id}))
        except Exception as exc:                        # noqa: BLE001
            record('重启后的状态语义', 'FAIL',
                   f'{type(exc).__name__}: {exc}',
                   traceback=traceback.format_exc(limit=4))
            second = None

        if second:
            statuses = second['statuses']
            done = ((statuses.get('已完成任务') or {}).get('payload') or {})
            if first and (first.get('build') or {}).get('job_id'):
                record('重启后已完成任务仍是 succeeded',
                       'OK' if done.get('status') == 'succeeded' else 'FAIL',
                       f'status={done.get("status")!r}（应为 succeeded）',
                       payload=statuses.get('已完成任务'))
            unfinished = ((statuses.get('未完成任务') or {}).get('payload') or {})
            record('重启后未完成任务标记中断',
                   'OK' if unfinished.get('status') == 'interrupted' else 'FAIL',
                   f'status={unfinished.get("status")!r}（应为 interrupted）',
                   payload=statuses.get('未完成任务'))

        after_restart = set(design_environment_query()['pids'])
        record('重启不自动重跑（没偷偷开 CST）',
               'OK' if after_restart == before_restart else 'FAIL',
               f'重启前 {sorted(before_restart)} → 重启后 {sorted(after_restart)}')

    finally:
        # 收尾：关掉「别人的」DE，再关本次多出来的 DE
        try:
            if foreign is not None:
                foreign.close()
                time.sleep(1.0)
                record('关闭脚本自己开的 DE', 'OK', '已 close()')
        except Exception as exc:                        # noqa: BLE001
            record('关闭脚本自己开的 DE', 'FAIL', f'{type(exc).__name__}: {exc}')
        closed = close_extra_design_environments(_baseline, verbose=True)
        record('收尾', 'OK', f'关闭本次新建的 DE：{closed or "无"}')
        query = design_environment_query()
        record('收尾后的 DE', 'OK' if query['ok'] else 'UNKNOWN',
               f'{query["pids"]}（基线 {sorted(_baseline)}）'
               if query['ok'] else query['reason'])
        leftovers = save_prompts()
        if leftovers:
            record('收尾弹窗', 'FAIL',
                   f'{len(leftovers)} 个未处理弹窗：'
                   + '; '.join(repr(p['title']) for p in leftovers))
        check_dialogs('收尾')
        print(f'收尾 CST 对话框：\n{describe_dialogs()}', flush=True)

    print('\n=== 汇总 ===')
    for entry in _results:
        print(f"{entry['status']:^7}  {entry['item']}")
    failed = [r for r in _results if r['status'] == 'FAIL']
    print(f'\nOK {len([r for r in _results if r["status"] == "OK"])} / '
          f'INFO {len([r for r in _results if r["status"] == "INFO"])} / '
          f'WARN {len([r for r in _results if r["status"] == "WARN"])} / '
          f'FAIL {len(failed)}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
