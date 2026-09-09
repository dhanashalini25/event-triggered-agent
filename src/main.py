"""CLI entrypoint.

    python -m src.main "your prompt here"
"""
from __future__ import annotations

import sys

from .agent import DEMO, run

if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or DEMO
    print(run(prompt))
