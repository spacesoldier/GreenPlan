from __future__ import annotations

import http.client
import json
import os
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import signal
import subprocess
import threading
import time
from typing import Callable, Mapping
from urllib.request import urlopen


@dataclass(frozen=True)
class ModelProfile:
    alias: str
    path: Path


class ProfileRegistry:
    def __init__(self, profiles: Mapping[str, ModelProfile]):
        self._profiles = dict(profiles)

    def resolve(self, alias: str) -> ModelProfile:
        try:
            profile = self._profiles[alias]
        except KeyError as exc:
            raise KeyError(f"unknown model profile: {alias}") from exc
        try:
            with profile.path.open("rb") as stream:
                magic = stream.read(4)
        except OSError as exc:
            raise ValueError(f"model is unavailable: {profile.path}") from exc
        if magic != b"GGUF":
            raise ValueError(f"model does not have a GGUF header: {profile.path}")
        return profile

    def describe(self) -> list[dict[str, object]]:
        result = []
        for alias, profile in self._profiles.items():
            valid = True
            error = None
            try:
                self.resolve(alias)
            except (KeyError, ValueError) as exc:
                valid = False
                error = str(exc)
            result.append({
                "id": alias,
                "path": str(profile.path),
                "valid": valid,
                "error": error,
            })
        return result


@dataclass(frozen=True)
class RuntimeConfig:
    llama_server: str = "/app/llama-server"
    internal_host: str = "127.0.0.1"
    internal_port: int = 8081
    context_size: int = 4096
    threads: int = 4
    load_timeout: float = 300
    request_timeout: float = 900


