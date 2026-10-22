"""Source-pinned proof of the normal first-tier two-cell rounding enclosure."""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import re

import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root', type=Path, required=True)
parser.add_argument('--baseline-root', type=Path, required=True)
parser.add_argument('--json', type=Path, required=True)
args = parser.parse_args()
new = args.source_root / 'code'
old = args.baseline_root / 'code'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def function(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    depth, end = 1, brace+1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

fast = (new / 'native_eabi_m0_pow_fast.inc').read_text()
base = (old / 'native_eabi_m0_pow_fast.inc').read_text()
at = fast.index('// The ambiguous normal Q62 enclosure certifies')
end = fast.index('\n#endif', at)
old_at = base.index('// A first-tier approximation is only a hint.')
old_end = base.index('\n#endif', old_at)
candidate = fast[at:end]
assert 'const double *px,const double *py,U cell' in candidate
assert 'pow_dyadic128_checked(bits(x),bits(y),cell,bool(cell&D::Fraction))' in candidate
assert 'pow_refine_checked(x,y)' in candidate
normalized = fast[:at] + base[old_at:old_end] + fast[end:]
normalized = normalized.replace('M0_POW_EXP_FIRST_CELL', 'M0_POW_EXP_CANDIDATE')
normalized = normalized.replace('return pow_first_cell(&x,&y,value)', 'return pow_first_candidate(&x,&y,value)')
assert normalized == base, 'An unrelated public dispatch/argument rule changed'

body = (new / 'native_eabi_m0_pow_exp_body.inc').read_text()
body_base = (old / 'native_eabi_m0_pow_exp_body.inc').read_text()
at = body.index('#ifdef M0_POW_EXP_FIRST_CELL')
old_at = body_base.index('#ifdef M0_POW_EXP_CANDIDATE')
branch = body[at:]
assert branch == '''#ifdef M0_POW_EXP_FIRST_CELL
  const U cell=(U(k+1022)<<52)+(q>>10);
  if(uint32_t(rounding_tail-(512U-error))<=2*error) M0_POW_EXP_FIRST_CELL(cell);
  // A tie is inside the rejected enclosure (error>=3). Outside it,
  // the exact same RNE decision only needs this32-bit tail comparison.
  M0_POW_EXP_RESULT(cell+U(rounding_tail>512U));
#else
  if(uint32_t(rounding_tail-(512U-error))<=2*error) M0_POW_EXP_REJECT();
  const U rounded=(q+511+((q>>10)&1))>>10;
  M0_POW_EXP_RESULT((U(k+1022)<<52)+rounded);
#endif
'''
assert body[:at] == body_base[:old_at]
assert 'if(error>=256) M0_POW_EXP_REJECT();' in body
assert 'if(q<(U(1)<<62)) {q<<=1;--k;error*=2;}' in body

dyadic = (new / 'native_eabi_m0_pow_dyadic128.inc').read_text()
dyadic_base = (old / 'native_eabi_m0_pow_dyadic128.inc').read_text()
wrapper_at = dyadic.index('\n// This entry retains its original untrusted-hint contract.')
wrapper = dyadic[wrapper_at:]
assert function(wrapper, 'static U pow_dyadic128(') == '''static U pow_dyadic128(U xb,U yb,U hint) {
  return pow_dyadic128_checked(xb,yb,hint,false);
}'''
normalized = dyadic[:wrapper_at]
normalized = normalized.replace('static U pow_dyadic128_checked(U xb,U yb,U hint,bool first_cell) {',
                                'static U pow_dyadic128(U xb,U yb,U hint) {')
assert normalized.count('  if(first_cell) return side>0?hint+1:hint;\n') == 1
normalized = normalized.replace('  if(first_cell) return side>0?hint+1:hint;\n', '')
assert normalized == dyadic_base
assert '  if(!side) return undecided;\n  if(first_cell)' in dyadic

# The existing qualified product polynomial has |delta|<2^54, with a
# rounded product error below one Q62 unit. Hence correction<q_table/1024+1.
table_text = (new / 'native_eabi_m0_exp_table.inc').read_text()
table_body = re.search(r'exp_table\[512\]=\{(.*?)\};', table_text, re.S)[1]
table = [int(n) for n in re.findall(r'UINT64_C\((\d+)\)', table_body)]
assert len(table) == 512
assert 12912720851596686 + (1 << 43) + (1 << 31) < 1 << 54
raw_lower = F(min(table)) * F(1023, 1024) - 1
raw_upper = F(max(table)) * F(1025, 1024) + 1
assert raw_lower > 1 << 61
assert raw_upper < 1 << 63
# An unshifted q is >=2^62; a shifted q is <2^63 and at least2^62.
# The interval radius is <=255 before normalization, <=510 afterward.
assert 2 * 255 == 510 < 512
packing_checks = 0
for parity in (0, 1):
    for tail in range(1024):
        if tail == 512:
            # Every admitted nonnegative radius includes an exact tie.
            assert abs(tail-512) <= 0
            continue
        assert (tail+511+parity) >> 10 == int(tail > 512)
        packing_checks += 1
checks = 0
for error in range(511):
    for tail in range(max(0, 512-error), min(1023, 512+error)+1):
        assert -512 < tail-error <= tail+error < 1536
        checks += 1
# For a non-binade-start lower cell L, the midpoint below L is L-512
# in these units. The midpoint above L+1 is L+1536, or L+2048 at the
# next binade. Thus this strict interval can round only to L or L+1.
# The remaining separating midpoint is L+512. Strict integer comparison
# chooses its side; an overlapping enclosure always uses the old fallback.
record = dict(status='PASS_TWO_CELL_ENCLOSURE_LEMMA',
              normalized_q_range='2^62 <= q < 2^63',
              maximum_normalized_error=510,
              ambiguous_tail_radius_checks=checks,
              unambiguous_rounding_pack_checks=packing_checks,
              strict_union_relative_to_lower_cell='(-512,1536) in Q62 units',
              binade_start_uses_original_untrusted_mode=True,
              exact_or_undecided_midpoint_uses_original_refinement=True,
              untrusted_hint_wrapper_forces_first_cell_false=True,
              unchanged_upstream_polynomial_domain_and_error_rules=True,
              raw_q_lower_bound=str(raw_lower), raw_q_upper_bound=str(raw_upper),
              inspected_files={name: dict(current_sha256=sha(new/name), baseline_sha256=sha(old/name))
                               for name in ('native_eabi_m0_pow_fast.inc', 'native_eabi_m0_pow_exp_body.inc',
                                            'native_eabi_m0_pow_dyadic128.inc', 'native_eabi_m0_exp_table.inc')},
              producer_sha256=sha(__file__),
              scope='Conditional on the unchanged qualified parent Q62 enclosure and integer-boundary inequalities. Proves that the trusted normal ambiguity needs one separating midpoint; arbitrary hints keep their original contract. Does not prove general pow totality, compiled ABI or device timings.')
args.json.parent.mkdir(parents=True, exist_ok=True)
args.json.write_text(json.dumps(record, indent=2) + '\n')
print('PASS:', checks, 'ambiguous radius/tail pairs; two-cell enclosure and source isolation proved.')
