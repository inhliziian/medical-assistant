"""Provider interface. Every model, hosted or local, is used through `Provider.extract()` and returns
an `ExtractionResult`, so the run loop, the scorer and the report never know which model they talk to.

Validation policy (course task 3): every answer is validated against the schema. An invalid answer gets
exactly one repair call: the same system prompt and sampling settings, the conversation extended with the
model's own invalid answer and the validation error, asking for a corrected object. If the repair is also
invalid the document is marked `failed`. Transport failures (timeouts, HTTP errors) are retried separately
and never count as repair attempts."""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import ValidationError

from medassist.schema import Report, strict_json_schema

Message = dict[str, str]  # {"role": "user" | "assistant", "content": str}

REPAIR_MESSAGE = (
    "Your previous answer did not validate against the required JSON schema.\n"
    "Validation error: {error}\n"
    "Return the corrected JSON object only: every required field, allowed values only, no text around it."
)

STATUSES = ("ok", "repaired", "failed", "error")


@dataclass(frozen=True)
class RunConfig:
    """One named configuration from config/runs.toml: which provider, which model, which knobs."""
    name: str
    provider: str          # key under [providers] in the TOML
    kind: str              # "anthropic" | "ollama"
    model: str
    params: dict[str, Any] = field(default_factory=dict)   # effort / temperature / top_p / constrained / ...
    price_input_per_mtok: float = 0.0
    price_output_per_mtok: float = 0.0
    timeout_s: float = 120.0
    max_retries: int = 2
    base_url: str | None = None

    @property
    def constrained(self) -> bool:
        """Schema-constrained decoding on the provider side (default). Off = free-form JSON, which is how
        the repair path gets exercised for real."""
        return bool(self.params.get("constrained", True))


@dataclass
class ExtractionResult:
    config: str
    provider: str
    model: str
    params: dict[str, Any]
    raw_text: str | None               # final answer text (the repaired one if a repair happened)
    parsed: dict[str, Any] | None
    valid: bool
    validation_error: str | None       # error of the final answer, None when valid
    latency_ms: float                  # wall clock over every call, retries and the repair included
    input_tokens: int | None           # summed over every call that returned usage
    output_tokens: int | None
    attempts: int                      # model calls made in total (transport retries + repair)
    status: str = "ok"                 # ok | repaired | failed | error
    transport_retries: int = 0         # retries after timeouts / HTTP errors, over all calls
    repair_attempted: bool = False
    validation_errors: list[str] = field(default_factory=list)   # first answer's error, then the repair's
    error: str | None = None           # transport error that ended the document, if any
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def cost_usd(self) -> float | None:
        return self.extra.get("cost_usd")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_report(raw_text: str | None) -> tuple[dict[str, Any] | None, bool, str | None]:
    """Parse + validate a model answer against the schema. Returns (parsed, valid, error)."""
    if raw_text is None or not raw_text.strip():
        return None, False, "empty: the model returned no text"
    try:
        report = Report.model_validate_json(raw_text)
        return report.model_dump(), True, None
    except ValidationError as e:
        # keep whatever JSON there was, so error analysis can see what the model produced
        try:
            parsed = json.loads(raw_text)
        except Exception:
            parsed = None
        first = e.errors()[0]
        if first.get("type") == "json_invalid":   # pydantic reports unparseable text as a validation error
            return None, False, f"json: {first['msg']}"
        loc = "/".join(str(p) for p in first["loc"]) or "<root>"
        return parsed, False, f"schema: {first['msg']} at {loc} ({len(e.errors())} error(s))"
    except Exception as e:  # json decode error etc.
        return None, False, f"json: {type(e).__name__}: {e}"


def _add(a: int | None, b: int | None) -> int | None:
    if a is None:
        return b
    if b is None:
        return a
    return a + b


class Provider(ABC):
    """Common interface. Subclasses implement `_call` only; timing, retry, validation, repair and cost
    accounting are shared."""

    def __init__(self, config: RunConfig):
        self.config = config
        self.schema = strict_json_schema()

    @abstractmethod
    def _call(self, instructions: str, messages: list[Message]) -> tuple[str | None, int | None, int | None, dict[str, Any]]:
        """One model call. `messages` is the user/assistant conversation (the system text is separate).
        Return (raw_text, input_tokens, output_tokens, extra). Must raise on transport failure."""

    def _call_with_retries(self, instructions: str, messages: list[Message]):
        """Returns (raw, in_tok, out_tok, extra, retries, error). `error` is set only when every attempt failed."""
        retries = 0
        while True:
            try:
                raw, in_tok, out_tok, extra = self._call(instructions, messages)
                return raw, in_tok, out_tok, extra, retries, None
            except Exception as e:  # transport-level failure: retry with backoff
                err = f"{type(e).__name__}: {e}"
                if retries >= self.config.max_retries:
                    return None, None, None, {}, retries, err
                retries += 1
                time.sleep(min(2 ** retries, 10))

    @staticmethod
    def repair_messages(messages: list[Message], raw: str | None, error: str) -> list[Message]:
        """The conversation for the one repair call: original turn, the invalid answer, the error."""
        answer = raw if raw and raw.strip() else "(empty answer)"
        return [*messages,
                {"role": "assistant", "content": answer.strip()},
                {"role": "user", "content": REPAIR_MESSAGE.format(error=error)}]

    def extract(self, instructions: str, report_text: str) -> ExtractionResult:
        c = self.config
        t0 = time.perf_counter()
        messages: list[Message] = [{"role": "user", "content": report_text}]

        raw, in_tok, out_tok, extra, retries, error = self._call_with_retries(instructions, messages)
        calls = 1 + retries
        errors: list[str] = []
        parsed, valid, verr = (None, False, None) if error else validate_report(raw)
        repaired = False

        if error is None and not valid:
            errors.append(verr)
            repaired = True
            raw2, in2, out2, extra2, retries2, error2 = self._call_with_retries(
                instructions, self.repair_messages(messages, raw, verr))
            calls += 1 + retries2
            retries += retries2
            in_tok, out_tok = _add(in_tok, in2), _add(out_tok, out2)
            extra = {**extra, "first_answer": raw, "repair": extra2}
            if error2 is None:
                raw = raw2
                parsed, valid, verr = validate_report(raw2)
                if not valid:
                    errors.append(verr)
            else:
                error = error2

        if error:
            status = "error"
        elif valid:
            status = "repaired" if repaired else "ok"
        else:
            status = "failed"

        latency_ms = (time.perf_counter() - t0) * 1000
        if in_tok is not None and out_tok is not None:
            extra["cost_usd"] = (in_tok * c.price_input_per_mtok + out_tok * c.price_output_per_mtok) / 1_000_000
        return ExtractionResult(
            config=c.name, provider=c.provider, model=c.model, params=dict(c.params),
            raw_text=raw, parsed=parsed, valid=valid, validation_error=None if valid else verr,
            latency_ms=round(latency_ms, 1), input_tokens=in_tok, output_tokens=out_tok,
            attempts=calls, status=status, transport_retries=retries, repair_attempted=repaired,
            validation_errors=errors, error=error, extra=extra,
        )
