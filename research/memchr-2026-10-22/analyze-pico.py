#!/usr/bin/env python3
"""Re-decode physical Pico reports before comparing the frozen memchr cases."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(HERE),str(ROOT/'tests'),str(ROOT/'tools')]
from session import Hold

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m

oracle=load('analysis_pico_oracle',HERE/'pico-wide.py')
native=load('analysis_pico_native',HERE/'pico-native-proof.py')
stage=load('analysis_pico_stage',HERE/'pico-lab-matrix.py')


def compare(rows):
    result={}
    for name in oracle.NAMES:
        positive=[r['timings'][name]['median_cycles'] for r in rows if r['timings'][name]['median_cycles']>0]
        pairs=[(r['timings']['baseline']['median_cycles'],r['timings'][name]['median_cycles']) for r in rows
               if r['timings']['baseline']['median_cycles']>0 and r['timings'][name]['median_cycles']>0]
        wins=0;resolved=0
        for r in rows:
            timings=[x['median_cycles'] for x in r['timings'].values()]
            if min(timings)<=0:continue
            resolved+=1;wins+=r['timings'][name]['median_cycles']<=min(timings)*1.02
        result[name]=dict(median_cycles_across_positive_cases=statistics.median(positive) if positive else None,
            unweighted_geomean_speedup_vs_old_SDK=math.exp(statistics.mean(math.log(a/b) for a,b in pairs)) if pairs else None,
            positive_ratio_case_count=len(pairs),nonpositive_median_case_count=len(rows)-len(positive),
            within_two_percent_best_cases=wins,resolved_best_case_count=resolved,
            negative_raw_paired_samples=sum(v<0 for r in rows for v in r['timings'][name]['paired_cycles']))
    return result


def pairwise(rows,left,right):
    values=[r['timings'][right]['median_cycles']/r['timings'][left]['median_cycles']
            for r in rows if r['timings'][left]['median_cycles']>0 and r['timings'][right]['median_cycles']>0]
    return dict(left=left,right=right,positive_cases=len(values),
        unweighted_geomean_left_speedup=math.exp(statistics.mean(map(math.log,values))) if values else None,
        left_more_than_two_percent_faster=sum(v>1.02 for v in values),
        right_more_than_two_percent_faster=sum(v<1/1.02 for v in values))


def analyze(plan_path,result_path,partial=False):
    plan=json.loads(plan_path.read_text());result=json.loads(result_path.read_text())
    plan_sha=hashlib.sha256(plan_path.read_bytes()).hexdigest()
    if result['plan_sha256']!=plan_sha:raise Hold('Pico result belongs to another plan')
    complete=result['status']=='PASS'
    if not complete and not partial:raise Hold('A final choice requires the completed hardware PASS')
    if complete and (not result.get('restoration_complete') or not result.get('full_original_return_verified') or
                     not result['serial_closed'] or not result['no_cdc_holder_after_close'] or
                     result['return_pending'] or result['rtc_return_pending']):raise Hold('Pico return is incomplete')
    reports=checks=total=0;apps=[]
    for campaign in plan['campaigns']:
        proof=native.verify(campaign['elf'],campaign['prefix'],plan['payload_layout'])
        for index,row in enumerate(campaign['apps']):
            folder=result_path.parent/(campaign['native']+'-app-'+str(index));saved=folder/'result.json'
            if not saved.exists():
                if complete:raise Hold('Missing Pico APP result')
                continue
            try:app_result=json.loads(saved.read_text())
            except json.JSONDecodeError:
                if complete:raise
                continue
            if complete and (app_result['status']!='PASS' or app_result['cleanup_pending']):raise Hold('Pico APP did not finish/clean')
            bounded=oracle.prepare(row,plan['payload_elf'],plan['payload_layout'],proof['static_end'],proof['heap_limit'],proof['provider'])
            cases=stage.corpus_cases(row['corpus']);chunks=[cases[i:i+7] for i in range(0,len(cases),7)]
            ready=len(app_result['groups'])
            if complete and ready!=len(chunks):raise Hold('Pico APP corpus is incomplete')
            rows=[]
            for group,inputs in enumerate(chunks[:ready]):
                raw=(folder/f'{group:03d}.bin').read_bytes()
                decoded=oracle.decode(raw,inputs,bounded,group==0 and row['corpus']['full_hardware_correctness_sweep'])
                rows+=decoded['rows'];checks+=decoded['checks'];reports+=1
            total+=len(rows);categories=[]
            for source in [0,1]:
                for label,lo,hi in [('0..16',0,16),('17..255',17,255),('256..4096',256,4096)]:
                    group=[r for r in rows if r['source']==source and lo<=r['size']<=hi]
                    if not group:continue
                    categories.append(dict(data='Flash' if source else 'SRAM',sizes=label,cases=len(group),functions=compare(group)))
            regimes=[]
            for source in [0,1]:
                for label,select in [
                    ('zero length',lambda r:r['size']==0),
                    ('first byte',lambda r:r['size']>0 and r['prefix_bytes']==1),
                    ('prefix 2..7',lambda r:2<=r['prefix_bytes']<=7),
                    ('prefix 8..63',lambda r:8<=r['prefix_bytes']<=63),
                    ('prefix 64..511',lambda r:64<=r['prefix_bytes']<=511),
                    ('prefix 512..4096',lambda r:r['prefix_bytes']>=512)]:
                    group=[r for r in rows if r['source']==source and select(r)]
                    if not group:continue
                    regimes.append(dict(data='Flash' if source else 'SRAM',label=label,cases=len(group),
                        functions=compare(group),pairwise=[pairwise(group,'fast64',n) for n in ['pair64','balanced64','byte']]))
            examples=[]
            for r in rows:
                if r['size'] not in [0,1,4,16,64,128,256,512,1024,4096] or r['offset'] not in [0,1,7]:continue
                if r['source']==0 and r['mode'] not in [0,1,4]:continue
                examples.append({**{k:r[k] for k in ['size','offset','value','source','mode','prefix_bytes']},
                    'cycles':{n:t['median_cycles'] for n,t in r['timings'].items()}})
            apps.append(dict(native=campaign['native'],directory=row['directory'],shared=row['shared'],instruction_placement=row['placement'],
                rows=len(rows),expected_rows=len(cases),reports=ready,provider=proof['provider'],categories=categories,
                regimes=regimes,examples=examples))
    if complete and (total!=6528 or reports!=936 or checks!=837960):raise Hold('Unexpected complete Pico case/check counts')
    return dict(status='PASS' if complete else 'PARTIAL_NOT_A_SELECTION',scope='Physical M0+ raw reports re-decoded with exact ELF/code/runtime pointers',
        plan_sha256=plan_sha,timing_rows=total,raw_reports=reports,correctness_calls=checks,apps=apps,
        comparison_note='Finite unweighted cases are not an application workload. Keep lengths, data/code placement, match position and call paths separate. Nonpositive and negative raw paired samples are retained; ratios omit only unresolved nonpositive medians.',
        product_RAM_acceptance=False,cold_power_acceptance=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);p.add_argument('--result',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--partial',action='store_true');a=p.parse_args()
    summary=analyze(a.plan,a.result,a.partial);a.output.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ['status','raw_reports','timing_rows','correctness_calls']}))
