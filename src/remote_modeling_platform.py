"""远程建模服务器平台适配（Linux / Windows）。

集中封装 Windchill 远程建模流程中的平台差异：
- Shell 命令语法（bash vs cmd/PowerShell）
- 路径分隔符（``/`` vs ``\\``）
- 提示符识别（``$`` / ``#`` / ``>`` / ``wt>>``）
- 输出编码（UTF-8 vs GBK）
- SFTP 目录判断兼容（Windows OpenSSH sftp-server 有时不返回 POSIX 类型位）

``platform`` 取值 ``"linux"`` / ``"windows"``；``None`` 表示连接后自动探测
（``uname -s`` 有输出按 linux，无输出按 windows，兼容 AIX/Solaris 等非 Windows）。
"""

from __future__ import annotations

import ntpath
import posixpath
import re
import stat
from typing import Iterable, List, Optional

LINUX = "linux"
WINDOWS = "windows"

# Windows 上 Windchill shell 启动命令候选（按优先级尝试）
WINDCHILL_SHELL_CANDIDATES = ("windchill.cmd", "windchill.bat", "windchill.exe")


def normalize_platform(platform: Optional[str]) -> Optional[str]:
    """规范化平台值；None/空 表示待自动探测。未知值按 linux 处理（向后兼容）。"""
    if platform is None:
        return None
    p = str(platform).strip().lower()
    if p in ("windows", "win32", "win", "nt"):
        return WINDOWS
    return LINUX


def is_windows(platform: Optional[str]) -> bool:
    return platform == WINDOWS


def detect_platform(client) -> str:
    """连接后自动探测远程系统类型（不抛异常）。

    Windows OpenSSH 默认 shell（cmd/PowerShell）下 ``uname`` 不存在，
    stdout 为空 → 判定为 windows；Linux/AIX/Solaris 等有输出 → linux。
    """
    try:
        _stdin, stdout, _stderr = client.exec_command("uname -s", timeout=10)
        out = (stdout.read() or b"").decode("utf-8", errors="ignore").strip()
    except Exception:
        return WINDOWS
    return LINUX if out else WINDOWS


def remote_path_module(platform: Optional[str]):
    """远程路径处理模块：windows → ntpath，linux → posixpath。"""
    return ntpath if is_windows(platform) else posixpath


def fmt_remote(path: str, platform: Optional[str]) -> str:
    """将路径分隔符统一为远程平台原生形式。"""
    if is_windows(platform):
        return str(path).replace("/", "\\")
    return str(path).replace("\\", "/")


def norm_remote(path: str, platform: Optional[str]) -> str:
    """规范化远程路径（统一分隔符并去除冗余 . / ..）。"""
    p = str(path)
    if is_windows(platform):
        p = p.replace("/", "\\")
    else:
        p = p.replace("\\", "/")
    return remote_path_module(platform).normpath(p)


def join_remote(base: str, *parts: str, platform: Optional[str]) -> str:
    """拼接远程路径并规范化为平台分隔符形式。"""
    mod = remote_path_module(platform)
    joined = mod.join(str(base), *[str(x) for x in parts])
    return norm_remote(joined, platform)


def remote_dirname(path: str, platform: Optional[str]) -> str:
    return remote_path_module(platform).dirname(str(path))


def prompt_pattern() -> re.Pattern:
    """匹配 bash($/#)、cmd/PowerShell(>) 以及 Windchill(wt>>) 提示符。"""
    return re.compile(r"(?:wt\>\>|[$#]\s*$|>+\s*$)")


def decode_bytes(data: bytes) -> str:
    """优先 UTF-8 解码，失败回退 GBK（中文 Windows 控制台默认代码页 936）。"""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("gbk", errors="replace")


def set_wt_home_cmd(wt_home: str, platform: Optional[str]) -> str:
    if is_windows(platform):
        return f"set WT_HOME={norm_remote(wt_home, platform)}"
    return f'export WT_HOME="{wt_home}"'


def cd_wt_home_cmd(wt_home: str, platform: Optional[str]) -> str:
    """进入 Windchill 主目录（Windows 用 cd /d 处理盘符切换，双引号防空格）。"""
    home = norm_remote(wt_home, platform)
    if is_windows(platform):
        return f'cd /d "{home}"'
    return f'cd "{home}"'


def pwd_cmd(platform: Optional[str]) -> str:
    return "cd" if is_windows(platform) else "pwd"


