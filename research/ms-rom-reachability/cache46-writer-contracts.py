#!/usr/bin/env python3
"""Source-driven primary ROM writer contracts, all conditional, not native.

No emulator setters, ROM changes or claimed keyboard entry are used. The Z3
states and free return tags below are hypotheses. Future serial inputs and
physical key pins are arbitrary (a conservative superset of real execution).
"""
import runpy
from pathlib import Path
from z3 import And, BitVecVal, If, Or, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
ip=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]
A=lambda a:[a.r[3*i] for i in range(12)]
B=lambda a:[a.r[1+3*i] for i in range(14)]
raw=(0,3,9,12,18,21)

def eq(xs,ys): return And(*[x==y for x,y in zip(xs,ys)])
def same(a,b):
    return And(*[eq(getattr(a,n),getattr(b,n)) for n in ('r','st','m')],
               *[getattr(a,n)==getattr(b,n) for n in ('s','s1','l','t','carry')])
def prove(p,claim,label,log=True):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);outcome=p.check()
    assert outcome==unsat,(label,p.model() if outcome==sat else p.reason_unknown())
    p.pop()
    if log:print('PASS:',label,flush=True)
def step(a,code,label):
    out=[];b=ex(a,code,*keys(label),emitted_outputs=out)
    return b,out
def holds_ring(out,a):return eq(out,a.m)
def holds_others(out,a,written):
    return And(*[out[i]==a.m[i] for i in range(42) if i not in written])

def entry46_and_exit47():
    a=State('cache46_entry');p=base(a,0x46);b,out=step(a,0x46,'cache46_entry_keys')
    prove(p,And(ip(b)==0xE5,b.s1==8,eq(A(b),A(a)),eq(b.st[:36],a.st[:36]),
                stack(b)[0]==0x47,stack(b)[1]==stack(a)[0],stack(b)[2]==stack(a)[1],
                holds_ring(out,a)),
          '46 pushes47, sets S1=8, calls E5, holds A12/numeric ST and all outgoing ring')
    a=State('cache46_exit');p=base(a,0x47);b,out=step(a,0x47,'cache46_exit_keys')
    prove(p,And(ip(b)==0x49,eq(A(b),a.st[0:36:3]),
                *[And(b.st[j]==a.st[j+1],b.st[j+1]==a.st[j+2],b.st[j+2]==a.st[j])
                  for j in range(0,36,3)],
                eq(stack(b),stack(a)),holds_ring(out,a)),
          '47 replaces A12 by old ST first lane, rotates each numeric ST trio, exits49, no ring write')
    other=State('cache46_exit_other');paired=a.copy()
    for j in range(12):paired.r[3*j]=other.r[3*j]
    k=keys('cache46_exit_pair_keys');serial=State('cache46_exit_pair_serial').m
    oa=[];ob=[];aa=ex(a,0x47,*k,serial_inputs=serial,emitted_outputs=oa)
    bb=ex(paired,0x47,*k,serial_inputs=serial,emitted_outputs=ob)
    prove(p,And(same(aa,bb),eq(oa,ob)),
          '47 pair theorem: arbitrary differences in incoming A12 disappear from whole primary state and outgoing ring')

def loss_of_displaced_m2():
    for code in (0xC7,0xE7):
        a=State('cache46_loss_%02X'%code);p=base(a,code);p.add(stack(a)[0]==0x47)
        b=a.copy();other=State('cache46_loss_other_%02X'%code)
        for j in range(12):b.m[1+3*j]=other.m[1+3*j]
        out_a=[];out_b=[];k=keys('cache46_loss_keys_%02X'%code)
        serial=State('cache46_loss_serial_%02X'%code).m
        aa=ex(a,code,*k,serial_inputs=serial,emitted_outputs=out_a)
        bb=ex(b,code,*k,serial_inputs=serial,emitted_outputs=out_b)
        prove(p,And(ip(aa)==0x47,ip(bb)==0x47,eq(out_a,out_b),
                    eq(aa.st,bb.st),eq(aa.m,bb.m),
                    *[aa.r[i]==bb.r[i] for i in range(42) if i not in range(0,36,3)],
                    *[getattr(aa,n)==getattr(bb,n) for n in ('s','s1','l','t','carry')]),
              '%02X displaced M2 reaches ONLY A12, not B/C/ST/scalars or outgoing ring'%code)
        out_a=[];out_b=[];k=keys('cache46_loss47_keys_%02X'%code)
        serial=State('cache46_loss47_serial_%02X'%code).m
        aa=ex(aa,0x47,*k,serial_inputs=serial,emitted_outputs=out_a)
        bb=ex(bb,0x47,*k,serial_inputs=serial,emitted_outputs=out_b)
        prove(p,And(same(aa,bb),eq(out_a,out_b)),
              '%02X→47 loses all displaced numeric M2 information in primary and outgoing ring'%code)
    print('LOCAL LIMIT: prior independent backups / other-chip copies and alternative returns are not excluded.',flush=True)

