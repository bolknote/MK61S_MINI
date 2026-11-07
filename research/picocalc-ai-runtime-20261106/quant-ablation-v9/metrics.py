from pathlib import Path
import sys,json,hashlib,subprocess,concurrent.futures,time,ctypes as C
import numpy as np
from engine import Engine
B=Path(__file__).resolve().parent

def collect(profile,segments):
 e=Engine(profile,reuse=False);l=e.lib;vocab=8224;raw=(C.c_float*vocab)();view=np.ctypeslib.as_array(raw);best=C.c_ushort();out=[]
 for s in segments:
  l.mk_ai_reset();l.codec_distribution(int(s['support']is None));positions=set(s['score_positions']);values=[]
  support=np.array(s['support'],dtype=np.int64)if s['support']is not None else np.arange(vocab)
  for at,token in enumerate(s['ids'][:-1]):
   score=at in positions;status=l.codec_forward(token,int(score),C.byref(best),raw if score else None)
   if status:raise RuntimeError((profile,s['id'],at,status))
   if score:values.append(view[support].copy())
  a=np.stack(values);assert np.isfinite(a).all()and(a>-1e30).all(),s['id'];out.append(a)
 return out

def logsoftmax(x):
 a=x.astype(np.float64);m=a.max(axis=1,keepdims=True);return a-(m+np.log(np.exp(a-m).sum(axis=1,keepdims=True)))

def summarize(base,value,segments):
 result={}
 for kind in dict.fromkeys(x['kind']for x in segments):
  pairs=[(a,b,s)for a,b,s in zip(base,value,segments)if s['kind']==kind];A=np.concatenate([x[0]for x in pairs]);D=np.concatenate([x[1]for x in pairs]);lp=logsoftmax(A);lq=logsoftmax(D);p=np.exp(lp);kl=(p*(lp-lq)).sum(axis=1);top=A.argmax(axis=1);other=D.argmax(axis=1)
  targets=[]
  for a,b,s in pairs:
   support=s['support']if s['support']is not None else list(range(8224));index={x:i for i,x in enumerate(support)}
   targets.extend(index[s['ids'][pos+1]]for pos in s['score_positions'])
  targets=np.array(targets);row=np.arange(len(targets));nll0=-lp[row,targets];nll1=-lq[row,targets];margin=np.partition(A,-2,axis=1)[:,-1]-np.partition(A,-2,axis=1)[:,-2];changed=top!=other
  result[kind]=dict(positions=len(targets),kl_mean=float(kl.mean()),kl_max=float(kl.max()),kl_p95=float(np.quantile(kl,.95)),top1_matches=int((~changed).sum()),top1_agreement=float((~changed).mean()),baseline_nll=float(nll0.mean()),nll=float(nll1.mean()),nll_delta=float((nll1-nll0).mean()),baseline_perplexity=float(np.exp(nll0.mean())),perplexity=float(np.exp(nll1.mean())),perplexity_ratio=float(np.exp((nll1-nll0).mean())),mean_abs_logit_delta=float(np.abs(A-D).mean()),max_abs_logit_delta=float(np.abs(A-D).max()),changed_baseline_margin_min=float(margin[changed].min())if changed.any()else None,changed_baseline_margin_max=float(margin[changed].max())if changed.any()else None)
 return result

def worker(profile,split):
 seg=json.loads((B/('metric-'+split+'.json')).read_text());started=time.monotonic();arrays=collect(profile,seg);ref=B/('reference-'+split+'.npz')
 if profile==0:np.savez(ref,**{'a'+str(i):a for i,a in enumerate(arrays)})
 data=np.load(ref);base=[data['a'+str(i)]for i in range(len(seg))];result=dict(profile=profile,split=split,seconds=time.monotonic()-started,metrics=summarize(base,arrays,seg))
 if profile==24:
  # Numeric equivalence is also directly visible in raw logits, not only task success.
  reference=B/('int8-'+split+'.npz');q=np.load(reference);result['int8_logits_bit_equal']=all(np.array_equal(a,q['a'+str(i)])for i,a in enumerate(arrays))
 if profile==1:np.savez(B/('int8-'+split+'.npz'),**{'a'+str(i):a for i,a in enumerate(arrays)})
 out=B/('metrics-'+split);out.mkdir(exist_ok=True);(out/(str(profile)+'.json')).write_text(json.dumps(result,indent=2)+'\n')
 print(profile,split,json.dumps(result['metrics']['commands40']),flush=True)

def main():
 split=sys.argv[1]if len(sys.argv)>1 else'calibration';m=json.loads((B/'metric-manifest.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 assert all(sha(B/p)==h for p,h in m['source_pins'].items());assert sha(B/'quality-probe.dylib')==m['library_sha256'];assert all(sha(B/n)==h for n,h in m['input_pins'].items())
 profiles=list(map(int,json.loads((B/'profiles.json').read_text())))if split=='calibration'else json.loads((B/'selected-for-audit.json').read_text())
 def launch(profile):
  with(B/(f'metric-{split}-{profile}.log')).open('x')as log:
   p=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--worker',str(profile),split],stdout=log,stderr=subprocess.STDOUT,timeout=900)
  if p.returncode:raise RuntimeError(f'metric worker{profile} failed')
  return profile
 launch(0)
 if 1 in profiles:launch(1)
 with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:
  for profile in pool.map(launch,[x for x in profiles if x not in [0,1]]):print('DONE',profile,flush=True)
 result=[json.loads((B/('metrics-'+split)/(str(p)+'.json')).read_text())for p in profiles]
 (B/('metrics-'+split+'.json')).write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':
 if '--worker'in sys.argv:worker(int(sys.argv[-2]),sys.argv[-1])
 else:main()
