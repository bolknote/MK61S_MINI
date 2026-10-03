#!/usr/bin/env python3
"""Extract the production Explorer run policy for a host regression test."""

import sys
from pathlib import Path

from ui_contract_surface import body


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = Path(sys.argv[1])
    source = root / "code/development.cpp"
    view = body(source, "static bool view_entry(")
    assert view.index("reject_unavailable_chip8(entry)") < view.index("shared_scratch::Lease")
    output.write_text(
        body(source, "static bool reject_unavailable_chip8(") + "\n" +
        body(source, "static bool entry_can_run("),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
