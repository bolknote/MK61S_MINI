#!/usr/bin/env python3
"""Local symbolic cache writer contracts, never native reachability.

The native reference is observed, never edited. An ST34=4 substitution is
made only in a Z3 primary-chip state and is explicitly hypothetical.
"""
import json
from pathlib import Path
import runpy
import subprocess
from z3 import And, BitVec, BitVecVal, If, Or, ZeroExt, sat, unsat, simplify

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]
A=lambda a:[a.r[3*i] for i in range(12)]
positions=(0,3,9,12,18,21)

def prove(p,claim,label,log=True):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);outcome=p.check()
    assert outcome==unsat,(label,p.model() if outcome==sat else outcome)
    p.pop()
    if log:print('PASS:',label,flush=True)

def constant(e):
    a=State('hypothetical_constant')
    for group in ('r','m','st'):
        setattr(a,group,[q['N4'](n) for n in e[group]])
    for n in ('s','s1'):setattr(a,n,q['N4'](e[n]))
    for n in ('l','t','carry'):setattr(a,n,q['N1'](e[n]))
    return a

def number(v):
    v=simplify(v)
    assert hasattr(v,'as_long'),v
    return v.as_long()

def snap(a):
    return {**{n:[number(x) for x in getattr(a,n)] for n in ('r','st')},
            **{n:number(getattr(a,n)) for n in ('s','s1','l','t','carry')}}

def report(a,out=None):
    return {'ip':'%02X'%number(address(a)),
      'A':''.join('%X'%number(v) for v in A(a)),
      'B':''.join('%X'%number(a.r[1+3*i]) for i in range(12)),
      'C':''.join('%X'%number(a.r[2+3*i]) for i in range(12)),
      'r34':number(a.r[34]),'st34':number(a.st[34]),'s1':number(a.s1),
      'sp':['%02X'%number(v) for v in stack(a)],
      **({'emittedM1':''.join('%X'%number(out[3*i]) for i in range(12))} if out is not None else {})}

def local():
    a=State('dc_de_d4');p=base(a,0xDC);p.add(a.r[34]==4)
    pages=[State('dc_page_%d'%i).m for i in range(6)]
    a.m=pages[0];b=a;outs=[]
    for index,ip in enumerate((0xDC,0xDE,0xD4,0xDD,0xD4)):
        prove(p,address(b)==ip,'%02X is forced in DC/DE/D4/DD/D4 with B-header4'%ip)
        out=[];b=ex(b,ip,*keys('dc_writer_keys_%d'%index),
                   serial_inputs=pages[index+1],emitted_outputs=out)
        outs.append(out)
        if ip in (0xDC,0xDE,0xDD):
            prove(p,And(*[x==y for x,y in zip(out,pages[index])]),'%02X has no outgoing ring write'%ip)
    prove(p,And(address(b)==stack(a)[0],b.s1==4),
          'five-command writer returns through ORIGINAL top return byte, S1=4')
    first=outs[2];second=outs[4]
    prove(p,And(first[0]==14,*[first[3*(i+1)]==a.r[3*i] for i in range(8)],
                first[27]==a.r[25],first[30]==a.r[28],first[33]==a.r[31]),
          'first D4 writes M1=(E,A0..A7,B8,B9,B10); A8 is replaced by DC')
    prove(p,And(*[second[3*i]==a.r[3*i] for i in range(8)],
                second[24]==a.r[25],second[27]==a.r[28],second[30]==a.r[31],second[33]==15),
          'second DD/D4 writes M1=(A0..A7,B8,B9,B10,F) aligned')
    prove(p,And(*[And(first[j]==pages[2][j],second[j]==pages[4][j])
                  for j in range(42) if j%3!=0 or j>=36]),
          'both D4 writes preserve all M2/M3 and nonnumeric tail tetras')
    prove(p,And(*[b.r[(i+33)%36]==a.r[i] for i in positions]),
          'all six raw cache tetras survive both M1 writes, with A rotated by DD')
    p.add(stack(a)[0]==0xAF)
    for index,ip in enumerate((0xAF,0xAE),5):
        prove(p,address(b)==ip,'writer return %02X is forced'%ip)
        out=[];before=b
        b=ex(b,ip,*keys('dc_writer_keys_%d'%index),emitted_outputs=out)
        prove(p,And(*[x==y for x,y in zip(out,before.m)]),
              '%02X does not write the outgoing ring'%ip)
    prove(p,And(address(b)==0xDC,
                *[b.r[3*i]==a.r[3*(i+1)] for i in range(7)],
                b.r[21]==a.r[25],b.r[24]==a.r[28],b.r[27]==a.r[31],
                b.r[30]==15,b.r[33]==a.r[0],
                *[b.r[1+3*i]==a.r[1+3*i] for i in range(11)],
                stack(b)[0]==0xAF),
          'AF return re-enters DC after 7 commands with A shifted/truncated; AF may change B header')

