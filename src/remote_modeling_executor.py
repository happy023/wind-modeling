"""共享的 Windchill 交互式 SSH 执行器（prepare / generate 共用）。

Windows OpenSSH 默认 cmd.exe：命令必须以 ``\\r\\n`` 结束，且必须先排空登录横幅，
否则会把初始提示符误判成“命令已完成”，随后一直等到超时。
"""

from __future__ import annotations

import re
import sys
import time
from typing import List, Optional, Tuple

import paramiko

from remote_modeling_platform import (
    decode_bytes,
    detect_platform,
    is_windows,
    norm_remote,
    normalize_platform,
    prompt_pattern,
    set_wt_home_cmd,
    windchill_pipe_cmd,
    windchill_shell_cmds,
)

# cmd/PowerShell 下命令不存在或执行失败的标记
FAIL_MARKERS = (
    "BUILD FAILED",
    "不是内部或外部命令",
    "not recognized",
    "command not found",
    "No such file or directory",
    "系统找不到指定的路径",
    "系统找不到指定的文件",
)

# 纯 ASCII 级别标签：GBK/UTF-8 控制台、网页都安全，不用 emoji
_LEVEL_TAGS = {
    "success": "[OK]",
    "error": "[ERR]",
    "warning": "[WARN]",
    "info": "[INFO]",
}
_LEVEL_ALIASES = {
    "ok": "success",
    "done": "success",
    "succ": "success",
    "err": "error",
    "fail": "error",
    "failed": "error",
    "warn": "warning",
}
# 仅 TTY 着色；非 TTY / 重定向保持纯文本，避免污染日志文件与管道
_LEVEL_ANSI = {
    "success": "\033[1;32m",  # bold green
    "error": "\033[1;31m",    # bold red
    "warning": "\033[1;33m",  # bold yellow
    "info": "\033[36m",       # cyan
}
_ANSI_RESET = "\033[0m"

_ERROR_HINTS = (
    "失败", "错误", "异常", "出错", "未能",
    "failed", "error", "exception", "traceback", "build failed",
)
_SUCCESS_HINTS = ("成功", "完成", "已完成", "success", "done")
_WARN_HINTS = ("警告", "warning", "warn")


def normalize_log_level(level: Optional[str]) -> str:
    key = (level or "info").strip().lower()
    key = _LEVEL_ALIASES.get(key, key)
    return key if key in _LEVEL_TAGS else "info"


def detect_log_level(text: str) -> str:
    """从标签或关键词推断级别（前端/落盘用；正文可无 ANSI）。"""
    raw = (text or "").strip()
    if not raw:
        return "info"
    for level, tag in _LEVEL_TAGS.items():
        if raw.startswith(tag):
            return level
    lower = raw.lower()
    for hint in _ERROR_HINTS:
        if hint in raw or hint in lower:
            return "error"
    for hint in _SUCCESS_HINTS:
        if hint in raw or hint in lower:
            return "success"
    for hint in _WARN_HINTS:
        if hint in raw or hint in lower:
            return "warning"
    return "info"


def _stream_isatty(stream) -> bool:
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _safe_write(stream, text: str) -> None:
    """写入流；编码失败时用 UTF-8 replace，兼容 GBK 控制台。"""
    try:
        stream.write(text)
        stream.flush()
    except Exception:
        try:
            data = text.encode("utf-8", errors="replace")
            buf = getattr(stream, "buffer", None)
            if buf is not None:
                buf.write(data)
                buf.flush()
            else:
                sys.stderr.buffer.write(data)
                sys.stderr.buffer.flush()
        except Exception:
            pass


def log(msg: str, level: str = "info") -> None:
    """统一日志：ASCII 级别标签 + 可选 ANSI（仅 TTY）。

    - 走 stderr，避免污染 CLI JSON stdout
    - 不用 emoji，避免 GBK Windows 控制台炸编码
    - 与 Linux/Windows 远程交互无关的本地展示层，正文保持原样
    """
    lvl = normalize_log_level(level)
    tag = _LEVEL_TAGS[lvl]
    plain = f"{tag} {msg}"
    stream = sys.stderr
    if _stream_isatty(stream):
        colored = f"{_LEVEL_ANSI[lvl]}{plain}{_ANSI_RESET}\n"
        _safe_write(stream, colored)
    else:
        _safe_write(stream, plain + "\n")


