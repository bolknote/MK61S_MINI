"""Independent bounded directional-ln proof and exact entire-ELF binding."""
from pathlib import Path
from fractions import Fraction as F
import ast,hashlib,json,re,struct,subprocess,sys
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
W=ROOT/'.build/m0-ln-near-directional-20261024';P=ROOT/'.build/m0-ln-enclosure-20261024'
V=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def get(p):return json.loads(Path(p).read_text())
def put(n,o):
    with (OUT/n).open('x') as f:json.dump(o,f,indent=2);f.write('\n')
def allocated(e):return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8}
def nobits(e):return {n:s[5] for n,s in e.named_sections.items() if s[2]&2 and s[1]==8}
assert sha(ROOT/'.build/m0-ln-enclosure-independent-20261024/FINAL-REVIEW.json')=='be4ab2a8053c3686e797d5dbd33d8808e421cc763d0c0dcf9ff26ce7239f0006'
assert sha(W/'HANDOFF.md')=='d707166ed58c073c8d5aecad5c80446b406c4d62b36d27134ac65298cd5102fe'
assert sha(W/'result.json')=='607c0e11a53050cb4e24aa9f3616fad32fd80dc5eca91eb8e8a47a82f871293e'
author=get(W/'result.json');pins=get(W/'input-pins.json')['files']
assert all(sha(W/n)==v for n,v in author['files'].items())
assert all(sha(ROOT/n)==v for n,v in pins.items())
for n in ('native_eabi_m0.cpp','native_eabi_m0_log10.inc','native_eabi_m0_log70_center.inc','native_eabi_m0_log70_ratio.inc','native_eabi_m0_log_subnormal.inc','ratio.S'):
    assert (W/n).read_bytes()==(P/n).read_bytes()
source=(W/'native_eabi_m0_log70.inc').read_text()
start=source.index('#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\n// The polynomial division remainders')
end=source.index('__attribute__((always_inline)) inline double ln_pack_relative',start)
rewind=source[:start]+source[end:]
decl='''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  int32_t bias12=0,residue=0;
  const uint32_t den=8064U+index;
#endif
'''
rem='''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
    const int32_t r2=-int32_t(z&1U);
    const int32_t r3=int32_t(cube)-3*int32_t(third);
    const int32_t r4=int32_t((fourth+2)&3U)-2;
    const int32_t even_bias=6*r2+3*r4;
    bias12=-4*r3+(subtract?-even_bias:even_bias);
    residue=int32_t((uint32_t(delta)<<21)-uint32_t(h)*den);
#endif
'''
ret='''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  return ln_near_round_pack(low,high,negative?D::Sign:0,bias12,residue,den,subtract==negative,!delta,x);
#else
  return ln_pack70(low,high,negative?D::Sign:0,ln_near_radius,x);
#endif'''
assert rewind.count(decl)==rewind.count(rem)==rewind.count(ret)==1
rewind=rewind.replace(decl,'').replace(rem,'').replace(ret,'  return ln_pack70(low,high,negative?D::Sign:0,ln_near_radius,x);')
assert rewind==(P/'native_eabi_m0_log70.inc').read_text()

# Reuse only independently accepted pure rational/RNE definitions.
accepted=ROOT/'.build/m0-ln-enclosure-independent-20261024/static-review.py'
tree=ast.parse(accepted.read_text());functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('nearest','log_interval','round64')]
math={'F':F};exec(compile(ast.Module(body=functions,type_ignores=[]),'<accepted-pure-Fraction-functions>','exec'),math)
nearest,log_interval=math['nearest'],math['log_interval']
S=1<<70;half=F(1,2);nh=F(1,16000)
argument=F(69,128)+F(1,1<<22)
nsquare=1+F(1,1<<18)
ncube=half+nh*nsquare+(half*S*nh/(1<<26)+half*(S*nh**2+nsquare)/(1<<13)+F(1,4))/(1<<31)
nfourth=half+(2*S*nh**2*nsquare+nsquare**2)/S+((S*nh**2+nsquare)/(1<<13)+F(1,4))/(1<<44)
derivative=argument*nh/(1-nh)
upper=derivative+half+nsquare/2+ncube/3+nfourth/4
lower=upper+S*nh**5/(5*(1-nh))
cert=get(W/'certificate.json')
assert upper==F(cert['upper'])<F(3,2) and lower==F(cert['lower'])<F(7,4)
assert argument==F(cert['quotient_error_bound'])==F(2260993,4194304)
# Product54: omitted a0*b0+(a0*b1+a1*b0)*2^16 <2^49+2^32.
# Divide by2^54, add half-up rounding: <17/32+2^-22.
# RNE reciprocal contributes at most(delta/2^55)<=1/128.
assert half+F((1<<49)+(1<<32),1<<54)+F(1,128)==argument
assert F(1,16130)+argument/S<nh
assert S*nh+argument<1<<57 and S*nh**2+nsquare<1<<43
assert S*nh**3+ncube<1<<29 and S*nh**4+nfourth<1<<15
assert F((1<<29)-1,3*(1<<33))+F(2,3)<1
max_residue=(argument*8320).__ceil__();max_gate=8320*(36+16)+12*max_residue
assert max_residue==4486 and max_gate==486472 and max_gate<1<<19

