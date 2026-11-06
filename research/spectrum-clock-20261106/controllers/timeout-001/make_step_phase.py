"""Prepare one short10MHz step after a successful previous mode."""
import argparse
import json
from pathlib import Path
import clock_hil as c
def main():
    parser=argparse.ArgumentParser();parser.add_argument('mhz',type=int)
    parser.add_argument('previous_receipt',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();mhz=args.mhz
    sequence=[125,*range(130,251,10)]
    c.need(mhz in sequence and mhz not in (125,200,250),'Not an intermediate step')
    previous=args.previous_receipt.resolve();r=json.loads(previous.read_text())
    c.need(r['status']=='PASS' and r['lease']=='reserved_ports_closed' and
           r['result']['mhz']==sequence[sequence.index(mhz)-1],'Previous step incomplete/changed')
    c.need(all(s['closed'] and not s['errors'] for s in r['cdc_sessions']),'Previous CDC session not released')
    c.clock_guard(r['status_after'],r['expected'],125)
    c.need(not args.output.exists(),'One-shot phase exists')
    p=dict(action='step',uid=c.UID,mhz=mhz,expected=r['expected'],native_binding=r['native_binding'],
           previous_receipt=str(previous),pins={str(path):c.sha(path) for path in (previous,Path(__file__).resolve())})
    args.output.write_text(json.dumps(p,indent=2)+'\n');print('Prepared intermediate',mhz,'MHz')
if __name__=='__main__':main()
