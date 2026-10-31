#!/usr/bin/env python3
"""Analyze one completed strlen phase without pooling firmware layouts.

Predeclared comparison: equal weight for every length/alignment/data group;
geometric mean speedup relative to the same phase's native cached strlen.
Also retain short-string scores, every median, negative values and worst
regressions. Physical provenance and complete original return are evaluated
separately from these numerical calculations.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics

spec=importlib.util.spec_from_file_location('strlen_analyze_wire',Path(__file__).with_name('decode.py'))
wire=importlib.util.module_from_spec(spec);spec.loader.exec_module(wire)


def mean_ratio(values):
    return math.exp(statistics.mean(math.log(value) for value in values)) if values else None


def analyze(experiment,body_path):
    exp=json.loads(Path(experiment).read_text())
    anchor=json.loads(wire.pinned(exp['anchors']))
    corpus=json.loads(wire.pinned(exp['corpus']))
    body=json.loads(Path(body_path).read_text())
    wire.require(body['status']=='COMPLETE_APP_BODY_ORIGINAL_RETURN_PENDING','Complete APP body required')
    wire.require(body['cpu']==exp['cpu'] and body['phase']==anchor['phase'],'Body CPU/phase')
    wire.require(body['firmware_build']==f'{anchor["build"]:08X}' and body['firmware_crc32']==f'{anchor["crc32"]:08X}','Body image')
    wire.require(body['apps']==4 and body['batches']==212 and body['groups']==1472 and body['rounds']==7,'Body counts')
    rows={app['name']:[] for app in exp['apps']}
    seen=set()
    for item in body['results']:
        key=(item['app'],item['batch'])
        wire.require(key not in seen,'Duplicate result');seen.add(key)
        app=next(a for a in exp['apps'] if a['name']==item['app'])
        wire.require(0<=item['batch']<len(corpus['batches']),'Batch number')
        batch=corpus['batches'][item['batch']]
        wire.require(item['first']==batch['first'],'Body batch offset')
        raw=Path(item['raw_file']).read_bytes()
        wire.require(hashlib.sha256(raw).hexdigest()==item['raw_sha256'],'Raw result digest')
        parsed=wire.decode(raw,exp,anchor,app,batch,wire.pinned(batch['input']))
        wire.require(parsed['status']=='PASS_WIRE_ONLY','Successful wire report required')
        rows[app['name']]+=parsed['rows']
    wire.require(seen=={(app['name'],i) for app in exp['apps'] for i in range(53)},'Complete exact result matrix')
    modes=[]
    for app in exp['apps']:
        mode_rows=rows[app['name']]
        wire.require(len(mode_rows)==368,'Complete groups per APP')
        reference=app['function_names'].index('native_cached')
        functions=[]
        for f,name in enumerate(app['function_names']):
            comparisons=[];nonpositive=[]
            for row in mode_rows:
                baseline=row['median_per_call'][reference];own=row['median_per_call'][f]
                pair=dict(input=row['input'],native_median=baseline,median=own,
                          speedup=baseline/own if baseline>0 and own>0 else None)
                comparisons.append(pair)
                if pair['speedup'] is None:nonpositive.append(row['input'])
            ratios=[pair['speedup'] for pair in comparisons if pair['speedup'] is not None]
            short=[pair['speedup'] for pair in comparisons if pair['input'][0]<=31 and pair['speedup'] is not None]
            eligible=not nonpositive
            functions.append(dict(name=name,code_bank=app['function_banks'][f],score_complete=eligible,
                geometric_mean_speedup_vs_native=mean_ratio(ratios) if eligible else None,
                short_0_to_31_geometric_mean=mean_ratio(short) if all(pair['speedup'] is not None for pair in comparisons if pair['input'][0]<=31) else None,
                wins=sum(value>1 for value in ratios),ties=sum(value==1 for value in ratios),
                regressions=sum(value<1 for value in ratios),nonpositive_groups=nonpositive,
                worst_speedup=min(ratios) if ratios else None,best_speedup=max(ratios) if ratios else None,
                cases=comparisons))
        leaves=functions[:len(anchor['leaves'])]
        winners={}
        for bank in ['sram','flash']:
            candidates=[row for row in leaves if row['code_bank']==bank and row['score_complete']]
            winners[bank]=max(candidates,key=lambda row:row['geometric_mean_speedup_vs_native'])['name'] if candidates else None
        modes.append(dict(app=app['name'],functions=functions,highest_predeclared_score=winners))
    return dict(status='NUMERICAL_ANALYSIS_PHYSICAL_AND_RETURN_EVIDENCE_REQUIRED',cpu=exp['cpu'],
        firmware_phase=anchor['phase'],firmware_build=f'{anchor["build"]:08X}',firmware_crc32=f'{anchor["crc32"]:08X}',
        timer='microseconds' if exp['cpu']=='m0' else 'cycles',layouts_pooled=False,
        score='equal-case geometric mean relative to native cached within the same phase',
        negative_values_retained=True,nonpositive_scores_not_silently_dropped=True,
        physical_provenance_proved=False,original_return_proved=False,modes=modes,raw_rows=rows)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment',type=Path,required=True)
    p.add_argument('--body',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=analyze(a.experiment,a.body)
    wire.require(not a.output.exists(),'New analysis output required')
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    for mode in result['modes']:
        print(mode['app'],mode['highest_predeclared_score'])
