"""Independent bounded sqrt dispatch review; offline reassembly and real ARM only."""
from pathlib import Path
from collections import Counter
import hashlib, importlib.util, json, math, struct, subprocess, sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
W = ROOT / '.build/m0-sqrt-cold-original-goal-20261024'
P = ROOT / '.build/m0-asin-scaled-bound-v164-20261023/source/code'
Q = ROOT / '.build/m0-float-fma-qualification-20261023'
sys.path.insert(0, str(Q / 'support'))
from check_stm32_vectors import ElfImage
from native_eabi_m0_arm_self_test import Machine, SP, STOP
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_XPSR

FIRMWARE = ROOT / '.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf'
REFERENCE = ROOT / '.build/m0-v138-execution-20261023/reference/reference.elf'
ROM = ROOT / 'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
CC = Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin/arm-none-eabi-gcc')
SIGN, FRAC, INF = 1 << 63, (1 << 52) - 1, 0x7ff0000000000000
commands = []


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(condition, detail):
    if not condition: raise AssertionError(detail)
def run(args):
    args = list(map(str, args)); commands.append(args)
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout
def allocated(e): return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8}
def nobits(e): return {n:(s[2],s[5],s[8]) for n,s in e.named_sections.items() if s[2]&2 and s[1]==8}
def symbols(e):
    rows = []
    for sec in e.sections:
        if sec[1] != 2: continue
        strings = e.bytes_at(e.sections[sec[6]])
        for at in range(sec[4], sec[4]+sec[5], sec[9]):
            name,value,size,info,other,index=struct.unpack_from('<IIIBBH', e.data, at)
            rows.append((e.string(strings,name),value,size,info,other,index))
    return rows


def check_pins():
    require(sha(W/'HANDOFF.md')=='c0fbc3e470566d0f0838c68b22b0c9c6320e146fe67eddb2b034cc9e6e46c867','handoff')
    require(sha(W/'result.json')=='4862bfacc499bec396e5eb21814de35da1759a62087c38d60bcc4e7bda688992','result')
    result=json.loads((W/'result.json').read_text())
    for name,digest in result['files'].items(): require(sha(W/name)==digest,'changed author artifact '+name)
    pins=json.loads((W/'input-pins.json').read_text())['files']
    for name,digest in pins.items(): require(sha(ROOT/name)==digest,'changed baseline '+name)
    require(sha(W/'candidate.elf')=='2662c539807c1cdbe9c728154ea0d83262c99e974729a9dbfb9ff847c1ee36d1','ELF')
    return dict(author_files=len(result['files']),baseline_pins=len(pins),all_match=True)


