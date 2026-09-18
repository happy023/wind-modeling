"""wind-modeling 库入口（供 windchill-cli 等外部调用）。

独立脚本用法不变：在 src/ 下直接跑 remote_modeling_*.py / modeling_server.py。
"""

from .api import ModelingSession, collect, generate, prepare, run_pipeline, upload
from .servers import (
    ModelingServer,
    ServersFile,
    build_session_from_config,
    list_modeling_servers,
    load_servers,
    resolve_servers_config_path,
)

__all__ = [
    "ModelingSession",
    "ModelingServer",
    "ServersFile",
    "prepare",
    "upload",
    "generate",
    "collect",
    "run_pipeline",
    "build_session_from_config",
    "list_modeling_servers",
    "load_servers",
    "resolve_servers_config_path",
]

__version__ = "0.1.0"
