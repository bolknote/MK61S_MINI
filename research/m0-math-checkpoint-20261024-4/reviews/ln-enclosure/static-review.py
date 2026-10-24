"""Focused strict-ln radius proof and exact child source/object binding."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json,re,struct,subprocess,sys
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
W=ROOT/'.build/m0-ln-enclosure-20261024';P=ROOT/'.build/m0-log-ratio-dirty-20261024'
V=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def get(p):return json.loads(Path(p).read_text())
def put(n,o):
    with (OUT/n).open('x') as f:json.dump(o,f,indent=2);f.write('\n')
def allocated(e):return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8}
def nobits(e):return {n:s[5] for n,s in e.named_sections.items() if s[2]&2 and s[1]==8}
assert sha(ROOT/'.build/m0-log-ratio-dirty-independent-20261024/FINAL-REVIEW.json')=='45d06d0b57246951d97059355a53bc7c6543bdf2afd989686b70845ccca74f6b'
assert sha(W/'HANDOFF.md')=='75158b4a34feb2c2929c3f805c81b40938ec3079b8cf055db2360025200ed344'
assert sha(W/'result.json')=='9c40ecbe12d871cff65e65cf40672c0b9325314ec0828c797f7d19913a89ad02'
author=get(W/'result.json');pins=get(W/'input-pins.json')['files']
assert all(sha(W/n)==s for n,s in author['files'].items())
assert all(sha(ROOT/n)==s for n,s in pins.items())
for n in ('native_eabi_m0.cpp','native_eabi_m0_log70_center.inc','native_eabi_m0_log70_ratio.inc','native_eabi_m0_log10.inc','ratio.S'):
    assert (W/n).read_bytes()==(P/n).read_bytes()

# Rewind only the declared two-header radius/selector edits.
text=(W/'native_eabi_m0_log70.inc').read_text();old=(V/'native_eabi_m0_log70.inc').read_text()
prefix=text[:text.index('// A ten-bit segment')]
assert 'ln_main_radius=8U,ln_near_radius=4U' in prefix and 'ln_main_radius=16U,ln_near_radius=8U' in prefix
assert 'ln_near_lower=UINT64_C(0x3FEF808000000001)' in prefix
guard=text[text.index('#if defined(MK61_M0_RP2040_EABI)',len(prefix)):text.index('  const uint32_t lo=',len(prefix))]
assert 'const uint32_t guard=error-1;' in guard and 'const uint32_t guard=error;' in guard
rewind=text[len(prefix):].replace(guard,'  if(uint32_t(tail-(half-error))<=2*error) return ln_refine(x);\n',1)
for a,b in [('b>=ln_near_lower','b>=UINT64_C(0x3FEF800000000000)'),('negative?D::Sign:0,ln_near_radius,x','negative?D::Sign:0,8,x'),('low,high,0,ln_main_radius,x','low,high,0,16,x'),('k<0?D::Sign:0,ln_main_radius+(n+1)/2,x','k<0?D::Sign:0,16+(n+1)/2,x')]:
    assert rewind.count(a)==1;rewind=rewind.replace(a,b,1)
assert rewind==old
sub=(W/'native_eabi_m0_log_subnormal.inc').read_text()
rewind=sub.replace('  const uint32_t guard=error-1;\n  if(uint32_t(tail-(half-guard))<=2*guard) return mk61_m0_cr_ln(x);','  if(uint32_t(tail-(half-error))<=2*error) return mk61_m0_cr_ln(x);',1)
rewind=rewind.replace('D::Sign,ln_main_radius+(n+1)/2,x','D::Sign,16+(n+1)/2,x',1)
assert rewind==(V/'native_eabi_m0_log_subnormal.inc').read_text()

# Independently propagate the actual discarded products and rounding terms.
S=1<<70;half=F(1,2);h=F(1,2048);argument=F(1)
square=1+F(1,1<<16);cube=F(35,64)+h*square
third=half+cube/3
fourth=1+63*h*64+S*h**3/(1<<43)+h*cube
fifth=1+h*fourth+S*h**4/(1<<43)
c=F(52429,1<<18)
fifth_term=c*fifth+max(2*c+(c-F(1,5))*S*h**5,1-2*c)
remainder=S*h**6/(6*(1-h))
main=argument/(1-h)+half+(half+square/2)+third+(half+fourth/4)+fifth_term+remainder
nh=F(1,16000);na=F(17,32)+F(1,1<<22)+F(1,128)
nsquare=1+F(1,1<<18)
ncube=(half+nh*nsquare+(half*S*nh/(1<<26)+half*(S*nh**2+nsquare)/(1<<13)+F(1,4))/(1<<31))
nthird=half+ncube/3
nfourth=half+(2*S*nh**2*nsquare+nsquare**2)/S+((S*nh**2+nsquare)/(1<<13)+F(1,4))/(1<<44)
near=na/(1-nh)+half+(half+nsquare/2)+nthird+(half+nfourth/4)+S*nh**5/(5*(1-nh))
cert=get(W/'certificate.json')
assert main==F(cert['main_bound'])<8 and near==F(cert['near_bound'])<4
assert F(1,2049)+argument/S<h and F(1,16130)+na/S<nh
assert S*(F(1,2049)+argument/S)<1<<59
assert S*(F(1,2049)+argument/S)**2+square<1<<48

def nearest(q):
    n,r=divmod(q.numerator,q.denominator)
    return n+int(2*r>q.denominator or (2*r==q.denominator and n&1))
def log_interval(x):
    z=(x-1)/(x+1);p=z;v=F(0)
    assert 0<=z<1
    for k in range(80):v+=2*p/(2*k+1);p*=z*z
    return v,v+2*p/(161*(1-z*z))
ln2lo,ln2hi=log_interval(F(2))
ln2src=(V/'native_eabi_m0_log70_table.inc').read_text()
two=int(re.search(r'log70_two_low=UINT64_C\((\d+)\)',ln2src)[1])+(int(re.search(r'log70_two_high=(\d+)U',ln2src)[1])<<64)
assert F(two)-half<ln2lo*S<=ln2hi*S<F(two)+half
assert F(2,3)<ln2lo<ln2hi<F(7,10)
neartext=(V/'native_eabi_m0_log_table.inc').read_text().split('log_near_table[256][2]={',1)[1]
nearrows=re.findall(r'\{UINT64_C\((\d+)\),UINT64_C\((\d+)\)\}',neartext)
assert len(nearrows)==256
for i in (0,127,255):
    center=F(8065+i,8192);recip,value=map(int,nearrows[i])
    lo,hi=log_interval(center if center>=1 else 1/center)
    assert F(value)-half<lo*S<=hi*S<F(value)+half
    assert recip==nearest(F(1<<62)/center)

# Actual selector: a=(1-x)*2^62; n=floor((a+2^48)/2^49).
boundary=F(16129,16384)
assert int.from_bytes(struct.pack('<d',float(boundary)),'little')==0x3fef808000000000
assert ((1-boundary)*(1<<62)+(1<<48))/(1<<49)==128
for raw,expected in ((0x3fef808000000000,128),(0x3fef808000000001,127)):
    x=F(struct.unpack('<d',raw.to_bytes(8,'little'))[0])
    n=int(((1-x)*(1<<62)+(1<<48))/(1<<49))
    assert n==expected

# Binade safety of the discrete strict-radius guard, including lower dyadic
# boundaries where binary64 spacing halves. Only affected pack domains used.
near_min=F(1,16384)-F(1,2*16384**2)
assert near_min*S-2*near > 1<<55
assert (F(1,64)-F(1,2*64**2))*S-main > 1<<63
assert main+F(1,2)<9 and main+F(1023,2)<520
assert main+F(1074,2)<545
assert 1022*ln2lo>512 and 1074*ln2hi<1024

def round64(x):
    sign=0
    if x<0:sign=1<<63;x=-x
    if not x:return sign
    e=x.numerator.bit_length()-x.denominator.bit_length()
    if x < (F(1<<e) if e>=0 else F(1,1<<-e)):e-=1
    assert -1022<=e<=1023
    scaled=x*(1<<(52-e)) if e<=52 else x/F(1<<(e-52))
    q=nearest(scaled)
    if q==1<<53:q>>=1;e+=1
    return sign+((e+1023)<<52)+(q-(1<<52))
guard_checks=0;accepted=0
for e,radius,B in ((-15,4,near),(-14,4,near),(-13,4,near),(-7,8,main),(-6,9,main+half),(-1,520,main+F(1023,2)),(9,545,main+F(1074,2))):
    shift=e+18;quantum=1<<shift;mid=quantum>>1
    assert 3<=shift<=27 and 0<radius<=mid and B<radius
    minimum=near_min*S-near if e==-15 else F(0)
    qs={1<<52,(1<<52)+1,(1<<53)-2,(1<<53)-1}
    if e==-15:
        floorq=int(minimum)//quantum;qs.update((floorq,floorq+1))
    distances={0,1,radius-1,radius,radius+1,mid}
    for q in qs:
        for tail in {0,1,quantum-1}|{mid+s*d for d in distances for s in (-1,1) if 0<=mid+s*d<quantum}:
            M=q*quantum+tail
            if M<minimum:continue
            decline=((tail-(mid-(radius-1)))&0xffffffff)<=2*(radius-1)
            assert decline==(abs(tail-mid)<radius)
            guard_checks+=1
            if decline:continue
            for sign in (-1,1):
                assert round64(sign*F(M,S))==round64(sign*(F(M)-B)/S)==round64(sign*(F(M)+B)/S),(e,radius,q,tail)
                accepted+=1
put('STRICT-BOUND-AND-GUARD.json',dict(status='PASS_EXACT_STRICT_RADIUS_RNE_AND_SELECTOR',
 main_bound=str(main),near_bound=str(near),main_float=float(main),near_float=float(near),
 normal_radius='8+ceil(abs(k)/2); |k|<=1023',subnormal_radius='8+ceil(n/2);1023<=n<=1074',
 ln2_strict_half_unit_RNE_verified=True,selected_near_table_rows_verified=[0,127,255],
 guard_checks=guard_checks,accepted_signed_Fraction_RNE_endpoint_checks=accepted,
 exact_midpoint_always_declines=True,near_n128_boundary='x<=16129/16384 general; next binary64 and above near n<=127',
 lower_dyadic_edge='Near half4 is only reachable far above its lower2^-15 binade edge; all later near lower-half gaps>=4>3.685. Main |k|<=1 half>=1024 and radius<=9; |k|>=2 half>=65536 and radius<=520. Subnormal magnitude strictly512..1024, half2^26, radius<=545.',
 n0_relative_near_one_packer_unchanged=True,packing_shifts_in_affected_domains='3..27, positive radii, no zero or overwidth shift',
 polynomial_primitive_ratio_and_table_proofs_inherited=True))

# Whole source CPP, unchanged ratio assembly, entire diagnostic ELF binding.
build=get(W/'candidate-build.json');commands=[]
for index,name in ((0,'candidate-full.o'),(1,'candidate-ratio.o')):
    cmd=list(build['commands'][index]);cmd[cmd.index('-o')+1]=str(OUT/name)
    subprocess.run(cmd,check=True,capture_output=True);commands.append(cmd)
    assert sha(OUT/name)==sha(W/name)
cmd=list(build['commands'][2])
for name in ('candidate-full.o','candidate-ratio.o','candidate.elf'):cmd[cmd.index(str(W/name))]=str(OUT/name)
subprocess.run(cmd,check=True,capture_output=True);commands.append(cmd)
assert sha(OUT/'candidate.elf')==sha(W/'candidate.elf')=='36d1662268eaa35b5bd688fb7c2ff16958c1bc46dd92166dab5722e96b6f62f6'
assert sha(W/'control-full.o')==sha(P/'candidate-full.o') and sha(W/'control.elf')==sha(P/'candidate.elf')
old,new=ElfImage(W/'control-full.o'),ElfImage(OUT/'candidate-full.o');a,b=allocated(old),allocated(new)
assert set(a)==set(b) and nobits(old)==nobits(new)
changed={n:[len(a[n]),len(b[n])] for n in a if a[n]!=b[n]}
assert changed=={'.text.ln_near_interval':[912,912],'.m0_log_subnormal':[2464,2464],'.text.mk61_m0_ln':[1272,1272]}
def body(e,name,section_name=None):
    at=e.symbols[name]&~1;size=e.sizes[name]
    s=e.named_sections[section_name] if section_name else next(s for s in e.named_sections.values() if s[2]&2 and s[3]<=at and at+size<=s[3]+s[5])
    return e.bytes_at(s)[at-s[3]:at-s[3]+size]
assert body(old,'mk61_m0_log10_special','.m0_log_subnormal')==body(new,'mk61_m0_log10_special','.m0_log_subnormal')
assert sha(OUT/'candidate-ratio.o')==sha(P/'candidate-ratio.o')
nm=Path(build['commands'][0][0]).with_name('arm-none-eabi-nm')
undef=lambda p:subprocess.check_output([str(nm),'-u',str(p)],text=True).splitlines()
assert undef(W/'control-full.o')==undef(OUT/'candidate-full.o')
contexts={}
for context in ('generic_M0','M4_soft','M4_hard'):
    x,y=[ElfImage(W/(context+'-'+v+'.o')) for v in ('control','candidate')]
    assert allocated(x)==allocated(y) and nobits(x)==nobits(y)
    assert sha(W/(context+'-candidate.o'))==sha(P/(context+'-candidate.o'))
    contexts[context]=dict(exact=True,allocated_bytes=sum(map(len,allocated(x).values())))
x,y=ElfImage(W/'control.elf'),ElfImage(OUT/'candidate.elf')
assert allocated(x)['.rodata']==allocated(y)['.rodata'] and not nobits(y)
primitive=[]
for name in ('mk61_m0_log_ratio70','mk61_m0_log_ratio70_slow'):
    assert x.symbols[name]==y.symbols[name] and body(x,name)==body(y,name);primitive.append(name)
tab=next(n for n in y.symbols if 'log10_table' in n)
assert x.symbols[tab]==y.symbols[tab] and body(x,tab)==body(y,tab);primitive.append(tab)
assert build['resident_bindings']==get(P/'candidate-build.json')['resident_bindings']
assert all(not 0x101a0000<=(v&~1)<0x10200000 for v in build['resident_bindings'].values())
put('SOURCE-OBJECT-PROOF.json',dict(status='PASS_CHILD_SOURCE_ENTIRE_OBJECT_ELF_AND_PARENT_CLOSURE',
 source_sha256=sha(W/'native_eabi_m0_log70.inc'),subnormal_sha256=sha(W/'native_eabi_m0_log_subnormal.inc'),
 whole_object_sha256=sha(OUT/'candidate-full.o'),entire_ELF_sha256=sha(OUT/'candidate.elf'),no_excluded_bytes=True,
 changed_sections=changed,allocated_object_and_linked_delta=0,log10_special_unchanged=True,
 tables_RAM_undefined_deps_unchanged=True,primitive_addresses_and_bytes_unchanged=primitive,
 ratio_ASM_object_byteexact_parent=True,off_target_controls=contexts,M4_controls_only_M0_TU_not_whole_firmware=True,
 commands=commands,author_root_files=len(author['files']),input_pins=len(pins)))
print(json.dumps(dict(status='PASS_STATIC_BOUND_AND_BINDING',own_ELF=sha(OUT/'candidate.elf'),guard_checks=guard_checks,RNE_checks=accepted)))
