"""Narrow independent small-h atan gate proof. No device APIs or promotion."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import ast,hashlib,importlib.util,json,re,struct,subprocess,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
W=ROOT/'.build/m0-atan-tight-ninth-20261024'
P=ROOT/'.build/m0-atan-directional-ninth-20261024'
PRIOR=ROOT/'.build/m0-atan-directional-ninth-independent-20261024'
S=1<<70;MASK=(1<<64)-1
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def put(n,v):(HERE/n).write_text(json.dumps(v,indent=2)+'\n')
def require(v,m):
    if not v:raise AssertionError(m)
def pins():
    require(sha(W/'HANDOFF.md')=='bfb2a8aa2db8d23b5a4f543ff9f5ac954f0cb0895cefcd41fa8077f4ee3be982','handoff')
    require(sha(W/'result.json')=='9af6b56537f17bfb9937182ef55ea1e6a3a361670d99db895049b95003def35e','result')
    for n,h in read(W/'result.json')['files'].items():require(sha(W/n)==h,'author '+n)
    for n,h in read(W/'input-pins.json')['files'].items():require(sha(ROOT/n)==h,'input '+n)
    require(sha(PRIOR/'FINAL-REVIEW.json')=='67bc49a1d7c2bc717bce9dfd9f046d3fca1f2c49e84561752984482eb7c7b985','accepted parent')
    return dict(author_files=len(read(W/'result.json')['files']),input_files=len(read(W/'input-pins.json')['files']),accepted_parent_exact=True)
INITIAL=pins()
spec=importlib.util.spec_from_file_location('accepted_directional_review',PRIOR/'review.py')
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
old=parent.old;ElfImage=old.ElfImage;Machine=old.Machine;SP=old.SP;STATES=parent.STATES
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_SP
COMMANDS=[]
def run(args):
    args=list(map(str,args));COMMANDS.append(args)
    return subprocess.run(args,check=True,capture_output=True,text=True).stdout

def source():
    text=(W/'native_eabi_m0_atan_fast.inc').read_text();before=(P/'native_eabi_m0_atan_fast.inc').read_text()
    insertion='''          // For h<1/512 the old polynomial's lower error is below
          // 1.900690+r5/5-r3/3 Q70 (2.400690 in the wider geometry).
          if(!safe && h<(U(1)<<61) && bool(tail<half)!=reverse) {
            const int32_t r3_shifted=int32_t(poly_meta>>4);
            safe=int32_t(15*repaired_distance)+5*r3_shifted-3*r5>=(normal?34:42);
          }
'''
    require(text.count(insertion)==1 and text.replace(insertion,'')==before,'delta not exactly one gate')
    for n in ('native_eabi_m0.cpp','native_eabi_m0_atan.inc'):require((W/n).read_bytes()==(P/n).read_bytes(),'other math source changed')
    q=subprocess.run(['patch','--dry-run','--silent',str(P/'native_eabi_m0_atan_fast.inc')],input=(W/'small-h-lower-only.patch').read_text(),capture_output=True,text=True)
    require(q.returncode==0,'declared patch')
    b=read(W/'candidate-build.json');cc=list(b['commands'][-2]);ld=list(b['commands'][-1])
    cc[cc.index('-o')+1]=str(HERE/'candidate-full.o');run(cc)
    require(sha(HERE/'candidate-full.o')==sha(W/'candidate-full.o')=='7fe226827039b3f6c63b58ad63b9940621924e07ec02a12e19ef9298b8ef9a55','whole object')
    ld[ld.index(str(W/'candidate-full.o'))]=str(HERE/'candidate-full.o');ld[ld.index('-o')+1]=str(HERE/'candidate.elf');run(ld)
    require(sha(HERE/'candidate.elf')==sha(W/'candidate.elf')=='fce98d75c6a88d57282b74798371c9c990029193741c4a986483a273321a50c9','whole ELF without exclusions')
    require(sha(W/'control-full.o')==sha(PRIOR/'candidate-full.o') and sha(W/'control.elf')==sha(PRIOR/'candidate.elf'),'accepted parent object/ELF')
    a,z=ElfImage(W/'control-full.o'),ElfImage(HERE/'candidate-full.o');aa,zz=old.allocated(a),old.allocated(z)
    changed={n:(len(aa[n]),len(zz[n])) for n in aa if aa[n]!=zz[n]}
    require(set(aa)==set(zz) and changed=={'.text.atan_fast':(2040,2100)},'other allocation changed')
    require(old.nobits(a)==old.nobits(z) and old.undefined(a)==old.undefined(z),'RAM/deps changed')
    contexts=[]
    for name in ('generic_M0','M4_soft','M4_hard'):
        require(sha(W/(name+'-candidate.o'))==sha(P/(name+'-candidate.o')),'off-target accepted object changed')
        x,y=(ElfImage(W/(name+'-'+label+'.o'))for label in ('control','candidate'))
        require(old.allocated(x)==old.allocated(y) and old.nobits(x)==old.nobits(y),'off-target changed')
        contexts.append(dict(context=name,allocated_bytes=sum(map(len,old.allocated(y).values())),exact=True))
    image=ElfImage(HERE/'candidate.elf');pi=ElfImage(W/'control.elf');resident=ElfImage(old.FIRMWARE)
    bindings=b['resident_bindings'];require(bindings==read(W/'control-build.json')['resident_bindings'],'binding map')
    require(all(resident.symbols[n]==v for n,v in bindings.items()),'resident symbols')
    assignments={n:int(v,16)for n,v in re.findall(r'(?m)^(\w+) = (0x[0-9a-f]+);',(W/'candidate.ld').read_text())}
    require(assignments==bindings,'linker bindings')
    require(old.allocated(image)['.rodata']==old.allocated(pi)['.rodata'] and len(old.allocated(image)['.rodata'])==780,'tables')
    require(set(old.allocated(image))=={'.text','.rodata'} and not old.nobits(image) and not old.undefined(image),'ELF allocation')
    require(all(0x10185000<=s[3]<s[3]+s[5]<=0x10188000 for s in image.sections if s[2]&2),'overlay bound')
    require(all(not 0x10185000<=(v&~1)<0x10188000 for v in bindings.values()),'resident overlap')
    dis=run([str(Path(cc[0]).with_name('arm-none-eabi-objdump')),'-d',str(HERE/'candidate.elf')]);(HERE/'candidate.dis').write_text(dis)
    author_dis=(W/'candidate.dis').read_text()
    require(dis[dis.index('Disassembly of section'):]==author_dis[author_dis.index('Disassembly of section'):],'actual instructions differ')
    # Reuse accepted scalar-only pack wrapper, replacing only its exact pack
    # source with this child. Public body is separately rebuilt byte-exact.
    wrapper=(PRIOR/'pack-unit.cpp').read_text();f='__attribute__((optimize("Os"),noinline)) static double atan_fast'
    block=text[text.index('// top/den has at most six quotient bits.'):text.index('\n#endif\n\n'+f)]
    start=wrapper.index('// top/den has at most six quotient bits.');end=wrapper.index('struct Case {')
    wrapper=wrapper[:start]+block+'\n'+wrapper[end:];(HERE/'pack-unit.cpp').write_text(wrapper)
    (HERE/'pack-unit.ld').write_bytes((PRIOR/'pack-unit.ld').read_bytes())
    u=read(W/'ninth-unit-build.json');c=list(u['commands'][0]);l=list(u['commands'][1])
    c[c.index('-c')+1]=str(HERE/'pack-unit.cpp');c[c.index('-o')+1]=str(HERE/'pack-unit.o');run(c)
    l[l.index('-T')+1]=str(HERE/'pack-unit.ld');l[l.index(str(W/'ninth-unit.o'))]=str(HERE/'pack-unit.o');l[l.index('-o')+1]=str(HERE/'pack-unit.elf');run(l)
    require(not old.undefined(ElfImage(HERE/'pack-unit.elf')),'bare wrapper deps')
    result=dict(status='PASS_FULL_OBJECT_ENTIRE_ELF_AND_ONE_GATE_ISOLATION',source_sha256=sha(W/'native_eabi_m0_atan_fast.inc'),own_full_object_sha256=sha(HERE/'candidate-full.o'),own_entire_ELF_sha256=sha(HERE/'candidate.elf'),whole_patch_reconstructs_candidate=True,
        changed_sections=changed,code_delta_bytes=60,all_other_allocated_sections_tables_RAM_deps_exact=True,atan_table_bytes=780,contexts=contexts,resident_bindings=bindings,commands=COMMANDS,
        scalar_pack_wrapper_distinct_register_allocation=True,no_firmware_or_whole_M4_rebuild=True)
    put('SOURCE-OBJECT-PROOF.json',result);return result

def bounds():
    c=F(1,512);cube,positive5,all5,seventh=parent.polynomial(c)
    # Independent sign expansion: P7=h-C3/3+C5/5-C7/7+r3/3-r5/5+r7/7.
    # Every adverse product error is absolute; r7>=-3. atan's alternating
    # positive ninth remainder is at most h^9/9, without 1/(1-h^2).
    ratio=F(1,2)+F(35,1<<20);derivative=33*(c+F(33,S))**2
    normal=cube/3+all5/5+seventh/7+F(3,7)+S*c**9/9+ratio+F(1,2)+derivative
    wide=normal+F(1,2);cert=read(W/'low-certificate.json')
    require(normal==F(cert['lower_base_normal']) and wide==F(cert['lower_base_wide']),'exact lower enclosure')
    require(normal<F(29,15) and wide<F(37,15),'integer thresholds')
    require(S*c==1<<61,'small h boundary')
    checks=0;accepted=Counter();declined=0
    for e,invert in ((-6,False),(-5,False),(-4,False),(-3,False),(-2,False),(-1,False),(0,True),(5,True)):
      norm=(e+5)&0xffffffff;isnormal=norm<5;B=normal if isnormal else wide;threshold=29 if isnormal else 37
      for reverse in (False,True):
       for r3 in (-1,0,1):
        for r5 in range(-4,10):
         metadata=(r5+4)|((r3+1)<<4)
         require(metadata>>4==r3+1 and (metadata&15)-4==r5,'metadata overlap')
         for distance in range(7):
          gate=15*distance+5*(metadata>>4)-3*r5>=(34 if isnormal else 42)
          require(gate==(15*distance+5*r3-3*r5>=threshold),'shifted encoding')
          if not distance:require(not gate,'midpoint admitted')
          if not gate:declined+=1;continue
          require(B-F(r3,3)+F(r5,5)<distance,'unsafe lower enclosure')
          for lower in (0,1):
           shift=(0 if invert else e)+18-lower;half=1<<(shift-1)
           for parity in (0,1):
            center=(((1<<52)+parity)<<shift)+half+(distance if reverse else -distance)
            true_endpoint=F(center)+((-1 if reverse else 1)*(B-F(r3,3)+F(r5,5)))
            require(old.round_fraction(F(center,S))==old.round_fraction(true_endpoint/S),'RNE endpoint changes result')
            accepted['normal'if isnormal else'wide']+=1;checks+=1
    require(54+33+16<1024 and 15*86+10+12<(1<<31),'retained quantum/int32 bounds')
    result=dict(status='PASS_EXACT_SMALL_H_ONE_SIDED_ENCLOSURE',normal_base=str(normal),wide_base=str(wide),normal_base_float=float(normal),wide_base_float=float(wide),
        thresholds_unshifted=[29,37],thresholds_encoded=[34,42],metadata_remainders='r3[-1,1],r5[-4,9]; r3+1 in upper bits, r5+4 in low4 without overlap.',
        error_sign='P7-atan > -B+r3/3-r5/5. GeometryNegative XOR invert flips sign; new gate uses the opposite side to inherited upper enclosure and recomputes side after residual correction.',
        derivative_proof='For |t|<=c+33/S<1, |(t-t^3/3+t^5/5-t^7/7)prime-1|=t^2*(1-t^2+t^4)<=t^2; residual displacement<33 contributes at most33*(c+33/S)^2.',
        ratio_bound=str(ratio),alternating_omitted_tail_bound=str(S*c**9/9),finite_RNE_endpoint_checks=checks,accepted=dict(accepted),declined=declined,
        exact_midpoint_declines=True,int32_and_retained_quantum_safe=True,parent_product_ratio_geometry_fallback_proofs_reused=True,no_large_corpus_repeated=True)
    put('EXACT-LOWER-BOUND.json',result);return result

def pack_model_function():
    tree=ast.parse((PRIOR/'review.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='pack_model')
    text=ast.get_source_segment((PRIOR/'review.py').read_text(),fn)
    needle="         else:\n          extra,rnew=ninth_model(h,r5)"
    replacement="         elif h<(1<<61) and (tail<half)!=reverse and 15*dist+5*r3-3*r5>=(29 if norm<5 else 37):stage='small-h-lower'\n"+needle
    require(text.count(needle)==1,'accepted model insertion')
    env=dict(parent.__dict__);exec(compile(text.replace(needle,replacement),'<independent-unshifted-small-h-model>','exec'),env)
    return env['pack_model']

def bare_pack():
    model=pack_model_function();selected={};MASK64=(1<<64)-1
    for e,invert in ((-6,False),(-5,False),(0,True)):
      base=0 if invert else e;shift=base+18;half=1<<(shift-1)
      for capclass in (-1,0,1):
       exact_h=(1<<61)+capclass*4096;d=1<<58;n=exact_h>>6
       require(not invert or n%64==d%64==0,'inverted fixture domain')
       for reverse in (False,True):
        for r3,r5 in ((-1,-4),(0,0),(1,9)):
         for distance in (-5,-3,-2,-1,0,1,2,3,5):
          q=(((1<<52)+1)<<shift)+half+distance
          c=(q,exact_h,n,d,0,e,invert,reverse!=invert,r3,r5);want,meta=model(c)
          key=(e,invert,reverse,capclass,meta['stage'])
          selected.setdefault(key,(c,want,meta))
    require('small-h-lower' in {k[-1]for k in selected},'no new gate witness')
    require(all(k[3]<0 for k in selected if k[-1]=='small-h-lower'),'h cap equality accepted')
    m=Machine(HERE/'pack-unit.elf',True);pointer=0x20010000
    def mmio(uc,access,address,size,value,user):require(address<0x40000000,'bare pack MMIO')
    m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,mmio)
    rows=[]
    for c,want,meta in selected.values():
      q,h,n,d,sign,e,invert,negative,r3,r5=c
      blob=struct.pack('<5Q2Ii3I',q&MASK64,h,n,d,sign,q>>64,(r5+4)|((r3+1)<<4),e,int(invert),int(negative),0)
      for sn,state in STATES.items():
        m.stack_lowest=SP;m.uc.mem_write(pointer,blob);m.uc.mem_write(0xd0000060,state)
        got=m.call('check_pack',pointer)[0]
        require(got==want,'actual new pack differs unshifted scalar model '+str((c,meta,hex(got),hex(want))))
        require(bytes(m.uc.mem_read(pointer,64))==blob and bytes(m.uc.mem_read(0xd0000060,28))==state,'bare pack input/SIO changed')
        rows.append(dict(e=e,invert=invert,negative=negative,r3=r3,r5=r5,h=hex(h),SIO=sn,output=f'{got:016x}',stack_bytes=SP-m.stack_lowest,**meta))
    result=dict(status='PASS_SELECTED_SMALL_H_GATE_ARM_WRAPPER',ARM_calls=m.calls,rows=rows,stages=dict(Counter(r['stage']for r in rows)),
      h_boundaries=['2^61-4096','2^61','2^61+4096'],actual_source_pack_body=True,model_uses_unshifted29_37=True,
      no_firmware_or_ROM_mapped=True,no_MMIO=True,PCS_SP_bounded_writes_every_call=True,SIO_and_input_exact=True,
      synthetic_contract_cases_not_public_inputs=True)
    put('SELECTED-PACK-ARM.json',result);return result

def public():
    # Few public delta witnesses, cap neighbors and one retained fallback;
    # every finite oracle is fresh directed MPFR plus independent Fraction.
    chosen={}
    def add(raw,tag):chosen.setdefault(raw,tag)
    for h in (0x3fef1bcdcf0d1830,0x3fabb0edc0ae5c6f):
      for off in (-1,0,1):
       for sign in (0,1<<63):add((h+off)|sign,'fixed2-or-small-tradeoff-neighbors')
    for center in (F(1,64),F(1,2)):
      v=(center+F(1,512))/(1-center*F(1,512))
      for value in (v,1/v):
       raw=struct.unpack('<Q',struct.pack('<d',float(value)))[0]
       for off in (-1,0,1):
        for sign in (0,1<<63):add((raw+off)|sign,'small-h-cap-boundary')
    for raw in (0x3f99c24957c90e1f,0xbf99c24957c90e1f,0,1<<63,0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001):add(raw,'retained-fallback-and-specials')
    machines={'V164':Machine(old.FIRMWARE,True,bootrom=old.ROM),'Qfplib':Machine(old.REFERENCE,True)}
    for label,path in (('parent',W/'control.elf'),('candidate',HERE/'candidate.elf')):
      m=Machine(old.FIRMWARE,True,bootrom=old.ROM);im=ElfImage(path);im.load(m.uc);m.elf.symbols[label]=im.symbols['mk61_m0_atan'];machines[label]=m
    require(not any(m.rom_models for m in machines.values()),'modeled public ROM')
    image=ElfImage(HERE/'candidate.elf');resident=ElfImage(old.FIRMWARE);binding=read(W/'candidate-build.json')['resident_bindings']
    ranges=[(s[3],s[3]+s[5])for im in (image,resident)for s in im.sections if s[2]&6==6 and s[5]]+[(0,0x4000)]
    helper=image.symbols[next(n for n in image.symbols if n.startswith('atan_fast_tail_repair'))]&~1
    current=dict(raw=0,SIO='',repair=0,CORE=0,reference=0,gate=0);gates=[];geometries=[];events=Counter()
    # Addresses bound by own entire ELF identity + exact own disassembly.
    # 6986 starts15*distance+5*(meta>>4)-3*r5;69a0 compares34/42.
    def code(uc,pc,size,user):
      require(any(a<=pc and pc+size<=b for a,b in ranges),'candidate escaped actual execution closure')
      if pc==helper:
        current['repair']+=1;n=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32);d=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32);h=struct.unpack('<Q',uc.mem_read(uc.reg_read(UC_ARM_REG_SP),8))[0]
        geometries.append(dict(SIO=current['SIO'],**parent.geometry(current['raw'],n,d,h)))
      if pc==binding['mk61_m0_cr_atan']&~1:current['CORE']+=1
      if pc==0x10186986:
        current['gate']+=1;sp=uc.reg_read(UC_ARM_REG_SP);h=struct.unpack('<Q',uc.mem_read(sp+8,8))[0]
        distance=uc.reg_read(UC_ARM_REG_R2);r3shift=uc.reg_read(UC_ARM_REG_R4);r5=parent.signed32(uc.reg_read(UC_ARM_REG_R5));norm=struct.unpack('<I',uc.mem_read(sp+88,4))[0]
        require(h<1<<61 and 0<=r3shift<=2 and -4<=r5<=9 and distance<6,'new gate runtime domain')
        gates.append(dict(raw=f"{current['raw']:016x}",SIO=current['SIO'],h=hex(h),distance=distance,r3_shifted=r3shift,r5=r5,threshold=34 if norm<5 else 42,lhs=15*distance+5*r3shift-3*r5))
      if pc==0x101869a0:
        g=gates[-1];require(parent.signed32(uc.reg_read(UC_ARM_REG_R5))==g['lhs'] and uc.reg_read(UC_ARM_REG_R3)==g['threshold'],'actual threshold instructions not source expression');g['accepted']=g['lhs']>=g['threshold']
      for name,address in binding.items():
        if pc==address&~1:events[name]+=1
    def mmio(uc,access,address,size,value,user):
      if address>=0x40000000:require(0xd0000060<=address and address+size<=0xd000007c,'unexpected public MMIO')
    machines['candidate'].uc.hook_add(UC_HOOK_CODE,code);machines['candidate'].uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,mmio)
    def reference(uc,pc,size,user):
      a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32);b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
      require(a==current['raw'] and b==0x3ff0000000000000,'reference is not actual atan2(x,1)');current['reference']+=1
    qfp=machines['Qfplib'];address=qfp.elf.symbols['qfp_datan2']&~1;qfp.uc.hook_add(UC_HOOK_CODE,reference,begin=address,end=address)
    spec=importlib.util.spec_from_file_location('own_mpfr',ROOT/'.build/m0-float-fma-qualification-20261023/support/m0_mpfr_oracle.py');mp=importlib.util.module_from_spec(spec);spec.loader.exec_module(mp);oracle=mp.Oracle()
    author={(r['x'].lower(),r['SIO']):r for r in read(W/'qualification.json')['rows']};rows=[];oracles={};checked=0
    for raw,tag in chosen.items():
      want,proof=old.expected(raw)
      if raw&~old.SIGN<=old.INF:require(oracle.reference('atan',raw)==want,'fresh MPFR/Fraction disagreement')
      oracles[f'{raw:016x}']=dict(expected=f'{want:016x}',Fraction=proof,MPFR='fresh directed'if raw&~old.SIGN<=old.INF else'inherited raw NaN sign/payload policy')
      for sn,state in STATES.items():
        current.update(raw=raw,SIO=sn,repair=0,CORE=0,reference=0,gate=0);outputs={};counts={};depth={}
        for label,m in machines.items():
          m.stack_lowest=SP;m.uc.mem_write(0xd0000060,state);symbol='mk61_m0_atan'if label=='V164'else'audit_atan'if label=='Qfplib'else label
          got,_,cost=m.call(symbol,raw,count=True);after=bytes(m.uc.mem_read(0xd0000060,28))
          require(after==state if sn=='DIRTY'else struct.unpack('<7I',after)[6]&3==1,'SIO preservation')
          if label!='Qfplib':require(got==want,'actual public result '+str((hex(raw),label,hex(got),hex(want))))
          outputs[label]=f'{got:016x}';counts[label]=cost;depth[label]=SP-m.stack_lowest
        require(current['reference']==1,'reference accounting')
        record=author.get((f'{raw:016x}',sn))
        if record:
          for label in machines:
            key='resident'if label=='V164'else label
            require(outputs[label]==record['outputs'][key].lower() and counts[label]==record['instructions'][key],'author selected actual cost/output')
          checked+=1
        if raw&~old.SIGN==0x3fef1bcdcf0d1830:require(current['gate']==1 and not current['CORE'] and counts['candidate']<=counts['Qfplib'],'last2 not fixed on actual new gate')
        if raw&~old.SIGN==0x3f99c24957c90e1f:require(current['CORE']==1 and outputs['Qfplib']!=f'{want:016x}','retained fallback hidden')
        rows.append(dict(input=f'{raw:016x}',group=tag,SIO=sn,expected=f'{want:016x}',outputs=outputs,instructions=counts,stack_bytes=depth,repair_entries=current['repair'],new_gate_entries=current['gate'],CORE_entries=current['CORE']))
    require(gates and any(g['accepted']for g in gates),'new public gate not executed')
    result=dict(status='PASS_SELECTED_ACTUAL_PUBLIC_ARM_FRACTION_MPFR',unique_inputs=len(chosen),states=len(rows),ARM_calls=sum(m.calls for m in machines.values()),rows=rows,
        actual_new_gate_instruction_witnesses=gates,selected_reduction_geometry=geometries,resident_calls=dict(events),selected_author_cost_controls=checked,
        MPFR_version=oracle.version,stack_max={label:max(r['stack_bytes'][label]for r in rows)for label in machines},
        actual_reference='Qfplib audit_atan calls qfp_datan2(x,1), counted once.',PCS_R4_R11_SP_bounded_stack_every_call=True,SIO_DIRTY_exact_READY_clean=True,
        candidate_public_own_entire_relinked_ELF=True,pinned_resident_helpers_actual_bootROM=True,instructions_not_physical_cycles=True,no_full_corpus_replayed=True)
    put('SELECTED-PUBLIC-ARM.json',result);put('OWN-ORACLE-INTERVALS.json',oracles);return result

if __name__=='__main__':
    if sys.argv[1]=='source':source();bounds()
    elif sys.argv[1]=='arm':
        a=bare_pack();b=public();print(json.dumps(dict(pack_ARM=a['ARM_calls'],public_inputs=b['unique_inputs'],public_ARM=b['ARM_calls'],stack_max=b['stack_max'])))
    else:raise SystemExit('source|arm')
    require(INITIAL==pins(),'pins changed')
