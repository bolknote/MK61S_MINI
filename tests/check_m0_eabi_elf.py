#!/usr/bin/env python3
"""Compare linked M0 addition fast paths with an independently tested ELF."""
import argparse
import hashlib
import json
from pathlib import Path
from check_stm32_vectors import ElfImage


def region(image, first, last):
    start, end = (image.symbols[name] & ~1 for name in (first, last))
    for section in image.sections:
        if (section[1] != 8 and section[2] & 2
                and section[3] <= start < end <= section[3] + section[5]):
            offset = section[4] + start - section[3]
            return image.data[offset:offset + end - start]
    raise AssertionError(('ELF region not found', first, last))


def compare(reference, production):
    images = [ElfImage(path) for path in (reference, production)]
    regions = {}
    # These contiguous regions contain only internal branches and literals.
    # The external call to the IEEE fallback is in the preceding slow stub.
    for name, first, last in (
            ('subtraction_entry', '__aeabi_dsub', '__aeabi_dadd'),
            ('complete_addition_fast_paths', '__aeabi_dadd', '__aeabi_dmul')):
        expected, actual = (region(image, first, last) for image in images)
        assert expected == actual, name + ' differs from the tested ARM binary'
        regions[name] = {'bytes': len(actual), 'sha256': hashlib.sha256(actual).hexdigest()}
    return {
        'status': 'PASS',
        'production_elf_sha256': hashlib.sha256(production.read_bytes()).hexdigest(),
        'tested_elf_sha256': hashlib.sha256(reference.read_bytes()).hexdigest(),
        'regions': regions,
        'scope': 'Read-only byte comparison: subtraction entry and all addition fast paths '
                 'in the production ELF exactly match the independently tested ARM binary. '
                 'No ELF execution or external fallback relocation check is performed.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('production', type=Path)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    report = json.dumps(compare(args.reference, args.production), indent=2) + '\n'
    print(report, end='')
    if args.json:
        args.json.write_text(report)


if __name__ == '__main__':
    main()
