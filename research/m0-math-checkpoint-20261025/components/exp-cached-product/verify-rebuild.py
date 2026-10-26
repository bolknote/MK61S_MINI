"""Rebuild CPP, RAM assembly, public overlay and bare units into new outputs."""
from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
R=W/'rebuild';R.mkdir(exist_ok=False)
commands=[];matched=[];outputs={}
for record in ('build.json','unit-build.json'):
 for old in json.loads((W/record).read_text())['commands']:
  command=[outputs.get(v,v) for v in old]
  index=command.index('-o')+1
  prior=old[old.index('-o')+1]
  path=R/Path(prior).name
  command[index]=str(path)
  subprocess.run(command,cwd=W,check=True);commands.append(command)
  assert Path(prior).read_bytes()==path.read_bytes(),Path(prior).name
  matched.append(dict(name=Path(prior).name,sha256=sha(path),bytes=path.stat().st_size))
  outputs[prior]=str(path)
out=dict(status='PASS_COMPLETE_CPP_ASM_PUBLIC_AND_UNIT_ELF_REBUILDS_BYTE_EXACT',
 matched=matched,commands=commands,hardware_accessed=False,canonical_or_Git_changes=False)
(W/'rebuild-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))
