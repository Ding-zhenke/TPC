# -*- coding: utf-8 -*-
"""
通过 GitHub Git Data API 推送本地提交（github.com:443 不可达时的备用通道）
==========================================================================
**什么时候需要它**：部分网络环境会针对性阻断 `github.com:443`（表现为
`Connection was reset` / 连接超时），但 `api.github.com:443` 与
`codeload.github.com:443` 仍然可达。此时 `git push` 无法建立连接，而本脚本
用 Git Data API 把 `origin/main..HEAD` 的提交**逐个原样重建**到远端。

用法::

    python scripts/push_via_api.py            # 推送 origin/main..HEAD
    python scripts/push_via_api.py --verify   # 只校验远端与本地是否一致

令牌来源：`git credential fill`（即 Git Credential Manager 已存的那一份），
**不落盘、不打印**。仓库为公开仓库时 `public_repo` 权限即可。

安全性设计
----------
- 每个提交重建后都与本地 SHA 逐一比对（含 tree）；只要有一个不一致就整体中止；
- 远端 ref **只在全部提交都成功后才推进**；中途失败只会留下悬空对象，
  不会破坏远端历史；
- 用 `force: false` 更新 ref，若远端已前进则会被拒绝，不会覆盖他人提交。

@author: PC
"""

import argparse
import base64
import datetime
import json
import subprocess
import sys
import urllib.error
import urllib.request

API = 'https://api.github.com'
REPO = 'Ding-zhenke/TPC'
BRANCH = 'main'


def get_token():
    """从 Git Credential Manager 取令牌（不打印、不写盘）。"""
    p = subprocess.run(['git', 'credential', 'fill'],
                       input=b'protocol=https\nhost=github.com\n\n',
                       capture_output=True, check=True)
    for line in p.stdout.decode().splitlines():
        if line.startswith('password='):
            return line.split('=', 1)[1]
    raise SystemExit('无法从 git credential 取到令牌，请先 git fetch 触发一次登录')


TOKEN = None


def gh(method, path, payload=None):
    global TOKEN
    if TOKEN is None:
        TOKEN = get_token()
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header('Authorization', 'Bearer ' + TOKEN)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'tpc-push-via-api')
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            body = r.read().decode('utf-8')
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        raise SystemExit(
            f'API {method} {path} -> {e.code}\n{e.read().decode("utf-8", "replace")[:400]}')


def git(*args, text=True):
    p = subprocess.run(['git'] + list(args), capture_output=True, check=True)
    return p.stdout.decode('utf-8', 'replace') if text else p.stdout


def parse_commit(sha):
    """
    从原始 commit 对象里取出**精确**的 tree / parents / author / committer / message。

    .. important::
        不要用 ``git show --format=%B`` 取消息：它会在末尾补一个换行，
        回填给 API 后消息字节数变了，重建出的 SHA 必然不同。
    """
    raw = git('cat-file', 'commit', sha, text=False)
    head, msg = raw.split(b'\n\n', 1)
    info = {'parents': []}
    for line in head.decode('utf-8').split('\n'):
        if line.startswith('tree '):
            info['tree'] = line[5:].strip()
        elif line.startswith('parent '):
            info['parents'].append(line[7:].strip())
        elif line.startswith('author '):
            info['author'] = _ident(line[7:])
        elif line.startswith('committer '):
            info['committer'] = _ident(line[10:])
    info['message'] = msg.decode('utf-8')
    return info


def _ident(tail):
    """``Name <email> 1757869205 +0800`` -> API 需要的 ISO 8601 形式。"""
    name_email, ts, tz = tail.rsplit(' ', 2)
    name, email = name_email.rsplit(' <', 1)
    sign = 1 if tz[0] == '+' else -1
    offset = datetime.timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5])) * sign
    dt = datetime.datetime.fromtimestamp(int(ts), datetime.timezone(offset))
    return {'name': name, 'email': email.rstrip('>'), 'date': dt.isoformat()}


def remote_ref():
    return gh('GET', f'/repos/{REPO}/git/ref/heads/{BRANCH}')['object']['sha']


