#!/usr/bin/env python3
"""Independent, correctly rounded binary64 references (host MPFR only).

Evaluate lower/upper directed MPFR bounds and increase precision until both
bounds round to the same binary64. No firmware or approximation table is used.
"""
import ctypes as C
import ctypes.util
import math
import struct


def bits(x):
    return struct.unpack('<Q', struct.pack('<d', x))[0]


def real(x):
    return struct.unpack('<d', struct.pack('<Q', x))[0]


class _Number(C.Structure):
    _fields_ = [('precision', C.c_long), ('sign', C.c_int),
                ('exponent', C.c_long), ('limbs', C.POINTER(C.c_ulong))]


class Oracle:
    NAMES = {'ln': 'log', 'sqrt': 'sqrt', 'sin': 'sin', 'cos': 'cos',
             'tan': 'tan', 'atan': 'atan', 'asin': 'asin', 'acos': 'acos',
             'exp': 'exp', 'log10': 'log10', 'pow': 'pow', 'fma': 'fma',
             'dadd': 'add', 'dsub': 'sub', 'dmul': 'mul', 'ddiv': 'div'}
    BINARY = ('pow', 'dadd', 'dsub', 'dmul', 'ddiv')

    def __init__(self):
        path = C.util.find_library('mpfr')
        if not path:
            raise RuntimeError('MPFR is required for the independent rounding oracle')
        self.lib = C.CDLL(path)
        pointer = C.POINTER(_Number)
        self.lib.mpfr_init2.argtypes = [pointer, C.c_long]
        self.lib.mpfr_clear.argtypes = [pointer]
        self.lib.mpfr_set_d.argtypes = [pointer, C.c_double, C.c_int]
        self.lib.mpfr_get_d.argtypes = [pointer, C.c_int]
        self.lib.mpfr_get_d.restype = C.c_double
        self.lib.mpfr_get_version.restype = C.c_char_p
        self.version = self.lib.mpfr_get_version().decode()
        for name, operation in self.NAMES.items():
            arity = 3 if name == 'fma' else 2 if name in self.BINARY else 1
            function = getattr(self.lib, 'mpfr_' + operation)
            function.argtypes = [pointer] * (arity + 1) + [C.c_int]
            function.restype = C.c_int

    def reference(self, name, *arguments):
        # MPFR has one NaN kind; set_d loses the signalling distinction.
        # IEEE operations quiet sNaN, including pow(1,sNaN)/pow(sNaN,0).
        for argument in arguments:
            magnitude=argument&0x7FFFFFFFFFFFFFFF
            if magnitude>0x7FF0000000000000 and not (argument&(1<<51)):
                return argument|(1<<51)
        function = getattr(self.lib, 'mpfr_' + self.NAMES[name])
        # At 53 bits every binary64 input, including subnormals, is exact.
        inputs = [_Number() for _ in arguments]
        for number, argument in zip(inputs, arguments):
            self.lib.mpfr_init2(C.byref(number), 53)
            self.lib.mpfr_set_d(C.byref(number), real(argument), 0)
        try:
            precision = 128
            while precision <= 16384:
                endpoints = []
                for direction in (3, 2):  # MPFR_RNDD, MPFR_RNDU
                    result = _Number()
                    self.lib.mpfr_init2(C.byref(result), precision)
                    try:
                        function(C.byref(result), *map(C.byref, inputs), direction)
                        endpoints.append(self.lib.mpfr_get_d(C.byref(result), 0))
                    finally:
                        self.lib.mpfr_clear(C.byref(result))
                lo, hi = endpoints
                if bits(lo) == bits(hi) or (math.isnan(lo) and math.isnan(hi)):
                    return bits(lo)
                # Exact cancellation has opposite directed zero signs. RNE
                # is +0 (except when every zero term has the negative sign).
                if lo == hi == 0 and name in ('fma', 'dadd', 'dsub'):
                    result = _Number()
                    self.lib.mpfr_init2(C.byref(result), precision)
                    try:
                        function(C.byref(result), *map(C.byref, inputs), 0)
                        return bits(self.lib.mpfr_get_d(C.byref(result), 0))
                    finally:
                        self.lib.mpfr_clear(C.byref(result))
                precision *= 2
            raise AssertionError(('MPFR interval did not decide rounding', name, arguments))
        finally:
            for number in inputs:
                self.lib.mpfr_clear(C.byref(number))


if __name__ == '__main__':
    oracle = Oracle()
    assert oracle.reference('sqrt', bits(4.)) == bits(2.)
    assert oracle.reference('sin', bits(-0.)) == bits(-0.)
    assert oracle.reference('ln', bits(1.)) == bits(0.)
    assert oracle.reference('pow', bits(10.), bits(3.)) == bits(1000.)
    assert oracle.reference('fma', bits(1. + 2.**-27), bits(1. - 2.**-27), bits(-1.)) == bits(-2.**-54)
    assert oracle.reference('dadd', bits(1.), bits(2.**-53)) == bits(1.)
    assert oracle.reference('dadd', bits(1.), bits(-1.)) == bits(0.)
    assert oracle.reference('dsub', bits(-0.), bits(0.)) == bits(-0.)
    assert oracle.reference('dmul', 1, bits(1.)) == 1
    assert oracle.reference('ddiv', bits(1.), bits(3.)) == 0x3FD5555555555555
    print('PASS: MPFR', oracle.version, 'directed interval oracle')
