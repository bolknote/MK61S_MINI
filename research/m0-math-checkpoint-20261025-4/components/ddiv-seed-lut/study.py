"""Own integer reciprocal approximation; enumerate its complete finite domain."""
from pathlib import Path
from collections import Counter
import json,time
W=Path(__file__).resolve().parent
N=(1<<32)-1
reports=[]
for bins in [32,64,128,256]:
 shift=16-(bins.bit_length()-1);width=1<<shift
 table=[(1<<32)//(65536+i*width+width//2)for i in range(bins)]
 assert all(32768<=u<65536 for u in table)
 for input_round in ['floor','ceil']:
  for inner_round in ['floor','ceil']:
   for outer_round in ['floor','ceil']:
    errors=Counter();max_product=max_nr_product=0;worst=[]
    for d in range(65536,131072):
     u=table[(d-65536)>>shift]
     x=(d+(input_round=='ceil'))>>1
     p=x*u;assert p<(1<<32);max_product=max(max_product,p)
     e=(p+(65535 if inner_round=='ceil'else 0))>>16
     t=u*e;assert t<(1<<32);max_nr_product=max(max_nr_product,t)
     q=2*u-((t+(32767 if outer_round=='ceil'else 0))>>15)
     exact=N//d;errors[q-exact]+=1
     residual=N-q*d;assert -(1<<31)<=residual<(1<<31)
     if len(worst)<8 and abs(q-exact)>2:worst.append(dict(D=d,seed=u,estimate=q,exact=exact))
    reports.append(dict(bins=bins,table_bytes=2*bins,shift=shift,input_round=input_round,inner_round=inner_round,outer_round=outer_round,
     error_histogram=dict(sorted(errors.items())),min_error=min(errors),max_error=max(errors),
     mean_absolute_corrections=sum(abs(k)*v for k,v in errors.items())/65536,max_half_divisor_product=max_product,max_NR_product=max_nr_product,
     all_intermediate_products_fit32=True,all_exact_residuals_fit_signed32=True,examples=worst))
selected=next(r for r in reports if r['bins']==128 and r['input_round']=='ceil'and r['inner_round']=='floor'and r['outer_round']=='floor')
table=[(1<<32)//(65536+i*512+256)for i in range(128)]
(W/'seed-table.inc').write_text('// Own exact integer constants: floor(2^32/(65536+512*i+256)).\n'+''.join(' .hword '+','.join(str(v)for v in table[i:i+8])+'\n'for i in range(0,128,8)))
(W/'study.json').write_text(json.dumps(dict(status='COMPLETE_INTEGER_DOMAIN_APPROXIMATION_AUDIT_NOT_ARM_QUALIFICATION',divisors=65536,configurations=len(reports),reports=reports,selected=selected,table=table,hardware_accessed=False),indent=2)+'\n')
print(json.dumps(dict(selected=selected,best_by_bins={n:min((r for r in reports if r['bins']==n),key=lambda r:r['mean_absolute_corrections'])for n in [32,64,128,256]}),indent=2))
