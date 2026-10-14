#!/usr/bin/env python3
"""Conservative control-stack/vector analysis; a path is only a candidate."""
import runpy
import argparse
from pathlib import Path
from collections import deque
from z3 import And, BitVecVal, Or, Solver, UGE, ULE, ZeroExt, sat, unsat

def expression_vars(expressions):
    # Z3 expressions are DAGs: walking each shared subexpression once is vital.
    seen, variables, pending = set(), set(), list(expressions)
    while pending:
        expr = pending.pop()
        ident = expr.get_id()
        if ident in seen:
            continue
        seen.add(ident)
        children = expr.children()
        if not children:
            variables.add(str(expr))
        else:
            pending.extend(children)
    return variables

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
def byte(lo, hi):
    return ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)

parser=argparse.ArgumentParser()
parser.add_argument('--target', choices=['a3','cd','ms','non60','ddentry','c7','type7','mode07'], default='a3',
                    help='c7 permits any number of C8 executions while searching for C7')
parser.add_argument('--limit', type=int, default=150000)
parser.add_argument('--r38', action='store_true', help='track R38, R26, and R38-R35')
parser.add_argument('--physical-key-rows', action='store_true',
                    help='restrict active row signals to 2..11; still permit arbitrary per-tick changes')
parser.add_argument('--full-stack-cache', action='store_true', help='disable stack dependency cache reduction')
parser.add_argument('--types', action='store_true', help='track the R32/R35 command-type pair')
parser.add_argument('--r2', action='store_true', help='track the R2 mode discriminator independently of --types')
parser.add_argument('--r5', action='store_true', help='track the saved R2 value exchanged with R5 by the keyboard prefix')
parser.add_argument('--r33', action='store_true', help='track the opcode high nibble used by AA and the 93/94 vector builder')
parser.add_argument('--last-dd', action='store_true',
                    help='for mode07, require DD to be the last non-preserving R38 assignment')
parser.add_argument('--first-entry-lemmas', action='store_true',
                    help='apply separately proved R41/E6 and A2/A3 source-lifetime invariants')
parser.add_argument('--include-ms', action='store_true',
                    help='also admit C7/C8 in auxiliary analyses such as type7; no first-entry lemmas')
parser.add_argument('--report-entry', type=lambda text:int(text,16), action='append', default=[],
                    help='report joined domains at a hexadecimal ROM address after the run')
parser.add_argument('--check-1f-invariants', action='store_true',
                    help='assert selector bounds that exclude 68->A5 before first C7/C8')
parser.add_argument('--check-dd-invariants', action='store_true',
                    help='assert DD helper selectors and A2/A3 selector-vector correlations')
parser.add_argument('--check-c8-invariants', action='store_true',
                    help='assert continuation invariants in a completed C7 analysis allowing C8')
args=parser.parse_args()
if args.target=='ddentry' and not args.r38:
    parser.error('--target ddentry requires --r38')
if args.target=='type7' and not (args.r38 and args.types):
    parser.error('--target type7 requires --r38 --types')
if args.target=='mode07' and not (args.r38 and args.r2):
    parser.error('--target mode07 requires --r38 --r2')
if args.last_dd and args.target != 'mode07':
    parser.error('--last-dd is a history refinement of --target mode07')
if args.first_entry_lemmas and (args.target=='c7' or args.include_ms):
    parser.error('first-entry lemmas are not enabled for analyses continuing after C8')
TYPE_FIELDS = ((32,35) + ((2,) if args.r2 else ()) + ((5,) if args.r5 else ())
               + ((33,) if args.r33 else ()))
key_constraints = {}


def command_keys(label, ip):
    xs, ys = keys(label)
    if args.physical_key_rows:
        key_constraints.setdefault(ip, []).extend(
            Or(y == 0, And(UGE(x, 2), ULE(x, 11))) for x,y in zip(xs,ys))
    return xs, ys


