# -*- coding: utf-8 -*-
"""
S 参数对比：本库生成模型 vs 参考工程
====================================

用途：**阶段 4 T6 的可复现工具**（计算资源受限版）。

设计约束（用户要求）
--------------------
1. **计算资源紧张** —— 只比"个别几个频点"，不做全频段曲线研究；
2. **参考工程绝不能被改动** —— 仿真会往工程里写求解器设置与结果，
   因此**一律先复制副本再打开**（`AB_feed.cst` 与同名工程目录一起复制）；
3. 两个模型必须用**完全相同的求解器设置与监视器频点**，否则比较不公平。

成本控制（都通过 cst_solver 的封装下发，不手写 VBA）
----------------------------------------------------
- 关闭网格自适应：`app.set_mesh_adaption(False)`
- 放宽稳态限制：`app.set_steady_state_limit(-20)`（默认 -30，越负越慢）
- 监视器只在需要的频点建：`configure_solver(..., monitor_frequencies=[...])`

⚠️ 时域求解器**一次算完整个频段**，监视器频点数不影响耗时；
"只挑几个点"指的是**只比较几个点**，不是只算几个点。

用法
----
    python scripts/compare_s_parameters.py --built <本库生成工程.cst> \
                                           --reference <参考工程.cst> \
                                           --workdir <工作目录> \
                                           --freqs 310,320,340,360,380

退出码: 0=两模型在所选频点上一致（|ΔS| < 容差）; 1=有超差或出错
"""

import argparse
import json
import re
import shutil
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 默认比较频点：与参考工程 AB_feed 的监视器频点一致
DEFAULT_FREQS = [310.0, 312.0, 314.0, 316.0, 318.0, 320.0]
# S 参数一致性容差（dB）
TOLERANCE_DB = 1.0


def _copy_project(src_cst: Path, dst_dir: Path) -> Path:
    """把 .cst 与其同名工程目录一起复制到目标目录，返回副本的 .cst 路径。"""
    src_cst = Path(src_cst).resolve()
    src_dir = src_cst.parent / src_cst.stem
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_cst = dst_dir / src_cst.name
    if src_dir.exists():
        dst_proj_dir = dst_dir / src_cst.stem
        if dst_proj_dir.exists():
            shutil.rmtree(dst_proj_dir)
        shutil.copytree(src_dir, dst_proj_dir)
    shutil.copy2(src_cst, dst_cst)
    return dst_cst


def _configure_and_run(app, freqs, label):
    """统一求解器设置并跑一次时域求解（两个模型必须调用同一函数）。"""
    from topo_modeler.builders import configure_solver
    configure_solver(app, freq_range=(freqs[0], freqs[-1]), monitors=('E',),
                     calculation_type='TD-S', steady_state=-20,
                     parallel_threads=8, gpus=0,
                     monitor_frequencies=freqs)
    app.set_mesh_adaption(False)                    # 关自适应，省时间
    app.set_gpu_acceleration(gpus=0, enable=False)  # 明确关 GPU，避免无卡机器报错
    print(f"  [{label}] 求解器已配置（关自适应 / 稳态 -20 dB / 频点 {freqs}），开始求解…",
          flush=True)
    app.run()
    print(f"  [{label}] 求解调用已返回", flush=True)


def _read_s(app_cst: Path, freqs, label):
    """从已完成的工程里读 S 参数（离线，不需要 DE）。"""
    from cst_solver import Result
    res = Result(str(app_cst))
    tree = res.get_tree_items()
    print(f"  [{label}] 结果树条目数: {len(tree)}", flush=True)

    out = {}
    for sp in ("S1,1", "S2,1"):
        try:
            data = res.read_s_parameter(sp)
            out[sp] = data
            print(f"  [{label}] {sp}: {len(data)} 点，频率 {data[0][0]:.1f}–{data[-1][0]:.1f} GHz",
                  flush=True)
        except Exception as exc:
            print(f"  [{label}] 读 {sp} 失败: {exc!r}", flush=True)
    return out


