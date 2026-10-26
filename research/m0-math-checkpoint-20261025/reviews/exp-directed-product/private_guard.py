"""Exact production guard controls and actual marker-to-use liveness."""
import ast,copy,json,re,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-exp-directed-product-20261024'
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
source=(W/'verify-private-return.py').read_text();nodes=ast.parse(source).body
fn=next(n for n in nodes if isinstance(n,ast.FunctionDef)and n.name=='parse')
env={'re':re};exec(compile(ast.Module(body=[fn],type_ignores=[]),'actual_guard_parse','exec'),env)
code=env['parse']((O/'candidate.actual.dis').read_text());im=ElfImage(W/'candidate.elf')
start=im.symbols['mk61_m0_exp']&~1;end=start+im.sizes['mk61_m0_exp'];marker=im.symbols['mk61_m0_exp_fraction_capture']
wrapper=im.symbols['mk61_m0_pow_exp_product_flash']&~1
body={a:r for a,r in code.items()if start<=a<end}
# Execute the exact sealed production CFG validator AST on actual parsed instructions.
first=next(i for i,n in enumerate(nodes)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='calls'for t in n.targets))
last=next(i for i,n in enumerate(nodes)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='size'for t in n.targets))
compiled=compile(ast.Module(body=nodes[first:last],type_ignores=[]),'actual_guard_CFG','exec')
def check(b):
 e=dict(re=re,body=b,wrapper=wrapper,marker=marker);exec(compiled,e);return e
passed=check(body);entry=passed['entry'];assert sorted(passed['visited'])==[entry,entry+2]
negative=[]
for label,mnemonic,operands in [('R12_write','mov','ip, r0'),('R12_read','mov','r0, ip'),('call','bl','101a0280'),('indirect_call','blx','r0'),('return','pop','{r4, pc}'),('tail_return','bx','lr'),('PCwrite','mov','pc, r0'),('outside_branch','b','101a1116'),('cycle','b',f'{entry:x}'),('conditional_escape','beq','101a1116')]:
 b=copy.deepcopy(body);b[entry]['mnemonic']=mnemonic;b[entry]['operands']=operands
 try:check(b)
 except(AssertionError,KeyError):negative.append(label)
 else:raise AssertionError('production guard accepted '+label)
# A real Thumb R12-clobber word in the linked post-call window also rejects.
actual=(O/'candidate.actual.dis').read_text();changed=actual.replace('101a14ec:\t9004      \tstr\tr0, [sp, #16]','101a14ec:\t4684      \tmov\tip, r0')
assert changed!=actual
try:check({a:r for a,r in env['parse'](changed).items()if start<=a<end})
except AssertionError:negative.append('actual_disassembly_R12_clobber')
else:raise AssertionError('actual parser failed to reject clobber')
# The marker is a zero-byte compiler definition; inspect its actual live range
# through the eventual MOV r0,ip rather than assuming the definition saves a value.
use=next(a for a,r in body.items()if a>=marker and r['mnemonic']=='mov'and r['operands']=='r0, ip')
conditional={'beq','bne','bcs','bcc','bhs','blo','bmi','bpl','bvs','bvc','bhi','bls','bge','blt','bgt','ble'}
edges={}
for a,r in body.items():
 op=r['mnemonic'];args=r['operands'];nxt=a+r['bytes']
 if op=='b':targets=[int(args.split()[0],16)]
 elif op in conditional:targets=[int(args.split()[0],16),nxt]
 elif op in('bx',)or(op=='pop'and re.search(r'\bpc\b',args)):targets=[]
 else:targets=[nxt]
 edges[a]=[t for t in targets if t in body]
rev={}
for a,targets in edges.items():
 for t in targets:rev.setdefault(t,[]).append(a)
def reach(first,graph):
 seen=set();pending=[first]
 while pending:
  a=pending.pop()
  if a in seen:continue
  seen.add(a);pending.extend(graph.get(a,[]))
 return seen
live=reach(marker,edges)&reach(use,rev);assert marker in live and use in live
for a in live-{use}:
 r=body[a];assert r['mnemonic']not in('bl','blx','bx')and not re.search(r'\b(?:ip|r12)\b',r['operands']),(a,r)
out=dict(status='PASS_OWN_ACTUAL_PRIVATE_RETURN_GUARD_AND_LIVE_RANGE',
 actual_production_AST=True,positive_actual_postcall_instructions=2,negative_controls=negative,
 marker=hex(marker),consumer=hex(use),live_instructions_before_use=len(live)-1,
 no_R12_touch_or_call_on_any_marker_to_consumer_path=True,
 actual_pack_path_R12_reuse_after_consumption_or_on_nonconsumer_path_allowed=True,
 actual_16byte_Flash_tail_veneer_and_77instruction_producer_bound_by_binding=True,
 integration_requirement='Re-run against actual integrated ELF, its fresh disassembly, actual veneer and compiler/flags; preserve verified private producer-to-definition and definition-to-use dataflow. The scalar C prototype alone is insufficient.',
 no_generic_multiple_return_ABI_claim=True,hardware=False)
with(O/'private-guard.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(out,indent=2))
