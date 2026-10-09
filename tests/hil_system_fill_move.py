#!/usr/bin/env python3
"""Qualify global Flash memset/memmove with one unchanged APP on Classic.

Only sealed, matched C9 residents are used. By default a failed check restores
the exact original firmware; --keep-last-image disables that restoration.
Own APP/report files are removed and original
content hashes plus empty calculator state are verified after each image.
"""
import argparse
import base64
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import struct
import subprocess

from hil_system_memory import connect, health, require_empty, flash, PUBLIC, STATE_COMMANDS
from hil_packbits_firmware import firmware_info, fingerprint
from hil_c5_stack import read_file as get_file
from hil_c6_system_bootstrap import read_file, write_file
from hil_rtc_alarm import warm_reset
from hil_usb_disk_transaction import listing_entries
from hil_multi_device_identity import parse_identity

REMOTE='/FILMOV.APP'
LENGTHS=(0,1,2,3,4,5,6,7,8,9,12,15,16,17,31,32,33,63,64,65,128,256,512,2048,8192)
FAMILIES=('memmove','memset')
SCENARIOS=(('shift_left17','shift_left1','self','shift_right1','shift_right17','disjoint_right','disjoint_left'),
           ('zero','value_FF','value_0x1234'))
RESERVED={f'/FILMOV{page:02}.txt' for page in range(len(LENGTHS)*2)}


def save(path,data):
    path.write_text(json.dumps(data,indent=2)+'\n')


def oracle(binary,elf,toolchain):
    image=binary.read_bytes()
    listing=subprocess.check_output([str(toolchain/'arm-none-eabi-nm'),'-P','-S',str(elf)],text=True)
    symbols={parts[0]:parts[1:] for line in listing.splitlines() if len(parts:=line.split())>=4}
    result={}
    for name in ('memmove','memset','memcpy','memcmp'):
        kind,at,size=symbols[name][:3];address=int(at,16)
        assert kind=='T' and 0x08000000<=address<0x08080000,(name,kind,at)
        offset=address-0x08000000
        result[name]={'address':address|1,'bytes':int(size,16),'code_hex':image[offset:offset+32].hex()}
    return result


