#!/usr/bin/env python3
"""Measure private ZX0 SRAM prototypes through ordinary APPs; no flashing."""
import argparse
import base64
from contextlib import ExitStack
from dataclasses import asdict
import errno
import hashlib
import json
from pathlib import Path
import statistics
import struct
import time
from hil_system_memory import health,require_empty,PUBLIC,SERIAL,PROFILE,STATE_COMMANDS
from hil_packbits_firmware import fingerprint
from hil_c5_stack import read_file as get_file
from hil_c6_system_bootstrap import read_file,write_file
from hil_rtc_alarm import Port,warm_reset
from hil_usb_disk_transaction import listing_entries
from hil_multi_device_identity import parse_identity

CONTROL='/ZX0CFG.txt'
REPORTS={f'/ZX0R{i:02}.txt' for i in range(8)}
FAMILIES=('LZ_copy','match_length','LCP_table','ZX0_decode','ZX0_encode')
VARIANTS=('scalar','word','DSP')

READ_RETRIES=[]
class CorrelatedPort(Port):
    def __init__(self,path):super().__init__(path,require_echo=True)
    def command(self,text,timeout=4):
        readonly=text in ('identity','df','crash show','mpu status','reg','stk','dump','pwd','hout','alarm') or text.startswith(('ls ','fsget '))
        for attempt in range(2 if readonly else 1):
            # Match the old ScreenPort's command spacing without a screen session.
            time.sleep(.02)
            try:return super().command(text,timeout)
            except TimeoutError:
                if not readonly or attempt:raise
                READ_RETRIES.append(dict(command=text,attempt=attempt+1))
                self.write_line('');time.sleep(.3);self.drain()


def connect(path,build=None,wait=30):
    """Pin a correlated text session after USB re-enumeration settles."""
    deadline=time.monotonic()+wait
    while True:
        port=None
        try:
            port=CorrelatedPort(path)
            # A late boot identity can otherwise absorb the first command echo.
            # Finish that line before asking for a fresh, fully canonical reply.
            port.write_line('');time.sleep(.3);port.drain()
            current=parse_identity(port.command('identity',timeout=15))
            assert (current.public,current.usb,current.profile)==(PUBLIC,SERIAL,PROFILE),current
            if build:assert current.build==build,(current.build,build)
            return port
        except (OSError,TimeoutError) as error:
            if port is not None:port.close()
            if isinstance(error,OSError) and error.errno not in (errno.EBUSY,errno.ENOENT):raise
            if time.monotonic()>=deadline:raise
            time.sleep(.3)
        except BaseException:
            if port is not None:port.close()
            raise


def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def parse(data,job,index):
    assert len(data)==384
    fields=struct.unpack_from('<4s15I',data)
    magic,version,actual,count,failures,family,n,parameter,pattern,kind,demcr,control,checksum,total,dsp,reserved=fields
    case=job['cases'][index]
    names=job.get('variants_by_family',{}).get(str(family),VARIANTS[:3 if family in (2,4) else 2])
    variants=len(names)
    received=(magic,version,actual,count,failures,family,n,parameter,pattern,kind,total,dsp,reserved)
    expected=(b'ZX01',1,index,variants*4,0,case['family'],case['size'],case['parameter'],case['pattern'],job['kind'],len(job['cases']),1,int(job.get('resident_crc','0'),16))
    assert received==expected,dict(received=received,expected=expected)
    rows=[]
    for i in range(count):
        variant,align,success,unused,iterations,minimum,median,maximum=struct.unpack_from('<4B4I',data,64+i*20)
        assert variant<variants and align<4 and success==1 and unused==0 and iterations and 0<minimum<=median<=maximum
        rows.append(dict(family=FAMILIES[family],size=n,parameter=parameter,pattern=pattern,
            variant=names[variant],alignment=align,iterations=iterations,
            min_cycles=minimum/iterations,median_cycles=median/iterations,max_cycles=maximum/iterations))
    assert len({(r['variant'],r['alignment']) for r in rows})==count
    return dict(index=index,demcr_before=demcr,dwt_control_before=control,checksum=checksum,rows=rows)


