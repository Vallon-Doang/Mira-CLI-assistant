"""Shared fixtures: a fake Ollama HTTP server and an isolated config."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


class FakeOllama:
    def __init__(self) -> None:
        self.host = ""
        self.models = [
            {
                "name": "test-model:latest",
                "model": "test-model:latest",
                "size": 1_500_000_000,
                "details": {
                    "parameter_size": "1.5B",
                    "quantization_level": "Q4_K_M",
                },
            }
        ]
        self.chat_text = "Hello from the fake model."
        self.thinking_text = ""
        self.think_supported = True
        self.fail_status: int | None = None
        self.fail_body = ""
        self.requests: list[dict] = []
        self.last_chat_payload: dict | None = None

    def request_count(self, path: str) -> int:
        return sum(1 for item in self.requests if item.get("path") == path)


def _handler_for(fake: FakeOllama):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            fake.requests.append({"method": "GET", "path": self.path, "payload": None})
            if self.path == "/api/version":
                self._send(200, {"version": "0.0.0-fake"})
            elif self.path == "/api/tags":
                self._send(200, {"models": fake.models})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            payload = json.loads(raw) if raw else {}
            fake.requests.append({"method": "POST", "path": self.path, "payload": payload})
            if fake.fail_status is not None:
                self._send(fake.fail_status, {"error": fake.fail_body or "fake failure"})
                return
            if self.path == "/api/show":
                model = payload.get("model")
                if not any(item["name"] == model for item in fake.models):
                    self._send(404, {"error": f"model {model!r} not found"})
                    return
                capabilities = ["completion"]
                if fake.think_supported:
                    capabilities.append("thinking")
                self._send(
                    200,
                    {
                        "capabilities": capabilities,
                        "thinking": {"values": [False, True], "default": True}
                        if fake.think_supported
                        else {},
                    },
                )
                return
            if self.path == "/api/chat":
                fake.last_chat_payload = payload
                model = payload.get("model")
                if not any(item["name"] == model for item in fake.models):
                    self._send(404, {"error": f"model {model!r} not found"})
                    return
                if payload.get("stream", True):
                    self._stream_chat(fake)
                else:
                    self._send(200, self._full_chat(fake))
                return
            self._send(404, {"error": "not found"})

        def _full_chat(self, fake: FakeOllama) -> dict:
            message = {"role": "assistant", "content": fake.chat_text}
            if fake.thinking_text:
                message["thinking"] = fake.thinking_text
            return {
                "model": "test-model:latest",
                "message": message,
                "done": True,
                "prompt_eval_count": 12,
                "eval_count": 5,
                "eval_duration": 500_000_000,
            }

        def _stream_chat(self, fake: FakeOllama) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            def write_line(data: dict) -> None:
                line = (json.dumps(data) + "\n").encode("utf-8")
                self.wfile.write(f"{len(line):X}\r\n".encode("ascii"))
                self.wfile.write(line)
                self.wfile.write(b"\r\n")
                self.wfile.flush()

            words = fake.chat_text.split(" ")
            for index, word in enumerate(words):
                content = word if index == 0 else " " + word
                message: dict[str, str] = {"role": "assistant", "content": content}
                if fake.thinking_text:
                    message["thinking"] = fake.thinking_text
                write_line({"model": "test-model:latest", "message": message, "done": False})
            write_line(
                {
                    "model": "test-model:latest",
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "prompt_eval_count": 12,
                    "eval_count": 5,
                    "eval_duration": 500_000_000,
                }
            )
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()

    return Handler


@pytest.fixture
def fake_ollama():
    fake = FakeOllama()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(fake))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fake.host = f"http://127.0.0.1:{server.server_port}"
    try:
        yield fake
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def mira_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_ollama: FakeOllama) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        "[model]\n"
        'name = "test-model:latest"\n'
        "num_predict = 32\n"
        "num_ctx = 2048\n"
        "\n[ollama]\n"
        f'host = "{fake_ollama.host}"\n'
        "timeout = 10\n"
        "\n[behavior]\n"
        "direct_answers = true\n"
        "\n[retrieval]\n"
        "max_results = 3\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MIRA_CONFIG", str(path))
    return path
