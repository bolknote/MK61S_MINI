"""Exercise every n with exact source and rational polynomial/ln2 intervals."""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'.build/m0-float-fma-qualification-20261023'))
sys.path.insert(0,str(ROOT/'.build/m0-float-fma-qualification-20261023/support'))
from native_eabi_m0_arm_self_test import Machine,SP
from oracles import round_ratio
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE

proof=json.loads((W/'certificate.json').read_text());b=json.loads((W/'pack-unit-build.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(W/'native_eabi_m0_log70.inc')==proof['source_sha256']==b['source_sha256']
assert sha(W/'pack-unit.elf')==b['unit_ELF_sha256']
m=Machine(W/'pack-unit.elf',True,stack_bytes=160)
accesses=[0]
def access(*args):accesses[0]+=1
m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,access,begin=0xd0000060,end=0xd000007b)
states=[struct.pack('<7I',0,0,0,0,0,0,1),struct.pack('<7I',17,3,17,3,5,2,3)]
exact,raw=F(proof['exact_polynomial_bound']),F(proof['raw_polynomial_bound'])
fraction=proof['Q94_minus_shifted_Q70'];bias_per_n=-F(fraction,1<<24)
calls=configurations=endpoints=0;digest=hashlib.sha256();costs=[]
for n in range(1,1024):
    extra=(n+1)//2
    for name,bound,minimum,maximum in (('audit_exact',exact,8,7+extra),('audit_raw',raw,14,15+extra)):
        for d in sorted({minimum,maximum,(minimum+maximum)//2}):
            width=64+(n+configurations)%17;shift=width-53;half=1<<(shift-1)
            retained=(1<<52)+(0,1,1<<51,(1<<52)-1)[configurations%4]
            q=(retained<<shift)+half+d
            assert q.bit_length()==width and 0<d<half
            high,low=q>>64,q&((1<<64)-1);sign=bool(configurations&1)
            config=high|(n<<16)|(int(sign)<<26)
            assert high<1<<16 and config<1<<27
            expected=round_ratio(q,1,-70,64,sign)
            e2lo=n*(bias_per_n-F(1,1<<25));e2hi=n*(bias_per_n+F(1,1<<25))
            for error in (e2lo-bound,e2hi+bound):
                true=F(q)-error
                assert round_ratio(true.numerator,true.denominator,-70,64,sign)==expected,(n,name,d,width)
                endpoints+=1
            for state_index,state in enumerate(states):
                m.uc.mem_write(0xd0000060,state)
                got,_,cost=m.call(name,low,config,count=(configurations%97==0))
                assert got==expected,(n,name,d,width,hex(got),hex(expected))
                assert bytes(m.uc.mem_read(0xd0000060,28))==state
                digest.update(name.encode()+struct.pack('<QQQB',low,config,got,state_index));calls+=1
                if configurations%97==0:costs.append(cost)
            configurations+=1
assert accesses[0]==0
out=dict(status='PASS_EXACT_MAIN_LN_LN2_UPPER_GATE_BARE_ARM_AND_RATIONAL_ENDPOINTS',source_sha256=proof['source_sha256'],unit_ELF_sha256=b['unit_ELF_sha256'],actual_ARM_calls=calls,configurations=configurations,rational_RNE_endpoint_checks=endpoints,
    all_n_1_through_1023=True,exact_and_raw_packers=True,output_widths=[64,80],signs_parities_and_binade_carries=True,
    scope='Only new upper shortcut in the original uncertainty band; abstract point error bounds are independently enclosed by polynomial and ln2 intervals. Existing lower/fallback paths inherited.',
    SIO_accesses=accesses[0],both_SIO_states_preserved=True,PCS_SP_bounded_writes_every_call=True,observed_stack_bytes=SP-m.stack_lowest,profiled_instruction_range=[min(costs),max(costs)],transcript_sha256=digest.hexdigest(),full_firmware_or_ROM_loaded=False,hardware_accessed=False)
(W/'pack-unit-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