def m2_contracts():
    # These three entry contracts are conditional ROM gadgets. They do not
    # construct the missing native return tags or a keyboard entry at 46.
    a=State('m2_marker_wait');p=base(a,0xE5);p.add(a.s1==8,stack(a)[0]==0x47)
    out=[];b=ex(a,0xE5,*keys('m2_marker_wait_keys'),emitted_outputs=out)
    prove(p,And(address(b)==If(a.m[22]==15,BitVecVal(0xE6,8),BitVecVal(0xE5,8)),
                b.s1==8,stack(b)[0]==0x47,*[b.r[3*i]==a.r[3*i] for i in range(12)],
                *[x==y for x,y in zip(out,a.m)]),
          'E5 raw-source marker wait may repeat any finite count, holds all12 A tetras and return47')
    for lane,prelude in ((0,(0x46,)),(1,(0x98,0x9A,0x46)),
                         (2,(0x9A,0x98,0x9A,0x46))):
        a=State('m2_gadget_lane%d'%lane);p=base(a,prelude[0])
        source=[a.r[lane+3*i] for i in range(12)]
        if lane==1:p.add(stack(a)[0]==0x46)
        if lane==2:p.add(stack(a)[0]==0x98,stack(a)[1]==0x46)
        seq=prelude+(0xE5,0xE5,0xE6,0xE8,0xE7)
        pages=[State('m2_lane%d_page%d'%(lane,i)).m for i in range(len(seq)+1)]
        a.m=pages[0];b=a
        for i,ip in enumerate(seq):
            if ip==0xE5:p.add(pages[i][22]==(0 if seq[i+1]==0xE5 else 15))
            prove(p,address(b)==ip,'symbolic M2 source lane%d executes %02X'%(lane,ip))
            out=[];b=ex(b,ip,*keys('m2_lane%d_keys%d'%(lane,i)),
                       serial_inputs=pages[i+1],emitted_outputs=out)
            if ip==0xE7:
                prove(p,And(*[out[1+3*j]==source[j] for j in range(12)],
                            *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37],
                            *[b.r[3*j]==pages[i][1+3*j] for j in range(12)],
                            address(b)==0x47),
                      'conditional lane%d route exchanges all 12 raw source tetras with M2, returns47'%lane)
            else:
                prove(p,And(*[x==y for x,y in zip(out,pages[i])]),
                      'conditional lane%d %02X writes no outgoing ring tetra'%(lane,ip))
        print('CONDITIONAL M2 ROM GADGET, not native:',lane,
              ' '.join('%02X'%ip for ip in seq),'-> 47',flush=True)

def original_return_contracts():
    # Source already in B at 98, with original numeric return tags. These
    # finite routes do not produce any M2 write before reaching idle 35.
    for ret in (0x8E,0x93):
        a=State('original_return_%02X'%ret);p=base(a,0x98)
        p.add(stack(a)[0]==ret)
        if ret==0x93:p.add(stack(a)[1]==0x8E)
        source=[a.r[1+3*i] for i in range(12)]
        seq=(0x98,0x9A)+((0x93,0x94,0x95,0x98,0x9A) if ret==0x93 else ())
        seq+=(0x8E,0x5E,0x5D,0xB8,0x7F)
        b=a
        for index,ip in enumerate(seq):
            prove(p,address(b)==ip,'original %02X route command %d forced'%(ret,index),False)
            out=[];before=b;b=ex(b,ip,*keys('original_%02X_keys%d'%(ret,index)),emitted_outputs=out)
            prove(p,And(*[x==y for x,y in zip(out,before.m)]),
                  'original %02X route %02X no memory write'%(ret,ip),False)
        prove(p,address(b)==0x33,'original %02X return route reaches33 without any ring write'%ret)
        b=ex(b,0x33)
        prove(p,address(b)==0x35,'quiet 33 finishes the original %02X return at35'%ret)
        if ret==0x8E:
            prove(p,And(*[b.r[3*i]==source[i] for i in range(12)]),
                  'original8E route preserves all12 raw B tetras in A at35, but writes no M2')
        print('ORIGINAL TAG CONDITIONAL, not native:',' '.join('%02X'%ip for ip in seq),'-> 33 (quiet) -> 35',flush=True)

