#!/usr/bin/env python3
"""Prepare sin/cos-only diagnostic firmware and bounded timing APP; no USB."""
import argparse,collections,gzip,hashlib,json,math,shutil,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'tools')]
from build_picocalc import compiler_bin
from check_stm32_vectors import ElfImage
from check_m0_math_layout import verify,symbol_types
from m0_mpfr_oracle import Oracle,real
from m0_reference_image import join_reference

QFP_SHA='c9db54280a92c30e7c3b55adda24a8a540d33d52b7cba6185f9735c5efdd4654'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('production-elf','qfplib-source','profile','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--directory',default='MK61S-M0-TIMING-SINCOS-20261104')
    a=p.parse_args();assert sha(a.qfplib_source)==QFP_SHA
    assert a.directory.startswith('MK61S-M0-TIMING-') and all(c.isalnum() or c=='-' for c in a.directory)
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    raw=a.qfplib_source.read_text();assert raw.count('.thumb\n')==1
    qfp=out/'qfplib.S';qfp.write_text(raw.replace('.thumb\n','.thumb\n.section .m0_qfplib,"ax",%progbits\n'))
    adapter=out/'adapters.S';adapter.write_text('.syntax unified\n.thumb\n.section .m0_qfplib,"ax",%progbits\n')
    join_reference(out,a.production_elf,qfp,adapter)
    elf_path=out/'firmware/mk61s-picocalc-pico-h.elf';elf=ElfImage(elf_path)
    proof=verify(a.production_elf,elf_path,{'_ZN12compact_math3sinEd','_ZN12compact_math3cosEd'})
    (out/'layout-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    reference=Oracle();buckets=collections.OrderedDict();focus=[]
    profile_result=json.loads((a.profile/'RESULT.json').read_text())
    assert profile_result['status']=='PASS_FINITE_SINCOS_ARM_COMPARISON'
    with gzip.open(a.profile/'records.jsonl.gz','rt') as f:
        for line in f:
            r=json.loads(line);op=r['operation'];x=int(r['input'],16)
            assert op in ('sin','cos')
            if not math.isfinite(real(x)):continue
            expected=reference.reference(op,x);assert expected==int(r['expected'],16)
            good=r['values']['qfp']['correct'] and abs(real(x))<=1024
            key=(op,r['stream'],good);buckets.setdefault(key,[]).append((x,0,expected,r))
    groups=[]
    for (op,stream,good),values in buckets.items():
        groups.append(dict(operation=op,stream=stream+('/correct-reference' if good else '/diagnostic'),
            eligible=good,vectors=[v[:3] for v in values]))
        if good:
            selected={values[0][0]:values[0]}
            for role in ('base','next'):
                v=max(values,key=lambda v:v[3]['values'][role]['instructions']);selected[v[0]]=v
            focus.extend(dict(operation=op,stream=stream+'/focus/'+f'{v[0]:016X}',
                eligible=True,vectors=[v[:3]]) for v in selected.values())
    groups+=focus;chunks=[];inputs=out/'inputs';inputs.mkdir()
    for i,g in enumerate(groups):
        assert 0<len(g['vectors'])<=512
        op=g['operation'];own='_ZN12compact_math3'+op+'Ed';q='qfp_d'+op
        address=[elf.symbols[n]|1 for n in (own,q)];loops=max(1,2048//len(g['vectors']))
        blob=struct.pack('<8I',0x4D304246,1,i,1,len(g['vectors']),loops,*address)
        blob+=b''.join(struct.pack('<3Q',*v) for v in g['vectors']);f=inputs/f'{i:03d}.bin';f.write_bytes(blob)
        chunks.append(dict(index=i,stream_index=i,part=0,operation=op,stream=g['stream'],kind=1,
            cases=len(g['vectors']),loops=loops,input=str(f),input_sha256=sha(f),
            own_symbol=own,qfplib_symbol=q,own_address=address[0],qfplib_address=address[1],
            primary_reference_eligible=g['eligible'],reference_kind='direct_Qfplib',
            reference_domain='finite |x|<=1024 and exact MPFR answer' if g['eligible'] else 'diagnostic: wrong Qfplib answer or outside its documented domain'))
    fixture=out/'TIMING-fixture.c';shutil.copy2(ROOT/'tests/fixtures/m0_math_compare_benchmark.c',fixture)
    wrapper=out/'TIMING.c';wrapper.write_text('#define MK61_M0_TIMING_CACHE 1\n#define MK61_M0_TIMING_BOUNDED_WARMUP 1\n'+
        f'#define MK61_MATH_COMPARE_ROOT "/{a.directory}"\n#include "{fixture}"\n')
    argv=[sys.executable,'-B',str(ROOT/'tools/build_portable_app.py'),'--target','picocalc-pico-h',
          '--name','TIMING','--source',str(wrapper),'--shared-runtime',
          '--arm-toolchain-bin',str(compiler_bin(None)),'--output-dir',str(out/'app')]
    with (out/'app-build.log').open('x') as f:subprocess.run(argv,check=True,stdout=f,stderr=subprocess.STDOUT)
    app=out/'app/TIMING.APP';manifest=json.loads((out/'firmware/manifest.json').read_text())
    config=dict(status='BUILT_NOT_RUN',directory='/'+a.directory,firmware_manifest=manifest,
        elf_sha256=sha(elf_path),qfplib_source_sha256=QFP_SHA,app=str(app),app_sha256=sha(app),
        chunks=chunks,streams=len(chunks),cache_counters=True,fixture_sha256=sha(fixture),
        app_warmup_us=1000000,warmup_pairs_cap=32768,rounds=12,report_version=5,
        primary_estimator='order_balanced_median',production_link_preserved=True,
        layout_proof_sha256=sha(out/'layout-proof.json'),reference_bytes=elf.named_sections['.m0_qfplib'][5],
        reference_flash_address=0x10180000,source_profile_sha256=sha(a.profile/'RESULT.json'),
        role_input_bits_and_MPFR_references_frozen=True,pow_calls=0,hardware_IO=0,
        purpose='Temporary comparison only; correct references and diagnostics retained separately. No private state is in this bundle.')
    (out/'benchmark.json').write_text(json.dumps(config,indent=2)+'\n')
    print('BUILT_SINCOS_ONLY',len(chunks),'groups',sum(c['cases'] for c in chunks),'cases',app.stat().st_size,'APPbytes')


if __name__=='__main__':main()
