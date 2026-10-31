#!/usr/bin/env python3
"""Synthetic guards only; no fake physical admission or real-state preservation."""
import argparse
import copy
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path

from quiet_guards import assess, SCOPE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    policy = json.loads(Path(__file__).with_name('policy.UNBOUND.json').read_text())
    # FIXTURE values cannot be mistaken for a source-proven repaired base.
    policy['accepted_base'] = dict(build='FIXTURE', source_sha256='a'*64, elf_sha256='b'*64)
    state = dict(base=policy['accepted_base'], uid=policy['uid'], boot_id='fixture-boot-1', ip=0, steps=105,
                 register_values=['0']*15, stack_values=['0']*5, last_x='0', program_hex='00'*105,
                 run=0, busy=0, dirty=0, physical_keys=0, service='CLOSED', runtime='NONE', ui='CALCULATOR',
                 terminal='COMMAND', usb_disk=0, usb_screen='OFF', m61_active=0, m61_suspended=0, cwd='/',
                 rtc_set=0, rtc_ppm=0, settings_sequence=331, settings_fingerprint='FAKE stable settings',
                 alarms=['OFF ONCE','OFF ONCE'], retained_fault=False, health_ok=True,
                 clock=dict(rtc='2026-01-01 00:00:00', wall_before=0., wall_after=.1, host_boot_id='fixture-host'))
    fixture = dict(scope=SCOPE, pre=state, post=copy.deepcopy(state), fresh_power_and_no_user_input=True,
                   source_domain_proof_matches_base=True, fresh_exclusive_scope_handoff=True,
                   operations=[dict(kind='read_command',command='date')],
                   sd=dict(complete_current_bytes=True, independent_actual_review=True,
                           postcold_lineage_covered=True, every_original_byte_reverified=True))
    fixture['post']['clock'] = dict(rtc='2026-01-01 00:01:40', wall_before=100., wall_after=100.1, host_boot_id='fixture-host')
    (args.output/'FIXTURE-policy.json').write_text(json.dumps(policy,indent=2)+'\n')
    (args.output/'FIXTURE-data.json').write_text(json.dumps(fixture,indent=2)+'\n')
    good = assess(fixture, policy)
    assert good['model_matches'] and not good['hardware_GO'] and not good['real_provider_bound']
    faults = {
        'wrong_base': lambda d: d['pre']['base'].update(build='other'),
        'wrong_uid': lambda d: d['post'].update(uid='OTHER'),
        'IP_nonzero': lambda d: d['pre'].update(ip=24),
        'nonzero_register': lambda d: d['pre']['register_values'].__setitem__(4,'1'),
        'nonzero_program': lambda d: d['post'].update(program_hex='01'+'00'*104),
        'foreign_owner': lambda d: d['post'].update(runtime='M61'),
        'input_after_boot': lambda d: d.update(fresh_power_and_no_user_input=False),
        'source_proof_missing': lambda d: d.update(source_domain_proof_matches_base=False),
        'old_scope_handoff': lambda d: d.update(scope='P0_CURRENT_ALL_SD_ONLY'),
        'settings_changed': lambda d: d['post'].update(settings_sequence=332),
        'RTC_SET1': lambda d: d['post'].update(rtc_set=1),
        'date_setter': lambda d: d['operations'].append(dict(kind='read_command',command='date 2026-10-23 00:00:00')),
        'foreign_write': lambda d: d['operations'].append(dict(kind='owned_upload',path='/USER.bin')),
        'unreviewed_APP': lambda d: d['operations'].append(dict(kind='owned_app',path='/INTRP01/other.APP',sha256='0'*64)),
        'ALL_incomplete': lambda d: d['sd'].update(complete_current_bytes=False),
        'ALL_not_verified': lambda d: d['sd'].update(every_original_byte_reverified=False),
        'postcold_lineage_missing': lambda d: d['sd'].update(postcold_lineage_covered=False),
        'boot_changed': lambda d: d['post'].update(boot_id='different'),
        'RTC_jump': lambda d: d['post']['clock'].update(rtc='2026-01-01 01:00:00'),
        'host_reboot': lambda d: d['post']['clock'].update(host_boot_id='new-host'),
    }
    rows=[]
    for name, change in faults.items():
        data=copy.deepcopy(fixture); change(data); result=assess(data,copy.deepcopy(policy))
        assert not result['model_matches'] and not result['hardware_GO'], (name,result)
        rows.append(dict(case=name,status=result['status'],failures=result['failures']))
    # A deliberately calibrated clock may drift tens of seconds over hours;
    # compare its source-derived divider trajectory, not a fixed3s allowance.
    calibrated=copy.deepcopy(fixture); seconds=100000; ppm=500; hz=policy['reference_rtc_hz']
    divider=(hz*(1000000-ppm)+500000)//1000000
    calibrated['pre']['rtc_ppm']=calibrated['post']['rtc_ppm']=ppm
    calibrated['post']['clock'].update(wall_before=seconds,wall_after=seconds+.1,
        rtc=(datetime(2026,1,1)+timedelta(seconds=int(seconds*hz/divider))).isoformat(' '))
    assert assess(calibrated,policy)['model_matches']
    unbound=json.loads(Path(__file__).with_name('policy.UNBOUND.json').read_text())
    assert not assess(fixture,unbound)['model_matches']
    files=('quiet_guards.py','test_quiet_guards.py','policy.UNBOUND.json')
    report=dict(status='PASS_SYNTHETIC_GUARD_MODEL_ONLY',negative_cases=rows,positive_cases=2,
                unbound_base_rejected=True, hardware_GO=False, device_opened=False, real_provider_bound=False,
                source_sha256={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in files})
    report['fixture_sha256']={n:hashlib.sha256((args.output/n).read_bytes()).hexdigest() for n in ('FIXTURE-policy.json','FIXTURE-data.json')}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],negative_cases=len(rows),positive_cases=2,hardware_GO=False),indent=2))


if __name__=='__main__':main()
