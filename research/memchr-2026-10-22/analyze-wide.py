#!/usr/bin/env python3
"""Re-decode exact raw M4 reports before summarizing physical cycle results."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT/'tests'))
import wide
from session import Hold


def analyze(plan_path,result_path,partial=False):
    plan=json.loads(plan_path.read_text());result=json.loads(result_path.read_text())
    digest=hashlib.sha256(plan_path.read_bytes()).hexdigest()
    if result['plan_sha256']!=digest:raise Hold('Result does not belong to this plan')
    complete=result['status']=='PASS'
    if not complete and not partial:raise Hold('A final comparison requires strict hardware PASS')
    if complete and (result['firmware_restore_pending'] or result['cleanup_pending'] or not result['serial_closed'] or not result['full_original_flash_verified']):raise Hold('Incomplete restoration receipt')
    wide.verify_images(plan);summaries=[];reports=0;checks=0;total_rows=0
    for i,row in enumerate(plan['apps']):
        bounded=wide.proof(plan,row);cases=wide.cases(SimpleNamespace(**row['corpus']))
        chunks=[cases[j:j+7] for j in range(0,len(cases),7)];rows=[]
        for index,inputs in enumerate(chunks):
            path=result_path.parent/('app-'+str(i))/f'{index:03d}.bin'
            if not path.exists():
                if complete:raise Hold('Missing complete raw report: '+str(path))
                break
            decoded=wide.decode(path.read_bytes(),inputs,bounded,index==0 and row['corpus']['full_hardware_correctness_sweep'])
            rows+=decoded['rows'];checks+=decoded['checks'];reports+=1
        total_rows+=len(rows);categories=[]
        for source in (0,1):
            for label,lo,hi in (('0..16',0,16),('17..255',17,255),('256..4096',256,4096)):
                group=[r for r in rows if r['source']==source and lo<=r['size']<=hi]
                if not group:continue
                stats={}
                for name in wide.NAMES:
                    positive=[r['timings'][name]['median_cycles'] for r in group if r['timings'][name]['median_cycles']>0]
                    ratios=[r['timings']['baseline']['median_cycles']/r['timings'][name]['median_cycles'] for r in group
                            if r['timings']['baseline']['median_cycles']>0 and r['timings'][name]['median_cycles']>0]
                    wins=sum(r['timings'][name]['median_cycles']<=min(t['median_cycles'] for t in r['timings'].values())*1.02 for r in group)
                    stats[name]=dict(median_cycles_across_cases=statistics.median(positive) if positive else None,
                        unweighted_geomean_speedup_vs_baseline=math.exp(statistics.mean(map(math.log,ratios))) if ratios else None,
                        within_two_percent_of_best_cases=wins,
                        negative_raw_paired_samples=sum(v<0 for r in group for v in r['timings'][name]['paired_cycles']))
                categories.append(dict(source='Flash' if source else 'SRAM',sizes=label,cases=len(group),functions=stats))
        examples=[]
        for r in rows:
            if r['size'] in (0,1,4,16,64,128,512,4096) and r['offset'] in (0,1,4) and r['mode']==0 and r['value']==0:
                examples.append({**{k:r[k] for k in ('size','offset','source','mode','prefix_bytes')},
                    'cycles':{n:t['median_cycles'] for n,t in r['timings'].items()}})
        summaries.append(dict(directory=row['directory'],shared=row['shared'],placement=row['placement'],rows=len(rows),categories=categories,examples=examples))
    if complete and total_rows!=sum(len(wide.cases(SimpleNamespace(**r['corpus']))) for r in plan['apps']):raise Hold('Incomplete timing corpus')
    return dict(status='PASS' if complete else 'PARTIAL_NOT_A_SELECTION',scope='Physical M4 raw reports re-decoded against exact code/pointers',
        plan_sha256=digest,raw_reports=reports,timing_rows=total_rows,correctness_calls=checks,
        comparison_note='Unweighted case summaries are not an application workload. Keep short/long, data placement and call paths separate.',apps=summaries)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);p.add_argument('--result',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--partial',action='store_true');a=p.parse_args()
    summary=analyze(a.plan,a.result,a.partial);a.output.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ('status','raw_reports','timing_rows','correctness_calls')}))
