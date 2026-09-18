"""多建模机配置：固定几台建模服务器，与业务项目 / wc profile 无关。

配置文件：``modeling.servers.yaml``（示例见仓库根 ``modeling.servers.example.yaml``）。
查找顺序：
1. 环境变量 ``WIND_MODELING_SERVERS``（绝对或相对路径）
2. 当前工作目录 ``modeling.servers.yaml``
3. 仓库根（开发可编辑安装时）``modeling.servers.yaml``
4. ``~/.wind-modeling/servers.yaml``
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .api import ModelingSession

_ENV_PATH = "WIND_MODELING_SERVERS"
_FILENAME = "modeling.servers.yaml"
_HOME_REL = Path(".wind-modeling") / "servers.yaml"


@dataclass(frozen=True, slots=True)
class ModelingServer:
    id: str
    host: str
    user: str
    password: str
    wt_home: str
    label: str = ""
    port: int = 22
    timeout: int = 60
    os: str = ""  # linux / windows / 空=自动探测

    def display_label(self) -> str:
        return (self.label or self.id).strip() or self.id

    def to_public_dict(self) -> dict[str, Any]:
        """列表/API 用：密码打码。"""
        return {
            "id": self.id,
            "label": self.display_label(),
            "host": self.host,
            "user": self.user,
            "password": "***" if self.password else "",
            "port": self.port,
            "wt_home": self.wt_home,
            "os": self.os or "auto",
            "timeout": self.timeout,
        }

    def to_session(
        self,
        *,
        model_classes: list[str],
        local_root: str,
        local_base: str,
    ) -> ModelingSession:
        return ModelingSession(
            hostname=self.host,
            username=self.user,
            password=self.password,
            wt_home=self.wt_home,
            port=self.port,
            timeout=self.timeout,
            local_root=local_root,
            local_base=local_base,
            model_classes=list(model_classes),
            platform=(self.os.strip() or None),
        )


@dataclass
class ServersFile:
    path: Path
    default: str | None
    servers: dict[str, ModelingServer] = field(default_factory=dict)

    def get(self, server_id: str | None = None) -> ModelingServer:
        sid = (server_id or self.default or "").strip()
        if not sid:
            if len(self.servers) == 1:
                return next(iter(self.servers.values()))
            raise KeyError(
                "未指定建模机 id，且无 default；请传 server_id 或在配置中设置 default"
            )
        if sid not in self.servers:
            known = ", ".join(sorted(self.servers)) or "(空)"
            raise KeyError(f"未知建模机 id: {sid!r}；可选: {known}")
        return self.servers[sid]

    def list_public(self) -> list[dict[str, Any]]:
        out = [s.to_public_dict() for s in self.servers.values()]
        out.sort(key=lambda x: x["id"])
        return out


def _repo_root_candidates() -> list[Path]:
    """可编辑安装时 ``src/wind_modeling/servers.py`` → 仓库根。"""
    here = Path(__file__).resolve()
    # .../wind-modeling/src/wind_modeling/servers.py
    if here.parent.name == "wind_modeling" and here.parents[1].name == "src":
        return [here.parents[2]]
    return []


def resolve_servers_config_path(explicit: str | Path | None = None) -> Path | None:
    if explicit is not None:
        p = Path(explicit).expanduser()
        return p if p.is_file() else None
    env = (os.environ.get(_ENV_PATH) or "").strip()
    if env:
        p = Path(env).expanduser()
        if p.is_file():
            return p
        return None
    candidates: list[Path] = [
        Path.cwd() / _FILENAME,
        *(_root / _FILENAME for _root in _repo_root_candidates()),
        Path.home() / _HOME_REL,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "读取建模机配置需要 PyYAML：pip install pyyaml"
        ) from exc
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"配置根须为 mapping: {path}")
    return data


def _parse_server(sid: str, raw: dict[str, Any]) -> ModelingServer:
    host = str(raw.get("host") or "").strip()
    user = str(raw.get("user") or "").strip()
    password = str(raw.get("password") or "")
    wt_home = str(raw.get("wt_home") or "").strip()
    missing = [k for k, v in (("host", host), ("user", user), ("wt_home", wt_home)) if not v]
    if missing:
        raise ValueError(f"servers.{sid} 缺少字段: {', '.join(missing)}")
    port = int(raw.get("port") or 22)
    timeout = int(raw.get("timeout") or 60)
    os_name = str(raw.get("os") or "").strip().lower()
    label = str(raw.get("label") or sid).strip()
    return ModelingServer(
        id=sid,
        label=label,
        host=host,
        user=user,
        password=password,
        wt_home=wt_home,
        port=port,
        timeout=timeout,
        os=os_name,
    )


def load_servers(path: str | Path | None = None) -> ServersFile:
    resolved = resolve_servers_config_path(path)
    if resolved is None:
        hint = (
            f"未找到 {_FILENAME}。请复制 modeling.servers.example.yaml，"
            f"或设置环境变量 {_ENV_PATH}"
        )
        raise FileNotFoundError(hint)
    data = _load_yaml(resolved)
    raw_servers = data.get("servers") or {}
    if not isinstance(raw_servers, dict):
        raise ValueError(f"{resolved}: servers 须为 mapping")
    servers: dict[str, ModelingServer] = {}
    for sid, body in raw_servers.items():
        if not isinstance(body, dict):
            raise ValueError(f"{resolved}: servers.{sid} 须为 mapping")
        servers[str(sid)] = _parse_server(str(sid), body)
    default = data.get("default")
    default_s = str(default).strip() if default else None
    if default_s and default_s not in servers and servers:
        raise ValueError(f"{resolved}: default={default_s!r} 不在 servers 中")
    return ServersFile(path=resolved, default=default_s, servers=servers)


def list_modeling_servers(
    path: str | Path | None = None,
) -> dict[str, Any]:
    """供 UI / CLI：列出建模机（密码打码）。"""
    try:
        cfg = load_servers(path)
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "config_path": None,
            "default": None,
            "servers": [],
        }
    except (ValueError, ImportError) as exc:
        return {
            "ok": False,
            "error": str(exc),
            "config_path": str(path) if path else None,
            "default": None,
            "servers": [],
        }
    return {
        "ok": True,
        "error": None,
        "config_path": str(cfg.path),
        "default": cfg.default,
        "servers": cfg.list_public(),
    }


def build_session_from_config(
    server_id: str | None,
    *,
    model_classes: list[str],
    local_root: str | Path,
    local_base: str | Path,
    config_path: str | Path | None = None,
) -> tuple[ModelingServer, ModelingSession]:
    cfg = load_servers(config_path)
    server = cfg.get(server_id)
    session = server.to_session(
        model_classes=model_classes,
        local_root=str(local_root),
        local_base=str(local_base),
    )
    return server, session
