# -*- coding: utf-8 -*-
"""
CST 仿真结果读取类
====================
封装 cst.results.ProjectFile，提供导航树结果查询和数据读取接口

@author: PC
"""

import csv
import re
import numpy as np
from cst_solver.environment import _load_cst_module

#: CST 的 S 参数命名（``S1,1``；允许空格）
_S_PARAMETER_NAME_RE = re.compile(r'^S\s*\d+\s*,\s*\d+$')


# ============================================================
# 复数/单位量归一化
#
# CST 的 xdata/ydata 返回的是 Quantity / ComplexQuantity，直接参与比较会触发
# ``ComplexWarning: Casting complex values to real discards the imaginary part``
# （实测于阶段 4 T6，见 docs/next_plan/README.md §4.5）。
# 这里的三个小函数负责把它们统一压成 numpy 数组。
# ============================================================

def _as_real(value):
    """把标量/数组压成 float 数组（复数的实部）。"""
    arr = np.asarray(value)
    if np.iscomplexobj(arr):
        arr = arr.real
    return arr.astype(float, copy=False)


def _as_complex(value):
    """把标量/数组压成 complex 数组（实数会被提升）。"""
    return np.asarray(value).astype(complex, copy=False)


def _to_db(value):
    """
    |S| 转 dB。

    :param value: complex 标量/数组，注意**不是**已经取过对数的值
    :return: float 数组；幅度为 0 时取 -300 dB（与 scripts/compare_s_parameters.py 一致）
    """
    mag = np.abs(_as_complex(value))
    with np.errstate(divide='ignore'):        db = 20.0 * np.log10(mag)
    return np.where(mag > 0, db, -300.0)


def describe_result_open_failure(cst_file, exc) -> str:
    """
    把「打不开工程结果」的原因翻译成**可执行**的话（不吞掉原始异常）。

    实测（2026-09-17，CST 2026 + Python 3.11）：

    * 路径**不存在**且含非 ASCII 字符时，`cst.results.ProjectFile()` 抛的是
      ``UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb2 ...`` ——
      看起来像编码问题，其实是「文件不存在」（错误消息里带着按本地代码页编码的路径，
      读取器又按 UTF-8 解它）。纯 ASCII 的不存在路径则正常报
      ``FileNotFoundError: File does not exist``。
      所以我们**先自己判存在性**，别让用户去猜一个莫名其妙的 UnicodeDecodeError。
    * `allow_interactive=False` 时，若该工程被认为「正在 CST 里打开」，会抛
      ``UserWarning: Project is opened in CST Studio Suite``（本库统一用
      `allow_interactive=True`，因此这条只在别的调用方出现）。

    ⚠️ **非 ASCII 路径本身不影响读取**：中文路径下的已求解工程实测能正常读出 31 个结果树条目
    （与复制到纯 ASCII 路径的结果一致）—— 这一点最初被误判过，已更正。

    :param cst_file: str, 工程路径
    :param exc: Exception, 原始异常
    :return: str, 面向用户的说明
    """
    import os as _os
    if not _os.path.isfile(cst_file):
        message = f'工程文件不存在：{cst_file}（原始错误：{type(exc).__name__}: {exc}）'
        try:
            str(cst_file).encode('ascii')
        except UnicodeEncodeError:
            message += ('。⚠️ 路径含非 ASCII 字符时，CST 的离线读取器会把「文件不存在」'
                        '报成 UnicodeDecodeError，容易误判成编码问题')
        return message
    message = f'打开工程结果失败（{type(exc).__name__}: {exc}）：{cst_file}'
    if 'opened in CST Studio Suite' in str(exc):
        message += ('。该工程可能正在 CST 里打开；本读取器用的是 '
                    'allow_interactive=True，若仍失败请先在 CST 里保存或关闭该工程')
    return message


