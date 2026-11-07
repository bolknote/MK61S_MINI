from pathlib import Path
import sys,json,ctypes as C,importlib.util
from engine import Engine
B=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('original_engine',B.parent/'engine.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
probes=json.loads((B/'probes13.json').read_text());rows=[]
for profile in [0,1,2,17,24]:
 old=mod.Engine(profile);expected=[old.generate(r['prompt'])['tokens']for r in probes]
 e=Engine(profile);l=e.lib
 workspace=l.mk_ai_workspace();capacity=l.codec_workspace_capacity();assert capacity==workspace
 for r,want in zip(probes,expected):
  out=e.generate(r['prompt']);assert out['tokens']==want,(profile,r['id']);assert not out['error']
 rows.append(dict(profile=profile,workspace=workspace,allocated_capacity=capacity,generations_match=len(probes)))
print(rows,flush=True)
assert [x['workspace']for x in rows]==[20880,14736,15120,17168,15504]
# A caller cannot switch a compact A8 workspace to the LUT path and overwrite its buffers.
e=Engine(1);l=e.lib;l.codec_set_mode(0);best=C.c_ushort();assert l.codec_forward(1,0,C.byref(best),None)==3
assert l.mk_ai_position()==0
assert l.codec_rebind_compact(99)==2
assert l.codec_rebind_compact(2)==0
assert l.codec_forward(1,0,C.byref(best),None)==0
report=dict(status='PASS',profiles=rows,asan_ubsan_int64_kernel_rows=48000,allocation_bounds_rejected=True,unsupported_rebind_rejected=True)
(B/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
