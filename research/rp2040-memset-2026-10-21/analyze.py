#!/usr/bin/env python3
"""Summarize per-case medians across the independent physical benchmark runs."""
import argparse
import gzip
import json
from pathlib import Path
import statistics

def summarize(report):
    assert report['status']=='PASS'
    groups=report['groups'];keys={}
    for group in groups:
        for row in group['rows']:
            key=(row['size'],row['offset'],row['value'])
            keys.setdefault(key,[]).append(row)
    cases=[]
    for (n,a,v),rows in sorted(keys.items()):
        assert len(rows)==report['runs'],(n,a,v,len(rows))
        cases.append(dict(size=n,offset=a,value=v,median_ns={
            name:statistics.median(r['timings'][name]['median_ns'] for r in rows)
            for name in rows[0]['timings']}))
    names=cases[0]['median_ns']
    out=dict(status='PASS',runs=report['runs'],cases=len(cases),timed_rows=sum(len(g['rows']) for g in groups),
        checks=sum(g['checks'] for g in groups),names=list(names),case_medians=cases,
        rom_version=groups[0]['rom_version'],rom_address=groups[0]['rom_address'],
        resident_address=groups[0]['resident_address'],app_sha256=report['app_sha256'])
    if 'sdk' in names:
        out['sdk_slower_than_cached_rom_cases']=[c for c in cases if c['median_ns']['sdk']>c['median_ns']['rom_cached']+2]
        out['sdk_slower_than_byte_cases']=[c for c in cases if c['median_ns']['sdk']>c['median_ns']['byte']+2]
        out['sdk_versus_direct_rom_3_to_7_bytes_median_delta_ns']=statistics.median(
            c['median_ns']['sdk']-c['median_ns']['rom'] for c in cases if 3<=c['size']<=7)
        out['at_4096_bytes']=dict(median_ns={name:statistics.median(c['median_ns'][name] for c in cases if c['size']==4096) for name in names})
    out['runtime_reduction_ns']=statistics.median(c['median_ns']['runtime_old']-c['median_ns']['runtime_r3'] for c in cases if c['size']<=256)
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args();raw=a.input.read_bytes()
    if a.input.suffix=='.gz':raw=gzip.decompress(raw)
    summary=summarize(json.loads(raw))
    if a.output:a.output.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='case_medians'},indent=2))
    print('Aligned, zero-filled buffers; nanoseconds after empty-call subtraction:')
    for c in summary['case_medians']:
        if c['offset']==0 and c['value']==0 and c['size'] in (0,1,4,8,16,64,256,1024,4096):
            print(c['size'],{k:round(v,1) for k,v in c['median_ns'].items()})

if __name__=='__main__':main()