def windchill_shell_cmds(wt_home: str, platform: Optional[str]) -> List[str]:
    """Windchill shell 启动命令候选（按优先级尝试，仅 Linux 交互场景）。"""
    if is_windows(platform):
        # Windows 上 windchill shell 是「新实例」交互程序，SSH 下不可交互，
        # 需用管道方式非交互执行（见 windchill_pipe_cmd），此处返回空列表。
        return []
    return [f"{wt_home}/bin/windchill shell"]


def windchill_exe_path(wt_home: str, platform: Optional[str]) -> str:
    """Windows 上 windchill 可执行文件（windchill.exe / windchill2.bat）。"""
    if is_windows(platform):
        return norm_remote(f"{wt_home}\\bin\\windchill.exe", platform)
    return norm_remote(f"{wt_home}/bin/windchill", platform)


def windchill_pipe_cmd(wt_home: str, commands: Iterable[str], platform: Optional[str]) -> Optional[str]:
    """Windows 非交互执行 Windchill 环境命令（管道喂 windchill.exe shell）。

    与 windchill-cli 的 `wc build` 同款方案：windchill shell 是「新实例」交互程序，
    SSH 交互会话拿不到它的输出；改为 ``(echo cmd1 & echo cmd2 & echo exit) |
    windchill.exe shell`` 一次启动完成全部命令。Linux 返回 None（走交互 shell）。
    """
    if not is_windows(platform):
        return None
    cmds = list(commands)
    if not cmds:
        return None
    wt = norm_remote(wt_home, platform)
    windchill = windchill_exe_path(wt_home, platform)
    lines = " & ".join(f"echo {c}" for c in cmds)
    return (
        f'set "WT_HOME={wt}" && '
        f'(echo cd /d "{wt}" & {lines} & echo exit) | '
        f'"{windchill}" shell'
    )


def remove_dir_cmds(wt_home: str, rel_paths: Iterable[str], platform: Optional[str]) -> List[str]:
    """删除目录的命令列表（幂等：不存在的目录直接跳过）。"""
    cmds: List[str] = []
    if is_windows(platform):
        home = norm_remote(wt_home, platform)
        for rel in rel_paths:
            full = norm_remote(f"{home}\\{rel}", platform)
            cmds.append(f'if exist "{full}" rmdir /s /q "{full}"')
    else:
        for rel in rel_paths:
            cmds.append(f"rm -rf {wt_home}/{rel}")
    return cmds


def make_dir_cmds(wt_home: str, rel_paths: Iterable[str], platform: Optional[str]) -> List[str]:
    """创建目录的命令列表（cmd 的 mkdir / mkdir -p 均递归创建中间目录）。"""
    cmds: List[str] = []
    if is_windows(platform):
        home = norm_remote(wt_home, platform)
        for rel in rel_paths:
            full = norm_remote(f"{home}\\{rel}", platform)
            cmds.append(f'if not exist "{full}" mkdir "{full}"')
    else:
        for rel in rel_paths:
            cmds.append(f"mkdir -p {wt_home}/{rel}")
    return cmds


def ensure_dir_cmds(wt_home: str, rel_paths: Iterable[str], platform: Optional[str]) -> List[str]:
    """清理并重建目录的命令列表：全部删除在前、全部创建在后（幂等）。"""
    return remove_dir_cmds(wt_home, rel_paths, platform) + make_dir_cmds(wt_home, rel_paths, platform)


def ant_tools_path(platform: Optional[str]) -> str:
    return "bin\\tools.xml" if is_windows(platform) else "bin/tools.xml"


def is_sftp_dir(sftp, path: str) -> bool:
    """跨平台判断远程路径是否为目录。

    Windows OpenSSH 的 sftp-server 有时不返回 POSIX 类型位，此时退化为 listdir 探测。
    """
    try:
        st = sftp.stat(path)
        mode = getattr(st, "st_mode", 0) or 0
        if stat.S_IFMT(mode):
            return stat.S_ISDIR(mode)
        sftp.listdir(path)
        return True
    except IOError:
        return False


def ensure_sftp_dir(sftp, path: str, platform: Optional[str]) -> None:
    """递归确保远程目录存在（含 Windows 根目录判断，避免无限递归）。"""
    mod = remote_path_module(platform)
    dir_path = mod.dirname(str(path))
    if not dir_path:
        return
    try:
        sftp.stat(dir_path)
    except IOError:
        parent = mod.dirname(dir_path)
        if parent and parent != dir_path:
            ensure_sftp_dir(sftp, parent, platform)
        try:
            sftp.mkdir(dir_path)
        except IOError:
            pass
