"""Bounded independent RP2040 atan packing/enclosure review; no hardware APIs."""
from pathlib import Path
from fractions import Fraction as F
from functools import lru_cache
from collections import Counter
import datetime, hashlib, json, struct, subprocess, sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]
W=ROOT/'.build/m0-atan-original-goal-20261024'; P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'; SOURCE=P/'source/code'
FIRMWARE=P/'firmware/mk61s-picocalc-pico-h.elf'
REFERENCE=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
sys.path.insert(0,str(Q/'support'))
from check_stm32_vectors import ElfImage
from native_eabi_m0_arm_self_test import Machine, SP, STOP
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3
SIGN=1<<63; FRAC=(1<<52)-1; INF=0x7ff0000000000000
commands=[]


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok,msg):
    if not ok:raise AssertionError(msg)
def read(p):return json.loads(Path(p).read_text())
def run(argv):
    argv=list(map(str,argv));commands.append(argv)
    return subprocess.run(argv,check=True,capture_output=True,text=True).stdout
def allocated(e):return {n:e.bytes_at(s)for n,s in e.named_sections.items()if s[2]&2 and s[1]!=8}
def nobits(e):return {n:(s[2],s[5],s[8])for n,s in e.named_sections.items()if s[2]&2 and s[1]==8}
def symbols(e):
    result=[]
    for s in e.sections:
        if s[1]!=2:continue
        strings=e.bytes_at(e.sections[s[6]])
        for at in range(s[4],s[4]+s[5],s[9]):
            name,value,size,info,other,index=struct.unpack_from('<IIIBBH',e.data,at)
            result.append((e.string(strings,name),value,size,info,other,index))
    return result
def undefined(e):return sorted({r[0]for r in symbols(e)if r[0]and not r[5]})
def body(e,n,size=None):
    start=e.symbols[n]&~1;size=e.sizes[n]if size is None else size
    for s in e.sections:
        if s[2]&2 and s[1]!=8 and s[3]<=start and start+size<=s[3]+s[5]:return e.data[s[4]+start-s[3]:s[4]+start-s[3]+size]
    raise AssertionError('body outside allocated image '+n)


def pins():
    require(sha(W/'HANDOFF.md')=='d912b45003f48351a951fb19e22138dfccfd95d18bd5f08fedf66ca8acf803bf','handoff')
    require(sha(W/'result.json')=='82dbe45fe869c8984cc94b38be5003d633e8232c16bbf5834e0cb2760e5fe3a9','result')
    files=read(W/'result.json')['files']
    for name,digest in files.items():require(sha(W/name)==digest,'author artifact changed '+name)
    inputs=read(W/'input-pins.json')['files']
    for name,digest in inputs.items():require(sha(ROOT/name)==digest,'pinned input changed '+name)
    return dict(author_files=len(files),input_files=len(inputs),all_match=True)