def state_solver(a, ip):
    """Input constraints backed by independent proofs, never candidate paths.

    check_85_paths.py proves the Boolean R41 invariant and E6's only entries
    E5/self, with S=R41+C preserved by the self-loop.
    check_type_entry.py covers every A2/A3 predecessor and the complete A1
    return-tag lifetime. Vectors outside 90/D3 must come through AD, which
    supplies constructor 2/3 and clears R26. Both proofs use the completed
    unrefined reset vector fixpoint, not the result being sought here.
    """
    p = base(a, ip)
    p.add(*key_constraints.get(ip, []))
    if args.first_entry_lemmas:
        p.add(Or(a.r[41] == 0, a.r[41] == 15))
        if ip == 0xE6:
            p.add(a.s == a.r[41]+12)
        if ip in (0xA2,0xA3):
            av = byte(a.r[37],a.r[40])
            constructor = a.r[32] == 2 if ip == 0xA2 else Or(a.r[32] == 2,a.r[32] == 3)
            p.add(Or(av == 0x90,av == 0xD3,And(constructor,a.r[26] == 0)))
    return p

templates = {}
for ip in range(256):
    a = State(f'abstract_{ip}')
    b = execute(a, ip, *command_keys(f'keys_{ip}', ip))
    if ip == 0x93:
        s=base(a,ip);s.add(byte(b.r[36],b.r[39])!=0x94)
        assert s.check()==unsat
        b=execute(b,0x94,*command_keys('keys_93_then_94', ip))
    if args.r38 and ip==0x12:
        s=base(a,ip);s.add(byte(b.r[36],b.r[39])!=0xC6)
        assert s.check()==unsat
        b=execute(b,0xC6,*command_keys('keys_12_then_C6', ip))
    av, bv = byte(a.r[37], a.r[40]), byte(b.r[37], b.r[40])
    old = [byte(a.st[36+i], a.st[39+i]) for i in range(3)]
    new = [byte(b.st[36+i], b.st[39+i]) for i in range(3)]
    pushed = (ip & 0xf0) | ((ip+1) & 15)
    operations = {'same':old, 'rotate':old[1:]+old[:1], 'push':[pushed]+old[:2]}
    if args.r38 and ip==0x12:operations['push2']=[0xC7,0x13,old[0]]
    kind = None
    for label, values in operations.items():
        s = base(a, ip)
        s.add(~And(*[x==y for x,y in zip(new,values)]))
        if s.check() == unsat:
            kind=label
            break
    assert kind is not None, ip
    s=base(a, ip);s.add(av!=bv)
    if s.check()==unsat:
        vector='preserve'
    else:
        s=base(a,ip);assert s.check()==sat
        v=s.model().eval(bv,model_completion=True).as_long()
        s.add(bv!=v)
        vector=v if s.check()==unsat else None
        if vector is None:
            s=base(a,ip);s.add(b.r[37]!=b.r[40])
            if s.check()==unsat:vector='diagonal'
    s=base(a,ip);s.add(a.s1!=b.s1)
    if s.check()==unsat:
        selector='preserve'
    else:
        s=base(a,ip)
        selector=tuple(q['possible_values'](b.s1,s,17))
    adelta, bdelta = a.s1-a.r[35], b.s1-b.r[35]
    s=base(a,ip);assert s.check()==sat
    change=s.model().eval(bdelta-adelta,model_completion=True).as_long()
    s.add(bdelta-adelta!=change)
    if s.check()==unsat:
        delta=('add',change)
    else:
        s=base(a,ip);assert s.check()==sat
        v=s.model().eval(bdelta,model_completion=True).as_long()
        s.add(bdelta!=v)
        delta=('set',v if s.check()==unsat else None)
    adr38, bdr38=a.r[38]-a.r[35],b.r[38]-b.r[35]
    dr38=('set',None)
    if args.r38:
        s=base(a,ip);assert s.check()==sat
        change=s.model().eval(bdr38-adr38,model_completion=True).as_long()
        s.add(bdr38-adr38!=change)
        if s.check()==unsat:
            dr38=('add',change)
        else:
            s=base(a,ip);assert s.check()==sat
            v=s.model().eval(bdr38,model_completion=True).as_long()
            s.add(bdr38!=v)
            dr38=('set',v if s.check()==unsat else None)
    s=base(a,ip);s.add(b.r[38]!=a.r[38])
    preserves_r38=s.check()==unsat
    s=base(a,ip);s.add(b.r[26]!=a.r[26])
    preserves_r26=s.check()==unsat
    type_preserved=[]
    for index in TYPE_FIELDS:
        s=base(a,ip);s.add(b.r[index]!=a.r[index])
        type_preserved.append(s.check()==unsat)
    addr=byte(b.r[36],b.r[39])
    dependencies=expression_vars([addr,b.s1,bdelta,b.r[38],bdr38,b.r[26],b.r[32]]
                                 + ([b.r[2]] if args.r2 else [])
                                 + ([b.r[5]] if args.r5 else [])
                                 + ([b.r[33]] if args.r33 else []))
    sp_deps=tuple(i for i in range(3) if str(a.st[36+i]) in dependencies
                  or str(a.st[39+i]) in dependencies)
    if args.full_stack_cache:sp_deps=tuple(range(3))
    templates[ip]=(a,addr,av,old,kind,pushed,vector,selector,b.s1,delta,sp_deps,
                   b.r[38],preserves_r38,dr38,b.r[26],preserves_r26,
                   tuple(b.r[index] for index in TYPE_FIELDS),tuple(type_preserved))
    if ip%32==31:print(f'compiled {ip+1}/256',flush=True)
