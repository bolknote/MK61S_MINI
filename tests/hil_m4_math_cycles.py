#!/usr/bin/env python3
"""DWT A/B/A of per-operation SRAM APPs; preserve firmware, files and state."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import struct

from build_m4_math_cycles import NAMES,cases
from compact_math_arm_self_test import distance
from hil_c5_stack import read_file,write_file
from hil_multi_device_identity import parse_identity
from hil_packbits_firmware import fingerprint
from hil_portable_apps import ScreenPort
from hil_rtc_alarm import canonical_state_reply
from m0_remaining_oracle import log_reference,atan_reference
from profile_m0_math import reference as sqrt_exp_reference
from profile_m0_trig import oracle as trig_reference

REMOTE=('/M4MATH.APP','/M4MATH.bin')

def expected(op,a):
    if op in ('sin','cos','tan'):return trig_reference(a)[('sin','cos','tan').index(op)]
    if op in ('ln','log10'):return log_reference(a,op=='log10')
    if op=='atan':return atan_reference(a)
    if op in ('exp','sqrt'):return sqrt_exp_reference(op,a)
    raise ValueError(op)

def decode(op,raw):
    inputs=cases(op)
    assert len(raw)==24+32*len(inputs),len(raw)
    assert struct.unpack_from('<6I',raw)==(0x3448544D,1,NAMES.index(op),len(inputs),256,9)
    rows=[]
    for i,(a,b) in enumerate(inputs):
        aa,bb,result,cycles,control=struct.unpack_from('<QQQII',raw,24+32*i)
        assert (a,b)==(aa,bb)
        reference=expected(op,a);error=distance(result,reference)
        assert error<=(2 if op in ('tan','log10') else 1),(op,hex(a),hex(result),hex(reference),error)
        if reference&0x7FFFFFFFFFFFFFFF==0:assert result==reference,(op,a,result,reference)
        assert cycles>control,(op,i,cycles,control)
        rows.append({'a':f'{a:016X}','b':f'{b:016X}','result':f'{result:016X}',
            'reference':f'{reference:016X}','ulp':error,'raw_batch_cycles':cycles,
            'control_batch_cycles':control,'net_cycles_per_call':(cycles-control)/256})
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    p.add_argument('--public-id',required=True)
    p.add_argument('--expected-build',required=True)
    p.add_argument('--baseline-dir',type=Path,required=True)
    p.add_argument('--candidate-dir',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--operations',nargs='+',choices=('sin','cos','tan','atan','ln','log10','exp'),
                   default=['sin','cos','tan','atan','ln','log10','exp'])
    a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
    builds={label:json.loads((path/'build.json').read_text()) for label,path in
            (('BASE',a.baseline_dir),('OWN',a.candidate_dir))}
    apps={label:{op:path/op/'M4MATH.APP' for op in a.operations} for label,path in
          (('BASE',a.baseline_dir),('OWN',a.candidate_dir))}
    for label,operations in apps.items():
        for op,path in operations.items():
            assert hashlib.sha256(path.read_bytes()).hexdigest()==builds[label]['operations'][op]['app_sha256']
            memory=struct.unpack_from('<I',path.read_bytes(),32)[0]
            assert memory<=20480,(label,op,memory)
    report={'status':'RUNNING','method':'SRAM DWT CYCCNT A/B/A; each point is median of nine 256-call batches minus the identity loop. Interrupts enabled; USB/watchdog serviced between batches. Local non-LTO EABI helpers, no resident math imports.',
            'builds':builds,'stages':[]}
    def save():
        (a.output_dir/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    with ScreenPort(a.port) as port:
        identity=parse_identity(port.command('identity',15))
        assert identity.public==a.public_id.upper() and identity.build==a.expected_build.upper(),identity
        report['identity']=identity.__dict__;report['prof_before']=port.command('prof',20)
        original=fingerprint(port)
        logical={c:canonical_state_reply(port.command(c,20)) for c in ('reg','stk','dump','pwd')}
        assert not any(path.casefold() in {p.casefold() for p in REMOTE} for path in original['files'])
        report['files_before']=original;save()
        try:
            for stage,label in (('before','BASE'),('after','OWN'),('before_repeat','BASE')):
                measured={'stage':stage,'implementation':label,'operations':{}}
                report['stages'].append(measured)
                for op in a.operations:
                    write_file(port,REMOTE[0],apps[label][op].read_bytes())
                    launch=port.command('open "'+REMOTE[0]+'"',timeout=120)
                    assert 'Open failed!' not in launch,launch
                    raw=read_file(port,REMOTE[1]);rows=decode(op,raw)
                    (a.output_dir/(stage+'-'+op+'.bin')).write_bytes(raw)
                    measured['operations'][op]={'rows':rows,'launch':launch,
                        'mean_net_cycles':statistics.mean(r['net_cycles_per_call'] for r in rows)}
                    save();print(stage,op,round(measured['operations'][op]['mean_net_cycles'],3),flush=True)
            comparison={}
            for op in a.operations:
                before,after,repeat=[s['operations'][op] for s in report['stages']]
                b,c,r=[x['mean_net_cycles'] for x in (before,after,repeat)]
                drift=abs(b-r)
                assert min(b,r)-c>drift,(op,b,c,r,drift)
                comparison[op]={'before_mean_cycles':b,'after_mean_cycles':c,
                    'before_repeat_mean_cycles':r,'control_drift_cycles':drift,
                    'speedup_vs_mean_controls':(b+r)/2/c,
                    'all_control_drifts_smaller_than_improvement':True}
            report['comparison']=comparison;report['status']='PASS'
        finally:
            port.command('fsput cancel')
            current=fingerprint(port)
            for path in REMOTE:
                actual=next((p for p in current['files'] if p.casefold()==path.casefold()),None)
                if actual:
                    removed=port.command('rm "'+actual+'"',30)
                    assert 'Removed 1 entry.' in removed,removed
            assert fingerprint(port)==original,'Original files changed'
            assert {c:canonical_state_reply(port.command(c,20)) for c in logical}==logical,'Calculator state changed'
            identity=parse_identity(port.command('identity',15))
            assert identity.public==a.public_id.upper() and identity.build==a.expected_build.upper()
            report['health']={c:port.command(c,20) for c in ('df','crash show','mpu status')}
            assert 'FIRMWARE CRC state=valid' in report['health']['df']
            assert 'CRASH none' in report['health']['crash show']
            assert 'enabled=1 layout=ok' in report['health']['mpu status']
            report['preservation']='Firmware identity/CRC unchanged; original files, program, registers, stack and cwd exact'
            (a.output_dir/'terminal.txt').write_bytes(port.text);save()
    print('Classic M4 DWT comparison and preservation PASS',flush=True)

if __name__=='__main__':main()
