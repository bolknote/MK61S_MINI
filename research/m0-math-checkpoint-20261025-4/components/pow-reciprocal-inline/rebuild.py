"""Rebuild recorded sources at their original paths, with no numerical rerun."""
from pathlib import Path
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;assert not(W/'FROZEN.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
commands=[c for name in ['build.json','unit-build.json','source-proof.json']for c in json.loads((W/name).read_bytes())['commands']]
outputs={c[c.index('-o')+1]for c in commands};assert len(outputs)==24
before={p:sha(Path(p))for p in outputs}
for i,c in enumerate(commands):
 print('rebuild',i+1,'/',len(commands),Path(c[c.index('-o')+1]).name,flush=True);subprocess.run(c,cwd=W,check=True)
after={p:sha(Path(p))for p in outputs};assert before==after
(W/'rebuild-proof.json').write_text(json.dumps(dict(status='PASS24_SOURCE_OBJECT_ELF_REBUILDS_BYTE_EXACT',outputs=after,commands=commands,actual_ARM_or_MPFR_calls=0,hardware_accessed=False),indent=2)+'\n')
