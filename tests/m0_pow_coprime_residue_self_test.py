#!/usr/bin/env python3
"""Check the coprime-modulus pow candidate against exact integers and ARMv6-M."""

import argparse
import ctypes as C
from hashlib import sha256
import json
from math import prod
from pathlib import Path
from random import Random
import struct
import subprocess
import sys

from m0_pow_mixed_residue_self_test import (BUDGET, GAP, INFINITY, ONE, RESEARCH,
                                            ROOT, Oracle, aligned_powers, bits,
                                            forced_case, log_gap_is_below, width_for)

sys.path.insert(0, str(RESEARCH))
from coprime_residue_table import MODULI, OFFSET_LIMIT, RADIX, emit, table

WIDTH = 32*MODULI-1
CPP = ROOT/'tests/fixtures/m0_pow_coprime_residue.cpp'


def work_bound():
    nk = GAP+WIDTH-2
    # On acceptance both aligned integers are below 2**(N+1).
    # A nontrivial odd factor is at least 3, so its exponent is <= N+1.
    exponent_bits = (nk+1).bit_length()
    power = 2*exponent_bits-1
    full_products = power+(exponent_bits-1)+(power+1)+1+1
    horner = MODULI*(MODULI-1)//2
    counts = [0,0]
    for k in range((nk//54).bit_length()):
        q_bits = 54 << k
        if k+q_bits > nk:
            break
        for inverse in range(2):
            max_p = (nk-k-inverse*q_bits)//53
            counts[inverse] += (max_p+1)//2 if k else max_p
    return dict(n_plus_k=nk, horner_steps=horner,
                modular_products_per_ring=full_products,
                all_bases_positive_exponents=counts[0],
                all_bases_negative_exponents=counts[1])


def build_args(output):
    return ['-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
            '-I'+str(ROOT/'code'), '-I'+str(RESEARCH), '-I'+str(output), str(CPP)]


def host(output, compiler):
    library = output/('residue.dylib' if sys.platform == 'darwin' else 'residue.so')
    subprocess.run([compiler, '-O3', '-fPIC', '-dynamiclib' if sys.platform == 'darwin' else '-shared',
                    *build_args(output), '-o', str(library)], check=True)
    lib = C.CDLL(str(library))
    u, U, word = C.c_uint32, C.c_uint64, C.POINTER(C.c_uint32)
    lib.residue_reduce.argtypes, lib.residue_reduce.restype = [U,u], u
    lib.residue_multiply_add_short.argtypes, lib.residue_multiply_add_short.restype = [u,u,u,u], u
    lib.residue_reconstruct.argtypes, lib.residue_reconstruct.restype = [word,u,word], C.c_int
    lib.residue_compare.argtypes, lib.residue_compare.restype = [U,U,U,u,word,u], C.c_int
    scratch = (u*(MODULI+2))()
    scratch[0], scratch[-1] = 0xe1ab3d9d, 0x9d3dabe1
    digits = C.cast(C.byref(scratch,C.sizeof(u)),word)

    rng = Random(0x97a615)
    offsets, _, _ = table()
    reductions = short_products = reconstructions = 0
    for offset in (1,5,65534,offsets[-1],OFFSET_LIMIT-1):
        modulus = RADIX-offset
        for value in (0,1,RADIX-2,RADIX-1,RADIX,(1<<64)-1,
                      *(rng.getrandbits(64) for _ in range(400))):
            assert lib.residue_reduce(value,offset) == value%modulus
            reductions += 1
        for x, weight, digit in ((RADIX-1,65535,RADIX-1),
                                 *((rng.getrandbits(32),rng.getrandbits(16),rng.getrandbits(32))
                                   for _ in range(400))):
            assert lib.residue_multiply_add_short(x,weight,digit,offset) == (x*weight+digit)%modulus
            short_products += 1
    for count in (1,2,5,17,256,MODULI):
        moduli = [RADIX-offset for offset in offsets[:count]]
        half = prod(moduli)//2
        values = (0,1,-1,half,half-1,-half,-half+1,
                  *(rng.randrange(-half,half+1) for _ in range(3)))
        for value in values:
            residues = (u*count)(*(value%m for m in moduli))
            assert lib.residue_reconstruct(residues,count,digits) == ((value>0)-(value<0))
            reconstructions += 1

    oracle = Oracle()

    def check(case, expected, width):
        want = expected or (1 if case[2]&1 else -1)
        assert lib.residue_compare(*case,digits,MODULI) == (want if width<=WIDTH else 0), case
        assert scratch[0] == 0xe1ab3d9d and scratch[-1] == 0x9d3dabe1

    checked = 0
    for _ in range(320):
        x = rng.randrange(ONE-(2<<52),ONE+(2<<52))
        y = bits(rng.choice((-1,1))*rng.randrange(1,220)/(1<<rng.randrange(7)))
        result = oracle.reference('pow',x,y)
        for lower in (result-1,result):
            if not 0<=lower<INFINITY:
                continue
            a,b,k,n,_ = aligned_powers(x,y,lower)
            if log_gap_is_below(a,b,k,38):
                exact = (a>b)-(a<b)
                check((x,y,lower,38),exact,width_for(a,b,k,n,38))
                assert (exact or (1 if lower&1 else -1)) == (1 if result>lower else -1)
                checked += 1
    for x,y,lower in ((2.,-1075.,0),(.5,1075.,0),(3.,34.,bits(float(3**34-1))),
                      (7.,19.,bits(float(7**19-1)))):
        case = bits(x),bits(y),lower,GAP
        a,b,k,n,_ = aligned_powers(*case[:3])
        assert a == b
        check(case,0,width_for(a,b,k,n,GAP))
        checked += 1
    cases = []
    for width, sign, q in ((88415,1,1),(88416,-1,128),(WIDTH,1,1),
                           (WIDTH,-1,256),(WIDTH+1,1,1)):
        case, expected = forced_case(width,sign,q,oracle)
        check(case,expected,width)
        cases.append((width,case,expected if width<=WIDTH else 0))
    assert C.sizeof(u)*MODULI == 2*BUDGET
    return dict(reductions=reductions, short_products=short_products,
                reconstructions=reconstructions, pow_boundaries=checked,
                forced_boundaries=len(cases), maximum_width=WIDTH,
                scratch_bytes=C.sizeof(u)*MODULI,
                table_bytes=(C.sizeof(u)+1)*MODULI), cases


def arm(output, toolchain, cases):
    from native_eabi_m0_arm_self_test import Machine, SP, signed
    from unicorn import UC_HOOK_BLOCK

    elf = output/'residue-arm.elf'
    subprocess.run([str(toolchain/'arm-none-eabi-g++'), '-mcpu=cortex-m0plus', '-mthumb',
                    '-mfloat-abi=soft', '-O3', '-ffreestanding', '-fno-builtin', '-fno-exceptions',
                    '-fno-rtti', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
                    '-ffunction-sections', '-fdata-sections', '-fstack-usage', '-nostdlib',
                    *build_args(output), '-lc', '-lgcc', '-Wl,-Ttext=0x08000000,-e,residue_arm,--gc-sections',
                    '-o', str(elf)], check=True)
    assert not subprocess.check_output([str(toolchain/'arm-none-eabi-nm'),'-u',str(elf)])
    machine = Machine(elf,True,stack_bytes=23808,instruction_budget=1_300_000_000)
    address = 0x20001000
    length_cache = {}
    rows = []
    for width, case, expected in cases:
        machine.stack_lowest = SP
        instructions = 0

        def block(uc, start, size, _):
            nonlocal instructions
            key = start,size
            if key not in length_cache:
                code = uc.mem_read(start,size)
                index, length = 0, 0
                while index < size:
                    halfword = code[index] | (code[index+1]<<8)
                    index += 4 if halfword&0xf800 >= 0xe800 else 2
                    length += 1
                assert index == size
                length_cache[key] = length
            instructions += length_cache[key]

        machine.uc.mem_write(address,struct.pack('<QQQI',*case))
        hook = machine.uc.hook_add(UC_HOOK_BLOCK,block)
        machine.uc.ctl_flush_tb()
        try:
            result = signed(machine.call('residue_arm',address,width=32)[0]&0xffffffff,32)
        finally:
            machine.uc.hook_del(hook)
        assert result == expected, (width,result,expected)
        if not expected:
            assert machine.call('residue_arm',address,width=32,count=True)[2] == instructions
        row = dict(width=width, x=f'{case[0]:016x}', y=f'{case[1]:016x}',
                   midpoint_lower=f'{case[2]:016x}', gap=case[3], side=result,
                   observed_instructions=instructions, stack_bytes=SP-machine.stack_lowest)
        print(json.dumps(row),flush=True)
        rows.append(row)
    return dict(elf_sha256=sha256(elf.read_bytes()).hexdigest(), cases=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cxx',default='c++')
    parser.add_argument('--arm-toolchain',type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    emit(output/'coprime_residue_table.inc')
    report, cases = host(output,args.cxx)
    report['work_bound_at_gap_16300'] = work_bound()
    print(json.dumps(report),flush=True)
    if args.arm_toolchain:
        report['arm'] = arm(output,args.arm_toolchain,cases)
    (output/'coprime-residue.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    main()
