from pathlib import Path
import subprocess,sys,concurrent.futures,json,hashlib
B=Path(__file__).resolve().parent
manifest=dict(status='FROZEN_BEFORE_WEIGHT_LOGITS',profiles={100:'same uniformQ4/directFP32 arithmetic control',101:'4bit signed logarithmic7positive levels+zero',102:'4bit signed APoT B=3 magnitude construction (15 effective signed levels)'},source_pins={str(p.relative_to(B)):hashlib.sha256(p.read_bytes()).hexdigest()for p in(B/'weights-source').rglob('*')if p.is_file()},library_sha256=hashlib.sha256((B/'weights-probe.dylib').read_bytes()).hexdigest(),scope='posttraining recode of existingQ4 dequantized weights; no QAT, no activation quantization; quality only, no native shift-kernel performance claim')
(B/'weight-metrics-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
def run(profile):
 with(B/(f'weight-metric-{profile}.log')).open('x')as log:p=subprocess.run([sys.executable,'-B',str(B/'metrics.py'),'--worker',str(profile),'calibration'],stdout=log,stderr=subprocess.STDOUT,timeout=900)
 if p.returncode:raise RuntimeError('weight metric failed '+str(profile))
 print('DONE weight',profile,flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:list(pool.map(run,[100,101,102]))
a=[json.loads((B/'metrics-calibration'/(str(i)+'.json')).read_text())for i in [100,101,102]];(B/'weight-metrics.json').write_text(json.dumps(a,indent=2)+'\n')
