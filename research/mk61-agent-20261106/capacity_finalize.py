"""Post-selection retention/baseline checks and final export, without reselection."""
import json
import argparse
from pathlib import Path
import time

from capacity_round import ROOT,CAP,INITIAL,assess,REL
from run_experiment import run,SCRIPT


def main():
    p=argparse.ArgumentParser();p.add_argument('--wait',action='store_true');args=p.parse_args()
    start=time.monotonic()
    while args.wait and not(ROOT/'complete.json').exists():
        if json.loads((ROOT/'status.json').read_text())['phase']=='failed':raise RuntimeError('Main experiment failed')
        if time.monotonic()-start>3600:raise TimeoutError('Main experiment did not complete')
        time.sleep(10)
    if not(ROOT/'complete.json').exists():raise ValueError('Wait for the controlled comparison to finish')
    selection=json.loads((ROOT/'preselected.json').read_text());level=selection['level']
    baseline=assess(INITIAL['small'],'parent-q4-level1-fresh',1,'q4','fresh')
    if level==2:
        assess(INITIAL['small'],'parent-q4-level2-fresh',2,'q4','fresh')
        for arm,model in selection['models'].items():
            assess(model,arm+'-q4-level1-retention-fresh',1,'q4','fresh')
    formats={};candidates=[]
    for arm in ['small','grown']:
        model=selection['models'][arm]
        formats[arm+'-primary']={'model':model,'format':'q4'}
        chosen=selection['formats'][arm]['best_under_1_8_mib_weights']
        if chosen:
            formats[arm+'-budget']=chosen;candidates.append((chosen['key'],-chosen['packed']['bytes'],arm,chosen))
    _,_,arm,chosen=max(candidates,key=lambda x:(x[0],x[1]))
    formats['selected-budget']={**chosen,'arm':arm}
    for label,entry in formats.items():
        output=CAP+'export/'+label
        if not(ROOT/'export'/label/'manifest.json').exists():
            run('capacity-v1/export-'+label+'.log',SCRIPT+'capacity_export.py','--model',entry['model'],
                '--output',output,'--format',entry['format'])
    for label in ['small-primary','grown-primary','selected-budget']:
        entry=formats[label];output=CAP+'full-formal/'+label+'.json'
        if not(ROOT/'full-formal'/(label+'.json')).exists():
            run('capacity-v1/full-formal-'+label+'.log',SCRIPT+'capacity_formal.py','--model',entry['model'],
                '--tasks',REL+'tasks/test-extended-v2.jsonl','--format',entry['format'],'--output',output)
    result={'selection':'Frozen validation keys; smaller file breaks exact validation ties',
      'fresh_used_for_selection':False,'chosen_under_weight_ceiling':formats['selected-budget'],
      'exports':{k:json.loads((ROOT/'export'/k/'manifest.json').read_text())for k in formats},
      'parent_level1_fresh':baseline['summary'],'primary_level':level}
    (ROOT/'final-export.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
