"""Independent bounded review of the atan geometry gate; no hardware APIs."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import ast, hashlib, importlib.util, json, re, struct, subprocess, sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
W=ROOT/'.build/m0-atan-residual-geometry-20261024'
PARENT=ROOT/'.build/m0-atan-residual-original-goal-20261024'
PRIOR=ROOT/'.build/m0-atan-residual-independent-20261024'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,m):
    if not v:raise AssertionError(m)
def read(p):return json.loads(Path(p).read_text())
def put(n,r):(HERE/n).write_text(json.dumps(r,indent=2)+'\n')
def pins():
    require(sha(W/'HANDOFF.md')=='21e52ab6db11367e20d0f8dd95babc4a58775164602fa27942fb9fd1c02218d3','handoff changed')
    require(sha(W/'result.json')=='2f3f8deb8a78125c6a55c1f146c6dd1c72d9b56ff4f677bba3bacd84ce34f22d','result changed')
    for n,h in read(W/'result.json')['files'].items():require(sha(W/n)==h,'author changed '+n)
    inputs=read(W/'input-pins.json')['files']
    for n,h in inputs.items():require(sha(ROOT/n)==h,'input changed '+n)
    require(sha(PRIOR/'FINAL-REVIEW.json')=='b6a2234936391b97077999065e3055fd28e1935e519fd603a6a008c9d44bbaed','parent review changed')
    for n,h in read(PRIOR/'FINAL-REVIEW.json')['own_artifacts'].items():require(sha(PRIOR/n)==h,'parent evidence changed '+n)
    return dict(author_files=len(read(W/'result.json')['files']),input_files=len(inputs),parent_evidence_exact=True)
INITIAL=pins()
spec=importlib.util.spec_from_file_location('previous_residual_review',PRIOR/'review.py')
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
old=previous.old;ElfImage=old.ElfImage;Machine=old.Machine;SP=old.SP
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP
S=1<<70;INNER=(1<<62)+(1<<40);OUTER=S//250

def source():
    new=(W/'native_eabi_m0_atan_fast.inc').read_text();parent=(PARENT/'native_eabi_m0_atan_fast.inc').read_text()
    restored=new.replace('// Internal domain: every fast reduction geometry, quotient error <33.',
                         '// Internal domain: non-inverted exponent -5..-1 and quotient error <33.')
    restored=restored.replace('// d>=2^58, hence the truncated divisor is at least2^20.',
                             '// d>=2^59, hence the truncated divisor is never zero.')
    gate='''        uint32_t repaired_radius=6;
        if(h>(U(1)<<62)+(U(1)<<40)) {
          if(h>UINT64_C(4722366482869645213)) return false;
          repaired_radius=7;
        }'''
    require(restored.count(gate)==1,'gate changed')
    restored=restored.replace(gate,'        if(normalization>=5 || h>(U(1)<<62)+(U(1)<<40)) return false;')
    restored=restored.replace('if(repaired_distance<repaired_radius) return false;','if(repaired_distance<6) return false;')
    require(restored==parent,'source delta outside exact geometry gate/comments')
    for n in ('native_eabi_m0.cpp','native_eabi_m0_atan.inc'):require((W/n).read_bytes()==(PARENT/n).read_bytes(),'other public translation source')
    commands=[]
    def run(args):
        commands.append(list(map(str,args)));return subprocess.run(args,check=True,capture_output=True,text=True).stdout
    build=read(W/'candidate-build.json');cmd=list(build['commands'][-2]);link=list(build['commands'][-1])
    require(cmd[0].endswith('arm-none-eabi-g++') and link[0].endswith('arm-none-eabi-ld'),'compiler/linker binding')
    cmd[cmd.index('-o')+1]=str(HERE/'candidate-full.o');run(cmd)
    require(sha(HERE/'candidate-full.o')==sha(W/'candidate-full.o')=='a68a1ad91a4ec5931b2ff8ee16afc7982604b414bffb4651077997f9f99dd569','own full object')
    link[link.index(str(W/'candidate-full.o'))]=str(HERE/'candidate-full.o');link[link.index('-o')+1]=str(HERE/'candidate.elf');run(link)
    require(sha(HERE/'candidate.elf')==sha(W/'candidate.elf')=='5cea0e75f3d4a7b29af31c3af6d6315b0e0d569bb7c5a3ca5125bf341cfdecc7','entire own relink')
    require(sha(W/'control-full.o')==sha(PRIOR/'candidate-full.o') and sha(W/'control.elf')==sha(PRIOR/'candidate.elf'),'parent artifact identity')
    a,b=ElfImage(W/'control-full.o'),ElfImage(HERE/'candidate-full.o');aa,bb=old.allocated(a),old.allocated(b)
    changed={n:(len(aa[n]),len(bb[n]))for n in aa if aa[n]!=bb[n]}
    require(set(aa)==set(bb) and changed=={'.text.atan_fast':(1748,1780)},'other allocated section changes')
    require(old.nobits(a)==old.nobits(b) and old.undefined(a)==old.undefined(b),'global RAM/dependencies changed')
    helper='.text.unlikely.atan_fast_tail_repair';require(aa[helper]==bb[helper] and len(bb[helper])==344,'helper changed')
    contexts=[]
    for context in ('generic_M0','M4_soft','M4_hard'):
        ea,eb=(ElfImage(W/(context+'-'+label+'.o'))for label in ('control','candidate'))
        require(old.allocated(ea)==old.allocated(eb) and old.nobits(ea)==old.nobits(eb),'offtarget changed')
        require(sha(W/(context+'-candidate.o'))==sha(PARENT/(context+'-candidate.o')),'offtarget parent identity')
        contexts.append(dict(context=context,allocated_bytes=sum(map(len,old.allocated(ea).values())),exact=True))
    bindings=build['resident_bindings'];resident=ElfImage(old.FIRMWARE)
    require(bindings==read(W/'control-build.json')['resident_bindings'],'resident bindings changed')
    require(all(resident.symbols[n]==v for n,v in bindings.items()),'resident symbol mismatch')
    assignments={n:int(v,16)for n,v in re.findall(r'(?m)^(\w+) = (0x[0-9a-f]+);',(W/'candidate.ld').read_text())}
    require(assignments==bindings,'linker map')
    image=ElfImage(HERE/'candidate.elf');pi=ElfImage(W/'control.elf')
    require(set(old.allocated(image))=={'.text','.rodata'} and not old.nobits(image),'component RAM')
    require(old.allocated(image)['.rodata']==old.allocated(pi)['.rodata'] and len(old.allocated(image)['.rodata'])==780,'table changed')
    require(all(0x10185000<=s[3]<s[3]+s[5]<=0x10188000 for s in image.sections if s[2]&2),'component bounds')
    require(all(not 0x10185000<=(v&~1)<0x10188000 for v in bindings.values()),'resident overlap')
    r=dict(status='PASS_GEOMETRY_ONLY_FULL_OBJECT_AND_ENTIRE_RELINK',source_sha256=sha(W/'native_eabi_m0_atan_fast.inc'),own_full_object_sha256=sha(HERE/'candidate-full.o'),entire_own_ELF_sha256=sha(HERE/'candidate.elf'),
        source_reverse_reconstructs_parent=True,changed_sections=changed,allocated_delta_bytes=32,helper_section_sha256=hashlib.sha256(bb[helper]).hexdigest(),helper344B_byteexact=True,
        all_other_allocated_sections_tables_global_RAM_undefined_dependencies_exact=True,atan_table_bytes=780,contexts=contexts,resident_bindings=bindings,commands=commands,
        no_production_or_whole_M4_or_hardware_qualification=True)
    put('SOURCE-OBJECT-PROOF.json',r);return r

def bounds():
    # Reuse only the independent parent's pure polynomial-error expression.
    tree=ast.parse((PRIOR/'review.py').read_text());fn=next(n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name=='polynomial')
    env={'F':F,'S':S,'half':F(1,2)};exec(compile(ast.Module(body=[fn],type_ignores=[]),str(PRIOR/'review.py'),'exec'),env)
    polynomial=env['polynomial'];pc=read(PARENT/'certificate.json')
    # The old independent polynomial includes .5 table; all geometries here
    # require <=1 table+halving, so add exactly .5, not another ratio error.
    B=(F(pc['parent_ratio_error_bound'])-F(13,2));global_ratio=F(13,2)+2*B
    require(global_ratio==F(read(W/'certificate.json')['global_ratio_error']) and global_ratio<33,'global residual premise')
    regions=[]
    for cap,radius in ((F(INNER,S),6),(F(1,250),7)):
        error=polynomial(cap)+F(1,2)+1+F(34,1<<20)+33*(cap+F(33,S))**2
        cert=next(r for r in read(W/'certificate.json')['regions']if r['strict_radius_Q70']==radius)
        require(error==F(cert['total_error']) and error<radius and S*cap>=cert['integer_h_cap']>S*cap-1,'radius or cap mismatch')
        regions.append(dict(hcap=str(cap),integer_hcap=cert['integer_h_cap'],strict_radius=radius,total_error=str(error),total_error_float=float(error)))
    require(OUTER==4722366482869645213 and (1<<58)>>38==1<<20,'new integer domain')
    require(33*((1<<64)-1)<1<<70 and 33*(1<<26)<1<<32,'helper arithmetic still bounded')
    # Sample exact dyadic reduction identities in each affected geometry. No
    # compiler/author oracle; signs and optional halving are exact Fractions.
    geometry=[]
    for e,s,index,invert in ((-6,(1<<52)+1,1,False),(-6,(1<<53)-1,2,False),(-5,(1<<52)+17,2,False),(-1,(1<<53)-1,64,False),(0,(1<<52)+1,64,True),(2,(1<<52)+123,16,True),(5,(1<<53)-1,1,True),(6,1<<52,1,True)):
        x=F(s,1<<52)*(F(1<<e)if e>=0 else F(1,1<<(-e)))
        y=1/x if invert else x;true=abs((y-F(index,64))/(1+y*F(index,64)))*S
        if invert:n=abs((1<<(58-e))-s*index)<<6;d=(s<<6)+(index<<(52-e))
        else:
            z=abs((s<<6)-(index<<(52-e)));n=z<<(5 if e==-6 else 6)
            d=((1<<63)|(s*index>>1))if e==-6 else (1<<(58-e))+s*index
        delta=F(n<<64,d)-true
        require((0<=delta<F(1,2))if e==-6 and not invert else delta==0,'dyadic reduction identity')
        require(1<<58<=d<1<<64,'denominator bounds')
        geometry.append(dict(exponent=e,inverted=invert,denominator=d,halving_error_Q70=str(delta)))
    accepted=declined=0
    for base,invert in ((-6,False),(-5,False),(-1,False),(0,True)):
      for lower in (0,1):
       e=base-lower;shift=base+18-lower;halfstep=1<<(shift-1)
       for retained in (1<<52,(1<<52)+1,(1<<53)-1):
        for radius in (6,7):
         for distance in (-53,-7,-6,-5,0,5,6,7,53):
          for delta in (-33,0,33):
           tail=halfstep+distance+delta;require(0<tail<halfstep*2,'retained quantum changed')
           if abs(tail-halfstep)<radius:declined+=1;continue
           q=(retained<<shift)+tail;want=((e+1022)<<52)+retained+int(tail>halfstep)
           require(old.round_fraction(F(q-radius,S),1)==want==old.round_fraction(F(q+radius,S),-1),'new radius admits ambiguous rounding')
           accepted+=1
    r=dict(status='PASS_INDEPENDENT_EXACT_FRACTION_ALL_GEOMETRY_RADII',regions=regions,global_ratio_error=str(global_ratio),minimum_denominator=1<<58,minimum_truncated_divisor=1<<20,
        ratio_premise='Inherited normalized quotient error is <=6.5+2B<33. D>=2^58 means the unchanged truncated quotient bound1+34/2^20 and signed71-bit arithmetic remain valid.',
        geometry_proof='Inverted D=(s<<6)+(index<<(52-e))>=2^58 and is exact. Ordinary e=-6 halves its65-bit D with exact numerator halving: stored residual ratio excess <.5Q70 since its true h<2^63 and Dhalf>=2^63. Ordinary table<=.5; inverted table+pi/2<=1 with no halving. Their combined worst case<=1.',
        sign_proof='q gets +correction when geometry nonnegative, - when negative; pi/2 inversion reverses it. Thus delta sign is reversed iff geometryNegative XOR invert. Original input sign remains in final pack.',
        shifts='Fast source e=-6..6; e=invert?0:source_e gives pack shifts11..18. normalization=unsigned(source_e+5) is used only behind normalization<5 short-circuit gates; widening repair introduces no negative shift.',
        sampled_exact_geometries=geometry,admitted_synthetic_open_intervals=accepted,declined_near_ties=declined,
        tail_reuse='Within53.25Q70 before correction plus |delta|<=33 is <minimumhalf1024; quantum/binade stay exact. At distance>=radius, strict bound stays within one RNE cell, including equality6/7.',
        prior_helper_proof_reused=True,large_helper_or_public_corpus_repeated=False)
    put('EXACT-GEOMETRY-BOUND.json',r);return r

STATES=previous.STATES
def jobs():
    result={}
    def add(raw,tag):result.setdefault(raw,tag)
    for r in read(W/'result.json')['fixed_rows']:
        v=int(r['x'],16);add(v,'fixed6');add(v^old.SIGN,'fixed6-signcontrol')
    for v in (0x3fe5d1004fc925b6,0xbfe5d1004fc925b6,0x3fecb99548f4fa32,0xbfecb99548f4fa32):add(v,'prior-hard4')
    for r in read(W/'remaining-slower.json')['rows']:add(int(r['x'],16),'remaining17')
    for r in read(W/'regressions.json')['V164_regression_rows']:add(int(r['x'],16),'V164-regression')
    for v in (0,old.SIGN,1,old.SIGN|1,old.FRAC,old.SIGN|old.FRAC,old.INF,old.INF|old.SIGN,old.INF|1,old.INF|(1<<51)|0x123,old.SIGN|old.INF|0x80000000,old.SIGN|old.INF|old.FRAC):add(v,'special')
    for e in (-6,-5,0,6):
      for d in (-1,0,1):
       for sign in (0,old.SIGN):add((((e+1023)<<52)+d)|sign,'geometry-dispatch-edge')
    for cap in (F(INNER,S),F(1,250)):
      for center,invert in ((F(1,64),False),(F(31,64),False),(F(31,64),True)):
       v=(center+cap)/(1-center*cap);v=1/v if invert else v;raw=old.round_fraction(v)
       for d in (-1,0,1):
        for sign in (0,old.SIGN):add((raw+d)|sign,'hcap-invert-edge')
    for raw in (0x4012a253c99075d1,0xc012a253c99075d1):add(raw,'selected-actual-inverted-repair')
    for raw in (0x3fb97996f4e5f9f0,0xbfdd440162570130):add(raw,'old2')
    require(len(result)<128,'compact replay widened');return result

def geometry_args(raw,n,d,h):
    mag=raw&(old.SIGN-1);invert=mag>0x3ff0000000000000;e=(mag>>52)-1023;s=(mag&old.FRAC)|(1<<52)
    if invert:
        index=(((1<<30)//(s>>37))+(1<<(8+e)))>>(9+e)
        a=1<<(58-e);c=s*index;want_n=abs(a-c)<<6;want_d=(s<<6)+(index<<(52-e))
    else:
        index=((s>>(45-e))+1)//2;a=s<<6;c=index<<(52-e);z=abs(a-c)
        want_n=z<<(5 if e==-6 else 6);want_d=((1<<63)|(s*index>>1))if e==-6 else(1<<(58-e))+s*index
    require((n,d)==(want_n,want_d),'actual helper geometry arguments differ')
    x=old.decode(mag);y=1/x if invert else x;true=abs((y-F(index,64))/(1+y*F(index,64)))*S
    quantization=F(n<<64,d)-true
    require((0<=quantization<F(1,2))if not invert and e==-6 else quantization==0,'actual geometry identity')
    require(1<<58<=d<1<<64 and abs(F(n<<64,d)-h)<33 and h<=OUTER,'actual helper domain')
    return dict(domain='inverted'if invert else'halved-e-6'if e==-6 else'ordinary',index=index,geometry_negative=a<c,input_negative=bool(raw&old.SIGN),
        numerator=f'{n:016x}',denominator=f'{d:016x}',h=f'{h:016x}',halving_error_Q70=str(quantization),radius=6 if h<=INNER else 7)

def arm():
    machines={'V164':Machine(old.FIRMWARE,True,bootrom=old.ROM),'Qfplib':Machine(old.REFERENCE,True)}
    for label,file in (('parent',W/'control.elf'),('candidate',HERE/'candidate.elf')):
        m=Machine(old.FIRMWARE,True,bootrom=old.ROM);im=ElfImage(file);im.load(m.uc);m.elf.symbols[label]=im.symbols['mk61_m0_atan'];machines[label]=m
    require(not any(m.rom_models for m in machines.values()),'abstract ROM callback')
    image=ElfImage(HERE/'candidate.elf');resident=ElfImage(old.FIRMWARE);bindings=read(W/'candidate-build.json')['resident_bindings']
    ranges=[(s[3],s[3]+s[5])for e in(image,resident)for s in e.sections if s[2]&6==6 and s[5]]+[(0,0x4000)]
    name=next(n for n in image.symbols if n.startswith('atan_fast_tail_repair'));helper=image.symbols[name]&~1
    require(image.sizes[name]==344,'helper bounds');current=dict(mode='public',raw=0,SIO=None,repair=0,CORE=0,reference=0)
    events=Counter();observations=[];entries={v&~1:k for k,v in bindings.items()}
    def code(uc,pc,n,user):
        require(any(lo<=pc and pc+n<=hi for lo,hi in ranges),'candidate code escape')
        if current['mode']=='helper':require(helper<=pc and pc+n<=helper+344,'new domain helper dependency')
        elif pc==helper:
            current['repair']+=1
            a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32);b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
            h=struct.unpack('<Q',uc.mem_read(uc.reg_read(UC_ARM_REG_SP),8))[0]
            observations.append(dict(input=f"{current['raw']:016x}",SIO=current['SIO'],**geometry_args(current['raw'],a,b,h)))
        if pc==bindings['mk61_m0_cr_atan']&~1:current['CORE']+=1
        if pc in entries:events[entries[pc]]+=1
    def mmio(uc,access,address,n,value,user):
        if address>=0x40000000:require(current['mode']!='helper'and 0xd0000060<=address and address+n<=0xd000007c,'unexpected MMIO')
    m=machines['candidate'];m.uc.hook_add(UC_HOOK_CODE,code);m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,mmio)
    # Only the newly admitted minimum-denominator boundary, not the accepted
    # prior helper corpus. Existing helper body/0..33 proof is reused unchanged.
    m.elf.symbols['low_helper']=image.symbols[name];new_boundary=[];current['mode']='helper'
    for d in (1<<58,(1<<58)+(1<<38)-1):
      for n in (0,d//4-1):
       floor=(n<<64)//d
       for offset in (-32,0,32):
        h=floor+offset
        if h<0:continue
        for sn,state in STATES.items():
          m.stack_lowest=SP;m.uc.mem_write(0xd0000060,state);got=m.call('low_helper',n,d,c=h)[0]&0xffffffff;got=got-(1<<32)if got>>31 else got
          r=(n<<64)-h*d;want=(abs(r)>>38)//(d>>38);want=-want if r<0 else want
          require(got==want and abs(F(got)-(F(n<<64,d)-h))<1+F(34,1<<20),'new minimum denominator helper failed')
          require(bytes(m.uc.mem_read(0xd0000060,28))==state,'new denominator SIO changed')
          new_boundary.append(dict(n=f'{n:016x}',d=f'{d:016x}',h=f'{h:016x}',delta=got,SIO=sn))
    current['mode']='public';ref=machines['Qfplib']
    def reference(uc,pc,n,user):
        a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32);b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
        require(a==current['raw']and b==0x3ff0000000000000,'reference not actual atan2(x,1)');current['reference']+=1
    ref.uc.hook_add(UC_HOOK_CODE,reference,begin=ref.elf.symbols['qfp_datan2']&~1,end=ref.elf.symbols['qfp_datan2']&~1)
    previous_rows={(r['input'],r['SIO']):r for r in read(PRIOR/'SELECTED-PUBLIC-ARM.json')['rows']}
    fixed={(r['x'].lower(),r['SIO']):r for r in read(W/'result.json')['fixed_rows']}
    remaining={(r['x'].lower(),r['SIO']):r for r in read(W/'remaining-slower.json')['rows']}
    regress={(r['x'].lower(),r['SIO']):r for r in read(W/'regressions.json')['V164_regression_rows']}
    hard4={f'{v:016x}'for v in(0x3fe5d1004fc925b6,0xbfe5d1004fc925b6,0x3fecb99548f4fa32,0xbfecb99548f4fa32)}
    rows=[];oracles={};parent_checks=0
    for raw,tag in jobs().items():
      want,oracle=old.expected(raw);oracles[f'{raw:016x}']=oracle
      for sn,state in STATES.items():
        outputs={};counts={};depth={};current.update(raw=raw,SIO=sn,repair=0,CORE=0,reference=0)
        for label,m in machines.items():
            m.stack_lowest=SP;m.uc.mem_write(0xd0000060,state);symbol='mk61_m0_atan'if label=='V164'else'audit_atan'if label=='Qfplib'else label
            got,_,cost=m.call(symbol,raw,count=True);after=bytes(m.uc.mem_read(0xd0000060,28))
            require(after==state if sn=='DIRTY'else struct.unpack('<7I',after)[6]&3==1,'SIO changed/notclean')
            if label!='Qfplib':require(got==want,'own rational RNE oracle differs '+str((hex(raw),label,hex(got),hex(want))))
            outputs[label]=f'{got:016x}';counts[label]=cost;depth[label]=SP-m.stack_lowest
        require(current['reference']==1,'atan2 reference not observed once');key=(f'{raw:016x}',sn)
        if key in previous_rows:
            prior=previous_rows[key];require(outputs['parent']==prior['outputs']['candidate']and counts['parent']==prior['instructions']['candidate'],'parent controls changed');parent_checks+=1
        if key in fixed:
            author=fixed[key];require(outputs['Qfplib']==f'{want:016x}'and counts['candidate']<counts['Qfplib'],'six fixed inputs not wins')
            require(current['repair']==1 and current['CORE']==0,'fixed input did not use bounded repair')
            require(all(counts[n]==author['instructions'][n]for n in('candidate','parent','Qfplib')),'fixed count mismatch')
        if key[0]in hard4:require(outputs['Qfplib']==f'{want:016x}'and counts['candidate']<counts['Qfplib'],'prior hard4 wins lost')
        if key in remaining:
            author=remaining[key];require(outputs['Qfplib']==f'{want:016x}'and counts['candidate']>counts['Qfplib']and counts['parent']>counts['Qfplib'],'remaining deficit hidden')
            require(all(counts[n]==author['instructions'][n]for n in('candidate','parent','Qfplib')),'remaining count mismatch')
        if key in regress:
            author=regress[key];require(counts['candidate']>counts['V164']and all(counts[n]==author['instructions']['resident'if n=='V164'else n]for n in('candidate','parent','V164','Qfplib')),'V164 regression hidden/mismatched')
        rows.append(dict(input=key[0],group=tag,SIO=sn,expected=f'{want:016x}',outputs=outputs,instructions=counts,stack_bytes=depth,repair_entries=current['repair'],CORE_entries=current['CORE'],fixed6=key in fixed,remaining17=key in remaining,V164_regression=key in regress))
    require({r['domain']for r in observations}=={'inverted','halved-e-6','ordinary'}and {r['radius']for r in observations}=={6,7},'missing actual affected geometry/radius')
    report=dict(status='PASS_COMPACT_ACTUAL_ARM_GEOMETRY_WITH_OWN_RATIONAL_ORACLE',unique_inputs=len(jobs()),public_state_cases=len(rows),public_ARM_calls=len(rows)*4,new_min_denominator_helper_calls=len(new_boundary),
        reused_prior_helper_ARM_calls_not_repeated=488,all_large_author_corpora_replayed=False,groups=dict(Counter(r['group']for r in rows)),
        fixed6=[r for r in rows if r['fixed6']],prior_hard4=[r for r in rows if r['input']in hard4],remaining17=[r for r in rows if r['remaining17']],V164_regressions=[r for r in rows if r['V164_regression']],
        parent_controls_exact=parent_checks,maximum_candidate_stack=max(r['stack_bytes']['candidate']for r in rows),maximum_parent_stack=max(r['stack_bytes']['parent']for r in rows),
        selected_vs_parent=dict(Counter('faster'if r['instructions']['candidate']<r['instructions']['parent']else'equal'if r['instructions']['candidate']==r['instructions']['parent']else'slower'for r in rows)),
        selected_parent_instruction_deltas=dict(Counter(str(r['instructions']['candidate']-r['instructions']['parent'])for r in rows)),
        actual_repair_geometry_observations=observations,new_min_denominator_boundaries=new_boundary,
        own_oracle='Pinned independent exact Fraction outward Taylor/Machin/reciprocal intervals, uniquely rounded binary64; parent quietNaN sign/payload policy.',
        reference='Actual unchanged audit_atan -> qfp_datan2(originalraw,1.0); no standalone public atan API.',raw_Qfplib_wrong_outcomes_retained=sum(r['outputs']['Qfplib']!=r['expected']for r in rows),
        candidate_pinned_resident_entries=dict(events),abstract_ROM_callbacks=[],candidate_code_extent_checked=True,MMIO_only_existing_SIO_divider=True,DIRTY_exact=True,READY_allowed_and_left_clean=True,PCS_R4_R11_SP_and_bounded_writes_checked=True,physical_cycles=False,rows=rows)
    put('SELECTED-ARM-GEOMETRY.json',report);put('OWN-ORACLE-INTERVALS.json',oracles);return report

if __name__=='__main__':
    mode=sys.argv[1]if len(sys.argv)>1 else'all';report={}
    if mode in('all','source'):report['source']=source()['status']
    if mode in('all','bounds'):report['bounds']=bounds()['status']
    if mode in('all','arm'):
        r=arm();report['arm']=dict(status=r['status'],public_calls=r['public_ARM_calls'],new_Dmin_calls=r['new_min_denominator_helper_calls'])
    require(pins()==INITIAL,'pins changed after review');print(json.dumps(report,indent=2),flush=True)