def source_proof():
    pin=pins();new=(W/'native_eabi_m0_atan_fast.inc').read_text();old=(SOURCE/'native_eabi_m0_atan_fast.inc').read_text()
    marker='#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\n// Pack the bounded atan domain'
    first=new.index(marker);last=new.index('__attribute__((optimize("Os"),noinline)) static double atan_fast',first)
    reconstructed=new[:first]+new[last:]
    call='''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  if(atan_fast_pack(q,e,invert,negative,h,uint32_t(numerator>>32),sign,result)) return real(result);
#else
  if(r96_pack(q,24,sign,64,result)) return real(result);
#endif'''
    require(reconstructed.count(call)==1,'new invocation scope')
    reconstructed=reconstructed.replace(call,'  if(r96_pack(q,24,sign,64,result)) return real(result);')
    require(reconstructed==old,'source delta outside packing/enclosure')
    for name in ('native_eabi_m0.cpp','native_eabi_m0_atan.inc'):require((W/name).read_bytes()==(SOURCE/name).read_bytes(),'other public source changed')
    build=read(W/'candidate-build.json');compile=list(build['commands'][-2]);link=list(build['commands'][-1])
    require(compile[0].endswith('arm-none-eabi-g++') and link[0].endswith('arm-none-eabi-ld'),'unexpected build tool')
    compile[compile.index('-o')+1]=str(HERE/'candidate-full.o');run(compile)
    require(sha(HERE/'candidate-full.o')==sha(W/'candidate-full.o')=='fe74189c9165e4d9378b4a182130fdb24f827579896a34f3ec43d5372333366e','own public object')
    link[link.index(str(W/'candidate-full.o'))]=str(HERE/'candidate-full.o');link[link.index('-o')+1]=str(HERE/'candidate.elf');run(link)
    require(sha(HERE/'candidate.elf')==sha(W/'candidate.elf')=='93830c121ef76ccc3278233bd54b4ed2a5f2a4313a466d8854115c097f02f946','whole own relink mismatch')
    controlbuild=read(W/'control-build.json');compile=list(controlbuild['commands'][-2]);compile[compile.index('-o')+1]=str(HERE/'control-full.o');run(compile)
    require(sha(HERE/'control-full.o')==sha(W/'control-full.o'),'own parent object')
    oldobj,newobj=ElfImage(HERE/'control-full.o'),ElfImage(HERE/'candidate-full.o')
    oldalloc,newalloc=allocated(oldobj),allocated(newobj)
    changed={n:(len(oldalloc[n]),len(newalloc[n]))for n in oldalloc if oldalloc[n]!=newalloc[n]}
    require(set(oldalloc)==set(newalloc)and changed=={'.text.atan_fast':(1744,1648)},'other allocated object delta')
    require(nobits(oldobj)==nobits(newobj)and undefined(oldobj)==undefined(newobj),'RAM/dependency changed')
    original_name=next(n for n in read(W/'input-pins.json')['files']if n.endswith('native_eabi_m0.cpp.o'))
    original=ElfImage(ROOT/original_name)
    require(allocated(original)==oldalloc and nobits(original)==nobits(oldobj),'rebuilt parent differs from frozen object')
    contexts=[]
    for name in ('generic_M0','M4_soft','M4_hard'):
        a,b=(ElfImage(W/(name+'-'+v+'.o'))for v in ('control','candidate'))
        require(allocated(a)==allocated(b)and nobits(a)==nobits(b),'generic/M4 contribution changed')
        contexts.append(dict(context=name,allocated_bytes=sum(map(len,allocated(a).values())),exact=True))
    resident=ElfImage(FIRMWARE);candidate=ElfImage(W/'candidate.elf');control=ElfImage(W/'control.elf')
    bindings=build['resident_bindings'];require(bindings==controlbuild['resident_bindings'],'resident maps differ')
    for name,value in bindings.items():require(resident.symbols[name]==value,'resident address mismatch '+name)
    assignments={n:int(v,16)for n,v in __import__('re').findall(r'(?m)^(\w+) = (0x[0-9a-f]+);',(W/'candidate.ld').read_text())}
    require(assignments==bindings,'linker script binding mismatch')
    require(not undefined(candidate),'undefined linked fixture')
    require(set(allocated(candidate))=={'.text','.rodata'}and not nobits(candidate),'component has global RAM/extra allocation')
    for s in candidate.sections:
        if s[2]&2:require(0x10185000<=s[3]<s[3]+s[5]<=0x10188000,'component overlaps unbounded firmware')
    require(all(not 0x10185000<=(v&~1)<0x10188000 for v in bindings.values()),'component overwrites its resident binding')
    table=allocated(candidate)['.rodata'];require(table==allocated(control)['.rodata']and len(table)==780,'atan table differs')
    for name in ('atan_fast_ratio','atan_fast_reciprocal'):
        require(body(oldobj,name)==body(newobj,name),'unchanged reciprocal code differs '+name)
    ref=ElfImage(REFERENCE);adapter=body(ref,'audit_atan',18)
    require(adapter[:6]==bytes.fromhex('10b50022024b')and adapter[10:12]==bytes.fromhex('10bd')and adapter[14:18]==bytes.fromhex('0000f03f'),'atan adapter instructions/literal')
    ins1,ins2=struct.unpack_from('<2H',adapter,6);sign=(ins1>>10)&1
    disp=(sign<<24)|((1^((ins2>>13)&1)^sign)<<23)|((1^((ins2>>11)&1)^sign)<<22)|((ins1&1023)<<12)|((ins2&2047)<<1)
    if sign:disp-=1<<25
    target=(ref.symbols['audit_atan']&~1)+6+4+disp
    require(target==(ref.symbols['qfp_datan2']&~1),'audit adapter target')
    require(struct.unpack_from('<I',adapter,14)[0]==0x3ff00000,'atan2 denominator is not1')
    report=dict(status='PASS_FULL_SOURCE_OBJECT_ELF_AND_PINNED_DEPENDENCIES',pins=pin,changed_sections=changed,whole_own_ELF_sha256=sha(HERE/'candidate.elf'),
        own_object_sha256=sha(HERE/'candidate-full.o'),parent_original_allocated_bytes=sum(map(len,oldalloc.values())),
        unchanged_source_geometry_reciprocal_polynomial_table_fallback=True,no_new_RAM_tables_external_deps=True,resident_bindings=bindings,
        executed_fixture='Candidate component loaded into pinned resident firmware and capturedBootROM; not bare firmware',
        atan_table_bytes=780,atan_table_sha256=hashlib.sha256(table).hexdigest(),contexts=contexts,
        reference='Unchanged audit_atan calls actual Qfplib qfp_datan2(x,1); not a public Qfplib atan entry',
        reference_adapter_hex=adapter.hex(),reference_BL_target=hex(target),commands=commands,hardware_access=False)
    (HERE/'SOURCE-OBJECT-PROOF.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def floor_log2(x):
    n,d=x.numerator,x.denominator;e=n.bit_length()-d.bit_length()
    if (n<d<<e)if e>=0 else (n<<(-e)<d):e-=1
    return e
def round_fraction(x,open_side=0):
    require(x>=0,'positive encoder')
    if not x:return 0
    e=floor_log2(x);shift=-1074 if e< -1022 else e-52
    n,d=x.numerator,x.denominator
    if shift>=0:d<<=shift
    else:n<<=-shift
    q,r=divmod(n,d)
    q+=2*r>d or (2*r==d and (open_side>0 if open_side else q&1))
    if e< -1022:return q
    if q==1<<53:q>>=1;e+=1
    return ((e+1023)<<52)|(q&FRAC)


@lru_cache(None)
def atan_series_interval(t,bits):
    """Rigorous alternating-series interval; each term rounded outward in2^-bits."""
    require(0<=t<=F(1,2),'Taylor reduced domain')
    if not t:return F(0),F(0)
    n,d=t.numerator,t.denominator;nn,dd=n*n,d*d;npow,dpow=n,d
    lo=hi=0;k=0
    while True:
        denominator=dpow*(2*k+1);q,r=divmod(npow<<bits,denominator);ceiling=q+bool(r)
        if k&1:lo-=ceiling;hi-=q
        else:lo+=q;hi+=ceiling
        npow*=nn;dpow*=dd;k+=1
        # Remaining alternating tail has the next term's sign and size.
        if (npow<<bits)<dpow*(2*k+1):
            if k&1:lo-=1
            else:hi+=1
            break
        require(k<1024,'Taylor term budget')
    return F(lo,1<<bits),F(hi,1<<bits)


@lru_cache(None)
def pi_interval(bits):
    a,b=atan_series_interval(F(1,5),bits),atan_series_interval(F(1,239),bits)
    return 16*a[0]-4*b[1],16*a[1]-4*b[0]


def atan_interval(x,bits=340):
    require(x>=0,'atan positive magnitude')
    pi=pi_interval(bits)
    if x>1:
        a,b=atan_interval(1/x,bits);return pi[0]/2-b,pi[1]/2-a
    if x>F(1,2):
        a,b=atan_series_interval((1-x)/(1+x),bits);return pi[0]/4-b,pi[1]/4-a
    return atan_series_interval(x,bits)


def decode(raw):
    e=(raw>>52)&2047;m=raw&FRAC
    if e:m|=1<<52
    p=e-1075 if e else -1074
    return F(m<<p)if p>=0 else F(m,1<<(-p))


@lru_cache(None)
def expected(raw):
    mag=raw&(SIGN-1)
    if not mag:return raw,dict(kind='signedzero')
    if mag>INF:return raw|(1<<51),dict(kind='inherited quiet NaN sign/payload')
    if mag==INF:lo,hi=(v/2 for v in pi_interval(340));bits=340
    else:
        value=decode(mag);bits=340+max(0,-floor_log2(value));lo,hi=atan_interval(value,bits)
    a,b=round_fraction(lo),round_fraction(hi);require(a==b,'oracle interval crosses binary64 midpoint '+hex(raw))
    return (a|(raw&SIGN)),dict(kind='own exact rational alternating-series enclosure',precision_bits=bits,lower=str(lo),upper=str(hi))


def local_bounds():
    """Re-evaluate only directional specialization; never call parent endpoint sweep."""
    scale=1<<70;half=F(1,2)
    first=F(17,2)+F(1,1<<14);second=first*first/(1<<30)+half+F(1,1<<22);c=second+1;B=4*c*c+3
    require(c<2 and F(1<<62,(1<<31)+1)+second<1<<31,'inherited finalr/nooverflow assumption')
    require(B==F(read(W/'certificate.json')['reciprocal_error']),'lower reciprocal bound')
    def error(h,ratio,table,halve):
        square=half+F(13,512);cube=square+h*square
        fifth=half+h*h*cube+h**3*square+cube*square/scale+((1<<17)-1)*(scale*h*h+square)/scale+((1<<24)-1)*(scale*h**3+cube)/scale
        seventh=half+h*h*fifth+h**5*square+fifth*square/scale+7*(scale*h*h+square)/scale+((1<<24)-1)*(scale*h**5+fifth)/scale
        c5=F(0xcccccccd,1<<31);c7=F(2454267027,1<<34)
        fifth_term=fifth/5+F(7,5)+(c5-F(8,5))*(scale*h**5+fifth)/8+half
        seventh_term=c7*seventh+max(3*c7+(c7-F(1,7))*scale*h**7,1-3*c7)
        return ratio+halve+table+half+cube/3+fifth_term+seventh_term+scale*h**9/(9*(1-h*h))
    rows=[]
    for name,h,n,table,halve,radii in (
        ('global',F(1,128),F(2),F(1),half,(282,426)),('small',F(1,256),F(2),F(1),half,(144,288)),
        ('narrow',F(47,8192),F(49,64),half,F(0),(121,176)),('tiny',F(1,256),F(1,8),half,F(0),(91,100))):
        down,up=error(h,F(13,2)+n*3,table,halve),error(h,F(13,2)+n*B,table,halve)
        require(8*down<radii[0]and 8*up<radii[1],'insufficient strict directional radius '+name)
        rows.append(dict(region=name,error_down_Q70=str(down),error_up_Q70=str(up),radius_Q73=radii))
    normalizations=[]
    for e in range(-5,0):
        k=e+5;lo=1<<(58-e);require((1<<(e+60))<=lo and 64-lo.bit_length()==k,'denominator binade')
        for normalized in ((49<<56)-1,49<<56,(49<<56)+1,(1<<59)-1,1<<59,(1<<59)+1):
            n=normalized>>k
            require(((n>>32)>>(24-k)<49)==((n<<k)<49<<56),'narrow highword equivalence')
            require(((n>>32)>>(27-k)==0)==((n<<k)<1<<59),'tiny highword equivalence')
        normalizations.append(dict(exponent=e,shift=k,lower=lo,strict_upper=2*lo))
    for e in range(-6,1):
        require(F(1,1<<(-e))*scale/6>64 and (1<<(e+18))>64,'noninverted binade margin')
    require(F(1,6)*scale>64 and F(1,64)*scale>64 and (1<<60)+33<1<<62,'inverted/tiny margin')
    # Independently round both OPEN endpoints of the certified center interval.
    # This checks strict-equality acceptance, carry, sign-direction and half ties.
    packed_cases=declined=0
    for base,lower,invert,negative,region,rd,ru in [
        (-6,0,False,False,'global',282,426),(-5,1,False,True,'narrow',121,176),
        (-1,0,False,False,'tiny',91,100),(0,1,True,False,'small',144,288),
        (0,0,True,True,'global',282,426)]:
        e=base-lower;shift=base+18-lower;halfstep=1<<(shift-1)
        for retained in ((1<<52),(1<<52)+1,(1<<53)-1):
            for d in (-54,-53,-36,-35,-22,-18,-16,-15,-13,-12,-11,-1,0,1,11,12,13,15,16,18,22,35,36,53,54):
                tail=halfstep+d;q=(retained<<shift)+tail;favored=(tail<halfstep)==(negative!=invert)
                radius=rd if favored else ru
                if abs(d)*8<radius:declined+=1;continue
                result=((e+1022)<<52)+retained+int(tail>halfstep)
                down,up=(ru,rd)if negative!=invert else(rd,ru)
                lo=F(8*q-down,8*scale);hi=F(8*q+up,8*scale)
                require(round_fraction(lo,1)==result==round_fraction(hi,-1),'packer admitted interval not one RNE cell')
                packed_cases+=1
    candidate=ElfImage(W/'candidate.elf');table=allocated(candidate)['.rodata'];selected=[]
    for index in (0,1,2,7,31,32,63,64):
        words=struct.unpack_from('<3I',table,index*12);q=words[0]|(words[1]<<32)|(words[2]<<64)
        lo,hi=atan_interval(F(index,64),340)
        require(F(2*q-1,2*scale)<=lo<=hi<=F(2*q+1,2*scale),'selected table row outside half Q70')
        selected.append(dict(index=index,Q70=hex(q),oracle_lower=str(lo),oracle_upper=str(hi)))
    proof=dict(status='PASS_LOCAL_EXACT_FRACTION_AND_PACKING_CERTIFICATE',directional=rows,normalizations=normalizations,
        newton_direction='ExactT-R=-d(S-R)^2/2^126<=0. Finalfloorcorrection differs from X by [0,r/2^30+1)<3. r<=2^31,c<2 guarantee product<2^64; inherited lower B unchanged.',
        binade='atan(x)>=2x/3 and x-grid ULP margins >64Q70 prove base/base-1; inversionatan(1)..atan(64) lies(2/3,2-1/64). All shifts11..18, distance73<=2^20, opposite midpoint>=1024Q70.',
        strict_equality_pack_acceptances=packed_cases,midpoint_or_insufficient_margin_declines=declined,selected_table_rows=selected,
        parent_458752_and_author_147456_sweeps_repeated=False,hardware_access=False)
    (HERE/'EXACT-LOCAL-BOUNDS.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def selected_jobs():
    jobs={}
    def add(v,tag):jobs.setdefault(v,tag)
    old2=(0x3fb97996f4e5f9f0,0xbfdd440162570130)
    remaining=(0x3fe5d1004fc925b6,0xbfe5d1004fc925b6,0x3fecb99548f4fa32,0xbfecb99548f4fa32)
    for raw in old2:add(raw,'historical2')
    for raw in remaining:add(raw,'remaining4-preexistingCORE')
    for raw in (*old2,*remaining):
        for delta in (-1,1):add(raw+delta,'old-or-remaining-neighbours')
    for raw in (0,SIGN,1,SIGN|1,FRAC,SIGN|FRAC,INF,INF|SIGN,INF|1,INF|(1<<51)|0x123,SIGN|INF|0x80000000,SIGN|INF|FRAC):add(raw,'IEEE-and-unchanged-paths')
    for exponent in (-28,-27,-6,-5,-1,0,1,6,55):
        raw=(exponent+1023)<<52
        for delta in (-1,0,1):
            for sign in (0,SIGN):add((raw+delta)|sign,'dispatch-binade-neighbours')
    for x in (F(1,64),F(1,32),F(31,64),F(1,2),F(63,64),F(1),F(2),F(64),F(3,128),F(63,128),F(127,128)):
        raw=round_fraction(x)
        for delta in (-1,0,1):add(raw+delta,'selected-table-geometry')
    for center,offset in ((F(1,8),F(49,8192)),(F(1,4),F(1,1024)),(F(1,2),F(1,256))):
        x=(center+offset)/(1-center*offset);raw=round_fraction(x)
        for delta in (-1,0,1):add(raw+delta,'directional-region-neighbours')
    require(len(jobs)<160,'selected replay widened')
    return jobs


def selected_arm():
    jobs=selected_jobs();machines={'parent':Machine(FIRMWARE,True,bootrom=ROM),'Qfplib':Machine(REFERENCE,True)}
    for label in ('control','candidate'):
        m=Machine(FIRMWARE,True,bootrom=ROM);e=ElfImage(W/(label+'.elf'));e.load(m.uc);m.elf.symbols[label+'_atan']=e.symbols['mk61_m0_atan'];machines[label]=m
    require(not any(m.rom_models for m in machines.values()),'abstract ROM callback')
    m=machines['candidate'];component=ElfImage(W/'candidate.elf');resident=ElfImage(FIRMWARE)
    code_ranges=[(s[3],s[3]+s[5])for e in (resident,component)for s in e.sections if s[2]&6==6 and s[5]]+[(0,0x4000)]
    events=Counter();current={'raw':None,'cr':0};binding=read(W/'candidate-build.json')['resident_bindings'];entries={v&~1:k for k,v in binding.items()}
    def track(uc,pc,size,user):
        require(any(lo<=pc and pc+size<=hi for lo,hi in code_ranges),'execution outside pinned resident/component/ROM '+hex(pc))
        if pc in entries:events[entries[pc]]+=1
        if pc==(binding['mk61_m0_cr_atan']&~1):current['cr']+=1
    def mmio(uc,access,address,size,value,user):
        if address>=0x40000000:require(0xd0000060<=address and address+size<=0xd000007c,'unexpected MMIO '+hex(address))
    m.uc.hook_add(UC_HOOK_CODE,track);m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,mmio)
    ref=machines['Qfplib'];reference_entries=[]
    def qref(uc,pc,size,user):
        a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32)
        b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
        require(a==current['raw']and b==0x3ff0000000000000,'audit reference not atan2(x,1)')
        reference_entries.append(True)
    ref.uc.hook_add(UC_HOOK_CODE,qref,begin=ref.elf.symbols['qfp_datan2']&~1,end=ref.elf.symbols['qfp_datan2']&~1)
    states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
    rows=[];oracles={}
    for raw,tag in jobs.items():
        want,oracle=expected(raw);oracles[f'{raw:016x}']=oracle
        for state_name,state in states.items():
            values={};counts={};depth={};current.update(raw=raw,cr=0);reference_entries.clear()
            for label in ('parent','control','candidate','Qfplib'):
                machine=machines[label];machine.stack_lowest=SP;machine.uc.mem_write(0xd0000060,state)
                name='mk61_m0_atan'if label=='parent'else'audit_atan'if label=='Qfplib'else label+'_atan'
                got,_,cost=machine.call(name,raw,count=True);after=bytes(machine.uc.mem_read(0xd0000060,28))
                if state_name=='DIRTY':require(after==state,'DIRTY context changed')
                else:require(struct.unpack('<7I',after)[6]&3==1,'READY divider not left clean/ready')
                if label!='Qfplib':require(got==want,'own interval RNE mismatch '+str((hex(raw),label,hex(got),hex(want))))
                values[label]=got;counts[label]=cost;depth[label]=SP-machine.stack_lowest
            require(values['control']==values['parent'] and counts['control']==counts['parent'],'control/resident count differs')
            require(counts['candidate']<=counts['parent'],'selected candidate regressed parent')
            require(len(reference_entries)==1,'reference adapter did not call atan2 exactlyonce')
            if tag=='historical2':
                require(values['Qfplib']==want and counts['candidate']<counts['Qfplib'],'old2 deficit remains')
                exact={'READY':(1362,1304),'DIRTY':(1548,1470)}[state_name][0 if raw==0x3fb97996f4e5f9f0 else 1]
                require(counts['candidate']==exact and counts['Qfplib']==1796,'old2 count changed')
            if tag=='remaining4-preexistingCORE':
                require(current['cr']>0 and values['Qfplib']==want and counts['candidate']>counts['Qfplib'] and counts['parent']>counts['Qfplib'],'remaining deficit hidden')
            rows.append(dict(input=f'{raw:016x}',group=tag,SIO=state_name,expected=f'{want:016x}',outputs={k:f'{v:016x}'for k,v in values.items()},instructions=counts,stack_bytes=depth,CORE_entries=current['cr']))
    report=dict(status='PASS_SELECTED_ACTUAL_ARM_AND_OWN_RATIONAL_ATAN_INTERVALS',unique_inputs=len(jobs),state_cases=len(rows),ARM_calls=4*len(rows),
        groups=dict(Counter(r['group']for r in rows)),max_candidate_stack_bytes=max(r['stack_bytes']['candidate']for r in rows),max_parent_stack_bytes=max(r['stack_bytes']['parent']for r in rows),
        old2=[r for r in rows if r['group']=='historical2'],remaining4=[r for r in rows if r['group']=='remaining4-preexistingCORE'],
        raw_NaN_policy_parent_exact=True,all_rebuilt_control_results_counts_parent_exact=True,
        DIRTY_preserved_every_call=True,READY_idle_divider_use_allowed_and_left_clean=True,PCS_R4_R11_SP_bounded_stack_by_Machine=True,
        actual_component_uses_pinned_resident_and_captured_ROM=True,abstract_ROM_callbacks=[],candidate_observed_resident_entries=dict(events),
        candidate_execution_within_pinned_code_ROM_ranges=True,candidate_MMIO_restricted_to_existing_SIO_divider=True,
        reference='Every actual audit_atan observed qfp_datan2(originalraw,1.0); no public atan reference claim',
        Qfplib_raw_wrong_answers_retained=sum(r['outputs']['Qfplib']!=r['expected']for r in rows),
        own_oracle='Exact binary64 Fraction decode; outward-rounded fixed-point alternating Taylor intervals, rational reciprocal/pi/4 reduction and Machin pi; both exact interval endpoints encode same binary64 RNE. No author oracle, MPFR or hostfloatingatan.',
        machine_sha256=sha(Q/'support/native_eabi_m0_arm_self_test.py'),candidate_ELF_sha256=sha(W/'candidate.elf'),firmware_sha256=sha(FIRMWARE),reference_sha256=sha(REFERENCE),ROM_sha256=sha(ROM),
        author_full_sweeps_repeated=False,hardware_access=False,physical_cycles_measured=False,rows=rows)
    (HERE/'SELECTED-ARM-ATAN.json').write_text(json.dumps(report,indent=2)+'\n');(HERE/'OWN-ORACLE-INTERVALS.json').write_text(json.dumps(oracles,indent=2)+'\n')
    return report


if __name__=='__main__':
    source=source_proof();bounds=local_bounds()
    if '--source-only'in sys.argv:print(json.dumps(dict(source=source['status'],bounds=bounds['status'],synthetic_packed=bounds['strict_equality_pack_acceptances']),indent=2))
    else:
        arm=selected_arm();require(pins()==source['pins'],'inputs changed during review')
        print(json.dumps({k:v for k,v in arm.items()if k not in ('rows','old2','remaining4')},indent=2))
