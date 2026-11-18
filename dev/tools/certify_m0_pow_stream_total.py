#!/usr/bin/env python3
"""Bound the exact pow comparator's DAG, indices and tracked work."""
import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

SOURCE = Path(__file__).resolve().parents[2] / 'code/native_eabi_m0_pow_stream.inc'


@dataclass(frozen=True)
class Node:
    bits: int
    depth: int = 0
    work: int = 0

    @property
    def words(self):
        return (self.bits+15)//16

    def multiply(self, right):
        bits = self.bits+right.bits
        words = (bits+15)//16
        pairs = self.words*right.words
        # A prefix visits each column once and each digit pair at most
        # once. Each column takes up to two outer dispatches and each pair
        # takes up to three plus the two requests for child digits.
        # This also dominates the other routes for a single digit, since
        # one window column delegates at most one child digit.
        work = 2*words+pairs*(3+self.work+right.work)
        return Node(bits, 1+max(self.depth, right.depth), work)


def power(bit_width):
    """Dominate a p-chain with this many bits by setting every bit of p."""
    base = node = Node(53)
    for _ in range(bit_width-1):
        node = node.multiply(node).multiply(base)
    return node


def power_of_two(squarings):
    node = Node(54)
    for _ in range(squarings):
        node = node.multiply(node)
    return node


def bound(p_bits, k, inverse, retained_words):
    p_max = (1 << p_bits)-1
    q = 1 << k
    # Bound the magnitudes of both scales, their gap, and the bit
    # estimate added to either signed scale during early comparison.
    gap = 1074*p_max+1075*q
    left, right = power(p_bits), power_of_two(k)
    nodes = 2+2*(p_bits-1)+k
    if inverse:
        left, right = left.multiply(right), Node(1)
        nodes += 1
    bits = max(left.bits, right.bits)
    assert bits+gap < 1 << 127
    # One extra digit accounts for a shift that straddles a radix word.
    scan = (gap+bits+15)//16+1
    # Materialize only when both inputs fit and are already retained.
    # Each product has L+R <= retained_words, hence L*R <= floor(N*N/4).
    materialize = (nodes-2)*(retained_words+(retained_words**2)//4)
    work = materialize+scan+left.words*left.work+right.words*right.work
    return dict(nodes=nodes, frames=max(left.depth, right.depth), scan_columns_lt=scan.bit_length(),
                tracked_steps_lt=work.bit_length())


def certify(source=SOURCE):
    data = source.read_bytes()

    def constant(name):
        match = re.search(rb'\bconstexpr unsigned '+name.encode()+rb' = (\d+);', data)
        assert match is not None, name
        return int(match[1])

    assert constant('RadixBits') == 16
    assert constant('ProgressInterval') == 1024
    retained = constant('MaterializedWords')
    # The active finite range is 2**-64 <= |y| < 2**63.
    # A nonintegral y has at most 53 numerator bits and k <= 64+52.
    classes = {}
    for name, p_bits, k in (('integer', 63, 0), ('fraction', 53, 116)):
        for inverse in (False, True):
            key = f'{name}_{"negative" if inverse else "positive"}'
            classes[key] = bound(p_bits, k, inverse, retained)
    assert max(row['nodes'] for row in classes.values()) <= constant('NodeCount') <= 256
    assert max(row['frames'] for row in classes.values()) <= constant('MaximumDepth')
    return dict(source_sha256=sha256(data).hexdigest(), classes=classes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    report = certify()
    if args.json:
        args.json.write_text(json.dumps(report, indent=2)+'\n')
    for key, row in report['classes'].items():
        print(f'{key}: {row["nodes"]} nodes, {row["frames"]} frames, '
              f'<2**{row["scan_columns_lt"]} scan columns, '
              f'<2**{row["tracked_steps_lt"]} tracked steps')


if __name__ == '__main__':
    main()