def summarize(runs):
    groups={}
    for run in runs:
        for batch in run:
            for row in batch['rows']:
                key=tuple(row[k] for k in ('family','size','parameter','pattern','alignment','variant'))
                groups.setdefault(key,[]).append(row['median_cycles'])
    medians={k:statistics.median(v) for k,v in groups.items()};result=[]
    cases=sorted({key[:4] for key in medians})
    for family,n,parameter,pattern in cases:
        available={k[5] for k in medians if k[:4]==(family,n,parameter,pattern)}
        names=(['scalar','word']+sorted(available-{'scalar','word'})) if {'scalar','word'}<=available else sorted(available)
        values=[{v:medians[(family,n,parameter,pattern,a,v)] for v in names} for a in range(4)]
        row=dict(family=family,size=n,parameter=parameter,pattern=pattern,aligned_cycles=values[0],
            speedup_vs_scalar={v:[min(x['scalar']/x[v] for x in values),max(x['scalar']/x[v] for x in values)] for v in names[1:]} if 'scalar' in available else {})
        if 'DSP' in available:row['DSP_vs_word_speedup']=[min(x['word']/x['DSP'] for x in values),max(x['word']/x['DSP'] for x in values)]
        if 'register_word' in available:row['register_vs_word_speedup']=[min(x['word']/x['register_word'] for x in values),max(x['word']/x['register_word'] for x in values)]
        result.append(row)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--runs',type=int,default=3)
    p.add_argument('--only',action='append',help='run only these APP names from the manifest')
    args=p.parse_args();assert 1<=args.runs<=10
    manifest=json.loads(args.manifest.read_text());jobs=manifest['jobs']
    selected=set(args.only or (job['name'] for job in jobs))
    assert selected<=set(job['name'] for job in jobs),selected
    jobs=[job for job in jobs if job['name'] in selected]
    apps={f'/{job["name"]}.APP':Path(job['app']).read_bytes() for job in jobs}
    out=args.output_dir.resolve();out.mkdir(parents=True)
    results={};installed=set();control_owned=False;retries=[]
    with ExitStack() as contexts:
        port=contexts.enter_context(connect(args.port));identity=asdict(parse_identity(port.command('identity')));build=identity['build']
        before=health(port,build);require_empty(before);files=fingerprint(port)
        alarms=port.command('alarm')
        assert 'RTC ALARM A off' in alarms and 'RTC ALARM B off' in alarms,alarms
        save(out/'state-before.json',before);save(out/'content-before.json',files)
        reserved=set(apps)|REPORTS|{CONTROL}
        assert not ({s.casefold() for s in reserved}&{s.casefold() for s in files['files']})
        fresh,path,elapsed=warm_reset(port,port.path,PUBLIC);fresh.close();port=contexts.enter_context(connect(path,build))

        def verified_get(remote):
            for attempt in range(3):
                try:return get_file(port,remote)
                except (AssertionError,TimeoutError):
                    if attempt==2:raise
                    retries.append(dict(file=remote,attempt=attempt+1));time.sleep(.1);port.drain()

        def remove_reports():
            entries=listing_entries(port.command('ls /',timeout=20))
            names={line.split('\t')[-1].casefold() for line in entries if line.startswith('f\t')}
            for remote in sorted(REPORTS):
                if remote[1:].casefold() in names:
                    response=port.command(f'rm "{remote}"',timeout=15);assert 'Removed 1 entry.' in response,response

        try:
            write_file(port,CONTROL,b'A');control_owned=True;read_file(port,CONTROL,b'A')
            for remote,app in apps.items():
                write_file(port,remote,app);installed.add(remote);read_file(port,remote,app)
            for job in jobs:
                batches_per_run=[];results[job['name']]=dict(runs=batches_per_run,job=job)
                chunks=(len(job['cases'])+7)//8
                for run in range(args.runs):
                    batches=[]
                    for chunk in range(chunks):
                        response=port.command(f'open "/{job["name"]}.APP"',timeout=180)
                        assert 'Open failed!' not in response,response
                        for local in range(min(8,len(job['cases'])-chunk*8)):
                            index=chunk*8+local
                            data=base64.b64decode(verified_get(f'/ZX0R{local:02}.txt'),validate=True)
                            (out/f'{job["name"]}-{run}-{index}.bin').write_bytes(data)
                            batches.append(parse(data,job,index))
                        read_file(port,CONTROL,bytes([ord('A')+(chunk+1)%chunks]));remove_reports()
                        print(f'{job["name"]} run {run+1}, cases {chunk*8}..{min(len(job["cases"]),chunk*8+8)-1} PASS',flush=True)
                    batches_per_run.append(batches);save(out/'runs.json',results)
        finally:
            fresh,path,elapsed=warm_reset(port,port.path,PUBLIC);fresh.close();port=contexts.enter_context(connect(path,build))
            remove_reports()
            for remote in sorted(installed):
                read_file(port,remote,apps[remote]);response=port.command(f'rm "{remote}"',timeout=15);assert 'Removed 1 entry.' in response,response
            if control_owned:
                control=verified_get(CONTROL);assert len(control)==1 and b'A'<=control<=b'Z'
                response=port.command(f'rm "{CONTROL}"',timeout=15);assert 'Removed 1 entry.' in response,response
            after=health(port,build)
            alarms_after=port.command('alarm')
            assert 'RTC ALARM A off' in alarms_after and 'RTC ALARM B off' in alarms_after,alarms_after
            save(out/'state-after.json',after)
            for command in STATE_COMMANDS:
                assert before[command].rstrip()==after[command].rstrip(),dict(command=command,before=before[command],after=after[command])
            assert fingerprint(port)==files
            for value in results.values():
                if value['runs']:value['summary']=summarize(value['runs'])
            save(out/'content-after.json',files)
            save(out/'report.json',dict(status='PASS' if len(results)==len(jobs) and all(len(v['runs'])==args.runs for v in results.values()) else 'INCOMPLETE',
                identity=identity,before=before,after=after,manifest=manifest,results=results,
                alarms_before=alarms,alarms_after=alarms_after,
                apps={name:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in apps.items()},
                original_file_hashes_preserved=len(files['files']),verified_CDC_retries=retries,read_only_CDC_retries=READ_RETRIES,
                scope=manifest.get('scope','SRAM kernels and complete bounded ZX0 streams, through ordinary APPs. '
                      'No resident Flash or NOR/USB throughput claim; DSP is only the encoder LCP update.')))
            print('Firmware and original files/state preserved; all own APP/control/reports removed',flush=True)


if __name__=='__main__':main()
