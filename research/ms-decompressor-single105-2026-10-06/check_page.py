"""Verify the saved, single-page M61 and check all startup bytes and trace game commands."""
from pathlib import Path
import json,os,re,subprocess,sys
from psycho_sfx import CELL,EXPECTED,TAIL,KERNEL
HERE=Path(__file__).resolve().parent;runner=Path(sys.argv[1]).resolve()
source=(HERE/'psycho-selfextract.m61').read_text()
loaded=0;highest=-1
for line in source.splitlines():
 if line.startswith('hin '):
  _,a,h=line.split();a=int(a);data=bytes.fromhex(h)
  assert 0<=a and a+len(data)<=105
  highest=max(highest,a+len(data)-1);loaded+=len(data)
assert highest==102 and loaded==57
# Canary is ordinary M61 initialization. The production file has no RF line.
source=source.replace('\nrun\n','\nRF= 98765.43\nrun\n',1)
folder=HERE/'saved-page-check';folder.mkdir(exist_ok=True)
(folder/'autoexec.m61').write_text(source)
route=[4,11,7,8,15,35,21,22,29,36,43,49,3,17,73]
commands='dump\n'+''.join(f'goto {a:02d}\n' for a in route)+'restart 0\n'+''.join(f'goto {a:02d}\n' for a in CELL.values())
r=subprocess.run([str(runner),str(folder)],input=commands,text=True,capture_output=True,check=True,env=dict(os.environ,ELITE_TRACE='1'))
states=[json.loads(line) for line in r.stdout.splitlines()]
assert len(states)==47 and all(not s['error'] and not s['running'] for s in states)
assert states[15]['x']==30 and states[15]['regs'][13:15]==[5,3]
assert states[16]['x']==0 and states[16]['regs'][13:15]==[5,3]
assert all(s['regs'][15]==98765.43 and s['reg_words'][15]==states[0]['reg_words'][15] for s in states)
assert all(s['output_code'][0]==EXPECTED.hex() and s['output_tail'][0]==(TAIL+KERNEL+bytes(9)).hex() for s in states)
trace=[]
for line in r.stderr.splitlines():
 m=re.match(r'(\d+) op=([0-9a-f]+) ',line)
 if m:trace.append((int(m[1]),int(m[2],16)))
assert trace and max(a for a,b in trace)<105
assert all(0<=a<105 for a,b in trace)
assert (0,0x54) in trace and (1,0x60) in trace
assert not [b for a,b in trace if b in {0x4f,0x6f,0x7f,0x8f,0x9f,0xaf,0xbf,0xcf,0xdf,0xef,0xff}]
assert all(b!=0x1f for a,b in trace)
(folder/'states.json').write_text(json.dumps(states,indent=2)+'\n')
(folder/'native-trace.txt').write_text(r.stderr)
report={'loaded_native_bytes':loaded,'highest_address_written':highest,'highest_game_address_traced':max(a for a,b in trace),'all_commands_in_00_through_104':True,'extra_banks':0,'rf_preserved_byte_for_byte':True,'rf_access_commands':0,'bank_prefix_commands':0,'game_commands_traced':len(trace),'checked_stops':len(states),'entry_zero_verified':True,'victory':states[15]['x'],'restart':states[16]['x']}
(HERE/'page-check.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
