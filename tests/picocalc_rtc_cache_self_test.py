#!/usr/bin/env python3
"""Run production RTC cache and verify hooks in the actual archived BIOS."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/firmware/picocalc'))
from bios_rtc_cache import stage_rtc_cache


def stage_test(work, folder):
    manifest = json.loads((folder / 'manifest.json').read_text())
    assert hashlib.sha256((folder/'source.zip').read_bytes()).hexdigest() == manifest['files']['source.zip']['sha256']
    with zipfile.ZipFile(folder/'source.zip') as z:
        expected = json.loads(z.read('expected.json'))
        for name in z.namelist():
            if name.startswith('source/') and not name.endswith('/'):
                assert '..' not in Path(name).parts
                data = z.read(name)
                assert hashlib.sha256(data).hexdigest() == expected['sources'][name]
                p = work / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
    source = work/'source'
    main = source/'Core/Src/main.c'
    # The packaged release will already contain the patch after integration.
    if 'bios_rtc_cache_poll();' in main.read_text():
        assert (source/'Core/Src/rtc_cache.c').read_bytes() == (ROOT/'ports/picocalc/bios/rtc_cache.c').read_bytes()
    else:
        stage_rtc_cache(source)
    text = main.read_text()
    assert text.count('bios_rtc_cache_init();') == text.count('bios_rtc_cache_poll();') == 1
    assert text.index('reg_init();') < text.index('bios_rtc_cache_init();') < text.index('HAL_I2C_EnableListen_IT')
    assert 'HAL_RTC_GetDate(&hrtc, &rtc_date._s' not in text
    assert 'HAL_RTC_GetTime(&hrtc, &rtc_time._s' not in text
    i2cs = (source/'Core/Src/i2cs.c').read_text()
    assert i2cs.count('bios_rtc_cache_changed();') == 2
    for name in ['Date', 'Time']:
        call = f'HAL_RTC_Set{name}(&hrtc, &rtc_{name.lower()}._s, RTC_FORMAT_BIN);'
        assert i2cs.index('bios_rtc_cache_changed();', i2cs.index(call)) - i2cs.index(call) < len(call)+30
    rtc = (source/'Core/Src/rtc.c').read_text()
    assert rtc.count('bios_rtc_cache_changed();') == 2
    assert 'RTC_IRQHandler' not in (source/'Core/Src/rtc_cache.c').read_text()
    assert 'RTC_IT_SEC' not in (source/'Core/Src/rtc_cache.c').read_text()
    print('RTC archived staging PASS: startup, two I2C setters, calendar load/reconciliation; no new IRQ')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--release-dir', type=Path, default=ROOT/'firmware/picocalc-m3-boot')
    args = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='mk61-rtc-cache-') as directory:
        work = Path(directory)
        stage_test(work, args.release_dir)
        binary = work/'test'
        flags = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        if os.environ.get('MK61_TEST_SANITIZERS', '1') == '0': flags = []
        subprocess.run(['clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', *flags,
            '-I'+str(ROOT/'tests/fixtures/picocalc_rtc_cache'), '-I'+str(ROOT/'ports/picocalc/bios'),
            str(ROOT/'tests/picocalc_rtc_cache_self_test.c'), str(ROOT/'ports/picocalc/bios/rtc_cache.c'),
            '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == '__main__': main()
