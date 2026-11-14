#!/usr/bin/env python3
"""Recheck paired physical RP2040 exp/sin/cos records and produce a compact table."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from m0_sincos_timing import decode_v5


def data(path):
    return json.loads(path.read_bytes())


def sha(value):
    return hashlib.sha256(value).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline','candidate','session','csv'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--candidate-session',type=Path,
                        help='Read a separately coordinated candidate run against the original control')
    parser.add_argument('--candidate-role',choices=('candidate','compact','balanced'),default='candidate')
    args=parser.parse_args()
    cfg={r:data(p/'benchmark.json') for r,p in (('base',args.baseline),('candidate',args.candidate))}
    reference='RP2040_factory_BootROM_v3'
    assert all(c['reference_kind']==reference and c['reference_flash_bytes']==0 for c in cfg.values())
    assert len({c['bootrom_sha256'] for c in cfg.values()})==1
    runs={'base':(args.session,'base'), 'candidate':(args.candidate_session or args.session,args.candidate_role)}
    for role,(path,subdir) in runs.items():
        session=data(path/'session.json')
        assert session['status']=='PASS'
        assert session.get('clean_restored_readback') or (session.get('final_image_retained') and
            session['last_readback_verified']==subdir and session['additional_flash_writes']==0)
        assert session[subdir+'_namespace_removed'] and session['cdc_descriptor_closed']
        (readback,)=path.glob(f'*-{subdir}-readback.bin')
        assert sha(readback.read_bytes())==cfg[role]['firmware_manifest']['bin_sha256']
    maps={r:{chunk['index']:chunk for chunk in c['chunks']} for r,c in cfg.items()}
    assert maps['base'].keys()==maps['candidate'].keys()
    rows=[]
    for index in sorted(maps['base']):
        devices={}
        inputs={}
        for role,c in cfg.items():
            chunk=maps[role][index];inputs[role]=Path(chunk['input']).read_bytes()
            assert sha(inputs[role])==chunk['input_sha256']
            path,subdir=runs[role]
            raw=(path/subdir/f'{index:03d}.bin').read_bytes()
            report=decode_v5(raw,chunk,inputs[role],minimum_warmup_us=c['app_warmup_us'],
                             pairs_cap=c['warmup_pairs_cap'])
            assert report['qfplib_wrong_results']==report['owned_wrong_rounding']==0
            devices[role]=report
        a,b=inputs.values()
        assert a[:24]==b[:24] and a[28:]==b[28:]
        baseline,candidate=devices.values()
        row=dict(index=index,operation=baseline['operation'],stream=baseline['stream'],cases=baseline['cases'])
        for role,r in devices.items():
            t=r['order_balanced'];a,b=t['empirical_delta_range_us']
            row.update({role+'_own_us':t['us_per_call']['own'],role+'_rom_us':t['us_per_call']['qfplib'],
                        role+'_delta_min_us':a,role+'_delta_max_us':b,
                        role+'_own_misses':r['timings']['own']['cache']['median_misses_per_call']})
        rows.append(row)
    with args.csv.open('w',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(rows)
    n=sum(r['cases'] for r in rows)
    losses=[r['index'] for r in rows if r['candidate_own_us']>r['candidate_rom_us']]
    print(f'{len(rows)} paired groups, {4*n} MPFR checks passed; candidate slower in groups {losses}')


if __name__=='__main__':main()
