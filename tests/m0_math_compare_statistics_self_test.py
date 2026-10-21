#!/usr/bin/env python3
"""Reproduce odd-round order bias and check old/new timing wire decoders."""
import json
import struct

from hil_m0_math_compare import decode


def fixture(version,own=20,qfplib=20,first_penalty=10):
    rounds=9 if version in (1,2) else 12
    cached=version in (2,4)
    chunk=dict(index=0,stream_index=0,part=0,kind=1,cases=1,loops=1000,operation='sin',stream='synthetic_order_effect')
    value=0x3FF0000000000000
    inputs=struct.pack('<8I3Q',0x4D304246,1,0,1,1,1000,0x10000101,0x10180001,value,0,value)
    elapsed=[]
    for library,base in enumerate((own,qfplib)):
        elapsed += [1000*(1+base+(first_penalty if library==(r&1) else 0)) for r in range(rounds)]
    raw=struct.pack('<10I',0x4D305250,version,0,1,1,1000,rounds,0,0xFFFFFFFF,1000000)
    raw+=struct.pack('<'+'I'*(4*rounds),*elapsed,*([1000]*(2*rounds)))
    if cached:raw+=bytes(32*rounds)
    raw+=struct.pack('<2Q',value,value)
    return raw,chunk,inputs


def main():
    checks=0
    for version in (1,2,3,4):
        for penalty in (-10,10):
            raw,chunk,inputs=fixture(version,first_penalty=penalty)
            row=decode(raw,chunk,inputs);balanced=row['order_balanced']
            assert balanced['own_over_qfplib']==1
            assert balanced['median_paired_delta_us']==0
            assert balanced['rounds_excluded']==(1 if version<3 else 0)
            if version<3:
                assert row['timings']['own']['median_us']!=row['timings']['qfplib']['median_us']
            checks+=1
        for delta in (-1,1):
            raw,chunk,inputs=fixture(version,own=20+delta)
            balanced=decode(raw,chunk,inputs)['order_balanced']
            assert balanced['median_paired_delta_us']==delta
            assert (balanced['own_over_qfplib']>1)==(delta>0)
            checks+=1
        raw,chunk,inputs=fixture(version)
        bad_rounds=bytearray(raw);struct.pack_into('<I',bad_rounds,24,7)
        bad_value=bytearray(raw);bad_value[-16]^=1
        bad_version=bytearray(raw);struct.pack_into('<I',bad_version,4,99)
        for invalid in (raw[:-1],bad_rounds,bad_value,bad_version):
            try:decode(invalid,chunk,inputs)
            except (AssertionError,struct.error):pass
            else:raise AssertionError('Malformed timing report accepted')
            checks+=1
    print(json.dumps(dict(status='PASS',checks=checks,
        reproduced='Equal-cost kernels falsely rank differently under odd-round per-library medians with an alternating order effect. Opposite-order pair averages recover equality and preserve a real one-us difference.',
        formats=[1,2,3,4],hardware_used=False),indent=2))


if __name__=='__main__':
    main()
