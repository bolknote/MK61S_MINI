#!/usr/bin/env python3
"""Per-function hardware decisions with complete coverage and regression maps.

Consumes only exported raw reports and independently correlated requests.
The seven intervals stay intact. No HOST clock or subtracted loop overhead
enters a performance number. Workload assumptions are reported explicitly.
"""
import argparse,collections,json,math,statistics,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(HERE),str(ROOT/'tests')]
from prepare import FUNCTIONS,PROFILES,pin,save,ROWS
import wire
from check_stm32_vectors import ElfImage
LABELS=('C-control','byte1','byte2','byte4','word1','word2','public-SDK','current-native','real-runtime')
def need(v,why):
    if not v:raise ValueError(why)
def weighted(rows,cases,logical,target,kind):
    groups=collections.defaultdict(list)
    for case in logical:groups[case['length']].append(case)
    terms=[];floors=[];spreads=[];normal=0.
    lengths=sorted(groups)
    if kind=='ternary':
        selected={0,1,3,9,27,81,243,729};lengths=[n for n in lengths if n in selected]
    for length in lengths:
        group=groups[length];mass=1. if kind=='equal-length' else 1./(length+1)
        for logical_case in group:
            r=rows[logical_case['physical_index']];raw=r['raw'][target];n=r['repeats'];w=mass/len(group)
            if kind=='inverse-work':w=1./(logical_case['work']+1)/len(logical)
            values=sorted(raw);terms.append(w*values[3]/n);floors.append(w/n);spreads.append(w*(values[5]-values[1])/n);normal+=w
    need(normal>0,'empty workload')
    return dict(us_per_checked_iteration=sum(terms)/normal,quantization_bound_us=sum(floors)/normal,seven_group_spread_us=sum(spreads)/normal,logical_rows=len(logical))
def regression_map(cases,rows,target,baseline):
    groups=collections.defaultdict(list)
    for index,row in rows.items():
        c=cases[index];ratio=statistics.median(row['raw'][target])/statistics.median(row['raw'][baseline])
        groups[(c['length'],c['banks'],tuple(c['alignment']),c['mode'],c['count'],len(bytes.fromhex(c['seed_hex'])))].append((index,ratio))
    return [dict(length=key[0],banks=key[1],alignment=list(key[2]),mode=key[3],count=key[4],seed_length=key[5],cases=[v[0] for v in values],baseline=LABELS[baseline],median_ratio_to_baseline=statistics.median(v[1] for v in values),worst_ratio_to_baseline=max(v[1] for v in values)) for key,values in groups.items()]
def summarize_route(t,route,rows):
    functions={}
    for function in FUNCTIONS:
        logical=[r for r in t['logical_map'] if r['function']==function];subset={i:r for i,r in rows.items() if r['function']==function}
        need(len(subset)==sum(c['function']==function for c in t['cases']),'per-function coverage gap')
        weights={kind:{LABELS[f]:weighted(subset,t['cases'],logical,f,kind) for f in range(9 if function in t['runtime_slots'] else 8)} for kind in ('inverse-length','equal-length','inverse-work','ternary')}
        regressions={};SDK_regressions={}
        for f in range(6):
            native=regression_map(t['cases'],subset,f,7)
            regressions[LABELS[f]]=[dict(v,median_ratio_to_current_native=v['median_ratio_to_baseline'],worst_ratio_to_current_native=v['worst_ratio_to_baseline']) for v in native]
            SDK_regressions[LABELS[f]]=regression_map(t['cases'],subset,f,6)
        functions[function]=dict(weighted=weights,regressions=regressions,SDK_regressions=SDK_regressions)
    return dict(route=route,functions=functions,physical_rows=len(rows))
def decision(routes,function,place,baseline):
    indexes=[0,2] if place=='SRAM' else [1,3]
    # Shared APPs delegate these functions to native Flash/RAM. They are
    # not a second standalone SDK baseline for the local implementation.
    if baseline=='public-SDK' and function in ('strlen','strncmp','memcmp','strncat'):indexes=[0]
    candidates=[]
    for f in range(6):
        ratios=[];absolute=[];floor=[];spread=[];sensitivity={k:[] for k in ('equal-length','inverse-work','ternary')}
        for route in indexes:
            v=routes[route]['functions'][function]['weighted'];b=v['inverse-length'][baseline];x=v['inverse-length'][LABELS[f]]
            ratios.append(x['us_per_checked_iteration']/b['us_per_checked_iteration']);absolute.append(x['us_per_checked_iteration'])
            floor.append(2*x['quantization_bound_us']/b['us_per_checked_iteration']);spread.append((x['seven_group_spread_us']+b['seven_group_spread_us'])/b['us_per_checked_iteration'])
            for kind in sensitivity:sensitivity[kind].append(v[kind][LABELS[f]]['us_per_checked_iteration']/v[kind][baseline]['us_per_checked_iteration'])
        candidates.append(dict(target=LABELS[f],profile=PROFILES[f],placement=place,geomean_ratio_to_baseline=math.prod(ratios)**(1/len(indexes)),route_ratios=ratios,route_indexes=indexes,mean_checked_us=statistics.mean(absolute),maximum_quantization_ratio=max(floor),maximum_seven_group_spread_ratio=max(spread),sensitivity_ratios={k:math.prod(v)**(1/len(indexes)) for k,v in sensitivity.items()}))
    return sorted(candidates,key=lambda v:v['geomean_ratio_to_baseline'])
