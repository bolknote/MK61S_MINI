#!/usr/bin/env python3
"""AB bypass: exact decoder, indirect tail cuts and native primary replays.

Original ROM/reference only. Arbitrary-state SAT is not a keyboard recipe.
Shortest cached graph words omit waits: UNSAT excludes precisely that expanded
word sequence, NOT all loop counts or all paths in the graph. Native replays
below deliberately retain EVERY wait and every conditional instruction.
"""
from collections import deque
import gzip
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And,Or,UGE,ZeroExt,sat,unsat

root=Path(__file__).resolve().parent
w=runpy.run_path(str(root/'cache-writer-contract.py'));q=w['q']
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
ip,stack,prove,constant,number=(w[n] for n in ('address','stack','prove','constant','number'))


def decoder_and_normalizers():
    a=State('st24_ab_bypass');p=base(a,0xAB);p.add(UGE(a.r[35],7));b=a
    for j,code in enumerate((0xAB,0xA5,0x1F)):
        prove(p,ip(b)==code,'AB bypass word',False)
        b=ex(b,code,*keys('st24_bypass_keys'+str(j)))
    prove(p,And(ip(b)==q['BitVecVal'](0x10,8)+ZeroExt(4,a.r[35]),
                b.r[26]==15,b.r[32]==0),
          'AB→A5→1F preservesF but dispatches ONLY to17..1F by originalAB.R35')
    for typecode,tail,kind in ((13,(),0),(11,(0x1B,),1),
                               (8,(0x18,0x1B),2),(10,(0x1A,0x18,0x1B),3)):
        a=State('st24_typed_constructor'+str(typecode));p=base(a,0xAB)
        p.add(a.r[35]==typecode);b=a
        for j,code in enumerate((0xAB,0xA5,0x1F)+tail):
            prove(p,ip(b)==code,'typed constructor word',False)
            b=ex(b,code,*keys('st24_constructor_keys%d_%d'%(typecode,j)))
        prove(p,And(ip(b)==0x1D,b.r[32]==kind,b.r[26]==15),
              'Exact ordinary indirect type%X constructor reaches1D with R32=%d / R26=F'%(typecode,kind))
    a=State('st24_resolution_gate28');p=base(a,0x28)
    b=ex(a,0x28,*keys('st24_resolution_gate28keys'))
    prove(p,And(b.s1==14,b.r[26]==a.r[26],
                ip(b)==q['If'](a.r[26]==0,q['BitVecVal'](0x2A,8),q['BitVecVal'](0x7E,8))),
          '28 always makesS1=E; nonzeroR26 goes7E, zero goes2A')
    a=State('st24_kind_dispatch');p=base(a,0x7E)
    b=ex(a,0x7E,*keys('st24_kind_dispatch_keys'))
    prove(p,And(ip(b)==q['BitVecVal'](0x70,8)+ZeroExt(4,a.r[35]),
                b.s1==a.s1,b.r[26]==a.r[26]),
          '7E dispatches EXACTLY to70..7F by kind0..F; holdsS1/R26')
    for code in (0x70,0x71):
        a=State('st24_normalizer_%02X'%code);p=base(a,code)
        b=ex(a,code,*keys('st24_normalizer_keys_%02X'%code))
        prove(p,And(b.r[33]==4,b.r[35]==a.s1+8,b.r[26]==a.r[26]),
              '%02X universally builds ordinary header4 / operand(S1+8) mod16, holdsR26'%code)


