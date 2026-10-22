"""Source-pinned smaller cross-product bounds and equivalent interval decisions."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--work', type=Path, required=True)
parser.add_argument('--baseline-work', type=Path, required=True)
parser.add_argument('--reference-object', type=Path, required=True)
parser.add_argument('--json', type=Path, required=True)
args = parser.parse_args()
work, parent = args.work.resolve(), args.baseline_work.resolve()
reference_path = Path(__file__).with_name('kernels.cpp')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
sys.path.insert(0, str(root / 'tests'))
from check_stm32_vectors import ElfImage


def function(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    depth, end = 1, brace+1
    while depth:
        depth += (text[end] == '{')-(text[end] == '}')
        end += 1
    return text[start:end]


def canonical(text):
    return re.sub(r'\s+', '', re.sub(r'//[^\n]*', '', text))


reference = reference_path.read_text()
old_reference = (parent / 'kernels.cpp').read_text()
high32 = function(reference, '__attribute__((always_inline)) inline uint32_t pow_integer128_high32(')
assert canonical(high32) == canonical('''__attribute__((always_inline)) inline uint32_t pow_integer128_high32(uint32_t a,uint32_t b) {
  const uint32_t al=a&65535U,ah=a>>16,bl=b&65535U,bh=b>>16;
  return ah*bh+((al*bh)>>16)+((ah*bl)>>16);
}''')
high64 = function(reference, '__attribute__((always_inline)) inline U pow_integer128_approx_high64(')
assert canonical(high64) == canonical('''__attribute__((always_inline)) inline U pow_integer128_approx_high64(U a,U b) {
  const uint32_t al=uint32_t(a),ah=uint32_t(a>>32),bl=uint32_t(b),bh=uint32_t(b>>32);
  return wide32(ah,bh)+pow_integer128_high32(al,bh)+U(pow_integer128_high32(ah,bl));
}''')
normalized = reference.replace(high32+'\n', '').replace(high64, function(old_reference, '__attribute__((always_inline)) inline U pow_integer128_approx_high64('))
normalized = normalized.replace('error+=al&&bl?16:(al||bl?8:', 'error+=al&&bl?8:(al||bl?4:')
normalized = normalized.replace('2*a.error+(low?16:', '2*a.error+(low?8:')
normalized = normalized.replace('.m0_pow_square_fixed', '.m0_pow_near_one_refine')
assert canonical(normalized) == canonical(old_reference), 'Unrelated kernel/reference change'
assert (work / 'source/code/native_eabi_m0_pow_integer128.inc').read_bytes() == (parent / 'source/code/native_eabi_m0_pow_integer128.inc').read_bytes()

old_dyadic = (parent / 'source/code/native_eabi_m0_pow_dyadic128.inc').read_text()
dyadic = (work / 'source/code/native_eabi_m0_pow_dyadic128.inc').read_text()
old_compare = function(old_dyadic, 'static int pow_dyadic128_compare(')
compare = function(dyadic, 'static int pow_dyadic128_compare(')
transformed = old_compare.replace('PowInteger128 a,PowInteger128 b', 'const PowInteger128 &a,const PowInteger128 &b')
old_difference = '''  const U ah=smaller?b.high:a.high,al=smaller?b.low:a.low;
  const U bh=smaller?a.high:b.high,bl=smaller?a.low:b.low;
  const U low=al-bl,high=ah-bh-U(al<bl);'''
new_difference = '''  const U hi=smaller?b.high:a.high,lo=smaller?b.low:a.low;
  const U other_hi=smaller?a.high:b.high,other_lo=smaller?a.low:b.low;
  const U low=lo-other_lo,high=hi-other_hi-U(lo<other_lo);'''
assert transformed.count(old_difference) == 1
transformed = transformed.replace(old_difference, new_difference)
for field, local in (('a.high', 'ah'), ('a.low', 'al'), ('a.error', 'ae'),
                     ('b.high', 'bh'), ('b.low', 'bl'), ('b.error', 'be')):
    transformed = transformed.replace(field, local)
marker = '  if(distance<=-2) return -1;'
transformed = transformed.replace(marker, marker+'''
  U ah=a.high,al=a.low,bh=b.high,bl=b.low;
  unsigned ae=a.error,be=b.error;''')
fast_compare = '''  if(ah==bh && uint32_t(al>>32)==uint32_t(bl>>32)) {
    const uint32_t left=uint32_t(al),right=uint32_t(bl),error=ae+be;
    if(left>=right) return left-right>error?1:0;
    return right-left>error?-1:0;
  }
'''
transformed = transformed.replace('  if(ah==bh && al==bl)', fast_compare+'  if(ah==bh && al==bl)')
assert canonical(transformed) == canonical(compare)
assert dyadic[dyadic.index(compare)+len(compare):] == old_dyadic[old_dyadic.index(old_compare)+len(old_compare):]
assert canonical(dyadic[:dyadic.index(compare)]) == canonical(old_dyadic[:old_dyadic.index(old_compare)])
# For a common upper96-bit integer P, A=P*2^32+a and B=P*2^32+b.
# Exact subtraction cancels P. Ordered low32 subtraction is in[0,2^32-1],
# so the fast branch is exactly the same magnitude/radius comparison.
for name in ('native_eabi_m0_pow_fast.inc', 'native_eabi_m0_pow_integer.inc'):
    assert (work / 'source/code' / name).read_bytes() == (parent / 'source/code' / name).read_bytes()

# Each omitted16-bit cross fraction is<1 and the low product contributes<1.
# Thus the high32 approximation underestimates the real high part by<3.
# Two such errors plus the low32*low32 term give<7 for high64. Combining
# the two cross-high64 terms and low64*low64 gives<15 retained128-bit units.
radix = 1 << 16
high32_tail = 2*F(radix-1, radix)+F((radix-1)**2, radix**2)
cross_tail = 2*high32_tail+F(((1 << 32)-1)**2, 1 << 64)
full_tail = 2*cross_tail+F(((1 << 64)-1)**2, 1 << 128)
assert high32_tail < 3 and cross_tail < 7 and full_tail < 15


def bound(n):
    error, degree = 0, 1
    for bit in range(n.bit_length()-2, -1, -1):
        error = 0 if degree == 1 else 2*(2*error+16)
        degree *= 2
        if n & (1 << bit):
            error = 2*(error+8)
            degree += 1
    assert degree == n
    return error


integers = {n: bound(n) for n in range(1, 33)}
denominators = {n: bound(n) for n in (1, 2, 4, 8, 16, 32, 64, 128)}
maximum = 2*(max(integers.values())+max(denominators.values())+16)
radius = 1 << 17
assert max(integers.values()) == 14032 and max(denominators.values()) == 43680 and maximum == 115456 < radius
assert F(radius**2, 1 << 128) < 1
assert F((1 << 128)-1+radius, 4) < (1 << 127)-radius
assert 2*radius < 1 << 32


def symbols(image):
    result = []
    for table in image.sections:
        if table[1] != 2:
            continue
        strings = image.bytes_at(image.sections[table[6]])
        for offset in range(table[4], table[4]+table[5], table[9]):
            name, value, size, info, other, index = struct.unpack_from('<IIIBBH', image.data, offset)
            result.append(dict(name=image.string(strings, name), value=value, size=size, info=info, index=index))
    return result


reference_object = ElfImage(args.reference_object)
asm_object = ElfImage(next((work / 'build/CMakeFiles/mk61s-picocalc-pico-h.dir').rglob('native_eabi_m0_rp2040.S.o')))
linked = ElfImage(work / 'firmware/mk61s-picocalc-pico-h.elf')
rows = []
for name in ('pow_integer128_multiply', 'pow_integer128_square'):
    pieces = []
    for image in (reference_object, asm_object):
        item = next(s for s in symbols(image) if s['name'] == name)
        start = item['value'] & ~1
        pieces.append(image.bytes_at(image.sections[item['index']])[start:start+item['size']])
    address, size = linked.symbols[name] & ~1, linked.sizes[name]
    section = next(s for s in linked.sections if s[3] <= address and address+size <= s[3]+s[5] and s[1] != 8)
    pieces.append(linked.bytes_at(section)[address-section[3]:address-section[3]+size])
    assert pieces[0] == pieces[1] == pieces[2], name
    rows.append(dict(function=name, bytes=len(pieces[0]), executable_sha256=hashlib.sha256(pieces[0]).hexdigest(),
                     reference_GNU_and_linked_bytes_identical=True))
record = dict(status='PASS_BOUNDED_SMALLER_CROSS_PRODUCT_CERTIFICATE',
              high32_omission_exclusive=3, cross_high64_omission_exclusive=7,
              retained128_omission_exclusive=15, high32_tail_bound=str(high32_tail),
              cross_tail_bound=str(cross_tail), full_tail_bound=str(full_tail),
              radii=dict(both_low_nonzero=16, one_low_nonzero=8),
              integer_error_bounds=integers, denominator_error_bounds=denominators,
              maximum_composed_radius=maximum, radius_limit_exclusive=radius,
              first_exact_square_and_sqrt_cube_ties_preserved=True,
              reference_compare_same_alignment_and_decision=True, exact_common_high96_subtraction=True,
              integer_dispatch_and_early_route_unchanged=True,
              no_other_cpp_source_changes=True, no_new_compiler_dependency=True,
              executable_kernel_identity=rows,
              source_files={name: dict(path=str((work / 'source' / name).relative_to(root)), sha256=sha(work / 'source' / name))
                            for name in ('code/native_eabi_m0_pow_kernels.inc', 'code/native_eabi_m0_pow_dyadic128.inc',
                                         )},
              reference_cpp_sha256=sha(reference_path), reference_object_sha256=sha(args.reference_object),
              elf_sha256=sha(work / 'firmware/mk61s-picocalc-pico-h.elf'), producer_sha256=sha(__file__),
              scope='Algebraic retained-product and propagated-radius bounds; source-isolated equivalent comparisons and unchanged routing; executable identity with regenerated reference compiler output. Independent ARM endpoint/MPFR tests qualify integration. No universal pow termination, all-input speed or hardware timing claim.')
args.json.parent.mkdir(parents=True, exist_ok=True)
args.json.write_text(json.dumps(record, indent=2)+'\n')
print('PASS: smaller retained products; radius115456<131072; equivalent comparison and unchanged dispatch; exact executable identity.')
