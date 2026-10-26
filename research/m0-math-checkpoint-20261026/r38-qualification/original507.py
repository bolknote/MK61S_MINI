"""Fresh MPFR and instruction measurements on one source-linked math ELF."""
from pathlib import Path
from collections import Counter
import ctypes as C
import gzip
import hashlib
import importlib.util
import json
import struct
import sys
import time

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
U = ROOT / '.build/m0-math-unified-exp-row0-midpoint-r38-20261026'
Q = ROOT / '.build/m0-float-fma-qualification-20261023'
sys.path[:0] = [str(Q), str(Q / 'support'), str(ROOT / 'tests')]
from m0_mpfr_oracle import Oracle, _Number
from oracles import equal, round_ratio
from native_eabi_m0_arm_self_test import Machine, SP

spec = importlib.util.spec_from_file_location('unified_math_machine', U / 'harness.py')
unified = importlib.util.module_from_spec(spec)
spec.loader.exec_module(unified)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(U/'FROZEN.json')=='da406f31b39e0a01ee415a1ee9d2658d1fbed5ac5ceb04784dc8a25e146a60a2'
MATRIX = ROOT / '.build/m0-asin-scaled-bound-v164-20261023/slower-inputs.json'
REF = ROOT / '.build/m0-v138-execution-20261023/reference/reference.elf'
assert sha(REF) == 'b66da3a6805ecd110580e6dd281e17c37bc4399bee0ba1fae86f8c8cf78bfc26'
assert not (W / 'original507.json').exists()
assert not (W / 'original507-records.jsonl.gz').exists()
matrix = json.loads(MATRIX.read_bytes())['rows']
assert len(matrix) == 507
operations = {
    'pow': ('_ZN12compact_math3powEdd', ['qfp_composed_pow', 'qfp_composed_pow_exact', 'qfp_composed_pow_integer']),
    'exp': ('_ZN12compact_math3expEd', ['qfp_dexp']),
    'ln': ('_ZN12compact_math2lnEd', ['qfp_dln']),
    'atan': ('_ZN12compact_math4atanEd', ['audit_atan']),
    'sin': ('_ZN12compact_math3sinEd', ['qfp_dsin']),
    'cos': ('_ZN12compact_math3cosEd', ['qfp_dcos']),
    'sqrt': ('_ZN12compact_math4sqrtEd', ['qfp_dsqrt']),
    'dadd': ('__aeabi_dadd', ['qfp_dadd']),
    'dsub': ('__aeabi_dsub', ['qfp_dsub']),
    'd2uiz': ('__aeabi_d2uiz', ['qfp_double2uint']),
    'l2d': ('__aeabi_l2d', ['qfp_int642double']),
}
states = {'READY': struct.pack('<7I', 0, 0, 0, 0, 0, 0, 1),
          'DIRTY': struct.pack('<7I', 17, 3, 17, 3, 5, 2, 3)}
machines = {n: unified.machine(n) for n in ['candidate', 'zero-control']}
machines['Qfplib'] = Machine(REF, True)
assert not machines['Qfplib'].rom_models
for label, m in machines.items():
    for op, (own, refs) in operations.items():
        for name in refs if label == 'Qfplib' else [own]:
            assert name in m.elf.symbols, (label, op, name)
o = Oracle()
lib = o.lib
pointer = C.POINTER(_Number)
lib.mpfr_set_si.argtypes = [pointer, C.c_long, C.c_int]
lib.mpfr_get_ui.argtypes = [pointer, C.c_int]
lib.mpfr_get_ui.restype = C.c_ulong
n = _Number()
lib.mpfr_init2(C.byref(n), 64)


def reference(op, x, y):
    if op == 'l2d':
        value = x - (1 << 64) if x >> 63 else x
        exact = round_ratio(abs(value), 1, 0, 64, value < 0)
        lib.mpfr_set_si(C.byref(n), value, 0)
        result = struct.unpack('<Q', struct.pack('<d', lib.mpfr_get_d(C.byref(n), 0)))[0]
        assert result == exact
        return result
    if op == 'd2uiz':
        e, f = (x >> 52) & 2047, x & ((1 << 52) - 1)
        exact = 0 if x >> 63 or e < 1023 or (e == 2047 and f) else 0xffffffff if e >= 1055 else ((1 << 52) | f) >> (1075 - e)
        value = struct.unpack('<d', struct.pack('<Q', x))[0]
        lib.mpfr_set_d(C.byref(n), value, 0)
        result = min(int(lib.mpfr_get_ui(C.byref(n), 1)), 0xffffffff)
        assert result == exact
        return result
    return o.reference(op, *([x, y] if op in ['pow', 'dadd', 'dsub'] else [x]))


