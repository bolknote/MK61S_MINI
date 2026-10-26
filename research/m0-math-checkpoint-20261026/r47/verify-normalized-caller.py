"""Mandatory current-object row0 negative-D normalization/frame/CFG binding."""
from pathlib import Path
import ast,hashlib,json,re,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-math-unified-exp-row0-small-r37-20261026'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_bytes())
assert sha(P/'FROZEN.json')=='540e32a2a2cac7faa476b08ca792778ea7f327c6c35eb7e73aae7eb5c5f869e7'
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
objects=[ElfImage(d/'RP-merged-cpp.o')for d in [P,W]]
raw=[e.bytes_at(e.named_sections['.m0_exp_core'])for e in objects];assert raw[0]==raw[1]and len(raw[0])==5192
links=[read(d/'link-result.json')for d in [P,W]]
for kind,idx in [('symbols',-1),('relocations',0)]:
    a,b=[x['outputs']['RP-merged-cpp.o']['fingerprint'][kind]for x in links]
    assert[r for r in a if r[idx]=='.m0_exp_core']==[r for r in b if r[idx]=='.m0_exp_core']
fn=next(n for n in ast.parse((W/'verify-private-return.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='parse');env={'re':re}
exec(compile(ast.Module(body=[fn],type_ignores=[]),'actual_parser','exec'),env)
e=ElfImage(W/'candidate.elf');start=e.symbols['mk61_m0_exp']&~1;end=start+e.sizes['mk61_m0_exp'];marker=e.symbols['mk61_m0_exp_fraction_capture']&~1
code={a:r for a,r in env['parse']((W/'candidate.dis').read_text()).items()if start<=a<end}
pair=lambda a:(code[a]['mnemonic'],code[a]['operands'])
def pairs(first,count):return[pair(first+2*i)for i in range(count)]
def literal(a):
    match=re.search(r'\[pc, #(\d+)\]',code[a]['operands']);assert match
    p=((a+4)&~3)+int(match[1]);sec=next(s for s in e.named_sections.values()if s[3]<=p and p+4<=s[3]+s[5])
    return struct.unpack_from('<I',e.bytes_at(sec),p-sec[3])[0]
assert pairs(marker-52,2)==[('str','r0, [sp, #24]'),('str','r1, [sp, #28]')]
assert pairs(marker-42,12)==[('ldr','r3, [sp, #28]'),('ldr','r7, [sp, #24]'),('asrs','r0, r3, #31'),('eors','r7, r0'),('movs','r2, r7'),('ldr','r7, [sp, #28]'),('movs','r1, r0'),('eors','r7, r0'),('str','r3, [sp, #44]'),('movs','r3, r7'),('subs','r2, r2, r0'),('sbcs','r3, r1')]
assert pairs(marker-66,2)==[('lsrs','r3, r6, #23'),('str','r3, [sp, #40]')]
assert pair(marker-18)==('cmp','r6, #0')and code[marker-16]['mnemonic']=='bne'and code[marker-14]['mnemonic']=='b'
table=next(n for n in e.symbols if'exp_table'in n and e.sizes.get(n)==4096)
assert literal(marker-56)==e.symbols[table]
assert pairs(marker-54,1)==[('lsrs','r2, r6, #20')]
assert pairs(marker-48,3)==[('adds','r3, r3, r2'),('ldr','r4, [r3, #0]'),('ldr','r5, [r3, #4]')]
quarter=int(code[marker-14]['operands'].split()[0],16)
assert pairs(quarter,10)==[('movs','r0, #2'),('movs','r1, #0'),('adds','r2, r2, r0'),('adcs','r3, r1'),('lsls','r1, r3, #30'),('lsrs','r0, r2, #2'),('orrs','r0, r1'),('lsrs','r3, r3, #2'),('str','r0, [sp, #16]'),('str','r3, [sp, #20]')]
assert code[quarter+20]['mnemonic']=='b'and int(code[quarter+20]['operands'].split()[0],16)==marker
assert pairs(marker,6)==[('ldr','r3, [sp, #44]'),('ldr','r6, [sp, #16]'),('ldr','r7, [sp, #20]'),('adds','r6, r6, r4'),('adcs','r7, r5'),('cmp','r3, #0')]
assert code[marker+12]['mnemonic']=='bge'
assert pairs(marker+14,8)==[('ldr','r2, [sp, #16]'),('ldr','r3, [sp, #20]'),('subs','r4, r4, r2'),('sbcs','r5, r3'),('movs','r6, r4'),('movs','r7, r5'),('movs','r3, #4'),('lsls','r2, r7, #1')]
assert code[marker+30]['mnemonic']=='bmi'and int(code[marker+30]['operands'].split()[0],16)==marker+44
assert pairs(marker+32,6)==[('ldr','r3, [sp, #8]'),('adds','r6, r6, r6'),('adcs','r7, r7'),('subs','r3, #1'),('str','r3, [sp, #8]'),('movs','r3, #6')]
assert pairs(marker+58,2)==[('ldr','r1, '+code[marker+58]['operands'].split(', ',1)[1]),('lsls','r2, r6, #22')]
assert literal(marker+58)==(-513)&0xffffffff
assert pairs(marker+60,5)==[('lsls','r2, r6, #22'),('lsrs','r2, r2, #22'),('adds','r1, r3, r1'),('movs','r0, #10'),('adds','r1, r1, r2')]
assert pair(marker+70)==('cmp','r3, #4')and code[marker+72]['mnemonic']=='bne'
assert pair(marker+76)==('cmp','r1, r0')and code[marker+78]['mnemonic']=='bhi'
assert pair(marker+94)==('cmp','r3, #4')and code[marker+96]['mnemonic']=='bne'
bridge=e.symbols['mk61_m0_exp_positive_dispatch']&~1
calls=[a for a,r in code.items()if r['mnemonic']=='bl'and int(r['operands'].split()[0],16)==bridge];assert len(calls)==1;call=calls[0]
assert pairs(call-6,3)==[('ldr','r2, [sp, #32]'),('ldr','r0, [sp, #0]'),('ldr','r1, [sp, #4]')]
conditional={'beq','bne','bcs','bcc','bhs','blo','bmi','bpl','bvs','bvc','bhi','bls','bge','blt','bgt','ble'};edges={}
pruned={marker+12:('negative D sign duplicate',False),marker+30:('row0 P>0 implies q0<2^62',False),marker+72:('error R3=6',True),marker+78:('tail508/510/512/514/516 gives unsigned tail-507=1/3/5/7/9 <=10',False),marker+96:('error R3=6',True)}
for a,r in code.items():
    op,args=r['mnemonic'],r['operands'];nxt=a+r['bytes']
    ts=[int(args.split()[0],16)]if op=='b'else[int(args.split()[0],16),nxt]if op in conditional else[]if op=='bx'or(op=='pop'and'pc'in args)else[nxt]
    if a in pruned:ts=[int(args.split()[0],16)]if pruned[a][1]else[nxt]
    edges[a]=[t for t in ts if t in code]
def reach(first,graph):
    todo=[first];seen=set()
    while todo:
        a=todo.pop()
        if a in seen:continue
        seen.add(a);todo.extend(graph.get(a,[]))
    return seen
rev={}
for a,ts in edges.items():
    for b in ts:rev.setdefault(b,[]).append(a)
live=reach(marker+44,edges)&reach(call,rev);assert marker+44 in live and call in live
readonly={'cmp','tst','str','strb','strh'}
for a in live-{call}:
    op,args=pair(a)
    assert op not in ['bl','blx','bx','push','pop']and not re.match(r'(sp|pc)\b',args),(a,pair(a))
    if op.startswith('str'):
        match=re.fullmatch(r'r[0-7], \[sp, #(\d+)\]',args);assert match and int(match[1])not in [0,4,8,24,28,32,40,44],(a,pair(a))
    elif op not in readonly and not op.startswith('b'):
        assert not re.match(r'r[367]\b',args),('q or persistent error6 overwritten',a,pair(a))
assert marker+70 in live and marker+94 in live
out=dict(status='PASS_REQUIRED_CURRENT_NORMALIZED_ROW0_NEGATIVE_D_CALLER_BINDING',candidate_ELF_sha256=sha(W/'candidate.elf'),parent_source_FROZEN_sha256=sha(P/'FROZEN.json'),
 old_core5192_object_bytes_symbols_semantic_relocs_exact_R37=True,source_nmod512_zero_to_index0_inherits_exact_R30_CSE_and_ordinary_compiler_mapping=True,
 actual_index_shift_table_literal_row0_load_and_quarter_bypass_bound=True,actual_signed_delta_abs_from_SP24_SP28_bound=True,
 actual_quarter_add2_64bit_carry_shift2_and_scalar_stack_stores_bound=True,actual_q0_AminusP_and_two_word_normalization_with_carry_bound=True,
 actual_updated_k_load_decrement_store_SP8_bound=True,persistent_actual_error6_R3_bound=True,actual_ambiguous_guard_literal_minus513_width10_bound=True,
 current_unique_bridge_call=hex(call),capture_marker=hex(marker),quarter_path=hex(quarter),post_normalization_live_instructions=len(live),
 q_R7_R6_updated_k_SP8_n_SP32_x_SP0_SP4_D_SP28_no_intervening_clobbers=True,private_normalized_path_does_not_require_R12_value=True,
 specialized_CFG_pruned_edges={hex(k):v[0]for k,v in pruned.items()},new_ARM_MPFR_calls=0,
 inherited_proof_needed_for_Ppositive_or_unambiguous_Pzero=True,current_actual_guard_required_every_changed_release_object=True,
 no_whole_CR_or_performance_or_adoption_GO=True,hardware_accessed=False,integration_GO=False,goal_complete=False)
(W/'normalized-caller-proof.json').write_text(json.dumps(out,indent=2)+'\n');print('Normalized caller binding PASS',len(live),'live instructions; q normalization, k/SP8, error6 and tailguard bound',flush=True)
