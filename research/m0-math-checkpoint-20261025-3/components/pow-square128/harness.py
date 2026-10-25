"""Actual previous table-product pow image plus one fixed-address kernel delta."""
import json,struct,sys
from collections import Counter
sys.dont_write_bytecode=True
from parent_harness import *
HERE=A;BASE=W
kernel_images={n:ElfImage(HERE/(n+'.elf')) for n in ['control','candidate']}
build=json.loads((HERE/'build.json').read_text())
for n in kernel_images:assert sha(HERE/(n+'.elf'))==build['images'][n]['ELF_sha256']
base_machine=machine
def square_machine(label):
    if label=='Qfplib':return base_machine(label)
    m=base_machine('candidate')
    if label in kernel_images:kernel_images[label].load(m.uc)
    return m

MASK64=(1<<64)-1
def high32(a,b):return (a>>16)*(b>>16)+((a&65535)*(b>>16)>>16)+((a>>16)*(b&65535)>>16)
def approximate(a,b):return ((a>>32)*(b>>32)+high32(a&0xffffffff,b>>32)+high32(a>>32,b&0xffffffff))&MASK64
unit=json.loads((HERE/'unit-proof.json').read_text())
costs={k:v for k,v in unit['class_costs'].items()}
def square_trace(m):
    calls=[]
    address=build['entry_address']
    def hook(uc,pc,size,user):
        pointer=uc.reg_read(UC_ARM_REG_R0)
        h,l,e,r=struct.unpack('<QQII',uc.mem_read(pointer,24))
        product=(h*h+(2*approximate(l,h) if l else 0))&((1<<128)-1)
        key=str((bool(l),bool(product>>127)));c=costs[key]
        calls.append(dict(high=f'{h:016X}',low=f'{l:016X}',exponent=e,radius=r,
                          old_cost=c['control'],new_cost=c['candidate']))
    m.uc.hook_add(UC_HOOK_CODE,hook,begin=address,end=address)
    return calls
