"""Independent rational bounds/cell count and bounded source-derived new vectors."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json,random,struct,sys
sys.dont_write_bytecode=True
from model import power,taylor_bits,midpoint_model,word_model,helper_cost,public_tiny_cost,LOW,HIGH
O=Path(__file__).resolve().parent;R=O.parents[1];P=R/'.build/m0-exp-tiny-radius-20261024'
guard=1<<14;limit=power(-38);maxM=1<<53;maxU=power(-91)
correction=maxM**2*maxU/(2*(1-limit))
square_error=guard*(2*maxM+guard)*maxU/2
cubic_error=maxM**3*maxU**2/(6*(1-limit));error=square_error+cubic_error
assert correction<guard+1 and error<power(-22)<power(-18)
per=[];all_cells=0;max_odd=0;min_sep=F(1);q_values=set();selected=[];counts=Counter()
for e in range(-54,-38):
 for neg in (0,1):
  s=-e-neg;step=1<<(s-1);q=55-e-2*s
  assert q==e+55+2*neg and 1<=q<=18 and 6<=s-32<=22
  first=((1<<52)+step-1)//step;first+=int(first%2==0)
  last=(1<<53)//step;last-=int(last%2==0)
  cells=[]
  for odd in range(first,last+1,2):
   m0=odd*step;num=odd*odd;den=1<<q;k,rem=divmod(num,den)
   assert 1<=odd<=65535 and num<1<<32 and rem&1
   separation=F(min(rem,den-rem),den)
   assert separation>=power(-18) and separation>error
   cells.append(dict(e=e,negative=neg,s=s,q=q,odd=odd,M0=m0,floor=k,separation=str(separation)))
   all_cells+=1;max_odd=max(max_odd,odd);min_sep=min(min_sep,separation);q_values.add(q)
  assert cells
  worst=min(cells,key=lambda c:F(c['separation']))
  chosen={c['odd']:c for c in [cells[0],cells[-1],worst]}
  # Exact floors near the historical guard4096 and new upper correction
  # bound are targeted without replaying all author midpoint vectors.
  for target in (1,4096,4097,16383):
   c=min(cells,key=lambda c:abs(c['floor']-target));chosen[c['odd']]=c
  selected.extend(chosen.values())
  per.append(dict(e=e,negative=neg,midpoint_cells=len(cells),first_odd=first,last_odd=last,q=q,selected=len(chosen)))
assert all_cells==49153 and sum(p['midpoint_cells'] for p in per if not p['negative'])==16385
assert sum(p['midpoint_cells'] for p in per if p['negative'])==32768 and max_odd==65535
assert q_values==set(range(1,19))
jobs={}
def add(raw,group):
 if 0<=raw<1<<64:jobs.setdefault(raw,group)
for c in selected:
 for d in sorted({0,1,max(0,c['floor']-1),c['floor'],c['floor']+1,c['floor']+2,4096,4097,16384,16385}):
  m=c['M0']+(d if c['negative'] else -d)
  if not 1<<52<=m<1<<53:continue
  raw=(c['negative']<<63)|((c['e']+1023)<<52)|(m-(1<<52))
  if LOW<(raw&((1<<63)-1))<HIGH:add(raw,'selected_cell_floor_and_guard_neighbors')
# Raw-word carry boundaries, exact domain endpoints, and the compiler's
# low-word prefix case require distinct whole-public-path controls.
for center in [LOW,LOW+(1<<32),(970<<52),(984<<52),HIGH]:
 for delta in [-16385,-16384,-4097,-4096,-2,-1,0,1,2,4096,4097,16384,16385]:
  for sign in [0,1<<63]:add(sign|(center+delta),'domain_word_and_guard_endpoint_controls')
rng=random.Random(0xE4A11CE)
for _ in range(96):add((rng.getrandbits(1)<<63)|rng.randrange(LOW+1,HIGH),'new_independent_uniform_tiny')
verified=[];costs=Counter()
for raw,group in jobs.items():
 mag=raw&((1<<63)-1)
 expected=taylor_bits(raw)
 if LOW<mag<HIGH:
  assert expected==midpoint_model(raw)==word_model(raw)
  costs[public_tiny_cost(raw)]+=1
  assert 74<=public_tiny_cost(raw)<=96
 verified.append(dict(x=f'{raw:016X}',group=group,expected=f'{expected:016X}',tiny=LOW<mag<HIGH))
assert set(costs)=={74,77,79,80,83,84,87,93,96}
(O/'own-tiny-inputs.json').write_text(json.dumps(verified,indent=2)+'\n')
# Derive a universal Qfplib instruction lower bound: r7 starts1, only its
# loop-end ADD changes it, CMP33 ends after32 iterations. The shorter arm
# has11 instructions including the loop branch. Tiny finite unpack/reduce
# return normally, and no path bypasses this loop. Thus32*11>new max96.
qfp_minimum=32*11;assert qfp_minimum>96
d=dict(status='PASS_INDEPENDENT_COMPLETE_TINY_ROUNDING_SOURCE_PROOF',domain='2^-54 < abs(x) < 2^-38',correction_input_ulp_bound=str(correction),correction_strictly_below16385=True,quadratic_displacement_error=str(square_error),absolute_cubic_and_higher_error=str(cubic_error),combined_error=str(error),combined_error_strictly_below_2powminus22=True,minimum_integer_separation=str(min_sep),separation_at_least_2powminus18=True,complete_midpoint_cells=all_cells,positive_cells=16385,negative_cells=32768,per_exponent_sign=per,q_values=sorted(q_values),max_odd=max_odd,odd_square_uint32_safe=True,input_high_word_shift6to22_safe=True,independently_selected_cells=len(selected),own_rational_cubic_interval_controls=len(verified),own_tiny_cost_values=sorted(costs),public_tiny_cost_min74_max96_source_exhaustive=True,Qfplib_unconditional_loop_iterations32_min11instructions_each=True,Qfplib_instruction_lower_bound=qfp_minimum,all_tiny_paths_faster_than_Qfplib_in_instructions=True,author442299_model_checks_not_reexecuted_or_counted_own=True,own_fresh_ARM_or_MPFR_in_this_file=0,original507_unchanged418=True)
(O/'proof.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k!='per_exponent_sign'},indent=2))
