#!/usr/bin/env python3
"""Compare existing hardware runs and code sizes; never accesses the device."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    runs={}
    for name in ('bulk','local-style','local-edges','local-loop'):
        report=json.loads((HERE/('benchmark-'+name)/'benchmark.json').read_text())
        assert report['status']=='PASS'
        assert all(report[k] for k in ('files_unchanged','state_unchanged','identity_unchanged'))
        m=report['measurements']
        assert m['resident_pointer']=='08008935'
        runs[name]={(r['bytes'],r['alignment']):r for r in m['rows'] if r['bytes']>=16}
    assert all(len(rows)==88 for rows in runs.values())
    variants=[('bulk',16,'Factory ROM; adapter in SRAM'),
              ('local-style',82,'Local ROM-style bulk in SRAM'),
              ('local-edges',64,'Local overlapping edges in SRAM'),
              ('local-loop',66,'Local edges and unpredicated loop in SRAM')]
    out={'baseline':'Existing 88-byte bulk function, at its real address in Flash',
         'decision_criterion':'User prioritizes speed. Code size is secondary when performance is comparable.',
         'preferred_candidate':'Preserve existing 0..15-byte paths; factory ROM for larger blocks on the tested Classic, pending final integration measurements. No production change.',
         'local_candidate_gate':'A local implementation must demonstrate better performance from actual Flash before being preferred; SRAM timings do not establish that.',
         'units':'Cycles per call after common empty-call overhead; medians of 9 rounds x 128 calls',
         'placement_limit':'Local candidates ran in SRAM. Their eventual Flash performance is unmeasured.',
         'variants':[], 'representative_rows':[]}
    for name,size,description in variants:
        rows=runs[name].values()
        out['variants'].append({'name':name,'description':description,'code_bytes':size,
                               'code_saving_before_guards_and_link_layout':88-size,
                               'faster_cases':sum(r['rom_over_resident']<1 for r in rows),
                               'slower_cases':sum(r['rom_over_resident']>1 for r in rows),
                               'equal_cases':sum(r['rom_over_resident']==1 for r in rows),
                               'ratio_to_resident_range':[min(r['rom_over_resident'] for r in rows),max(r['rom_over_resident'] for r in rows)]})
    for n,a in [(16,0),(17,0),(32,0),(64,0),(256,0),(1024,0),(4096,0),(4096,1)]:
        row={'bytes':n,'alignment':a}
        c=runs['bulk'][(n,a)]['cycles_per_call']
        row['resident']=(c['before']+c['repeat'])/2
        for name,_,_ in variants:row[name]=runs[name][(n,a)]['cycles_per_call']['rom']
        out['representative_rows'].append(row)
    (HERE/'local-comparison.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))


if __name__=='__main__':
    main()
