"""Provider-neutral interface for free, locally served open-weight models."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence


ChatMessage = Mapping[str, str]


class ChatBackend(Protocol):
    model: str

    def generate(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 256,
    ) -> str: ...


@dataclass
class OpenAICompatibleLocalBackend:
    """Call a local OpenAI-compatible server such as `mlx_lm.server`."""

    model: str
    base_url: str = "http://127.0.0.1:8000/v1"
    timeout_seconds: float = 120.0

    def generate(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 256,
    ) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": list(messages),
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(
                f"local model server unavailable at {self.base_url}: {exc}"
            ) from exc
        try:
            return str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("local model server returned an invalid response") from exc


@dataclass
class CachedChatBackend:
    """Content-addressed completion cache for reproducible audit trails."""

    backend: ChatBackend
    cache_dir: Path

    @property
    def model(self) -> str:
        return self.backend.model

    def generate(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 256,
    ) -> str:
        request_record = {
            "model": self.model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        canonical = json.dumps(request_record, sort_keys=True, separators=(",", ":"))
        key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            return str(json.loads(path.read_text(encoding="utf-8"))["response"])

        response = self.backend.generate(
            messages, temperature=temperature, max_tokens=max_tokens
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        artifact = {"request": request_record, "response": response}
        path.write_text(
            json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return response
