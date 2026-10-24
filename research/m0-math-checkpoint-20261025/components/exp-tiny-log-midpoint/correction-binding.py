"""Reconcile every nonquadratic cell with existing actual ARM acquisitions."""
from pathlib import Path
import gzip,hashlib,json
W=Path(__file__).resolve().parent
cells=json.loads((W/'corrected-midpoint-cells.json').read_text())
assert len(cells)==154
targets={}
for e,n,z,threshold in cells:
 s=-e-n;r=(z-1)//2;M0=z<<(s-1);q=e+55+2*n;old=(z*z)>>q
 assert threshold!=old
 for d in (threshold,threshold+1):
  M=M0+d if n else M0-d
  raw=(n<<63)|((e+1023)<<52)|(M-(1<<52))
  up=d>threshold if n else d<=threshold
  old_up=d>old if n else d<=old
  expected=0x3ff0000000000000+(-1 if n else 1)*(r+up)
  targets[raw]=dict(e=e,negative=bool(n),odd=z,distance=d,expected=f'{expected:016X}',differs_from_quadratic_only=up!=old_up,seen=[])
with gzip.open(W/'qualification-records.jsonl.gz','rt',encoding='utf-8') as f:
 for line in f:
  row=json.loads(line);t=targets.get(int(row['x'],16))
  if t:
   assert row['candidate']==row['expected']==t['expected']
   t['seen'].append(row['SIO'])
for t in targets.values():assert sorted(t['seen'])==['DIRTY','READY']
assert sum(t['differs_from_quadratic_only'] for t in targets.values())==154
out=dict(status='PASS_ALL154_CUBIC_LOG_THRESHOLD_CORRECTIONS_ACTUAL_ARM_MPFR_BOUND',
 distinct_inputs=len(targets),existing_actual_ARM_state_rows=2*len(targets),
 unique_actual_results_requiring_cubic_correction=154,
 newly_executed_ARM_or_MPFR_calls=0,acquisition_is_the_full_qualification=True,
 candidate_ELF_sha256=hashlib.sha256((W/'candidate.elf').read_bytes()).hexdigest(),
 cells={f'{x:016X}':v for x,v in targets.items()},hardware_accessed=False)
(W/'correction-cell-arm-binding.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='cells'},indent=2))
