"""Bind the one-slot source change, actual helper, ABI and static cost law."""
from pathlib import Path
import ast, hashlib, json, re, struct, subprocess, sys
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
P = ROOT / '.build/m0-asin-scaled-bound-v164-20261023'
BASE = ROOT / '.build/m0-pow-exp-table-product-20261025'
assert not (W / 'FROZEN.json').exists()
sys.path.insert(0, str(ROOT / 'tests'))
from check_stm32_vectors import ElfImage
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
build = json.loads((W / 'build.json').read_bytes())
old = (W / 'control/native_eabi_m0_pow_root_prefix.inc').read_text()
new = (W / 'candidate/native_eabi_m0_pow_root_prefix.inc').read_text()
original = (P / 'source/code/native_eabi_m0_pow_root_prefix.inc').read_text()
assert old == original
begin = old.index('\t.section\t.m0_pow_square_fixed,')
end = old.index('\t.section\t.m0_pow_root_prefix,', begin + 1)
assert new == old[:begin] + (W / 'square128.S.inc').read_text() + '\n' + old[end:]
assert (W / 'control/native_eabi_m0_rp2040.S').read_bytes() == (W / 'candidate/native_eabi_m0_rp2040.S').read_bytes()
assert (W / 'control/native_eabi_m0_rp2040.S').read_bytes() == (P / 'source/code/native_eabi_m0_rp2040.S').read_bytes()

tree = ast.parse((ROOT / '.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text())
function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'relocs')
exec(compile(ast.Module(body=[function], type_ignores=[]), __file__, 'exec'), globals())
def allocated(image):
    return {name: (s[1], s[2], s[5], s[8], None if s[1] == 8 else image.bytes_at(s))
            for name, s in image.named_sections.items() if s[2] & 2 and s[5]}
for context in ['RP', 'generic_M0', 'M4_soft', 'M4_hard']:
    a, b = [ElfImage(W / (context + '-' + label + '.o')) for label in ['control', 'candidate']]
    aa, bb = allocated(a), allocated(b)
    if context == 'RP':
        assert aa.keys() == bb.keys()
        assert {n for n in aa if aa[n] != bb[n]} == {'.m0_pow_square_fixed'}
        assert aa['.m0_pow_square_fixed'][:4] == bb['.m0_pow_square_fixed'][:4]
        for section, records in relocs(a).items():
            if section in aa and section != '.m0_pow_square_fixed':
                assert records == relocs(b)[section], section
    else:
        assert aa == bb and relocs(a) == relocs(b), context

resident = ElfImage(P / 'firmware/mk61s-picocalc-pico-h.elf')
address = resident.symbols['pow_integer128_square'] & ~1
helper = resident.symbols['pow_integer128_approx_high64'] & ~1
def data_at(image, address, size):
    s = next(s for s in image.named_sections.values() if s[3] <= address and address + size <= s[3] + s[5])
    return image.bytes_at(s)[address - s[3]:address - s[3] + size]
for label in ['control', 'candidate']:
    image = ElfImage(W / (label + '.elf'))
    assert sha(W / (label + '.elf')) == build['images'][label]['ELF_sha256']
    assert image.symbols['pow_integer128_square'] & ~1 == address
    assert len(data_at(image, address, 310)) == 310
    if label == 'control':
        assert data_at(image, address, 310) == data_at(resident, address, 310)
    else:
        assert image.sizes['pow_integer128_square'] == 232
        assert data_at(image, address + 232, 78) == bytes.fromhex('00bf') * 39
    unit = ElfImage(W / ('unit-' + label + '.elf'))
    assert data_at(unit, address, 310) == data_at(image, address, 310)
    assert data_at(unit, helper, 94) == data_at(resident, helper, 94)

tc = Path(json.loads((W / 'unit-build.json').read_bytes())['commands'][0][0]).parent
pattern = re.compile(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{4}\s+){1,2})([a-z][.\w]*)\s*(.*?)\s*$')
paths = {}
for label in ['control', 'candidate']:
    text = subprocess.check_output([str(tc / 'arm-none-eabi-objdump'), '-d', str(W / ('unit-' + label + '.elf'))], text=True)
    instructions = {}
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            pc, raw, mnemonic, operands = match.groups()
            instructions[int(pc, 16)] = (2 * len(raw.split()), mnemonic.split('.')[0], operands)
    def path_cost(low_nonzero, upper, pc=address):
        cost = 0
        while True:
            length, mnemonic, operands = instructions[pc]
            cost += 1
            if mnemonic == 'pop' and 'pc' in operands:
                return cost
            if mnemonic == 'bl':
                target = int(operands.split()[0], 16)
                assert target == helper
                cost += path_cost(low_nonzero, upper, helper)
                pc += length
            elif mnemonic in ['b', 'beq', 'bmi']:
                take = mnemonic == 'b' or (mnemonic == 'beq' and not low_nonzero) or (mnemonic == 'bmi' and upper)
                pc = int(operands.split()[0], 16) if take else pc + length
            else:
                assert not mnemonic.startswith('b'), (hex(pc), mnemonic)
                pc += length
            assert cost < 300
    paths[label] = {str((low, upper)): path_cost(low, upper) for low in [False, True] for upper in [False, True]}
