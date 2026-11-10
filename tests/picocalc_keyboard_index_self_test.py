#!/usr/bin/env python3
"""Compare actual archived/indexed keyboard C states and GPIO traces; no devices."""
from pathlib import Path
import hashlib
import importlib.util
import subprocess
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/picocalc_keyboard'
spec=importlib.util.spec_from_file_location('keyboard_index',ROOT/'tools/firmware/picocalc/bios_keyboard_index.py')
stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)
PUBLIC=['keyboard_set_key_callback','keyboard_set_lock_callback','keyboard_get_capslock','keyboard_get_numlock',
        'keyboard_get_hold_period','keyboard_set_hold_period','keyboard_get_shift','keyboard_get_alt',
        'keyboard_process','keyboard_reset','io_matrix','js_bits','probe_snapshot']
with tempfile.TemporaryDirectory(prefix='picocalc-keyboard-')as temporary:
    work=Path(temporary);baseline=work/'baseline';candidate=work/'candidate'
    with zipfile.ZipFile(ROOT/'firmware/picocalc-southbridge/source.zip')as archive:
        for name in archive.namelist():
            if name.startswith('source/Core/Inc/')or name=='source/Core/Src/keyboard.c':
                path=baseline/Path(name).relative_to('source')
                if name.endswith('/'):continue
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.read(name))
    original=(baseline/'Core/Src/keyboard.c').read_bytes()
    p=candidate/'Core/Src/keyboard.c';p.parent.mkdir(parents=True);p.write_bytes(original)
    delta=stage.stage_keyboard_index(candidate)
    assert delta['keyboard_GPIO_reads_per_scan']==152 and delta['keyboard_index_persistent_RAM_bytes']==0
    indexed=p.read_bytes()
    assert hashlib.sha256(indexed).hexdigest()=='f6dc61f828dc8e168ab7c01ea978269d0df2cb1763fcc07cdf25b85605482afb'
    for unknown in (indexed,original+b'\n'):
        p.write_bytes(unknown)
        try:stage.stage_keyboard_index(candidate)
        except ValueError:pass
        else:raise AssertionError('Unknown/already-patched input accepted')
        assert p.read_bytes()==unknown
    p.write_bytes(indexed)
    flags=['-std=c11','-funsigned-char','-fgnu89-inline','-O2','-Wall','-Wextra','-Werror',
           '-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer',
           '-I'+str(FIXTURE),'-I'+str(baseline/'Core/Inc')]
    objects=[]
    for prefix,root in [('ref',baseline),('new',candidate)]:
        source=work/(prefix+'.c');source.write_text((root/'Core/Src/keyboard.c').read_text()+(FIXTURE/'probe.inc').read_text())
        output=work/(prefix+'.o');objects.append(output)
        subprocess.run(['clang',*flags,*['-D'+name+'='+prefix+'_'+name for name in PUBLIC],'-c',str(source),'-o',str(output)],check=True)
    binary=work/'keyboard-test'
    subprocess.run(['clang',*flags,str(FIXTURE/'keyboard_equivalence.c'),*map(str,objects),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
print('Keyboard index: exact tested C, unknown source rejection, ASan/UBSan and ordered state/GPIO/callback equivalence PASS')