def tail_cuts():
    routes={0:(0x26,0x28,0x7E,0x70,0xAB,0xAD),1:(0x26,0x28,0x7E,0x71,0xAA),
            2:(0x7E,0x72,0x74,0x86),4:(0x7E,0x74,0x86),6:(0x7E,0x76)}
    destinations={0:0xA6,1:0xE5,2:0xD3,4:0xD3,6:0xE2}
    for kind,sequence in routes.items():
        a=State('st24_kind_tail'+str(kind));p=base(a,sequence[0]);p.add(a.r[35]==kind)
        if kind<=1:p.add(a.r[26]!=0)
        b=a
        for j,code in enumerate(sequence):
            prove(p,ip(b)==code,'kind%d step%d'%(kind,j),False)
            b=ex(b,code,*keys('st24_kind_tailkeys%d_%d'%(kind,j)))
        prove(p,And(ip(b)==destinations[kind],
                    b.r[26]==(a.r[26] if kind==1 else 0)),
              'Exact kind%d tail %s→%02X: %s'%(kind,
                 ' '.join('%02X'%c for c in sequence),destinations[kind],
                 'F held, but AA/header4 goesE5 NOT AC' if kind==1 else 'R26 forcedzero'))
    a=State('st24_call_tail');p=base(a,0x73)
    b=ex(a,0x73,*keys('st24_call_tailkeys0'));p.add(ip(b)==0x6F)
    for j,code in enumerate((0x6F,0x62,0x74,0x86)):
        prove(p,ip(b)==code,'call6F branch step'+str(j),False)
        b=ex(b,code,*keys('st24_call_tailkeys'+str(j+1)))
    prove(p,And(ip(b)==0xD3,b.r[26]==0),
          'ANY 73→6F branch returns through original tag74 and 86, forcingR26=0')
    a=State('st24_abort_condition');p=base(a,0x27);p.add(UGE(a.r[26],2))
    b=a
    for j,code in enumerate((0x27,0x29)):
        prove(p,ip(b)==code,'skipped-condition tail',False)
        b=ex(b,code,*keys('st24_abort_conditionkeys'+str(j)))
    prove(p,And(ip(b)==0xD3,b.r[26]==0),
          'ANY skipped27 condition with R26>=2 (includingD/E/F) forces29 and zero')
    a=State('st24_nonordinary_kind7');p=base(a,0x26);p.add(a.r[35]==7,a.r[26]!=0)
    b=a
    for j,code in enumerate((0x26,0x28,0x7E,0x77,0x6D)):
        prove(p,ip(b)==code,'kind7 preserves positive flag',False)
        b=ex(b,code,*keys('st24_nonordinary_kind7keys'+str(j)))
    prove(p,And(ip(b)==0x60,b.r[26]==a.r[26],b.r[32]==a.r[32],b.r[38]==a.r[38]),
          'CONDITIONAL nonordinary kind7 goes26 28 7E 77 6D→60, holdsR26/R32/R38')
    print('OPEN: kind5→75, kind7→77, the other73→75 branch and changed '
          'preparations are NOT excluded. Native kind7 / paired C8 signature '
          'have not been constructed.',flush=True)


def shortest_graph_filters():
    audit=runpy.run_path(str(root/'k1-formatter-entry-audit.py'))
    data=json.loads(gzip.decompress(audit['cache_path'].read_bytes()))
    meta=data['metadata'];assert meta['sourceSha256']==audit['fingerprints']()
    assert meta['argv']==audit['argv'] and meta['complete']
    assert meta['pending']==0 and meta['terminal'] is None
    states,edges=data['states'],data['successors']
    starts={j:i for i,a in enumerate(states) if a[0]==0xAB
            for j in edges[i] if states[j][0]==0xA5}
    parents={j:None for j in starts};pending=deque(starts)
    while pending:
        i=pending.popleft()
        for j in edges[i]:
            if 15 in states[j][7] and j not in parents:
                parents[j]=i;pending.append(j)
    targets=[i for i in parents if states[i][0]==0xAC]
    assert (len(starts),len(parents),len(targets))==(30,5231,20)
    paths=[]
    for target in targets:
        path=[];i=target
        while i is not None:path.append(i);i=parents[i]
        path.reverse();path.insert(0,starts[path[0]]);words=[]
        for i in path:
            code=states[i][0];words.append(code)
            if code==0x93:words.append(0x94)
            elif code==0x12:words.append(0xC6)
        paths.append((len(words),target,words))
    filt=runpy.run_path(str(root/'verify_c8_recovery_candidate.py'),init_globals={'transport':{'q':q}})
    failures=[]
    for _,target,words in sorted(paths)[:5]:
        result=filt['verify_sequence'](words)
        assert result['result']==unsat
        failures.append({'target':target,'length':len(words),'firstFailure':result['index']})
    print('PASS five shortest cached WORD-SEQUENCE filters:',json.dumps(failures),flush=True)
    print('SCOPE: this F-continuous graph cut is not a reset-to-AC proof. '
          'Failed shortest words do NOT exclude extra waits or longer routes; '
          'the native prefix below really DOES execute21→23.',flush=True)


