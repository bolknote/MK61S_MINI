from pathlib import Path
import json,hashlib,subprocess,os,concurrent.futures,time
B=Path(__file__).resolve().parent;R=B.parents[2]
M0=R/'.build/mk61ai/v3/models/full-lut/MODEL.MKA';M1=R/'.build/mk61ai/swar-v5/MODEL-NIBBLE.MKA';EXE=B/'evaluator'
m=json.loads((B/'manifest.json').read_text());m['criteria'][3]='retain every baseline-solved task in both suites';(B/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(EXE)==m['evaluation_sha256'] and sha(M0)==m['model_lut_sha256'] and sha(M1)==m['model_int8_sha256']
for f,h in m['source_pins'].items():assert sha(Path(f))==h
for label in ['fresh64','regression20']:assert sha(B/(label+'.jsonl'))==m['fresh_sha256' if label=='fresh64' else 'regression_sha256']
def run(label,mode,oracle=False):
 out=B/(label+'-'+mode+('-oracle' if oracle else ''));out.mkdir()
 model=M0 if mode=='lut-fp32' else M1
 with (out/'results.jsonl').open('x') as f,(out/'progress.log').open('x') as log:
  env=dict(os.environ)
  if oracle:env['MK61_QUALITY_ORACLE']='1'
  p=subprocess.run([str(EXE),str(model),str(B/('oracle64.tsv' if oracle else label+'.tsv')),'--arithmetic='+mode,'--linear=sram'],stdout=f,stderr=log,env=env,timeout=240)
 rows=[json.loads(x) for x in (out/'results.jsonl').read_text().splitlines()]
 tasks=[json.loads(x) for x in (B/(label+'.jsonl')).read_text().splitlines()]
 if p.returncode or [x['id'] for x in rows]!=[x['id'] for x in tasks]:raise RuntimeError('incomplete run '+str(out))
 report=dict(rows=len(rows),passed=sum(x['passed'] for x in rows),passed_examples=sum(x['passed_tests'] for x in rows),total_examples=sum(x['tests'] for x in rows),valid_replies=sum(x['valid_replies'] for x in rows),replies=sum(x['replies'] for x in rows),context_failures=sum('Контекст' in x['feedback'] for x in rows),source_pins_verified=True,exit_code=p.returncode)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(out.name,json.dumps(report),flush=True);return rows
oracle=run('fresh64','lut-fp32',True);assert all(x['passed'] for x in oracle),'fresh fixture oracle failed'
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 futures={(label,mode):pool.submit(run,label,mode) for label in ['regression20','fresh64'] for mode in ['lut-fp32','int8']}
 results={k:v.result() for k,v in futures.items()}
paired={};gate=True
for label in ['regression20','fresh64']:
 a=results[label,'lut-fp32'];b=results[label,'int8'];lost=[];gained=[];changed=[]
 for x,y in zip(a,b):
  if x['passed'] and not y['passed']:lost.append(x['id'])
  if y['passed'] and not x['passed']:gained.append(x['id'])
  if (x['code'],x['reply'])!=(y['code'],y['reply']):changed.append(x['id'])
 lr=sum(x['valid_replies'] for x in a)/max(1,sum(x['replies'] for x in a));ir=sum(x['valid_replies'] for x in b)/max(1,sum(x['replies'] for x in b))
 gate=gate and not lost and sum(x['passed'] for x in b)>=sum(x['passed'] for x in a)>0 and ir>=lr
 paired[label]=dict(total=len(a),lut_passed=sum(x['passed'] for x in a),int8_passed=sum(x['passed'] for x in b),lost=lost,gained=gained,changed_answers=changed,lut_valid_fraction=lr,int8_valid_fraction=ir)
report=dict(status='PASS_NONREGRESSION_GATE' if gate else 'FAIL_NONREGRESSION_GATE',default_switch_allowed=gate,suites=paired,hardware_io=0,training=0,policy=m['criteria'],scope='paired native-model functional outcomes; not a universal statistical equivalence proof',manifest_sha256=sha(B/'manifest.json'))
(B/'paired-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
