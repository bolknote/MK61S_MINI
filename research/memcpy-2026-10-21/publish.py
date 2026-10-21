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
    parser.add_argument('--work', type=Path, default=ROOT / '.build/memcpy-20261021')
    parser.add_argument('--output', type=Path, default=HERE / 'evidence')
    args = parser.parse_args()
    # All three standalone measurements execute their functions from SRAM.
    sessions = [
        ('m4-standalone', 'm4-final', 'm4-app-final-hil'),
        ('m4-flash', 'm4-flash-final-app', 'm4-flash-final-hil/bench'),
        ('m4-shared', 'm4-shared-selected', 'm4-shared-selected-hil/bench'),
        ('m0-standalone', 'm0-v4', 'm0-v4-hil'),
        ('m0-shared', 'm0-v4-shared', 'm0-v4-shared-hil'),
        ('m0-before-short-fix', 'm0-final', 'm0-final-hil'),
    ]
    retained = ('recorded_at', 'status', 'cpu', 'app_sha256', 'method', 'runs', 'groups',
                'calculator_data_preserved', 'files_preserved', 'temporary_directory_removed')
    for name, build, run in sessions:
        report_path = args.work / run / 'result.json'
        report = json.loads(report_path.read_text())
        assert report['status'] == 'PASS', name
        assert all(report[k] for k in retained[-3:]), name
        app = args.work / build / 'app/COPYBEN.APP'
        assert hashlib.sha256(app.read_bytes()).hexdigest() == report['app_sha256'], name
        output = args.output / name
        output.mkdir(parents=True, exist_ok=True)
        filtered = {key: report[key] for key in retained}
        (output / 'measurements.json.gz').write_bytes(gzip.compress(
            (json.dumps(filtered, separators=(',', ':')) + '\n').encode(), mtime=0))
        for artifact in ('COPYBEN.APP', 'COPYBEN.elf'):
            shutil.copyfile(app.parent / artifact, output / artifact)
        shutil.copyfile(args.work / build / 'benchmark.json', output / 'benchmark.json')
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
        shutil.copyfile(args.work / 'm4-flash-final' / name, payload / name)
    for source, target in [
        ('production-validation-v4.json', 'production-validation.json'),
        ('runtime-validation.json', 'runtime-validation.json'),
        ('pico-firmware-validation-v4.json', 'pico-firmware-validation.json'),
        ('pico-memory-link-validation.json', 'pico-memory-link-validation.json'),
        ('code-proof-v4.json', 'code-proof.json'),
        ('qualification.json', 'qualification.json'),
    ]:
        shutil.copyfile(args.work / source, args.output / target)
    manifest = {str(path.relative_to(args.output)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(args.output.rglob('*')) if path.is_file() and path.name != 'sha256.json'}
    (args.output / 'sha256.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Published', len(manifest), 'artifacts to', args.output)


if __name__ == '__main__':
    main()
