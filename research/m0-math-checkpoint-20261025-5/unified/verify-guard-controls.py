"""Exercise the actual producer/consumer validator AST on parsed code."""
from pathlib import Path
import ast,copy,hashlib,json,re,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
nodes=ast.parse((W/'verify-private-return.py').read_text()).body
parse=next(n for n in nodes if isinstance(n,ast.FunctionDef) and n.name=='parse')
env={'re':re};exec(compile(ast.Module(body=[parse],type_ignores=[]),'actual_parse','exec'),env)
proof=json.loads((W/'private-return-proof.json').read_text())
code=env['parse']((W/'candidate.dis').read_text())
start=int(proof['public_function_start'],16);end=start+proof['public_function_size']
marker=int(proof['private_output_definition_marker'],16);wrapper=int(proof['original_wrapper_address'],16)
body={a:r for a,r in code.items() if start<=a<end}
first=next(i for i,n in enumerate(nodes) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='calls' for t in n.targets))
last=next(i for i,n in enumerate(nodes) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='size' for t in n.targets))
compiled=compile(ast.Module(body=nodes[first:last],type_ignores=[]),'actual_CFG','exec')
def check(b):
 e=dict(re=re,body=b,wrapper=wrapper,marker=marker);exec(compiled,e);return e
passed=check(body);entry=passed['entry'];negative=[]
for label,op,args in [('R12_write','mov','ip, r0'),('R12_read','mov','r0, ip'),('call','bl',f'{start:x}'),('indirect_call','blx','r0'),('return','pop','{r4, pc}'),('tail_return','bx','lr'),('PC_write','mov','pc, r0'),('outside','b',f'{start-2:x}'),('cycle','b',f'{entry:x}'),('conditional_escape','beq',f'{start-2:x}')]:
 b=copy.deepcopy(body);b[entry]['mnemonic']=op;b[entry]['operands']=args
 try:check(b)
 except (AssertionError,KeyError):negative.append(label)
 else:raise AssertionError('Accepted invalid post-call window: '+label)
live_fn=next(n for n in nodes if isinstance(n,ast.FunctionDef) and n.name=='live_range')
e=dict(re=re,marker=marker,consumer=int(proof['actual_consumer'],16),conditional={'beq','bne','bcs','bcc','bhs','blo','bmi','bpl','bvs','bvc','bhi','bls','bge','blt','bgt','ble'})
exec(compile(ast.Module(body=[live_fn],type_ignores=[]),'actual_liveness','exec'),e)
live=e['live_range'](body);live_negative=[]
for label,op,args in [('R12_write','mov','ip, r0'),('R12_read','mov','r0, ip'),('call','bl',f'{start:x}'),('indirect_call','blx','r0'),('PC_write','mov','pc, r0'),('self_cycle','beq',f'{marker:x}'),('escape','b',f'{start-2:x}')]:
 b=copy.deepcopy(body);b[marker]['mnemonic']=op;b[marker]['operands']=args
 try:e['live_range'](b)
 except (AssertionError,KeyError):live_negative.append(label)
 else:raise AssertionError('Accepted invalid marker-to-use live range: '+label)
out=dict(status='PASS_ACTUAL_LINKED_PRIVATE_GUARD_POSITIVE_AND_REJECTION_CONTROLS',
 candidate_ELF_sha256=proof['candidate_ELF_sha256'],actual_fresh_disassembly_sha256=proof['actual_fresh_disassembly_sha256'],
 exact_production_AST_used=True,postcall_negative_controls=negative,marker_to_consumer_negative_controls=live_negative,
 positive_postcall_instructions=len(passed['visited']),positive_live_instructions=len(live)-1,
 no_firmware_execution_or_hardware=True)
(W/'private-guard-controls.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
