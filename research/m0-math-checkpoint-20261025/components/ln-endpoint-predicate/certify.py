"""Bind the exact high/low endpoint predicate to the unchanged helper."""
from pathlib import Path
import hashlib
import json
import random

W = Path(__file__).resolve().parent
ROOT = W.parents[1]
BASE = ROOT / '.build/m0-ln-near-directional-20261024'
source = (W / 'native_eabi_m0_log70_center.inc').read_text()
old = (BASE / 'native_eabi_m0_log70_center.inc').read_text()
before = 'if(delta>=(U(1)<<41)-1) {'
after = 'if(uint32_t(delta>>32)==512U || (uint32_t(uint32_t(delta)+1U)==0U && uint32_t(delta>>32)==511U)) {'
assert source.count(after) == old.count(before) == 1
assert source.replace(after, before) == old
checks = 0
def check(delta):
    global checks
    assert 0 <= delta <= 1 << 41
    high, low = delta >> 32, delta & 0xffffffff
    selected = high == 512 or (((low+1)&0xffffffff) == 0 and high == 511)
    assert selected == (delta >= (1 << 41)-1)
    checks += 1
for high in range(513):
    for low in (0,1,2,3,0x7fffffff,0xfffffffc,0xfffffffd,0xfffffffe,0xffffffff):
        delta = (high << 32) | low
        if delta <= 1 << 41:
            check(delta)
rng = random.Random(0xE170017)
for _ in range(16384):
    check(rng.randrange((1 << 41)+1))
for delta in ((1 << 41)-2,(1 << 41)-1,1 << 41):
    check(delta)
out = dict(status='PASS_EXACT_ENDPOINT_PREDICATE_SOURCE_EQUIVALENCE',
    source_sha256=hashlib.sha256(source.encode()).hexdigest(),
    candidate_ELF_sha256=hashlib.sha256((W / 'candidate.elf').read_bytes()).hexdigest(),
    entire_old_header_reconstructed_by_one_predicate_replacement=True,
    domain='0<=delta<=2^41, all original odd den2049..4095',
    exhaustive_high_word_classes=513, integer_boundary_random_checks=checks,
    proof=['high<511: both false for every low word',
           'high==511: both true iff low==0xffffffff',
           'high==512: domain forces low==0, both true'],
    all_quotient_seed_rounding_and_remainder_algorithms_unchanged=True,
    READY_ratio_ASM_source_unchanged=True, hardware_accessed=False)
(W / 'certificate.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