print('compiled 256 abstract transfer functions',flush=True)

cache={}
start_types = ((0,),(0,)) if args.types else (None,None)
if args.r2:start_types += ((0,),)
if args.r5:start_types += ((0,),)
if args.r33:start_types += ((0,),)
if not (args.types or args.r2 or args.r5 or args.r33):start_types = None
start=(0,(0,0,0),0,(0,),0,(0,) if args.r38 else None,0 if args.r38 else None,
       (0,) if args.r38 else None,start_types)
if args.last_dd:start += (False,)
parents={start:None}
reported_predecessors={entry:set() for entry in args.report_entry}
queue=deque([start])
terminal=None
while queue and len(parents)<args.limit:
    state=queue.popleft()
    ip,sp,vector,selector,delta,r38,dr38,r26,types=state[:9]
    last_dd=state[9] if args.last_dd else None
    possible_r35=set(range(16))
    if types is not None and types[1] is not None:possible_r35.intersection_update(types[1])
    if delta is not None:possible_r35.intersection_update((n-delta)%16 for n in selector)
    if dr38 is not None:possible_r35.intersection_update((n-dr38)%16 for n in r38)
    if ((args.target=='a3' and ip==0xA3 and vector in (None,0xC7,0xC8))
        or (args.target=='cd' and ip==0xCD and any(n in selector for n in [7,8]))
        or (args.target=='ddentry' and ip==0x1D and 8 in r26 and 7 in possible_r35)
        or (args.target=='type7' and ip==0x7E and 7 in possible_r35 and any(n != 0 for n in r26))
        or (args.target=='mode07' and ip==0x07 and 4 in r38
            and any(n >= 5 for n in types[2]) and any(n != 0 for n in r26)
            and (not args.last_dd or last_dd))
        or (args.target=='c7' and ip==0xC7)
        or (args.target in ('ms','non60') and ip in (0xC7,0xC8))):
        terminal=state
        break
    (a,addr,av,old,kind,pushed,new_vector,new_selector,final_selector,delta_op,sp_deps,
     final_r38,preserves_r38,dr38_op,final_r26,preserves_r26,
     final_types,type_preserved)=templates[ip]
    # This tag follows every path. It does NOT discard an earlier 1F/E6
    # execution: a later DD can prepare a new selector and make it relevant.
    next_last_dd=last_dd if preserves_r38 else ip==0xDD
    next_sp=(sp if kind=='same' else sp[1:]+sp[:1] if kind=='rotate'
             else (0xC7,0x13,sp[0]) if kind=='push2' else (pushed,sp[0],sp[1]))
    next_vector=vector if new_vector=='preserve' else new_vector
    next_delta=((delta+delta_op[1])%16 if delta is not None else None) if delta_op[0]=='add' else delta_op[1]
    next_dr38=((dr38+dr38_op[1])%16 if dr38 is not None else None) if dr38_op[0]=='add' else dr38_op[1]
    key=(ip,tuple(sp[i] for i in sp_deps),vector,selector,delta,r38,dr38,r26,types)
    if key not in cache:
        s=state_solver(a,ip)
        if vector=='diagonal':s.add(a.r[37]==a.r[40])
        elif vector is not None:s.add(av==vector)
        s.add(Or(*[a.s1==n for n in selector]))
        if delta is not None:s.add(a.s1-a.r[35]==delta)
        if r38 is not None:s.add(Or(*[a.r[38]==n for n in r38]))
        if dr38 is not None:s.add(a.r[38]-a.r[35]==dr38)
        if r26 is not None:s.add(Or(*[a.r[26]==n for n in r26]))
        if types is not None:
            for index,values in zip(TYPE_FIELDS,types):
                if values is not None:s.add(Or(*[a.r[index]==n for n in values]))
        s.add(*[v==n for v,n in zip(old,sp)])
        s.push()
        next_ips=q['possible_values'](addr,s,257)
        s.pop()
        outputs=[]
        for next_ip in next_ips:
            if new_selector=='preserve' and len(selector)==1:
                next_selector=selector
            else:
                s.push();s.add(addr==next_ip)
                next_selector=tuple(q['possible_values'](final_selector,s,17))
                s.pop()
            if r38 is None:
                next_r38=None
            elif preserves_r38 and len(r38)==1:
                next_r38=r38
            else:
                s.push();s.add(addr==next_ip)
                next_r38=tuple(q['possible_values'](final_r38,s,17))
                s.pop()
            if r26 is None:
                next_r26=None
            elif preserves_r26 and len(r26)==1:
                next_r26=r26
            else:
                s.push();s.add(addr==next_ip)
                next_r26=tuple(q['possible_values'](final_r26,s,17))
                s.pop()
            next_types=None
            if types is not None:
                new=[]
                for values,expression,preserve in zip(types,final_types,type_preserved):
                    if values is None:new.append(None)
                    elif preserve and len(values)==1:new.append(values)
                    else:
                        s.push();s.add(addr==next_ip)
                        new.append(tuple(q['possible_values'](expression,s,17)))
                        s.pop()
                next_types=tuple(new)
            outputs.append((next_ip,next_selector,next_r38,next_r26,next_types))
        cache[key]=outputs
    for next_ip,next_selector,next_r38,next_r26,next_types in cache[key]:
        if not args.include_ms and args.target not in ('ms','non60','c7') and next_ip in (0xC7,0xC8):continue
        if args.target=='non60' and ip==0x60 and next_ip==0xC8:continue
        nxt=(next_ip,next_sp,next_vector,next_selector,next_delta,next_r38,next_dr38,next_r26,next_types)
        if args.last_dd:nxt += (next_last_dd,)
        if next_ip in reported_predecessors:
            reported_predecessors[next_ip].add(ip)
        if nxt not in parents:
            parents[nxt]=state
            queue.append(nxt)
    if len(parents)%10000==0:
        print(f'{len(parents)} states; {len(queue)} pending',flush=True)
