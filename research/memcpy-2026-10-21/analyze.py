#!/usr/bin/env python3
"""Collapse hardware rounds/runs without discarding raw paired samples."""
import argparse,json,statistics
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();data=json.loads(a.input.read_text());assert data['status']=='PASS'
groups={}
for group in data['groups']:
 for row in group['rows']:
  key=(row['source'],row['size'],row['src_offset'],row['dst_offset'])
  groups.setdefault(key,[]).append(row)
rows=[]
for key,samples in sorted(groups.items()):
 assert len(samples)==data['runs']
 times={name:statistics.median(r['timings'][name]['median_cycles'] for r in samples) for name in samples[0]['timings']}
 rows.append(dict(zip(('source','size','src_offset','dst_offset'),key),cycles=times))
summary=dict(cpu=data['cpu'],cases=len(rows),runs=data['runs'],correctness_checks=sum(g['checks'] for g in data['groups']),rows=rows)
for baseline in ('baseline','rom','resident','runtime'):
 ratios=[r['cycles']['sdk']/r['cycles'][baseline] for r in rows if r['size']]
 losses=[dict(source=r['source'],size=r['size'],src=r['src_offset'],dst=r['dst_offset'],old=r['cycles'][baseline],new=r['cycles']['sdk']) for r in rows if r['cycles']['sdk']>r['cycles'][baseline]+1]
 summary[baseline]=dict(median_ratio=statistics.median(ratios),worst_ratio=max(ratios),best_ratio=min(ratios),slower_by_over_one_cycle=losses)
a.output.write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='rows' and k not in ('baseline','rom','resident','runtime')},indent=2))
for baseline in ('baseline','rom','resident','runtime'):
 s=summary[baseline];print(baseline,'median/new/old',round(s['median_ratio'],3),'worst',round(s['worst_ratio'],3),'losses>1cy',len(s['slower_by_over_one_cycle']))
for r in rows:
 if r['size'] in (0,1,4,16,64,4096) and r['src_offset']==0 and r['dst_offset'] in (0,1):
  print(r['source'],r['size'],r['src_offset'],r['dst_offset'],{k:round(v,2) for k,v in r['cycles'].items()})