def verify():
    """校验远端 main 与本地 HEAD 的 commit / tree 是否完全一致。"""
    local_head = git('rev-parse', 'HEAD').strip()
    local_tree = git('rev-parse', 'HEAD^{tree}').strip()
    head = remote_ref()
    tree = gh('GET', f'/repos/{REPO}/git/commits/{head}')['tree']['sha']
    print(f'本地 HEAD : {local_head}')
    print(f'远端 main : {head}')
    print(f'HEAD 一致 : {local_head == head}')
    print(f'tree 一致 : {local_tree == tree}')
    return local_head == head and local_tree == tree


def push():
    base = remote_ref()
    local_base = git('rev-parse', 'origin/main').strip()
    if base != local_base:
        raise SystemExit(
            f'远端 {BRANCH}={base[:7]} 与本地 origin/main={local_base[:7]} 不一致。\n'
            '请先用其它方式同步本地引用，脚本中止（避免误覆盖）')

    commits = git('rev-list', '--reverse', f'{base}..HEAD').split()
    if not commits:
        print('没有需要推送的提交。')
        return verify()
    print(f'远端 {BRANCH} = {base[:7]}，待推送 {len(commits)} 个提交\n')

    parent_commit = base
    parent_tree = git('rev-parse', f'{base}^{{tree}}').strip()

    for idx, sha in enumerate(commits, 1):
        info = parse_commit(sha)
        if info['parents'] != [parent_commit]:
            raise SystemExit(
                f'第 {idx} 个提交 {sha[:7]} 的父提交不是预期的 {parent_commit[:7]}，中止')

        raw = git('diff-tree', '-r', '--no-commit-id', '--name-status',
                  '--no-renames', '-z', sha, text=False)
        parts = raw.decode('utf-8', 'replace').split('\0')
        entries, i = [], 0
        while i < len(parts):
            if not parts[i]:
                i += 1
                continue
            status, path = parts[i], parts[i + 1]
            i += 2
            if status == 'D':
                entries.append({'path': path, 'mode': '100644',
                                'type': 'blob', 'sha': None})
                continue
            content = git('show', f'{sha}:{path}', text=False)
            blob = gh('POST', f'/repos/{REPO}/git/blobs', {
                'content': base64.b64encode(content).decode('ascii'),
                'encoding': 'base64'})['sha']
            mode = git('ls-tree', sha, '--', path).split()[0]
            entries.append({'path': path, 'mode': mode, 'type': 'blob', 'sha': blob})

        tree = gh('POST', f'/repos/{REPO}/git/trees',
                  {'base_tree': parent_tree, 'tree': entries})['sha']
        if tree != info['tree']:
            raise SystemExit(
                f'第 {idx} 个提交 {sha[:7]} 的 tree 不一致：\n'
                f'  API  : {tree}\n  本地 : {info["tree"]}\n中止，远端 ref 未改动')

        commit = gh('POST', f'/repos/{REPO}/git/commits', {
            'message': info['message'],
            'tree': tree,
            'parents': [parent_commit],
            'author': info['author'],
            'committer': info['committer']})['sha']
        if commit != sha:
            raise SystemExit(
                f'第 {idx} 个提交 SHA 不一致：API {commit} vs 本地 {sha}\n'
                '中止，远端 ref 未改动')

        subject = info['message'].split('\n', 1)[0]
        print(f'[{idx:2d}/{len(commits)}] OK {sha[:7]} {len(entries):3d} 项  {subject[:56]}')
        sys.stdout.flush()
        parent_commit, parent_tree = commit, tree

    res = gh('PATCH', f'/repos/{REPO}/git/refs/heads/{BRANCH}',
             {'sha': parent_commit, 'force': False})
    print(f'\n远端 ref 已更新: {res["object"]["sha"]}')
    print(f'期望值          : {commits[-1]}')
    return verify()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--verify', action='store_true',
                    help='只校验远端与本地是否一致，不推送')
    args = ap.parse_args()
    ok = verify() if args.verify else push()
    print('\n结果:', '一致' if ok else '不一致')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
