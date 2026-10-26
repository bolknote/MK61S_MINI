"""Repeat actual whole CPP/ASM and complete private ELF links byte-exact."""
from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;R=W/'rebuild';R.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
outputs={};matched=[];commands=[]
source_commands=json.loads((W/'build.json').read_text())['commands']+json.loads((W/'isolation.json').read_text())['commands'][:4]
for old in source_commands:
 command=[outputs.get(v,v) for v in old]
 index=command.index('-o')+1;prior=old[old.index('-o')+1];path=R/Path(prior).name
 command[index]=str(path)
 subprocess.run(command,cwd=W,check=True);commands.append(command)
 assert Path(prior).read_bytes()==path.read_bytes(),Path(prior).name
 outputs[prior]=str(path);matched.append(dict(name=Path(prior).name,sha256=sha(path),bytes=path.stat().st_size))
out=dict(status='PASS_COMPLETE_CPP_ASM_PARTIAL_AND_WHOLE_SOURCE_ELF_REBUILDS_BYTE_EXACT',matched=matched,commands=commands,hardware_accessed=False)
(W/'rebuild-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))
