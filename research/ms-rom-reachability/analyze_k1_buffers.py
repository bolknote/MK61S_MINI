#!/usr/bin/env python3
"""Search one-pair K1 candidates while tracking exact copies in R, ST and S.

This is a candidate finder, NOT a reachability or impossibility proof. Its
control graph overapproximates the real ring. Its payload transport is narrower:
only universally proved, unconditional tetrade copies, with no arithmetic or
temporary storage in the external ring. Per-tetrade alias classification is
deliberately incomplete (large expressions are skipped). Neither a positive
nor a negative result by itself settles native K1.
"""
from collections import deque, Counter
from pathlib import Path
import runpy
from z3 import is_const, is_bv_value, Z3_OP_UNINTERPRETED, unsat


def fields(a):
    return a.r + a.st + [a.s, a.s1]


def small_variables(expression, limit=4):
    """Visit the expression DAG once; abandon large dependency sets early."""
    pending=[expression];visited=set();variables=[]
    while pending:
        value=pending.pop();identifier=value.get_id()
        if identifier in visited:continue
        visited.add(identifier)
        if is_const(value) and value.decl().kind()==Z3_OP_UNINTERPRETED:
            variables.append(value)
            if len(variables)>limit:return None
        else:pending.extend(value.children())
    return variables


def compile_copies(m, preserved_a=()):
    """Each output stores a proved input index, or -1 for unknown/non-copy.

    Internal field positions: R[0:42], ST[0:42], S, S1. Input-only positions
    86..127 denote the current M page; these do not survive the next command.
    """
    q=m['q']; result={}
    for ip in range(256):
        a=q['State'](f'k1_buffers_{ip}')
        emitted=[]
        b=q['execute_command'](a,ip,*q['arbitrary_keys'](f'k1_buffer_keys_{ip}'),
                               emitted_outputs=emitted)
        for extra in ((0x94,) if ip==0x93 else (0xC6,) if ip==0x12 else ()):
            b=q['execute_command'](b,extra,*q['arbitrary_keys'](f'k1_buffer_extra_{ip}'))
        original=fields(a)+a.m
        identifiers={v.get_id():i for i,v in enumerate(original)}
        p=q['base_solver'](a,ip);p.set(timeout=1000)
        mapping=[]
        for index,value in enumerate(fields(b)+emitted):
            if index<36 and index%3==0 and ip in preserved_a:
                mapping.append(index);continue
            if value.get_id() in identifiers:
                mapping.append(identifiers[value.get_id()]);continue
            if is_bv_value(value):mapping.append(-1);continue
            variables=small_variables(value)
            if variables is None:mapping.append(-1);continue
            candidates=[identifiers[v.get_id()] for v in variables
                        if v.get_id() in identifiers]
            found=-1
            if len(variables)<=4:
                for candidate in candidates:
                    p.push();p.add(value!=original[candidate])
                    same=p.check()==unsat;p.pop()
                    if same:found=candidate;break
            mapping.append(found)
        result[ip]=tuple(mapping)
        if ip%32==31:print('Compiled copy maps:',ip+1,flush=True)
    return result


def transport(mapping, internal, page=bytes(42)):
    source=internal+page
    return bytes(source[i] if i>=0 else 0 for i in mapping)


def analyze(m, copies, aligned=True, limit=500000, tail_only=False):
    ctl=runpy.run_path(str(Path(__file__).with_name('audit_ms_rom_control.py')))
    successors,_=ctl['graph'](m)
    # Twelve independent tokens; their order, signs and exponent tetras matter.
    tokens=bytes(range(1,13));empty=bytes(86)
    entry=0xE7 if tail_only else 0xD6
    source_page=bytearray(42)
    for i in range(12):source_page[3*i+(1 if tail_only else 0)]=i+1
    read=transport(copies[entry],empty,bytes(source_page))[:86]
    parents={};queue=deque()
    for state in successors:
        if state[0]!=entry:continue
        for target in successors[state]:
            item=(target,1 if tail_only else 0,1 if aligned else 0,read)
            if item not in parents:parents[item]=(None,state);queue.append(item)
    terminal=None;processed=0;dropped=Counter()
    while queue and len(parents)<limit:
        item=queue.popleft();state,stage,phase,payload=item;ip=state[0]
        mapping=copies[ip]
        if ip==0xD4:
            out=transport(mapping,payload)[86:]
            if stage==1 and (not aligned or phase==0) and out[0:36:3]==tokens:
                terminal=item;break
            continue
        if ip==0xE7 and stage==0 and (not aligned or phase==0) and payload[0:36:3]==tokens:
            # The register word has just reached its intended Ms page. Track
            # the old Ms word from now on; discard internal copies of Πi.
            ms=bytearray(42)
            for i in range(12):ms[1+3*i]=i+1
            new_payload=transport(mapping,empty,bytes(ms))[:86];new_stage=1
        else:
            new_payload=transport(mapping,payload)[:86];new_stage=stage
        if not all(token in new_payload for token in tokens):
            dropped[(stage,ip)]+=1;continue
        length=2 if ip in (0x12,0x93) else 1
        next_phase=(phase+length)%15 if aligned else 0
        for target in successors[state]:
            nxt=(target,new_stage,next_phase,new_payload)
            if nxt not in parents:parents[nxt]=(item,None);queue.append(nxt)
        processed+=1
        if processed%25000==0:
            print('Buffer search:',processed,'processed,',len(parents),'states,',
                  len(queue),'pending',flush=True)
    print('Buffered K1:',len(parents),'states,',len(queue),'pending, candidate=',
          terminal is not None,'aligned=',aligned,'tail_only=',tail_only,flush=True)
    print('Stages:',Counter(stg for _,stg,_,_ in parents),flush=True)
    print('Payload-losing frontiers:',[(stage,f'{ip:02X}',count)
          for (stage,ip),count in dropped.most_common(15)],flush=True)
    path=[];item=terminal
    while item is not None:
        state,stage,phase,payload=item;path.append((state,stage,phase,payload))
        previous,start=parents[item]
        if start is not None:path.append((start,-1,0,empty))
        item=previous
    path.reverse()
    if path:
        print('CANDIDATE:',' '.join(f'{state[0]:02X}' for state,_,_,_ in path),flush=True)
    return {'path':path,'parents':parents,'pending':len(queue),'dropped':dropped}


