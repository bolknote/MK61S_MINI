#!/usr/bin/env python3
"""Strictly admit an INTERP APP result, retaining every raw ABBA observation."""
import argparse
from fractions import Fraction
import hashlib
import json
from math import isqrt
from pathlib import Path
import statistics
import struct
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))

GROUP_NAMES=('wide32','mul32x8','q62','rsqrt_new_cpu','rsqrt_new_interp',
 'sqrt_new_cpu','sqrt_new_interp','exp_address','ln_split_addresses','pow_refine_address')
VARIANTS={'all':(0,10,768),'alu':(0,3,288),'rsqrt':(3,2,96),'sqrt':(5,2,96),'address':(7,3,288)}

def seed_oracle(m,p):
    num=1<<116;den=m<<p;q=isqrt(num//den);mid=den*(2*q+1)**2
    if 4*num>mid or (4*num==mid and q&1):q+=1
    return min(0xFFFFFFFF,q)

def frequency(values):
    ctrl,div,selected,cs,pwr,fb,prim=values
    assert ctrl&1 and not ctrl&0xE0 and selected==2,'CLK_SYS must select PLL_SYS'
    assert cs&(1<<31) and not pwr&0x29,'PLL_SYS not locked/running'
    ref=cs&63;post1=(prim>>16)&7;post2=(prim>>12)&7
    assert ref and post1 and post2 and div
    # The named Pico H target and A748 build use a 12 MHz external crystal.
    return Fraction(12000000*(fb&4095)*256,ref*post1*post2*div)

def decode(raw,*,physical=True,expected_rounds=7,expected_samples=4096,variant='all'):
    assert len(raw)>=256,'short output'
    h=struct.unpack_from('<14I',raw)
    magic,version,length,rows,rounds,samples,checks,failures,status,core,control,ipsr,primask,restored=h
    first,groups,expected_checks=VARIANTS[variant]
    assert (magic,version,length,rows,rounds,samples)==(0x31505249,3,len(raw),groups*6,expected_rounds,expected_samples),h
    assert checks==expected_checks and failures==0 and status==1 and core==0 and not control&1 and ipsr==0 and primask==0 and restored==1,h
    before=struct.unpack_from('<7I',raw,56);after=struct.unpack_from('<7I',raw,84)
    assert before==after,'CPU clock changed during run'
    hz=frequency(before);assert hz==125000000,('unexpected clock',str(hz))
    div_before=struct.unpack_from('<4I',raw,112);div_after=struct.unpack_from('<4I',raw,128)
    assert div_before==div_after,'divider state changed'
    state_before=struct.unpack_from('<14I',raw,144);state_after=struct.unpack_from('<14I',raw,200)
    assert state_before==state_after,'interpolator state changed'
    row_size=48+40*rounds
    assert len(raw)==256+rows*row_size
    result=[]
    for index in range(rows):
        offset=256+index*row_size;g,mode,kind=struct.unpack_from('<3I',raw,offset)
        assert (g,mode,kind)==(first+index//6,index//3%2,index%3)
        x,y,a,b=struct.unpack_from('<4Q',raw,offset+16)
        if g<3:
            if g==0:expected=(x&0xFFFFFFFF)*(y&0xFFFFFFFF)
            elif g==1:expected=(x&0xFFFFFFFF)*(y&255)
            else:
                q,r=divmod(x*y,1<<62);expected=(q+int(r>(1<<61) or (r==(1<<61) and q&1)))&((1<<64)-1)
            assert a==b==expected,('arithmetic',g,kind)
        elif g<7:
            if g<5:
                expected=seed_oracle(x,y);assert abs(a-expected)<=13 and abs(b-expected)<=13
            else:
                n=x<<(10+y);r=isqrt(n)
                if 4*n>(2*r+1)**2 or (4*n==(2*r+1)**2 and r&1):r+=1
                r=min(0xFFFFFFFF,r);num=1<<114;den=x<<y;v=isqrt(num//den)
                if 4*num>den*(2*v+1)**2 or (4*num==den*(2*v+1)**2 and v&1):v+=1
                assert abs((a&0xFFFFFFFF)-r)<=11 and abs((a>>32)-v)<=13
                assert abs((b&0xFFFFFFFF)-r)<=2 and abs((b>>32)-v)<=6
        else:
            j=(x>>10)&1023
            expected=0x20010000+((x&511)<<3) if g==7 else (0x20010000+(j<<3))|((0x20014000+j)<<32) if g==8 else 0x20010000+12*j
            assert a==b==expected,('address',g,kind)
        raw_times=[list(struct.unpack_from('<4I',raw,offset+48+16*r)) for r in range(rounds)]
        empty=[list(struct.unpack_from('<2I',raw,offset+48+16*rounds+8*r)) for r in range(rounds)]
        hashes=[list(struct.unpack_from('<4I',raw,offset+48+24*rounds+16*r)) for r in range(rounds)]
        pairs=[]
        for r in range(rounds):
            assert hashes[r][0]==hashes[r][3] and hashes[r][1]==hashes[r][2],('ABBA result drift',g,r)
            if g<3 or g>6:assert len(set(hashes[r]))==1,('candidate/control checksum',g,r)
            ta=(raw_times[r][0]+raw_times[r][3])/2;tb=(raw_times[r][1]+raw_times[r][2])/2
            if r&1:ta,tb=tb,ta
            control_time=sum(empty[r])/2
            pairs.append(dict(cpu_raw_us=ta,candidate_raw_us=tb,empty_us=control_time,
              delta_us_per_call=(tb-ta)/samples,cpu_total_us_per_call=ta/samples,
              candidate_total_us_per_call=tb/samples,empty_reference_us_per_call=control_time/samples))
        result.append(dict(group=GROUP_NAMES[g],mode='per_call_transaction' if mode else 'prepared_batch',input=kind,
          a=hex(x),b=hex(y),result_a=hex(a),result_b=hex(b),raw_us=raw_times,empty_us=empty,checksums=hashes,
          rounds=pairs,median_delta_us_per_call=statistics.median(v['delta_us_per_call'] for v in pairs)))
    return dict(status='PASS',variant=variant,hardware_verified=physical,physical_timing=physical,
      output_sha256=hashlib.sha256(raw).hexdigest(),rows=rows,checks=checks,clock_hz=int(hz),
      clock_basis='Read CLK_SYS/PLL_SYS before and after; fixed 12 MHz Pico H crystal; no CPU cycle counter.',
      checksum='V3 sequential low/high-word multiply and right-shift mix; 32-bit integrity check, not a proof against arbitrary corruption.',
      timing_units='Raw microseconds include function calls, loop, checksum and applicable setup/restore. Empty references are retained without subtraction; no kernel-only speed is inferred. Deltas preserve quantisation, interrupts and negative observations.',
      interpolator_state_restored=True,divider_state_restored=True,results=result)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('raw',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--variant',choices=VARIANTS,required=True)
    a=p.parse_args();r=decode(a.raw.read_bytes(),variant=a.variant);a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k!='results'},indent=2))
if __name__=='__main__':main()
