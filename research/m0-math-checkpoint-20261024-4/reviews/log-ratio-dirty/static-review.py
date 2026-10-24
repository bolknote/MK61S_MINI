"""Independent, delta-only exact integer and source/object binding review."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib, json, re, struct, subprocess, sys
sys.dont_write_bytecode = True
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
W=ROOT/'.build/m0-log-ratio-dirty-20261024'
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def get(p):return json.loads(Path(p).read_text())
def put(name,value):
    with (OUT/name).open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def allocated(e):return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8}
def nobits(e):return {n:s[5] for n,s in e.named_sections.items() if s[2]&2 and s[1]==8}

assert sha(W/'HANDOFF.md')=='2d4be03240a2bc94b5e36c3a30505e951788d78d098c0b94d99533b2f0a5a677'
assert sha(W/'result.json')=='d76525b1cf50b407f9de8421a643b47a7e8503032cb23a3d6c9eb752bcd3fa3e'
result=get(W/'result.json');pins=get(W/'input-pins.json')['files']
assert all(sha(W/n)==v for n,v in result['files'].items())
assert all(sha(ROOT/n)==v for n,v in pins.items())
assert sha(W/'native_eabi_m0_log70_center.inc')=='9480f6ffa1abc80b502f35499b4d8b2fd1fdd42b3de0408af2feaadcd7be6d74'
assert sha(W/'native_eabi_m0_log70_ratio.inc')=='30fd45e3489f1f09a45388915c18e7f0c93015033187969509260316480b48ce'

# Reconstruct all four source changes, with unchanged callers/enclosures.
old=(P/'source/code/native_eabi_m0.cpp').read_text()
added='#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\n#define MK61_M0_LOG10_TABLE_INCLUDED 1\n#include "native_eabi_m0_log10_table.inc"\n#endif\n'
assert (W/'native_eabi_m0.cpp').read_text().replace(added,'',1)==old
oldlog=(P/'source/code/native_eabi_m0_log10.inc').read_text()
assert (W/'native_eabi_m0_log10.inc').read_text().replace('#ifndef MK61_M0_LOG10_TABLE_INCLUDED\n#include "native_eabi_m0_log10_table.inc"\n#endif','#include "native_eabi_m0_log10_table.inc"',1)==oldlog
oldcenter=(P/'source/code/native_eabi_m0_log70_center.inc').read_text();newcenter=(W/'native_eabi_m0_log70_center.inc').read_text()
assert oldcenter[oldcenter.index('\n#endif'):]==newcenter[newcenter.index('\n#endif'):]
oldratio=(P/'source/code/native_eabi_m0_log70_ratio.inc').read_text();newratio=(W/'native_eabi_m0_log70_ratio.inc').read_text()
oldtail='.Llog_ratio70_slow:\n ldr r3,=mk61_m0_log_ratio70_slow\n bx r3\n'
newtail='.Llog_ratio70_slow:\n movs r3,r0\n orrs r3,r1\n beq .Llog_ratio70_zero\n ldr r3,=mk61_m0_log_ratio70_slow\n bx r3\n.Llog_ratio70_zero:\n bx lr\n'
assert newratio.replace(newtail,oldtail,1)==oldratio

# Every seed and both dyadic endpoint identities checked as exact integers.
table=(P/'source/code/native_eabi_m0_log10_table.inc').read_text()
rows=[[int(x.rstrip('Uu'),0) for x in row.split(',') if x.strip()] for row in re.findall(r'\{([0-9Uu,\s]+)\}',table)]
assert len(rows)==1024 and all(len(r)==4 for r in rows)
S=1<<46;D=1<<41
# The product retains every term except a0*b0+(a0*b1+a1*b0)*2^16.
# Omitted magnitude is strictly below 2^49+2^32. Half-up rounding and
# bias4 make its signed error lie strictly above -4.5-2^-14 and <=4.5.
omitted_bound=F((1<<49)+(1<<32),S)
product_lower=F(7,2)-omitted_bound
product_upper=F(9,2)
assert product_lower==-F(73729,16384)
seed_lower=product_lower-2;seed_upper=product_upper
assert -seed_lower==F(106497,16384) and seed_lower>-7
assert (-seed_lower+1)*4095 < (1<<15)
checks=0;endpoint_checks=0;den_records=[]
for i,row in enumerate(rows):
    den=2049+2*i;R=(row[1]<<32)|(row[0]&~63)
    assert R==((1<<75)//den)&~63
    assert 0<=F(1<<75,den)-R<64 and R%(1<<46)!=0
    for delta in (D-1,D):
        q=(R>>5)-((R>>46)+1 if delta<D else 0)
        assert q==(delta*R)//S
        rem=(delta<<29)-q*den
        assert 0<=rem<3*den<(1<<15)
        assert q+(rem>=den)+(rem>=2*den)==(delta<<29)//den
        endpoint_checks+=1
    for quotient in range(8):
        for rem in (0,1,den-1):
            top=quotient*den+rem;n=top;q=0
            for bit in (4,2,1):
                carry=int(n>=den*bit)
                if carry:n-=den*bit
                q=2*q+carry
            assert q==top//den and n==top%den
            checks+=1
    den_records.append(dict(den=den,R=R))
put('INTEGER-PROOF.json',dict(status='PASS_EXACT_ALL_DENOMINATOR_SEEDS_ENDPOINTS_AND_CORRECTION',
 denominators=1024,endpoint_checks=endpoint_checks,three_bit_transition_checks=checks,
 domain='0<=delta<=2^41; den=2049+2*index, 0<=index<1024',
 product_error_interval=[str(product_lower),str(product_upper)],product_lower_strict=True,
 quotient_seed_error_interval=[str(seed_lower),str(seed_upper)],quotient_lower_strict=True,
 residual_bound=str(-seed_lower*4095),negative_ceiling_top_bound=str((-seed_lower+1)*4095),
 signed32_low_word_reconstruction_exact=True,correction_bits=3,
 explanation='Exact quotient is below2^60. Modulo2^32 subtraction recovers the unique signed residual since its magnitude and negative ceil numerator are <2^15. Three CMP/SUB/ADC steps divide by4den,2den,den. Negative residual uses ceil; endpoints use exact shifted seed and at most2increments. Busy-zero returns unchanged zero result words.',
 table_sha256=sha(P/'source/code/native_eabi_m0_log10_table.inc')))

# Compile only the reviewed TU and ratio assembly; link the entire fixture.
build=get(W/'candidate-build.json');commands=[]
for index,name in ((0,'candidate-full.o'),(1,'candidate-ratio.o')):
    cmd=list(build['commands'][index]);cmd[cmd.index('-o')+1]=str(OUT/name)
    subprocess.run(cmd,check=True,capture_output=True);commands.append(cmd)
    assert sha(OUT/name)==sha(W/name)
cmd=list(build['commands'][2])
for name in ('candidate-full.o','candidate-ratio.o','candidate.elf'):
    cmd[cmd.index(str(W/name))]=str(OUT/name)
subprocess.run(cmd,check=True,capture_output=True);commands.append(cmd)
assert sha(OUT/'candidate.elf')==sha(W/'candidate.elf')=='4e1a6b9151b96b5f9355e75c891c508809cad22d6c67fb9ef33354485acd5dff'
old,new=ElfImage(W/'control-full.o'),ElfImage(OUT/'candidate-full.o')
a,b=allocated(old),allocated(new)
assert set(a)==set(b) and nobits(old)==nobits(new)
changed={n:[len(a[n]),len(b[n])] for n in a if a[n]!=b[n]}
assert changed=={'.m0_pow_extension':[3644,3800]}
shared={}
for name in ('pow_rsqrt_boundary','pow_small_integer','pow_fast_log'):
    bodies=[]
    for image in (old,new):
        s=image.named_sections['.m0_pow_extension'];at=image.symbols[name]&~1
        bodies.append(image.bytes_at(s)[at-s[3]:at-s[3]+image.sizes[name]])
    assert bodies[0]==bodies[1];shared[name]=len(bodies[0])
nm=Path(build['commands'][0][0]).with_name('arm-none-eabi-nm')
undef=lambda p:subprocess.check_output([str(nm),'-u',str(p)],text=True).splitlines()
assert undef(W/'control-full.o')==undef(OUT/'candidate-full.o')
contexts={}
for label in ('generic_M0','M4_soft','M4_hard'):
    x,y=[ElfImage(W/(label+'-'+variant+'.o')) for variant in ('control','candidate')]
    assert allocated(x)==allocated(y) and nobits(x)==nobits(y)
    contexts[label]=dict(allocated_bytes=sum(map(len,allocated(x).values())),exact=True,
        scope='M0 TU disabled in M4; this does not represent a whole M4 firmware build' if label.startswith('M4') else 'Generic M0 TU with RP2040 macro absent')
oldasm,newasm=[allocated(ElfImage(W/(label+'-ratio.o'))) for label in ('control','candidate')]
assert sum(map(len,newasm.values()))-sum(map(len,oldasm.values()))==8
image=ElfImage(OUT/'candidate.elf');resident=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf')
assert sha(P/'firmware/mk61s-picocalc-pico-h.elf')==build['resident_ELF_sha256']
for name,address in build['resident_bindings'].items():
    actual=resident.symbols[name] if name in resident.symbols else resident.symbols['__wrap_'+name]
    assert address==actual and not 0x101a0000<=(address&~1)<0x10200000
assert 'mk61_m0_log_ratio70' not in build['resident_bindings']
assert 0x101a0000<=(image.symbols['mk61_m0_log_ratio70']&~1)<0x10200000
assert build['resident_bindings']['mk61_m0_log_product46']==resident.symbols['mk61_m0_log_product46']
assert allocated(image)['.rodata']==allocated(ElfImage(W/'control.elf'))['.rodata']
assert not nobits(image)

# Reassemble retained seed macros from pinned source, not hand-written code.
product_source=(P/'source/code/native_eabi_m0_product.inc').read_text()
fragments=[]
for name in ('product62_pair','product62_half1','product62_word2','product62_half2','log_product'):
    matches=re.findall(r'(?ms)^\.macro '+name+r'\b.*?^\.endm\s*$',product_source)
    assert len(matches)==1;fragments.append(matches[0])
unit=(W/'seed-kernel.S').read_text();prefix=unit[:unit.index('.macro product62_pair')]
assert prefix+'\n'.join(fragments)+'\nlog_product mk61_m0_log_product46,46,4\n'==unit
cmd=list(get(W/'seed-source-proof.json')['command']);cmd[cmd.index('-o')+1]=str(OUT/'seed-kernel.o')
subprocess.run(cmd,check=True,capture_output=True);commands.append(cmd)
seed=ElfImage(OUT/'seed-kernel.o');capsule=seed.bytes_at(seed.named_sections['.text.seed'])
address=resident.symbols['mk61_m0_log_product46']&~1;section=next(s for s in resident.named_sections.values() if s[3]<=address<s[3]+s[5])
assert len(capsule)==184 and capsule==resident.bytes_at(section)[address-section[3]:address-section[3]+184]
put('SOURCE-OBJECT-PROOF.json',dict(status='PASS_EXACT_CPP_ASM_WHOLE_ELF_AND_ISOLATION',
 whole_CPP_object_sha256=sha(OUT/'candidate-full.o'),ratio_object_sha256=sha(OUT/'candidate-ratio.o'),
 entire_ELF_sha256=sha(OUT/'candidate.elf'),no_excluded_bytes=True,source_delta_paths=4,
 changed_sections=changed,shared_other_bodies=shared,asm_growth_bytes=8,total_object_growth_bytes=164,
 linked_growth_bytes=sum(map(len,allocated(image).values()))-sum(map(len,allocated(ElfImage(W/'control.elf')).values())),
 tables_RAM_undefined_deps_unchanged=True,off_target_controls=contexts,
 resident_bindings_checked=len(build['resident_bindings']),seed_capsule_bytes=184,
 seed_capsule_sha256=hashlib.sha256(capsule).hexdigest(),commands=commands,
 author_root_files=len(result['files']),input_pins=len(pins),hardware_accessed=False))

# Account for sealed evidence; do not repeat its14907-input ARM corpus.
qualification=get(W/'qualification.json');rr=qualification['rows']
assert len(rr)==29814 and len({r['x'] for r in rr})==14907
assert all(r['correct']['candidate'] and r['outputs']['candidate']==r['outputs']['parent']==r['outputs']['resident'] for r in rr)
groups=[]
for state in ('READY','DIRTY'):
    rows=[r for r in rr if r['SIO']==state]
    changes=Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else 'equal' if r['instructions']['candidate']==r['instructions']['parent'] else 'slower' for r in rows)
    losses=[r for r in rows if r['correct']['Qfplib'] and r['instructions']['candidate']>r['instructions']['Qfplib']]
    before=sum(r['correct']['Qfplib'] and r['instructions']['parent']>r['instructions']['Qfplib'] for r in rows)
    groups.append(dict(SIO=state,vs_parent=dict(changes),losses=len(losses),parent_losses=before,Qfplib_wrong=sum(not r['correct']['Qfplib'] for r in rows)))
remaining=[r for r in rr if r['correct']['Qfplib'] and r['instructions']['candidate']>r['instructions']['Qfplib']]
assert remaining==get(W/'remaining-slower.json')['rows'] and len(remaining)==54 and len({r['x'] for r in remaining})==27
assert groups[0]['vs_parent']=={'equal':14907} and groups[1]['vs_parent']=={'faster':12893,'equal':2014}
assert [g['losses'] for g in groups]==[27,27] and [g['parent_losses'] for g in groups]==[27,8310]
historical={r['x'] for r in get(P/'slower-inputs.json')['rows'] if r['operation']=='ln'}
assert len(historical)==10 and historical<={r['x'] for r in remaining}
put('AUTHOR-ACCOUNTING.json',dict(status='PASS_HONEST_SEALED_CORPUS_ACCOUNTING_NOT_REPLAY',
 unique_inputs=14907,states=29814,groups=groups,remaining_inputs=27,remaining_state_rows=54,
 all_ten_historical_ln_losses_retained=True,DIRTY_correct_Qfplib_deficits_removed=8283,
 READY_unchanged=True,new_deficits=0,author_public_stack_bytes=488,author_helper_stack_bytes=68,
 no_exhaustive_binary64_performance_or_physical_cycles_claim=True))
print(json.dumps(dict(status='PASS_STATIC_BINDING_AND_INTEGER_PROOF',own_ELF_sha256=sha(OUT/'candidate.elf'),author_files=len(result['files']),input_pins=len(pins))))
