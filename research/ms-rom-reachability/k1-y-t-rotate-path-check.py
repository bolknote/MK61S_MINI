#!/usr/bin/env python3
"""Connected Y/T rotate request and its real/Z continuation geometry.

Local, conditional symbolic ROM proofs, not native reachability claims.
Native experiments neither import nor modify the machine's state.
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat

root=Path(__file__).resolve().parent
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']


def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check()
    assert answer==unsat,(label,p.model() if answer==sat else answer)
    p.pop()


def secondary():
    q=runpy.run_path(str(root/'analyze_ms_pending_opcodes.py'))
    State,ex,base,keys,address=(q[n] for n in ('State','ex','base','keys','address'))
    pages={n:State('yt_rotate_secondary_'+n).m for n in slots};original=dict(pages)
    a=State('yt_rotate_secondary');a.m=pages['Y'];p=base(a,0x6E)
    p.add(a.r[29]==0,pages['Z'][34]==2,pages['Z'][31]==5,
          a.st[36]==10,a.st[39]==3,a.st[37]==10,a.st[40]==3)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','Y','T') else pages[n][22]!=15)
    expected=[('X','V'),('Y','Z'),('Z','T'),('T','U')];route=[];writes=[]
    for step in range(100):
        p.push();ips=q['q']['possible_values'](address(a),p,257);p.pop()
        assert len(ips)==1,('unforced',route,ips)
        ip=ips[0];here=slots[(4+step)%15];nxt=slots[(5+step)%15]
        route.append('%02X(%s)'%(ip,here));old=pages[here];out=[]
        a=ex(a,ip,*keys('yt_rotate_secondary_'+str(step)),serial_inputs=pages[nxt],emitted_outputs=out)
        if ip in (0x3A,0x2A):
            target,source=expected[len(writes)];assert here==target
            prove(p,And(*[out[1+3*j]==original[source][1+3*j] for j in range(12)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact '+source+' -> '+target)
            writes.append((target,source))
        elif ip==0x27:
            assert here=='control'
            prove(p,And(out[31]==15,*[out[j]==old[j] for j in range(42) if j!=31]),'only control ACK')
        else:prove(p,And(*[x==y for x,y in zip(out,old)]),'no other secondary write '+route[-1])
        pages[here]=out
        if ip==0x39:
            prove(p,And(address(a)==0x6E,a.r[29]==0),'quiet return')
            break
    else:raise AssertionError('unclosed secondary path')
    assert writes==expected
    print('PASS secondary25:', ' -> '.join(route),flush=True)
    print('RESULT:',writes,'; no Ms write, Z marker replaces Y/T.',flush=True)


def continuation(start,code):
    """Map selected readers after real/Z, up to the second (formatter) EE."""
    q=runpy.run_path(str(root/'ik1302_symbolic.py'))
    State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
    address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
    tag='yt_rotate_follow_%02x_'%code+start
    pages={n:State(tag+n).m for n in slots};original=dict(pages)
    a=State(tag);a.m=pages[start];p=base(a,0x9C)
    p.add(a.r[30]==code%16,a.r[33]==code//16,
          If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7)))
    if code in (0x0E,0x0F):p.add(a.s1==code)
    if code==0x54:
        p.add(a.r[23]==0,a.r[26]==0,a.r[29]==4)
        for n in ('control','T'):
            p.add(If(pages[n][31]==15,UGE(pages[n][34],1),UGE(pages[n][34],7)))
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','Z') else pages[n][22]!=15)
    route=[];reads=[];writes=[];carried=None
    for step in range(120):
        p.push();ips=q['possible_values'](address(a),p,257);p.pop()
        assert len(ips)==1,('unforced',route,ips)
        ip=ips[0];here=slots[(slots.index(start)+step)%15];nxt=slots[(slots.index(start)+step+1)%15]
        route.append('%02X(%s)'%(ip,here));old=pages[here]
        if ip==0xEE:
            reads.append(here)
            if len(reads)==2:
                prove(p,And(a.st[36]==3,a.st[39]==14),'formatter return E3')
                first=('U' if start=='control' else 'X1') if code==0x0F else ('V' if start=='control' else 'X')
                assert reads==[first,'X']
                assert writes==([] if code==0x54 else ['X','Y','Z','T'])
                print('PASS follow %02X'%code,start,'reads',reads,'writes',writes,flush=True)
                print('PATH',' -> '.join(route),flush=True)
                return {'reads':reads,'writes':writes}
            carried=[old[1+3*j] for j in range(12)]
        out=[];a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[nxt],emitted_outputs=out)
        if ip==0xD6:carried=[old[3*j] for j in range(12)]
        if ip in (0xE7,0xA8):
            assert carried is not None
            prove(p,And(*[out[1+3*j]==carried[j] for j in range(12)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact push '+here)
            carried=[old[1+3*j] for j in range(12)];writes.append(here)
        else:prove(p,And(*[x==y for x,y in zip(out,old)]),'no extra write '+route[-1])
        pages[here]=out
    raise AssertionError('no bounded late reader')


def next_request(start,code):
    """Both scanner origins for a secondary request with only real/Z."""
    q=runpy.run_path(str(root/'ik1302_symbolic.py'))
    State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
    address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
    tag='z_request_%02x_'%code+start
    pages={n:State(tag+n).m for n in slots};original=dict(pages)
    a=State(tag);a.m=pages[start];p=base(a,0x9C)
    p.add(a.r[30]==code%16,a.r[33]==code//16,
          If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7)))
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','Z') else pages[n][22]!=15)
    source,target,request=('V','X1','T') if start=='control' else ('X','U','control')
    route=[];reads=[];writes=[]
    for step in range(80):
        p.push();ips=q['possible_values'](address(a),p,257);p.pop()
        assert len(ips)==1,('unforced request',route,ips)
        ip=ips[0];here=slots[(slots.index(start)+step)%15];nxt=slots[(slots.index(start)+step+1)%15]
        route.append('%02X(%s)'%(ip,here));old=pages[here];out=[]
        if ip==0xEE:reads.append(here)
        a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[nxt],emitted_outputs=out)
        if ip==0xE9:
            assert here==target
            prove(p,And(*[out[1+3*j]==original[source][1+3*j] for j in range(12)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact reserve '+source+' -> '+target)
            writes.append(('E9',here))
        elif ip==0xA3:
            assert here==request
            prove(p,And(out[28]==original[source][28],out[31]==code%16,out[34]==code//16,
                        *[out[j]==old[j] for j in range(42) if j not in (28,31,34)],address(a)==0xD3),
                  'only request header '+request)
            writes.append(('A3',here))
        else:prove(p,And(*[x==y for x,y in zip(out,old)]),'no extra primary write '+route[-1])
        pages[here]=out
        if ip==0xA3:break
    else:raise AssertionError('no bounded request')
    assert reads==[source] and writes==[('E9',target),('A3',request)]
    print('PASS next request %02X'%code,start,{'source':source,'reserve':target,'request':request},flush=True)
    print('PATH',' -> '.join(route),flush=True)


if __name__=='__main__':
    runpy.run_path(str(root/'k1-y-t-swap-v-path-check.py'))['primary'](0x25)
    secondary()
    check=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
    # The primary chip reads the old X=v immediately BEFORE the secondary
    # writes X=u. Z has become the sole extra marker before the late scan.
    check(9,0,source_slot='X',marker_slots=('marker','Z'),target_by_class=['V']*5+['X']*4)
    check(0,0,True,source_slot='X',marker_slots=('marker','Z'),target_by_class=['V']*5+['X']*4)
    for code in (0x0E,0x0F,0x60,0x54):
        for start in ('control','T'):continuation(start,code)
    for code in (0x28,0x3A,0x35):
        for start in ('control','T'):next_request(start,code)
    print('LIMIT: local accepted paths and fixed formatter class only; no universal K1 or native scheduling claim.',flush=True)
