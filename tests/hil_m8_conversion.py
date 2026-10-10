#!/usr/bin/env python3
"""Measure M8 conversion kernels in SRAM via an ordinary APP; no flashing."""
import argparse
import base64
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import statistics
import struct
import time
from hil_system_memory import connect,health,require_empty,PUBLIC,STATE_COMMANDS
from hil_packbits_firmware import fingerprint
from hil_c5_stack import read_file as get_file
from hil_c6_system_bootstrap import read_file,write_file
from hil_rtc_alarm import warm_reset
from hil_usb_disk_transaction import listing_entries
from hil_multi_device_identity import parse_identity

REMOTE='/M8CHECK.APP';CONTROL='/M8CFG.txt'
LENGTHS=(0,1,2,3,4,7,8,12,16,31,64,128,512)
FAMILIES=('M8_to_UTF8','UTF8_to_M8','M8_to_UTF16','UTF16_to_M8')
PATTERNS=('ASCII','Russian','alternating_ASCII_Russian','exceptions','program_text')
VARIANTS=('legacy_scalar','mapped_scalar','word_blocks','DSP_blocks')
REPORTS={f'/M8CV{i:02}.txt' for i in range(20)}


def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def parse(data,index,local):
    fields=struct.unpack_from('<4s15I',data)
    magic,version,page,count,failures,n,family,pattern,actual,demcr,control,sink,in_size,out_size,dsp,reserved=fields
    assert (magic,version,page,count,failures,n,family,pattern,actual,dsp,reserved)==\
        (b'M8C1',1,index*20+local,16,0,LENGTHS[index],local%4,local//4,index,1,0)
    assert len(data)==384 and (family==1 or in_size==n) and (family==0 or out_size==n)
    rows=[]
    for i in range(count):
        variant,align,success,reserved,iterations,minimum,median,maximum=struct.unpack_from('<4B4I',data,64+i*20)
        assert variant<4 and align<4 and success==1 and reserved==0 and iterations and 0<minimum<=median<=maximum
        rows.append({'family':FAMILIES[family],'pattern':PATTERNS[pattern],'characters':n,'variant':VARIANTS[variant],
                     'alignment':align,'input_length':in_size,'output_length':out_size,'iterations':iterations,
                     'min_cycles':minimum/iterations,'median_cycles':median/iterations,'max_cycles':maximum/iterations})
    assert len({(r['variant'],r['alignment']) for r in rows})==count
    return {'page':page,'demcr_before':demcr,'dwt_control_before':control,'checksum':sink,'rows':rows}


def summarize(runs):
    groups={}
    for run in runs:
        for batch in run:
            for r in batch['rows']:
                key=(r['family'],r['pattern'],r['characters'],r['alignment'],r['variant'])
                groups.setdefault(key,[]).append(r['median_cycles'])
    medians={k:statistics.median(v) for k,v in groups.items()};result=[]
    for family in FAMILIES:
        for pattern in PATTERNS:
            for n in LENGTHS:
                values=[{v:medians[(family,pattern,n,a,v)] for v in VARIANTS} for a in range(4)]
                result.append({'family':family,'pattern':pattern,'characters':n,'aligned_cycles':values[0],
                    'speedup_vs_legacy':{v:[min(x['legacy_scalar']/x[v] for x in values),max(x['legacy_scalar']/x[v] for x in values)] for v in VARIANTS[1:]},
                    'word_vs_mapped_speedup':[min(x['mapped_scalar']/x['word_blocks'] for x in values),max(x['mapped_scalar']/x['word_blocks'] for x in values)],
                    'DSP_vs_word_speedup':[min(x['word_blocks']/x['DSP_blocks'] for x in values),max(x['word_blocks']/x['DSP_blocks'] for x in values)]})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True);p.add_argument('--app',type=Path)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--runs',type=int,default=3)
    p.add_argument('--inspect',action='store_true')
    args=p.parse_args();assert 1<=args.runs<=10
    out=args.output_dir.resolve();out.mkdir(parents=True)
    with ExitStack() as contexts:
        port=contexts.enter_context(connect(args.port))
        identity=asdict(parse_identity(port.command('identity')));build=identity['build']
        before=health(port,build);require_empty(before);files=fingerprint(port)
        save(out/'content-before.json',files);save(out/'state-before.json',before)
        if args.inspect:
            save(out/'inspect.json',{'identity':identity,'state':before,'files':files});print('Pinned Classic',build,'empty calculator;',len(files['files']),'original files',flush=True);return
        assert args.app is not None
        assert not ({s.casefold() for s in REPORTS|{REMOTE,CONTROL}} & {s.casefold() for s in files['files']})
        app=args.app.read_bytes();runs=[];installed=False;control_owned=False
        fresh,path,elapsed=warm_reset(port,port.path,PUBLIC);fresh.close()
        port=contexts.enter_context(connect(path,build))
        retries=[]
        def read_report(remote):
            # CDC can drop a TX packet under sustained fsget output. Every
            # attempt is independently length/cksum-verified by get_file;
            # never accept or splice an incomplete response.
            for attempt in range(3):
                try:return get_file(port,remote)
                except (AssertionError,TimeoutError):
                    if attempt==2:raise
                    retries.append({'file':remote,'attempt':attempt+1})
                    print('Retry verified CDC read:',remote,flush=True)
                    time.sleep(.1);port.pump(.1)
        def remove_reports():
            entries=listing_entries(port.command('ls /',timeout=20))
            names={line.split('\t')[-1].casefold() for line in entries if line.startswith('f\t')}
            for remote in sorted(REPORTS):
                if remote[1:].casefold() in names:
                    result=port.command(f'rm "{remote}"',timeout=15);assert 'Removed 1 entry.' in result,result
        try:
            write_file(port,CONTROL,b'A');control_owned=True;read_file(port,CONTROL,b'A')
            write_file(port,REMOTE,app);installed=True;read_file(port,REMOTE,app)
            for run in range(args.runs):
                batches=[]
                for index,n in enumerate(LENGTHS):
                    response=port.command(f'open "{REMOTE}"',timeout=120);assert 'Open failed!' not in response,response
                    for local in range(20):
                        data=base64.b64decode(read_report(f'/M8CV{local:02}.txt'),validate=True)
                        batches.append(parse(data,index,local));(out/f'report-{run}-{index}-{local}.bin').write_bytes(data)
                    read_file(port,CONTROL,bytes([ord('A')+(index+1)%len(LENGTHS)]));remove_reports()
                    print(f'Run {run+1}: {n} characters, four conversions/five texts/four variants PASS',flush=True)
                runs.append(batches);save(out/'runs.json',runs)
            assert len({(b['demcr_before'],b['dwt_control_before']) for run in runs for b in run})==1
        finally:
            fresh,path,elapsed=warm_reset(port,port.path,PUBLIC);fresh.close()
            port=contexts.enter_context(connect(path,build))
            remove_reports()
            if installed:
                read_file(port,REMOTE,app);r=port.command(f'rm "{REMOTE}"',timeout=15);assert 'Removed 1 entry.' in r,r
            if control_owned:
                payload=get_file(port,CONTROL);assert len(payload)==1 and b'A'<=payload<=b'M'
                r=port.command(f'rm "{CONTROL}"',timeout=15);assert 'Removed 1 entry.' in r,r
            after=health(port,build)
            for c in STATE_COMMANDS:assert before[c]==after[c],c
            assert fingerprint(port)==files
            save(out/'content-after.json',files)
            save(out/'report.json',{'status':'PASS' if len(runs)==args.runs else 'INCOMPLETE',
                 'identity':identity,'before':before,'after':after,'app_sha256':hashlib.sha256(app).hexdigest(),'app_bytes':len(app),
                 'runs':runs,'summary':summarize(runs) if runs else [],'original_file_hashes_preserved':len(files['files']),
                 'verified_CDC_retries':retries,
                 'scope':'Same-placement SRAM kernels through one ordinary APP. Not a resident Flash or end-to-end storage speed claim. '
                         'Original scalar vs arithmetic Cyrillic priority vs bounded word blocks vs ARM SIMD32 blocks.'})
            print('Firmware unchanged; all original files/state preserved; own APP/control/reports removed',flush=True)


if __name__=='__main__':main()
