"""Independent output paths, same exact commands and sources, no runtime tests."""
from pathlib import Path
import hashlib,json,subprocess
W=Path(__file__).resolve().parent;R=W/'rebuild';R.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
b=json.loads((W/'build.json').read_text());i=json.loads((W/'isolation.json').read_text())
sources=[W/'rsqrt.S',W/'candidate.S',W/'candidate/native_eabi_m0.cpp',W/'candidate/native_eabi_m0.S',W/'candidate/native_eabi_m0_pow_rsqrt.inc']
before={str(p):sha(p) for p in sources}
selected=list(b['commands'])
for command in i['commands']:
 out=Path(command[command.index('-o')+1])
 if out.name in ('RP-candidate-cpp.o','RP-candidate-asm.o','whole-fixture-asm.o','whole-source.elf'):selected.append(command)
outputs={command[command.index('-o')+1] for command in selected};records=[]
for command in selected:
 original=Path(command[command.index('-o')+1]);rewritten=[str(R/Path(s).name) if s in outputs else s for s in command]
 subprocess.run(rewritten,cwd=W,check=True)
 rebuilt=R/original.name
 assert original.read_bytes()==rebuilt.read_bytes(),original.name
 records.append({'original':str(original.relative_to(W)),'rebuild':str(rebuilt.relative_to(W)),'bytes':original.stat().st_size,'sha256':sha(original),'command':rewritten})
assert before=={str(p):sha(p) for p in sources}
out={'status':'PASS_ALL_TEN_OBJECT_AND_ELF_REBUILDS_BYTE_EXACT','rebuilds':len(records),'sources_unchanged':before,'records':records,'hardware_accessed':False,'compiler_and_flags_from_frozen_V164':True}
assert len(records)==10
(W/'rebuild-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'status':out['status'],'rebuilds':len(records),'names':[r['original'] for r in records]},indent=2))
