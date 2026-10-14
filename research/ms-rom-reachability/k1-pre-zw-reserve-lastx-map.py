#!/usr/bin/env python3
"""Bounded rejected reserve: LastX at the three reachable Z/W origins.

This proves connected primary prefixes through the late read. It does not
claim full formatter behavior, native reachability of each origin, or a
whole-K1 impossibility theorem.
"""
import runpy
from pathlib import Path

root=Path(__file__).resolve().parent
reader=runpy.run_path(str(root/'k1-ytv-reader-map.py'))['reader']
cases={
    'control':(['U','P8'],['X','Y','Z','T']),
    'T':(['P7','P8'],['X','Y','Z','T']),
    'Q':(['X1','V'],['P8','P9','P10','marker']),
}
for origin,(reads,push) in cases.items():
    result=reader(origin,0x0F,('Z','W'))
    assert result['reads']==reads and result['push']==push
    assert not set(result['reads']) & {'Q','T'}
print('PASS: no early q/v reserve in these accepted LastX prefixes; the visible paths displace T.',flush=True)