def designated(row):
    if row['operation'] != 'pow':
        return operations[row['operation']][1][0]
    return ('qfp_composed_pow_exact' if row['stream'] == 'composed_exact_exponents' else
            'qfp_composed_pow_integer' if row['stream'].startswith('composed_negative_') else
            'qfp_composed_pow')


pins = {str(p.relative_to(ROOT)): sha(p) for p in [MATRIX, REF, U / 'candidate.elf', U / 'zero-control.elf',
        U / 'harness.py', U / 'link-result.json', U / 'loader-layout-proof.json', U / 'private-return-proof.json',
        U / 'private-guard-controls.json', Q / 'support/m0_mpfr_oracle.py', Q / 'support/native_eabi_m0_arm_self_test.py',
        Q / 'oracles.py', unified.ROM, Path(__file__)]}
(W / 'original507-source-pins.json').write_text(json.dumps(dict(files=pins,
    candidate_is_one_ELF_plus_real_BootROM=True, previous_loop_timing_control=True,
    no_old_firmware_or_component_overlays_loaded=True), indent=2) + '\n')
rows, case_results = [], []
completed = Counter()
attempted = Counter()
oracle_calls = shortcuts = 0
started = time.monotonic()
current = None
try:
    with gzip.GzipFile(filename=str(W / 'original507-records.jsonl.gz'), mode='wb', mtime=0) as stream:
        for index, original in enumerate(matrix):
            op, x, y = original['operation'], int(original['x'], 16), int(original['y'], 16)
            current = dict(index=index, operation=op, x=original['x'], y=original['y'])
            if index % 32 == 0:
                print('unified-original507', index, '/', len(matrix), round(time.monotonic() - started, 1), flush=True)
            expected = reference(op, x, y)
            oracle_calls += 1
            shortcuts += any((v & 0x7fffffffffffffff) > 0x7ff0000000000000 and not v & (1 << 51)
                             for v in ([x, y] if op in ['pow', 'dadd', 'dsub'] else [x])) if op not in ['l2d', 'd2uiz'] else 0
            width = 32 if op == 'd2uiz' else 64
            mask = (1 << width) - 1
            assert equal(expected, int(original['expected'], 16), width), ('historical oracle mismatch', current, hex(expected), original['expected'])
            own, refs = operations[op]
            records = []
            for state_name, sio in states.items():
                outputs, counts, correct = {}, {}, {}
                for label in ['candidate', 'zero-control', *refs]:
                    m = machines[label if label in machines else 'Qfplib']
                    m.uc.mem_write(0xd0000060, sio)
                    name = own if label in ['candidate', 'zero-control'] else label
                    attempted[label] += 1
                    got, _, cost = m.call(name, x, y, count=True)
                    completed[label] += 1
                    got &= mask
                    after = bytes(m.uc.mem_read(0xd0000060, 28))
                    if state_name == 'DIRTY':
                        assert after == sio, (label, 'DIRTY SIO changed', current)
                    else:
                        assert not struct.unpack('<7I', after)[6] & 2, (label, 'READY left DIRTY', current)
                    outputs[label], counts[label], correct[label] = f'{got:016X}', cost, equal(got, expected, width)
                    if label in ['candidate', 'zero-control']:
                        assert correct[label], ('wrong unified output', current, label, outputs[label], f'{expected:016X}')
                assert outputs['candidate'] == outputs['zero-control']
                row = dict(index=index, operation=op, stream=original['stream'], origin=original['origin'],
                           x=original['x'], y=original['y'], SIO=state_name, expected=f'{expected:016X}',
                           result_width=width, historical_reference=designated(original),
                           outputs=outputs, instructions=counts, correct=correct)
                records.append(row)
                rows.append(row)
                stream.write((json.dumps(row, separators=(',', ':')) + '\n').encode())
            case_results.append(dict(index=index, operation=op, stream=original['stream'], x=original['x'], y=original['y'],
                historical_reference=designated(original),
                historical_reference_correct=all(r['correct'][designated(original)] for r in records),
                historical_classification=('slower' if any(r['instructions']['candidate'] > r['instructions'][designated(original)] for r in records)
                    else 'equal' if any(r['instructions']['candidate'] == r['instructions'][designated(original)] for r in records) else 'strict'),
                every_correct_reference_classification=('slower' if any(r['correct'][q] and r['instructions']['candidate'] > r['instructions'][q] for r in records for q in refs)
                    else 'equal' if any(r['correct'][q] and r['instructions']['candidate'] == r['instructions'][q] for r in records for q in refs) else 'strict')))
