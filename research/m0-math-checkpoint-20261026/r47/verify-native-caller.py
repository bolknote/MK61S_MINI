"""Mandatory actual linked carry-contract guard, with deliberate broken controls."""
from pathlib import Path
import ast,copy,hashlib,json,re,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
parsefn=next(n for n in ast.parse((W/'verify-private-return.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='parse');env={'re':re};exec(compile(ast.Module(body=[parsefn],type_ignores=[]),'actual_parser','exec'),env)
e=ElfImage(W/'candidate.elf');code=env['parse']((W/'candidate.dis').read_text());native=e.symbols['mk61_m0_pow_rsqrt_local_q8_native']&~1;ordinary=e.symbols['mk61_m0_pow_rsqrt_local_q8']&~1;frame=e.symbols['mk61_m0_pow_rsqrt_q8_frame_ready']&~1
def literal(a,r):
    m=re.search(r'\[pc, #(\d+)\]',r['operands']);assert m
    p=((a+4)&~3)+int(m[1]);sec=next(s for s in e.named_sections.values()if s[3]<=p and p+4<=s[3]+s[5]);return struct.unpack_from('<I',e.bytes_at(sec),p-sec[3])[0]
def check(c):
    calls=[a for a,r in c.items()if r['mnemonic']=='bl'and int(r['operands'].split()[0],16)==native];assert calls==[frame+2]
    assert not[a for a,r in c.items()if r['mnemonic']=='bl'and int(r['operands'].split()[0],16)==ordinary]
    expected=[('ldr','r2, [sp, #28]'),('ldr',None),('subs','r2, r2, r3'),('cmp','r2, #1'),('bhi',None),('str','r0, [sp, #36]'),('str','r1, [sp, #40]'),('str','r5, [sp, #8]'),('mov','r0, sp'),('bl',None)]
    for i,(op,args)in enumerate(expected):
        a=frame-16+2*i;r=c[a];assert r['mnemonic']==op and(args is None or r['operands']==args)
        assert r['bytes']==(4 if op=='bl'else 2)
    assert literal(frame-14,c[frame-14])==0x7fffffff
    rejected=int(c[frame-8]['operands'].split()[0],16)
    assert rejected<frame-16 and c[rejected]['mnemonic']=='lsls'and c[rejected]['operands']=='r2, r1, #22'
    assert[(c[native+2*i]['mnemonic'],c[native+2*i]['operands'])for i in range(3)]==[('push','{r4, r5, r6, r7, lr}'),('mov','r4, r0'),('sbcs','r0, r0')]
    assert[(c[ordinary+2*i]['mnemonic'],c[ordinary+2*i]['operands'])for i in range(6)]==[('push','{r4, r5, r6, r7, lr}'),('mov','r4, r0'),('ldr','r0, [r4, #28]'),('asrs','r0, r0, #31'),('mvns','r0, r0'),('b',c[ordinary+10]['operands'])]
    common=int(c[ordinary+10]['operands'].split()[0],16);assert common==native+6
    assert[(c[common+2*i]['mnemonic'],c[common+2*i]['operands'])for i in range(3)]==[('ldr','r5, [r4, #24]'),('ldr','r6, [r4, #20]'),('eors','r0, r6')]
    return dict(callsite=frame+2,native_entry=native,ordinary_entry=ordinary,common=common,rejected_other_factor_target=rejected)
actual=check(code);negatives=[]
edits=[('wrong-factor-offset',frame-16,'ldr','r2, [sp, #24]'),('wrong-difference',frame-12,'subs','r2, r2, r0'),('wrong-CMP-constant',frame-10,'cmp','r2, #0'),('wrong-CMP-register',frame-10,'cmp','r3, #1'),('wrong-domain-branch',frame-8,'bls',code[frame-8]['operands']),('missing-frame-qlo',frame-6,'movs','r0, #0'),('flag-clobber-after-guard',frame-4,'adds','r1, #0'),('flag-clobber-before-call',frame,'lsrs','r0, r0, #1'),('wrong-call-entry',frame+2,'bl',f'{ordinary:x}'),('wrong-native-prologue',native+2,'movs','r4, #0'),('wrong-SBC',native+4,'sbcs','r0, r1'),('generic-flag-contract-break',ordinary+4,'sbcs','r0, r0')]
for name,at,op,args in edits:
    bad=copy.deepcopy(code);bad[at]=dict(bad[at],mnemonic=op,operands=args)
    try:check(bad)
    except AssertionError:negatives.append(name)
    else:raise AssertionError('guard accepted broken control '+name)
truth=[]
for high in (0x7fffffff,0x80000000):
    diff=(high-0x7fffffff)&0xffffffff;C=int(diff>=1);mask=-(1-C)&0xffffffff;assert diff<=1 and mask==(0 if high>>31 else 0xffffffff)
    truth.append(dict(Fhi=high,difference=diff,C=C,SBC_mask=mask))
out=dict(status='PASS_R43_MANDATORY_LINKED_NATIVE_CARRY_CONTRACT_AND_12_NEGATIVE_CONTROLS',candidate_ELF_sha256=sha(W/'candidate.elf'),actual=actual,guard_instructions=[code[frame-16+2*i]for i in range(10)],integer_truth=truth,all_native_calls_guarded_unique=True,ordinary_entry_never_uses_incoming_flags=True,all_intervening_STR_MOV_BL_and_native_PUSH_MOV_preserve_C=True,negative_controls_rejected=negatives,mandatory_after_each_changed_release_object=True,new_ARM_MPFR_calls=0,hardware_accessed=False,integration_GO=False,goal_complete=False)
(W/'native-caller-proof.json').write_text(json.dumps(out,indent=2)+'\n');print('native carry guard PASS; negatives',len(negatives),flush=True)