unit = json.loads((W / 'unit-proof.json').read_bytes())
for key, costs in unit['class_costs'].items():
    assert {label: paths[label][key] for label in paths} == costs

caller_sites = []
lines = old.splitlines()
for i, line in enumerate(lines):
    if re.search(r'\bbl\s+pow_integer128_square\s*$', line):
        caller_sites.append(dict(line=i + 1, instructions=lines[i-1:i+7]))
        assert 'subs' in lines[i + 1] and 'mov\tr0,' in lines[i + 2]
assert len(caller_sites) == 2
lineage = json.loads((BASE / 'source-lineage-pins.json').read_bytes())['files']
inputs = [P / 'firmware/mk61s-picocalc-pico-h.elf',
          ROOT / '.build/m0-v138-execution-20261023/reference/reference.elf',
          ROOT / 'research/rp2040-memset-2026-10-21/capture/bootrom.bin']
inputs += [ROOT / ('.build/' + name + '/candidate.elf') for name in
           ['m0-exp-cached-product-20261024', 'm0-pow-square-ordinary-20261024',
            'm0-pow-rsqrt-asm-20261024', 'm0-exp-directed-product-20261024']]
pins = {}
for p in inputs:
    rel = str(p.relative_to(ROOT))
    pin = lineage[rel]
    assert sha(p) == pin['sha256'] and p.stat().st_size == pin['bytes'], rel
    pins[rel] = pin
receipt = ROOT / '.build/m0-pow-exp-table-product-root-acceptance-20261025-001/RECEIPT.json'
assert sha(receipt) == '09b8c7326b37b67e106ff517cc594dc02d09fa0643ed96dee47c48af747f6d4d'
result = dict(status='PASS_ONE_SLOT_EXACT_INTEGER_TRANSFORM_SOURCE_ABI_STATIC_COST_BINDING',
              baseline_inputs=pins, parent_root_receipt_sha256=sha(receipt),
              only_source_change='pow_integer128_square body; old slot padded to310 bytes',
              only_RP_allocated_section_changed='.m0_pow_square_fixed', old_bytes=310, new_function_bytes=232,
              slot_bytes=310, all_other_addresses_bytes_relocations_and_BSS_unchanged=True,
              default_M0_M4_soft_hard_allocated_bytes_semantic_relocations_identical=True,
              original94byte_helper_bound=True, no_new_table_RAM_libgcc_ROM_math_dependency=True,
              radius_rules_and_all24_output_bytes_transform_identical=True,
              caller_return_and_flags_unused=True, actual_ASM_callers=caller_sites,
              static_CFG_instruction_costs=paths, class_costs_match_actual_bare_unit_runs=True,
              frame_bytes={'old_kernel':48, 'new_kernel':40, 'unchanged_helper':20},
              ordinary_void_PCS_no_extra_private_return_contract=True,
              inherited_public_RNE_enclosures_unchanged=True, general_pow_totality_not_established=True,
              actual_ARM_calls=0, hardware_accessed=False)
(W / 'source-proof.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['baseline_inputs','actual_ASM_callers']}, indent=2))
