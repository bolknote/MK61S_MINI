#!/usr/bin/env python3
"""Exercise compact system APP size ceilings without requiring an ARM build."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_portable_app", ROOT / "tools/build_portable_app.py")
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


BUILDER.enforce_system_size_budget(
    "focal", {"app_bytes": 12_000, "memory_bytes": 17_000})
BUILDER.enforce_system_size_budget(
    "tinybasic", {"app_bytes": 99_999, "memory_bytes": 99_999})

try:
    BUILDER.enforce_system_size_budget(
        "focal", {"app_bytes": 12_001, "memory_bytes": 17_001})
except ValueError as error:
    message = str(error)
    assert "app_bytes=12001 > 12000" in message
    assert "memory_bytes=17001 > 17000" in message
else:
    raise AssertionError("oversize FOCAL APP was accepted")

print("portable APP size budget tests: OK")
