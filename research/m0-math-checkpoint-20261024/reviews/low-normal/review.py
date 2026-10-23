"""Bounded independent low-normal/NaN delta review. No device interfaces."""
from pathlib import Path
from collections import Counter
import hashlib,importlib.util,json,struct,subprocess,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
W=ROOT/'.build/m0-add-cold-normal-20261023';PARENT=ROOT/'.build/m0-mixed-sign-top-normal-20261023'
PREVIOUS=ROOT/'.build/m0-mixed-sign-top-normal-independent-20261023'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,note):
    if not v:raise AssertionError(note)
require(sha(PREVIOUS/'FINAL-REVIEW.json')=='1fa5ec2420e2ddf1a8d8a1ca881976f4c0033f308d601dd7d99b12afad58b86f','Previous own integer proof changed')
previous_receipt=json.loads((PREVIOUS/'FINAL-REVIEW.json').read_text())
require(sha(PREVIOUS/'review.py')==previous_receipt['review_script']['sha256'],'Previous independent oracle changed')
spec=importlib.util.spec_from_file_location('independent_prior_integer',PREVIOUS/'review.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
ElfImage=prior.ElfImage;Machine=prior.Machine;SP=prior.SP
SIGN=1<<63;FRAC=(1<<52)-1;INF=0x7ff0000000000000;QUIET=1<<51
commands=[]
def run(args):
    args=list(map(str,args));result=subprocess.run(args,check=True,capture_output=True,text=True);commands.append(args);return result.stdout
def ref(p):return {'path':str(p),'sha256':sha(p)}


def source_proof():
    require(sha(W/'result.json')=='70014f74e93ddf39ff37a1001a56601c85e16dcd89a22b3e0dbbce1f3f5a5bdb','Wrong current result')
    r=json.loads((W/'result.json').read_text())
    for name,row in r['artifacts'].items():require(sha(W/name)==row['sha256']and(W/name).stat().st_size==row['bytes'],'Changed artifact '+name)
    require(sha(PARENT/'result.json')==r['parent_result_sha256'],'Parent changed')
    source=(W/'native_eabi_m0_rp2040.S').read_text();old=(PARENT/'native_eabi_m0_rp2040.S').read_text()
    qualification=json.loads((W/'qualification.json').read_text())
    require(qualification['source_sha256']==sha(W/'native_eabi_m0_rp2040.S')and qualification['candidate_ELF_sha256']==sha(W/'candidate.elf'),'Executed ancestry mismatch')
    extracted=source.split('mk61_m0_dadd_end:',1)[0].replace('__aeabi_dadd','cold_candidate_dadd').replace('__aeabi_dsub','cold_candidate_dsub').replace('.text.mk61_rp2040_arithmetic','.text.m0_cold_trial')+'\n#endif\n'
    require(extracted==(W/'candidate.S').read_text(),'Private/public extraction mismatch')
    compiler=Path(json.loads((W/'build.json').read_text())['commands'][0][0]);include=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
    common=[compiler,'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-I',include,'-c']
    run(common+[W/'native_eabi_m0_rp2040.S','-o',HERE/'public.o']);run(common+[PARENT/'native_eabi_m0_rp2040.S','-o',HERE/'parent.o'])
    require(sha(HERE/'public.o')==sha(W/'candidate-full.o')and sha(HERE/'parent.o')==sha(W/'control-full.o'),'Own public/parent assembly not byte exact')
    public,parent=ElfImage(HERE/'public.o'),ElfImage(HERE/'parent.o');a,b=prior.allocated(parent),prior.allocated(public)
    require(set(a)==set(b)and[n for n in a if a[n]!=b[n]]==['.text.mk61_rp2040_arithmetic'],'Unexpected allocated delta')
    name='.text.mk61_rp2040_arithmetic';section=public.named_sections[name]
    require(parent.symbols['mk61_m0_dadd_end']==880 and public.symbols['mk61_m0_dadd_end']==1204,'Body boundary mismatch')
    require(a[name][880:]==b[name][1204:],'Following multiply/divide changed')
    body=b[name][:1204];executed=(W/'candidate.bin').read_bytes();rel=[]
    for sec in public.sections:
        if sec[1]!=9 or public.sections[sec[7]]!=section:continue
        names=prior.symbols(public,public.sections[sec[6]])
        for at in range(sec[4],sec[4]+sec[5],sec[9]):
            offset,info=struct.unpack_from('<2I',public.data,at)
            if offset<1204:rel.append((offset,info&255,names[info>>8][0]))
    require(rel==[(90,10,'mk61_m0_dadd_slow')],'Extra/new body relocation')
    require(len(executed)==1204 and body[:90]+body[94:]==executed[:90]+executed[94:],'Executed body mismatch')
    hi,lo=struct.unpack_from('<2H',executed,90);s=(hi>>10)&1
    immediate=(s<<24)|((1^((lo>>13)&1)^s)<<23)|((1^((lo>>11)&1)^s)<<22)|((hi&1023)<<12)|((lo&2047)<<1)
    if s:immediate-=1<<25
    target=0x10183000+94+immediate
    require(target==(ElfImage(prior.FIRMWARE).symbols['mk61_m0_dadd_slow']&~1)==0x100e6e44,'Fallback target changed')
    diagnostic=ElfImage(W/'candidate.elf')
    for operation in ('dadd','dsub'):require((public.symbols['__aeabi_'+operation]&~1)==(diagnostic.symbols['cold_candidate_'+operation]&~1)-0x10183000,'Entry offset mismatch')
    contexts=[]
    for context in ('M4_soft','M4_hard','generic_M0'):
        before,after=(ElfImage(W/(context+'-'+suffix+'.o'))for suffix in ('control','candidate'))
        require(prior.allocated(before)==prior.allocated(after),'Generic/M4 contribution changed')
        contexts.append(dict(context=context,allocated_bytes=sum(map(len,prior.allocated(after).values())),equal=True))
    undefined=[]
    for e in (parent,public):undefined.append(sorted({row[0]for sec in e.sections if sec[1]==2 for row in prior.symbols(e,sec)if row[0]and row[5]==0}))
    require(undefined[0]==undefined[1],'Undefined dependency change')
    start=' // With equal signs there is no cancellation';end='.Lda_mixed_sign:'
    require(source[source.index(start):source.index(end)]==old[old.index(start):old.index(end)],'Ordinary same-sign kernel changed')
    mixed=source[source.index(end):source.index('\n.ltorg',source.index(end))].replace('.Lda_mixed_unsigned_core:\n','')
    require(mixed==old[old.index(end):old.index('\n.ltorg',old.index(end))],'Ordinary mixed kernel changed beyond new label')
    top='.Lda_top_same_start:'
    require(source[source.index(top):source.index('.Lda_low_start:')].strip()==old[old.index(top):old.index('\n.align 2\n\n.ltorg\nmk61_m0_dadd_end:')].strip(),'Top kernel changed')
    (HERE/'public.dis').write_text(run([compiler.with_name('arm-none-eabi-objdump'),'-dr',HERE/'public.o']))
    report=dict(status='PASS_EXACT_SOURCE_PUBLIC_OBJECT_EXECUTED_BODY',checked_artifacts=len(r['artifacts']),body_bytes=1204,parent_body_bytes=880,extra_bytes=324,
      relocation=rel,decoded_old_BL_target=f'{target:08x}',all_other_body_bytes_equal=True,entry_offsets_equal=True,
      following_kernels_and_other_allocated_sections_equal=True,undefined_dependencies_equal=True,ordinary_same_mixed_and_top_kernels_source_unchanged=True,
      contexts=contexts,M4_full_firmware_rebuilt=False,commands=commands,hardware_access=False)
    (HERE/'SOURCE-OBJECT-PROOF.json').write_text(json.dumps(report,indent=2)+'\n')
    return r


def expected_policy(a,b,subtract):
    effective=b^SIGN if subtract else b
    def nan(x):return(x&~SIGN)>INF
    if nan(a):return a|QUIET
    if nan(effective):return effective|QUIET
    if a&~SIGN==INF and effective&~SIGN==INF and(a^effective)&SIGN:return INF|QUIET
    if a&~SIGN==INF:return a
    if effective&~SIGN==INF:return effective
    return prior.integer_oracle(a,b,subtract)


def selected():
    from unicorn import UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_SP
    jobs={}
    def sem(a,b,tag):
        for op in ('dadd','dsub'):jobs.setdefault((op,a,b^(SIGN if op=='dsub'else 0)),tag)
    for e in (1,2,4,5,8,9,16,17,32,33,53,54):
        a=(e<<52)+1;b=(e<<52)|SIGN
        sem(a,b,'capped-budget-boundaries');sem(b,a,'capped-budget-boundaries')
        if e in (1,53,54):sem(a^SIGN,b^SIGN,'capped-negative-and-normal-transition')
    for e in (1,17,33):
        for bit in (1,16,32,48,52):sem((e<<52)+(1<<bit)-1,(e<<52)|SIGN,'normalization-chunk-widths')
    for a,b in (((2<<52),(1<<52)|FRAC),((2<<52),(1<<52)),((2<<52)+1,(1<<52)|FRAC),
                ((54<<52)|FRAC,(53<<52)+1),((54<<52)|FRAC,(53<<52)+3),((1<<52),(1<<52))):
        sem(a,b^SIGN,'adjacent-binade-subnormal-carry-and-tie');sem(b,a^SIGN,'adjacent-binade-subnormal-carry-and-tie')
    for gap in (0,1,2,31,32,33,52,53):
        a=(54<<52)|FRAC;b=((54-gap)<<52)|1
        sem(a,b,'same-sign-alignment-and-carry');sem(b|SIGN,a|SIGN,'same-sign-alignment-and-carry')
    for a,b in ((INF|1,INF|QUIET|77),(INF|QUIET|77,INF|1),
                (INF|SIGN|(1<<31),INF|QUIET|19),(INF|QUIET|19,INF|SIGN|(1<<31)),
                (1<<52,INF|SIGN|1),(INF|SIGN|1,1<<52),(INF,INF|SIGN|(1<<50)),
                (INF|QUIET|9,INF),(INF,INF),(INF,INF|SIGN),(1<<52,INF),(INF|SIGN,1<<52)):
        # Raw input order matters for NaN priority; cover dsub's effective sign.
        for op in ('dadd','dsub'):jobs[(op,a,b)]='first-NaN-payload-sign-and-Inf-policy'
    for a,b in ((0,0),(SIGN,SIGN),(1,1<<52),(FRAC,(1<<52)),(0,INF|SIGN|1)):
        for op in ('dadd','dsub'):jobs[(op,a,b)]='unchanged-E0-input-fallback'
    early=ROOT/'.build/m0-mixed-sign-original-goal-20261023'
    for row in json.loads((early/'edges.json').read_text())['rows']:
        if row['group']=='known_slower':jobs[(row['operation'],int(row['x'],16),int(row['y'],16))]='old17'
    for a,b in (((55<<52)|1,55<<52),((2045<<52)|FRAC,2045<<52),
                (0x7fefffffffffffff,(1993<<52)-1),(0x7fefffffffffffff,1993<<52),
                (0x7fefffffffffffff,(1993<<52)+1),(2046<<52,2046<<52)):
        sem(a,b,'unchanged-ordinary-top-overflow-controls');sem(a,b^SIGN,'unchanged-ordinary-top-overflow-controls')
    require(len(jobs)<=250,'Replay grew beyond selected boundaries')
    machine=Machine(prior.FIRMWARE,True,stack_bytes=4096,bootrom=prior.ROM);reference=Machine(prior.REFERENCE,True,stack_bytes=4096)
    require(not machine.rom_models,'Abstract ROM callbacks are prohibited')
    for folder,base,label,prefix in ((PARENT,0x10182000,'old_','top_candidate_'),(W,0x10183000,'new_','cold_candidate_')):
        elf=ElfImage(folder/'candidate.elf');machine.uc.mem_write(base,(folder/'candidate.bin').read_bytes())
        for op in ('dadd','dsub'):machine.elf.symbols[label+op]=elf.symbols[prefix+op]
    slow=machine.elf.symbols['mk61_m0_dadd_slow']&~1;events=[]
    hook=machine.uc.hook_add(UC_HOOK_CODE,lambda uc,pc,size,user:events.append(uc.reg_read(UC_ARM_REG_SP)),begin=slow,end=slow)
    state=struct.pack('<7I',17,3,17,3,5,2,3);rows=[]
    for(op,a,b),group in jobs.items():
        expected=expected_policy(a,b,op=='dsub');values={};cost={}
        for label,symbol,engine in (('candidate','new_'+op,machine),('parent','old_'+op,machine),('Qfplib','qfp_'+op,reference)):
            engine.uc.mem_write(0xd0000060,state);events.clear();engine.stack_lowest=SP
            got,_,instructions=engine.call(symbol,a,b,count=True)
            require(bytes(engine.uc.mem_read(0xd0000060,28))==state,'SIO context changed')
            values[label]=got;cost[label]=instructions
            if label!='Qfplib':require(got==expected,'Integer/NaN-policy mismatch '+str((group,op,hex(a),hex(b),label,hex(got),hex(expected))))
            if label=='candidate':
                fallback=((a>>52)&2047)==0 or((b>>52)&2047)==0
                require(bool(events)==fallback,'E0/normal/nonfinite dispatch mismatch')
                require(all(sp==SP-24 and sp%8==0 for sp in events),'Bad E0 fallback frame')
                if not fallback:require(engine.stack_lowest==SP-20,'New fast path used extra stack/writes')
        if group in ('old17','unchanged-ordinary-top-overflow-controls','unchanged-E0-input-fallback'):
            require(cost['candidate']==cost['parent'],'Existing control instruction cost changed')
        else:require(cost['candidate']<=cost['parent'],'New path instruction regression against parent')
        rows.append(dict(group=group,operation=op,x=f'{a:016x}',y=f'{b:016x}',expected=f'{expected:016x}',
          outputs={label:f'{value:016x}'for label,value in values.items()},instructions=cost))
    machine.uc.hook_del(hook)
    report=dict(status='PASS_SELECTED_ARM_EXACT_INTEGER_AND_RAW_NAN_POLICY',cases=len(rows),ARM_calls=3*len(rows),groups=dict(Counter(r['group']for r in rows)),rows=rows,
      oracle='Reused previous independent exact binary-lattice RNE oracle for finite values; explicit first-NaN quiet/sign/payload and infinity policy independent of author oracle/MPFR',
      reused_integer_source=ref(PREVIOUS/'review.py'),old17_and_selected_ordinary_top_E0_costs_equal=True,
      callee_saved_SP_bounded_stack_and_READY_DIRTY_checked_every_call=True,fast_frame20_and_E0_frame24_checked=True,
      candidate_ELF=ref(W/'candidate.elf'),firmware=ref(prior.FIRMWARE),ROM=ref(prior.ROM),reference_ELF=ref(prior.REFERENCE),
      Machine_source=ref(prior.Q/'support/native_eabi_m0_arm_self_test.py'),ELF_parser=ref(prior.Q/'support/check_stm32_vectors.py'),
      abstract_ROM_callbacks=machine.rom_models,bootrom_initializers=machine.rom_initializers,hardware_access=False,physical_cycles_measured=False)
    (HERE/'SELECTED-ARM-INTEGER.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    source_proof();report=selected()
    print(json.dumps({key:value for key,value in report.items()if key!='rows'},indent=2))