except Exception as error:
    failure = dict(status='FAILED_UNIFIED_ORIGINAL507_ATTEMPT', error=repr(error), current=current,
                   completed_ARM_calls=dict(completed), attempted_ARM_calls=dict(attempted),
                   partial_ARM_calls=sum(attempted.values()) - sum(completed.values()),
                   completed_oracle_evaluations=oracle_calls, sNaN_policy_shortcuts=shortcuts,
                   last_completed_rows=rows[-3:], no_failed_calls_in_qualified_totals=True,
                   elapsed_seconds=time.monotonic() - started, hardware_accessed=False, goal_complete=False)
    (W / 'original507-FAILURE.json').write_text(json.dumps(failure, indent=2) + '\n')
    raise
finally:
    lib.mpfr_clear(C.byref(n))

groups = {}
for op in operations:
    selected = [c for c in case_results if c['operation'] == op]
    rs = [r for r in rows if r['operation'] == op]
    comparisons = Counter()
    wrong = 0
    for r in rs:
        for ref in operations[op][1]:
            if not r['correct'][ref]:
                wrong += 1
                continue
            c, q = r['instructions']['candidate'], r['instructions'][ref]
            comparisons['faster' if c < q else 'equal' if c == q else 'slower'] += 1
    groups[op] = dict(cases=len(selected), state_rows=len(rs),
        historical_reference_classification=dict(Counter(c['historical_classification'] for c in selected)),
        every_correct_reference_classification=dict(Counter(c['every_correct_reference_classification'] for c in selected)),
        correct_Qfplib_comparison=dict(comparisons), wrong_Qfplib_outputs_costs_retained=wrong)
assert len(rows) == 1014 and len(case_results) == 507
assert all(c['historical_reference_correct'] for c in case_results)
result = dict(status='PASS_UNIFIED_ORIGINAL507_RNE_AND_FRESH_INSTRUCTION_QUALIFICATION',
    candidate_ELF_sha256=sha(U / 'candidate.elf'), zero_control_ELF_sha256=sha(U / 'zero-control.elf'),
    matrix_sha256=sha(MATRIX), reference_ELF_sha256=sha(REF), raw_records_sha256=sha(W / 'original507-records.jsonl.gz'),
    original_cases=507, states=1014, candidate_wrong=0, zero_control_wrong=0,
    completed_ARM_calls=dict(completed), actual_qualified_math_ARM_calls=sum(completed.values()),
    automatic_ROM_lookup_initializations_excluded=2, explicit_source_loader_calls_excluded=2,
    MPFR_version=o.version, oracle_evaluations=oracle_calls, actual_directed_MPFR_inputs=oracle_calls-shortcuts,
    sNaN_policy_shortcuts=shortcuts, integer_conversions_also_checked_with_exact_integer_oracle=True,
    historical_reference_classification=dict(Counter(c['historical_classification'] for c in case_results)),
    every_correct_reference_classification=dict(Counter(c['every_correct_reference_classification'] for c in case_results)),
    candidate_minus_zero_control_instruction_deltas=dict(Counter(r['instructions']['candidate']-r['instructions']['zero-control'] for r in rows)),
    groups=groups, cases=case_results, observed_stacks={label:SP-m.stack_lowest for label,m in machines.items()},
    single_ELF_candidate_no_overlays=True, all_correct_references_compared=True,
    all_incorrect_reference_outputs_and_costs_retained=True, no_nominal_reference_domain_filter=True,
    PCS_SP_bounded_writes_and_SIO_checked_every_call=True, instructions_are_not_physical_cycles=True,
    broad_regressions_and_totality_pending=True, integration_GO=False, canonical_or_M4_changed=False,
    elapsed_seconds=time.monotonic()-started, hardware_accessed=False, goal_complete=False)
(W / 'original507.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k:v for k,v in result.items() if k!='cases'}, indent=2), flush=True)
