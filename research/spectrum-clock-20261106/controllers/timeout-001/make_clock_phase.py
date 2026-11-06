"""Prepare one next frequency only after a complete predecessor PASS."""
import argparse
import json
from pathlib import Path
import clock_hil as c

def main():
    parser=argparse.ArgumentParser();parser.add_argument('mhz',type=int,choices=(125,200,250))
    parser.add_argument('previous_receipt',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();previous=args.previous_receipt.resolve()
    r=json.loads(previous.read_text());c.need(r['status']=='PASS' and r['lease']=='reserved_ports_closed',
        'Predecessor must complete successfully and close every port')
    c.need(all(row['closed'] and not row['errors'] for row in r['cdc_sessions']),'Predecessor descriptor fault')
    c.need(not args.output.exists(),'One-shot phase already exists')
    expected=r['expected']
    if args.mhz==125:c.need(r['action']=='flash' or r.get('installation_verified'),
                           '125MHz must start from verified diagnostic install')
    else:
        c.need(r['action']=='step' and r['result']['mhz']=={200:190,250:240}[args.mhz],
               'Higher frequency requires the preceding10MHz step')
    c.clock_guard(r['status_after'],expected,125)
    root=c.ROOT/'.build/spectrum-games-20261106'
    files={c.APP:root/'cosmic-ay-dense/profile-accepted-paced/SPPIPE.APP',
        'SPCF.Z80':root/'COSMIC.Z80','SPCF.ULP':root/'COSMIC.ULP'}
    hashes={c.APP:'3b5d9f5acff6af235eeb55aea67b34e0cd302b7ffbe038d284f4992fb4146c84',
        'SPCF.Z80':'fb548f065667d28ce91eeb66007533a7661a12f8b43e3e6d318f97db369b401c',
        'SPCF.ULP':'1d0fba6bca201bf7b3061d5f2000c31a895e980308f5bbe906c42dac52c2ab16'}
    for name,path in files.items():c.need(c.sha(path)==hashes[name],'Unqualified payload/fixture')
    p=dict(action='clock',uid=c.UID,mhz=args.mhz,expected=expected,folder=c.FOLDER,
        cleanup_mode='lease-timeout' if args.mhz==250 else 'command-reset',
        native_binding=r['native_binding'],previous_receipt=str(previous),
        measurement=dict(warmup_frames=100,window_frames=300,windows=10,timer_interval_uncertainty_us=1),
        files={name:dict(local=str(path),sha256=hashes[name]) for name,path in files.items()},
        game=dict(id='SPCF',title='Cosmic Payback',ulaplus=0,hud_roi_bytes=[0,32,0,8],hud_signature='67D57373'),
        pins={str(path):c.sha(path) for path in (*files.values(),previous,Path(__file__).resolve())})
    args.output.write_text(json.dumps(p,indent=2)+'\n')
    print('Prepared',args.mhz,'MHz, exact firmware',expected,'after',previous.name)
if __name__=='__main__':main()
