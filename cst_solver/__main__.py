# -*- coding: utf-8 -*-
"""python -m cst_solver doctor [--probe]：只读 JSON 环境诊断。"""

import argparse
import json

from cst_solver.environment import diagnose_environment


def main():
    """输出诊断；配置错误或 probe 失败时返回非零退出码，不启动 CST。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['doctor'])
    parser.add_argument('--probe', action='store_true', help='尝试导入 CST 接口，不启动设计环境')
    args = parser.parse_args()
    report = diagnose_environment(probe=args.probe)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 1 if report['status'] in ('unavailable', 'configuration_error') else 0


if __name__ == '__main__':
    raise SystemExit(main())
