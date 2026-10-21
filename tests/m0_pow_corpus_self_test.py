#!/usr/bin/env python3
"""Regress the decimal literals and signaling NaNs in official pow.wc."""
from qualify_m0_pow_worst import parse_token, signaling_nan


def main():
    cases={
        '17':0x4031000000000000,
        '-17':0xC031000000000000,
        '+42':0x4045000000000000,
        '-42':0xC045000000000000,
        '9.5':0x4023000000000000,
        '+0':0,
        '-0':0x8000000000000000,
        '+1':0x3FF0000000000000,
        '0x1p-1074':1,
        '0x.fffffffffffffp-1022':0x000FFFFFFFFFFFFF,
        '0x1p-1022':0x0010000000000000,
        '0x1.fffffffffffffp+1023':0x7FEFFFFFFFFFFFFF,
        '+inf':0x7FF0000000000000,
        '-inf':0xFFF0000000000000,
        '+snan':0x7FF0000000000001,
        '-snan':0xFFF0000000000001,
    }
    for token,expected in cases.items():
        got=parse_token(token);assert got==expected,(token,hex(got),hex(expected))
    for token in ('snan','+snan','-snan'):assert signaling_nan(parse_token(token))
    for token in ('nan','+nan','-nan','inf','0','-0','1'):assert not signaling_nan(parse_token(token))
    for token in ('--snan','snan:bad','0x1p'):
        try:parse_token(token)
        except ValueError:pass
        else:raise AssertionError(('Accepted malformed token',token))
    print('PASS pow.wc decimal/hex/sNaN parser regression')


if __name__=='__main__':main()
