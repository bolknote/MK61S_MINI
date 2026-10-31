#!/usr/bin/env python3
"""Positive/fault/malformed wire tests from offline execution, no HIL claims."""
import argparse
import importlib.util
import json
from pathlib import Path
import struct

spec=importlib.util.spec_from_file_location('strlen_decoder',Path(__file__).with_name('decode.py'))
wire=importlib.util.module_from_spec(spec)
spec.loader.exec_module(wire)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment',type=Path,required=True)
    p.add_argument('--proof',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    proof=json.loads((a.proof/'proof.json').read_text())
    assert proof['status']=='PASS_HOST_ONLY_NOT_HARDWARE'
    positive=negative=preserved_negative=0
    for output in proof['outputs']:
        name=output['file']
        app_name=next(app for app in ['standalone-sram','shared-sram','standalone-flash','shared-flash'] if name.startswith(app+'-'))
        batch=int(name.split('-')[3])
        exp,anchor,app,rows,input_bytes=wire.context(a.experiment,app_name,batch)
        raw=(a.proof/name).read_bytes()
        result=wire.decode(raw,exp,anchor,app,rows,input_bytes)
        positive+=1
        if result['status']!='PASS_WIRE_ONLY':
            continue
        # Every dynamic and static anchor, placement, descriptor, unused field,
        # unknown error, short/long buffer and negative correction is checked.
        changes=[(i*4,16 if i==11 else 1) for i in [0,1,2,3,4,5,6,7,8,9,10,11,12,13,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,60,61,62,63]]
        changes += [(256+4*i,1) for i in range(6)]
        functions=len(app['functions']);leaves=len(anchor['leaves'])
        changes += [((32+functions+i)*4,1) for i in range(leaves)]
        changes += [((32+functions+leaves)*4,1)]
        if len(rows['rows'])<7:
            changes += [(256+len(rows['rows'])*(24+7*4*(functions+4)),1)]
        for offset,xor in changes:
            broken=bytearray(raw)
            struct.pack_into('<I',broken,offset,struct.unpack_from('<I',broken,offset)[0]^xor)
            try:
                wire.decode(bytes(broken),exp,anchor,app,rows,input_bytes)
            except wire.Invalid:
                negative+=1
            else:
                raise AssertionError(('mutant accepted',name,offset))
        for broken in [raw[:-1],raw+b'\0']:
            try:
                wire.decode(broken,exp,anchor,app,rows,input_bytes)
            except wire.Invalid:
                negative+=1
            else:
                raise AssertionError('Length mutant accepted')
        broken=bytearray(raw)
        struct.pack_into('<I',broken,6*4,1)
        struct.pack_into('<I',broken,7*4,99)
        try:
            wire.decode(broken,exp,anchor,app,rows,input_bytes)
        except wire.Invalid:
            negative+=1
        else:
            raise AssertionError('Unknown failure accepted')
        # An unusually large control can make a corrected sample negative.
        # Keep the raw value and its sign; neither rejection nor clamping.
        for off in [256+24,256+24+4*(functions+3)]:
            struct.pack_into('<I',broken,off,100000)
        struct.pack_into('<I',broken,6*4,0)
        struct.pack_into('<I',broken,7*4,0)
        parsed=wire.decode(broken,exp,anchor,app,rows,input_bytes)
        assert any(v<0 for v in parsed['rows'][0]['corrected_per_call'][0])
        assert parsed['rows'][0]['raw'][0][0]==100000
        preserved_negative+=1
    result=dict(status='PASS_HOST_ONLY',positive_synthetic_reports=positive,rejected_mutants=negative,
        negative_corrections_preserved=preserved_negative,physical_reports=0)
    assert not a.output.exists()
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':
    main()
