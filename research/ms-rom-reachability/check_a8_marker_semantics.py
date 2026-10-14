#!/usr/bin/env python3
"""False-marker four-word block and its header-7 exit in original IK1302.

These are conditional ROM contracts with arbitrary ring inputs and keys.
Native reachability and all-chip ring preservation are checked separately
by check_a8_marker_route.cjs; symbolic SAT alone is not a key sequence.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat

ROOT=Path(__file__).resolve().parent


def check(q):
    byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
    address=lambda a:byte(a.r[36],a.r[39])
    stack=lambda a:tuple(byte(a.st[36+i],a.st[39+i]) for i in range(3))

    def prove(p,claim,label):
        assert p.check()==sat,('empty premise',label)
        p.push();p.add(~claim);assert p.check()==unsat,label;p.pop()
        print('PASS:',label,flush=True)

    a=q['State']('marker_block');p=q['base_solver'](a,0xE5)
    p.add(a.m[22]==15,a.s1==8,stack(a)[0]==0xA8,stack(a)[1]==0xE1)
    sequence=[0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9]
    pages=[a.m]+[q['State']('marker_page_%d'%i).m for i in range(1,9)]
    b=a;initial_word=[a.r[3*i] for i in range(12)];entries=[]
    for index,ip in enumerate(sequence):
        prove(p,address(b)==ip,'forced four-word path entry %d: %02X'%(index,ip))
        before=b;entries.append(before);out=[]
        b=q['execute_command'](before,ip,*q['arbitrary_keys']('marker_block_keys_%d'%index),
                               serial_inputs=pages[index+1],emitted_outputs=out)
        if 3<=index<=6:
            carried=initial_word if index==3 else [pages[index-1][1+3*i] for i in range(12)]
            prove(p,And(*[out[1+3*i]==carried[i] for i in range(12)],
                        *[b.r[3*i]==pages[index][1+3*i] for i in range(12)],
                        *[out[i]==pages[index][i] for i in range(42) if i%3!=1 or i>=37]),
                  '%02X pass %d exchanges exactly twelve numeric tetras'%(ip,index-2))
        else:
            prove(p,And(*[out[i]==pages[index][i] for i in range(42)]),
                  '%02X does not write this ring word'%ip)
    prove(p,And(address(b)==0xE1,b.s1==0,
                *[b.r[3*i]==pages[6][1+3*i] for i in range(10)],
                b.r[30]==entries[-1].r[32],b.r[33]==entries[-1].r[35]),
          'finite block returns E1; A9 retains ten displaced tetras, replaces its exponent high fields')

    # Actual last read of the false-marker construction takes a header-7 X,
    # whereas the previously found short A8 route needs header 6 here.
    x=q['State']('marker_header7');p=q['base_solver'](x,0xEE)
    suffix=[int(s,16) for s in 'EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A E4 DE D7 7F'.split()]
    b=x;entries=[]
    for index,ip in enumerate(suffix):
        p.add(address(b)==ip)
        assert p.check()==sat,('inconsistent header-7 suffix',index,hex(ip))
        b=b.copy();b.r[36]=q['N4'](ip);b.r[39]=q['N4'](ip>>4);entries.append(b)
        b=q['execute_command'](b,ip,*q['arbitrary_keys']('marker_header_keys_%d'%index))
    prove(p,x.m[34]==7,'the D7 exit requires header 7 at its preceding EE')
    # Identify data provenance without assuming convenient values of the
    # initial mode, saved stack, mantissa, or future serial inputs.
    prove(p,And(b.r[2]==x.st[4],b.r[5]==x.st[1],b.r[23]==7),
          'header-7 exit restores R2=old ST4, R5=old ST1 and leaves keyboard-prefix R23=7')
    # Equality to M34 under the D7-path premise is NOT provenance: both
    # expressions equal 7 there. DE actually writes the literal constant.
    c=q['State']('marker_de_prefix');d=q['execute_command'](c,0xDE,*q['arbitrary_keys']('marker_de_keys'))
    prove(q['base_solver'](c,0xDE),d.r[23]==7,
          'DE writes literal 7 to R23 for EVERY input header; D7 skips the ordinary formatter that clears it')
    for ip in (0x33,0x35,0xC5,0x8A,0x65,0x7B,0xB5,0x83,0xB7,0x45,0x8B):
        c=q['State']('marker_scan_%x'%ip)
        d=q['execute_command'](c,ip,*q['arbitrary_keys']('marker_scan_keys_%x'%ip))
        local=q['base_solver'](c,ip)
        prove(local,d.r[23]==c.r[23],'%02X preserves the abnormal R23 before decoding'%ip)
    c=q['State']('marker_decode');d=q['execute_command'](c,0x4A,*q['arbitrary_keys']('marker_decode_keys'))
    local=q['base_solver'](c,0x4A)
    prove(local,And(d.r[23]==c.r[23]-1,(address(d)==0x4C)==(c.r[23]==0)),
          '4A tests the saved prefix and decrements it: incoming 7 cannot take the ordinary zero-prefix 4C edge')
    return {'q':q,'initial':x,'solver':p,'entries':entries,'final':b}


if __name__=='__main__':
    check(runpy.run_path(str(ROOT/'ik1302_symbolic.py')))
