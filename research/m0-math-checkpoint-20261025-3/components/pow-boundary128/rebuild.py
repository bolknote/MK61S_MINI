from pathlib import Path
import hashlib,json,subprocess
W=Path(__file__).resolve().parent
commands=[c for name,key in [('build.json','commands'),('unit-build.json','commands'),('source-proof.json','inactive_CPP_commands')]
          for c in json.loads((W/name).read_bytes())[key]]
outputs={Path(c[c.index('-o')+1])for c in commands};assert len(outputs)==len(commands)==17
before={str(p):p.read_bytes()for p in outputs}
for c in commands:subprocess.run(c,cwd=W,check=True)
for name,data in before.items():assert Path(name).read_bytes()==data,name
out=dict(status='PASS_SEVENTEEN_FULL_SOURCE_OBJECT_AND_ELF_REBUILDS_BYTE_EXACT',
 outputs={name:hashlib.sha256(data).hexdigest()for name,data in before.items()},commands=commands,
 actual_ARM_or_MPFR_calls=0,hardware_accessed=False)
(W/'rebuild-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='commands'},indent=2))
