#!/usr/bin/env python3
"""Extract the production Explorer run policy for a host regression test."""

import sys
from pathlib import Path

from ui_contract_surface import body


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = Path(sys.argv[1])
    output.write_text(
        body(root / "code/development.cpp", "static bool entry_can_run("),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
