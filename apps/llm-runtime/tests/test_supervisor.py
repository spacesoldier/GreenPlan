from pathlib import Path
from unittest.mock import Mock

import pytest

from supervisor import ModelProfile, ModelRuntime, ProfileRegistry, RuntimeConfig


def write_gguf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"GGUF" + b"fixture")


def test_registry_resolves_only_allowlisted_gguf(tmp_path: Path) -> None:
    model = tmp_path / "qwen.gguf"
    write_gguf(model)
    registry = ProfileRegistry({"cad-qwen": ModelProfile("cad-qwen", model)})

    assert registry.resolve("cad-qwen").path == model
    with pytest.raises(KeyError):
        registry.resolve("../../arbitrary")


def test_registry_rejects_missing_or_invalid_gguf(tmp_path: Path) -> None:
    invalid = tmp_path / "bad.gguf"
    invalid.write_bytes(b"nope")
    registry = ProfileRegistry({"bad": ModelProfile("bad", invalid)})

    with pytest.raises(ValueError, match="GGUF"):
        registry.resolve("bad")


def test_runtime_reuses_active_profile_and_stops_before_switch(tmp_path: Path) -> None:
    qwen = tmp_path / "qwen.gguf"
    gemma = tmp_path / "gemma.gguf"
    write_gguf(qwen)
    write_gguf(gemma)
    registry = ProfileRegistry({
        "cad-qwen": ModelProfile("cad-qwen", qwen),
        "cad-gemma": ModelProfile("cad-gemma", gemma),
    })
    events: list[str] = []
    first = Mock()
    first.poll.return_value = None
    second = Mock()
    second.poll.return_value = None
    processes = iter((first, second))

    runtime = ModelRuntime(
        registry,
        RuntimeConfig(load_timeout=1),
        spawn=lambda command: events.append(f"start:{command[-1]}") or next(processes),
        wait_ready=lambda: None,
        stop=lambda process: events.append("stop"),
    )

    runtime.ensure("cad-qwen")
    runtime.ensure("cad-qwen")
    runtime.ensure("cad-gemma")

    assert events == ["start:cad-qwen", "stop", "start:cad-gemma"]
    assert runtime.active_profile == "cad-gemma"
