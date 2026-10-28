"""Hosted provider: Claude via the Anthropic SDK with structured output (output_config.format).

Knobs (config/runs.toml [configs.*]): effort = low|medium|high (Haiku 5.5 rejects non-default
temperature/top_p, so effort is the sampling-side dimension here), max_tokens (default 8000; thinking
tokens count toward it), constrained (default true; false drops the schema from the request so the model
writes free-form JSON and the repair path is exercised).
"""
from __future__ import annotations

from typing import Any

import anthropic

from .base import Message, Provider, RunConfig


class AnthropicProvider(Provider):
    def __init__(self, config: RunConfig):
        super().__init__(config)
        # SDK retries 408/409/429/5xx and connection errors itself; timeout is in seconds.
        self.client = anthropic.Anthropic(timeout=config.timeout_s, max_retries=config.max_retries)

    def _call(self, instructions: str, messages: list[Message]):
        p = self.config.params
        output_config: dict[str, Any] = {}
        if self.config.constrained:
            output_config["format"] = {"type": "json_schema", "schema": self.schema}
        if p.get("effort"):
            output_config["effort"] = p["effort"]
        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=int(p.get("max_tokens", 8000)),
            system=instructions,
            messages=messages,
            **({"output_config": output_config} if output_config else {}),
        )
        text = next((b.text for b in response.content if b.type == "text"), None)
        extra = {"stop_reason": response.stop_reason, "response_id": response.id}
        return text, response.usage.input_tokens, response.usage.output_tokens, extra
