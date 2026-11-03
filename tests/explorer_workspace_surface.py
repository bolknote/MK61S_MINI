#!/usr/bin/env python3
"""Exercise the production owner and memory dispatcher against a bounded backend."""
from pathlib import Path
import sys
from ui_contract_surface import body

root = Path(__file__).resolve().parents[1]
out = Path(sys.argv[1])
source = root / 'code/loadable_system_api.cpp'
(out / 'explorer_memory_owner.inc').write_text(body(source, 'static language_workspace::Owner owner('))
(out / 'explorer_memory_cases.inc').write_text(
    body(source, 'case MK61_SYS_MEMORY_ACQUIRE: {') +
    body(source, 'case MK61_SYS_MEMORY_RELEASE: {'))
(out / 'explorer_workspace_layout.inc').write_text(
    body(root / 'code/explorer_ui.cpp', '  struct CachedIcon {', True) +
    body(root / 'code/explorer_ui.cpp', '  struct Workspace {', True))
