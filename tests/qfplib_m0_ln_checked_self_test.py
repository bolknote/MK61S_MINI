#!/usr/bin/env python3
"""Audit experimental Qfplib ln certificates, RNE outputs, ARM ABI and cost."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import random
import struct
import sys

from m0_mpfr_oracle import Oracle, _Number, bits, real
from native_eabi_m0_arm_self_test import Machine, SP, nan
from qualify_m0_rounding import corpus


class IntervalOracle:
    def __init__(self, oracle):
        self.lib=oracle.lib
        ptr=C.POINTER(_Number)
        self.lib.mpfr_set_str.argtypes=[ptr,C.c_char_p,C.c_int,C.c_int]
        self.lib.mpfr_div_2ui.argtypes=[ptr,ptr,C.c_ulong,C.c_int]
        self.lib.mpfr_cmp.argtypes=[ptr,ptr]

    def contains(self,x,approx,error,precision=62):
        values=[_Number() for _ in range(5)]
        inp,lower,upper,left,right=values
        for v in values:self.lib.mpfr_init2(C.byref(v),256)
        try:
            self.lib.mpfr_set_d(C.byref(inp),real(x),0)
            self.lib.mpfr_log(C.byref(lower),C.byref(inp),3)
            self.lib.mpfr_log(C.byref(upper),C.byref(inp),2)
            for v,n in [(left,approx-error),(right,approx+error)]:
                assert self.lib.mpfr_set_str(C.byref(v),str(n).encode(),10,0)==0
                self.lib.mpfr_div_2ui(C.byref(v),C.byref(v),precision,0)
            assert self.lib.mpfr_cmp(C.byref(left),C.byref(lower))<=0,('below interval',hex(x),approx,error)
            assert self.lib.mpfr_cmp(C.byref(right),C.byref(upper))>=0,('above interval',hex(x),approx,error)
        finally:
            for v in values:self.lib.mpfr_clear(C.byref(v))


def round_fixed(p,precision=62):
    if not p:return 0
    sign=(p<0)<<63;p=abs(p);width=p.bit_length();s=width-53
    if s>0:
        q,r=divmod(p,1<<s)
        q+=2*r>(1<<s) or 2*r==(1<<s) and q&1
        if q==1<<53:q>>=1;width+=1
    else:q=p<<-s
    return sign|((width-1-precision+1023)<<52)|(q&((1<<52)-1))


def check_pack(machine,address,precision=62):
    rng=random.Random(0x5041434b)
    cases=[(sign*((1<<60)+delta),65) for sign in [-1,1] for delta in range(-256,257)]
    for _ in range(10000):
        width=rng.randrange(54,94 if precision==82 else 74)
        cases.append((rng.randrange(1<<(width-1),1<<width)*rng.choice([-1,1]),rng.choice([1,32,64,65,200,601,65536])))
    accepted=0
    for value,error in cases:
        machine.uc.mem_write(address,value.to_bytes(12,'little',signed=True)+struct.pack('<I',error))
        ok=machine.call('pack_fast',address,address+16,width=32)[0]&0xffffffff
        if not ok:continue
        got=int.from_bytes(machine.uc.mem_read(address+16,8),'little')
        lo,hi=round_fixed(value-error,precision),round_fixed(value+error,precision)
        assert lo==hi==got,(value,error,hex(lo),hex(hi),hex(got))
        accepted+=1
    return dict(cases=len(cases),accepted=accepted,power_boundary_regressions=1026)


def check_multiply(machine,address):
    rng=random.Random(0x4d554c)
    edges=[0,1,65535,65536,0xffff0000,0xffffffff,0x80000000]
    pairs=[(a,b) for a in edges for b in edges]
    pairs.extend((rng.getrandbits(32),rng.getrandbits(32)) for _ in range(10000))
    for a,b in pairs:
        high=machine.call('mul_hi',a|(b<<32),address)[0]&0xffffffff
        low=int.from_bytes(machine.uc.mem_read(address,4),'little')
        assert low|(high<<32)==a*b,(hex(a),hex(b),hex(low),hex(high))
    return len(pairs)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--samples',type=int,default=10000)
    p.add_argument('--json',type=Path,required=True)
    args=p.parse_args()
    path=args.build/'checked.elf';original=args.build/'original.elf'
    expected_sha=hashlib.sha256(path.read_bytes()).hexdigest()
    machine=Machine(path);fast_machine=Machine(path);forced=Machine(path)
    compensated='qfp_ln_comp96' in machine.elf.symbols
    precision=82 if compensated else 62
    fast_symbol='qfp_ln_comp96' if compensated else 'qfp_ln_fast96'
    compensation=None;integer_model=None
    if compensated:
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/qfplib-m0-full'))
        from generate_ln_compensated import generate_compensation
        from prove_compensated_ln import model
        compensation=generate_compensation()[1];integer_model=model
    relative66='qfp_ln_near_seed66' in machine.elf.symbols
    relative64='qfp_ln_near_seed64' in machine.elf.symbols
    relative=relative66 or relative64 or 'qfp_ln_near_seed' in machine.elf.symbols
    relative_model=None
    if relative:
        if relative66:from prove_near66_ln import model as relative_model
        elif relative64:from prove_near64_ln import model as relative_model
        else:from prove_near_ln import model as relative_model
    near_low=0x3feffc0000000000 if relative64 or relative66 else 0x3feffe0000000000
    near_high=0x3ff0020000000000 if relative64 or relative66 else 0x3ff0010000000000
    oracle=Oracle();interval=IntervalOracle(oracle)
    values={x[0] for x in corpus('ln',args.samples)}
    one=bits(1.)
    for i in range(1,2047):values.update(((i<<52)-1,i<<52,(i<<52)+1))
    for i in range(53):
        for sign in [-1,1]:
            middle=one+sign*(1<<i)
            values.update(v for v in range(middle-3,middle+4) if v>0)
    for center in [one-65535,one+32767,bits(100.),0x3FF01E2A43FC46C8]:values.update(range(center-4,center+5))
    rng=random.Random(0x514c4e)
    values.update(rng.randrange(1,1<<52) for _ in range(args.samples//4))
    if relative:
        near_rng=random.Random(0x4e454152)
        values.update(bits(1+near_rng.uniform(-2.**-12,2.**-12)) for _ in range(args.samples))
        if relative64 or relative66:values.update(bits(1+near_rng.uniform(-2.**-11,2.**-11)) for _ in range(args.samples))
        for x in [near_low,near_high]:values.update(range(x-4,x+5))
        for j in range(-512,513):
            c=bits(1+j*2.**-21);values.update(range(c-1,c+2))
    values=sorted(values)
    address=SP-4032
    pack=check_pack(fast_machine,address,precision)
    products=check_multiply(fast_machine,address)
    print('PASS fast pack',pack,flush=True)
    print('PASS wide integer products',products,flush=True)
    digest=hashlib.sha256();certificates=0;relative_certificates=0
    for i,x in enumerate(values):
        expected=oracle.reference('ln',x)
        got=machine.call('qfp_dln_checked',x)[0]
        assert got==expected or nan(expected) and nan(got) and bool(got&(1<<51)),(hex(x),hex(got),hex(expected))
        if 0<x<0x7ff0000000000000:
            fast_machine.call(fast_symbol,x,address)
            data=bytes(fast_machine.uc.mem_read(address,16))
            approx=int.from_bytes(data[:12],'little',signed=True)
            error=int.from_bytes(data[12:],'little')
            if compensated:assert (approx,error)==integer_model(x,compensation),(hex(x),approx,error)
            interval.contains(x,approx,error,precision);certificates+=1
        if relative and near_low<=x<=near_high and x!=one:
            fast_machine.call('qfp_ln_near_seed66' if relative66 else 'qfp_ln_near_seed64' if relative64 else 'qfp_ln_near_seed',x,address)
            data=bytes(fast_machine.uc.mem_read(address,16))
            seed=(int.from_bytes(data[:8],'little'),int.from_bytes(data[8:12],'little'),int.from_bytes(data[12:],'little'))
            assert seed==relative_model(x),(hex(x),seed,relative_model(x))
            interval.contains(x,-seed[0] if seed[2] else seed[0],1 if relative66 else 2 if relative64 else 5,(128 if relative66 else 126 if relative64 else 124)-seed[1])
            relative_certificates+=1
        digest.update(struct.pack('<3Q',x,got,expected))
        if (i+1)%1000==0:print('PASS',i+1,'RNE cases',flush=True)
    forced_cases=0
    positive=[v for v in values if 0<v<0x7ff0000000000000]
    forced_values=positive[::max(1,len(positive)//128)]+[one,one-1,one+1,1]
    undecided={4:0,8:0}
    for w in [4,8]:
        for x in forced_values:
            ok=forced.call('refine',x,w|(address<<32))[0]&0xffffffff
            if not ok:
                assert w==4 or x==one,('Q245 undecided',hex(x))
                undecided[w]+=1;continue
            got=int.from_bytes(forced.uc.mem_read(address,8),'little')
            expected=oracle.reference('ln',x)
            assert got==expected,(w,hex(x),hex(got),hex(expected))
            forced_cases+=1
    # Instruction comparisons include refinements, not only accepted fast cases.
    baseline=Machine(original)
    groups={}
    profiles={
        'normal_exponents':[(rng.randrange(1,2047)<<52)|rng.getrandbits(52) for _ in range(256)],
        'ordinary_half_to_two':[bits(rng.uniform(.5,2.)) for _ in range(256)],
        'near_one_tiny':[one+d for d in [-128,-17,-2,-1,0,1,2,17,128]],
        'near_one_outer':[bits(1+sgn*2.**-i) for i in range(10,37) for sgn in [-1,1]],
        'decimal_powers':[bits(10.**i) for i in range(-300,301,5)],
    }
    if relative:
        near_rng=random.Random(0x514e4541)
        profiles['near_one_random']=[bits(1+near_rng.uniform(-2.**-12,2.**-12)) for _ in range(512)]
    for name,inputs in profiles.items():
        old=[];new=[]
        for x in inputs:
            old.append(baseline.call('qfp_dln',x,count=True)[2])
            result=machine.call('qfp_dln_checked',x,count=True)
            assert result[0]==oracle.reference('ln',x)
            new.append(result[2])
        groups[name]=dict(cases=len(inputs),original_mean=sum(old)/len(old),checked_mean=sum(new)/len(new),original_max=max(old),checked_max=max(new),checked_over_original=sum(new)/sum(old))
        print(name,groups[name],flush=True)
    assert expected_sha==hashlib.sha256(path.read_bytes()).hexdigest()
    allocated=sum(s[5] for s in machine.elf.sections if s[2]&2)
    report=dict(status='PASS_RESEARCH_GATES',cases=len(values),wrong_rounding=0,
        fast_interval_certificates=certificates,fast_interval_precision=precision,
        fast_Q62_interval_certificates=certificates if precision==62 else 0,
        fast_Q82_interval_certificates=certificates if precision==82 else 0,
        integer_model_matches=certificates if compensated else 0,forced_refinement_cases=forced_cases,
        relative_seed_interval_certificates=relative_certificates,
        forced_refinement_undecided=undecided,instructions=groups,
        checked_code_and_constants_bytes=allocated,additional_constant_table_bytes=800+(472 if compensated else 0),
        static_ram_bytes=sum(s[5] for s in machine.elf.sections if s[2]&3==3),
        observed_stack_bytes=SP-machine.stack_lowest,
        elf_sha256=expected_sha,oracle='MPFR directed bounds: exact RNE and direct containment of Q62 intervals',mpfr=oracle.version,
        result_sha256=digest.hexdigest(),build=json.loads((args.build/'build.json').read_text()),
        synthetic_pack_certificates=pack,
        exact_integer_product_cases=products,
        qualification_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitations=['Not integrated into firmware; M4 unchanged.','Finite qualification corpus; Q245 final undecided trap remains, all-input totality unproved.','Physical timing pending; instruction groups may still be slower than Qfplib.','Other Qfplib functions retain their previous limitations.'],
        scope='Research qualification of interval-certified ln only; does not establish completion of the whole runtime objective.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS_RESEARCH_GATES',len(values),'cases',flush=True)


if __name__=='__main__':main()
