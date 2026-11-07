from pathlib import Path
import json,time
from engine import Engine
B=Path(__file__).resolve().parent;rows=json.loads((B/'probes13.json').read_text());out=[]
for reuse in [False,True]:
 engine=Engine('lut-fp32',reuse=reuse)
 for row in rows:
  start=time.monotonic();actual=engine.generate(row['prompt']);ok=actual['tokens']==row['tokens']and actual['input_tokens']==row['input_tokens']
  out.append(dict(id=row['id'],prefix_reuse=reuse,matched=ok,seconds=time.monotonic()-start,expected_tokens=row['tokens'],**actual));print(reuse,row['id'],ok,flush=True)
  if not ok:break
(B/'compatibility.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
assert len(out)==26 and all(x['matched']for x in out),'fresh native/B200 compatibility mismatch'
print('Fresh model native/B20013 probes match with and without prefix reuse.',flush=True)
