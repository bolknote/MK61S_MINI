"""Check the selected directed-gap witnesses through exact V138 public pow."""
import hashlib
import json
from pathlib import Path
import struct
import sys
ROOT=Path.cwd();WORK=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tests'))
from native_eabi_m0_arm_self_test import Machine
from unicorn import UC_HOOK_CODE
elf=ROOT/'.build/m0-pow-horner-final-v138-20261023/firmware/mk61s-picocalc-pico-h.elf'
m=Machine(elf,True,stack_bytes=16384,instruction_budget=200000000,
          bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
hits=[0]
def entered(*unused):hits[0]+=1
address=m.elf.symbols['mk61_m0_pow_rescue']&~1
m.uc.hook_add(UC_HOOK_CODE,entered,begin=address,end=address)
source=WORK/'boundary-gap.json';rows=json.loads(source.read_text())['cases'];digest=hashlib.sha256()
for row in rows:
    x,y,want=(int(row[k],16) for k in ('x','y','rounded'))
    actual=m.call('_ZN12compact_math3powEdd',x,y)[0]
    assert actual==want,(row,hex(actual))
    digest.update(struct.pack('<4Q',x,y,want,actual))
record=dict(status='PASS_PUBLIC_POW_ON_DIRECTED_GAP_WITNESSES',cases=len(rows),wrong_rounding=0,
    final_rescue_entries=hits[0],elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
    input_report_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),result_sha256=digest.hexdigest(),
    scope='Nineteen targeted public API calls on exact V138, with actual captured BootROM and ABI/bounded-write checks. No new full firmware qualification, physical timing or all-input proof.',
    interpretation='These difficult points remain correct in V138. A zero rescue count means this run does not test the final1024-bit undecided branch.',
    candidate_changed=False,hardware_accessed=False)
(WORK/'witness-arm.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
