#!/usr/bin/env python3
"""Reject an altered internal exact-pow helper in a comparison ELF."""
import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from check_m0_math_layout import verify, symbol_types
from check_stm32_vectors import ElfImage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production', type=Path, required=True)
    parser.add_argument('--json', type=Path, required=True)
    args = parser.parse_args()
    original = ElfImage(args.production)
    proof = verify(args.production, args.production)
    helpers = [row for row in proof['symbols'] if 'm0_pow_exact' in row['symbol']]
    assert helpers, 'Internal exact-pow helpers are missing from the layout proof'
    chosen = next(row for row in helpers if 'multiply' in row['symbol'])
    assert chosen['size'] >= 2
    types = symbol_types(original)
    address = chosen['address'] & ~1 if types[chosen['symbol']] == 2 else chosen['address']
    section = next(s for s in original.sections
                   if s[2] & 2 and s[1] != 8 and s[3] <= address < s[3] + s[5])
    offset = section[4] + address - section[3]
    damaged = bytearray(original.data)
    damaged[offset] ^= 1
    with TemporaryDirectory(prefix='m0-math-layout-') as temporary:
        path = Path(temporary) / 'altered.elf'
        path.write_bytes(damaged)
        try:
            verify(args.production, path)
        except AssertionError as error:
            assert 'Math bytes changed' in str(error) and chosen['symbol'] in str(error), error
        else:
            raise AssertionError('Altered internal exact-pow code was accepted')
    report = dict(status='PASS', production_elf_sha256=hashlib.sha256(original.data).hexdigest(),
                  checked_symbols=proof['checked_symbols'], internal_exact_helpers=len(helpers),
                  altered_symbol=chosen['symbol'], altered_byte_rejected=True,
                  scope='The production layout passes unchanged; changing one instruction byte inside an internal exact-pow helper is rejected. No firmware execution or hardware access.')
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS:', len(helpers), 'internal exact-pow helpers checked; altered instruction rejected')


if __name__ == '__main__':
    main()
