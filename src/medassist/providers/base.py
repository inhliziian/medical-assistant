"""Provider interface. Every model, hosted or local, is used through `Provider.extract()` and returns
an `ExtractionResult`, so the run loop, the scorer and the report never know which model they talk to."""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import ValidationError

from medassist.schema import Report, strict_json_schema


@dataclass(frozen=True)
class RunConfig:
    """One named configuration from config/runs.toml: which provider, which model, which knobs."""
    name: str
    provider: str          # key under [providers] in the TOML
    kind: str              # "anthropic" | "ollama"
    model: str
    params: dict[str, Any] = field(default_factory=dict)   # effort / temperature / top_p / ...
    price_input_per_mtok: float = 0.0
    price_output_per_mtok: float = 0.0
    timeout_s: float = 120.0
    max_retries: int = 2
    base_url: str | None = None


@dataclass
class ExtractionResult:
    config: str
    provider: str
    model: str
    params: dict[str, Any]
    raw_text: str | None
    parsed: dict[str, Any] | None
    valid: bool
    validation_error: str | None
    latency_ms: float
    input_tokens: int | None
    output_tokens: int | None
    attempts: int
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def cost_usd(self) -> float | None:
        return self.extra.get("cost_usd")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_report(raw_text: str | None) -> tuple[dict[str, Any] | None, bool, str | None]:
    """Parse + validate a model answer against the schema. Returns (parsed, valid, error)."""
    if raw_text is None:
        return None, False, "no output"
    try:
        report = Report.model_validate_json(raw_text)
        return report.model_dump(), True, None
    except ValidationError as e:
        # keep whatever JSON there was, so error analysis can see what the model produced
        try:
            parsed = json.loads(raw_text)
        except Exception:
            parsed = None
        return parsed, False, f"schema: {e.errors()[0]['msg']} at {'/'.join(str(p) for p in e.errors()[0]['loc'])}"
    except Exception as e:  # json decode error etc.
        return None, False, f"json: {type(e).__name__}: {e}"


class Provider(ABC):
    """Common interface. Subclasses implement `_call` only; timing, validation and cost are shared."""

    def __init__(self, config: RunConfig):
        self.config = config
        self.schema = strict_json_schema()

    @abstractmethod
    def _call(self, instructions: str, report_text: str) -> tuple[str | None, int | None, int | None, dict[str, Any]]:
        """Return (raw_text, input_tokens, output_tokens, extra). Must raise on transport failure."""

    def extract(self, instructions: str, report_text: str) -> ExtractionResult:
        c = self.config
        t0 = time.perf_counter()
        attempts = 0
        raw = None
        in_tok = out_tok = None
        extra: dict[str, Any] = {}
        error = None
        while attempts <= c.max_retries:
            attempts += 1
            try:
                raw, in_tok, out_tok, extra = self._call(instructions, report_text)
                error = None
                break
            except Exception as e:  # transport-level failure: retry
                error = f"{type(e).__name__}: {e}"
                if attempts > c.max_retries:
                    break
                time.sleep(min(2 ** attempts, 10))
        latency_ms = (time.perf_counter() - t0) * 1000
        parsed, valid, verr = validate_report(raw)
        if in_tok is not None and out_tok is not None:
            extra["cost_usd"] = (in_tok * c.price_input_per_mtok + out_tok * c.price_output_per_mtok) / 1_000_000
        return ExtractionResult(
            config=c.name, provider=c.provider, model=c.model, params=dict(c.params),
            raw_text=raw, parsed=parsed, valid=valid, validation_error=verr,
            latency_ms=round(latency_ms, 1), input_tokens=in_tok, output_tokens=out_tok,
            attempts=attempts, error=error, extra=extra,
        )
