#!/usr/bin/env python3
"""Check the portable saved HOST evidence; no toolchain, ports or absolute paths needed."""
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    report = json.loads((HERE / 'RESULTS-HOST.json').read_text())
    assert report['physical_IO'] == 0 and report['hardware_winner'] is None
    for item in report['evidence'] + report['sources']:
        path = ROOT / item['path']
        data = path.read_bytes()
        assert len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256'], path

    def read(name):
        return json.loads(gzip.decompress((HERE / 'evidence' / (name + '.json.gz')).read_bytes()))

    core, apps, build, plan = (read(n) for n in ['core-results', 'app-results', 'core-build', 'plan'])
    assert core['total_calls'] == 620640 == sum(r['calls'] for r in core['results'])
    assert sum(r['rejected_invalid_ARM_read_write_probes'] for r in core['results']) == 18
    assert apps['total_checks'] == 77760 == sum(r['checks'] for r in apps['results'])
    assert len(apps['results']) == 16 and apps['total_runtime18_calls'] == 31581
    assert sum(r['synthetic_bench_search_calls'] for r in apps['results']) == 4263
    assert sum(r['synthetic_bench_runs'] for r in apps['results']) == 87
    assert sum(r['negative_checks'] for r in apps['results']) == 108
    assert len(plan['cases']) == plan['case_count'] == 1152
    assert sum(c['operand_bank'] == 'SRAM' for c in plan['cases']) == 576
    for c in plan['cases']:
        text = bytes.fromhex(c['text_hex'])
        assert text[-1] == 0 and len(text) == c['text_bytes']
        assert text.find(bytes([c['character'] & 255])) == c['expected_offset']
    for row in apps['results']:
        if 1 <= row['variant'] <= 6:
            name = ['byte1', 'byte4', 'word1', 'word2', 'dsp1', 'dsp2'][row['variant'] - 1] + '_strchr'
            product = next(x for x in build['products'] if x['arch'] == row['arch'] and x['placement'] == 'sram')
            assert row['strchr_sha256'] == product['bodies'][name]['sha256']
    print('strchr saved evidence: SHA, 620640 ARM calls, 16 packed APPs, actual slot18, bench wiring and 1152 planned cases PASS')


if __name__ == '__main__':
    main()