print('states',len(parents),'pending',len(queue),'candidate',bool(terminal),flush=True)
if not terminal:
    print('FIXPOINT: target excluded in this abstraction' if not queue
          else 'INCOMPLETE: state limit reached; no exclusion proved',flush=True)
print('A3 vectors:', sorted({str(v) if not isinstance(v,int) else f'{v:02X}'
                             for ip,sp,v,sel,delta,r38,dr38,r26,types in (st[:9] for st in parents) if ip==0xA3}),flush=True)
print('CD selectors:',sorted({n for ip,sp,v,sel,delta,r38,dr38,r26,types in (st[:9] for st in parents) if ip==0xCD for n in sel}),flush=True)
for requested in args.report_entry:
    entries=[st for st in parents if st[0]==requested]
    print(f'entry {requested:02X}: {len(entries)} abstract states',flush=True)
    print('  predecessors:', sorted(f'{ip:02X}' for ip in reported_predecessors[requested]),flush=True)
    print('  vectors:',sorted({str(st[2]) if not isinstance(st[2],int)
                              else f'{st[2]:02X}' for st in entries}),flush=True)
    for selector in sorted({s for st in entries for s in st[3]}):
        subset=[st for st in entries if selector in st[3]]
        print(f'  S1={selector:X} vector classes:',
              sorted({str(st[2]) if not isinstance(st[2],int) else f'{st[2]:02X}'
                      for st in subset}),flush=True)
        print('    top address-stack bytes:',sorted({f'{st[1][0]:02X}' for st in subset}),flush=True)
    tagged=[st for st in entries if st[1][-1]==requested]
    if tagged and args.r38:
        print('  R38 when bottom stack byte equals the entry (includes rotated returns):',
              sorted({n for st in tagged for n in st[5]}),flush=True)
    for label,index in [('S1',3),('R38',5),('R26',7)]:
        print(f'  {label}:',sorted({n for st in entries if st[index] is not None
                                   for n in st[index]}),flush=True)
    if args.r2:
        print('  R2:', sorted({n for st in entries for n in st[8][2]}),flush=True)
    if args.r5:
        print('  R5:', sorted({n for st in entries for n in st[8][TYPE_FIELDS.index(5)]}),flush=True)
    if args.r33:
        print('  R33:', sorted({n for st in entries for n in st[8][TYPE_FIELDS.index(33)]}),flush=True)
    if args.last_dd:
        print('  states whose last R38 writer is DD:',sum(st[9] for st in entries),flush=True)
