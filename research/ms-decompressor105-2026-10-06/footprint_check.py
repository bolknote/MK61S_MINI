"""Native loading/execution bounds and saved-file victory/restart check."""
from pathlib import Path
import json,subprocess,os,re
p=Path(__file__).resolve().parent;runner=p/'raw_runner';source=(p/'psycho-selfextract.m61').read_text()
loaded={}
for line in source.splitlines():
 if not line.startswith('hin '):continue
 _,addr,data=line.split();addr=int(addr)
 for i,v in enumerate(bytes.fromhex(data)):
  absolute=addr+i;assert absolute%112<105,(absolute,v)
  loaded[absolute]=v
assert max(a%112 for a in loaded)==101
folder=p/'saved-file';folder.mkdir(exist_ok=True);(folder/'autoexec.m61').write_text(source)
route=[4,11,7,8,15,35,21,22,29,36,43,49,3,17,73]
commands='dump\n'+''.join(f'goto {a:02d}\n' for a in route)+'restart 0\n'
r=subprocess.run([str(runner),str(folder)],input=commands,text=True,capture_output=True,check=True)
states=list(map(json.loads,r.stdout.splitlines()))
assert len(states)==17 and not any(s['error'] or s['running'] for s in states)
assert states[-2]['x']==30 and states[-2]['regs'][13:15]==[5,3]
assert states[-1]['x']==0 and states[-1]['regs'][13:15]==[5,3]
assert all(s['output_code'][0]==states[0]['output_code'][0] and s['output_tail'][0]==states[0]['output_tail'][0] for s in states)
(folder/'states.json').write_text(json.dumps(states,indent=2)+'\n')
trace=p/'trace';trace.mkdir(exist_ok=True)
# Stop before normal setup so the driver's native boundary hook observes
# every setup/decoder instruction when execution resumes through C/P.
source=re.sub(r'(?m)^hin 0000 ', 'hin 0000 0d50',source)
(trace/'autoexec.m61').write_text(source)
r=subprocess.run([str(runner),str(trace)],input='dump\nrun\n',text=True,capture_output=True,check=True,env=dict(os.environ,ELITE_TRACE='1'))
(trace/'native-trace.txt').write_text(r.stderr)
addresses=[int(line.split()[0]) for line in r.stderr.splitlines() if ' op=' in line]
assert addresses and max(a%112 for a in addresses)==101
assert not any(a%112>=105 for a in addresses)
report={'loaded_highest_local_address':101,'native_trace_highest_local_address':101,'native_traced_commands':len(addresses),'saved_file_stops':len(states),'victory_x':states[-2]['x'],'restart_x':states[-1]['x'],'all_loaded_and_executed_commands_below_105':True,'requires_112_rf_mode_for_ms':True}
(p/'footprint-check.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
