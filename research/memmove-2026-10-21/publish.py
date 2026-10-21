#!/usr/bin/env python3
"""Publish reproducible measurements without terminal logs or calculator data."""
import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / '.build/memmove-20261021')
    parser.add_argument('--output', type=Path, default=HERE / 'evidence')
    args = parser.parse_args()
    # Both standalone measurements execute their functions from SRAM.
    sessions = [
        ('m4-standalone', 'm4-v3-app', 'm4-v3-app-hil'),
        ('m4-short-boundary', 'm4-v3-app', 'm4-v3-short-hil'),
        ('m4-flash', 'm4-v3-flash-app', 'm4-v3-flash-hil/bench'),
        ('m4-shared', 'm4-v3-shared-app', 'm4-v3-flash-hil/shared'),
        ('m0-standalone', 'm0-final-app', 'm0-app-hil'),
        ('m0-back-boundary', 'm0-final-app', 'm0-back-boundary-hil'),
        ('m0-shared', 'm0-shared-app', 'm0-shared-hil'),
        ('m4-before-short-fix', 'm4-final-app-before-short-fix', 'm4-app-hil'),
        ('m0-before-short-fix', 'm0-final-app-before-short-fix', 'm0-scout'),
        ('m0-before-back-fix', 'm0-final-app-before-back-fix', 'm0-before-back-fix-hil'),
    ]
    retained = ('recorded_at', 'status', 'cpu', 'app_sha256', 'method', 'runs', 'groups',
                'calculator_data_preserved', 'files_preserved', 'temporary_directory_removed')
    for name, build, run in sessions:
        report_path = args.work / run / 'result.json'
        report = json.loads(report_path.read_text())
        assert report['status'] == 'PASS', name
        assert all(report[k] for k in retained[-3:]), name
        app = args.work / build / 'app/MOVEBEN.APP'
        assert hashlib.sha256(app.read_bytes()).hexdigest() == report['app_sha256'], name
        output = args.output / name
        output.mkdir(parents=True, exist_ok=True)
        filtered = {key: report[key] for key in retained}
        (output / 'measurements.json.gz').write_bytes(gzip.compress(
            (json.dumps(filtered, separators=(',', ':')) + '\n').encode(), mtime=0))
        for artifact in ('MOVEBEN.APP', 'MOVEBEN.elf'):
            shutil.copyfile(app.parent / artifact, output / artifact)
        shutil.copyfile(args.work / build / 'benchmark.json', output / 'benchmark.json')
        benchmark_source = (args.work / 'benchmark-sram-before-short-fix.c' if name=='m4-before-short-fix' else HERE / 'benchmark.c')
        shutil.copyfile(benchmark_source, output / 'benchmark.c')
        if name=='m4-before-short-fix':shutil.copyfile(args.work / 'candidates-before-short-fix.S', output / 'candidates.S')
        if name=='m0-before-short-fix':shutil.copyfile(args.work / 'candidates-before-m0-short-fix.S', output / 'candidates.S')
        if name=='m0-before-back-fix':shutil.copyfile(args.work / 'candidates-before-m0-back-fix.S', output / 'candidates.S')
        subprocess.run([sys.executable, str(HERE / 'analyze.py'), str(report_path),
                        '--output', str(output / 'summary.json')], check=True, capture_output=True)
        if name in ('m4-flash', 'm4-shared'):
            transaction = json.loads((report_path.parent.parent / 'report.json').read_text())
            assert transaction['status'] == 'PASS'
            keys = ('status', 'backup_sha256', 'installed_crc', 'restored_crc',
                    'files_preserved', 'state_preserved', 'identity_preserved')
            (output / 'restoration.json').write_text(json.dumps(
                {key: transaction[key] for key in keys}, indent=2) + '\n')
    payload = args.output / 'm4-flash/payload'
    payload.mkdir(exist_ok=True)
    for name in ('payload.bin', 'payload.elf', 'layout.json', 'validation.json', 'flash-layout.h'):
        shutil.copyfile(args.work / 'm4-v3-flash' / name, payload / name)
    for name in ('production-validation.json','m0-final-validation.json','trampoline-validation.json',
                 'pico-full-validation.json','pico-link-validation.json',
                 'code-proof.json','qualification.json'):
        shutil.copyfile(args.work / name, args.output / name)
    shutil.copyfile(args.work / 'baseline-proof/result.json', args.output / 'baseline-equivalence.json')
    manifest = {str(path.relative_to(args.output)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(args.output.rglob('*')) if path.is_file() and path.name != 'sha256.json'}
    (args.output / 'sha256.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Published', len(manifest), 'artifacts to', args.output)


if __name__ == '__main__':
    main()