def parse(data,page,expected):
    fields=struct.unpack_from('<4s15I',data)
    magic,version,actual,count,failures,n,family,pages,demcr,control,sink,*addresses=fields
    assert (magic,version,actual,failures,pages)==(b'FMC1',1,page,0,len(LENGTHS)*2)
    assert (n,family,count)==(LENGTHS[page//2],page%2,len(SCENARIOS[page%2])*4)
    assert len(data)==128+count*20
    assert addresses==[expected[x]['address'] for x in ('memmove','memset','memcpy','memcmp')]+[0]
    for i,name in enumerate(FAMILIES):
        assert data[64+count*20+i*32:96+count*20+i*32].hex()==expected[name]['code_hex'],name
    rows=[]
    for i in range(count):
        f,align,scenario,reserved,iterations,minimum,median,maximum=struct.unpack_from('<4B4I',data,64+i*20)
        assert f==family and align<4 and scenario<len(SCENARIOS[family]) and reserved==0
        assert iterations and 0<minimum<=median<=maximum
        rows.append({'family':FAMILIES[f],'bytes':n,'alignment':align,'scenario':SCENARIOS[f][scenario],
                     'iterations':iterations,'min_cycles':minimum/iterations,
                     'median_cycles':median/iterations,'max_cycles':maximum/iterations})
    assert len({(r['alignment'],r['scenario']) for r in rows})==count
    return {'page':page,'demcr_before':demcr,'dwt_control_before':control,'checksum':sink,'rows':rows}


def measure(args,name,target,expected,original_files,original_state,output):
    output.mkdir();payload=args.app.read_bytes();installed=False;runs=[]
    with ExitStack() as contexts:
        port=contexts.enter_context(connect(args.port,target['build']))
        before=health(port,target['build'])
        for c in STATE_COMMANDS:assert before[c]==original_state[c],c
        assert fingerprint(port)==original_files
        def remove_reports():
            entries=listing_entries(port.command('ls /',timeout=20))
            names={entry.split('\t')[-1].casefold() for entry in entries if entry.startswith('f\t')}
            for remote in sorted(RESERVED):
                if remote[1:].casefold() in names:
                    response=port.command(f'rm "{remote}"',timeout=15)
                    assert 'Removed 1 entry.' in response,response
        try:
            write_file(port,REMOTE,payload);installed=True;read_file(port,REMOTE,payload)
            for run in range(args.runs):
                response=port.command(f'open "{REMOTE}"',timeout=300)
                assert 'Open failed!' not in response,response
                batches=[]
                for page in range(len(LENGTHS)*2):
                    data=base64.b64decode(get_file(port,f'/FILMOV{page:02}.txt'),validate=True)
                    batches.append(parse(data,page,expected))
                    (output/f'report-{run}-{page}.bin').write_bytes(data)
                    if page%2==1:
                        print(name,f'run {run+1}: {LENGTHS[page//2]} bytes PASS',flush=True)
                runs.append(batches);save(output/'runs.json',runs);remove_reports()
        finally:
            fresh,path,elapsed=warm_reset(port,port.path,PUBLIC);fresh.close()
            port=contexts.enter_context(connect(path,target['build']))
            if installed:
                remove_reports();read_file(port,REMOTE,payload)
                response=port.command(f'rm "{REMOTE}"',timeout=15)
                assert 'Removed 1 entry.' in response,response
            after=health(port,target['build'])
            for c in STATE_COMMANDS:assert after[c]==original_state[c],c
            assert fingerprint(port)==original_files
            save(output/'report.json',{'status':'PASS' if len(runs)==args.runs else 'INCOMPLETE',
                 'firmware':target,'oracle':expected,'before':before,'after':after,'runs':runs})
    assert len({(b['demcr_before'],b['dwt_control_before']) for run in runs for b in run})==1
    return runs


def summarize(baseline,candidate):
    medians={}
    for name,runs in (('baseline',baseline),('candidate',candidate)):
        groups={}
        for run in runs:
            for batch in run:
                for r in batch['rows']:
                    key=(r['family'],r['bytes'],r['scenario'],r['alignment'])
                    groups.setdefault(key,[]).append(r['median_cycles'])
        medians[name]={k:statistics.median(v) for k,v in groups.items()}
    rows=[]
    for family in FAMILIES:
        for n in LENGTHS:
            for scenario in SCENARIOS[FAMILIES.index(family)]:
                keys=[(family,n,scenario,a) for a in range(4)]
                b=[medians['baseline'][k] for k in keys];c=[medians['candidate'][k] for k in keys]
                rows.append({'family':family,'bytes':n,'scenario':scenario,'baseline_cycles':b,'candidate_cycles':c,
                             'speedup_range':[min(x/y for x,y in zip(b,c)),max(x/y for x,y in zip(b,c))],
                             'worst_delta_cycles':max(y-x for x,y in zip(b,c))})
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True);p.add_argument('--dfu-util',type=Path,required=True)
    p.add_argument('--toolchain-bin',type=Path,required=True);p.add_argument('--app',type=Path,required=True)
    for name in ('original','baseline','candidate'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('baseline','candidate'):p.add_argument('--'+name+'-elf',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--runs',type=int,default=3)
    p.add_argument('--install-candidate',action='store_true')
    p.add_argument('--keep-last-image',action='store_true',
                   help='leave the last flashed image even after failed qualification (explicit user choice)')
    p.add_argument('--reuse-baseline',type=Path,
                   help='reuse a completed matching baseline directory from an earlier run')
    args=p.parse_args();assert 1<=args.runs<=10
    out=args.output_dir.resolve();out.mkdir(parents=True)
    targets={name:firmware_info(getattr(args,name)) for name in ('original','baseline','candidate')}
    expected={name:oracle(getattr(args,name),getattr(args,name+'_elf'),args.toolchain_bin)
              for name in ('baseline','candidate')}
    with connect(args.port,targets['original']['build']) as port:
        state=health(port,targets['original']['build']);require_empty(state);files=fingerprint(port)
        assert not ({s.casefold() for s in RESERVED|{REMOTE}} & {s.casefold() for s in files['files']})
    shutil.copy2(args.original,out/'original.bin');save(out/'content-before.json',files);save(out/'state-before.json',state)
    result={'status':'RUNNING','firmwares':targets,'oracles':expected,'runs_per_firmware':args.runs,
            'app_sha256':hashlib.sha256(args.app.read_bytes()).hexdigest(),'app_bytes':args.app.stat().st_size}
    save(out/'report.json',result);completed=False;last='original'
    try:
        runs={}
        for name in ('baseline','candidate'):
            if name=='baseline' and args.reuse_baseline:
                previous=json.loads((args.reuse_baseline/'baseline/report.json').read_text())
                assert previous['status']=='PASS' and previous['firmware']['sha256']==targets[name]['sha256']
                assert previous['oracle']==expected[name] and len(previous['runs'])==args.runs
                assert json.loads((args.reuse_baseline/'content-before.json').read_text())==files
                old_state=json.loads((args.reuse_baseline/'state-before.json').read_text())
                for c in STATE_COMMANDS:assert old_state[c]==state[c],c
                runs[name]=previous['runs'];result['reused_baseline']=str(args.reuse_baseline.resolve())
                continue
            flash(args,targets[name],out/(name+'-flash.json'))
            last=name
            runs[name]=measure(args,name,targets[name],expected[name],files,state,out/name)
        result['summary']=summarize(runs['baseline'],runs['candidate'])
        large=[r for r in result['summary'] if r['bytes']>=512 and r['scenario']!='self']
        tiny=[r for r in result['summary'] if r['bytes']<16]
        result['performance_gate']={'large_minimum_speedup':min(r['speedup_range'][0] for r in large),
                                    'tiny_maximum_extra_cycles':max(r['worst_delta_cycles'] for r in tiny),
                                    'limits':{'large_minimum_speedup':1.3,'tiny_maximum_extra_cycles':16}}
        if args.install_candidate:
            assert result['performance_gate']['large_minimum_speedup']>=1.3,result['performance_gate']
            assert result['performance_gate']['tiny_maximum_extra_cycles']<=16,result['performance_gate']
        completed=True
    finally:
        restore=(not completed or not args.install_candidate) and not args.keep_last_image
        if restore:flash(args,targets['original'],out/'restore-flash.json');last='original'
        final=targets[last]
        with connect(args.port,final['build']) as port:
            result['final_identity']=asdict(parse_identity(port.command('identity')))
            result['final_health']=health(port,final['build'])
            assert fingerprint(port)==files
            for c in STATE_COMMANDS:assert result['final_health'][c]==state[c],c
        result['status']='PASS' if completed else 'INCOMPLETE'
        result['candidate_installed']=last=='candidate'
        result['original_file_hashes_preserved']=len(files['files'])
        save(out/'report.json',result)
        print('Final firmware',final['build'],'; original files/state preserved; own APP/reports removed',flush=True)


if __name__=='__main__':main()