def describe_result_item_failure(tree_path, exc, tried) -> str:
    """
    把「结果项读不出来」翻译成**可执行**的话（不吞掉原始异常）。

    两类已知情形（2026-09-17 实测，CST 2026）：

    1. ``UserWarning: tree path not found: '…'`` —— 路径写法不对。
       ⚠️ 本项目里 `read_1D()` 会**自动加** ``1D Results\\`` 前缀，
       而 `get_tree_items()` 返回的是**完整**路径 —— 直接把后者喂进前者会得到
       ``1D Results\\1D Results\\…``。所以现在两种写法都接受，并在失败信息里
       把**试过的候选路径**列出来。
    2. ``UnicodeDecodeError`` —— CST 的离线读取器在**加载该项元数据**时就解不开
       （实测：`ANT_LEAKY_EPC_GRID.cst` 的 63 个结果项里 45 个正常、18 个
       ``1D Results\\farfield (f=…)`` 项在 `get_result_item()` 阶段即失败；
       同工程的括号名、材料色散、端口信息等条目都正常，**不是路径写法问题**）。

    :param tree_path: str, 调用方给的路径
    :param exc: Exception, 原始异常
    :param tried: 序列, 实际尝试过的候选路径
    :return: str
    """
    message = (f'结果项 {tree_path!r} 读取失败（{type(exc).__name__}: {exc}）；'
               f'已尝试的树路径：{list(tried)}')
    if isinstance(exc, UnicodeDecodeError):
        message += ('。该项的**元数据**在 CST 离线读取器里就解不开（实测某些 '
                    '`1D Results\\farfield (f=…)` 项会这样，同工程其它条目正常）—— '
                    '可改用 `Tables` 下的远场汇总条目，或从 CST 里把该结果导出成 '
                    'CSV/ASCII 再读')
    elif 'tree path not found' in str(exc):
        message += ('。该路径在结果树里不存在 —— 注意 `read_1D()` 会自动补 '
                    '`1D Results\\` 前缀，传完整路径也是可以的（两种都支持），'
                    '也可以先用 `get_tree_items()` 看一下真实路径')
    return message


