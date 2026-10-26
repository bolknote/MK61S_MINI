"""Read-only CPU harness for actual parent/control/candidate pow images."""
from pathlib import Path
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
A=Path(__file__).resolve().parent;ROOT=A.parents[1];W=ROOT/'.build/m0-pow-exp-table-product-20261025'
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
B=ROOT/'.build/m0-exp-cached-product-20261024'
S=ROOT/'.build/m0-pow-square-ordinary-20261024'
R=ROOT/'.build/m0-pow-rsqrt-asm-20261024'
C=ROOT/'.build/m0-exp-directed-product-20261024'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP,STOP,bits
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import equal
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3

sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),
        'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
linked=json.loads((W/'link.json').read_text())
images={n:ElfImage(W/(n+'.elf')) for n in ('control','candidate')}
for n,e in images.items():assert sha(W/(n+'.elf'))==linked['images'][n]['ELF_sha256']
resident=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf')
new=images['candidate'].named_sections['.pow_flash']
assert not any(old[2]&2 and old[5] and max(old[3],new[3])<min(old[3]+old[5],new[3]+new[5]) for old in resident.named_sections.values())

def machine(label):
    if label=='Qfplib':
        return Machine(ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
    m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,
              bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
    for directory in (B,S,R):
        e=ElfImage(directory/'candidate.elf');e.load(m.uc)
        m.elf.symbols.update({n:a for n,a in e.symbols.items() if n.startswith('mk61_m0_pow_')})
    e=ElfImage(C/'candidate.elf');s=e.named_sections['.product_ram']
    m.uc.mem_write(s[3],e.bytes_at(s))
    if label!='parent':
        e=images[label];e.load(m.uc)
        m.elf.symbols.update({n:a for n,a in e.symbols.items() if n.startswith('mk61_m0_pow_')})
    return m

def state_after(m,state):
    after=bytes(m.uc.mem_read(0xd0000060,28))
    if state==states['DIRTY']:assert after==state
    else:assert not(struct.unpack('<7I',after)[6]&2)

def table():
    e=images['candidate'];name='_ZN7m0_eabiL9exp_tableE'
    a=e.symbols[name];assert e.sizes[name]==4096
    s=next(s for s in e.named_sections.values() if s[3]<=a<s[3]+s[5])
    raw=e.bytes_at(s)[a-s[3]:a-s[3]+4096]
    roots=struct.unpack('<512Q',raw)
    assert roots[0]==1<<62 and all(v&0xffffffff for v in roots[1:])
    assert all(1<<62<=v<1<<63 for v in roots)
    return roots,dict(address=a,bytes_sha256=hashlib.sha256(raw).hexdigest(),
                      roots=512,only_low32zero_index=0,identity=roots[0])

def hook_products(m,label):
    calls=[];e=images[label] if label!='parent' else images['control']
    targets={0x20038ee4:'general'}
    if label=='candidate':targets[e.symbols['mk61_m0_pow_exp_table_product']&~1]='table'
    for address,kind in targets.items():
        def hook(uc,pc,size,user,kind=kind):
            a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32)
            b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
            calls.append(dict(kind=kind,a=f'{a:016X}',b=f'{b:016X}'))
        m.uc.hook_add(UC_HOOK_CODE,hook,begin=address,end=address)
    return calls
