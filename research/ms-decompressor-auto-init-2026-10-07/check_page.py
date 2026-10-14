"""Single-page/RF limits and the actual register-state backup in Ms."""
from pathlib import Path
import json,os,re,subprocess,sys
from decimal import Decimal
from psycho_sfx import image,CELL,EXPECTED,TAIL,KERNEL,PLACE
HERE=Path(__file__).resolve().parent;runner=Path(sys.argv[1]).resolve()
source=image();loaded=0;highest=-1
for line in source.splitlines():
 if line.startswith('hin '):
  _,a,h=line.split();a=int(a);n=len(h)//2
  assert a>=0 and a+n<=105
  highest=max(highest,a+n-1);loaded+=n
assert highest==104 and loaded==79 and not any(s.startswith('R') or s.startswith('poke') for s in source.splitlines())
folder=HERE/'saved-page-check';folder.mkdir(exist_ok=True)
(folder/'autoexec.m61').write_text(image(rf_canary=98765.43))
route=[4,11,7,8,15,35,21,22,29,36,43,49,3,17,75]
commands='dump\n'+''.join(f'goto {a:02d}\n' for a in route)+'restart 0\n'+''.join(f'goto {a:02d}\n' for a in CELL.values())
p=subprocess.run([str(runner),str(folder)],input=commands,text=True,capture_output=True,check=True,env=dict(os.environ,ELITE_TRACE='1'))
states=[json.loads(s) for s in p.stdout.splitlines()]
assert len(states)==47 and all(not s['error'] and not s['running'] for s in states)
assert states[0]['regs'][:15]==PLACE+[65,70,1,5,0]
assert states[15]['x']==30 and states[15]['regs'][13:15]==[5,3]
assert states[16]['x']==0 and states[16]['regs'][13:15]==[5,3]
assert all(s['regs'][15]==98765.43 and s['reg_words'][15]==states[0]['reg_words'][15] for s in states)
assert all(s['output_code'][0]==EXPECTED.hex() and s['output_tail'][0]==(bytes(2)+TAIL+KERNEL+bytes(7)).hex() for s in states)
# The addressed run keeps the M61 boundary hook until the stop. To observe
# intermediate exchanges without replacing that hook, start the identical
# image with the former equivalent keyboard launcher in a separate trace run.
trace_folder=HERE/'exchange-trace';trace_folder.mkdir(exist_ok=True)
trace_source=image(rf_canary=98765.43).replace('run 8\n','cmd 51\ncmd 00\ncmd 08\ncmd 50\n')
(trace_folder/'autoexec.m61').write_text(trace_source)
trace_run=subprocess.run([str(runner),str(trace_folder)],input='dump\n',text=True,capture_output=True,check=True,env=dict(os.environ,ELITE_TRACE='1'))
trace_text=trace_run.stderr
(trace_folder/'native-trace.txt').write_text(trace_text)
trace=[]
for line in trace_text.splitlines():
 m=re.match(r'(\d+) op=([0-9a-f]+) ',line)
 if m:trace.append((int(m[1]),int(m[2],16)))
assert trace and max(a for a,b in trace)==104 and all(0<=a<105 for a,b in trace)
assert not [b for a,b in trace if b in {0x1f,0x4f,0x6f,0x7f,0x8f,0x9f,0xaf,0xbf,0xcf,0xdf,0xef}]
before=[float(s) for s in re.search(r'STATE 86 regs=([^\n]+)',trace_text)[1].split(',')]
after=[float(s) for s in re.search(r'STATE 101 regs=([^\n]+)',trace_text)[1].split(',')]
assert before==after==PLACE[:9]
words=re.search(r'MS88 words=([^\n]+)',trace_text)[1].split(',')
def pack(value):
 if not value:return bytes(7).hex()
 digits=str(value).ljust(8,'0')[::-1];t=list(map(int,digits))+[0,len(str(value))-1,0,0]
 return bytes([0]+[t[i]|t[i+1]<<4 for i in range(0,12,2)]).hex()
assert words==[pack(x) for x in PLACE[:9]],words
(folder/'states.json').write_text(json.dumps(states,indent=2)+'\n');(folder/'native-trace.txt').write_text(p.stderr)
report={'complete_native_bytes_including_initialization':loaded,'highest_address_written':highest,'highest_address_executed':max(a for a,b in trace),'extra_banks':0,'rf_preserved_byte_for_byte':True,'native_commands_traced':len(trace),'checked_stops':len(states),'regs_before_first_kod':before,'regs_in_ms_after_first_kpv':PLACE[:9],'regs_after_final_kpv':after,'game_registers_initialized_by_native_code':True,'m61_register_assignments_in_production':0,'victory':states[15]['x'],'restart':states[16]['x']}
(HERE/'page-check.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
