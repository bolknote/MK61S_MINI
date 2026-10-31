#!/usr/bin/env python3
"""Draft scope orchestration with reviewed Wire/decoder and explicit doubles."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from scoped import ScopedCompareCarrier

ROOT=Path('/Users/bolk/Projects/MK61S_MINI')
PACKET=ROOT/'.build/rp2040-interpolator-20261023/combined-v3-v1'
PACKET_SHA='1a71e2fc0b5f86512945aba7b4b078071c961a551a6658f2da536aea0b427afc'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--guard-fixtures',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    report=json.loads((args.guard_fixtures/'report.json').read_text())
    for n,digest in report['fixture_sha256'].items():assert sha(args.guard_fixtures/n)==digest
    policy=json.loads((args.guard_fixtures/'FIXTURE-policy.json').read_text())
    fixture=json.loads((args.guard_fixtures/'FIXTURE-data.json').read_text())
    assert sha(PACKET/'combined-manifest.json')==PACKET_SHA
    manifest=json.loads((PACKET/'combined-manifest.json').read_text())
    entry=PACKET/'source/bind.py';assert sha(entry)==manifest['files']['source/bind.py']['sha256']
    spec=importlib.util.spec_from_file_location('_quiet_draft_reviewed_join',entry);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    real=module.BoundSet(PACKET,PACKET_SHA)
    class ShortFixtureBinding:
        apps=real.apps
        def admit(self,raw,variant):return real.admit(raw,variant,2,4)
    records=[]
    for fault in ('normal','unknown_admission','foreign_owner','reboot','clock_drift','incomplete_SD','no_return'):
        current_policy=copy.deepcopy(policy);context=copy.deepcopy(fixture)
        context.pop('pre');context.pop('post');context.pop('sd')
        if fault=='unknown_admission':current_policy['accepted_base']=None
        class Port:
            def __init__(self):self.text=bytearray();self.active=False;self.closed=False;self.fd=self.lock_fd=-1
            def open(self,path):
                self.open_text_start=len(self.text);self.active=fault=='no_return'
                self.text+=b'running' if self.active else b'APP_FLOW_RESULT=0\r\nmk61> '
            def wait_text(self,expected,start,timeout):
                if self.active:raise TimeoutError('Unreturned model APP')
                assert expected in self.text[start:]
            def __exit__(self,*args):self.closed=True
        port=Port();wire=real.adapter.Wire(real.accepted,lambda:port)
        class Observer:
            def __init__(self):self.calls=[]
            def capture(self,w,label,record):
                assert w.command_ready and not port.active
                self.calls.append(label);state=copy.deepcopy(fixture['pre' if label=='pre' else 'post'])
                if fault=='foreign_owner' and label=='pre':state['runtime']='FOREIGN'
                if fault=='reboot' and label.startswith('after-'):state['boot_id']='new-boot'
                if fault=='clock_drift' and label=='post':state['clock']['rtc']='2026-01-02 00:00:00'
                record(label+'-FAKE-normalized.json',state);return state
        class Storage:
            def __init__(self):self.calls=[];self.owned=False
            def bind_current_all(self,w,record):
                self.calls.append('bind');sd=copy.deepcopy(fixture['sd']);sd['every_original_byte_reverified']=False
                if fault=='incomplete_SD':sd['complete_current_bytes']=False
                return sd
            def prepare_owned(self,w,record):self.calls.append('prepare');self.owned=True
            def run_owned_v3(self,w,variant,app,record):
                assert w.command_ready and sha(app['path'])==app['sha256'];self.calls.append('run-'+variant)
                w.run_app(app['path'])
                return (real.math/'protocol'/variant/'synthetic-result.bin').read_bytes()
            def cleanup_owned(self,w,record):
                assert w.command_ready and not port.active;self.calls.append('cleanup');self.owned=False
            def verify_all_originals(self,w,sd,record):
                assert w.command_ready and not port.active;self.calls.append('verify_ALL');return dict(every_original_byte_reverified=True)
        observer=Observer();storage=Storage()
        carrier=ScopedCompareCarrier(ShortFixtureBinding(),wire,observer,storage,context,current_policy,args.output/fault)
        result=carrier.execute()
        if fault=='unknown_admission':assert wire.p is None and not port.closed and not observer.calls and not storage.calls
        else:assert port.closed and result['serial_closed']
        assert not result['hardware_GO'] and not result['real_preservation_PASS']
        if fault=='normal':assert result['status']=='DRAFT_COMPARE_COMPLETE_MODEL_ONLY' and len(result['completed'])==4
        else:assert result['status']=='HOLD_DRAFT_COMPARE'
        if fault in ('unknown_admission','foreign_owner','incomplete_SD'):
            assert 'prepare' not in storage.calls and 'cleanup' not in storage.calls and 'verify_ALL' not in storage.calls
            assert observer.calls==([] if fault=='unknown_admission' else ['pre']),'Commands after failed initial admission'
        if fault=='no_return':
            assert storage.owned and result['manual_recovery_required'] and result['pending']
            assert not result.get('owned_cleanup') and not result.get('public_environment_compared')
        if fault=='reboot':assert len([x for x in storage.calls if x.startswith('run-')])==1
        records.append(dict(case=fault,status=result['status'],pending=result['pending'],storage_calls=storage.calls,observer_calls=observer.calls,
                            serial_closed=port.closed,port_never_constructed=wire.p is None))
    files=('quiet_guards.py','scoped.py','test_scoped.py','policy.UNBOUND.json','integration-plan.json')
    result=dict(status='PASS_DRAFT_SCOPED_CARRIER_MODEL_ONLY',cases=records,hardware_GO=False,real_preservation_PASS=False,device_opened=False,
                source_sha256={n:sha(Path(__file__).with_name(n))for n in files},combined_manifest_sha256=PACKET_SHA,
                scope='Actual reviewed RX-only Wire wrapper and actual V3 decoder. Port, normalized observer, authority/ALL-SD source evidence and storage delivery are explicit test doubles. No real scope/provider admission exists.')
    (args.output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],cases=len(records),hardware_GO=False),indent=2))


if __name__=='__main__':main()
