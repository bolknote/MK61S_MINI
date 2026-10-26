"""Mandatory compiler-specific caller binding for the private cold bridge."""
from pathlib import Path
import ast,hashlib,json,re,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-math-unified-exp-cached-index-r30-20261026'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(P/'FROZEN.json')=='7c4ea69858bdaa995868aa1b5b70f112315e726f17aeaf719c9049ff6533bfb1'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
objects=[ElfImage(d/'RP-merged-cpp.o')for d in [P,W]]
raw=[e.bytes_at(e.named_sections['.m0_exp_core'])for e in objects]
assert len(raw[0])==len(raw[1])==5192
off=5012;assert raw[0][:off]+raw[0][off+4:]==raw[1][:off]+raw[1][off+4:]
for name in ['mk61_m0_exp','mk61_m0_exp_fraction_capture','exp_refine']:
    assert objects[0].symbols[name]==objects[1].symbols[name]and objects[0].sizes.get(name)==objects[1].sizes.get(name)
links=[json.loads((d/'link-result.json').read_bytes())for d in [P,W]]
rel=[x['outputs']['RP-merged-cpp.o']['fingerprint']['relocations']for x in links]
old=[r for r in rel[0]if r[0]=='.m0_exp_core'];new=[r for r in rel[1]if r[0]=='.m0_exp_core']
assert old==[r for r in new if r[1]!=off]
assert [r for r in new if r[1]==off]==[['.m0_exp_core',off,10,'mk61_m0_exp_positive_dispatch']]
nodes=ast.parse((W/'verify-private-return.py').read_text()).body
fn=next(n for n in nodes if isinstance(n,ast.FunctionDef)and n.name=='parse');env={'re':re}
exec(compile(ast.Module(body=[fn],type_ignores=[]),'actual_parse','exec'),env)
e=ElfImage(W/'candidate.elf');start=e.symbols['mk61_m0_exp']&~1;end=start+e.sizes['mk61_m0_exp'];marker=e.symbols['mk61_m0_exp_fraction_capture']&~1
code={a:r for a,r in env['parse']((W/'candidate.dis').read_text()).items()if start<=a<end}
bridge=e.symbols['mk61_m0_exp_positive_dispatch']&~1
calls=[a for a,r in code.items()if r['mnemonic']=='bl'and int(r['operands'].split()[0],16)==bridge];assert len(calls)==1;call=calls[0]
assert call-start==off-(objects[1].symbols['mk61_m0_exp']&~1)
def pair(a):return code[a]['mnemonic'],code[a]['operands']
assert [pair(a)for a in [call-6,call-4,call-2]]==[('ldr','r2, [sp, #32]'),('ldr','r0, [sp, #0]'),('ldr','r1, [sp, #4]')]
assert [pair(marker+x)for x in range(0,10,2)]==[('ldr','r3, [sp, #44]'),('ldr','r6, [sp, #16]'),('ldr','r7, [sp, #20]'),('adds','r6, r6, r4'),('adcs','r7, r5')]
conditional={'beq','bne','bcs','bcc','bhs','blo','bmi','bpl','bvs','bvc','bhi','bls','bge','blt','bgt','ble'}
ordered=sorted(code);edges={};pruned=[]
readonly={'cmp','tst','str','strb','strh','push'}
for i,a in enumerate(ordered):
    r=code[a];op=r['mnemonic'];args=r['operands'];nxt=a+r['bytes']
    ts=[int(args.split()[0],16)]if op=='b'else[int(args.split()[0],16),nxt]if op in conditional else[]if op=='bx'or(op=='pop'and'pc'in args)else[nxt]
    if op in ['bge','blt','bmi','bpl']and i and pair(ordered[i-1])==('cmp','r3, #0'):
        definition=None
        for b in reversed(ordered[max(0,i-9):i-1]):
            br=code[b]
            if re.match(r'r3\b',br['operands'])and br['mnemonic']not in readonly and not br['mnemonic'].startswith('b'):
                definition=pair(b);break
        if definition==('ldr','r3, [sp, #44]'):
            ts=[int(args.split()[0],16)]if op in ['bge','bpl']else[nxt];pruned.append(dict(address=hex(a),reason='eligible delta_high>=0 and SP44 equals SP28'))
    if op=='bmi'and i and pair(ordered[i-1])==('lsls','r2, r7, #1'):
        ts=[int(args.split()[0],16)];pruned.append(dict(address=hex(a),reason='A+P>=2^62 and global q<2^63 =>error4'))
    edges[a]=[t for t in ts if t in code]
def reach(first,graph):
    pending=[first];seen=set()
    while pending:
        a=pending.pop()
        if a in seen:continue
        seen.add(a);pending.extend(graph.get(a,[]))
    return seen
rev={}
for a,ts in edges.items():
    for b in ts:rev.setdefault(b,[]).append(a)
live=reach(marker+10,edges)&reach(call,rev);assert marker+10 in live and call in live and len(pruned)==3
for a in live-{call}:
    r=code[a];op=r['mnemonic'];args=r['operands']
    assert op not in ['bl','blx','bx','push','pop']and not re.match(r'pc\b',args),(a,r)
    assert not re.search(r'\b(?:ip|r12)\b',args),('eligible fraction touched',a,r)
    assert not re.match(r'sp\b',args),('caller SP changed',a,r)
    if op.startswith('str'):
        m=re.fullmatch(r'r[0-7], \[sp, #(\d+)\]',args);assert m,(a,r)
        assert int(m[1])not in [0,4,8,28,32,44],('metadata overwritten',a,r)
    elif op not in readonly and not op.startswith('b'):
        assert not re.match(r'r[67]\b',args),('q overwritten',a,r)
assert [pair(marker-50),pair(marker-42),pair(marker-40)]==[('str','r1, [sp, #28]'),('ldr','r3, [sp, #28]'),('ldr','r7, [sp, #24]')]
assert pair(marker-26)==('str','r3, [sp, #44]')
out=dict(status='PASS_REQUIRED_CURRENT_OBJECT_COLD_BRIDGE_CALLER_BINDING',candidate_ELF_sha256=sha(W/'candidate.elf'),parent_FROZEN_sha256=sha(P/'FROZEN.json'),
 parent_core_sha256=hashlib.sha256(raw[0]).hexdigest(),current_core_sha256=hashlib.sha256(raw[1]).hexdigest(),core_bytes=5192,
 only_old_core_machine_code_change_one4byte_callsite=True,callsite_section_offset=off,all_other_core_bytes_and_semantic_relocations_exact=True,
 current_unique_bridge_call=hex(call),capture_marker=hex(marker),caller_x_n_exact_APCS_preparation=True,
 positive_displacement_q_after_capture='R7:R6=A+P',delta_high_SP_offset=28,duplicate_sign_SP_offset=44,k_SP_offset=8,n_SP_offset=32,
 eligible_pruned_edges=pruned,eligible_live_instructions=len(live),eligible_no_calls_SP_changes_R12_touches_q_or_metadata_writes=True,
 fraction_nonzero_index_is_same_actual_leaf_R12=True,row0_must_use_bridge_constant_not_R12=True,
 baseline_CPP_used_noipa_refine_body_machine_bytes_exact=True,compiler_flags_dependent_private_contract=True,
 required_again_every_changed_release_object=True,no_new_ARM_MPFR_calls=True,hardware_accessed=False,integration_GO=False,goal_complete=False)
(W/'private-caller-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print('Private caller binding PASS; only BL changed; eligible metadata live',len(live),'nodes',flush=True)
