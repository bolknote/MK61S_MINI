#!/usr/bin/env python3
"""Reproduce the ARMv6-M/C++ CORE-MATH port from the pinned local snapshot.

No mathematical coefficients or algorithms are changed: replace compiler-only
128-bit integers, adapt C aggregate/goto syntax to GNU C++, and isolate modules.
The generated files retain their upstream MIT notices.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
NAMES=('sin','cos','tan','atan','asin','acos','log','log10','exp','pow')

def adapt(name,filename,s):
    class FileName:
        name=filename
    p=FileName()
    s=re.sub(r'#if \(defined\(__clang__\).*?typedef unsigned _BitInt\(128\) u128;\n#else\ntypedef unsigned __int128 u128;\n#endif', 'typedef mk61_u128 u128;',s,flags=re.S)
    # C permits arbitrary designation order. GNU C++ requires declaration order.
    s=re.sub(r'\{\s*\.h\s*=\s*([^,{}]+),\s*\.l\s*=\s*([^{}]+?)\s*\}',r'{.l=\2, .h=\1}',s)
    s=re.sub(r'struct\s*\{\s*u128 r;\s*int64_t _ex;\s*uint64_t _sgn;\s*\};','u128 r;',s)
    if name in ('sin','cos','tan','pow'):
     s=re.sub(r'\.hi\s*=\s*([^,{}]+),\s*\.lo\s*=\s*([^,{}]+),',r'.lo=\2, .hi=\1,',s)
    s=s.replace('(k < 128) ? B >> k : 0','(k < 128) ? B >> k : u128(0)')
    if name=='pow':
     s=re.sub(r'(struct\s*\{\s*u128 rl;\s*u128 rh;.*?uint64_t _sgn;\s*\})\s*;',r'\1 pair;',s,flags=re.S)
     s=re.sub(r'(->|\.)(rl|rh)\b',r'\1pair.\2',s)
     s=re.sub(r'\.hh\s*=\s*([^,{}]+),\s*\.hl\s*=\s*([^,{}]+),\s*\.lh\s*=\s*([^,{}]+),\s*\.ll\s*=\s*([^,{}]+),',r'.ll=\4, .lh=\3, .hl=\2, .hh=\1,',s)
     s=s.replace('? bh >> (k - 128) : 0','? bh >> (k - 128) : u128(0)')
     s=s.replace('(k >= 128) ? 0 : bh >> k','(k >= 128) ? u128(0) : bh >> k')
     if p.name=='pow.h':
      s=s.replace('f64_u v = {.u = hi};','f64_u v; v.u = hi;')
      # The C goto leaves a scope in which v is only a temporary bit copy.
      s=s.replace('f64_u v; v.u = hi;','{ f64_u v; v.u = hi;').replace('ret = v.f;','ret = v.f; }')
     if p.name=='pow.c':
      s=s.replace('  uint64_t t = n << F;','  { uint64_t t = n << F;')
      s=s.replace('  pow2(r, G);\n\n end:', '  pow2(r, G); }\n\n end:')
    return s


def share_storage(name, filename, text):
    """Share identical types and read-only arrays; retain every coefficient."""
    if name in ('sin', 'cos', 'tan') and filename == name + '.c':
        pattern = r'#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__\ntypedef union \{.*?\n#endif'
        match = re.search(pattern, text, re.S)
        assert match and 'dint64_t;' in match.group(), name
        text = text[:match.start()] + 'using dint64_t = ::core_m0_shared::Trig;\n' + text[match.end():]
        if name in ('cos', 'tan'):
            for table in ('S', 'C'):
                text = share_array(text, table, 'core_sin')
    if name in ('log', 'log10') and filename == 'dint.h':
        pattern = r'typedef struct \{\n  uint64_t hi;\n  uint64_t lo;\n  int64_t ex;\n  uint64_t sgn;\n\} dint64_t;'
        assert len(re.findall(pattern, text)) == 1, name
        text = re.sub(pattern, 'using dint64_t = ::core_m0_shared::Log;', text)
        if name == 'log10':
            for table in ('_INVERSE_2', '_LOG_INV_2', 'P_2'):
                text = share_array(text, table, 'core_log')
    return text


def share_array(text, name, owner):
    pattern = r'static const dint64_t ' + re.escape(name) + r'\s*\[[^]]*\]\s*=\s*\{'
    matches = list(re.finditer(pattern, text))
    assert len(matches) == 1, name
    match = matches[0]
    end = text.index('\n};', match.end()) + len('\n};')
    return text[:match.start()] + f'static constexpr const auto &{name} = {owner}::{name};' + text[end:]


def shared_types(source):
    sin = adapt('sin', 'sin.c', (source / 'src/sin/sin.c').read_text())
    log = adapt('log', 'dint.h', (source / 'src/log/dint.h').read_text())
    trig_type = re.search(r'#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__\ntypedef union \{.*?\n#endif', sin, re.S).group()
    log_type = re.search(r'typedef struct \{\n  uint64_t hi;\n  uint64_t lo;\n  int64_t ex;\n  uint64_t sgn;\n\} dint64_t;', log).group()
    assert 'dint64_t;' in trig_type
    return ('// Identical CORE-MATH storage types in a neutral namespace avoid ADL\n'
            '// between separately included function implementations. No field changes.\n'
            'namespace core_m0_shared {\ntypedef mk61_u128 u128;\n' +
            trig_type.replace('dint64_t;', 'Trig;') + '\n' +
            log_type.replace('dint64_t;', 'Log;') + '\n' +
            'static_assert(sizeof(Trig)==32 && sizeof(Log)==32,"CORE-MATH constant layout");\n}\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True,help='core-math-binary64 checkout')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    dest=ROOT/'third_party/core_math'
    pin=json.loads((dest/'provenance.json').read_text())
    for filename,hashes in pin['files'].items():
        source=args.source/'src'/filename
        raw=source.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==hashes['upstream_sha256'],filename
        name=filename.split('/')[0]
        result=share_storage(name,source.name,adapt(name,source.name,raw.decode())).encode()
        assert hashlib.sha256(result).hexdigest()==hashes['ported_sha256'],filename
        target=dest/filename
        if args.check:
            assert target.read_bytes()==result,filename
        else:
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(result)
    types = shared_types(args.source).encode()
    assert hashlib.sha256(types).hexdigest() == pin['shared_types']['sha256']
    target = ROOT / pin['shared_types']['path']
    if args.check:
        assert target.read_bytes() == types
    else:
        target.write_bytes(types)
    print('PASS: pinned CORE-MATH port reproduced')

if __name__=='__main__':main()
