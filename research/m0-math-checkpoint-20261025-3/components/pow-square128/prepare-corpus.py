"""Preserve the complete previous116468-pair reference union for a fresh replay."""
from pathlib import Path
import gzip,hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-pow-exp-table-product-20261025'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
jobs={}
def add(row,cost,output,references):
 key=(row['x'],row['y'],row['SIO']);fixed=dict(x=row['x'],y=row['y'],SIO=row['SIO'],expected=row['expected'],parent_cost=cost,parent_output=output)
 job=jobs.setdefault(key,fixed|dict(references={}))
 assert all(job[k]==v for k,v in fixed.items()),key
 for name,value in references.items():
  if name in job['references']:assert job['references'][name]==value,(key,name)
  job['references'][name]=value
with gzip.open(P/'old-records.jsonl.gz','rt') as stream:
 for line in stream:
  r=json.loads(line);refs={n:{k:v[k] for k in ['output','instructions','correct_Qfplib']} for n,v in r['references'].items()}
  add(r,r['candidate_instructions'],r['candidate'],refs)
for r in json.loads((P/'new-qualification.json').read_text())['rows']:
 refs={n:dict(output=r['outputs'][n],instructions=r['instructions'][n],correct_Qfplib=r['correct'][n]) for n in ['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']}
 add(r,r['instructions']['candidate'],r['outputs']['candidate'],refs)
assert len(jobs)==232936 and len({k[:2] for k in jobs})==116468
assert sum(len(r['references']) for r in jobs.values())==252450
data=b''.join((json.dumps(r,separators=(',',':'))+'\n').encode() for r in jobs.values())
(W/'parent-corpus.jsonl.gz').write_bytes(gzip.compress(data,compresslevel=6,mtime=0))
out=dict(status='COMPLETE_PARENT_UNION_BOUND_NO_REFERENCE_FILTER',unique_pairs=116468,states=232936,reference_state_variants=252450,
         corpus_sha256=sha(W/'parent-corpus.jsonl.gz'),sources={str((P/n).relative_to(ROOT)):sha(P/n) for n in ['FROZEN.json','old-records.jsonl.gz','new-qualification.json']})
(W/'corpus-binding.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
