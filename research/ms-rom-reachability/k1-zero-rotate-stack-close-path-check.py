#!/usr/bin/env python3
"""Local ROM contracts for closing the guarded upper rotation.

These are conditional paths, not a proof of native keyboard timing or of
the full numeric domain. The native audit must establish their premises.
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat

root=Path(__file__).resolve().parent
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']


def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);result=p.check();p.pop()
    assert result==unsat,label


def secondary():
    q=runpy.run_path(str(root/'analyze_ms_pending_opcodes.py'))
    State,ex,base,keys,address=(q[n] for n in ('State','ex','base','keys','address'))
    pages={n:State('zt_visible_swap_'+n).m for n in slots};original=dict(pages)
    a=State('zt_visible_swap');a.m=pages['marker'];p=base(a,0x6E)
    p.add(a.r[29]==0,pages['control'][34]==1,pages['control'][31]==4)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','Z','T') else pages[n][22]!=15)
    route=[];writes=[];acks=[]
    for step in range(80):
        p.push();ips=q['q']['possible_values'](address(a),p,257);p.pop()
        assert len(ips)==1,('unforced',route,ips)
        ip=ips[0];here=slots[step%15];nxt=slots[(step+1)%15]
        route.append('%02X(%s)'%(ip,here));old=pages[here];out=[]
        a=ex(a,ip,*keys('zt_swap_'+str(step)),serial_inputs=pages[nxt],emitted_outputs=out)
        if ip in (0x4E,0x2A):
            target,source=('X','Y') if ip==0x4E else ('Y','X')
            assert here==target
            prove(p,And(*[out[1+3*j]==original[source][1+3*j] for j in range(12)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact '+source+' -> '+target)
            writes.append((target,source))
        elif ip==0x27:
            assert here=='control'
            prove(p,And(out[31]==15,*[out[j]==old[j] for j in range(42) if j!=31]),'only control ACK')
            acks.append(here)
        else:prove(p,And(*[x==y for x,y in zip(out,old)]),'no extra write '+route[-1])
        pages[here]=out
        if ip==0x39:
            prove(p,And(address(a)==0x6E,a.r[29]==0),'quiet return');break
    else:raise AssertionError('unclosed secondary path')
    assert writes==[('X','Y'),('Y','X')]
    print('PASS secondary visible swap:',writes,'ACK',acks,flush=True)
    print('PATH',' -> '.join(route),flush=True)


def reader(start,code,markers):
    q=runpy.run_path(str(root/'ik1302_symbolic.py'))
    State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
    address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
    tag='zt_reader_%02X_%s_%s_'%(code,start,'_'.join(markers))
    pages={n:State(tag+n).m for n in slots};original=dict(pages)
    a=State(tag);a.m=pages[start];p=base(a,0x9C)
    p.add(a.r[30]==code%16,a.r[33]==code//16,
          If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7)))
    if code==0x54:
        p.add(a.r[23]==0,a.r[26]==0,a.r[29]==4)
        # The connected NOP routes below revisit only control or T. U is
        # already a canonical (and rejected) data header after the swap.
        for n in ('control','T'):
            p.add(If(pages[n][31]==15,UGE(pages[n][34],1),UGE(pages[n][34],7)))
    if code==0x61:p.add(pages['V'][21]!=15)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker',*markers) else pages[n][22]!=15)
    route=[];reads=[];writes=[];loads=[];carried=None
    for step in range(120):
        p.push();ips=q['possible_values'](address(a),p,257);p.pop()
        assert len(ips)==1,('unforced',route,ips)
        ip=ips[0];here=slots[(slots.index(start)+step)%15];nxt=slots[(slots.index(start)+step+1)%15]
        route.append('%02X(%s)'%(ip,here));old=pages[here]
        if ip==0xEE:
            reads.append(here)
            if len(reads)==2:
                assert here=='X'
                prove(p,And(a.st[36]==3,a.st[39]==14),'formatter return E3')
                assert writes==([] if code==0x54 else ['X','Y','Z','T'])
                assert loads==([] if code==0x54 else ['V'])
                for n in slots:
                    if n not in writes:prove(p,And(*[pages[n][j]==original[n][j] for j in range(42)]),'untouched '+n)
                print('PASS reader:',{'code':'%02X'%code,'accepted':start,'markers':markers,
                      'reads':reads,'loads':loads,'push':writes},flush=True)
                print('PATH',' -> '.join(route),flush=True)
                return
            carried=[old[1+3*j] for j in range(12)]
        out=[];a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[nxt],emitted_outputs=out)
        if ip==0xD6:
            assert here=='V';loads.append(here);carried=[old[3*j] for j in range(12)]
        if ip in (0xE7,0xA8):
            assert carried is not None
            prove(p,And(*[out[1+3*j]==carried[j] for j in range(12)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact push '+here)
            carried=[old[1+3*j] for j in range(12)];writes.append(here)
        else:prove(p,And(*[x==y for x,y in zip(out,old)]),'no extra write '+route[-1])
        pages[here]=out
    raise AssertionError('no bounded formatter read')


if __name__=='__main__':
    producer=runpy.run_path(str(root/'k1-u-reserve-control-mask-check.py'))['producer']
    producer('U',0x10,('T',),'X','V','control')
    producer('T',0x14,('Z','T'),'X','U','control')
    secondary()
    for start in ('control','T','U'):reader(start,0x54,('Z','T'))
    for markers in (('Z','T'),('T',)):
        for start in (('control','T','U') if len(markers)==2 else ('control','U')):
            reader(start,0x61,markers)
    f=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
    f(0,7,True,True,source_slot='X',marker_slots=('marker','T'),target_by_class=['W']*6+['X']*3)
    f(0,0,True,source_slot='X',marker_slots=('marker','Z','T'),target_by_class=['V']*5+['W']+['X']*3)
    f(9,0,source_slot='X',marker_slots=('marker','Z','T'),target_by_class=['V']*5+['W']+['X']*3)
    f(0,5,True,source_slot='X',marker_slots=('marker','T'),target_by_class=['W']*6+['X']*3)
    f(0,5,True,source_slot='X',marker_slots=('marker',),target_by_class=['X']*9)
    print('LIMIT: local blocks only; native timing, the lifting addition, input coverage and clean exit require separate checks.',flush=True)
