#!/usr/bin/env python3
"""Verify the committed synthetic M4 timings; never contact a device."""
import csv,gzip,hashlib,io,json,math,statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent
def gm(values):return math.exp(statistics.fmean(math.log(x) for x in values))
def main():
    expected=json.loads((HERE/'RESULTS-M4.json').read_text());tables={}
    for archive in expected['archives']:
        raw=(HERE/'evidence'/archive['path']).read_bytes()
        assert len(raw)==archive['bytes'] and hashlib.sha256(raw).hexdigest()==archive['sha256']
        source=gzip.decompress(raw)
        assert len(source)==archive['uncompressed_bytes'] and hashlib.sha256(source).hexdigest()==archive['uncompressed_sha256']
        rows=list(csv.DictReader(io.StringIO(source.decode())));table={};raw_count=0
        for row in rows:
            key=(row['kind'],int(row['index']),int(row['route']));assert key not in table
            ticks=list(map(int,row['raw_ticks'].split()));assert len(ticks)==7 and all(x>0 for x in ticks)
            table[key]=statistics.median(ticks)/64;raw_count+=len(ticks)
        groups,samples=(17688,123816) if archive['name']=='m4-candidates' else (2592,18144)
        assert len(table)==groups and raw_count==samples
        tables[archive['name']]=(rows,table)
    rows,table=tables['m4-final-static'];cmp_ids=sorted({int(r['index']) for r in rows if r['operation']=='strcmp'})
    assert len(cmp_ids)==288
    measured={}
    for name,kind,route,baseline in [('native_latency_ratio','shared',2,3),('standalone_latency_ratio','standalone',0,1),('shared_local_latency_ratio','shared',0,1),('shared_bridge_latency_ratio_vs_local','shared',4,0)]:
        value=gm([table[kind,i,route]/table[kind,i,baseline] for i in cmp_ids])
        assert math.isclose(value,expected['M4']['selected_strcmp'][name],rel_tol=1e-12)
        measured[name]=value
    assert all(table['shared',i,2]<table['shared',i,3] for i in cmp_ids)
    print(json.dumps(dict(status='PASS_COMMITTED_RAW_EVIDENCE',groups=20280,raw_duration_values=141960,final_static_ratios=measured,hardware_IO=0)))

if __name__=='__main__':main()
