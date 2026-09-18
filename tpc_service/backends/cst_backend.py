# -*- coding: utf-8 -*-
r"""
真实 CST 后端（P2）
==================

把服务层的三类任务接到既有能力上：

============================  ==========================================================
``build``                     `topo_modeler.preflight` 预检 → `topo_modeler.config`
                              的 `template_from_config` → `build_all()` → `save()`
``solve``                     `cst_solver.setup` 打开工程 → `run_checked()` 判定
                              → **保存** → `topo_modeler.result_reader` 读指标
``study``                     扫描 → `topo_modeler.scanner.ParameterScan`；
                              批量 → `topo_modeler.batch.BatchModeler`；
                              优化 → `topo_modeler.optimizer.GeneticOptimizer`
============================  ==========================================================

三条纪律（都来自计划 P2）
------------------------
1. **先保存再读**：`solve` 只有在 ``app.save()`` 成功之后才返回 ``saved=True``；
   否则服务层会判失败 —— 宁可失败，也不能把上一轮的结果当本轮结果。
2. **串行**：所有工作都在服务的单 worker 线程里做；扫描/批量本身也是串行实现
   （`ParameterScan.run()` 明确不并行），服务层不额外开线程。
3. **只关自己的会话**：`solve` 自己 ``setup()`` 出来的工程由自己 ``close()``；
   `close_project` 只在服务层判定 ``session_owned=True`` 时被调用。

⚠️ **本后端的真机行为尚未验证**（计划 P4/V7：真实 runner 小范围串行闭环）。
本文档不给任何「已验证」的说法；离线测试只覆盖「导入不碰 CST」与失败路径。
"""

import os
from typing import Any, Dict, List

from tpc_service.backends.base import Backend, artifact, fail_result, ok_result

__all__ = ['CstBackend']


