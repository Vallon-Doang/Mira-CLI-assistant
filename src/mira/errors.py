"""Error types and exit codes for MIRA."""

from __future__ import annotations

EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_USAGE = 2
EXIT_OLLAMA = 3
EXIT_MODEL = 4
EXIT_INTERRUPTED = 130


class MiraError(Exception):
    """Base class for expected, user-facing failures."""

    exit_code = EXIT_GENERIC

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def render(self) -> str:
        if self.hint:
            return f"MIRA: {self.message}\n\n{self.hint}"
        return f"MIRA: {self.message}"


class UsageError(MiraError):
    exit_code = EXIT_USAGE


class ConfigError(UsageError):
    """Malformed or invalid configuration."""


class OllamaUnreachableError(MiraError):
    exit_code = EXIT_OLLAMA


class ModelMissingError(MiraError):
    exit_code = EXIT_MODEL


class GenerationError(MiraError):
    exit_code = EXIT_GENERIC


class InterruptedError_(MiraError):
    exit_code = EXIT_INTERRUPTED
