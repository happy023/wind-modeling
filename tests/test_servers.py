"""modeling.servers.yaml 加载。"""

from __future__ import annotations

from pathlib import Path

import pytest

from wind_modeling.servers import load_servers, list_modeling_servers


def test_load_servers_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "modeling.servers.yaml"
    cfg.write_text(
        """
default: a
servers:
  a:
    label: Alpha
    host: 10.0.0.1
    user: root
    password: secret
    wt_home: /ptc/Windchill
  b:
    host: 10.0.0.2
    user: admin
    password: x
    wt_home: C:/ptc/Windchill
    os: windows
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("WIND_MODELING_SERVERS", str(cfg))
    loaded = load_servers()
    assert loaded.default == "a"
    assert loaded.get().host == "10.0.0.1"
    assert loaded.get("b").os == "windows"
    pub = list_modeling_servers()
    assert pub["ok"] is True
    assert pub["servers"][0]["password"] == "***"
    session = loaded.get("a").to_session(
        model_classes=["ext.app.Foo"],
        local_root="/tmp/up",
        local_base="/tmp/dist",
    )
    assert session.hostname == "10.0.0.1"
    assert session.model_classes == ["ext.app.Foo"]
