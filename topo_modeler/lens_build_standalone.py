# -*- coding: utf-8 -*-
"""透镜工程独立构建脚本（供 ANT6_C6_hexring.ipynb 用 subprocess 并行启动）

职责：
  ① 从参考模板复制出**只含透镜**的工程 ANT6_C6_lens.cst（清掉模板自带变量）
  ② 登记透镜需要的 CST 参数（全部以 a 为基准，与 notebook 第 2 节一致）
  ③ exec lens_build.py 建透镜（孔阵列 DXF → 导入 → 镜像 → 椭圆−孔 → 楔形裁剪 → 平移 → 旋转×6）
  ④ 导出**子工程几何** ANT6_C6_lens_export.sab（SAT.WriteAll —— 签名见 CST 类型库文档）
  ⑤ 保存工程（原地保存 + 供 notebook 读取参数表做缓存判定）

参数来源：命令行第 1 个参数（默认 <工作目录>/lens_params.json，由 notebook 第 2.5 节写出"本次意图参数"）

★ 本脚本随 TPC 库走（放在 <TPC>/topo_modeler/ 下），工程/过程文件写到环境变量
  `LENS_WORK_DIR` 指定的目录（notebook 第 3.5 节传入），默认当前目录 ⇒ 换电脑/上服务器都不用改路径。

★ 这是一段**脚本**，不是模块：请用 `python lens_build_standalone.py <参数.json>` 运行，
  **不要 `import` 它** —— import 会当场执行整个建模流程、把调用进程占住（notebook 里
  只应该按路径取用，然后 subprocess 启动）。
"""
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))     # 本脚本所在目录（= <TPC>/topo_modeler）
# ★ 所有工程/过程文件都写到 WORK（notebook 用环境变量 LENS_WORK_DIR 指定），默认当前目录
WORK = os.path.abspath(os.environ.get('LENS_WORK_DIR') or os.getcwd())
os.makedirs(WORK, exist_ok=True)
os.chdir(WORK)

# ★ 库根目录由 __file__ 推出来（本脚本位于 <TPC>/topo_modeler/ 下）⇒ 跟着库走，可用 TPC_PATH 覆盖
TPC_PATH = os.environ.get('TPC_PATH') or os.path.dirname(HERE)
if TPC_PATH not in sys.path:
    sys.path.append(TPC_PATH)
from cst_solver import setup                                       # noqa: E402

PARAMS_JSON = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 \
    else os.path.join(WORK, 'lens_params.json')
LENS_CST = os.path.join(WORK, 'ANT6_C6_lens.cst')
LENS_SAB = os.path.join(WORK, 'ANT6_C6_lens_export.sab')
LENS_PY = os.path.join(HERE, 'lens_build.py')               # 同目录（TPC 内）的建模脚本
# 参考模板：只有"首次运行"需要（还没有干净模板时用它造）；路径由 notebook 用环境变量传入
TEMPLATE_SRC = os.environ.get('TPC_TEMPLATE_SRC', '')
TEMPLATE_CLEAN = os.path.join(WORK, 'ANT6_C6_tmpl.cst')   # notebook 第 2.5 节产出的"已清空变量"模板

T0 = time.perf_counter()


def log(*a):
    print(f'[{time.perf_counter() - T0:7.1f} s]', *a, flush=True)


# ---------------- 参数 ----------------
with open(PARAMS_JSON, encoding='utf-8') as f:
    P = json.load(f)
a = P['a']
h = P['h']
lens_ratio = P['ratio']
lens_Nx, lens_Ny = P['Nx'], P['Ny']
lens_r1_0, lens_r2_0 = P['r1_0'], P['r2_0']
n_small, lx1 = P['nsm'], P['lx1']
R_big = a * (3 * n_small / 4 + lx1)                                # 大六边形外接圆半径 = nRbig*a
log(f'参数：a={a} h={h} ratio={lens_ratio} Nx/Ny={lens_Nx}/{lens_Ny} '
    f'r1_0={lens_r1_0} r2_0={lens_r2_0} nsm={n_small} lx1={lx1} ⇒ R_big={R_big:.4f}')

# ---------------- ① 复制模板成透镜工程 ----------------
#   ★ 优先用 notebook 已经清干净变量的 ANT6_C6_tmpl.cst —— 参数表本来就是空的，
#     省掉一次"打开参考模型 + 删 77 个变量 + 保存"的 ~68 s（下面清理步骤会自动跳过）。
shutil.rmtree(os.path.splitext(LENS_CST)[0], ignore_errors=True)
if os.path.exists(LENS_CST):
    os.remove(LENS_CST)
if os.path.exists(TEMPLATE_CLEAN):
    _src, _clean = TEMPLATE_CLEAN, True
elif os.path.exists(TEMPLATE_SRC):
    _src, _clean = TEMPLATE_SRC, False
