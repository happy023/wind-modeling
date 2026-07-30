"""可注入会话的建模 API（薄封装，复用原有 remote_modeling_* 函数）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import remote_modeling_collector
import remote_modeling_generator
import remote_modeling_pipeline
import remote_modeling_prepare
import remote_modeling_upload


@dataclass
class ModelingSession:
    """一次建模任务的连接与路径配置。"""

    hostname: str
    username: str
    password: str
    wt_home: str
    port: int = 22
    timeout: int = 60
    local_base: str = "../dist"
    local_root: str = "../model"
    model_classes: list[str] = field(default_factory=list)

    def ssh_config(self) -> dict:
        return {
            "hostname": self.hostname,
            "username": self.username,
            "password": self.password,
            "port": self.port,
            "timeout": self.timeout,
        }

    def modeling_config(self) -> dict:
        return {
            "wt_home": self.wt_home,
            "local_base": self.local_base,
            "local_root": self.local_root,
        }

    def _kwargs(self) -> dict:
        return {
            "model_classes": list(self.model_classes),
            "ssh_config": self.ssh_config(),
            "modeling_config": self.modeling_config(),
        }


def _result(ok: bool, error: Optional[str], step: str) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": ok, "step": step}
    if error:
        out["error"] = error
    return out


def prepare(session: ModelingSession) -> dict[str, Any]:
    ok, err = remote_modeling_prepare.prepare_directories(**session._kwargs())
    return _result(ok, err, "prepare")


def upload(session: ModelingSession) -> dict[str, Any]:
    ok, err = remote_modeling_upload.upload_models(**session._kwargs())
    return _result(ok, err, "upload")


def generate(session: ModelingSession) -> dict[str, Any]:
    ok, err = remote_modeling_generator.generate_code(**session._kwargs())
    return _result(ok, err, "generate")


def collect(session: ModelingSession) -> dict[str, Any]:
    ok, err = remote_modeling_collector.collect_files(**session._kwargs())
    return _result(ok, err, "collect")


def run_pipeline(session: ModelingSession) -> dict[str, Any]:
    """完整流程：prepare → upload → generate → collect。"""
    ok, err = remote_modeling_pipeline.modeling(**session._kwargs())
    out = _result(ok, err, "pipeline")
    out["classes"] = list(session.model_classes)
    return out
