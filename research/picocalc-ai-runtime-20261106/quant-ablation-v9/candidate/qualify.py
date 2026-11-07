from pathlib import Path
import sys,json,hashlib,subprocess,concurrent.futures
from evaluate import worker
B=Path(__file__).resolve().parent
if '--worker'in sys.argv:worker(sys.argv[-1]);raise SystemExit(0)
# Candidate choice was based on disjoint calibration KL, not these functional outcomes.
manifest=dict(status='FROZEN_BEFORE_FUNCTIONAL_AUDIT',profiles=['lut-fp32','int16','a16-head-fp32'],selection='A16 best integer KL; A16+FP32-head predeclared conservative comparison',cases=1175,source_pins={str(p.relative_to(B)):hashlib.sha256(p.read_bytes()).hexdigest()for folder in [B/'source',B/'runtime']for p in folder.rglob('*')if p.is_file()and'__pycache__'not in p.parts},library_sha256=hashlib.sha256((B/'quality-probe.dylib').read_bytes()).hexdigest(),default_changed=False,hardware_io=0)
(B/'qualification-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
def run(mode):
 with(B/(mode+'.log')).open('x')as log:p=subprocess.run([sys.executable,'-B',__file__,'--worker',mode],stdout=log,stderr=subprocess.STDOUT,timeout=1800)
 (B/(mode+'-process.json')).write_text(json.dumps(dict(reaped=True,exit_code=p.returncode))+'\n')
 if p.returncode:raise RuntimeError('functional audit failed '+mode)
 print('DONE',mode,flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:list(pool.map(run,manifest['profiles']))
load=lambda m:{(x['suite'],x['id']):x for x in map(json.loads,(B/('run-'+m)/'results.jsonl').read_text().splitlines())}
base=load('lut-fp32');result={}
for mode in ['int16','a16-head-fp32']:
 rows=load(mode);lost=[list(k)for k in base if base[k]['passed']and not rows[k]['passed']];gained=[list(k)for k in rows if rows[k]['passed']and not base[k]['passed']];fd0=sum(x.get('false_done',False)for x in base.values());fd1=sum(x.get('false_done',False)for x in rows.values())
 result[mode]=dict(lost=lost,gained=gained,baseline_passed=sum(x['passed']for x in base.values()),passed=sum(x['passed']for x in rows.values()),total=len(rows),baseline_false_done=fd0,false_done=fd1,gate_passed=not lost and fd1<=fd0)
previous=B.parents[1]/'int8-quality-v8/run-lut-fp32/results.jsonl';old={(x['suite'],x['id']):x for x in map(json.loads,previous.read_text().splitlines())};assert base.keys()==old.keys();assert all(x['passed']==old[k]['passed']for k,x in base.items())
(B/'paired-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
