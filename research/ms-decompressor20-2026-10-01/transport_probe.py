from concurrent.futures import ThreadPoolExecutor
import json,os,subprocess
from pathlib import Path
from block_probe import word
HERE=Path(__file__).resolve().parent
RUNNER=HERE/'raw_runner'

def run(c):
 name,slots,body=c
 folder=HERE/'transport-probes'/name;folder.mkdir(parents=True,exist_ok=True)
 code=bytes.fromhex('1f 56 18 55')+bytes(body)+bytes.fromhex('0d 50')
 (folder/'autoexec.m61').write_text('reinit\nhin 0000 '+code.hex()+'\n'+''.join(f'hin {24*112+r*7:04d} {w.hex()}\n' for r,w in slots.items())+'run\n')
 p=subprocess.run([str(RUNNER),str(folder)],input='dump\n',text=True,capture_output=True,timeout=20)
 out={'name':name,'body':bytes(body).hex(' '),'sources':{r:w.hex() for r,w in slots.items()},'exit':p.returncode}
 if p.returncode:out['stderr']=p.stderr[-300:]
 else:out.update(json.loads(p.stdout.splitlines()[0]))
 return out

def main():
 cases=[]
 for u in (0,3,6,7,8,9,10,11,15):
  for t in (0,1):
   for sign in (0,1):
    slots={4:word('A2030329' if sign==0 else '02030330',sign,u,t)}
    prefix=f'sign{sign}-u{u:X}-t{t}'
    for name,body in [('d4',[0xd4]),('copy',[0x64,0x43]),('vp3',[0x64,0x0c,3,0x43]),('dotvp3',[0x64,0x0a,0x0c,3,0x43]),('chs-vp3',[0x64,0x0b,0x0c,3,0x43]),('frac',[0x64,0x35,0x43]),('sign',[0x64,0x32,0x43]),('max',[0x64,0x0e,0x36,0x43])]:
     cases.append((prefix+'-'+name,slots,body))
 for r,fl in ((0,0x5d),(1,0x5b),(2,0x58),(3,0x5a)):
  for u in (0,7,10):
   for t in (0,1):
    for sign in (0,1):
     src=word('A2030331' if sign==0 else '02030331',sign,u,t)
     cases.append((f'fl{r}-sign{sign}-u{u:X}-t{t}',{r:src},[fl,6]))
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(run,cases))
 (HERE/'transport-probe.json').write_text(json.dumps(rows,indent=2)+'\n')
 print('cases',len(rows),'stopped',sum(r['exit']==0 for r in rows),'error',sum(r.get('error',False) for r in rows))
 for r in rows:
  if r['exit']==0 and ((r['name'].startswith('sign1-u7-t0') and not r['name'].endswith(('sign','max'))) or r['name'].startswith('fl0')):
   print(r['name'],r['reg_words'][:5],r['stack_words'],r['error'])
if __name__=='__main__':main()
