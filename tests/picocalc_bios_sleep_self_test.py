#!/usr/bin/env python3
"""Exercise production M3 sleep and Pico handshake with ASan/UBSan."""
from pathlib import Path
import argparse,json,sys,zipfile
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/firmware/picocalc'))
from bios_sleep import stage_bios_sleep
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--release-dir',type=Path,default=ROOT/'firmware/picocalc-m3-boot')
args=p.parse_args()
with tempfile.TemporaryDirectory(prefix='m3-sleep-') as folder:
    folder=Path(folder)
    with zipfile.ZipFile(args.release_dir/'source.zip') as z:
        for name in z.namelist():
            if name.startswith('source/') and not name.endswith('/'):
                assert '..' not in Path(name).parts
                target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
    staged=folder/'source'
    if 'bios_sleep_requested()' not in (staged/'Core/Src/main.c').read_text():stage_bios_sleep(staged)
    for name in ['bios_sleep.h','bios_sleep.c']:
        target=staged/'Core'/('Inc' if name.endswith('.h') else 'Src')/name
        assert target.read_bytes()==(ROOT/'ports/picocalc/bios'/name).read_bytes()
    main=(staged/'Core/Src/main.c').read_text();wire=(staged/'Core/Src/i2cs.c').read_text()
    assert main.count('bios_sleep_poll(!pwr_off_active && !stop_mode_active && coproc_storage_idle());')==1
    assert main.index('coproc_poll();')<main.index('bios_sleep_poll(')
    assert 'if (is_write) bios_sleep_write(i2cs_r_buff[1]);' in wire
    assert 'reg == BIOS_SLEEP_REG ||' in wire and 'bios_sleep_status();' in wire
    print('M3 archived sleep hooks PASS: one foreground boundary, real I2C read/write and module/power guards')
    binary=folder/'m3-test'
    subprocess.run(['clang','-std=c11','-O2','-Wall','-Wextra','-Werror',
        '-fsanitize=address,undefined','-fno-sanitize-recover=all',
        '-I'+str(ROOT/'tests/fixtures/picocalc_bios_sleep'),'-I'+str(ROOT/'ports/picocalc/bios'),
        str(ROOT/'tests/picocalc_bios_sleep_self_test.c'),str(ROOT/'ports/picocalc/bios/bios_sleep.c'),
        '-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
    text=(ROOT/'ports/picocalc/hardware.cpp').read_text()
    start=text.index('bool Keyboard::request_register(')
    end=text.index('void Keyboard::clock_changed(',start)
    fixture=(ROOT/'tests/picocalc_bios_sleep_poll_self_test.cpp').read_text()
    source=folder/'pico-test.cpp'
    source.write_text(fixture.replace('// ACTUAL_KEYBOARD_POLL',text[start:end]))
    binary=folder/'pico-test'
    subprocess.run(['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',
        '-DMK61_CORE_STANDALONE=1','-fsanitize=address,undefined','-fno-sanitize-recover=all',
        '-I'+str(ROOT/'ports/picocalc'),'-I'+str(ROOT/'code'),str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