class Result:
    """
    CST 仿真结果读取类
    用于从已完成的 CST 仿真工程中读取 S 参数、场数据等结果

    ``cst.results.ProjectFile(...)`` 是**离线读取**：只要工程里已经存有仿真结果，
    不需要设计环境（DE）也能读出数据（阶段 4 T6 的对比脚本就是这样用的）。

    用法示例:
        >>> app_result = Result("path/to/project.cst")
        >>> s21 = app_result.read_1D("S-Parameters\\S2,1")
        >>> s11 = app_result.read_1D("S-Parameters\\S1,1", run_id=0)
        >>> all_s = app_result.read_all_s_parameters()
        >>> app_result.export_s_parameters_csv("s_params.csv")
    """

    def __init__(self, cst_file):
        """初始化结果读取器
        :param cst_file: str, CST 工程文件路径（.cst）
        :raises RuntimeError: 打不开结果时（消息里带可执行的处置建议）
        """
        try:
            module = _load_cst_module('cst.results')
            self.app_result = module.ProjectFile(cst_file, allow_interactive=True)
        except Exception as exc:                       # noqa: BLE001
            raise RuntimeError(describe_result_open_failure(cst_file, exc)) from exc
        self.result_module = self.app_result.get_3d()
        #: 最近一次批量读取/导出中失败的条目 {名称: 错误字符串}。
        #: 批量接口不因为个别条目失败就整体抛异常（CST 的结果树常常缺项），
        #: 但失败的事实必须能被看到，所以留在这里而不是静默丢弃。
        self.last_errors = {}

    def get_tree_items(self, tree_filter=None):
        """
        列出导航树中的结果项

        :param tree_filter: str 可选, 结果类型过滤。官方接口支持
            ``"0D/1D"``（1D 曲线）/ ``"colormap"``（2D 云图）/
            ``"farfields"`` / ``"s-parameter-CC"`` 等；不传则返回全部
        :return: list, 结果路径字符串（部分 CST 版本返回 ResultItem，见 ``_tree_paths``）
        """
        if tree_filter:
            return self.result_module.get_tree_items(tree_filter)
        return self.result_module.get_tree_items()

    def get_available_results(self):
        """获取所有可用的结果项（中文别名）"""
        return self.get_tree_items()

    def get_all_run_ids(self, max_mesh_passes_only: bool = True):
        """获取所有已存在的仿真运行 ID
        :param max_mesh_passes_only: True-仅最终结果 False-含中间结果
        :return: list[int], 运行 ID 列表
        """
        return self.result_module.get_all_run_ids(max_mesh_passes_only)

    # ---- 路径写法统一：完整路径与相对路径都接受 ----
    # `get_run_ids()` / `get_result_item()` / `read_1D()` 共用下面这份候选展开逻辑，
    # 不再各写一套（2026-09-17 之前三种方法三种约定，`get_run_ids('S-Parameters\S1,1')`
    # 会直接报 tree path not found）。

    #: 结果树里的一级分类前缀（`get_tree_items()` 返回的路径以此开头）
    _TREE_PREFIXES = ('1D Results\\', '2D/3D Results\\', 'Tables\\', 'Farfields\\')

    @classmethod
    def _candidate_paths(cls, tree_path, prefix=''):
        """
        把用户给的路径展开成**候选列表**（完整路径优先，其次补前缀）。

        同一个类里三种路径约定会让人踩坑（2026-09-17 实测）：`read_1D` 接受
        「完整或相对」，而 `get_run_ids` / `get_result_item` 只接受完整路径 ——
        于是 `get_run_ids('S-Parameters\\\\S1,1')` 报 `tree path not found`。
        现在三个方法共用这一份展开逻辑。

        :param tree_path: str, 结果树路径（完整或相对）
        :param prefix: str, 相对路径时要补的前缀（如 ``'1D Results\\\\'``）
        :return: list[str], 候选路径（去重、保持顺序）
        """
        text = str(tree_path)
        if text.startswith(cls._TREE_PREFIXES):
            return [text]
        candidates = [prefix + text] if prefix else []
        candidates.append(text)
        if not prefix:
            candidates += [p + text for p in cls._TREE_PREFIXES]
        seen, unique = set(), []
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                unique.append(candidate)
        return unique

    def _get_item_with_prefix(self, tree_path, run_id, prefix, **kwargs):
        """
        取结果项：**两种写法都接受**。

        * 传完整路径（`get_tree_items()` 的返回值，以 ``1D Results\\`` 等开头）→ 原样使用；
        * 传相对路径（``'S-Parameters\\S1,1'``）→ 自动补 `prefix`。

        历史坑：`read_1D()` 一直是无条件加前缀，于是把 `get_tree_items()` 的返回值
        再传回来会变成 ``1D Results\\1D Results\\…``，报「tree path not found」。

        :param tree_path: str, 结果树路径（完整或相对）
        :param run_id: int, 运行 ID
        :param prefix: str, 相对路径时要补的前缀
        :param kwargs: 透传给 `get_result_item`
        :return: `cst.results.ResultItem`
        :raises RuntimeError: 所有候选都失败时（消息里列出试过的候选路径）
        """
        candidates = self._candidate_paths(tree_path, prefix)
        last_error = None
        for candidate in candidates:
            try:
                return self.result_module.get_result_item(candidate, run_id, **kwargs)
            except Exception as exc:                      # noqa: BLE001
                last_error = exc
        raise RuntimeError(describe_result_item_failure(tree_path, last_error,
                                                        candidates)) from last_error

    def get_run_ids(self, treepath: str, skip_nonparametric: bool = False):
        """
        获取指定导航树项目的所有运行 ID。

        路径写法与 `read_1D()` **一致**：完整（``'1D Results\\\\S-Parameters\\\\S1,1'``）
        或相对（``'S-Parameters\\\\S1,1'``）都可以 —— 此前只接受完整路径，
        相对写法会在 `cst.results` 里报 `tree path not found`。

        :param treepath: str, 导航树路径
        :param skip_nonparametric: True-排除 run_id=0
        :return: list[int], 运行 ID 列表
        :raises RuntimeError: 所有候选路径都失败时
        """
        if getattr(self.result_module, 'get_run_ids', None) is None:
            raise RuntimeError(
                '当前 CST 结果接口没有 get_run_ids（该版本不支持按结果项查运行 ID）')
        candidates = self._candidate_paths(treepath, '1D Results\\')
        last_error = None
        for candidate in candidates:
            try:
                return self.result_module.get_run_ids(candidate, skip_nonparametric)
            except Exception as exc:                      # noqa: BLE001
                last_error = exc
        raise RuntimeError(describe_result_item_failure(treepath, last_error,
                                                        candidates)) from last_error

    def get_result_item(self, treepath: str, run_id=0, load_impedances: bool = True):
        """
        获取指定导航树路径的结果项对象（路径写法同 `read_1D()`：完整或相对）。

        :param treepath: str, 导航树路径
        :param run_id: int, 运行 ID（0=最终结果）
        :param load_impedances: False-跳过自动加载参考阻抗
        :return: cst.results.ResultItem
        :raises RuntimeError: 所有候选路径都失败时
        """
        return self._get_item_with_prefix(treepath, run_id, '1D Results\\',
                                          load_impedances=load_impedances)

    def read_1D(self, tree_path, run_id: int = 0):
        """读取 1D 结果数据（如 S 参数）

        :param tree_path: str, 结果树路径 —— **完整**（``'1D Results\\S-Parameters\\S1,1'``，
            即 `get_tree_items()` 的返回值）或**相对**（``'S-Parameters\\S1,1'``）都行
        :param run_id: int, 运行 ID
        :return: ndarray (n,2) [xdata, ydata]
        :raises RuntimeError: 读不出来时（消息里说明原因与处置办法）
        """
        item = self._get_item_with_prefix(tree_path, run_id, '1D Results\\')
        return np.asarray([item.get_xdata(), item.get_ydata()]).T

    def read_2d(self, tree_path, run_id: int = 0):
        """读取 2D 结果数据（路径写法同 :meth:`read_1D`）"""
        data = self._get_item_with_prefix(tree_path, run_id, '2D Results\\')
        return {
            'x': data.get_xdata(), 'y': data.get_ydata(),
            'z': data.get_zdata() if hasattr(data, 'get_zdata') else None,
            'values': data.get_data()
        }

    def read_s_parameter(self, s_param: str, run_id: int = 0):
        """直接读取 S 参数（便捷方法）
        :param s_param: str, 如 'S1,1', 'S2,1'
        :return: ndarray (n,2) [频率, S参数值]
        """
        return self.read_1D(f"S-Parameters\\{s_param}", run_id)

    def read_3d(self, tree_path, run_id: int = 0):
        """读取 3D 结果数据（电场/磁场/功率损耗等）"""
        for prefix in ["2D/3D Results\\"]:
            try:
                full_path = prefix + tree_path
                data = self.result_module.get_result_item(full_path, run_id)
                return {
                    'x': data.get_xdata(), 'y': data.get_ydata(),
                    'z': data.get_zdata() if hasattr(data, 'get_zdata') else None,
                    'values': data.get_data()
                }
            except Exception:
                continue
        raise ValueError(f"无法读取 3D 结果: {tree_path}")

    # ================================================================
    # 批量读取与 CSV 导出（阶段 5.5）
    #
    # 设计要点：**纯离线**。只读工程里已存的结果文件，不打开设计环境，
    # 不写任何东西回工程 —— 因此可以在没有空闲许可/不想占算力时随便跑。
    #
    # ⚠️ 未验证风险：本机目前没有"已存结果可读"的工程，S 参数批量读取的
    # S-Parameters 树路径格式取自 scripts/compare_s_parameters.py 的实测用法，
    # 但**列表发现逻辑（list_s_parameters）与远场导出尚未在真实工程上跑过**。
    # 这是阶段 5 明确登记的未验证风险，不是"已验证"。
    # ================================================================

    def _tree_paths(self, tree_filter=None):
        """
        取出结果树里的所有路径字符串。

        官方文档写 ``get_tree_items()`` 返回 ``list[str]``，但同一份资料的另一处
        又说实测返回 ``list[ResultItem]``。这里两种都兼容：
        有 ``treepath`` 属性就用它，否则把元素本身当字符串。
        """
        try:
            items = self.get_tree_items(tree_filter)
        except Exception:
            if tree_filter is None:
                raise
            items = self.get_tree_items()
        out = []
        for it in items or ():
            path = getattr(it, 'treepath', None)
            out.append(str(path) if path is not None else str(it))
        return out

    def list_s_parameters(self, tree_filter='0D/1D'):
        """
        列出工程里所有可读的 S 参数名。

        判定规则（2026-09-17 收紧，修掉一个真实误报）：

        * 必须是 ``S-Parameters`` 目录的**直接子项**（``…\\S-Parameters\\S1,1``）；
        * 叶子名必须符合 CST 的 S 参数命名 ``S<端口1>,<端口2>``。

        为什么两条都要：``ANT_LEAKY_EPC_GRID.cst`` 里有一条
        ``1D Results\\Convergence\\S-Parameters\\Reflection S-Parameters [1]``
        —— **收敛监控曲线**，路径里同样含 ``S-Parameters``、也确实挂在同名目录下，
        但用它去 `read_s_parameter()` 什么也读不到。旧实现（只看路径里有没有
        ``'S-Parameter'``）会把它排在第一个返回，于是 ``names[0]`` 之类的调用直接炸。

        **不变式**：本函数返回的每个名字都必须能被 `read_s_parameter()` 读出来。

        :param tree_filter: str, 结果树过滤类型，默认 ``'0D/1D'``（1D 曲线）
        :return: list[str], 如 ``['S1,1', 'S2,1']``（已排序去重）
        """
        names = []
        for path in self._tree_paths(tree_filter):
            segments = [s.strip() for s in str(path).replace('/', '\\').split('\\')
                        if s.strip()]
            if len(segments) < 2 or segments[-2] not in ('S-Parameters',
                                                         'S-Parameter'):
                continue                     # 不是 S-Parameters 目录的直接子项
            leaf = segments[-1]
            if not _S_PARAMETER_NAME_RE.match(leaf):
                continue                     # 例如 'Reflection S-Parameters [1]'
            if leaf not in names:
                names.append(leaf)
        return sorted(names)

    def read_all_s_parameters(self, run_id: int = 0, names=None):
        """
        一次读回工程里所有 S 参数。

        个别条目读失败**不会**让整体抛异常（CST 结果树常常缺项，
        比如单端口器件就没有 S2,1）；失败项记在 ``self.last_errors`` 里，
        调用方可以自己决定要不要因为缺项而失败。

        :param run_id: int, 运行 ID（0 = 当前/最新结果）
        :param names: list[str] 可选, 只读指定的 S 参数；不传则自动发现
        :return: dict, ``{名称: ndarray(n,2)}``，第 0 列为频率（**float**，
            已剥掉 CST 返回的复数外壳），第 1 列为复数 S 值
        """
        if names is None:
            names = self.list_s_parameters()
        data, errors = {}, {}
        for name in names:
            try:
                raw = self.read_s_parameter(name, run_id)
                arr = np.asarray(raw)
                data[name] = np.column_stack((_as_real(arr[:, 0]),
                                              _as_complex(arr[:, 1])))
            except Exception as exc:
                errors[name] = repr(exc)
        self.last_errors = errors
        return data

    def export_s_parameters_csv(self, save_path, run_id: int = 0,
                                names=None, in_db: bool = True,
                                delimiter=',', encoding='utf-8-sig'):
        """
        把工程里所有 S 参数导出成一张 CSV（**离线**，不需要设计环境）。

        每个 S 参数一列，第一列是频率。多个 S 参数的频点必须一致
        （同一个求解器的结果本来就是同一套频点）；不一致的条目会被跳过
        并记入 ``self.last_errors``。

        :param save_path: str, 输出 CSV 路径
        :param run_id: int, 运行 ID
        :param names: list[str] 可选, 只导出指定 S 参数
        :param in_db: bool, True 写 dB（20*log10|S|，S 参数最常用的口径）；
            False 写复数（列名加 ``_re`` / ``_im`` 后缀）
        :param delimiter: str, 分隔符
        :param encoding: str, 文件编码，默认 ``'utf-8-sig'``（带 BOM，
            Excel 打开中文列名不乱码）
        :return: str, 写出的文件绝对路径
        :raises ValueError: 一个 S 参数都没读到
        """
        import os
        all_s = self.read_all_s_parameters(run_id=run_id, names=names)
        if not all_s:
            raise ValueError(
                "没有读到任何 S 参数；请先用 list_s_parameters() 看结果树里有什么。"
                f"已知错误：{self.last_errors}")

        # 以第一个成功读到的频轴为准
        ref_name = sorted(all_s)[0]
        freq = _as_real(all_s[ref_name][:, 0])

        skipped = dict(self.last_errors)
        columns, matrix = [], []
        for name in sorted(all_s):
            arr = all_s[name]
            if len(arr) != len(freq):
                skipped[name] = (f'频点数与 {ref_name} 不一致：'
                                 f'{len(arr)} vs {len(freq)}')
                continue
            columns.append(name)
            matrix.append(arr[:, 1])

        if in_db:
            header = ['freq_GHz'] + columns
            rows = np.column_stack([freq] + [_to_db(m) for m in matrix])
        else:
            header = ['freq_GHz']
            for c in columns:
                header += [f'{c}_re', f'{c}_im']
            parts = [freq]
            for m in matrix:
                parts += [_as_complex(m).real, _as_complex(m).imag]
            rows = np.column_stack(parts)

        save_path = os.path.abspath(save_path)
        with open(save_path, 'w', newline='', encoding=encoding) as fh:
            writer = csv.writer(fh, delimiter=delimiter)
            writer.writerow(header)
            for row in rows:
                writer.writerow(['%.10g' % v for v in row])

        self.last_errors = skipped
        return save_path

    def export_farfield_csv(self, save_path, tree_path='Farfields',
                            run_id: int = 0, delimiter=',',
                            encoding='utf-8-sig'):
        """
        导出远场结果到 CSV（**离线**）。

        远场在结果树里是 2D 云图（``2D/3D Results\\Farfields\\...``），
        本方法把它拉平成 ``x, y, value`` 三列的长表，便于外部工具处理。

        ⚠️ 未验证：本机没有含远场结果的工程，这条路径**没有在真实工程上跑过**
        （见 ``stages/05`` 的未验证风险登记）。失败时本方法会抛出
        ``ValueError`` 并附上结果树里的候选路径，方便定位。

        :param save_path: str, 输出 CSV 路径
        :param tree_path: str, 远场结果在 ``2D/3D Results\\`` 下的路径；
            默认 ``'Farfields'``，具体分支名（如 ``'farfield (f=310)'``）需按工程实际填
        :param run_id: int, 运行 ID
        :param delimiter: str, 分隔符
        :param encoding: str, 文件编码
        :return: str, 写出的文件绝对路径
        :raises ValueError: 该路径下读不到结果
        """
        import os
        try:
            data = self.read_3d(tree_path, run_id)
        except Exception as exc:
            raise ValueError(
                f"读不到远场结果 '{tree_path}'（底层错误：{exc!r}）。"
                f"结果树里的候选路径：{self._tree_paths()[:20]}") from exc

        xs = _as_real(data['x'])
        ys = _as_real(data['y'])
        vals = np.asarray(data['values'])
        if np.iscomplexobj(vals):
            vals = np.abs(vals)

        xs = np.atleast_1d(xs).ravel()
        ys = np.atleast_1d(ys).ravel()
        vals = np.atleast_2d(vals)

        rows = []
        for i, x in enumerate(xs):
            for j, y in enumerate(ys):
                if i < vals.shape[0] and j < vals.shape[1]:
                    rows.append((x, y, vals[i, j]))

        save_path = os.path.abspath(save_path)
        with open(save_path, 'w', newline='', encoding=encoding) as fh:
            writer = csv.writer(fh, delimiter=delimiter)
            writer.writerow(['x', 'y', 'value'])
            for x, y, v in rows:
                writer.writerow(['%.10g' % x, '%.10g' % y, '%.10g' % v])
        return save_path


class result(Result):
    """CST 仿真结果读取类（旧名，向后兼容）"""
    pass
