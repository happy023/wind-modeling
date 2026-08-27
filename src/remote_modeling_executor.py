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
    normalize_platform,
    prompt_pattern,
    set_wt_home_cmd,
    windchill_shell_cmds,
)


def log(msg: str) -> None:
    """日志走 stderr，避免污染 wc 的 JSON stdout；GBK 控制台遇到 emoji 不崩。"""
    try:
        sys.stderr.write(str(msg) + "\n")
        sys.stderr.flush()
    except Exception:
        sys.stderr.buffer.write((str(msg) + "\n").encode("utf-8", errors="replace"))
        sys.stderr.buffer.flush()


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
                    log("已进入 Windchill shell")
                    break
            if not entered:
                log("未能进入 Windchill shell（未检测到 wt>> 提示符），请检查 windchill 命令是否可用")

            return True
        except Exception as e:
            log(f"连接失败: {e}")
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
            raw_output = self._send_and_wait(command, timeout)
            cleaned = []
            for line in raw_output.replace("\r\n", "\n").split("\n"):
                if line.strip() not in (command.strip(), "") and not self.prompt_pattern.search(line):
                    cleaned.append(line)
            msg = "\n".join(cleaned).strip()

            failed = any(
                k in msg
                for k in (
                    "BUILD FAILED",
                    "不是内部或外部命令",
                    "not recognized",
                    "command not found",
                    "No such file or directory",
                    "系统找不到指定的路径",
                )
            )
            log(f"{'执行失败' if failed else '执行成功'}: {command}")
            if msg:
                log(msg)
            return (not failed), msg
        except Exception as e:
            error = f"执行出错: {e}，命令 {command}"
            log(error)
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
