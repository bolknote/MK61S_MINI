"""All saved all-D/all-flags vectors against independently derived integers."""
import gzip,hashlib,json
from collections import Counter
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[1];U=R/'.build/m0-ddiv-seed-bound3-20261025'
domain={r['D']:r for r in json.loads((O/'integer-domain.json').read_text())['rows']};seen=set();deltas=Counter();costs={n:Counter()for n in ['control','candidate']};errors=Counter()
with gzip.open(U/'unit-records.jsonl.gz','rt')as f:
 for line in f:
  r=json.loads(line);D=r['D'];assert D not in seen;seen.add(D);e=domain[D]
  assert[r['initial'],r['exact'],r['error'],r['control_residual'],r['candidate_residual']&0xffffffff]==[e['estimate'],e['quotient'],e['error'],e['old_residue'],e['new_residue']]
  assert r['NZCV']==list(range(16))and all(len(v)==16 for v in r['instructions'].values());errors[e['error']]+=16
  for old,new in zip(r['instructions']['control'],r['instructions']['candidate']):assert old-new==e['saving'];deltas[new-old]+=1;costs['control'][old]+=1;costs['candidate'][new]+=1
assert seen==set(domain)and deltas=={-3:18592,0:1029984}and sum(errors.values())==1048576
j=json.loads((U/'unit-proof.json').read_text());assert costs=={n:Counter({int(k):v for k,v in d.items()})for n,d in j['cost_histograms'].items()}
out=dict(status='PASS_ALL65536_SAVED_VECTORS_ALL1048576_FLAGS_EXACT_INTEGER_AND_COST_BINDING',saved_D_rows=65536,saved_flag_tests=1048576,author_paired_ARM_calls=2097152,
 delta_histogram=dict(deltas),cost_histograms={n:dict(v)for n,v in costs.items()},error_histogram_flags=dict(errors),
 error1_branch_direction_changes_in564032cases_NOT_measured_cycles=True,all5errors_and_everyflag_bound_to_independent_HOSTmodel=True,saved_signed_residual_normalized_modulo_uint32_only=True,
 no_new_ARM_calls=0,no_new_MPFR_inputs=0,records_sha256=hashlib.sha256((U/'unit-records.jsonl.gz').read_bytes()).hexdigest(),devices=0)
p=O/'unit-accounting.json'
with p.open('x')as f:json.dump(out,f,indent=2);f.write('\n')
b=p.read_bytes();print(json.dumps(dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())),flush=True)