def alternate_call_frontier():
    a=State('st24_call75_frontier');p=base(a,0x73)
    b=ex(a,0x73,*keys('st24_call75_frontierkeys0'))
    prove(p,(ip(b)==0x75)==And(a.r[31]==0,a.r[34]==0),
          'Other73→75 branch occurs IFF the original PC is00')
    p.add(ip(b)==0x75)
    prove(p,stack(b)[0]==0x74,'73/75 keeps tag74',False)
    b=ex(b,0x75,*keys('st24_call75_frontierkeys1'))
    prove(p,And(ip(b)==0xCA,stack(b)[0]==0x76),
          '75 pushes tag76 and entersCA')
    b=ex(b,0xCA,*keys('st24_call75_frontierkeys2'))
    prove(p,And(Or(ip(b)==0xDA,ip(b)==0xDB),b.r[26]==15,stack(b)[0]==0x76),
          'CA recreatesF and choosesDA/DB with tag76 held')
    prove(p,(ip(b)==0xDA)==(a.r[33]==15),
          'Other call branch reachesDA IFF original73.R33=F; sign of a numeric pointer is not this field')
    for code in (0xDA,0xDB):
        p.push();p.add(ip(b)==code)
        c=ex(b,code,*keys('st24_call75_frontierkeys_%02X'%code))
        prove(p,And(ip(c)==0xDC,c.r[26]==15,stack(c)[0]==0x76),
              'CONDITIONAL 73 75 CA %02X→DC frontier holdsF/tag76'%code)
        p.push();p.add(a.r[35]==3,a.s1==14)
        headers=(3,4) if code==0xDA else (2,3)
        prove(p,Or(*[c.r[34]==v for v in headers]),
              'Typed call/S1=E branch%02X permits ONLY DC headers%s'%(code,headers))
        if code==0xDA:
            p.add(c.r[34]==4);assert p.check()==sat
            d=c
            for j,step in enumerate((0xDC,0xDE)):
                prove(p,ip(d)==step,'conditional call/D4 prefix',False)
                d=ex(d,step,*keys('st24_call75_d4prefix'+str(j)))
            prove(p,And(ip(d)==0xD4,d.r[26]==0,stack(d)[0]==0xDD,
                        stack(d)[1]==0x76),
                  'CONDITIONAL call/DA/header4 enters D4 with tagsDD/76 and R26=0; NOT native cache entry')
        p.pop()
        p.pop()
    print('FRONTIER LIMIT: PC00 route does NOT prove raw cache preservation, '
          'header4, a native cache-export D4 or an AC/C8 signature.',flush=True)
    native_cases=json.loads(subprocess.check_output(
        ['node',str(root/'cache-st24-call00-frontier.cjs'),'--proof-input'],text=True))
    for native in native_cases:
        events=native['frontier'];b=constant(events[0])
        for j,event in enumerate(events[:-1]):
            following=events[j+1];assert number(ip(b))==event['ip']
            b=ex(b,event['ip'],event['keyX'],event['keyY'],
                 serial_inputs=[q['N4'](v) for v in following['m']])
            for group in ('r','st','m'):
                assert [number(v) for v in getattr(b,group)]==following[group]
            for n in ('s','s1','l','t','carry'):
                assert number(getattr(b,n))==following[n]
        assert number(ip(b))==0xDC and number(b.r[26])==15 and number(b.r[34])==3
        assert [e['address'] for e in native['report']['programChanges']]==[38,39]
        print('PASS native PC00 frontier73/75/CA/DB/DC pointer',native['report']['pointer'],
              ': every primary field matches; header3, not4; program damage38/39 explicit.',flush=True)


def exact_native_replays():
    cases=json.loads(subprocess.check_output(
        ['node',str(root/'cache-st24-indirect-tail.cjs'),'--proof-input'],text=True))
    for case in cases:
        es=case['proofEvents'];assert es[0]['ip']==0xAB and es[-1]['ip']==0xAC
        b=constant(es[0]);pairs=set()
        for j,event in enumerate(es[:-1]):
            following=es[j+1];pairs.add((event['ip'],following['ip']))
            assert number(ip(b))==event['ip']
            b=ex(b,event['ip'],event['keyX'],event['keyY'],
                 serial_inputs=[q['N4'](v) for v in following['m']])
            for group in ('r','st','m'):
                assert [number(v) for v in getattr(b,group)]==following[group],(j,group)
            for n in ('s','s1','l','t','carry'):
                assert number(getattr(b,n))==following[n],(j,n)
        if case['report'].get('skippedCondition'):
            assert (0x27,0x29) in pairs
        else:assert (0x21,0x23) in pairs,'keep the real wait-expanded resolution, not a false short substitute'
        assert number(b.r[26])==0
        print('PASS ALL native primary fields / EVERY macro including waits:',
              case['report']['operation'],len(es)-1,'steps; AC.R26=0.',flush=True)
    print('LIMIT: no native ST24 D/E/F preparation or cache-export D4. '
          'These fixed controls do not exclude other preparations.',flush=True)


if __name__=='__main__':
    decoder_and_normalizers()
    tail_cuts()
    alternate_call_frontier()
    shortest_graph_filters()
    exact_native_replays()
