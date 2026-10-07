#!/usr/bin/env python3
"""Extract the real resident adapter for flow lifetime/legacy/pin gates."""
from pathlib import Path
import sys
from ui_contract_surface import body
root = Path(__file__).resolve().parents[1]
source = root / "code/loadable_module_runtime.cpp"
Path(sys.argv[1]).write_text(body(source, "static __attribute__((noinline)) u32 call_entry(") +
                           body(source, "bool flow_overlaps_app(") +
                           body(source, "struct FlowBinding", True) +
                           body(source, "app_flow::Status flow_invoke("))
