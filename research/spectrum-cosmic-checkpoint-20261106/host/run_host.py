from pathlib import Path
import os, subprocess, sys
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
C=HERE/'candidate'
sys.path.insert(0,str(ROOT))
from tools.apps.spectrum.build_spectrum_app import SOURCES
core=[str(C/p) for p in SOURCES[1:]]
flags=['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-DMK61_TARGET_PICOCALC=1',
       '-fsanitize=address,undefined','-fno-omit-frame-pointer',
       '-I'+str(ROOT/'sdk/portable/include'),'-I'+str(ROOT/'code')]
env=dict(os.environ,ASAN_OPTIONS='detect_stack_use_after_return=1')
with (HERE/'presentation-tests.log').open('w') as log:
    for name in ('presentation_stats_self_test','pipeline_scheduler_self_test','profile_audio_self_test'):
        exe=HERE/name
        subprocess.run(flags+[str(C/'tests'/f'{name}.c')]+core+['-o',str(exe)],check=True,stdout=log,stderr=log)
        args=[str(exe)]
        if name=='presentation_stats_self_test':args.append(str(HERE/'presentation-wire.txt'))
        subprocess.run(args,check=True,stdout=log,stderr=log,env=env)
print((HERE/'presentation-tests.log').read_text())
