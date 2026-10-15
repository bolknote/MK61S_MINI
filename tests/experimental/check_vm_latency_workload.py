#!/usr/bin/env python3
"""Check real latency fixtures with both arithmetic VMs and the native cache."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--execute', type=Path, nargs=2, required=True)
    parser.add_argument('--replay', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.corpus / 'manifest.json').read_text())
    executed = []
    for executable in args.execute:
        for item in manifest['modules'] + manifest['auxiliary']:
            if item.get('kind') == 'ESC':
                continue  # The intentionally long loop is stopped only by HIL.
            name = item.get('name', Path(item['filename']).stem)
            image = args.corpus / 'images' / (name + '-owned.bvm')
            mode = 'input' if item.get('kind') == 'INPUT' else 'normal'
            output = subprocess.check_output([executable, image, item['tag'], mode], text=True)
            assert output.endswith('execution exact PASS\n'), output
            executed.append(dict(vm=str(executable), image=str(image),
                                 sha256=hashlib.sha256(image.read_bytes()).hexdigest()))
    modules = manifest['modules']
    ids = {module['name']: index + 1 for index, module in enumerate(modules)}
    order = manifest['order'] * manifest['cycles']
    rows = [f'3 0 {len(order)} {len(modules)} {len(order)}']
    for module in modules:
        image = (args.corpus / 'images' / (module['name'] + '-owned.bvm')).resolve()
        language = 1 if module['language'] == 'basic' else 2
        rows.append(f'{ids[module["name"]]} {language} {json.dumps(str(image))}')
    rows.append(' '.join(str(ids[name]) for name in order))
    replay = json.loads(subprocess.check_output([args.replay], input='\n'.join(rows) + '\n', text=True))
    assert replay['status'] == 'PASS'
    assert {(v['budget'], v['mixed']) for v in replay['variants']} == {
        (24576, False), (24576, True), (32768, False)}
    assert len(replay['variants']) == 3
    for variant in replay['variants']:
        assert variant['budget'] == variant['object_bytes']
        assert len(variant['passes']) == 3
        for result in variant['passes']:
            assert result['fallback'] == 0, result
            assert result['hits'] + result['misses'] == len(order), result
    result = dict(status='PASS', corpus=str(args.corpus), executions=executed, replay=replay)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('Both arithmetic VMs and native guarded raw/mixed cache PASS', args.corpus)
    print(json.dumps(replay))


if __name__ == '__main__':
    main()
