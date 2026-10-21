#!/usr/bin/env python3
"""Build a private Qfplib-fork comparison without relinking resident firmware."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'tools')]
from build_picocalc import compiler_bin
from check_stm32_vectors import ElfImage
from check_m0_math_layout import verify,symbol_types
from m0_mpfr_oracle import Oracle,bits
from m0_reference_image import join_reference


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--restore',type=Path,required=True)
    p.add_argument('--qualified-build',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    restore=args.restore.resolve();qualified=args.qualified_build.resolve()
    control=json.loads((restore/'RESTORE.json').read_text())
    manifest=json.loads((restore/'manifest.json').read_text())
    assert control['hardware_verified'] and control['build_id']==manifest['build_id']
    assert sha(restore/'manifest.json')==control['manifest_sha256']
    assert sha(restore/'mk61s-picocalc-pico-h.uf2')==control['uf2_sha256']
    qualification=json.loads((qualified/'result.json').read_text())
    assert qualification['status']=='PASS_RESEARCH_GATES'
    assert qualification['elf_sha256']==sha(qualified/'checked.elf')
    assert qualification['build']['images']['checked']['variant'] in ('compensated_Q82_relative_near','compensated_Q82_relative_near64','compensated_Q82_relative_near66')
    fork=ROOT/'research/qfplib-m0-full'
    for name,digest in qualification['build']['images']['checked']['sources_sha256'].items():assert sha(fork/name)==digest,name
    snapshot=out/'fork';shutil.copytree(fork,snapshot)
    section='\n.section .m0_qfplib,"ax",%progbits\n'
    assembly=out/'fork.S'
    parts=[snapshot/'src/qfplib-m0-full_gcc.S',snapshot/'src/ln_comp_constants.inc',snapshot/'src/ln_comp96.inc']
    text='\n'.join(path.read_text() for path in parts)
    assert text.count('.thumb\n')==1
    assembly.write_text(text.replace('.thumb\n','.thumb\n'+section))
    upstream=(snapshot/'upstream/qfplib-m0-full_gcc.S').read_text()
    names=re.findall(r'^\.global\s+(\w+)\s*$',upstream,re.M)
    assert names and all(name.startswith('qfp_') for name in names)
    reference=out/'original.S'
    reference.write_text('\n'.join('#define '+name+' qfp_ref_'+name[4:] for name in names)+'\n'+upstream.replace('.thumb\n','.thumb\n'+section))
    c=out/'checked.c'
    c.write_text('#define QFP_COMPENSATED_LN 1\n#define QFP_NEAR_LN 1\n#include "'+str(snapshot/'src/ln_checked.c')+'"\n')
    join=join_reference(out,restore/'mk61s-picocalc-pico-h.elf',assembly,reference,c,
                        extra_flags=['-ffreestanding','-fno-builtin'],production_symbols=False)
    tc=compiler_bin(None)
    imports=subprocess.run([str(tc/'arm-none-eabi-nm'),'-u',str(out/'reference-link/checked.c.o')],check=True,capture_output=True,text=True).stdout
    imports=set(re.findall(r'\bU\s+(\S+)',imports))
    assert imports<={'qfp_dln','qfp_ln_comp96'},imports
    target=out/'firmware/mk61s-picocalc-pico-h.elf';elf=ElfImage(target)
    layout=verify(restore/'mk61s-picocalc-pico-h.elf',target)
    (out/'layout-proof.json').write_text(json.dumps(layout,indent=2)+'\n')
    refelf=out/'reference-link/reference.elf'
    shutil.copy2(refelf,out/'checked.elf');shutil.copy2(qualified/'original.elf',out/'original.elf')
    build=dict(status='PASS',images=dict(checked=dict(elf=str(out/'checked.elf'),elf_sha256=sha(out/'checked.elf'),variant=qualification['build']['images']['checked']['variant'],sources_sha256=qualification['build']['images']['checked']['sources_sha256'])),
               firmware_linked=False,scope='Private diagnostic reference separately linked; resident firmware link and initializers preserved. No public firmware changed.')
    (out/'build.json').write_text(json.dumps(build,indent=2)+'\n')
    rng=random.Random(0x514c4e)
    for _ in range(2500):rng.randrange(1,1<<52)
    one=bits(1.)
    groups={
      'normal_exponents':[(rng.randrange(1,2047)<<52)|rng.getrandbits(52) for _ in range(256)],
      'ordinary_half_to_two':[bits(rng.uniform(.5,2.)) for _ in range(256)],
      'near_one_tiny':[one+d for d in [-128,-17,-2,-1,0,1,2,17,128]],
      'near_one_outer':[bits(1+sign*2.**-i) for i in range(10,37) for sign in [-1,1]],
      'decimal_powers':[bits(10.**i) for i in range(-300,301,5)],
    }
    rng=random.Random(0x514e4541)
    groups['near_one_random']=[bits(1+rng.uniform(-2.**-12,2.**-12)) for _ in range(512)]
    inputs=out/'inputs';inputs.mkdir();chunks=[];oracle=Oracle()
    types=symbol_types(elf)
    own=elf.symbols['qfp_dln_checked']|1;old=elf.symbols['qfp_ref_dln']|1
    assert types['qfp_dln_checked']==types['qfp_ref_dln']==2
    for i,(name,values) in enumerate(groups.items()):
        loops=max(1,8192//len(values))
        header=struct.pack('<8I',0x4d304246,1,i,1,len(values),loops,own,old)
        raw=header+b''.join(struct.pack('<3Q',x,0,oracle.reference('ln',x)) for x in values)
        path=inputs/f'{i:03d}.bin';path.write_bytes(raw)
        chunks.append(dict(index=i,stream_index=i,part=0,operation='ln',stream=name,kind=1,cases=len(values),loops=loops,
                           input=str(path),input_sha256=sha(path),own_symbol='qfp_dln_checked',qfplib_symbol='qfp_ref_dln',own_address=own,qfplib_address=old))
    fixture=out/'TIMING-fixture.c';shutil.copy2(ROOT/'tests/fixtures/m0_math_compare_benchmark.c',fixture)
    directory='MK61S-M0-TIMING-QFP-LN-20261021'
    wrapper=out/'TIMING.c'
    wrapper.write_text('#define MK61_M0_TIMING_CACHE 1\n#define MK61_MATH_COMPARE_ROOT "/'+directory+'"\n#include "'+str(fixture)+'"\n')
    command=[sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target','picocalc-pico-h','--name','TIMING','--source',str(wrapper),
             '--shared-runtime','--arm-toolchain-bin',str(tc),'--output-dir',str(out/'app')]
    with (out/'app-build.log').open('w') as log:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
    manifest=json.loads((out/'firmware/manifest.json').read_text())
    result=dict(status='BUILT_NOT_RUN',directory='/'+directory,firmware_manifest=manifest,
        linked_image_bytes=manifest['flash_bytes'],elf_sha256=sha(target),app=str(out/'app/TIMING.APP'),app_sha256=sha(out/'app/TIMING.APP'),
        fixture_sha256=sha(fixture),chunks=chunks,streams=len(chunks),cache_counters=True,app_warmup_us=1000000,
        production_link_preserved=True,production_layout={k:v for k,v in layout.items() if k!='symbols'},layout_proof_sha256=sha(out/'layout-proof.json'),
        reference_bytes=join['reference_bytes'],reference_flash_address=join['reference_flash_address'],reference_sha256=join['reference_sha256'],
        source_snapshot_sha256={str(path.relative_to(snapshot)):sha(path) for path in sorted(snapshot.rglob('*')) if path.is_file()},
        self_contained_C_imports=sorted(imports),restore=str(restore),restore_uf2_sha256=control['uf2_sha256'],comparison_set='qfplib_ln_fork',
        purpose='Private evaluation; neither the default product math nor public firmware is replaced.',
        method=f'Pinned original Qfplib and checked fork both execute from the same isolated flash reference at0x10180000; all resident math addresses/bytes and RAM initializers retain accepted{manifest["prototype_version"]}/{manifest["build_id"]} layout. Identical vectors; nine alternating paired batches with typed calibration, TIMERAWL, interrupts enabled; at least1s paired warmup.8192calls/round approximately. XIP hit/access counters sampled outside timing.')
    (out/'benchmark.json').write_text(json.dumps(result,indent=2)+'\n')
    print('BUILT:',len(chunks),'ln streams; resident firmware layout preserved; reference',join['reference_bytes'],'bytes')


if __name__=='__main__':main()
