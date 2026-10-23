"""Independent bounded top-normal delta review; compile-only + explicit ARM emulator."""
from pathlib import Path
from collections import Counter
import hashlib,json,struct,subprocess,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]
W=ROOT/'.build/m0-mixed-sign-top-normal-20261023'
PARENT=ROOT/'.build/m0-mixed-sign-original-goal-20261023'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
FIRMWARE=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf'
REFERENCE=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
sys.path[:0]=[str(Q/'support')]
from check_stm32_vectors import ElfImage
from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_SP
SIGN=1<<63; FRAC=(1<<52)-1; INF=0x7ff0000000000000
commands=[]


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok,note):
    if not ok:raise AssertionError(note)
def run(args):
    completed=subprocess.run(list(map(str,args)),check=True,capture_output=True,text=True)
    commands.append(list(map(str,args)))
    return completed.stdout
def allocated(e):return {n:e.bytes_at(s)for n,s in e.named_sections.items()if s[2]&2 and s[1]!=8}


def symbols(e,section):
    names=e.sections[section[6]];names=e.bytes_at(names);rows=[]
    for at in range(section[4],section[4]+section[5],section[9]):
        name,value,size,info,other,index=struct.unpack_from('<IIIBBH',e.data,at)
        rows.append((e.string(names,name),value,size,info,other,index))
    return rows


def source_proof():
    require(sha(W/'result.json')=='6e4e5b7eafeea3a11eebb499860f53d1d51fe892ce47b325ae4e48ae90f7d11d','Wrong result')
    result=json.loads((W/'result.json').read_text())
    for name,row in result['artifacts'].items():
        require((W/name).stat().st_size==row['bytes']and sha(W/name)==row['sha256'],'Artifact changed '+name)
    require(sha(PARENT/'result.json')==result['parent_result_sha256'],'Parent result changed')
    source=(W/'native_eabi_m0_rp2040.S').read_text(); old=(PARENT/'native_eabi_m0_rp2040.S').read_text()
    qualification=json.loads((W/'qualification.json').read_text())
    end=source.index('mk61_m0_dadd_end:');align=source.rfind('.align 2',0,end)
    prealigned=source[:align].rstrip('\n')+'\n'*3+source[align+len('.align 2'):].lstrip('\n')
    require(hashlib.sha256(prealigned.encode()).hexdigest()==qualification['source_sha256'],'Alignment-only source ancestry failed')
    private=source.split('mk61_m0_dadd_end:',1)[0].replace('__aeabi_dadd','top_candidate_dadd').replace('__aeabi_dsub','top_candidate_dsub').replace('.text.mk61_rp2040_arithmetic','.text.m0_top_trial')+'\n#endif\n'
    require(private==(W/'candidate.S').read_text(),'Private extraction differs from final public source')
    build=json.loads((W/'build.json').read_text()); compiler=Path(build['commands'][0][0]);objdump=compiler.with_name('arm-none-eabi-objdump')
    include=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
    common=[compiler,'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-I',include,'-c']
    run(common+[W/'native_eabi_m0_rp2040.S','-o',HERE/'public.o'])
    require(sha(HERE/'public.o')==sha(W/'candidate-full.o'),'Own public object differs')
    run(common+[PARENT/'native_eabi_m0_rp2040.S','-o',HERE/'parent.o'])
    require(sha(HERE/'parent.o')==sha(W/'control-full.o'),'Own parent object differs')
    public=ElfImage(HERE/'public.o');parent=ElfImage(HERE/'parent.o');diag=ElfImage(W/'candidate.elf')
    a,b=allocated(parent),allocated(public);changed=[n for n in a if a[n]!=b[n]]
    require(set(a)==set(b)and changed==['.text.mk61_rp2040_arithmetic'],'Unexpected allocated delta')
    section=public.named_sections[changed[0]];body=b[changed[0]][:public.symbols['mk61_m0_dadd_end']]
    require(len(body)==880 and parent.symbols['mk61_m0_dadd_end']==648,'Wrong body bounds')
    require(a[changed[0]][648:]==b[changed[0]][880:],'Multiply/divide suffix differs')
    executed=(W/'candidate.bin').read_bytes()
    rel=[]
    for s in public.sections:
        if s[1]!=9 or public.sections[s[7]]!=section:continue
        table=symbols(public,public.sections[s[6]])
        for at in range(s[4],s[4]+s[5],s[9]):
            offset,info=struct.unpack_from('<2I',public.data,at)
            if offset<880:rel.append((offset,info&255,table[info>>8][0]))
    require(rel==[(14,10,'mk61_m0_dadd_slow')],'Not exactly the old fallback BL relocation')
    require(body[:14]+body[18:]==executed[:14]+executed[18:]and len(executed)==880,'Public/executed body differs outside one BL')
    hi,lo=struct.unpack_from('<2H',executed,14);s=(hi>>10)&1
    displacement=(s<<24)|((1^((lo>>13)&1)^s)<<23)|((1^((lo>>11)&1)^s)<<22)|((hi&1023)<<12)|((lo&2047)<<1)
    if s:displacement-=1<<25
    destination=0x10182000+14+4+displacement
    slow=ElfImage(FIRMWARE).symbols['mk61_m0_dadd_slow']&~1
    require(destination==slow==0x100e6e44,'Fallback target changed')
    for normal,private in (('__aeabi_dadd','top_candidate_dadd'),('__aeabi_dsub','top_candidate_dsub')):
        require((public.symbols[normal]&~1)==(diag.symbols[private]&~1)-0x10182000,'Entry offset mismatch')
    contexts=[]
    for label in ('M4_soft','M4_hard','generic_M0'):
        before,after=(ElfImage(W/(label+'-'+suffix+'.o'))for suffix in ('control','candidate'))
        require(allocated(before)==allocated(after),'M4/generic controls changed')
        contexts.append(dict(label=label,allocated_bytes=sum(map(len,allocated(after).values())),byte_equal=True,
                             scope='Revalidated sealed object contribution, not full M4 firmware'))
    undefined=[]
    for e in (parent,public):
        undefined.append(sorted({row[0]for sec in e.sections if sec[1]==2 for row in symbols(e,sec)if row[0]and row[5]==0}))
    require(undefined[0]==undefined[1],'Undefined dependency delta')
    require(qualification['candidate_ELF_sha256']==sha(W/'candidate.elf'),'Qualified diagnostic changed')
    require(sha(FIRMWARE)=='3b92d7dc30cc860c0b1f17943f1cd626f94112a98adaf165ec4f9cd300364db1'and sha(ROM)==qualification['ROM_sha256'],'Firmware/ROM ancestry')
    text=run([objdump,'-dr',HERE/'public.o']);(HERE/'public.dis').write_text(text)
    proof=dict(status='PASS_FINAL_SOURCE_OBJECT_EXECUTED_BODY',artifact_count=len(result['artifacts']),body_bytes=880,
      own_reassembly_byte_exact=True,only_body_relocation=rel,decoded_BL_target=f'{destination:08x}',
      all_other_body_bytes_equal=True,all_other_sections_and_following_kernels_equal=True,contexts=contexts,
      undefined_dependencies_equal=True,qualification_source_reconstructed_by_alignment_and_blank_only=True,
      guard='CMP1991/BHS preserves Z into BNE; maxE2046 uniquely added, ordinary sign XOR/next arithmetic overwrite changed CMP flags',
      fallback_AAPCS='20-byte entry PUSH +4-byte R3 alignment slot; call SP8-aligned; POP R3-R7/PC restores all saved registers, R3 is volatile',
      commands=commands,hardware_access=False)
    (HERE/'SOURCE-OBJECT-PROOF.json').write_text(json.dumps(proof,indent=2)+'\n')
    return qualification


