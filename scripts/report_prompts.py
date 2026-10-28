"""Build the prompt comparison page (v1 against v2 on the golden set and the full dataset).

  uv run python scripts/report_prompts.py [--out results/report-prompt-v1-vs-v2.html]"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from medassist.report_prompts import DEFAULT_OUT, build_prompt_page  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    build_prompt_page(Path(ap.parse_args().out), verbose=True)
