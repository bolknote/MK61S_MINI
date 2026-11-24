"""Seal the two pow probes and compare their on-board timing reports."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

from check_stm32_vectors import ElfImage
from compact_math_arm_self_test import MathMachine
from m0_pow_classic_self_test import PICO_MATH, POW
from native_eabi_m0_arm_self_test import Machine


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe_pairs(elf):
    name, = [n for n in elf.symbols if n.endswith('L5pairsE')]
    start, size = elf.symbols[name], elf.sizes[name]
    for _, offset, address, _, length, _, _, _ in elf.segments:
        if address <= start and start+size <= address+length:
            offset += start-address
            return elf.data[offset:offset+size]
    raise ValueError('input matrix outside probe ELF')


def prepare(args):
    from hil_packbits_firmware import firmware_info
    from tools.apps.packer.mk61_module_pack import bcj_transform, validate_relocations, zx0_decode
    classic = MathMachine(args.classic)
    if not classic.compact:
        raise ValueError('expected the Classic compact binary64 resident')
    pico = Machine(args.pico, rp2040=True, bootrom=args.bootrom)
    ram = Machine(args.ram, rp2040=True, bootrom=args.bootrom)
    matrix = probe_pairs(ram.elf)
    app_elf = ElfImage(args.app.with_suffix('.elf'))
    assert matrix == probe_pairs(app_elf)
    app = args.app.read_bytes()
    version, header, abi, kind, compression = struct.unpack_from('<HHHBB',app,8)
    assert app[:8] == b'MK61APP\0' and (version,header,abi,kind,compression) == (1,64,6,4,1)
    flags, base, length, size, memory, entry, packed, relocs, checksum, image_crc = struct.unpack_from('<10I',app,16)
    assert flags in (5,7) and base == 0x20000000 and len(app)-header == length
    assert struct.unpack_from('<I',app,60)[0] == zlib.crc32(app[:60]) and checksum == zlib.crc32(app[header:])
    payload = zx0_decode(app[header:header+packed],size)
    if flags & 2:
        payload = bcj_transform(payload,False)
    assert payload == app_elf.bytes_at(app_elf.named_sections['.module_image']) and zlib.crc32(payload) == image_crc
    assert memory == app_elf.symbols['__module_memory_end']-base and (app_elf.symbols['mk61_module_entry']&~1)-base == entry
    assert validate_relocations(app[header+packed:],payload,memory) == relocs
    loads = []
    for kind, _, va, pa, size, mem, flags, _ in ram.elf.segments:
        if kind == 1:
            assert 0x20000000 <= va == pa and size <= mem and va+mem <= 0x20042000
            loads.append(dict(start=va, bytes=size, memory=mem, flags=flags))
    entry, = struct.unpack_from('<I', ram.elf.data, 24)
    assert entry & 1 and any(s['flags']&1 and s['start'] <= entry-1 < s['start']+s['bytes'] for s in loads)
    rows = []
    for x,y in struct.iter_unpack('<QQ',matrix):
        expected, m4_ticks = classic.call(10,x,y,count=True)
        actual, _, m0_ticks = pico.call(PICO_MATH,10,x,c=y,count=True)
        local, _, candidate_ticks = ram.call(POW,x,y,count=True)
        portable, _, portable_ticks = ram.call('_ZN17classic_reference3powEdd',x,y,count=True)
        assert expected == actual == local == portable,tuple(map(hex,(x,y,expected,actual,local,portable)))
        rows.append(dict(x=f'{x:016x}',y=f'{y:016x}',bits=f'{expected:016x}',
                         pico_service_insns=m0_ticks,classic_service_insns=m4_ticks,
                         pico_ram_insns=candidate_ticks,portable_ram_insns=portable_ticks))
    footer = firmware_info(args.classic.with_suffix('.bin'))
    image = args.classic.with_suffix('.bin').read_bytes()
    classic_elf = ElfImage(args.classic)
    for kind, offset, _, pa, size, _, _, _ in classic_elf.segments:
        if kind == 1 and size:
            start = pa-0x08000000
            assert start >= 0 and image[start:start+size] == classic_elf.data[offset:offset+size]
    files = {k:dict(path=str(getattr(args,k).resolve()),sha256=sha(getattr(args,k)))
             for k in ('ram','pico','classic','app','bootrom')}
    return dict(files=files,classic_image=footer,classic_id='AEB505B6E0067623',
                pico_id='E6657CD423721C35',pico_entry=entry,pico_loads=loads,
                matrix_sha256=hashlib.sha256(matrix).hexdigest(),samples=128,rounds=7,rows=rows)


def compare(receipt, pico_log, classic_bin):
    rows = receipt['rows']
    count, samples, rounds = len(rows), receipt['samples'], receipt['rounds']
    lines = [s.strip() for s in pico_log.read_text().splitlines()]
    first = lines.index(f'POW1 {count} {samples} {rounds} 125000000')+1
    assert lines[first+count] == 'END POW1'
    raw = classic_bin.read_bytes()
    assert struct.unpack_from('<4I',raw) == (0x31574f50,count,samples,rounds)
    assert len(raw) == 16+16*count
    samples_us = []
    for i,row in enumerate(rows):
        idx, pb, pt, pc, rb, rt, rc = lines[first+i].split()
        mb, mt, mc = struct.unpack_from('<QII',raw,16+i*16)
        assert int(idx) == i and int(row['bits'],16) == mb == int(pb,16) == int(rb,16)
        ticks = [int(pt)-int(pc),int(rt)-int(rc),mt-mc]
        if min(ticks) <= 0:
            raise ValueError(f'unresolved timer/control difference at row {i}')
        samples_us.append(dict(x=row['x'],y=row['y'],pico=ticks[0]/(125*samples),
                              portable=ticks[1]/(125*samples),classic=ticks[2]/(96*samples)))
    means = {k:sum(s[k] for s in samples_us)/count for k in ('pico','portable','classic')}
    passed = means['pico'] < min(means['portable'],means['classic'])
    return dict(passed=passed,equal_weight_mean_us=means,rows_us=samples_us)


def main():
    if not __debug__:
        raise SystemExit('run with Python assertions enabled')
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_subparsers(dest='mode',required=True)
    prep = modes.add_parser('prepare')
    for name in ('ram','classic','pico','app','bootrom','output'):
        prep.add_argument('--'+name,type=Path,required=True)
    check = modes.add_parser('check')
    for name in ('receipt','pico-log','classic-bin'):
        check.add_argument('--'+name,type=Path,required=True)
    args = p.parse_args()
    if args.mode == 'prepare':
        args.output.write_text(json.dumps(prepare(args),indent=2)+'\n')
    else:
        result = compare(json.loads(args.receipt.read_text()),args.pico_log,args.classic_bin)
        print(json.dumps(result,indent=2))
        return not result['passed']


if __name__ == '__main__':
    raise SystemExit(main())