def _db(value):
    """S 参数（复数或 dB）转 dB。"""
    import math
    try:
        v = complex(value)
        mag = abs(v)
        return 20 * math.log10(mag) if mag > 0 else -300.0
    except Exception:
        return float(value)


def _sample_at(data, freq):
    """从 (n,2) 数组里取最接近 freq 的点。"""
    # 注意：CST 的 xdata 是 complex 类型（310+0j），需取 .real 才不触发
    # ComplexWarning: Casting complex values to real discards the imaginary part
    best = min(data, key=lambda row: abs(complex(row[0]).real - freq))
    return complex(best[0]).real, _db(best[1])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--built", required=True, help="本库生成的 .cst")
    ap.add_argument("--reference", required=True, help="参考工程 .cst（会被复制，不会改动原件）")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--freqs", default=",".join(str(f) for f in DEFAULT_FREQS))
    args = ap.parse_args(argv)

    freqs = [float(x) for x in args.freqs.split(",") if x.strip()]
    work = Path(args.workdir).resolve()
    work.mkdir(parents=True, exist_ok=True)

    # 先导入 cst_solver —— 它会在导入时读取 config.py 并把 CST 的
    # python_cst_libraries 加入 sys.path，之后才能 import cst.interface
    from cst_solver import setup, Result
    from cst.interface import running_design_environments, DesignEnvironment

    baseline = set(running_design_environments())
    print(f"开跑前已存在的 DE：{sorted(baseline) or '（无）'}", flush=True)

    def close_extra():
        extra = [p for p in running_design_environments() if p not in baseline]
        for pid in extra:
            try:
                DesignEnvironment.connect(pid).close()
                print(f"  已关闭本次新建的 DE：{pid}", flush=True)
            except Exception as exc:
                print(f"  兜底关闭 DE {pid} 失败，请手动关掉该窗口：{exc!r}", flush=True)
        if not extra:
            print("  无遗留 DE", flush=True)

    # ---- 参考工程一律用副本 ----
    ref_copy = _copy_project(Path(args.reference), work / "ref")
    print(f"参考工程副本：{ref_copy}", flush=True)

    results = {}
    try:
        for label, cst_path in (("built", Path(args.built).resolve()),
                                ("ref", ref_copy)):
            print(f"\n===== {label}: {cst_path} =====", flush=True)
            app = setup(str(cst_path))
            try:
                _configure_and_run(app, freqs, label)
                app.save()
            finally:
                try:
                    app.close()
                    print(f"  [{label}] 工程与设计环境已关闭", flush=True)
                except Exception as exc:
                    print(f"  [{label}] 关闭出错：{exc!r}", flush=True)
            results[label] = _read_s(cst_path, freqs, label)
    except Exception:
        traceback.print_exc()
    finally:
        close_extra()

    # ---- 对比 ----
    print(f"\n{'=' * 72}\n对比（仅所选频点，容差 {TOLERANCE_DB} dB）\n{'=' * 72}")
    if "built" not in results or "ref" not in results:
        print("有一侧没有取到结果，无法对比。")
        return 1

    bad = 0
    for sp in ("S1,1", "S2,1"):
        if sp not in results["built"] or sp not in results["ref"]:
            print(f"{sp}: 一侧缺失，跳过")
            continue
        print(f"\n--- {sp} ---")
        for f in freqs:
            fb, vb = _sample_at(results["built"][sp], f)
            fr, vr = _sample_at(results["ref"][sp], f)
            d = abs(vb - vr)
            flag = "  <== 超差" if d > TOLERANCE_DB else ""
            if d > TOLERANCE_DB:
                bad += 1
            print(f"  {f:6.1f} GHz   built={vb:8.3f} dB   ref={vr:8.3f} dB   Δ={d:6.3f} dB{flag}")

    print(f"\n结论：{bad} 个频点超差（容差 {TOLERANCE_DB} dB）")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
