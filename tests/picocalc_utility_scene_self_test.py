#!/usr/bin/env python3
"""Actual ZX0 decoder and native animation raster under ASan/UBSan."""
from pathlib import Path
import hashlib,json,os,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
def main():
    subprocess.run(['python3',str(ROOT/'dev/tools/generate_picocalc_utility_art.py'),'--check'],check=True)
    with tempfile.TemporaryDirectory(prefix='pico-utility-test-') as tmp:
        folder=Path(tmp);binary=folder/'test'
        subprocess.run(['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror',
            '-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(ROOT/'code'),'-I'+str(ROOT/'ports/picocalc'),
            str(ROOT/'tests/picocalc_utility_scene_self_test.cpp'),str(ROOT/'code/zx0.cpp'),'-o',str(binary)],check=True)
        subprocess.run([str(binary),str(folder)],check=True,env={**os.environ,'UBSAN_OPTIONS':'halt_on_error=1'})
        manifest=json.loads((ROOT/'doc/picocalc-utility/manifest.json').read_text())
        for name,record in manifest.items():
            raw=(folder/(name+'.raw')).read_bytes()
            assert len(raw)==record['raw_bytes'] and hashlib.sha256(raw).hexdigest()==record['raw_sha256'],name
    print('Native artwork: all illustrations and EN/RU banners match generator SHA256 PASS')
if __name__=='__main__':main()