def overwrite_without_read():
    for code,slots in ((0x32,range(1,28,3)),(0x34,range(28,35,3)),
                       (0xE9,range(1,36,3)),(0xBC,range(1,42,3))):
        a=State('cache46_overwrite_%02X'%code);p=base(a,code)
        b=a.copy();other=State('cache46_overwrite_other_%02X'%code)
        for j in slots:b.m[j]=other.m[j]
        k=keys('cache46_overwrite_keys_%02X'%code)
        serial=State('cache46_overwrite_serial_%02X'%code).m;oa=[];ob=[]
        aa=ex(a,code,*k,serial_inputs=serial,emitted_outputs=oa)
        bb=ex(b,code,*k,serial_inputs=serial,emitted_outputs=ob)
        prove(p,And(same(aa,bb),eq(oa,ob)),
              '%02X pair theorem: overwritten M2 input has no surviving primary/outgoing copy'%code)

def marker_wait():
    a=State('cache46_wait');p=base(a,0xE5);b,out=step(a,0xE5,'cache46_wait_keys')
    prove(p,And(ip(b)==If(a.m[22]==15,BitVecVal(0xE6,8),BitVecVal(0xE5,8)),
                b.s1==a.s1,eq(stack(b),stack(a)),eq(A(b),A(a)),
                eq(b.st[:36],a.st[:36]),holds_ring(out,a)),
          'E5 induction lemma: any finite marker wait holds A12/numeric ST/S1/return and writes nothing')

def direct_exchange_bypasses():
    for code,selector,writer in ((0xCD,7,0xC7),(0xE6,7,0xE7),(0xE8,None,0xE7)):
        a=State('cache46_direct_%02X'%code);p=base(a,code)
        if selector is not None:p.add(a.s1==selector)
        b,out=step(a,code,'cache46_direct_pre_keys_%02X'%code)
        prove(p,And(ip(b)==writer,eq(A(b),A(a)),eq(b.st[:36],a.st[:36]),
                    eq(stack(b),stack(a)),holds_ring(out,a)),
              '%02X%s→%02X bypasses46 and preserves A12/ST/old return, no write'%
              (code,'' if selector is None else '/S1=%X'%selector,writer))
        page=b.m;b,out=step(b,writer,'cache46_direct_writer_keys_%02X'%code)
        prove(p,And(ip(b)==stack(a)[0],eq([out[1+3*j] for j in range(12)],A(a)),
                    eq(A(b),page[1:36:3]),holds_others(out,StatePage(page),set(range(1,36,3)))),
              '%02X direct conditional exchange stores A12, reads displaced M2 into A, returns ORIGINAL top'%writer)

class StatePage:
    def __init__(self,m):self.m=m

def alternative_calls():
    # Original return A1 is a store call, unlike E0/A7's four-page lift.
    a=State('cache46_a1');p=base(a,0xA1);b=a
    for j,code in enumerate((0xA1,0xE5,0xE6,0xE9)):
        if code==0xE5:p.add(b.m[22]==15)
        prove(p,ip(b)==code,'A1 store command%02X forced'%code,False)
        before=b;b,out=step(b,code,'cache46_a1_keys%d'%j)
        if code==0xE9:
            prove(p,And(ip(b)==0xA2,eq(A(b),A(a)),
                        eq([out[1+3*i] for i in range(12)],A(a)),
                        holds_others(out,before,set(range(1,36,3)))),
                  'A1 E5* E6 E9→A2 is one exact A12 M2 store without46 or displaced-word read')
        else:prove(p,And(eq(A(b),A(a)),holds_ring(out,before)),
                   'A1 prefix holds all12 raw A tetras and writes nothing',False)
    a=State('cache46_e0_a7');p=base(a,0xE0);b=a;pages=[];writes=[]
    seq=(0xE0,0xA7,0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9)
    for j,code in enumerate(seq):
        if code==0xE5:p.add(b.m[22]==15)
        prove(p,ip(b)==code,'E0 fourpage command%02X forced'%code,False)
        before=b;pages.append(before.m);b,out=step(b,code,'cache46_e0_keys%d'%j)
        if code in (0xE7,0xA8):
            writes.append((j,out))
            prove(p,And(eq([out[1+3*i] for i in range(12)],A(before)),
                        eq(A(b),before.m[1:36:3]),
                        holds_others(out,before,set(range(1,36,3)))),
                  'E0 lift %02X is a12-tetra exchange'%code,False)
        else:prove(p,holds_ring(out,before),'E0 lift nonwriter%02X no ring write'%code,False)
    prove(p,And(ip(b)==0xE1,b.s1==0,
                eq([writes[0][1][1+3*i] for i in range(12)],A(a)),
                *[eq([writes[n][1][1+3*i] for i in range(12)],pages[writes[n-1][0]][1:36:3])
                  for n in range(1,4)],
                *[b.r[3*i]==pages[8][1+3*i] for i in range(10)],
                b.r[30]==a.r[32],b.r[33]==a.r[35]),
          'E0/A7 without46 writes four M2 pages, exitsE1; A9 retains displaced final page only first10 tetras')

