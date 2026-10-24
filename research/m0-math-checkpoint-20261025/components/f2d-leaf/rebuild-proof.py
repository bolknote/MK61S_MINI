from pathlib import Path
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;R=W/'rebuild';R.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
b=json.loads((W/'build.json').read_text());i=json.loads((W/'isolation.json').read_text())
commands=list(b['commands'])
commands += [c for c in i['commands'] if Path(c[c.index('-o')+1]).name in ('RP-candidate.o','whole-source.elf')]
outputs={c[c.index('-o')+1] for c in commands};records=[]
for c in commands:
 original=Path(c[c.index('-o')+1]);rewritten=[str(R/Path(s).name) if s in outputs else s for s in c]
 subprocess.run(rewritten,cwd=W,check=True)
 assert original.read_bytes()==(R/original.name).read_bytes()
 records.append({'original':str(original.relative_to(W)),'rebuilt':str((R/original.name).relative_to(W)),'sha256':sha(original),'bytes':original.stat().st_size,'command':rewritten})
assert len(records)==4
(W/'rebuild-proof.json').write_text(json.dumps({'status':'PASS_FOUR_COMPLETE_OBJECT_AND_ELF_REBUILDS_BYTE_EXACT','records':records,'hardware_accessed':False},indent=2)+'\n')
print('PASS four complete object/ELF rebuilds byte exact')
