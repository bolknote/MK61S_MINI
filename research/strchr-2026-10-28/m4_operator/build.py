#!/usr/bin/env python3
"""Build four ordinary SDK APP carriers against an explicit HOST template.

No physical access, firmware build or Flash programming is performed.
"""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'tests'), str(ROOT / 'tools'), str(ROOT / 'tools/.mk61-app')]
from prepare import body, pin, sha
from check_stm32_vectors import ElfImage


def load_template(path):
    template = json.loads(path.read_text())
    if template['status'] != 'HOST_TEMPLATE_NOT_A_HARDWARE_GRANT':
        raise ValueError('explicit HOST template required')
    for ref in template['generated'] + [template['resident_bin'], template['resident_elf'],
                                       template['qualified_core_build'], template['qualified_core_elf'], template['plan']]:
        if pin(Path(ref['path'])) != ref:
            raise ValueError('template dependency changed: ' + ref['path'])
    return template


def build(template_path, toolchain, output):
    template = load_template(template_path)
    spec = importlib.util.spec_from_file_location('strchr_m4_operator_app_builder', ROOT / 'tools/build_portable_app.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    original_run = builder.run
    output.mkdir(parents=True, exist_ok=False)
    apps = []
    for shared in (False, True):
        for flash in (False, True):
            mode = ('shared' if shared else 'standalone') + ('-flash' if flash else '-sram')
            folder = output / mode
            actual_commands = []

            def run(argv):
                argv = [str(x) for x in argv]
                if '-c' in argv:
                    argv += ['-DST_CODE_FLASH=' + str(int(flash))]
                    if str(RESEARCH / 'bench.c') in argv:
                        argv += ['-fno-lto']
                actual_commands.append(argv)
                return original_run(argv)

            builder.run = run
            args = argparse.Namespace(target='stm32', name='SCHR4',
                source=[HERE / 'carrier.c', RESEARCH / 'bench.c', RESEARCH / 'candidates.S',
                        template_path.parent / 'controls.S'], system=None, shared_runtime=shared,
                text_only=False, no_ui_fonts=False, local_float_math=False, local_float_math_mask=None,
                language_vm_compiler=False, split_language_vm=False,
                include=[template_path.parent, RESEARCH], library=[], output_dir=folder,
                arm_toolchain_bin=toolchain, packer=ROOT / 'tools/.mk61-app/mk61_module_pack.py',
                rustc=None, handled_magic=None)
            log = io.StringIO()
            try:
                with contextlib.redirect_stdout(log):
                    result = builder.build(args)
            finally:
                builder.run = original_run
                folder.mkdir(parents=True, exist_ok=True)
                (folder / 'build.log').write_text(log.getvalue())
                (folder / 'actual-commands.json').write_text(json.dumps(actual_commands, indent=2) + '\n')
            image = ElfImage(folder / 'SCHR4.elf')
            controls = {}
            if not flash:
                for leaf in template['leaves']:
                    name = 'st_' + leaf['name'] if leaf['name'].endswith('_control') else leaf['symbol']
                    address, code = body(image, name)
                    if len(code) != leaf['bytes'] or sha(code) != leaf['sha256']:
                        raise ValueError('APP leaf differs from qualified body: ' + name)
                    controls[name] = dict(address=address, bytes=len(code), sha256=sha(code))
            public_address, public_body = body(image, 'strchr')
            if not shared:
                expected = next(x for x in template['leaves'] if x['name'] == 'sdk_control')
                if sha(public_body) != expected['sha256']:
                    raise ValueError('real standalone public SDK strchr changed')
            if result['memory_bytes'] > 20480:
                raise ValueError('carrier exceeds the existing 20KiB APP image budget')
            apps.append(dict(mode=mode, shared_runtime=shared, code_Flash=flash,
                APP=pin(folder / 'SCHR4.APP'), ELF=pin(folder / 'SCHR4.elf'),
                actual_commands=pin(folder / 'actual-commands.json'), report=result,
                qualified_local_bodies=controls,
                public_strchr=dict(address=public_address, bytes=len(public_body), sha256=sha(public_body))))
            print(mode, result['app_bytes'], 'file bytes,', result['memory_bytes'], 'loaded bytes', flush=True)
    result = dict(status='HOST_APPS_BUILT_NOT_A_HARDWARE_GRANT', physical_IO=0,
        template=pin(template_path), apps=apps, runtime_count=26, strchr_slot=18,
        source_pins=[pin(x) for x in [HERE / 'prepare.py', HERE / 'build.py', HERE / 'carrier.c',
            RESEARCH / 'bench.c', RESEARCH / 'bench.h', RESEARCH / 'candidates.S',
            ROOT / 'sdk/portable/memory.c', ROOT / 'sdk/portable/start.c',
            ROOT / 'sdk/portable/shared_runtime.c', ROOT / 'sdk/portable/system/runtime.S',
            ROOT / 'tools/build_portable_app.py']], hardware_GO=None)
    (output / 'BUILD.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--template', type=Path, required=True)
    p.add_argument('--toolchain-bin', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    result = build(a.template, a.toolchain_bin, a.output_dir)
    print(json.dumps(dict(build=pin(a.output_dir / 'BUILD.json'), apps=len(result['apps']), physical_IO=0)))


if __name__ == '__main__':
    main()
