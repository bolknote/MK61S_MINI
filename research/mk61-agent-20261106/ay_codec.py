"""A prefix arithmetic tree encoded in existing HEX bytes, not MK-61 opcodes.

One destination byte FF (preserve memory) or 00..0E (store X in that register),
then one expression. Leaves 00..0E = initial registers; 10 kk = constant pool,
11 = pi; 20..31 = the 18 unary operators; 40..44 = the five binary operators.
Angle mode is supplied by the harness exactly as for ordinary HEX.
"""
from full_isa_math import UNARY, BINARY, compile_expr
from full_isa_protocol import REGISTERS
from ha_protocol import canonical, assemble, encode as encode_hex

UNARY_NAMES=list(UNARY)
BINARY_NAMES=list(BINARY)
MAX_NODES=31


def encode(spec,pool):
    writes=spec.get('writes',{})
    if len(writes)>1 or any(x!=spec['X']for x in writes.values()):raise ValueError('ONE_RESULT_STORE_ONLY')
    out=[int(next(iter(writes))[1:],16)if writes else 0xFF]
    def visit(expr):
        if isinstance(expr,str):
            if expr not in REGISTERS:raise ValueError('INITIAL_REGISTER_REQUIRED')
            out.append(int(expr[1:],16));return
        if isinstance(expr,dict):
            if 'pi'in expr:out.append(0x11)
            else:out.extend([0x10,pool.index(canonical(expr['constant']))])
            return
        op,*args=expr
        if op in UNARY:out.append(0x20+UNARY_NAMES.index(op))
        else:out.append(0x40+BINARY_NAMES.index(op))
        for x in args:visit(x)
    visit(spec['X']);return out


def decode(body,pool,angle):
    if not 2<=len(body)<=96 or any(type(x)is not int or not 0<=x<=255 for x in body):raise ValueError('SPEC_BYTES')
    destination=body[0]
    if destination!=0xFF and destination>14:raise ValueError('SPEC_DESTINATION')
    at=1;nodes=0
    def visit(depth=0):
        nonlocal at,nodes
        if depth>12 or nodes>=MAX_NODES:raise ValueError('SPEC_LIMIT')
        if at>=len(body):raise ValueError('SPEC_INCOMPLETE')
        op=body[at];at+=1;nodes+=1
        if op<=14:return 'R'+format(op,'X')
        if op==0x10:
            if at>=len(body)or body[at]>=len(pool):raise ValueError('SPEC_CONSTANT')
            index=body[at];at+=1;return {'constant':pool[index]}
        if op==0x11:return {'pi':True}
        if 0x20<=op<0x20+len(UNARY_NAMES):return [UNARY_NAMES[op-0x20],visit(depth+1)]
        if 0x40<=op<0x40+len(BINARY_NAMES):return [BINARY_NAMES[op-0x40],visit(depth+1),visit(depth+1)]
        raise ValueError('SPEC_OPCODE '+format(op,'02X'))
    expr=visit()
    if at!=len(body):raise ValueError('SPEC_TRAILING_BYTES')
    writes={}if destination==0xFF else{'R'+format(destination,'X'):expr}
    return {'X':expr,'writes':writes,'angle':angle}


def compile_spec(spec,pool):
    code=compile_expr(spec['X'])
    for r,expr in spec.get('writes',{}).items():
        if expr!=spec['X']:raise ValueError('STORE_RESULT_REQUIRED')
        code.append(0x40+int(r[1:],16))
    code.append(0x50)
    if len(code)>105:raise ValueError('PROGRAM_MEMORY_LIMIT')
    return encode_hex(code,pool,'asm')


def to_program(body,pool,angle,arm):
    if arm=='hex':
        assemble(body,pool,'asm');return list(body),None
    assert arm=='spec'
    spec=decode(body,pool,angle);return compile_spec(spec,pool),spec
