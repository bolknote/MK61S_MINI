"""Strict quiet-NaN reference classification of saved public raw outputs.

The ARM/MPFR run is not repeated and its raw evidence remains unchanged.
"""
import hashlib,json
from pathlib import Path
O=Path(__file__).resolve().parent
def ref(p):p=Path(p);d=p.read_bytes();return dict(path=str(p),bytes=len(d),sha256=hashlib.sha256(d).hexdigest())
def equal(a,b):
 a,b=int(a,16),int(b,16)
 return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
d=json.loads((O/'public-arm-mpfr.json').read_text());changes=[];refs={}
for row in d['rows']:
 corrected={n:equal(v,row['expected'])for n,v in row['outputs'].items()}
 for n in ['parent','control','candidate']:assert corrected[n]
 for n,v in corrected.items():
  if row['correct'][n]!=v:changes.append(dict(x=row['x'],y=row['y'],SIO=row['SIO'],reference=n,output=row['outputs'][n],expected=row['expected'],old=row['correct'][n],correct=v))
 refs[row['x'],row['y'],row['SIO']]=corrected
out=dict(status='PASS_STRICT_QUIET_NAN_SAVED_RAW_PUBLIC_RECLASSIFICATION',raw=ref(O/'public-arm-mpfr.json'),
 executed_harness=ref(O/'arm-executed-policy-001.py'),future_corrected_harness=ref(O/'arm.py'),
 policy='If expected is NaN, got must be a quiet NaN. sNaN output is wrong, rather than accepted by any-NaN equivalence.',
 candidate_parent_control_wrong=0,derived_reference_flag_corrections=changes,
 ARM_calls=0,MPFR_evaluations=0,original_raw_outputs_costs_and_counts_unchanged=True,
 full_public_qualified_calls=d['qualified_calls'],inputs=d['unique_pairs'],MPFR_inputs=d['directed_MPFR_inputs'],sNaN_shortcuts=d['sNaN_shortcuts'])
with (O/'public-reference-policy.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(dict(result=ref(O/'public-reference-policy.json'),corrected_reference_flags=len(changes)),indent=2))