def backward_tail(m, copies, aligned=True, limit=500000):
    """Demand all twelve output tokens at D4 and trace exact copies backwards.

    A demand stores one input position per distinct token. No arbitrary ring
    read is accepted as a source: only E7's twelve M2 input tetras can finish
    this search. Thus a completed negative remains limited to this copy cover.
    """
    ctl=runpy.run_path(str(Path(__file__).with_name('audit_ms_rom_control.py')))
    successors,predecessors=ctl['graph'](m)
    required=tuple(copies[0xD4][86+3*i] for i in range(12))
    assert len(set(required))==12 and min(required)>=0 and max(required)<86
    parents={(state,0,required):None for state in successors if state[0]==0xD4}
    queue=deque(parents);terminal=None;starts=len(queue)
    ms=tuple(86+1+3*i for i in range(12))
    while queue and len(parents)<limit:
        item=queue.popleft();state,phase,demand=item
        for pred in predecessors[state]:
            ip=pred[0]
            if ip==0xD4:continue
            length=2 if ip in (0x12,0x93) else 1
            old_phase=(phase-length)%15 if aligned else 0
            before=tuple(copies[ip][position] for position in demand)
            if min(before)<0 or len(set(before))<12:continue
            if ip==0xE7 and before==ms and (not aligned or old_phase==0):
                terminal=(pred,old_phase,before);parents[terminal]=item;break
            if max(before)>=86:continue
            previous=(pred,old_phase,before)
            if previous not in parents:parents[previous]=item;queue.append(previous)
        if terminal is not None:break
    path=[];item=terminal
    while item is not None:path.append(item);item=parents[item]
    print('Backward E7 -> D4:',starts,'D4 starts,',len(parents),'states,',
          len(queue),'pending, candidate=',terminal is not None,'aligned=',aligned,flush=True)
    print('Backward demand IPs:',len({state[0] for state,_,_ in parents}),flush=True)
    if path:
        print('CANDIDATE:',' '.join(f'{state[0]:02X}' for state,_,_ in path),flush=True)
    return {'path':path,'parents':parents,'pending':len(queue)}


def join_searches(forward, backward):
    """Join proven copy availability to backward requirements at one state."""
    from collections import defaultdict
    index=defaultdict(list)
    for item in forward['parents']:
        state,stage,phase,payload=item
        if stage==1:index[(state,phase)].append(item)
    for back in backward['parents']:
        state,phase,demand=back
        if max(demand)>=86:continue
        for front in index[(state,phase)]:
            payload=front[3]
            if not all(payload[position]==i+1 for i,position in enumerate(demand)):continue
            states=[];item=front
            while item is not None:
                states.append(item[0]);previous,start=forward['parents'][item]
                if start is not None:states.append(start)
                item=previous
            states.reverse();item=backward['parents'][back]
            while item is not None:states.append(item[0]);item=backward['parents'][item]
            print('JOINED CANDIDATE:',' '.join(f'{s[0]:02X}' for s in states),flush=True)
            return states
    print('No forward/backward join in the explored subsets.',flush=True)
    return []


if __name__=='__main__':
    import argparse
    import sys
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unaligned',action='store_true')
    parser.add_argument('--tail-only',action='store_true')
    parser.add_argument('--direction',choices=('forward','backward','join'),default='forward')
    parser.add_argument('--limit',type=int,default=500000)
    options=parser.parse_args();aligned=not options.unaligned
    assert options.limit>0
    sys.argv=['analyze_gates.py','--target','c7','--r38','--check-c8-invariants']
    m=runpy.run_path(str(Path(__file__).with_name('analyze_gates.py')))
    direct=runpy.run_path(str(Path(__file__).with_name('analyze_k1_carrier.py')))['analyze'](m,aligned)
    copies=compile_copies(m,direct['preserves'])
    if options.direction=='backward':backward_tail(m,copies,aligned,options.limit)
    elif options.direction=='join':
        forward=analyze(m,copies,aligned,options.limit,True)
        backward=backward_tail(m,copies,aligned,options.limit)
        candidate=join_searches(forward,backward)
        if candidate:
            checker=runpy.run_path(str(Path(__file__).with_name('check_k1_buffers.py')))
            checker['exact_path'](m,candidate)
    else:analyze(m,copies,aligned,options.limit,options.tail_only)
