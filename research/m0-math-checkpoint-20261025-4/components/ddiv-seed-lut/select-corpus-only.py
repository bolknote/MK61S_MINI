"""Predict caller-only savings from measured bare costs; not public qualification."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-soft-20261025'
proof=json.loads((W/'unit-proof.json').read_bytes());unit={}
with gzip.open(W/'unit-records.jsonl.gz','rt')as stream:
 for line in stream:
  row=json.loads(line);d=row['D'];costs=row['instructions']
  if d in unit:assert unit[d]==costs
  unit[d]=costs
assert len(unit)==65536
variants=list(proof['parent_delta_histograms']);losses={n:set()for n in variants};old=set();savings={n:Counter()for n in variants};changed=0
with gzip.open(P/'qualification-records.jsonl.gz','rt')as stream:
 for line in stream:
  r=json.loads(line);pair=r['x'],r['y'];parent=r['candidate_instructions'];seeds=r['software_seed_divisors']
  changed+=bool(seeds)
  for name in variants:
   delta=sum(unit[d][name]-unit[d]['control']for d in seeds);assert delta<=0
   cost=parent+delta;savings[name][delta]+=1
   for ref in r['references'].values():
    if not ref['correct_Qfplib']:continue
    if parent>ref['instructions']:old.add(pair)
    if cost>ref['instructions']:losses[name].add(pair)
assert len(old)==11386 and changed==377
summary={}
for name in variants:
 assert not losses[name]-old
 summary[name]=dict(predicted_loss_pairs=len(losses[name]),predicted_new_fixes=len(old-losses[name]),
  measured_allocated_seed_bytes=proof['code_and_allocated_sizes'][name]['allocated_bytes'],
  measured_seed_cost_min=min(map(int,proof['cost_histograms'][name])),measured_seed_cost_max=max(map(int,proof['cost_histograms'][name])),
  predicted_public_saving_min=-max(d for d in savings[name]if d<0),predicted_public_saving_max=-min(savings[name]),
  mean_measured_unit_instructions=sum(int(k)*v for k,v in proof['cost_histograms'][name].items())/proof['tests'])
# Prefer the strongest same-corpus speed result, then the smallest allocated
# body+table among candidates giving that result. These are only predictions.
selected=min(variants,key=lambda n:(summary[n]['predicted_loss_pairs'],summary[n]['measured_allocated_seed_bytes']))
out=dict(status='MEASURED_SEED_COSTS_PREDICTED_PUBLIC_EFFECT_NOT_PUBLIC_QUALIFICATION',selected=selected,results=summary,
 selected_bare_qualified_ARM_calls=2*proof['tests'],other_variant_experimental_ARM_calls=(len(variants)-1)*proof['tests'],
 unit_total_actual_ARM_calls=proof['actual_ARM_calls'],all_selected_seed_costs_no_greater_than_parent=True,
 parent_FROZEN_sha256=hashlib.sha256((P/'FROZEN.json').read_bytes()).hexdigest(),
 unit_proof_sha256=hashlib.sha256((W/'unit-proof.json').read_bytes()).hexdigest(),hardware_accessed=False)
(W/'selection.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