def header_local_contracts():
    a=State('header7_exit');p=base(a,0xDC);p.add(a.r[34]==7);b=a
    for index,ip in enumerate((0xDC,0xDE,0xD7,0x7F)):
        prove(p,address(b)==ip,'header7 exit step%d forced'%index,False)
        before=b;out=[];b=ex(b,ip,*keys('header7_keys%d'%index),emitted_outputs=out)
        prove(p,And(*[x==y for x,y in zip(out,before.m)]),'header7 %02X has no memory write'%ip,False)
    prove(p,And(address(b)==0x33,*[b.r[(i+33)%36]==a.r[i] for i in positions]),
          'R34=7 gives forced DC DE D7 7F→33, holds all6 rotated raw cache tetras; no write')
    b=ex(b,0x33)
    prove(p,address(b)==0x35,'quiet33 finishes header7 exit at35')
    a=State('d1_pair');p=base(a,0xD1);b=a
    seq=(0xD1,0x91,0x92,0x93,0x94,0x95,0x98,0x9A,0x93,0x94,0x95,0x98,0x9A)
    for index,ip in enumerate(seq):
        prove(p,address(b)==ip,'D1 call step%d forced'%index,False)
        before=b;out=[];b=ex(b,ip,*keys('d1_pair_keys%d'%index),emitted_outputs=out)
        prove(p,And(*[x==y for x,y in zip(out,before.m)]),'D1 pair %02X has no memory write'%ip,False)
    prove(p,And(address(b)==0xD2,*[b.r[3*i]==a.r[3*i] for i in range(12)]),
          'D1 paired numeric restore forces D2, holding all12 A tetras with no memory writes')

def selected_hypothesis(native,forall_final=None):
    events=native['events'];start=next(i for i,e in enumerate(events) if e['ip']==0x8C)
    stop=next(i for i,e in enumerate(events[start:],start) if e['ip']==0xDC)
    # Replay baseline exactly before substituting ST34. Actual future M pages
    # are supplied as fixed serial data; this is no full-ring witness.
    for hypothesized in (False,True):
        b=constant(events[start]);
        if hypothesized:b.st[34]=q['N4'](4)
        for i,e in enumerate(events[start:stop],start):
            assert number(address(b))==e['ip']
            b=ex(b,e['ip'],e['keyX'],e['keyY'],serial_inputs=[q['N4'](v) for v in events[i+1]['m']])
            if not hypothesized:
                expected=constant(events[i+1])
                assert snap(b)==snap(expected),('baseline replay mismatch',i)
        print('BASELINE' if not hypothesized else 'HYPOTHETICAL ST34=4 before 8C',json.dumps(report(b)),flush=True)
        if not hypothesized:continue
        expected=constant(events[stop]);expected.r[34]=q['N4'](4)
        assert snap(b)==snap(expected),'selected ST34=4 changes more than the DC B header'
        sequence=[];seen={};reports=[];concrete_states=[];joined=False;closed=False
        for index in range(120):
            ip=number(address(b));sequence.append(ip)
            if index==70 and forall_final is not None:
                solver=q['Solver']()
                prove(solver,And(*[x==y for field in ('r','st') for x,y in zip(getattr(forall_final,field),getattr(b,field))],
                                 *[getattr(forall_final,n)==getattr(b,n) for n in ('s','s1','carry')]),
                      'forall6 after ten forced cycles joins the fixed closed-cycle trajectory')
                joined=True
            state_key=json.dumps(snap(b),sort_keys=True)
            if state_key in seen:
                period=index-seen[state_key]
                assert ip in (0xDC,0xD4) and period==14
                print('HYPOTHETICAL internal-state cycle at command',index,
                      'period',period,'A',report(b)['A'],flush=True)
                # Prove the repeated internal cycle with arbitrary future
                # ring and keyboard pins from this fixed primary entry.
                for i,step in enumerate(sequence[seen[state_key]:index]):
                    before=concrete_states[seen[state_key]+i].copy()
                    before.m=State('fixed_cycle_page%d'%i).m
                    before.t=q['BitVec']('fixed_cycle_t%d'%i,1)
                    before.l=q['BitVec']('fixed_cycle_l%d'%i,1)
                    after=concrete_states[seen[state_key]+i+1] if i+1<period else b
                    c=ex(before,step,*keys('fixed_cycle_keys%d'%i));solver=q['Solver']()
                    prove(solver,And(*[x==y for field in ('r','st') for x,y in zip(getattr(c,field),getattr(after,field))],
                                     *[getattr(c,n)==getattr(after,n) for n in ('s','s1','carry')]),
                          'fixed hypothesis cycle step %d (%02X) independent of keys and incoming ring'%(i,step))
                print('PASS: fixed hypothesis closed 14-command primary-data/control cycle (L/T may follow key activity)',flush=True)
                closed=True
                break
            seen[state_key]=index
            concrete_states.append(b)
            before=report(b);out=[]
            b=ex(b,ip,serial_inputs=[q['N4'](0) for _ in range(42)],emitted_outputs=out)
            entry={**before,**({'emittedM1':''.join('%X'%number(out[3*i]) for i in range(12))} if ip==0xD4 else {}),'next':'%02X'%number(address(b))}
            reports.append(entry)
            if index<7 or ip==0xDC:print('HYPOTHETICAL step',index,json.dumps(entry),flush=True)
            if ip==0xDC and index>0 and number(address(b))==0xEA:break
        assert closed,'the selected hypothesis failed to establish a closed cycle'
        assert forall_final is None or joined,'forall6 trajectory did not join the verified closed cycle'
        print('HYPOTHETICAL route',' '.join('%02X'%v for v in sequence),flush=True)

