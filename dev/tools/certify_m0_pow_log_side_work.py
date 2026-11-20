#!/usr/bin/env python3
"""Recalculate the audited Thumb instruction envelope of the 16384-bit comparator."""

import argparse
from collections import Counter
from hashlib import file_digest
import json
from pathlib import Path

from certify_m0_pow_log_side import (BLOCKS, FIRST_BLOCK, GROUPS, P, ROOT, TABLE_LAST,
                                    WORDS, arithmetic)


ELF_SHA256 = '9e8ea9bf957a9dff1d2dae6fe841a0e84ff7a35349c0bf97398cb0c22384d3cd'
ROM_SHA256 = 'ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'
SOURCE_SHA256 = '101dfc82e9db785324a491d0701fc4caa9fef61ca0ad059073f8652296247418'


def checksum(path):
    with path.open('rb') as file:
        return file_digest(file,'sha256').hexdigest()


def memset_work(byte_count):
    # RP2040 ROM MS clears up to 16 bytes per 3-instruction iteration.
    return 48+3*((byte_count+15)//16)


def work():
    proof = arithmetic()
    updates = proof['maximum_selected_operations_per_log']
    factors = sum(proof['maximum_factors'].values())
    powers = Counter()
    for n in range(1,P//(FIRST_BLOCK-8)+1):
        count = min(BLOCKS,max(0,(P//n+8-FIRST_BLOCK)//7+1))
        powers['calls'] += count
        powers['rounds'] += n*count
        powers['output_words'] += ((n+1)//2)*count

    words = WORDS+5
    accumulate = 32+16*words
    carry_calls = updates['single_factor_group_inserts']+powers['calls']
    # Between the first and last step, each carry consumes a full word.
    # A direct write or the last step of an insertion can create one.
    carry_steps = 3*carry_calls+powers['output_words']
    progress = factors//32+GROUPS//16
    per_log = dict(
        setup_and_select=4096+16*WORDS+12*WORDS+360*(factors+1),
        reduction=22*updates['reduction_word_updates'],
        buffer_clearing=(GROUPS+1)*memset_work(2*words)+memset_work(257),
        series_outer_loop=140*GROUPS,
        division=40*(updates['limb_divisions']+GROUPS),
        single_term_scans=20*updates['single_factor_group_inserts'],
        powers=124*powers['calls']+20*powers['rounds']+22*powers['output_words']
               +10*updates['block_power_limb_products'],
        carry=9*carry_steps,
        accumulation=(GROUPS+2*(TABLE_LAST-1)+1)*accumulate,
        progress=256*progress,
    )
    outside_logs = 2048+3*memset_work(2*words)+4*(WORDS+1)*16+32*words+accumulate
    instruction_limit = 2*sum(per_log.values())+outside_logs
    return dict(maximum_thumb_instructions=instruction_limit, instructions_per_log=per_log,
                instructions_outside_logs=outside_logs, maximum_progress_calls=2*progress,
                maximum_carry_iterations_per_log=carry_steps,
                scope='One logarithmic midpoint comparison. Default hardware clock-source callback; '
                      'timer reads complete within one low-word wrap. Interrupt service is excluded.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--bootrom',type=Path,required=True)
    args = parser.parse_args()
    for path,expected in ((args.elf,ELF_SHA256),(args.bootrom,ROM_SHA256),
                          (ROOT/'code/native_eabi_m0_pow_log_side.inc',SOURCE_SHA256)):
        if checksum(path) != expected:
            parser.error(f'bytes differ from the audited image: {path}')
    if not __debug__:
        parser.error('enable arithmetic assertions')
    print(json.dumps(work(),indent=2,sort_keys=True))


if __name__ == '__main__':
    main()
