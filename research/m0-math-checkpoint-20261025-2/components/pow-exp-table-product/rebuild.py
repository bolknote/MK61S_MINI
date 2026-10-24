"""Repeat every recorded full-source compile and diagnostic link byte exactly."""
from pathlib import Path
import hashlib,json,subprocess
W=Path(__file__).resolve().parent
assert not (W/'FROZEN.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
commands=json.loads((W/'compile.json').read_text())['commands']+json.loads((W/'link.json').read_text())['commands']
outputs={}
for c in commands:
    p=Path(c[c.index('-o')+1]);assert p.parent==W
    outputs[str(p)]=sha(p)
assert len(outputs)==20
before=dict(outputs)
for c in commands:subprocess.run(c,cwd=W,check=True)
for name,digest in before.items():assert sha(Path(name))==digest,name
out=dict(status='PASS_TWENTY_COMPLETE_OBJECT_AND_ELF_REBUILDS_BYTE_EXACT',
         outputs=before,candidate_ELF_sha256=sha(W/'candidate.elf'),
         source_proof_sha256=sha(W/'source-proof.json'),
         fresh_ARM_or_MPFR_calls=0,hardware_accessed=False)
(W/'rebuild-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(dict(status=out['status'],outputs=len(before),candidate_ELF_sha256=out['candidate_ELF_sha256']),indent=2))
