#!/usr/bin/env python3
"""Qualify/profile the same C operand generator used by the RP2040 SRAM APP.

This executes ARM instructions through Unicorn. Instruction counts are not
RP2040 cycle measurements. Qfplib is supplied as a separate external ELF.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import struct
import subprocess
import sys
from native_eabi_m0_arm_self_test import Machine, SP, bits, real
from check_stm32_vectors import ElfImage
from hil_m0_eabi_benchmark import decode_muldiv_streams
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE

ROOT=Path(__file__).resolve().parents[1]


def trace_call(machine,symbol,a,b):
    counters={name:0 for name in ('instructions','taken_transfers','multiplies',
        'stack_reads','stack_writes','constant_reads','sio_reads','sio_writes')}
    following=[None]
    def code(uc,address,size,user):
        del user
        if following[0] is not None and address!=following[0]:counters['taken_transfers']+=1
        following[0]=address+size;counters['instructions']+=1
        if int.from_bytes(uc.mem_read(address,2),'little')&0xFFC0==0x4340:counters['multiplies']+=1
    def memory(uc,access,address,size,value,user):
        del uc,access,value
        if SP-4096<=address<SP:kind='stack'
        elif 0xD0000000<=address<0xD0001000:kind='sio'
        else:
            assert user=='reads' and 0x08000000<=address<0x10200000,(hex(address),user)
            kind='constant'
        counters[kind+'_'+user]+=size//4
    hooks=[machine.uc.hook_add(UC_HOOK_CODE,code),
        machine.uc.hook_add(UC_HOOK_MEM_READ,memory,'reads'),
        machine.uc.hook_add(UC_HOOK_MEM_WRITE,memory,'writes')]
    try:got,_,count=machine.call(symbol,a,b,count=True)
    finally:
        for hook in hooks:machine.uc.hook_del(hook)
    assert count==counters['instructions']
    counters['taken_transfers']+=1 # Final return reaches the emulator stop address.
    return got,counters


def generator(toolchain, runtime, directory, full):
    directory.mkdir(parents=True,exist_ok=True)
    source=ROOT/'tests/fixtures/m0_eabi_muldiv_benchmark.c'
    target=directory/'inputs.elf'
    subprocess.run([str(toolchain/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb',
        '-mfloat-abi=soft','-Os','-fno-builtin','-nostdlib','-DM0_BENCH_INPUTS_ONLY=1',
        '-DM0_BENCH_FULL_STREAMS='+str(int(full)),'-Wl,-Ttext=0x08100000',
        '-Wl,-e,m0_bench_pair','-Wl,--just-symbols='+str(runtime),str(source),'-o',str(target)],check=True)
    machine=Machine(runtime,True)
    image=ElfImage(target);image.load(machine.uc)
    for name in ('m0_bench_pair','m0_bench_seed'):machine.elf.symbols[name]=image.symbols[name]
    seed=machine.call('m0_bench_seed',0)[0]&0xFFFFFFFF
    state,output=SP-2048,SP-2112
    machine.uc.mem_write(state,struct.pack('<I',seed))
    raw=bytearray(struct.pack('<6I',0x30414C55,5 if full else 4,32,1024,9,12))
    for op in range(2):
        for kind in range(6):
            for i in range(32):
                selector=(op<<16)|(kind<<8)|i
                machine.call('m0_bench_pair',state|(selector<<32),output)
                a,b=struct.unpack('<2Q',machine.uc.mem_read(output,16))
                result=bits(real(a)*real(b) if op==0 else real(a)/real(b))
                raw.extend(struct.pack('<3Q',a,b,result))
            # Decode only the pair layout; these are placeholders, not timers.
            raw.extend(bytes(72))
    rows=decode_muldiv_streams(raw)
    for groups in rows.values():
        for group in groups:
            for key in ('us_per_call','raw_us','control_us'):group.pop(key)
    return rows,{'elf_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'integer_runtime_elf_sha256':hashlib.sha256(runtime.read_bytes()).hexdigest(),
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'seed':seed,
        'actual_arm_generator_calls':machine.calls,'writes':'Caller-provided state/output in the bounded test stack only.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owned-elf',type=Path,required=True)
    parser.add_argument('--generator-runtime-elf',type=Path,
        help='ELF with integer helpers for input generation; defaults to --owned-elf (firmware may remove unused helpers)')
    parser.add_argument('--baseline-elf',type=Path)
    parser.add_argument('--require-no-instruction-regression',action='store_true',
        help='Require OWN to execute no more instructions than BASE on every input; not a hardware timing check')
    parser.add_argument('--qfplib-elf',type=Path,required=True)
    parser.add_argument('--legacy-streams',action='store_true')
    parser.add_argument('--legacy-report',type=Path,help='Verify every legacy input/result against a previous acceptance report')
    parser.add_argument('--toolchain',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    if args.require_no_instruction_regression and not args.baseline_elf:
        parser.error('--require-no-instruction-regression requires --baseline-elf')
    assert not args.legacy_report or args.legacy_streams
    sys.path.insert(0,str(ROOT/'tools'));from build_picocalc import compiler_bin
    owned=args.owned_elf.resolve();full=not args.legacy_streams
    generator_runtime=(args.generator_runtime_elf or owned).resolve()
    rows,inputs=generator(compiler_bin(args.toolchain),generator_runtime,args.output_dir,full)
    if args.legacy_report:
        previous=json.loads(args.legacy_report.read_text())['additional_streams']['raw']['results']['OWN']
        for op,groups in rows.items():
            assert len(groups)==len(previous[op])
            for now,old in zip(groups,previous[op]):
                assert now['name']==old['name'] and now['pairs']==old['pairs'],(op,now['name'],'legacy operands or results changed')
    paths={'OWN':owned,'QFP':args.qfplib_elf.resolve()}
    if args.baseline_elf:paths['BASE']=args.baseline_elf.resolve()
    machines={name:Machine(path,True) for name,path in paths.items()}
    summary={}
    for key,groups in rows.items():
        op=key.split('_')[0];stats=[]
        for group in groups:
            traces={name:[] for name in paths}
            for pair in group['pairs']:
                a,b,expected=(int(pair[k],16) for k in ('a','b','result'))
                pair['trace']={}
                for name,machine in machines.items():
                    symbol=('qfp_' if name=='QFP' else '__aeabi_')+op
                    got,counters=trace_call(machine,symbol,a,b)
                    assert got==expected,(op,group['name'],name,pair,hex(got))
                    traces[name].append(counters);pair['trace'][name]=counters
                if args.require_no_instruction_regression:
                    now,baseline=(pair['trace'][name]['instructions'] for name in ('OWN','BASE'))
                    assert now<=baseline,(op,group['name'],pair['a'],pair['b'],
                        'instruction regression',now,baseline)
            stats.append({'name':group['name'],'trace':{name:{key:{
                'mean':statistics.mean(row[key] for row in values),
                'min':min(row[key] for row in values),'max':max(row[key] for row in values)}
                for key in values[0]} for name,values in traces.items()}})
            print(op,group['name'],{name:round(statistics.mean(row['instructions'] for row in values),3)
                for name,values in traces.items()},flush=True)
        summary[op]=stats
    report={'status':'PASS','mode':'full-53-bit-significands' if full else 'unchanged-legacy-streams',
        'input_generator':inputs,'cases_per_implementation':384,
        'elf_sha256':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in paths.items()},
        'legacy_inputs_and_results_unchanged':True if args.legacy_report else None,
        'no_instruction_regression_against_baseline':True if args.require_no_instruction_regression else None,
        'groups':rows,'summary':summary,
        'abi':'All generator and arithmetic calls verify R4-R11/SP preservation and bounded writes.',
        'timing_note':'Executed ARM instructions, taken transfers (including the final return), MULs and data words accessed. Not RP2040 cycles, microseconds, or evidence of a hardware speed ordering.'}
    args.json.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
