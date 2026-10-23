"""Observe the existing endpoint approximation before any firmware change."""
import hashlib,json,re,struct,sys
from pathlib import Path
root=Path.cwd();work=Path(__file__).resolve().parent;parent=root/'.build/m0-sqrt-zero-tail-v163-20261023'
sys.path.insert(0,str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine,SP
from m0_mpfr_oracle import Oracle
elf=parent/'firmware/mk61s-picocalc-pico-h.elf'
m=Machine(elf,True,stack_bytes=16384,instruction_budget=200000000,
    bootrom=root/'research/rp2040-memset-2026-10-21/capture/bootrom.bin');oracle=Oracle()
table=(parent/'source/code/native_eabi_m0_refine_table.inc').read_text()
words=list(map(int,re.findall(r'(\d+)U',re.search(r'refine_atan_half_pi\[3\]=\{(.*?)\};',table)[1])))
half_pi=sum(v<<(32*j) for j,v in enumerate(words));one=0x3ff0000000000000;records=[]
for n in (1,2,3,63,64,65,96,97,98,127,128,129,1<<20,1<<24,1<<26,1<<27):
    x=one-n;X=((x&((1<<52)-1))|(1<<52))<<10
    scale_ptr=SP-2048;exponent_ptr=SP-2052
    qroot=m.call('asin_root_estimate',X,scale_ptr)[0]
    scale=struct.unpack('<I',m.uc.mem_read(scale_ptr,4))[0]
    q=m.call('asin_atan_small',qroot,X,c=(exponent_ptr<<32)|scale)[0]
    exponent=struct.unpack('<i',m.uc.mem_read(exponent_ptr,4))[0]
    if not q:continue
    shift=-(exponent+7);retained,tail=divmod(q,1<<shift)
    quant=retained+(tail>(1<<(shift-1)) or (tail==(1<<(shift-1)) and retained&1))
    center=half_pi-quant;distance=abs((center&((1<<18)-1))-(1<<17))
    actual,_,instructions=m.call('_ZN12compact_math4asinEd',x,count=True)
    assert actual==oracle.reference('asin',x)
    records.append(dict(distance_below_one=n,x=f'{x:016X}',scale=scale,exponent=exponent,
        root=f'{qroot:016X}',small=f'{q:016X}',center_q70=str(center),distance_to_midpoint_q70=distance,
        rejected_by_radius128=distance<=128,would_pass_radius2=distance>2,output=f'{actual:016X}',instructions=instructions))
report=dict(status='DIAGNOSTIC_EXISTING_V163_ENDPOINTS_NOT_NEW_BOUND_PROOF',records=records,
    elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    ABI='Direct helpers use reserved output slots; those slots are not a callee stack measurement.',hardware_accessed=False,goal_complete=False)
(work/'probe.json').write_text(json.dumps(report,indent=2)+'\n')
for r in records:print(r['distance_below_one'],'e',r['exponent'],'distanceQ70',r['distance_to_midpoint_q70'],'instructions',r['instructions'])
