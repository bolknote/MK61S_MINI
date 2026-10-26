"""Bare helper check: component plus only its pinned184-byte product kernel."""
from fractions import Fraction as F
from pathlib import Path
from collections import Counter
import hashlib
import json
import random
import struct
import sys
import time

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
P = ROOT / '.build/m0-asin-scaled-bound-v164-20261023'
sys.path.insert(0, str(ROOT / '.build/m0-float-fma-qualification-20261023/support'))
from native_eabi_m0_arm_self_test import Machine, SP
from check_stm32_vectors import ElfImage
from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


build = json.loads((W/'candidate-build.json').read_text())
assert sha(W/'candidate.elf') == build['ELF_sha256']
assert sha(W/'native_eabi_m0_log70_center.inc') == build['source_include_sha256']
resident = ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf')
name = 'mk61_m0_log_product46'
address, size = resident.symbols[name] & ~1, resident.sizes[name]
section = next(s for s in resident.named_sections.values() if s[3] <= address < s[3]+s[5])
code = resident.bytes_at(section)[address-section[3]:address-section[3]+size]
assert len(code) == size == 184
m = Machine(W/'candidate.elf', True, stack_bytes=128)
m.uc.mem_write(address, code)
m.elf.symbols['seed_product'] = resident.symbols[name]
sio = [0]


def access(*args):
    sio[0] += 1


m.uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, access, begin=0xd0000060, end=0xd000007b)
table_name = next(n for n in m.elf.symbols if 'log10_table' in n)
table_addr = m.elf.symbols[table_name]
states = [struct.pack('<7I', 0, 0, 0, 0, 0, 0, 1), struct.pack('<7I', 17, 3, 17, 3, 5, 2, 3)]
rng = random.Random(0x10770D17)
digest = hashlib.sha256()
calls, pairs, costs = 0, 0, []
corrections = Counter()
minimum, maximum = F(0), F(0)
start = time.monotonic()
for index in range(1024):
    den = 2049+2*index
    row = struct.unpack('<4I', m.uc.mem_read(table_addr+index*16, 16))
    reciprocal = (row[1] << 32) | (row[0] & ~63)
    assert reciprocal == ((1 << 75)//den) & ~63
    jobs = {0, 1, 2, 3, den-1, den, den+1, (1 << 41)-1, 1 << 41}
    jobs.update((v for high in (1,255,510,511,512) for low in (-2,-1,0,1,2) if 0<=(v:=(high<<32)+low)<=(1<<41)))
    for bit in (11, 16, 24, 31, 32, 40):
        jobs.update(((1 << bit)-1, 1 << bit, (1 << bit)+1))
    center = ((1 << 41)//den)*den
    jobs.update((center-1, center, min(center+1, 1 << 41)))
    for _ in range(8):
        jobs.add(rng.randrange((1 << 41)+1))
    for delta in sorted(jobs):
        exact = (delta << 29)//den
        H = F(delta << 29, den)
        pairs += 1
        for state_index, state in enumerate(states):
            m.uc.mem_write(0xd0000060, state)
            seed = m.call('seed_product', delta, reciprocal)[0]
            err = F(seed)-H
            assert abs(err) < F(13, 2)+F(1, 1 << 14)
            residue = (delta << 29)-seed*den
            assert -(1 << 31) <= residue < 1 << 31
            enabled = index in (0, 511, 1023)
            result, _, count = m.call('mk61_m0_log_ratio70_slow', delta, den, count=enabled)
            assert result == exact, (index, delta, result, exact)
            assert abs(result-seed) <= 7
            assert bytes(m.uc.mem_read(0xd0000060, 28)) == state
            digest.update(struct.pack('<QIQQB', delta, den, seed, result, state_index))
            minimum, maximum = min(minimum, err), max(maximum, err)
            corrections[result-seed] += 1
            if enabled:
                costs.append(count)
            calls += 2
assert sio[0] == 0
out = dict(status='PASS_EXACT_DIRTY_LOG_RATIO_BARE_ARM_ALL_DENOMINATORS',
           pairs=pairs, denominators=1024, actual_ARM_calls=calls,
           all_results_exact_integer_floor=True, source_sha256=build['source_include_sha256'],
           candidate_ELF_sha256=build['ELF_sha256'],
           additional_loaded_seed_code_bytes=size, additional_loaded_seed_code_sha256=hashlib.sha256(code).hexdigest(),
           firmware_or_ROM_mapped=False, seed_capsule_from_pinned_resident_ELF=True,
           SIO_accesses=sio[0], both_SIO_states_preserved_every_call=True,
           PCS_SP_and_bounded_writes_checked_every_call=True,
           observed_stack_bytes=SP-m.stack_lowest,
           helper_instruction_range=[min(costs), max(costs)], profiled_helper_calls=len(costs),
           observed_seed_error_min=str(minimum), observed_seed_error_max=str(maximum),
           corrections_relative_to_generic_product_seed=dict(sorted(corrections.items())),
           dyadic_endpoint_helper_calls=4096, transcript_sha256=digest.hexdigest(),
           hardware_accessed=False, elapsed_seconds=time.monotonic()-start,
           full_public_qualification_or_independent_review=False)
(W/'helper-proof.json').write_text(json.dumps(out, indent=2)+'\n')
print(json.dumps(out, indent=2))
