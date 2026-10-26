"""Only endpoint predicate equivalence and entire object/ELF binding."""
from pathlib import Path
from fractions import Fraction
import hashlib
import json
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
ROOT = D.parents[1]
W = ROOT/'.build/m0-ln-endpoint-predicate-20261024'
P = ROOT/'.build/m0-ln-near-directional-20261024'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
get = lambda p: json.loads(Path(p).read_text())


def put(name, obj):
    with (D/name).open('x') as file:
        json.dump(obj,file,indent=2)
        file.write('\n')


def pins():
    assert sha(W/'HANDOFF.md') == 'd0c613067eaf915a25f12f212e751e0a07527859bbe98e1afffeb240f1ccf956'
    assert sha(W/'result.json') == 'ed41028332a625ab5dfb38f2f9960d8d9e708168116c443757e46cf8f8e09592'
    result = get(W/'result.json')
    inputs = get(W/'input-pins.json')['files']
    for name,digest in result['files'].items():
        assert sha(W/name) == digest,name
    for name,digest in inputs.items():
        assert sha(ROOT/name) == digest,name
    parent = ROOT/'.build/m0-ln-near-directional-independent-20261024/FINAL-REVIEW.json'
    assert sha(parent) == '00d4c9ec7d311fdae72ea3b33523da148aaef6279fbb27fe771ce4dcc0b64ae9'
    return dict(artifacts=len(result['files']),inputs=len(inputs),parent_review_sha256=sha(parent))