else:
    raise FileNotFoundError(
        f'找不到透镜模板：既没有已清理的 {TEMPLATE_CLEAN}，也没有参考模板'
        f'（环境变量 TPC_TEMPLATE_SRC = {TEMPLATE_SRC!r}）。'
        ' 首次运行请把参考模型 tmp.cst 放到工作目录下，或用环境变量 TPC_TEMPLATE_SRC 指向它。')
shutil.copyfile(_src, LENS_CST)
log('透镜工程已就绪：', os.path.basename(_src), '⇒', os.path.basename(LENS_CST),
    '（模板' + ('已干净' if _clean else '需清理') + '）')

app = setup(LENS_CST)
cst_file = app.cst_file
_m3 = cst_file.model3d


def cst_log(tag=''):
    msgs = cst_file.get_messages()
    log(f'[{tag}]', 'CST 无消息' if not msgs else str(msgs)[:300])


# ---------------- 清掉模板自带变量 ----------------
_names = []
try:
    _names = [str(_x) for _x in (_m3.GetProjectParameters() or [])]
except Exception:
    _names = []
if not _names:
    for _i in range(_m3.GetNumberOfParameters()):
        try:
            _nm = _m3.GetParameterName(_i)
        except Exception:
            continue
        if _nm and _nm not in _names:
            _names.append(_nm)
if _names:
    for _nm in _names:
        _m3.DeleteParameter(_nm)
    cst_file.save(LENS_CST, include_results=False, allow_overwrite=True)
    log(f'已删除模板遗留变量 {len(_names)} 个并保存')
else:
    log('模板没有遗留变量 → 跳过清理')

# ---------------- ② 登记 CST 参数表（单一来源：notebook 第 2.5 节写出的 ctsparams） ----------------
#   ★ 这里登记的是**与基板工程完全相同的整张表**（a/h/…/Rbig/Ls/ec_a/ratio/…）。
#     此前只登透镜专用的 17 个 ⇒ lens_build.py 里的 translate(..., 'Rbig')
#     会报 `Unable to evaluate expression: "Rbig"`。一个来源、两张相同的表，才彻底避免。
app.new_material('Silicon (lossy)')
_csp = P.get('ctsparams')
if not _csp:
    raise RuntimeError('lens_params.json 里没有 ctsparams（CST 参数表）'
                       '—— 请先跑 notebook 第 2.5 节重新生成')
for _n, _v, _d in _csp:
    app.para(_n, _v, expression=_d)
log(f'已登记 CST 参数 {len(_csp)} 项（与基板工程同一张表），参数总数 =',
    _m3.GetNumberOfParameters())

# ---------------- ③ 建透镜 ----------------
#   ★ 变量名一定要避开 lens_build.py 里的名字（它会把 _t 设为 numpy 数组、
#     还用 _t0 / _dt_*）：exec 共享 globals，撞名会把驱动脚本自己的计时变量覆盖掉，
#     上一版就因此在“透镜建模完成”那行日志上报 TypeError，导出/保存全被跳过。
_t_lens = time.perf_counter()
exec(open(LENS_PY, encoding='utf-8').read(), globals())
log('透镜建模完成，耗时 %.1f s' % float(time.perf_counter() - _t_lens))

# ---------------- ③b 先落盘一次：几何建了 200~300 s，别因为后面任何一步失败白费 ----------------
cst_file.save(LENS_CST, include_results=False, allow_overwrite=True)
log('✓ 透镜几何已落盘：', os.path.basename(LENS_CST))

# ---------------- ④ 导出子工程几何 .sab ----------------
if os.path.exists(LENS_SAB):
    os.remove(LENS_SAB)
_t_exp = time.perf_counter()
_vba = f'''With SAT
  .Reset
  .FileName "{LENS_SAB}"
  .SaveVersion "15.0"
  .WriteAll
End With'''
_m3.add_to_history('export SAT (subproject geometry)', _vba)
_dt_exp = float(time.perf_counter() - _t_exp)
if os.path.exists(LENS_SAB):
    log(f'✓ 已导出子工程几何：{os.path.basename(LENS_SAB)} '
        f'{os.path.getsize(LENS_SAB) / 1024 / 1024:.1f} MB，耗时 {_dt_exp:.1f} s')
else:
    log(f'✗ SAT 导出失败（{_dt_exp:.1f} s）—— 检查 .sab 路径/权限')
    raise RuntimeError('SAT 导出失败')
cst_log('导出子工程几何')

# ---------------- ⑤ 保存工程 ----------------
cst_file.save(LENS_CST, include_results=False, allow_overwrite=True)
log('✓ 透镜工程已保存：', os.path.basename(LENS_CST))
try:
    app.close()
except Exception:
    pass
log('全部完成，总耗时 %.1f s' % float(time.perf_counter() - T0))
