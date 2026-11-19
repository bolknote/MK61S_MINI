#!/usr/bin/env python3
"""Audit the mixed-residue experiment's exact window and admitted work."""

import argparse
from hashlib import sha256
from math import gcd, prod
import json
from pathlib import Path

from certify_m0_pow_log_side import GAP, ROOT, arithmetic

BUDGET_WORDS = 9216
MODES = (
    ('binary', ('B',)),
    ('binary_minus', ('B', 'B-1')),
    ('binary_plus', ('B', 'B+1')),
    ('odd_pair', ('B-1', 'B+1')),
    ('triple', ('B', 'B-1', 'B+1')),
)


def sign(a):
    return (a > 0)-(a < 0)


def reconstructed(base, rings, residues):
    half = base//2
    if rings == ('B',):
        r = residues['B']
        return 0 if not r else (1 if r < half else -1)
    low = residues.get('B', 0)
    if rings == ('B', 'B-1'):
        a = (residues['B-1']-low) % (base-1)
        high = sign(a-(half-1))
        return 0 if not (a or low) else -(high or (-1 if low < half else 1))
    if rings == ('B', 'B+1'):
        b = (low-residues['B+1']) % (base+1)
        high = sign(b-half)
        return 0 if not (b or low) else -(high or (-1 if low < half else 1))
    a = (residues['B-1']-low) % (base-1)
    b = (low-residues['B+1']) % (base+1) if 'B' in rings else residues['B+1']
    d = (a-b) % (base+1)
    t = (d+(base+1)*(d&1))//2
    if not (t or a or low):
        return 0
    high = sign(t-half) or sign(a-(half-1))
    return -(high or (1 if 'B' in rings and low >= half else -1))


def exhaust_toy_windows():
    checks = 0
    for base in (2,4,8,16,32):
        for _, rings in MODES:
            moduli = {'B':base,'B-1':base-1,'B+1':base+1}
            # At B=2 the first odd modulus degenerates. The experiment
            # has B>=65536; exclude that artificial geometry here.
            if any(moduli[r] <= 1 for r in rings):
                continue
            for i,r in enumerate(rings):
                assert all(gcd(moduli[r],moduli[s]) == 1 for s in rings[:i])
            product = prod(moduli[r] for r in rings)
            last = (product-1)//2
            for d in range(-last,last+1):
                assert reconstructed(base,rings,{r:d%moduli[r] for r in rings}) == sign(d)
                checks += 1
    return checks


def work_bound(rings, words, magnitude_bits):
    """Bound digit products after the proven |ln(A/B)| guard."""
    # Before the j-th remaining square, log2 of the unshifted exact
    # power is < magnitude_bits / 2**j. Reduction never raises it
    # (the special B value in the plus ring uses a short negation).
    squares = (magnitude_bits-1).bit_length()-1
    assert magnitude_bits < 1 << 17 and squares <= 16
    sizes = [min(words,(magnitude_bits+(16<<j)-1)//(16<<j))
             for j in range(squares+1)]
    result = {}
    for ring in rings:
        if ring == 'B':
            # Sum exact triangular Comba counts for a square. The
            # full nonsymmetric multiply uses at most n(n+1)/2 pairs.
            square = sum(sum(max(0,min(used,words-i)-i) for i in range(used))
                         for used in sizes[1:])
            final = words*(words+1)//2
        else:
            square = sum(used*(used+1)//2 for used in sizes[1:])
            final = words*words
        # At most one multiply by the 4-word base per left power bit.
        short = 4*sum(sizes[:-1])
        result[ring] = dict(square_both_powers=2*square, left_short_products=short,
                            inverse_final_product=final,
                            maximum_products=2*square+short+final)
    return result


def certify(budget):
    assert __debug__ and 5 <= budget <= BUDGET_WORDS
    assert arithmetic()['unresolved_gap'] == f'2^-{GAP}' and GAP == 16300
    assert GAP > 116+2
    modes = {}
    maximum_words = 0
    for name,rings in MODES:
        words = budget//(len(rings)+2)-int('B+1' in rings)
        if words < 1:
            continue
        maximum_words = max(maximum_words,words)
        base = 1 << (16*words)
        modulus = prod({'B':base,'B-1':base-1,'B+1':base+1}[r] for r in rings)
        w = modulus.bit_length()-1
        assert (1<<w) <= modulus < (1<<(w+1))
        # W=N+2+k-gap for |D|<2**(W-1). If N+k <= this
        # capacity+gap-2, the modulus product covers both signs.
        nk = w+GAP-2
        work = work_bound(rings,words,nk+1)
        modes[name] = dict(words_per_ring=words, guaranteed_width=w,
                           maximum_n_plus_k=nk,
                           scratch_words=(len(rings)+2)*(words+int('B+1' in rings)),
                           multiplication_bounds_by_ring=work,
                           admitted_limb_products_upper=sum(v['maximum_products'] for v in work.values()))
    # An exact product column has at most n (unordered, or doubled)
    # contributions to the ordinary convolution. Add n*(2^16-1)
    # as a bound on the incoming carry.
    assert maximum_words*65535*65536 < 1 << 44
    assert 1075*((1<<63)+(1<<116))+116+2 < 1 << 127
    source = ROOT/'research/m0-pow-comparison-20261117/mixed_residue.hpp'
    return dict(status='PASS_BOUNDED_ARITHMETIC', gap_bits=GAP, budget_words=budget,
                exhaustive_small_window_checks=exhaust_toy_windows(), modes=modes,
                all_active_inputs_n_upper='2^127 (not a reachability result)',
                practical_all_input_bound_established=False,
                source_sha256=sha256(source.read_bytes()).hexdigest())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--budget-words',type=int,default=BUDGET_WORDS)
    p.add_argument('--json',type=Path)
    args = p.parse_args()
    if not __debug__ or not 5<=args.budget_words<=BUDGET_WORDS:
        p.error('enable assertions and choose a supported scratch budget')
    result = json.dumps(certify(args.budget_words),indent=2)+'\n'
    if args.json:
        with args.json.open('x') as f:
            f.write(result)
    print(result,end='')


if __name__ == '__main__':
    main()
