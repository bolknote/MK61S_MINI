#!/usr/bin/env python3
"""Aggregate three actual-Flash runs without conflating SRAM measurements."""
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent

def main():
    report=json.loads((HERE/'flash-hil-3/report.json').read_text())
    assert report['status']=='PASS' and len(report['runs'])==3
    names=[e['name'] for e in report['layout']['entries'][1:]]
    runs=[[r for p in run['pages'] for r in p['rows']] for run in report['runs']]
    rows=[]
    for i,first in enumerate(runs[0]):
        group=[run[i] for run in runs]
        assert len({(r['bytes'],r['alignment'],r['value']) for r in group})==1
        base=median(r['baseline_cycles'] for r in group)
        cycles={name:median(r['cycles'][name] for r in group) for name in names}
        rows.append({'bytes':first['bytes'],'alignment':first['alignment'],
            'baseline_cycles':base,'cycles':cycles,
            'candidate_over_baseline':{name:c/base for name,c in cycles.items()},
            'aa_max_drift':max(abs(r['before_cycles']-r['after_cycles']) for r in group),
            'across_run_spread':{name:max(r['cycles'][name] for r in group)-min(r['cycles'][name] for r in group) for name in names}})
    summary={}
    for name in names:
        large=[r for r in rows if r['bytes']>=16]
        small=[r for r in rows if r['bytes']<16]
        ratios=[r['candidate_over_baseline'][name] for r in large]
        summary[name]={'large_cases':len(large),
            'large_slower_by_over_one_cycle':sum(r['cycles'][name]>r['baseline_cycles']+1 for r in large),
            'small_slower_by_over_one_cycle':sum(r['cycles'][name]>r['baseline_cycles']+1 for r in small),
            'large_cycle_reduction_percent_min':100*(1-max(ratios)),
            'large_cycle_reduction_percent_median':100*(1-median(ratios)),
            'large_cycle_reduction_percent_max':100*(1-min(ratios)),
            'large_faster_than_rom_by_over_one_cycle':sum(r['cycles'][name]+1<r['cycles']['rom'] for r in large),
            'small_max_cycle_change':max(abs(r['cycles'][name]-r['baseline_cycles']) for r in small)}
    result={'priority':'speed','report':'flash-hil-3/report.json',
        'full_flash_restored':report['full_flash_restored'],
        'correctness_checks_per_run':report['runs'][0]['pages'][-1]['correctness_checks'],
        'summary':summary,'max_aa_drift_cycles':max(r['aa_max_drift'] for r in rows),'rows':rows}
    (HERE/'flash-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
    for r in rows:
        if r['bytes'] in (0,1,4,15,16,32,64,256,1024,4096) and r['alignment'] in (0,1):
            print(r['bytes'],r['alignment'],round(r['baseline_cycles'],2),{n:round(v,2) for n,v in r['cycles'].items()})

if __name__=='__main__':main()
