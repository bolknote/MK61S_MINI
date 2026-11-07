#!/usr/bin/env python3
"""Rebuild frozen HOST backends in a new directory; never perform device I/O."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args, cwd=None):
    subprocess.run([str(x) for x in args], cwd=cwd, check=True, timeout=1800)


def compile_backend(folder):
    source = folder / 'source'
    run('clang', '-std=c11', '-O2', '-ffp-contract=off', '-fPIC', '-c',
        source/'mk61_ai_kernels.c', '-o', folder/'kernels.o')
    run('clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fPIC', '-shared',
        '-I'+str(source), *[source/x for x in ['mk61_ai_model.cpp', 'mk61_ai_linear.cpp',
        'mk61_ai_tokenizer.cpp', 'probe.cpp']], folder/'kernels.o', '-o', folder/'quality-probe.dylib')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--workdir', type=Path, required=True, help='new directory; existing paths are rejected')
    ap.add_argument('--model-dir', type=Path, required=True, help='local frozen model.mka and model-nibble.mka')
    ap.add_argument('--metrics', choices=['none','calibration','audit','both'], default='none')
    ap.add_argument('--functional', action='store_true', help='rerun 1175 cases for each of three profiles')
    a = ap.parse_args()
    if a.metrics != 'none':
        try:
            import numpy  # Required for logit metrics, not the default kernel/generation checks.
        except ImportError:
            ap.error('The selected Python needs numpy for --metrics; use your numerical Python environment.')
    inventory = json.loads((HERE/'publication-manifest.json').read_text())['files']
    for name, digest in inventory.items():
        assert sha(HERE/name) == digest, 'Changed published artifact '+name
    external = json.loads((HERE/'external-model.json').read_text())
    for name in ['model.mka', 'model-nibble.mka']:
        assert sha(a.model_dir/name) == external['files'][name]['sha256'], 'Wrong checkpoint '+name
    work = a.workdir.resolve(); work.mkdir(exist_ok=False)
    # Inputs are copied, not mutated in the publication directory.
    for folder in ['source','runtime','weights-source','emulator/core-source']:
        shutil.copytree(HERE/folder, work/folder)
    for name in ['engine.py','evaluate.py','metrics.py','probes13.json','profiles.json',
                 'metric-calibration.json','metric-audit.json','selected-for-audit.json',
                 'integer_kernel_test.cpp']:
        shutil.copyfile(HERE/name, work/name)
    shutil.copytree(HERE/'model', work/'model')
    for name in ['model.mka','model-nibble.mka']:
        shutil.copyfile(a.model_dir/name, work/'model'/name)
    for item in json.loads((HERE/'archives.json').read_text()):
        dst = work/item['path'][:-3]; dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(gzip.decompress((HERE/item['path']).read_bytes()))
        assert sha(dst) == item['uncompressed_sha256']
    candidate = work/'candidate'
    shutil.copytree(HERE/'candidate/source', candidate/'source')
    for folder in ['model','runtime','emulator','cases']:
        shutil.copytree(work/folder, candidate/folder)
    for name in ['engine.py','evaluate.py','verify.py','probes13.json','profiles.json']:
        shutil.copyfile(HERE/'candidate'/name, candidate/name)
    compile_backend(work);compile_backend(candidate)
    # Independent int64 oracle, not a second spelling of the optimized loop.
    run('clang', '-std=c11', '-O1', '-g', '-fsanitize=address,undefined',
        '-c', candidate/'source/mk61_ai_kernels.c', '-o', work/'checked-kernels.o')
    run('clang++', '-std=c++17', '-O1', '-g', '-fsanitize=address,undefined',
        '-fno-omit-frame-pointer', '-ffp-contract=off', '-I'+str(candidate/'source'),
        work/'integer_kernel_test.cpp', candidate/'source/mk61_ai_linear.cpp',
        work/'checked-kernels.o', '-o', work/'integer-kernel-test')
    run(work/'integer-kernel-test')
    run(sys.executable, '-B', candidate/'verify.py')
    metric_runs = []
    for split in (['calibration','audit'] if a.metrics=='both' else ([] if a.metrics=='none' else [a.metrics])):
        profile_ids = list(map(int,json.loads((work/'profiles.json').read_text()))) if split=='calibration' else json.loads((work/'selected-for-audit.json').read_text())
        for profile in profile_ids:
            run(sys.executable, '-B', work/'metrics.py', '--worker', profile, split)
        metric_runs.append(split)
    if a.functional:
        # Archive rows are the historical result, distinct from this replay.
        for mode in ['lut-fp32','int16','a16-head-fp32']:
            (candidate/('run-'+mode)).rename(candidate/('historical-'+mode))
            run(sys.executable, '-B', candidate/'evaluate.py', '--worker', mode)
        def rows(mode):
            return {(r['suite'],r['id']):r for r in map(json.loads,
                    (candidate/('run-'+mode)/'results.jsonl').read_text().splitlines())}
        base = rows('lut-fp32'); paired = {}
        historical = {(r['suite'],r['id']):r for r in map(json.loads,
                     (candidate/'historical-lut-fp32/results.jsonl').read_text().splitlines())}
        assert base.keys() == historical.keys()
        assert all(r['passed'] == historical[k]['passed'] for k,r in base.items()), 'Baseline replay changed'
        for mode in ['int16','a16-head-fp32']:
            new = rows(mode);assert new.keys() == base.keys()
            lost = [list(k) for k,r in base.items() if r['passed'] and not new[k]['passed']]
            fd0 = sum(r.get('false_done',False) for r in base.values())
            fd1 = sum(r.get('false_done',False) for r in new.values())
            paired[mode] = dict(lost=lost,false_done=fd1,gate_passed=not lost and fd1<=fd0)
            assert paired[mode]['gate_passed'], 'Functional nonregression gate failed '+mode
        (candidate/'replayed-paired-report.json').write_text(json.dumps(paired,indent=2)+'\n')
    result = dict(status='PASS', hardware_io=False, rebuilt_source=True, checked_kernel_rows=48000,
                  compact_backend_generations=65, metrics=metric_runs, functional=a.functional,
                  backend_sha256=sha(work/'quality-probe.dylib'),
                  candidate_sha256=sha(candidate/'quality-probe.dylib'))
    (work/'replay-report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
