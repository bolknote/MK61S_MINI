"""Validate all raw groups and keep CDB, F0 and AE2 images separate."""
import argparse,collections,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
D=ROOT/'.build/m0-libc-batch-20261107-v1'
sys.path[:0]=[str(HERE),str(ROOT/'tests'),str(ROOT)]
import wire_stream as wire
import analyze as core
from prepare import pin,save,FUNCTIONS,PROFILES
KINDS=('inverse-length','equal-length','inverse-work','ternary')
LABELS=core.LABELS+('local-SDK-control',)

def load(package,campaign_path,start,end,wanted_status):
    t=json.loads((package/'template-001/PLAN.json').read_text());apps=json.loads((package/'apps-001/BUILD.json').read_text());campaign=json.loads(campaign_path.read_text())
    assert campaign['status']==wanted_status and campaign['first_fault'] is None
    assert campaign['lease']['released'] and campaign['lease']['fd_closed'] and campaign['lease']['same_inode']
    outer=campaign_path.parent.parent/'outer-process/PROCESS.json';process(json.loads(outer.read_text()))
    rows=[{} for _ in range(4)];seen=[];q=None;refs=[pin(campaign_path),pin(outer)];intervals=0
    for step in campaign['phase_receipts']:
        assert pin(step['receipt']['path'])==step['receipt'] and pin(step['process']['path'])==step['process']
        receipt=json.loads(Path(step['receipt']['path']).read_text());assert receipt['status']=='PASS' and not receipt.get('port_close_errors') and all(s['closed'] and not s['errors'] for s in receipt['cdc_sessions']);process(json.loads(Path(step['process']['path']).read_text()))
        folder=Path(step['receipt']['path']).parent;refs.extend([step['receipt'],step['process']])
        if step['scope']=='qualification':
            assert q is None;q=json.loads((folder/'QUALIFICATION.json').read_text());assert q['template_sha256']==pin(package/'template-001/PLAN.json')['sha256']
            for info in q['routes'].values():assert pin(info['raw']['path'])==info['raw']
        if step['scope']!='timing':continue
        assert q is not None
        for job in receipt['completed_jobs']:
            assert job==start+len(seen);seen.append(job);route=job//168;app=apps['products'][route];stem='job-%03d'%job
            raw=folder/(stem+'.bin');request=folder/(stem+'-input.bin');decoded=folder/(stem+'.decoded')
            parsed=wire.parse_report(raw.read_bytes(),request.read_bytes(),t,app,decoded.read_bytes())
            assert parsed['header'][24:30]==q['routes'][app['route']]['context'] and parsed['request']['batch']==job%168
            for row in parsed['rows']:
                assert row['index'] not in rows[route];rows[route][row['index']]=row;intervals+=7*sum(any(v) for v in row['raw'])
            refs.extend([pin(raw),pin(request),pin(decoded)])
    assert seen==list(range(start,end))
    return dict(template=t,rows=rows,contexts=q['routes'],jobs=len(seen),intervals=intervals,raw_pins=refs)

def process(p):
    assert p['status']=='PASS_PROCESS_EXIT' and p['EXIT']==0 and p['reaped'] and p['group_gone'] and p['parent_fds_before']==p['parent_fds_after']

def scores(t,rows,name,baseline,place):
    subset={i:r for i,r in rows.items() if r['function']==name};logical=[r for r in t['logical_map'] if r['function']==name and r['physical_index'] in subset]
    assert subset and logical
    data={k:{f:core.weighted(subset,t['cases'],logical,f,k) for f in list(range(6))+[baseline]} for k in KINDS}
    short=[r for r in logical if r['length']<=16];result=[]
    for f in range(6):
        x=data['inverse-length'][f];b=data['inverse-length'][baseline];ratio=x['us_per_checked_iteration']/b['us_per_checked_iteration'];noise=(x['quantization_bound_us']+b['quantization_bound_us']+x['seven_group_spread_us']+b['seven_group_spread_us'])/b['us_per_checked_iteration']
        short_ratio=core.weighted(subset,t['cases'],short,f,'inverse-length')['us_per_checked_iteration']/core.weighted(subset,t['cases'],short,baseline,'inverse-length')['us_per_checked_iteration'] if short else None
        result.append(dict(target=LABELS[f],index=f,profile=PROFILES[f],placement=place,baseline=LABELS[baseline],ratio=ratio,gain_percent=100*(1-ratio),noise_ratio=noise,resolved_gain=1-ratio>noise,checked_us=x['us_per_checked_iteration'],baseline_checked_us=b['us_per_checked_iteration'],weighted_short_ratio=short_ratio,body_bytes=t['leaves'][FUNCTIONS.index(name)][f]['bytes'],quantization_us=x['quantization_bound_us'],spread_us=x['seven_group_spread_us'],sensitivity_ratios={k:data[k][f]['us_per_checked_iteration']/data[k][baseline]['us_per_checked_iteration'] for k in KINDS[1:]},physical_cases=len(subset),logical_cases=len(logical)))
    return sorted(result,key=lambda v:v['ratio'])

def regressions(t,rows,name,target,baseline):
    resolved=[];short=[];worst=0
    for index,row in rows.items():
        if row['function']!=name:continue
        case=t['cases'][index];x=sorted(row['raw'][target]);b=sorted(row['raw'][baseline]);ratio=x[3]/b[3];worst=max(worst,ratio);noise=2+x[5]-x[1]+b[5]-b[1]
        if x[3]-b[3]>noise:
            record=dict(index=index,length=case['length'],banks=case['banks'],alignment=case['alignment'],mode=case['mode'],count=case['count'],seed_length=len(bytes.fromhex(case['seed_hex'])),ratio=ratio,median_target_ticks=x[3],median_baseline_ticks=b[3],quantization_plus_spread_ticks=noise);resolved.append(record)
            if case['length']<=16:short.append(index)
    return dict(resolved_regression_cases=len(resolved),resolved_short_regression_cases=len(short),worst_case_ratio=worst,resolved_regressions=resolved)