def round_even(value,shift):
    if shift<=0:return value<<(-shift)
    quotient,remainder=divmod(value,1<<shift);half=1<<(shift-1)
    return quotient+(remainder>half or(remainder==half and quotient&1))


def integer_oracle(a,b,subtract):
    if subtract:b^=SIGN
    ea,eb=(a>>52)&2047,(b>>52)&2047
    if ea==2047 or eb==2047:return None
    def decode(v,e):
        mant=(v&FRAC)|(1<<52 if e else 0)
        return (-mant if v&SIGN else mant),(e-1075 if e else -1074)
    ma,pa=decode(a,ea);mb,pb=decode(b,eb);power=min(pa,pb)
    value=(ma<<(pa-power))+(mb<<(pb-power))
    if not value:return SIGN if not ma and not mb and a&SIGN and b&SIGN else 0
    sign=SIGN if value<0 else 0;value=abs(value);exponent=power+value.bit_length()-1
    if exponent< -1022:return sign|round_even(value,-1074-power)
    rounded=round_even(value,value.bit_length()-53)
    if rounded==(1<<53):rounded>>=1;exponent+=1
    if exponent>1023:return sign|INF
    return sign|((exponent+1023)<<52)|(rounded&FRAC)


def selected_arm(qualification):
    jobs={}
    def add(a,b,tag,sem_same=True):
        for op in ('dadd','dsub'):
            actual=b^(SIGN if op=='dsub'else 0)
            jobs.setdefault((op,a,actual),tag)
    maxfinite=0x7fefffffffffffff
    for x in (maxfinite,maxfinite-1,maxfinite-2):
        for y in ((1993<<52)-1,1993<<52,(1993<<52)+1):
            for a,b in ((x,y),(y,x)):
                for sign in (0,SIGN):add(a|sign,b|sign,'overflow-midpoint-and-neighbours')
    for gap in (0,1,31,32,33,52,53,54):
        a=(2046<<52)|0x23456ffffffff;b=((2046-gap)<<52)|0x876543210abcd
        for x,y in ((a,b),(b,a)):
            for sign in (0,SIGN):
                add(x|sign,y|sign,'top-alignment-and-sticky')
                if gap in (0,1,32,53,54):add(x|sign,(y|sign)^SIGN,'top-opposite-sign')
    for a,b in ((maxfinite,maxfinite),(2046<<52,2046<<52),((2046<<52)+1,2046<<52),
                (maxfinite,1<<52),(maxfinite,1),((54<<52)+1,54<<52),((55<<52)+1,55<<52),
                ((2045<<52)|FRAC,2045<<52),(0,0),(SIGN,SIGN),(INF,INF),(INF,INF|SIGN),
                (INF|1,1<<52),(INF|(1<<51)|123,1<<52)):
        add(a,b,'guard-IEEE-and-normalization-controls');add(a,b^SIGN,'guard-IEEE-and-normalization-controls')
    prior=json.loads((PARENT/'edges.json').read_text())
    legacy=[row for row in prior['rows']if row['group']=='known_slower']
    require(len(legacy)==17,'Wrong old17 case selection')
    for row in legacy:jobs[(row['operation'],int(row['x'],16),int(row['y'],16))]='old17'
    require(len(jobs)<400,'Selected replay accidentally widened')
    machine=Machine(FIRMWARE,True,stack_bytes=4096,bootrom=ROM);reference=Machine(REFERENCE,True,stack_bytes=4096)
    require(not machine.rom_models,'Abstract ROM callbacks are prohibited for this proof')
    for folder,base,prefix,names in ((PARENT,0x10180000,'old_','candidate_'),(W,0x10182000,'new_','top_candidate_')):
        e=ElfImage(folder/'candidate.elf');machine.uc.mem_write(base,(folder/'candidate.bin').read_bytes())
        for op in ('dadd','dsub'):machine.elf.symbols[prefix+op]=e.symbols[names+op]
    slow=machine.elf.symbols['mk61_m0_dadd_slow']&~1;slow_events=[]
    hook=machine.uc.hook_add(UC_HOOK_CODE,lambda uc,pc,size,user:slow_events.append(uc.reg_read(UC_ARM_REG_SP)),begin=slow,end=slow)
    state=struct.pack('<7I',17,3,17,3,5,2,3);rows=[]
    for(op,a,b),group in jobs.items():
        expected=integer_oracle(a,b,op=='dsub');values={};counts={};new_slow=None
        for label,symbol,engine in (('candidate','new_'+op,machine),('parent','old_'+op,machine),('Qfplib','qfp_'+op,reference)):
            engine.uc.mem_write(0xd0000060,state);slow_events.clear()
            got,_,cost=engine.call(symbol,a,b,count=True)
            require(bytes(engine.uc.mem_read(0xd0000060,28))==state,'SIO READY/DIRTY/context changed')
            values[label]=got;counts[label]=cost
            if label=='candidate':
                ea,eb=(a>>52)&2047,(b>>52)&2047
                should_slow=not(ea and eb and 55<=max(ea,eb)<=2046)
                require(bool(slow_events)==should_slow,'Phase guard sent an input to the wrong domain')
                require(all(sp==SP-24 and sp%8==0 for sp in slow_events),'Fallback call is not exact aligned24-byte frame')
                new_slow=bool(slow_events)
            if expected is not None and label!='Qfplib':require(got==expected,'Integer oracle mismatch '+str((op,hex(a),hex(b),label,hex(got),hex(expected))))
        if expected is None:require(values['candidate']==values['parent'],'IEEE fallback raw result changed')
        if group=='old17':require(counts['candidate']==counts['parent'],'Old17 instruction count changed')
        if group.startswith('top-')or group.startswith('overflow-'):
            if values['Qfplib']==expected:require(counts['candidate']<=counts['Qfplib'],'New top path slower than correct Qfplib on selected boundary')
        rows.append(dict(group=group,op=op,x=f'{a:016x}',y=f'{b:016x}',integer_expected=None if expected is None else f'{expected:016x}',
                         outputs={key:f'{value:016x}'for key,value in values.items()},instructions=counts,candidate_fallback=new_slow))
    machine.uc.hook_del(hook)
    proof=dict(status='PASS_SELECTED_ACTUAL_ARM_AND_INDEPENDENT_INTEGER_RNE',cases=len(rows),ARM_calls=3*len(rows),
      groups=dict(Counter(row['group']for row in rows)),rows=rows,old17_results_and_counts_unchanged=True,
      own_integer_oracle='Exact signed integer sum on a common binary lattice, one round-to-even step at binary64 normal/subnormal precision; no host float/MPFR/author oracle',
      callee_saved_SP_bounded_stack_checked_by_actual_Machine=True,exact_slow_frame_checked=True,SIO_READY_DIRTY_preserved_every_call=True,
      machine_source_sha256=sha(Q/'support/native_eabi_m0_arm_self_test.py'),ELF_parser_sha256=sha(Q/'support/check_stm32_vectors.py'),
      candidate_ELF_sha256=sha(W/'candidate.elf'),firmware_sha256=sha(FIRMWARE),ROM_sha256=sha(ROM),reference_ELF_sha256=sha(REFERENCE),
      bootrom_models=machine.rom_models,bootrom_initializers=machine.rom_initializers,hardware_access=False,physical_cycles_measured=False)
    (HERE/'SELECTED-ARM-INTEGER.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    proof=selected_arm(source_proof())
    print(json.dumps({key:value for key,value in proof.items()if key!='rows'},indent=2))