def source_proof():
    pins=check_pins()
    old=(P/'native_eabi_m0.S').read_text(); new=(W/'native_eabi_m0.S').read_text()
    old_start=old.index(' lsrs r3,r1,#20\n adds r2,r3,#1\n lsrs r2,#11\n', old.index('function mk61_m0_sqrt, .m0_sqrt64_fixed'))
    new_start=new.index(' lsrs r3,r1,#20\n adds r2,r3,#1\n lsrs r2,#11\n', new.index('function mk61_m0_sqrt, .m0_sqrt64_fixed'))
    require(old[:old_start]==new[:new_start] and old[old.index('.Lsqrt64_normal:\n',old_start):]==new[new.index('.Lsqrt64_normal:\n',new_start):], 'source outside entry guard changed')
    require((P/'native_eabi_m0_rp2040.S').read_bytes()==(W/'native_eabi_m0_rp2040.S').read_bytes(),'other public source changed')
    old_cold=(P/'native_eabi_m0_sqrt_special.S.inc').read_text()
    new_cold=(W/'native_eabi_m0_sqrt_special.S.inc').read_text()
    require(old_cold.split('.Lsqrt_special_subnormal:\n',1)[1]==new_cold.split('.Lsqrt_special_subnormal:\n',1)[1], 'subnormal suffix changed')
    common=[CC,'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-I',P,'-c']
    for source,out,control in (('native_eabi_m0.S','main.o','control-main.o'),('native_eabi_m0_rp2040.S','rp.o','control-rp.o')):
        run(common+[W/source,'-o',HERE/out]);run(common+[P/source,'-o',HERE/control])
        require(sha(HERE/out)==sha(W/out),'public object differs '+out)
        require(sha(HERE/control)==sha(W/control),'parent object differs '+control)
    pairs=[(ElfImage(HERE/'control-main.o'),ElfImage(HERE/'main.o')),(ElfImage(HERE/'control-rp.o'),ElfImage(HERE/'rp.o'))]
    changed=[]
    for before,after in pairs:
        a,b=allocated(before),allocated(after)
        require(set(a)==set(b) and nobits(before)==nobits(after),'sections/RAM delta')
        changed += [(n,len(a[n]),len(b[n])) for n in a if a[n]!=b[n]]
    require(changed==[('.m0_sqrt64_fixed.mk61_m0_sqrt',8544,8544),('.m0_sqrt_special',164,156)], 'unexpected changed sections '+str(changed))
    a,b=(allocated(e)['.m0_sqrt64_fixed.mk61_m0_sqrt'] for e in pairs[0])
    require(pairs[0][0].symbols['pow_sqrt64_coefficients']==pairs[0][1].symbols['pow_sqrt64_coefficients']==0x160,'table moved')
    require(a[352:]==b[352:] and a[344:352]==b'\xc0\x46'*4,'table/padding changed')
    body_a,body_b=a[20:344],b[28:352]
    diffs=[i for i in range(0,len(body_a),2) if body_a[i:i+2]!=body_b[i:i+2]]
    require(diffs==[66],'normal body changed beyond ADR')
    for block,pc in ((a,0x56),(b,0x5e)):
        insn=struct.unpack_from('<H',block,pc)[0]
        require(insn>>8==0xa4 and ((pc+4)&~3)+4*(insn&255)==352,'ADR target incorrect')
    def external(objects):
        allrows=[row for e in objects for row in symbols(e)]
        defined={r[0] for r in allrows if r[5] and r[3]>>4}
        return sorted({r[0] for r in allrows if r[0] and not r[5]}-defined)
    require(external([p[0] for p in pairs])==external([p[1] for p in pairs]),'new external dependency')
    run([CC.with_name('arm-none-eabi-ld'),'-T',W/'candidate.ld',HERE/'main.o',HERE/'rp.o','-o',HERE/'relinked.elf'])
    executed,relinked=ElfImage(W/'candidate.elf'),ElfImage(HERE/'relinked.elf')
    require(allocated(executed)==allocated(relinked) and nobits(executed)==nobits(relinked),'executed bytes relink mismatch')
    require(symbols(executed)==symbols(relinked),'executed symbols differ from own relink')
    require(not [r for r in symbols(executed) if r[0] and not r[5]],'undefined standalone symbol')
    require(not [s for s in executed.sections if s[1] in (4,9)],'standalone relocations')
    require(set(allocated(executed))=={'.sqrt_special','.sqrt','.conversion'} and not nobits(executed),'extra standalone allocation')
    require(executed.symbols['mk61_m0_sqrt']==0x1016bb01 and executed.symbols['mk61_m0_sqrt_special']==0x1016ba21 and executed.symbols['mk61_m0_sqrt_subnormal']==0x1016ba3b,'entry addresses')
    require(len(allocated(executed)['.sqrt_special'])<=0xe0 and len(allocated(executed)['.sqrt'])<=0x4500,'slot overflow')
    contexts=[]
    for context in ('generic_M0','M4_soft','M4_hard'):
        total=0
        for unit in ('main','rp'):
            control=ElfImage(W/(context+'-'+unit+'-control.o'));candidate=ElfImage(W/(context+'-'+unit+'-candidate.o'))
            require(allocated(control)==allocated(candidate) and nobits(control)==nobits(candidate),'generic/M4 allocation changed')
            total+=sum(map(len,allocated(candidate).values()))
        contexts.append(dict(context=context,allocated_bytes=total,exact=True))
    proof=dict(status='PASS_SOURCE_OBJECT_EXECUTED_ELF',pins=pins,changed_sections=changed,
       normal_code_literals_shift=8,only_normal_encoding_change='ADR R4 old+0x56/new+0x5e both address table+0x160',
       coefficient_table_bytes=8192,table_address_and_bytes_exact=True,subnormal_source_suffix_exact=True,
       own_public_objects_exact=True,own_relink_all_allocated_bytes_and_all_symbols_exact=True,own_relink_ELF_sha256=sha(HERE/'relinked.elf'),
       candidate_ELF_sha256=sha(W/'candidate.elf'),standalone_undefined=[],standalone_relocations=[],new_RAM=False,new_external_dependencies=False,
       preserved_combined_external_symbols=external([p[1] for p in pairs]),contexts=contexts,
       flags_proof='Thumb LSLS R2,R1,#1 gives C=input bit63; ORRS updates N/Z, preserves C; BNE preserves flags; BCS uses original input sign.',
       own_disassembly_sha256=None,commands=commands,hardware_access=False)
    dis=run([CC.with_name('arm-none-eabi-objdump'),'-dr',HERE/'relinked.elf']);(HERE/'relinked.dis').write_text(dis)
    proof['own_disassembly_sha256']=sha(HERE/'relinked.dis')
    (HERE/'SOURCE-OBJECT-PROOF.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def sqrt_integer(raw):
    mag=raw & (SIGN-1); e=(raw>>52)&2047; fraction=raw&FRAC
    if not mag: return raw
    if e==2047:
        if fraction or raw&SIGN: return raw|(1<<51)
        return raw
    if raw&SIGN: return 0x7ff8000000000000
    m=(1<<52)|fraction if e else fraction
    p=e-1075 if e else -1074
    k=(m.bit_length()-1+p)//2
    a=m<<(p-2*k+104); z=math.isqrt(a)
    relation=4*a-(2*z+1)**2
    if relation>0 or relation==0 and z&1: z+=1
    if z==1<<53: z>>=1;k+=1
    require(1<<52<=z<1<<53 and -1022<=k<=1023,'oracle packing domain')
    return ((k+1023)<<52)|(z&FRAC)


def encode_positive_integer_power(m,p):
    k=m.bit_length()-1; shift=k-52
    if shift>0:
        q,r=divmod(m,1<<shift); half=1<<(shift-1);q+=r>half or (r==half and q&1)
    else: q=m<<(-shift)
    if q==1<<53: q>>=1;k+=1
    return ((k+p+1023)<<52)|(q&FRAC)


def selected_arm():
    jobs={}
    def add(v,tag): jobs.setdefault(v,tag)
    for v in (0,SIGN,INF,INF|SIGN):add(v,'signed-zero-and-inf')
    for sign in (0,SIGN):
        for fraction in (1,1<<31,1<<32,1<<50,1<<51,(1<<51)|1,FRAC):add(sign|INF|fraction,'raw-NaN-sign-payload')
    for v in (1,2,3,FRAC,1<<52,0x3ff0000000000000,0x4000000080000000,0x7fefffffffffffff):add(SIGN|v,'negative-finite-sign-carry')
    for width in (1,2,16,31,32,33,48,49,50,51,52):
        for v in ((1<<(width-1))-1,1<<(width-1),(1<<(width-1))+1,(1<<width)-1):
            if v and v<=FRAC:add(v,'subnormal-width-and-neighbours')
    for e in (1,2,3,54,55,1022,1023,1024,2045,2046):
        for f in (0,1,FRAC):add((e<<52)|f,'normal-exponent-and-carry-edges')
    for cell in (0,1,127,128,254,255):
        for v in (-1,0,1):
            raw=(1023<<52)|(cell<<44)
            if raw+v>0:add(raw+v,'normal-coefficient-boundary')
    for exponent in (-500,0,500):
        for low in (0,1,2,3,0x7fffffff,0x80000000,0xffffffff,(1<<52)-2):
            root_m=(1<<52)+low
            nearest=encode_positive_integer_power((2*root_m+1)**2,2*exponent-106)
            for raw in (nearest-1,nearest,nearest+1):add(raw,'normal-squared-midpoint-neighbours')
    require(len(jobs)<250,'compact replay accidentally widened')
    candidate=Machine(W/'candidate.elf',True,stack_bytes=32)
    parent=Machine(FIRMWARE,True,stack_bytes=4096,bootrom=ROM)
    reference=Machine(REFERENCE,True,stack_bytes=4096)
    require(not candidate.rom_models and not candidate.rom_initializers and not parent.rom_models,'abstract ROM callbacks')
    ranges=[(s[3],s[3]+s[5]) for s in candidate.elf.sections if s[2]&2]
    calls={'raw':None,'special':[],'subnormal':[],'accesses':Counter()}
    def within(address,size): return any(lo<=address and address+size<=hi for lo,hi in ranges)
    def memory(uc,access,address,size,value,user):
        require(SP-32<=address and address+size<=SP or (access==16 and within(address,size)), 'candidate nonstack/nonallocated memory '+hex(address))
        calls['accesses']['read' if access==16 else 'write']+=1
    def code(uc,pc,size,user):require(within(pc,size),'candidate escaped standalone allocated code '+hex(pc))
    def special(uc,pc,size,user):
        raw=calls['raw'];carry=(uc.reg_read(UC_ARM_REG_XPSR)>>29)&1
        require(carry==raw>>63 and uc.reg_read(UC_ARM_REG_R3)==raw>>52 and uc.reg_read(UC_ARM_REG_SP)==SP,'cold input/sign/stack contract')
        require((uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32))==raw,'cold rawinput changed')
        calls['special'].append(carry)
    def subnormal(uc,pc,size,user):
        require(calls['raw']>>52==0 and calls['raw']!=0 and uc.reg_read(UC_ARM_REG_R3)==0 and uc.reg_read(UC_ARM_REG_SP)==SP,'alias input contract')
        calls['subnormal'].append(True)
    candidate.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,memory)
    candidate.uc.hook_add(UC_HOOK_CODE,code)
    for name,fn in (('mk61_m0_sqrt_special',special),('mk61_m0_sqrt_subnormal',subnormal)):
        address=candidate.elf.symbols[name]&~1;candidate.uc.hook_add(UC_HOOK_CODE,fn,begin=address,end=address)
    rows=[]
    for raw,tag in jobs.items():
        values={};counts={};depths={};expected=sqrt_integer(raw)
        calls['raw']=raw;calls['special']=[];calls['subnormal']=[]
        state=struct.pack('<7I',17,3,17,3,5,2,1 if len(rows)%2 else 3)
        for label,engine,name in (('candidate',candidate,'mk61_m0_sqrt'),('parent',parent,'mk61_m0_sqrt'),('Qfplib',reference,'qfp_dsqrt')):
            engine.uc.mem_write(0xd0000060,state);engine.stack_lowest=SP
            got,_,cost=engine.call(name,raw,count=True)
            require(bytes(engine.uc.mem_read(0xd0000060,28))==state,'SIO context changed')
            values[label]=got;counts[label]=cost;depths[label]=SP-engine.stack_lowest
            if label!='Qfplib':require(got==expected,'own integer oracle '+str((hex(raw),label,hex(got),hex(expected))))
        e=(raw>>52)&2047;mag=raw&(SIGN-1)
        cold=bool(mag and (raw&SIGN or e==2047));sub=bool(mag and not raw&SIGN and e==0)
        require(bool(calls['special'])==cold and bool(calls['subnormal'])==sub,'wrong dispatch')
        saving=3 if cold else 2 if sub else 0
        require(counts['parent']-counts['candidate']==saving,'unexpected cost delta '+hex(raw))
        require(depths['candidate']==(28 if sub else 0 if cold or not mag else 20),'stack depth changed')
        rows.append(dict(group=tag,input=f'{raw:016x}',integer_expected=f'{expected:016x}',outputs={k:f'{v:016x}'for k,v in values.items()},instructions=counts,stack_bytes=depths,cold_carry=calls['special'],subnormal_alias=bool(calls['subnormal'])))
    inf=next(row for row in rows if row['input']=='7ff0000000000000')
    require(inf['instructions']==dict(candidate=12,parent=15,Qfplib=12),'positive infinity target not achieved')
    correct_q=[r for r in rows if r['outputs']['Qfplib']==r['integer_expected']]
    require(all(r['instructions']['candidate']<=r['instructions']['Qfplib'] for r in correct_q),'slower selected bit-correct Qfplib case')
    proof=dict(status='PASS_SELECTED_REAL_ARM_INTEGER_SQRT_RNE',cases=len(rows),ARM_calls=3*len(rows),groups=dict(Counter(r['group']for r in rows)),
       positive_infinity_instructions=inf['instructions'],raw_NaN_policy_parent_exact=True,positive_normal_and_signed_zero_cost_parent_exact=True,
       subnormal_saves=2,other_nonzero_cold_saves=3,first_cold_C_equals_input_sign_checked_every_entry=True,
       callee_saved_R4_R11_SP_checked_every_call=True,max_candidate_stack_bytes=max(r['stack_bytes']['candidate']for r in rows),
       candidate_memory_reads_only_allocated_or_stack=True,candidate_writes_only_stack32=True,no_candidate_SIO_or_ROM_access=True,
       SIO_READY_DIRTY_preserved_every_call=True,candidate_code_contained_in_standalone_ELF=True,candidate_abstract_ROM_callbacks=[],
       correct_Qfplib_cases=len(correct_q),Qfplib_raw_wrong_answers_retained=len(rows)-len(correct_q),slower_than_bit_correct_Qfplib=0,
       own_oracle='Exact binary64 decode M*2^p; integer isqrt of M<<scale; compare 4A against (2floor(sqrt(A))+1)^2 then one RNE step. No float/MPFR/author oracle. Signedzero and prior raw NaN quiet/sign policy explicit.',
       machine_source_sha256=sha(Q/'support/native_eabi_m0_arm_self_test.py'),ELF_parser_sha256=sha(Q/'support/check_stm32_vectors.py'),
       candidate_ELF_sha256=sha(W/'candidate.elf'),firmware_sha256=sha(FIRMWARE),ROM_sha256=sha(ROM),reference_ELF_sha256=sha(REFERENCE),
       parent_ROM_initializers=parent.rom_initializers,physical_cycles_measured=False,hardware_access=False,rows=rows)
    (HERE/'SELECTED-ARM-INTEGER.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    source=source_proof()
    if '--source-only' in sys.argv: print(json.dumps(source,indent=2))
    else:
        arm=selected_arm();require(check_pins()==source['pins'],'inputs changed during review')
        print(json.dumps({k:v for k,v in arm.items()if k!='rows'},indent=2))