class SmartWindchillExecutor:
    def __init__(
        self,
        hostname: str,
        username: str,
        password: str,
        wt_home: str,
        port: int = 22,
        timeout: int = 30,
        platform: Optional[str] = None,
    ):
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.wt_home = wt_home
        self.timeout = timeout
        self.platform = normalize_platform(platform)
        self.client = None
        self.shell = None
        self.prompt_pattern = prompt_pattern()
        self.command_end_markers = [
            self.prompt_pattern,
            re.compile(r"Command completed"),
        ]

    def _eol(self) -> str:
        return "\r\n" if is_windows(self.platform) else "\n"

    def connect(self) -> bool:
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                hostname=self.hostname,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=min(self.timeout, 30),
            )

            if self.platform is None:
                self.platform = detect_platform(self.client)
            log(f"远程服务器平台: {self.platform}")

            if is_windows(self.platform):
                # Windows：windchill shell 是「新实例」交互程序，SSH 下不可交互；
                # 目录等普通命令直接走 exec 通道，ant 类命令走管道喂 windchill.exe shell。
                log("Windows 模式：非交互 exec 通道执行（windchill 命令走管道）")
                self.shell = None
                return True

            self.shell = self.client.invoke_shell()
            self.shell.settimeout(1)
            self._drain_until_prompt(timeout=20)

            self._send_and_wait(set_wt_home_cmd(self.wt_home, self.platform), timeout=20)
            entered = False
            for cmd in windchill_shell_cmds(self.wt_home, self.platform):
                log(f"尝试进入 Windchill shell: {cmd}")
                response = self._send_and_wait(cmd, timeout=20)
                if "wt>>" in response:
                    entered = True
                    self.prompt_pattern = re.compile(r"wt\>\>\s*$")
                    self.command_end_markers = [self.prompt_pattern]
                    log("已进入 Windchill shell", "success")
                    break
            if not entered:
                log("未能进入 Windchill shell（未检测到 wt>> 提示符），请检查 windchill 命令是否可用", "error")

            return True
        except Exception as e:
            log(f"连接失败: {e}", "error")
            self.close()
            return False

    def _recv_once(self) -> str:
        if self.shell and self.shell.recv_ready():
            return decode_bytes(self.shell.recv(4096))
        return ""

    def _drain_until_prompt(self, timeout: int = 20) -> str:
        if not self.shell:
            raise RuntimeError("SSH连接未建立")
        end_time = time.time() + timeout
        output = ""
        while time.time() < end_time:
            data = self._recv_once()
            if data:
                output += data
                if self.prompt_pattern.search(output):
                    return output
            else:
                time.sleep(0.1)
        return output

    def _send_and_wait(self, command: str, timeout: Optional[int] = None) -> str:
        if not self.shell:
            raise RuntimeError("SSH连接未建立")

        timeout = timeout or self.timeout
        end_time = time.time() + timeout
        self.shell.send(command + self._eol())

        output = ""
        while time.time() < end_time:
            data = self._recv_once()
            if data:
                output += data
                if any(marker.search(output) for marker in self.command_end_markers):
                    extra = self._recv_once()
                    if extra:
                        output += extra
                    break
            else:
                time.sleep(0.1)
        return output

    def execute_command(self, command: str, timeout: Optional[int] = None) -> Tuple[bool, str]:
        try:
            if is_windows(self.platform) and self.client:
                # Windows：普通 cmd 命令（目录操作等），exec 通道逐条执行
                timeout = timeout or self.timeout
                _stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
                out = decode_bytes(stdout.read() or b"")
                err = decode_bytes(stderr.read() or b"")
                msg = f"{out}\n{err}".strip()
                failed = any(k in msg for k in FAIL_MARKERS)
                log(f"{'执行失败' if failed else '执行成功'}: {command}",
                    "error" if failed else "success")
                if msg:
                    log(msg)
                return (not failed), msg

            raw_output = self._send_and_wait(command, timeout)
            cleaned = []
            for line in raw_output.replace("\r\n", "\n").split("\n"):
                if line.strip() not in (command.strip(), "") and not self.prompt_pattern.search(line):
                    cleaned.append(line)
            msg = "\n".join(cleaned).strip()

            failed = any(k in msg for k in FAIL_MARKERS)
            log(f"{'执行失败' if failed else '执行成功'}: {command}",
                "error" if failed else "success")
            if msg:
                log(msg)
            return (not failed), msg
        except Exception as e:
            error = f"执行出错: {e}，命令 {command}"
            log(error, "error")
            return False, error

    def execute_windchill(self, commands: List[str], timeout: Optional[int] = None) -> Tuple[bool, str]:
        """批量在 Windchill 环境中执行命令。

        - Windows：一次启动 windchill.exe shell（管道喂命令），全部命令一次跑完；
        - Linux：逐个走交互 shell。
        """
        if not commands:
            return True, ""
        if not is_windows(self.platform):
            results = self.execute_commands(commands)
            failed = [r for r in results if not r[0]]
            return (not failed), "\n".join(r[1] for r in results)

        if not self.client:
            return False, "SSH 连接未建立"
        total = max(timeout or 0, self.timeout * max(1, len(commands)))
        pipe = windchill_pipe_cmd(self.wt_home, commands, self.platform)
        if not pipe:
            return False, "无法生成 windchill 管道命令"
        log(f"批量执行 {len(commands)} 条 Windchill 命令（管道，超时 {total}s）")
        try:
            _stdin, stdout, stderr = self.client.exec_command(pipe, timeout=total)
            out = decode_bytes(stdout.read() or b"")
            err = decode_bytes(stderr.read() or b"")
            msg = f"{out}\n{err}".strip()
            failed = any(k in msg for k in FAIL_MARKERS)
            log(f"{'执行失败' if failed else '执行成功'}: Windchill 批量命令",
                "error" if failed else "success")
            if msg:
                log(msg)
            return (not failed), msg
        except Exception as e:
            error = f"执行出错: {e}"
            log(error, "error")
            return False, error

    def execute_commands(self, commands: List[str]) -> List[Tuple[bool, str]]:
        return [self.execute_command(cmd) for cmd in commands]

    def close(self):
        try:
            if self.shell:
                self.shell.close()
            if self.client:
                self.client.close()
        except Exception:
            pass
        finally:
            self.shell = None
            self.client = None

    def __enter__(self):
        if not self.connect():
            raise RuntimeError("SSH/Windchill 连接失败")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
