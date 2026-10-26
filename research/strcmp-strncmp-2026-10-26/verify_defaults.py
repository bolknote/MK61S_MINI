#!/usr/bin/env python3
"""Prove selected M4 defaults, unchanged M0 controls and qualified core byte identity."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from string_compare_arm_self_test import build,pin,command,EXPERIMENT
BASE='6e814dd7bb8b12c8700bbb9ad3817a20ceb8800e'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--toolchain-bin',type=Path,required=True)
    p.add_argument('--tested-core-dir',type=Path,help='Optional original build.json directory; defaults to checked-in qualified identities')
    p.add_argument('--final-core-dir',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();tc=a.toolchain_bin;a.output_dir.mkdir(parents=True,exist_ok=False)
    current=json.loads((a.final_core_dir/'build.json').read_text())['products'] if (a.final_core_dir/'build.json').exists() else build(tc,a.final_core_dir)
    old_manifest=a.tested_core_dir/'build.json' if a.tested_core_dir else ROOT/'research/strcmp-strncmp-2026-10-26/evidence/host-core-build.json'
    old=json.loads(old_manifest.read_text())['products'];equal=[]
    for product in current:
        before=next(x for x in old if (x['arch'],x['placement'])==(product['arch'],product['placement']))
        assert product['elf']['sha256']==before['elf']['sha256'],(product,before)
        equal.append(dict(arch=product['arch'],placement=product['placement'],tested=before['elf'],final_rebuilt=product['elf'],ELF_byte_equal=True))
    commands=[];proof=[]
    for arch,cpu in [('m4','cortex-m4'),('m0','cortex-m0plus')]:
      for source,symbols in [('code/system_strings.c',['strcmp','strncmp']),('sdk/portable/memory.c',['strcmp']),('ports/picocalc/memory.c',[])]:
        prefix=source.replace('/','-').replace('.','-');oldfile=a.output_dir/(prefix+'-before.c')
        oldfile.write_bytes((EXPERIMENT/source).read_bytes())
        blobs={}
        for label,path in [('before',oldfile),('after',ROOT/source)]:
          obj=a.output_dir/f'{arch}-{prefix}-{label}.o'
          command([tc/'arm-none-eabi-gcc','-mcpu='+cpu,'-mthumb','-mfloat-abi=soft','-Os','-fno-builtin','-fno-tree-loop-distribute-patterns','-ffunction-sections','-I'+str(EXPERIMENT/'code'),'-I'+str(ROOT/'code'),'-I'+str(ROOT/'sdk/portable'),'-DMK61_STRING_TEST_BUILD=1','-DPICO_ON_DEVICE=1','-c',path,'-o',obj],commands)
          names=command([tc/'arm-none-eabi-nm','--defined-only',obj],commands)
          if not symbols:assert not any(line.split()[-1] in ['strcmp','strncmp'] for line in names.splitlines())
          for symbol in symbols:
            binary=a.output_dir/f'{arch}-{prefix}-{label}-{symbol}.bin'
            command([tc/'arm-none-eabi-objcopy','-O','binary','--only-section=.text.'+symbol,obj,binary],commands)
            blobs[label,symbol]=pin(binary)
        for symbol in symbols:
          selected=arch=='m4' and symbol=='strcmp'
          if selected:assert blobs['after',symbol]['bytes']==20 and blobs['after',symbol]['sha256']=='13a952e2a2fe15d6063fab526a4300904fa25a335e889da5f037ecca9e1e1fbd'
          else:assert blobs['before',symbol]['sha256']==blobs['after',symbol]['sha256'],(arch,source,symbol)
          proof.append(dict(arch=arch,source=source,symbol=symbol,before=blobs['before',symbol],after=blobs['after',symbol],body_byte_equal=not selected,selected_M4_measured20B=selected))
    result=dict(status='PASS_M4_SELECTED20_M0_UNCHANGED_AND_CORE_ELFS_BYTE_IDENTICAL_TO_TESTED',physical_IO=0,source_base=BASE,core_ELF_equal=equal,default_body_equal=proof,Pico_default_emits_no_comparison_overrides=True,commands=commands,inputs=[pin(ROOT/n) for n in ['research/strcmp-strncmp-2026-10-26/fixture-root/code/string_compare_arm.h','code/system_strings.c','sdk/portable/memory.c','ports/picocalc/memory.c','tests/string_compare_arm_self_test.py','tests/string_compare_app_self_test.py','research/strcmp-strncmp-2026-10-26/verify_defaults.py']])
    (a.output_dir/'PROOF.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(proof=pin(a.output_dir/'PROOF.json'),identical_ELFs=len(equal),unchanged_default_bodies=sum(x["body_byte_equal"] for x in proof),selected_M4_bodies=sum(x["selected_M4_measured20B"] for x in proof))))
if __name__=='__main__':main()
