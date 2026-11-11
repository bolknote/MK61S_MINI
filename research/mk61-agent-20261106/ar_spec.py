"""Bounded numerical verification and partial symbolic decoding; no intent oracle.

The checker accepts a *declared* arithmetic postcondition. It never interprets
Russian and never calls a model. TESTED is finite testing, not a proof.
"""
import copy
import math
from decimal import Decimal

from full_isa_math import UNARY, BINARY, value
from full_isa_protocol import REGISTERS
from ha_protocol import assemble, canonical

TOLERANCE = 2e-6


def expression_text(expr):
    if isinstance(expr, str):
        return expr
    if isinstance(expr, dict):
        return 'pi' if 'pi' in expr else str(expr['constant'])
    op, *args = expr
    if len(args) == 1:
        return op + '(' + expression_text(args[0]) + ')'
    return '(' + expression_text(args[0]) + op + expression_text(args[1]) + ')'


def spec_text(spec):
    if spec is None:
        return 'недоступна'
    result = 'X=' + expression_text(spec['X'])
    for register, expr in sorted(spec.get('writes', {}).items()):
        result += '; ' + register + '=' + expression_text(expr)
    return result + '; остальные регистры сохранить; ' + spec['angle']


def expected(spec, inputs):
    state = {k: float(inputs.get(k, '0')) for k in [*REGISTERS, 'X', 'Y', 'Z', 'T']}
    answer = {k: state[k] for k in REGISTERS}
    answer['X'] = value(spec['X'], state, spec['angle'])
    for register, expr in spec.get('writes', {}).items():
        answer[register] = value(expr, state, spec['angle'])
    if not all(math.isfinite(x) and abs(x) < 1e90 for x in answer.values()):
        raise ValueError('Nonfinite or unbounded postcondition')
    return answer


def close(a, b):
    if a is None:
        return False
    a, b = float(a), float(b)
    return math.isfinite(a) and abs(a-b) <= max(TOLERANCE, abs(b)*TOLERANCE)


def equivalent(a, b, bank):
    if a is None or b is None:
        return {'tested_equal': False, 'reason': 'SPEC_UNAVAILABLE'}
    for index, inputs in enumerate(bank):
        try:
            x, y = expected(a, inputs), expected(b, inputs)
        except (ValueError, ArithmeticError, OverflowError, KeyError) as error:
            return {'tested_equal': False, 'reason': 'DOMAIN', 'case': index, 'error': str(error)}
        for name in x:
            if not close(x[name], y[name]):
                return {'tested_equal': False, 'reason': 'COUNTEREXAMPLE', 'case': index,
                        'inputs': inputs, 'name': name, 'declared': x[name], 'required': y[name]}
    return {'tested_equal': True, 'cases': len(bank), 'reason': 'TESTED'}


def verify(vm, body, pool, spec, bank):
    if spec is None:
        return {'status': 'UNKNOWN', 'reason': 'SPEC_UNAVAILABLE', 'cases': 0}
    try:
        code = assemble(body or [], pool, 'asm')
    except (ValueError, ArithmeticError) as error:
        return {'status': 'FAIL', 'reason': 'ASSEMBLY', 'error': str(error), 'cases': 0}
    for index, inputs in enumerate(bank):
        try:
            target = expected(spec, inputs)
        except (ValueError, ArithmeticError, OverflowError, KeyError) as error:
            return {'status': 'UNKNOWN', 'reason': 'SPEC_DOMAIN', 'case': index, 'cases': index,
                    'inputs': inputs, 'error': str(error)}
        actual, _ = vm.execute(code, inputs, angle=spec['angle'], max_commands=128, max_frames=1024)
        if actual['status'] != 'stopped':
            return {'status': 'FAIL', 'reason': 'EXECUTION', 'case': index, 'cases': index+1,
                    'inputs': inputs, 'actual_status': actual['status']}
        for name, number in target.items():
            if not close(actual['numeric'][name], number):
                return {'status': 'FAIL', 'reason': 'COUNTEREXAMPLE', 'case': index, 'cases': index+1,
                        'inputs': inputs, 'name': name, 'expected': number,
                        'actual': actual['numeric'][name], 'actual_raw': actual['raw'][name]}
    return {'status': 'TESTED', 'cases': len(bank), 'proof': False}


def infer(body, pool, angle):
    """Conservative decoder for straight-line RPN, with explicit UNKNOWN.

    Expressions refer to initial state, including after stores. Only canonical
    constant entry and normalized powers are recognized. No branch is guessed.
    """
    code = assemble(body or [], pool, 'asm')
    stack = ['X', 'Y', 'Z', 'T']
    memory = {k: k for k in REGISTERS}
    unary = {v: k for k, v in UNARY.items()}
    binary = {v: k for k, v in BINARY.items() if k != 'pow'}
    at = 0

    def push(expr):
        stack[:] = [copy.deepcopy(expr), *stack[:3]]

    while at < len(code):
        op = code[at]
        if op == 0x50:
            return {'X': stack[0], 'writes': {k: v for k, v in memory.items() if v != k},
                    'angle': angle, 'decoder': 'straight-line-v1'}
        if code[at:at+2] == [0x0E, 0x0D]:
            end = at+2
            digits = []
            while end < len(code) and code[end] <= 0x0A:
                digits.append('.' if code[end] == 10 else str(code[end]))
                end += 1
            if not digits:
                raise ValueError('UNKNOWN: noncanonical number entry')
            number = canonical(''.join(digits))
            if end < len(code) and code[end] == 0x0B:
                number = canonical(-Decimal(number)); end += 1
            push({'constant': number}); at = end; continue
        if code[at:at+4] == [0x24, 0x14, 0x0D, 0x10]:
            stack[:] = [['pow', stack[0], stack[1]], stack[2], stack[3], stack[3]]
            at += 4; continue
        if 0x60 <= op <= 0x6E:
            push(memory['R'+format(op-0x60, 'X')])
        elif 0x40 <= op <= 0x4E:
            memory['R'+format(op-0x40, 'X')] = copy.deepcopy(stack[0])
        elif op == 0x20:
            push({'pi': True})
        elif op in unary:
            stack[0] = [unary[op], stack[0]]
        elif op in binary:
            stack[:] = [[binary[op], stack[1], stack[0]], stack[2], stack[3], stack[3]]
        elif op == 0x14:
            stack[0], stack[1] = stack[1], stack[0]
        elif op != 0x54:
            raise ValueError('UNKNOWN: unsupported byte '+format(op, '02X'))
        at += 1
    raise ValueError('UNKNOWN: no explicit stop')
