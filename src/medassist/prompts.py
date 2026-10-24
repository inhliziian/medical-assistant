"""Prompt files: markdown with a YAML-ish front matter (version, changelog) and a {{report_text}} slot.
The part before the slot is sent as system instructions; the report text goes in the user turn."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPT_DIR = ROOT / "prompts" / "extraction"


@dataclass(frozen=True)
class Prompt:
    name: str          # e.g. "v1"
    version: str
    instructions: str  # system text, with the {{report_text}} line removed

    @classmethod
    def load(cls, name: str) -> "Prompt":
        path = PROMPT_DIR / f"{name}.md"
        text = path.read_text(encoding="utf-8")
        version = name
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if m:
            fm = m.group(1)
            vm = re.search(r"^version:\s*(\S+)", fm, re.M)
            if vm:
                version = vm.group(1)
            text = text[m.end():]
        # the report is sent as the user message, so drop the placeholder line and anything after it
        text = re.split(r"\{\{\s*report_text\s*\}\}", text)[0]
        return cls(name=name, version=version, instructions=text.strip())
