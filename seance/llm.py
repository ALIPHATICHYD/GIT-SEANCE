"""The medium: talks to an open-weight model running on your own machine.

Two dialects are supported, both local by default:
  * Ollama's native /api/chat (the default, e.g. `ollama pull gemma3:4b`)
  * any OpenAI-compatible server (llama.cpp's llama-server, LM Studio, vLLM)

Only the standard library is used, so nothing phones home.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterator

DEFAULT_MODEL = os.environ.get("SEANCE_MODEL", "gemma3:4b")
DEFAULT_BACKEND = os.environ.get("SEANCE_BACKEND", "ollama")
DEFAULT_HOST = os.environ.get("SEANCE_HOST", "")


class MediumError(RuntimeError):
    pass


class Medium:
    def __init__(self, model: str = DEFAULT_MODEL, backend: str = DEFAULT_BACKEND, host: str = DEFAULT_HOST,
                 temperature: float = 0.8):
        self.model = model
        self.backend = backend
        self.host = (host or ("http://localhost:11434" if backend == "ollama" else "http://localhost:8080")).rstrip("/")
        self.temperature = temperature

    def channel(self, messages: list[dict]) -> Iterator[str]:
        """Stream the spirit's reply, token by token."""
        if self.backend == "ollama":
            url = f"{self.host}/api/chat"
            payload = {"model": self.model, "messages": messages, "stream": True,
                       "options": {"temperature": self.temperature}}
        elif self.backend == "openai":
            url = f"{self.host}/v1/chat/completions"
            payload = {"model": self.model, "messages": messages, "stream": True,
                       "temperature": self.temperature}
        else:
            raise MediumError(f"unknown backend {self.backend!r} (use 'ollama' or 'openai')")

        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        local = urllib.parse.urlparse(self.host).hostname in ("localhost", "127.0.0.1", "::1")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if local else urllib.request.build_opener()
        try:
            resp = opener.open(req, timeout=300)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            if e.code == 404 and self.backend == "ollama":
                raise MediumError(f"model {self.model!r} is not here. Try: ollama pull {self.model}") from e
            raise MediumError(f"the medium refused ({e.code}): {detail[:200]}") from e
        except urllib.error.URLError as e:
            hint = "Is Ollama running? Try: ollama serve" if self.backend == "ollama" else "Is your local server running?"
            raise MediumError(f"no answer from {self.host}. {hint}") from e

        with resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if self.backend == "openai":
                    if not line.startswith("data:"):
                        continue
                    line = line[5:].strip()
                    if line == "[DONE]":
                        break
                    chunk = json.loads(line)
                    delta = (chunk.get("choices") or [{}])[0].get("delta", {}).get("content")
                else:
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise MediumError(chunk["error"])
                    delta = chunk.get("message", {}).get("content")
                    if chunk.get("done"):
                        if delta:
                            yield delta
                        break
                if delta:
                    yield delta


class ScriptedMedium:
    """A stand-in spirit for tests and `--rehearse`: replays a fixed reply."""

    def __init__(self, reply: str):
        self.reply = reply
        self.model = "rehearsal"
        self.seen: list[list[dict]] = []

    def channel(self, messages: list[dict]) -> Iterator[str]:
        self.seen.append(messages)
        for word in self.reply.split(" "):
            yield word + " "
