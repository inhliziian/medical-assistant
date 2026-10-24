"""Load config/runs.toml into RunConfig objects and build the matching provider."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

from .providers.base import Provider, RunConfig

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "runs.toml"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Load KEY=VALUE lines from .env into the environment without overriding variables already set.
    Keeps the API key out of the shell profile and out of git (.env is ignored)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()


def load_configs(path: Path = DEFAULT_CONFIG) -> dict[str, RunConfig]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    providers = data["providers"]
    out: dict[str, RunConfig] = {}
    for name, cfg in data["configs"].items():
        cfg = dict(cfg)
        pname = cfg.pop("provider")
        prov = providers[pname]
        out[name] = RunConfig(
            name=name, provider=pname, kind=prov["type"], model=prov["model"], params=cfg,
            price_input_per_mtok=prov.get("price_input_per_mtok", 0.0),
            price_output_per_mtok=prov.get("price_output_per_mtok", 0.0),
            timeout_s=prov.get("timeout_s", 120.0), max_retries=prov.get("max_retries", 2),
            base_url=prov.get("base_url"),
        )
    return out


def build_provider(config: RunConfig) -> Provider:
    if config.kind == "anthropic":
        from .providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(config)
    if config.kind == "ollama":
        from .providers.ollama_provider import OllamaProvider
        return OllamaProvider(config)
    raise ValueError(f"unknown provider type {config.kind!r}")


def get(config_name: str, path: Path = DEFAULT_CONFIG) -> tuple[Provider, RunConfig]:
    cfgs = load_configs(path)
    if config_name not in cfgs:
        raise KeyError(f"no config {config_name!r}; available: {', '.join(cfgs)}")
    c = cfgs[config_name]
    return build_provider(c), c