def main():
    before = pins()
    old = (P/'native_eabi_m0_log70_center.inc').read_text()
    source = (W/'native_eabi_m0_log70_center.inc').read_text()
    old_test = 'if(delta>=(U(1)<<41)-1) {'
    new_test = 'if(uint32_t(delta>>32)==512U || (uint32_t(uint32_t(delta)+1U)==0U && uint32_t(delta>>32)==511U)) {'
    assert old.count(old_test) == source.count(new_test) == 1
    assert source.replace(new_test,old_test) == old
    for name in ('native_eabi_m0.cpp','native_eabi_m0_log70.inc','native_eabi_m0_log70_ratio.inc',
                 'native_eabi_m0_log10.inc','native_eabi_m0_log_subnormal.inc','ratio.S'):
        assert (W/name).read_bytes() == (P/name).read_bytes()
    main_source = (W/'native_eabi_m0_log70.inc').read_text()
    assert 'const unsigned index=unsigned((b&D::Fraction)>>42);' in main_source
    assert 'const U offset=b&((U(1)<<42)-1),half_segment=U(1)<<41;' in main_source
    assert 'const U delta=negative?half_segment-offset:offset-half_segment;' in main_source
    assert 'return mk61_m0_log_ratio70(delta,2049+2*index)+1;' in source
    # Full domain partitions, not random sampling as a mathematical substitute.
    # U is the accepted unsigned64 alias, uint32_t operations wrap by definition.
    mask=(1<<32)-1
    limit=1<<41
    symbolic=[]
    point_checks=0
    for high in range(513):
        maxlow=0 if high==512 else mask
        lo,hi=high<<32,(high<<32)+maxlow
        if high<511:
            assert hi<limit-1
            symbolic.append(dict(high=high,low_domain=[0,maxlow],selected='none',reason='both high tests false and full delta below threshold'))
        elif high==511:
            assert hi==limit-1 and lo<hi
            assert ((mask+1)&mask)==0 and (mask+1)==1<<32
            symbolic.append(dict(high=high,low_domain=[0,mask],selected='exactly low0xffffffff',reason='only unsigned increment wrap equals0'))
        else:
            assert lo==hi==limit
            symbolic.append(dict(high=high,low_domain=[0,0],selected='low0 only',reason='domain excludes every other low word'))
        for low in (0,1,2,0x7fffffff,0x80000000,0xfffffffd,0xfffffffe,mask):
            if low>maxlow:
                continue
            delta=(high<<32)|low
            new=(high==512 or (((low+1)&mask)==0 and high==511))
            assert new==(delta>=limit-1)
            point_checks+=1
    assert len(symbolic)==513
    # The endpoint condition is intentionally not a globally equivalent uint64 test.
    # Its public caller bound is therefore an essential inherited precondition.
    assert (1<<42)>=limit-1 and not ((1<<42)>>32==512 or (((1<<42)&mask)+1)&mask==0 and (1<<42)>>32==511)
    put('PREDICATE-DOMAIN-PROOF.json',dict(status='PASS_UNSIGNED_DOMAIN_ENDPOINT_EQUIVALENCE',
        highword_classes=len(symbolic),classes=symbolic,point_boundary_checks=point_checks,
        source_sha256=sha(W/'native_eabi_m0_log70_center.inc'),
        complete_old_header_reconstructed=True,
        domain='0<=delta<=2^41; index0..1023; oddden2049+2index in2049..4095',
        caller_bound='offset in[0,2^42-1]; small branch half-offset in[1,2^41], other branch offset-half in[0,2^41-1]. Both unsigned differences nonnegative.',
        unsigned_operations='U64 shift32 loses no relevant bits because high<=512; uint32_t low+1U is modular32 addition, with zero iff low==0xffffffff.',
        not_a_claim_outside_domain=True,reciprocal_seed_correction_rounding_unchanged=True))

    # One actual recompile/relink of only this private component.
    build=get(W/'candidate-build.json')
    cmds=[]
    for index,name in [(0,'candidate-full.o'),(1,'candidate-ratio.o')]:
        cmd=list(build['commands'][index]);cmd[cmd.index('-o')+1]=str(D/name)
        proc=subprocess.run(cmd,check=True,capture_output=True,text=True)
        assert sha(D/name)==sha(W/name)
        cmds.append(cmd)
    cmd=list(build['commands'][2])
    for name in ('candidate-full.o','candidate-ratio.o','candidate.elf'):
        cmd[cmd.index(str(W/name))]=str(D/name)
    subprocess.run(cmd,check=True,capture_output=True,text=True)
    cmds.append(cmd)
    assert sha(D/'candidate.elf')==sha(W/'candidate.elf')=='5187e1bbba29ec6b0d24cfc57aba9feb74598cc0b8df0df06fe6b13a53039e7e'
    assert sha(W/'control-full.o')==sha(P/'candidate-full.o')
    assert sha(W/'control.elf')==sha(P/'candidate.elf')
    sys.path.insert(0,str(ROOT/'tests'))
    from check_stm32_vectors import ElfImage
    x,y=ElfImage(W/'control-full.o'),ElfImage(D/'candidate-full.o')
    allocated=lambda e:{n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8}
    bss=lambda e:{n:(s[3],s[5]) for n,s in e.named_sections.items() if s[2]&2 and s[1]==8}
    a,b=allocated(x),allocated(y)
    assert set(a)==set(b) and bss(x)==bss(y)
    changes=[name for name in a if a[name]!=b[name]]
    assert changes==['.m0_pow_extension']
    name='mk61_m0_log_ratio70_slow'
    assert x.symbols[name]==y.symbols[name] and x.sizes[name]==y.sizes[name]==232
    target=y.symbols[name]&~1
    section=y.named_sections['.m0_pow_extension'];offset=target-section[3]
    old_bytes,new_bytes=a['.m0_pow_extension'],b['.m0_pow_extension']
    assert len(old_bytes)==len(new_bytes)==3800 and offset==848
    assert old_bytes[:offset]==new_bytes[:offset] and old_bytes[offset+232:]==new_bytes[offset+232:]
    assert len(old_bytes[:offset])+232+len(old_bytes[offset+232:])==len(old_bytes)
    n,c=ElfImage(W/'control.elf'),ElfImage(D/'candidate.elf')
    assert bss(n)==bss(c) and not bss(c)
    assert set(allocated(n))==set(allocated(c))
    assert n.symbols==c.symbols and n.sizes==c.sizes
    linked_target=c.symbols[name]&~1
    changed=0;outside=0;diff_bytes=0
    for sn,old_data in allocated(n).items():
        new_data=allocated(c)[sn];s0,s1=n.named_sections[sn],c.named_sections[sn]
        assert (s0[3],s0[5],s0[2])==(s1[3],s1[5],s1[2])
        assert len(old_data)==len(new_data)
        for at,(u,v) in enumerate(zip(old_data,new_data)):
            absolute=s0[3]+at
            if linked_target<=absolute<linked_target+232:
                changed+=1;diff_bytes+=(u!=v)
            else:
                assert u==v,(sn,hex(absolute));outside+=1
    assert changed==232 and diff_bytes>0
    assert sha(D/'candidate-ratio.o')==sha(P/'candidate-ratio.o')
    contexts={}
    for context in ('generic_M0','M4_soft','M4_hard'):
        p0,p1=[W/(context+'-'+v+'.o') for v in ('control','candidate')]
        assert p0.read_bytes()==p1.read_bytes()
        contexts[context]=dict(entire_object_equal=True,sha256=sha(p1))
    nm=Path(build['commands'][0][0]).with_name('arm-none-eabi-nm')
    undef=lambda obj:subprocess.check_output([str(nm),'-u',str(obj)],text=True).splitlines()
    assert undef(W/'control-full.o')==undef(D/'candidate-full.o')
    assert build['resident_bindings']==get(P/'candidate-build.json')['resident_bindings']
    # Only the existing source-bound product46 capsule is added to the bare helper.
    resident_path=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf'
    res=ElfImage(resident_path);pn='mk61_m0_log_product46';pa=res.symbols[pn]&~1;size=res.sizes[pn]
    sec=next(s for s in res.sections if s[2]&2 and s[1]!=8 and s[3]<=pa and pa+size<=s[3]+s[5])
    capsule=res.bytes_at(sec)[pa-sec[3]:pa-sec[3]+size]
    assert len(capsule)==184 and hashlib.sha256(capsule).hexdigest()=='75729579767fb4b3269141b6c62b1ae4fad49ed8817158b0e7d4bedcc717ecc8'
    (D/'product46-capsule.bin').write_bytes(capsule)
    after=pins();assert after==before
    put('SOURCE-WHOLE-ELF-PROOF.json',dict(status='PASS_ENDPOINT_ONLY_ENTIRE_SOURCE_OBJECT_ELF',
        input_pins=before,commands=cmds,entire_CPP_ASM_ELF_byteexact_no_exclusions=True,
        source_only_one_predicate=True,changed_object_section='.m0_pow_extension',
        shared_section_bytes=3800,helper_offset=848,helper_bytes=232,
        linked_helper_address=hex(linked_target),linked_changed_span_bytes=changed,actually_different_bytes=diff_bytes,
        every_other_allocated_byte_checked=outside,all_symbol_addresses_sizes_equal=True,
        all_literals_padding_and_other_function_bytes_equal=True,
        allocated_code_data_delta=0,new_BSS_tables_or_undefined_dependencies=False,
        ratio_ASM_exact=True,controls=contexts,
        retained_seed_capsule=dict(bytes=184,address=hex(pa),sha256=hashlib.sha256(capsule).hexdigest(),resident_ELF_sha256=sha(resident_path)),
        parent_near_proof_reused=True,hardware_access=False,canonical_or_source_modified=False))
    print('PASS static predicate',point_checks,'boundary points /513classes; entire ELF exact; outside helper bytes',outside)


if __name__=='__main__':
    main()
