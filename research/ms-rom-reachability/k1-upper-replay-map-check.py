#!/usr/bin/env python3
"""Connected secondary-rotation maps with an additional visible marker.

This checks ROM geometry, not native keyboard reachability. Only the
selected geometries are covered; primary request writes remain separate.
"""
import runpy
from pathlib import Path
from z3 import And, sat, unsat

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'analyze_ms_pending_opcodes.py'))
State,ex,base,keys,addr=(q[n] for n in ('State','ex','base','keys','address'))
slots=q['slots']

def holds(p,claim):
    assert p.check()==sat, 'empty premise'
    p.push();p.add(~claim);r=p.check();p.pop()
    return r==unsat

def initial(start,extra):
    tag='upper_replay_'+start+'_'+''.join(extra)
    pages={n:State(tag+n).m for n in slots};original=dict(pages)
    a=State(tag);a.m=pages[start];p=base(a,0x6E)
    request=slots[(slots.index(start)+1)%15]
    p.add(a.r[29]==0,pages[request][31]==5,pages[request][34]==2,
          a.st[36]==10,a.st[39]==3,a.st[37]==10,a.st[40]==3)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker',*extra) else pages[n][22]!=15)
    return a,p,pages,original,tag

def block(a,p,pages,start,expected,expected_acks,tag):
    original=dict(pages)
    path=[];copies=[];acks=[]
    for step in range(100):
        p.push();ips=q['q']['possible_values'](addr(a),p,257);p.pop()
        assert len(ips)==1,('unforced',path,ips)
        ip=ips[0];here=slots[(slots.index(start)+step)%15];following=slots[(slots.index(start)+step+1)%15]
        path.append('%02X(%s)'%(ip,here));old=pages[here];out=[]
        a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        if ip in (0x3A,0x2A):
            dest,source=expected[len(copies)];assert here==dest,(path,expected)
            assert holds(p,And(*[out[1+3*j]==original[source][1+3*j] for j in range(12)],
                               *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37])),(here,source)
            copies.append((dest,source))
        elif ip==0x27:
            assert here==expected_acks[len(acks)],(path,expected_acks)
            assert holds(p,And(out[31]==15,*[out[j]==old[j] for j in range(42) if j!=31]))
            acks.append(here)
        else:assert holds(p,And(*[x==y for x,y in zip(out,old)])),path
        pages[here]=out
        if ip==0x39:
            assert holds(p,And(addr(a)==0x6E,a.r[29]==0));break
    else:raise AssertionError('no bounded return')
    assert copies==expected and acks==expected_acks
    print('PASS',{'start':start,'copies':copies,'ack':acks,'nextPage':following},flush=True)
    print('PATH',' -> '.join(path),flush=True)
    return a,following

def rotation(start,extra,expected,acks):
    a,p,pages,original,tag=initial(start,extra)
    block(a,p,pages,start,expected,acks,tag)

def connected_xv_repeat():
    a,p,pages,original,tag=initial('V',('X','V'))
    a,next_page=block(a,p,pages,'V',
        [('X','P8'),('Y','V'),('Z','W'),('T','P7')],['Y','control'],tag+'first')
    assert next_page=='V'
    assert holds(p,And(pages['V'][22]==15,pages['W'][31]==5,pages['W'][34]==2))
    for n in slots:
        assert holds(p,pages[n][22]==15 if n in ('marker','Y','V') else pages[n][22]!=15)
    # Continue the same symbolic state, ring and solver. No second fixture,
    # stack reset, assumed marker relocation, or injected second request.
    a,next_page=block(a,p,pages,next_page,
        [('U','P8'),('V','W'),('W','Q'),('Q','P7')],['Z','Z'],tag+'second')
    assert next_page=='P8'
    final_sources={'X':'P8','Y':'V','T':'P7','U':'P8','V':'W','W':'Q','Q':'P7'}
    for n in slots:
        for j in range(42):
            if j%3==1 and j<37 and n in final_sources:
                expected=original[final_sources[n]][j]
            elif n=='Z' and j%3==1 and j<37:
                expected=15 if j==31 else original['W'][j]
            elif n=='control' and j==31:expected=15
            else:expected=original[n][j]
            assert holds(p,pages[n][j]==expected),(n,j)
    for n in slots:
        assert holds(p,pages[n][22]==15 if n in ('marker','Y') else pages[n][22]!=15)
    # A strict canonical-word endpoint bound, NOT an information-theoretic
    # impossibility result or a result about concurrent primary writes.
    # Y contains F in a mantissa digit. Z/V start with request header 2,
    # whereas canonical exponent headers are 0 or 9.
    assert holds(p,And(pages['Y'][22]==15,pages['Z'][34]==2,pages['V'][34]==2))
    groups=[('X','U','P8'),('T','Q','P7')]
    for group in groups:
        assert holds(p,And(*[pages[n][1+3*j]==pages[group[0]][1+3*j]
                            for n in group[1:] for j in range(12)]))
    canonical_capacity=15+(len(slots)-2)-3-sum(len(g)-1 for g in groups)
    assert canonical_capacity==21
    print('PASS connected two-block repeat: V/W stays pending after block 1; '
          'block 2 removes V. Exact whole-ring endpoint verified.',flush=True)
    print('LIMIT: this isolated secondary endpoint can hold at most 21 distinct '
          'canonical input words in the usual 23 stored + 5 visible slots. '
          'Concurrent primary writes, encoding and other storage are outside this bound.',flush=True)

if __name__=='__main__':
    rotation('V',('V',),[('P7','P8'),('P8','P9'),('P9','P10'),('P10','P7')],['W','W'])
    rotation('V',('Z','T','V'),[('V','P8'),('W','Q'),('Q','P7'),('P7','P7')],['T','T'])
    rotation('T',('T','V'),[('W','Q'),('Q','P7'),('P7','P8'),('P8','W')],['U','U'])
    rotation('V',('Y','V'),[('U','P8'),('V','W'),('W','Q'),('Q','P7')],['Z','Z'])
    rotation('V',('X','V'),[('X','P8'),('Y','V'),('Z','W'),('T','P7')],['Y','control'])
    rotation('U',('X','U'),[('X','P7'),('Y','V'),('Z','W'),('T','Q')],['Y','control'])
    connected_xv_repeat()
    print('LIMIT: no keyboard producer, inter-chip scheduling, or preserving full K1 is implied.',flush=True)
