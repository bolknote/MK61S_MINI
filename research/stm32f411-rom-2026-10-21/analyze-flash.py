#!/usr/bin/env python3
"""Validate the actual linked Flash dispatchers before hardware execution."""
import hashlib
import json
import random
from analyze import Machine, SP, HERE, ROOT

def main():
    build=ROOT/'.build/stm32f411-rom-20261021/flash-experiment'
    layout=json.loads((build/'layout.json').read_text())
    payload=(build/'payload.bin').read_bytes()
    assert hashlib.sha256(payload).hexdigest()==layout['sha256']
    baseline=(HERE/'benchmark/resident-code.bin').read_bytes()
    m=Machine()
    m.uc.mem_write(0x08008800,baseline)
    m.uc.mem_map(layout['base'],4096)
    m.uc.mem_write(layout['base'],payload)
    rng=random.Random(0x61411)
    cases=[(n,a,v) for n in range(66) for a in range(8) for v in (0,1,0x1234,0xffffffff)]
    cases += [(rng.randrange(8193),rng.randrange(32),rng.getrandbits(32)) for _ in range(2000)]
    results=[]
    for entry in layout['entries']:
        for n,a,v in cases:
            dest=0x20004000+a
            m.uc.mem_write(0x20000000,b'\x5a'*0x20000)
            assert m.call(entry['address'],dest,v,n)==dest,(entry,n,a,v,'return')
            expected=bytearray(b'\x5a'*0x20000)
            expected[dest-0x20000000:dest-0x20000000+n]=bytes([v&255])*n
            actual=bytearray(m.uc.mem_read(0x20000000,0x20000))
            # Resident bulk saves 20 bytes; short helper saves 12; local/ROM saves 8.
            stack=20 if n>=16 and entry['name']=='resident' else 12 if 4<=n<16 else 8 if n>=16 else 0
            expected[SP-0x20000000-stack:SP-0x20000000]=actual[SP-0x20000000-stack:SP-0x20000000]
            assert actual==expected,(entry,n,a,v,'bounds/content')
        result={'name':entry['name'],'cases':len(cases),'status':'PASS'}
        results.append(result);print(json.dumps(result),flush=True)
    (HERE/'flash-validation.json').write_text(json.dumps({'payload_sha256':layout['sha256'],
        'checks':'whole SRAM excluding exact stack save; return pointer; R4-R11 and SP',
        'results':results},indent=2)+'\n')

if __name__=='__main__':main()
