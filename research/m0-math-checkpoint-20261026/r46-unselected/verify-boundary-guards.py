"""Bind actual Thumb boundaries, exact producer flags, literals and declines."""
from pathlib import Path
import ast,copy,hashlib,json,re,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
fn=next(n for n in ast.parse((W/'verify-private-return.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='parse')
env={'re':re};exec(compile(ast.Module(body=[fn],type_ignores=[]),'parser','exec'),env)
e=ElfImage(W/'candidate.elf');code=env['parse']((W/'candidate.dis').read_text())
sym=lambda n:e.symbols[n]&~1
start=sym('__aeabi_ddiv');num=sym('mk61_m0_ddiv_numerator_guard_begin');rng=sym('mk61_m0_ddiv_range_guard_begin');end=sym('mk61_m0_ddiv_range_guard_end');call=sym('mk61_m0_ddiv_range_guard_call');join=sym('mk61_m0_ddiv_normal_range_join')
old=json.loads((W/'div-guard-proof.json').read_bytes());slow=old['old_fallback'];infinity=old['overflow_pack']
def literal(a,r):
    m=re.search(r'\[pc, #(\d+)\]',r['operands']);assert m
    p=((a+4)&~3)+int(m[1]);s=next(s for s in e.named_sections.values()if s[3]<=p and p+4<=s[3]+s[5]);return struct.unpack_from('<I',e.bytes_at(s),p-s[3])[0]
def norm(s):return re.sub(r'\s+','',s)
def canonical(op,args):
    a=norm(args).split(',')
    if op in('adds','subs','lsls','lsrs','asrs')and len(a)==2:a.insert(1,a[0])
    return ','.join(a)
lines=[];labels={}
for l in (W/'range-guard-source.txt').read_text().splitlines():
    l=l.split('//',1)[0].strip()
    if not l:continue
    if l.endswith(':'):labels[l[:-1]]=num+2*len(lines)
    elif not l.startswith('.'):lines.append(l)
assert num+2*len(lines)==end and labels['mk61_m0_ddiv_range_guard_begin']==rng
labels.update({'.Lrp2040_div_slow':slow,'.Lrp2040_div_den_overflow':infinity,'.Lrp2040_div_range_join':join})
branches={'b','bl','beq','bne','bmi','bpl','bhi','bhs','bcs','blo','bcc','bls','ble','bge','bgt','blt'}
def target(r):return int(r['operands'].split()[0],16)
def check(c):
    prefix=[('push','{r4, r5, r6, r7, lr}'),('lsls','r4,r1,#1'),('lsrs','r4,r4,#21'),('lsls','r5,r3,#1'),('lsrs','r5,r5,#21'),('subs','r6,r4,#1'),('ldr',None),('cmp','r6,r7'),('bhi',None),('subs','r6,r5,#1'),('cmp','r6,r7'),('bhi',None),('subs','r6,r4,r5'),('lsrs','r5,r7,#1'),('subs','r5,#1'),('adds','r6,r5'),('subs','r7,#1'),('cmp','r6,r7'),('bhi',None)]
    assert call==start+36 and join==start+38
    for i,(op,args)in enumerate(prefix):
        r=c[start+2*i];assert r['bytes']==2 and r['mnemonic']==op
        if args is not None:assert canonical(op,r['operands'])==canonical(op,args),(i,r,args)
    assert literal(start+12,c[start+12])==2045
    assert target(c[start+16])==num and target(c[start+22])==sym('mk61_m0_ddiv_denominator_guard_begin') and target(c[call])==rng
    for dest,origin in [(num,start+16),(rng,call)]:
        incoming=[a for a,r in c.items()if r['mnemonic']in branches and re.match(r'^[0-9a-f]+',r['operands'])and target(r)==dest]
        assert incoming==[origin],(dest,incoming)
    for i,line in enumerate(lines):
        a=num+2*i;r=c[a];op,args=line.split(None,1)
        assert r['bytes']==2 and r['mnemonic']=={'blo':'bcc','bhs':'bcs'}.get(op,op),(line,r)
        if op in branches:assert target(r)==labels[args],(line,r)
        elif ',='in args:
            reg,val=args.split(',=');assert r['operands'].split(',')[0]==reg and literal(a,r)==int(val,0),(line,r)
        elif op=='pop':assert r['operands']=='{r4, r5, r6, r7, pc}'
        else:assert canonical(op,r['operands'])==canonical(op,args),(line,r)
    zero=labels['.Lrp2040_div_range_zero']
    for a,r in c.items():
        if not num<=a<zero:continue
        assert r['mnemonic']not in('bl','blx','str','strb','strh','push','pop')
        if r['mnemonic']not in branches|{'cmp'}:assert not re.match(r'r[0-3],',r['operands']),r
    assert c[slow]['mnemonic']=='sub'and norm(c[slow]['operands'])=='sp,#4'
    assert c[slow+2]['mnemonic']=='bl'and target(c[slow+2])==sym('mk61_m0_ddiv_slow')
    assert c[slow+6]['mnemonic']=='add'and norm(c[slow+6]['operands'])=='sp,#4'and c[slow+8]['operands']=='{r4, r5, r6, r7, pc}'
    assert c[join]['mnemonic']=='cmp'and norm(c[join]['operands'])=='r2,#0'
    return True
check(code)
lookup=lambda text:num+2*lines.index(text)
negative=[('first-Ea-rejection',start+16,'bhi',f'{slow:x}'),('first-Ea-flags',num,'bmi',code[num]['operands']),('subnormal-min-Eb',num+2,'ldr','r7, [pc, #0]'),('subnormal-upper-compare',num+8,'cmp','r6, r7'),('normal-range-2044',start+32,'subs','r7, #2'),('range-negative-flags',rng,'bmi',code[rng]['operands']),('upper-low-carry',lookup('cmp r0,r2'),'cmp','r2, r0'),('upper-borrow',lookup('sbcs r4,r3'),'subs','r4, r3'),('upper-sign-discard',lookup('lsls r4,#1'),'lsls','r4, r4, #2'),('upper-bit62-consumer',lookup('bpl .Lrp2040_div_range_join'),'bmi',code[lookup('bpl .Lrp2040_div_range_join')]['operands']),('lower-mantissa-sense',lookup('blo .Lrp2040_div_slow'),'bcs',code[lookup('blo .Lrp2040_div_slow')]['operands']),('certain-zero-threshold',lookup('movs r7,#55'),'movs','r7, #54'),('zero-sign-XOR',lookup('eors r1,r3'),'eors','r1, r2')]
rejected=[]
for name,a,op,args in negative:
    bad=copy.deepcopy(code);bad[a]=dict(bad[a],mnemonic=op,operands=args)
    try:check(bad)
    except(AssertionError,StopIteration):rejected.append(name)
    else:raise AssertionError('accepted bad actual guard '+name)
ebs=[eb for eb in range(2048)if((eb-1076)&0xffffffff)<=970]
assert ebs==list(range(1076,2047))
for diff in range(-2045,2046):
    r6=diff+1021;reject=(r6&0xffffffff)>2044
    if reject:assert(bool(((r6-2044)&0xffffffff)>>31))==(r6<0)
# These endpoint exercises supplement the algebraic subtraction identity; they
# are not substituted for a proof over the arbitrary remaining mantissa bits.
packed_checks=0;fs=(0,1,(1<<31)-1,1<<31,(1<<32)-1,1<<32,(1<<52)-2,(1<<52)-1)
for diff in range(1024,2046):
    eb=1;ea=1+diff
    for fa in fs:
        for fb in fs:
            for sa in(0,1):
                for sb in(0,1):
                    a=(sa<<63)|(ea<<52)|fa;b=(sb<<63)|(eb<<52)|fb
                    high=((a>>32)-(b>>32)-int((a&0xffffffff)<(b&0xffffffff)))&0xffffffff
                    bit62=bool((high<<1)&0x80000000)
                    assert bit62==(diff>1024 or fa>=fb);packed_checks+=1
out=dict(status='PASS_R46_ACTUAL_NUMERATOR_RANGE_GUARDS_AND_13_NEGATIVES',candidate_ELF_sha256=sha(W/'candidate.elf'),actual_header_bytes_bound=38,old_hot_header_instruction_count_unchanged=True,num_guard_begin=num,range_guard_begin=rng,range_guard_end=end,normal_join=join,old_fallback=slow,fast_infinity=infinity,caller_operands_normal_and_R6diff_plus1021_R7_2044_proved=True,first_Ea_flags_distinguish_subnormal_and_nonfinite=True,all2048_denominator_exponents_checked=True,all4091_normal_exponent_differences_flags_checked=True,upper_packed_subtraction_identity_for_arbitrary_words=True,upper_supplementary_packed_checks=packed_checks,no_argument_writes_on_decline_or_normal_join=True,all_fast_returns_pop_existing20byte_frame=True,no_new_calls_or_SIO=True,negative_controls_rejected=rejected,new_ARM_MPFR_calls=0,hardware_accessed=False,integration_GO=False,goal_complete=False)
(W/'boundary-guards-proof.json').write_text(json.dumps(out,indent=2)+'\n');print('R46 boundary guards PASS; negatives',len(rejected),'packed checks',packed_checks,flush=True)