class CstBackend(Backend):
    """
    真实 CST 后端（惰性导入，模块本身可离线导入）。

    :param s_parameters: 序列 可选, 默认要读的 S 参数（默认 ``('S1,1', 'S2,1')``）
    :param frequencies_ghz: 序列 可选, 额外取的频点（写进结果摘要）
    """

    name = 'cst'

    def __init__(self, *, s_parameters=('S1,1', 'S2,1'),
                 frequencies_ghz=(310.0, 330.0, 350.0, 370.0)):
        self.s_parameters = tuple(s_parameters)
        self.frequencies_ghz = tuple(float(f) for f in frequencies_ghz)

    # ================================================================
    # build
    # ================================================================

    def build(self, *, project, params, job):
        """按 ``params['spec']`` 建模并保存。"""
        from tpc_service.store import ensure_within
        from topo_modeler.config import template_from_config
        from topo_modeler.preflight import validate_model_spec

        spec = params.get('spec')
        if not isinstance(spec, dict):
            return fail_result('backend_failed',
                               'build 需要 params["spec"]（模型规格 dict）',
                               got=type(spec).__name__)
        project_path = str(project.get('path') or '')
        workdir = os.path.dirname(project_path) or os.getcwd()

        report = validate_model_spec(spec, base_dir=workdir)
        if not report['ok']:
            first = (report['errors'] or [{}])[0]
            return fail_result(first.get('code', 'config_invalid'),
                               first.get('message', '预检未通过'),
                               log=[f'预检未通过：{first.get("code")}'],
                               preflight=report)
        output = params.get('output') or os.path.join(
            workdir, f"{report['model_type']}"
                     f"_{report.get('ctor_kwargs', {}).get('length', 'x')}.cst")
        output = ensure_within(workdir, output)
        try:
            template = template_from_config(spec, output_path=output,
                                            template_cst=project_path)
        except Exception as exc:                      # noqa: BLE001
            return fail_result('backend_failed',
                               f'按规格建模板失败：{type(exc).__name__}: {exc}',
                               retryable=True)
        log: List[str] = [f'建模：{report["model_type"]} → {output}']
        outcome = None
        try:
            template.build_all()
            saved = template.save(output)
            # 🔴 验收必须在**关闭会话之前**做：`validate()` 走的是
            #    `self.app.validate_model()`（读消息 + Rebuild），会话关了就只能失败。
            #    离线编排测试 `tpc_service/tests/test_cst_backend_offline.py` 钉住了顺序
            #    （build_all → save → validate → close）。
            try:
                outcome = template.validate()
                log.append(f'Rebuild 验收：{outcome.get("status")}')
            except Exception as exc:                  # noqa: BLE001
                log.append(f'验收调用失败（不掩盖建模结果）：{exc!r}')
        except Exception as exc:                      # noqa: BLE001
            return fail_result('backend_failed',
                               f'建模执行失败：{type(exc).__name__}: {exc}',
                               retryable=True, log=log)
        finally:
            try:
                template.close()
            except Exception as exc:                  # noqa: BLE001
                log.append(f'关闭模板失败（不掩盖建模结果）：{exc!r}')
        return ok_result(
            log=log,
            artifacts=[artifact(str(saved), kind='project', note='建模产物')],
            result_summary={'model_type': report['model_type'],
                            'validation': (outcome or {}).get('status', 'unknown'),
                            'preflight_warnings': report.get('warnings', [])},
            saved=True)

    # ================================================================
    # solve
    # ================================================================

    def solve(self, *, project, params, job):
        """求解已有工程：`run_checked` 判定 → 保存 → 再读结果。"""
        from cst_solver import setup
        from topo_modeler.result_reader import ResultReader

        path = str(project.get('path') or '')
        if not os.path.isfile(path):
            return fail_result('project_not_found', f'工程不存在：{path}',
                               path=path)
        run_id = int(params.get('run_id', 0))
        log: List[str] = []
        app = None
        try:
            app = setup(path)
            outcome = app.run_checked(project_path=path,
                                      note=str(params.get('note', '')))
            log.append(f'运行契约：status={outcome.get("status")}')
            log.extend(str(m) for m in outcome.get('messages', []))
            if outcome.get('status') != 'succeeded':
                first = (outcome.get('errors') or [{}])[0]
                return fail_result(
                    first.get('code', 'backend_failed'),
                    f'求解未确认成功（status={outcome.get("status")}）：'
                    f'{first.get("message", "")}',
                    retryable=True, log=log,
                    run_identity={'run_token': outcome.get('run_token')})
            app.save(path)                            # ← 先保存，再交给读取器
            log.append(f'结果已保存：{path}')
        except Exception as exc:                      # noqa: BLE001
            return fail_result('backend_failed',
                               f'求解过程异常：{type(exc).__name__}: {exc}',
                               retryable=True, log=log)
        finally:
            if app is not None:
                try:
                    app.close()                       # 只关自己开的会话
                except Exception as exc:              # noqa: BLE001
                    log.append(f'关闭会话失败（不掩盖求解结果）：{exc!r}')

        summary = self._read_summary(ResultReader, path, run_id, log)
        return ok_result(
            log=log,
            artifacts=[artifact(path, kind='result', note=f'run_id={run_id}')],
            run_identity={'run_token': outcome.get('run_token'), 'run_id': run_id},
            result_summary=summary, saved=True)

    def _read_summary(self, ResultReader, path: str, run_id: int,
                      log: List[str]) -> Dict[str, Any]:
        """读 S 参数摘要（读失败不改变「已保存」这一事实，但要说清楚）。"""
        from cst_solver.run_contract import result_conventions
        summary: Dict[str, Any] = {'run_id': run_id,
                                   'conventions': result_conventions()}
        try:
            reader = ResultReader(path, names=list(self.s_parameters),
                                  run_id=run_id)
            metrics: Dict[str, Any] = {}
            for name in self.s_parameters:
                peak = reader.peak_position(name, kind='min')
                if peak is not None:
                    metrics[f'{name}_min_db'] = {'freq_ghz': peak[0],
                                                 'db': peak[1]}
                for freq in self.frequencies_ghz:
                    metrics[f'{name}_at_{freq:g}GHz_db'] = reader.value_at(
                        name, freq, in_db=True)
            summary['metrics'] = metrics
            if getattr(reader, 'last_errors', None):
                summary['read_errors'] = dict(reader.last_errors)
                log.append(f'部分结果读取失败：{reader.last_errors}')
        except Exception as exc:                      # noqa: BLE001
            summary['read_error'] = f'{type(exc).__name__}: {exc}'
            log.append(f'结果读取失败（不影响「已保存」判定）：{exc!r}')
        return summary

    # ================================================================
    # study
    # ================================================================

    def study(self, *, project, params, job):
        """
        参数研究：``params['study']['kind']`` ∈ ``scan`` / ``batch`` / ``optimize``。

        ::

            params = {
              'study': {
                'kind': 'scan',
                'base_config': {...模型规格...},
                'params': {'length': [16, 18, 20]},
                'apply_to': 'geometry',
              }
            }
        """
        study = params.get('study') or {}
        kind = str(study.get('kind', 'scan'))
        template = str(project.get('path') or '')
        outdir = os.path.join(os.path.dirname(template) or os.getcwd(),
                              f'study_{kind}_{job.get("job_id", "job")}')
        os.makedirs(outdir, exist_ok=True)

        def runner(point_or_entry):
            """把「一个配置」跑成「一组指标」：建模 → 求解 → 读。"""
            config = getattr(point_or_entry, 'config', None)
            cst_path = getattr(point_or_entry, 'cst_path', None) or os.path.join(
                outdir, f'{getattr(point_or_entry, "name", "point")}.cst')
            built = self.build(project={'path': template},
                               params={'spec': config, 'output': cst_path},
                               job=job or {})
            if not built.get('ok'):
                raise RuntimeError(f'建模失败：{built.get("error")}')
            solved = self.solve(project={'path': cst_path},
                                params={'run_id': study.get('run_id', 0)},
                                job=job or {})
            if not solved.get('ok'):
                raise RuntimeError(f'求解失败：{solved.get("error")}')
            return dict((solved.get('result_summary') or {}).get('metrics') or {})

        try:
            if kind == 'scan':
                from topo_modeler.scanner import ParameterScan
                scan = ParameterScan(
                    base_config=study['base_config'], params=study['params'],
                    runner=runner, workdir=outdir,
                    apply_to=study.get('apply_to', 'geometry'),
                    name=study.get('name'))
                scan.run(continue_on_error=True)
                return ok_result(
                    log=[f'扫描完成：{len(scan.points)} 个组合'],
                    artifacts=[artifact(outdir, kind='dir', note='扫描产物目录')],
                    result_summary={'n_points': len(scan.points),
                                    'errors': dict(scan.last_errors),
                                    'points': [{'name': p.name, 'status': p.status,
                                                'metrics': p.metrics}
                                               for p in scan.points]},
                    saved=True)
            if kind == 'batch':
                from topo_modeler.batch import BatchModeler
                batch = BatchModeler(entries=study['entries'], workdir=outdir,
                                     runner=runner)
                batch.run_all(continue_on_error=True)
                return ok_result(
                    log=[f'批量完成：{len(batch.entries)} 个模型'],
                    artifacts=[artifact(outdir, kind='dir', note='批量产物目录')],
                    result_summary={'summary': batch.summary(),
                                    'errors': dict(batch.last_errors)},
                    saved=True)
            if kind == 'optimize':
                from topo_modeler.optimizer import ContinuousVar, GeneticOptimizer
                variables = [ContinuousVar(**v) for v in study['variables']]
                objective = study.get('objective') or {}
                metric_name = objective.get('metric', 'S2,1_at_330GHz_db')
                direction = objective.get('direction', 'min')

                def evaluate(genotype):
                    config = _deep_copy(study['base_config'])
                    for var, value in zip(variables, genotype):
                        config.setdefault(study.get('apply_to', 'geometry'),
                                          {})[var.name] = value
                    metrics = runner(_Point(name=f'gen_{hash(tuple(genotype)) & 0xffffff}',
                                            config=config,
                                            cst_path=os.path.join(
                                                outdir,
                                                f'gen_{hash(tuple(genotype)) & 0xffffff}.cst')))
                    value = float(metrics.get(metric_name))
                    return value if direction == 'min' else -value

                optimizer = GeneticOptimizer(
                    variables, evaluate,
                    population_size=int(study.get('population_size', 20)),
                    generations=int(study.get('generations', 10)),
                    seed=study.get('seed'))
                result = optimizer.run()
                return ok_result(
                    log=[f'优化完成：{study.get("generations", 10)} 代'],
                    artifacts=[artifact(outdir, kind='dir', note='优化产物目录')],
                    result_summary={'best_fitness': getattr(result, 'best_fitness', None),
                                    'best_params': getattr(result, 'best_params', None),
                                    'generations_run': getattr(result, 'generations_run',
                                                               None),
                                    'seed': getattr(result, 'seed', None)},
                    saved=True)
        except KeyError as exc:
            return fail_result('backend_failed',
                               f'study 参数缺少必需字段：{exc}', kind=kind)
        except Exception as exc:                      # noqa: BLE001
            return fail_result('backend_failed',
                               f'{kind} 研究执行失败：{type(exc).__name__}: {exc}',
                               retryable=True, kind=kind)
        return fail_result('backend_failed',
                           f'未知 study.kind={kind!r}（可选 scan / batch / optimize）',
                           kind=kind)


class _Point:
    """给优化器的 ``evaluate`` 伪造一个 ScanPoint 形状的对象。"""

    def __init__(self, *, name: str, config: Dict[str, Any], cst_path: str):
        self.name = name
        self.config = config
        self.cst_path = cst_path


def _deep_copy(data: Any) -> Any:
    import copy
    return copy.deepcopy(data)
