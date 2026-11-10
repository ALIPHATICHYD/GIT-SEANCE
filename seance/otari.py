"""The switchboard: talks to an Otari gateway (https://otari.ai, Mozilla AI's open-source AI gateway).

One key reaches many open-weight models. Otari also tells us which provider really
answered, whether a fallback fired, and what each séance cost, so the CLI can show
the summoner the receipt. Only the standard library is used.

Environment:
  OTARI_API_KEY    an API key from https://otari.ai/dashboard/#/keys (required)
  OTARI_BASE_URL   default https://api.otari.ai/api/v1 (EU: https://eu.api.otari.ai/api/v1,
                   self-hosted: http://localhost:8000/api/v1)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Iterator

DEFAULT_BASE = "https://api.otari.ai/api/v1"
DEFAULT_OTARI_MODEL = os.environ.get("SEANCE_OTARI_MODEL", "openai/gpt-oss-120b")

# Open-weight families we prefer for the tribunal when the caller names none.
PREFERRED = ("gemma", "llama", "qwen", "mistral", "gpt-oss", "deepseek", "glm", "kimi", "phi", "olmo")


class OtariError(RuntimeError):
    pass


@dataclass
class Receipt:
    """What Otari says about one séance: who answered, how, and for how much."""

    request_id: str = ""
    provider: str = ""
    model: str = ""
    attempts: int = 1
    fallback: bool = False
    duration_ms: int | None = None
    cost_usd: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    tool_calls: list[dict] = field(default_factory=list)

    def line(self) -> str:
        bits = [f"answered by {self.model or '?'}" + (f" on {self.provider}" if self.provider else "")]
        if self.fallback or self.attempts > 1:
            bits.append(f"after {self.attempts} attempts (fallback fired)")
        if self.duration_ms is not None:
            bits.append(f"first byte in {self.duration_ms / 1000:.1f}s")
        if self.completion_tokens is not None:
            bits.append(f"{(self.prompt_tokens or 0) + self.completion_tokens} tokens")
        if self.cost_usd is not None:
            bits.append(f"${self.cost_usd:.6f}")
        if self.request_id:
            bits.append(f"request {self.request_id}")
        return " · ".join(bits)


def _float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class Otari:
    def __init__(self, key: str | None = None, base: str | None = None, timeout: int = 300):
        self.key = key if key is not None else os.environ.get("OTARI_API_KEY", "")
        self.base = (base or os.environ.get("OTARI_BASE_URL") or DEFAULT_BASE).rstrip("/")
        if not self.base.endswith("/v1"):
            self.base += "/api/v1" if not self.base.endswith("/api") else "/v1"
        self.timeout = timeout

    # ------------------------------------------------------------ plumbing

    def _request(self, method: str, path: str, body: dict | None = None,
                 headers: dict | None = None) -> urllib.response.addinfourl:
        if not self.key:
            raise OtariError("no OTARI_API_KEY. Make one at https://otari.ai/dashboard/#/keys and export it.")
        h = {"Authorization": f"Bearer {self.key}", "Accept": "application/json",
             "User-Agent": "git-seance"}
        data = None
        if body is not None:
            h["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, data=data, headers=h, method=method)
        host = urllib.parse.urlparse(self.base).hostname
        opener = (urllib.request.build_opener(urllib.request.ProxyHandler({}))
                  if host in ("localhost", "127.0.0.1", "::1") else urllib.request.build_opener())
        try:
            return opener.open(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            code = e.headers.get("Otari-Error-Code") or ""
            try:
                msg = json.loads(detail).get("detail") or detail
            except (ValueError, AttributeError):
                msg = detail
            if isinstance(msg, (dict, list)):
                msg = json.dumps(msg)
            hint = {401: " Check OTARI_API_KEY.", 421: " Your key belongs to the other region: set OTARI_BASE_URL.",
                    402: " The balance or pricing refused it.", 403: " A budget or policy refused it.",
                    424: " No provider serves that model for your key. Try: seance mediums"}.get(e.code, "")
            raise OtariError(f"Otari answered {e.code}{' ' + code if code else ''}: {str(msg)[:240]}.{hint}") from e
        except urllib.error.URLError as e:
            raise OtariError(f"no answer from {self.base} ({e.reason})") from e

    def _json(self, method: str, path: str, body: dict | None = None) -> dict:
        with self._request(method, path, body) as r:
            return json.loads(r.read().decode() or "{}")

    # ------------------------------------------------------------ chat

    def chat(self, model: str, messages: list[dict], receipt: Receipt, temperature: float = 0.8,
             tags: dict | None = None, tools: list[dict] | None = None) -> Iterator[str]:
        """Stream a chat completion, filling `receipt` from Otari's headers and usage chunk."""
        body: dict = {"model": model, "messages": messages, "stream": True, "temperature": temperature,
                      "stream_options": {"include_usage": True}}
        if tags:
            body["metadata"] = {k: str(v)[:512] for k, v in list(tags.items())[:16]}
        if tools:
            body["tools"] = tools
        resp = self._request("POST", "/chat/completions", body, {"Accept": "text/event-stream"})
        hd = resp.headers
        receipt.request_id = hd.get("Otari-Request-ID", "") or ""
        receipt.provider = hd.get("Otari-Provider", "") or ""
        receipt.model = hd.get("Otari-Model", "") or model
        receipt.attempts = int(hd.get("Otari-Attempt-Count") or 1)
        receipt.fallback = (hd.get("Otari-Fallback") or "").lower() in ("1", "true", "yes")
        dur = hd.get("Otari-Response-Duration-Ms")
        receipt.duration_ms = int(float(dur)) if dur else None
        calls: dict[str, dict] = {}
        with resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                line = line[5:].strip()
                if line == "[DONE]":
                    break
                try:
                    chunk = json.loads(line)
                except ValueError:
                    continue
                if chunk.get("error"):
                    err = chunk["error"]
                    raise OtariError(err.get("message") if isinstance(err, dict) else str(err))
                for tc in chunk.get("otari_tool_calls") or []:
                    calls[tc.get("id", str(len(calls)))] = tc
                usage = chunk.get("usage")
                if usage:
                    receipt.prompt_tokens = usage.get("prompt_tokens", receipt.prompt_tokens)
                    receipt.completion_tokens = usage.get("completion_tokens", receipt.completion_tokens)
                    if usage.get("cost_usd") is not None:
                        receipt.cost_usd = _float(usage.get("cost_usd"))
                if chunk.get("model") and not hd.get("Otari-Model"):
                    receipt.model = chunk["model"]
                for ch in chunk.get("choices") or []:
                    delta = (ch.get("delta") or {}).get("content")
                    if delta:
                        yield delta
        receipt.tool_calls = list(calls.values())

    # ------------------------------------------------------------ the rest of the switchboard

    def fetch(self, url: str, max_chars: int = 2500) -> dict:
        """Read one public page through Otari's gateway fetcher (POST /fetch)."""
        return self._json("POST", "/fetch", {"url": url, "max_chars": max_chars})

    def budget(self) -> dict:
        """What this key may still spend (GET /key/budget)."""
        return self._json("GET", "/key/budget")

    def open_weight_models(self) -> list[dict]:
        """Open-weight chat models this key can reach, cheapest first."""
        try:
            d = self._json("GET", "/catalog/models?type=chat&limit=200&sort=price&direction=asc")
            models = [m for m in d.get("models", []) if m.get("open_weights")]
            if models:
                return [{"id": m.get("selector") or m["id"], "name": m.get("name") or m["id"],
                         "vendor": m.get("vendor") or "", "context": m.get("context_window"),
                         "in": m.get("min_input_price_per_million"), "out": m.get("min_output_price_per_million")}
                        for m in models]
        except OtariError:
            pass
        d = self._json("GET", "/models")
        out = []
        for m in d.get("data", []):
            mid = m.get("id", "")
            if (m.get("type") in (None, "chat")) and any(p in mid.lower() for p in PREFERRED):
                pr = m.get("pricing") or {}
                out.append({"id": mid, "name": m.get("name") or mid, "vendor": m.get("owned_by", ""),
                            "context": m.get("context_window"), "in": pr.get("input_price_per_million"),
                            "out": pr.get("output_price_per_million")})
        return out


def pick_panel(models: list[dict], n: int = 3) -> list[str]:
    """Choose n open-weight mediums from different families, so the tribunal is a fair fight."""
    chosen, families = [], set()
    for fam in PREFERRED:
        for m in models:
            mid = m["id"].lower()
            if fam in mid and fam not in families and "embed" not in mid and "guard" not in mid:
                chosen.append(m["id"])
                families.add(fam)
                break
        if len(chosen) == n:
            break
    return chosen
