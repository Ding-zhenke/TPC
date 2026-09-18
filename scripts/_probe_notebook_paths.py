# -*- coding: utf-8 -*-
"""
离线探针：参考 notebook 的路径/角度口径（P4/V1 的 `bend_angle` 语义取证）
======================================================================

只读解析 `.ipynb` 的 JSON（**不执行**任何单元格、不改任何文件），把「主路径怎么走」
相关的参数定义抠出来对照：

* `px1..py3`：路径三个点的表达式（参考 notebook 用物理坐标写路径）
* `xmax / xup / yup / ydn`：由 x1/y1 推出的范围
* 基板多边形的顶点序列（看臂到底往哪边拐）

用法::

    python scripts/_probe_notebook_paths.py
"""

import json
import os
import re
import sys

BASE = r'D:\成电博士生涯\拓扑光子晶体模型\硅基'

# 关注的 notebook（相对 BASE）
TARGETS = [
    r'普通单元天线\Ant1_D_AB_120D_cylinder_DF.ipynb',
    r'普通单元天线\Ant1_D_BA_120D_circle_DF.ipynb',
    r'单元天线GRIB\AB型\120°透镜\Ant1_grid_120D_circle_turn.ipynb',
    r'单元天线GRIB\AB型\120°透镜\Ant1_grid_240D_circle.ipynb',
    r'单元天线GRIB\BA型\120°透镜\Ant1_grid_BA_120D.ipynb',
]

_PARA_RE = re.compile(r"para\(\s*'([A-Za-z_][\w]*)'\s*,\s*'?([^'\)]*)'?\s*\)")
_WANT = ('px1', 'py1', 'px2', 'py2', 'px3', 'py3', 'xmax', 'xup', 'yup', 'ydn',
         'x1', 'y1')


def scan(path):
    """
    抽取一个 notebook 里的参数定义与基板多边形。

    :param path: str, notebook 绝对路径
    :return: dict, ``{'params': {name: expr}, 'substrate': [ [x,y], ... ]}``
    """
    data = json.load(open(path, encoding='utf-8'))
    params = {}
    substrate = []
    for cell in data['cells']:
        src = ''.join(cell.get('source', []))
        for name, expr in _PARA_RE.findall(src):
            if name in _WANT and name not in params:
                params[name] = expr.strip()
        if 'polyline' in src and 'ymax_up' in src and not substrate:
            block = src[src.find('data=['):src.find('polyline')]
            substrate = [line.strip() for line in block.splitlines()
                         if line.strip() and line.strip() not in ('data=[', ']')]
    return {'params': params, 'substrate': substrate}


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    found = sys.argv[1:] or [
        os.path.join(BASE, rel) for rel in TARGETS
        if os.path.isfile(os.path.join(BASE, rel))]
    if not found:
        print(f'（{BASE} 下没找到这些 notebook）')
        return 1
    for path in found:
        print('=' * 72)
        print(os.path.relpath(path, BASE))
        info = scan(path)
        for name in _WANT:
            if name in info['params']:
                print(f"   {name:5s} = {info['params'][name]}")
        if info['substrate']:
            print('   基板多边形：')
            for line in info['substrate']:
                print('      ' + line)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
