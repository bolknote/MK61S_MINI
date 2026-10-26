"""Generate additional guard/midpoint neighbours; these are not MPFR gold."""
from pathlib import Path
import ctypes as C, gzip, hashlib, json, struct, sys
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent; ROOT = W.parents[1]
P = ROOT / '.build/m0-math-unified-exp-row0-small-r37-qualification-20261026'
S = ROOT / '.build/m0-math-unified-exp-row0-midpoint-r38-20261026'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(P / 'FROZEN.json') == '00dc5efa117f764392cacc06a7d97145ba9cca7650909dd4fc6b68cda5bae8e4'
assert sha(S / 'FROZEN.json') == 'da406f31b39e0a01ee415a1ee9d2658d1fbed5ac5ceb04784dc8a25e146a60a2'
assert not (W / 'fresh-edge-inputs.json').exists()
sys.path.insert(0, str(ROOT / '.build/m0-float-fma-qualification-20261023/support'))
from m0_mpfr_oracle import Oracle, _Number
o = Oracle(); lib = o.lib; ptr = C.POINTER(_Number)
lib.mpfr_const_log2.argtypes = [ptr, C.c_int]
lib.mpfr_mul_si.argtypes = [ptr, ptr, C.c_long, C.c_int]
lib.mpfr_set_ui.argtypes = [ptr, C.c_ulong, C.c_int]
lib.mpfr_mul_2si.argtypes = [ptr, ptr, C.c_long, C.c_int]
lib.mpfr_sub.argtypes = [ptr, ptr, ptr, C.c_int]
a, b, c = _Number(), _Number(), _Number()
for n in (a, b, c): lib.mpfr_init2(C.byref(n), 256)
lib.mpfr_const_log2(C.byref(a), 0)
groups = {}
for shift in (33, 31):
    lib.mpfr_set_ui(C.byref(c), 1, 0); lib.mpfr_mul_2si(C.byref(c), C.byref(c), -shift, 0)
    for k in range(-1021, 1025):
        lib.mpfr_mul_si(C.byref(b), C.byref(a), k, 0)
        lib.mpfr_sub(C.byref(b), C.byref(b), C.byref(c), 0)
        bits = struct.unpack('<Q', struct.pack('<d', lib.mpfr_get_d(C.byref(b), 0)))[0]
        for d in (-1, 0, 1): groups.setdefault(f'{bits + d:016X}', f'fresh-ln2-minus2pow{shift}-midpoint-and-guard')
for n in (a, b, c): lib.mpfr_clear(C.byref(n))
fixed = set()
with gzip.open(S / 'probe-records.jsonl.gz', 'rt') as f:
    for line in f:
        r = json.loads(line)
        if r['instructions']['candidate'] - r['instructions']['parent'] < -1000: fixed.add(r['x'])
assert len(fixed) == 19
for x in sorted(fixed):
    for d in range(-4, 5): groups.setdefault(f'{int(x, 16) + d:016X}', 'fresh-midpoint-family-neighbour')
old = set()
for phase in ('full', 'boundary', 'power', 'edge'):
    with gzip.open(P / (phase + '-records.jsonl.gz'), 'rt') as f:
        old.update(json.loads(line)['x'] for line in f)
with gzip.open(S / 'probe-records.jsonl.gz', 'rt') as f:
    old.update(json.loads(line)['x'] for line in f)
assert len(old) == 556578
out = dict(status='PREPARED_R38_FRESH_MIDPOINT_AND_GUARD_INPUTS_NOT_ORACLES', parent_qualification_FROZEN_sha256=sha(P / 'FROZEN.json'), source_FROZEN_sha256=sha(S / 'FROZEN.json'),
    unique_inputs=len(groups), groups=groups, old556578_overlap=len(set(groups) & old), new_inputs=len(set(groups) - old), generation_precision=256,
    generation_log2_calls=1, generation_mpfr_mul_calls=4092, generation_mpfr_sub_calls=4092, generation_delta_init_shift_calls=4,
    generation_not_accuracy_validation=True, new_ARM_calls=0, hardware_accessed=False, goal_complete=False)
(W / 'fresh-edge-inputs.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps({k: v for k, v in out.items() if k != 'groups'}, indent=2), flush=True)
