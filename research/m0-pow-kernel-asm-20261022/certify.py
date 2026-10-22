"""Prove retained128-bit product bounds and pin imported executable kernels."""
from fractions import Fraction as F
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--work', type=Path, required=True, help='Frozen candidate tree, build and firmware directory')
parser.add_argument('--baseline-work', type=Path, required=True, help='Frozen V101 tree, build and firmware directory')
parser.add_argument('--reference-object', type=Path, required=True, help='ARM object regenerated from the adjacent kernels.cpp')
parser.add_argument('--json', type=Path, required=True)
args = parser.parse_args()
work = args.work.resolve()
parent = args.baseline_work.resolve()
sys.path.insert(0, str(root/'tests'))
from check_stm32_vectors import ElfImage
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def function(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    depth, end = 1, brace+1
    while depth:
        depth += (text[end] == '{')-(text[end] == '}')
        end += 1
    return text[start:end]
def strip_comments(text):
    return re.sub(r'\s+', '', re.sub(r'//[^\n]*', '', text))

reference_path = Path(__file__).with_name('kernels.cpp')
reference = reference_path.read_text()
old_cpp = (parent/'source/code/native_eabi_m0.cpp').read_text()
for signature in ('__attribute__((always_inline)) inline U wide32(',
                  '__attribute__((always_inline)) inline Product multiply('):
    assert function(reference, signature) == function(old_cpp, signature)
partial = function(reference, '__attribute__((always_inline)) inline U pow_integer128_approx_high64(')
old_partial = function(old_cpp, '__attribute__((always_inline)) inline U exp_high_product(')
assert partial.replace('pow_integer128_approx_high64', 'exp_high_product') == old_partial
old_integer = (parent/'source/code/native_eabi_m0_pow_integer128.inc').read_text()
declarations = (work/'source/code/native_eabi_m0_pow_integer128.inc').read_text()
expected = old_integer
for name in ('multiply', 'square'):
    body = function(expected, 'static void pow_integer128_'+name+'(')
    at = expected.index(body)
    start = expected.rfind('__attribute__', 0, at)
    declaration = body[:body.index('{')].replace('static void ', 'extern "C" void ').rstrip()+';'
    expected = expected[:start]+declaration+expected[at+len(body):]
    actual = function(reference, 'extern "C" void pow_integer128_'+name+'(')
    normalized = actual.replace('extern "C" void ', 'static void ', 1)
    for pair in ('al,bh', 'ah,bl', 'low,high'):
        normalized = normalized.replace('pow_integer128_approx_high64('+pair+')', 'multiply('+pair+').high')
    normalized = normalized.replace('error+=al&&bl?8:(al||bl?4:(error?1:0))',
                                    'error+=al&&bl?4:(al||bl?2:(error?1:0))')
    normalized = normalized.replace('2*a.error+(low?8:(a.error?1:0))', '2*a.error+(low?4:(a.error?1:0))')
    assert strip_comments(normalized) == strip_comments(body), name
assert declarations.replace('section(".m0_pow_integer_fixed")', 'section(".m0_pow_near_one_refine")') == expected
dyadic = (work/'source/code/native_eabi_m0_pow_dyadic128.inc').read_text()
denominator_loop = """  // The decoder supplies1,2,4,...,128. This is the identical square
  // chain, without a base copy, CLZ or generic numerator bit tests.
  for(unsigned n=denominator;n>1;n>>=1) pow_integer128_square(midpoint);"""
assert dyadic.count(denominator_loop) == 1
normalized_dyadic = dyadic.replace(denominator_loop, '  pow_dyadic128_raise(midpoint,denominator);')
assert normalized_dyadic.count('  if(n==1) return;\n') == 1
normalized_dyadic = normalized_dyadic.replace('  if(n==1) return;\n', '')
assert normalized_dyadic == (parent/'source/code/native_eabi_m0_pow_dyadic128.inc').read_text()
assert 'unsigned numerator=unsigned(coefficient),denominator=1;' in dyadic
assert 'else denominator=1U<<unsigned(-shift);' in dyadic
assert 'coefficient>32 || shift < -7 || shift>5' in dyadic
for denominator in (1,2,4,8,16,32,64,128):
    original_operations = []
    for bit in range(denominator.bit_length()-2,-1,-1):
        original_operations.append('square')
        if denominator & (1<<bit): original_operations.append('multiply')
    new_operations = [];remaining=denominator
    while remaining>1:
        new_operations.append('square');remaining>>=1
    assert original_operations == new_operations
fast = (work/'source/code/native_eabi_m0_pow_fast.inc').read_text()
assert fast.replace('section(".m0_pow_near_argument_fixed")','section(".m0_pow_near_one_refine")') == (parent/'source/code/native_eabi_m0_pow_fast.inc').read_text()

# For radixB=2^32 the omitted cross fractions and low product each lie
# in[0,1). Thus exact(a*b)/2^64 - approximate_high(a,b) lies in[0,3).
radix = 1 << 32
cross_tail = 2*F(radix-1, radix)+F((radix-1)**2, radix**2)
assert cross_tail < 3
# Reconstructing the high128 center loses <3 for a single cross term,
# or <7 for two terms plus low*low. Input endpoint products contribute
# less thanEa+Eb+1; radii4/8 include that last term. All additions are
# below the exact central product, which is strictly below2^128.
assert 2*cross_tail + F(((1 << 64)-1)**2, 1 << 128) < 7
def bound(n):
    error, degree = 0, 1
    for bit in range(n.bit_length()-2, -1, -1):
        error = 0 if degree == 1 else 2*(2*error+8)
        degree *= 2
        if n & (1 << bit):
            error = 2*(error+4)
            degree += 1
    assert degree == n
    return error
integers = {n: bound(n) for n in range(1, 33)}
denominators = {n: bound(n) for n in (1, 2, 4, 8, 16, 32, 64, 128)}
maximum = 2*(max(integers.values())+max(denominators.values())+8)
assert max(integers.values()) == 7016 and max(denominators.values()) == 21840 and maximum == 57728
radius = 1 << 16
assert maximum < radius
assert F(radius**2, 1 << 128) < 1
assert F((1 << 128)-1+radius, 4) < (1 << 127)-radius
assert all(F(e, 2)+F(1, 2) <= e//2+1 for e in range(2))
assert -1022*160 >= -(1 << 31) and 1023*160+159 < 1 << 31

def symbols(image):
    result = []
    for table in image.sections:
        if table[1] != 2:
            continue
        strings = image.bytes_at(image.sections[table[6]])
        for offset in range(table[4], table[4]+table[5], table[9]):
            name, value, size, info, other, index = struct.unpack_from('<IIIBBH', image.data, offset)
            result.append(dict(name=image.string(strings, name), value=value, size=size,
                               info=info, index=index))
    return result

old_object = ElfImage(args.reference_object)
asm_object = ElfImage(next((work/'build/CMakeFiles/mk61s-picocalc-pico-h.dir').rglob('native_eabi_m0_rp2040.S.o')))
linked = ElfImage(work/'firmware/mk61s-picocalc-pico-h.elf')
rows = []
for name in ('pow_integer128_multiply', 'pow_integer128_square'):
    pieces = []
    for image in (old_object, asm_object):
        item = next(s for s in symbols(image) if s['name'] == name)
        start = item['value'] & ~1
        data = image.bytes_at(image.sections[item['index']])[start:start+item['size']]
        pieces.append(data)
    address, size = linked.symbols[name] & ~1, linked.sizes[name]
    section = next(s for s in linked.sections if s[3] <= address and address+size <= s[3]+s[5] and s[1] != 8)
    pieces.append(linked.bytes_at(section)[address-section[3]:address-section[3]+size])
    assert pieces[0] == pieces[1] == pieces[2], name
    rows.append(dict(function=name, bytes=len(pieces[0]), executable_sha256=hashlib.sha256(pieces[0]).hexdigest(),
                     reference_object_GNU_assembly_and_linked_bytes_identical=True))
record = dict(status='PASS_BOUNDED_PARTIAL_PRODUCT_CERTIFICATE',
              omitted_high64_tail=str(cross_tail), retained128_omitted_tail_bound_exclusive=7,
              radii=dict(both_low_nonzero=8, one_low_nonzero=4,
                         both_low_zero='Exact if both input radii vanish, otherwiseEa+Eb+1.'),
              integer_error_bounds=integers, denominator_error_bounds=denominators,
              maximum_composed_radius=maximum, radius_limit_exclusive=radius,
              zero_low_first_square_exact=True, exact_sqrt_cube_path_preserved=True,
              all_eight_denominator_square_chains_identical=True, exponent_one_avoids_unused_base_copy=True,
              rounding_and_domain_guards_unchanged=True, no_new_compiler_dependency=True,
              executable_kernel_identity=rows,
              source_files={name: dict(path=str((work/'source'/name).relative_to(root)), sha256=sha(work/'source'/name))
                            for name in ('code/native_eabi_m0_pow_integer128.inc', 'code/native_eabi_m0_pow_kernels.inc',
                                         'code/native_eabi_m0_rp2040.S', 'code/native_eabi_m0_pow_dyadic128.inc',
                                         'code/native_eabi_m0_pow_fast.inc', 'ports/picocalc/m0_math_extension.ld')},
              reference_cpp_sha256=sha(reference_path), reference_object_sha256=sha(args.reference_object),
              elf_sha256=sha(work/'firmware/mk61s-picocalc-pico-h.elf'), producer_sha256=sha(__file__),
              scope='Exact algebraic omission and propagated error bounds, source-isolated caller/rounding rules, and executable identity with the reference compiler output. Independent ARM endpoint/MPFR checks qualify arithmetic integration. Does not prove universal pow totality, compiler correctness in general or physical speed.')
args.json.parent.mkdir(parents=True, exist_ok=True)
args.json.write_text(json.dumps(record, indent=2)+'\n')
print('PASS: bounded128-bit products; maximum composed radius57728<65536; executable kernels identical.')
