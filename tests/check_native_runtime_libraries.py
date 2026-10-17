#!/usr/bin/env python3
"""Reject actual archive members; merely listing an empty archive is harmless."""
import argparse
from pathlib import Path
import re
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('map',type=Path)
p.add_argument('--without-libc',action='store_true')
p.add_argument('--app',action='store_true',help='APP uses the resident runtime table')
a=p.parse_args()
s=a.map.read_text();assert 'Linker script and memory map' in s
included=s.split('Discarded input sections',1)[0]
for library in ('libgcc', 'libm', 'libstdc++') + (('libc_nano','libc','libnosys') if a.without_libc or a.app else ()):
    assert not re.search(r'/'+re.escape(library)+r'\.a\(',included),('unexpected runtime archive member',library)
if not a.app:
    for symbol in ('__aeabi_ddiv','__aeabi_uldivmod'):
        assert symbol in s,('export missing',symbol)
    assert 'native_eabi_fixed.S.obj' in s and 'native_eabi.cpp.obj' in s
print('Native runtime archive gate: no libgcc/libm/libstdc++'+('/libc/libnosys' if a.without_libc or a.app else '')+' members PASS')
