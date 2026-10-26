"""Bind the new denominator guard and its normal-numerator/N-flag precondition."""
from pathlib import Path
import ast,copy,hashlib,json,re,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
fn=next(n for n in ast.parse((W/'verify-private-return.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='parse');env={'re':re};exec(compile(ast.Module(body=[fn],type_ignores=[]),'parser','exec'),env)
e=ElfImage(W/'candidate.elf');code=env['parse']((W/'candidate.dis').read_text());start=e.symbols['__aeabi_ddiv']&~1;call=e.symbols['mk61_m0_ddiv_denominator_guard_call']&~1;begin=e.symbols['mk61_m0_ddiv_denominator_guard_begin']&~1;end=e.symbols['mk61_m0_ddiv_denominator_guard_end']&~1
literal=lambda a,r:None
def literal(a,r):
    m=re.search(r'\[pc, #(\d+)\]',r['operands']);assert m;ptr=((a+4)&~3)+int(m[1]);s=next(s for s in e.named_sections.values()if s[3]<=ptr and ptr+4<=s[3]+s[5]);return struct.unpack_from('<I',e.bytes_at(s),ptr-s[3])[0]
def norm(s):return re.sub(r'\s+','',s)
parts={}
for n in ast.parse((ROOT/'.build/m0-math-unified-ddiv-cold-overflow-r45-20261026'/'build.py').read_text()).body:
    if isinstance(n,ast.Assign)and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)and n.targets[0].id=='guard':parts['guard']=ast.literal_eval(n.value)
lines=[];labels={}
for line in parts['guard'].splitlines():
    line=line.split('//',1)[0].strip()
    if not line:continue
    if line.endswith(':'):labels[line[:-1]]=begin+2*len(lines)
    elif not line.startswith('.'):lines.append(line)
assert begin+2*len(lines)==end
slow=int(code[begin]['operands'].split()[0],16);labels['.Lrp2040_div_slow']=slow
def check(c):
    assert call==start+22
    prefix=[('push','{r4, r5, r6, r7, lr}'),('lsls','r4, r1, #1'),('lsrs','r4, r4, #21'),('lsls','r5, r3, #1'),('lsrs','r5, r5, #21'),('subs','r6, r4, #1'),('ldr',None),('cmp','r6, r7'),('bhi',None),('subs','r6, r5, #1'),('cmp','r6, r7'),('bhi',None)]
    for i,(op,args)in enumerate(prefix):
        r=c[start+2*i];assert r['bytes']==2 and r['mnemonic']==op and(args is None or r['operands']==args)
    assert c[start+12]['operands'].startswith('r7, [pc,')and literal(start+12,c[start+12])==2045
    assert int(c[start+16]['operands'].split()[0],16)==slow and int(c[call]['operands'].split()[0],16)==begin
    incoming=[a for a,r in c.items()if r['mnemonic']in('b','bl','bhi','bhs','bpl','bmi','beq','bne','blo','bls')and re.match(r'^[0-9a-f]+',r['operands'])and int(r['operands'].split()[0],16)==begin];assert incoming==[call]
    for i,line in enumerate(lines):
        a=begin+2*i;r=c[a];op,args=line.split(None,1);assert r['bytes']==2 and r['mnemonic']=={'bhs':'bcs','blo':'bcc'}.get(op,op),(line,r)
        if op.startswith('b'):assert int(r['operands'].split()[0],16)==labels[args]
        elif ',='in args:
            reg,val=args.split(',=');assert r['operands'].split(',')[0]==reg and literal(a,r)==int(val,0)
        elif op=='pop':assert r['operands']=='{r4, r5, r6, r7, pc}'
        else:assert norm(r['operands'])==norm(args),(line,r)
    assert c[slow]['mnemonic']=='sub'and norm(c[slow]['operands'])=='sp,#4'
    assert c[slow+2]['mnemonic']=='bl'and int(c[slow+2]['operands'].split()[0],16)==(e.symbols['mk61_m0_ddiv_slow']&~1)
    assert c[slow+6]['mnemonic']=='add'and norm(c[slow+6]['operands'])=='sp,#4'and c[slow+8]['operands']=='{r4, r5, r6, r7, pc}'
    overflow=labels['.Lrp2040_div_den_overflow']
    for a,r in c.items():
        if begin<=a<overflow:
            assert r['mnemonic']not in('bl','blx','str','strb','strh','push','pop')
            if r['mnemonic']not in('cmp','b','bpl','bmi','beq','bne','bhi','bhs','blo','bls','ble'):
                assert not re.match(r'r[0-3],',r['operands']),r
    return overflow
overflow=check(code);negatives=[]
edits=[('bad-Ea-unpack',start+4,'lsrs','r4, r4, #20'),('bad-first-Ea-reject',start+16,'blo',code[start+16]['operands']),('bad-Eb-CMP',start+20,'cmp','r5, r7'),('wrong-cold-target',call,'bhi',f'{slow:x}'),('wrong-flag-consumer',begin,'bmi',code[begin]['operands']),('wrong-sign-XOR',overflow,'eors','r1, r2')]
for name,a,op,args in edits:
    bad=copy.deepcopy(code);bad[a]=dict(bad[a],mnemonic=op,operands=args)
    try:check(bad)
    except AssertionError:negatives.append(name)
    else:raise AssertionError('accepted bad denominator guard '+name)
truth=[]
for Eb in range(2048):
    r=(Eb-1)&0xffffffff;enter=r>2045;N=((r-2045)&0xffffffff)>>31
    if enter:truth.append(dict(Eb=Eb,N=N))
assert truth==[dict(Eb=0,N=1),dict(Eb=2047,N=0)]
out=dict(status='PASS_R45_ACTUAL_NORMAL_NUMERATOR_DENOMINATOR_GUARD_AND_6_NEGATIVES',candidate_ELF_sha256=sha(W/'candidate.elf'),caller=start+22,guard_begin=begin,guard_end=end,overflow_pack=overflow,old_fallback=slow,caller_prefix_proves_Ea1to2046_and_Eb0or2047=True,all2048_Eb_integer_truth=truth,no_argument_writes_on_any_decline=True,normal_common_division_prefix_instruction_count_unchanged=True,guard_source_instructions_branches_literals_bound=True,callee_stack20bytes_popped_on_fast_return=True,no_new_calls_or_SIO=True,negative_controls_rejected=negatives,mandatory_after_each_changed_release=True,new_ARM_MPFR_calls=0,hardware_accessed=False,physical_cycles_measured=False,integration_GO=False,goal_complete=False)
(W/'div-guard-proof.json').write_text(json.dumps(out,indent=2)+'\n');print('R45 denominator guard PASS; negatives',len(negatives),flush=True)
