#!/usr/bin/env python3
"""Class-6 a is not interchangeable with the checked long class-0 a."""
import runpy
from pathlib import Path
root=Path(__file__).resolve().parent
fmt=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
for source,markers,target in (
    ('P7',('marker','Z','V'),'X'),
    ('X',('marker','Z','V'),'P7'),
    ('X',('marker','Z','W'),'P8'),
):
    fmt(0,5,True,source_slot=source,marker_slots=markers,target_by_class=[target]*9)
print('PASS decimal class 6: ENTER still reads a to X, but NOP does not remove V; post-push late copy hits P8.',flush=True)
