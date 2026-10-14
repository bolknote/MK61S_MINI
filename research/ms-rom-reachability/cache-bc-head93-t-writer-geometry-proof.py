#!/usr/bin/env python3
"""Conditional SIGN/A1/E9 geometry, all fifteen accepted entry positions.

Symbolic ring words and keys, not keyboard constructors. The original ROM
calculates every primary step. No model state is loaded into an emulator.
Current T/aux1 marks cannot targetT through this common accepted SIGN path;
an explicitly hypothetical P8/Y marker pair supplies a different address.
"""
from pathlib import Path
import runpy

from z3 import And, If, UGE

root=Path(__file__).resolve().parent
prior=runpy.run_path(str(root/'cache-bc-head93-t-marker-recovery-proof.py'))
w,q=(prior[n] for n in ('w','q'))
slots=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y']


def check(start,marks,hypothesis=False):
    label='T_E9_'+('hyp_' if hypothesis else 'actual_')+start
    pages={n:q['State'](label+'_'+n).m for n in slots};original=dict(pages)
    a=q['State'](label);a.m=pages[start];p=w['base'](a,0x9C)
    p.add(a.r[30]==2,a.r[33]==3,
          If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7)))
    for n in slots:p.add(pages[n][22]==15 if n in marks else pages[n][22]!=15)
    reads=[];writes=[];route=[];first_writer=None
    for step in range(80):
        p.push();ips=q['possible_values'](w['ip'](a),p,257);p.pop()
        assert len(ips)==1,(label,route,ips)
        code=ips[0];here=slots[(slots.index(start)+step)%15]
        following=slots[(slots.index(start)+step+1)%15]
        route.append(f'{code:02X}/{here}')
        if code==0xEE:reads.append(here)
        old=pages[here];out=[]
        a=w['ex'](a,code,*q['arbitrary_keys'](label+'_keys'+str(step)),
                  serial_inputs=pages[following],emitted_outputs=out)
        if code==0xE9:
            assert first_writer is None;first_writer=here
            source=reads[-1]
            w['prove'](p,And(*[out[1+3*j]==original[source][1+3*j] for j in range(12)],
                *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),
                label+' exact single E9, other lanes/services held',False)
            writes.append(('E9',here))
        elif code==0xA3:
            w['prove'](p,And(out[28]==original[reads[-1]][28],out[31]==2,out[34]==3,
                *[out[j]==old[j] for j in range(42) if j not in (28,31,34)]),
                label+' request32 header only',False)
            writes.append(('A3',here));break
        else:
            w['prove'](p,And(*[out[j]==old[j] for j in range(42)]),
                       label+' no other ring writes',False)
        pages[here]=out
    else:raise AssertionError((label,'no bounded writer'))
    if not hypothesis:
        assert reads in (['Z'],['V']),(label,reads)
        assert writes==[('E9','Y'),('A3','X1')],(label,writes)
        w['prove'](p,And(*[pages['T'][j]==original['T'][j] for j in range(42)],
            *[pages['P10'][j]==original['P10'][j] for j in range(42)]),
            label+' T and P10 unchanged',False)
    else:
        assert start in ('X1','V','X') and reads==['aux0']
        assert writes==[('E9','T'),('A3','P9')],writes
        w['prove'](p,And(*[pages['P10'][j]==original['P10'][j] for j in range(42)]),
            label+' primary P10 untouched (secondary NOT covered)',False)
    print('PASS CONDITIONAL',label,'EE',reads,'writers',writes,'words',len(route),flush=True)
    return route


def run():
    prior['r']['inlet']['immutable_reference']()
    for start in slots:check(start,{'T','aux1'})
    print('PASS all15 accepted9C positions: fixed T/aux1 geometry always writes Y/X1, '
          'notT/X; arbitrary other page fields and keys. Not a theorem for '
          'other callers, marker layouts or native entry construction.',flush=True)
    route=check('X1',{'T','P8','aux1','Y'},True)
    print('HYPOTHESIS ONLY: adding P8/F and Y/F at accepted9C/X1 yields '
          'EE/aux0 -> E9/T -> A3/P9. Native markers, secondary completion '
          'and arbitrary old-bank preservation remain unproved.',flush=True)
    print('PATH',' -> '.join(route),flush=True)
    for start in ('V','X'):
        check(start,{'P8','aux1','Y'},True)
    print('PASS CONDITIONAL prepared P8/aux1/Y (T=non-F): accepted9C/V orX '
          'readsaux0, writesE9/T and requestA3/P9; all other page fields/keys '
          'arbitrary. Native retry observed accepted9C/X; whole secondary '
          'arithmetic target and arbitrary old-bank preservation remain separate.',flush=True)
    prior['r']['inlet']['immutable_reference']()


if __name__=='__main__':run()
