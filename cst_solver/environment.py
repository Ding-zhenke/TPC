# -*- coding: utf-8 -*-
"""CST 安装发现、配置与按需加载；导入本模块不启动 CST。"""

import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import runpy
import sys
from dataclasses import asdict, dataclass
from typing import Iterable, Mapping, Optional

__all__ = ['CSTPaths', 'CSTConfigurationError', 'CSTUnavailableError',
           'discover_cst_installations', 'get_cst_paths', 'diagnose_environment',
           'describe_interface_abi', 'interpreter_abi_tag']


class CSTConfigurationError(ValueError):
    """CST 配置文件无法读取或包含无效设置。"""


class CSTUnavailableError(RuntimeError):
    """CST Python 接口缺失或不能被当前解释器加载。"""


@dataclass(frozen=True)
class CSTPaths:
    """解析后的路径与配置来源；未发现安装时路径为 None。"""

    install_path: Optional[str]
    python_lib: Optional[str]
    material_lib: Optional[str]
    source: str


def discover_cst_installations(
    search_roots: Optional[Iterable[os.PathLike]] = None,
) -> list:
    """枚举安装目录，按版本由新到旧返回绝对路径列表。

    参数：search_roots 为安装父目录；默认仅检查 Windows 常见目录。
    返回：含 CST Python 库目录的安装路径，不启动 CST 或扫描整个磁盘。
    """
    if search_roots is None:
        search_roots = [os.environ.get('ProgramFiles', r'C:\Program Files'),
                        os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
                        r'C:\SOFTWARE'] if os.name == 'nt' else []
    found = {}
    for root in search_roots:
        try:
            children = Path(root).expanduser().iterdir()
            for child in children:
                match = re.fullmatch(r'CST Studio Suite (\d{4})', child.name)
                if match and (child / 'AMD64' / 'python_cst_libraries').is_dir():
                    resolved = str(child.resolve())
                    found[os.path.normcase(resolved)] = (int(match[1]), resolved)
        except OSError:
            continue
    return [path for _, path in sorted(found.values(), reverse=True)]


def _read_config(environ: Mapping[str, str]):
    """JSON 用户配置优先；兼容可信的本机 config.py，不读取模板默认值。"""
    filename = environ.get('CST_CONFIG_FILE')
    path = Path(filename).expanduser() if filename else Path(__file__).with_name('config.py')
    if not filename and not path.exists():
        return {}, 'unconfigured', Path.cwd()
    try:
        config = (json.loads(path.read_text(encoding='utf-8-sig')) if filename
                  else runpy.run_path(str(path)))
        if not isinstance(config, dict):
            raise ValueError('配置顶层必须是 JSON 对象')
        for key in ('CST_INSTALL_PATH', 'CST_PYTHON_LIB', 'CST_MATERIAL_LIB', 'CST_GUARD_MODE'):
            if key in config and config[key] is not None and not isinstance(config[key], str):
                raise ValueError(f'{key} 必须是字符串')
    except Exception as exc:
        raise CSTConfigurationError(f'无法读取 CST 配置 {path}: {exc}') from exc
    return config, str(path.resolve()), path.resolve().parent


def get_cst_paths(*, install_path: Optional[os.PathLike] = None,
                  environ: Optional[Mapping[str, str]] = None,
                  search_roots: Optional[Iterable[os.PathLike]] = None) -> CSTPaths:
    """解析配置，不导入 CST、不修改 sys.path。

    参数：install_path 显式安装目录；environ/search_roots 便于隔离测试。
    返回：CSTPaths。安装目录优先级为显式参数、环境变量、用户配置、自动发现。
    说明：CST_CONFIG_FILE 指向 JSON；配置内相对路径以配置目录为基准。
    显式安装目录或环境变量覆盖旧配置时，从新目录推导从属路径。
    """
    env = os.environ if environ is None else environ
    config, source, base = _read_config(env)

    def absolute(value, parent=Path.cwd()):
        if not value:
            return None
        path = Path(value).expanduser()
        return str((path if path.is_absolute() else parent / path).resolve())

    override = install_path is not None or bool(env.get('CST_INSTALL_PATH'))
    if override:
        install = absolute(install_path if install_path is not None else env['CST_INSTALL_PATH'])
        source = 'argument' if install_path is not None else 'environment'
    else:
        install = absolute(config.get('CST_INSTALL_PATH'), base)
        if not install and not (config.get('CST_PYTHON_LIB') or env.get('CST_PYTHON_LIB')):
            candidates = discover_cst_installations(search_roots)
            install = candidates[0] if candidates else None
            if install:
                source = 'discovery'

    def derived(key, *parts):
        if env.get(key):
            return absolute(env[key])
        if not override and config.get(key):
            return absolute(config[key], base)
        return str(Path(install).joinpath(*parts)) if install else None

    if any(env.get(key) for key in ('CST_PYTHON_LIB', 'CST_MATERIAL_LIB')):
        source += '+environment'
    return CSTPaths(install, derived('CST_PYTHON_LIB', 'AMD64', 'python_cst_libraries'),
                    derived('CST_MATERIAL_LIB', 'Library', 'Materials'), source)