def _spawn(command: list[str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(command, start_new_session=True)


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


class ModelRuntime:
    def __init__(
        self,
        registry: ProfileRegistry,
        config: RuntimeConfig,
        *,
        spawn: Callable[[list[str]], subprocess.Popen[bytes]] = _spawn,
        wait_ready: Callable[[], None] | None = None,
        stop: Callable[[subprocess.Popen[bytes]], None] = _stop,
    ):
        self.registry = registry
        self.config = config
        self._spawn = spawn
        self._wait_ready = wait_ready or self._default_wait_ready
        self._stop = stop
        self._process: subprocess.Popen[bytes] | None = None
        self.active_profile: str | None = None
        self.lock = threading.RLock()
        self.state = "idle"
        self.last_error: str | None = None

    def _command(self, profile: ModelProfile) -> list[str]:
        return [
            self.config.llama_server,
            "--model", str(profile.path),
            "--host", self.config.internal_host,
            "--port", str(self.config.internal_port),
            "--ctx-size", str(self.config.context_size),
            "--threads", str(self.config.threads),
            "--threads-batch", str(self.config.threads),
            "--parallel", "1",
            "--no-ui",
            "--metrics",
            "--alias", profile.alias,
        ]

    def _default_wait_ready(self) -> None:
        deadline = time.monotonic() + self.config.load_timeout
        url = f"http://{self.config.internal_host}:{self.config.internal_port}/health"
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self._process is None or self._process.poll() is not None:
                raise RuntimeError("llama-server stopped during model loading")
            try:
                with urlopen(url, timeout=2) as response:
                    if 200 <= response.status < 300:
                        return
            except Exception as exc:  # readiness polling deliberately tolerates startup failures
                last_error = exc
            time.sleep(0.5)
        raise TimeoutError(f"llama-server readiness timed out: {last_error}")

    def ensure(self, alias: str) -> None:
        with self.lock:
            if (
                alias == self.active_profile
                and self._process is not None
                and self._process.poll() is None
            ):
                return
            profile = self.registry.resolve(alias)
            self.shutdown()
            self.state = "loading"
            self.last_error = None
            try:
                self._process = self._spawn(self._command(profile))
                self._wait_ready()
            except Exception as exc:
                self.last_error = str(exc)
                self.state = "failed"
                if self._process is not None:
                    self._stop(self._process)
                self._process = None
                self.active_profile = None
                raise
            self.active_profile = alias
            self.state = "ready"

    def shutdown(self) -> None:
        with self.lock:
            if self._process is not None:
                self._stop(self._process)
            self._process = None
            self.active_profile = None
            if self.state != "failed":
                self.state = "idle"

    def status(self) -> dict[str, object]:
        process_alive = self._process is not None and self._process.poll() is None
        return {
            "state": self.state,
            "activeProfile": self.active_profile,
            "processAlive": process_alive,
            "lastError": self.last_error,
            "config": asdict(self.config),
            "profiles": self.registry.describe(),
        }


def default_registry(root: Path) -> ProfileRegistry:
    return ProfileRegistry({
        "cad-qwen": ModelProfile("cad-qwen", root / "qwen3-4b/Qwen3-4B-Q4_K_M.gguf"),
        "cad-gemma": ModelProfile("cad-gemma", root / "gemma-3-4b-it/gemma-3-4b-it-Q4_K_M.gguf"),
        "cad-yandex": ModelProfile(
            "cad-yandex",
            root / "yandexgpt-5-lite-8b/YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf",
        ),
    })


def make_handler(runtime: ModelRuntime, api_key: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "GreenPlanLLMRuntime/1"

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"llm-runtime: {fmt % args}", flush=True)

        def _json(self, status: int, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            return not api_key or self.headers.get("Authorization") == f"Bearer {api_key}"

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                status = runtime.status()
                valid = all(item["valid"] for item in status["profiles"])
                self._json(200 if valid else 503, {"status": "ok" if valid else "degraded", **status})
                return
            if self.path == "/v1/models":
                if not self._authorized():
                    self._json(401, {"error": "unauthorized"})
                    return
                profiles = runtime.registry.describe()
                self._json(200, {"object": "list", "data": [
                    {"id": item["id"], "object": "model", "owned_by": "greenplan"}
                    for item in profiles if item["valid"]
                ]})
                return
            self._json(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/v1/chat/completions":
                self._json(404, {"error": "not_found"})
                return
            if not self._authorized():
                self._json(401, {"error": "unauthorized"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 2_000_000:
                    raise ValueError("request body must be between 1 byte and 2 MB")
                body = self.rfile.read(length)
                payload = json.loads(body)
                alias = payload.get("model")
                if not isinstance(alias, str):
                    raise ValueError("model must be an allowlisted profile alias")
                if alias == "cad-qwen":
                    template_options = payload.setdefault("chat_template_kwargs", {})
                    if isinstance(template_options, dict):
                        template_options.setdefault("enable_thinking", False)
                    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                runtime.registry.resolve(alias)
                with runtime.lock:
                    runtime.ensure(alias)
                    connection = http.client.HTTPConnection(
                        runtime.config.internal_host,
                        runtime.config.internal_port,
                        timeout=runtime.config.request_timeout,
                    )
                    connection.request(
                        "POST", "/v1/chat/completions", body=body,
                        headers={"Content-Type": "application/json"},
                    )
                    response = connection.getresponse()
                    response_body = response.read()
                    response_type = response.getheader("Content-Type") or "application/json"
                    connection.close()
                self.send_response(response.status)
                self.send_header("Content-Type", response_type)
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": "invalid_request", "detail": str(exc)})
            except Exception as exc:
                self._json(502, {"error": "model_runtime_failed", "detail": str(exc)})

    return Handler


def main() -> None:
    root = Path(os.getenv("MODEL_ROOT", "/models")).resolve()
    config = RuntimeConfig(
        llama_server=os.getenv("LLAMA_SERVER_BIN", "/app/llama-server"),
        context_size=int(os.getenv("LLM_CONTEXT_SIZE", "4096")),
        threads=int(os.getenv("LLM_THREADS", "4")),
        load_timeout=float(os.getenv("LLM_LOAD_TIMEOUT", "300")),
        request_timeout=float(os.getenv("LLM_REQUEST_TIMEOUT", "900")),
    )
    runtime = ModelRuntime(default_registry(root), config)
    server = ThreadingHTTPServer(
        (os.getenv("RUNTIME_HOST", "0.0.0.0"), int(os.getenv("RUNTIME_PORT", "8080"))),
        make_handler(runtime, os.getenv("LLM_RUNTIME_API_KEY", "")),
    )

    def stop_server(_signum: int, _frame: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop_server)
    signal.signal(signal.SIGINT, stop_server)
    try:
        server.serve_forever()
    finally:
        runtime.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
