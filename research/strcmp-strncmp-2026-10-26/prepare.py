#!/usr/bin/env python3
"""Prepare target-independent benchmark inputs; never inspect a device."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from string_compare_arm_self_test import pin,command

def cases():
    result=[];seen=set()
    for op in ['strcmp','strncmp']:
      for n in [0,1,4,16,64,128,512]:
       for aa,ba in [(0,0),(1,1),(0,1),(1,0)]:
        modes=['equal','first','last','prefix_left'] if op=='strcmp' else ['equal','first','last','outside_n','nul_middle','prefix_left','unsigned_last']
        for mode in modes:
          a=bytes(1+i%255 for i in range(n));b=a
          if mode in ['first','last','unsigned_last']:
            if not n:continue
            at=0 if mode=='first' else n-1
            x=bytearray(a);y=bytearray(b)
            if mode=='unsigned_last':x[at]=255;y[at]=127
            else:y[at]=255 if x[at]!=255 else 1
            a=bytes(x);b=bytes(y)
          elif mode=='prefix_left':
            if not n:continue
            a=a[:n//2]
          elif mode=='nul_middle':a=a[:n//2];b=a
          elif mode=='outside_n':a+=b'A';b+=b'B'
          key=(op,n if op=='strncmp' else None,aa,ba,a,b)
          if key in seen:continue
          seen.add(key)
          expected=(a>b)-(a<b) if op=='strcmp' else (a[:n]>b[:n])-(a[:n]<b[:n])
          for bank in ['SRAM_SRAM','SRAM_FLASH','FLASH_FLASH']:
            result.append(dict(index=len(result),operation=op,n=n if op=='strncmp' else None,alignment=[aa,ba],mode=mode,banks=bank,left_hex=(a+b'\0').hex(),right_hex=(b+b'\0').hex(),left_bytes=len(a)+1,right_bytes=len(b)+1,expected_sign=expected))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--toolchain-bin',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=False);logs=[]
    exe=a.output_dir/'bench-self-test'
    command(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',HERE/'bench.c',HERE/'bench_self_test.c','-o',exe],logs)
    text=command([exe],logs);print(text,end='')
    objects=[]
    for arch,cpu in [('m4','cortex-m4'),('m0','cortex-m0plus')]:
        obj=a.output_dir/f'{arch}-bench.o'
        command([a.toolchain_bin/'arm-none-eabi-gcc','-mcpu='+cpu,'-mthumb','-mfloat-abi=soft','-Os','-fno-builtin','-fno-lto','-Wall','-Wextra','-Werror','-c',HERE/'bench.c','-o',obj],logs)
        dis=command([a.toolchain_bin/'arm-none-eabi-objdump','-d',obj],logs)
        (a.output_dir/f'{arch}-bench.dis').write_text(dis)
        assert '\tblx\t' in dis and 'cpsid' not in dis and 'cpsie' not in dis
        objects.append(dict(arch=arch,object=pin(obj),real_indirect_calls=True,IRQ_mask_instructions=False))
    matrix=cases();counts={op:sum(c['operation']==op for c in matrix) for op in ['strcmp','strncmp']}
    plan=dict(status='HOST_READY_TARGET_INDEPENDENT_NOT_A_HARDWARE_GRANT',physical_IO=0,hardware_winner=None,
        cases=matrix,case_counts=counts,rounds=7,raw_values_per_route=len(matrix)*7,
        candidate_ids=dict(byte1=1,byte4=2,word1=3,word2=4,dsp1=5,dsp2=6),
        candidates=dict(M4=['old_native','old_sdk','newlib','byte1','byte4','word1','word2','dsp1','dsp2'],M0=['actual_installed_newlib_to_be_bound','old_sdk','byte1','byte4','word1','word2']),
        code_placements=['resident Flash','resident SRAM on M0','standalone APP SRAM','shared APP veneer to actual runtime19'],
        operand_layout='64-byte guards; allocate aligned readable containing words beyond each NUL, fill padding 0xa5, preserve exact logical lengths separately; compare both inputs and all guards after each group',
        runtime=dict(count=26,strncmp_slot=19,strcmp='existing strncmp19 with SIZE_MAX; compare separately from local strcmp',resident_targets_must_match_actual_final_build=True,modeled_table_is_not_an_actual_firmware_integration_measurement=True),
        timing=dict(core='bench.c; caller supplies qualified uint32 tick provider',unit_and_frequency='must be recorded from actual installed target',IRQ='enabled; keep separate from old IRQ-masked campaigns',metric='whole repeated indirect-call loop, raw ticks; no empty subtraction',repeat_choice='M4/M0 per-case repeats must be frozen after target/timer qualification; 1..4096',primer='one checked call before each aggregate; hot context',selection='per architecture/function/code placement; preserve every group, short-string regressions, code/RAM budget, medians and paired uncertainty; never infer a speed winner from HOST'),
        required_before_hardware=['fresh OS/device identity and firmware/source binding after user connection','actual SYS_HZ/power mode and unique context flags/PATH','Root-approved exact candidate carrier/APP/timer/argv/lease','full original image plus actual files/cache/typed state/RTC snapshot before changes','one first-fault run, raw outputs and actual PID/session/EXIT/reap/FD/lock records','restore actual pre-window original and user state; independent Root CLOSED'],
        M0_outer_supplier='NativePico only, through coordinator; M0strlen keeps its earlier queue position',
        target_binding='UNBOUND: Classic absent from latest permitted OS inventory; Pico no hardware scope',
        source_pins=[pin(HERE/n) for n in ['bench.h','bench.c','bench_self_test.c','prepare.py']],bench_core_tests=dict(status='PASS',synthetic_ticks_only=True,commands=logs,ARM_objects=objects))
    (a.output_dir/'PLAN.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps(dict(plan=pin(a.output_dir/'PLAN.json'),cases=counts,physical_IO=0)))
if __name__=='__main__':main()
