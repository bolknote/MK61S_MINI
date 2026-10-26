"""Fresh linked private R12 guard controls and literal pack rebuild binding."""
import ast,copy,hashlib,json,re,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-exp-near-one-20261024'
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):p=Path(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
proof=json.loads((W/'private-return-proof.json').read_text())
nodes=ast.parse((W/'verify-private-return.py').read_text()).body
parse=next(n for n in nodes if isinstance(n,ast.FunctionDef)and n.name=='parse')
env={'re':re};exec(compile(ast.Module(body=[parse],type_ignores=[]),'<actual-private-disassembly-parser>','exec'),env)
code=env['parse']((O/'candidate.actual.dis').read_text())
im=ElfImage(O/'rebuild/candidate.elf');start=im.symbols['mk61_m0_exp']&~1;end=start+im.sizes['mk61_m0_exp']
marker=im.symbols['mk61_m0_exp_fraction_capture']&~1;wrapper=im.symbols['mk61_m0_pow_exp_product_flash']&~1
body={a:r for a,r in code.items()if start<=a<end}
first=next(i for i,n in enumerate(nodes)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='calls'for t in n.targets))
last=next(i for i,n in enumerate(nodes)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='size'for t in n.targets))
compiled=compile(ast.Module(body=nodes[first:last],type_ignores=[]),'<actual-postcall-validator>','exec')
def check_post(b):
 e=dict(re=re,body=b,wrapper=wrapper,marker=marker);exec(compiled,e);return e
passed=check_post(body);entry=passed['entry'];negative=[]
for label,op,args in [('write','mov','ip, r0'),('read','mov','r0, ip'),('call','bl',f'{start:x}'),('indirect','blx','r0'),('return','pop','{r4, pc}'),('tail','bx','lr'),('PC','mov','pc, r0'),('outside','b',f'{start-2:x}'),('cycle','b',f'{entry:x}'),('conditional_escape','beq',f'{start-2:x}')]:
 b=copy.deepcopy(body);b[entry].update(mnemonic=op,operands=args)
 try:check_post(b)
 except (AssertionError,KeyError):negative.append(label)
 else:raise AssertionError(label)
live_fn=next(n for n in nodes if isinstance(n,ast.FunctionDef)and n.name=='live_range')
e=dict(re=re,marker=marker,consumer=int(proof['actual_consumer'],16),conditional={'beq','bne','bcs','bcc','bhs','blo','bmi','bpl','bvs','bvc','bhi','bls','bge','blt','bgt','ble'})
exec(compile(ast.Module(body=[live_fn],type_ignores=[]),'<actual-private-live-validator>','exec'),e)
live=e['live_range'](body);live_negative=[]
for label,op,args in [('write','mov','ip, r0'),('read','mov','r0, ip'),('call','bl',f'{start:x}'),('indirect','blx','r0'),('PC','mov','pc, r0'),('cycle','beq',f'{marker:x}'),('escape','b',f'{start-2:x}')]:
 b=copy.deepcopy(body);b[marker].update(mnemonic=op,operands=args)
 try:e['live_range'](b)
 except (AssertionError,KeyError):live_negative.append(label)
 else:raise AssertionError(label)
assert len(passed['visited'])==2 and len(live)-1==88 and len(negative)+len(live_negative)==17
guard=save('private-guard-controls.json',dict(status='PASS_FRESH_PRIVATE_LINKED_GUARD_AND17_NEGATIVE_AST_CONTROLS',
 actual_ELF=ref(O/'rebuild/candidate.elf'),fresh_disassembly=ref(O/'candidate.actual.dis'),source=ref(W/'verify-private-return.py'),
 two_postcall_instructions=len(passed['visited']),live_instructions=len(live)-1,postcall_rejections=negative,live_rejections=live_negative,
 exact_existing_Flash_veneer16=proof['original_wrapper_sha256'],production_fresh_validator_exit0=True,
 required_again_on_changed_actual_integrated_ELF=True,integration_GO=False))
frag=(W/'small-fragment.cpp').read_text();first=frag.index('  const unsigned shift=unsigned(16-e)');pack=frag[first:frag.rindex('\n}')]
pack=pack.replace('if(unsafe) return bits(exp_refine(real(a),0));','if(unsafe) return UINT64_MAX;')
expected='''#include <stdint.h>
using U=uint64_t;
extern "C" __attribute__((optimize("Os"))) U audit_exp_small_pack(U a,U correction,U error64) {
  const bool negative=bool(a>>63);
  const int e=int((a>>52)&2047U)-1023;
  const uint32_t lo=uint32_t(a),hi=(uint32_t(a>>32)&0xFFFFFU)|0x100000U;
  const U m=(U(hi)<<32)|lo;
  const uint32_t error=uint32_t(error64);
'''+pack+'\n}\n'
assert expected==(W/'pack-unit.cpp').read_text()
certificate=json.loads((W/'certificate.json').read_text());d=O/'literal-rebuild';d.mkdir();commands=[];results=[]
for oldcmd in certificate['commands']:
 cmd=list(oldcmd);oldout=Path(cmd[cmd.index('-o')+1]);cmd[cmd.index('-o')+1]=str(d/oldout.name)
 cmd=[str(d/'pack-unit.o')if x==str(W/'pack-unit.o')and i!=cmd.index('-o')+1 else x for i,x in enumerate(cmd)]
 p=subprocess.run(cmd,cwd=W,capture_output=True)
 (d/(oldout.name+'.stdout')).write_bytes(p.stdout);(d/(oldout.name+'.stderr')).write_bytes(p.stderr)
 assert p.returncode==0,p.stderr.decode();assert (d/oldout.name).read_bytes()==oldout.read_bytes()
 commands.append(cmd);results.append(ref(d/oldout.name))
unit=save('literal-unit-binding.json',dict(status='PASS_LITERAL_SOURCE_PACK_AND_TWO_WHOLE_EXACT_REBUILDS',
 source=ref(W/'pack-unit.cpp'),fragment_sha256=hashlib.sha256(pack.encode()).hexdigest(),commands=commands,results=results,
 only_fallback_sentinel_replaced=True,hardware_IO=0,integration_GO=False))
print(json.dumps(dict(guard=guard,unit=unit),indent=2))
