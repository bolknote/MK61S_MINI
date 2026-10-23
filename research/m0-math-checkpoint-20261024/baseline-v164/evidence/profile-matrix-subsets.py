#!/usr/bin/env python3
"""Count actual ARM instructions over a prepared Qfplib comparison matrix."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

import sys
ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/'tests'))
from native_eabi_m0_arm_self_test import Machine, SP, nan


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark',type=Path,required=True)
    parser.add_argument('--elf',type=Path,help='Defaults to the diagnostic ELF recorded in benchmark.json')
    parser.add_argument('--owned-elf',type=Path,help='Execute owned symbols from a separate production ELF; Qfplib still uses the pinned diagnostic ELF')
    parser.add_argument('--bootrom',type=Path,help='Execute captured RP2040 ROM bit/memory code instead of intrinsic models')
    parser.add_argument('--baseline',type=Path,help='Compare owned instruction counts with a previous matrix report')
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    config_path=args.benchmark/'benchmark.json'
    config=json.loads(config_path.read_text())
    elf=args.elf or args.benchmark/'firmware/mk61s-picocalc-pico-h.elf'
    assert sha(elf)==config['elf_sha256'],'Diagnostic ELF differs from benchmark'
    owned_elf=args.owned_elf or elf
    owned_sha=sha(owned_elf)
    reference=Machine(elf,True,stack_bytes=16384,instruction_budget=20000000,bootrom=args.bootrom)
    owned=(Machine(owned_elf,True,stack_bytes=16384,instruction_budget=20000000,bootrom=args.bootrom)
           if args.owned_elf else reference)
    machines=dict(own=owned,qfplib=reference)
    rows=[]
    for chunk in config['chunks']:
        input_path=Path(chunk['input'])
        assert sha(input_path)==chunk['input_sha256'],input_path
        mask=(1<<(32 if chunk['kind'] in (6,7,11,12) else 64))-1
        sums=Counter()
        extrema={name:[None,0] for name in ('own','qfplib')}
        qfp_wrong=0
        eligible_cases=semantic_wrong=0;eligible_sums=Counter();eligible_slower=[]
        digest=hashlib.sha256()
        vectors=list(struct.iter_unpack('<3Q',input_path.read_bytes()[32:]))
        assert len(vectors)==chunk['cases']
        for a,b,expected in vectors:
            result={}
            for name in ('own','qfplib'):
                got,_,count=machines[name].call(chunk[name+'_symbol'],a,b,count=True)
                got&=mask
                result[name]=(got,count)
                sums[name]+=count
                bounds=extrema[name]
                bounds[0]=count if bounds[0] is None else min(bounds[0],count)
                bounds[1]=max(bounds[1],count)
            assert result['own'][0]==expected,(chunk['index'],hex(a),hex(b),result,hex(expected))
            qfp_wrong+=result['qfplib'][0]!=expected
            fp_output=not chunk['operation'].startswith('dcmp') and chunk['operation'] not in ('d2iz','d2uiz','d2lz','d2ulz')
            width=32 if chunk['operation']=='d2f' else 64
            quiet_bit=22 if width==32 else 51
            qbits=result['qfplib'][0]
            quiet_nan=(fp_output and nan(expected,width) and nan(qbits,width) and bool(qbits&(1<<quiet_bit)))
            same=quiet_nan or qbits==expected
            semantic_wrong+=not same
            if same:
                eligible_cases+=1
                for side in ('own','qfplib'):eligible_sums[side]+=result[side][1]
                if result['own'][1]>result['qfplib'][1]:
                    eligible_slower.append(dict(x=f'{a:016X}',y=f'{b:016X}',expected=f'{expected:016X}',
                        own_instructions=result['own'][1],qfplib_instructions=result['qfplib'][1]))
            digest.update(struct.pack('<8Q',a,b,expected,result['own'][0],result['qfplib'][0],
                                      result['own'][1],result['qfplib'][1],mask))
        row={key:chunk[key] for key in ('index','stream_index','part','operation','stream','cases')}
        row.update(mean_instructions={name:sums[name]/len(vectors) for name in ('own','qfplib')},
                   instruction_extrema=extrema,owned_wrong_rounding=0,
                   qfplib_wrong_results=qfp_wrong,result_sha256=digest.hexdigest())
        row.update(both_correct_cases=eligible_cases,both_correct_instruction_sums=dict(eligible_sums),
            both_correct_mean_instructions={name:eligible_sums[name]/eligible_cases if eligible_cases else None for name in ('own','qfplib')},
            both_correct_own_slower=len(eligible_slower),both_correct_slower_rows=eligible_slower,
            qfplib_semantic_wrong=semantic_wrong)
        rows.append(row)
        print(chunk['index'],chunk['operation'],chunk['stream'],row['mean_instructions'],flush=True)
    groups=[]
    for index in sorted({row['stream_index'] for row in rows}):
        parts=[row for row in rows if row['stream_index']==index]
        cases=sum(row['cases'] for row in parts)
        first=parts[0]
        mean={name:sum(row['mean_instructions'][name]*row['cases'] for row in parts)/cases
              for name in ('own','qfplib')}
        groups.append(dict(stream_index=index,operation=first['operation'],stream=first['stream'],cases=cases,
                           mean_instructions=mean,own_over_qfplib=mean['own']/mean['qfplib'],
                           owned_wrong_rounding=0,
                           qfplib_wrong_results=sum(row['qfplib_wrong_results'] for row in parts)))
    for group in groups:
        parts=[row for row in rows if row['stream_index']==group['stream_index']]
        count=sum(row['both_correct_cases'] for row in parts)
        totals={name:sum(row['both_correct_instruction_sums'].get(name,0) for row in parts) for name in ('own','qfplib')}
        group.update(both_correct_cases=count,both_correct_instruction_sums=totals,
            both_correct_mean_instructions={name:totals[name]/count if count else None for name in totals},
            both_correct_own_slower=sum(row['both_correct_own_slower'] for row in parts),
            qfplib_semantic_wrong=sum(row['qfplib_semantic_wrong'] for row in parts))
    assert sha(elf)==config['elf_sha256'],'ELF changed during profiling'
    assert sha(owned_elf)==owned_sha,'Owned ELF changed during profiling'
    result=dict(status='PASS',diagnostic_elf_sha256=sha(elf),benchmark_sha256=sha(config_path),
                owned_elf_sha256=owned_sha,sides_share_elf=owned_sha==sha(elf),
                qfplib_source_sha256=config['qfplib_source_sha256'],
                groups=groups,chunks=rows,cases=sum(row['cases'] for row in rows),owned_wrong_rounding=0,
                instruction_groups_faster=sum(row['mean_instructions']['own']<row['mean_instructions']['qfplib'] for row in groups),
                instruction_groups_equal=sum(row['mean_instructions']['own']==row['mean_instructions']['qfplib'] for row in groups),
                instruction_groups_slower=sum(row['mean_instructions']['own']>row['mean_instructions']['qfplib'] for row in groups),
                stack_bytes=16384,maximum_observed_stack_bytes=max(SP-m.stack_lowest for m in machines.values()),
                sdk_rom_intrinsic_models=owned.rom_models,
                actual_bootrom=(dict(sha256=owned.bootrom_sha256,initializers=owned.rom_initializers)
                                if owned.bootrom_sha256 else None),
                profiler_sha256=sha(__file__),machine_sha256=sha(ROOT/'tests/native_eabi_m0_arm_self_test.py'),
                scope='Executed ARM instructions on the prepared finite corpus, with typed 32-bit return masking. If sides_share_elf is false, owned production symbols and pinned diagnostic Qfplib symbols run on separate instances of the same Cortex-M0 emulator. When actual_bootrom is present, SDK ROM lookup initializers, wrappers and ROM bodies execute without intrinsic models. SIO division remains functionally modeled. These are not hardware cycles, cache comparisons, timings, or proof of speed parity.',
                physical_timing_available=False,goal_complete=False)
    result['subset_scope']='Both-correct eligibility uses exact finite bits and quiet-NaN semantics with payload/sign unspecified. Original strict-bit mismatch counts and raw means remain unchanged. Individual slower rows are retained per chunk.'
    result['both_correct_subset_mean_deficits']=[g for g in groups if g['both_correct_cases'] and g['both_correct_mean_instructions']['own']>g['both_correct_mean_instructions']['qfplib']]
    if args.baseline:
        prior=json.loads(args.baseline.read_text())
        previous={row['stream_index']:row for row in prior['groups']}
        assert set(previous)=={row['stream_index'] for row in groups},'Baseline matrix differs'
        result['baseline_sha256']=sha(args.baseline)
        result['instruction_changes']=[dict(stream_index=row['stream_index'],operation=row['operation'],stream=row['stream'],
            before=previous[row['stream_index']]['mean_instructions'],after=row['mean_instructions']) for row in groups
            if previous[row['stream_index']]['mean_instructions']!=row['mean_instructions']]
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS:',len(groups),'groups,',len(rows),'chunks,',result['cases'],'cases;',
          result['instruction_groups_faster'],'faster,',result['instruction_groups_equal'],'equal,',
          result['instruction_groups_slower'],'slower by instruction count; physical timing pending',flush=True)


if __name__=='__main__':
    main()
