"""Bounded independent directional/ninth atan review. No device APIs."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import ast, hashlib, importlib.util, json, re, struct, subprocess, sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
W=ROOT/'.build/m0-atan-directional-ninth-20261024'
P=ROOT/'.build/m0-atan-residual-geometry-20261024'
PRIOR=ROOT/'.build/m0-atan-geometry-independent-20261024'
S=1<<70;MASK=(1<<64)-1
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,m):
    if not v:raise AssertionError(m)
def read(p):return json.loads(Path(p).read_text())
def put(n,r):(HERE/n).write_text(json.dumps(r,indent=2)+'\n')
def pins():
    require(sha(W/'HANDOFF.md')=='3efc40adb8ef6f022eaf32ea4435a0e3bb8a945e6a0068c56db1c29e7cdb0a63','handoff changed')
    require(sha(W/'result.json')=='d87a220d5db188d03a5f4b7039da7cedae63957875ace0451cb47bee77e06f03','result changed')
    for n,h in read(W/'result.json')['files'].items():require(sha(W/n)==h,'author artifact changed '+n)
    for n,h in read(W/'input-pins.json')['files'].items():require(sha(ROOT/n)==h,'input changed '+n)
    require(sha(PRIOR/'FINAL-REVIEW.json')=='20f3a52335bf160c89b02bcf25262b4a5306e29cbbe0b61da94e284e8b6ba1fc','parent review changed')
    for n,h in read(PRIOR/'FINAL-REVIEW.json')['own_artifacts'].items():require(sha(PRIOR/n)==h,'parent evidence changed '+n)
    return dict(author_files=len(read(W/'result.json')['files']),input_files=len(read(W/'input-pins.json')['files']),parent_review_exact=True)
INITIAL=pins()
spec=importlib.util.spec_from_file_location('accepted_geometry_review',PRIOR/'review.py')
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
old=parent.old;ElfImage=old.ElfImage;Machine=old.Machine;SP=old.SP
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP
COMMANDS=[]
def run(args):
    args=list(map(str,args));COMMANDS.append(args)
    return subprocess.run(args,check=True,capture_output=True,text=True).stdout

def source():
    new=(W/'native_eabi_m0_atan_fast.inc').read_text();before=(P/'native_eabi_m0_atan_fast.inc').read_text()
    delta=run(['diff','--version']) if False else (W/'directional-ninth-only.patch').read_text()
    # Check the patch against the exact accepted parent without writing it.
    q=subprocess.run(['patch','--dry-run','--silent',str(P/'native_eabi_m0_atan_fast.inc')],input=delta,text=True,capture_output=True)
    require(q.returncode==0,'declared patch does not apply to parent')
    # Literal reverse boundaries keep selection, geometry, reciprocal, first
    # polynomial, tables, fallback, and public dispatch outside this delta.
    for marker in ('__attribute__((optimize("Os"),noinline)) static U atan_fast_reciprocal',
                   '__attribute__((optimize("Os"),noinline)) static U atan_fast_ratio'):
        i=new.index(marker);j=new.index('\n}',i)+2;a=new[i:j]
        k=before.index(marker);l=before.index('\n}',k)+2
        require(a==before[k:l],'unchanged reduction helper source')
    f='__attribute__((optimize("Os"),noinline)) static double atan_fast'
    tail=new[new.index(f):];oldtail=before[before.index(f):]
    meta='''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  const int32_t r3=int32_t(uint32_t(c3)-3U*uint32_t(third));
  const int32_t r5=int32_t(uint32_t(c5)-5U*uint32_t(fifth));
  const uint32_t poly_meta=uint32_t(r5+4)|(uint32_t(r3+1)<<4);
#endif
'''
    require(tail.count(meta)==1,'metadata source scope')
    require(tail.replace(meta,'').replace('sign,poly_meta,result','sign,result')==oldtail,'public math outside metadata changed')
    for n in ('native_eabi_m0.cpp','native_eabi_m0_atan.inc'):
        require((W/n).read_bytes()==(P/n).read_bytes(),'dispatch/translation unit changed')
    b=read(W/'candidate-build.json');cc=list(b['commands'][-2]);ld=list(b['commands'][-1])
    cc[cc.index('-o')+1]=str(HERE/'candidate-full.o');run(cc)
    require(sha(HERE/'candidate-full.o')==sha(W/'candidate-full.o')=='69095e178c6a559c812fc7528143515387456264e72cc509cbae8fc728f3bbe7','entire public object')
    ld[ld.index(str(W/'candidate-full.o'))]=str(HERE/'candidate-full.o');ld[ld.index('-o')+1]=str(HERE/'candidate.elf');run(ld)
    require(sha(HERE/'candidate.elf')==sha(W/'candidate.elf')=='35247afa5324a99d061028c606b495a5cd2ccf4bb778a62949d285cf32d99b0a','entire linked component')
    require(sha(W/'control-full.o')==sha(PRIOR/'candidate-full.o') and sha(W/'control.elf')==sha(PRIOR/'candidate.elf'),'accepted parent bindings')
    a,z=ElfImage(W/'control-full.o'),ElfImage(HERE/'candidate-full.o');aa,zz=old.allocated(a),old.allocated(z)
    changed={n:(len(aa[n]),len(zz[n]))for n in aa if aa[n]!=zz[n]};added={n:len(zz[n])for n in zz.keys()-aa.keys()}
    require(changed=={'.text.unlikely.atan_fast_tail_repair':(344,358),'.text.atan_fast':(1780,2040)} and added=={'.text.unlikely.atan_inverse_half':126},'unrelated allocated code changed')
    require(not aa.keys()-zz.keys() and old.nobits(a)==old.nobits(z) and old.undefined(a)==old.undefined(z),'RAM/undefined dependencies changed')
    contexts=[]
    for n in ('generic_M0','M4_soft','M4_hard'):
        x,y=(ElfImage(W/(n+'-'+label+'.o'))for label in ('control','candidate'))
        require(old.allocated(x)==old.allocated(y) and old.nobits(x)==old.nobits(y),'off-target delta')
        require(sha(W/(n+'-candidate.o'))==sha(P/(n+'-candidate.o')),'off-target not accepted parent')
        contexts.append(dict(context=n,allocated_bytes=sum(map(len,old.allocated(y).values())),exact=True))
    image=ElfImage(HERE/'candidate.elf');pi=ElfImage(W/'control.elf');resident=ElfImage(old.FIRMWARE)
    bindings=b['resident_bindings'];require(bindings==read(W/'control-build.json')['resident_bindings'],'changed binding map')
    require(all(resident.symbols[n]==v for n,v in bindings.items()),'resident targets do not match pinned firmware')
    assignments={n:int(v,16)for n,v in re.findall(r'(?m)^(\w+) = (0x[0-9a-f]+);',(W/'candidate.ld').read_text())}
    require(assignments==bindings,'linker binding mismatch')
    require(set(old.allocated(image))=={'.text','.rodata'} and not old.nobits(image) and not old.undefined(image),'component allocations')
    require(old.allocated(image)['.rodata']==old.allocated(pi)['.rodata'] and len(old.allocated(image)['.rodata'])==780,'table changed')
    require(all(0x10185000<=s[3]<s[3]+s[5]<=0x10188000 for s in image.sections if s[2]&2),'overlay bounds')
    require(all(not 0x10185000<=(v&~1)<0x10188000 for v in bindings.values()),'overlay overwrites resident target')
    # Rebuild the producer's exact-inline-source diagnostic, independently.
    u=read(W/'ninth-unit-build.json');c=list(u['commands'][0]);l=list(u['commands'][1])
    c[c.index('-o')+1]=str(HERE/'ninth-unit.o');run(c)
    l[l.index(str(W/'ninth-unit.o'))]=str(HERE/'ninth-unit.o');l[l.index('-o')+1]=str(HERE/'ninth-unit.elf');run(l)
    require(sha(HERE/'ninth-unit.o')==sha(W/'ninth-unit.o') and sha(HERE/'ninth-unit.elf')==sha(W/'ninth-unit.elf'),'inline wrapper rebuild')
    fragment=new[new.index('struct AtanTailCorrection '):new.index('// Pack the bounded atan domain')]
    require(fragment in (W/'ninth-unit.cpp').read_text() and hashlib.sha256(fragment.encode()).hexdigest()==u['exact_fragment_sha256'],'inline wrapper not actual source')
    # Small diagnostic of the actual pack/helper source, with a scalar-only
    # input record and stack-local output. This is not the public allocation.
    cpp=(W/'native_eabi_m0.cpp').read_text();i=cpp.index('__attribute__((always_inline)) inline U wide32(');wide=cpp[i:cpp.index('struct Product',i)]
    block=new[new.index('// top/den has at most six quotient bits.'):new.index('\n#endif\n\n'+f)]
    text='#include <stdint.h>\nusing U=uint64_t;\nstruct Refine96 {U low;uint32_t high;};\n'+wide+block+'''
struct Case {U low,h,n,d,sign;uint32_t high,meta;int32_t e;uint32_t invert,negative,pad;};
static_assert(sizeof(Case)==64);
extern "C" U check_pack(const Case* p) {
  U out=~U(0);bool ok=atan_fast_pack({p->low,p->high},p->e,p->invert,p->negative,p->h,p->n,p->d,p->sign,p->meta,out);
  return ok?out:~U(0);
}
'''
    (HERE/'pack-unit.cpp').write_text(text)
    (HERE/'pack-unit.ld').write_text('SECTIONS { . = 0x101d0000; .text : { *(.text*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) } }\n')
    c=list(u['commands'][0]);c[c.index('-c')+1]=str(HERE/'pack-unit.cpp');c[c.index('-o')+1]=str(HERE/'pack-unit.o');run(c)
    l=list(u['commands'][1]);l[l.index('-T')+1]=str(HERE/'pack-unit.ld');l[l.index(str(W/'ninth-unit.o'))]=str(HERE/'pack-unit.o');l[l.index('-o')+1]=str(HERE/'pack-unit.elf');run(l)
    require(not old.undefined(ElfImage(HERE/'pack-unit.elf')),'pack diagnostic dependency')
    r=dict(status='PASS_FULL_OBJECT_ENTIRE_ELF_AND_DELTA_ISOLATION',source_sha256=sha(W/'native_eabi_m0_atan_fast.inc'),entire_own_object_sha256=sha(HERE/'candidate-full.o'),entire_own_ELF_sha256=sha(HERE/'candidate.elf'),
        changed_sections=changed,added_sections=added,net_code_delta_bytes=400,all_other_allocated_sections_tables_global_RAM_undefined_dependencies_exact=True,table_bytes=780,
        contexts=contexts,resident_bindings=bindings,inline_diagnostic_source_exact=True,inline_diagnostic_register_allocation_is_distinct=True,public_component_executed_separately=True,
        pack_diagnostic_source_sha256=sha(HERE/'pack-unit.cpp'),commands=COMMANDS,hardware_accessed=False)
    put('SOURCE-OBJECT-PROOF.json',r);return r

def polynomial(h):
    # Independently retained product62 error expression, with explicit
    # nonnegative fifth truncation loss separated from its positive side.
    square=F(1,2)+F(13,512);cube=F(1,2)+F(13,512)+h*square
    positive5=F(1,2)+h*h*cube+h**3*square+cube*square/S
    all5=positive5+((1<<17)-1)*(S*h*h+square)/S+((1<<24)-1)*(S*h**3+cube)/S
    seventh=F(1,2)+h*h*all5+h**5*square+all5*square/S+7*(S*h*h+square)/S+((1<<24)-1)*(S*h**5+all5)/S
    return cube,positive5,all5,seventh

def total_old(h,ratio):
    c3,p5,c5,c7=polynomial(h);k5=F(0xCCCCCCCD,1<<31);k7=F(2454267027,1<<34)
    fifth=c5/5+F(7,5)+(k5-F(8,5))*(S*h**5+c5)/8+F(1,2)
    seventh=k7*c7+max(3*k7+(k7-F(1,7))*S*h**7,1-3*k7)
    return F(1)+F(1,2)+c3/3+fifth+seventh+S*h**9/(9*(1-h*h))+ratio

def bounds():
    h=F(1,128);c3,p5,c5,c7=polynomial(h);ratio=F(1,2)+F(35,1<<20);drift=33*(h+F(33,S))**2
    ninth_error=F(1,2)+F(13,4608);require(ninth_error==F(2317,4608)<F(51,100),'Q16 ninth error')
    positive7=c3/3+F(1,3)+p5/5+c7/7+F(3,7)+ratio+1+drift
    tail11=S*h**11/(11*(1-h*h))
    positive9=c3/3+p5/5+c7/7+F(3,7)+F(51,100)+tail11+ratio+1+drift
    symmetric9=c3/3+F(1,3)+c5/5+F(2,5)+c7/7+F(3,7)+F(51,100)+tail11+ratio+1+drift
    require(positive7<F(14,5) and positive7-F(1,2)<F(11,5),'old directional thresholds')
    require(positive9<F(42,15) and positive9-F(1,2)<F(35,15) and symmetric9<7,'ninth thresholds')
    regions=[]
    for cap,radius in ((F(1,250),6),(F(1,160),9),(F(1,128),23)):
        error=total_old(cap,ratio)+33*(cap+F(33,S))**2
        require(error<radius,'repaired symmetric radius')
        regions.append(dict(h_cap=str(cap),radius=radius,bound=str(error),bound_float=float(error)))
    inv=total_old(F(1,180),F(1,2));require(inv<7,'inverted unchanged-q radius')
    # Complete small remainder domains, and endpoint cell decisions. This
    # is finite integer gate algebra, not a replay of the public corpus.
    intervals=declined=0
    for normal in (False,True):
      for reverse in (False,True):
       for r3 in range(-1,2):
        for r5 in range(-4,10):
         v=r5+7;q5=(v*13108)>>16;delta=q5-1;rnew=r5-5*delta
         require(q5==v//5 and delta==((abs(r5)+2)//5)*(-1 if r5<0 else 1) and -2<=rnew<=2,'fifth exact nearest')
         for distance in range(12):
          for ninth in (False,True):
           upper=(positive9+r3/F(3)-rnew/F(5))if ninth else positive7-r5/F(5)
           if normal:upper-=F(1,2)
           gate=(15*distance>=(35 if normal else 42)+5*r3-3*rnew)if ninth else 5*distance+r5>=(11 if normal else 14)
           if not gate:declined+=1;continue
           require(upper<distance,'directional gate admits endpoint outside rounding cell')
           for parity in (0,1):
            # center is on favorable side; near upper/lower midpoint the
            # strict error endpoint must round to that side, even at ties.
            shift=12;half=1<<(shift-1);retained=(1<<52)+parity
            center=(retained<<shift)+half+(-distance if reverse else distance)
            true_endpoint=F(center)+(upper if reverse else -upper)
            want=old.round_fraction(F(center,S))
            require(old.round_fraction(true_endpoint/S)==want,'exact endpoint RNE')
            intervals+=1
    require(65535**2+32768<1<<32,'Q16 product overflow')
    for n in range(133):require((n*7282)>>16==n//9,'small ninth divisor')
    # Rounded residual: b=floor(D/2^38)>=2^20, |R|/D<33;
    # floor numerators/divisors and odd b rounding give <.5+35/b.
    require(33*((1<<26)-1)+33+((1<<26)-1)//2<1<<32,'rounded numerator overflow')
    require(33*(1<<54)<1<<60 and 54+33+16<1024,'inverse sign representation/retained quantum')
    r=dict(status='PASS_INDEPENDENT_FRACTION_DIRECTIONAL_NINTH_ENCLOSURES',old_positive_base=str(positive7),old_positive_base_float=float(positive7),ninth_positive_base=str(positive9),ninth_positive_base_float=float(positive9),
        ninth_symmetric_bound=str(symmetric9),ninth_symmetric_bound_float=float(symmetric9),Q16_ninth_error_exact=str(ninth_error),regions=regions,inverse_bound=str(inv),inverse_bound_float=float(inv),
        gate_endpoint_RNE_checks=intervals,gate_declines=declined,
        directional_sign='final q error flips iff geometryNegative XOR invert; upper-polynomial-error is relevant above midpoint when not reversed, below midpoint when reversed; direction is recomputed after each correction.',
        polynomial_signs='P7-atan includes -h^9/9 (nonpositive, dropped only in upper bound); after adding ninth, omitted -h^11/11 in atan becomes positive P9 error and is included.',
        Q16_error_derivation='x=floor(65536*h/2^63), all x and q<=65535. Unit-scale Lipschitz plus nearest-rounding errors:1->2.5->5.5->11.5->13. Final /4608 nearest adds .5;13/4608+.5=2317/4608.',
        rounded_residual_bound=str(ratio),rounded_residual_proof='For b=floor(D/2^38)>=2^20, t=floor(abs(R)/2^38), r=abs(R)/D<33: -1/b < t/b-r <33/b. floor((t+floor(b/2))/b) adds at most .5+1/(2b) error, below the stated .5+35/2^20.',
        inverse_proof='Inverted N,D are multiples64 and D<2^60. Rprime=(N<<58)-h*(D>>6), abs(Rprime)<33*(D>>6)<2^60. low64(h*(D>>6)) represents -Rprime; shifted unsigned interval true implies abs(Rprime)<=floor((D>>6)/2).',
        exact_midpoint_new_gates_decline=True,retained_quantum_unchanged=True,parent_selector_reciprocal_and_tables_proof_reused=True,large_corpus_repeated=False)
    put('EXACT-DIRECTIONAL-NINTH-BOUND.json',r);return r

def ninth_model(h,r5):
    x=h>>47;q2=(x*x+32768)>>16;q4=(q2*q2+32768)>>16;q8=(q4*q4+32768)>>16;q9=(q8*x+32768)>>16
    ninth=(((q9+2304)>>9)*7282)>>16;q5=((r5+7)*13108)>>16
    return q5+ninth-1,r5-5*(q5-1)

def pack_model(c):
    q,h,n,d,sign,e,invert,negative,r3,r5=c
    base=0 if invert else e;high=q>>64;lower=int(high<(1<<(base+6)));shift=base+18-lower;half=1<<(shift-1)
    tail=q&((half<<1)-1);distance=abs(tail-half);reverse=negative!=invert;norm=(e+5)&0xffffffff
    small=h<=1<<62;favored=(tail<half)==reverse;stage='initial';extra=0;delta=0;rnew=r5
    if distance*8<(288 if small else 426):
      radius=(144 if favored else 288)if small else(282 if favored else 426)
      if distance*8<radius:
       if norm<5 and h<=47<<57 and ((n>>32)>>(24-norm))<49:
        radius=121 if favored else 176
        if distance*8<radius and ((n>>32)>>(27-norm))==0:radius=91 if favored else 100
       if distance*8<radius:
        residue=(h*(d>>6))&MASK
        if invert and h<=S//180 and distance>=7 and ((residue+((d>>6)>>1))&MASK)<d>>6:stage='inverse'
        else:
         r=(n<<64)-h*d;den=d>>38;delta=((abs(r)>>38)+(den>>1))//den;delta=-delta if r<0 else delta
         if reverse:delta=-delta
         tail+=delta;dist=abs(tail-half);radius=23 if h>S//160 else 9 if h>S//250 else 6
         if dist>=radius:stage='symmetric'
         elif (tail<half)==reverse and 5*dist+r5>=(11 if norm<5 else 14):stage='directional'
         else:
          extra,rnew=ninth_model(h,r5)
          if reverse:extra=-extra
          tail+=extra;dist=abs(tail-half)
          if dist>=7:stage='ninth-symmetric'
          elif (tail<half)==reverse and 15*dist>=(35 if norm<5 else 42)+5*r3-3*rnew:stage='ninth-directional'
          else:stage='fallback'
    result=MASK if stage=='fallback'else sign+((base+1022-lower)<<52)+(q>>shift)+int(tail>half)
    return result,dict(stage=stage,delta=delta,extra=extra,final_distance=abs(tail-half),r5new=rnew,reverse=reverse,initial_side=(q&((half<<1)-1))<half,final_side=tail<half)

STATES=parent.STATES
def signed32(v):return v-(1<<32)if v>>31 else v
def geometry(raw,n,d,h):
    mag=raw&(old.SIGN-1);invert=mag>0x3ff0000000000000;e=(mag>>52)-1023;s=(mag&old.FRAC)|(1<<52)
    if invert:
        index=(((1<<30)//(s>>37))+(1<<(8+e)))>>(9+e);a=1<<(58-e);b=s*index
        wn=abs(a-b)<<6;wd=(s<<6)+(index<<(52-e))
    else:
        index=((s>>(45-e))+1)//2;a=s<<6;b=index<<(52-e);z=abs(a-b)
        wn=z<<(5 if e==-6 else 6);wd=((1<<63)|(s*index>>1))if e==-6 else(1<<(58-e))+s*index
    require((n,d)==(wn,wd),'actual helper geometry differs')
    x=old.decode(mag);y=1/x if invert else x;exact=abs((y-F(index,64))/(1+y*F(index,64)))*S
    quant=F(n<<64,d)-exact
    require((0<=quant<F(1,2))if not invert and e==-6 else quant==0,'actual reduction identity')
    require(1<<58<=d<1<<64 and h<1<<63 and abs(F(n<<64,d)-h)<33,'helper quotient domain')
    if invert:require(d<1<<60 and n%64==d%64==0,'inverted domain')
    return dict(input=f'{raw:016x}',domain='inverted'if invert else'halved-e-6'if e==-6 else'ordinary',n=f'{n:016x}',d=f'{d:016x}',h=f'{h:016x}',geometry_negative=a<b,halving_error=str(quant))

def jobs():
    out={}
    def add(raw,tag):out.setdefault(raw,tag)
    for r in read(W/'result.json')['fixed_rows']:add(int(r['x'],16),'fixed18')
    for r in read(W/'remaining-slower.json')['rows']:add(int(r['x'],16),'remaining2')
    # Six cell edges and adjacent raw values; geometry and cap crossovers.
    for cap in (F(1,250),F(1,160),F(1,180)):
      for invert in (False,True):
        center=F(31,64);v=(center+cap)/(1-center*cap);v=1/v if invert else v
        raw=old.round_fraction(v)
        for off in (-1,0,1):add(raw+off,'repair-cap-edge')
    for v in (0x3fb97996f4e5f9f0,0xbfdd440162570130,0x3fe5d1004fc925b6,0xbfe5d1004fc925b6,0x3fecb99548f4fa32,0xbfecb99548f4fa32):add(v,'old-hard-control')
    for v in (0,old.SIGN,1,old.SIGN|1,old.FRAC,old.SIGN|old.FRAC,old.INF,old.INF|old.SIGN,old.INF|1,old.SIGN|old.INF|1,old.INF|0x8000000000123,old.SIGN|old.INF|old.FRAC):add(v,'special')
    for e in (-6,0,6):
      for off in (-1,0,1):add(((e+1023)<<52)+off,'dispatch-edge')
    for r in read(W/'regressions.json').get('V164_regression_rows',[]):add(int(r['x'],16),'V164-regression')
    require(len(out)<96,'focused public replay widened');return out

def arm_helpers():
    # All three machines have only component/diagnostic code and SRAM,
    # not a resident firmware or captured/abstract ROM implementation.
    m=Machine(HERE/'candidate.elf',True,stack_bytes=128);u=Machine(HERE/'ninth-unit.elf',True,stack_bytes=128);p=Machine(HERE/'pack-unit.elf',True,stack_bytes=256)
    require(not m.rom_models and not u.rom_models and not p.rom_models,'abstract helper ROM callback')
    names={k:next(n for n in m.elf.symbols if n.startswith(k))for k in('atan_fast_tail_repair','atan_inverse_half')}
    for label,ma in [('component',m),('ninth',u),('pack',p)]:
        ranges=[(s[3],s[3]+s[5])for s in ma.elf.sections if s[2]&6==6 and s[5]]
        def code(uc,pc,size,user,ranges=ranges):require(any(a<=pc and pc+size<=b for a,b in ranges),'bare helper code dependency')
        def mmio(uc,access,address,size,value,user):require(address<0x40000000,'bare helper SIO/MMIO access')
        ma.uc.hook_add(UC_HOOK_CODE,code);ma.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,mmio)
    repair=[]
    for d in (1<<58,(1<<58)+(1<<38)-1,(1<<63)+1,MASK):
      for n in (0,d//4-1):
       H=F(n<<64,d);floor=H.numerator//H.denominator
       for off in (-32,-1,0,1,32):
        h=floor+off
        if not 0<=h<1<<63 or abs(H-h)>=33:continue
        R=(n<<64)-h*d;den=d>>38;want=((abs(R)>>38)+(den>>1))//den;want=-want if R<0 else want
        for sn,state in STATES.items():
         m.stack_lowest=SP;m.uc.mem_write(0xd0000060,state);got=m.call(names['atan_fast_tail_repair'],n,d,c=h)[0]&0xffffffff
         require(signed32(got)==want and abs(F(want)-(H-h))<F(1,2)+F(35,1<<20),'rounded residual mismatch')
         require(bytes(m.uc.mem_read(0xd0000060,28))==state,'bare repair changed SIO')
         repair.append(dict(n=f'{n:016x}',d=f'{d:016x}',h=f'{h:016x}',delta=want,SIO=sn,stack_bytes=SP-m.stack_lowest))
    ninth=[]
    for h in (0,1,(1<<47)-1,1<<47,(1<<62)-1,1<<62,S//250,S//160,(1<<63)-1):
      for r5 in (-4,-3,-2,0,2,3,7,9):
       want,rem=ninth_model(h,r5);delta5=((abs(r5)+2)//5)*(-1 if r5<0 else 1)
       require(abs(F(want-delta5)-F(h**9,9*(1<<560)))<F(51,100),'ninth model exact polynomial error')
       for sn,state in STATES.items():
        u.uc.mem_write(0xd0000060,state);got=u.call('check_ninth',h,r5&0xffffffff)[0]
        require(signed32(got&0xffffffff)==want and signed32(got>>32)==rem,'actual inline ninth result')
        require(bytes(u.uc.mem_read(0xd0000060,28))==state,'bare ninth changed SIO')
        ninth.append(dict(h=f'{h:016x}',r5=r5,delta=want,remainder=rem,SIO=sn))
    inverse=[]
    for d in (1<<58,(1<<58)+64,(1<<60)-64):
      for n in (0,64,(d//4)&~63):
       H=F(n<<64,d);floor=H.numerator//H.denominator
       for off in (-32,-1,0,1,32):
        h=floor+off
        if not 0<=h<1<<63 or abs(H-h)>=33:continue
        residue=h*(d>>6)-(n<<58);want=0<=residue+((d>>6)>>1)<d>>6
        for sn,state in STATES.items():
         m.uc.mem_write(0xd0000060,state);got=m.call(names['atan_inverse_half'],h,d)[0]&0xffffffff
         require(got==int(want) and (not got or abs(H-h)<=F(1,2)),'inverse residue mismatch/false admission')
         require(bytes(m.uc.mem_read(0xd0000060,28))==state,'inverse changed SIO')
         inverse.append(dict(n=f'{n:016x}',d=f'{d:016x}',h=f'{h:016x}',accept=bool(got),SIO=sn))
    third=[]
    for v in (0,1,2,3,4,0xfffffffe,0xffffffff,1<<32,(1<<32)+1,(2<<32)-1,(1<<49)-1):
      for sn,state in STATES.items():
       u.uc.mem_write(0xd0000060,state);got=u.call('check_third',v)[0]
       require(got==(v+1)//3 and -1<=v-3*got<=1,'actual third remainder')
       require(bytes(u.uc.mem_read(0xd0000060,28))==state,'third changed SIO')
       third.append(dict(input=f'{v:016x}',output=f'{got:016x}',SIO=sn))
    # Select only threshold/correction direction witnesses, not a sweep.
    selected={};pointer=0x20010000
    for e,invert in ((-6,False),(-5,False),(0,True)):
     base=0 if invert else e;shift=base+18;half=1<<(shift-1)
     for hbase in (S//250,S//160,(1<<63)-64):
      # Inverted N,D must both be multiples64. With D=2^58,
      # H=N*64 therefore needs 4096 alignment, not just 64 alignment.
      alignment=12 if invert else 6
      exact_h=(hbase>>alignment)<<alignment;d=1<<58;n=exact_h>>6
      for off in (-32,0,32):
       h=exact_h+off
       for reverse in (False,True):
        for r3,r5 in ((-1,-4),(0,0),(1,9)):
         for distance in (-8,-7,-6,-3,-2,-1,0,1,2,3,6,7,8):
          negative=reverse!=invert;q=(((1<<52)+1)<<shift)+half+distance
          c=(q,h,n,d,0,e,invert,negative,r3,r5);want,meta=pack_model(c)
          key=(e,invert,reverse,meta['stage'],meta['initial_side']!=meta['final_side'])
          selected.setdefault(key,(c,want,meta))
    require({'directional','ninth-directional','ninth-symmetric','fallback','symmetric','inverse'}<=set(k[3]for k in selected),'missing changed gate witness')
    pack=[]
    for c,want,meta in selected.values():
      q,h,n,d,sign,e,invert,negative,r3,r5=c
      blob=struct.pack('<5Q2Ii3I',q&MASK,h,n,d,sign,q>>64,(r5+4)|((r3+1)<<4),e,int(invert),int(negative),0)
      require(len(blob)==64,'pack diagnostic layout')
      for sn,state in STATES.items():
       p.uc.mem_write(pointer,blob);p.uc.mem_write(0xd0000060,state);got=p.call('check_pack',pointer)[0]
       require(got==want,'actual pack differs independent scalar gate model '+str((c,meta,hex(got),hex(want))))
       require(bytes(p.uc.mem_read(pointer,64))==blob and bytes(p.uc.mem_read(0xd0000060,28))==state,'pack changed input/SIO')
       pack.append(dict(e=e,invert=invert,negative=negative,r3=r3,r5=r5,SIO=sn,result=f'{got:016x}',**meta))
    r=dict(status='PASS_SELECTED_BARE_ARM_HELPERS_AND_PACK_CELLS',rounded_residual_rows=repair,ninth_rows=ninth,inverse_rows=inverse,third_rows=third,pack_rows=pack,
        ARM_calls=len(repair)+len(ninth)+len(inverse)+len(third)+len(pack),pack_stages=dict(Counter(x['stage']for x in pack)),PCS_SP_bounded_stack_and_no_MMIO=True,
        bare_no_firmware_no_ROM=True,synthetic_pack_cases_are_gate_contract_tests_not_public_atan_inputs=True,hardware_accessed=False)
    put('SELECTED-HELPER-ARM.json',r);return r

def arm_public(selected=None,stem='SELECTED-PUBLIC-ARM'):
    chosen=jobs()if selected is None else selected
    machines={'V164':Machine(old.FIRMWARE,True,bootrom=old.ROM),'Qfplib':Machine(old.REFERENCE,True)}
    for label,file in (('parent',W/'control.elf'),('candidate',HERE/'candidate.elf')):
        m=Machine(old.FIRMWARE,True,bootrom=old.ROM);im=ElfImage(file);im.load(m.uc);m.elf.symbols[label]=im.symbols['mk61_m0_atan'];machines[label]=m
    require(not any(m.rom_models for m in machines.values()),'abstract public ROM callback')
    image=ElfImage(HERE/'candidate.elf');resident=ElfImage(old.FIRMWARE);bindings=read(W/'candidate-build.json')['resident_bindings']
    ranges=[(s[3],s[3]+s[5])for im in(image,resident)for s in im.sections if s[2]&6==6 and s[5]]+[(0,0x4000)]
    helpers={k:image.symbols[next(n for n in image.symbols if n.startswith(k))]&~1 for k in ('atan_fast_tail_repair','atan_inverse_half')}
    current=dict(raw=0,SIO=None,repair=0,inverse=0,CORE=0,reference=0);events=Counter();observations=[]
    def code(uc,pc,size,user):
        require(any(a<=pc and pc+size<=b for a,b in ranges),'public candidate escaped executable closure')
        if pc==helpers['atan_fast_tail_repair']:
            current['repair']+=1;n=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32);d=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
            h=struct.unpack('<Q',uc.mem_read(uc.reg_read(UC_ARM_REG_SP),8))[0]
            observations.append(dict(SIO=current['SIO'],**geometry(current['raw'],n,d,h)))
        if pc==helpers['atan_inverse_half']:current['inverse']+=1
        if pc==bindings['mk61_m0_cr_atan']&~1:current['CORE']+=1
        for n,a in bindings.items():
            if pc==a&~1:events[n]+=1
    def mmio(uc,access,address,size,value,user):
        if address>=0x40000000:require(0xd0000060<=address and address+size<=0xd000007c,'unexpected public MMIO')
    m=machines['candidate'];m.uc.hook_add(UC_HOOK_CODE,code);m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,mmio)
    def reference(uc,pc,size,user):
        a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32);b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
        require(a==current['raw'] and b==0x3ff0000000000000,'Qfplib reference not atan2(x,1)');current['reference']+=1
    ref=machines['Qfplib'];address=ref.elf.symbols['qfp_datan2']&~1;ref.uc.hook_add(UC_HOOK_CODE,reference,begin=address,end=address)
    # Independently call the existing directed MPFR oracle for this compact
    # selection, alongside the inherited rational Taylor/Machin enclosure.
    path=ROOT/'.build/m0-float-fma-qualification-20261023/support/m0_mpfr_oracle.py'
    spec=importlib.util.spec_from_file_location('directed_mpfr_review',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mpfr=mod.Oracle()
    fixed={(r['x'].lower(),r['SIO']):r for r in read(W/'result.json')['fixed_rows']}
    remaining={(r['x'].lower(),r['SIO']):r for r in read(W/'remaining-slower.json')['rows']}
    prior={(r['input'],r['SIO']):r for r in read(PRIOR/'SELECTED-ARM-GEOMETRY.json')['rows']}
    # Only read the already sealed producer records for selected input costs.
    author={(r['x'].lower(),r['SIO']):r for r in read(W/'qualification.json')['rows']}
    rows=[];oracles={};parent_checks=0;author_checks=0;wrong=[]
    for raw,tag in chosen.items():
      want,oracle=old.expected(raw)
      if raw&~old.SIGN<=old.INF:
        mp=mpfr.reference('atan',raw);require(mp==want,'independent MPFR/Fraction disagreement')
      else:mp=None
      oracles[f'{raw:016x}']=dict(rational=oracle,MPFR=f'{mp:016x}'if mp is not None else'raw NaN policy from parent')
      for sn,state in STATES.items():
        outputs={};counts={};depth={};current.update(raw=raw,SIO=sn,repair=0,inverse=0,CORE=0,reference=0)
        for label,m in machines.items():
            m.stack_lowest=SP;m.uc.mem_write(0xd0000060,state);symbol='mk61_m0_atan'if label=='V164'else'audit_atan'if label=='Qfplib'else label
            got,_,cost=m.call(symbol,raw,count=True);after=bytes(m.uc.mem_read(0xd0000060,28))
            require(after==state if sn=='DIRTY'else struct.unpack('<7I',after)[6]&3==1,'public SIO changed/not clean')
            if label!='Qfplib':require(got==want,'independent oracle mismatch '+str((hex(raw),label,hex(got),hex(want))))
            outputs[label]=f'{got:016x}';counts[label]=cost;depth[label]=SP-m.stack_lowest
        key=(f'{raw:016x}',sn)
        require(current['reference']==1,'reference not actual one atan2 call')
        if key in prior:
            x=prior[key];require(outputs['parent']==x['outputs']['candidate'] and counts['parent']==x['instructions']['candidate'],'accepted parent controls changed');parent_checks+=1
        if key in author:
            x=author[key]
            require(all(outputs[k]==x['outputs']['resident'if k=='V164'else k].lower() and counts[k]==x['instructions']['resident'if k=='V164'else k] for k in machines),'producer selected cost/body not reproducible');author_checks+=1
        if key in fixed:require(outputs['Qfplib']==f'{want:016x}' and counts['candidate']<counts['Qfplib'] and current['CORE']==0,'fixed18 not correct faster bounded path')
        if key in remaining:require(outputs['Qfplib']==f'{want:016x}' and counts['candidate']>counts['Qfplib'] and current['CORE']==1,'remaining fallback deficit suppressed')
        if outputs['Qfplib']!=f'{want:016x}':wrong.append(dict(input=key[0],SIO=sn,raw=outputs['Qfplib'],correct=f'{want:016x}'))
        rows.append(dict(input=key[0],group=tag,SIO=sn,expected=f'{want:016x}',outputs=outputs,instructions=counts,stack_bytes=depth,repair_entries=current['repair'],inverse_entries=current['inverse'],CORE_entries=current['CORE'],fixed18=key in fixed,remaining2=key in remaining))
    require(all(m.calls==2*len(chosen)for m in machines.values()),'actual call accounting')
    r=dict(status='PASS_SELECTED_PUBLIC_ARM_FRACTION_AND_DIRECTED_MPFR',unique_inputs=len(chosen),states=len(rows),ARM_calls=sum(m.calls for m in machines.values()),MPFR_version=mpfr.version,
        rows=rows,selected_helper_geometries=observations,observed_resident_calls=dict(events),accepted_parent_result_and_cost_controls=parent_checks,selected_author_output_cost_controls=author_checks,
        wrong_Qfplib_outputs_retained=wrong,Qfplib_reference='Actual audit_atan -> qfp_datan2(x,1); not a separate public Qfplib atan API.',candidate_uses_pinned_resident_helpers_and_captured_ROM=True,
        stack_max={k:max(r['stack_bytes'][k]for r in rows)for k in machines},PCS_SP_bounded_writes_DIRTY_exact_READY_clean=True,instructions_are_not_physical_cycles=True,hardware_accessed=False)
    put(stem+'.json',r);put('OWN-ORACLE-INTERVALS.json'if selected is None else stem+'-ORACLES.json',oracles);return r

if __name__=='__main__':
    if sys.argv[1]=='source':source();bounds()
    elif sys.argv[1]=='arm':
        a=arm_helpers();b=arm_public();print(json.dumps(dict(helper_ARM=a['ARM_calls'],public_inputs=b['unique_inputs'],public_ARM=b['ARM_calls'],stack_max=b['stack_max'])))
    elif sys.argv[1]=='arm-inverted':
        chosen={v:'selected-actual-inverted-repair'for v in(0x4012a253c99075d1,0xc012a253c99075d1,0x404554aaaaaaaaac,0xc04554aaaaaaaaac)}
        b=arm_public(chosen,'SELECTED-INVERTED-ARM');print(json.dumps(dict(public_inputs=b['unique_inputs'],public_ARM=b['ARM_calls'],helper_geometries=b['selected_helper_geometries'])))
    else:raise SystemExit('source|arm|arm-inverted')
    require(INITIAL==pins(),'input pins changed during review')