def split_store32_and_clear00():
    a=State('cache46_store32');p=base(a,0x32);b,out=step(a,0x32,'cache46_store32_keys')
    prove(p,And(ip(b)==0x34,eq(A(b),A(a)),
                eq([out[1+3*i] for i in range(9)],A(a)[:9]),
                holds_others(out,a,set(range(1,28,3)))),
          '32→34 stores lower9 A into M2 including ALL6 raw cache tetras, holds A12; no oldM2 read')
    before=b;b,out=step(b,0x34,'cache46_store34_keys')
    prove(p,And(ip(b)==0xE2,eq(A(b),A(a)),
                eq([out[1+3*i] for i in range(9,12)],A(a)[9:]),
                holds_others(out,before,{28,31,34})),
          '34→E2 stores upper3 A into next M2 page, holds A12; split-store is NOT one aligned12-tetra word store')
    a=State('cache46_clear00');p=base(a,0);b,out=step(a,0,'cache46_clear00_keys')
    prove(p,And(ip(b)==0x32,*[v==15 for v in A(b)],holds_ring(out,a),
                eq([b.r[i] for i in raw],[a.r[i] for i in raw])==And(*[a.r[i]==15 for i in raw])),
          '00→32 sets ALL12 A to F; all6 raw cache fields survive iff all6 were already F')
    a=State('cache46_ret32');p=base(a,0x9A);p.add(stack(a)[0]==0x32)
    b,out=step(a,0x9A,'cache46_ret32_keys')
    prove(p,And(ip(b)==0x32,eq(A(b),A(a)),holds_ring(out,a)),
          '9A/top32 is a raw-A-preserving no-write entry32 hypothesis, not native tag construction')

def b_store_bc():
    a=State('cache46_bb');p=base(a,0xBB);b,out=step(a,0xBB,'cache46_bb_keys')
    prove(p,And(ip(b)==0xBC,b.s==a.r[1],eq(A(b),A(a)),holds_ring(out,a)),
          'BB→BC preloads first B tetra, shifts14 B, holds A12, no write')
    before=b;b,out=step(b,0xBC,'cache46_bc_keys')
    prove(p,And(ip(b)==stack(a)[0],eq(A(b),A(a)),
                eq([out[1+3*i] for i in range(14)],B(a)),
                holds_others(out,before,set(range(1,42,3)))),
          'BB BC stores aligned14 B including service37/40, holds A12; does NOT read oldM2')
    a=State('cache46_b3');p=base(a,0xB3);p.add(a.r[29]==12)
    b,out=step(a,0xB3,'cache46_b3_keys')
    prove(p,And(ip(b)==0xBC,b.s==7,eq(A(b),A(a)),eq(B(b),B(a)),holds_ring(out,a)),
          'B3/R29=C→BC holds A12/B14, preloads S=7 (not aligned BB store)')
    before=b;b,out=step(b,0xBC,'cache46_b3bc_keys')
    prove(p,And(ip(b)==stack(a)[0],out[1]==7,
                eq([out[1+3*i] for i in range(1,14)],B(a)[:13]),
                eq(A(b),A(a)),holds_others(out,before,set(range(1,42,3)))),
          'B3 BC stores (7,B0..B12) across14 M2 tetras; raw B6 preserved with one-tetra displacement')

def nonreturn46():
    a=State('cache46_41');p=base(a,0x41);b,out=step(a,0x41,'cache46_41_keys')
    prove(p,And((ip(b)==0x42)==Or(*[a.r[j]!=0 for j in range(0,24,3)]),
                eq(A(b),A(a)),holds_ring(out,a)),
          '41→42 iff at least one A0..A7 is nonzero; else43, holds A12')
    a=State('cache46_42');p=base(a,0x42);b,out=step(a,0x42,'cache46_42_keys')
    prove(p,And((ip(b)==0x46)==(a.r[21]!=0),eq(A(b),A(a)),
                stack(b)[0]==0x43,holds_ring(out,a)),
          '42→46 iff A7/R21!=0, pushes43 and holds A12; zero instead44')
    a=State('cache46_43');p=base(a,0x43);b,out=step(a,0x43,'cache46_43_keys')
    prove(p,And(ip(b)==0x46,*[v==0 for v in A(b)],holds_ring(out,a),
                eq([b.r[i] for i in raw],[a.r[i] for i in raw])==And(*[a.r[i]==0 for i in raw])),
          '43→46 zeroes ALL12 A; six raw fields held only if allsix already0 (including under41→43)')

if __name__=='__main__':
    entry46_and_exit47()
    loss_of_displaced_m2()
    overwrite_without_read()
    marker_wait()
    direct_exchange_bypasses()
    alternative_calls()
    split_store32_and_clear00()
    b_store_bc()
    nonreturn46()
    print('ALL CONDITIONAL ROM CONTRACTS PASS; no native reachability or full K2 claim.',flush=True)