# All actual unchanged center/reciprocal bytes checked with independent
# rational log-series intervals, including c=1 and both outer endpoints.
image=ElfImage(W/'candidate.elf');tab=next(n for n in image.symbols if 'log_near_table' in n)
address=image.symbols[tab];size=image.sizes[tab]
s=next(s for s in image.named_sections.values() if s[2]&2 and s[3]<=address and address+size<=s[3]+s[5])
table=image.bytes_at(s)[address-s[3]:address-s[3]+size]
assert len(table)==4096
for i in range(256):
    reciprocal,value=struct.unpack_from('<QQ',table,16*i);c=F(8065+i,8192)
    assert reciprocal==nearest(F(1<<62)/c)
    lo,hi=log_interval(c if c>=1 else 1/c)
    assert F(value)-half<lo*S<=hi*S<F(value)+half

# Exact remainders and the two directional inequalities. Both correction
# directions and all extrema are included; no dependency on table payloads.
biases=set();remainder_checks=0
for z in range(8):
    r2=z-2*((z+1)//2);assert r2==-(z&1)
    for cube in range(12):
        q=(cube*0xaaaaaaab)>>33;third=q+(cube-3*q>=2)
        r3=cube-3*third;assert r3 in (-1,0,1)
        for fourth in range(8):
            r4=fourth-4*((fourth+2)//4);assert r4==((fourth+2)&3)-2
            for subtract in (False,True):
                sgn=1 if subtract else -1
                beta=-4*r3+( -(6*r2+3*r4) if subtract else 6*r2+3*r4)
                assert beta==-4*r3-sgn*(6*r2+3*r4)
                biases.add(beta);remainder_checks+=1
gate_checks=0
for den in (8065,8066,8127,8192,8193,8257,8319,8320):
    edge=(argument*den).__ceil__()-1
    for residue in (-edge,-1,0,1,edge):
        for beta in biases:
            B=F(beta,12)-F(residue,den)
            assert B+upper<4 and B-lower>-4
            for distance in (1,2,3):
                up=den*(12*distance-beta)+12*residue>=18*den
                down=den*(12*distance+beta)-12*residue>=21*den
                assert up==(distance-B>=F(3,2))
                assert down==(distance+B>=F(7,4))
                if up:assert B+upper<distance
                if down:assert B-lower>-distance
                gate_checks+=2
assert min(biases)==-16 and max(biases)==16
put('DIRECTIONAL-EXACT-PROOF.json',dict(status='PASS_FULL_H_ERROR_EXACT_REMAINDERS_AND_DIRECTIONAL_INTERVAL',
 full_h_bound=str(argument),full_h_bound_float=float(argument),upper=str(upper),lower=str(lower),
 upper_float=float(upper),lower_float=float(lower),all_existing_table_rows_verified=256,table_bytes=4096,
 table_sha256=hashlib.sha256(table).hexdigest(),remainder_checks=remainder_checks,gate_checks=gate_checks,
 max_abs_signed_residue_strictly_below=max_residue,max_abs_gate_strictly_below=max_gate,
 exact_error='h-H=-r/den. B=beta/12-r/den. Added correction q-true in[B-L,B+U]; subtracted in[-B-U,-B+L].',
 orientation='(tail>half)==add selects upper error constraint d-B>=3/2; other side selects d+B>=7/4. Strict U/L make threshold equality safe.',
 omitted_fifth_sign='Correction odd+even approximates -log(1-h); odd-even approximates log(1+h). Both omitted remainders are positive, enlarging only the lower error.',
 exact_center='Only table error<=1/2 remains; any nonzero integer midpoint distance safe. Distance0 always falls back.',
 far_distance_and_dyadics='Distance>=4 retains accepted symmetric parent bound. Near reachable half4 stays away from lower binade edge; later lower midpoint gap>=4. Signed magnitude reflection uses the unchanged RNE pack.',
 generic_M0_main_subnormal_and_ratio_proofs_inherited=True))

# Entire source-object-ELF binding, with no omitted bytes or symbol fixups.
build=get(W/'candidate-build.json');commands=[]
for i,name in ((0,'candidate-full.o'),(1,'candidate-ratio.o')):
    cmd=list(build['commands'][i]);cmd[cmd.index('-o')+1]=str(OUT/name)
    subprocess.run(cmd,check=True,capture_output=True);commands.append(cmd);assert sha(OUT/name)==sha(W/name)
cmd=list(build['commands'][2])
for name in ('candidate-full.o','candidate-ratio.o','candidate.elf'):cmd[cmd.index(str(W/name))]=str(OUT/name)
subprocess.run(cmd,check=True,capture_output=True);commands.append(cmd)
assert sha(OUT/'candidate.elf')==sha(W/'candidate.elf')=='272ecb817c396bd655cb19132f4df97c4d5d9da6046dc999a94a164de55e4425'
assert sha(W/'control-full.o')==sha(P/'candidate-full.o') and sha(W/'control.elf')==sha(P/'candidate.elf')
x,y=ElfImage(W/'control-full.o'),ElfImage(OUT/'candidate-full.o');a,b=allocated(x),allocated(y)
assert set(a)==set(b) and nobits(x)==nobits(y)
changed={n:[len(a[n]),len(b[n])] for n in a if a[n]!=b[n]}
assert changed=={'.text.ln_near_interval':[912,1160]}
assert sha(OUT/'candidate-ratio.o')==sha(P/'candidate-ratio.o')
nm=Path(build['commands'][0][0]).with_name('arm-none-eabi-nm')
undef=lambda p:subprocess.check_output([str(nm),'-u',str(p)],text=True).splitlines()
assert undef(W/'control-full.o')==undef(OUT/'candidate-full.o')
contexts={}
for c in ('generic_M0','M4_soft','M4_hard'):
    x,y=[ElfImage(W/(c+'-'+v+'.o')) for v in ('control','candidate')]
    assert allocated(x)==allocated(y) and nobits(x)==nobits(y) and sha(W/(c+'-candidate.o'))==sha(P/(c+'-candidate.o'))
    contexts[c]=dict(exact=True,allocated_bytes=sum(map(len,allocated(x).values())))
x,y=ElfImage(W/'control.elf'),ElfImage(OUT/'candidate.elf')
assert allocated(x)['.rodata']==allocated(y)['.rodata'] and not nobits(y)
assert build['resident_bindings']==get(P/'candidate-build.json')['resident_bindings']

# Exact bare inline wrapper: unchanged author fixture rebuilt from the
# actual final fragment and original clz helpers, independently byte-bound.
cpp=(W/'native_eabi_m0.cpp').read_text();hs=cpp.index('MK61_M0_TRIG_CACHE(clz32) unsigned clz32(');he=cpp.index('// Four 16x16 products',hs)
helpers=cpp[hs:he].replace('MK61_M0_TRIG_CACHE(clz32)','static').replace('MK61_M0_TRIG_CACHE(clz64)','static')
fs=source.index('__attribute__((always_inline)) inline double ln_near_round_pack(');fe=source.index('\n#endif',fs);fragment=source[fs:fe]
unit=(W/'pack-unit.cpp').read_text()
assert helpers in unit and fragment in unit and unit.count(fragment)==1
(OUT/'pack-unit.cpp').write_text(unit);(OUT/'pack-unit.ld').write_bytes((W/'pack-unit.ld').read_bytes())
ub=get(W/'pack-unit-build.json');uc=list(ub['commands'][0]);ul=list(ub['commands'][1])
uc[uc.index('-c')+1]=str(OUT/'pack-unit.cpp');uc[uc.index('-o')+1]=str(OUT/'pack-unit.o')
ul[ul.index('-T')+1]=str(OUT/'pack-unit.ld');ul[ul.index(str(W/'pack-unit.o'))]=str(OUT/'pack-unit.o');ul[ul.index('-o')+1]=str(OUT/'pack-unit.elf')
for c in (uc,ul):subprocess.run(c,check=True,capture_output=True);commands.append(c)
assert sha(OUT/'pack-unit.elf')==sha(W/'pack-unit.elf')=='b3f0b7a9f3a0b24314d9b7d1c6a8008e70a1507d0f74c1ce337daa9c8a554821'
put('SOURCE-OBJECT-PROOF.json',dict(status='PASS_FULL_PUBLIC_AND_EXACT_INLINE_UNIT_BINDING',
 whole_object_sha256=sha(OUT/'candidate-full.o'),entire_ELF_sha256=sha(OUT/'candidate.elf'),no_excluded_bytes=True,
 changed_sections=changed,allocated_code_growth_bytes=248,all_other_bodies_tables_global_RAM_deps_unchanged=True,
 ratio_ASM_byteexact_parent=True,existing_near_table_bytes_identical=True,off_target_controls=contexts,
 M4_controls_M0_TU_disabled_not_whole_firmware=True,bare_unit_ELF_sha256=sha(OUT/'pack-unit.elf'),
 bare_fragment_sha256=hashlib.sha256(fragment.encode()).hexdigest(),commands=commands,
 author_files=len(author['files']),input_pins=len(pins)))
print(json.dumps(dict(status='PASS_STATIC_DIRECTIONAL_PROOF_AND_BYTE_BINDING',gate_checks=gate_checks,ELF=sha(OUT/'candidate.elf'))))
