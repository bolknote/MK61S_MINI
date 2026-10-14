#!/usr/bin/env python3
"""Reject actual archive members; merely listing an empty archive is harmless."""
import argparse
from pathlib import Path
import re
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('map',type=Path)
p.add_argument('--without-libc',action='store_true')
a=p.parse_args()
s=a.map.read_text();assert 'Archive member included to satisfy reference' in s
included=s.split('Discarded input sections',1)[0]
for library in ('libgcc', 'libm', 'libstdc++') + (('libc_nano','libc','libnosys') if a.without_libc else ()):
    assert not re.search(r'/'+re.escape(library)+r'\.a\(',included),('unexpected runtime archive member',library)
for symbol in ('__aeabi_ddiv','__aeabi_uldivmod'):
    assert symbol in s,('export missing',symbol)
assert 'native_eabi_fixed.S.obj' in s and 'native_eabi.cpp.obj' in s
print('Native runtime archive gate: no libgcc/libm/libstdc++'+('/libc/libnosys' if a.without_libc else '')+' members PASS')