def six_payload_cycles(native):
    dc=next(e for e in native['events'] if e['ip']==0xDC)
    a=constant(dc);a.r[34]=q['N4'](4)
    for i,pos in enumerate(positions):a.r[pos]=BitVec('forall_raw_payload%d'%i,4)
    b=a;p=q['Solver']();p.set(timeout=10000)
    # The controller cycle and A truncation formulas were proved universally
    # above. Here only AF's header remains to be checked against the fixed
    # non-payload fields and successive shifted A shapes.
    for cycle in range(10):
        start=b
        for index,ip in enumerate((0xDC,0xDE,0xD4,0xDD,0xD4,0xAF,0xAE)):
            prove(p,address(b)==ip,'forall6 cycle%d command%d forced'%(cycle,index),False)
            # The seven commands' primary dataflow is insensitive to keys;
            # prove that locally against a common arbitrary serial stream,
            # then use quiet pins to avoid recursively expanding key terms.
            serial=State('forall6_cycle%d_step%d_serial'%(cycle,index)).m
            quiet=ex(b,ip,serial_inputs=serial)
            with_unknown_t=b.copy();with_unknown_t.t=q['BitVec']('forall6_cycle%d_step%d_t'%(cycle,index),1)
            with_unknown_t.l=q['BitVec']('forall6_cycle%d_step%d_l'%(cycle,index),1)
            arbitrary=ex(with_unknown_t,ip,*keys('forall6_cycle%d_step%d_keys'%(cycle,index)),serial_inputs=serial)
            prove(p,And(*[x==y for field in ('r','st') for x,y in zip(getattr(quiet,field),getattr(arbitrary,field))],
                        *[getattr(quiet,n)==getattr(arbitrary,n) for n in ('s','s1','carry')]),
                  'forall6 cycle%d %02X internal result independent of keys'%(cycle,ip),False)
            b=quiet
        p.push();p.add(b.r[34]!=4);outcome=p.check()
        if outcome==sat:
            print('COUNTEREXAMPLE forall6 writer control cycle',cycle,
                  'payload',[p.model().eval(a.r[pos],model_completion=True).as_long() for pos in positions],
                  'AF header',p.model().eval(b.r[34]),flush=True)
            p.pop();raise AssertionError('forall6 writer header/control cycle has a counterexample')
        assert outcome==unsat,p.reason_unknown();p.pop()
        print('PASS: forall six opaque raw tetras, cycle%d preserves B header4'%cycle,flush=True)
    print('PASS: ten repeated controller cycles for all six raw tetras; payload truncated by the second cycle',flush=True)
    substitutions=[(a.r[pos],q['N4'](dc['r'][pos])) for pos in positions]
    from z3 import substitute
    prove(p,And(*[value==substitute(value,*substitutions) for field in ('r','st') for value in getattr(b,field)],
                *[getattr(b,n)==substitute(getattr(b,n),*substitutions) for n in ('s','s1','carry')]),
          'after ten cycles primary data/control no longer depends on any of the six raw tetras')
    return b

if __name__=='__main__':
    local()
    m2_contracts()
    original_return_contracts()
    header_local_contracts()
    native=json.loads(subprocess.check_output(['node',str(root/'cache-writer-native.cjs'),'--proof-input'],text=True))
    forall_final=six_payload_cycles(native)
    assert forall_final is not None
    selected_hypothesis(native,forall_final)
