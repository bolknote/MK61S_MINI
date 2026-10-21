#!/usr/bin/env python3
"""Publish selected completed sessions without private device state or backups."""
import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path
from analyze import analyze

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / '.build/memcmp-20261021')
    parser.add_argument('--manifest', type=Path, required=True,
                        help='JSON with sessions [{name,build,run}] and receipt paths relative to work')
    parser.add_argument('--output', type=Path, default=HERE / 'evidence')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    keep = ('recorded_at', 'status', 'cpu', 'app_sha256', 'method', 'runs', 'groups',
            'calculator_data_preserved', 'files_preserved', 'temporary_directory_removed')
    args.output.mkdir(parents=True, exist_ok=True)
    for session in manifest['sessions']:
        report = json.loads((args.work / session['run'] / 'result.json').read_text())
        assert report['status'] == 'PASS', session['name']
        assert all(report[k] for k in keep[-3:]), session['name']
        build = args.work / session['build']
        app = build / 'app/CMPBEN.APP'
        assert hashlib.sha256(app.read_bytes()).hexdigest() == report['app_sha256'], session['name']
        destination = args.output / session['name']
        destination.mkdir(exist_ok=True)
        filtered = {key: report[key] for key in keep}
        (destination / 'measurements.json.gz').write_bytes(gzip.compress(
            (json.dumps(filtered, separators=(',', ':')) + '\n').encode(), mtime=0))
        (destination / 'summary.json').write_text(json.dumps(analyze(filtered, session.get('candidate', 'sdk')), indent=2) + '\n')
        for name in ('CMPBEN.APP', 'CMPBEN.elf'):
            shutil.copyfile(app.parent / name, destination / name)
        shutil.copyfile(build / 'benchmark.json', destination / 'benchmark.json')
        for name in ('benchmark.c', 'candidates.S', 'baseline-memory.h'):
            source = build / name
            assert source.is_file(), ('Freeze source beside each build before measuring', source)
            shutil.copyfile(source, destination / name)
        if 'flash_transaction' in session:
            transaction = json.loads((args.work / session['flash_transaction'] / 'report.json').read_text())
            assert transaction['status'] == 'PASS'
            keys = ('status', 'backup_sha256', 'installed_crc', 'restored_crc',
                    'files_preserved', 'state_preserved', 'identity_preserved')
            (destination / 'restoration.json').write_text(json.dumps(
                {key: transaction[key] for key in keys}, indent=2) + '\n')
    for filename in manifest.get('receipts', []):
        source = args.work / filename
        shutil.copyfile(source, args.output / source.name)
    payloads = manifest.get('payloads', [])
    if manifest.get('payload'):
        payloads = payloads + [dict(build=manifest['payload'], name='flash-payload')]
    for payload in payloads:
        source = args.work / payload['build']
        destination = args.output / payload['name']
        destination.mkdir(exist_ok=True)
        for name in ('payload.bin', 'payload.elf', 'layout.json', 'validation.json', 'flash-layout.h'):
            shutil.copyfile(source / name, destination / name)
    hashes = {str(path.relative_to(args.output)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(args.output.rglob('*')) if path.is_file() and path.name != 'sha256.json'}
    (args.output / 'sha256.json').write_text(json.dumps(hashes, indent=2) + '\n')
    print('Published', len(hashes), 'artifacts to', args.output)


if __name__ == '__main__':
    main()
