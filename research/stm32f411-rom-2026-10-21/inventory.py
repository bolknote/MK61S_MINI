#!/usr/bin/env python3
"""Conservative code inventory; indirect dispatch/table coverage is not complete."""
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / '.build/stm32f411-rom-20261021/deps'))
from capstone import *
from capstone.arm import *

BASE, END = 0x1FFF0000, 0x1FFF4266
raw = (HERE / 'capture/rom-a.bin').read_bytes()
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
md.detail = True
md.skipdata = True

def instruction(address):
    return next(md.disasm(raw[address-BASE:address-BASE+4], address, count=1), None)

def walk(entry):
    pending, found, calls, literals, indirect = [entry], {}, set(), {}, set()
    while pending and len(found) < 2048:
        pc = pending.pop()
        conditional = 0
        while BASE+0x188 <= pc < END and pc not in found and len(found) < 2048:
            ins = instruction(pc)
            if not ins or not ins.id: break
            found[pc] = ins
            predicated = conditional > 0
            conditional = max(0, conditional - 1)
            if ins.id == ARM_INS_IT: conditional = len(ins.mnemonic)-1
            for op in ins.operands:
                if op.type == ARM_OP_MEM and op.mem.base == ARM_REG_PC:
                    address = ((pc + 4) & ~3) + op.mem.disp
                    if BASE <= address <= BASE + len(raw)-4:
                        literals[address] = struct.unpack_from('<I', raw, address-BASE)[0]
            if ins.id in (ARM_INS_BL, ARM_INS_BLX):
                if ins.operands[0].type == ARM_OP_IMM: calls.add(ins.operands[0].imm)
                else: indirect.add(pc)
            elif ins.id in (ARM_INS_B, ARM_INS_CBZ, ARM_INS_CBNZ):
                target = ins.operands[-1].imm
                if BASE + 0x188 <= target < END: pending.append(target)
                else: calls.add(target)
                if ins.id == ARM_INS_B and ins.cc == ARM_CC_AL and not predicated: break
            elif ins.id in (ARM_INS_BX, ARM_INS_BXJ, ARM_INS_TBB, ARM_INS_TBH):
                if ins.id != ARM_INS_BX or ins.operands[0].reg != ARM_REG_LR: indirect.add(pc)
                if not predicated: break
            elif ins.id in (ARM_INS_POP, ARM_INS_LDM) and any(op.type == ARM_OP_REG and op.reg == ARM_REG_PC for op in ins.operands):
                if not predicated: break
            elif ins.id in (ARM_INS_UDF, ARM_INS_BKPT): break
            pc += ins.size
    return found, calls, literals, indirect

seeds = {0x1FFF4252, 0x1FFF425E, 0x1FFF4262, 0x1FFF3BD4, 0x1FFF3FDA, 0x1FFF102E, 0x1FFF0A4C}
for ins in md.disasm(raw[0x188:END-BASE], BASE+0x188):
    if ins.id in (ARM_INS_BL, ARM_INS_BLX) and ins.operands[0].type == ARM_OP_IMM:
        target=ins.operands[0].imm
        if BASE+0x188 <= target < END: seeds.add(target)
    if ins.id == ARM_INS_PUSH: seeds.add(ins.address)
for data in (raw, (HERE/'relocated-ram.bin').read_bytes()):
    for offset in range(0, len(data)-3, 4):
        target=struct.unpack_from('<I', data, offset)[0]
        if target & 1 and BASE+0x188 <= target < END: seeds.add(target & ~1)

report=[]
listing=[]
for entry in sorted(seeds):
    found, calls, literals, indirect=walk(entry)
    row={'entry':f'{entry:08X}', 'instructions':len(found),
         'calls':[f'{v:08X}' for v in sorted(calls)],
         'literal_values':{f'{a:08X}':f'{v:08X}' for a,v in sorted(literals.items())},
         'indirect_sites':[f'{v:08X}' for v in sorted(indirect)]}
    report.append(row)
    if not calls and not indirect and not any(0x20000000 <= v < 0x60000000 or v >= 0xE0000000 for v in literals.values()):
        listing.append('\n' + json.dumps(row))
        listing.extend(f'{i.address:08x}: {i.mnemonic:8} {i.op_str}' for _,i in sorted(found.items()))
(HERE/'inventory.json').write_text(json.dumps(report,indent=2)+'\n')
(HERE/'leaf-candidates.S').write_text('\n'.join(listing)+'\n')
print('entries',len(report),'candidate blocks',len([s for s in listing if s.startswith('\n')]))
