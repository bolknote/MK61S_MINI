from concurrent.futures import ThreadPoolExecutor
import json,subprocess
from pathlib import Path
from monster_probe import seed
HERE=Path(__file__).resolve().parent
RUNNER=HERE/'raw_runner'

def run(c):
 name,exponent,tail=c
 folder=HERE/'monster-transport'/name;folder.mkdir(parents=True,exist_ok=True)
 code=bytes(seed(1,'0203033',exponent)+tail+[0x50])
 (folder/'autoexec.m61').write_text(f'reinit\nhin 0000 {code.hex()}\nrun\n')
 p=subprocess.run([str(RUNNER),str(folder)],input='dump\n',capture_output=True,text=True,timeout=20)
 row={'name':name,'code':code.hex(' '),'exit':p.returncode}
 if p.returncode:row['stderr']=p.stderr[-200:]
 else:row.update(json.loads(p.stdout.splitlines()[0]))
 return row

def main():
 cases=[]
 for e in (400,407,410,411,417,471,499):
  for name,ops in [('store',[0x40]),('copy-y',[0x3e,0x40]),('roll',[0x25,0x40]),('enter',[0x0e,0x40]),('swap',[0x14,0x40]),('frac',[0x35,0x40]),('vp0',[0x0c,0,0x40]),('chs',[0x0b,0x40]),('cx-copy-y',[0x0d,0x3e,0x40])]:
   cases.append((f'e{e}-{name}',e,ops))
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(run,cases))
 (HERE/'monster-transport.json').write_text(json.dumps(rows,indent=2)+'\n')
 print('cases',len(rows),'stopped',sum(r['exit']==0 for r in rows),'error',sum(r.get('error',False) for r in rows))
 for r in rows:
  if r['exit']==0 and (r['name'].startswith('e400-') or r['name'].endswith('-store')):
   print(r['name'],r['reg_words'][0],r['reg_words'][12],r['stack_words'],r['error'])
if __name__=='__main__':main()