if args.check_1f_invariants:
    assert args.r38 and args.target in ('cd','non60')
    assert not queue and terminal is None, 'selector bounds require a completed first-entry fixpoint'
    for requested,allowed in [(0xF8,{7,8}),(0xFC,{7,8,14}),(0x68,{7,8,14})]:
        actual={n for st in parents if st[0]==requested for n in st[5]}
        assert actual and actual<=allowed, (requested,actual)
    print('PASS: first-entry R38 domains at F8/FC/68 exclude selector 2 and thus 68->A5',flush=True)
if args.check_dd_invariants:
    assert args.r38 and args.target in ('cd','non60')
    assert not queue and terminal is None, 'DD invariants require a completed first-entry fixpoint'
    vector_by_selector={0:{0x90},9:{0x93,0xCC,0xD8,'diagonal'},
                        11:{0xD3},13:{0xD3}}
    for requested in (0xA2,0xA3):
        entries=[st for st in parents if st[0]==requested]
        assert entries, requested
        for st in entries:
            for selector in st[3]:
                assert st[2] in vector_by_selector.get(selector,set()), (requested,st)
    for requested,allowed in [(0xCB,{4,6}),(0xD4,{4}),(0xD6,{6})]:
        actual={n for st in parents if st[0]==requested for n in st[3]}
        assert actual and actual<=allowed, (requested,actual)
    print('PASS: first-entry A2/A3 selector-vector correlations; '
          'CB selectors {4,6}, D4 {4}, D6 {6}',flush=True)
if args.check_c8_invariants:
    assert args.r38 and args.target=='c7'
    assert not queue and terminal is None, 'post-C8 invariants require a completed fixpoint'
    entries=[st for st in parents if st[0]==0xC8]
    assert entries, 'C8 must actually be admitted and processed by this analysis'
    for st in entries:
        assert st[1][0]==0x6E and st[2]==0x5E and set(st[3])=={0},st
        assert set(st[5])=={4} and 0 not in st[7],st
    allowed_vectors={0x90,0x93,0xCC,0xD3,0xD8,'diagonal'}
    assert all(st[2] in allowed_vectors for st in parents if st[0]==0xA3)
    assert {n for st in parents if st[0]==0xCD for n in st[3]}=={9}
    print(f'PASS: {len(entries)} C8 abstract states processed with return 6E; '
          'A3 vector bounds and CD selector 9 remain invariant despite admitted C8 executions; '
          'C7 excluded without bounding the number of C8 calls',flush=True)
if terminal:
    path=[]
    cursor=terminal
    while cursor is not None:
        path.append(cursor)
        cursor=parents[cursor]
    path.reverse()
    expanded=[]
    for st in path:
        expanded.append(st[0])
        if st[0]==0x93:expanded.append(0x94)
        if args.r38 and st[0]==0x12:expanded.append(0xC6)
    print('candidate path:',' '.join(f'{ip:02X}' for ip in expanded),flush=True)
    print('states:',[(f'{ip:02X}','/'.join(f'{v:02X}' for v in sp),
                      '*' if v is None else v if isinstance(v,str) else f'{v:02X}',sel,delta,r38,dr38,r26,types)
                     for ip,sp,v,sel,delta,r38,dr38,r26,types in (st[:9] for st in path)],flush=True)
    if args.last_dd:
        print('last-DD history:',[(f'{st[0]:02X}',st[9]) for st in path],flush=True)
