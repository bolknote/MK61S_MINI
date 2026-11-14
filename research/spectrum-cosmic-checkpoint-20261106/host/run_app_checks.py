from pathlib import Path
import os,subprocess,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent;C=HERE/'candidate'
sys.path.insert(0,str(ROOT))
from tools.apps.spectrum.build_spectrum_app import SOURCES
flags=['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-DMK61_TARGET_PICOCALC=1',
       '-fsanitize=address,undefined','-fno-omit-frame-pointer',
       '-I'+str(ROOT/'sdk/portable/include'),'-I'+str(ROOT/'code')]
core=[str(C/p) for p in SOURCES[1:] if not p.endswith('/ui.c')]
env=dict(os.environ,ASAN_OPTIONS='detect_stack_use_after_return=1')
with (HERE/'app-current-tests.log').open('w') as log:
    exe=HERE/'app-current-test'
    subprocess.run(flags+[str(C/'tests/spectrum_app_self_test.c')]+core+['-o',str(exe)],check=True,stdout=log,stderr=log)
    for mode in ('','xip','mismatch'):
        args=[str(exe),str(HERE.parent/'cosmic-profile/cpu-hot-layout/app-assets')]+([mode] if mode else [])
        subprocess.run(args,check=True,stdout=log,stderr=log,env=env)
print((HERE/'app-current-tests.log').read_text())
