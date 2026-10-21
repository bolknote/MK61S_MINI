#!/usr/bin/env python3
"""Require comparison firmware to preserve production math addresses/bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from check_stm32_vectors import ElfImage


def symbol_types(image):
    result={}
    for section in image.sections:
        if section[1]!=2:continue
        names=image.bytes_at(image.sections[section[6]])
        for offset in range(section[4],section[4]+section[5],section[9]):
            name,_value,_size,info,_other,_index=struct.unpack_from('<IIIBBH',image.data,offset)
            result[image.string(names,name)]=info&15
    return result


def verify(production,comparison,required=()):
    production,comparison=Path(production),Path(comparison)
    before,after=ElfImage(production),ElfImage(comparison)
    before_types,after_types=symbol_types(before),symbol_types(after)
    def numerical(name):
        return (name.startswith(('mk61_m0_','__aeabi_','checked_trig_','atan_','asin_','ln_','log10_','exp_','pow_','r96_')) or
                'm0_eabi' in name or 'm0_pow_interval' in name or 'm0_pow_exact' in name or
                'compact_math' in name or re.match(r'_ZN\d+core_',name))
    names=sorted({n for n in before.symbols if before.sizes.get(n,0) and numerical(n)}|set(required))
    assert names,'No production math symbols'
    def contents(image,types,name):
        address=image.symbols[name]&~1 if types[name]==2 else image.symbols[name]
        size=image.sizes[name]
        for section in image.sections:
            if section[2]&2 and section[3]<=address and address+size<=section[3]+section[5]:
                return None if section[1]==8 else image.bytes_at(section)[address-section[3]:address-section[3]+size]
        raise AssertionError(('Math symbol outside allocated sections',name,hex(address),size))
    rows=[];digest=hashlib.sha256()
    for name in names:
        assert name in before.symbols and name in after.symbols,('Missing resident math symbol',name)
        assert (before.symbols[name],before.sizes[name],before_types[name])==(after.symbols[name],after.sizes[name],after_types[name]),('Math layout changed',name,hex(before.symbols[name]),hex(after.symbols[name]))
        original=contents(before,before_types,name);actual=contents(after,after_types,name)
        assert original==actual,('Math bytes changed',name)
        sha=hashlib.sha256(original).hexdigest() if original is not None else None
        rows.append(dict(symbol=name,address=before.symbols[name],size=before.sizes[name],sha256=sha))
        digest.update(name.encode()+b'\0'+struct.pack('<II',before.symbols[name],before.sizes[name])+(original or b''))
    return dict(status='PASS',production_elf=str(production.resolve()),comparison_elf=str(comparison.resolve()),
        production_elf_sha256=hashlib.sha256(production.read_bytes()).hexdigest(),
        comparison_elf_sha256=hashlib.sha256(comparison.read_bytes()).hexdigest(),
        checked_symbols=len(rows),checked_bytes=sum(r['size'] for r in rows),sha256=digest.hexdigest(),symbols=rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production',type=Path,required=True)
    parser.add_argument('--comparison',type=Path,required=True)
    parser.add_argument('--json',type=Path)
    args=parser.parse_args();result=verify(args.production,args.comparison)
    if args.json:args.json.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS:',result['checked_symbols'],'production math symbols have identical addresses and bytes')


if __name__=='__main__':main()
