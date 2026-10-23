"""Compare every retained128 state bit against the qualified V122 kernels."""
import hashlib
import json
from pathlib import Path
import random
import struct
import sys
root=Path.cwd();work=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine,SP
rom=root/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
paths=[root/'.build/m0-pow-root-prefix-v122-20261023/firmware/mk61s-picocalc-pico-h.elf',work/'firmware/mk61s-picocalc-pico-h.elf']
machines=[Machine(p,True,stack_bytes=16384,bootrom=rom) for p in paths]
rng=random.Random(0x13012864);digest=hashlib.sha256();ptr,bptr=SP-15000,SP-14936
counts=dict(squares=0,products=0,base_products=0,aliases=0)
def state(low_zero=False):
    high=rng.randrange(1<<63,1<<64);low=0 if low_zero else rng.getrandbits(64)
    error=0 if low_zero else rng.randrange(131073)
    return struct.pack('<QQiI',high,low,rng.randrange(-32736,32737),error)
def run(machine,name,a,b,alias):
    machine.uc.mem_write(ptr,a);machine.uc.mem_write(bptr,b)
    machine.call(name,ptr,ptr if alias else bptr,32)
    if not alias:assert bytes(machine.uc.mem_read(bptr,24))==b
    return bytes(machine.uc.mem_read(ptr,24))
for index in range(6000):
    a,b=state(index%7==0),state(index%5==0)
    for name,key,alias in [('pow_integer128_square','squares',False),('pow_integer128_multiply','products',index%17==0)]:
        other=a if alias else b
        results=[run(m,name,a,other,alias) for m in machines]
        assert results[0]==results[1],(index,name)
        counts[key]+=1;counts['aliases']+=alias;digest.update(a+other+results[1])
    exact=state(True)
    before=run(machines[0],'pow_integer128_multiply',a,exact,False)
    after=run(machines[1],'pow_integer128_base',a,exact,False)
    assert before==after,(index,'exact-base')
    counts['base_products']+=1;digest.update(a+exact+after)
record=dict(status='PASS_BIT_IDENTICAL_RETAINED128_ARM_STATES',counts=counts,result_sha256=digest.hexdigest(),
    parent_elf_sha256=hashlib.sha256(paths[0].read_bytes()).hexdigest(),elf_sha256=hashlib.sha256(paths[1].read_bytes()).hexdigest(),
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    scope='Complete24-byte outputs match qualified V122 kernels, including zero-low squares and multiplier aliases; new exact-base specialization matches the generic parent multiply. Every ARM call checks ABI/bounded writes. Finite state test; algebra and public MPFR runs are separate.')
(work/'cores.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS:',counts,flush=True)
