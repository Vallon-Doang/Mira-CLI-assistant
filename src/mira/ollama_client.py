"""Minimal stdlib client for the local Ollama HTTP API."""

from __future__ import annotations

import json
import shutil
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.client import HTTPException
from typing import Iterator

from .errors import GenerationError, ModelMissingError, OllamaUnreachableError

_UNREACHABLE_HINT = (
    "Check:\n"
    "  systemctl status ollama\n"
    "\n"
    "Or start it manually:\n"
    "  ollama serve"
)

_NOT_INSTALLED_HINT = (
    "Ollama does not appear to be installed.\n"
    "\n"
    "Install it from:\n"
    "  https://ollama.com/download"
)


def _unreachable_hint() -> str:
    return _NOT_INSTALLED_HINT if shutil.which("ollama") is None else _UNREACHABLE_HINT


@dataclass
class ChatChunk:
    content: str = ""
    thinking: str = ""
    done: bool = False
    prompt_eval_count: int | None = None
    eval_count: int | None = None
    total_duration: int | None = None
    eval_duration: int | None = None
    prompt_eval_duration: int | None = None
    load_duration: int | None = None
    done_reason: str | None = None


class OllamaClient:
    def __init__(
        self,
        host: str,
        timeout: float = 120.0,
        connect_timeout: float = 3.0,
    ) -> None:
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self._thinking_cache: dict[str, bool] = {}

    # -- metadata ---------------------------------------------------------

    def version(self) -> dict:
        return self._get_json("/api/version", timeout=self.connect_timeout)

    def check_connection(self) -> None:
        """Fail fast when Ollama is not running or unreachable."""
        try:
            self.version()
        except OllamaUnreachableError:
            raise
        except GenerationError as exc:
            raise OllamaUnreachableError(
                "Ollama is not responding.",
                hint=_unreachable_hint(),
            ) from exc

    def list_models(self) -> list[dict]:
        data = self._get_json("/api/tags")
        models = data.get("models", [])
        if not isinstance(models, list):
            raise GenerationError("Ollama returned an unexpected model list.")
        return models

    def model_names(self) -> list[str]:
        names: list[str] = []
        for item in self.list_models():
            name = item.get("name") or item.get("model")
            if isinstance(name, str) and name:
                names.append(name)
        return names

    def ensure_model(self, model: str) -> None:
        names = self.model_names()
        if model in names:
            return
        available = ", ".join(names[:8]) if names else "none"
        raise ModelMissingError(
            f"Model {model!r} is not installed.",
            hint=(
                f"Available models: {available}\n\n"
                "List them with:\n"
                "  mira --list-models\n\n"
                "Pull it manually with:\n"
                f"  ollama pull {model}"
            ),
        )

    def show(self, model: str) -> dict:
        try:
            return self._post_json("/api/show", {"model": model})
        except ModelMissingError:
            raise
        except GenerationError as exc:
            raise GenerationError(f"Could not inspect model {model!r}: {exc}") from exc

    def supports_thinking(self, model: str) -> bool:
        if model in self._thinking_cache:
            return self._thinking_cache[model]
        supported = False
        try:
            info = self.show(model)
        except ModelMissingError:
            raise
        except GenerationError:
            info = {}
        capabilities = info.get("capabilities")
        if isinstance(capabilities, list) and "thinking" in capabilities:
            supported = True
        thinking = info.get("thinking")
        if isinstance(thinking, dict):
            values = thinking.get("values")
            if isinstance(values, list) and True in values:
                supported = True
        self._thinking_cache[model] = supported
        return supported

    def resolve_think(self, model: str, desired: bool) -> bool | None:
        """Return the API value, or None when the model has no control."""
        if self.supports_thinking(model):
            return desired
        return None

    # -- generation -------------------------------------------------------

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, object] | None = None,
        think: bool | None = None,
        stream: bool = True,
        keep_alive: str | int | None = "5m",
    ) -> Iterator[ChatChunk]:
        payload: dict[str, object] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if options:
            payload["options"] = options
        if think is not None:
            payload["think"] = think
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive

        if not stream:
            data = self._post_json("/api/chat", payload, model=model)
            yield self._chunk_from(data)
            return

        request = self._build_request("/api/chat", payload)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                for raw_line in response:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise GenerationError("Ollama returned an invalid streaming response.") from exc
                    if "error" in data:
                        raise GenerationError(f"Ollama error: {data['error']}")
                    yield self._chunk_from(data)
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc, model) from exc
        except urllib.error.URLError as exc:
            raise self._url_error(exc) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise self._timeout_error() from exc
        except (HTTPException, ConnectionError) as exc:
            raise GenerationError("The connection to Ollama was interrupted.") from exc

    # -- internals --------------------------------------------------------

    def _build_request(self, path: str, payload: dict | None) -> urllib.request.Request:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        return urllib.request.Request(
            f"{self.host}{path}",
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST" if payload is not None else "GET",
        )

    def _get_json(self, path: str, timeout: float | None = None) -> dict:
        request = self._build_request(path, None)
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return self._decode(response.read())
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc, None) from exc
        except urllib.error.URLError as exc:
            raise self._url_error(exc) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise self._timeout_error(timeout or self.timeout) from exc
        except (HTTPException, ConnectionError) as exc:
            raise GenerationError("The connection to Ollama was interrupted.") from exc

    def _post_json(self, path: str, payload: dict, model: str | None = None) -> dict:
        request = self._build_request(path, payload)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return self._decode(response.read())
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc, model) from exc
        except urllib.error.URLError as exc:
            raise self._url_error(exc) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise self._timeout_error() from exc
        except (HTTPException, ConnectionError) as exc:
            raise GenerationError("The connection to Ollama was interrupted.") from exc

    def _decode(self, raw: bytes) -> dict:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GenerationError("Ollama returned an invalid response.") from exc
        if not isinstance(data, dict):
            raise GenerationError("Ollama returned an unexpected response.")
        if "error" in data:
            raise GenerationError(f"Ollama error: {data['error']}")
        return data

    def _chunk_from(self, data: dict) -> ChatChunk:
        message = data.get("message")
        content = ""
        thinking = ""
        if isinstance(message, dict):
            content = message.get("content") or ""
            thinking = message.get("thinking") or ""
        if not content and isinstance(data.get("response"), str):
            content = data["response"]
        return ChatChunk(
            content=content if isinstance(content, str) else "",
            thinking=thinking if isinstance(thinking, str) else "",
            done=bool(data.get("done", False)),
            prompt_eval_count=data.get("prompt_eval_count"),
            eval_count=data.get("eval_count"),
            total_duration=data.get("total_duration"),
            eval_duration=data.get("eval_duration"),
            prompt_eval_duration=data.get("prompt_eval_duration"),
            load_duration=data.get("load_duration"),
            done_reason=data.get("done_reason"),
        )

    def _http_error(self, exc: urllib.error.HTTPError, model: str | None) -> Exception:
        message = ""
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
                message = str(parsed.get("error", raw))
            except json.JSONDecodeError:
                message = raw
        except OSError:
            pass
        message = message.strip() or exc.reason or "unknown error"
        lowered = message.lower()
        if exc.code == 404 and ("model" in lowered or "not found" in lowered):
            if model:
                return ModelMissingError(
                    f"Model {model!r} is not installed.",
                    hint=(
                        "List installed models with:\n"
                        "  mira --list-models\n\n"
                        "Pull it manually with:\n"
                        f"  ollama pull {model}"
                    ),
                )
            return ModelMissingError("The requested model was not found.")
        if exc.code >= 500 and ("memory" in lowered or "out of memory" in lowered):
            return GenerationError(
                "Ollama could not load the model (out of memory).",
                hint=(
                    "Close GPU-heavy applications, or choose a smaller model:\n"
                    "  mira --model <smaller-model> \"...\""
                ),
            )
        if exc.code >= 500:
            return GenerationError(
                f"Ollama request failed: {message}",
                hint="Check the Ollama service logs:\n  journalctl -u ollama -n 50",
            )
        return GenerationError(f"Ollama request failed: {message}")

    def _url_error(self, exc: urllib.error.URLError) -> Exception:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return self._timeout_error()
        if isinstance(reason, (ConnectionRefusedError, FileNotFoundError, socket.gaierror)):
            return OllamaUnreachableError("Ollama is not responding.", hint=_unreachable_hint())
        return OllamaUnreachableError(
            f"Cannot reach Ollama at {self.host}: {reason}",
            hint=_unreachable_hint(),
        )

    def _timeout_error(self, timeout: float | None = None) -> Exception:
        seconds = timeout if timeout is not None else self.timeout
        return GenerationError(
            f"Ollama did not respond within {seconds:.0f}s.",
            hint=(
                "The model may still be loading. Retry, or raise ollama.timeout\n"
                "in your MIRA configuration."
            ),
        )
