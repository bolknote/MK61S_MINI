#!/usr/bin/env python3
"""Check saved physical M0 evidence without a toolchain, ports or local builds."""
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
import zlib

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
E=HERE/'evidence/m0-20261107'
def read(name):return json.loads(gzip.decompress((E/name).read_bytes()))
def source_bytes(ref):
    """Verify the source used in this historical measurement campaign.

    Later independent libc work may change the surrounding source file while
    retaining the measured strchr instructions. The old SHA is never updated:
    a byte-exact archived source is required when the current source differs.
    This does not certify the current production build or its hardware time.
    """
    def matches(data):return len(data)==ref['bytes'] and hashlib.sha256(data).hexdigest()==ref['sha256']
    path=ROOT/ref['path']
    if path.is_file():
        data=path.read_bytes()
        if matches(data):return data,False
    archive=E/'source'/(ref['path']+'.gz')
    assert archive.is_file(),ref['path']
    data=gzip.decompress(archive.read_bytes());assert matches(data),ref['path']
    return data,True
def main():
    summary=json.loads((HERE/'M0-RESULTS-2026-11-07.json').read_text())
    for ref in summary['evidence_files']:
        data=(ROOT/ref['path']).read_bytes()
        assert len(data)==ref['bytes'] and hashlib.sha256(data).hexdigest()==ref['sha256'],ref['path']
    archived=[ref['path'] for ref in summary['production_sources'] if source_bytes(ref)[1]]
    meta=read('metadata.json.gz');analysis=read('analysis.json.gz');plan=read('plan.json.gz')
    raw=gzip.decompress((E/'raw-timing.bin.gz').read_bytes());qual=gzip.decompress((E/'qualifications.bin.gz').read_bytes())
    size=meta['report_bytes'];assert size==3024 and len(raw)==464*size and len(qual)==4*size
    token=int(meta['nonce'],16);rows=[]
    def header(data,route):
        h=struct.unpack_from('<96I',data);check=bytearray(data);struct.pack_into('<I',check,248,0)
        assert h[62]==zlib.crc32(check) and h[:2]==(0x34524843,11) and not any(h[2:4])
        assert h[8:10]==(9,7) and h[11:13]==(token&0xffffffff,token>>32)
        assert h[13:15]==(int(route.startswith('shared')),int(route.endswith('flash')))
        assert h[15:18]==(meta['runtime_table'],meta['native_entry'],meta['native_crc'])
        assert h[18]==h[19]==meta['fixture_crc'] and h[91]==meta['native_crc'] and h[92]==meta['runtime_crc']
        assert list(h[32:38])==list(h[38:44])==meta['contexts'][route]
        assert h[24]&3==2 and h[25:28]==(256,4,0x60c)
        assert h[30]==1000000 and 8<=h[28]<=250 and 0<h[29]<0x80000000 and abs(h[29]-1000*h[28])<=2000
        assert h[78]==size and h[79]==0 and not any(h[44:60])
        for f,leaf in enumerate(meta['leaves']):assert h[80+f]==leaf['crc32']
        return h
    for job in range(464):
        route=meta['routes'][job//116];batch=job%116;data=raw[job*size:(job+1)*size]
        assert hashlib.sha256(data).hexdigest()==meta['raw_reports'][job]['raw_sha256']
        h=header(data,route);count=min(10,1152-batch*10)
        assert h[4:8]==(1,batch*10,count,count) and h[10]==batch
        for row in range(10):
            index,repeats,address=struct.unpack_from('<3I',data,384+row*264)
            intervals=struct.unpack_from('<63I',data,396+row*264)
            if row>=count:assert index==repeats==address==0 and not any(intervals);continue
            assert index==batch*10+row
            key=meta['keys'][index//2];case=plan['cases'][index]
            assert repeats==key['repeats'] and address%4==key['alignment']
            assert address==(0x10182000+key['offset'] if index&1 else h[77]+64+key['alignment'])
            assert all(0<v<0x80000000 for v in intervals)
            rows.append(dict(route=route,case=case,us=[statistics.median(intervals[f*7:f*7+7])/repeats for f in range(9)]))
    for i,route in enumerate(meta['routes']):
        h=header(qual[i*size:(i+1)*size],route);assert h[4:8]==(0,0,0,0)
    assert len(rows)==4608 and len(rows)*63==290304
    def score(subset,metric):
        lengths=Counter(r['case']['length'] for r in subset)
        if metric.startswith('geometric-'):
            base=int(metric.split('-')[1]);bucket=lambda n:int(math.floor(math.log(max(1,n+1),base)+1e-12));bins=Counter(bucket(r['case']['length']) for r in subset)
        weights=[]
        for r in subset:
            c=r['case'];n=c['length'];scanned=c['expected_offset']+1 if c['expected_offset']>=0 else n+1
            if metric=='inverse_input_length':w=1/(n+1)/lengths[n]
            elif metric=='inverse_scanned':w=1/max(1,scanned)
            elif metric=='equal_length':w=1/lengths[n]
            else:b=bucket(n);w=base**(-b)/bins[b]
            weights.append(w)
        total=sum(weights)
        return [sum(w*r['us'][f] for w,r in zip(weights,subset))/total for f in range(9)]
    for comparison in analysis['comparisons']:
        route,bank=comparison['route'],comparison['operand_bank'];subset=[r for r in rows if r['route']==route and (bank=='both_equal_case_counts' or r['case']['operand_bank']==bank)]
        assert len(subset)==comparison['rows']
        for result in [comparison['primary'],*comparison['sensitivity']]:
            values=score(subset,result['metric'])
            assert all(abs(a-result['values'][name])<1e-12 for name,a in zip(meta['functions'],values))
            assert meta['functions'][min(range(7),key=values.__getitem__)]==result['fastest_leaf']
        assert comparison['selected_leaf']=='byte4'
        for regression in comparison['regressions']:
            baseline=meta['functions'].index(regression['baseline']);bad=[r for r in subset if r['us'][4]>r['us'][baseline]]
            assert len(bad)==regression['count'] and sum(r['case']['length']<=16 for r in bad)==regression['short_count']
            assert [r['case']['index'] for r in bad]==[r['case'] for r in regression['all_case_regressions']]
            for row,saved in zip(bad,regression['all_case_regressions']):assert abs(row['us'][4]/row['us'][baseline]-saved['ratio'])<1e-12
    final=summary['final_hardware'];data=gzip.decompress((E/'final-checks.bin.gz').read_bytes());assert len(data)==512
    for i,route in enumerate(final['routes']):
        raw=data[i*256:(i+1)*256];h=struct.unpack('<64I',raw);check=bytearray(raw);struct.pack_into('<I',check,248,0)
        assert h[62]==zlib.crc32(check) and hashlib.sha256(raw).hexdigest()==route['raw_sha256']
        assert h[:3]==(0x46434853,1,0) and h[6:10]==(3456,3,3,1152) and h[30:34]==(1152,1152,1152,3456)
        token=int(final['nonce'],16);assert h[10:13]==(token&0xffffffff,token>>32,i)
        assert h[13:17]==(final['runtime_table'],final['native_entry'],0xaa7ebc77,meta['fixture_crc'])
        assert h[17:19]==(route['public_crc32'],route['public_entry']) and h[51]==route['APP_image_crc32']
        assert h[43:45]==(meta['fixture_crc'],0xaa7ebc77) and h[20:26]==h[45:51]
        assert list(h[20:26])==meta['contexts'][meta['routes'][0]]
    closure=read('closure.json.gz')
    assert final['correctness_calls']==6912 and final['independent_CLOSED'] and closure['independent_CLOSED']
    assert closure['all_reaped'] and closure['FD_unchanged'] and closure['CDC_closed'] and closure['lease_released']
    print('M0 saved physical evidence: 464 APPs, 4608 rows, all 290304 raw intervals, weights/regressions and final 6912 checks PASS')
    if archived:print('Historical source SHA pins verified from immutable snapshots: '+', '.join(archived))
if __name__=='__main__':main()
