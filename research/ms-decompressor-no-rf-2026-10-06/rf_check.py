"""Prove that native setup, unpacker and game do not access RF."""
from pathlib import Path
import json,os,re,subprocess,sys
from psycho_sfx import CELL,EXPECTED,TAIL,KERNEL,BANK
HERE=Path(__file__).resolve().parent
runner=Path(sys.argv[1]).resolve()
source=(HERE/'psycho-selfextract.m61').read_text()
for line in source.splitlines():
 if line.startswith('hin '):
  _,address,data=line.split();address=int(address)
  assert all((address+i)%112<105 for i in range(len(bytes.fromhex(data))))
# Test setup is native calculator input, and stops before the real program.
# The driver installs its instruction hook only after this stop, excluding
# the intentional canary write from the candidate's instruction trace.
source=re.sub(r'(?m)^hin 0000 ', 'hin 0000 0d09080706050a04034f50',source)
folder=HERE/'rf-canary';folder.mkdir(exist_ok=True)
(folder/'autoexec.m61').write_text(source)
route=[4,11,7,8,15,35,21,22,29,36,43,49,3,17,73]
commands='dump\nrun\n'+''.join(f'goto {a:02d}\n' for a in route)+'restart 0\n'+''.join(f'goto {a:02d}\n' for a in CELL.values())
p=subprocess.run([str(runner),str(folder)],input=commands,text=True,capture_output=True,check=True,env=dict(os.environ,ELITE_TRACE='1'))
states=[json.loads(s) for s in p.stdout.splitlines()]
assert len(states)==48 and not any(s['error'] or s['running'] for s in states)
rf=states[0]['reg_words'][15]
assert states[0]['regs'][15]==98765.43
assert all(s['reg_words'][15]==rf for s in states)
assert states[16]['x']==30 and states[16]['regs'][13:15]==[5,3]
assert states[17]['x']==0 and states[17]['regs'][13:15]==[5,3]
assert all(s['output_code'][0]==EXPECTED.hex() and s['output_tail'][0]==(TAIL+KERNEL+bytes(112-len(EXPECTED)-len(TAIL)-len(KERNEL))).hex() for s in states[1:])
trace=[]
for line in p.stderr.splitlines():
 m=re.match(r'(\d+) op=([0-9a-f]+) ',line)
 if m:trace.append((int(m[1]),int(m[2],16)))
assert trace and max(a%112 for a,b in trace)==102
rf_ops={0x4f,0x6f,0x7f,0x8f,0x9f,0xaf,0xbf,0xcf,0xdf,0xef,0xff}
assert not [(a,b) for a,b in trace if b in rf_ops]
(folder/'states.json').write_text(json.dumps(states,indent=2)+'\n')
(folder/'native-trace.txt').write_text(p.stderr)
report={'rf_canary':98765.43,'rf_preserved_byte_for_byte':True,'rf_access_instructions':0,'native_commands_checked':len(trace),'checked_stops':len(states),'all_map_cells_checked':len(CELL),'victory_x':states[16]['x'],'restart_x':states[17]['x'],'maximum_local_address_loaded_and_executed':102,'uses_only_registers_0_through_e':True,'requires_expanded_mode_for_ms_and_banks':True}
(HERE/'rf-check.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
