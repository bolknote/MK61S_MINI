from pathlib import Path
import subprocess,sys
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
C=HERE/'candidate'
sys.path.insert(0,str(ROOT))
from tools.apps.spectrum.build_spectrum_app import SOURCES
toolchain='/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin'
for name,entry,app in (
    ('profile-accepted-full-audio','tests/profile_audio_main.c','SPPIPE'),
    ('profile-accepted-paced','tests/spectrum_hil_paced.c','SPPIPE'),
    ('production-current','examples/portable-apps/SPECTRUM/main.c','SPECTRUM')):
    command=[sys.executable,str(ROOT/'tools/apps/portable/build_portable_app.py'),
             '--target','picocalc-pico-h','--shared-runtime','--name',app,
             '--arm-toolchain-bin',toolchain,'--output-dir',str(HERE/name)]
    for p in [entry]+SOURCES[1:]:command+=['--source',str(C/p)]
    with (HERE/f'{name}.log').open('w') as log:
        result=subprocess.run(command,stdout=log,stderr=log)
    print(name,result.returncode,(HERE/f'{name}.log').read_text()[-1800:],flush=True)
