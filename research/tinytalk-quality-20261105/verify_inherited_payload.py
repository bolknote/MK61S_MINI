#!/usr/bin/env python3
"""Compare fixed packed regions directly, independently of gradient-mask code."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True)
    p.add_argument('--trained',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--inherited-mlp-width',type=int,default=1024)
    args=p.parse_args();old=args.inherited_mlp_width
    assert old%32==0
    def read(path):
        data=Path(path).read_bytes();size=struct.unpack_from('<I',data,8)[0]
        meta=json.loads(data[12:12+size]);assert meta['format']=='TTQ4v1' and meta['tied_output']
        return data,meta,(12+size+15)//16*16
    before,sm,so=read(args.source);after,tm,to=read(args.trained)
    targets={t['name']:t for t in tm['tensors']};checked=0;active_changed=0
    for t in sm['tensors']:
        u=targets[t['name']];a=before[so+t['offset']:so+t['offset']+t['bytes']];b=after[to+u['offset']:to+u['offset']+u['bytes']]
        if t['name'].endswith('mlp.c_fc.weight'):
            assert t['shape'][1]==u['shape'][1]
            n=old*(t['padded_columns']//32)*18;assert a[:n]==b[:n],t['name'];checked+=n
            active_changed+=a[n:]!=b[n:]
        elif t['name'].endswith('mlp.c_fc.bias'):
            n=old*4;assert a[:n]==b[:n],t['name'];checked+=n;active_changed+=a[n:]!=b[n:]
        elif t['name'].endswith('mlp.c_proj.weight'):
            assert t['shape'][0]==u['shape'][0]
            sa=t['padded_columns']//32*18;sb=u['padded_columns']//32*18;n=old//32*18
            for row in range(t['shape'][0]):
                assert a[row*sa:row*sa+n]==b[row*sb:row*sb+n],t['name'];checked+=n
                active_changed+=a[row*sa+n:(row+1)*sa]!=b[row*sb+n:(row+1)*sb]
        elif t['name'].endswith('wte.weight'):
            assert t['shape'][1]==u['shape'][1] and u['shape'][0]>=t['shape'][0]
            assert a==b[:len(a)],t['name'];checked+=len(a);active_changed+=len(b)>len(a)
        else:
            assert t['shape']==u['shape'] and a==b,t['name'];checked+=len(a)
    assert active_changed>0,'Confirm this is a learned model, not just the initializer'
    report={'source_packed_sha256':hashlib.sha256(before).hexdigest(),
        'trained_packed_sha256':hashlib.sha256(after).hexdigest(),'all_inherited_packed_bytes_identical':True,
        'inherited_payload_bytes_checked':checked,'tensors_checked':len(sm['tensors']),
        'changed_active_segments':active_changed,'inherited_mlp_width':old,
        'quality_improvement_measured':False,'native_runtime_measured':False}
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':main()