def main():
    p=argparse.ArgumentParser();p.add_argument('--template',type=Path,required=True);p.add_argument('--apps',type=Path,required=True);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=json.loads(a.template.read_text());apps=json.loads(a.apps.read_text());campaign=json.loads(a.campaign.read_text())
    need(campaign['status']=='PASS_ALL_EIGHT_MATRIX_AWAITING_INDEPENDENT_ROOT_CLOSED' and campaign['first_fault'] is None and len(campaign['phase_receipts'])==45,'No complete successful physical matrix')
    a.output.mkdir(parents=True,exist_ok=False);byroute=[{} for _ in range(4)];contexts={};rawpins=[];seen=set();total=0
    for phase in campaign['phase_receipts']:
        receipt=json.loads(Path(phase['receipt']['path']).read_text());proc=json.loads(Path(phase['process']['path']).read_text())
        need(pin(phase['receipt']['path'])==phase['receipt'] and pin(phase['process']['path'])==phase['process'],'Receipt/process changed')
        need(receipt['status']=='PASS' and proc['status']=='PASS_PROCESS_EXIT' and proc['EXIT']==0 and proc['reaped'] and proc['group_gone'],'Open/failed phase process')
        folder=Path(phase['receipt']['path']).parent
        if phase['scope']=='qualification':contexts=json.loads((folder/'QUALIFICATION.json').read_text())['routes']
        if phase['scope']!='timing':continue
        for job in receipt['completed_jobs']:
            need(job not in seen,'Replayed job');seen.add(job);route=job//168;app=apps['products'][route]
            stem='job-'+str(job).zfill(3);raw=folder/(stem+'.bin');input=folder/(stem+'-input.bin');decoded=folder/(stem+'.decoded')
            parsed=wire.parse_report(raw.read_bytes(),input.read_bytes(),t,app,decoded.read_bytes())
            need(parsed['status']=='PASS_RAW_ALL_GROUPS','faulty raw group')
            need(parsed['header'][24:30]==contexts[app['route']]['context'],'Qualification/context mix')
            for row in parsed['rows']:
                need(row['index'] not in byroute[route],'Duplicated case');byroute[route][row['index']]=row
                total+=(9 if row['function'] in t['runtime_slots'] else 8)*7
            rawpins.extend([pin(raw),pin(input)]);print('verified hardware job',job,flush=True)
    need(seen==set(range(672)) and all(set(v)==set(range(len(t['cases']))) for v in byroute),'Missing jobs/cases')
    need(total==8651776,'Missing raw intervals')
    route_results=[]
    for i,rows in enumerate(byroute):
        result=summarize_route(t,apps['products'][i]['route'],rows);save(a.output/(result['route']+'.json'),result);route_results.append(result)
    equal_context=len({tuple(v['context']) for v in contexts.values()})==1;decisions={}
    for function in FUNCTIONS:
        native=decision(route_results,function,'SRAM','current-native')+decision(route_results,function,'Flash','current-native');native.sort(key=lambda v:v['geomean_ratio_to_baseline'])
        sdk=decision(route_results,function,'SRAM','public-SDK');best=native[0];best_sdk=sdk[0]
        def verdict(v):
            noise=v['maximum_quantization_ratio']+v['maximum_seven_group_spread_ratio']
            return 'GAIN_UNDER_FROZEN_WORKLOAD' if equal_context and 1-v['geomean_ratio_to_baseline']>noise else 'KEEP_CURRENT_NO_RESOLVED_GAIN'
        decisions[function]=dict(native_verdict=verdict(best),native=best,native_ranking=native,SDK_verdict=verdict(best_sdk),SDK=best_sdk,SDK_ranking=sdk,shared_runtime='delegates to selected native' if function in t['runtime_slots'] else 'local SDK; no runtime slot',full_regression_maps_in_route_files=True)
    result=dict(status='HARDWARE_MEASUREMENTS_ANALYZED_AWAITING_INTEGRATION_AND_ROOT_CLOSED',physical_timing=True,raw_intervals=total,physical_rows=4*len(t['cases']),same_qualified_context_for_cross_placement_decision=equal_context,contexts=contexts,decisions=decisions,
        primary_workload=t['workload'],uncertainty_rule='gain must exceed two quantization bounds plus the observed middle-five seven-group spread; no statistical confidence claim',
        limitations='Checked indirect-call loop time, not isolated instruction latency; workload frequency is an assumption; no universal winner is claimed. All raw groups and regression maps retained.',
        campaign=pin(a.campaign),template=pin(a.template),apps=pin(a.apps),raw_and_request_pins=rawpins,analysis_source=pin(Path(__file__)))
    save(a.output/'RESULT.json',result)
    for name,v in decisions.items():print(name,v['native_verdict'],v['native']['target'],v['native']['placement'],round(100*(1-v['native']['geomean_ratio_to_baseline']),2),'percent; SDK',v['SDK_verdict'],v['SDK']['target'])
if __name__=='__main__':main()
