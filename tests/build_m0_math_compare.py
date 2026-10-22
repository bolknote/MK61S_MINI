#!/usr/bin/env python3
"""Build a private RP2040 comparison image and its small timing APP.

Does not access hardware. A full relink uses the supplied source snapshot.
Preserving the production link copies only reference-build metadata; the
identified production ELF supplies all owned code and RAM initializers.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tests')]
from build_picocalc import compiler_bin
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from native_eabi_m0_arm_self_test import bits,real
from check_m0_math_layout import verify as verify_layout, symbol_types

QFP_SHA='c9db54280a92c30e7c3b55adda24a8a540d33d52b7cba6185f9735c5efdd4654'
KINDS={'i2d':2,'ui2d':3,'l2d':4,'ul2d':5,'d2iz':6,'d2uiz':7,'d2lz':8,'d2ulz':9,'f2d':10,'d2f':11}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_snapshot(snapshot, destination, output, *, reference_only=False):
    snapshot, destination, output = (Path(p).resolve() for p in
                                     (snapshot, destination, output))
    if snapshot == destination or snapshot.is_relative_to(destination):
        raise ValueError('Snapshot destination must not contain the input snapshot')
    if reference_only:
        # The owned image is never relinked in this mode. Its source tree,
        # build caches and Git data are unnecessary for the reference link.
        target = destination / 'ports/picocalc/CMakeLists.txt'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snapshot / 'ports/picocalc/CMakeLists.txt', target)
        return

    def ignore(directory, names):
        return [name for name in names
                if name in {'.build', '.git', '__pycache__'} or
                (Path(directory) / name).resolve() == output]

    # output can be inside snapshot, as with the normal workspace/.build
    # layout. Exclude it before walking to prevent recursive self-copying.
    shutil.copytree(snapshot, destination, dirs_exist_ok=True, ignore=ignore)


def prepared_corpus(folder):
    """Reuse exact, hashed vectors across candidate layouts, never addresses."""
    config=json.loads((folder/'benchmark.json').read_text());groups={}
    for chunk in sorted(config['chunks'],key=lambda c:(c['stream_index'],c['part'])):
        path=Path(chunk['input']);assert sha(path)==chunk['input_sha256']
        data=path.read_bytes();header=struct.unpack_from('<8I',data)
        assert header[:6]==(0x4D304246,1,chunk['index'],chunk['kind'],chunk['cases'],chunk['loops'])
        assert len(data)==32+24*chunk['cases']
        key=chunk['stream_index']
        fields=('operation','stream','own_symbol','qfplib_symbol','kind')
        if key not in groups:
            groups[key]={k:chunk[k] for k in fields};groups[key]['vectors']=[]
        group=groups[key];assert all(group[k]==chunk[k] for k in fields)
        group['vectors'] += list(struct.iter_unpack('<3Q',data[32:]))
    return list(groups.values())

def corpus(folder,extra):
    groups=[];reference=Oracle()
    def unary(op,stream,cases):
        own='__aeabi_i2d' if op=='i2d' else f'_ZN12compact_math{len(op)}{op}Ed'
        qfp='qfp_int2double' if op=='i2d' else 'qfp_d'+op
        vectors=[]
        for row in cases:
            a=int(row['input'],16)
            expected=bits(float(a-(1<<32) if a>>31 else a)) if op=='i2d' else reference.reference(op,a)
            vectors.append((a,0,expected))
        groups.append(dict(operation=op,stream=stream,own_symbol=own,qfplib_symbol=qfp,kind=KINDS.get(op,1),vectors=vectors))
    for filename in ('final-production-trig-profile.json','final-production-sqrt-exp-profile.json'):
        p=json.loads((folder/filename).read_text());assert p['status']=='PASS'
        for g in p['groups']:
            if not g.get('qfplib_speed_comparison_eligible',True):continue
            unary(g['operation'],g.get('stream',g.get('name')),g['cases'])
    p=json.loads((folder/'final-remaining-profile.json').read_text());assert p['status']=='PASS'
    for g in p['groups']:
        if not g['same_operation_on_this_domain']:continue
        op=g['operation'];vectors=[]
        for row in g['cases']:
            a,b=int(row['a'],16),int(row['b'],16)
            expected=reference.reference(op,a) if op in ('ln','atan') else int(row['reference'],16)
            vectors.append((a,b,expected))
        groups.append(dict(operation=op,stream=g['stream'],own_symbol=g['own_symbol'],qfplib_symbol=g['qfplib_symbol'],
            kind=12 if op.startswith('dcmp') else KINDS.get(op,1),vectors=vectors))
    for path in extra:
        p=json.loads(path.read_text());assert p['status']=='PASS'
        for name,rows in p.get('groups',p.get('results',{}).get('OWN',{})).items():
            op=name.split('_')[0]
            if op not in ('dadd','dsub','dmul','ddiv'):continue
            if rows and 'pairs' not in rows[0]:rows=[dict(name='fixed_cases',pairs=rows)]
            for row in rows:
                vectors=[]
                for pair in row['pairs']:
                    a,b=int(pair['a'],16),int(pair['b'],16);x,y=real(a),real(b)
                    expected=bits(x+y if op=='dadd' else x-y if op=='dsub' else x*y if op=='dmul' else x/y)
                    vectors.append((a,b,expected))
                groups.append(dict(operation=op,stream=name+':'+row['name'],own_symbol='__aeabi_'+op,qfplib_symbol='qfp_'+op,kind=0,vectors=vectors))
    return groups,p['adapter_source'] if 'adapter_source' in p else json.loads((folder/'final-remaining-profile.json').read_text())['adapter_source']


def hard_pow_corpus(path):
    """Add source-pinned difficult inputs, rechecking every expected value."""
    report=json.loads(path.read_text())
    assert report['status']=='PASS_PROFILE' and report['owned_wrong_rounding']==0
    assert report['qfplib_source_sha256']==QFP_SHA
    oracle=Oracle();groups=[]
    expected_streams={'regular_exponents','near_one_large_exponents','moderate'}
    assert len(report['groups'])==3 and {g['stream'] for g in report['groups']}==expected_streams
    for group in report['groups']:
        vectors=[]
        for row in group['cases']:
            a,b=int(row['a'],16),int(row['b'],16)
            x,y=real(a),real(b)
            assert math.isfinite(x) and math.isfinite(y) and x>0 and x!=1 and y!=0
            if group['stream']=='near_one_large_exponents':
                assert abs(x-1)<=2.**-20 and 16<abs(y)<=2.**52
                assert abs(math.log(x)*y)<=512
            else:
                assert .01<=x<=100 and abs(y)<=16
            expected=oracle.reference('pow',a,b)
            assert expected==int(row['expected'],16),row
            vectors.append((a,b,expected))
        assert vectors
        groups.append(dict(operation='pow',stream='hard_pow_'+group['stream'],kind=0,
            own_symbol='_ZN12compact_math3powEdd',qfplib_symbol='qfp_composed_pow',vectors=vectors,
            target_calls_per_round=512,
            reference_kind='qfplib_composition',reference_formula='exp(mul(y, ln(x)))',
            reference_domain='positive normal base; bounded finite exponent/logarithm-product; saved hard pow inputs'))
    return groups


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--production-elf',type=Path,required=True,help='Verify that comparison linking preserves this production math layout.')
    p.add_argument('--corpus',type=Path,required=True)
    p.add_argument('--qfplib-source',type=Path,required=True)
    p.add_argument('--sdk',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--directory',default='MK61S-M0-TIMING-20261019')
    p.add_argument('--extra-profile',type=Path,action='append',default=[])
    p.add_argument('--cache-counters',action='store_true',help='Record RP2040 XIP hit/access counters outside timed intervals.')
    p.add_argument('--comparison-set',choices=('direct','composed','all'),default='direct',
                   help='Composed baselines explicitly combine Qfplib calls for asin/acos/log10/pow.')
    p.add_argument('--prepared-corpus',type=Path,help='Reuse exact hashed direct-comparison inputs from a prior benchmark build.')
    p.add_argument('--hard-pow-profile',type=Path,help='Append three source-pinned difficult pow streams and revalidate their MPFR results')
    p.add_argument('--preserve-production-link',action='store_true',
                   help='Link only the reference, then join it to the production ELF without changing its veneers or RAM initializer.')
    a=p.parse_args()
    if a.hard_pow_profile and a.comparison_set=='direct':
        p.error('--hard-pow-profile requires --comparison-set composed or all')
    assert a.directory.startswith('MK61S-M0-TIMING-') and all(c.isalnum() or c=='-' for c in a.directory)
    assert sha(a.qfplib_source)==QFP_SHA,'Use the pinned comparison source'
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    source=out/'source'
    copy_snapshot(a.snapshot,source,out,reference_only=a.preserve_production_link)
    if a.prepared_corpus:
        assert not a.extra_profile,'Prepared vectors already include their arithmetic profiles'
        groups=prepared_corpus(a.prepared_corpus)
        adapters=json.loads((a.corpus/'final-remaining-profile.json').read_text())['adapter_source']
    else:
        groups,adapters=corpus(a.corpus,a.extra_profile)
    composed=a.comparison_set in ('composed','all')
    if composed:
        from m0_qfplib_compositions import corpus as composed_corpus
        groups=(groups if a.comparison_set=='all' else [])+composed_corpus()
    if a.hard_pow_profile:
        hard_groups=hard_pow_corpus(a.hard_pow_profile)
        groups+=hard_groups
    # Keep the reference out of .text/.rodata so it cannot move the owned
    # tables or change their cache aliases compared with production.
    reference_section='.section .m0_qfplib,"ax",%progbits\n'
    qfp_path=source/'ports/picocalc/m0_timing_qfplib.S';original=a.qfplib_source.read_text()
    assert original.count('.thumb\n')==1 and not any(line.lstrip().startswith(('.text','.section','.data','.bss')) for line in original.splitlines())
    qfp_path.write_text(original.replace('.thumb\n','.thumb\n'+reference_section))
    assert adapters.count('.text\n')==1
    (source/'ports/picocalc/m0_timing_adapters.S').write_text(adapters.replace('.text\n',reference_section))
    layout=source/'ports/picocalc/m0_reference.ld'
    layout.write_text('SECTIONS {\n  .m0_qfplib 0x10180000 : { KEEP(*(.m0_qfplib)) __flash_binary_end = ABSOLUTE(.); } > FLASH\n}\nINSERT AFTER .flash_end;\n')
    cmake=source/'ports/picocalc/CMakeLists.txt';text=cmake.read_text()
    assert 'm0_timing_qfplib.S' not in text
    text+='\n# Private comparison image only.\ntarget_sources(mk61s-picocalc-pico-h PRIVATE m0_timing_qfplib.S m0_timing_adapters.S)\n'
    if composed:
        shutil.copy2(ROOT/'tests/fixtures/m0_qfplib_compositions.c',source/'ports/picocalc/m0_qfplib_compositions.c')
        text+='target_sources(mk61s-picocalc-pico-h PRIVATE m0_qfplib_compositions.c)\n'
        text+='set_source_files_properties(m0_qfplib_compositions.c PROPERTIES COMPILE_OPTIONS "-Os;-fno-lto;-fno-unwind-tables;-fno-asynchronous-unwind-tables")\n'
    names=sorted({g[k] for g in groups for k in ('own_symbol','qfplib_symbol')})
    text+='target_link_options(mk61s-picocalc-pico-h PRIVATE\n'+''.join(f'    "-Wl,-u,{name}"\n' for name in names)+')\n'
    text+='target_link_options(mk61s-picocalc-pico-h PRIVATE "-Wl,-T,${CMAKE_CURRENT_SOURCE_DIR}/m0_reference.ld")\n'
    cmake.write_text(text)
    command=[sys.executable,str(source/'tools/build_picocalc.py'),'--sdk',str(a.sdk.resolve()),
        '--build-path',str(out/'build'),'--output-dir',str(out/'firmware'),'--jobs','4']
    if a.preserve_production_link:
        from m0_reference_image import join_reference
        join_reference(out,a.production_elf,qfp_path,source/'ports/picocalc/m0_timing_adapters.S',
                       source/'ports/picocalc/m0_qfplib_compositions.c' if composed else None)
        from m0_reference_image_self_test import qualify as qualify_boot_guard
        qualify_boot_guard(out/'firmware/mk61s-picocalc-pico-h.elf',out/'firmware/manifest.json',out/'firmware-self-test.json')
    else:
        with (out/'firmware-build.log').open('w') as log:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
    elf_path=out/'firmware/mk61s-picocalc-pico-h.elf';elf=ElfImage(elf_path)
    manifest=json.loads((out/'firmware/manifest.json').read_text())
    linked_image_bytes=elf.symbols['__flash_binary_end']-0x10000000
    assert linked_image_bytes==manifest['flash_bytes']==manifest['firmware_integrity']['image_size'], 'Boot CRC extent must include the isolated reference'
    proof=verify_layout(a.production_elf,elf_path,{g['own_symbol'] for g in groups})
    (out/'layout-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    types=symbol_types(elf)
    sram_functions=[{k:r[k] for k in ('symbol','address','size','sha256')} for r in proof['symbols']
                    if types[r['symbol']]==2 and 0x20000000 <= r['address'] < 0x20042000]
    reference=elf.named_sections['.m0_qfplib']
    assert reference[3]==0x10180000 and reference[3]+reference[5]<=0x101FE000
    inputs=out/'inputs';inputs.mkdir(exist_ok=True);chunks=[]
    for stream,g in enumerate(groups):
        for part,start in enumerate(range(0,len(g['vectors']),512)):
            vectors=g['vectors'][start:start+512];index=len(chunks)
            target_calls=g.get('target_calls_per_round',2048)
            loops=max(1,target_calls//len(vectors))
            own,qfp=(elf.symbols[g[k]]|1 for k in ('own_symbol','qfplib_symbol'))
            assert 0x10000000<qfp<0x10200000
            assert 0x10000000<own<0x10200000 or 0x20000000<own<0x20042000
            assert types[g['own_symbol']]==2 and types[g['qfplib_symbol']]==2
            header=struct.pack('<8I',0x4D304246,1,index,g['kind'],len(vectors),loops,own,qfp)
            blob=header+b''.join(struct.pack('<3Q',*v) for v in vectors)
            target=inputs/f'{index:03d}.bin';target.write_bytes(blob)
            chunks.append(dict(index=index,stream_index=stream,part=part,operation=g['operation'],stream=g['stream'],
                kind=g['kind'],cases=len(vectors),loops=loops,input=str(target),input_sha256=sha(target),
                own_symbol=g['own_symbol'],qfplib_symbol=g['qfplib_symbol'],own_address=own,qfplib_address=qfp))
            chunks[-1].update({k:g[k] for k in ('reference_kind','reference_formula','reference_domain') if k in g})
            if 'target_calls_per_round' in g:chunks[-1]['target_calls_per_round']=target_calls
    fixture=out/'TIMING-fixture.c';shutil.copy2(ROOT/'tests/fixtures/m0_math_compare_benchmark.c',fixture)
    assert '#define ROUNDS 12U' in fixture.read_text(),'Update the wire/estimator contract when changing round count'
    wrapper=out/'TIMING.c';wrapper.write_text(('#define MK61_M0_TIMING_CACHE 1\n' if a.cache_counters else '')+
        f'#define MK61_MATH_COMPARE_ROOT "/{a.directory}"\n#include "{fixture}"\n')
    command=[sys.executable,str(ROOT/'tools/build_portable_app.py'),'--target','picocalc-pico-h','--name','TIMING',
        '--source',str(wrapper),'--shared-runtime','--arm-toolchain-bin',str(compiler_bin(None)),'--output-dir',str(out/'app')]
    with (out/'app-build.log').open('w') as log:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
    app=out/'app/TIMING.APP'
    report=dict(status='BUILT_NOT_RUN',directory='/'+a.directory,firmware_manifest=manifest,linked_image_bytes=linked_image_bytes,
        elf_sha256=sha(elf_path),qfplib_source_sha256=QFP_SHA,app=str(app),app_sha256=sha(app),chunks=chunks,
        streams=len(groups),cache_counters=a.cache_counters,fixture_sha256=sha(fixture),app_warmup_us=1000000,
        rounds=12,report_version=4 if a.cache_counters else 3,primary_estimator='order_balanced_median',
        production_link_preserved=a.preserve_production_link,
        production_layout={k:v for k,v in proof.items() if k!='symbols'},layout_proof_sha256=sha(out/'layout-proof.json'),
        owned_code_placement='flash_and_sram' if sram_functions else 'flash',owned_sram_functions=sram_functions,
        qfplib_linked_source_sha256=sha(qfp_path),reference_flash_address=reference[3],reference_bytes=reference[5],
        reference_section_sha256=hashlib.sha256(elf.bytes_at(reference)).hexdigest(),
        cache_counter_reset_order='accesses_before_hits' if a.cache_counters else None,
        method='Owned code retains its production flash/SRAM placement; Qfplib executes from flash. Identical input order, twelve calibrated rounds with six first runs per library, TIMERAWL, typed soft-float calls and matching calibration leaves. The primary estimator is the median of six opposite-order pair averages. Interrupts enabled.'+
            (' XIP hit/access counters sampled outside timing; include both cores, with paired control counts recorded.' if a.cache_counters else '')+
            ' Owned math addresses and bytes match production; Qfplib is isolated at 0x10180000. Both libraries warm up inside the APP for at least 1000000 us before timing.',
        purpose='Private hardware comparison. Qfplib is included only in this diagnostic image; the production image does not link it.')
    report['comparison_set']=a.comparison_set
    if a.hard_pow_profile:
        report['hard_pow_profile']=dict(path=str(a.hard_pow_profile.resolve()),sha256=sha(a.hard_pow_profile),
            streams=len(hard_groups),cases=sum(len(g['vectors']) for g in hard_groups),
            scope='Exact encodings from the additional difficult pow profile; every expected result independently revalidated with directed MPFR bounds.')
    if a.prepared_corpus:
        report['prepared_corpus']=dict(path=str(a.prepared_corpus.resolve()),
            benchmark_sha256=sha(a.prepared_corpus/'benchmark.json'),scope='Exact input/result bits reused; function addresses resolved from the newly linked image.')
    if composed:
        report['composition_source_sha256']=sha(source/'ports/picocalc/m0_qfplib_compositions.c')
        report['composition_scope']='Explicit Qfplib compositions and algebraic shortcuts, not native Qfplib entry points. Results are independently checked against MPFR; each stream states its base/exponent domain.'
    (out/'benchmark.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Built',len(groups),'streams;',len(chunks),'chunks; APP',app.stat().st_size,'bytes',flush=True)

if __name__=='__main__':main()
