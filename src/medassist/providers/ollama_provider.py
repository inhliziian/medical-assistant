"""Local provider: any Ollama model through POST /api/chat with the JSON schema in `format`.

Knobs: temperature, top_p, seed, num_predict (passed through to `options`), think (bool, default
false; Qwen3 otherwise spends tokens on reasoning), keep_alive, constrained (default true; false drops
the schema from `format` so the model writes free-form JSON).
"""
from __future__ import annotations

from typing import Any

import httpx

from .base import Message, Provider, RunConfig

OPTION_KEYS = ("temperature", "top_p", "top_k", "seed", "num_predict", "num_ctx", "repeat_penalty")


class OllamaProvider(Provider):
    def __init__(self, config: RunConfig):
        super().__init__(config)
        self.base_url = (config.base_url or "http://localhost:11434").rstrip("/")
        self.client = httpx.Client(timeout=config.timeout_s)

    def _call(self, instructions: str, messages: list[Message]):
        p = self.config.params
        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": [{"role": "system", "content": instructions}, *messages],
            "stream": False,
            "think": bool(p.get("think", False)),
            "keep_alive": p.get("keep_alive", "10m"),
            "options": {k: p[k] for k in OPTION_KEYS if k in p},
        }
        if self.config.constrained:
            body["format"] = self.schema
        r = self.client.post(f"{self.base_url}/api/chat", json=body)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        text = data.get("message", {}).get("content")
        extra = {
            "done_reason": data.get("done_reason"),
            "server_total_ms": round(data.get("total_duration", 0) / 1e6, 1),
            "server_eval_ms": round(data.get("eval_duration", 0) / 1e6, 1),
        }
        return text, data.get("prompt_eval_count"), data.get("eval_count"), extra
