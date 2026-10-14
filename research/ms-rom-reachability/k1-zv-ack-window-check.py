#!/usr/bin/env python3
"""Exact final ACK scanner at real/Z, independent of numeric arithmetic.

Finite analysis of the 15 possible positions of ROM 37, not a keyboard
search. Stops at ACK; neither arithmetic reachability nor output is claimed.
"""
import runpy
from pathlib import Path
from z3 import And, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('analyze_ms_pending_opcodes.py')))
slots=q['slots']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check();p.pop()
    assert answer==unsat,(label,answer)

def check(start):
    tag='ack_window_'+start
    pages={n:q['State'](tag+'_'+n).m for n in slots};original=dict(pages)
    a=q['State'](tag);a.m=pages[start];p=q['base'](a,0x37)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','Z') else pages[n][22]!=15)
    scanned=[]
    for step in range(16):
        here=slots[(slots.index(start)+step)%15]
        following=slots[(slots.index(start)+step+1)%15]
        p.push();ips=q['q']['possible_values'](q['address'](a),p,257);p.pop()
        assert len(ips)==1,(start,scanned,ips)
        ip=ips[0];assert ip in (0x37,0x27)
        old=pages[here];out=[]
        a=q['ex'](a,ip,*q['keys'](tag+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        if ip==0x37:
            scanned.append(here)
            prove(p,And(*[x==y for x,y in zip(out,old)]),'scan holds '+here)
        else:
            marker='Z' if start in ('control','X1','X','Y','Z') else 'marker'
            target='T' if marker=='Z' else 'control'
            assert here==target and scanned[-1]==marker
            prove(p,And(out[31]==15,*[out[j]==old[j] for j in range(42) if j!=31]),'only ACK '+here)
            pages[here]=out
            for n in slots:
                if n!=here:prove(p,And(*[x==y for x,y in zip(pages[n],original[n])]),'held page '+n)
            return {'scanStart':start,'markerFound':marker,'ackSlot':target,'scanCommands':len(scanned)}
        pages[here]=out
    raise AssertionError('no ACK within one ring')

if __name__=='__main__':
    for start in slots:print('PASS',check(start),flush=True)
    print('LIMIT: local IK1303 37 -> 27 only. Correct ACK is necessary, not sufficient '
          'for a safe result or full keyboard protocol.',flush=True)
