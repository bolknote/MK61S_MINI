"""Narrow independent residual-helper review; no hardware or project mutations."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import datetime, hashlib, importlib.util, json, re, struct, subprocess, sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]
W=ROOT/'.build/m0-atan-residual-original-goal-20261024'
PARENT=ROOT/'.build/m0-atan-original-goal-20261024'
PRIOR=ROOT/'.build/m0-atan-original-goal-independent-20261024'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(value,message):
    if not value:raise AssertionError(message)
def read(p):return json.loads(Path(p).read_text())
def put(name,value):(HERE/name).write_text(json.dumps(value,indent=2)+'\n')
def pins():
    require(sha(W/'HANDOFF.md')=='650a6f36fc02c71671085fc3ab335aff4654a8b282b59c0267a5df02f9cc5146','handoff changed')
    require(sha(W/'result.json')=='e047da61a015906cac349efa0331625bd625c53a7e42de622fb94268225d669c','author result changed')
    files=read(W/'result.json')['files'];inputs=read(W/'input-pins.json')['files']
    for name,digest in files.items():require(sha(W/name)==digest,'author file changed: '+name)
    for name,digest in inputs.items():require(sha(ROOT/name)==digest,'input changed: '+name)
    require(sha(PRIOR/'review.py')=='d7961d6a055b3a78b0e5629ad2b3fc5b97344b8557ccc03fc47fb624a96d1a56','prior independent oracle changed')
    return dict(author_files=len(files),pinned_inputs=len(inputs),all_match=True)

INITIAL=pins()
spec=importlib.util.spec_from_file_location('prior_independent_atan',PRIOR/'review.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
ElfImage=old.ElfImage;Machine=old.Machine;SP=old.SP
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3

def source_proof():
    commands=[]
    def run(argv):
        commands.append(list(map(str,argv)))
        return subprocess.run(argv,capture_output=True,text=True,check=True).stdout
    source=(W/'native_eabi_m0_atan_fast.inc').read_text();parent=(PARENT/'native_eabi_m0_atan_fast.inc').read_text()
    # Reverse the explicit new helper/pack edits, then compare the entire include.
    marker='// top/den has at most six quotient bits.'
    begin=source.index(marker);end=source.index('// Pack the bounded atan domain',begin)
    restored=source[:begin]+source[end:]
    restored=restored.replace('U h,U numerator,U denominator,U sign,U &result)',
                              'U h,uint32_t numerator_high,U sign,U &result)')
    restored=restored.replace('  const uint32_t numerator_high=uint32_t(numerator>>32);\n','')
    restored=restored.replace('  const uint32_t half=1U<<(shift-1);\n  uint32_t tail=uint32_t(q.low)&((half<<1)-1);',
                              '  const uint32_t half=1U<<(shift-1),tail=uint32_t(q.low)&((half<<1)-1);')
    start=restored.index('      if(distance73<radius73) {\n        if(normalization>=5')
    end=restored.index('\n      }',start)+len('\n      }')
    restored=restored[:start]+'      if(distance73<radius73) return false;'+restored[end:]
    restored=restored.replace('h,numerator,denominator,sign,result)','h,uint32_t(numerator>>32),sign,result)')
    require(restored==parent,'source edits outside new residual helper/pack branch')
    for name in ('native_eabi_m0.cpp','native_eabi_m0_atan.inc'):
        require((W/name).read_bytes()==(PARENT/name).read_bytes(),'other translation source changed '+name)
    build=read(W/'candidate-build.json');cmd=list(build['commands'][-2]);link=list(build['commands'][-1])
    require(cmd[0].endswith('arm-none-eabi-g++') and link[0].endswith('arm-none-eabi-ld'),'tool binding')
    cmd[cmd.index('-o')+1]=str(HERE/'candidate-full.o');run(cmd)
    require(sha(HERE/'candidate-full.o')==sha(W/'candidate-full.o')=='163cfa097f5df1a28b6d62dba7bd927d7c7ebf0aa11327ceafd369b90182f02e','own full object differs')
    link[link.index(str(W/'candidate-full.o'))]=str(HERE/'candidate-full.o');link[link.index('-o')+1]=str(HERE/'candidate.elf');run(link)
    require(sha(HERE/'candidate.elf')==sha(W/'candidate.elf')=='f7c4c88bd931f48b97e361528d9d9fa78301a2eaf8a0165d543f6c0d49c49a35','whole relink differs')
    a,b=ElfImage(W/'control-full.o'),ElfImage(HERE/'candidate-full.o')
    require(sha(W/'control-full.o')==sha(PRIOR/'candidate-full.o'),'control is not accepted parent')
    aa,bb=old.allocated(a),old.allocated(b)
    added={n:len(bb[n])for n in set(bb)-set(aa)}
    changed={n:(len(aa[n]),len(bb[n]))for n in set(aa)&set(bb)if aa[n]!=bb[n]}
    require(not set(aa)-set(bb) and added=={'.text.unlikely.atan_fast_tail_repair':344} and changed=={'.text.atan_fast':(1648,1748)},'other allocated code/data changed')
    require(old.nobits(a)==old.nobits(b) and old.undefined(a)==old.undefined(b),'new RAM or dependency')
    # Relocatable symbols use section-relative zero addresses: compare their
    # named sections, rather than the prior linked-image address lookup.
    for name in ('atan_fast_ratio','atan_fast_reciprocal'):
        require(aa['.text.'+name]==bb['.text.'+name],'ratio changed '+name)
    contexts=[]
    for context in ('generic_M0','M4_soft','M4_hard'):
        ca,cb=(ElfImage(W/(context+'-'+v+'.o'))for v in ('control','candidate'))
        require(old.allocated(ca)==old.allocated(cb) and old.nobits(ca)==old.nobits(cb),'off-target changed')
        contexts.append(dict(context=context,allocated_bytes=sum(map(len,old.allocated(ca).values())),exact=True))
    bindings=build['resident_bindings'];resident=ElfImage(old.FIRMWARE)
    require(bindings==read(W/'control-build.json')['resident_bindings'],'resident dependencies differ')
    require(all(resident.symbols[n]==v for n,v in bindings.items()),'resident binding not actual ELF')
    assignments={n:int(v,16)for n,v in re.findall(r'(?m)^(\w+) = (0x[0-9a-f]+);',(W/'candidate.ld').read_text())}
    require(assignments==bindings,'linker assignments differ')
    image=ElfImage(HERE/'candidate.elf');parent_image=ElfImage(W/'control.elf')
    require(set(old.allocated(image))=={'.text','.rodata'} and not old.nobits(image),'component global RAM')
    require(old.allocated(image)['.rodata']==old.allocated(parent_image)['.rodata'] and len(old.allocated(image)['.rodata'])==780,'table changed')
    require(all(0x10185000<=s[3]<s[3]+s[5]<=0x10188000 for s in image.sections if s[2]&2),'component extent')
    require(all(not 0x10185000<=(v&~1)<0x10188000 for v in bindings.values()),'resident overlap')
    cc=Path(cmd[0]).parent
    dis=run([str(cc/'arm-none-eabi-objdump'),'-d','--disassemble=atan_fast_tail_repair',str(HERE/'candidate.elf')])
    require('<atan_fast_tail_repair>:' in dis and not re.search(r'\tblx?\s',dis),'helper has a dependency/call')
    (HERE/'helper.dis').write_text(dis)
    ref=ElfImage(old.REFERENCE)
    prior_ref=read(PRIOR/'SOURCE-OBJECT-PROOF.json')
    require(old.body(ref,'audit_atan',18).hex()==prior_ref['reference_adapter_hex'],'atan2 adapter changed')
    report=dict(status='PASS_FULL_PUBLIC_SOURCE_OBJECT_ENTIRE_ELF_AND_DEPENDENCIES',source_sha256=sha(W/'native_eabi_m0_atan_fast.inc'),
        entire_own_object_sha256=sha(HERE/'candidate-full.o'),entire_own_ELF_sha256=sha(HERE/'candidate.elf'),
        accepted_parent_review_sha256=sha(PRIOR/'FINAL-REVIEW.json'),exact_source_reverse_reconstructs_parent=True,
        changed_sections=changed,added_sections=added,total_allocated_delta=444,global_RAM_tables_and_undefined_dependencies_unchanged=True,
        atan_table_bytes=780,atan_table_sha256=hashlib.sha256(old.allocated(image)['.rodata']).hexdigest(),
        helper_has_no_BL_or_BLX=True,contexts=contexts,resident_bindings=bindings,commands=commands,
        fixture_uses_pinned_resident_helpers_and_captured_ROM=True,reference_is_unchanged_audit_atan_qfp_datan2_x_1=True,
        no_whole_M4_or_firmware_or_hardware_qualification=True)
    put('SOURCE-OBJECT-PROOF.json',report);return report

def bounds():
    S=1<<70;half=F(1,2)
    first=F(17,2)+F(1,1<<14);second=first*first/(1<<30)+half+F(1,1<<22);c=second+1;B=4*c*c+3
    require(B==F(read(PARENT/'certificate.json')['reciprocal_error']),'reciprocal premise')
    # Same independently reviewed fixed-point polynomial operations; no author certificate function is executed.
    def polynomial(h):
        square=half+F(13,512);cube=square+h*square
        fifth=half+h*h*cube+h**3*square+cube*square/S+((1<<17)-1)*(S*h*h+square)/S+((1<<24)-1)*(S*h**3+cube)/S
        seventh=half+h*h*fifth+h**5*square+fifth*square/S+7*(S*h*h+square)/S+((1<<24)-1)*(S*h**5+fifth)/S
        c5=F(0xcccccccd,1<<31);c7=F(2454267027,1<<34)
        fifth_term=fifth/5+F(7,5)+(c5-F(8,5))*(S*h**5+fifth)/8+half
        seventh_term=c7*seventh+max(3*c7+(c7-F(1,7))*S*h**7,1-3*c7)
        return half+half+cube/3+fifth_term+seventh_term+S*h**9/(9*(1-h*h))
    ratio=F(13,2)+B;cap=F((1<<62)+(1<<40),S)
    require(ratio<19<33 and 33*((1<<64)-1)<1<<70,'signed residual domain')
    # With T=2^38, D/T=d0+b and |R|/T=r0+a; 0<=a,b<1.
    # q0=floor(r0/d0)<=33; true quotient - q0=(r0%d0+a-q0*b)/(d0+b).
    require((1<<59)//(1<<38)==1<<21,'minimum denominator')
    quotient_error=1+F(34,1<<20)  # conservative, including either sign
    error=polynomial(cap)+quotient_error+33*(cap+F(33,S))**2
    require(error==F(read(W/'certificate.json')['total_error']) and error<6,'repair enclosure differs/insufficient')
    require(33*(1<<26)<1<<32 and ((1<<26)-1)<<5<1<<32,'bounded divider overflow')
    # Exact admitted interval check at +/-6, neighboring rejected ties, both
    # retained parities and a significand carry. Retained quantum is unchanged.
    accepted=declined=0
    for base in (-5,-1):
      for lower in (0,1):
       exponent=base-lower;shift=base+18-lower;halfstep=1<<(shift-1)
       for retained in (1<<52,(1<<52)+1,(1<<53)-1):
        for old_tail in (-53,-6,-5,0,5,6,53):
         for delta in (-33,-1,0,1,33):
          tail=halfstep+old_tail+delta
          require(0<tail<(halfstep<<1),'repair crossed retained quantum')
          if abs(tail-halfstep)<6:declined+=1;continue
          quantum=(retained<<shift)+tail
          want=((exponent+1022)<<52)+retained+int(tail>halfstep)
          require(old.round_fraction(F(quantum-6,S),1)==want==old.round_fraction(F(quantum+6,S),-1),'admitted repair interval crosses RNE cell')
          accepted+=1
    report=dict(status='PASS_INDEPENDENT_EXACT_FRACTION_RESIDUAL_AND_ROUNDING_BOUND',ratio_error_Q70=str(ratio),ratio_error_strictly_below_33=True,
        polynomial_and_table_Q70=str(polynomial(cap)),signed_quotient_error_bound=str(quotient_error),curvature_error=str(33*(cap+F(33,S))**2),
        total_error_Q70=str(error),total_error_float=float(error),strict_radius=6,
        signed71_reason='|R|<33D<2^70; low64 plus signed low7 high bits uniquely recover R modulo2^71. 32-bit high-high product is sufficient modulo2^32.',
        divider_reason='D0>=2^21, D0<2^26; R0<33(D0+1); q0<=33. Six iterations choose bits32,16,8,4,2,1; CMP/SUB preserve borrow as ADC carry; no zero divisor/shift overflow.',
        geometry_reason='Only non-inverted e=-5..-1 reaches repair: normalization=e+5<5. Nearest1/64 selection gives N<<normalization=2^69*|x-index/64|<=2^62. No denominator halving; inherited ratio error<=6.5+B.',
        tail_reason='Pre-repair midpoint distance<426/8=53.25; |delta|<=33; minimum half1024. Retained bits and binade cannot change. distance>=6 accepts only one RNE cell; smaller/tie retains old fallback.',
        admitted_synthetic_intervals=accepted,declined_near_ties=declined,large_author_sweeps_repeated=False)
    put('EXACT-RESIDUAL-BOUND.json',report);return report

STATES={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}

def helper_arm():
    image=ElfImage(HERE/'candidate.elf');m=Machine(old.FIRMWARE,True,bootrom=old.ROM);image.load(m.uc)
    name=next(n for n in image.symbols if n.startswith('atan_fast_tail_repair'));start=image.symbols[name]&~1;size=image.sizes[name]
    require(size==344,'helper extent');m.elf.symbols['repair']=image.symbols[name]
    def code(uc,pc,n,user):require(start<=pc and pc+n<=start+size,'helper called outside its bounded body')
    def mmio(uc,access,address,n,value,user):require(address<0x40000000,'helper accessed MMIO')
    m.uc.hook_add(UC_HOOK_CODE,code);m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,mmio)
    cases=set();cap=(1<<62)+(1<<40)
    for d in (1<<59,(1<<59)+1,(1<<59)+(1<<38)-1,(1<<60)-1,(1<<63)+1,(1<<64)-1):
      for n in (0,1,d//4-1,d//4+d//(1<<24)):
       H=F(n<<64,d);floor=H.numerator//H.denominator
       for offset in (-32,-31,-16,-1,0,1,16,31,32,33):
        h=floor+offset
        if 0<=h<=cap and abs(H-h)<33:cases.add((n,d,h))
    # One exact modular construction supplies the q=33 truncation boundary.
    d=(1<<59)+(1<<38)-1;inverse=pow(1<<64,-1,d)
    extra=None
    for gap in range(1,65):
        n=((d-gap)*inverse)%d
        if n<=d//4:
            H=F(n<<64,d);floor=H.numerator//H.denominator
            if ((abs((n<<64)-(floor-32)*d)>>38)//(d>>38))==33:
                extra=(n,d,floor);break
    require(extra is not None,'did not construct exact q33 boundary')
    n,d,floor=extra
    for offset in range(-32,34):
        h=floor+offset
        if 0<=h<=cap and abs(F(n<<64,d)-h)<33:cases.add((n,d,h))
    rows=[];quotients=set();max_error=F(0);max_stack=0;zero_low_negative=False
    for n,d,h in sorted(cases):
      residual=(n<<64)-h*d;want=(abs(residual)>>38)//(d>>38);want=-want if residual<0 else want
      for state_name,state in STATES.items():
        m.stack_lowest=SP;m.uc.mem_write(0xd0000060,state)
        raw,_,cost=m.call('repair',n,d,c=h,count=True);delta=raw&0xffffffff;delta=delta-(1<<32)if delta>>31 else delta
        require(delta==want and abs(delta)<=33,'actual helper vs exact unbounded residual/truncated division')
        error=abs(F(delta)-(F(n<<64,d)-h));require(error<1+F(34,1<<20),'helper error enclosure')
        require(bytes(m.uc.mem_read(0xd0000060,28))==state,'helper changed SIO')
        max_error=max(max_error,error);max_stack=max(max_stack,SP-m.stack_lowest);quotients.add(abs(delta))
        if residual<0 and not residual&((1<<64)-1):zero_low_negative=True
        rows.append(dict(n=f'{n:016x}',d=f'{d:016x}',h=f'{h:016x}',SIO=state_name,delta=delta,instructions=cost,error=str(error),stack_bytes=SP-m.stack_lowest))
    require(quotients==set(range(34)) and zero_low_negative,'missing quotient or two-word negation carry boundary')
    report=dict(status='PASS_SELECTED_ACTUAL_ARM_HELPER_EXACT_FRACTION',triples=len(cases),ARM_calls=len(rows),maximum_error=str(max_error),maximum_stack_bytes=max_stack,
        quotient_magnitudes=sorted(quotients),negative_low64_zero_carry_covered=True,helper_code_self_contained=True,no_MMIO_read_or_write=True,
        READY_DIRTY_exact_every_call=True,PCS_R4_R11_SP_and_bounded_stack_checked=True,candidate_ELF_sha256=sha(HERE/'candidate.elf'),rows=rows)
    put('SELECTED-HELPER-ARM.json',report);return report

def public_jobs():
    jobs={}
    def add(raw,tag):jobs.setdefault(raw,tag)
    for raw in (0x3fe5d1004fc925b6,0xbfe5d1004fc925b6,0x3fecb99548f4fa32,0xbfecb99548f4fa32):
        add(raw,'hard4')
        for delta in (-1,1):add(raw+delta,'hard4-neighbour')
    for raw in (0x3fb97996f4e5f9f0,0xbfdd440162570130):add(raw,'old2')
    for row in read(W/'speed-proof.json')['remaining_rows']:add(int(row['x'],16),'remaining11')
    for raw in (0,old.SIGN,1,old.SIGN|1,old.FRAC,old.SIGN|old.FRAC,old.INF,old.INF|old.SIGN,old.INF|1,old.INF|(1<<51)|0x123,old.SIGN|old.INF|0x80000000,old.SIGN|old.INF|old.FRAC):add(raw,'special')
    for exponent in (-6,-5,0,6):
      raw=(exponent+1023)<<52
      for delta in (-1,0,1):
       for sign in (0,old.SIGN):add((raw+delta)|sign,'dispatch-edge')
    center=F(1,2);hcap=F(1,256)+F(1,1<<30);x=(center+hcap)/(1-center*hcap);raw=old.round_fraction(x)
    for delta in (-1,0,1):
        for sign in (0,old.SIGN):add((raw+delta)|sign,'hcap-edge')
    require(len(jobs)<80,'public subset widened')
    return jobs

def public_arm():
    machines={'V164':Machine(old.FIRMWARE,True,bootrom=old.ROM),'Qfplib':Machine(old.REFERENCE,True)}
    for label,file in (('parent',W/'control.elf'),('candidate',HERE/'candidate.elf')):
        m=Machine(old.FIRMWARE,True,bootrom=old.ROM);image=ElfImage(file);image.load(m.uc);m.elf.symbols[label]=image.symbols['mk61_m0_atan'];machines[label]=m
    require(not any(m.rom_models for m in machines.values()),'abstract ROM callback')
    image=ElfImage(HERE/'candidate.elf');resident=ElfImage(old.FIRMWARE);bindings=read(W/'candidate-build.json')['resident_bindings']
    ranges=[(s[3],s[3]+s[5])for e in (image,resident)for s in e.sections if s[2]&6==6 and s[5]]+[(0,0x4000)]
    helper=image.symbols[next(n for n in image.symbols if n.startswith('atan_fast_tail_repair'))]&~1
    current=dict(raw=0,repair=0,CORE=0,reference=0);events=Counter();entries={v&~1:k for k,v in bindings.items()}
    def code(uc,pc,n,user):
        require(any(lo<=pc and pc+n<=hi for lo,hi in ranges),'candidate escaped pinned code/ROM')
        if pc==helper:current['repair']+=1
        if pc==bindings['mk61_m0_cr_atan']&~1:current['CORE']+=1
        if pc in entries:events[entries[pc]]+=1
    def mmio(uc,access,address,n,value,user):
        if address>=0x40000000:require(0xd0000060<=address and address+n<=0xd000007c,'unexpected candidate MMIO')
    m=machines['candidate'];m.uc.hook_add(UC_HOOK_CODE,code);m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,mmio)
    ref=machines['Qfplib']
    def reference(uc,pc,n,user):
        a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32);b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
        require(a==current['raw'] and b==0x3ff0000000000000,'reference is not actual atan2(x,1)');current['reference']+=1
    ref.uc.hook_add(UC_HOOK_CODE,reference,begin=ref.elf.symbols['qfp_datan2']&~1,end=ref.elf.symbols['qfp_datan2']&~1)
    prior_rows={(r['input'],r['SIO']):r for r in read(PRIOR/'SELECTED-ARM-ATAN.json')['rows']}
    author_hard={(r['x'].lower(),r['SIO']):r for r in read(W/'result.json')['hard4']}
    author_remaining={(r['x'].lower(),r['SIO']):r for r in read(W/'speed-proof.json')['remaining_rows']}
    rows=[];oracles={};parent_checks=0
    for raw,tag in public_jobs().items():
      want,oracle=old.expected(raw);oracles[f'{raw:016x}']=oracle
      for state_name,state in STATES.items():
        current.update(raw=raw,repair=0,CORE=0,reference=0);outputs={};counts={};depth={}
        for label,m in machines.items():
            m.stack_lowest=SP;m.uc.mem_write(0xd0000060,state)
            symbol='mk61_m0_atan'if label=='V164'else'audit_atan'if label=='Qfplib'else label
            got,_,cost=m.call(symbol,raw,count=True);after=bytes(m.uc.mem_read(0xd0000060,28))
            if state_name=='DIRTY':require(after==state,'DIRTY SIO changed')
            else:require(struct.unpack('<7I',after)[6]&3==1,'READY SIO not left clean')
            if label!='Qfplib':require(got==want,'own rational RNE oracle differs '+str((hex(raw),label,hex(got),hex(want))))
            outputs[label]=f'{got:016x}';counts[label]=cost;depth[label]=SP-m.stack_lowest
        require(current['reference']==1,'actual atan2 reference not observed once')
        key=(f'{raw:016x}',state_name)
        if key in prior_rows:
            prior=prior_rows[key];require(outputs['parent']==prior['outputs']['candidate'] and counts['parent']==prior['instructions']['candidate'],'accepted parent result/count changed');parent_checks+=1
        if tag=='hard4':
            author=author_hard[key]
            require(outputs['Qfplib']==f'{want:016x}' and counts['candidate']<counts['Qfplib'],'hard4 win absent')
            require(counts['candidate']==author['instructions']['candidate'] and counts['Qfplib']==author['instructions']['Qfplib'],'hard4 actual count differs')
            require(current['repair']==1 and current['CORE']==0,'hard4 wrong route')
        if tag=='remaining11':
            author=author_remaining[key]
            require(outputs['Qfplib']==f'{want:016x}' and counts['candidate']>counts['Qfplib'] and counts['parent']>counts['Qfplib'],'preexisting remaining deficit hidden')
            require(all(counts[k]==author['instructions'][k]for k in ('candidate','parent','Qfplib')),'remaining actual count differs')
        rows.append(dict(input=f'{raw:016x}',group=tag,SIO=state_name,expected=f'{want:016x}',outputs=outputs,instructions=counts,stack_bytes=depth,repair_entries=current['repair'],CORE_entries=current['CORE']))
    report=dict(status='PASS_COMPACT_PUBLIC_ACTUAL_ARM_WITH_OWN_RATIONAL_ORACLE',unique_inputs=len(public_jobs()),state_cases=len(rows),ARM_calls=len(rows)*4,
        groups=dict(Counter(r['group']for r in rows)),parent_result_and_instruction_controls_checked=parent_checks,
        maximum_candidate_stack=max(r['stack_bytes']['candidate']for r in rows),maximum_parent_stack=max(r['stack_bytes']['parent']for r in rows),
        hard4=[r for r in rows if r['group']=='hard4'],remaining11=[r for r in rows if r['group']=='remaining11'],
        selected_vs_parent=dict(Counter('faster'if r['instructions']['candidate']<r['instructions']['parent']else'equal'if r['instructions']['candidate']==r['instructions']['parent']else'slower'for r in rows)),
        selected_parent_instruction_deltas=dict(Counter(str(r['instructions']['candidate']-r['instructions']['parent'])for r in rows)),
        own_oracle='Reused pinned independent outward-rounded exact Fraction Taylor/Machin/reciprocal intervals; both endpoints uniquely binary64 RNE. NaN policy parent raw sign/payload.',
        raw_incorrect_Qfplib_outcomes_retained=sum(r['outputs']['Qfplib']!=r['expected']for r in rows),
        actual_reference='Unchanged audit_atan observes actual qfp_datan2(original_raw,1.0); not a standalone public atan API',
        DIRTY_preserved_every_call=True,READY_divider_use_allowed_and_left_clean=True,PCS_R4_R11_SP_and_bounded_stack_checked=True,
        actual_pinned_resident_and_captured_ROM=True,abstract_ROM_callbacks=[],candidate_resident_entries=dict(events),
        code_extent_checked=True,MMIO_only_existing_SIO_divider=True,physical_cycles_measured=False,rows=rows)
    put('SELECTED-PUBLIC-ARM.json',report);put('OWN-ORACLE-INTERVALS.json',oracles);return report

if __name__=='__main__':
    choice=sys.argv[1]if len(sys.argv)>1 else 'all'
    reports={}
    if choice in ('all','source'):reports['source']=source_proof()['status']
    if choice in ('all','bounds'):reports['bounds']=bounds()['status']
    if choice in ('all','helper'):
        r=helper_arm();reports['helper']=dict(status=r['status'],calls=r['ARM_calls'])
    if choice in ('all','public'):
        r=public_arm();reports['public']=dict(status=r['status'],calls=r['ARM_calls'])
    require(pins()==INITIAL,'pins changed after execution')
    print(json.dumps(reports,indent=2),flush=True)
