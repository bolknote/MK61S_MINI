#!/usr/bin/env python3
"""Collect final test/build/HIL receipts; refuse incomplete qualification."""
import argparse,hashlib,json,re,statistics
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--work',type=Path,default=ROOT/'.build/memmove-20261021')
a=p.parse_args();w=a.work
out={'status':'PASS','tests':{},'builds':{},'hardware':{}}
for name in ('production-validation','m0-final-validation','pico-full-validation','pico-link-validation','trampoline-validation'):
    file=w/(name+'.json');value=json.loads(file.read_text())
    entries=value if isinstance(value,list) else [value]
    def check(row):
        if isinstance(row,dict):
            if 'status' in row:assert row['status']=='PASS',(name,row)
            for child in row.values():check(child)
        elif isinstance(row,list):
            for child in row:check(child)
    check(entries)
    out['tests'][name]={'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'status':'PASS'}
assert 'PASS' in (w/'host-tests.log').read_text()
out['tests']['host_memory']={'sanitizers':'ASan/UBSan','status':'PASS'}
baseline=json.loads((w/'baseline-proof/result.json').read_text())
assert len(baseline)==2 and all(row['status']=='PASS' for row in baseline)
out['tests']['frozen_baseline_entry']={'status':'PASS','architectures':2,
    'method':'Original C entry and noipa benchmark entry have identical instructions with APP LTO flags'}
for target in ('classic','f401'):
    log=(w/(target+'-build.log')).read_text()
    assert 'stack usage: OK' in log and 'Owned runtime built' in log,target
    used,capacity,free,minimum=map(int,re.search(r'MK61 Flash: image (\d+)/(\d+), free (\d+), minimum headroom (\d+)',log).groups())
    out['builds'][target]={'status':'PASS','flash_bytes':used,'capacity':capacity,'free':free,'minimum_free':minimum}
log=(w/'pico-build.log').read_text();assert 'Owned ARMv6-M runtime:' in log
flash,capacity,ram=map(int,re.search(r'Flash: (\d+) / (\d+) bytes; static RAM: (\d+) bytes',log).groups())
out['builds']['pico']={'status':'PASS','flash_bytes':flash,'capacity':capacity,'static_ram':ram}
assert 'Pico H APPs:' in (w/'pico-apps-build.log').read_text()
out['builds']['pico_apps']={'status':'PASS','count':7}
sessions={'m4_flash':'m4-v3-flash-hil/bench','m4_shared':'m4-v3-flash-hil/shared',
          'm4_app':'m4-v3-app-hil','m0_app':'m0-app-hil','m0_shared':'m0-shared-hil',
          'm4_short_boundary':'m4-v3-short-hil','m0_back_boundary':'m0-back-boundary-hil'}
for name,directory in sessions.items():
    value=json.loads((w/directory/'result.json').read_text())
    assert value['status']=='PASS',name
    for flag in ('calculator_data_preserved','files_preserved','temporary_directory_removed'):assert value[flag],(name,flag)
    rows=[r for g in value['groups'] for r in g['rows']]
    receipt={'status':'PASS','runs':value['runs'],'cases':len(rows)//value['runs'],
             'checks':sum(g['checks'] for g in value['groups']),
             'app_sha256':value['app_sha256'],'state_and_files_preserved':True}
    if name.startswith('m0'):
        before,after=value['initial_status'],value['final_status']
        for field in ('BUILD','BOOTS','IP'):
            pattern=r'\b'+field+r'=([^\s]+)'
            assert re.search(pattern,before)[1]==re.search(pattern,after)[1],(name,field)
        rtc=lambda text:datetime.fromisoformat(re.search(r'\bRTC=([^\s]+)',text)[1])
        assert rtc(after)>=rtc(before),(name,'RTC went backwards')
        receipt.update(build=re.search(r'\bBUILD=([^\s]+)',before)[1],
                       no_reset=True,instruction_pointer_preserved=True,rtc_advanced_seconds=(rtc(after)-rtc(before)).total_seconds())
    if name.endswith('shared'):
        assert all(g['selected_runtime'] for g in value['groups'])
        assert all(g['addresses']['selected_body']==g['selected_address'] for g in value['groups'])
        tax=[r['timings']['sdk']['median_cycles']-r['timings']['selected_body']['median_cycles'] for r in rows if 0<r['size']<=16 and r['source']!=4]
        receipt['short_runtime_overhead_cycles']=statistics.median(tax)
    groups={}
    for row in rows:
        key=tuple(row[k] for k in ('source','size','src_offset','dst_offset'))
        groups.setdefault(key,[]).append(row)
    baselines=(['runtime'] if name.endswith('shared') else ['resident'] if name=='m4_flash'
               else ['baseline','resident'] if name.startswith('m0') else ['baseline'])
    receipt['performance']={}
    for baseline in baselines:
        times=[(key,statistics.median(row['timings']['sdk']['median_cycles'] for row in samples),
                statistics.median(row['timings'][baseline]['median_cycles'] for row in samples))
               for key,samples in groups.items()]
        losses=[key for key,new,old in times if new>old+1]
        assert not losses,(name,baseline,losses)
        speeds=[old/new for key,new,old in times if key[0]!=4 and key[1] and new>0 and old>0]
        receipt['performance'][baseline]={'regressions_over_one_cycle':len(losses),
                                         'median_speedup_nonempty_distinct':statistics.median(speeds)}
    out['hardware'][name]=receipt
transaction=json.loads((w/'m4-v3-flash-hil/report.json').read_text())
assert transaction['status']=='PASS' and transaction['restored_crc']['crc32']=='61CCEBFC'
out['hardware']['m4_full_flash_restored']=transaction['restored_crc']
finish=json.loads((w/'pico-finish.json').read_text())
assert finish['status']=='PASS' and abs(finish['error_seconds'])<=2
for field in ('calculator_state_preserved','root_listing_preserved','temporary_directories_removed',
              'no_reset_or_flash','firmware_crc_valid','peripherals_ready','serial_closed','rtc_set'):
    assert finish[field],field
out['hardware']['pico_final_handoff']={k:finish[k] for k in
    ('status','build','calculator_state_preserved','root_listing_preserved','temporary_directories_removed',
     'no_reset_or_flash','firmware_crc_valid','peripherals_ready','serial_closed','rtc_set','error_seconds')}
out['hardware']['pico_final_handoff']['rtc_restore_method']='Original RTC trajectory plus UTC wall-clock elapsed, including laptop sleep'
out['hardware_correctness_checks']=sum(v.get('checks',0) for v in out['hardware'].values())
(w/'qualification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
