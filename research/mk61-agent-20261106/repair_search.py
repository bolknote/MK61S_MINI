"""Bounded public-example-guided arithmetic repair; never receives hidden tests."""
from decimal import Decimal
import itertools
import time

from harness import check_program

UNARY=[0x31,0x0B,0x22]
BINARY=[0x10,0x11,0x12,0x13]


def neighbors(code,reads):
    body=code[:-1]
    for i,op in enumerate(body):
        choices=reads if 0x60<=op<=0x6E else UNARY+BINARY
        for other in choices:
            if other!=op:yield body[:i]+[other]+body[i+1:]+[0x50]
    for i in range(len(body)):
        if len(body)>1:yield body[:i]+body[i+1:]+[0x50]
    for i in range(len(body)+1):
        for op in UNARY:yield body[:i]+[op]+body[i:]+[0x50]
    for i in range(len(body)-1):
        if 0x60<=body[i]<=0x6E and 0x60<=body[i+1]<=0x6E and body[i]!=body[i+1]:
            yield body[:i]+[body[i+1],body[i]]+body[i+2:]+[0x50]


def elementary(reads):
    for reg in reads:
        yield[reg,0x50]
        for op in UNARY:yield[reg,op,0x50]
    for a,b in itertools.product(reads,repeat=2):
        for op in BINARY:yield[a,b,op,0x50]


def search(emulator,seed,public_tests,*,budget=512,beam=8):
    """Return first public-fitting repair, or a bounded failure. No task text/oracle."""
    started=time.monotonic();attempts=0;seen=set();scored=[]
    meta={'budget':budget,'beam':beam,'uses_hidden_tests':False,'seconds':0.,'trials':0,'found':False}
    if not seed or any(t.get('expected_registers')for t in public_tests):return {**meta,'reason':'not_arithmetic_X_only'}
    code=list(seed)
    if 0x50 in code:code=code[:code.index(0x50)+1]
    else:code.append(0x50)
    if any(not(0x60<=x<=0x6E or x in UNARY+BINARY)for x in code[:-1]):return {**meta,'reason':'unsupported_instruction'}
    registers=sorted({k for t in public_tests for k in t['registers']if k.startswith('R')})
    reads=[0x60+int(k[1:],16)for k in registers]
    if not reads or len(reads)>4:return {**meta,'reason':'unsupported_input_registers'}
    def assess(candidate):
        nonlocal attempts
        key=tuple(candidate)
        if key in seen or len(candidate)>105 or attempts>=budget:return None
        seen.add(key);attempts+=1
        result=check_program(emulator,candidate,public_tests)
        count=sum(t['pass']for t in result['details']);error=0.
        for row in result['details']:
            try:
                expected=Decimal(row['expected_X']);actual=Decimal(row['actual']['X'])
                error+=min(1000000.,float(abs(actual-expected)/(1+abs(expected)))) if actual.is_finite()else 1000000.
            except (ValueError,ArithmeticError,KeyError):error+=1000000.
        scored.append(((count,-error,-abs(len(candidate)-len(code))),candidate))
        return result
    initial=assess(code)
    if initial and initial['pass']:return {**meta,'reason':'already_public_pass','trials':attempts}
    pools=[neighbors(code,reads),elementary(reads)]
    for pool in pools:
        for candidate in pool:
            result=assess(candidate)
            if result and result['pass']:
                return {**meta,'found':True,'code':candidate,'trials':attempts,'seconds':time.monotonic()-started,'reason':'public_pass'}
            if attempts>=budget:break
    # A second local edit is explored from public-score-ranked candidates only.
    best=[c for _,c in sorted(scored,key=lambda x:x[0],reverse=True)[:beam]]
    for parent in best:
        for candidate in neighbors(parent,reads):
            result=assess(candidate)
            if result and result['pass']:
                return {**meta,'found':True,'code':candidate,'trials':attempts,'seconds':time.monotonic()-started,'reason':'public_pass'}
            if attempts>=budget:break
        if attempts>=budget:break
    return {**meta,'trials':attempts,'seconds':time.monotonic()-started,'reason':'budget_or_neighborhood_exhausted'}
