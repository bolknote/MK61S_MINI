"""Exact current Thumb producer/consumer binding for normalized division."""
from pathlib import Path
import ast,copy,hashlib,json,re,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
fn=next(n for n in ast.parse((W/'verify-private-return.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='parse')
env={'re':re};exec(compile(ast.Module(body=[fn],type_ignores=[]),'parser','exec'),env)
e=ElfImage(W/'candidate.elf');code=env['parse']((W/'candidate.dis').read_text());sym=lambda n:e.symbols[n]&~1
edit=json.loads((W/'source-edits.json').read_bytes());old=json.loads((W/'div-guard-proof.json').read_bytes());start=sym('__aeabi_ddiv');slow=old['old_fallback'];inf=old['overflow_pack']
def norm(s):return re.sub(r'\s+','',s).replace('ip','r12')
def canon(op,args):
    a=norm(args).split(',')
    if op in('adds','subs','lsls','lsrs','asrs')and len(a)==2:a.insert(1,a[0])
    return ','.join(a)
def literal(a,r):
    m=re.search(r'\[pc, #(\d+)\]',r['operands']);assert m
    p=((a+4)&~3)+int(m[1]);s=next(s for s in e.named_sections.values()if s[3]<=p and p+4<=s[3]+s[5]);return struct.unpack_from('<I',e.bytes_at(s),p-s[3])[0]
labels={'.Lrp2040_div_slow':slow,'.Lrp2040_div_den_overflow':inf};blocks=[]
for key,base in [('header_after',start+24),('num_guard',sym('mk61_m0_ddiv_numerator_guard_body')),('range_guard',sym('mk61_m0_ddiv_range_guard_begin'))]:
    lines=[]
    for line in edit[key].splitlines():
        line=line.split('//',1)[0].strip()
        if not line:continue
        if line.endswith(':'):labels[line[:-1]]=base+2*len(lines)
        elif not line.startswith('.'):lines.append(line)
    blocks.append((key,base,lines))
branches={'b','bl','beq','bne','bmi','bpl','bhi','bhs','bcs','blo','bcc','bls','ble','bge','bgt','blt'}
target=lambda r:int(r['operands'].split()[0],16)
def actual_dd0(c):
    sites=[a for a,r in c.items()if start<a<start+600 and r['mnemonic']=='bne'and c.get(a-2,{}).get('mnemonic')=='lsrs'and canon('lsrs',c[a-2]['operands'])=='r1,r5,#30']
    assert len(sites)==1
    dest=target(c[sites[0]]);assert start<dest<start+600;return dest
def check(c):
    prefix=[('push','{r4, r5, r6, r7, lr}'),('lsls','r4,r1,#1'),('lsrs','r4,r4,#21'),('lsls','r5,r3,#1'),('lsrs','r5,r5,#21'),('subs','r6,r4,#1'),('ldr',None),('cmp','r6,r7'),('bhi',None),('subs','r6,r5,#1'),('cmp','r6,r7'),('bhi',None)]
    for i,(op,args)in enumerate(prefix):
        r=c[start+2*i];assert r['bytes']==2 and r['mnemonic']==op
        if args is not None:assert canon(op,r['operands'])==canon(op,args),(i,r,args)
    assert literal(start+12,c[start+12])==2045
    assert target(c[start+16])==sym('mk61_m0_ddiv_numerator_guard_begin')
    assert target(c[start+22])==sym('mk61_m0_ddiv_denominator_guard_begin')
    for key,base,lines in blocks:
        for i,line in enumerate(lines):
            a=base+2*i;r=c[a];op,args=line.split(None,1)
            assert r['bytes']==2 and r['mnemonic']=={'blo':'bcc','bhs':'bcs'}.get(op,op),(key,line,r)
            if op in branches:assert target(r)==labels[args],(key,line,r)
            elif ',='in args:
                reg,val=args.split(',=');assert r['operands'].split(',')[0]==reg and literal(a,r)==int(val,0)
            elif op=='pop':assert r['operands']=='{r4, r5, r6, r7, pc}'
            else:assert canon(op,r['operands'])==canon(op,args),(key,line,r)
    assert labels['mk61_m0_ddiv_range_guard_call']==sym('mk61_m0_ddiv_range_guard_call')==start+50
    assert labels['mk61_m0_ddiv_normal_range_join']==sym('mk61_m0_ddiv_normal_range_join')==start+56
    assert labels['mk61_m0_ddiv_numerator_guard_begin']==sym('mk61_m0_ddiv_numerator_guard_begin')
    assert labels['mk61_m0_ddiv_range_guard_end']==sym('mk61_m0_ddiv_range_guard_end')
    for dest,origin in [(sym('mk61_m0_ddiv_numerator_guard_begin'),start+16),(sym('mk61_m0_ddiv_numerator_guard_body'),sym('mk61_m0_ddiv_numerator_guard_begin')),(sym('mk61_m0_ddiv_range_guard_begin'),start+50)]:
        incoming=[a for a,r in c.items()if r['mnemonic']in branches and re.match(r'^[0-9a-f]+',r['operands'])and target(r)==dest];assert incoming==[origin],(dest,incoming)
    # The polynomial, refinement and midpoint calculation keep the old source;
    # only the three exponent-adjustment instructions disappear at dd_0.
    d=actual_dd0(c);assert c[d]['mnemonic']=='adds'and canon('adds',c[d]['operands'])=='r3,r3,#128'
    join=sym('mk61_m0_ddiv_normal_range_join')
    expected=[('lsls','r7,r3,#15'),('orrs','r7,r2'),('bne',None)]
    for i,(op,args)in enumerate(expected):
        r=c[join+2*i];assert r['mnemonic']==op and r['bytes']==2
        if args:assert canon(op,r['operands'])==canon(op,args)
    assert c[slow]['mnemonic']=='sub'and norm(c[slow]['operands'])=='sp,#4'
    assert c[slow+2]['mnemonic']=='bl'and target(c[slow+2])==sym('mk61_m0_ddiv_slow')
    assert c[slow+6]['mnemonic']=='add'and norm(c[slow+6]['operands'])=='sp,#4'and c[slow+8]['operands']=='{r4, r5, r6, r7, pc}'
    return True
check(code)
def at(key,text):
    _,base,lines=next(b for b in blocks if b[0]==key);return base+2*lines.index(text)
edits=[('first-numerator-target',start+16,'bhi',f'{slow:x}'),('packed-low-borrow',at('header_after','cmp r0,r2'),'cmp','r2, r0'),('packed-high-SBC',at('header_after','sbcs r6,r3'),'subs','r6, r3'),('packed-sign-correction',at('header_after','eors r6,r4'),'eors','r6, r5'),('packed-arithmetic-shift',at('header_after','asrs r6,#20'),'lsrs','r6, r6, #20'),('normal-range-bias',at('header_after','ldr r5,=1022'),'ldr','r5, [pc, #0]'),('R12-mask-definition',at('header_after','mov r12,r4'),'mov','r12, r3'),('R12-packed-add',at('header_after','add r12,r6'),'mov','r12, r6'),('subnormal-N-flag',at('num_guard','bpl .Lrp2040_div_slow'),'bmi',code[at('num_guard','bpl .Lrp2040_div_slow')]['operands']),('subnormal-denominator-limit',at('num_guard','cmp r6,r7'),'cmp','r5, r7'),('subnormal-shift-53',at('num_guard','cmp r7,#53'),'cmp','r7, #52'),('subnormal-zero-LSB',at('num_guard','cmp r0,r6'),'cmp','r2, r6'),('tiny-exponent-53',at('range_guard','movs r7,#53'),'movs','r7, #54'),('tiny-tie-inclusive',at('range_guard','blt .Lrp2040_div_range_zero'),'ble',code[at('range_guard','blt .Lrp2040_div_range_zero')]['operands']),('tiny-mantissa-equality',at('range_guard','eors r4,r2'),'eors','r4, r3'),('removed-upper-fix',actual_dd0(code),'movs','r2, #1')]
rejected=[]
for name,a,op,args in edits:
    bad=copy.deepcopy(code);bad[a]=dict(bad[a],mnemonic=op,operands=args)
    try:check(bad)
    except(AssertionError,StopIteration):rejected.append(name)
    else:raise AssertionError('accepted bad actual R47 '+name)
out=dict(status='PASS_R47_ACTUAL_NORMALIZED_DIVISION_AND_16_NEGATIVES',candidate_ELF_sha256=sha(W/'candidate.elf'),header_normalized_exponent_sign_R12_instructions_bound=True,header_masked_SBC_ASR20_handles_both_signs_and_low_borrow=True,range_normal_e_minus1022_to1023_bound=True,upper_pack_three_instruction_fix_removed=True,coarse_divisor_three_instruction_predicate_bound=True,num_entry_short_branch_preserves_actual_Ea_CMP_N_flags=True,num_full_guard_all_branches_shifts_literals_bound=True,tiny_equal_mantissas_tie_zero_else_min_subnormal_bound=True,all_declines_keep_arguments_and_old_aligned_CPP_call=True,existing20byte_frame_all_fast_returns=True,negative_controls_rejected=rejected,new_ARM_MPFR_calls=0,hardware_accessed=False,integration_GO=False,goal_complete=False)
(W/'normalized-div-proof.json').write_text(json.dumps(out,indent=2)+'\n');print('R47 normalized divider PASS; negatives',len(rejected),flush=True)
