#!/usr/bin/env python3
"""Run the bounded comparator candidate on the Thumb-1 emulator."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess

from m0_pow_mixed_residue_self_test import CPP, MODES, RESEARCH, ROOT, aligned_powers, log_gap_is_below
from native_eabi_m0_arm_self_test import Machine, SP, signed


def arm(toolchain, host_report, output, only_widths=(), count_widths=()):
    report = json.loads(host_report.read_text())
    source_hash = sha256((RESEARCH/'mixed_residue.hpp').read_bytes()).hexdigest()
    assert report['source_sha256'] == source_hash
    fixture_hash = sha256(CPP.read_bytes()).hexdigest()
    assert report['fixture_sha256'] == fixture_hash
    output.mkdir(parents=True,exist_ok=True)
    elf = output/'mixed-arm.elf'
    subprocess.run([str(toolchain/'arm-none-eabi-g++'),'-mcpu=cortex-m0plus','-mthumb',
                    '-mfloat-abi=soft','-Os','-std=c++17','-ffreestanding','-fno-builtin',
                    '-fno-exceptions','-fno-rtti','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
                    '-ffunction-sections','-fdata-sections','-fstack-usage','-nostdlib',
                    '-I'+str(ROOT/'code'),'-I'+str(RESEARCH),str(CPP),'-lc','-lgcc',
                    '-Wl,-Ttext=0x08000000,-e,mixed_arm,--gc-sections,--undefined=existing_arm',
                    '-o',str(elf)], check=True)
    assert not subprocess.check_output([str(toolchain/'arm-none-eabi-nm'),'-u',str(elf)])
    machine = Machine(elf,True,stack_bytes=23808,instruction_budget=390_000_000)
    arg_addr = 0x20001000
    selected = set(only_widths) or {16000,49152,49153,73727,88415,88416}
    rows = []
    for row in report['cases']:
        w = row['required_width']
        if w not in selected:
            continue
        x,y,boundary = (int(row[k],16) for k in ('x','y','midpoint_lower'))
        gap = row['gap']
        a,b,k,n,_ = aligned_powers(x,y,boundary)
        assert n+2+k-gap == w and log_gap_is_below(a,b,k,gap)
        expected = (a>b)-(a<b)
        assert expected == row['expected']
        machine.uc.mem_write(arg_addr,struct.pack('<QQQI',x,y,boundary,gap))
        entries = [('mixed_arm',0,expected if w<=88415 else 0)]
        if w in (16000,49153,88416):
            entries.append(('existing_arm',0,expected if w<=49152 else 0))
        if w == 16000:
            entries.extend(('mixed_arm',m,expected) for m in MODES if m!=1)
        for fn,mode,want in entries:
            machine.stack_lowest = SP
            count = w in count_widths or w in (16000,88416) or (w==49153 and fn=='existing_arm')
            result,_,ninst = machine.call(fn,arg_addr,mode,width=32,count=count)
            result = signed(result&0xffffffff,32)
            assert result == want,(w,fn,mode,result,want)
            data = dict(required_width=w, comparator=fn, forced_mode=MODES.get(mode),
                        result=result, deepest_stack_write_bytes=SP-machine.stack_lowest,
                        instructions=ninst if count else None)
            rows.append(data)
            print(json.dumps(data),flush=True)
    assert rows and {r['required_width'] for r in rows} == selected
    return dict(status='PASS_ARM_CANDIDATE_NOT_WCET', elf_sha256=sha256(elf.read_bytes()).hexdigest(),
                source_sha256=source_hash, fixture_sha256=fixture_hash, instructions_are_not_cycles=True,
                maximum_observed_stack_write_bytes=max(row['deepest_stack_write_bytes'] for row in rows),
                cases=rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--toolchain',type=Path,required=True)
    p.add_argument('--host-report',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--report',type=Path)
    p.add_argument('--only-width',type=int,action='append',default=[])
    p.add_argument('--count-width',type=int,action='append',default=[])
    args = p.parse_args()
    result = arm(args.toolchain,args.host_report,args.output,args.only_width,args.count_width)
    with (args.report or args.output/'mixed-arm.json').open('x') as dest:
        json.dump(result,dest,indent=2)
        dest.write('\n')
    print(result['status'])


if __name__ == '__main__':
    main()