def interpreter_abi_tag() -> str:
    """
    当前解释器的 CPython ABI 标签，例如 ``cp311``。

    用于与 CST 安装目录里的 ``_cst_interface.cpNN-win_amd64.pyd`` 比对 ——
    **这一步完全离线**（只读目录名与 ``sys.implementation``），不启动 CST。

    :return: str, 形如 ``cp311``；取不到时返回空串
    """
    tag = getattr(sys.implementation, 'cache_tag', '') or ''
    # cache_tag 形如 'cpython-311'，而 CST 的扩展名用的是 'cp311'
    if tag.startswith('cpython-'):
        return 'cp' + tag.split('-', 1)[1]
    return tag.split('-')[0]


def describe_interface_abi(install_path: Optional[os.PathLike] = None) -> dict:
    """
    报告 CST Python 接口与当前解释器的 ABI 匹配情况（离线，不启动 CST）。

    CST 的 Python 接口是 pybind11 扩展
    ``<安装目录>\\AMD64\\_cst_interface.cpNN-win_amd64.pyd``，
    **只有 ABI 与解释器一致的版本才能被 import**（例如 Python 3.11 需要 ``cp311``）。

    ⚠️ 有同 ABI 的 ``.pyd`` **只说明「有可能导入」**：真正的导入还依赖 DLL 依赖与许可，
    因此本函数**不**声称「已验证组合」，只如实报告文件与标签。

    :param install_path: 安装目录；省略时用 :func:`get_cst_paths` 的结果
    :return: dict，``{'install_path', 'amd64_dir', 'interpreter_abi',
        'interfaces': [...], 'matching_abi': str|None, 'abi_match': bool,
        'note': str}``
    """
    if install_path is None:
        try:
            install_path = get_cst_paths().install_path
        except CSTConfigurationError:
            install_path = None
    interpreter_abi = interpreter_abi_tag()
    info = {'install_path': str(install_path) if install_path else None,
            'amd64_dir': None, 'interpreter_abi': interpreter_abi,
            'interfaces': [], 'matching_abi': None, 'abi_match': False,
            'note': ''}
    if not install_path:
        info['note'] = '没有配置/发现 CST 安装目录，无法比对接口 ABI'
        return info
    amd64 = Path(install_path) / 'AMD64'
    info['amd64_dir'] = str(amd64)
    pattern = re.compile(r'_cst_interface\.(cp\d+)-win_amd64\.pyd$', re.IGNORECASE)
    try:
        names = sorted(p.name for p in amd64.iterdir())
    except OSError as exc:
        info['note'] = f'无法读取 {amd64}：{exc}'
        return info
    tags = sorted({m.group(1).lower() for m in
                   (pattern.search(name) for name in names) if m})
    info['interfaces'] = tags
    if interpreter_abi and interpreter_abi in tags:
        info['matching_abi'] = interpreter_abi
        info['abi_match'] = True
        info['note'] = (f'安装提供 {interpreter_abi} 接口，与当前解释器一致；'
                        '但不等于「已验证组合」—— 实际导入还依赖 DLL 与许可')
    elif tags:
        info['note'] = (f'安装只提供 {tags}，当前解释器是 {interpreter_abi or "未知"}；'
                        '该解释器**无法**加载 CST 接口（请用 CST 自带的 Python 或对应版本）')
    else:
        info['note'] = f'{amd64} 下没找到 _cst_interface.*.pyd'
    return info


def _load_cst_module(name: str):
    """仅在实际使用 CST 时添加有效路径并导入接口；保留底层异常链。"""
    paths = get_cst_paths()
    if paths.python_lib:
        if not Path(paths.python_lib).is_dir():
            raise CSTUnavailableError(
                f'CST Python 库目录不存在: {paths.python_lib}。'
                '请设置 CST_INSTALL_PATH 或 CST_PYTHON_LIB，修改后重启 Python。')
        if paths.python_lib not in sys.path:
            sys.path.insert(0, paths.python_lib)
            importlib.invalidate_caches()
    try:
        return importlib.import_module(name)
    except (ImportError, OSError) as exc:
        raise CSTUnavailableError(
            f'不能加载 {name}: {exc}。请检查 CST 安装路径、Python 版本及 DLL 依赖；'
            'CST 接口由 CST 安装提供，不能通过 pip install cst 替代。') from exc


def diagnose_environment(*, probe: bool = False) -> dict:
    """返回可 JSON 序列化的诊断，不创建设计环境或提交求解。

    参数：probe=False 仅检查路径和模块可发现性；True 尝试导入两种官方接口。
    返回：路径、解释器、发现状态及错误；接口可导入不等于许可/仿真可用。
    """
    try:
        paths = get_cst_paths()
    except CSTConfigurationError as exc:
        return {'status': 'configuration_error', 'error': str(exc), 'probe': probe}
    try:
        discoverable = importlib.util.find_spec('cst') is not None
    except (ImportError, ValueError):
        discoverable = 'cst' in sys.modules
    report = {
        'paths': asdict(paths), 'python_executable': sys.executable,
        'python_version': sys.version.split()[0], 'platform': sys.platform,
        'python_lib_exists': bool(paths.python_lib and Path(paths.python_lib).is_dir()),
        'module_discoverable': discoverable, 'probe': probe,
        # 离线比对「CST 提供的接口 ABI」与「当前解释器 ABI」——不启动 CST
        'interface_abi': describe_interface_abi(paths.install_path),
        'status': 'not_probed', 'errors': {},
    }
    if probe:
        for module in ('cst.interface', 'cst.results'):
            try:
                _load_cst_module(module)
            except CSTUnavailableError as exc:
                report['errors'][module] = str(exc)
        report['status'] = 'importable' if not report['errors'] else 'unavailable'
    return report
